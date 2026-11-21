# 05 · Strategy DSL v1

Per ADR-003 the DSL is the **only** executable form of a strategy. The natural-language
builder, the visual builder and AI research all emit this document; the strategy engine
(`packages/strategy/engine`) executes only this document; backtest, replay, paper and live
all run the same engine (ADR-002). No code is ever executed from a strategy.

Implementation: Pydantic v2 models in `packages/strategy/dsl/models.py`; JSON Schema is
exported to `packages/strategy/dsl/schema/v1.json` and served at
`GET /api/v1/strategies/dsl-schema`. The LLM is given this schema as its structured-output
schema.

---

## 1. Design rules

1. **Declarative.** The document states conditions; the engine decides *how* to evaluate.
2. **Closed bars only.** Every indicator and price reference is evaluated on the last
   *closed* bar of its timeframe. The engine never exposes the forming bar to a rule.
3. **Named indicators.** Every indicator is declared once under `indicators` with an id and
   referenced by id. This makes warm-up, caching and validation deterministic.
4. **No silent defaults for user intent.** Fields that express the user's intent (entry,
   exit, stop, target, sizing) are `null` until stated. Engine defaults exist only for
   mechanics (e.g. `fill.order_type`), and are listed in §9.
5. **Versioned.** `dsl_schema_version` is mandatory; the engine refuses unknown versions.

## 2. Top-level document

```python
class StrategyDSL(BaseModel):
    dsl_schema_version: Literal["1.0"]
    name: str                                 # ≤ 80 chars
    description: str | None
    origin: Literal["user_nl", "user_visual", "ai_research", "import"]
    original_text: str | None                 # verbatim user description (never altered)
    language: Literal["mr", "hi", "en"] | None

    market: str                               # exchange code, e.g. "NSE"
    universe: Universe                        # what to trade
    timeframe: Timeframe                      # primary bar size for rules
    context_timeframes: list[Timeframe] = []  # higher TFs referenced by indicators (max 2)

    session: SessionRules
    regime_filters: list[RegimeFilter] = []
    time_filters: list[TimeFilter] = []

    indicators: dict[str, IndicatorSpec]      # id -> spec

    entry: EntryRules | None                  # null = missing (NL draft)
    exit: ExitRules | None
    stop_loss: StopSpec | None
    target: TargetSpec | None
    trailing: TrailingSpec | None

    position_sizing: PositionSizing | None
    max_positions: int = 1                    # concurrent open positions for this strategy
    max_trades_per_day: int | None
    direction: Literal["long_only", "short_only", "both"] = "long_only"

    fill: FillPreferences = FillPreferences()
    metadata: dict[str, str] = {}
```

### 2.1 Universe
```python
class Universe(BaseModel):
    kind: Literal["instrument", "underlying_future", "underlying_option", "watchlist", "scanner"]
    instrument_ids: list[str] = []            # kind=instrument
    underlying: str | None                    # "NIFTY", "BANKNIFTY" for derivatives
    contract: ContractSelector | None         # kind=underlying_*
    watchlist_id: str | None
    scanner_id: str | None

class ContractSelector(BaseModel):
    expiry: Literal["current_week", "next_week", "current_month", "next_month"]
    option_type: Literal["CE", "PE"] | None
    strike: Literal["ATM", "ITM1", "ITM2", "OTM1", "OTM2", "OTM3"] | None
    roll_days_before_expiry: int = 1          # switch contract N days before expiry
```
`Timeframe = Literal["1m","3m","5m","15m","30m","1h","1d","1w"]`.

### 2.2 Session rules
```python
class SessionRules(BaseModel):
    product: Literal["INTRADAY", "DELIVERY", "CARRY_FORWARD"]
    trade_start: str | None       # "09:20" exchange local; null = session open
    no_new_entries_after: str | None   # "14:45"
    square_off_at: str | None     # "15:15"; REQUIRED when product == INTRADAY
    skip_first_minutes: int = 0   # ignore bars within N minutes of open
    trade_on_expiry_day: bool = True
    allowed_weekdays: list[int] = [0,1,2,3,4]   # Mon=0
```
Times are exchange-local strings; the engine converts via the exchange timezone (ADR-006).

