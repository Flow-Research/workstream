"""Exact execution custody contracts; no value is self-authorizing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import UTC
from typing import Annotated, Literal, Protocol

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from app.core.hashing import canonical_json_hash

from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    PostSubmissionExecutionResult,
)
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmitCurrentResultReference
from app.modules.checkers.api.evaluation_context import (
    PostSubmitInputContextCustody, validate_input_context_custody,
)
from app.modules.checkers.api.canonical_values import (
    CheckerValue,
    ResourceId,
    Sha256,
    VersionNumber,
)
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitRequestDeliveryFacts,
)
from app.modules.model_usage.api import ModelRecoveryCandidate

REQUEST_EVENT = "PostSubmissionEvaluationRequested"
COMPLETION_EVENT = "PostSubmissionEvaluationCompleted"


class CheckerExecutionUnavailable(RuntimeError):
    """Conceal absent, foreign, denied, stale or already leased execution."""


class CheckerRequestConflict(CheckerExecutionUnavailable):
    """A request key or generation already belongs to different facts."""


class CheckerRetrySourceUnavailable(CheckerExecutionUnavailable):
    """Conceal an absent, foreign, stale or ineligible retry source."""


class CheckerRetryOperationUnavailable(CheckerExecutionUnavailable):
    """Fail closed when retained retry or authority evidence is inconsistent."""


class CheckerRetryAuthorityDenied(CheckerExecutionUnavailable):
    """An exact retry authority denial available for canonical HTTP restaging."""


class CheckerRetryCursorInvalid(ValueError):
    """The presented recovery cursor does not match its exact signed query."""


def _checker_retry_reason(value: str) -> str:
    if not value.strip() or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise ValueError("checker retry reason is invalid")
    return value


CheckerRetryReason = Annotated[
    str,
    Field(min_length=1, max_length=500),
    AfterValidator(_checker_retry_reason),
]


class CheckerRetryCommand(CheckerValue):
    """Operator's exact source, reason and replay key; no caller-selected successor."""

    project_id: ResourceId
    source_run_id: ResourceId
    request_key: ResourceId
    reason: CheckerRetryReason


class CheckerRetryRequest(CheckerValue):
    """Public body for one exact project/run retry command."""

    reason: CheckerRetryReason


class CheckerRetrySource(CheckerValue):
    """Stored immutable failed-run tuple presented to AUTH before supersession."""

    project_id: ResourceId
    task_id: ResourceId
    assignment_id: ResourceId
    submission_id: ResourceId
    submission_version: VersionNumber
    source_run_id: ResourceId
    source_request_id: ResourceId
    source_request_digest: Sha256
    source_result_id: ResourceId
    source_result_digest: Sha256
    source_finalize_evidence_id: ResourceId
    source_generation: VersionNumber
    failure_code: str = Field(min_length=1, max_length=100)


class CheckerRetryPreparation(CheckerValue):
    """Stable actor/request/source identity bound before AUTH grants are locked."""

    actor_profile_id: ResourceId
    request_key: ResourceId
    reason: CheckerRetryReason
    source: CheckerRetrySource


class CheckerRetrySuccessor(CheckerValue):
    """Actual coordinator and participant identities appended in one transaction."""

    request_id: ResourceId
    request_digest: Sha256
    run_id: ResourceId
    result_id: ResourceId
    generation: VersionNumber
    event_id: ResourceId
    audit_event_id: ResourceId


class CheckerRetryResult(CheckerValue):
    """Retained receipt identities returned on new request or authorized replay."""

    receipt_id: ResourceId
    source: CheckerRetrySource
    successor: CheckerRetrySuccessor
    authorization_decision_id: ResourceId


class CheckerRetrySourceQuery(CheckerValue):
    """One project-bound page request for retained terminal retry sources."""

    project_id: ResourceId
    limit: int = Field(ge=1, le=100, strict=True)
    cursor: str | None = Field(default=None, max_length=512)


class CheckerRetrySourcePosition(CheckerValue):
    """Stable keyset boundary returned only by the signed cursor authority."""

    created_at: AwareDatetime
    source_run_id: ResourceId


