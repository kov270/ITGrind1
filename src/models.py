from abc import ABC, abstractmethod
from uuid import uuid4
from decimal import Decimal, localcontext

from .utils import check_amount, check_text, check_asset, check_growth_rates
from .utils import check_balance, round_money
from .utils import (AccountFrozenError, AccountClosedError,
                     InvalidOperationError, InsufficientFundsError, check_rate)


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
                 status="active", currency="RUB", withdraw_limit=100_000):
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


        super().__init__(account_id, owner, balance, account_number, status)
        self.currency = currency
        withdraw_limit = check_amount(withdraw_limit)

        if withdraw_limit == 0:
            raise InvalidOperationError("Лимит снятия должен быть больше нуля.")

        self.withdraw_limit = withdraw_limit

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
            "status": self.status,
            "currency": self.currency,
            "withdraw_limit": self.withdraw_limit,
        }

    def __str__(self):
        return (f"BankAccount | {self.owner} | ****{self.account_number[-4:]} | "
                f"{self.status} | {self._balance:.2f} {self.currency}")

class SavingsAccount(BankAccount):
    def __init__(self, owner, balance=0, account_number=None,
                 status="active", currency="RUB", monthly_rate="0.01", min_balance=0):
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
        with localcontext() as context:
            context.prec = 50
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
                 status="active", currency="RUB", withdraw_limit=500_000,
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
                 status="active", currency="RUB", withdraw_limit=100_000):
        super().__init__(owner, balance, account_number, status, currency,
                         withdraw_limit)
        self.portfolio = {
            "stocks": Decimal("0.00"),
            "bonds": Decimal("0.00"),
            "etf": Decimal("0.00"),
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
        with localcontext() as context:
            context.prec = 50
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
        info["portfolio"] = self.portfolio.copy()
        return info

    def __str__(self):
        return (f"InvestmentAccount | {self.owner} | ****{self.account_number[-4:]} | "
                f"{self.status} | {self._balance:.2f} {self.currency} | "
                f"портфель: {self.portfolio}")
