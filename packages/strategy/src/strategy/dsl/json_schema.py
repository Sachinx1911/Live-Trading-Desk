"""JSON Schema export of the DSL (served at GET /strategies/dsl-schema; fed to the LLM)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from strategy.dsl.schema import DSL_SCHEMA_VERSION, StrategyDocument

SCHEMA_DIR = Path(__file__).parent / "schema"


def json_schema() -> dict[str, Any]:
    schema = StrategyDocument.model_json_schema()
    schema["title"] = f"StrategyDSL v{DSL_SCHEMA_VERSION}"
    return schema


def write_schema_file() -> Path:
    SCHEMA_DIR.mkdir(exist_ok=True)
    path = SCHEMA_DIR / f"v{DSL_SCHEMA_VERSION}.json"
    path.write_text(json.dumps(json_schema(), indent=2, sort_keys=True) + "\n")
    return path
