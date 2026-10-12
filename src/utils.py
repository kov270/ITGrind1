from math import isfinite


class InvalidOperationError(ValueError):
    """Некорректные данные или недопустимая операция."""
    pass


class AccountFrozenError(InvalidOperationError):
    """Операция запрещена: счёт заморожен."""
    pass


class AccountClosedError(InvalidOperationError):
    """Операция запрещена: счёт закрыт."""
    pass


class InsufficientFundsError(InvalidOperationError):
    """На счёте недостаточно средств."""
    pass


def check_amount(amount):
    if type(amount) not in [int, float]:
        raise InvalidOperationError("Сумма должна быть числом.")
    if not isfinite(amount):
        raise InvalidOperationError("Некорректная сумма.")
    if amount < 0:
        raise InvalidOperationError("Сумма не может быть отрицательной.")
    if amount != round(amount, 2):
        raise InvalidOperationError("Допускается не более двух знаков после запятой.")
    return float(amount)


def check_text(text):
    if type(text) != str:
        raise InvalidOperationError("Ожидается текст.")
    text = text.strip()
    if text == "":
        raise InvalidOperationError("Текст не должен быть пустым.")
    return text
