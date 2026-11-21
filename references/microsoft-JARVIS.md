# microsoft/JARVIS — HuggingGPT, TaskBench, EasyTool (research)

- Source: https://github.com/microsoft/JARVIS (studied commit `7624cf3`, 2025-07-29; last
  functional updates 2023–2024, effectively archived research code)
- Three independent research projects in one repo; Python, notebooks-style server code.
- **Licence: MIT** (root). `taskbench/` declares Apache-2.0 in its README. Datasets come from
  third parties (ToolBench, RestBench, HuggingFace) with their own terms.

## What it is

Not a product. Microsoft Research's code and datasets for three papers about **LLMs that plan
and call tools**:

| Part | Paper | Idea |
|---|---|---|
| `hugginggpt/` | HuggingGPT (2023) | An LLM as **controller** over many expert models. Four stages: task planning → model selection → task execution → response generation |
| `taskbench/` | TaskBench (2023) | Benchmark for task automation in three steps: **task decomposition, tool selection, parameter prediction**, built on a *tool graph* |
| `easytool/` | EasyTool (2024) | Turn long, inconsistent tool docs into **short, uniform tool instructions** with examples; agents pick and use tools better |

## How HuggingGPT plans

The controller returns a JSON task list: `{"task", "id", "dep": [ids], "args"}`, where an argument
can be `<GENERATED>-<id>`, meaning "the output of task id". Tasks with no unmet dependencies run
in parallel; results are fed back for one final answer. Task types are a fixed list; anything
outside it must be refused ("reply empty JSON []").

## What we can take

| Idea | Our use |
|---|---|
| **Plan as a dependency graph** with "output of step N" references | JARVIS multi-step commands ("scan for breakouts, backtest the top 3, show results on screen 2"): the model returns a plan of catalogue tool calls with `dep` links; our runner executes it, checks every step's risk level *before* starting, and stops at the first Red |
| Plan first, show it, then execute | For Yellow/Red plans the owner sees the whole plan once and confirms once, instead of a prompt per step |
| Fixed task vocabulary, refuse otherwise | Tool catalogue is closed; an unknown tool name is a refusal, never improvisation |
| **TaskBench's three metrics**: decomposition, tool choice, parameters | Exactly how to score our future JARVIS command eval set (mark-1-plan §2.5 step 3): for each Marathi/Hindi/English command compare planned steps, chosen tools (graph match) and arguments separately, like `nl_eval` does per DSL field |
| **Tool graph + back-instruct** data generation: sample a chain of tools, have a model write the instruction, then human-check | Bootstrapping that eval set: generate candidate commands from real tool chains, owner corrects them |
| **EasyTool**: concise, uniform tool descriptions with one usage example | Our tool manifest text: short purpose line, typed args, one example per tool. Fewer tokens per turn and better tool choice |

## What to avoid

- Running dozens of local expert models (24 GB VRAM, 284 GB disk); irrelevant to us.
- The controller decides *which model executes*; for us the executor is always our own
  deterministic code, and anything touching money stays outside model choice (ADR-009).
- Research-grade code (Python 3.8, hard-coded configs, keys in YAML); patterns only.

## Verdict

Old (2023) but the **foundational ideas** for JARVIS planning are here: plan-as-graph with step
outputs, closed tool vocabulary, and a proper way to **evaluate** an assistant's planning. Most
useful for Mark 1 Stage 4–5 and for building the command eval set; EasyTool for writing the
tool catalogue.
