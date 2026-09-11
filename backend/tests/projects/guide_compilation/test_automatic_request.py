"""Automatic request proof using real authorized source mutations and ART material."""

from tests.projects.guide_compilation.helpers import runtime_configuration
from tests.migration_fixtures import current_schema_revision

from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.adapters.artifacts import (
    guide_document_manifest_port,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind, AuthorizationDenied
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
from app.modules.checkers.catalogue import project_guide_pre_submission_capabilities
from app.modules.projects.guide_compilation.automatic_request import AutomaticCompilationInputs
from app.modules.projects.models import ProjectSetupRun
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue

from tests.projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)
from tests.projects.guide_fixtures import (
    create_project,
    create_guide,
    read_guide_source_snapshot,
    complete_guide_payload,
)
from tests.committed_guide_fixtures import create_committed_document_fixture
from .test_authorized_execution_service import _execution_service


@pytest.fixture
async def automatic_source(project_client, project_database_env, monkeypatch):  # noqa: F811
    get_settings.cache_clear()
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    engine = create_async_engine(project_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        setup = await session.scalar(
            select(ProjectSetupRun).where(ProjectSetupRun.source_snapshot_id == snapshot["id"])
        )
        profile = await session.scalar(
            select(ActorProfile).where(ActorProfile.service_identity == "workstream.project.setup")
        )
        link = await session.scalar(
            select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == profile.id)
        )
        actor = ActorIdentityFacts(
            UUID(profile.id), UUID(link.id), ActorKind.SERVICE, "workstream.project.setup"
        )
        setup_id = UUID(setup.id)
        acknowledge_automatic_setup(setup)
        await session.commit()
    try:
        yield factory, actor, setup_id, snapshot
    finally:
        await engine.dispose()


def acknowledge_automatic_setup(setup):
    from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

    # Automatic requests require an acknowledged, exact broker claim.
    setup.status = "queued"
    setup.current_step = "queued"
    setup.celery_task_id = project_guide_compilation_task_id(setup.id, setup.setup_generation)
    setup.error_code = None
    setup.error_summary = None


def automatic_service(session, actor):
    inputs = AutomaticCompilationInputs(
        guide_document_manifest_port(session),
        project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue()),
        current_post_submit_catalogue(),
        runtime_configuration=runtime_configuration(),
    )
    return _execution_service(session, actor, automatic_inputs=inputs)


