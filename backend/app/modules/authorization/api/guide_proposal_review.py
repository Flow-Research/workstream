"""Unavailable-by-default authority seam for complete guide proposal operations."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from typing import Literal, Protocol
from uuid import UUID

from app.core.hashing import canonical_json_hash

ProposalAction = Literal[
    "project.guide_compilation.review_package.read",
    "project.submission_artifact_policy.approve",
    "project.guide_compilation.correction.request",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class GuideProposalAuthorizationLocator:
    """Selectors for authority locks before PROJECTS locks its resources."""

    project_id: UUID
    guide_id: UUID
    compilation_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    action_id: ProposalAction
    operation_id: UUID
    request_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GuideProposalAuthorizationFacts:
    """Commitments recomposed under product locks; no raw model or guide text."""

    locator: GuideProposalAuthorizationLocator
    finalization_id: UUID
    artifact_policy_id: UUID | None
    setup_run_id: UUID
    setup_generation: int
    target_digest: str
    request_digest: str
    output_digest: str
    current_approval_operation_id: UUID | None
    current_approval_output_digest: str | None

    @property
    def digest(self) -> str:
        """Bind all typed facts including the full source and output commitments."""
        values = asdict(self)
        values["locator"] = {
            key: str(value) if isinstance(value, UUID) else value
            for key, value in values["locator"].items()
        }
        # Transport request identity is checked by the live prepared handle;
        # an exact retry retains its original business-resource commitment.
        del values["locator"]["request_id"]
        return canonical_json_hash(
            {key: str(value) if isinstance(value, UUID) else value for key, value in values.items()}
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class GuideProposalAuthorityReceipt:
    """Human authority evidence checked before any approval or successor write."""

    actor_profile_id: UUID
    identity_link_id: UUID
    admin_role_grant_id: UUID
    authorization_decision_event_id: UUID
    action_id: ProposalAction
    permission_id: str
    scope_project_id: UUID
    resource_context_digest: str


class PreparedGuideProposalOperation(ABC):
    """Nominal request-local handle; AUTH-12F4 owns concrete binding and checks."""

    __slots__ = ()

    def __reduce_ex__(self, _protocol):
        raise TypeError("prepared guide proposal authority is process-local")

    @abstractmethod
    async def authorize_read(self, facts: GuideProposalAuthorizationFacts) -> None:
        """Authorize exact bounded disclosure with current actor authority."""

    @abstractmethod
    async def consume_new(
        self,
        facts: GuideProposalAuthorizationFacts,
    ) -> GuideProposalAuthorityReceipt:
        """Consume authority in the exact caller session and root transaction."""

    @abstractmethod
    async def validate_replay(
        self,
        facts: GuideProposalAuthorizationFacts,
        decision_event_id: UUID,
    ) -> None:
        """Revalidate current authority and exact retained operation evidence."""


class GuideProposalAuthorizationPort(Protocol):
    """The hidden product owner receives a request-bound capability explicitly."""

    def prepare_proposal_operation(
        self,
        locator: GuideProposalAuthorizationLocator,
    ) -> AbstractAsyncContextManager[PreparedGuideProposalOperation]: ...
