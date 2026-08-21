"""PostgreSQL digest parity and insert-only request custody proof."""

from __future__ import annotations

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
            row = (
                await connection.execute(
                    text(
                        "select project_guide_compilation_request_facts_digest(o,a),"
                        "project_guide_compilation_request_authority_digest(o,g) "
                        "from project_guide_compilation_request_operations o "
                        "join project_guide_compilation_attempts a on a.id=o.attempt_id "
                        "join audit_events e on e.id=o.authorization_decision_event_id "
                        "join admin_role_grants g on g.id=e.matched_grant_id::uuid"
                    )
                )
            ).one()
            await connection.rollback()
        assert row == (expected_facts, expected_authority)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "statement",
    (
        "update project_guide_compilation_request_operations set setup_generation=2",
        "delete from project_guide_compilation_request_operations",
        "truncate table project_guide_compilation_request_operations",
    ),
)
@pytest.mark.asyncio
async def test_request_operation_rejects_every_change(
    clean_postgres_database: str, statement: str
) -> None:
    await _create_request(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError, match="request custody is immutable"):
                await connection.execute(text(statement))
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
