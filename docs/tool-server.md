# Tool server (Mark 1 Stage 4.1)

The tool server is how the owner's own assistant, **jarvis** (`Sachinx1911/jarvis`, its own
repo, see `references/sachinx1911-jarvis.md`), reads Live-Trading-Desk. It serves one tool
catalogue over two transports: a typed HTTP API and MCP. No LLM runs here, and no tool places,
modifies or cancels an order (CLAUDE.md rules 1-2).

- App: `apps/tool_server` (`tool_server.main`), port **8100**, bound to **127.0.0.1** by default.
- Catalogue: `packages/protocols/src/protocols/catalogue.py`, a thin layer over the protocol
  action registry (`protocols.actions.REGISTRY`, plus the Stage 4 read actions in
  `protocols/read_actions.py`). One list of what the platform can do, used by protocols and the
  tool server alike.
- Tokens and the call log: tables `tool_tokens`, `tool_calls` (migration 0015), managed from the
  web app at **Settings → Tool server** (`/settings/tools`).

## Run it

```bash
make tool-server            # uv run python -m tool_server.main
curl -s http://127.0.0.1:8100/healthz
```

Settings (`.env`, documented in `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `TOOL_SERVER_HOST` | `127.0.0.1` | Loopback only. Set a LAN address only if jarvis runs on another machine (the token still guards every call; MCP DNS-rebinding protection allows only this host and loopback). |
| `TOOL_SERVER_PORT` | `8100` | HTTP and MCP on the same port. |
| `TOOL_SERVER_MAX_LEVEL` | `green` | The highest level the server serves (`green` or `yellow`). The token's own `max_level` can only lower it. Red is never served. |
| `TOOL_SERVER_RATE_PER_MINUTE` | `120` | Per-token calls per minute (in-memory token bucket). |

The server uses the same `DATABASE_URL`, `REDIS_URL`, `SECRETS_KEY` and
`DEFAULT_MARKET_DATA_PROVIDER` as the API.

## Auth

1. The owner creates a token at `/settings/tools` (or `POST /api/v1/tool-tokens`
   `{name, max_level}`). The plaintext (`ltd_…`) is shown **once**; only its SHA-256 is stored.
   The list shows the first 12 characters (prefix) to tell tokens apart.
2. jarvis stores it in its Keychain and sends `Authorization: Bearer <token>` on every request
   (HTTP and MCP).
3. Unknown or revoked tokens are refused (401). Revoking at `/settings/tools` (or
   `POST /api/v1/tool-tokens/{id}/revoke`) takes effect on the next call.
4. Effective level = the lower of `TOOL_SERVER_MAX_LEVEL` and the token's `max_level`.

Every call is written to `tool_calls` (append-only authority log): time, token, transport,
tool, level, arguments (scrubbed: keys such as `token`/`secret`/`api_key` and any token-shaped
or secret value are replaced by `[redacted]`), status `ok | error | refused`, error text,
duration and a small `result_meta` (source, freshness, is_demo, row counts). Refusals are
logged too: missing/invalid/revoked token, unknown tool, level not allowed, rate limit, bad
arguments, timeout. Without a log row there is no answer. The owner reads the log at
`/settings/tools` or `GET /api/v1/tool-calls?status=&tool=&token_id=&transport=&limit=`.

Neither the token, its hash, broker credentials, broker session tokens nor `SECRETS_KEY` ever
appear in a response, a `tool_calls` row, the audit trail or the logs (secret-scan test in
`apps/tool_server/tests/test_db_tools.py`).

## Levels and jarvis tiers

| Level | jarvis tier | jarvis does | Stage 4 |
|---|---|---|---|
| Green (read only) | **T0** | runs it | served |
| Yellow with standing permission (paper changes, kill switch ON) | **T1** | runs it, then reports | listed, not callable (Stage 5) |
| Other yellow | **T2** | asks the owner first | none exist yet |
| Red (money, safety, live) | none | never offered | **never exposed**; cannot be registered in the catalogue |

The server enforces this itself, whatever the caller sends (hypothesis property test over both
transports). jarvis's tier mapping is a second line, not the first.

## Every answer carries provenance (CLAUDE.md rule 5)

Every tool result has `source`, `freshness` and `is_demo`, and a one-line `summary`.
`freshness` is one of `live | delayed | stale | historical | disconnected | demo` (the values of
`core.models.Freshness`) or `none` when the answer has no market source (health, protocol runs,
owner rules, news headlines) or nothing is stored. jarvis must repeat these and never present
demo, stale or historical data as live. Missing data is reported as missing (`status:
"no_data"` with the reason); nothing is invented. Decimal values are sent as strings so they
stay exact.

Examples of honest answers: with the market closed and the broker token expired, `quote` says
`disconnected` with the reason ("NSE market closed; collector …") and the last stored close
labelled `historical`; a chain snapshot from the previous session is `historical`; anything
from the fake provider is `demo` with `is_demo: true`.

## Tools (Stage 4)

All green / T0. `GET /tools` returns each one's JSON Schemas, level, tier and timeout.

| Tool | What it answers | Example arguments |
|---|---|---|
| `quote` | Latest cached quote per symbol with its freshness; disconnected (with reason and last stored close) when there is none | `{"symbols": ["NIFTY", "BANKNIFTY"]}` |
| `candles` | Last N stored candles, active provider only | `{"symbol": "NIFTY", "timeframe": "5m", "limit": 50}` |
| `option_chain` | Newest stored chain around ATM: LTP, OI, OI change, volume, IV, PCR | `{"underlying": "NIFTY", "expiry": "2026-11-25", "strikes_around_atm": 5}` |
| `oi_change` | Per-strike call/put OI change between two IST times of one day | `{"underlying": "BANKNIFTY", "start": "09:15", "end": "11:00"}` |
| `greeks` | IV and Greeks as the provider sent them, newest or as of `at` | `{"underlying": "NIFTY", "strikes_around_atm": 3}` |
| `pcr` | PCR by OI vs the owner's pcr_guard thresholds | `{"symbols": ["NIFTY"]}` |
| `regime` | Stored daily regime and today's day type | `{"symbols": ["NIFTY", "BANKNIFTY"]}` |
| `breadth` | Stored daily breadth (A/D, 52w highs/lows, % above EMAs) | `{"universe": "NIFTY50"}` |
| `scanner_run` | Preset or ad-hoc filters over the latest nightly snapshot | `{"preset": "Top gainers", "limit": 10}` |
| `backtest_results` | Recent jobs with headline metrics, or one job's metrics | `{"limit": 5}` / `{"job_id": 12}` |
| `paper_positions` | Open paper positions with unrealised P&L | `{}` |
| `paper_pnl` | Paper realised P&L for day/week/month/custom, plus open P&L | `{"period": "week"}` |
| `paper_status` | Paper accounts at a glance (cash, day P&L, running strategies, halts) | `{}` |
| `health` | Every process and broker session in one answer | `{}` |
| `broker_sessions` | Broker session state and expiry (no secrets) | `{}` |
| `alerts` | Stored alerts, newest first | `{"hours": 24, "unacknowledged_only": true}` |
| `events_today` | Today's stored market events | `{}` |
| `daily_report` | Stored evening brief, latest or for a date | `{"day": "2026-11-20"}` |
| `news` | Recent headlines, optionally for one symbol | `{"symbol": "RELIANCE", "hours": 24}` |
| `protocol_status` | Recent protocol runs and their outcomes | `{"limit": 5}` |
| `owner_rules` | The owner's hard trading rules and thresholds | `{}` |
| `record_view` | Record a market view JARVIS stated, with our reference price, to be scored later (writes one measurement row; never read by trading) | `{"symbol": "NIFTY", "direction": "up", "horizon_days": 5, "confidence": "0.65", "invalidation_price": "25000"}` |

Listed for planning, **not callable in Stage 4** (yellow, T1, `planned_stage: 5`):
`kill_switch_on` (a jarvis `/stop` or "Clean Slate" maps here; it only ever turns trading
**off**; turning the kill switch off stays red, owner only in the web UI),
`stop_paper_strategies`, `close_paper_positions`. Nothing in the catalogue turns trading on.

`record_view` (Stage 4.6 accuracy loop) is registered in `apps/tool_server/views_tool.py`
through `protocols.catalogue.register_tool` as a green tool with `writes=True`. It lives in the
app, not in `packages/protocols`, so that nothing the paper trader imports can reach the views
module. The server sets the caller to `jarvis` and takes the reference price itself.

## HTTP

```bash
TOKEN=...   # from /settings/tools, never commit or log it
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8100/tools | jq '.tools[].name'
curl -s -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"symbols":["NIFTY"]}' http://127.0.0.1:8100/tools/quote | jq
```

`POST /tools/{name}` takes a JSON object of arguments and answers

```json
{"ok": true,  "tool": "quote", "call_id": 42, "result": {"source": "...", "freshness": "...", "is_demo": false, "summary": "...", "...": "..."}}
{"ok": false, "tool": "kill_switch_on", "call_id": 43, "error": {"code": "level_not_allowed", "message": "..."}}
```

Status codes: 200 ok, 401 `unauthorized`, 403 `level_not_allowed`, 404 `unknown_tool`,
422 `bad_args` / `tool_error`, 429 `rate_limited`, 504 `timeout`, 500 `internal` (exception
type only), 503 `log_unavailable`.

## MCP

Streamable HTTP at `http://127.0.0.1:8100/mcp` (official `mcp` Python SDK, low-level server,
stateless, JSON responses). Same tools, same JSON Schemas (`inputSchema`, `outputSchema`),
level/tier/timeout in each tool's `_meta`, results as `structuredContent` plus a JSON text
block, errors with `isError: true`. The bearer token is required on every request; without a
valid one the endpoint answers 401 before MCP is reached.

```python
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})
async with http, Client(streamable_http_client("http://127.0.0.1:8100/mcp", http_client=http)) as c:
    tools = await c.list_tools()
    res = await c.call_tool("health", {})
```

jarvis has its own in-process typed tool registry and no MCP client: it can use the typed HTTP
API directly (GET `/tools` gives everything needed to generate its tool definitions); MCP is
there for any MCP-speaking client.

## How jarvis should map it

- One connector `trading` pointing at `http://127.0.0.1:8100`, health check `GET /healthz`,
  token from the Keychain.
- Build tool definitions from `GET /tools`: `name`, `description` (purpose + example call),
  `input_schema`, and the tier from `tier` (T0 here; anything not in `tools` is not callable).
  `not_callable` lists planned tools with the reason.
- Always repeat `source`, `freshness` and `is_demo` when speaking a number; say "demo" or
  "market closed / stale" out loud. Every number comes from a tool; if a tool says
  `no_data`, say so.
- Put "no orders from an LLM" and the owner rules (`owner_rules` tool) in the trading
  workspace's constraints; the tool server enforces them anyway.
