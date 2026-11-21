"""Breadth universes. NIFTY 50 membership is the NSE Indices constituent file
(https://niftyindices.com/IndexConstituent/ind_nifty50list.csv), fetched 2026-11-21.

Nothing in the repo stored index membership before this (the Upstox daily back-fill of
"NIFTY 50" was done by hand and also holds former members BPCL, BRITANNIA, HEROMOTOCO and
WIPRO). Membership changes twice a year; update this tuple and `NIFTY50_AS_OF` when NSE
rebalances. Breadth for past dates uses today's list (no survivorship correction).
"""

from __future__ import annotations

from datetime import date

NIFTY50_AS_OF = date(2026, 11, 21)
NIFTY50_SOURCE = "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv"

NIFTY50: tuple[str, ...] = (
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJAJFINSV",
    "BAJFINANCE",
    "BEL",
    "BHARTIARTL",
    "BSE",
    "CIPLA",
    "COALINDIA",
    "DRREDDY",
    "EICHERMOT",
    "ETERNAL",
    "GRASIM",
    "HCLTECH",
    "HDFCBANK",
    "HDFCLIFE",
    "HINDALCO",
    "HINDUNILVR",
    "ICICIBANK",
    "INDIGO",
    "INFY",
    "ITC",
    "JIOFIN",
    "JSWSTEEL",
    "KOTAKBANK",
    "LT",
    "M&M",
    "MARUTI",
    "MAXHEALTH",
    "NESTLEIND",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "RELIANCE",
    "SBILIFE",
    "SBIN",
    "SHRIRAMFIN",
    "SUNPHARMA",
    "TATACONSUM",
    "TATASTEEL",
    "TCS",
    "TECHM",
    "TITAN",
    "TMPV",
    "TRENT",
    "ULTRACEMCO",
)

INDEX_SYMBOLS: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "INDIAVIX")

UNIVERSES: dict[str, tuple[str, ...]] = {"NIFTY50": NIFTY50}


def universe_symbols(name: str) -> tuple[str, ...]:
    try:
        return UNIVERSES[name.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown universe {name!r}; known: {sorted(UNIVERSES)}") from exc
