"""Historical replay: server-driven clock over stored 1-minute candles with an optional
strategy overlay that runs the exact paper flow (engine -> risk -> simulator -> book)
on virtual capital. Ephemeral: nothing is written to paper_* tables (ADR-002)."""