class CheckerRetryDiscoverySource(CheckerValue):
    """Bounded failed-run identity sufficient to select one recovery source."""

    project_id: ResourceId
    task_id: ResourceId
    submission_id: ResourceId
    submission_version: VersionNumber
    source_run_id: ResourceId
    source_request_id: ResourceId
    source_request_digest: Sha256
    source_result_id: ResourceId
    source_result_digest: Sha256
    source_finalize_evidence_id: ResourceId
    source_generation: VersionNumber
    failure_code: str = Field(min_length=1, max_length=100)


class CheckerRetrySourceItem(CheckerValue):
    """Privacy-bounded known terminal failure and its immutable retry state."""

    source: CheckerRetryDiscoverySource
    recovery_state: Literal["eligible", "retried", "not_current"]
    created_at: AwareDatetime
    completed_at: AwareDatetime
    retry_receipt_id: ResourceId | None = None
    successor: CheckerRetrySuccessor | None = None
    model_recovery_candidates: tuple[ModelRecoveryCandidate, ...] = ()

    @model_validator(mode="after")
    def exact_retry_state(self):
        retried = self.recovery_state == "retried"
        retained = self.retry_receipt_id is not None and self.successor is not None
        partial = (self.retry_receipt_id is None) != (self.successor is None)
        if retried != retained or partial:
            raise ValueError("checker retry source state is invalid")
        return self


class CheckerRetryPublicResult(CheckerValue):
    """Privacy-bounded public projection of one retained retry result."""

    receipt_id: ResourceId
    source: CheckerRetryDiscoverySource
    successor: CheckerRetrySuccessor
    authorization_decision_id: ResourceId

    @classmethod
    def from_result(cls, result: CheckerRetryResult) -> CheckerRetryPublicResult:
        result = CheckerRetryResult.model_validate(result)
        return cls(
            receipt_id=result.receipt_id,
            source=CheckerRetryDiscoverySource(
                project_id=result.source.project_id,
                task_id=result.source.task_id,
                submission_id=result.source.submission_id,
                submission_version=result.source.submission_version,
                source_run_id=result.source.source_run_id,
                source_request_id=result.source.source_request_id,
                source_request_digest=result.source.source_request_digest,
                source_result_id=result.source.source_result_id,
                source_result_digest=result.source.source_result_digest,
                source_finalize_evidence_id=result.source.source_finalize_evidence_id,
                source_generation=result.source.source_generation,
                failure_code=result.source.failure_code,
            ),
            successor=result.successor,
            authorization_decision_id=result.authorization_decision_id,
        )


class CheckerRetrySourcePage(CheckerValue):
    """One bounded exact project page; a cursor conveys no authority."""

    project_id: ResourceId
    items: tuple[CheckerRetrySourceItem, ...]
    next_cursor: str | None

    @model_validator(mode="after")
    def exact_project(self):
        if len(self.items) > 100 or any(
            item.source.project_id != self.project_id for item in self.items
        ):
            raise ValueError("checker retry source page is invalid")
        return self


class CheckerRetryDiscoveryAuthorizationPort(Protocol):
    """Fresh system-Operator read authority and signed keyset custody."""

    async def authorize_and_decode(
        self, request: CheckerRetrySourceQuery,
    ) -> CheckerRetrySourcePosition | None:
        ...

    def encode(
        self, request: CheckerRetrySourceQuery, position: CheckerRetrySourcePosition,
    ) -> str:
        ...

    async def restage_denial(self, error: Exception) -> bool:
        ...


class CheckerRetryEventExpectation(CheckerValue):
    """Immutable retry event facts for exact TASK delivery comparison."""

    event_type: str
    event_version: int
    aggregate_type: str
    aggregate_id: ResourceId
    correlation_id: str
    causation_event_id: ResourceId | None
    idempotency_key: str
    payload_json: str
    payload_digest: Sha256


class CheckerRetryDelivery(CheckerValue):
    """CHECKERS-owned committed source and exact event for the single TASK handler."""

    request: PostSubmissionExecutionRequest
    expected_event: CheckerRetryEventExpectation


class CheckerRetryAuthorityReceipt(CheckerValue):
    """AUTH's consumed exact resource, used only in the caller transaction."""

    actor_profile_id: ResourceId
    identity_link_id: ResourceId
    decision_id: ResourceId
    resource_digest: Sha256
    resource_json: str


