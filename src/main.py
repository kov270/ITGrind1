from src.models import BankAccount
from src.utils import AccountFrozenError


def main():
    active = BankAccount("Иван", balance=1000)
    frozen = BankAccount("Анна", balance=500, status="frozen")
    print(active)
    print(frozen)

    active.deposit(250.50)
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


if __name__ == "__main__":
    main()
