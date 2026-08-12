"""Shared dependency-safe construction for focused pre-submit tests."""

from uuid import UUID, uuid4

from app.adapters.checkers import PreSubmitCheckerExecutionAdapter
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationService,
    PreparedBundlePreSubmitEvidenceService,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.tasks.repository import TaskRepository


def checker_execution(inspector, catalogue) -> PreSubmitCheckerExecutionAdapter:
    """Build the owner adapter used by ART materialization tests."""
    return PreSubmitCheckerExecutionAdapter(
        archive_inspector=inspector,
        catalogue=catalogue,
    )


def submission_preparation_request(
    request,
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
) -> SubmissionBundlePreparationRequest:
    """Project one private materialization fixture into the public ART request."""
    return SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            actor_kind=ActorKind.HUMAN,
        ),
        request_id=uuid4(),
        correlation_id=uuid4(),
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        predecessor_submission_id=None,
        idempotency_key=uuid4(),
        summary=request.packet.summary,
        contributor_attestation=request.packet.contributor_attestation,
        media_type="application/zip",
        byte_source=_empty_bytes(),
    )


async def _empty_bytes():
    if False:  # pragma: no cover - preserve the async-iterable request shape
        yield b""


def evidence_workflow(
    *, session, preparation, inspector, catalogue, materialization_authorization,
    preparation_authorization,
) -> PreparedBundlePreSubmitEvidenceService:
    """Compose the exact public-port evidence workflow for database proof."""
    return PreparedBundlePreSubmitEvidenceService(
        session=session,
        materialization=PreparedBundleMaterializationService(
            authorization=materialization_authorization,
            preparation=preparation,
            checker_execution=checker_execution(inspector, catalogue),
            storage_scheme="s3",
        ),
        preparation_authorization=preparation_authorization,
        task_contexts=TaskRepository(session),
        project_contexts=ProjectLockedPolicyRepository(session),
    )
