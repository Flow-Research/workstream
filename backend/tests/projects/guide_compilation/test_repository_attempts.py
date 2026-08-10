"""PostgreSQL attempt reservation and terminal-state behavior."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.projects.guide_compilation.repository import (
    GuideCompilationIntegrityError,
    GuideCompilationRepository,
)

from .helpers import context, identity, seed_database


@pytest.mark.asyncio
async def test_concurrent_reservation_converges_on_one_key(
    clean_postgres_database: str,
) -> None:
    """Concurrent exact claims converge on one durable provider key."""
    values = await seed_database(clean_postgres_database)
    attempt_identity = identity(context(values))
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async def reserve():
            async with factory() as session, session.begin():
                return await GuideCompilationRepository(session).reserve_attempt(
                    attempt_identity
                )

        first, second = await asyncio.gather(reserve(), reserve())
        assert {first[0], second[0]} == {"claimed", "existing"}
        assert first[1].id == second[1].id
        assert first[1].provider_idempotency_key == attempt_identity.provider_idempotency_key()

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reservation_identity_mismatch_reuses_no_key(
    clean_postgres_database: str,
) -> None:
    """Identity drift cannot allocate a second provider key for the generation."""
    values = await seed_database(clean_postgres_database)
    attempt_identity = identity(context(values))
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            _, original = await GuideCompilationRepository(session).reserve_attempt(
                attempt_identity
            )
        changed = attempt_identity.model_copy(update={"instruction_version": "v2"})
        async with factory() as session, session.begin():
            outcome, preserved = await GuideCompilationRepository(session).reserve_attempt(
                changed
            )
        assert outcome == "mismatch"
        assert preserved.id == original.id
        assert preserved.provider_idempotency_key == original.provider_idempotency_key
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_uncertain_to_invalid_terminal_preserves_one_attempt(
    clean_postgres_database: str,
) -> None:
    """Uncertain execution can terminate but can never allocate a retry key."""
    values = await seed_database(clean_postgres_database)
    attempt_identity = identity(context(values))
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            _, attempt = await GuideCompilationRepository(session).reserve_attempt(
                attempt_identity
            )
            key = attempt.provider_idempotency_key
        async with factory() as session, session.begin():
            uncertain = await GuideCompilationRepository(session).mark_provider_uncertain(
                attempt.id
            )
            assert uncertain.provider_idempotency_key == key
        async with factory() as session, session.begin():
            terminal = await GuideCompilationRepository(session).mark_invalid_terminal(
                attempt_id=attempt.id, failure_code="schema_invalid"
            )
            assert terminal.status == "compilation_invalid_terminal"
        async with factory() as session, session.begin():
            with pytest.raises(GuideCompilationIntegrityError):
                await GuideCompilationRepository(session).mark_provider_uncertain(attempt.id)
    finally:
        await engine.dispose()
