from src.enums import AccountStatus, AccountType, AssetType, Currency
from datetime import datetime
from src.transactions import demo_transactions
from src.audit import demo_audit

from src.models import (
    Bank,
    BankAccount,
    Client,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)
from src.utils import (
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)


def main():
    print("Банк и клиент:")
    # Демонстрационные часы: меняем время без ожидания настоящей ночи.
    demo_now = datetime(2000, 1, 1, 12)
    bank = Bank(now=lambda: demo_now)
    client = Client("Иван Петров Сергеевич", 25, {"phone": "+79991234567"})
    bank.add_client(client, "example-password")
    print("Вход выполнен:", bank.authenticate_client(client.client_id, "example-password"))
    account = bank.open_account(client.client_id, balance=0)
    bank.freeze_account(client.client_id, account.account_number)
    print("Замороженные счета:", bank.search_accounts(client.client_id, status=AccountStatus.FROZEN))
    try:
        account.withdraw(10)
    except AccountFrozenError as error:
        print("Снятие с замороженного счёта Ивана отклонено:", error)
    bank.unfreeze_account(client.client_id, account.account_number)
    account.deposit(100)
    print("После разморозки пополнение разрешено:", account)
    account.withdraw(100)
    bank.close_account(client.client_id, account.account_number)
    print("Закрытые счета:", bank.search_accounts(client.client_id, status=AccountStatus.CLOSED))

    print("\nЗащита банка (демонстрационные часы):")
    savings_in_bank = bank.open_account(client.client_id, AccountType.SAVINGS, balance=100)
    demo_now = datetime(2000, 1, 2, 0)
    try:
        savings_in_bank.deposit(10)
    except InvalidOperationError as error:
        print("Ночная операция отклонена:", error)
    print("Поиск ночью доступен:", len(bank.search_accounts(client.client_id)))
    demo_now = datetime(2000, 1, 2, 5)
    print("Пополнение в 05:00:", savings_in_bank.deposit(10))

    blocked_client = Client("Анна Смирнова", 30, {"phone": "+79990000000"})
    bank.add_client(blocked_client, "another-example-password")
    print(
        "Успешный вход Анны:",
        bank.authenticate_client(blocked_client.client_id, "another-example-password"),
    )
    anna_account = bank.open_account(blocked_client.client_id, AccountType.PREMIUM, balance=500)
    bank.freeze_account(blocked_client.client_id, anna_account.account_number)
    try:
        anna_account.withdraw(100)
    except AccountFrozenError as error:
        print("Снятие с замороженного счёта Анны отклонено:", error)
    bank.unfreeze_account(blocked_client.client_id, anna_account.account_number)
    for attempt in range(3):
        print(
            f"Неверный вход Анны, попытка {attempt + 1}:",
            bank.authenticate_client(blocked_client.client_id, "wrong"),
        )
    print("После трёх ошибок:", blocked_client.status)
    print(
        "Правильный пароль после блокировки:",
        bank.authenticate_client(blocked_client.client_id, "another-example-password"),
    )
    try:
        anna_account.deposit(100)
    except InvalidOperationError as error:
        print("Операция заблокированного клиента отклонена:", error)
    print("Журнал подозрительных действий:", bank.suspicious_actions)

    print("\nОтчёты банка:")
    report_client = Client("Мария Орлова", 28, {"phone": "+79991111111"})
    bank.add_client(report_client, "report-example-password")
    print("Неверный вход Марии:", bank.authenticate_client(report_client.client_id, "wrong"))
    print(
        "Успешный вход Марии после ошибки:",
        bank.authenticate_client(report_client.client_id, "report-example-password"),
    )
    bank.open_account(report_client.client_id, balance=200)
    bank.open_account(report_client.client_id, balance=50, currency=Currency.USD)
    try:
        bank.freeze_account(report_client.client_id, savings_in_bank.account_number)
    except InvalidOperationError as error:
        print("Попытка Марии заморозить счёт Ивана отклонена:", error)
    print("Свободный баланс по валютам:", bank.get_total_balance())
    print("Рейтинг клиентов в RUB:", bank.get_clients_ranking(Currency.RUB))

    active = BankAccount("Иван", balance=1000)
    frozen = BankAccount("Анна", balance=500, status=AccountStatus.FROZEN)
    print(active)
    print(frozen)

    active.deposit("250.50")
    active.withdraw(100)
    print("После пополнения и снятия:")
    print(active)

    try:
        frozen.deposit(100)
    except AccountFrozenError as error:
        print("Не удалось пополнить:", error)

    try:
        frozen.withdraw(100)
    except AccountFrozenError as error:
        print("Не удалось снять:", error)

    print("\nНакопительный счёт:")
    savings = SavingsAccount(
        "Ольга", balance=10000, monthly_rate="0.01", min_balance=1000
    )
    print(savings)
    savings.apply_monthly_interest()
    print("После начисления 1% за месяц:")
    print(savings)
    savings.withdraw(9100)
    print("После снятия до минимального остатка:")
    print(savings)
    try:
        savings.withdraw(1)
    except InvalidOperationError as error:
        print("Не удалось снять ниже минимального остатка:", error)

    second_savings = SavingsAccount(
        "Дмитрий", balance=100, monthly_rate="0.015", min_balance=0
    )
    second_savings.deposit(50)
    second_savings.apply_monthly_interest()
    print("Второй накопительный счёт после пополнения и начисления 1.5%:")
    print(second_savings)
    try:
        second_savings.withdraw(200)
    except InsufficientFundsError as error:
        print("Не удалось снять больше баланса:", error)

    print("\nРазница лимитов обычного и премиального счетов:")
    ordinary = BankAccount("Павел", balance=300000)
    premium = PremiumAccount("Павел", balance=300000)
    try:
        ordinary.withdraw(200000)
    except InvalidOperationError as error:
        print("Обычный счёт, снятие 200000:", error)
    premium.withdraw(200000)
    print("Премиальный счёт после снятия 200000 без комиссии:")
    print(premium)

    print("\nОвердрафт и погашение долга:")
    credit = PremiumAccount(
        "Сергей", balance=1000,
        overdraft_limit=5000, overdraft_commission=500
    )
    credit.withdraw(1500)
    print("После снятия 1500 и комиссии 500:")
    print(credit)
    credit.deposit(200)
    print("После частичного погашения на 200:")
    print(credit)
    try:
        credit.withdraw(4000)
    except InsufficientFundsError as error:
        print("Не удалось превысить овердрафт:", error)
    credit.deposit(800)
    print("После полного погашения долга:")
    print(credit)

    print("\nИнвестиционный счёт:")
    investment = InvestmentAccount("Мария", balance=10000)
    investment.invest(AssetType.STOCKS, 5000)
    investment.invest(AssetType.BONDS, 3000)
    investment.invest(AssetType.ETF, 1000)
    print(investment)

    growth_rates = {AssetType.STOCKS: "0.10", AssetType.BONDS: "0.04", AssetType.ETF: "0.07"}
    print("Ожидаемый годовой прирост:",
          investment.project_yearly_growth(growth_rates), investment.currency)

    second_investment = InvestmentAccount("Елена", balance=5000)
    second_investment.invest(AssetType.BONDS, 2000)
    second_investment.invest(AssetType.ETF, 1000)
    second_investment.withdraw(500)
    print("Второй инвестиционный счёт после вложений и снятия свободных денег:")
    print(second_investment)
    print(
        "Ожидаемый годовой прирост второго портфеля:",
        second_investment.project_yearly_growth(growth_rates),
        second_investment.currency,
    )


    demo_transactions()
    demo_audit()


if __name__ == "__main__":
    main()
