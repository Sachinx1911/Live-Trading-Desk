# Reference repositories

Other projects the owner picked as references for ideas (trading platform and JARVIS). This
folder is separate from the product: nothing here is product code or a decision. A decision
only exists once it is written into `docs/mark-1-plan.md` or an ADR.

- One summary per repository: `references/<repo-name>.md` (our own words, committed).
- Shallow clones used for reading live in `references/_repos/` and are **git-ignored**; they
  are read only, never run, and never copied into the product without checking the licence.

Each summary covers: what it is, stack, architecture, features, what we can take (mapped to
Mark 1 stages), what to avoid, and the licence.

| Repository | What it is | Useful for | Licence | Studied |
|---|---|---|---|---|
| [hectorg2211/jarvis](hectorg2211-jarvis.md) | Windows double-clap → open apps on chosen monitors + cached ElevenLabs welcome | Protocol with screen layout, window placement, cached voice phrases (Mark 2) | None (all rights reserved) | 2026-11-21 |
| [open-jarvis/OpenJarvis](open-jarvis-OpenJarvis.md) | Stanford's local-first personal-agent framework: 5 primitives, registries, memory backends, traces, proactive agent, Tauri app | JARVIS core design checklist: tool spec + confirmation, approval queue, hybrid memory, guardrails, traces | Apache-2.0 | 2026-11-21 |
| [microsoft/JARVIS](microsoft-JARVIS.md) | Microsoft Research: HuggingGPT (LLM plans tool graph), TaskBench (planning benchmark), EasyTool (concise tool docs) | Multi-step plans with step dependencies, scoring the JARVIS command eval set, writing tool descriptions | MIT (TaskBench Apache-2.0) | 2026-11-21 |