@pytest.mark.asyncio
async def test_automatic_source_requires_documents_then_persists_one_request_and_replays(
    automatic_source,
):
    factory, actor, setup_id, snapshot = automatic_source
    from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError

    async with factory() as session:
        with pytest.raises(GuideCompilationIntegrityError, match="automatic compilation setup unavailable"):
            await automatic_service(session, actor).request_automatic(
                actor=actor, setup_run_id=setup_id
            )
        for table in (
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
        ):
            assert await session.scalar(text(f"select count(*) from {table}")) == 0
        assert (
            await session.scalar(
                text(
                    "select count(*) from audit_events where action_id='project.guide_compilation.request_automatic'"
                )
            )
            == 0
        )
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session:
        first = await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )
        replay = await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )
        assert first == replay
        row = (
            await session.execute(
                text(
                    "select request_trigger,source_mutation_operation_id,source_authorization_decision_event_id from project_guide_compilation_request_operations"
                )
            )
        ).one()
        assert row.request_trigger == "automatic_source_ready"
        assert (
            row.source_mutation_operation_id is not None
            and row.source_authorization_decision_event_id is not None
        )
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert (
            await session.scalar(
                text(
                    "select count(*) from audit_events where action_id='project.guide_compilation.request_automatic'"
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_revoked_service_cannot_recover_automatic_request(automatic_source):
    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='test revocation' where id=:id"
            ),
            {"id": str(actor.identity_link_id)},
        )
    async with factory() as session:
        with pytest.raises(AuthorizationDenied):
            await automatic_service(session, actor).request_automatic(
                actor=actor, setup_run_id=setup_id
            )
        assert (
            await session.scalar(
                text(
                    "select count(*) from audit_events where action_id='project.guide_compilation.request_automatic'"
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_concurrent_automatic_callbacks_share_one_attempt(automatic_source):
    import asyncio

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])

    async def request():
        async with factory() as session:
            return await automatic_service(session, actor).request_automatic(
                actor=actor, setup_run_id=setup_id
            )

    first, second = await asyncio.gather(request(), request())
    assert first == second
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert (
            await session.scalar(
                text("select count(*) from project_guide_compilation_request_operations")
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "column", ["source_mutation_operation_id", "source_authorization_decision_event_id"]
)
async def test_direct_insert_rejects_forged_source_origin(automatic_source, column):
    from uuid import uuid4
    from sqlalchemy.exc import IntegrityError
    from app.modules.projects.guide_compilation.models import (
        ProjectGuideCompilationRequestOperation,
    )

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )
        row = await session.scalar(select(ProjectGuideCompilationRequestOperation))
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        await session.rollback()
        forged = {**values, column: uuid4() if column.endswith("operation_id") else str(uuid4())}
        with pytest.raises(IntegrityError, match="automatic compilation origin lineage is invalid"):
            async with session.begin():
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(**forged)
                )
        # The exact persisted tuple clears the origin guard and reaches uniqueness.
        with pytest.raises(IntegrityError, match="duplicate key value"):
            async with session.begin():
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(**values)
                )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation"]
)
async def test_sql_origin_rejects_each_missing_lineage_selector(automatic_source, field):
    from dataclasses import replace
    from uuid import uuid4
    from app.modules.projects.guide_compilation.repository import (
        GuideCompilationIntegrityError,
        GuideCompilationRepository,
    )

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session, session.begin():
        facts, _identity, origin = await automatic_service(
            session, actor
        )._automatic_inputs.resolve(session, setup_id)
    async with factory() as session:
        changed = replace(
            facts, **{field: facts.setup_generation + 1 if field == "setup_generation" else uuid4()}
        )
        with pytest.raises(GuideCompilationIntegrityError, match="origin unavailable"):
            async with session.begin():
                await GuideCompilationRepository(session).require_automatic_request_origin(
                    changed, origin
                )
        async with session.begin():
            await GuideCompilationRepository(session).require_automatic_request_origin(
                facts, origin
            )
        assert (
            await session.scalar(
                text("select count(*) from project_guide_compilation_request_operations")
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value,error",
    [
        ("request_trigger", "project_manager", "request trigger is invalid"),
        ("actor_profile_id", "00000000-0000-0000-0000-000000000001", "audit event is invalid"),
        ("request_facts_digest", "sha256:" + "0" * 64, "facts digest is invalid"),
        (
            "identity_link_id",
            "00000000-0000-0000-0000-000000000001",
            "service authority is invalid",
        ),
    ],
)
async def test_direct_automatic_insert_requires_exact_authority_and_content(
    automatic_source, field, value, error
):
    from sqlalchemy.exc import IntegrityError
    from app.modules.projects.guide_compilation.models import (
        ProjectGuideCompilationRequestOperation,
    )

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )
        row = await session.scalar(select(ProjectGuideCompilationRequestOperation))
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        await session.rollback()
        with pytest.raises(IntegrityError, match=error):
            async with session.begin():
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(
                        **{**values, field: value}
                    )
                )
        with pytest.raises(IntegrityError, match="duplicate key value"):
            async with session.begin():
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(**values)
                )


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", ["identity_link", "grant"])
async def test_original_manager_revocation_does_not_rewrite_source_consent(
    automatic_source, authority
):
    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session, session.begin():
        setup = await session.get(ProjectSetupRun, str(setup_id))
        if authority == "identity_link":
            await session.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='test revocation' where id=:id"
                ),
                {"id": setup.authorized_via_identity_link_id},
            )
        else:
            await session.execute(text("alter table admin_role_grants disable trigger user"))
            await session.execute(
                text(
                    "update admin_role_grants set status='revoked',version=2,revoked_by_actor_profile_id=:actor,revoked_by_admin_role_grant_id=:grant,revoked_at=now(),revoked_reason='source consent test' where id=:grant"
                ),
                {
                    "actor": setup.authorized_by_actor_profile_id,
                    "grant": setup.authorized_by_admin_role_grant_id,
                },
            )
            await session.execute(text("alter table admin_role_grants enable trigger user"))
    async with factory() as session:
        receipt = await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )
        assert receipt.classification == "compilation_reserved"
        row = (
            await session.execute(
                text(
                    "select actor_profile_id,source_authorization_decision_event_id from project_guide_compilation_request_operations"
                )
            )
        ).one()
        assert row.actor_profile_id == str(actor.actor_profile_id)
        assert row.source_authorization_decision_event_id == setup.authorization_decision_event_id


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
async def test_retained_automatic_evidence_prevents_guide_creation_downgrade(
    automatic_source, migration_lock
):
    import asyncio
    from alembic import command
    from alembic.config import Config

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )

    async with factory() as session:
        assert await session.scalar(text("select version_num from alembic_version")) == current_schema_revision()

    def downgrade():
        with migration_lock():
            command.downgrade(Config("alembic.ini"), "0012_contribution_policy_audit_resource")

    with pytest.raises(
        RuntimeError, match="guide document creation custody cannot be downgraded"
    ):
        await asyncio.to_thread(downgrade)
    async with factory() as session:
        assert (
            await session.scalar(text("select version_num from alembic_version"))
            == current_schema_revision()
        )
        assert (
            await session.scalar(
                text("select count(*) from project_guide_compilation_request_operations")
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["project_manager", "automatic_source_ready"])
async def test_concurrent_request_recovery_rechecks_current_authority(
    automatic_source, monkeypatch, trigger
):
    from dataclasses import replace
    from uuid import uuid4
    from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
    from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
    from app.modules.projects.guide_compilation.service import GuideCompilationService
    from .test_authorized_request_service import _authorized_service

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session, session.begin():
        facts, identity, origin = await automatic_service(session, actor)._automatic_inputs.resolve(
            session, setup_id
        )
        if trigger == "project_manager":
            setup = await session.get(ProjectSetupRun, str(setup_id))
            actor = ActorIdentityFacts(
                UUID(setup.authorized_by_actor_profile_id),
                UUID(setup.authorized_via_identity_link_id),
                ActorKind.HUMAN,
            )
            facts = replace(
                facts, operation_id=uuid4(), request_id=uuid4(), idempotency_key=uuid4()
            )
            origin = ProjectGuideCompilationRequestOrigin(trigger="project_manager")

    async def request():
        async with factory() as session:
            service = (
                _authorized_service(session, actor)
                if trigger == "project_manager"
                else automatic_service(session, actor)
            )
            return await service.authorize_request(
                actor=actor,
                facts=facts,
                identity=identity,
                origin=origin,
                runtime_configuration=runtime_configuration(),
            )

    await request()
    original_match = GuideCompilationRepository.matching_request_operation
    original_recovery = GuideCompilationService._recover_request
    matches, recoveries = [], []

    async def miss_until_concurrent_winner_visible(repository, **kwargs):
        matches.append(True)
        if len(matches) == 1:
            return None
        return await original_match(repository, **kwargs)

    async def revoke_between_reservation_rollback_and_recovery(service, **kwargs):
        assert not service._session.in_transaction()
        recoveries.append(True)
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='recovery race' where id=:id"
                ),
                {"id": str(actor.identity_link_id)},
            )
        return await original_recovery(service, **kwargs)

    monkeypatch.setattr(
        GuideCompilationRepository,
        "matching_request_operation",
        miss_until_concurrent_winner_visible,
    )
    monkeypatch.setattr(
        GuideCompilationService,
        "_recover_request",
        revoke_between_reservation_rollback_and_recovery,
    )
    with pytest.raises(AuthorizationDenied):
        await request()
    assert len(recoveries) == 1 and len(matches) == 2
    async with factory() as session:
        assert (
            await session.scalar(
                text("select count(*) from project_guide_compilation_request_operations")
            )
            == 1
        )
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert (
            await session.scalar(
                text(
                    "select count(*) from audit_events where action_id in ('project.guide_compilation.request','project.guide_compilation.request_automatic')"
                )
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "project_id",
        "guide_id",
        "source_snapshot_id",
        "setup_run_id",
        "source_mutation_operation_id",
        "source_authorization_decision_event_id",
    ],
)
async def test_stored_foreign_source_is_rejected_by_repository_and_insert(
    automatic_source, project_client, field
):  # noqa: F811
    from dataclasses import replace
    from sqlalchemy.exc import IntegrityError
    from app.modules.authorization.api.project_guide_compilation import (
        project_guide_compilation_facts_digest,
    )
    from app.modules.projects.guide_compilation.models import (
        ProjectGuideCompilationRequestOperation,
    )
    from app.modules.projects.guide_compilation.repository import (
        GuideCompilationIntegrityError,
        GuideCompilationRepository,
    )

    factory, actor, setup_id, snapshot = automatic_source
    other_project = await create_project(project_client)
    other_guide = await create_guide(project_client, other_project["id"], complete_guide_payload())
    other_snapshot = await read_guide_source_snapshot(other_project["id"], other_guide["id"])
    await create_committed_document_fixture(snapshot["id"])
    await create_committed_document_fixture(other_snapshot["id"])
    async with factory() as session, session.begin():
        other_setup = await session.scalar(
            select(ProjectSetupRun).where(
                ProjectSetupRun.source_snapshot_id == other_snapshot["id"]
            )
        )
        facts, identity, origin = await automatic_service(session, actor)._automatic_inputs.resolve(
            session, setup_id
        )
        acknowledge_automatic_setup(other_setup)
        await session.flush()
        other_facts, _, other_origin = await automatic_service(
            session, actor
        )._automatic_inputs.resolve(session, UUID(other_setup.id))
    changed_facts, changed_origin = facts, origin
    if field in origin.__dataclass_fields__:
        changed_origin = replace(origin, **{field: getattr(other_origin, field)})
    else:
        changed_facts = replace(facts, **{field: getattr(other_facts, field)})
    async with factory() as session:
        with pytest.raises(GuideCompilationIntegrityError, match="origin unavailable"):
            async with session.begin():
                await GuideCompilationRepository(session).require_automatic_request_origin(
                    changed_facts, changed_origin
                )
        for table in (
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
        ):
            assert await session.scalar(text(f"select count(*) from {table}")) == 0
        assert (
            await session.scalar(
                text(
                    "select count(*) from audit_events where action_id='project.guide_compilation.request_automatic'"
                )
            )
            == 0
        )
        await session.rollback()
        await automatic_service(session, actor).authorize_request(
            actor=actor,
            facts=facts,
            identity=identity,
            origin=origin,
            runtime_configuration=runtime_configuration(),
        )
        row = await session.scalar(select(ProjectGuideCompilationRequestOperation))
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        await session.rollback()
        replacement = (
            getattr(changed_origin, field)
            if field in origin.__dataclass_fields__
            else getattr(changed_facts, field)
        )
        forged = {
            **values,
            field: replacement if field.endswith("operation_id") else str(replacement),
            "request_facts_digest": project_guide_compilation_facts_digest(changed_facts),
        }
        guard = "source operation" if field in origin.__dataclass_fields__ else "origin lineage"
        with pytest.raises(IntegrityError, match=f"automatic compilation {guard} is invalid"):
            async with session.begin():
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(**forged)
                )
        with pytest.raises(IntegrityError, match="duplicate key value"):
            async with session.begin():
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(**values)
                )
        for table in (
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
        ):
            assert await session.scalar(text(f"select count(*) from {table}")) == 1
        assert (
            await session.scalar(
                text(
                    "select count(*) from audit_events where action_id='project.guide_compilation.request_automatic'"
                )
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("event_kind", ["source", "request"])
async def test_direct_insert_checks_exact_authority_digest(automatic_source, event_kind):
    from sqlalchemy.exc import IntegrityError
    from app.modules.projects.guide_compilation.models import (
        ProjectGuideCompilationRequestOperation,
    )

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session, actor).request_automatic(
            actor=actor, setup_run_id=setup_id
        )
        row = await session.scalar(select(ProjectGuideCompilationRequestOperation))
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        event_id = (
            row.source_authorization_decision_event_id
            if event_kind == "source"
            else row.authorization_decision_event_id
        )
        await session.rollback()
        guard = "source authorization" if event_kind == "source" else "request authority digest"
        with pytest.raises(IntegrityError, match=f"automatic compilation {guard} is invalid"):
            async with session.begin():
                # Corrupt only this prerequisite inside a rolled-back test transaction;
                # request insertion and its origin/authority guards remain enabled.
                await session.execute(text("alter table audit_events disable trigger user"))
                await session.execute(
                    text(
                        "update audit_events set after_facts=jsonb_set(after_facts::jsonb,'{resource_context_digest}',to_jsonb(cast(:digest as text))) where id=:id"
                    ),
                    {"id": event_id, "digest": "sha256:" + "0" * 64},
                )
                await session.execute(text("alter table audit_events enable trigger user"))
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(**values)
                )
        with pytest.raises(IntegrityError, match="duplicate key value"):
            async with session.begin():
                await session.execute(
                    ProjectGuideCompilationRequestOperation.__table__.insert().values(**values)
                )
        assert (
            await session.scalar(
                text("select count(*) from project_guide_compilation_request_operations")
            )
            == 1
        )




