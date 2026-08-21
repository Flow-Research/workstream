"""Durable recovery classifications never invent provider certainty."""

from __future__ import annotations

from dataclasses import replace
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest

from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.guide_compilation.contracts import (
    CompilationRecoveryClassification,
)
from app.modules.projects.guide_compilation.service import GuideCompilationService
from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError

from .helpers import context, identity, seed_database, service_actor
from .test_authorized_execution_service import _execution_service, _preflight
from .test_authorized_request_service import _authorized_service, _request, _seed_human


class _NoAuthorityOrProvider:
    """Fail if uncertain recovery reaches AUTH or any external operation."""

    calls = 0

    def __getattr__(self, name: str):
        type(self).calls += 1
        raise AssertionError(f"uncertain recovery reached {name}")


@pytest.mark.asyncio
async def test_uncertain_restart_returns_unresolved_without_redispatch(
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
            first = await _execution_service(session, service).fence_dispatch(
                actor=service, facts=facts
            )
        _NoAuthorityOrProvider.calls = 0
        async with factory() as restarted_session:
            recovered = await GuideCompilationService(
                restarted_session, _NoAuthorityOrProvider()  # type: ignore[arg-type]
            ).fence_dispatch(actor=service, facts=facts)
        assert recovered == first
        assert recovered.classification is CompilationRecoveryClassification.PROVIDER_UNCERTAIN
        assert _NoAuthorityOrProvider.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_changed_request_replay_fails_without_new_authority_event(
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
            await _authorized_service(session, actor).authorize_request(
                actor=actor, facts=facts, identity=identity(context(values))
            )
        changed = replace(facts, instruction_version="v2")
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="replay mismatch"):
                await _authorized_service(session, actor).authorize_request(
                    actor=actor,
                    facts=changed,
                    identity=identity(context(values)).model_copy(
                        update={"instruction_version": "v2"}
                    ),
                )
    finally:
        await engine.dispose()
