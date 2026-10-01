"""Controlled complete CHECKERS owner facts for ART output-custody tests."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.service import ActorService
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    CheckerOutputArtifactAdmissionRequest,
)
from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
    ArtifactAdmissionScope,
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactReplica,
    ArtifactStorageNamespace,
)
from app.modules.checkers.api.output_custody import (
    CheckerOutputReservation,
    CheckerOutputSlot,
)
from app.modules.checkers.models import CheckerRun
from app.modules.checkers.post_submit_contracts import make_post_submit_request
from app.modules.tasks.models import Submission, WorkstreamTask
from tests.checkers.post_submit.support import request as checker_evaluation_request


async def make_checker_output_reservation(
    session,
    checker_run_id: str | UUID,
    *,
    slot_key: str = "platform-review",
    media_type: str = "application/octet-stream",
    maximum_bytes: int = 1024,
    worker_lease_id: UUID | None = None,
    worker_lease_generation: int = 1,
) -> CheckerOutputReservation:
    """Derive hash-valid public owner facts from one actual seeded run."""
    checker_run = await session.get(CheckerRun, str(checker_run_id))
    assert checker_run is not None
    submission = await session.scalar(
        select(Submission).where(
            Submission.id == checker_run.submission_id,
            Submission.version == checker_run.submission_version,
            Submission.task_id == checker_run.task_id,
        )
    )
    task = await session.get(WorkstreamTask, checker_run.task_id)
    assert submission is not None and task is not None
    seed = checker_evaluation_request(project_id=UUID(task.project_id))
    fields = seed.model_dump(exclude={"request_sha256"})
    fields.update(
        task_id=UUID(task.id),
        assignment_id=UUID(submission.task_assignment_id),
        submission_id=UUID(submission.id),
        submission_version=submission.version,
    )
    evaluation = make_post_submit_request(**fields)
    return CheckerOutputReservation(
        evaluation=evaluation,
        checker_run_id=UUID(checker_run.id),
        worker_lease_id=worker_lease_id or new_record_id(),
        worker_lease_generation=worker_lease_generation,
        slots=(
            CheckerOutputSlot(
                key=slot_key,
                media_type=media_type,
                maximum_bytes=maximum_bytes,
            ),
        ),
    )


async def make_checker_output_admission_request(
    session,
    checker_run_id: str,
    source,
    *,
    slot_key: str = "platform-review",
    worker_lease_id: UUID | None = None,
    worker_lease_generation: int = 1,
) -> CheckerOutputArtifactAdmissionRequest:
    """Build detached owner facts without rolling back or expiring caller state."""
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    async with factory() as reservation_session:
        reservation = await make_checker_output_reservation(
            reservation_session,
            checker_run_id,
            slot_key=slot_key,
            media_type=source.commitment.media_type,
            maximum_bytes=max(1, source.commitment.byte_count),
            worker_lease_id=worker_lease_id,
            worker_lease_generation=worker_lease_generation,
        )
    return CheckerOutputArtifactAdmissionRequest(
        reservation=reservation,
        slot_key=slot_key,
        source=source,
    )


_ADMISSION_BASELINE_MODELS = (
    ArtifactStorageNamespace,
    ArtifactAdmissionScope,
    ArtifactAdmissionCharge,
    ArtifactPutAttempt,
    ArtifactContent,
    ArtifactReplica,
    ArtifactOperationReceipt,
)


async def checker_admission_baseline(session) -> dict[type, int]:
    """Snapshot every ART row family asserted by checker admission proofs."""
    return {
        model: int(await session.scalar(select(func.count()).select_from(model)) or 0)
        for model in _ADMISSION_BASELINE_MODELS
    }


async def assert_checker_admission_unchanged(session, baseline: dict[type, int]) -> None:
    """Prove a denied checker request created no admission-owned rows."""
    for model in (
        ArtifactStorageNamespace,
        ArtifactAdmissionScope,
        ArtifactAdmissionCharge,
        ArtifactPutAttempt,
    ):
        assert await session.scalar(select(func.count()).select_from(model)) == baseline[model]


async def assert_exact_checker_admission(
    session,
    *,
    result,
    replay,
    takeover,
    request,
    authority,
    project_id: str,
    task_id: str,
    checker_run_id: str,
    baseline: dict[type, int],
) -> None:
    """Retain the complete fixed-service, quota and replay assertion set."""
    attempt = await session.get(ArtifactPutAttempt, str(result.attempt_id))
    scopes = (await session.scalars(select(ArtifactAdmissionScope).order_by(
        ArtifactAdmissionScope.scope_type, ArtifactAdmissionScope.scope_id,
    ))).all()
    links = (await session.scalars(select(ArtifactPutAttemptCharge).where(
        ArtifactPutAttemptCharge.attempt_id == str(result.attempt_id),
    ))).all()
    assert attempt is not None
    assert replay.attempt_id == result.attempt_id
    assert replay.charge_ids == result.charge_ids
    assert takeover.attempt_id == result.attempt_id
    assert takeover.replayed is True
    assert attempt.status == "prepared"
    assert attempt.producer_request_type == "checker_output"
    assert attempt.producer_type == "service_identity"
    assert attempt.producer_ref == ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
    assert attempt.project_id == project_id
    assert attempt.task_id == task_id
    assert attempt.checker_run_id == checker_run_id
    assert attempt.logical_role == "platform-review"
    assert attempt.submission_id == str(request.reservation.evaluation.submission_id)
    assert attempt.submission_version == request.reservation.evaluation.submission_version
    assert attempt.checker_request_digest is not None
    assert authority.calls == 3
    assert attempt.executor_id is None
    assert attempt.lease_expires_at is None
    assert attempt.next_run_at is None
    assert attempt.execution_generation == 0
    assert {scope.scope_type for scope in scopes} == {
        "deployment", "producer", "project", "task",
    }
    assert len(result.charge_ids) == 4
    assert len(links) == 4
    assert await session.scalar(select(func.count()).select_from(ArtifactPutAttempt)) == (
        baseline[ArtifactPutAttempt] + 1
    )
    assert await session.scalar(select(func.count()).select_from(ArtifactAdmissionCharge)) == (
        baseline[ArtifactAdmissionCharge] + 4
    )
    for model in (ArtifactContent, ArtifactReplica, ArtifactOperationReceipt):
        assert await session.scalar(select(func.count()).select_from(model)) == baseline[model]


class ControlledCheckerOutputAdmissionAuthority:
    """Hidden active fixed-service proof; never a production activation."""

    def __init__(self, session, actor_id: UUID, identity_link_id: UUID) -> None:
        self._session = session
        self._actor_id = actor_id
        self._identity_link_id = identity_link_id
        self.calls = 0

    async def consume(self, request: CheckerOutputArtifactAdmissionRequest) -> None:
        self.calls += 1
        proof = await ActorService(self._session).lock_admission_proof(
            self._actor_id,
            self._identity_link_id,
        )
        if (
            proof is None
            or proof.actor_kind != "service"
            or proof.actor_status != "active"
            or proof.identity_link_id != str(self._identity_link_id)
            or proof.identity_link_subject_kind != "service"
            or proof.identity_link_status != "active"
            or proof.service_identity
            != ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
        ):
            raise ArtifactAuthorityDeniedError(
                "checker output service identity is unavailable"
            )


async def seed_checker_output_relationships(session, namespace, *, policy_bundle=None) -> tuple[str, str, str]:
    """Prepare canonical input before callers mint bounded output scratch."""
    from tests.test_artifact_admission import _seed_human_actor, _context
    from tests.projects.unified_policy_fixtures import create_standalone_unified_policy

    if policy_bundle is None:
        assert not session.in_transaction(), "Arrange canonical setup before staging artifact rows"
        policy_bundle = await create_standalone_unified_policy(
            async_sessionmaker(session.bind, expire_on_commit=False), namespace,
        )
    values, effective, _pre = policy_bundle
    project_id = str(values["project"])
    task_id = str(new_record_id())
    contributor_id = str(new_record_id())
    contributor_link_id = str(new_record_id())
    await _seed_human_actor(
        session,
        _context(
            actor_profile_id=UUID(contributor_id),
            identity_link_id=UUID(contributor_link_id),
        ),
    )
    from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
    from tests.submission_preparation_auth_helpers import install_submitter_grant
    from tests.submission_fixtures import seed_retained_submission
    from tests.test_tasks import complete_submission_payload

    assignment_id = str(new_record_id())
    params = {"task": task_id, "assignment": assignment_id, "project": project_id,
              "actor": contributor_id}
    connection = await session.connection()
    await seed_started_task_for_artifact_test(connection, params)
    await install_submitter_grant(connection, params)
    await session.commit()
    payload = complete_submission_payload()
    payload["worker_attestation"] += " " + " ".join(
        effective["effective_policy"]["attestation_terms"]
    )
    submission_id = await seed_retained_submission(task_id, payload)
    from tests.checkers.execution.storage_fixture import seed_storage_run
    checker_run_id = await seed_storage_run(async_sessionmaker(session.bind, expire_on_commit=False),
                                            submission_id, state="queued")
    return project_id, task_id, checker_run_id
