"""PostgreSQL digest parity and insert-only request custody proof."""

from __future__ import annotations

from dataclasses import replace
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    project_guide_compilation_facts_digest,
    project_guide_compilation_request_authority_digest,
)
from app.modules.projects.guide_compilation.repository import (
    GuideCompilationConcurrencyError,
    GuideCompilationIntegrityError,
    GuideCompilationRepository,
    GuideCompilationStorageError,
)

from .helpers import context, identity, seed_database
from .test_authorized_request_service import _authorized_service, _request, _seed_human


async def _create_request(database_url: str) -> tuple[dict[str, UUID], UUID, UUID, UUID]:
    values = await seed_database(database_url)
    human, link, grant = await _seed_human(database_url, values)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
    finally:
        await engine.dispose()
    return values, human, link, grant


@pytest.mark.asyncio
async def test_sql_and_python_request_digests_are_byte_identical(
    clean_postgres_database: str,
) -> None:
    values, human, link, grant = await _create_request(clean_postgres_database)
    facts = _request(values)
    expected_facts = project_guide_compilation_facts_digest(facts)
    expected_authority = project_guide_compilation_request_authority_digest(
        actor_profile_id=human,
        identity_link_id=link,
        grant_id=grant,
        project_id=values["project"],
        operation_id=values["operation"],
        request_facts_digest=expected_facts,
    )
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.connect() as connection:
            row = (await connection.execute(text(_DIGEST_QUERY))).one()
            base_facts, base_authority = row
            assert row == (expected_facts, expected_authority)

            operation_fields = {
                "expected_predecessor_compilation_id",
                "guide_id",
                "idempotency_key",
                "operation_id",
                "project_id",
                "request_id",
                "setup_generation",
                "setup_run_id",
                "source_snapshot_id",
            }
            for field_name in facts.__dataclass_fields__:
                original = getattr(facts, field_name)
                mutated = _different_value(field_name, original)
                sql_digest = await connection.scalar(
                    text(_MUTATED_FACTS_DIGEST_QUERY),
                    {
                        "operation_patch": json.dumps(
                            {field_name: _json_value(mutated)}
                            if field_name in operation_fields
                            else {}
                        ),
                        "attempt_patch": json.dumps(
                            {field_name: _json_value(mutated)}
                            if field_name not in operation_fields
                            else {}
                        ),
                    },
                )
                python_digest = project_guide_compilation_facts_digest(
                    replace(facts, **{field_name: mutated})
                )
                assert sql_digest == python_digest
                assert sql_digest != base_facts

            authority_values = {
                "actor_profile_id": human,
                "identity_link_id": link,
                "grant_id": grant,
                "project_id": values["project"],
                "operation_id": values["operation"],
                "request_facts_digest": expected_facts,
            }
            operation_authority_fields = {
                "actor_profile_id",
                "identity_link_id",
                "project_id",
                "operation_id",
                "request_facts_digest",
            }
            for field_name, original in authority_values.items():
                mutated = _different_value(field_name, original)
                sql_digest = await connection.scalar(
                    text(_MUTATED_AUTHORITY_DIGEST_QUERY),
                    {
                        "operation_patch": json.dumps(
                            {field_name: _json_value(mutated)}
                            if field_name in operation_authority_fields
                            else {}
                        ),
                        "grant_patch": json.dumps(
                            {"id": str(mutated)} if field_name == "grant_id" else {}
                        ),
                    },
                )
                changed = authority_values | {field_name: mutated}
                python_digest = project_guide_compilation_request_authority_digest(
                    **changed
                )
                assert sql_digest == python_digest
                assert sql_digest != base_authority
            await connection.rollback()
    finally:
        await engine.dispose()


