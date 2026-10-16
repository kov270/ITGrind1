from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from secrets import token_bytes
from enum import Enum

from .enums import AssetType, Currency


# Общая точность вычислений при загрузке модулей проекта.
getcontext().prec = 50

CENT = Decimal("0.01")


def create_password_hash(password):
    if type(password) != str or not password.strip():
        raise InvalidOperationError("Пароль должен быть непустой строкой.")
    salt = token_bytes(16)
    password_hash = pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return salt, password_hash


def verify_password(password, salt, password_hash):
    if type(password) != str:
        return False
    candidate = pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return compare_digest(candidate, password_hash)


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


def check_enum(value, enum_class, uppercase=False):
    if isinstance(value, enum_class):
        return value
    if isinstance(value, Enum):
        raise InvalidOperationError(f"Ожидается значение {enum_class.__name__}.")
    value = check_text(value)
    if uppercase:
        value = value.upper()
    try:
        return enum_class(value)
    except ValueError:
        raise InvalidOperationError(f"Неизвестное значение {enum_class.__name__}: {value}") from None


def check_currency(currency):
    return check_enum(currency, Currency, uppercase=True)


def check_asset(asset):
    return check_enum(asset, AssetType)


def check_age(age):
    if type(age) != int:
        raise InvalidOperationError("Возраст должен быть целым числом.")
    if age < 18:
        raise InvalidOperationError("Клиенту должно быть не меньше 18 лет.")
    return age


def check_contacts(contacts):
    if type(contacts) != dict or not contacts:
        raise InvalidOperationError("Укажите контакты непустым словарём.")

    checked_contacts = {}
    for name, value in contacts.items():
        name = check_text(name)
        checked_contacts[name] = check_text(value)
    return checked_contacts


def check_growth_rates(growth_rates):
    if type(growth_rates) != dict:
        raise InvalidOperationError("Ставки должны передаваться словарём.")

    checked_rates = {}
    for asset, rate in growth_rates.items():
        asset = check_asset(asset)
        checked_rates[asset] = check_growth_rate(rate)

    # Для прогноза допускаем ноль и отрицательную доходность.
    return checked_rates
