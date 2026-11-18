"""Versioned prompt files. Each `<name>.md` starts with a front-matter block:

    ---
    version: 1
    ---
    <system prompt text>

`prompt_version` in `ai_calls` is `<name>@<version>`, so changing a prompt means bumping
its version and the evaluation set must be re-run for that version (roadmap Phase 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent


class PromptError(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str


def prompt_names() -> list[str]:
    return sorted(p.stem for p in PROMPT_DIR.glob("*.md") if not p.stem.startswith("_"))


def parse_prompt(name: str, text: str) -> Prompt:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise PromptError(f"prompt {name!r}: missing front matter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise PromptError(f"prompt {name!r}: unterminated front matter") from exc
    meta: dict[str, str] = {}
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            raise PromptError(f"prompt {name!r}: bad front matter line {raw!r}")
        meta[key.strip()] = value.strip()
    version = meta.get("version")
    if not version:
        raise PromptError(f"prompt {name!r}: front matter needs `version`")
    system = "\n".join(lines[end + 1 :]).strip()
    if not system:
        raise PromptError(f"prompt {name!r}: empty system prompt")
    return Prompt(name=name, version=version, system=system)


def load_prompt(name: str) -> Prompt:
    path = PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptError(f"unknown prompt {name!r}; available: {prompt_names()}")
    return parse_prompt(name, path.read_text(encoding="utf-8"))
