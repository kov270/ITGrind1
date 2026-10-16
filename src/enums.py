"""Фиксированные варианты значений банковской системы."""

from enum import Enum


class TextEnum(str, Enum):
    def __str__(self):
        return self.value


class ClientStatus(TextEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class AccountStatus(TextEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class AccountType(TextEnum):
    BANK = "bank"
    SAVINGS = "savings"
    PREMIUM = "premium"
    INVESTMENT = "investment"


class Currency(TextEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    KZT = "KZT"
    CNY = "CNY"


class AssetType(TextEnum):
    STOCKS = "stocks"
    BONDS = "bonds"
    ETF = "etf"


class TransactionType(TextEnum):
    INTERNAL_TRANSFER = "internal_transfer"
    EXTERNAL_TRANSFER = "external_transfer"


class TransactionStatus(TextEnum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY_PENDING = "retry_pending"


class AuditLevel(TextEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RiskLevel(TextEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskReason(TextEnum):
    LARGE_AMOUNT = "large_amount"
    ELEVATED_AMOUNT = "elevated_amount"
    FREQUENT_OPERATIONS = "frequent_operations"
    ELEVATED_FREQUENCY = "elevated_frequency"
    NEW_RECIPIENT = "new_recipient"
    NIGHT_OPERATION = "night_operation"


class SecurityReason(TextEnum):
    UNKNOWN_CLIENT = "unknown_client"
    BLOCKED_CLIENT = "blocked_client"
    WRONG_PASSWORD = "wrong_password"
    CLIENT_BLOCKED = "client_blocked"
    NOT_AUTHENTICATED = "not_authenticated"
    FOREIGN_OR_UNKNOWN_ACCOUNT = "foreign_or_unknown_account"
    NIGHT_OPERATION = "night_operation"


class AuditEvent(TextEnum):
    BALANCE_CHANGED = "balance_changed"
    TRANSACTION_QUEUED = "transaction_queued"
    TRANSACTION_CANCELLED = "transaction_cancelled"
    SECURITY_EVENT = "security_event"
    CLIENT_ADDED = "client_added"
    LOGIN_SUCCESS = "login_success"
    ACCOUNT_OPENED = "account_opened"
    ACCOUNT_CLOSED = "account_closed"
    ACCOUNT_FROZEN = "account_frozen"
    ACCOUNT_UNFROZEN = "account_unfrozen"
    RISK_ASSESSED = "risk_assessed"
    TRANSFER_COMPLETED = "transfer_completed"
    TRANSACTION_RETRY = "transaction_retry"
    TRANSACTION_FAILED = "transaction_failed"


class OperationAction(TextEnum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    INVEST = "invest"
    TRANSFER = "transfer"
    LOGIN = "login"
    ACCESS = "access"
    ACCOUNT_ACCESS = "account_access"
    OPEN_ACCOUNT = "open_account"
    CLOSE_ACCOUNT = "close_account"
    FREEZE_ACCOUNT = "freeze_account"
    UNFREEZE_ACCOUNT = "unfreeze_account"
    ACCOUNT_OPERATION = "account_operation"
    RECEIVE_TRANSFER = "receive_transfer"
