# JARVIS memory and data store — research note

Status: **research only** (2026-11-21). Nothing here is built; per `docs/mark-1-plan.md` §9 building
starts on the owner's go-ahead. This note exists so that Stage 4/5 of Mark 1 can start from a
decided storage design instead of inventing one under time pressure. It extends ADR-009 (what an
LLM may do) and the database design (`03-database-design.md`); it does not change them.

## 1. What exists today

| Store | Holds | Notes |
|---|---|---|
| PostgreSQL 16 + TimescaleDB | 62 tables; hypertables `historical_candles`, `market_quotes`, `option_chain_snapshots`, `api_logs` | System of record. Append-only raw data, derived tables rebuildable, UTC everywhere |
| Redis | `collector:health`, `kill:{scope}`, `ai:tokens:<day>`, quote cache, pub/sub `market.tick` / `market.candle`, arq job queue | Volatile state and coordination between API, worker, collector, trader |
| Parquet on disk (`DATA_DIR`) | Raw ticks when `COLLECT_RAW_TICKS=true` | Off by default (ADR-010) |
| MinIO / S3 | Planned: `ai_calls.payload_uri` (prompt + raw response), Parquet archive, backups | Not yet in use; compose profile `storage` |
| DuckDB | Planned Phase 8 read-only research layer over Parquet | Not yet |

AI-related records already designed (`03-database-design.md` §2i): `ai_calls` (built, append-only),
`ai_research_jobs`, `ai_recommendations`, `trade_reviews`, `morning_briefs`, `audit_findings`.
Conversation state exists only for the NL builder (`strategy_nl_drafts.thread`).

## 2. What "memory" has to mean for JARVIS

The agent-memory literature (CoALA and the 2026 surveys, see sources) uses one taxonomy that
maps cleanly onto this product. The table also says where each kind must live.

| Kind | In JARVIS | Lives in | Who may write |
|---|---|---|---|
| **Working** | The current conversation, the task in flight, which panels are open on which screen, mode (JARVIS/FRIDAY/EDITH/KAREN) | Redis with TTL + the open conversation row | JARVIS |
| **Episodic** | What happened: messages, tool calls and their results, alerts raised, trades, approvals | Postgres, append-only (`jarvis_messages`, `jarvis_tool_runs`, existing `audit_logs`, `journal_entries`, `ai_calls`) | System; never edited |
| **Semantic** | Durable facts and preferences: "owner trades NIFTY weeklies", "rule 1 blocked 14 trades in Nov", "avoid the first 15 minutes" | Postgres `jarvis_notes` (+ pgvector) and `owner_preferences` | Owner directly; JARVIS only as *draft* notes with provenance |
| **Procedural** | How to do things: protocols, prompts, the tool catalogue, owner trading rules | **Code and versioned config in git**, plus a `protocols` table for owner-defined bundles | Developers; owner for protocols. **Never the model** |

The last row is the important one. CoALA already warns that letting an agent write its own
procedures is the riskiest kind of memory; for this product it is also forbidden by ADR-009 and
CLAUDE.md rule 9: owner trading rules are code, run by the risk engine, and no memory can
weaken them.

## 3. Principles

1. **Numbers come from tools, never from memory.** Memory stores references (trade ids, backtest
   job ids, dates) and conclusions; when JARVIS quotes a figure it calls the tool again. This is the
   only way "never display fabricated data" survives a memory layer.
2. **Episodic memory is append-only** and shares one timeline with `audit_logs` and `ai_calls`,
   so any JARVIS action can be replayed: message → tool run → audit row → ai_call.
3. **Semantic memory is the owner's.** Every note is visible, editable and deletable in the UI.
   JARVIS proposes; the owner (or an explicit auto-accept rule for low-risk "lesson" notes) accepts.
4. **Provenance on every item**: `source_refs` (which trades / reviews / messages it came from) and
   `ai_call_id` when a model wrote it. A note without provenance is not stored.
5. **Memory never reaches execution.** The trader, risk engine, simulator and gateway do not read
   JARVIS memory. Memory is read by the conversation layer only (import-linter contract later).
6. **Retention is a policy, not an accident**: every store has a declared lifetime (section 7).
7. **One database.** No second datastore for vectors or conversations while the volumes stay
   where a single owner puts them (sources agree pgvector is the default below a few million
   vectors). Redis stays volatile. Object storage is for blobs only.

## 4. Proposed stores (for Stage 4, to be confirmed on go-ahead)

### 4.1 Postgres tables (new)

