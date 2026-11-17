"""Portable current schema shared as public contract data."""

import json
from pathlib import Path


def obligation_schema() -> dict:
    """Return a fresh portable schema; callers cannot mutate another validation."""
    path = Path(__file__).resolve().parents[1] / "contracts/obligation.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fulfillment_report_schema() -> dict:
    """Return the closed report schema shared by the two public owner paths."""
    path = Path(__file__).resolve().parents[1] / "contracts/fulfillment-report.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fulfillment_exception_schema() -> dict:
    """Return the closed post-success exception wire schema."""
    path = Path(__file__).resolve().parents[1] / "contracts/fulfillment-exception.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))
