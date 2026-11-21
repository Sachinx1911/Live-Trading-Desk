# Owner trading rules

Hard rules given by the product owner. Each one is a named, deterministic check in
`packages/risk/src/risk/owner_rules.py`, run by the risk engine on **every entry signal in
every mode** (paper, live, replay, backtest). A rule can only block an order; it never
creates or resizes one, and it never blocks an exit. No strategy, AI draft or manual path
can switch a rule off, because all orders pass through the risk engine.

Adding a rule: write the function with `@owner_rule(code, description)`, add tests in
`packages/risk/tests/test_owner_rules.py`, add a row here. If the rule needs new market
data, add the field to `MarketContext` and fill it where the trader builds the context.

| # | Code | Rule | Since |
|---|------|------|-------|
| 1 | `pcr_guard` | **PCR ≥ 2.0 → never buy a PUT. PCR ≤ 0.5 → never buy a CALL.** | 2026-11-21 |

## 1 · `pcr_guard`

- **PCR** = total put open interest ÷ total call open interest, over every strike of the
  underlying's nearest unexpired expiry, from the newest stored option-chain snapshot
  (the collector stores one every 5 minutes).
- **PCR ≥ 2.0**: put writers are at least double the call writers. Writers are defending
  the downside, so buying a put is forbidden.
- **PCR ≤ 0.5**: call writers are at least double the put writers. Writers are defending
  the upside, so buying a call is forbidden.
- Applies to **buy entries of options** only. Futures, equity, option selling and all exits
  are untouched.
- **No data means no trade** (paper and live): if there is no chain snapshot for the
  underlying, or the newest one is older than 15 minutes, option buys are blocked with the
  reason in the journal.
- **Backtest and replay**: option-chain history is not available to those engines yet, so
  the check is recorded as `pcr_guard:skipped`. When chain history is wired in, the same
  function applies unchanged.
- Thresholds live in the risk limits (`pcr_no_put_buy_at` = 2.0, `pcr_no_call_buy_at` =
  0.5, `pcr_max_age_minutes` = 15).
- A rejected signal shows up like any other risk rejection, e.g.
  `PCR 2.31 >= 2.0: put writers dominate, no PUT buy`.