class CheckerRetryAuthorizationPort(Protocol):
    """Fresh Operator preparation, consumption and exact historical replay."""

    async def prepare(self, facts: CheckerRetryPreparation) -> object:
        ...

    async def consume(
        self, handle: object, facts: CheckerRetryPreparation,
        successor: CheckerRetrySuccessor,
    ) -> CheckerRetryAuthorityReceipt:
        ...

    async def validate_replay(
        self, handle: object, facts: CheckerRetryPreparation,
        successor: CheckerRetrySuccessor, original_link_id: ResourceId,
        decision_id: ResourceId,
    ) -> None:
        ...

    def close(self, handle: object) -> None:
        ...

    async def restage_denial(self, error: CheckerRetryAuthorityDenied) -> bool:
        ...


class CheckerRetryAuditPort(Protocol):
    """Append one privacy-bounded initiation fact in the caller transaction."""

    async def record(
        self, preparation: CheckerRetryPreparation,
        successor: CheckerRetrySuccessor,
        authority: CheckerRetryAuthorityReceipt,
    ) -> None:
        ...


class EvaluationReservation(CheckerValue):
    """Stable request, attempt and result identities reserved together."""

    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    result_id: ResourceId
    evaluation_generation: VersionNumber


class ReservedEvaluation(CheckerValue):
    """Exact retained request and identities, without a currentness assertion."""

    request: PostSubmissionExecutionRequest
    reservation: EvaluationReservation


class ExecutionLease(CheckerValue):
    """Database-timed generation granting temporary use of one reserved attempt."""

    reservation: EvaluationReservation
    lease_id: ResourceId
    lease_generation: VersionNumber
    expires_at: AwareDatetime


class ExecuteFacts(CheckerValue):
    """Exact request and lease consumed by execution authority."""

    request: PostSubmissionExecutionRequest
    lease: ExecutionLease


class VerifiedMaterialFacts(CheckerValue):
    """ART-verified byte and lineage facts required for completed results."""

    submission_id: ResourceId
    submission_version: VersionNumber
    admission_id: ResourceId
    binding_id: ResourceId
    content_id: ResourceId
    replica_id: ResourceId
    content_sha256: Sha256
    byte_count: int = Field(strict=True, ge=0)
    semantic_manifest_sha256: Sha256


class FinalizeFacts(ExecuteFacts):
    """Exact terminal result and material custody consumed by finalization authority."""

    result: PostSubmissionExecutionResult
    material: VerifiedMaterialFacts | None
    input_materialization_evidence_id: ResourceId | None
    output_binding_ids: tuple[ResourceId, ...] = Field(max_length=0)
    input_context_custody: PostSubmitInputContextCustody | None = None

    @model_validator(mode="after")
    def material_receipt_required(self):
        """No material-bearing result may discard its actual input authority."""
        if (self.material is None) != (self.input_materialization_evidence_id is None):
            raise ValueError("checker material and input authorization must occur together")
        if self.material is None:
            if self.input_context_custody is not None:
                raise ValueError("checker input context requires material custody")
        else:
            validate_input_context_custody(self.request, self.input_context_custody)
        return self


class FinalizeAuthorityFacts(FinalizeFacts):
    """Final facts extended with the execute receipt read from the locked run."""

    execute_evidence_id: ResourceId


