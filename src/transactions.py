"""Транзакции и очередь."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from .enums import AuditEvent, OperationAction, RiskReason, SecurityReason, RiskLevel
from .audit import AuditLevel, RiskBlockedError
from .enums import AccountStatus, AccountType, Currency, TransactionStatus, TransactionType

from .utils import (
    InvalidOperationError,
    check_amount,
    check_rate,
    check_text,
    check_enum,
    check_currency,
)


def check_time(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidOperationError("Укажите datetime с часовым поясом.")
    return value.astimezone(timezone.utc)


class Transaction:
    def __init__(self, client_id, sender_number, recipient_number, amount,
                 currency=Currency.RUB, transaction_type=TransactionType.INTERNAL_TRANSFER,
                 recipient_bank=None, created_at=None):
        self.client_id = check_text(client_id)
        self.sender_number = check_text(sender_number)
        self.recipient_number = check_text(recipient_number)
        self.amount = check_amount(amount)
        if self.amount == 0:
            raise InvalidOperationError("Сумма перевода должна быть больше нуля.")
        self.currency = check_currency(currency)
        transaction_type = check_enum(transaction_type, TransactionType)

        self.transaction_id = uuid4().hex
        self.transaction_type = transaction_type
        self.recipient_bank = recipient_bank
        self.commission = Decimal("0.00")
        self.received_amount = None
        self.received_currency = None
        self.conversion_rate = None
        self.status = TransactionStatus.CREATED
        self.failure_reason = None
        self.risk_level = None
        self.risk_reasons = []
        self.attempts = 0
        self.priority = 0
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        self.created_at = check_time(created_at)
        self.updated_at = self.created_at
        self.started_at = None
        self.completed_at = None
        self.execute_at = None
        self.next_attempt_at = None


class TransactionQueue:
    def __init__(self, now=None):
        self._transactions = []
        self._clock = now

    def current_time(self):
        if self._clock is None:
            return datetime.now(timezone.utc)
        return check_time(self._clock())

    def add(self, transaction, priority=0, execute_at=None):
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError("Передайте объект Transaction.")
        if type(priority) != int:
            raise InvalidOperationError("Приоритет должен быть целым числом.")
        if transaction.status != TransactionStatus.CREATED:
            raise InvalidOperationError("Транзакция уже добавлена или обработана.")
        for existing in self._transactions:
            if existing.transaction_id == transaction.transaction_id:
                raise InvalidOperationError("Транзакция уже есть в очереди.")
        if execute_at is not None:
            execute_at = check_time(execute_at)

        transaction.priority = priority
        transaction.execute_at = execute_at
        transaction.status = TransactionStatus.PENDING
        transaction.updated_at = self.current_time()
        self._transactions.append(transaction)
        return transaction.transaction_id

    def cancel(self, transaction_id):
        for transaction in self._transactions:
            if transaction.transaction_id == transaction_id:
                if transaction.status not in [TransactionStatus.PENDING, TransactionStatus.RETRY_PENDING]:
                    raise InvalidOperationError("Транзакцию уже нельзя отменить.")
                current = self.current_time()
                transaction.status = TransactionStatus.CANCELLED
                transaction.updated_at = current
                transaction.completed_at = current
                transaction.next_attempt_at = None
                return transaction
        raise InvalidOperationError("Транзакция не найдена.")

    def get_next(self):
        current = self.current_time()
        selected = None
        for transaction in self._transactions:
            if transaction.status not in [TransactionStatus.PENDING, TransactionStatus.RETRY_PENDING]:
                continue
            if transaction.execute_at is not None and transaction.execute_at > current:
                continue
            if transaction.next_attempt_at is not None and transaction.next_attempt_at > current:
                continue
            if selected is None or transaction.priority > selected.priority:
                selected = transaction

        if selected is not None:
            selected.status = TransactionStatus.PROCESSING
            selected.started_at = current
            selected.updated_at = current
        return selected


class TemporaryTransactionError(InvalidOperationError):
    """Временная ошибка до списания: операцию можно повторить позже."""


class TransactionProcessor:
    def __init__(self, bank, queue, exchange_rates=None,
                 external_commission=10, max_attempts=3, retry_delay=60,
                 external_available=None):
        if type(max_attempts) != int or max_attempts < 1:
            raise InvalidOperationError("Количество попыток должно быть от 1.")
        if type(retry_delay) != int or retry_delay < 1:
            raise InvalidOperationError("Задержка повтора должна быть от 1 секунды.")
        self.bank = bank
        self.queue = queue
        self.external_commission = check_amount(external_commission)
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.external_available = external_available
        self.errors = []
        self.exchange_rates = {}
        if exchange_rates is None:
            exchange_rates = {}
        if type(exchange_rates) != dict:
            raise InvalidOperationError("Курсы должны быть словарём.")
        for pair, rate in exchange_rates.items():
            if type(pair) != tuple or len(pair) != 2:
                raise InvalidOperationError("Ключ курса — пара валют.")
            pair = (check_currency(pair[0]), check_currency(pair[1]))
            self.exchange_rates[pair] = check_rate(rate)

    def _execute(self, transaction):
        external = transaction.transaction_type == TransactionType.EXTERNAL_TRANSFER
        target_bank = transaction.recipient_bank
        if external:
            if target_bank is None or target_bank is self.bank:
                raise InvalidOperationError("Для внешнего перевода нужен другой Bank.")
            if self.external_available is not None and not self.external_available():
                raise TemporaryTransactionError("Внешний банк временно недоступен.")
        else:
            if target_bank is not None and target_bank is not self.bank:
                raise InvalidOperationError("Другой банк требует external_transfer.")
            target_bank = self.bank

        fee = self.external_commission if external else Decimal("0.00")
        return self.bank.transfer(
            transaction.client_id, transaction.sender_number,
            transaction.recipient_number, transaction.amount,
            transaction.currency, target_bank, fee, self.exchange_rates,
            transaction_id=transaction.transaction_id,
        )

    def process_ready(self):
        processed = []
        while True:
            transaction = self.queue.get_next()
            if transaction is None:
                break
            transaction.attempts += 1
            try:
                result = self._execute(transaction)
            except Exception as error:
                # Сохраняем и ожидаемые отказы, и непредвиденные ошибки.
                current = self.queue.current_time()
                transaction.failure_reason = str(error)
                if isinstance(error, RiskBlockedError):
                    transaction.risk_level = check_enum(error.assessment["level"], RiskLevel)
                    transaction.risk_reasons = error.assessment["reasons"]
                else:
                    assessments = self.bank.audit_log.filter(
                        event=AuditEvent.RISK_ASSESSED, transaction_id=transaction.transaction_id
                    )
                    if assessments:
                        transaction.risk_level = check_enum(assessments[-1]["risk_level"], RiskLevel)
                        transaction.risk_reasons = [check_enum(reason, RiskReason) for reason in assessments[-1]["details"]["reasons"]]
                self.errors.append({
                    "transaction_id": transaction.transaction_id,
                    "attempt": transaction.attempts,
                    "time": current,
                    "error_type": type(error).__name__,
                    "reason": str(error),
                })
                if isinstance(error, TemporaryTransactionError) and transaction.attempts < self.max_attempts:
                    transaction.status = TransactionStatus.RETRY_PENDING
                    transaction.next_attempt_at = current + timedelta(seconds=self.retry_delay)
                else:
                    transaction.status = TransactionStatus.FAILED
                    transaction.completed_at = current
                    transaction.next_attempt_at = None
                transaction.updated_at = current
                self.bank.audit_log.record(
                    AuditEvent.TRANSACTION_RETRY if transaction.status == TransactionStatus.RETRY_PENDING else AuditEvent.TRANSACTION_FAILED,
                    AuditLevel.ERROR, transaction.client_id, transaction.transaction_id,
                    transaction.risk_level,
                    {"error_type": type(error).__name__, "reason": str(error),
                     "attempt": transaction.attempts, "status": transaction.status},
                    current,
                )
            else:
                transaction.commission = result["commission"]
                transaction.received_amount = result["received_amount"]
                transaction.received_currency = check_currency(result["received_currency"])
                transaction.conversion_rate = result["conversion_rate"]
                transaction.risk_level = check_enum(result["risk_level"], RiskLevel)
                transaction.risk_reasons = result["risk_reasons"]
                transaction.status = TransactionStatus.COMPLETED
                transaction.failure_reason = None
                transaction.next_attempt_at = None
                transaction.completed_at = self.queue.current_time()
                transaction.updated_at = transaction.completed_at
            processed.append(transaction)
        return processed


def demo_transactions():
    """Десять операций: успехи, отказы, отмена, отсрочка и повтор."""
    from .models import Bank, Client

    current = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    bank = Bank(now=lambda: current)
    other_bank = Bank(now=lambda: current)
    sender_client = Client("Иван", 25, {"phone": "123"})
    recipient_client = Client("Анна", 25, {"phone": "456"})
    external_client = Client("Мария", 25, {"phone": "789"})
    for target, client in [(bank, sender_client), (bank, recipient_client),
                           (other_bank, external_client)]:
        target.add_client(client, "transaction-demo-password")
        target.authenticate_client(client.client_id, "transaction-demo-password")

    sender = bank.open_account(sender_client.client_id, balance=5000)
    premium = bank.open_account(sender_client.client_id, AccountType.PREMIUM)
    savings = bank.open_account(sender_client.client_id, AccountType.SAVINGS, balance=100, min_balance=80)
    frozen_sender = bank.open_account(sender_client.client_id, balance=100, status=AccountStatus.FROZEN)
    recipient = bank.open_account(recipient_client.client_id)
    usd_recipient = bank.open_account(recipient_client.client_id, currency=Currency.USD)
    frozen_recipient = bank.open_account(recipient_client.client_id, status=AccountStatus.FROZEN)
    external_recipient = other_bank.open_account(external_client.client_id)

    queue = TransactionQueue(now=lambda: current)
    external_online = False
    processor = TransactionProcessor(
        bank, queue, exchange_rates={(Currency.RUB, Currency.USD): "0.01"},
        external_available=lambda: external_online,
    )
    transactions = [
        Transaction(sender_client.client_id, sender.account_number, recipient.account_number, 100, created_at=current),
        Transaction(sender_client.client_id, sender.account_number, usd_recipient.account_number, 100, created_at=current),
        Transaction(sender_client.client_id, sender.account_number, recipient.account_number, 10000, created_at=current),
        Transaction(sender_client.client_id, sender.account_number, frozen_recipient.account_number, 10, created_at=current),
        Transaction(sender_client.client_id, frozen_sender.account_number, recipient.account_number, 10, created_at=current),
        Transaction(sender_client.client_id, premium.account_number, recipient.account_number, 100, created_at=current),
        Transaction(sender_client.client_id, sender.account_number, recipient.account_number, 10, created_at=current),
        Transaction(sender_client.client_id, sender.account_number, recipient.account_number, 25, created_at=current),
        Transaction(sender_client.client_id, sender.account_number, external_recipient.account_number,
                    50, transaction_type=TransactionType.EXTERNAL_TRANSFER, recipient_bank=other_bank, created_at=current),
        Transaction(sender_client.client_id, savings.account_number, recipient.account_number, 30, created_at=current),
    ]
    for index, transaction in enumerate(transactions):
        execute_at = current + timedelta(minutes=2) if index == 7 else None
        priority = 10 if index == 1 else 0
        queue.add(transaction, priority=priority, execute_at=execute_at)
    queue.cancel(transactions[6].transaction_id)

    print("\nДень 4: очередь из 10 транзакций, условный курс 1 RUB = 0.01 USD")
    first_batch = processor.process_ready()
    print("Первой обработана приоритетная операция:", first_batch[0] is transactions[1])
    print("После первого прохода:", [item.status.value for item in transactions])
    external_online = True
    current += timedelta(minutes=1)
    processor.process_ready()
    current += timedelta(minutes=1)
    processor.process_ready()

    for index, transaction in enumerate(transactions, 1):
        print(f"{index}: {transaction.status}, попыток: {transaction.attempts}, "
              f"комиссия: {transaction.commission}, отказ: {transaction.failure_reason}")
    print("Свободные остатки банка:", bank.get_total_balance())
    print("Ошибок в журнале процессора:", len(processor.errors))
    return bank, transactions, processor
