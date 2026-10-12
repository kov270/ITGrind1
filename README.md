# ITGrind1 — простой банковский счёт

Учебная версия: абстрактный AbstractAccount и его наследник BankAccount, статусы строками,
валюты в списке, суммы — числа int или float. UUID оставлен для ID
и автоматического номера счёта.
Номер счёта — строка ровно из 12 цифр
Если номер не задан, он формируется из числового UUID, с нулями слева при необходимости.

AbstractAccount хранит общие данные и объявляет три обязательных метода:
deposit(), withdraw(), get_account_info(). BankAccount реализует их.
Создать AbstractAccount напрямую нельзя. BankAccount проверяет все входные
данные и генерирует UUID, затем super().__init__() передаёт подготовленные
данные родительскому классу для хранения. В AbstractAccount проверок нет.

## Запуск

Из корня проекта в терминале PyCharm:

```powershell
python -m src.main
```

Нужен Python 3.10 или новее. Внешние библиотеки не нужны.
Для запуска в PyCharm выберите Module name: src.main.
Также можно запустить src/main.py кнопкой Run или командой `python src/main.py`.

## Пример

```python
from src.models import BankAccount

account = BankAccount("Иван", balance=1000, currency="RUB")
account.deposit(250.50)
account.withdraw(100)
print(account.get_account_info()["balance"])  # 1150.5
print(account)
```

Передавайте суммы числами без кавычек: 100 или 25.50.
Статусы: "active", "frozen", "closed".
Валюты: "RUB", "USD", "EUR", "KZT", "CNY".
Собственные ошибки: AccountFrozenError, AccountClosedError,
InvalidOperationError, InsufficientFundsError. Они наследуются от ValueError.

## Файлы

- src/main.py — пример работы, начните читать здесь.
- src/models.py — класс счёта и его операции.
- src/utils.py — функции проверки чисел и текста и четыре класса ошибок.
- src/__init__.py — обозначает пакет src.
- docs/algorithm.md — правила работы.

Методы счёта: deposit(), withdraw(), get_account_info(), __str__()
и вспомогательный check_status(). __init__() настраивает объект при создании.
Баланс хранится в _balance. Читайте через get_account_info(), меняйте через
deposit() и withdraw(). Статус задаётся при создании счёта.

