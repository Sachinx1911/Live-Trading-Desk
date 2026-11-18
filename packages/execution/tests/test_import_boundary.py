"""The Upstox order client must be unreachable from anywhere but the live gateway path."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ALLOWED = {
    "packages/execution/src/execution/live/upstox_orders.py",
}


def test_upstox_orders_imported_only_by_gateway_path() -> None:
    offenders = []
    for base in ("packages", "apps"):
        for py in (ROOT / base).rglob("*.py"):
            rel = py.relative_to(ROOT).as_posix()
            if "/tests/" in rel or "/node_modules/" in rel or "/.venv/" in rel:
                continue
            if "upstox_orders" in py.read_text(encoding="utf-8") and rel not in ALLOWED:
                # the package __init__ may mention it in a docstring only, never import it
                text = py.read_text(encoding="utf-8")
                if (
                    "import" in text
                    and "upstox_orders"
                    in [
                        line
                        for line in text.splitlines()
                        if line.strip().startswith(("from", "import"))
                    ].__str__()
                ):
                    offenders.append(rel)
    assert offenders == [], f"upstox_orders imported outside the gateway path: {offenders}"