### 2.3 Regime and time filters
```python
class RegimeFilter(BaseModel):
    source: Literal["vix", "adx", "daily_trend", "regime_label"]
    # vix:   min / max level
    # adx:   indicator_id + min (trend strategies) or max (mean reversion)
    # daily_trend: "up" | "down" | "sideways" from the daily structure detector
    # regime_label: one of the platform's regime records: trending|sideways|bullish|bearish|high_vol|low_vol
    min: float | None
    max: float | None
    indicator_id: str | None
    allowed: list[str] | None

class TimeFilter(BaseModel):
    start: str          # "09:30"
    end: str            # "11:30"
    mode: Literal["allow_entries", "block_entries"]
```
Filters gate **entries only**; exits, stops and square-off always run.

## 3. Indicators

```python
class IndicatorSpec(BaseModel):
    type: IndicatorType
    params: dict[str, float | int | str]
    source: PriceField = "close"            # where applicable
    timeframe: Timeframe | None             # null = primary; else must be in context_timeframes
```

### 3.1 Catalogue v1

| type | params | outputs (fields) | notes |
|---|---|---|---|
| `EMA` | `period` | `value` | |
| `SMA` | `period` | `value` | |
| `RSI` | `period` (default 14) | `value` | Wilder smoothing |
| `ATR` | `period` (14) | `value` | true range, Wilder |
| `VWAP` | `anchor`: `session` | `value`, `upper_1`, `lower_1`, `upper_2`, `lower_2` | σ bands; resets each session |
| `SUPERTREND` | `period` (10), `multiplier` (3) | `value`, `direction` (+1/−1) | |
| `BOLLINGER` | `period` (20), `std` (2) | `upper`, `middle`, `lower`, `width` | |
| `ADX` | `period` (14) | `value`, `plus_di`, `minus_di` | |
| `MACD` | `fast` (12), `slow` (26), `signal` (9) | `macd`, `signal`, `hist` | |
| `VOLUME_SMA` | `period` | `value` | volume average |
| `PREV_DAY` | – | `high`, `low`, `close` | previous session's values, constant for the day |
| `OPENING_RANGE` | `minutes` (15) | `high`, `low` | defined after first N minutes; `null` before → conditions false |
| `OI_CHANGE` | `lookback_bars` | `value`, `pct` | derivatives only; `null` if OI unavailable → condition false |
| `SWING` | `left` (5), `right` (5) | `last_high`, `last_low` | confirmed swing points (structure levels) |
| `DAILY_TREND` | `fast` (20), `slow` (50) | `label` (`up`/`down`/`sideways`) | daily EMA relation + slope |

Adding an indicator is a code change with reference tests against TA-Lib values.

### 3.2 Operands
```python
class IndicatorRef(BaseModel):
    kind: Literal["indicator"]; id: str; field: str = "value"; offset: int = 0   # offset=1 → previous closed bar
class PriceRef(BaseModel):
    kind: Literal["price"]; field: PriceField; offset: int = 0
class ConstRef(BaseModel):
    kind: Literal["const"]; value: float
class ArithRef(BaseModel):                     # limited arithmetic for things like "VWAP + 0.5*ATR"
    kind: Literal["arith"]; op: Literal["+","-","*","/"]; left: Operand; right: Operand

Operand = IndicatorRef | PriceRef | ConstRef | ArithRef
PriceField = Literal["open","high","low","close","volume","oi"]
```
`offset` is ≥ 0 (past bars only). `ArithRef` nesting depth ≤ 2.

**DSL 1.1 (Mark 1, Stage 2): `OptionRef`.** Option-chain facts of the traded instrument's
underlying (the index itself, or the underlying of an option / future contract):

```python
class OptionRef(BaseModel):
    kind: Literal["option"]
    feature: Literal["pcr", "iv_atm", "oi", "oi_change_from_open", "greek"]
    side: Literal["CE", "PE"] | None = None        # required for oi, oi_change_from_open, greek
    strike_offset: int = 0                          # -10..10 strikes from ATM
    greek: Literal["delta", "gamma", "theta", "vega", "iv"] | None = None  # feature greek only
```

