"""Exact complete-guide activation values; live authority is supplied separately."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Annotated, Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_proposals import Digest, MissingCheckerCapability
from app.modules.projects.api.post_policy import PostPolicyTarget
from app.modules.projects.api.guide_activation_context import (
    GuideContributionDiscoveryPort,
    GuidePolicySelection,
)


class ActivationValue(BaseModel):
    """Closed immutable activation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class GuideActivationInput(ActivationValue):
    """Bind exactly the separately approved generation displayed to the manager."""

    target: PostPolicyTarget
    post_approval_operation_id: UUID
    post_approval_output_digest: Digest
    guide_mutation_generation: Annotated[int, Field(strict=True, gt=0)]
    review: GuidePolicySelection
    revision: GuidePolicySelection
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    expected_previous_active_guide_id: UUID | None
    expected_previous_active_guide_generation: Annotated[int, Field(strict=True, gt=0)] | None

    @model_validator(mode="after")
    def exact_predecessor(self):
        if (
            self.expected_previous_active_guide_id is None
            and self.expected_previous_active_guide_generation is not None
        ):
            raise ValueError("previous active guide identity must be complete or absent")
        if self.expected_previous_active_guide_id == self.target.proposal.guide_id:
            raise ValueError("activation cannot supersede its own guide")
        return self

