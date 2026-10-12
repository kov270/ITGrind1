from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext


CENT = Decimal("0.01")


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


def to_decimal(value):
    if type(value) not in [int, float, str, Decimal]:
        raise InvalidOperationError("Ожидается число или числовая строка.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InvalidOperationError("Некорректное число.") from None
    if not number.is_finite():
        raise InvalidOperationError("Число должно быть конечным.")
    return number


def round_money(value):
    """Округлить начисленный доход до копеек: половина округляется вверх."""
    value = to_decimal(value)
    if abs(value) >= Decimal("1e18"):
        raise InvalidOperationError("Сумма должна быть меньше 10^18 по модулю.")
    with localcontext() as context:
        context.prec = 50
        return value.quantize(CENT, rounding=ROUND_HALF_UP)


def check_balance(balance):
    """Проверить денежное значение, допускающее отрицательный баланс."""
    balance = to_decimal(balance)
    rounded = round_money(balance)
    if balance != rounded:
        raise InvalidOperationError("Допускается не более двух знаков после запятой.")
    return rounded


def check_amount(amount):
    amount = check_balance(amount)
    if amount < 0:
        raise InvalidOperationError("Сумма не может быть отрицательной.")
    return amount


def check_growth_rate(rate):
    rate = to_decimal(rate)
    # Ограничиваем точность и размер, чтобы произведения помещались в 50 цифр.
    if len(rate.as_tuple().digits) > 28 or abs(rate) >= Decimal("1e18"):
        raise InvalidOperationError("Слишком большая или точная ставка.")
    if rate.as_tuple().exponent < -28:
        raise InvalidOperationError("В ставке допускается до 28 дробных знаков.")
    return rate

def check_rate(rate):
    rate = check_growth_rate(rate)
    if rate <= 0:
        raise InvalidOperationError("Ставка не может быть отрицательной или равна нулю.")

    return rate

def check_text(text):
    if type(text) != str:
        raise InvalidOperationError("Ожидается текст.")
    text = text.strip()
    if text == "":
        raise InvalidOperationError("Текст не должен быть пустым.")
    return text


def check_asset(asset):
    asset = check_text(asset)
    if asset not in ["stocks", "bonds", "etf"]:
        raise InvalidOperationError("Допустимые активы: stocks, bonds, etf.")
    return asset


def check_growth_rates(growth_rates):
    if type(growth_rates) != dict:
        raise InvalidOperationError("Ставки должны передаваться словарём.")

    checked_rates = {}
    for asset, rate in growth_rates.items():
        asset = check_asset(asset)
        checked_rates[asset] = check_growth_rate(rate)

    # Для прогноза допускаем ноль и отрицательную доходность.
    return checked_rates
