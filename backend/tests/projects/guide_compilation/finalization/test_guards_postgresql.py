"""Direct SQL probes distinguish database custody from service-side validation."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.projects.guide_compilation.finalization_payloads import (
    compose_facts,
    new_row,
    require_source_shape,
)
from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
from ..helpers import seed_database
from app.modules.projects.guide_compilation.models import ProjectGuideComponentProjectionOperation
from .pg_forgery import rebind_forged_evidence
from .pg_generations import second_generation
from .pg_prerequisites import compilation_and_projections
from .pg_support import DatabaseAuthorization, database_case, finalize, stored_state


async def pending_receipt(session, values, command):
    """Produce valid authority/receipt inputs without running finalization persistence."""
    from app.modules.authorization.api import (
        ProjectSetupFinalizationLocator,
        setup_finalization_identity,
    )

    repo = GuideCompilationRepository(session)
    attempt = await repo.finalization_attempt_id(command)
    view = await repo.lock_finalization(command, attempt)
    facts = compose_facts(view, require_source_shape(view))
    authority = DatabaseAuthorization(session, values)
    _, operation, correlation = setup_finalization_identity(
        command.setup_run_id, command.setup_generation, command.compilation_id
    )
    async with authority.prepare_setup_finalization(
        ProjectSetupFinalizationLocator(project_id=command.project_id, operation_id=operation, correlation_id=correlation)
    ) as handle:
        receipt = await handle.consume_new(facts)
    return new_row(facts, receipt), view.setup


async def sql_transition(session, command, row, *, extra="", changes=None):
    """Execute the complete transition with independently selectable malformed fields."""
    values = dict(
        status=row.setup_outcome,
        current_step="guide_sufficiency"
        if row.setup_outcome == "sufficiency_blocked"
        else "submission_artifact_policy_derivation",
        output_sufficiency_report_id=row.sufficiency_report_id,
        output_submission_artifact_policy_id=row.artifact_policy_id,
        finished_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    values.update(changes or {})
    assignments = ",".join(f"{column}=:{column}" for column in values)
    await session.execute(
        text("update project_setup_runs set " + assignments + extra + " where id=:id"),
        {**values, "id": str(command.setup_run_id)},
    )


async def assert_deferred_missing_receipt(session, command, row):
    """Reach deferred custody with a complete transition and omit only its receipt."""
    await sql_transition(session, command, row)
    stored = (
        await session.execute(
            text(
                "select status,output_sufficiency_report_id,output_submission_artifact_policy_id,"
                "finished_at from project_setup_runs where id=:id"
            ),
            {"id": str(command.setup_run_id)},
        )
    ).one()
    assert tuple(stored[:3]) == (
        row.setup_outcome, row.sufficiency_report_id, row.artifact_policy_id
    )
    assert stored.finished_at == await session.scalar(text("select transaction_timestamp()"))
    assert not await session.scalar(
        text("select exists(select 1 from project_guide_setup_finalizations where setup_run_id=:id)"),
        {"id": str(command.setup_run_id)},
    )
    # The UPDATE and its immediate guards have already succeeded. Only this
    # deferred assertion is shared with the guard-removal mutation probe.
    with pytest.raises(DBAPIError, match="setup finalization receipt missing"):
        await session.execute(text("set constraints finalization_atomic_custody immediate"))


@pytest.mark.parametrize("classification", ["guide_blocked", "draft_ready", "draft_ready_with_warnings"])
async def test_direct_setup_finalization_without_receipt_is_rejected(
    clean_postgres_database, classification
):
    async with database_case(clean_postgres_database, classification=classification) as (
        values, factory, command
    ):
        before = await stored_state(factory, command)
        async with factory() as session, session.begin():
            try:
                row, _ = await pending_receipt(session, values, command)
                await assert_deferred_missing_receipt(session, command, row)
            finally:
                await session.rollback()
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize("classification", ["guide_blocked", "draft_ready", "draft_ready_with_warnings"])
async def test_missing_receipt_proof_detects_removed_guard(clean_postgres_database, classification):
    async with database_case(clean_postgres_database, classification=classification) as (
        values, factory, command
    ):
        before = await stored_state(factory, command)
        async with factory() as session, session.begin():
            try:
                await session.execute(
                    text("alter table project_setup_runs disable trigger finalization_atomic_custody")
                )
                row, _ = await pending_receipt(session, values, command)
                # Run the exact same proof against the mutant: it must fail to
                # observe the deferred error, rather than pass on an earlier guard.
                with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                    await assert_deferred_missing_receipt(session, command, row)
            finally:
                # Restore both trigger DDL and the intentionally invalid product write.
                await session.rollback()
        assert await stored_state(factory, command) == before
        async with factory() as session:
            assert await session.scalar(
                text(
                    "select tgenabled::text from pg_trigger where tgrelid='project_setup_runs'::regclass "
                    "and tgname='finalization_atomic_custody'"
                )
            ) == "O"


async def test_compilation_without_outputs_cannot_finalize(clean_postgres_database):
    async with database_case(clean_postgres_database, project=False) as (_, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError, match="invalid finalization setup transition"):
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        "update project_setup_runs set status='sufficiency_blocked',"
                        "current_step='guide_sufficiency',finished_at=transaction_timestamp() where id=:id"
                    ),
                    {"id": str(command.setup_run_id)},
                )
        assert await stored_state(factory, command) == before


async def test_direct_finalization_receipt_without_setup_transition_is_rejected(
    clean_postgres_database,
):
    async with database_case(clean_postgres_database) as (values, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                session.add(row)
                await session.flush()
                # Prove insertion succeeded, so failure belongs to the deferred pair guard.
                assert row.created_at is not None
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize(
    "extra",
    [
        ",updated_at=transaction_timestamp()+interval '1 day'",
        ",created_by='forged'",
        ",error_code='forged'",
    ],
)
async def test_direct_finalization_with_extra_setup_field_mutation_is_rejected(
    clean_postgres_database, extra
):
    async with database_case(clean_postgres_database) as (values, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                session.add(row)
                await session.flush()
                await sql_transition(session, command, row, extra=extra)
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize(
    "field",
    ["output_sufficiency_report_id", "output_submission_artifact_policy_id", "current_step"],
)
async def test_direct_partial_setup_finalization_is_rejected(clean_postgres_database, field):
    async with database_case(clean_postgres_database) as (values, factory, command):
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                session.add(row)
                await session.flush()
                await sql_transition(session, command, row, changes={field: None})


async def test_finalization_created_at_is_postgresql_owned(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session, session.begin():
            row, _ = await pending_receipt(session, values, command)
            row.created_at = datetime(2000, 1, 1, tzinfo=UTC)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            tx = await session.scalar(text("select transaction_timestamp()"))
            assert row.created_at == tx
            await sql_transition(session, command, row)


async def test_finalization_finished_at_is_postgresql_owned(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session, session.begin():
            row, _ = await pending_receipt(session, values, command)
            session.add(row)
            await session.flush()
            await sql_transition(session, command, row)
            actual = await session.scalar(
                text("select finished_at from project_setup_runs where id=:id"),
                {"id": str(command.setup_run_id)},
            )
            assert actual == await session.scalar(text("select transaction_timestamp()"))


@pytest.mark.parametrize(
    "statement",
    [
        "update project_guide_setup_finalizations set setup_outcome=setup_outcome",
        "delete from project_guide_setup_finalizations",
        "truncate project_guide_setup_finalizations",
        "update project_setup_runs set updated_at=updated_at",
        "delete from project_setup_runs",
        "truncate project_setup_runs cascade",
    ],
    ids=[
        "receipt-update",
        "receipt-delete",
        "receipt-truncate",
        "setup-update",
        "setup-delete",
        "setup-truncate",
    ],
)
async def test_finalized_setup_cannot_be_rewritten(clean_postgres_database, statement):
    async with database_case(clean_postgres_database) as (values, factory, command):
        await finalize(factory, values, command)
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                await session.execute(text(statement))
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize(
    "field",
    [
        "compilation_id",
        "sufficiency_operation_id",
        "sufficiency_report_id",
        "artifact_policy_operation_id",
        "artifact_policy_id",
        "actor_profile_id",
        "identity_link_id",
        "source_state_digest",
        "result_hash",
        "facts_digest",
        "authority_resource_digest",
    ],
)
async def test_receipt_compilation_attempt_setup_tuple_must_match(clean_postgres_database, field):
    async with database_case(clean_postgres_database) as (values, factory, command):
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                original = getattr(row, field)
                value = "sha256:" + "f" * 64 if field.endswith(("hash", "digest")) else uuid4()
                if isinstance(original, str) and not field.endswith(("hash", "digest")):
                    value = str(value)
                setattr(row, field, value)
                session.add(row)
                await session.flush()


@pytest.mark.parametrize(
    "field", ["artifact_policy_operation_id", "artifact_policy_id", "artifact_policy_output_digest"]
)
@pytest.mark.parametrize("classification", ["guide_blocked", "draft_ready"])
async def test_nullable_finalization_custody_cannot_bypass_guards(
    clean_postgres_database, classification, field
):
    async with database_case(clean_postgres_database, classification=classification) as (
        values,
        factory,
        command,
    ):
        with pytest.raises(
            DBAPIError,
            match="ck_project_guide_setup_finalizations_ck_finalization_pr_ac00|finalization policy custody mismatch",
        ):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                value = (
                    "sha256:" + "f" * 64
                    if field.endswith("digest")
                    else (str(uuid4()) if field == "artifact_policy_id" else uuid4())
                )
                setattr(row, field, value if classification == "guide_blocked" else None)
                await rebind_forged_evidence(session, row)
                session.add(row)
                await session.flush()


async def test_legacy_setup_transition_needs_no_finalization_receipt(clean_postgres_database):
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "update project_setup_runs set status='sufficiency_blocked',current_step='guide_sufficiency',"
                    "finished_at=transaction_timestamp() where id=:id"
                ),
                {"id": str(values["setup_1"])},
            )
        async with factory() as session:
            assert (
                await session.scalar(
                    text("select status from project_setup_runs where id=:id"),
                    {"id": str(values["setup_1"])},
                )
                == "sufficiency_blocked"
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "field",
    [
        "compilation_id",
        "sufficiency_operation_id",
        "sufficiency_report_id",
        "artifact_policy_operation_id",
        "artifact_policy_id",
    ],
)
async def test_receipt_rejects_existing_foreign_compilation_and_projection_owners(
    clean_postgres_database, field
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
        with pytest.raises(
            DBAPIError,
            match="finalization (compilation|sufficiency|policy|projection) (lineage|custody) mismatch",
        ):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, current)
                operations = (
                    await session.scalars(
                        select(ProjectGuideComponentProjectionOperation).where(
                            ProjectGuideComponentProjectionOperation.setup_run_id
                            == str(first.setup_run_id)
                        )
                    )
                ).all()
                assert len(operations) == 2 and all(op.setup_generation == 1 for op in operations)
                by_component = {op.component: op for op in operations}
                foreign = {
                    "compilation_id": first.compilation_id,
                    "sufficiency_operation_id": by_component["guide_sufficiency"].operation_id,
                    "sufficiency_report_id": by_component["guide_sufficiency"].report_id,
                    "artifact_policy_operation_id": by_component[
                        "submission_artifact_policy"
                    ].operation_id,
                    "artifact_policy_id": by_component["submission_artifact_policy"].policy_id,
                }
                setattr(row, field, foreign[field])
                await rebind_forged_evidence(session, row)
                session.add(row)
                await session.flush()
        assert await stored_state(factory, current) == before
        await finalize(factory, values, current)


async def test_receipt_actor_identity_link_must_belong_to_actor(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        actor, link = str(uuid4()), str(uuid4())
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "insert into actor_profiles(id,actor_kind,status,provisioning_method,created_by) "
                    "values(:actor,'human','active','automatic_first_access','test')"
                ),
                {"actor": actor},
            )
            await session.execute(
                text(
                    "insert into actor_identity_links(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,last_verified_at) "
                    "values(:link,:actor,'https://identity.flowresearch.tech',:actor,'human','active','test',transaction_timestamp())"
                ),
                {"link": link, "actor": actor},
            )
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError, match="finalization authority mismatch"):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                assert (
                    row.actor_profile_id == str(values["actor"]) and row.actor_profile_id != actor
                )
                row.identity_link_id = link
                await rebind_forged_evidence(session, row)
                session.add(row)
                await session.flush()
        assert await stored_state(factory, command) == before
        await finalize(factory, values, command)


@pytest.mark.parametrize("kind", ["actor", "deactivate", "link"])
async def test_sql_finalization_rejects_revocation_after_valid_evidence(clean_postgres_database, kind):
    from .pg_authorization import revoke, seed_lifecycle_admin
    async with database_case(clean_postgres_database) as (values, factory, command):
        admin = await seed_lifecycle_admin(factory)
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError, match="finalization authority mismatch") as error:
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                await revoke(session, admin, values, kind)
                session.add(row)
                await session.flush()
        assert error.value.orig.sqlstate == "23514"
        assert await stored_state(factory, command) == before
        await finalize(factory, values, command)