@pytest.mark.asyncio
@pytest.mark.parametrize("authority", ["profile", "identity_link"])
async def test_automatic_replay_holds_authority_until_receipt_classification(
    automatic_source, monkeypatch, authority
):
    import asyncio
    from app.modules.projects.guide_compilation import service as service_module

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    entered, release, revoke_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = service_module._request_receipt

    async def classify(repository, operation):
        assert repository._session.in_transaction()
        entered.set()
        await release.wait()
        return await original(repository, operation)

    async def replay():
        async with factory() as session:
            return await automatic_service(session, actor).request_automatic(
                actor=actor, setup_run_id=setup_id
            )

    async def revoke():
        async with factory() as session, session.begin():
            revoke_started.set()
            if authority == "identity_link":
                await session.execute(
                    text(
                        "update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='replay race' where id=:id"
                    ),
                    {"id": str(actor.identity_link_id)},
                )
            else:
                await session.execute(
                    text(
                        "update actor_profiles set status='suspended',suspended_by='test',suspended_at=now(),suspension_reason='replay race' where id=:id"
                    ),
                    {"id": str(actor.actor_profile_id)},
                )

    pending = []
    try:
        first = await replay()
        monkeypatch.setattr(service_module, "_request_receipt", classify)
        replay_task = asyncio.create_task(replay())
        pending.append(replay_task)
        await asyncio.wait_for(entered.wait(), 5)
        revoke_task = asyncio.create_task(revoke())
        pending.append(revoke_task)
        await asyncio.wait_for(revoke_started.wait(), 5)
        done, _ = await asyncio.wait({revoke_task}, timeout=0.2)
        assert not done, "revocation escaped the replay transaction's authority lock"
        release.set()
        assert await asyncio.wait_for(replay_task, 5) == first
        await asyncio.wait_for(revoke_task, 5)
        with pytest.raises(AuthorizationDenied):
            await replay()
    finally:
        release.set()
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
