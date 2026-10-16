"""Комплексная демонстрация дня 6: python -m src.demo."""

from datetime import datetime, timedelta, timezone

from .audit import RiskAnalyzer
from .enums import (
    AccountType,
    AssetType,
    AuditEvent,
    Currency,
    TransactionStatus,
)
from .models import Bank, Client
from .transactions import Transaction, TransactionProcessor, TransactionQueue


def create_demo():
    # Общее изменяемое состояние часов используют банк, очередь и процессор.
    state = {"now": datetime(2000, 1, 1, 6, 30, tzinfo=timezone.utc)}
    risk = RiskAnalyzer(
        large_amounts={Currency.RUB: 10000, Currency.USD: 1000},
        warning_count=3,
        frequent_count=5,
    )
    bank = Bank(now=lambda: state["now"], risk_analyzer=risk)
    queue = TransactionQueue(now=lambda: state["now"])
    processor = TransactionProcessor(
        bank, queue, exchange_rates={(Currency.RUB, Currency.USD): "0.01"}
    )
    names = [
        "Иван Петров", "Анна Смирнова", "Мария Орлова",
        "Сергей Волков", "Ольга Морозова", "Дмитрий Соколов",
    ]
    balances = [50000, 20000, 15000, 25000, 18000, 22000]
    secondary_types = [
        AccountType.PREMIUM, AccountType.SAVINGS, AccountType.INVESTMENT,
        AccountType.PREMIUM, AccountType.SAVINGS, AccountType.BANK,
    ]
    secondary_balances = [0, 10000, 10000, 5000, 12000, 500]
    clients = []
    primary = []
    secondary = []
    for index, name in enumerate(names):
        client = Client(name, 25 + index, {"phone": f"+7999000000{index}"})
        password = f"demo-client-{index}-password"
        bank.add_client(client, password)
        bank.authenticate_client(client.client_id, password)
        clients.append(client)
        primary.append(bank.open_account(
            client.client_id, balance=balances[index],
            withdraw_limit=300 if index == 4 else 100000,
        ))
        options = {"balance": secondary_balances[index]}
        if secondary_types[index] == AccountType.SAVINGS:
            options["min_balance"] = 1000
        if index == 5:
            options["currency"] = Currency.USD
        secondary.append(bank.open_account(
            client.client_id, secondary_types[index], **options
        ))

    secondary[2].invest(AssetType.STOCKS, 3000)
    bank.freeze_account(clients[4].client_id, secondary[4].account_number)
    state.update({
        "bank": bank, "queue": queue, "processor": processor,
        "clients": clients, "primary": primary, "secondary": secondary,
        "items": [], "processing_order": [],
        "initial_balances": bank.get_total_balance(),
    })
    return state


def fill_queue(state):
    start = state["now"]
    primary = state["primary"]
    secondary = state["secondary"]
    clients = state["clients"]

    def add(label, client_index, sender, recipient_number, amount,
            minute, priority=0, currency=Currency.RUB, execute_at=None):
        if execute_at is None:
            execute_at = start + timedelta(minutes=minute)
        transaction = Transaction(
            clients[client_index].client_id, sender.account_number,
            recipient_number, amount, currency=currency, created_at=start,
        )
        state["queue"].add(
            transaction, priority=priority, execute_at=execute_at
        )
        item = {"number": len(state["items"]) + 1,
                "label": label, "transaction": transaction}
        state["items"].append(item)
        state["bank"].audit_log.record(
            AuditEvent.TRANSACTION_QUEUED, client_id=transaction.client_id,
            transaction_id=transaction.transaction_id,
            details={"number": item["number"], "label": label,
                     "priority": priority, "execute_at": execute_at},
            timestamp=start,
        )
        print(
            f"[В ОЧЕРЕДИ] #{item['number']:02} {label}: "
            f"{transaction.amount} {currency}, приоритет {priority}, "
            f"выполнение {execute_at.isoformat()}"
        )
        return transaction

    for index in range(18):
        client_index = index % len(clients)
        recipient_index = (client_index + 1) % len(clients)
        add("Обычный перевод", client_index, primary[client_index],
            primary[recipient_index].account_number, 50 + index * 10,
            minute=index * 3)

    add("Обычный приоритет", 0, primary[0],
        primary[1].account_number, 30, minute=54)
    add("Высокий приоритет", 0, primary[0],
        primary[1].account_number, 40, minute=54, priority=10)
    add("Недостаточно свободных денег", 2, secondary[2],
        primary[0].account_number, 8000, minute=57)
    add("Замороженный отправитель", 4, secondary[4],
        primary[0].account_number, 20, minute=60)
    add("Замороженный получатель", 0, primary[0],
        secondary[4].account_number, 20, minute=63)
    add("Неизвестный получатель", 0, primary[0],
        "unknown-account", 20, minute=66)
    add("Новый получатель", 0, primary[0],
        secondary[3].account_number, 100, minute=69)
    add("Крупная сумма", 0, primary[0],
        primary[1].account_number, 10000, minute=72)
    add("Крупная сумма новому получателю", 0, primary[0],
        secondary[1].account_number, 12000, minute=75)
    add("Неверная валюта отправителя", 0, primary[0],
        primary[1].account_number, 20, minute=78, currency=Currency.USD)
    add("Перевод на тот же счёт", 0, primary[0],
        primary[0].account_number, 20, minute=81)
    add("Нарушение минимального остатка", 1, secondary[1],
        primary[0].account_number, 9500, minute=84)
    add("Премиальный овердрафт", 0, secondary[0],
        primary[1].account_number, 500, minute=87)
    add("Превышение лимита операции", 4, primary[4],
        primary[0].account_number, 500, minute=90)
    add("Конвертация RUB в USD", 0, primary[0],
        secondary[5].account_number, 100, minute=93)
    cancelled = add("Отменённая операция", 0, primary[0],
                    primary[1].account_number, 25, minute=96)
    state["queue"].cancel(cancelled.transaction_id)
    state["bank"].audit_log.record(
        AuditEvent.TRANSACTION_CANCELLED, client_id=cancelled.client_id,
        transaction_id=cancelled.transaction_id, timestamp=start,
    )
    print("[ОТМЕНЕНО] #34 — деньги не списываются")
    night = datetime(2000, 1, 1, 18, 30, tzinfo=timezone.utc)
    add("Отложено до ночи: запрет операции", 0, primary[0],
        primary[1].account_number, 25, minute=0, execute_at=night)

    for index in range(5):
        add(f"Серия частых переводов {index + 1}/5", 1, primary[1],
            primary[0].account_number, 10, minute=102)


