"""Dependency-safe public APIs for the ACTORS business module."""

from app.modules.actors.api.compensation_adapter import (
    CompensationAdapterActorEligibilityFacts,
    CompensationAdapterActorEligibilityPort,
    CompensationAdapterActorUnavailable,
)

__all__ = (
    "CompensationAdapterActorEligibilityFacts",
    "CompensationAdapterActorEligibilityPort",
    "CompensationAdapterActorUnavailable",
)
