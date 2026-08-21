"""Independent-session concurrency proof for request and final custody."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.authorization.api import ActorIdentityFacts, ActorKind

from .helpers import context, identity, result, seed_database, service_actor
from .test_authorized_execution_service import _execution_service, _preflight
from .test_authorized_request_service import _authorized_service, _request, _seed_human


@pytest.mark.asyncio
async def test_concurrent_identical_requests_commit_one_attempt_event_and_receipt(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, link, _grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    facts, attempt_identity = _request(values), identity(context(values))
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def request_once():
        async with factory() as session:
            return await _authorized_service(session, actor).authorize_request(
                actor=actor, facts=facts, identity=attempt_identity
            )

    try:
        first, second = await asyncio.gather(request_once(), request_once())
        assert first == second
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from project_guide_compilation_attempts),"
                        "(select count(*) from project_guide_compilation_request_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.request')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_finalization_commits_one_compilation_and_event(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, link, _grant = await _seed_human(clean_postgres_database, values)
    human_actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    service = service_actor(values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            requested = await _authorized_service(session, human_actor).authorize_request(
                actor=human_actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
        facts = _preflight(values, requested.attempt_id)
        async with factory() as session:
            execution = _execution_service(session, service)
            await execution.fence_dispatch(actor=service, facts=facts)
        async with factory() as session:
            await _execution_service(session, service).record_accepted_result(
                actor=service, facts=facts, context=context(values), result=result()
            )

        async def persist_once():
            async with factory() as session:
                return await _execution_service(session, service).persist_accepted(
                    actor=service, facts=facts, context=context(values)
                )

        first, second = await asyncio.gather(persist_once(), persist_once())
        assert first == second
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1)
    finally:
        await engine.dispose()
