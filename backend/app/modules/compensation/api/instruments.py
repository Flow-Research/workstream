"""Canonical public compensation instrument identities."""

from enum import StrEnum


class CompensationInstrumentType(StrEnum):
    """Closed compensation instrument families."""

    MONEY = "money"
    PROJECT_POINTS = "project_points"
