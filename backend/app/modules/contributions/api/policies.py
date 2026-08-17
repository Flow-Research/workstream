"""Dependency-safe public contracts for hidden ContributionPolicy behavior."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, TypeAlias
from uuid import UUID

from app.modules.compensation.api import CompensationInstrumentType
from app.modules.projects.api import ProjectContributionPolicyEligibilityPort

PolicyAction = Literal[
    "contribution.policy.create_draft",
    "contribution.policy.update_draft",
]
PolicyEventType = Literal["draft_created", "draft_updated"]
ContributionType = Literal["accepted_submission", "completed_review"]
CompensationMode = Literal["unpaid", "compensated"]


class ContributionPolicyUnavailable(RuntimeError):
    """Fail closed or conceal inaccessible policy state."""


class ContributionPolicyConflict(RuntimeError):
    """Conceal stale, duplicate, foreign, or invalid mutations."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyDefinitionInput:
    """One requested immutable compensation definition."""

    instrument_type: CompensationInstrumentType
    unit_code: str
    quantity: str
    adapter_binding_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyRuleInput:
    """One complete contribution rule replacement."""

    contribution_type: ContributionType
    compensation_mode: CompensationMode
    definitions: tuple[PolicyDefinitionInput, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyReadRequest:
    """Select one exact policy and optional immutable version."""

    actor_profile_id: UUID
    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyCreateDraftRequest:
    """Create the next draft for one project policy aggregate."""

    operation_id: UUID
    actor_profile_id: UUID
    project_id: UUID
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyUpdateDraftRequest:
    """Replace one exact draft version's complete rule graph."""

    operation_id: UUID
    actor_profile_id: UUID
    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    rules: tuple[PolicyRuleInput, ...]


PolicyMutationRequest: TypeAlias = (
    ContributionPolicyCreateDraftRequest | ContributionPolicyUpdateDraftRequest
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyDefinitionView:
    """Server-owned immutable compensation definition facts."""

    definition_id: UUID
    instrument_type: CompensationInstrumentType
    unit_code: str
    quantity: str
    adapter_binding_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyRuleView:
    """Server-owned immutable contribution rule facts."""

    rule_id: UUID
    contribution_type: ContributionType
    compensation_mode: CompensationMode
    definitions: tuple[PolicyDefinitionView, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyView:
    """Authorized immutable view of one exact policy version graph."""

    project_id: UUID
    contribution_policy_id: UUID
    name: str
    policy_status: str
    contribution_policy_version_id: UUID
    version_number: int
    version_status: str
    rules: tuple[PolicyRuleView, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyMutationResult:
    """Immutable result reconstructed only from lifecycle-event truth."""

    event_id: UUID
    operation_id: UUID
    request_digest: str
    event_type: PolicyEventType
    actor_profile_id: UUID
    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    version_number: int
    prior_current_version_id: UUID | None
    prior_current_version_number: int | None
    from_policy_status: str | None
    to_policy_status: str
    from_version_status: str | None
    to_version_status: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyMutationAuthorizationFacts:
    """Exact immutable facts bound to opaque mutation authority."""

    action: PolicyAction
    actor_profile_id: UUID
    operation_id: UUID
    request_digest: str
    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    expected_policy_status: str | None
    expected_version_status: str | None


class ContributionPolicyReadAuthorizationPort(Protocol):
    """Authorize one exact policy/version disclosure."""

    async def authorize_contribution_policy_read(
        self, request: ContributionPolicyReadRequest
    ) -> None:
        """Authorize disclosure without returning product rows."""


class ContributionPolicyMutationAuthorizationPort(Protocol):
    """Prepare, consume, and close opaque mutation authority."""

    async def prepare_contribution_policy_mutation(
        self, facts: ContributionPolicyMutationAuthorizationFacts
    ) -> object:
        """Prepare process-local transaction-bound authority."""

    async def consume_contribution_policy_mutation(
        self, prepared: object, facts: ContributionPolicyMutationAuthorizationFacts
    ) -> UUID:
        """Consume exact authority and return its bound actor."""

    def close_contribution_policy_mutation(self, prepared: object) -> None:
        """Invalidate one prepared object exactly once."""


class DenyContributionPolicyAuthorization:
    """Production-safe default while CP05 actions remain unavailable."""

    async def authorize_contribution_policy_read(
        self, request: ContributionPolicyReadRequest
    ) -> None:
        del request
        raise ContributionPolicyUnavailable("contribution_policy_unavailable")

    async def prepare_contribution_policy_mutation(
        self, facts: ContributionPolicyMutationAuthorizationFacts
    ) -> object:
        del facts
        raise ContributionPolicyUnavailable("contribution_policy_unavailable")

    async def consume_contribution_policy_mutation(
        self, prepared: object, facts: ContributionPolicyMutationAuthorizationFacts
    ) -> UUID:
        del prepared, facts
        raise ContributionPolicyUnavailable("contribution_policy_unavailable")

    def close_contribution_policy_mutation(self, prepared: object) -> None:
        del prepared


ContributionPolicyProjectEligibilityPort = ProjectContributionPolicyEligibilityPort
