# open-jarvis/OpenJarvis — local-first personal AI framework

- Source: https://github.com/open-jarvis/OpenJarvis (studied commit `5a9b526`, 2026-11-21)
- Docs https://open-jarvis.github.io/OpenJarvis/ · paper https://arxiv.org/abs/2605.17172 · project site at stanford.edu
- Size: ~1,450 Python files, a Rust workspace (`rust/crates`), Tauri desktop app, React/TS
  frontend, MkDocs documentation, examples, tests.
- **Licence: Apache-2.0.** Code may be reused with attribution and the licence notice; check
  each dependency it pulls in before copying anything.

## What it is

A research-plus-production **framework for personal AI agents that run locally by default**
(Ollama, vLLM, llama.cpp…) and call cloud models only when needed. Positioned "in the spirit of
PyTorch": shared primitives, energy/latency/cost treated as first-class metrics, and a learning
loop that improves routing and skills from the user's own traces. Ships a CLI (`jarvis`), a
browser GUI, desktop installers and presets (morning digest, deep research, code assistant,
scheduled monitor, simple chat).

## Architecture (five primitives, registry pattern)

| Primitive | What it does |
|---|---|
| **Intelligence** | Model catalogue (size, context, VRAM, engines) and generation defaults |
| **Engine** | Uniform inference interface (`generate`, `stream`, `list_models`, `health`) over local and cloud backends, with health-based fallback |
| **Agentic logic** | Pluggable agents: simple, orchestrator (multi-turn tool loop), ReAct, CodeAct, scheduled "operative" with state, long-horizon **monitor operative**, proactive agent; optional Docker/Podman sandbox |
| **Memory** | Pluggable retrieval backends: SQLite FTS5/BM25 (default), FAISS, ColBERTv2, BM25, **hybrid via reciprocal rank fusion**; ingestion, chunking, context injection with source attribution |
| **Learning & traces** | Every interaction becomes a `Trace` (routing, retrieval, inference, tool calls, answer); analysers learn which model/agent/tool works best per query type; skills optimised from traces |

Everything is registered by decorator (`@AgentRegistry.register(...)`), configured in one
`config.toml`, and connected by an **EventBus**. Other modules: connectors (Gmail, Calendar,
Drive…), channels (messaging), scheduler + daemon, speech, MCP, A2A, security guardrails,
telemetry, evals/bench.

## Pieces that matter to us

| Their design | Our use |
|---|---|
| `ToolSpec` with `requires_confirmation`, `cost_estimate`, `latency_estimate`, `timeout_seconds`, `required_capabilities`, `category`; the executor **refuses** a confirm-required tool when no confirmation callback exists | Same shape as our tool manifest; we replace the boolean with our Green/Yellow/Red level and keep "no confirmer → refuse" as the server-side rule (research note §8) |
| **Proactive agent**: on a schedule, LLM proposes actions each with a tier and permission key; trivial or always-approve → run; always-deny → skip; rest → pending queue, user approves by replying `<id> yes` | Very close to our EDITH + standing permission. For us the *proposal* may be AI but the tiers and permission lists are fixed config, and anything trading-Red never enters the auto-approve path |
| Memory backends behind one ABC; hybrid BM25 + vector with RRF | `jarvis_notes` search: Postgres full-text + pgvector fused the same way, still one database |
| Traces of every step | Our `jarvis_tool_runs` + `ai_calls`; their trace format is a good checklist of fields |
| Engine health + automatic fallback | `LLMProvider` registry could gain a fallback chain (cloud → second provider) |
| Security scanners (secrets, PII) wrapping the engine with WARN / REDACT / BLOCK, events to an append-only audit table | Wrap our `LLMProvider` with a secret scanner so broker tokens can never leave in a prompt (CLAUDE.md rule 8) |
| Skills = tools discovered from a catalogue (agentskills.io standard) | Our protocols and tool catalogue; a standard format would help the "beyond trading" domains |
| Tauri desktop app with an overlay window | Confirms Tauri as the shell choice for plan §4 |
| Presets (`morning-digest`, `scheduled-monitor`) | Our protocols; their morning digest ≈ our Market Open report |

## What to avoid

- **Local-first is not our goal.** Running models locally is their core; for us the OpenAI path
  is decided and local models are optional later. Do not adopt their engine layer wholesale.
- **Self-improving routing / skill optimisation from traces** must not touch anything that
  decides trades (ADR-009, "no uncontrolled self-modification"). Only usable for chat routing.
- Code-executing agents (CodeAct, REPL, shell tools) contradict CLAUDE.md rule 4.
- Security scanning is *opt-in* there; for us guardrails around money are mandatory.
- Size and scope: a general framework with many optional parts; taking it as a dependency would
  pull far more than we need. Borrow patterns, not the framework.

## Verdict

The most relevant reference so far for **JARVIS core**: tool spec with confirmation, proactive
agent with approval queue, pluggable memory with hybrid retrieval, traces, guardrails, Tauri
shell. Use as a design checklist for Mark 1 Stage 4–5; reuse small pieces only after a licence
check. Nothing for the trading engine itself.