```
jarvis_conversations   id, user_id, mode, started_at, ended_at, title, summary (text, rolling),
                       pinned bool, screen_layout_id nullable
jarvis_messages        id, conversation_id, seq, role (owner|jarvis|helper|system|tool),
                       content text, content_refs jsonb (ids the text relies on),
                       tool_calls jsonb, ai_call_id fk, ts            -- append-only
jarvis_tool_runs       id, message_id fk, tool_name, risk_level (green|yellow|red),
                       input jsonb, output_ref jsonb (ids / payload_uri, not copies of data),
                       status (proposed|confirmed|running|done|failed|denied),
                       confirmed_by fk users nullable, confirmed_at, audit_log_id fk,
                       started_at, finished_at, error                  -- append-only
jarvis_notes           id, kind (fact|preference|lesson|watch), text, embedding vector(d),
                       source_refs jsonb, ai_call_id nullable, created_by (owner|jarvis),
                       status (draft|accepted|rejected|superseded), superseded_by nullable,
                       valid_from, valid_until nullable, created_at, updated_at
owner_preferences      key, value jsonb, updated_at                    -- language, default
                                                                        -- instrument, quiet hours,
                                                                        -- saved layouts
protocols              id, name, description, steps jsonb (ordered tool calls with fixed
                       inputs), layout jsonb nullable, created_by, created_at, version
```

Why not store conversation history the way agent SDKs do (a single opaque session blob)? Because
`jarvis_tool_runs` *is* the authority log the plan asks for: every Yellow/Red action has a row
with who confirmed it, and the row links to `audit_logs`. An opaque session cannot be queried
for "what did JARVIS change this week".

### 4.2 Redis (working memory, all keys with TTL)

- `jarvis:conv:<id>:context` — the assembled context of the open conversation (cache; source of
  truth is Postgres).
- `jarvis:task:<id>` — in-flight task state and progress for panels.
- `jarvis:layout:<screen>` — which panels are open where (desktop shell reads it).
- `edith:seen:<rule>:<key>` — alert de-duplication windows.
- `ai:tokens:<day>` — already exists (daily cap).

### 4.3 pgvector (semantic recall, same database)

Extension `vector`; one embedding column on `jarvis_notes`, and later optional embeddings on
`journal_entries.entry_reason` and `trade_reviews.findings` for "have I seen this before".
Embeddings go through `LLMProvider` (add `embed()`), logged in `ai_calls` like any call. Volume
estimate: thousands of notes and tens of thousands of journal rows for one owner, far below the
point where the sources say a dedicated vector database pays off. HNSW index; recall measured
on our own data before trusting it.

### 4.4 Object storage (MinIO, blobs only)

`ai-calls/<id>/` prompt and raw response (already designed as `payload_uri`), end-of-day reports,
chart images for KAREN reviews, Parquet cold data (Phase 8). Nothing the UI needs at interactive
speed lives here.

### 4.5 TimescaleDB lifecycle (independent of JARVIS, worth doing anyway)

Compression after 7 days and retention policies on `market_quotes` and `api_logs`; compression
on `option_chain_snapshots` (OI history in Stage 1 will grow fastest). Continuous aggregates are
*not* used for candles: the candle builder and resampler are the one source of derived bars
(ADR-002) and a second path would drift. Tiered storage to Parquet is the Phase 8 route; the
Timescale docs note tiering needs time-only partitioning, which our hypertables have.

## 5. How a JARVIS turn assembles its context

Borrowed from Letta's blocks and Anthropic's memory/context-editing results, but with our rules:

1. **Core blocks (always in context, small):** persona for the current mode; owner preferences;
   a one-paragraph summary of the hard rules; *today's state fetched by tools* (broker session,
   feed, open positions, kill switch) — fetched, not remembered.
2. **Relevant notes:** top-k `jarvis_notes` by embedding similarity and recency, accepted status
   only, each with its provenance line.
3. **Recent episodes:** the last N messages of this conversation; older turns are replaced by the
   stored `summary` (context editing), never silently dropped.
4. **Tool catalogue subset:** only the tools the mode allows (FRIDAY gets the short read-only
   set; KAREN gets reviews and reports), because every tool definition costs tokens each turn.

## 6. Consolidation ("sleep-time" work, Stage 5)

A nightly worker job (same place as the planned Auditor) reads the day's episodes — trades,
alerts, reviews, conversations — and writes **draft** `jarvis_notes` with `source_refs`. The
owner sees them in `/ai-hub` and accepts or rejects; an explicit allow-list may auto-accept
`lesson` notes under a confidence threshold. The job never writes preferences, protocols or
rules. This is the same shape as `ai_recommendations` (proposal → owner decision) and reuses
its budget and logging.

## 7. Retention (proposal)

| Data | Keep | Then |
|---|---|---|
| `jarvis_messages`, `jarvis_tool_runs`, `audit_logs`, `ai_calls` | Forever (append-only; small) | Compress in Timescale if they grow |
| `jarvis_conversations.summary` | Forever | — |
| `jarvis_notes` | Until superseded or owner deletes | Superseded rows kept for history |
| Redis working memory | Hours (TTL) | Gone |
| `market_quotes` | 30 days raw | Compressed, then dropped (candles keep the history) |
| `api_logs` | 90 days | Dropped |
| `option_chain_snapshots` | 1 year hot | Compressed; Parquet archive in Phase 8 |
| MinIO payloads | 1 year | Lifecycle rule |