Values come from the last stored chain snapshot (nearest unexpired expiry) at or before the
bar's start time, never a later one (`strategy.option_features.ChainHistory`); the same code
serves backtest, replay and paper (ADR-002). `pcr` = total put OI / total call OI;
`iv_atm` = mean of the ATM call and put IV; `oi_change_from_open` is against the first
snapshot at or after 09:15 IST of that day. Missing data gives no value, so the condition is
false; the validator warns that such strategies only trade where chain history exists, and
refuses `option` operands in a `1.0` document.

## 4. Condition grammar

```python
class Compare(BaseModel):
    kind: Literal["compare"]
    left: Operand
    op: Literal["gt","gte","lt","lte","eq"]
    right: Operand

class Cross(BaseModel):
    kind: Literal["cross"]
    left: Operand
    direction: Literal["crosses_above","crosses_below"]
    right: Operand
    # true only on the bar where left[0] vs right[0] flips relative to left[1] vs right[1]

class Between(BaseModel):
    kind: Literal["between"]; value: Operand; low: Operand; high: Operand

class Slope(BaseModel):
    kind: Literal["slope"]; value: Operand
    direction: Literal["rising","falling"]; bars: int           # value[0] vs value[bars], strictly monotonic optional
    strict: bool = False

class Label(BaseModel):                 # for categorical outputs (SUPERTREND.direction, DAILY_TREND.label)
    kind: Literal["label"]; value: IndicatorRef; equals: str | float

class Group(BaseModel):
    kind: Literal["group"]; op: Literal["and","or"]; conditions: list[Condition]   # 1..10 children, depth ≤ 4

class Not(BaseModel):
    kind: Literal["not"]; condition: Condition

Condition = Compare | Cross | Between | Slope | Label | Group | Not
```

## 5. Entry and exit

```python
class EntryRules(BaseModel):
    long: Condition | None       # required if direction in (long_only, both)
    short: Condition | None      # required if direction in (short_only, both)
    confirm_bars: int = 0        # condition must hold for N consecutive closed bars
    cooldown_bars: int = 0       # bars to wait after an exit before re-entry
    one_entry_per_signal: bool = True

class ExitRules(BaseModel):
    long: Condition | None       # rule-based exit for long positions
    short: Condition | None
    time_exit_bars: int | None   # exit after N bars in trade
    exit_on_opposite_signal: bool = False
```
A position closes on the **first** of: stop hit, target hit, trailing stop hit, exit rule,
time exit, session square-off, kill switch/deactivation.

## 6. Stop, target, trailing

```python
class LevelSpec(BaseModel):
    unit: Literal["points", "percent", "atr", "structure", "indicator"]
    value: float | None               # points / percent / ATR multiple
    atr_indicator_id: str | None      # unit=atr
    structure: Literal["swing_low","swing_high","prev_day_low","prev_day_high","opening_range_low","opening_range_high"] | None
    structure_indicator_id: str | None
    indicator_ref: IndicatorRef | None   # unit=indicator (e.g. exit at VWAP)
    buffer_points: float = 0

class StopSpec(LevelSpec):
    pass                              # distance below entry (long) / above (short)

class TargetSpec(LevelSpec):
    rr_multiple: float | None         # alternative: target = rr × stop distance (unit may then be omitted)
    partial: list[PartialTarget] = [] # scale-out

class PartialTarget(BaseModel):
    at: LevelSpec; close_pct: float    # 0 < close_pct ≤ 100; sum ≤ 100
    move_stop_to_breakeven: bool = False

class TrailingSpec(BaseModel):
    mode: Literal["atr", "percent", "points", "indicator", "swing"]
    value: float | None
    atr_indicator_id: str | None
    indicator_ref: IndicatorRef | None   # e.g. trail at SUPERTREND.value
    activate_after: LevelSpec | None     # start trailing only after this profit
```

## 7. Position sizing

