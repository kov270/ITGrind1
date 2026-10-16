from abc import ABC, abstractmethod
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .enums import AuditEvent, OperationAction, RiskReason, SecurityReason, RiskLevel
from .audit import AuditLevel, AuditLog, RiskAnalyzer, RiskBlockedError, RiskLevel

from .utils import check_amount, check_text, check_asset, check_growth_rates
from .utils import check_balance, round_money
from .utils import check_age, check_contacts, check_enum, check_currency
from .enums import AccountStatus, AccountType, AssetType, ClientStatus, Currency
from .utils import create_password_hash, verify_password
from .utils import (AccountFrozenError, AccountClosedError,
                     InvalidOperationError, InsufficientFundsError, check_rate)


class Client:
    def __init__(self, full_name, age, contacts, status=ClientStatus.ACTIVE):
        full_name = check_text(full_name)
        age = check_age(age)
        contacts = check_contacts(contacts)
        status = check_enum(status, ClientStatus)

        self.client_id = uuid4().hex
        self.full_name = full_name
        self.age = age
        self.contacts = contacts
        self.status = status
        self.account_numbers = []


class AbstractAccount(ABC):
    def __init__(self, account_id, owner, balance, account_number, status):
        # Сохраняем данные, подготовленные конкретным классом.
        self.account_id = account_id
        self.account_number = account_number
        self.owner = owner
        self._balance = balance
        self.status = status
        # Для счетов, открытых через Bank, здесь будет проверка доступа и времени.
        self._bank_guard = None

    @abstractmethod
    def deposit(self, amount):
        """Конкретный тип счёта должен реализовать пополнение."""
        pass

    @abstractmethod
    def withdraw(self, amount):
        """Конкретный тип счёта должен реализовать снятие."""
        pass

    @abstractmethod
    def get_account_info(self):
        """Конкретный тип счёта должен возвращать сведения о счёте."""
        pass



class BankAccount(AbstractAccount):
    def __init__(self, owner, balance=0, account_number=None,
                 status=AccountStatus.ACTIVE, currency=Currency.RUB, withdraw_limit=100_000):
        owner = check_text(owner)
        balance = check_amount(balance)
        status = check_enum(status, AccountStatus)
        if status == AccountStatus.CLOSED and balance != 0:
            raise InvalidOperationError("Закрытый счёт должен иметь нулевой баланс.")
        currency = check_currency(currency)

        # ID сохраняем целиком, для номера берём 12 цифр из числового UUID.
        account_uuid = uuid4()
        account_id = account_uuid.hex
        if account_number is None:
            account_number = str(account_uuid.int % 10**12).zfill(12)
        else:
            account_number = check_text(account_number)
        if len(account_number) != 12:
            raise InvalidOperationError("Номер счёта должен содержать ровно 12 цифр.")
        if not account_number.isascii() or not account_number.isdigit():
            raise InvalidOperationError("Номер счёта может содержать только цифры 0–9.")


        super().__init__(account_id, owner, balance, account_number, status)
        self.currency = currency
        withdraw_limit = check_amount(withdraw_limit)

        if withdraw_limit == 0:
            raise InvalidOperationError("Лимит снятия должен быть больше нуля.")

        self.withdraw_limit = withdraw_limit

    def check_status(self):
        if self._bank_guard is not None:
            self._bank_guard()
        if self.status == AccountStatus.FROZEN:
            raise AccountFrozenError("Счёт заморожен.")
        if self.status == AccountStatus.CLOSED:
            raise AccountClosedError("Счёт закрыт.")
        if self.status != AccountStatus.ACTIVE:
            raise InvalidOperationError("Неизвестный статус счёта.")

    def deposit(self, amount):
        self.check_status()
        amount = check_amount(amount)
        if amount == 0:
            raise InvalidOperationError("Сумма пополнения должна быть больше нуля.")
        self._balance = check_balance(self._balance + amount)
        return self._balance

    def withdraw(self, amount):
        self.check_status()
        amount = check_amount(amount)
        if amount == 0:
            raise InvalidOperationError("Сумма снятия должна быть больше нуля.")
        if amount > self._balance:
            raise InsufficientFundsError("Недостаточно средств.")
        if amount > self.withdraw_limit:
            raise InvalidOperationError("Превышен лимит снятия средств.")
        self._balance -= amount
        return self._balance

    def get_account_info(self):
        return {
            "account_id": self.account_id,
            "account_number": self.account_number,
            "owner": self.owner,
            "balance": self._balance,
            "status": self.status.value,
            "currency": self.currency.value,
            "withdraw_limit": self.withdraw_limit,
        }

    def __str__(self):
        return (f"BankAccount | {self.owner} | ****{self.account_number[-4:]} | "
                f"{self.status} | {self._balance:.2f} {self.currency}")

