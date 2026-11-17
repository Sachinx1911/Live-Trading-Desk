"""ORM models. Importing this package registers every table on `core.db.Base.metadata`,
which is what Alembic's env.py uses as target metadata.

Phase 1 scope: identity, reference data, instruments, strategy skeleton, market data core.
"""

from core.db.models import identity, instruments, market_data, reference, strategy
from core.db.models.identity import ApiLog, AuditLog, RefreshSession, Role, User, UserRole
from core.db.models.instruments import (
    Contract,
    CorporateAction,
    Event,
    Instrument,
    InstrumentHistory,
    InstrumentMapping,
)
from core.db.models.market_data import (
    DataImportJob,
    DataQualityCheck,
    HistoricalCandle,
    MarketQuote,
    OptionChainSnapshot,
)
from core.db.models.reference import (
    Broker,
    BrokerAccount,
    BrokerSession,
    CostSchedule,
    DataProvider,
    Exchange,
    Market,
    Segment,
    TradingCalendar,
)
from core.db.models.strategy import (
    Strategy,
    StrategyActivation,
    StrategyApproval,
    StrategyCondition,
    StrategyVersion,
)

__all__ = [
    "ApiLog",
    "AuditLog",
    "Broker",
    "BrokerAccount",
    "BrokerSession",
    "Contract",
    "CorporateAction",
    "CostSchedule",
    "DataImportJob",
    "DataProvider",
    "DataQualityCheck",
    "Event",
    "Exchange",
    "HistoricalCandle",
    "Instrument",
    "InstrumentHistory",
    "InstrumentMapping",
    "Market",
    "MarketQuote",
    "OptionChainSnapshot",
    "RefreshSession",
    "Role",
    "Segment",
    "Strategy",
    "StrategyActivation",
    "StrategyApproval",
    "StrategyCondition",
    "StrategyVersion",
    "TradingCalendar",
    "User",
    "UserRole",
    "identity",
    "instruments",
    "market_data",
    "reference",
    "strategy",
]
