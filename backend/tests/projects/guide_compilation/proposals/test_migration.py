"""Forward/reverse schema proof with retained-evidence protection."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from migration_fixtures import run_alembic_revision


async def test_empty_proposal_migration_round_trip(clean_postgres_database):
    engine = create_async_engine(clean_postgres_database)

    async def definitions():
        async with engine.connect() as connection:
            functions = (
                await connection.execute(
                    text(
                        "SELECT proname,pg_get_functiondef(p.oid) FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' "
                        "AND p.prokind='f' ORDER BY proname,p.oid::regprocedure::text"
                    )
                )
            ).all()
            constraints = (
                await connection.execute(
                    text(
                        "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) "
                        "FROM pg_constraint WHERE connamespace='public'::regnamespace "
                        "ORDER BY conrelid::regclass::text,conname"
                    )
                )
            ).all()
            indexes = (await connection.execute(text(
                "SELECT tablename,indexname,indexdef FROM pg_indexes "
                "WHERE schemaname='public' ORDER BY tablename,indexname"
            ))).all()
            return functions, constraints, indexes

    try:
        before = await definitions()
        await run_alembic_revision("downgrade", "0018_guide_document_creation")
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT to_regclass('project_guide_proposal_approvals')")
                )
                is None
            )
            assert (
                await connection.scalar(
                    text("SELECT to_regclass('project_guide_proposal_corrections')")
                )
                is None
            )
        await run_alembic_revision("upgrade", "head")
        assert await definitions() == before
    finally:
        await engine.dispose()


async def test_downgrade_refuses_retained_approval_without_mutation(clean_postgres_database, capfd):
    import pytest
    from uuid import uuid4
    from app.modules.projects.api.guide_proposals import GuideProposalApproval
    from .pg_support import proposal_case, read_package
    from .test_postgresql import approve

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        receipt = await approve(factory, command, actor, grant, payload)
        with pytest.raises(RuntimeError, match="isolated migration subprocess failed"):
            await run_alembic_revision("downgrade", "0018_guide_document_creation")
        assert "retained guide proposal evidence prevents downgrade" in capfd.readouterr().err
        async with factory() as session:
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0019_guide_proposal_review"
        assert await approve(factory, command, actor, grant, payload) == receipt


async def test_review_package_audit_requires_catalogue_manager_permission(clean_postgres_database):
    import json
    from uuid import uuid4
    import pytest
    from sqlalchemy.exc import DBAPIError
    from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
    from app.modules.projects.api.guide_proposals import GuideProposalApproval
    from .pg_support import proposal_case, read_package
    from .test_postgresql import approve

    action = ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ
    permission = ACTION_BY_ID[action].permission_id.value
    assert permission == "project.guide.manage"
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        receipt = await approve(factory, command, actor, grant, GuideProposalApproval(
            target=package.target, idempotency_key=uuid4()))
        async with factory() as session:
            source_event = await session.scalar(text(
                "SELECT authorization_decision_event_id FROM project_guide_proposal_approvals "
                "WHERE operation_id=:id"), {"id": receipt.operation_id})
        for candidate in (permission, "project.setup_diagnostic.read"):
            event_id = str(uuid4())
            patch = dict(id=event_id, entity_id=event_id, permission_id=candidate,
                         action_id=action.value, resource_type="project_guide_compilation_review_package",
                         resource_id=str(command.compilation_id))
            async with factory() as session, session.begin():
                statement = text(
                    "INSERT INTO audit_events SELECT (jsonb_populate_record(NULL::audit_events, "
                    "to_jsonb(source) || CAST(:patch AS jsonb))).* FROM audit_events source WHERE id=:source")
                if candidate == permission:
                    await session.execute(statement, {"patch": json.dumps(patch), "source": source_event})
                    assert await session.scalar(text("SELECT permission_id FROM audit_events WHERE id=:id"),
                                                {"id": event_id}) == permission
                else:
                    with pytest.raises(DBAPIError, match="ck_audit_events_authorization_action_evidence"):
                        async with session.begin_nested():
                            await session.execute(statement, {"patch": json.dumps(patch), "source": source_event})
                    assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE id=:id"),
                                                {"id": event_id}) == 0
