"""PostgreSQL accepted-result recovery and append-only behavior."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.projects.guide_compilation.repository import (
    GuideCompilationIntegrityError,
    GuideCompilationRepository,
)

from .helpers import (
    context,
    identity,
    insert_authorization_evidence,
    persistence_facts,
    result,
    seed_database,
    service_actor,
)


async def _accepted_attempt(factory, values, *, generation: int = 1):
    compilation_context = context(values, generation=generation)
    attempt_identity = identity(compilation_context)
    async with factory() as session, session.begin():
        repository = GuideCompilationRepository(session)
        _, attempt = await repository.reserve_attempt(attempt_identity)
        await repository.accept_result(
            attempt_id=attempt.id, context=compilation_context, result=result()
        )
    return attempt, attempt_identity, compilation_context


async def _persisted_root(factory, database_url: str, values):
    attempt, attempt_identity, compilation_context = await _accepted_attempt(factory, values)
    facts = persistence_facts(values, attempt.id, attempt_identity)
    decision_id = await insert_authorization_evidence(
        database_url,
        values,
        attempt.id,
        resource_context_digest=facts.resource_context_digest,
    )
    async with factory() as session, session.begin():
        return await GuideCompilationRepository(session).persist_accepted(
            attempt_id=attempt.id,
            context=compilation_context,
            expected_predecessor_id=None,
            actor=service_actor(values),
            facts=facts,
            authorization_decision_event_id=decision_id,
        )


@pytest.mark.asyncio
async def test_accepted_crash_recovery_persists_exactly_once(
    clean_postgres_database: str,
) -> None:
    """Accepted custody survives a transaction boundary and replay converges."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        attempt, attempt_identity, compilation_context = await _accepted_attempt(
            factory, values
        )
        facts = persistence_facts(values, attempt.id, attempt_identity)
        decision_id = await insert_authorization_evidence(
            clean_postgres_database,
            values,
            attempt.id,
            resource_context_digest=facts.resource_context_digest,
        )
        async with factory() as session, session.begin():
            first = await GuideCompilationRepository(session).persist_accepted(
                attempt_id=attempt.id,
                context=compilation_context,
                expected_predecessor_id=None,
                actor=service_actor(values),
                facts=facts,
                authorization_decision_event_id=decision_id,
            )
        async with factory() as session, session.begin():
            replay = await GuideCompilationRepository(session).persist_accepted(
                attempt_id=attempt.id,
                context=compilation_context,
                expected_predecessor_id=None,
                actor=service_actor(values),
                facts=facts,
                authorization_decision_event_id=decision_id,
            )
        assert replay.id == first.id
        assert replay.attempt_id == attempt.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_recovery_persists_one_compilation(
    clean_postgres_database: str,
) -> None:
    """Two recovery workers converge on one immutable business effect."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        attempt, attempt_identity, compilation_context = await _accepted_attempt(
            factory, values
        )
        facts = persistence_facts(values, attempt.id, attempt_identity)
        decision_id = await insert_authorization_evidence(
            clean_postgres_database,
            values,
            attempt.id,
            resource_context_digest=facts.resource_context_digest,
        )

        async def persist():
            async with factory() as session, session.begin():
                return await GuideCompilationRepository(session).persist_accepted(
                    attempt_id=attempt.id,
                    context=compilation_context,
                    expected_predecessor_id=None,
                    actor=service_actor(values),
                    facts=facts,
                    authorization_decision_event_id=decision_id,
                )

        first, second = await asyncio.gather(persist(), persist())
        assert first.id == second.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_wrong_resource_authority_leaves_accepted_attempt_unpersisted(
    clean_postgres_database: str,
) -> None:
    """A mismatched prepared fact cannot cross the durable boundary."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        attempt, attempt_identity, compilation_context = await _accepted_attempt(
            factory, values
        )
        facts = replace(
            persistence_facts(values, attempt.id, attempt_identity),
            guide_material_hash="sha256:" + "b" * 64,
        )
        decision_id = await insert_authorization_evidence(
            clean_postgres_database,
            values,
            attempt.id,
            resource_context_digest=facts.resource_context_digest,
        )
        async with factory() as session, session.begin():
            with pytest.raises(
                GuideCompilationIntegrityError,
                match="accepted compilation custody is invalid",
            ):
                await GuideCompilationRepository(session).persist_accepted(
                    attempt_id=attempt.id,
                    context=compilation_context,
                    expected_predecessor_id=None,
                    actor=service_actor(values),
                    facts=facts,
                    authorization_decision_event_id=decision_id,
                )
        async with factory() as session:
            classification = await GuideCompilationRepository(
                session
            ).recovery_classification(attempt.id)
            assert classification == "accepted_not_persisted"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unrelated_authority_event_cannot_create_compilation(
    clean_postgres_database: str,
) -> None:
    """PostgreSQL rejects a valid audit event borrowed from another action."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        attempt, attempt_identity, compilation_context = await _accepted_attempt(
            factory, values
        )
        facts = persistence_facts(values, attempt.id, attempt_identity)
        decision_id = await insert_authorization_evidence(
            clean_postgres_database,
            values,
            attempt.id,
            action_id="project.guide_sufficiency.run",
            permission_id="project.guide.manage",
            resource_context_digest=facts.resource_context_digest,
        )
        async with factory() as session, session.begin():
            with pytest.raises(DBAPIError):
                await GuideCompilationRepository(session).persist_accepted(
                    attempt_id=attempt.id,
                    context=compilation_context,
                    expected_predecessor_id=None,
                    actor=service_actor(values),
                    facts=facts,
                    authorization_decision_event_id=decision_id,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_wrong_authority_digest_cannot_create_compilation(
    clean_postgres_database: str,
) -> None:
    """Same-action evidence for a different final context fails closed."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        attempt, attempt_identity, compilation_context = await _accepted_attempt(
            factory, values
        )
        facts = persistence_facts(values, attempt.id, attempt_identity)
        decision_id = await insert_authorization_evidence(
            clean_postgres_database,
            values,
            attempt.id,
            resource_context_digest="sha256:" + "b" * 64,
        )
        async with factory() as session, session.begin():
            with pytest.raises(DBAPIError):
                await GuideCompilationRepository(session).persist_accepted(
                    attempt_id=attempt.id,
                    context=compilation_context,
                    expected_predecessor_id=None,
                    actor=service_actor(values),
                    facts=facts,
                    authorization_decision_event_id=decision_id,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fixed_service_profile_cannot_gain_a_second_wrong_link(
    clean_postgres_database: str,
) -> None:
    """Database identity custody prevents same-profile link substitution."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "insert into actor_identity_links(id,actor_profile_id,issuer,subject,"
                        "subject_kind,status,linked_by) values(:id,:actor,"
                        "'workstream-internal','wrong.service','service','active','test')"
                    ),
                    {"id": str(values["wrong_link"]), "actor": str(values["actor"])},
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compilation_delete_is_rejected(clean_postgres_database: str) -> None:
    """An immutable compilation cannot disappear through row deletion."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        compilation = await _persisted_root(factory, clean_postgres_database, values)
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text("delete from project_guide_compilations where id=:id"),
                    {"id": compilation.id},
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compilation_truncate_is_rejected(clean_postgres_database: str) -> None:
    """Bulk truncation cannot erase immutable compilation custody."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _persisted_root(factory, clean_postgres_database, values)
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(text("truncate table project_guide_compilations"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_child_fork_allows_exactly_one_successor(
    clean_postgres_database: str,
) -> None:
    """Two later generations racing on one predecessor cannot fork the graph."""
    values = await seed_database(clean_postgres_database, generations=3)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        root = await _persisted_root(factory, clean_postgres_database, values)
        candidates = []
        for generation in (2, 3):
            attempt, attempt_identity, compilation_context = await _accepted_attempt(
                factory, values, generation=generation
            )
            facts = persistence_facts(
                values,
                attempt.id,
                attempt_identity,
                predecessor_id=root.id,
            )
            decision_id = await insert_authorization_evidence(
                clean_postgres_database,
                values,
                attempt.id,
                resource_context_digest=facts.resource_context_digest,
            )
            candidates.append((attempt, compilation_context, facts, decision_id))

        async def persist(candidate):
            attempt, compilation_context, facts, decision_id = candidate
            async with factory() as session, session.begin():
                return await GuideCompilationRepository(session).persist_accepted(
                    attempt_id=attempt.id,
                    context=compilation_context,
                    expected_predecessor_id=root.id,
                    actor=service_actor(values),
                    facts=facts,
                    authorization_decision_event_id=decision_id,
                )

        outcomes = await asyncio.gather(
            *(persist(candidate) for candidate in candidates), return_exceptions=True
        )
        successes = [value for value in outcomes if not isinstance(value, Exception)]
        failures = [value for value in outcomes if isinstance(value, Exception)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], (GuideCompilationIntegrityError, DBAPIError))
        assert successes[0].supersedes_compilation_id == root.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_predecessor_fails_closed(
    clean_postgres_database: str,
) -> None:
    """A later generation cannot persist without naming the current predecessor."""
    values = await seed_database(clean_postgres_database, generations=2)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        first_attempt, first_identity, first_context = await _accepted_attempt(factory, values)
        first_facts = persistence_facts(values, first_attempt.id, first_identity)
        first_decision = await insert_authorization_evidence(
            clean_postgres_database,
            values,
            first_attempt.id,
            resource_context_digest=first_facts.resource_context_digest,
        )
        async with factory() as session, session.begin():
            await GuideCompilationRepository(session).persist_accepted(
                attempt_id=first_attempt.id,
                context=first_context,
                expected_predecessor_id=None,
                actor=service_actor(values),
                facts=first_facts,
                authorization_decision_event_id=first_decision,
            )
        second_attempt, second_identity, second_context = await _accepted_attempt(
            factory, values, generation=2
        )
        second_facts = persistence_facts(values, second_attempt.id, second_identity)
        second_decision = await insert_authorization_evidence(
            clean_postgres_database,
            values,
            second_attempt.id,
            resource_context_digest=second_facts.resource_context_digest,
        )
        async with factory() as session, session.begin():
            with pytest.raises(GuideCompilationIntegrityError, match="predecessor is stale"):
                await GuideCompilationRepository(session).persist_accepted(
                    attempt_id=second_attempt.id,
                    context=second_context,
                    expected_predecessor_id=None,
                    actor=service_actor(values),
                    facts=second_facts,
                    authorization_decision_event_id=second_decision,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compilation_update_is_rejected(clean_postgres_database: str) -> None:
    """An immutable compilation cannot be edited after insertion."""
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        compilation = await _persisted_root(factory, clean_postgres_database, values)
        async with factory() as session:
            with pytest.raises(DBAPIError):
                await session.execute(
                    text(
                        "update project_guide_compilations set agent_version='v2' where id=:id"
                    ),
                    {"id": compilation.id},
                )
    finally:
        await engine.dispose()
