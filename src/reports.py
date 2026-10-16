"""Отчёты и графики дня 7. Запуск: python -m src.reports."""

import csv
import io
import json
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .enums import AuditEvent, Currency, RiskLevel, TransactionStatus
from .utils import InvalidOperationError, check_currency


def serialize(value):
    """Сохранить точные деньги строками, Enum — значениями, время — ISO."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(serialize(key)): serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    return value


class ReportBuilder:
    def __init__(self, bank, transactions=None):
        self.bank = bank
        self.transactions = list(transactions) if transactions is not None else []

    def _transaction_rows(self, client_id=None):
        numbers = []
        if client_id is not None:
            if client_id not in self.bank.clients:
                raise InvalidOperationError("Клиент не найден.")
            numbers = self.bank.clients[client_id].account_numbers
        result = []
        for transaction in self.transactions:
            if client_id is not None:
                sent = transaction.client_id == client_id
                received = (
                    transaction.recipient_number in numbers
                    and transaction.recipient_bank in [None, self.bank]
                )
                if not sent and not received:
                    continue
            result.append({
                "transaction_id": transaction.transaction_id,
                "client_id": transaction.client_id,
                "sender": transaction.sender_number,
                "recipient": transaction.recipient_number,
                "type": transaction.transaction_type,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "commission": transaction.commission,
                "received_amount": transaction.received_amount,
                "received_currency": transaction.received_currency,
                "status": transaction.status,
                "risk_level": transaction.risk_level,
                "risk_reasons": list(transaction.risk_reasons),
                "failure_reason": transaction.failure_reason,
                "attempts": transaction.attempts,
                "created_at": transaction.created_at,
                "completed_at": transaction.completed_at,
            })
        return result

    def get_balance_history(self, account_number):
        if account_number not in self.bank.accounts:
            raise InvalidOperationError("Счёт не найден.")
        history = []
        for entry in self.bank.audit_log.filter():
            if entry["event"] not in [AuditEvent.ACCOUNT_OPENED, AuditEvent.BALANCE_CHANGED]:
                continue
            details = entry["details"]
            if details.get("account_number") != account_number or "balance" not in details:
                continue
            history.append({
                "time": entry["time"],
                "balance": Decimal(details["balance"]),
                "currency": details["currency"],
                "action": details.get("action", "opening"),
            })
        history.sort(key=lambda row: datetime.fromisoformat(row["time"]))
        return history

    def build_client_report(self, client_id):
        if client_id not in self.bank.clients:
            raise InvalidOperationError("Клиент не найден.")
        client = self.bank.clients[client_id]
        accounts = []
        totals = {}
        history = {}
        for number in client.account_numbers:
            account = self.bank.accounts[number]
            info = account.get_account_info()
            accounts.append(info)
            currency = account.currency.value
            totals[currency] = totals.get(currency, Decimal("0.00")) + info["balance"]
            history[number] = self.get_balance_history(number)
        return {
            "report_type": "client",
            "generated_at": self.bank._current_time(),
            "client": {"client_id": client.client_id, "full_name": client.full_name,
                       "age": client.age, "status": client.status,
                       "contacts": client.contacts.copy()},
            "accounts": accounts,
            "balances_by_currency": totals,
            "transactions": self._transaction_rows(client_id),
            "balance_history": history,
            "risk_profile": self.bank.risk_analyzer.client_profile(client_id),
        }

    def build_bank_report(self, currency=Currency.RUB):
        currency = check_currency(currency)
        counts = {status.value: 0 for status in TransactionStatus}
        for transaction in self.transactions:
            counts[transaction.status.value] += 1
        return {
            "report_type": "bank",
            "generated_at": self.bank._current_time(),
            "bank_id": self.bank.bank_id,
            "clients_count": len(self.bank.clients),
            "accounts_count": len(self.bank.accounts),
            "transactions_count": len(self.transactions),
            "transaction_statistics": counts,
            "balances_by_currency": self.bank.get_total_balance(),
            "top_three": self.bank.get_clients_ranking(currency)[:3],
            "ranking_currency": currency,
            "accounts": [account.get_account_info() for account in self.bank.accounts.values()],
            "transactions": self._transaction_rows(),
            "errors": self.bank.audit_log.error_statistics(),
        }

    def build_risk_report(self, client_id=None):
        if client_id is not None and client_id not in self.bank.clients:
            raise InvalidOperationError("Клиент не найден.")
        counts = {level.value: 0 for level in RiskLevel}
        for entry in self.bank.audit_log.filter(
            event=AuditEvent.RISK_ASSESSED, client_id=client_id
        ):
            counts[entry["risk_level"]] += 1
        clients = [client_id] if client_id is not None else list(self.bank.clients)
        return {
            "report_type": "risk",
            "generated_at": self.bank._current_time(),
            "risk_statistics": counts,
            "suspicious_operations": self.bank.audit_log.suspicious_operations(client_id),
            "client_profiles": [self.bank.risk_analyzer.client_profile(item) for item in clients],
            "errors": self.bank.audit_log.error_statistics(client_id),
        }

    def build_text(self, report):
        report = serialize(report)
        lines = [f"ОТЧЁТ: {report['report_type']}", ""]

        def write(value, indent=0):
            prefix = " " * indent
            if isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(item, (dict, list)):
                        lines.append(f"{prefix}{key}:")
                        write(item, indent + 2)
                    else:
                        lines.append(f"{prefix}{key}: {item}")
            elif isinstance(value, list):
                if not value:
                    lines.append(prefix + "нет записей")
                for index, item in enumerate(value, 1):
                    lines.append(f"{prefix}[{index}]")
                    write(item, indent + 2)
            else:
                lines.append(prefix + str(value))

        write(report)
        return "\n".join(lines) + "\n"

    def export_to_json(self, report, file_path):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(serialize(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path.resolve()

    def export_to_csv(self, report, file_path):
        # Общий формат для вложенных отчётов: путь к полю и его значение.
        rows = []

        def flatten(value, path=""):
            if isinstance(value, dict) and value:
                for key, item in value.items():
                    flatten(item, f"{path}.{key}" if path else key)
            elif isinstance(value, list) and value:
                for index, item in enumerate(value):
                    flatten(item, f"{path}[{index}]")
            else:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                rows.append((path, value))

        flatten(serialize(report))
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as target:
            writer = csv.writer(target)
            writer.writerow(["field", "value"])
            writer.writerows(rows)
        return path.resolve()

    def save_charts(self, output_dir, account_number=None, currency=Currency.RUB):
        # Графическая библиотека нужна только при сохранении графиков.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        currency = check_currency(currency)
        if account_number is not None and account_number not in self.bank.accounts:
            raise InvalidOperationError("Счёт для графика не найден.")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        statistics = self.build_bank_report(currency)["transaction_statistics"]
        selected = [(status, count) for status, count in statistics.items() if count]
        fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")
        if selected:
            ax.pie([row[1] for row in selected], labels=[row[0] for row in selected],
                   autopct="%1.1f%%", startangle=90)
        else:
            ax.text(0.5, 0.5, "Транзакций пока нет", ha="center", va="center")
            ax.set_axis_off()
        ax.set_title("Статусы транзакций")
        path = output_dir / "transaction_statuses.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path.resolve())

        ranking = self.bank.get_clients_ranking(currency)
        fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
        if ranking:
            # float используется только для отрисовки, не для финансовых расчётов.
            values = [float(row["balance"]) for row in ranking]
            ax.barh([row["full_name"] for row in ranking], values,
                    color=["#2874a6" if value >= 0 else "#c0392b" for value in values])
            ax.invert_yaxis()
            ax.axvline(0, color="#666666", linewidth=0.8)
        else:
            ax.text(0.5, 0.5, "Клиентов пока нет", ha="center", transform=ax.transAxes)
        ax.set_title(f"Свободные балансы клиентов — {currency.value}")
        ax.set_xlabel(currency.value)
        path = output_dir / "client_balances.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path.resolve())

        if account_number is None and self.bank.accounts:
            account_number = next(iter(self.bank.accounts))
        history = self.get_balance_history(account_number) if account_number is not None else []
        fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
        if history:
            times = [datetime.fromisoformat(row["time"]) for row in history]
            values = [float(row["balance"]) for row in history]
            ax.step(times, values, where="post", marker="o", markersize=3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter(
                "%d.%m\n%H:%M", tz=self.bank._timezone
            ))
            ax.set_ylabel(history[0]["currency"])
            ax.set_title(f"Движение баланса счёта ****{account_number[-4:]}")
        else:
            ax.text(0.5, 0.5, "Нет снимков баланса в аудите", ha="center", transform=ax.transAxes)
            ax.set_title("История баланса недоступна")
        ax.set_xlabel("Время банка (Asia/Colombo)")
        ax.grid(alpha=0.25)
        path = output_dir / "balance_history.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path.resolve())
        return paths


def run_reports(output_dir=None):
    from .demo import run_demo

    print("Подготовка данных: 6 клиентов, 12 счетов, 40 транзакций...")
    with redirect_stdout(io.StringIO()):
        state = run_demo()
    builder = ReportBuilder(
        state["bank"], [item["transaction"] for item in state["items"]]
    )
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent / "reports" / "day7"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = {
        "bank": builder.build_bank_report(),
        "client": builder.build_client_report(state["clients"][0].client_id),
        "risk": builder.build_risk_report(),
    }
    for name, report in reports.items():
        builder.export_to_json(report, output_dir / f"{name}.json")
        builder.export_to_csv(report, output_dir / f"{name}.csv")
        (output_dir / f"{name}.txt").write_text(builder.build_text(report), encoding="utf-8")
    charts = builder.save_charts(
        output_dir / "charts", state["primary"][0].account_number
    )
    print("Сохранены 3 текстовых, 3 JSON, 3 CSV-отчёта и 3 графика.")
    print("Папка:", output_dir.resolve())
    for path in charts:
        print("График:", path)
    return builder, reports, charts


if __name__ == "__main__":
    run_reports()
