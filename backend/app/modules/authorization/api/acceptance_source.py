"""Untrusted acceptance-source commitments; value construction grants no authority."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.core.hashing import canonical_json_hash

_Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
_Version = Annotated[int, Field(ge=1, le=2_147_483_647)]


class _SourceValue(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )


class HumanReviewSourceCommitment(_SourceValue):
    """Reconstructible Review/request facts, excluding transient AUTH context."""

    source: Literal["human_review"]
    review_id: UUID
    review_decision_request_id: UUID
    project_id: UUID
    task_id: UUID
    task_assignment_id: UUID
    submission_id: UUID
    submission_version: _Version
    review_queue_entry_id: UUID
    review_lease_id: UUID
    reviewer_id: UUID
    packet_manifest_id: UUID
    packet_manifest_digest: _Digest
    reviewer_contribution_policy_version_id: UUID
    locked_review_policy_id: UUID
    locked_review_policy_generation: _Version
    locked_review_policy_hash: _Digest
    artifact_hash: _Digest
    decision: Literal["accept", "needs_revision", "reject"]
    operation_id: UUID
    idempotency_key: UUID
    request_digest: _Digest
    review_aggregate_digest: _Digest


class PostSubmitRoutingSourceCommitment(_SourceValue):
    """TASK source plus its distinct immutable routing request."""

    source: Literal["task_post_submit_route"]
    routing_manifest_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version: _Version
    contributor_id: UUID
    contribution_policy_version_id: UUID
    checker_run_id: UUID
    evaluation_request_id: UUID
    evaluation_generation: _Version
    result_id: UUID
    completion_event_id: UUID
    human_review_required: bool
    locked_review_policy_id: UUID
    locked_review_policy_generation: _Version
    locked_review_policy_hash: _Digest
    content_id: UUID
    content_sha256: _Digest
    semantic_manifest_sha256: _Digest
    routing_source_digest: _Digest
    route_operation_id: UUID
    route_request_digest: _Digest

    @model_validator(mode="after")
    def require_distinct_request(self) -> Self:
        """Checker execution identity cannot stand in for routing identity."""
        if self.route_operation_id == self.evaluation_request_id:
            raise ValueError("routing operation must differ from checker request")
        return self


AcceptanceSourceCommitment = Annotated[
    HumanReviewSourceCommitment | PostSubmitRoutingSourceCommitment,
    Field(discriminator="source"),
]
_source_adapter = TypeAdapter(AcceptanceSourceCommitment)


def acceptance_source_commitment_digest(source: AcceptanceSourceCommitment) -> str:
    """Commit every selected source field without asserting stored authority."""
    checked = _source_adapter.validate_python(source)
    return canonical_json_hash(
        {
            "domain": "workstream.authorization.acceptance_source.v0.1",
            "source": checked.model_dump(mode="json"),
        }
    )


class AcceptanceSourceReceiptFacts(_SourceValue):
    """Detached claimed evidence, not an AUTH decision or executable handle.

    Every consumer must verify the actual immutable event and source, including
    persistence of this commitment. The full runtime resource digest is opaque.
    """

    authorization_decision_event_id: UUID
    action_id: Literal["review.decision", "task.post_submit.route"]
    permission_id: Literal["review.decision", "task.post_submit.route"]
    actor_profile_id: UUID
    actor_identity_link_id: UUID
    service_identity: Literal["workstream.task.post_submit_router"] | None
    matched_grant_id: UUID | None
    project_id: UUID
    resource_type: Literal["review", "task_post_submit_routing_manifest"]
    resource_id: UUID
    request_id: UUID
    correlation_id: UUID
    resource_context_digest: _Digest
    source: AcceptanceSourceCommitment
    source_commitment_digest: _Digest

    @model_validator(mode="after")
    def require_exact_source(self) -> Self:
        """Reject crossed source, principal, request and receipt commitments."""
        source = self.source
        if isinstance(source, HumanReviewSourceCommitment):
            action, resource, identity = "review.decision", "review", source.review_id
            operation = source.operation_id
            principal_valid = (
                self.actor_profile_id == source.reviewer_id
                and self.service_identity is None
                and self.matched_grant_id is not None
            )
        else:
            action = "task.post_submit.route"
            resource, identity = "task_post_submit_routing_manifest", source.routing_manifest_id
            operation = source.route_operation_id
            principal_valid = (
                self.service_identity == "workstream.task.post_submit_router"
                and self.matched_grant_id is None
            )
        if not (
            principal_valid
            and self.action_id == self.permission_id == action
            and self.project_id == source.project_id
            and self.resource_type == resource
            and self.resource_id == identity
            and self.request_id == self.correlation_id == operation
            and self.source_commitment_digest == acceptance_source_commitment_digest(source)
        ):
            raise ValueError("acceptance source receipt commitment differs")
        return self
