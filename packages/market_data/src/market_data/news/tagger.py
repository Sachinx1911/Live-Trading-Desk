"""Deterministic headline -> symbol tagging (no AI). Computed at query time, never stored.

Rules
- The canonical symbol matches as an upper-case token (``TCS``, ``M&M``, ``ONGC``).
- Each instrument also gets aliases: a curated list for the NIFTY 50 and the indices, plus one
  derived from the instrument name (legal suffixes such as "Ltd" removed).
- Multi-word aliases match case-insensitively; single-word aliases only in Title or UPPER case,
  so "Eternal" tags ETERNAL but "eternal optimism" does not.
- Some aliases carry exclusions for separately listed group companies
  ("Reliance Power" is not RELIANCE, "SBI Life" is not SBIN, "Nifty Bank" is not NIFTY).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# alias -> words that, when they follow the alias, mean a different company / index
_GROUP_EXCLUDE: dict[str, tuple[str, ...]] = {
    "Reliance": (
        "Power",
        "Infra",
        "Infrastructure",
        "Capital",
        "Communications",
        "Home",
        "Nippon",
        "General",
        "Consumer",
    ),
    "SBI": ("Life", "Card", "Cards", "Mutual", "MF", "Funds", "General"),
    "Nifty": (
        "Bank",
        "IT",
        "Auto",
        "Pharma",
        "FMCG",
        "Metal",
        "Realty",
        "Media",
        "Energy",
        "Infra",
        "PSU",
        "Private",
        "Financial",
        "Fin",
        "Midcap",
        "Smallcap",
        "Next",
        "Next50",
        "100",
        "200",
        "500",
        "Healthcare",
        "Oil",
        "Consumer",
        "Commodities",
        "CPSE",
        "Services",
        "Total",
        "India",
        "Microcap",
    ),
    "Kotak": ("Securities", "AMC", "Mutual", "Life", "Alternate"),
    "Airtel": ("Africa",),
    "Adani": (),
}

CURATED_ALIASES: dict[str, tuple[str, ...]] = {
    "NIFTY": ("Nifty 50", "Nifty50", "Nifty"),
    "BANKNIFTY": ("Bank Nifty", "Nifty Bank", "BankNifty"),
    "INDIAVIX": ("India VIX", "India Vix"),
    "FINNIFTY": ("Fin Nifty", "Nifty Financial Services"),
    "ADANIENT": ("Adani Enterprises",),
    "ADANIPORTS": ("Adani Ports", "Adani Ports and SEZ"),
    "APOLLOHOSP": ("Apollo Hospitals",),
    "ASIANPAINT": ("Asian Paints",),
    "AXISBANK": ("Axis Bank",),
    "BAJAJ-AUTO": ("Bajaj Auto",),
    "BAJAJFINSV": ("Bajaj Finserv",),
    "BAJFINANCE": ("Bajaj Finance",),
    "BEL": ("Bharat Electronics",),
    "BHARTIARTL": ("Bharti Airtel", "Airtel"),
    "BPCL": ("Bharat Petroleum",),
    "BRITANNIA": ("Britannia Industries", "Britannia"),
    "BSE": ("BSE Ltd", "BSE Limited"),
    "CIPLA": ("Cipla",),
    "COALINDIA": ("Coal India",),
    "DRREDDY": ("Dr Reddy's", "Dr. Reddy's", "Dr Reddys", "Dr Reddy"),
    "EICHERMOT": ("Eicher Motors", "Royal Enfield"),
    "ETERNAL": ("Eternal", "Zomato"),
    "GRASIM": ("Grasim Industries", "Grasim"),
    "HCLTECH": ("HCL Tech", "HCL Technologies", "HCLTech"),
    "HDFCBANK": ("HDFC Bank",),
    "HDFCLIFE": ("HDFC Life",),
    "HEROMOTOCO": ("Hero MotoCorp", "Hero Moto"),
    "HINDALCO": ("Hindalco",),
    "HINDUNILVR": ("Hindustan Unilever", "HUL"),
    "ICICIBANK": ("ICICI Bank",),
    "INDIGO": ("IndiGo", "InterGlobe Aviation", "Interglobe"),
    "INFY": ("Infosys",),
    "ITC": ("ITC",),
    "JIOFIN": ("Jio Financial", "Jio Financial Services", "Jio Finance"),
    "JSWSTEEL": ("JSW Steel",),
    "KOTAKBANK": ("Kotak Mahindra Bank", "Kotak Bank", "Kotak"),
    "LT": ("Larsen & Toubro", "Larsen and Toubro", "L&T", "Larsen"),
    "M&M": ("Mahindra & Mahindra", "Mahindra and Mahindra", "M&M"),
    "MARUTI": ("Maruti Suzuki", "Maruti"),
    "MAXHEALTH": ("Max Healthcare",),
    "NESTLEIND": ("Nestle India", "Nestlé India"),
    "NTPC": ("NTPC",),
    "ONGC": ("ONGC", "Oil and Natural Gas Corporation", "Oil & Natural Gas"),
    "POWERGRID": ("Power Grid", "PowerGrid"),
    "RELIANCE": ("Reliance Industries", "RIL", "Reliance"),
    "SBILIFE": ("SBI Life",),
    "SBIN": ("State Bank of India", "SBI"),
    "SHRIRAMFIN": ("Shriram Finance",),
    "SUNPHARMA": ("Sun Pharma", "Sun Pharmaceutical"),
    "TATACONSUM": ("Tata Consumer", "Tata Consumer Products"),
    "TATASTEEL": ("Tata Steel",),
    "TCS": ("Tata Consultancy Services", "Tata Consultancy", "TCS"),
    "TECHM": ("Tech Mahindra",),
    "TITAN": ("Titan Company", "Titan"),
    "TMPV": ("Tata Motors Passenger Vehicles", "Tata Motors PV", "TMPV"),
    "TRENT": ("Trent",),
    "ULTRACEMCO": ("UltraTech Cement", "UltraTech", "Ultratech"),
    "WIPRO": ("Wipro",),
}

_SUFFIXES = {
    "LTD",
    "LTD.",
    "LIMITED",
    "LT",
    "L",
    "CO",
    "CO.",
    "CORP",
    "CORP.",
    "CORPORATION",
    "INC",
    "INC.",
    "PLC",
    "ENTER.",
    "IND",
    "SERV",
}
_BOUND_L = r"(?<![A-Za-z0-9&\-])"
_BOUND_R = r"(?![A-Za-z0-9&\-])"
_MIN_DERIVED_LEN = 4


@dataclass(frozen=True)
class SymbolEntry:
    symbol: str
    name: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


def derived_alias(name: str | None) -> str | None:
    """Instrument name without legal suffixes: "TATA STEEL LIMITED" -> "TATA STEEL"."""
    if not name:
        return None
    words = name.replace(",", " ").split()
    while words and words[-1].upper() in _SUFFIXES:
        words.pop()
    alias = " ".join(words).strip()
    if len(alias) < _MIN_DERIVED_LEN or alias.upper() in {"INDIA", "BANK", "NIFTY"}:
        return None
    return alias


def _phrase(alias: str) -> str:
    parts = [re.escape(w) for w in alias.split()]
    return r"\s+".join(parts).replace(r"\&", r"(?:&|and)")


def _alias_pattern(alias: str) -> re.Pattern[str]:
    excl = _GROUP_EXCLUDE.get(alias)
    tail = ""
    if excl:
        tail = r"(?!\s+(?:" + "|".join(re.escape(x) for x in excl) + r")\b)"
    if " " not in alias.strip():
        word = re.escape(alias)
        forms = {word, re.escape(alias.upper()), re.escape(alias[:1].upper() + alias[1:])}
        return re.compile(_BOUND_L + "(?:" + "|".join(sorted(forms)) + ")" + _BOUND_R + tail)
    return re.compile(_BOUND_L + _phrase(alias) + _BOUND_R + tail, re.IGNORECASE)


def _symbol_pattern(symbol: str) -> re.Pattern[str] | None:
    if len(symbol) < 3 and "&" not in symbol:  # "LT" would hit "LT Foods"; aliases cover it
        return None
    return re.compile(_BOUND_L + re.escape(symbol) + _BOUND_R)


class SymbolMatcher:
    def __init__(self, entries: Iterable[SymbolEntry]) -> None:
        self._patterns: dict[str, list[re.Pattern[str]]] = {}
        for e in entries:
            sym = e.symbol.upper()
            pats: list[re.Pattern[str]] = []
            sp = _symbol_pattern(sym)
            if sp is not None:
                pats.append(sp)
            aliases = list(CURATED_ALIASES.get(sym, ())) + list(e.aliases)
            if sym not in CURATED_ALIASES:
                d = derived_alias(e.name)
                if d:
                    aliases.append(d)
            seen: set[str] = set()
            for a in aliases:
                if a and a not in seen:
                    seen.add(a)
                    pats.append(_alias_pattern(a))
            if pats:
                self._patterns[sym] = pats

    @property
    def symbols(self) -> list[str]:
        return sorted(self._patterns)

    def mentions(self, symbol: str, *texts: str | None) -> bool:
        pats = self._patterns.get(symbol.upper())
        if not pats:
            return False
        return any(p.search(t) for t in texts if t for p in pats)

    def tags(self, *texts: str | None) -> list[str]:
        body = [t for t in texts if t]
        return sorted(
            s for s, pats in self._patterns.items() if any(p.search(t) for t in body for p in pats)
        )


def tag_items(matcher: SymbolMatcher, items: Sequence[tuple[str, str | None]]) -> list[list[str]]:
    """Tags for (title, summary) pairs, in order."""
    return [matcher.tags(title, summary) for title, summary in items]
