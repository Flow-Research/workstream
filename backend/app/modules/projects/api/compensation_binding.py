"""Public PROJECTS capability for compensation-binding eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class ProjectCompensationBindingUnavailable(RuntimeError):
    """Conceal missing or ineligible compensation-binding projects."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectCompensationBindingEligibilityFacts:
    """Exact eligible project retained under a PROJECTS-owned fence."""

    project_id: UUID


class ProjectCompensationBindingEligibilityPort(Protocol):
    """Lock and validate one exact project for compensation binding."""

    async def lock_compensation_binding_project(
        self, project_id: UUID
    ) -> ProjectCompensationBindingEligibilityFacts:
        """Retain the PROJECTS eligibility fence through the caller transaction."""
