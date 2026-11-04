"""Nominal post-policy PREP seam over finalized immutable owner commitments."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
import json
from typing import Literal, Protocol
from uuid import UUID

from app.core.hashing import canonical_json_hash

PostPolicyAction = Literal[
    "project.post_submit_checker_policy.derive",
    "project.post_submit_checker_policy.approve",
    "project.post_submit_checker_policy.correction.request",
    "project.guide_compilation.review_package.read",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class PostPolicyAuthorizationLocator:
    """Authority selectors resolved before any guide or policy lock."""

    project_id: UUID
    guide_id: UUID
    compilation_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    action_id: PostPolicyAction
    operation_id: UUID
    request_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PostPolicyAuthorizationFacts:
    """Exact commitments recomposed under the existing product serialization."""

    locator: PostPolicyAuthorizationLocator
    policy_id: UUID
    finalization_id: UUID
    setup_run_id: UUID
    setup_generation: int
    upstream_approval_operation_id: UUID
    upstream_approval_output_digest: str
    policy_hash: str
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    result_hash: str
    post_component_hash: str
    requirement_inventory_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_bundle_hash: str
    projection_operation_id: UUID
    lifecycle_status: Literal["compiled", "approved", "superseded"]
    target_digest: str
    request_digest: str
    output_digest: str

    def resource_json(self) -> dict:
        values = json.loads(json.dumps(asdict(self), default=str))
        del values["locator"]["request_id"]
        return values

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.resource_json())


@dataclass(frozen=True, slots=True, kw_only=True)
class PostPolicyAuthorityReceipt:
    """An exact human project grant or fixed setup-service decision."""

    actor_profile_id: UUID
    identity_link_id: UUID
    authorization_decision_event_id: UUID
    action_id: PostPolicyAction
    permission_id: str
    scope_project_id: UUID
    resource_context_digest: str
    admin_role_grant_id: UUID | None
    service_identity: str | None


class PreparedPostPolicyOperation(ABC):
    """Request-local, root-transaction-bound capability; no duck-typed approval."""

    __slots__ = ()

    def __reduce_ex__(self, _protocol):
        raise TypeError("prepared post-policy authority is process-local")

    @abstractmethod
    async def authorize_read(self, facts: PostPolicyAuthorizationFacts) -> None: ...

    @abstractmethod
    async def consume_new(self, facts: PostPolicyAuthorizationFacts) -> PostPolicyAuthorityReceipt: ...

    @abstractmethod
    async def validate_replay(self, facts: PostPolicyAuthorizationFacts, decision_event_id: UUID) -> None: ...


class PostPolicyAuthorizationPort(Protocol):
    """Explicit authorization port; the composition root supplies live AUTH."""

    def prepare_post_policy_operation(
        self, locator: PostPolicyAuthorizationLocator,
    ) -> AbstractAsyncContextManager[PreparedPostPolicyOperation]: ...