```python
class PositionSizing(BaseModel):
    method: Literal["fixed_lots", "fixed_quantity", "fixed_capital", "risk_percent"]
    lots: int | None                  # fixed_lots (derivatives)
    quantity: int | None              # fixed_quantity (equity)
    capital: float | None             # fixed_capital: qty = floor(capital / price), lot-rounded
    risk_percent: float | None        # risk_percent: qty = floor(account_equity × risk% / stop_distance), lot-rounded
    max_lots: int | None              # hard cap regardless of method
    max_capital_pct: float | None     # cap notional at % of equity
```
`risk_percent` requires a `stop_loss`. The **risk engine** may still reduce or reject the
size (ADR-007); the DSL expresses intent, the risk engine enforces limits.

## 8. Fill preferences

```python
class FillPreferences(BaseModel):
    entry_order_type: Literal["MARKET", "LIMIT_AT_CLOSE", "LIMIT_OFFSET"] = "MARKET"
    limit_offset_points: float = 0
    limit_timeout_bars: int = 1       # cancel unfilled limit after N bars
    stop_order_type: Literal["SL_MARKET", "SL_LIMIT"] = "SL_MARKET"
```
Mechanics only; evaluated identically by simulator and live gateway.

## 9. Validation rules

Run by `POST /strategies/{id}/versions/{vid}/validate`; a version cannot leave `draft`
until the report has no errors. Warnings are allowed but shown.

**Structural (errors)**
- `dsl_schema_version` supported.
- Every `IndicatorRef.id` exists in `indicators`; every `field` exists for that type.
- Indicator `timeframe` is the primary or listed in `context_timeframes`.
- `ArithRef` depth ≤ 2; `Group` depth ≤ 4, children 1–10.
- `offset ≥ 0` everywhere (no look-ahead). `Cross` operands may not both be constants.
- `direction` ↔ `entry.long/short` presence consistent.
- `session.square_off_at` present when `product == INTRADAY` and before session close.
- `time_filters` and `session` windows are within the exchange session.
- `risk_percent` sizing requires `stop_loss`; `rr_multiple` target requires `stop_loss`.
- Partial targets sum ≤ 100 %.
- Universe resolves to ≥ 1 instrument on the validation date.

**Completeness (errors for `validated`, listed as `missing_information` for drafts)**
- `entry`, `position_sizing` present.
- `exit` or `target` present (a strategy must be able to leave a trade by rule, not only by stop/square-off).

**Live-readiness (errors for `approved_live`)**
- `stop_loss` present and finite.
- `position_sizing.max_lots` or `max_capital_pct` present.
- `max_trades_per_day` present.
- No indicator with `period > 500` bars on the primary timeframe (warm-up bound).
- `context_timeframes` ≤ 2.

**Warnings**
- More than 3 tunable numeric parameters (over-fitting risk; surfaced to optimisation).
- Entry condition contains > 6 leaf conditions.
- `confirm_bars == 0` with `Cross` on noisy indicators (RSI) — suggestion only.

**Warm-up:** the engine computes `warmup_bars = max(period-like params) × 3` per timeframe
and will not evaluate rules until that many closed bars exist; backtests report the
effective start date.

## 10. Worked examples

### 10.1 Master-prompt example → full DSL (after clarification answers)
User text (mr): *"EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर आणि RSI 55 पेक्षा जास्त असल्यास Buy करा."*
Clarifications answered: exit on opposite cross; stop 1 ATR; target 2 ATR; 1 lot; intraday.

