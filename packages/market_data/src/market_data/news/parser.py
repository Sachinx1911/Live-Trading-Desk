"""RSS / Atom parsing into raw headline rows. Title, link, feed summary and published time
only: article pages are never fetched (no scraping)."""

from __future__ import annotations

import calendar
import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser  # type: ignore[import-untyped]

SUMMARY_MAX = 1000
TITLE_MAX = 500
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_TRACKING = ("utm_", "fbclid", "gclid", "ref_src")


class FeedParseError(ValueError):
    """The document is not a usable RSS/Atom feed."""


@dataclass(frozen=True)
class ParsedItem:
    url: str
    title: str
    summary: str | None
    published_at: datetime | None  # aware UTC (ADR-006)


def clean_text(value: str | None, limit: int) -> str | None:
    """Strip tags and entities, collapse whitespace, cut to `limit` characters."""
    if not value:
        return None
    text = _WS.sub(" ", html.unescape(_TAG.sub(" ", value))).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_url(url: str) -> str | None:
    """http(s) only; drops the fragment and tracking parameters so the same story dedups."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING)
    ]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urlencode(query), ""))


def _published(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(key)
        if st:
            # feedparser normalises to UTC struct_time
            return datetime.fromtimestamp(calendar.timegm(st), tz=UTC)
    return None


def parse_feed(content: bytes) -> list[ParsedItem]:
    """Parse a feed document (bytes, never a URL: feedparser would fetch a str URL itself)."""
    if not isinstance(content, bytes | bytearray):
        raise TypeError("parse_feed expects the document bytes")
    doc = feedparser.parse(bytes(content))
    if not doc.get("version") and not doc.entries:
        exc = doc.get("bozo_exception")
        raise FeedParseError(f"not an RSS/Atom document: {exc or 'no entries'}")
    out: list[ParsedItem] = []
    seen: set[str] = set()
    for e in doc.entries:
        link = e.get("link") or ""
        if not link:
            for lk in e.get("links") or []:
                if lk.get("rel", "alternate") == "alternate" and lk.get("href"):
                    link = lk["href"]
                    break
        url = normalize_url(link) if link else None
        title = clean_text(e.get("title"), TITLE_MAX)
        if not url or not title or url in seen:
            continue
        seen.add(url)
        summary = clean_text(e.get("summary") or e.get("description"), SUMMARY_MAX)
        if summary == title:
            summary = None
        out.append(ParsedItem(url=url, title=title, summary=summary, published_at=_published(e)))
    return out
