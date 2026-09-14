"""Internal exact-version validation facts, never guide or action authority."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ContributionPolicyValidationPurpose(StrEnum):
    """Separate new binding eligibility from caller-owned revision adoption."""

    GUIDE_ACTIVATION = "guide_activation"
    REVISION_ADOPTION = "revision_adoption"


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyValidationRequest:
    """Explicit selection; revision IDs must come from locked guide custody."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    purpose: ContributionPolicyValidationPurpose


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyValidationFacts:
    """Version/resource validity retained only within the caller transaction."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    purpose: ContributionPolicyValidationPurpose
    version_number: int
    rules_and_definitions_digest: str
    adapter_binding_ids: tuple[UUID, ...]


class ContributionPolicyValidationPort(Protocol):
    """Validate exact policy resources without authorizing or binding a guide."""

    async def validate_contribution_policy(
        self, request: ContributionPolicyValidationRequest
    ) -> ContributionPolicyValidationFacts:
        """Retain eligibility fences until the caller commits or rolls back."""