class SavingsAccount(BankAccount):
    def __init__(self, owner, balance=0, account_number=None,
                 status=AccountStatus.ACTIVE, currency=Currency.RUB, monthly_rate="0.01", min_balance=0):
        super().__init__(owner, balance, account_number,
                 status, currency)
        min_balance = check_amount(min_balance)
        monthly_rate = check_rate(monthly_rate)

        if self._balance < min_balance:
            raise InvalidOperationError("Баланс ниже минимального остатка.")

        self.monthly_rate = monthly_rate
        self.min_balance = min_balance

    def withdraw(self, amount):
        self.check_status()
        amount = check_amount(amount)
        if amount > self._balance:
            raise InsufficientFundsError("Недостаточно средств.")
        if self._balance - amount < self.min_balance:
            raise InvalidOperationError(
                "После снятия баланс будет ниже минимального остатка."
            )
        return super().withdraw(amount)

    def get_account_info(self):
        info = super().get_account_info()
        info["monthly_rate"] = self.monthly_rate
        info["min_balance"] = self.min_balance
        return info

    def apply_monthly_interest(self):
        self.check_status()
        interest = round_money(self._balance * self.monthly_rate)
        if interest == 0:
            return self._balance
        return self.deposit(interest)

    def __str__(self):
        return (
            f"SavingsAccount | {self.owner} | "
            f"****{self.account_number[-4:]} | "
            f"{self.status} | {self._balance:.2f} {self.currency} | "
            f"ставка: {self.monthly_rate * 100}% в месяц | "
            f"минимальный остаток: {self.min_balance:.2f} {self.currency}"
        )

class PremiumAccount(BankAccount):
    def __init__(self, owner, balance=0, account_number=None,
                 status=AccountStatus.ACTIVE, currency=Currency.RUB, withdraw_limit=500_000,
                 overdraft_limit=5000, overdraft_commission=500):
        super().__init__(owner, balance, account_number,
                         status, currency, withdraw_limit)

        self.overdraft_limit = check_amount(overdraft_limit)
        self.overdraft_commission = check_amount(overdraft_commission)

    def withdraw(self, amount):
        self.check_status()
        amount = check_amount(amount)

        if amount == 0:
            raise InvalidOperationError("Сумма должна быть больше нуля.")

        if amount > self.withdraw_limit:
            raise InvalidOperationError("Превышен лимит снятия.")

        new_balance = self._balance - amount

        if new_balance < 0:
            new_balance -= self.overdraft_commission

        if new_balance < -self.overdraft_limit:
            raise InsufficientFundsError("Превышен лимит овердрафта.")

        self._balance = check_balance(new_balance)
        return self._balance

    def get_account_info(self):
        info = super().get_account_info()
        info["overdraft_limit"] = self.overdraft_limit
        info["overdraft_commission"] = self.overdraft_commission
        return info

    def __str__(self):
        return (f"PremiumAccount | {self.owner} | ****{self.account_number[-4:]} | "
                f"{self.status} | {self._balance:.2f} {self.currency}")


