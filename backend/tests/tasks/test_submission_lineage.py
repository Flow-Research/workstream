"""Real ZIP, ART custody and hidden TASK creation with exact contribution lineage."""

import asyncio
from dataclasses import replace
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.modules.artifacts.api import SubmissionBundlePreparationRequest, SubmissionAdmissionConsumptionError
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
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.tasks.api import (
    SubmissionCreationAdmissionError,
    SubmissionCreationRequest,
    TaskRetainedSubmissionParentsRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import AuditEvent, Submission, TaskAssignment, WorkstreamTask
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
from tests.archive_fixtures import byte_source as _bytes, submission_archive as _archive


from tests.tasks.submission_lineage_support import (
    _prepare_put_attempt,
    _seed_services,
    _verified_admission,
    _verify_put_attempt,
)


@asynccontextmanager
async def _prepared_packet(
    isolated_database_env, tmp_path, *, verify=True, pre_submit_registry_spec=None,
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
        request = SubmissionBundlePreparationRequest(
            actor=ActorIdentityFacts(
                context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN
            ),
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            task_id=task_id,
            assignment_id=assignment_id,
            predecessor_submission_id=None,
            idempotency_key=new_record_id(),
            summary='Completed the "required" project work in folder \\results with evidence.',
            contributor_attestation="I confirm no confidential client data, credentials, or copied source material is included in this submission; rights_confirmed. "
            + " ".join(policy["attestation_terms"]),
            media_type="application/zip",
            byte_source=_bytes(archive_bytes),
        )
        if verify:
            admission_id = await _verified_admission(
                factory, store, namespace, settings, context, request
            )
            put_attempt_id = None
            creation = SubmissionCreationRequest(
                task_id=task_id,
                assignment_id=assignment_id,
                contributor_id=context.actor_profile_id,
                predecessor_submission_id=None,
                admission_id=admission_id,
                summary=request.summary,
                contributor_attestation=request.contributor_attestation,
            )
        else:
            put_attempt_id = await _prepare_put_attempt(
                factory, settings, context, request
            )
            admission_id = None
            creation = None
        yield SimpleNamespace(
            factory=factory, context=context, task_id=task_id, assignment_id=assignment_id,
            project_id=plan.lineage.project_id,
            admission_id=admission_id, creation=creation,
            preparation_request=request, archive_bytes=archive_bytes, settings=settings,
            store=store, namespace=namespace,
            put_attempt_id=put_attempt_id,
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
    async with _prepared_packet(isolated_database_env, tmp_path, verify=False) as h:
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

        admission_id = await _verify_put_attempt(
            h.factory,
            h.store,
            h.namespace,
            h.settings,
            h.put_attempt_id,
        )
        assert admission_id is not None


@pytest.mark.parametrize("lifecycle_owner", ("profile", "identity_link"))
async def test_retained_verification_does_not_reauthorize_contributor_lifecycle(
    isolated_database_env,
    tmp_path,
    lifecycle_owner,
):
    async with _prepared_packet(isolated_database_env, tmp_path, verify=False) as h:
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


async def test_submission_verifier_missing_task_port_rolls_back_terminal_effects(
    isolated_database_env,
    tmp_path,
):
    async with _prepared_packet(isolated_database_env, tmp_path, verify=False) as h:
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
    async with _prepared_packet(isolated_database_env, tmp_path, verify=False) as h:
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


async def test_submission_verifier_locks_task_parents_before_terminal_art(
    isolated_database_env,
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

    async with _prepared_packet(isolated_database_env, tmp_path, verify=False) as h:
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


async def test_real_zip_admission_and_hidden_creation_copy_exact_assignment(
    isolated_database_env, tmp_path, monkeypatch,
):
    async with _prepared_packet(isolated_database_env, tmp_path) as h:
        factory, context = h.factory, h.context
        task_id, assignment_id = h.task_id, h.assignment_id
        admission_id, creation = h.admission_id, h.creation
        # ART rejection occurs after TASK insertion; the command must roll the
        # entire root transaction back without stranding a staged Submission.
        async with factory() as session:
            with pytest.raises(SubmissionCreationAdmissionError) as denied:
                await compose_hidden_submission_creation_command(
                    session,
                    context,
                    request_id=new_record_id(),
                    correlation_id=new_record_id(),
                ).create(replace(creation, admission_id=new_record_id()))
            assert denied.value.code == "submission_bundle_admission_unavailable"
            assert isinstance(denied.value.__cause__, SubmissionAdmissionConsumptionError)
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(Submission)) == 0
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "ready"

        async def assert_unconsumed():
            async with factory() as check:
                assert await check.scalar(select(func.count()).select_from(Submission)) == 0
                assert await check.scalar(select(func.count()).select_from(ArtifactBinding).where(
                    ArtifactBinding.resource_type == "submission",
                )) == 0
                assert await check.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
                )) == 0
                assert (await check.get(SubmissionBundleAdmission, str(admission_id))).status == "ready"
                assert (await check.get(WorkstreamTask, str(task_id))).status == "in_progress"

        # Each field is independently bound to the packet that actually passed.
        for field in ("summary", "contributor_attestation"):
            async with factory() as session:
                with pytest.raises(SubmissionCreationAdmissionError, match="submission_bundle_admission_unavailable"):
                    await compose_hidden_submission_creation_command(
                        session, context, request_id=new_record_id(), correlation_id=new_record_id(),
                    ).create(replace(creation, **{field: getattr(creation, field) + " Changed."}))
            await assert_unconsumed()

        # Change only the stored packet after real ART/AUTH consumption, before
        # dispatch sealing. Force only the deferred checked-packet constraint
        # so a later dispatch constraint cannot mask this independent proof.
        from app.modules.authorization.submission_creation_authorization import PreparedSubmissionCreationAuthorization
        consume = PreparedSubmissionCreationAuthorization.consume
        for column in ("summary", "worker_attestation"):
            async def substitute_packet(owner, handle, facts):
                decision = await consume(owner, handle, facts)
                await owner._session.execute(text(
                    f"UPDATE public.submissions SET {column} = {column} || ' Changed.' "
                    "WHERE submission_bundle_admission_id = :admission"
                ), {"admission": admission_id})
                await owner._session.execute(text("SET CONSTRAINTS submission_packet_custody IMMEDIATE"))
                return decision

            with monkeypatch.context() as patch:
                patch.setattr(PreparedSubmissionCreationAuthorization, "consume", substitute_packet)
                async with factory() as session:
                    with pytest.raises(IntegrityError, match="submission packet differs from checked evidence"):
                        await compose_hidden_submission_creation_command(
                            session, context, request_id=new_record_id(), correlation_id=new_record_id(),
                        ).create(creation)
            await assert_unconsumed()

        async def create():
            async with factory() as session:
                return await compose_hidden_submission_creation_command(
                    session,
                    context,
                    request_id=new_record_id(),
                    correlation_id=new_record_id(),
                ).create(creation)

        results = await asyncio.wait_for(
            asyncio.gather(create(), create(), return_exceptions=True), 30
        )
        successes = [value for value in results if not isinstance(value, BaseException)]
        failures = [value for value in results if isinstance(value, BaseException)]
        assert len(successes) == 2 and not failures, results
        assert successes[0] == successes[1]
        created = successes[0]
        async with factory() as session:
            task = await session.get(WorkstreamTask, str(task_id))
            assignment = await session.get(TaskAssignment, str(assignment_id))
            submission = await session.get(Submission, str(created.submission_id))
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            binding = await session.get(ArtifactBinding, str(created.artifact_binding_id))
            assert (
                submission.contribution_policy_version_id
                == assignment.submitter_contribution_policy_version_id
                == task.locked_contribution_policy_version_id
            )
            assert submission.task_assignment_id == assignment.id
            assert submission.submission_bundle_admission_id == admission.id
            assert submission.artifact_binding_id == binding.id
            assert (
                submission.artifact_content_id
                == binding.content_id
                == admission.artifact_content_id
            )
            assert admission.status == "consumed"
            assert admission.consumed_by_submission_id == submission.id
            assert await session.scalar(select(func.count()).select_from(Submission)) == 1
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
        await asyncio.to_thread(command.upgrade, _config(), "0068_issuer_profile_email")
        from tests.finance.migration_support import assert_reward_cutover_refusal
        await assert_reward_cutover_refusal(isolated_database_env)
