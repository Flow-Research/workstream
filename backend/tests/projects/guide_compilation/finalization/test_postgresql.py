"""Real finalization persistence, atomic rollback, replay, and resource isolation."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.authorization.api import AuthorizationDenied, setup_finalization_facts_digest
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from app.modules.projects.guide_compilation.models import ProjectGuideComponentProjectionOperation
from .pg_generations import second_generation
from .pg_prerequisites import compilation_and_projections
from .pg_support import DatabaseAuthorization, database_case, finalize, stored_state


@pytest.mark.parametrize(
    "classification", ["guide_blocked", "draft_ready", "draft_ready_with_warnings"]
)
async def test_finalization_changes_only_allowed_setup_columns(
    clean_postgres_database, classification
):
    async with database_case(clean_postgres_database, classification=classification) as (
        values,
        factory,
        command,
    ):
        before, _, _ = await stored_state(factory, command)
        result = await finalize(factory, values, command)
        after, receipt, count = await stored_state(factory, command)
        changed = {key for key in before if before[key] != after[key]}
        expected = {"status", "current_step", "output_sufficiency_report_id", "finished_at"}
        if classification != "guide_blocked":
            expected.add("output_submission_artifact_policy_id")
        assert changed == expected
        assert after["updated_at"] == before["updated_at"]
        assert result.result_classification == classification
        assert receipt["id"] == result.finalization_id
        assert count == 1


async def test_exact_replay_returns_stored_receipt_without_new_evidence(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        first = await finalize(factory, values, command)
        before = await stored_state(factory, command)
        events = []
        second = await finalize(factory, values, command, events=events)
        assert first == second
        assert await stored_state(factory, command) == before
        assert events == ["prepare", "replay", "close"]


async def test_receipt_created_at_equals_setup_finished_at(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        await finalize(factory, values, command)
        setup, receipt, _ = await stored_state(factory, command)
        assert setup["finished_at"] == receipt["created_at"]
        assert receipt["created_at"] is not None


async def test_late_database_failure_rolls_back_finalization_setup_and_authorization(
    clean_postgres_database,
):
    async with database_case(clean_postgres_database) as (values, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                authority = DatabaseAuthorization(session, values)
                await GuideCompilationFinalizationService(session, authority).finalize(command)
                await session.execute(text("select 1/0"))
        assert await stored_state(factory, command) == before
        assert authority.events == ["prepare", "consume", "close"]


async def test_closed_authority_is_unusable_after_late_rollback(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session:
            async with session.begin():
                authority = DatabaseAuthorization(session, values)
                await GuideCompilationFinalizationService(session, authority).finalize(command)
                await session.rollback()
            async with session.begin():
                with pytest.raises(AuthorizationDenied, match="invalid prepared binding"):
                    await authority.handles[0].consume_new(authority.last_facts)
        assert (await stored_state(factory, command))[1:] == (None, 0)


async def test_finalization_never_commits_caller_transaction(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session:
            async with session.begin():
                await GuideCompilationFinalizationService(
                    session, DatabaseAuthorization(session, values)
                ).finalize(command)
                # Another independent connection cannot see uncommitted receipt or evidence.
                assert (await stored_state(factory, command))[1:] == (None, 0)
                await session.rollback()
        assert (await stored_state(factory, command))[1:] == (None, 0)


@pytest.mark.parametrize("foreign_project", [True, False], ids=["foreign-project", "foreign-guide"])
async def test_cross_project_finalization_is_concealed(clean_postgres_database, foreign_project):
    async with database_case(clean_postgres_database) as (values, factory, command):
        project, guide = uuid4(), uuid4()
        async with factory() as session, session.begin():
            await session.execute(text("alter table projects disable trigger user"))
            await session.execute(
                text(
                    "insert into projects(id,name,slug,status) values(:id,'Foreign',:slug,'draft')"
                ),
                {"id": str(project), "slug": str(project)},
            )
            await session.execute(text("alter table projects enable trigger user"))
            await session.execute(text("alter table project_guides disable trigger user"))
            await session.execute(
                text(
                    "insert into project_guides(id,project_id,version,status,retained_content_markdown,created_by) "
                    "values(:id,:project,'foreign-v1','draft','Foreign guide','test')"
                ),
                {
                    "id": str(guide),
                    "project": str(project if foreign_project else command.project_id),
                },
            )
            await session.execute(text("alter table project_guides enable trigger user"))
        forged = command.model_copy(
            update={
                "project_id": project if foreign_project else command.project_id,
                "guide_id": guide,
            }
        )
        before = await stored_state(factory, command)
        with pytest.raises(ProjectGuideSetupFinalizationError, match="^source_state_unavailable$"):
            await finalize(factory, values, forged)
        assert await stored_state(factory, command) == before


async def test_finalization_digest_matches_postgresql(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session, session.begin():
            authority = DatabaseAuthorization(session, values)
            await GuideCompilationFinalizationService(session, authority).finalize(command)
            digest = await session.scalar(
                text(
                    "select project_guide_finalization_digest(r) from project_guide_setup_finalizations r"
                )
            )
            assert digest == setup_finalization_facts_digest(authority.last_facts)


async def test_finalization_audit_resource_vocabulary_matches_database(clean_postgres_database):
    from app.modules.audit.schemas import _RESOURCE_TYPES
    from app.modules.authorization.domain.audit import CONTEXT_DIGEST_RESOURCE_TYPES

    resource = "project_guide_setup_finalization"
    assert resource in _RESOURCE_TYPES and resource in CONTEXT_DIGEST_RESOURCE_TYPES
    async with database_case(clean_postgres_database) as (_, factory, _):
        async with factory() as session:
            definition = await session.scalar(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='audit_events'::regclass and conname='ck_audit_events_authority_privacy_bounds'"
                )
            )
        assert resource in definition


@pytest.mark.parametrize("owner", ["guide", "policy"])
async def test_preloaded_product_rows_are_refreshed_before_authority_consumption(
    clean_postgres_database, owner
):
    from sqlalchemy import select
    from app.modules.projects.models import ProjectGuide, SubmissionArtifactPolicy

    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session, session.begin():
            model = ProjectGuide if owner == "guide" else SubmissionArtifactPolicy
            cached = await session.scalar(select(model))
            table = model.__tablename__
            field = "status" if owner == "guide" else "lifecycle_status"
            target = "stale-cache-probe" if owner == "guide" else "superseded"
            original_value = getattr(cached, field)
            assert original_value != target
            # Deliberately inject an unsupported guide status without changing foreign
            # keys. This rolled-back refresh probe is not a valid lifecycle transition.
            await session.execute(text(f"alter table {table} disable trigger user"))
            await session.execute(
                text(f"update {table} set {field}=:value where id=:id"),
                {"value": target, "id": cached.id},
            )
            await session.execute(text(f"alter table {table} enable trigger user"))
            assert getattr(cached, field) == original_value
            authority = DatabaseAuthorization(session, values)
            with pytest.raises(
                ProjectGuideSetupFinalizationError, match="source_state_unavailable"
            ):
                await GuideCompilationFinalizationService(session, authority).finalize(command)
            assert authority.events == ["prepare", "close"]
            await session.rollback()


@pytest.mark.parametrize("component", ["guide_sufficiency", "submission_artifact_policy"])
async def test_mixed_generation_projection_set_denies_finalization_without_consumption(
    clean_postgres_database, component, monkeypatch
):
    async with database_case(clean_postgres_database) as (values, factory, first):
        next_context = await second_generation(factory, values)
        next_values = values | {key: uuid4() for key in ("operation", "request", "key")}
        current = await compilation_and_projections(
            clean_postgres_database,
            factory,
            next_values,
            compilation_context=next_context,
            predecessor_id=first.compilation_id,
        )
        before = await stored_state(factory, current)
        async with factory() as session, session.begin():
            old_operation = await session.scalar(
                select(ProjectGuideComponentProjectionOperation).where(
                    ProjectGuideComponentProjectionOperation.setup_run_id
                    == str(first.setup_run_id),
                    ProjectGuideComponentProjectionOperation.component == component,
                )
            )
            assert old_operation.setup_generation == 1
            authority = DatabaseAuthorization(session, values)
            service = GuideCompilationFinalizationService(session, authority)
            original = service._repository.lock_finalization

            async def mixed_view(command, attempt_id):
                view = await original(command, attempt_id)
                assert view.compilation_is_current and view.setup.setup_generation == 2
                assert all(op.setup_generation == 2 for op in view.operations)
                return replace(
                    view,
                    operations=tuple(
                        old_operation if op.component == component else op for op in view.operations
                    ),
                )

            monkeypatch.setattr(service._repository, "lock_finalization", mixed_view)
            with pytest.raises(
                ProjectGuideSetupFinalizationError, match="^source_state_unavailable$"
            ):
                await service.finalize(current)
            assert authority.events == ["prepare", "close"]
        assert await stored_state(factory, current) == before
        # A control using the same stored generation succeeds without the injected view defect.
        await finalize(factory, values, current)


async def test_database_replay_denial_closes_without_new_effect(
    clean_postgres_database, monkeypatch
):
    from .pg_support import DatabasePrepared

    async with database_case(clean_postgres_database) as (values, factory, command):
        await finalize(factory, values, command)
        before = await stored_state(factory, command)
        events = []

        async def deny_replay(handle, facts, stored_decision_id):
            handle.require_open()
            handle.port.events.append("replay")
            raise AuthorizationDenied("test port rejects replay")

        monkeypatch.setattr(DatabasePrepared, "validate_replay", deny_replay)
        with pytest.raises(ProjectGuideSetupFinalizationError, match="^service_authority_denied$"):
            await finalize(factory, values, command, events=events)
        assert events == ["prepare", "replay", "close"]
        assert await stored_state(factory, command) == before
