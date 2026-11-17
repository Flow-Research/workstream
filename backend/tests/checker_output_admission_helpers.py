"""Controlled complete CHECKERS owner facts for ART output-custody tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import re
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorProfile
from app.modules.actors.service import ActorService
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    CheckerOutputArtifactAdmissionRequest,
)
from app.modules.artifacts.api.checker_output_authority import (
    CheckerOutputCommitmentAuthorityFacts,
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
    CheckerOutputSelector,
    CheckerOutputSlot,
)
from app.modules.model_usage.api import ModelCallExecutionFacts, ModelPaidSlotKey
from app.modules.checkers.execution_repository import stored_request
from app.modules.model_usage.models import (
    CheckerModelUsageEnvelope,
    CheckerModelUsageSlot,
    ModelUsageEffect,
    ModelUsageProfile,
)
from app.modules.checkers.models import CheckerRun
from app.modules.tasks.models import AuditEvent, Submission, WorkstreamTask


_ISOLATED_DATABASE_RE = re.compile(r"workstream_test_([a-f0-9]{12})")
_ISOLATED_ROLE_RE = re.compile(r"workstream_role_([a-f0-9]{12})")
_CONTROLLED_MODEL_GUARDS = {
    "model_usage_profiles": ("model_usage_profiles_guard",),
    "model_usage_effects": (
        "model_usage_effects_guard",
        "checker_model_call_attempt_reconcile",
    ),
}


@asynccontextmanager
async def _suspend_controlled_model_guard(
    session: AsyncSession, *, table: str
) -> AsyncIterator[None]:
    """Suspend one named guard only in the isolated database for this ART fixture."""
    triggers = _CONTROLLED_MODEL_GUARDS.get(table)
    if triggers is None:
        raise RuntimeError("unsupported model usage guard suspension")
    database_name, database_role = (
        await session.execute(text("select current_database(), current_user"))
    ).one()
    database_match = _ISOLATED_DATABASE_RE.fullmatch(str(database_name))
    role_match = _ISOLATED_ROLE_RE.fullmatch(str(database_role))
    if (
        database_match is None
        or role_match is None
        or database_match.group(1) != role_match.group(1)
    ):
        raise RuntimeError("model usage guard suspension requires an isolated test database")
    try:
        for trigger in triggers:
            await session.execute(text(f"alter table {table} disable trigger {trigger}"))
        yield
        # PostgreSQL will not ALTER a table with deferred FK events pending. This
        # fixture owns its dedicated arrangement session, so finish the controlled
        # seed before restoring the guard in a new transaction.
        await session.commit()
        for trigger in triggers:
            await session.execute(text(f"alter table {table} enable trigger {trigger}"))
        await session.commit()
    except BaseException:
        await session.rollback()
        for trigger in triggers:
            await session.execute(text(f"alter table {table} enable trigger {trigger}"))
        await session.commit()
        raise


async def make_checker_output_reservation(
    session,
    checker_run_id: str | UUID,
    *,
    slot_key: str = "model_response",
    media_type: str = "application/json",
    maximum_bytes: int = 1024,
    content_sha256: str | None = None,
) -> CheckerOutputReservation:
    """Create one controlled effect beneath an actual seeded run for ART tests."""
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
    evaluation = stored_request(checker_run)
    assert (
        evaluation.project_id,
        evaluation.task_id,
        evaluation.submission_id,
        evaluation.submission_version,
        evaluation.assignment_id,
    ) == (
        UUID(task.project_id),
        UUID(task.id),
        UUID(submission.id),
        submission.version,
        UUID(submission.task_assignment_id),
    )
    profile_version = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(ModelUsageProfile.profile_version), 0)).where(
                    ModelUsageProfile.project_id == str(evaluation.project_id)
                )
            )
            or 0
        )
        + 1
    )
    profile_id = new_record_id()
    actor_id = await session.scalar(select(ActorProfile.id).order_by(ActorProfile.id).limit(1))
    audit_event_id = await session.scalar(
        select(AuditEvent.id)
        .where(
            ~select(ModelUsageProfile.id)
            .where(ModelUsageProfile.authorization_evidence_id == AuditEvent.id)
            .exists()
        )
        .order_by(AuditEvent.id)
        .limit(1)
    )
    assert actor_id is not None and audit_event_id is not None
    per_call_bytes = max(maximum_bytes, 1024)
    profile_digest = canonical_json_hash(
        {"project_id": str(evaluation.project_id), "profile_id": str(profile_id)}
    )
    profile = ModelUsageProfile(
        id=str(profile_id),
        project_id=str(evaluation.project_id),
        profile_version=profile_version,
        profile_digest=profile_digest,
        provider="test_provider",
        api="test.responses.v1",
        model_snapshot="test-model-2026-10-01",
        generation_settings={"reasoning_effort": "low", "text_verbosity": "low"},
        maximum_request_bytes=per_call_bytes,
        maximum_output_bytes=per_call_bytes,
        maximum_response_bytes=6 * per_call_bytes + 4096,
        maximum_input_tokens=1024,
        maximum_output_tokens=1024,
        maximum_calls=1,
        maximum_total_request_bytes=per_call_bytes,
        maximum_total_response_bytes=6 * per_call_bytes + 4096,
        maximum_total_input_tokens=1024,
        maximum_total_output_tokens=1024,
        allowed_tools=(),
        maximum_tool_calls=0,
        maximum_tool_output_bytes=0,
        deadline_ms=30_000,
        pricing_policy_id=str(new_record_id()),
        pricing_policy_version=1,
        pricing_policy_digest=canonical_json_hash({"profile_id": str(profile_id), "rate": 1}),
        uncached_input_rate=1,
        cached_input_rate=1,
        output_rate=1,
        operation_id=str(new_record_id()),
        actor_profile_id=str(actor_id),
        authorization_evidence_id=str(audit_event_id),
    )
    session.add(profile)
    # This fixture proves ART admission and intentionally does not reproduce MODEL-USAGE
    # authorization/evidence setup. Dedicated real-PG tests exercise both guards.
    async with _suspend_controlled_model_guard(session, table="model_usage_profiles"):
        await session.flush()
    configuration_sha256 = canonical_json_hash({"profile_id": str(profile_id)})
    paid_slot = ModelPaidSlotKey(
        project_id=evaluation.project_id,
        assignment_id=evaluation.assignment_id,
        submission_id=evaluation.submission_id,
        submission_version=evaluation.submission_version,
        requirement_id="model_evidence",
        registry_entry_digest=canonical_json_hash({"checker_run_id": checker_run.id}),
        configuration_sha256=configuration_sha256,
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=profile_digest,
    )
    digest = content_sha256 or canonical_json_hash(
        {"model_call": str(profile_id), "role": slot_key}
    )
    envelope_id, model_slot_id, attempt_id = (
        new_record_id(),
        new_record_id(),
        new_record_id(),
    )
    session.add(
        CheckerModelUsageEnvelope(
            id=str(envelope_id),
            project_id=str(evaluation.project_id),
            task_id=str(evaluation.task_id),
            assignment_id=str(evaluation.assignment_id),
            submission_id=str(evaluation.submission_id),
            submission_version=evaluation.submission_version,
            requirement_id=paid_slot.requirement_id,
            registry_entry_digest=paid_slot.registry_entry_digest,
            configuration_sha256=paid_slot.configuration_sha256,
            profile_id=str(profile_id),
            profile_version=profile_version,
            profile_digest=profile_digest,
        )
    )
    session.add(
        CheckerModelUsageSlot(
            id=str(model_slot_id),
            envelope_id=str(envelope_id),
            project_id=str(evaluation.project_id),
            task_id=str(evaluation.task_id),
            assignment_id=str(evaluation.assignment_id),
            submission_id=str(evaluation.submission_id),
            submission_version=evaluation.submission_version,
            requirement_id=paid_slot.requirement_id,
            registry_entry_digest=paid_slot.registry_entry_digest,
            configuration_sha256=paid_slot.configuration_sha256,
            profile_id=str(profile_id),
            profile_version=profile_version,
            profile_digest=profile_digest,
            slot_index=0,
            first_request_sha256=digest,
        )
    )
    await session.flush()
    session.add(
        ModelUsageEffect(
            id=str(attempt_id),
            checker_slot_id=str(model_slot_id),
            attempt_number=1,
            internal_call_request_id=str(new_record_id()),
            request_sha256=digest,
            state="dispatching",
            prepared_authorization_evidence_id=str(audit_event_id),
        )
    )
    async with _suspend_controlled_model_guard(session, table="model_usage_effects"):
        await session.flush()
    execution = ModelCallExecutionFacts(
        project_id=evaluation.project_id,
        task_id=evaluation.task_id,
        assignment_id=evaluation.assignment_id,
        submission_id=evaluation.submission_id,
        submission_version=evaluation.submission_version,
        evaluation_request_id=evaluation.evaluation_request_id,
        evaluation_generation=evaluation.evaluation_generation,
        checker_run_id=UUID(checker_run.id),
        worker_lease_id=new_record_id(),
        worker_lease_generation=1,
        worker_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    selector = CheckerOutputSelector(
        paid_slot=paid_slot,
        task_id=evaluation.task_id,
        model_call_slot_id=model_slot_id,
        model_call_attempt_id=attempt_id,
        slot_key=slot_key,
        content_sha256=digest,
        execution=execution if slot_key == "model_request" else None,
    )
    return CheckerOutputReservation(
        selector=selector,
        slot=CheckerOutputSlot(
            key=slot_key,
            media_type=media_type,
            maximum_bytes=maximum_bytes,
        ),
    )


async def make_checker_output_admission_request(
    session,
    checker_run_id: str,
    source,
    *,
    slot_key: str = "model_response",
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
            content_sha256=source.commitment.sha256,
        )
        await reservation_session.commit()
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
    request,
    authority,
    project_id: str,
    task_id: str,
    checker_run_id: str,
    baseline: dict[type, int],
) -> None:
    """Retain the complete fixed-service, quota and replay assertion set."""
    attempt = await session.get(ArtifactPutAttempt, str(result.attempt_id))
    scopes = (
        await session.scalars(
            select(ArtifactAdmissionScope).order_by(
                ArtifactAdmissionScope.scope_type,
                ArtifactAdmissionScope.scope_id,
            )
        )
    ).all()
    links = (
        await session.scalars(
            select(ArtifactPutAttemptCharge).where(
                ArtifactPutAttemptCharge.attempt_id == str(result.attempt_id),
            )
        )
    ).all()
    assert attempt is not None
    assert replay.attempt_id == result.attempt_id
    assert replay.charge_ids == result.charge_ids
    assert attempt.status == "prepared"
    assert attempt.producer_request_type == "checker_output"
    assert attempt.producer_type == "service_identity"
    assert attempt.producer_ref == ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
    assert attempt.project_id == project_id
    assert attempt.task_id == task_id
    assert attempt.checker_run_id is None
    assert attempt.model_call_attempt_id == str(request.reservation.selector.model_call_attempt_id)
    assert attempt.logical_role == request.reservation.selector.slot_key
    assert attempt.submission_id == str(request.reservation.selector.paid_slot.submission_id)
    assert attempt.submission_version == request.reservation.selector.paid_slot.submission_version
    assert attempt.checker_request_digest is not None
    assert authority.calls == 2
    assert attempt.executor_id is None
    assert attempt.lease_expires_at is None
    assert attempt.next_run_at is None
    assert attempt.execution_generation == 0
    assert {scope.scope_type for scope in scopes} == {
        "deployment",
        "producer",
        "project",
        "task",
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

    async def consume(self, facts: CheckerOutputCommitmentAuthorityFacts) -> None:
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
            or proof.service_identity != ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
        ):
            raise ArtifactAuthorityDeniedError("checker output service identity is unavailable")


async def seed_checker_output_relationships(
    session, namespace, *, policy_bundle=None
) -> tuple[str, str, str]:
    """Prepare canonical input before callers mint bounded output scratch."""
    from tests.test_artifact_admission import _seed_human_actor, _context
    from tests.projects.unified_policy_fixtures import create_standalone_unified_policy

    if policy_bundle is None:
        assert not session.in_transaction(), "Arrange canonical setup before staging artifact rows"
        policy_bundle = await create_standalone_unified_policy(
            async_sessionmaker(session.bind, expire_on_commit=False),
            namespace,
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
    params = {
        "task": task_id,
        "assignment": assignment_id,
        "project": project_id,
        "actor": contributor_id,
    }
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

    checker_run_id = await seed_storage_run(
        async_sessionmaker(session.bind, expire_on_commit=False), submission_id, state="queued"
    )
    return project_id, task_id, checker_run_id


async def unrelated_checker_task(session, canonical_task):
    """Keep the same locked policy tuple on a distinct task for ownership rejection."""
    unrelated_task_id = str(new_record_id())
    session.add(
        WorkstreamTask(
            id=unrelated_task_id,
            task_size=canonical_task.task_size,
            project_id=canonical_task.project_id,
            locked_guide_version=canonical_task.locked_guide_version,
            locked_post_submit_checker_policy_id=(
                canonical_task.locked_post_submit_checker_policy_id
            ),
            locked_post_submit_checker_policy_version=(
                canonical_task.locked_post_submit_checker_policy_version
            ),
            locked_post_submit_checker_policy_hash=(
                canonical_task.locked_post_submit_checker_policy_hash
            ),
            locked_post_submit_checker_policy_body=(
                canonical_task.locked_post_submit_checker_policy_body
            ),
            locked_review_policy_id=canonical_task.locked_review_policy_id,
            locked_review_policy_generation=(
                canonical_task.locked_review_policy_generation
            ),
            locked_review_policy_hash=canonical_task.locked_review_policy_hash,
            locked_revision_policy_id=canonical_task.locked_revision_policy_id,
            locked_revision_policy_generation=(
                canonical_task.locked_revision_policy_generation
            ),
            locked_revision_policy_hash=(canonical_task.locked_revision_policy_hash),
            locked_guide_source_snapshot_id=(
                canonical_task.locked_guide_source_snapshot_id
            ),
            locked_guide_source_snapshot_hash=(
                canonical_task.locked_guide_source_snapshot_hash
            ),
            locked_effective_project_submission_artifact_policy_id=(
                canonical_task.locked_effective_project_submission_artifact_policy_id
            ),
            locked_effective_project_submission_artifact_policy_hash=(
                canonical_task.locked_effective_project_submission_artifact_policy_hash
            ),
            locked_pre_submit_checker_policy_id=(
                canonical_task.locked_pre_submit_checker_policy_id
            ),
            locked_pre_submit_checker_bundle_hash=(
                canonical_task.locked_pre_submit_checker_bundle_hash
            ),
            title="Unrelated checker task",
            description="Must not own the checker output.",
            status="draft",
            created_by="setup-actor",
        )
    )
    await session.flush()
    return unrelated_task_id
