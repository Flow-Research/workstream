"""Exact post-submit byte access; neither durable execution nor live authority."""

from dataclasses import dataclass
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Protocol
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.execution import ExecuteFacts, execution_authority_digest, VerifiedMaterialFacts
from app.modules.checkers.api.material import SubmissionMaterialEntry
from app.modules.checkers.api.canonical_values import CheckerValue, ResourceId, Sha256, VersionNumber

from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    PostSubmissionExecutionResult,
)
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    PostSubmitExternalCheckerMaterial,
)


class PostSubmissionMaterializationUnavailable(RuntimeError):
    """Reject material without exposing provider or private packet details."""


class PostSubmissionMaterializationFailure(RuntimeError):
    """Retain a known post-authorization material failure after successful cleanup."""


class MaterializationFacts(CheckerValue):
    """Exact selected ancestry without provider coordinates or scratch authority."""

    execution: ExecuteFacts
    material: VerifiedMaterialFacts
    evidence_id: ResourceId
    verification_receipt_id: ResourceId
    verification_job_id: ResourceId
    verification_generation: VersionNumber
    namespace_fingerprint: Sha256
    semantic_manifest_id: ResourceId


def materialization_authority_digest(facts: MaterializationFacts) -> str:
    """Bind exact read custody without storing its raw facts in an audit payload."""
    if type(facts) is not MaterializationFacts:
        raise ValueError("invalid materialization authority facts")
    facts = MaterializationFacts.model_validate_json(facts.model_dump_json())
    request, material = facts.execution.request, facts.material
    if (material.submission_id, material.submission_version, material.binding_id,
        material.content_id, material.content_sha256, material.byte_count) != (
        request.submission_id, request.submission_version, request.binding_id,
        request.content_id, request.content_sha256, request.byte_count,
    ):
        raise ValueError("materialization authority identity mismatch")
    return canonical_json_hash({
        "domain": "workstream.authorization.post_submit_materialization",
        "action_id": "artifact.post_submit.checker_input.materialize",
        "permission_id": "artifact.checker_input.materialize",
        "service_identity": "workstream.artifact.materializer",
        "resource_type": "checker_run",
        "resource_id": str(facts.execution.lease.reservation.attempt_id),
        "scope_project_id": str(request.project_id),
        "execution_digest": execution_authority_digest(facts.execution),
        "material": facts.model_dump(mode="json", exclude={"execution"}),
    })


class PreparedMaterialization(ABC):
    """A read's exact authority stays within its issuing transaction."""

    @abstractmethod
    async def consume(self, facts: MaterializationFacts) -> UUID:
        """Record the authorized read before storage access."""
        ...

    @abstractmethod
    async def validate_replay(self, facts: MaterializationFacts, evidence_id: UUID) -> None:
        """Recheck the original read receipt after I/O without another audit row."""
        ...


class MaterializationAuthorityPort(Protocol):
    """Prepare before CHECKERS currentness and ART selection in one short transaction."""

    def prepare_materialization(self, facts: ExecuteFacts) -> AbstractAsyncContextManager[PreparedMaterialization]:
        """Hold the materializer principal until exact facts are consumed or revalidated."""
        ...


class PreSubmitMaterialView(Protocol):
    """Permit bounded reads only during the consumer callback."""

    @property
    def entries(self) -> tuple[SubmissionMaterialEntry, ...]:
        """Return verified entries only while the consumer is running."""

    def read_file(self, normalized_path: str, *, maximum_bytes: int) -> bytes:
        """Read one bounded verified file without filesystem authority."""

    def external_checker_grant(
        self, request: ExternalCheckerExecutionRequest
    ) -> AbstractContextManager["ExternalCheckerGrantReference"]:
        """Issue one request-bound opaque grant for this callback lifetime only."""



class SubmissionMaterialView(PreSubmitMaterialView, Protocol):
    """POST adds exact immutable input identity to callback-scoped reads."""

    @property
    def external_checker_material(self) -> PostSubmitExternalCheckerMaterial:
        """Return detached exact POST custody without provider or path coordinates."""


class ExternalCheckerGrantReference(Protocol):
    """Opaque ART grant identity accepted by the trusted service adapter."""

    grant_id: str
    binding_digest: str


class PostSubmissionMaterialConsumer(Protocol):
    """Evaluate scoped input asynchronously and return detached phase facts."""
    async def evaluate(
        self, request: PostSubmissionExecutionRequest, material: SubmissionMaterialView,
    ) -> PostSubmissionExecutionResult:
        """Return detached closed phase facts before ART revokes material access."""


@dataclass(frozen=True, slots=True)
class PostSubmissionMaterializationResult:
    """Bind a validated evaluation to its verified immutable input custody."""

    submission_id: UUID
    submission_version: int
    admission_id: UUID
    binding_id: UUID
    content_id: UUID
    replica_id: UUID
    content_sha256: str
    byte_count: int
    semantic_manifest_sha256: str
    evaluation: PostSubmissionExecutionResult
    input_materialization_evidence_id: UUID


class PostSubmissionMaterializationPort(Protocol):
    """Verify and scope exact input without publishing durable checker results."""
    async def materialize(
        self, facts: ExecuteFacts, consumer: PostSubmissionMaterialConsumer,
    ) -> PostSubmissionMaterializationResult:
        """Verify exact stored bytes and finish cleanup before returning phase facts."""
