from abc import ABC, abstractmethod
from uuid import uuid4

from .utils import check_amount, check_text
from .utils import (AccountFrozenError, AccountClosedError,
                     InvalidOperationError, InsufficientFundsError)


class AbstractAccount(ABC):
    def __init__(self, account_id, owner, balance, account_number, status):
        # Сохраняем данные, подготовленные конкретным классом.
        self.account_id = account_id
        self.account_number = account_number
        self.owner = owner
        self._balance = balance
        self.status = status

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
                 status="active", currency="RUB"):
        owner = check_text(owner)
        balance = check_amount(balance)
        if status not in ["active", "frozen", "closed"]:
            raise InvalidOperationError("Неизвестный статус счёта.")
        if status == "closed" and balance != 0:
            raise InvalidOperationError("Закрытый счёт должен иметь нулевой баланс.")
        currency = check_text(currency).upper()
        if currency not in ["RUB", "USD", "EUR", "KZT", "CNY"]:
            raise InvalidOperationError("Неизвестная валюта.")

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

        # Передаём проверенные данные родительскому классу для хранения.
        super().__init__(account_id, owner, balance, account_number, status)
        self.currency = currency

    def check_status(self):
        if self.status == "frozen":
            raise AccountFrozenError("Счёт заморожен.")
        if self.status == "closed":
            raise AccountClosedError("Счёт закрыт.")
        if self.status != "active":
            raise InvalidOperationError("Неизвестный статус счёта.")

    def deposit(self, amount):
        self.check_status()
        amount = check_amount(amount)
        if amount == 0:
            raise InvalidOperationError("Сумма пополнения должна быть больше нуля.")
        new_balance = round(self._balance + amount, 2)
        self._balance = check_amount(new_balance)
        return self._balance

    def withdraw(self, amount):
        self.check_status()
        amount = check_amount(amount)
        if amount == 0:
            raise InvalidOperationError("Сумма снятия должна быть больше нуля.")
        if amount > self._balance:
            raise InsufficientFundsError("Недостаточно средств.")
        self._balance = round(self._balance - amount, 2)
        return self._balance

    def get_account_info(self):
        return {
            "account_id": self.account_id,
            "account_number": self.account_number,
            "owner": self.owner,
            "balance": self._balance,
            "status": self.status,
            "currency": self.currency,
        }

    def __str__(self):
        return (f"BankAccount | {self.owner} | ****{self.account_number[-4:]} | "
                f"{self.status} | {self._balance:.2f} {self.currency}")
