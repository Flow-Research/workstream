"""Portable versioned schema shared as public contract data."""

import json
from pathlib import Path


def obligation_schema() -> dict:
    """Return a fresh portable schema; callers cannot mutate another validation."""
    path = Path(__file__).resolve().parents[1] / "contracts/obligation-v1.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))
