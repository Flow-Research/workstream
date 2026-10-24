"""Ports for trusted, non-monetary checker trial authority."""

from __future__ import annotations

from typing import Protocol

from app.modules.checkers.api.trial_profiles import (
    TrialAuthorityContext,
    TrialExecutionProjection,
    TrialExecutionProfile,
    TrialExecutionSelector,
)


class TrialProfileReaderPort(Protocol):
    """Resolve only locally provisioned immutable execution profiles."""

    def read(
        self,
        context: TrialAuthorityContext,
        selector: TrialExecutionSelector,
    ) -> tuple[TrialExecutionProfile, TrialExecutionProjection] | None:
        """Return an exact profile/projection bundle, or no authority."""


__all__ = ("TrialProfileReaderPort",)