def process_queue(state):
    # Переставляем часы на моменты готовности; sleep и реального ожидания нет.
    moments = {item["transaction"].execute_at for item in state["items"]}
    moments.add(state["now"] + timedelta(minutes=1))
    numbers = {item["transaction"].transaction_id: item
               for item in state["items"]}
    for current in sorted(moments):
        state["now"] = current
        results = state["processor"].process_ready()
        if not results:
            print(f"[ОЖИДАНИЕ] {current.isoformat()}: готовых операций нет")
        for transaction in results:
            item = numbers[transaction.transaction_id]
            state["processing_order"].append(item["number"])
            if transaction.status == TransactionStatus.COMPLETED:
                print(
                    f"[ИСПОЛНЕНО] #{item['number']:02} {item['label']}; "
                    f"комиссия {transaction.commission}; "
                    f"зачислено {transaction.received_amount} "
                    f"{transaction.received_currency}"
                )
            else:
                print(
                    f"[ОТКЛОНЕНО] #{item['number']:02} {item['label']}: "
                    f"{transaction.failure_reason}"
                )


def print_reports(state):
    bank = state["bank"]
    client = state["clients"][0]
    print(f"\nСЧЕТА КЛИЕНТА: {client.full_name}")
    for account in bank.search_accounts(client.client_id):
        print(
            f"****{account['account_number'][-4:]} | {account['status']} | "
            f"{account['balance']} {account['currency']}"
        )

    print("\nИСТОРИЯ КЛИЕНТА (отправленные и входящие операции)")
    for item in state["items"]:
        transaction = item["transaction"]
        sent = transaction.client_id == client.client_id
        received = transaction.recipient_number in client.account_numbers
        if sent or received:
            print(
                f"#{item['number']:02} {item['label']}: "
                f"{transaction.amount} {transaction.currency}, "
                f"{transaction.status}, отказ: {transaction.failure_reason}"
            )

    print("\nПОДОЗРИТЕЛЬНЫЕ ОПЕРАЦИИ")
    suspicious = bank.audit_log.suspicious_operations()
    for entry in suspicious:
        details = entry["details"]
        print(
            f"{entry['time']} | риск {entry['risk_level']} | "
            f"транзакция {entry['transaction_id']} | "
            f"{details.get('reasons', details.get('reason'))}"
        )

    print("\nТОП-3 КЛИЕНТОВ ПО СВОБОДНОМУ БАЛАНСУ В RUB")
    for position, row in enumerate(bank.get_clients_ranking(Currency.RUB)[:3], 1):
        print(f"{position}. {row['full_name']}: {row['balance']} {row['currency']}")

    counts = {status.value: 0 for status in TransactionStatus}
    for item in state["items"]:
        counts[item["transaction"].status.value] += 1
    print("\nСТАТИСТИКА ТРАНЗАКЦИЙ:", counts)
    print("Статистика ошибок:", bank.audit_log.error_statistics())
    print("Свободный баланс по валютам:", bank.get_total_balance())
    print("Вложения не входят в свободный баланс:",
          state["secondary"][2].get_account_info()["portfolio"])
    print("Риск-профиль выбранного клиента:",
          bank.risk_analyzer.client_profile(client.client_id))
    print("Файл аудита:", bank.audit_log.file_path)
    state["statistics"] = counts


def run_demo():
    print("ДЕНЬ 6 — КОМПЛЕКСНАЯ ДЕМОНСТРАЦИЯ")
    print("Учебные часы и курс 1 RUB = 0.01 USD; реальные курсы не используются.")
    state = create_demo()
    print(f"Создано клиентов: {len(state['bank'].clients)}; "
          f"счетов: {len(state['bank'].accounts)}")
    print("Начальные свободные остатки:", state["initial_balances"])
    print("Порог крупной суммы 10000 RUB, частота блокировки 5 за 60 секунд.")
    fill_queue(state)
    process_queue(state)
    print_reports(state)
    return state


if __name__ == "__main__":
    run_demo()
