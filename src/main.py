from src.models import (
    BankAccount,
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
    active = BankAccount("Иван", balance=1000)
    frozen = BankAccount("Анна", balance=500, status="frozen")
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
    investment.invest("stocks", 5000)
    investment.invest("bonds", 3000)
    investment.invest("etf", 1000)
    print(investment)

    growth_rates = {"stocks": "0.10", "bonds": "0.04", "etf": "0.07"}
    print("Ожидаемый годовой прирост:",
          investment.project_yearly_growth(growth_rates), investment.currency)


if __name__ == "__main__":
    main()
