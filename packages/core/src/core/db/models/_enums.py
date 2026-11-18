"""DB-only enumerations (Python enums shared with the domain live in core.models.enums).
Every Enum column uses `pg_enum()` so the Postgres type stores the *values*, not names."""

from __future__ import annotations

from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        native_enum=True,
        create_constraint=False,
        validate_strings=True,
    )


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AI = "ai"
    SCHEDULER = "scheduler"


class SessionType(StrEnum):
    NORMAL = "normal"
    HOLIDAY = "holiday"
    SPECIAL = "special"
    MUHURAT = "muhurat"
    HALF_DAY = "half_day"


class CostProduct(StrEnum):
    INTRADAY = "intraday"
    DELIVERY = "delivery"
    FUTURES = "futures"
    OPTIONS = "options"


class ChargeType(StrEnum):
    BROKERAGE = "brokerage"
    STT = "stt"
    EXCHANGE_TXN = "exchange_txn"
    SEBI = "sebi"
    STAMP_DUTY = "stamp_duty"
    GST = "gst"
    CLEARING = "clearing"


class ChargeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"
    BOTH = "both"


class RateType(StrEnum):
    PERCENT = "percent"
    FLAT_PER_ORDER = "flat_per_order"
    PER_LOT = "per_lot"


class AuthType(StrEnum):
    OAUTH2 = "oauth2"
    TOKEN = "token"  # noqa: S105 - enum label, not a credential


class BrokerSessionStatus(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"


class InstrumentType(StrEnum):
    EQUITY = "equity"
    INDEX = "index"
    FUTURE = "future"
    OPTION = "option"
    ETF = "etf"
    CURRENCY = "currency"
    COMMODITY = "commodity"


class HistoryAttribute(StrEnum):
    LOT_SIZE = "lot_size"
    TICK_SIZE = "tick_size"
    SYMBOL = "symbol"
    FREEZE_QTY = "freeze_qty"
    NAME = "name"


class ContractType(StrEnum):
    FUTURE = "future"
    OPTION = "option"


class Settlement(StrEnum):
    CASH = "cash"
    PHYSICAL = "physical"


class CorporateActionType(StrEnum):
    SPLIT = "split"
    BONUS = "bonus"
    DIVIDEND = "dividend"
    RIGHTS = "rights"
    MERGER = "merger"
    SYMBOL_CHANGE = "symbol_change"
    DELISTING = "delisting"


class EventType(StrEnum):
    RBI_POLICY = "rbi_policy"
    FED = "fed"
    BUDGET = "budget"
    EXPIRY = "expiry"
    RESULTS = "results"
    HOLIDAY_EVE = "holiday_eve"
    MACRO = "macro"
    CUSTOM = "custom"


class Impact(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class QuoteFreshness(StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    STALE = "stale"


class ImportSourceType(StrEnum):
    API = "api"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    PARQUET = "parquet"
    COLLECTOR = "collector"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class QualityCheckType(StrEnum):
    MISSING_CANDLES = "missing_candles"
    DUPLICATES = "duplicates"
    OHLC_INVALID = "ohlc_invalid"
    VOLUME_SPIKE = "volume_spike"
    GAP_VS_PREV_CLOSE = "gap_vs_prev_close"
    STALE_FEED = "stale_feed"


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class StrategyCategory(StrEnum):
    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    OPTIONS = "options"
    SWING = "swing"
    OTHER = "other"


class StrategyOrigin(StrEnum):
    USER_NL = "user_nl"
    USER_VISUAL = "user_visual"
    AI_RESEARCH = "ai_research"
    AI_LEARNING = "ai_learning"
    IMPORT = "import"


class StrategyVersionStatus(StrEnum):
    DRAFT = "draft"
    BACKTESTED = "backtested"
    VALIDATED = "validated"
    PAPER = "paper"
    APPROVED_LIVE = "approved_live"
    RETIRED = "retired"
    REJECTED = "rejected"


class CreatedBy(StrEnum):
    USER = "user"
    AI = "ai"


class ConditionRole(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"
    STOP = "stop"
    TARGET = "target"
    FILTER = "filter"


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ActivationStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


# --- Phase 3: trading ---------------------------------------------------------------


class OrderEventSource(StrEnum):
    BROKER_CALLBACK = "broker_callback"
    RECONCILIATION = "reconciliation"
    USER = "user"
    GATEWAY = "gateway"


class ReconciliationAction(StrEnum):
    NONE = "none"
    ALERT = "alert"
    KILL_SWITCH = "kill_switch"


class KillSwitchScope(StrEnum):
    GLOBAL = "global"
    ACCOUNT = "account"
    STRATEGY = "strategy"


class KillSwitchAction(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"


class RiskLimitScope(StrEnum):
    PAPER_ACCOUNT = "paper_account"
    LIVE_ACCOUNT = "live_account"
    STRATEGY = "strategy"


class AiAgent(StrEnum):
    """Who made an LLM call (ADR-009). Each agent has one job and one output table."""

    TRANSLATOR = "translator"  # NL -> strategy DSL draft
    ANALYST = "analyst"  # morning brief, regime commentary
    RESEARCHER = "researcher"  # hypotheses -> candidate draft versions
    REVIEWER = "reviewer"  # per-trade reviews
    RISK_REVIEWER = "risk_reviewer"  # risk report narrative
    MONITOR_EXPLAINER = "monitor_explainer"  # explains deterministic monitor alerts
    AUDITOR = "auditor"  # reviews other agents' outputs against data


class OptimizationKind(StrEnum):
    GRID = "grid"
    RANDOM = "random"
    WALK_FORWARD = "walk_forward"


class ReplayStatus(StrEnum):
    CREATED = "created"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"
