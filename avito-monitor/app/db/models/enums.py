"""Enums shared across models. PostgreSQL enums use these as source of truth."""
from enum import StrEnum


class ConditionClass(StrEnum):
    WORKING = "working"
    BLOCKED_ICLOUD = "blocked_icloud"
    BLOCKED_ACCOUNT = "blocked_account"
    NOT_STARTING = "not_starting"
    BROKEN_SCREEN = "broken_screen"
    BROKEN_OTHER = "broken_other"
    PARTS_ONLY = "parts_only"
    UNKNOWN = "unknown"


class ListingStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    REMOVED = "removed"


class ProcessingStatus(StrEnum):
    FETCHED = "fetched"
    CLASSIFIED = "classified"
    MARKET_DATA = "market_data"
    PENDING_MATCH = "pending_match"
    ANALYZED = "analyzed"
    NOTIFIED = "notified"
    FAILED = "failed"


class UserAction(StrEnum):
    """User-driven funnel state for a profile_listings link.

    The simplified V1 funnel: every new lot starts ``pending``, the user
    either ``accepted`` it (moves to «В работе» tab) or ``rejected`` it
    (gone from the feed). ``viewed`` / ``hidden`` / ``flagged`` are kept
    for backwards compat with prior callback handlers.
    """
    PENDING = "pending"
    VIEWED = "viewed"
    ACCEPTED = "accepted"   # «принят в работу»
    REJECTED = "rejected"   # «отклонён», скрыт из ленты навсегда
    HIDDEN = "hidden"       # legacy
    FLAGGED = "flagged"     # legacy


class SellerType(StrEnum):
    PRIVATE = "private"
    COMPANY = "company"


class LLMAnalysisType(StrEnum):
    CONDITION = "condition"
    MATCH = "match"
    COMPARE = "compare"


class NotificationType(StrEnum):
    NEW_LISTING = "new_listing"
    PRICE_DROP_LISTING = "price_drop_listing"
    PRICE_DROPPED_INTO_ALERT = "price_dropped_into_alert"
    MARKET_TREND_DOWN = "market_trend_down"
    MARKET_TREND_UP = "market_trend_up"
    HISTORICAL_LOW = "historical_low"
    SUPPLY_SURGE = "supply_surge"
    CONDITION_MIX_CHANGE = "condition_mix_change"
    ERROR = "error"
    PRICE_REPORT = "price_report"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"
    MAX = "max"


class StatGranularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ProfileRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
