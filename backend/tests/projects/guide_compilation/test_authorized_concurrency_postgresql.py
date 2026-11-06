"""Independent-session concurrency proof for request and final custody."""

from __future__ import annotations

from tests.projects.guide_compilation.helpers import runtime_configuration

from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from .runtime_fixtures import record_attempt_document_access
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.guide_compilation import (
    ProjectGuideCompilationAuthorizationAdapter,
)
from tests.auth_concurrency_support import wait_for_named_database_lock

from .helpers import acknowledge_requested_setup
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
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=actor,
                facts=facts,
                identity=attempt_identity,
                runtime_configuration=runtime_configuration(),
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
async def test_direct_and_natural_request_replays_share_auth_then_operation_lock_order(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, link, _grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    exact_facts, attempt_identity = _request(values), identity(context(values))
    origin = ProjectGuideCompilationRequestOrigin(trigger="project_manager")
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    auth_held = asyncio.Event()
    release_natural = asyncio.Event()
    direct_authorization_started = asyncio.Event()
    waiter_name = "guide-request-replay-" + uuid4().hex
    pids: dict[str, int] = {}
    tasks: list[asyncio.Task] = []
    original_prepare = ProjectGuideCompilationAuthorizationAdapter.prepare_request
    original_validate = ProjectGuideCompilationAuthorizationAdapter.validate_request_replay

    async def pause_natural_after_auth(adapter, **kwargs):
        handle = await original_prepare(adapter, **kwargs)
        task = asyncio.current_task()
        if task is not None and task.get_name() == "natural-request-replay":
            pids["natural"] = await adapter._prepared._session.scalar(
                text("select pg_backend_pid()")
            )
            auth_held.set()
            await release_natural.wait()
        return handle

    async def name_direct_authorization(adapter, *args, **kwargs):
        session = adapter._prepared._session
        task = asyncio.current_task()
        if task is not None and task.get_name() == "direct-request-replay":
            pids["direct"] = await session.scalar(text("select pg_backend_pid()"))
            await session.execute(
                text("select set_config('application_name', :name, true)"),
                {"name": waiter_name},
            )
            direct_authorization_started.set()
        return await original_validate(adapter, *args, **kwargs)

    async def replay(facts):
        async with factory() as session:
            return await _authorized_service(session, actor).authorize_request(
                origin=origin,
                actor=actor,
                facts=facts,
                identity=attempt_identity,
                runtime_configuration=runtime_configuration(),
            )

    try:
        first = await replay(exact_facts)
        stored_facts = replace(exact_facts, operation_id=first.operation_id)
        natural_facts = replace(stored_facts, operation_id=uuid4())
        monkeypatch.setattr(
            ProjectGuideCompilationAuthorizationAdapter,
            "prepare_request",
            pause_natural_after_auth,
        )
        monkeypatch.setattr(
            ProjectGuideCompilationAuthorizationAdapter,
            "validate_request_replay",
            name_direct_authorization,
        )
        natural = asyncio.create_task(replay(natural_facts), name="natural-request-replay")
        tasks.append(natural)
        await asyncio.wait_for(auth_held.wait(), 5)
        direct = asyncio.create_task(replay(stored_facts), name="direct-request-replay")
        tasks.append(direct)
        await asyncio.wait_for(direct_authorization_started.wait(), 5)
        await asyncio.wait_for(
            wait_for_named_database_lock(
                clean_postgres_database,
                waiter_name,
                expected_waiter_pid=pids["direct"],
                expected_blocker_pid=pids["natural"],
            ),
            5,
        )
        release_natural.set()
        natural_receipt, direct_receipt = await asyncio.wait_for(
            asyncio.gather(natural, direct), 10
        )
        assert natural_receipt == direct_receipt == first
        async with factory() as session:
            retained = (
                await session.execute(
                    text(
                        "select "
                        "(select count(*) from project_guide_compilation_attempts),"
                        "(select count(*) from project_guide_compilation_request_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.request'),"
                        "(select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute'),"
                        "(select count(*) from outbox_events),"
                        "(select status from project_guide_compilation_attempts)"
                    )
                )
            ).one()
        assert retained == (1, 1, 1, 0, 0, 0, "compilation_reserved")
    finally:
        release_natural.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
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
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=human_actor,
                facts=_request(values),
                identity=identity(context(values)),
                runtime_configuration=runtime_configuration(),
            )
        await acknowledge_requested_setup(factory, requested)
        facts = _preflight(values, requested.attempt_id, requested.operation_id)
        async with factory() as session:
            execution = _execution_service(session, service)
            await execution.fence_dispatch(actor=service, facts=facts)
        await record_attempt_document_access(factory, requested.attempt_id, context(values))
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