def execution_authority_values(facts: ExecuteFacts | FinalizeAuthorityFacts) -> dict:
    """Commit bounded phase facts; the request digest binds private policy/input text."""
    if type(facts) not in (ExecuteFacts, FinalizeAuthorityFacts):
        raise ValueError("invalid checker authority facts")
    facts = type(facts).model_validate_json(facts.model_dump_json())
    request, lease = facts.request, facts.lease
    reservation = lease.reservation
    if (reservation.request_id, reservation.request_digest, reservation.evaluation_generation) != (
        request.evaluation_request_id, request.request_sha256, request.evaluation_generation,
    ):
        raise ValueError("checker authority reservation mismatch")
    phase = "finalize" if type(facts) is FinalizeAuthorityFacts else "execute"
    action = "checker.post_submit." + phase
    values = {
        "project_id": str(request.project_id), "task_id": str(request.task_id),
        "submission_id": str(request.submission_id), "submission_version": request.submission_version,
        "request_id": str(request.evaluation_request_id), "request_digest": request.request_sha256,
        "evaluation_generation": request.evaluation_generation,
        "attempt_id": str(reservation.attempt_id), "result_id": str(reservation.result_id),
        "lease_id": str(lease.lease_id), "lease_generation": lease.lease_generation,
        "lease_expires_at": lease.expires_at.astimezone(UTC).isoformat(),
    }
    if phase == "finalize":
        facts.result.validate_request(request)
        if (facts.result.attempt_id, facts.result.result_id) != (reservation.attempt_id, reservation.result_id):
            raise ValueError("checker authority result mismatch")
        values.update(
            execute_evidence_id=str(facts.execute_evidence_id),
            input_materialization_evidence_id=(
                str(facts.input_materialization_evidence_id)
                if facts.input_materialization_evidence_id is not None
                else None
            ),
            result_digest=facts.result.result_digest,
            outcome=facts.result.outcome,
            failure_code=facts.result.infrastructure_failure_code,
            material=facts.material.model_dump(mode="json") if facts.material else None,
            output_binding_ids=[],
        )
        if facts.input_context_custody is not None:
            values["input_context_custody"] = facts.input_context_custody.model_dump(mode="json")
    return {
        "domain": "workstream.authorization.checker_post_submit", "phase": phase,
        "action_id": action, "permission_id": action,
        "service_identity": "workstream.checker.post_submit",
        "resource_type": "checker_run", "resource_id": str(reservation.attempt_id),
        "scope_project_id": str(request.project_id), "facts": values,
    }


def execution_authority_digest(facts: ExecuteFacts | FinalizeAuthorityFacts) -> str:
    """One canonical commitment shared by CHECKERS and AUTH, mirrored in PostgreSQL."""
    return canonical_json_hash(execution_authority_values(facts))


class ExecuteEvidence(CheckerValue):
    """Opaque action-specific receipt; real AUTH custody is installed by 04D."""

    evidence_id: ResourceId
    facts_digest: Sha256


class FinalizeEvidence(CheckerValue):
    """Nominally distinct from execute evidence, even for the same run."""

    evidence_id: ResourceId
    facts_digest: Sha256


class PreparedExecution(ABC):
    """Single-operation prepared authority for execution facts."""

    @abstractmethod
    async def consume(self, facts: ExecuteFacts) -> ExecuteEvidence:
        """Consume execution facts and return their action-specific receipt."""
        ...

    @abstractmethod
    async def validate_replay(self, facts: ExecuteFacts, evidence_id: ResourceId) -> None:
        """Validate the stored execute receipt under fresh authority without another allow."""
        ...


class PreparedFinalization(ABC):
    """Separately prepared authority for terminal result publication."""

    @abstractmethod
    async def consume(self, facts: FinalizeAuthorityFacts) -> FinalizeEvidence:
        """Consume finalization facts and return their distinct receipt."""
        ...

    @abstractmethod
    async def validate_replay(self, facts: FinalizeAuthorityFacts, evidence_id: ResourceId) -> None:
        """Validate the exact original finalization receipt without another allow."""
        ...


class CurrentExecutionPort(Protocol):
    """CHECKERS alone verifies current committed worker custody in the caller transaction."""

    async def require_current_execution(self, facts: ExecuteFacts) -> None:
        """Lock the exact fence/run and require the committed unexpired lease."""
        ...


class ExecutionAuthorityPort(Protocol):
    """Provide fresh authorization before acquiring an execution lease."""

    async def preflight(self, request: PostSubmissionExecutionRequest) -> None:
        """Reject unavailable execution authority before entering preparation."""
        ...

    def prepare_execution(
        self, request: PostSubmissionExecutionRequest
    ) -> AbstractAsyncContextManager[PreparedExecution]:
        """Hold execution preparation within the caller transaction."""
        ...


