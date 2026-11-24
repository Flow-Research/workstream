"""Real ZIP, ART custody and accepted TASK creation with exact contribution lineage."""

import asyncio
from tests.checkers.external.support import pre_registry_spec
from dataclasses import replace
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.artifacts.api import SubmissionAdmissionConsumptionError
from app.modules.artifacts.models import (
    SubmissionBundleAdmission,
    ArtifactBinding,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.authorization import PreparedArtifactInternalAuthority
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.submission_admission import SubmissionBundleAdmissionPublisher
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.tasks.api import (
    TaskRetainedSubmissionParentsRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from app.adapters.tasks import task_submission_context_port
from tests.selected_policy_fixtures import approved_selected_policy_fixture
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.test_artifact_admission import (
    _settings,
    _namespace,
    _local_store,
    _context,
    _seed_human_actor,
)
from tests.archive_fixtures import submission_archive as _archive


from tests.historical_pending_verification import retained_pending_verification

from tests.tasks.submission_lineage_support import (
    _seed_services,
    _verify_put_attempt,
)


@asynccontextmanager
async def _submission_task(
    isolated_database_env, tmp_path, *, pre_submit_registry_spec=pre_registry_spec(),
):
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings(tmp_path, maximum_bytes=1024 * 1024).model_copy(
        update={"external_checker_service_socket": tmp_path / "checker.sock",
                "external_checker_material_root": tmp_path / "scratch"}
    )
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    try:
        plan, policy = await approved_selected_policy_fixture(
            factory, namespace, guide_version="v1",
            pre_submit_registry_spec=pre_submit_registry_spec,
        )
        context = _context()
        await _seed_services(factory)
        task_id, assignment_id = new_record_id(), new_record_id()
        async with factory.begin() as session:
            await _seed_human_actor(session, context)
        async with engine.begin() as connection:
            params = dict(
                task=str(task_id),
                assignment=str(assignment_id),
                project=str(plan.lineage.project_id),
                actor=str(context.actor_profile_id),
            )
            await seed_started_task_for_artifact_test(connection, params)
            await install_submitter_grant(connection, params)
        archive_bytes = _archive(evidence_path=policy["evidence_path"])
        yield SimpleNamespace(
            factory=factory, context=context, task_id=task_id, assignment_id=assignment_id,
            project_id=plan.lineage.project_id, settings=settings, store=store,
            namespace=namespace, archive_bytes=archive_bytes, policy=policy,
        )
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize("changed_owner", ("project", "task", "assignment", "contributor"))
async def test_retained_submission_parent_lock_rejects_identity_substitution(
    isolated_database_env,
    tmp_path,
    changed_owner,
):
    async with _submission_task(isolated_database_env, tmp_path) as h:
        exact = TaskRetainedSubmissionParentsRequest(
            project_id=h.project_id,
            task_id=h.task_id,
            assignment_id=h.assignment_id,
            contributor_id=h.context.actor_profile_id,
        )
        field = {
            "project": "project_id",
            "task": "task_id",
            "assignment": "assignment_id",
            "contributor": "contributor_id",
        }[changed_owner]
        async with h.factory.begin() as session:
            with pytest.raises(TaskSubmissionContextUnavailable):
                await task_submission_context_port(
                    session
                ).lock_retained_submission_parents(
                    replace(exact, **{field: new_record_id()})
                )

        async with h.factory.begin() as session:
            await task_submission_context_port(session).lock_retained_submission_parents(exact)


@pytest.mark.parametrize("lifecycle_owner", ("profile", "identity_link"))
@pytest.mark.postgres_schema_contract
async def test_retained_verification_does_not_reauthorize_contributor_lifecycle(
    isolated_database_env,
    migration_lock,
    tmp_path,
    lifecycle_owner,
):
    async with retained_pending_verification(isolated_database_env, tmp_path, migration_lock) as h:
        async with h.factory.begin() as session:
            if lifecycle_owner == "profile":
                await session.execute(
                    text(
                        "UPDATE public.actor_profiles SET status='suspended', "
                        "suspended_by='retained-verification-test', "
                        "suspended_at=clock_timestamp(), "
                        "suspension_reason='Retained verification must preserve checked bytes' "
                        "WHERE id=:actor"
                    ),
                    {"actor": h.context.actor_profile_id},
                )
            else:
                await session.execute(
                    text(
                        "UPDATE public.actor_identity_links SET status='revoked', "
                        "revoked_by='retained-verification-test', "
                        "revoked_at=clock_timestamp(), "
                        "revoked_reason='Retained verification must preserve checked bytes' "
                        "WHERE id=:link"
                    ),
                    {"link": h.context.identity_link_id},
                )

        admission_id = await _verify_put_attempt(
            h.factory,
            h.store,
            h.namespace,
            h.settings,
            h.put_attempt_id,
        )
        async with h.factory() as session:
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission is not None and admission.status == "ready"


@pytest.mark.postgres_schema_contract
async def test_submission_verifier_missing_task_port_rolls_back_terminal_effects(
    isolated_database_env,
    migration_lock,
    tmp_path,
):
    async with retained_pending_verification(isolated_database_env, tmp_path, migration_lock) as h:
        async with h.factory() as session:
            job = await session.scalar(
                select(ArtifactVerificationJob).where(
                    ArtifactVerificationJob.originating_put_attempt_id
                    == str(h.put_attempt_id)
                )
            )
            assert job is not None
            job_id = UUID(job.id)
            replica_id = job.replica_id
            await session.rollback()
            verifier = PreparedArtifactInternalAuthority(
                session,
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                request_id=new_record_id(),
                correlation_id=new_record_id(),
            )
            with pytest.raises(RuntimeError, match="TASK composition is unavailable"):
                await ArtifactStorageOrchestrator(
                    session,
                    h.store,
                    h.namespace,
                    h.settings,
                    verifier,
                ).verify_object(job_id)

        async with h.factory() as session:
            job = await session.get(ArtifactVerificationJob, str(job_id))
            replica = await session.get(ArtifactReplica, replica_id)
            assert job is not None and job.status == "running"
            assert job.terminal_result_code is None
            assert replica is not None and replica.verification_state == "pending"
            assert await session.scalar(
                select(func.count()).select_from(ArtifactVerificationReceipt)
            ) == 0
            assert await session.scalar(
                select(func.count()).select_from(SubmissionBundleAdmission)
            ) == 0


async def test_retained_submission_parent_port_holds_task_and_assignment_locks(
    isolated_database_env,
    tmp_path,
):
    async with _submission_task(isolated_database_env, tmp_path) as h:
        exact = TaskRetainedSubmissionParentsRequest(
            project_id=h.project_id,
            task_id=h.task_id,
            assignment_id=h.assignment_id,
            contributor_id=h.context.actor_profile_id,
        )
        locks = (
            (WorkstreamTask, str(h.task_id)),
            (TaskAssignment, str(h.assignment_id)),
        )
        async with h.factory() as owner, owner.begin():
            await task_submission_context_port(owner).lock_retained_submission_parents(
                exact
            )
            for model, row_id in locks:
                with pytest.raises(DBAPIError) as blocked:
                    async with h.factory() as contender, contender.begin():
                        await contender.scalar(
                            select(model)
                            .where(model.id == row_id)
                            .with_for_update(nowait=True)
                        )
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"

        for model, row_id in locks:
            async with h.factory() as contender, contender.begin():
                assert await contender.scalar(
                    select(model)
                    .where(model.id == row_id)
                    .with_for_update(nowait=True)
                ) is not None


@pytest.mark.postgres_schema_contract
async def test_submission_verifier_locks_task_parents_before_terminal_art(
    isolated_database_env,
    migration_lock,
    tmp_path,
    monkeypatch,
):
    events = []
    original_task_lock = SubmissionBundleAdmissionPublisher.lock_retained_submission_parents
    original_job_lock = ArtifactRepository.lock_verification_job

    async def observe_task_lock(owner, **kwargs):
        result = await original_task_lock(owner, **kwargs)
        events.append("retained_task_parents")
        return result

    async def observe_job_lock(owner, job_id):
        result = await original_job_lock(owner, job_id)
        events.append("artifact_job")
        return result

    async with retained_pending_verification(isolated_database_env, tmp_path, migration_lock) as h:
        monkeypatch.setattr(
            SubmissionBundleAdmissionPublisher,
            "lock_retained_submission_parents",
            observe_task_lock,
        )
        monkeypatch.setattr(ArtifactRepository, "lock_verification_job", observe_job_lock)
        admission_id = await _verify_put_attempt(
            h.factory,
            h.store,
            h.namespace,
            h.settings,
            h.put_attempt_id,
        )

    assert admission_id is not None
    assert events == [
        "artifact_job",
        "artifact_job",
        "artifact_job",
        "retained_task_parents",
        "artifact_job",
    ]


async def _t5_lineage_snapshot(h):
    from tests.tasks.submission_dispatch.test_replacement_creation import _creation_snapshot

    async with h.factory() as session:
        retained = tuple([await session.scalar(text(
            f"SELECT jsonb_agg(to_jsonb(r) ORDER BY {key}) FROM public.{table} r"
        )) for table, key in (("artifact_contents", "id"), ("artifact_replicas", "id"),
                              ("submission_intake_operations", "id"),
                              ("submission_source_charges", "operation_id"), ("audit_events", "id"))])
    return await _creation_snapshot(h), retained


def _lineage_finalizer(h, settings, operation_id):
    from datetime import timedelta
    from app.adapters.artifacts import submission_admission_consumption_port
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.tasks import accepted_submission_creation_service, intake_task_custody_port
    from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
    from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization

    return AcceptedSubmissionFinalization(
        h.factory, tasks=intake_task_custody_port, checkers=selected_pre_submit_coordinator,
        store=h.store, lease_duration=timedelta(seconds=300),
        submissions=lambda session: accepted_submission_creation_service(
            session, settings=settings, admissions=submission_admission_consumption_port(
                session, request_id=new_record_id(), correlation_id=operation_id)),
        authorization=lambda session: PreparedSubmissionFinalizationAuthorization(
            session, request_id=new_record_id(), correlation_id=operation_id))


async def _assert_t5_packet_refusals(h, finalizer, operation_id, claim, observation, monkeypatch):
    from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
    from app.modules.tasks.submission_composition import TaskSubmissionCreationService

    before = await _t5_lineage_snapshot(h)
    create = TaskSubmissionCreationService.create_accepted
    for field in ("admission_id", "summary", "contributor_attestation"):
        reached = []
        async def substitute_request(service, request, **kwargs):
            reached.append(field)
            value = new_record_id() if field == "admission_id" else getattr(request, field) + " Changed."
            return await create(service, replace(request, **{field: value}), **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(TaskSubmissionCreationService, "create_accepted", substitute_request)
            with pytest.raises(SubmissionAdmissionConsumptionError) as denied:
                await finalizer._finalize(operation_id, claim, observation)
        assert denied.value.code == "submission_bundle_admission_unavailable"
        assert reached == [field]
        assert await _t5_lineage_snapshot(h) == before

    consume = PreparedSubmissionFinalizationAuthorization.consume
    for column in ("summary", "worker_attestation"):
        reached = []
        async def substitute_packet(authority, *, prepared_authorization, facts):
            decision = await consume(authority, prepared_authorization=prepared_authorization, facts=facts)
            assert facts.phase == "commit"
            changed = await authority._session.scalar(text(
                f"UPDATE public.submissions SET {column}={column} || ' Changed.' "
                "WHERE id=:id RETURNING id"), {"id": facts.submission_id})
            assert str(changed) == str(facts.submission_id)
            reached.append(column)
            await authority._session.execute(text("SET CONSTRAINTS submission_packet_custody IMMEDIATE"))
            return decision
        with monkeypatch.context() as patch:
            patch.setattr(PreparedSubmissionFinalizationAuthorization, "consume", substitute_packet)
            with pytest.raises(IntegrityError, match="submission packet differs from checked evidence") as denied:
                await finalizer._finalize(operation_id, claim, observation)
        assert denied.value.orig.sqlstate == "23514"
        assert reached == [column]
        assert await _t5_lineage_snapshot(h) == before


async def test_public_zip_and_t5_copy_exact_assignment_and_checked_packet(
    isolated_database_env, tmp_path, monkeypatch,
):
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.test_public_submission_intake import _client

    async with _submission_task(isolated_database_env, tmp_path) as h:
        h.creation = SimpleNamespace(
            summary=r'Completed the "required" project work in folder \results with evidence.',
            contributor_attestation="I confirm no confidential client data, credentials, or copied source material "
                "is included in this submission; rights_confirmed. " + " ".join(h.policy["attestation_terms"]))
        headers = {
            "Content-Type": "application/zip", "Idempotency-Key": str(new_record_id()),
            "X-Task-Assignment-Id": str(h.assignment_id), "X-Submission-Summary": h.creation.summary,
            "X-Contributor-Attestation": h.creation.contributor_attestation,
        }
        async with _client(h, monkeypatch, isolated_database_env) as client:
            _, settings, errors, calls = await configure_source_http(
                h.factory, client, tmp_path, monkeypatch, h.archive_bytes, "completed")
            route = f"/api/v1/tasks/{h.task_id}/submissions"
            accepted = await client.post(route, headers=headers, content=h.archive_bytes)
            assert accepted.status_code == 202, accepted.text
            assert len(calls) == 1 and errors == [], errors
            operation_id = UUID(accepted.json()["operation_id"])
            before = await _t5_lineage_snapshot(h)
            for name in ("X-Submission-Summary", "X-Contributor-Attestation"):
                changed = await client.post(route, headers=headers | {name: headers[name] + " Changed."},
                                            content=h.archive_bytes)
                assert changed.status_code == 409, changed.text
                assert changed.json()["error"]["code"] == "submission_idempotency_conflict"
                assert await _t5_lineage_snapshot(h) == before
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(Submission)) == 0
        finalizer = _lineage_finalizer(h, settings, operation_id)
        claim = await finalizer._claim(operation_id, new_record_id())
        observation = await h.store.observe_sealed_source(claim.source)
        await _assert_t5_packet_refusals(h, finalizer, operation_id, claim, observation, monkeypatch)
        first, second = await asyncio.wait_for(asyncio.gather(
            finalizer._finalize(operation_id, claim, observation),
            finalizer._finalize(operation_id, claim, observation)), 90)
        assert first == second
        created, h.admission_id = first, first.admission_id
        assert await finalize_retained_intake(h.factory, SimpleNamespace(
            operation_id=operation_id, store=h.store, namespace=h.namespace, settings=settings,
        )) == str(created.submission_id)
        async with h.factory() as session:
            task = await session.get(WorkstreamTask, str(h.task_id))
            assignment = await session.get(TaskAssignment, str(h.assignment_id))
            submission = await session.get(Submission, str(created.submission_id))
            admission = await session.get(SubmissionBundleAdmission, str(h.admission_id))
            binding = await session.get(ArtifactBinding, str(created.artifact_binding_id))
            operation = await session.get(SubmissionIntakeOperation, operation_id)
            assert submission.contribution_policy_version_id == assignment.submitter_contribution_policy_version_id
            assert submission.contribution_policy_version_id == task.locked_contribution_policy_version_id
            assert submission.task_assignment_id == assignment.id
            assert submission.submission_bundle_admission_id == admission.id
            assert submission.artifact_binding_id == binding.id
            assert submission.artifact_content_id == binding.content_id == admission.artifact_content_id
            assert admission.status == "consumed" and admission.consumed_by_submission_id == submission.id
            assert admission.source_operation_id == str(operation_id)
            assert admission.put_attempt_id is admission.durable_intent_id is admission.verification_receipt_id is None
            assert operation.state == "finalized" and operation.finalized_submission_id == submission.id
            assert task.status == "evaluation_pending" and task.active_submission_operation_id is None
            assert await session.scalar(select(func.count()).select_from(Submission)) == 1
            assert await session.scalar(text("SELECT public.submission_dispatch_valid(d) "
                "FROM public.submission_dispatches d WHERE submission_id=:id"), {"id": submission.id}) is True
        assert len(calls) == 1 and errors == []
        await _assert_bound_packet_immutable(h, created)


async def _assert_bound_packet_immutable(h, created):
    factory, admission_id, creation = h.factory, h.admission_id, h.creation
    # Existing owner immutability is part of the new cross-row guarantee.
    for update in (
        "submission_bundle_admission_id=NULL, artifact_binding_id=NULL, artifact_content_id=NULL",
        "submission_bundle_admission_id=:foreign",
        "artifact_binding_id=:foreign",
        "artifact_content_id=:foreign",
    ):
        with pytest.raises(DBAPIError, match="submission contribution identity is immutable"):
            async with factory.begin() as session:
                await session.execute(text(f"UPDATE public.submissions SET {update} WHERE id=:id"),
                                      {"id": created.submission_id, "foreign": new_record_id()})
    for statement, message in (
        ("UPDATE public.selected_pre_submit_runs SET request_digest='sha256:' || repeat('0',64) "
         "WHERE id=(SELECT selected_pre_submit_run_id FROM public.submission_bundle_admissions WHERE id=:id)",
         "selected PRE request custody is immutable"),
        ("UPDATE public.submission_bundle_admissions SET selected_pre_submit_run_id=:foreign WHERE id=:id",
         "submission bundle admission lineage is immutable"),
    ):
        with pytest.raises(DBAPIError, match=message):
            async with factory.begin() as session:
                await session.execute(text(statement), {"id": admission_id, "foreign": new_record_id()})
    async with factory() as session:
        retained = await session.get(Submission, str(created.submission_id))
        assert retained.summary == creation.summary
        assert retained.worker_attestation == creation.contributor_attestation
        assert retained.submission_bundle_admission_id == str(admission_id)
        assert retained.artifact_binding_id == str(created.artifact_binding_id)
        assert retained.artifact_content_id == str(created.artifact_content_id)


@pytest.mark.postgres_schema_contract
async def test_packet_custody_upgrade_preserves_retained_submission(
    isolated_database_env, tmp_path, migration_lock,
):
    import asyncpg
    from alembic import command
    from app.db import session as db_session
    from tests.historical_submission_fixtures import historical_material_fixture
    from tests.migration_fixtures import _config

    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0021_submission_manifest")
        async with historical_material_fixture(tmp_path, isolated_database_env) as h:
            submission_id = h.request["submission_id"]
            # The predecessor allowed this mismatch. Upgrade must neither invent
            # evidence nor rewrite/delete retained text, even when inconsistent.
            async with h.factory.begin() as session:
                await session.execute(text(
                    "UPDATE public.submissions SET summary = summary || ' Historical.' WHERE id=:id"
                ), {"id": submission_id})
                before = await session.scalar(text(
                    "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
                ), {"id": submission_id})
            # Bind this preservation proof to the packet-custody migration.
            await asyncio.to_thread(command.upgrade, _config(), "0022_submission_packet_custody")
            async with h.factory() as session:
                after = await session.scalar(text(
                    "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
                ), {"id": submission_id})
                assert after == before
                assert await session.scalar(text(
                    "SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgname='submission_packet_custody'"
                )) == 1
        await asyncio.to_thread(command.upgrade, _config(), "head")


@pytest.mark.postgres_schema_contract
async def test_retained_publication_failure_inserts_one_immutable_conflict(
    isolated_database_env, tmp_path, migration_lock, monkeypatch,
):
    from app.modules.artifacts.submission_admission import SubmissionBundleAdmissionPublicationError
    calls = []

    async def refuse_publication(self, **kwargs):
        calls.append(kwargs['verification_receipt_id'])
        # The tentative verified receipt really exists before publication fails.
        receipt = await self._session.get(ArtifactVerificationReceipt, kwargs['verification_receipt_id'])
        assert receipt.outcome == 'verified'
        raise SubmissionBundleAdmissionPublicationError('controlled publication rejection')

    async with retained_pending_verification(isolated_database_env, tmp_path, migration_lock) as h:
        monkeypatch.setattr(SubmissionBundleAdmissionPublisher, 'publish_verified', refuse_publication)
        async with h.factory() as session:
            job_id = await session.scalar(select(ArtifactVerificationJob.id).where(
                ArtifactVerificationJob.originating_put_attempt_id == str(h.put_attempt_id)))
            await session.rollback()
            authority = PreparedArtifactInternalAuthority(
                session, service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                request_id=new_record_id(), correlation_id=new_record_id(),
            )
            result = await ArtifactStorageOrchestrator(
                session, h.store, h.namespace, h.settings, authority,
            ).verify_object(UUID(job_id), submission_task_contexts=task_submission_context_port(session))
            assert result == 'conflict'
        async with h.factory() as session:
            receipt = (await session.scalars(select(ArtifactVerificationReceipt))).one()
            assert receipt.outcome == 'conflict'
            assert receipt.observed_sha256 is receipt.observed_byte_count is None
            assert len(calls) == 1 and receipt.id != calls[0]
            assert (await session.get(ArtifactVerificationJob, job_id)).status == 'conflict'
            assert await session.scalar(select(func.count()).select_from(SubmissionBundleAdmission)) == 0
