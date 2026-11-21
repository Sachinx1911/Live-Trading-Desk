"""Configured RSS/Atom feeds (NEWS_FEEDS) and their display names.

Defaults were checked with a real HTTP GET on 2026-11-21. The AI-MIOS list also had
Moneycontrol Markets and Moneycontrol Business; both still answer 200 but their newest item
is from 2024-04-23 (frozen feeds), so they are not defaults. An owner can still add any feed
through NEWS_FEEDS; a frozen feed is reported as stale in `ingest_errors`.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_FEEDS: tuple[str, ...] = (
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.livemint.com/rss/markets",
)

# host + path -> display name. Unknown feeds fall back to the host name.
KNOWN_SOURCES: dict[str, str] = {
    "economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms": "Economic Times Markets",
    "economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms": "Economic Times Stocks",
    "livemint.com/rss/markets": "LiveMint Markets",
    "livemint.com/rss/companies": "LiveMint Companies",
    "moneycontrol.com/rss/marketreports.xml": "Moneycontrol Markets",
    "moneycontrol.com/rss/business.xml": "Moneycontrol Business",
    "business-standard.com/rss/markets-106.rss": "Business Standard Markets",
}


@dataclass(frozen=True)
class FeedSpec:
    url: str
    source: str


def source_name(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").removeprefix("www.")
    key = f"{host}{parts.path}".rstrip("/")
    return KNOWN_SOURCES.get(key, host or url)


def parse_feed_list(raw: str | None) -> list[FeedSpec]:
    """Comma-separated http(s) URLs; empty -> defaults. Duplicates and non-http entries drop."""
    urls = [u.strip() for u in (raw or "").split(",") if u.strip()] or list(DEFAULT_FEEDS)
    out: list[FeedSpec] = []
    seen: set[str] = set()
    for u in urls:
        if urlsplit(u).scheme not in ("http", "https") or u in seen:
            continue
        seen.add(u)
        out.append(FeedSpec(url=u, source=source_name(u)))
    return out