_DIGEST_QUERY = (
    "select project_guide_compilation_request_facts_digest(o,a),"
    "project_guide_compilation_request_authority_digest(o,g) "
    "from project_guide_compilation_request_operations o "
    "join project_guide_compilation_attempts a on a.id=o.attempt_id "
    "join audit_events e on e.id=o.authorization_decision_event_id "
    "join admin_role_grants g on g.id=e.matched_grant_id::uuid"
)
_MUTATED_FACTS_DIGEST_QUERY = (
    "select project_guide_compilation_request_facts_digest("
    "jsonb_populate_record(o,cast(:operation_patch as jsonb)),"
    "jsonb_populate_record(a,cast(:attempt_patch as jsonb))) "
    "from project_guide_compilation_request_operations o "
    "join project_guide_compilation_attempts a on a.id=o.attempt_id"
)
_MUTATED_AUTHORITY_DIGEST_QUERY = (
    "select project_guide_compilation_request_authority_digest("
    "jsonb_populate_record(o,cast(:operation_patch as jsonb)),"
    "jsonb_populate_record(g,cast(:grant_patch as jsonb))) "
    "from project_guide_compilation_request_operations o "
    "join audit_events e on e.id=o.authorization_decision_event_id "
    "join admin_role_grants g on g.id=e.matched_grant_id::uuid"
)


def _json_value(value: object) -> object:
    return str(value) if isinstance(value, UUID) else value


