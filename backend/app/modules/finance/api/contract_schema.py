"""Portable versioned schema shared as public contract data."""

from importlib.resources import files
import json


def obligation_schema() -> dict:
    """Return a fresh portable schema; callers cannot mutate another validation."""
    return json.loads(
        files("app.modules.finance").joinpath("contracts/obligation-v1.schema.json").read_text()
    )