class GuideActivationCommand(GuideActivationInput):
    """Exact public selections plus the transport-validated replay key."""

    idempotency_key: UUID

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class GuideContributionPolicyFacts(ActivationValue):
    """PROJECTS-local facts returned by the injected CON public-port bridge."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    purpose: Literal["guide_activation"]
    version_number: Annotated[int, Field(strict=True, gt=0)]
    rules_and_definitions_digest: Digest
    adapter_binding_ids: tuple[UUID, ...]


class GuideContributionPolicyPort(Protocol):
    """Validate a new exact binding while retaining the caller transaction locks."""

    async def validate_for_activation(
        self,
        project_id: UUID,
        policy_id: UUID,
        version_id: UUID,
    ) -> GuideContributionPolicyFacts: ...


class GuideActivationReceipt(ActivationValue):
    """Immutable successful binding; later supersession never rewrites it."""

    operation_id: UUID
    command: GuideActivationCommand
    contribution: GuideContributionPolicyFacts
    activation_generation: Annotated[int, Field(strict=True, gt=0)]
    effective_at: datetime
    prior_project_status: Literal["draft", "active"]

    @model_validator(mode="after")
    def exact_binding(self):
        if (
            self.contribution.project_id != self.command.target.proposal.project_id
            or self.contribution.contribution_policy_id != self.command.contribution_policy_id
            or self.contribution.contribution_policy_version_id
            != self.command.contribution_policy_version_id
            or self.activation_generation != self.command.guide_mutation_generation + 1
            or self.effective_at.tzinfo is None
        ):
            raise ValueError("activation receipt binding mismatch")
        if self.operation_id.version != 7:
            raise ValueError("activation operation identity must be UUIDv7")
        return self


class GuideActivationLocator(ActivationValue):
    """Authority identity selected before product locks."""

    project_id: UUID
    guide_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    operation_id: UUID
    request_id: UUID
    action_id: Literal["project.guide.activate"] = "project.guide.activate"


class GuideActivationFacts(ActivationValue):
    """Exact locked input/output commitments consumed by authority."""

    locator: GuideActivationLocator
    receipt: GuideActivationReceipt

    def resource_json(self) -> dict:
        value = self.model_dump(mode="json")
        value["locator"].pop("request_id")
        return value

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.resource_json())


class GuideActivationAuthorityReceipt(ActivationValue):
    """Consumed manager authority over exactly one activation fact set."""

    actor_profile_id: UUID
    identity_link_id: UUID
    admin_role_grant_id: UUID
    authorization_decision_event_id: UUID
    action_id: Literal["project.guide.activate"]
    permission_id: Literal["project.guide.manage"]
    scope_project_id: UUID
    resource_context_digest: Digest


class PreparedGuideActivation(ABC):
    """Nominal, process-local participant bound to the caller root transaction."""

    __slots__ = ()

    def __reduce_ex__(self, _protocol):
        raise TypeError("prepared guide activation is process-local")

    @abstractmethod
    async def consume_new(self, facts: GuideActivationFacts) -> GuideActivationAuthorityReceipt: ...

    @abstractmethod
    async def validate_replay(
        self, facts: GuideActivationFacts, decision_event_id: UUID
    ) -> None: ...


class GuideActivationAuthorizationPort(Protocol):
    """Acquire full AUTH scope before owner locks; close the handle on every exit."""

    def lock_activation_scope(
        self,
        locator: GuideActivationLocator,
    ) -> AbstractAsyncContextManager[PreparedGuideActivation]: ...


_Actor = TypeVar("_Actor", contravariant=True)


class GuideActivationPort(Protocol[_Actor]):
    """One caller-owned atomic operation with explicit live activation authority."""

    async def activate(
        self,
        command: GuideActivationCommand,
        *,
        actor: _Actor,
        request_id: UUID,
    ) -> GuideActivationReceipt: ...


GuideActivationRefusalCode = Literal["proposal_unavailable", "proposal_stale", "approval_blocked"]
GuideActivationUnmetReason = Literal[
    "project_not_activatable",
    "post_policy_unavailable",
    "upstream_approval_not_current",
    "post_policy_not_approved",
    "guide_not_draft",
    "review_policy_unselected",
    "revision_policy_unselected",
    "source_snapshot_invalid",
    "checker_policy_unsupported",
    "checker_policy_mismatch",
    "checker_registry_changed",
    "checker_capability_missing",
    "human_review_required_by_guide",
    "activation_requirements_unmet",
    "contribution_policy_unpublished",
    "contribution_policy_invalid",
    "activation_integrity_failed",
]
_UNMET_MESSAGES: dict[str, str] = {
    "project_not_activatable": "The project is not draft or active.",
    "post_policy_unavailable": "No derived post-submit checker policy is available for this guide.",
    "upstream_approval_not_current": "The guide proposal approval is not the current approved chain tip.",
    "post_policy_not_approved": "The post-submit checker policy is not approved.",
    "guide_not_draft": "Only a draft guide can be activated.",
    "review_policy_unselected": "The guide has no selected review policy.",
    "revision_policy_unselected": "The guide has no selected revision policy.",
    "source_snapshot_invalid": "The guide source snapshot failed its integrity check.",
    "checker_policy_unsupported": "The approved checker policy is not a supported external checker policy.",
    "checker_policy_mismatch": "The approved pre-submit checker bundle differs from its stored policy.",
    "checker_registry_changed": "A selected checker registry entry changed after approval.",
    "checker_capability_missing": "The approved compilation still lists missing checker capabilities.",
    "human_review_required_by_guide": "The review policy disables human review but a requirement needs it.",
    "activation_requirements_unmet": "The guide, its policies or their approvals do not meet activation requirements.",
    "contribution_policy_unpublished": "The project has no current published contribution policy version.",
    "contribution_policy_invalid": "The current published contribution policy version cannot bind a guide.",
    "activation_integrity_failed": "Stored activation inputs failed an integrity check.",
}


class GuideActivationCondition(ActivationValue):
    """One unmet precondition with the refusal code activation would raise for it."""

    code: GuideActivationRefusalCode
    reason: GuideActivationUnmetReason
    message: str = Field(min_length=1, max_length=200)
    missing_capabilities: tuple[MissingCheckerCapability, ...] = Field(default=(), max_length=200)

    @classmethod
    def of(
        cls,
        code: GuideActivationRefusalCode,
        reason: GuideActivationUnmetReason,
        missing_capabilities: tuple[MissingCheckerCapability, ...] = (),
    ) -> "GuideActivationCondition":
        """Build a condition with the fixed message for its reason."""
        return cls(
            code=code, reason=reason, message=_UNMET_MESSAGES[reason],
            missing_capabilities=missing_capabilities,
        )


class GuideActivationReadiness(ActivationValue):
    """Dry-run result over the current selections; not a promise that activation will succeed later.

    ``unmet`` is in activation's check order, so its first entry carries the
    refusal code activation would raise now. A check whose inputs are missing
    is not evaluated.
    """

    project_id: UUID
    guide_id: UUID
    ready: bool
    unmet: tuple[GuideActivationCondition, ...]

    @model_validator(mode="after")
    def ready_means_no_unmet(self):
        """``ready`` is exactly the absence of unmet conditions."""
        if self.ready == bool(self.unmet):
            raise ValueError("activation readiness disagrees with its unmet conditions")
        return self


class GuideActivationReadinessPort(Protocol):
    """Evaluate activation's own conditions in the caller transaction, without writes or authority."""

    async def readiness(
        self,
        project_id: UUID,
        guide_id: UUID,
        *,
        contribution: GuideContributionDiscoveryPort,
    ) -> GuideActivationReadiness: ...