class InvestmentAccount(BankAccount):
    def __init__(self, owner, balance=0, account_number=None,
                 status=AccountStatus.ACTIVE, currency=Currency.RUB, withdraw_limit=100_000):
        super().__init__(owner, balance, account_number, status, currency,
                         withdraw_limit)
        self.portfolio = {
            AssetType.STOCKS: Decimal("0.00"),
            AssetType.BONDS: Decimal("0.00"),
            AssetType.ETF: Decimal("0.00"),
        }

    def invest(self, asset, amount):
        self.check_status()
        asset = check_asset(asset)
        amount = check_amount(amount)

        if amount == 0:
            raise InvalidOperationError("Сумма инвестиции должна быть больше нуля.")
        if amount > self._balance:
            raise InsufficientFundsError("Недостаточно средств для инвестиции.")

        new_asset_balance = self.portfolio[asset] + amount
        new_asset_balance = check_amount(new_asset_balance)
        self._balance -= amount
        self.portfolio[asset] = new_asset_balance
        return self.portfolio[asset]

    def withdraw(self, amount):
        # Снимаем только свободные деньги, портфель не продаём.
        return super().withdraw(amount)

    def project_yearly_growth(self, growth_rates):
        growth_rates = check_growth_rates(growth_rates)
        growth = Decimal("0")
        for asset, amount in self.portfolio.items():
            if amount > 0:
                if asset not in growth_rates:
                    raise InvalidOperationError(f"Не указана ставка для {asset}.")
                growth += amount * growth_rates[asset]

        # Возвращаем ожидаемый доход, не начисляем его на счёт.
        return round_money(growth)

    def get_account_info(self):
        info = super().get_account_info()
        info["portfolio"] = {asset.value: amount for asset, amount in self.portfolio.items()}
        return info

    def __str__(self):
        return (f"InvestmentAccount | {self.owner} | ****{self.account_number[-4:]} | "
                f"{self.status} | {self._balance:.2f} {self.currency} | "
                f"портфель: {self.get_account_info()['portfolio']}")


