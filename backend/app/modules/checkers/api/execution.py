"""Exact execution custody contracts; no value is self-authorizing."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import UTC
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field

from app.core.hashing import canonical_json_hash

from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmissionEvaluationResult,
    PostSubmitCurrentResultReference,
)
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitValue,
    ResourceId,
    Sha256,
    VersionNumber,
)

COMPLETION_EVENT = "PostSubmissionEvaluationCompleted"


class CheckerExecutionUnavailable(RuntimeError):
    """Conceal absent, foreign, denied, stale or already leased execution."""


class CheckerRequestConflict(CheckerExecutionUnavailable):
    """A request key or generation already belongs to different facts."""


class EvaluationReservation(PostSubmitValue):
    """Stable request, attempt and result identities reserved together."""

    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    result_id: ResourceId
    evaluation_generation: VersionNumber


class ExecutionLease(PostSubmitValue):
    """Database-timed generation granting temporary use of one reserved attempt."""

    reservation: EvaluationReservation
    lease_id: ResourceId
    lease_generation: VersionNumber
    expires_at: AwareDatetime


class ExecuteFacts(PostSubmitValue):
    """Exact request and lease consumed by execution authority."""

    request: PostSubmissionEvaluationRequest
    lease: ExecutionLease


class VerifiedMaterialFacts(PostSubmitValue):
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

    result: PostSubmissionEvaluationResult
    material: VerifiedMaterialFacts | None
    output_binding_ids: tuple[ResourceId, ...] = Field(max_length=0)


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
            result_digest=facts.result.result_digest, outcome=facts.result.outcome,
            failure_code=facts.result.infrastructure_failure_code,
            material=facts.material.model_dump(mode="json") if facts.material else None,
            output_binding_ids=[],
        )
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


class ExecuteEvidence(PostSubmitValue):
    """Opaque action-specific receipt; real AUTH custody is installed by 04D."""

    evidence_id: ResourceId
    facts_digest: Sha256


class FinalizeEvidence(PostSubmitValue):
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

    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None:
        """Reject unavailable execution authority before entering preparation."""
        ...

    def prepare_execution(
        self, request: PostSubmissionEvaluationRequest
    ) -> AbstractAsyncContextManager[PreparedExecution]:
        """Hold execution preparation within the caller transaction."""
        ...


class FinalizationAuthorityPort(Protocol):
    """Provide fresh authorization for atomic terminal publication."""

    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None:
        """Reject unavailable finalization authority before preparation."""
        ...

    def prepare_finalization(
        self, request: PostSubmissionEvaluationRequest
    ) -> AbstractAsyncContextManager[PreparedFinalization]:
        """Hold finalization preparation within the terminal transaction."""
        ...


class CompletedEvaluation(PostSubmitValue):
    """Fresh owner projection; the consumer must keep the caller transaction open."""

    reference: PostSubmitCurrentResultReference
    routing_recommendation: Literal["allow_review", "needs_revision", "task_setup_blocked"]
    result: PostSubmissionEvaluationResult


class EvaluationCoordinationPort(Protocol):
    """Reserve and read exact current evaluations in caller transactions."""

    async def reserve_current_evaluation(
        self, request: PostSubmissionEvaluationRequest
    ) -> EvaluationReservation:
        """Reserve or replay the exact request without committing the caller transaction."""
        ...

    async def read_current_result(
        self, request: PostSubmissionEvaluationRequest
    ) -> CompletedEvaluation:
        """Lock and return the completed evaluation for the exact current request."""
        ...


class EvaluationCompletion(PostSubmitValue):
    """Bounded publication facts, never perpetual authority or private packet data."""

    project_id: ResourceId
    task_id: ResourceId
    submission_id: ResourceId
    reference: PostSubmitCurrentResultReference
    routing_recommendation: Literal["allow_review", "needs_revision", "task_setup_blocked"]
    output_binding_ids: tuple[ResourceId, ...] = Field(max_length=0)
    execute_evidence_id: ResourceId
    finalize_evidence_id: ResourceId