## 8. Tool catalogue storage (ties memory to authority)

Tools are declared in code (decorator registry, like `owner_rules`) and exported as a JSON
manifest for the model. Each entry carries `risk_level`, `mode_allowed`, `idempotent`, and the
MCP annotation hints (`readOnlyHint`, `destructiveHint`) for interoperability — but, as the MCP
blog itself says, hints are untrusted; **enforcement is server-side** in the tool runner, which
writes `jarvis_tool_runs` and refuses Red actions without a confirmed row. Standing permission
for paper trading (plan §2.3) is a server-side rule in the runner, not a prompt instruction.

## 9. Deliberately not doing

- A separate vector database, a memory SaaS (Mem0 / Letta Cloud) or a graph store: more moving
  parts than one owner's data justifies, and the model must not depend on a service we do not
  control for facts about money.
- Letting the model edit its own instructions or protocols ("procedural memory" writes).
- Storing market numbers inside notes.
- Opaque session blobs from an agent SDK as the only record of what JARVIS did.

## 10. Open questions for the owner

1. Auto-accept rule for `lesson` notes: allowed at all, or every note needs a click?
2. Memory shared between the office PC and the MacBook: it is in Postgres, so it follows the
   database; which database is the one JARVIS talks to day to day (VPS, or the Mac)?
3. Retention numbers in section 7.
4. Whether KAREN's trade reviews may store chart images (MinIO) or only text and ids.

## 11. Beyond trading (owner, 2026-11-21)

The owner intends the same assistant to serve other kinds of work later; trading is the first
domain, not the only one. In the films JARVIS ran engineering, the workshop and house, suit
operations, research, business and health with one personality and changing tools; that is the
shape to keep. Decisions that follow for everything in this note:

- **The core is domain-agnostic.** Tool catalogue, risk levels, confirmation flow, memory tables,
  protocols, modes and the screen manager contain no trading concepts. Trading is one *tool
  domain*: its tools, its Red-level rules (`packages/risk`), its data.
- **`domain` on every memory and procedure row**: `jarvis_notes`, `protocols`, tool manifest
  entries and `jarvis_conversations` carry `domain` (first value `trading`). Context assembly
  (section 5) filters notes and tools by the active domain plus `domain = 'core'`.
- **Persona is layered**: a core persona block (voice, initiative, honesty rules) plus a block
  per domain. "Trading assistant" wording lives only in the trading block.
- **Risk levels are generic; what is Red is per domain.** The runner enforces a domain's Red list
  the same way for all domains; the trading list is the one in `docs/mark-1-plan.md` §2.3.
- **Packaging (decide at Stage 4):** JARVIS core as its own package (`packages/jarvis`) with
  trading tools as its first plugin, so a second domain is a second plugin, not a fork.
- **Not now.** Nothing above is built before trading works end to end; it only forbids baking
  trading into the core while Mark 1 is built.

## Sources

- CoALA, "Cognitive Architectures for Language Agents": working / episodic / semantic /
  procedural memory, and the warning about procedural writes — https://arxiv.org/pdf/2309.02427
- "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers" (2026
  survey) — https://arxiv.org/pdf/2603.07670
- Letta: memory blocks, recall vs archival, sleep-time compute —
  https://docs.letta.com/guides/agents/architectures/memgpt , https://letta.com/blog/memory-blocks ,
  https://letta.com/blog/sleep-time-compute
- Anthropic: context management and the memory tool (file-based, client-side, just-in-time
  retrieval) — https://www.anthropic.com/news/context-management ,
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- OpenAI Agents SDK sessions (SQLite / SQLAlchemy session storage) —
  https://openai.github.io/openai-agents-python/sessions/
- pgvector vs dedicated vector databases (small team, Postgres already present) —
  https://qdrant.tech/blog/pgvector-tradeoffs/ , https://bigdataboutique.com/blog/pgvector-in-production ,
  https://aiven.io/blog/pgvector-isnt-your-vector-databasing-cure-all
- MCP tool annotations are hints, not enforcement —
  https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/
- MCP resources vs tools — https://www.fast.io/resources/mcp-resources-vs-tools/
- OpenTelemetry GenAI agent span conventions (observability, not an audit log) —
  https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
- TimescaleDB data lifecycle: compression, retention, tiering to Parquet —
  https://www.tigerdata.com/docs/learn/data-lifecycle ,
  https://docs.timescale.com/use-timescale/latest/data-tiering/about-data-tiering