```json
{
  "dsl_schema_version": "1.0",
  "name": "NIFTY EMA Momentum",
  "origin": "user_nl", "language": "mr",
  "original_text": "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर आणि RSI 55 पेक्षा जास्त असल्यास Buy करा.",
  "market": "NSE",
  "universe": { "kind": "underlying_future", "underlying": "NIFTY",
                "contract": { "expiry": "current_month", "roll_days_before_expiry": 1 } },
  "timeframe": "5m",
  "session": { "product": "INTRADAY", "trade_start": "09:20", "no_new_entries_after": "14:45", "square_off_at": "15:15" },
  "regime_filters": [],
  "indicators": {
    "ema9":  { "type": "EMA", "params": { "period": 9 } },
    "ema21": { "type": "EMA", "params": { "period": 21 } },
    "rsi14": { "type": "RSI", "params": { "period": 14 } },
    "atr14": { "type": "ATR", "params": { "period": 14 } }
  },
  "direction": "long_only",
  "entry": {
    "long": { "kind": "group", "op": "and", "conditions": [
      { "kind": "cross", "left": { "kind": "indicator", "id": "ema9" }, "direction": "crosses_above", "right": { "kind": "indicator", "id": "ema21" } },
      { "kind": "compare", "left": { "kind": "indicator", "id": "rsi14" }, "op": "gt", "right": { "kind": "const", "value": 55 } }
    ] }
  },
  "exit": {
    "long": { "kind": "cross", "left": { "kind": "indicator", "id": "ema9" }, "direction": "crosses_below", "right": { "kind": "indicator", "id": "ema21" } }
  },
  "stop_loss": { "unit": "atr", "value": 1.0, "atr_indicator_id": "atr14" },
  "target":    { "unit": "atr", "value": 2.0, "atr_indicator_id": "atr14" },
  "position_sizing": { "method": "fixed_lots", "lots": 1, "max_lots": 1 },
  "max_positions": 1, "max_trades_per_day": 3
}
```
The NL draft before answers has `exit: null`, `stop_loss: null`, `target: null`,
`position_sizing: null`, `session.square_off_at: null` and
`missing_information: ["Exit condition","Stop loss","Target","Position sizing","Product/square-off"]`.

### 10.2 VWAP mean reversion, intraday, both directions
```json
{
  "dsl_schema_version": "1.0",
  "name": "BANKNIFTY VWAP Reversion",
  "origin": "user_visual", "market": "NSE",
  "universe": { "kind": "underlying_future", "underlying": "BANKNIFTY", "contract": { "expiry": "current_month" } },
  "timeframe": "5m", "context_timeframes": ["15m"],
  "session": { "product": "INTRADAY", "trade_start": "09:45", "no_new_entries_after": "14:30", "square_off_at": "15:10", "trade_on_expiry_day": false },
  "regime_filters": [
    { "source": "adx", "indicator_id": "adx15", "max": 25 },
    { "source": "vix", "min": 10, "max": 22 }
  ],
  "time_filters": [ { "start": "12:00", "end": "13:00", "mode": "block_entries" } ],
  "indicators": {
    "vwap":  { "type": "VWAP", "params": { "anchor": "session" } },
    "rsi7":  { "type": "RSI",  "params": { "period": 7 } },
    "atr14": { "type": "ATR",  "params": { "period": 14 } },
    "adx15": { "type": "ADX",  "params": { "period": 14 }, "timeframe": "15m" }
  },
  "direction": "both",
  "entry": {
    "long": { "kind": "group", "op": "and", "conditions": [
      { "kind": "compare", "left": { "kind": "price", "field": "close" }, "op": "lt", "right": { "kind": "indicator", "id": "vwap", "field": "lower_2" } },
      { "kind": "compare", "left": { "kind": "indicator", "id": "rsi7" }, "op": "lt", "right": { "kind": "const", "value": 25 } },
      { "kind": "slope", "value": { "kind": "indicator", "id": "rsi7" }, "direction": "rising", "bars": 1 }
    ] },
    "short": { "kind": "group", "op": "and", "conditions": [
      { "kind": "compare", "left": { "kind": "price", "field": "close" }, "op": "gt", "right": { "kind": "indicator", "id": "vwap", "field": "upper_2" } },
      { "kind": "compare", "left": { "kind": "indicator", "id": "rsi7" }, "op": "gt", "right": { "kind": "const", "value": 75 } },
      { "kind": "slope", "value": { "kind": "indicator", "id": "rsi7" }, "direction": "falling", "bars": 1 }
    ] },
    "cooldown_bars": 3
  },
  "exit": { "time_exit_bars": 24 },
  "stop_loss": { "unit": "atr", "value": 1.5, "atr_indicator_id": "atr14" },
  "target":    { "unit": "indicator", "indicator_ref": { "kind": "indicator", "id": "vwap", "field": "value" } },
  "position_sizing": { "method": "risk_percent", "risk_percent": 0.5, "max_lots": 2 },
  "max_positions": 1, "max_trades_per_day": 4
}
```