class Bank:
    def __init__(self, now=None, audit_log=None, risk_analyzer=None):
        self.bank_id = uuid4().hex
        self.clients = {}
        self.accounts = {}
        self._passwords = {}
        self._login_attempts = {}
        self._authenticated_clients = set()
        self._security_events = []
        # now — функция времени для демонстрации и проверки границ интервала.
        self._clock = now
        self._timezone = timezone(timedelta(hours=5, minutes=30), "Asia/Colombo")
        if audit_log is None:
            path = Path(__file__).resolve().parent.parent / "logs" / f"audit-{self.bank_id}.jsonl"
            audit_log = AuditLog(path)
        self.audit_log = audit_log
        self.risk_analyzer = risk_analyzer if risk_analyzer is not None else RiskAnalyzer()

    def _current_time(self):
        if self._clock is None:
            return datetime.now(self._timezone)
        current = self._clock()
        if current.tzinfo is None:
            return current.replace(tzinfo=self._timezone)
        return current.astimezone(self._timezone)

    @property
    def suspicious_actions(self):
        # Возвращаем копии записей, чтобы просмотр не изменял журнал банка.
        return [event.copy() for event in self._security_events]

    def _record_security_event(self, client_id, action, reason,
                               account_number=None):
        action = check_enum(action, OperationAction)
        reason = check_enum(reason, SecurityReason)
        self._security_events.append({
            "time": self._current_time().isoformat(),
            "client_id": client_id,
            "action": action.value,
            "reason": reason.value,
            "account_number": account_number,
        })
        high = reason in [SecurityReason.NIGHT_OPERATION, SecurityReason.CLIENT_BLOCKED, SecurityReason.BLOCKED_CLIENT]
        self.audit_log.record(
            AuditEvent.SECURITY_EVENT, AuditLevel.CRITICAL if high else AuditLevel.WARNING,
            client_id=client_id,
            risk_level=RiskLevel.HIGH if high else RiskLevel.MEDIUM,
            details={"action": action.value, "reason": reason.value, "account_number": account_number},
            timestamp=self._current_time(),
        )

    def _check_operation(self, client_id, action, account_number=None):
        client = self._get_client(client_id)
        if self._current_time().hour < 5:
            self._record_security_event(
                client_id, action, SecurityReason.NIGHT_OPERATION, account_number
            )
            raise InvalidOperationError(
                "Операции запрещены с 00:00 до 05:00 по времени Asia/Colombo."
            )
        return client

    def add_client(self, client, password):
        if not isinstance(client, Client):
            raise InvalidOperationError("Передайте объект Client.")
        if client.client_id in self.clients:
            raise InvalidOperationError("Клиент уже зарегистрирован.")
        if client.account_numbers:
            raise InvalidOperationError("У нового клиента список счетов должен быть пустым.")

        password_data = create_password_hash(password)
        self.clients[client.client_id] = client
        self._passwords[client.client_id] = password_data
        self._login_attempts[client.client_id] = 0
        self.audit_log.record(AuditEvent.CLIENT_ADDED, client_id=client.client_id,
                              timestamp=self._current_time())
        return client.client_id

    def authenticate_client(self, client_id, password):
        if client_id not in self.clients:
            self._record_security_event(client_id, OperationAction.LOGIN, SecurityReason.UNKNOWN_CLIENT)
            return False
        client = self.clients[client_id]
        if client.status != ClientStatus.ACTIVE:
            self._authenticated_clients.discard(client_id)
            self._record_security_event(client_id, OperationAction.LOGIN, SecurityReason.BLOCKED_CLIENT)
            return False

        salt, password_hash = self._passwords[client_id]
        if verify_password(password, salt, password_hash):
            self._login_attempts[client_id] = 0
            self._authenticated_clients.add(client_id)
            self.audit_log.record(AuditEvent.LOGIN_SUCCESS, client_id=client_id,
                                  timestamp=self._current_time())
            return True

        self._authenticated_clients.discard(client_id)
        self._login_attempts[client_id] += 1
        self._record_security_event(client_id, OperationAction.LOGIN, SecurityReason.WRONG_PASSWORD)
        if self._login_attempts[client_id] >= 3:
            client.status = ClientStatus.BLOCKED
            self._record_security_event(client_id, OperationAction.LOGIN, SecurityReason.CLIENT_BLOCKED)
        return False

    def _get_client(self, client_id):
        if client_id not in self.clients:
            self._record_security_event(client_id, OperationAction.ACCESS, SecurityReason.UNKNOWN_CLIENT)
            raise InvalidOperationError("Клиент не найден.")
        client = self.clients[client_id]
        if client.status != ClientStatus.ACTIVE:
            self._record_security_event(client_id, OperationAction.ACCESS, SecurityReason.BLOCKED_CLIENT)
            raise InvalidOperationError("Клиент заблокирован.")
        if client_id not in self._authenticated_clients:
            self._record_security_event(client_id, OperationAction.ACCESS, SecurityReason.NOT_AUTHENTICATED)
            raise InvalidOperationError("Сначала выполните вход.")
        return client

    def _get_account(self, client_id, account_number):
        client = self._get_client(client_id)
        if account_number not in client.account_numbers:
            self._record_security_event(
                client_id, OperationAction.ACCOUNT_ACCESS, SecurityReason.FOREIGN_OR_UNKNOWN_ACCOUNT,
                account_number,
            )
            raise InvalidOperationError("Счёт не принадлежит клиенту.")
        return self.accounts[account_number]

    def open_account(self, client_id, account_type=AccountType.BANK, **options):
        client = self._check_operation(client_id, OperationAction.OPEN_ACCOUNT)
        account_types = {
            AccountType.BANK: BankAccount,
            AccountType.SAVINGS: SavingsAccount,
            AccountType.PREMIUM: PremiumAccount,
            AccountType.INVESTMENT: InvestmentAccount,
        }
        account_type = check_enum(account_type, AccountType)
        if account_type not in account_types:
            raise InvalidOperationError("Неизвестный тип счёта.")
        if "owner" in options:
            raise InvalidOperationError("Владелец определяется по клиенту.")
        if check_enum(options.get("status", AccountStatus.ACTIVE), AccountStatus) == AccountStatus.CLOSED:
            raise InvalidOperationError("Нельзя открыть сразу закрытый счёт.")

        account_class = account_types[account_type]
        account = account_class(owner=client.full_name, **options)
        if account.account_number in self.accounts:
            if options.get("account_number") is not None:
                raise InvalidOperationError("Номер счёта уже занят.")
            while account.account_number in self.accounts:
                account.account_number = str(uuid4().int % 10**12).zfill(12)

        self.accounts[account.account_number] = account
        client.account_numbers.append(account.account_number)

        def guard():
            self._get_account(client_id, account.account_number)
            self._check_operation(
                client_id, OperationAction.ACCOUNT_OPERATION, account.account_number
            )

        # Проверка сработает и при прямом account.withdraw()/deposit()/invest().
        account._bank_guard = guard
        self.audit_log.record(
            AuditEvent.ACCOUNT_OPENED, client_id=client_id,
            details={"account_number": account.account_number, "type": account_type},
            timestamp=self._current_time(),
        )
        return account

    def close_account(self, client_id, account_number):
        account = self._get_account(client_id, account_number)
        self._check_operation(client_id, OperationAction.CLOSE_ACCOUNT, account_number)
        account.check_status()
        if account.get_account_info()["balance"] != 0:
            raise InvalidOperationError("Для закрытия нужен нулевой баланс.")
        if isinstance(account, InvestmentAccount):
            for amount in account.portfolio.values():
                if amount != 0:
                    raise InvalidOperationError("Для закрытия нужен пустой портфель.")
        # Сохраняем закрытый счёт и его принадлежность для истории.
        account.status = AccountStatus.CLOSED
        self.audit_log.record(AuditEvent.ACCOUNT_CLOSED, client_id=client_id,
                              details={"account_number": account_number},
                              timestamp=self._current_time())

    def freeze_account(self, client_id, account_number):
        account = self._get_account(client_id, account_number)
        self._check_operation(client_id, OperationAction.FREEZE_ACCOUNT, account_number)
        account.check_status()
        account.status = AccountStatus.FROZEN
        self.audit_log.record(AuditEvent.ACCOUNT_FROZEN, client_id=client_id,
                              details={"account_number": account_number},
                              timestamp=self._current_time())

    def unfreeze_account(self, client_id, account_number):
        account = self._get_account(client_id, account_number)
        self._check_operation(client_id, OperationAction.UNFREEZE_ACCOUNT, account_number)
        if account.status == AccountStatus.CLOSED:
            raise AccountClosedError("Закрытый счёт нельзя разморозить.")
        if account.status != AccountStatus.FROZEN:
            raise InvalidOperationError("Счёт не заморожен.")
        account.status = AccountStatus.ACTIVE
        self.audit_log.record(AuditEvent.ACCOUNT_UNFROZEN, client_id=client_id,
                              details={"account_number": account_number},
                              timestamp=self._current_time())

    def search_accounts(self, client_id, account_number=None, status=None):
        client = self._get_client(client_id)
        if status is not None:
            status = check_enum(status, AccountStatus)

        result = []
        for number in client.account_numbers:
            account = self.accounts[number]
            if account_number is not None and number != account_number:
                continue
            if status is not None and account.status != status:
                continue
            result.append(account.get_account_info())
        return result

    def transfer(self, client_id, sender_number, recipient_number, amount,
                 currency, recipient_bank=None, commission=0,
                 exchange_rates=None, transaction_id=None):
        """Перевод в памяти: все проверки выполняются до изменения балансов."""
        sender = self._get_account(client_id, sender_number)
        amount = check_amount(amount)
        commission = check_amount(commission)
        if amount == 0:
            raise InvalidOperationError("Сумма перевода должна быть больше нуля.")
        if check_currency(currency) != sender.currency:
            raise InvalidOperationError("Валюта перевода должна совпадать с валютой отправителя.")
        if amount > sender.withdraw_limit:
            raise InvalidOperationError("Превышен лимит операции.")

        if recipient_bank is None:
            recipient_bank = self
        if not isinstance(recipient_bank, Bank):
            raise InvalidOperationError("Получатель должен находиться в Bank.")
        if recipient_number not in recipient_bank.accounts:
            raise InvalidOperationError("Счёт получателя не найден.")
        recipient = recipient_bank.accounts[recipient_number]
        if sender is recipient:
            raise InvalidOperationError("Нельзя перевести деньги на тот же счёт.")
        if transaction_id is None:
            transaction_id = uuid4().hex
        current = self._current_time()
        assessment = self.risk_analyzer.analyze(
            client_id, recipient_bank.bank_id + ":" + recipient_number,
            amount, sender.currency, current, transaction_id,
        )
        severity = {RiskLevel.LOW.value: AuditLevel.INFO,
                    RiskLevel.MEDIUM.value: AuditLevel.WARNING,
                    RiskLevel.HIGH.value: AuditLevel.CRITICAL}
        self.audit_log.record(
            AuditEvent.RISK_ASSESSED, severity[assessment["level"]], client_id,
            transaction_id, assessment["level"], assessment, current,
        )
        if assessment["level"] == RiskLevel.HIGH:
            raise RiskBlockedError(assessment)
        sender.check_status()
        if recipient.status == AccountStatus.FROZEN:
            raise AccountFrozenError("Счёт получателя заморожен.")
        if recipient.status == AccountStatus.CLOSED:
            raise AccountClosedError("Счёт получателя закрыт.")
        if recipient.status != AccountStatus.ACTIVE:
            raise InvalidOperationError("Неизвестный статус получателя.")
        if recipient_bank._current_time().hour < 5:
            recipient_bank._record_security_event(
                client_id, OperationAction.RECEIVE_TRANSFER, SecurityReason.NIGHT_OPERATION, recipient_number
            )
            raise InvalidOperationError("Банк получателя не проводит операции с 00:00 до 05:00.")

        # Получателю не нужно входить для получения денег, но блокировку проверяем.
        for client in recipient_bank.clients.values():
            if recipient_number in client.account_numbers and client.status != ClientStatus.ACTIVE:
                raise InvalidOperationError("Клиент-получатель заблокирован.")

        if not isinstance(sender, PremiumAccount) and sender._balance < 0:
            raise InsufficientFundsError("Перевод с отрицательного баланса запрещён.")
        sender_balance = sender._balance - amount - commission
        if isinstance(sender, PremiumAccount):
            if sender_balance < 0:
                commission += sender.overdraft_commission
                sender_balance -= sender.overdraft_commission
            if sender_balance < -sender.overdraft_limit:
                raise InsufficientFundsError("Превышен лимит овердрафта.")
        else:
            if sender_balance < 0:
                raise InsufficientFundsError("Недостаточно средств с учётом комиссии.")
            if isinstance(sender, SavingsAccount) and sender_balance < sender.min_balance:
                raise InvalidOperationError("Перевод нарушит минимальный остаток.")

        rate = Decimal("1")
        if sender.currency != recipient.currency:
            pair = (sender.currency, recipient.currency)
            if exchange_rates is None or pair not in exchange_rates:
                raise InvalidOperationError("Не задан курс для пары валют.")
            rate = check_rate(exchange_rates[pair])
        received_amount = round_money(amount * rate)
        if received_amount == 0:
            raise InvalidOperationError("После конвертации получится нулевая сумма.")

        sender_balance = check_balance(sender_balance)
        recipient_balance = check_balance(recipient._balance + received_amount)
        result = {
            "commission": commission,
            "received_amount": received_amount,
            "received_currency": recipient.currency.value,
            "conversion_rate": rate,
            "risk_level": assessment["level"],
            "risk_reasons": assessment["reasons"],
        }
        # В однопоточном приложении после этих расчётов нет отказных проверок.
        sender._balance = sender_balance
        recipient._balance = recipient_balance
        self.risk_analyzer.mark_completed(assessment)
        self.audit_log.record(
            AuditEvent.TRANSFER_COMPLETED, client_id=client_id, transaction_id=transaction_id,
            risk_level=assessment["level"],
            details={"sender_number": sender_number, "recipient_number": recipient_number,
                     "amount": amount, "currency": sender.currency, **result},
            timestamp=current,
        )
        return result

    def get_total_balance(self):
        """Свободные остатки банка по валютам, включая задолженность."""
        totals = {}
        for account in self.accounts.values():
            currency = account.currency
            if currency not in totals:
                totals[currency.value] = Decimal("0.00")
            totals[currency.value] += account.get_account_info()["balance"]
        return totals

    def get_clients_ranking(self, currency=Currency.RUB):
        """Рейтинг всех клиентов по свободному балансу выбранной валюты."""
        currency = check_currency(currency)

        ranking = []
        for client in self.clients.values():
            balance = Decimal("0.00")
            for number in client.account_numbers:
                account = self.accounts[number]
                if account.currency == currency:
                    balance += account.get_account_info()["balance"]
            ranking.append({
                "client_id": client.client_id,
                "full_name": client.full_name,
                "balance": balance,
                "currency": currency.value,
            })

        ranking.sort(key=lambda client: client["balance"], reverse=True)
        return ranking