class FinalizationAuthorityPort(Protocol):
    """Provide fresh authorization for atomic terminal publication."""

    async def preflight(self, request: PostSubmissionExecutionRequest) -> None:
        """Reject unavailable finalization authority before preparation."""
        ...

    def prepare_finalization(
        self, request: PostSubmissionExecutionRequest
    ) -> AbstractAsyncContextManager[PreparedFinalization]:
        """Hold finalization preparation within the terminal transaction."""
        ...


class CompletedEvaluation(CheckerValue):
    """Fresh owner projection; the consumer must keep the caller transaction open."""

    reference: SelectedPostSubmitCurrentResultReference
    routing_recommendation: Literal["allow_review", "needs_revision", "task_setup_blocked"]
    result: PostSubmissionExecutionResult


class ReviewModePort(Protocol):
    """Observe whether a locked ReviewPolicy requires human review; grants nothing."""

    async def observe_review_mode(
        self, project_id: ResourceId, review_policy_id: ResourceId,
    ) -> bool | None:
        """Return the exact policy's human-review requirement, or None when unknown."""
        ...


class EvaluationTaskGuard(Protocol):
    """TASK locks exact evaluation scope; the boolean is reservation eligibility, not authority."""

    async def lock_evaluation_scope(self, request: PostSubmissionExecutionRequest) -> bool:
        """Hold TASK locks through commit; False forbids new reservations, not current reads."""
        ...

    async def lock_terminal_retry_scope(self, request: PostSubmissionExecutionRequest) -> None:
        """Lock the active, latest evaluation-pending TASK scope for a new retry."""
        ...

    async def lock_retry_replay_scope(self, request: PostSubmissionExecutionRequest) -> None:
        """Lock exact historical receipt owners without current lifecycle eligibility."""
        ...


class EvaluationCoordinationPort(Protocol):
    """Reserve and read exact current evaluations in caller transactions."""

    async def read_reserved_evaluation(
        self, *, project_id: ResourceId, task_id: ResourceId,
        submission_id: ResourceId, request_id: ResourceId,
    ) -> ReservedEvaluation:
        """Read scoped retained custody without reserving or advancing a fence."""
        ...

    async def read_retry_delivery(
        self, *, project_id: ResourceId, submission_id: ResourceId,
        event_id: ResourceId,
    ) -> CheckerRetryDelivery | None:
        """Return one exact committed retry receipt/event, or no retry source."""
        ...

    async def require_current_completion(
        self, event_id: ResourceId, completion: "EvaluationCompletion"
    ) -> "VerifiedEvaluationCompletion":
        """Lock the exact current completed outcome and return retained result/material facts."""
        ...

    async def reserve_current_evaluation(
        self, request: PostSubmissionExecutionRequest
    ) -> EvaluationReservation:
        """Reserve or replay the exact request without committing the caller transaction."""
        ...

    async def read_current_result(
        self, request: PostSubmissionExecutionRequest
    ) -> CompletedEvaluation:
        """Lock and return the completed evaluation for the exact current request."""
        ...

    async def classify_uncertain_delivery(
        self, request: PostSubmissionExecutionRequest,
    ) -> PostSubmitRequestDeliveryFacts:
        """Lock and classify exact request delivery facts without creating effects."""
        ...


class EvaluationCompletion(CheckerValue):
    """Bounded publication facts, never perpetual authority or private packet data."""

    project_id: ResourceId
    task_id: ResourceId
    submission_id: ResourceId
    reference: SelectedPostSubmitCurrentResultReference
    routing_recommendation: Literal["allow_review", "needs_revision", "task_setup_blocked"]
    output_binding_ids: tuple[ResourceId, ...] = Field(max_length=0)
    execute_evidence_id: ResourceId
    finalize_evidence_id: ResourceId


class VerifiedEvaluationCompletion(CheckerValue):
    """Current owner-verified completion and retained material, never routing authority."""

    completion: EvaluationCompletion
    submission_version: VersionNumber
    material: VerifiedMaterialFacts
    input_materialization_evidence_id: ResourceId
    result: PostSubmissionExecutionResult

    @model_validator(mode="after")
    def bind_completed_result(self):
        """Bind the retained body to its complete canonical result reference."""
        self.completion.reference.validate_result(self.result)
        return self
