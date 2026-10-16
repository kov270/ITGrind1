"""Аудит и объяснимые правила риска для банка."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .enums import AuditEvent, OperationAction, RiskReason, SecurityReason, RiskLevel
from .utils import InvalidOperationError, check_amount, check_text, check_currency, check_enum
from .enums import (AuditLevel, RiskLevel, Currency, RiskReason, AuditEvent,
                    AccountStatus)


class RiskBlockedError(InvalidOperationError):
    def __init__(self, assessment):
        self.assessment = deepcopy(assessment)
        super().__init__("Операция заблокирована: " + ", ".join(assessment["reasons"]))


class AuditLog:
    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self._records = []
        self.file_errors = []
        if self.file_path.exists():
            with self.file_path.open(encoding="utf-8") as source:
                for line in source:
                    if line.strip():
                        self._records.append(json.loads(line))

    def record(self, event, level=AuditLevel.INFO, client_id=None,
               transaction_id=None, risk_level=None, details=None, timestamp=None):
        event = check_enum(event, AuditEvent)
        level = check_enum(level, AuditLevel)
        if risk_level is not None:
            risk_level = check_enum(risk_level, RiskLevel).value
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        entry = {
            "time": timestamp.isoformat(),
            "event": event.value,
            "level": level.value,
            "client_id": client_id,
            "transaction_id": transaction_id,
            "risk_level": risk_level,
            "details": deepcopy(details) if details is not None else {},
            "persisted": True,
        }
        # JSONL: одна запись — одна строка. Decimal сохраняем точной строкой.
        serialized = json.dumps(entry, ensure_ascii=False, default=str)
        entry = json.loads(serialized)
        self._records.append(entry)
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("a", encoding="utf-8") as target:
                target.write(serialized + "\n")
        except OSError as error:
            # Ошибка диска не должна превращать уже выполненный перевод в failed.
            entry["persisted"] = False
            self.file_errors.append({"time": entry["time"], "reason": str(error)})
        return deepcopy(entry)

    def filter(self, level=None, client_id=None, transaction_id=None,
               event=None, risk_level=None, since=None, until=None):
        for boundary in [since, until]:
            if boundary is not None:
                if not isinstance(boundary, datetime) or boundary.tzinfo is None:
                    raise InvalidOperationError("Граница времени требует datetime с часовым поясом.")
        if since is not None and until is not None and since > until:
            raise InvalidOperationError("Начало интервала позже конца.")
        if level is not None:
            level = check_enum(level, AuditLevel).value
        if risk_level is not None:
            risk_level = check_enum(risk_level, RiskLevel).value
        if event is not None:
            event = check_enum(event, AuditEvent).value
        result = []
        for entry in self._records:
            if level is not None and entry["level"] != level:
                continue
            if client_id is not None and entry["client_id"] != client_id:
                continue
            if transaction_id is not None and entry["transaction_id"] != transaction_id:
                continue
            if event is not None and entry["event"] != event:
                continue
            if risk_level is not None and entry["risk_level"] != risk_level:
                continue
            timestamp = datetime.fromisoformat(entry["time"])
            if since is not None and timestamp < since:
                continue
            if until is not None and timestamp > until:
                continue
            result.append(deepcopy(entry))
        return result

    def suspicious_operations(self, client_id=None):
        result = []
        for entry in self.filter(client_id=client_id):
            if entry["event"] in [AuditEvent.RISK_ASSESSED, AuditEvent.SECURITY_EVENT]:
                if entry["risk_level"] in [RiskLevel.MEDIUM.value, RiskLevel.HIGH.value]:
                    result.append(entry)
        return result

    def error_statistics(self, client_id=None):
        counts = {}
        total = 0
        for entry in self.filter(client_id=client_id):
            error_type = entry["details"].get("error_type")
            if error_type is not None:
                counts[error_type] = counts.get(error_type, 0) + 1
                total += 1
        return {"total_errors": total, "by_type": counts,
                "file_errors": len(self.file_errors)}


class RiskAnalyzer:
    def __init__(self, large_amounts=None, window_seconds=60,
                 frequent_count=10, warning_count=5):
        if large_amounts is None:
            large_amounts = {Currency.RUB: 100000, Currency.USD: 1000, Currency.EUR: 1000,
                             Currency.KZT: 500000, Currency.CNY: 10000}
        if type(large_amounts) != dict:
            raise InvalidOperationError("Пороги сумм должны быть словарём валют.")
        self.large_amounts = {}
        for currency, amount in large_amounts.items():
            currency = check_currency(currency)
            amount = check_amount(amount)
            if amount == 0:
                raise InvalidOperationError("Порог суммы должен быть положительным.")
            self.large_amounts[currency] = amount
        if type(window_seconds) != int or window_seconds < 1:
            raise InvalidOperationError("Окно частоты должно быть от 1 секунды.")
        if type(warning_count) != int or type(frequent_count) != int:
            raise InvalidOperationError("Пороги частоты должны быть целыми.")
        if not 1 <= warning_count < frequent_count:
            raise InvalidOperationError("Порог предупреждения должен быть меньше блокировки.")
        self.window_seconds = window_seconds
        self.frequent_count = frequent_count
        self.warning_count = warning_count
        self._history = []
        self._known_recipients = {}

    def analyze(self, client_id, recipient_key, amount, currency, now,
                transaction_id):
        amount = check_amount(amount)
        currency = check_currency(currency)
        if currency not in self.large_amounts:
            raise InvalidOperationError("Не задан порог риска для валюты.")
        score = 0
        reasons = []
        threshold = self.large_amounts[currency]
        if amount >= threshold:
            score += 3
            reasons.append(RiskReason.LARGE_AMOUNT)
        elif amount >= threshold / 2:
            score += 1
            reasons.append(RiskReason.ELEVATED_AMOUNT)

        cutoff = now - timedelta(seconds=self.window_seconds)
        count = 1
        for previous in self._history:
            if previous["client_id"] == client_id:
                if cutoff < previous["time"] <= now and previous["transaction_id"] != transaction_id:
                    count += 1
        if count >= self.frequent_count:
            score += 3
            reasons.append(RiskReason.FREQUENT_OPERATIONS)
        elif count >= self.warning_count:
            score += 1
            reasons.append(RiskReason.ELEVATED_FREQUENCY)

        if recipient_key not in self._known_recipients.get(client_id, set()):
            score += 1
            reasons.append(RiskReason.NEW_RECIPIENT)
        if now.hour < 5:
            score += 3
            reasons.append(RiskReason.NIGHT_OPERATION)

        if score >= 3:
            level = RiskLevel.HIGH
        elif score > 0:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW
        assessment = {
            "client_id": client_id,
            "transaction_id": transaction_id,
            "recipient_key": recipient_key,
            "time": now,
            "amount": amount,
            "currency": currency,
            "score": score,
            "level": level,
            "reasons": reasons,
            "operations_in_window": count,
            "completed": False,
        }
        # Повтор одной транзакции обновляет оценку, а не создаёт новую операцию.
        self._history = [item for item in self._history
                         if item["transaction_id"] != transaction_id]
        self._history.append(assessment)
        return deepcopy(assessment)

    def mark_completed(self, assessment):
        client_id = assessment["client_id"]
        if client_id not in self._known_recipients:
            self._known_recipients[client_id] = set()
        self._known_recipients[client_id].add(assessment["recipient_key"])
        for item in self._history:
            if item["transaction_id"] == assessment["transaction_id"]:
                item["completed"] = True

    def client_profile(self, client_id):
        assessments = [item for item in self._history if item["client_id"] == client_id]
        counts = {level.value: 0 for level in RiskLevel}
        reasons = {}
        completed = 0
        for item in assessments:
            counts[item["level"]] += 1
            completed += int(item["completed"])
            for reason in item["reasons"]:
                reasons[reason.value] = reasons.get(reason.value, 0) + 1
        highest = RiskLevel.LOW.value
        if counts[RiskLevel.HIGH.value]:
            highest = RiskLevel.HIGH.value
        elif counts[RiskLevel.MEDIUM.value]:
            highest = RiskLevel.MEDIUM.value
        return {"client_id": client_id, "risk_level": highest,
                "analyzed_operations": len(assessments),
                "completed_operations": completed,
                "blocked_operations": counts[RiskLevel.HIGH.value],
                "by_risk": counts, "reasons": reasons,
                "known_recipients": len(self._known_recipients.get(client_id, set()))}


def demo_audit():
    """Обычные и подозрительные переводы с объяснением причин отказа."""
    from .models import Bank, Client
    from .transactions import Transaction, TransactionProcessor, TransactionQueue

    current = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    analyzer = RiskAnalyzer(large_amounts={Currency.RUB: 1000},
                            warning_count=3, frequent_count=5)
    bank = Bank(now=lambda: current, risk_analyzer=analyzer)
    client = Client("Алексей", 25, {"phone": "123"})
    bank.add_client(client, "audit-demo-password")
    bank.authenticate_client(client.client_id, "audit-demo-password")
    sender = bank.open_account(client.client_id, balance=5000)
    recipient = bank.open_account(client.client_id)
    new_recipient = bank.open_account(client.client_id)
    frozen = bank.open_account(client.client_id, status=AccountStatus.FROZEN)
    queue = TransactionQueue(now=lambda: current)
    processor = TransactionProcessor(bank, queue)
    transactions = []

    def submit(target, amount):
        transaction = Transaction(
            client.client_id, sender.account_number, target.account_number,
            amount, created_at=current,
        )
        queue.add(transaction)
        processor.process_ready()
        transactions.append(transaction)
        print(f"{len(transactions)}: {transaction.status}, риск {transaction.risk_level}, "
              f"причины {[reason.value for reason in transaction.risk_reasons]}, отказ {transaction.failure_reason}")

    print("\nДень 5: аудит и риск (учебный порог суммы 1000 RUB)")
    submit(recipient, 10)       # Новый получатель: средний риск.
    submit(recipient, 10)       # Знакомый получатель: низкий риск.
    submit(recipient, 1200)     # Крупная сумма: блокировка.
    submit(new_recipient, 10)   # Новый получатель и повышенная частота.
    submit(recipient, 10)       # Пятая операция за минуту: блокировка.
    current += timedelta(seconds=61)
    submit(recipient, 700)      # Повышенная сумма: средний риск.
    submit(frozen, 10)          # Обычная ошибка статуса попадёт в статистику.
    current = datetime(2000, 1, 1, 18, 30, tzinfo=timezone.utc)
    submit(recipient, 10)       # Полночь в Asia/Colombo: блокировка.

    print("Подозрительных записей:", len(bank.audit_log.suspicious_operations()))
    print("Риск-профиль:", bank.risk_analyzer.client_profile(client.client_id))
    print("Статистика ошибок:", bank.audit_log.error_statistics())
    print("Файл аудита:", bank.audit_log.file_path)
    return bank, transactions, processor