def _different_value(field_name: str, value: object) -> object:
    if field_name == "expected_predecessor_compilation_id" or isinstance(value, UUID):
        return uuid4()
    if field_name == "setup_generation":
        return 2
    if field_name.endswith(("_hash", "_digest")):
        return "sha256:" + "b" * 64
    return "mutated.v2"


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("facts", "request facts digest is invalid"),
        ("authority", "request authority digest is invalid"),
    ),
)
@pytest.mark.asyncio
async def test_request_insert_guard_rejects_stale_digest_evidence(
    clean_postgres_database: str, mutation: str, message: str
) -> None:
    await _create_request(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(
                text(
                    "create temporary table request_candidate on commit drop as "
                    "select * from project_guide_compilation_request_operations"
                )
            )
            await connection.execute(
                text(
                    "alter table project_guide_compilation_request_operations disable trigger "
                    "guide_compilation_request_change_guard"
                )
            )
            await connection.execute(
                text("delete from project_guide_compilation_request_operations")
            )
            await connection.execute(
                text(
                    "alter table project_guide_compilation_request_operations enable trigger "
                    "guide_compilation_request_change_guard"
                )
            )
            if mutation == "authority":
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger "
                        "audit_events_reject_update_delete"
                    )
                )
                await connection.execute(
                    text(
                        "update audit_events set after_facts=jsonb_set(after_facts::jsonb,"
                        "'{resource_context_digest}',to_jsonb(cast(:digest as text)))::json "
                        "where id=(select authorization_decision_event_id "
                        "from request_candidate)"
                    ),
                    {"digest": "sha256:" + "b" * 64},
                )
                await connection.execute(
                    text(
                        "alter table audit_events enable trigger "
                        "audit_events_reject_update_delete"
                    )
                )
            nested = await connection.begin_nested()
            with pytest.raises(DBAPIError, match=message):
                await connection.execute(
                    text(
                        "insert into project_guide_compilation_request_operations "
                        "select operation_id,request_id,idempotency_key,actor_profile_id,"
                        "identity_link_id,project_id,guide_id,source_snapshot_id,setup_run_id,"
                        "setup_generation,expected_predecessor_compilation_id,"
                        "case when :mutation='facts' then :digest else request_facts_digest end,"
                        "attempt_id,authorization_decision_event_id,created_at "
                        "from request_candidate"
                    ),
                    {"mutation": mutation, "digest": "sha256:" + "b" * 64},
                )
            await nested.rollback()
            await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("statement", "expected_error"),
    (
        (
            "update project_guide_compilation_request_operations set setup_generation=2",
            "request custody is immutable",
        ),
        (
            "delete from project_guide_compilation_request_operations",
            "request custody is immutable",
        ),
        (
            "truncate table project_guide_compilation_request_operations",
            "referenced in a foreign key constraint",
        ),
    ),
)
@pytest.mark.asyncio
async def test_request_operation_rejects_every_change(
    clean_postgres_database: str, statement: str, expected_error: str
) -> None:
    """Every mutation is rejected and leaves the request receipt intact."""
    await _create_request(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError) as error:
                await connection.execute(text(statement))
            message = str(error.value)
            assert expected_error in message
            if statement.startswith("truncate"):
                assert getattr(error.value.orig, "sqlstate", None) == "0A000"
                assert "project_guide_component_projection_operations" in message
                assert "project_guide_compilation_request_operations" in message
        async with engine.connect() as connection:
            count = await connection.scalar(
                text("select count(*) from project_guide_compilation_request_operations")
            )
        assert count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_required_repository_reads_fail_closed_without_durable_rows(
    clean_postgres_database: str,
) -> None:
    await seed_database(clean_postgres_database)
    missing = uuid4()
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            repository = GuideCompilationRepository(session)
            with pytest.raises(GuideCompilationIntegrityError, match="custody is missing"):
                await repository.request_operation_for_attempt(missing, lock=False)
            with pytest.raises(GuideCompilationIntegrityError, match="was not found"):
                await repository.attempt(missing, lock=True)
            with pytest.raises(GuideCompilationIntegrityError, match="disappeared"):
                await repository.attempt(missing, lock=False)
            with pytest.raises(GuideCompilationIntegrityError, match="is missing"):
                await repository.persisted_compilation(missing)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repository_read_views_return_exact_request_and_empty_lineage(
    clean_postgres_database: str,
) -> None:
    values, human, link, _grant = await _create_request(clean_postgres_database)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    facts = _request(values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            repository = GuideCompilationRepository(session)
            operation = await repository.matching_request_operation(
                actor=actor, facts=facts, lock=False
            )
            assert operation is not None
            assert (
                await repository.request_operation_for_attempt(
                    operation.attempt_id, lock=False
                )
                == operation
            )
            assert (
                await repository.current_compilation(
                    values["project"], values["guide"], lock=False
                )
                is None
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_request_failure_rolls_back_attempt_and_authority_event(
    clean_postgres_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure after AUTH consumption leaves no partial request custody."""
    values = await seed_database(clean_postgres_database)
    human, link, _grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)

    async def fail_request_insert(*_args: object, **_kwargs: object) -> None:
        raise GuideCompilationStorageError("injected request custody failure")

    monkeypatch.setattr(
        GuideCompilationRepository,
        "insert_request_operation",
        fail_request_insert,
    )
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            with pytest.raises(GuideCompilationStorageError, match="injected"):
                await _authorized_service(session, actor).authorize_request(
                    actor=actor,
                    facts=_request(values),
                    identity=identity(context(values)),
                )
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from "
                        "project_guide_compilation_attempts),"
                        "(select count(*) from "
                        "project_guide_compilation_request_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.request')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (0, 0, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_request_insert_is_classified_as_concurrent_replay(
    clean_postgres_database: str,
) -> None:
    values, human, link, _grant = await _create_request(clean_postgres_database)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    facts = _request(values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            with pytest.raises(GuideCompilationConcurrencyError, match="request won"):
                async with session.begin():
                    repository = GuideCompilationRepository(session)
                    attempt_id, event_id = (
                        await session.execute(
                            text(
                                "select attempt_id,authorization_decision_event_id "
                                "from project_guide_compilation_request_operations"
                            )
                        )
                    ).one()
                    attempt = await repository.attempt(attempt_id, lock=True)
                    await repository.insert_request_operation(
                        actor=actor,
                        facts=facts,
                        attempt=attempt,
                        authorization_decision_event_id=UUID(event_id),
                    )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_request_custody_failure_is_not_reported_as_replay(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, link, _grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    facts = _request(values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            with pytest.raises(GuideCompilationStorageError, match="before commit"):
                async with session.begin():
                    repository = GuideCompilationRepository(session)
                    _outcome, attempt = await repository.reserve_attempt(
                        identity(context(values))
                    )
                    await repository.insert_request_operation(
                        actor=actor,
                        facts=facts,
                        attempt=attempt,
                        authorization_decision_event_id=uuid4(),
                    )
    finally:
        await engine.dispose()
