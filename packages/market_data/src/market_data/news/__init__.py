"""Raw news headlines (Mark 1 Stage 3.5): RSS ingest, dedup by URL, deterministic symbol
tagging. No AI here; analysis waits for Stage 4."""

from market_data.news.feeds import DEFAULT_FEEDS, FeedSpec, parse_feed_list, source_name
from market_data.news.parser import ParsedItem, parse_feed
from market_data.news.tagger import SymbolEntry, SymbolMatcher

__all__ = [
    "DEFAULT_FEEDS",
    "FeedSpec",
    "ParsedItem",
    "SymbolEntry",
    "SymbolMatcher",
    "parse_feed",
    "parse_feed_list",
    "source_name",
]
