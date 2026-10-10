"""Real ZIP, ART custody and hidden TASK creation with exact contribution lineage."""

import asyncio
from dataclasses import replace
from contextlib import AsyncExitStack, asynccontextmanager
from types import SimpleNamespace
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRequest,
    SubmissionAdmissionConsumptionError,
)
from app.modules.artifacts.models import (
    SubmissionBundleAdmission,
    ArtifactBinding,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.models import AuditEvent, Submission, TaskAssignment, WorkstreamTask
from tests.pre_submit_test_helpers import approved_pre_submit_fixture
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.test_artifact_admission import (
    _settings,
    _namespace,
    _local_store,
    _context,
    _seed_human_actor,
)
from tests.test_default_pre_submit_execution import _archive, _bytes


from tests.tasks.submission_lineage_support import _seed_services, _verified_admission


@asynccontextmanager
async def _prepared_packet(isolated_database_env, tmp_path):
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    try:
        plan, policy = await approved_pre_submit_fixture(factory, namespace, guide_version="v1")
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
            byte_source=_bytes(_archive(evidence_path=policy["evidence_path"])),
        )
        admission_id = await _verified_admission(
            factory, store, namespace, settings, context, request
        )
        creation = SubmissionCreationRequest(
            task_id=task_id,
            assignment_id=assignment_id,
            contributor_id=context.actor_profile_id,
            predecessor_submission_id=None,
            admission_id=admission_id,
            summary=request.summary,
            contributor_attestation=request.contributor_attestation,
        )
        yield SimpleNamespace(
            factory=factory, context=context, task_id=task_id, assignment_id=assignment_id,
            admission_id=admission_id, creation=creation,
        )
    finally:
        bootstrap.close()
        await engine.dispose()


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
            with pytest.raises(SubmissionAdmissionConsumptionError):
                await compose_hidden_submission_creation_command(
                    session,
                    context,
                    request_id=new_record_id(),
                    correlation_id=new_record_id(),
                ).create(replace(creation, admission_id=new_record_id()))
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
                with pytest.raises(SubmissionAdmissionConsumptionError, match="submission_bundle_admission_unavailable"):
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
        ("UPDATE public.pre_submit_evidence_sets SET packet_sha256='sha256:' || repeat('0',64) "
         "WHERE id=(SELECT pre_submit_evidence_set_id FROM public.submission_bundle_admissions WHERE id=:id)",
         "pre_submit_evidence_sets rows are immutable"),
        ("UPDATE public.submission_bundle_admissions SET pre_submit_evidence_set_id=:foreign WHERE id=:id",
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
    from tests.migration_fixtures import _config, current_art_attempt_seed_schema

    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0021_submission_manifest")
        async with AsyncExitStack() as stack:
            async with current_art_attempt_seed_schema(isolated_database_env):
                h = await stack.enter_async_context(_prepared_packet(isolated_database_env, tmp_path))
                from tests.historical_submission_fixtures import write_historical_submission
                created = await write_historical_submission(h.factory, h.context, h.creation)
                # The predecessor allowed this mismatch. Upgrade must neither invent
                # evidence nor rewrite/delete retained text, even when inconsistent.
                async with h.factory.begin() as session:
                    await session.execute(text(
                        "UPDATE public.submissions SET summary = summary || ' Historical.' WHERE id=:id"
                    ), {"id": created.submission_id})
                    before = await session.scalar(text(
                        "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
                    ), {"id": created.submission_id})
            # Bind this preservation proof to the packet-custody migration.
            await asyncio.to_thread(command.upgrade, _config(), "0022_submission_packet_custody")
            async with h.factory() as session:
                after = await session.scalar(text(
                    "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
                ), {"id": created.submission_id})
                assert after == before
                assert await session.scalar(text(
                    "SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgname='submission_packet_custody'"
                )) == 1
        await asyncio.to_thread(command.upgrade, _config(), "head")
