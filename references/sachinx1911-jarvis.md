# Sachinx1911/jarvis — the owner's general personal assistant

- Source: https://github.com/Sachinx1911/jarvis (studied commit `201f911`, 2026-10-17,
  "Phase 9 offline part complete; 1813 passed")
- **Owner's own repository** (public), built with Claude Code on the MacBook and the office
  laptop. Ideas and code may be reused (same owner); copying still goes through our review,
  tests and safety rules.
- Size: ~40,600 lines of Python (`jarvis/`), 106 test files (**1,813 tests passing**), Next.js
  dashboard, macOS wrapper (`mac/Jarvis`), `PLAN.md` (1,900 lines, v3.5), `PROGRESS.md`.

## What it is

A **general personal AI assistant that already exists and works**: it remembers what it is
taught, uses typed tools under risk tiers and approvals, runs an agent team for big jobs,
verifies its own work, speaks up on its own, and talks over CLI, Telegram, voice (English and
Marathi, local) and a web dashboard. Not trading-specific at all. Model: Claude through the
Claude Code CLI subscription (no API key), behind its own provider interface; local models
evaluated (Stage B) for later.

## What is built (per its PLAN §18 and PROGRESS)

| Phase | Built |
|---|---|
| 0 Setup | Config, Keychain secrets, SQLite, audit log, provider interface + fake provider, CLI chat |
| 1 Brain + memory | Own agent loop, SOUL.md character, profile interview, Marathi understanding, memory write/read, session search, privacy gate (P0–P3 tags) |
| 2 Tools + safety | Typed tools, **risk tiers T0–T4**, approvals, taint flag, **kill switch**, verifier, audit, connector registry, web search |
| 3 Tasks + team | Task queue with states, planner, receipts, project workspaces, **teach-by-demonstration → skills**, Researcher / Writer / Checker sub-loops, budgets |
| 4 Telegram + proactive | Owner-only bot, approve buttons, `/stop`, heartbeat, **morning brief**, reminders, schedules |
| 5 Connectors | EventKit, Google Calendar, Gmail (send after approval), Apple Notes, document library with citations |
| 6 Voice | Push-to-talk, Whisper + IndicConformer (Marathi STT), Marathi TTS, optional "hey jarvis" wake word, barge-in |
| 7 Dashboard | FastAPI + Next.js: Chat, Memory, Tasks & Approvals, Agents, Connectors, Schedules, Settings & Usage, India, Teach |
| 8 Extras | Coder / Operator agents, isolated Playwright browser, step recording |
| 9 X-ray (offline part) | Website teardown with a reverse-engineering kit; live part waits for the owner |
| 10 Agent HQ (proposed) | Teams, an "Office" page with team rooms; workspaces ("lokas") per company, requests between them |

Also: India daily-life module (mutual fund NAV, bills, UPI, wallet, alerts), memory conflict
detection, nightly review, files-as-truth with `jarvis verify` / `rebuild`, preflight checks.

## Design compared with Live-Trading-Desk's planned JARVIS

| Topic | Owner's jarvis | Our Mark 1 plan | Note |
|---|---|---|---|
| Model | Claude (Code CLI subscription), provider interface | OpenAI behind `LLMProvider` (ADR-009) | Both are swappable by design |
| Memory | Markdown files = truth (`facts/`, `preferences/`, `procedures/`, `constraints.md`, daily `episodes/`), SQLite FTS5 + vectors as index; private, never in the public repo | Postgres + pgvector, `jarvis_notes` with provenance (research note) | Same principles: owner-readable, provenance, rebuildable index |
| Risk levels | T0 read · T1 local write · T2 ask first · T3 external/irreversible, always ask · T4 prohibited | Green · Yellow (paper standing permission) · Red (money/safety, gateway only) | Map: Green = T0, Yellow = T1/T2, Red = T3, and live orders stay outside JARVIS entirely |
| Agents | One Jarvis + task-scoped sub-loops, teams in Phase 10 | One JARVIS + temporary helpers | Same idea |
| Proactive | Heartbeat, morning brief, reminders, triggers | EDITH alerts, evening brief, protocols | Same idea, different domain |
| Voice | Built, Marathi included, local | Mark 2 | Already solved there |
| Workspaces | "Lokas": one realm per company, own memory and budget, requests between them | `domain` field on tools, notes, protocols (research note §11) | Theirs is the more complete version of our "beyond trading" plan |

## What this means for us

This changes the question behind Mark 1 Stage 4: **the general JARVIS the owner wants
"for other work later" already exists.** Building a second JARVIS core inside
Live-Trading-Desk would duplicate memory, voice, Telegram, approvals and the agent loop.

**Owner decision, 2026-11-21: option A (connect).** Worked out in
`docs/mark-1-build-plan.md` Stage 4–5. The options as they were presented:

| Option | What it means |
|---|---|
| A. Connect | Live-Trading-Desk stays the trading engine and exposes its actions as a **tool server** (MCP or typed HTTP, Green/Yellow tools only, each with risk level). The existing jarvis gets a "trading" workspace/loka that calls those tools. Money and orders remain only in our execution gateway |
| B. Separate | Build the JARVIS of `docs/mark-1-build-plan.md` Stage 4–5 inside Live-Trading-Desk as planned, borrowing designs from this repo |
| C. Merge later | Build Stage 1–3 (no AI) now, decide A or B before Stage 4 |

Things to reuse either way: T0–T4 policy wording and the "T4 never, log the attempt" rule; the
verifier + task receipt (Success / Partial / Failed); kill switch and `/stop` from Telegram;
privacy gate before cloud calls; memory conflict detection; teach-by-demonstration → skill;
Marathi voice stack; files-as-truth with a rebuildable index; preflight command.

Safety constraints that hold under any option: no LLM places, modifies or cancels an order
(CLAUDE.md rule 1); broker secrets never leave Live-Trading-Desk (rule 8); the tool server
never exposes Red actions as callable tools; owner rules cannot be bypassed (rule 9).

## Verdict

The most important reference so far: not an idea source but an **existing, tested assistant
owned by the same person**, with most of what Mark 1 Stage 4 and Mark 2 voice plan to build.
The Stage 4 design of Live-Trading-Desk should be decided with this repo in view.
