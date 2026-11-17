"""NSE public reference data: holidays, bhavcopy, corporate actions (ADR-011).

NSE is not a market data provider here; it is a source for calendars, corporate actions,
lot-size history and end-of-day candles. All responses are untrusted input and are parsed
defensively.
"""

from providers.nse.client import NseClient, NseError
from providers.nse.parse import (
    CorporateActionSpec,
    parse_cm_bhavcopy,
    parse_corporate_action_subject,
    parse_fo_bhavcopy,
    parse_holidays,
)

__all__ = [
    "CorporateActionSpec",
    "NseClient",
    "NseError",
    "parse_cm_bhavcopy",
    "parse_corporate_action_subject",
    "parse_fo_bhavcopy",
    "parse_holidays",
]
