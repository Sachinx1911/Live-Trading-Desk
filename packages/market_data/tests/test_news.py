"""News parsing, feed config and the deterministic symbol matcher (no DB, no network)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_data.news.feeds import DEFAULT_FEEDS, parse_feed_list, source_name
from market_data.news.parser import FeedParseError, clean_text, normalize_url, parse_feed
from market_data.news.tagger import SymbolEntry, SymbolMatcher, derived_alias

FIX = Path(__file__).parent / "fixtures" / "news"


def _load(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_rss_parse_cleans_dedups_and_converts_to_utc() -> None:
    items = parse_feed(_load("rss_sample.xml"))
    urls = [i.url for i in items]
    # empty title and missing link are skipped; the utm-variant duplicate collapses
    assert urls == [
        "https://news.example.com/markets/reliance-q2.cms?id=42",
        "https://news.example.com/markets/banks.cms",
        "https://news.example.com/markets/undated.cms",
    ]
    first = items[0]
    assert first.title.startswith("Reliance shares rise 2%")
    assert first.summary == "Shares of Reliance Industries rose & the index gained."
    assert first.published_at == datetime(2026, 11, 20, 10, 15, tzinfo=UTC)  # 15:45 IST
    assert items[1].published_at == datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    undated = items[2]
    assert undated.published_at is None
    assert undated.summary is None  # same as the title -> dropped


def test_atom_parse_link_and_dates() -> None:
    items = parse_feed(_load("atom_sample.xml"))
    assert [i.url for i in items] == [
        "https://atom.example.com/it-rally",
        "https://atom.example.com/second",
    ]
    assert items[0].title == "Infosys & TCS lead IT rally"
    assert items[0].summary == "Nifty IT up 3%."
    assert items[0].published_at == datetime(2026, 11, 21, 5, 30, tzinfo=UTC)
    # published wins over updated, converted from +05:30
    assert items[1].published_at == datetime(2026, 11, 20, 22, 30, tzinfo=UTC)


def test_non_feed_documents_are_rejected() -> None:
    with pytest.raises(FeedParseError):
        parse_feed(b"<html><body>Access denied</body></html>")
    with pytest.raises(FeedParseError):
        parse_feed(b"")
    with pytest.raises(TypeError):
        parse_feed("https://example.com/rss")  # type: ignore[arg-type]


def test_normalize_url_and_clean_text() -> None:
    assert normalize_url("ftp://x.com/a") is None
    assert normalize_url("javascript:alert(1)") is None
    assert (
        normalize_url(" https://X.com/a?b=1&utm_source=z&fbclid=q#frag ") == "https://x.com/a?b=1"
    )
    assert clean_text("  <p>a&nbsp;b</p>\n\n c ", 100) == "a b c"
    assert clean_text("<br/>", 100) is None
    long = clean_text("x" * 50, 10)
    assert long is not None and len(long) == 10 and long.endswith("…")


def test_feed_list_defaults_and_names() -> None:
    assert [f.url for f in parse_feed_list("")] == list(DEFAULT_FEEDS)
    feeds = parse_feed_list(
        "https://www.livemint.com/rss/markets, ftp://bad, https://www.livemint.com/rss/markets,"
        " https://blog.example.org/feed/"
    )
    assert [f.source for f in feeds] == ["LiveMint Markets", "blog.example.org"]
    assert (
        source_name("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms")
        == "Economic Times Markets"
    )


ENTRIES = [
    SymbolEntry("RELIANCE", "RELIANCE INDUSTRIES LTD"),
    SymbolEntry("SBIN", "STATE BANK OF INDIA"),
    SymbolEntry("SBILIFE", "SBI LIFE INSURANCE CO LTD"),
    SymbolEntry("HDFCBANK", "HDFC BANK LTD"),
    SymbolEntry("LT", "LARSEN & TOUBRO LTD."),
    SymbolEntry("M&M", "MAHINDRA & MAHINDRA LTD"),
    SymbolEntry("ETERNAL", "ETERNAL LIMITED"),
    SymbolEntry("TCS", "TATA CONSULTANCY SERV LT"),
    SymbolEntry("NIFTY", "Nifty 50"),
    SymbolEntry("BANKNIFTY", "Nifty Bank"),
    SymbolEntry("ITC", "ITC LTD"),
    SymbolEntry("DRREDDY", "DR. REDDY S LABORATORIES"),
    SymbolEntry("ACMESOLAR", "ACME SOLAR HOLDINGS LTD"),  # not curated: derived alias
]
M = SymbolMatcher(ENTRIES)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Reliance shares rise 2% after Q2", ["RELIANCE"]),
        ("RIL to raise funds; Reliance's retail arm grows", ["RELIANCE"]),
        ("Reliance Power hits upper circuit", []),
        ("Reliance Infrastructure and Reliance Capital slide", []),
        ("SBI raises lending rates", ["SBIN"]),
        ("SBI Life slips 3%", ["SBILIFE"]),
        ("State Bank of India Q2 profit", ["SBIN"]),
        ("L&T bags order; Larsen and Toubro shares up", ["LT"]),
        ("LT Foods rallies", []),
        ("M&M and Mahindra & Mahindra EV unit", ["M&M"]),
        ("Eternal (Zomato) posts profit", ["ETERNAL"]),
        ("Markets in eternal optimism", []),
        ("TCS, Tata Consultancy Services results", ["TCS"]),
        ("Nifty ends at record; Bank Nifty flat", ["BANKNIFTY", "NIFTY"]),
        ("Nifty Bank and Nifty IT outperform", ["BANKNIFTY"]),
        ("ITC demerger; itc hotels listing", ["ITC"]),
        ("Dr Reddy's recalls drug", ["DRREDDY"]),
        ("ACME Solar Holdings wins bid", ["ACMESOLAR"]),
        ("HDFC Bank and HDFC Life gain", ["HDFCBANK"]),
        ("Gold prices steady", []),
    ],
)
def test_symbol_matcher(text: str, expected: list[str]) -> None:
    assert M.tags(text) == expected


def test_matcher_uses_summary_and_mentions() -> None:
    assert M.tags("Banks rally", "State Bank of India leads") == ["SBIN"]
    assert M.mentions("reliance", "Reliance up", None)
    assert not M.mentions("UNKNOWN", "Reliance up")


def test_derived_alias() -> None:
    assert derived_alias("TATA STEEL LIMITED") == "TATA STEEL"
    assert derived_alias("HINDALCO  INDUSTRIES  LTD") == "HINDALCO INDUSTRIES"
    assert derived_alias("ITC LTD") is None  # too short to be a safe alias
    assert derived_alias(None) is None