### 10.3 Daily swing breakout on equities
```json
{
  "dsl_schema_version": "1.0",
  "name": "NIFTY50 20-day Breakout",
  "origin": "ai_research", "market": "NSE",
  "universe": { "kind": "watchlist", "watchlist_id": "wl_nifty50_liquid" },
  "timeframe": "1d",
  "session": { "product": "DELIVERY", "allowed_weekdays": [0,1,2,3,4] },
  "regime_filters": [ { "source": "daily_trend", "allowed": ["up"] } ],
  "indicators": {
    "hh20":   { "type": "SWING",      "params": { "left": 20, "right": 0 } },
    "ema50":  { "type": "EMA",        "params": { "period": 50 } },
    "volsma": { "type": "VOLUME_SMA", "params": { "period": 20 } },
    "atr14":  { "type": "ATR",        "params": { "period": 14 } },
    "trend":  { "type": "DAILY_TREND","params": { "fast": 20, "slow": 50 } }
  },
  "direction": "long_only",
  "entry": {
    "long": { "kind": "group", "op": "and", "conditions": [
      { "kind": "compare", "left": { "kind": "price", "field": "close" }, "op": "gt", "right": { "kind": "indicator", "id": "hh20", "field": "last_high", "offset": 1 } },
      { "kind": "compare", "left": { "kind": "price", "field": "close" }, "op": "gt", "right": { "kind": "indicator", "id": "ema50" } },
      { "kind": "compare", "left": { "kind": "price", "field": "volume" }, "op": "gt",
        "right": { "kind": "arith", "op": "*", "left": { "kind": "indicator", "id": "volsma" }, "right": { "kind": "const", "value": 1.5 } } }
    ] }
  },
  "exit": {
    "long": { "kind": "compare", "left": { "kind": "price", "field": "close" }, "op": "lt", "right": { "kind": "indicator", "id": "ema50" } },
    "time_exit_bars": 40
  },
  "stop_loss": { "unit": "atr", "value": 2.0, "atr_indicator_id": "atr14" },
  "target":    { "rr_multiple": 3.0, "unit": "atr", "value": 6.0, "atr_indicator_id": "atr14",
                 "partial": [ { "at": { "unit": "atr", "value": 3.0, "atr_indicator_id": "atr14" }, "close_pct": 50, "move_stop_to_breakeven": true } ] },
  "trailing": { "mode": "atr", "value": 2.5, "atr_indicator_id": "atr14", "activate_after": { "unit": "atr", "value": 3.0, "atr_indicator_id": "atr14" } },
  "position_sizing": { "method": "risk_percent", "risk_percent": 1.0, "max_capital_pct": 15 },
  "max_positions": 5, "max_trades_per_day": 2,
  "fill": { "entry_order_type": "LIMIT_AT_CLOSE", "limit_timeout_bars": 1 }
}
```

## 11. Execution semantics (what the engine guarantees)

- Rules are evaluated once per **closed** primary bar, after all context-timeframe bars
  that closed at or before that time are updated.
- Entry evaluation order: session window → regime filters → time filters → `max_positions`,
  `max_trades_per_day`, cooldown → entry condition → sizing → risk engine → order.
- Stops and targets are evaluated intra-bar by the simulator using bar high/low (or ticks
  when available) with the configured fill model; in live mode they are broker-side orders
  where supported, else engine-monitored on every tick.
- Partial targets and trailing stops are recomputed on each closed bar; trailing never loosens.
- Square-off at `session.square_off_at` is a MARKET order regardless of other rules.

## 12. Versioning and migration

- `dsl_schema_version` is `"1.1"` (`"1.0"` documents stay valid). Minor versions (`1.x`) add optional fields only; the
  engine accepts any `1.x` ≤ its own. A major bump (`2.0`) ships a migration function
  `migrate_1_to_2(doc)` in `packages/strategy/dsl/migrations.py`; migrated documents are
  stored as **new** strategy versions (status `draft`) linked by `parent_version_id`, never
  rewritten in place — approved versions are immutable (ADR-009).
- The indicator catalogue carries its own `indicator_lib_version` recorded on every
  backtest and activation so results remain reproducible if an indicator implementation
  changes.
- JSON Schema files are committed per version under `packages/strategy/dsl/schema/` and
  are part of the public API contract.
