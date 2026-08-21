"""Four-stage authorized execution custody through real PostgreSQL and AUTH."""

from __future__ import annotations

from dataclasses import asdict, replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind as PublicActorKind,
    ProjectGuideCompilationExecutePreflightFacts,
)
from app.modules.authorization.guide_compilation import (
    ProjectGuideCompilationAuthorizationAdapter,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.projects.guide_compilation.contracts import (
    CompilationRecoveryClassification,
)
from app.modules.projects.guide_compilation.repository import (
    GuideCompilationIntegrityError,
    GuideCompilationRepository,
)
from app.modules.projects.guide_compilation.service import GuideCompilationService

from .helpers import context, identity, persistence_facts, result, seed_database, service_actor
from .test_authorized_request_service import _authorized_service, _request, _seed_human


def _execution_service(
    session: AsyncSession, actor: ActorIdentityFacts
) -> GuideCompilationService:
    context_value = ServiceAuthorizationContext(
        actor_profile_id=actor.actor_profile_id,
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=actor.identity_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=ServiceIdentity.PROJECT_SETUP,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    repository = AdminAuthorizationRepository(session)
    authorization = AuthorizationService(
        session, context_value, admin_repository=repository
    )
    prepared = PreparedAuthorizationService(
        session, context_value, authorization, repository
    )
    return GuideCompilationService(
        session,
        ProjectGuideCompilationAuthorizationAdapter(authorization, prepared),
    )


def _preflight(
    values: dict[str, UUID], attempt_id: UUID
) -> ProjectGuideCompilationExecutePreflightFacts:
    complete = persistence_facts(values, attempt_id, identity(context(values)))
    names = ProjectGuideCompilationExecutePreflightFacts.__dataclass_fields__
    return ProjectGuideCompilationExecutePreflightFacts(
        **{name: asdict(complete)[name] for name in names}
    )


@pytest.mark.asyncio
async def test_authorized_execution_fences_accepts_and_persists_atomically(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, human_link, _grant = await _seed_human(clean_postgres_database, values)
    human_actor = ActorIdentityFacts(human, human_link, PublicActorKind.HUMAN)
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
            fenced = await _execution_service(session, service).fence_dispatch(
                actor=service, facts=facts
            )
        assert fenced.classification is CompilationRecoveryClassification.PROVIDER_UNCERTAIN
        async with factory() as session:
            accepted = await _execution_service(session, service).record_accepted_result(
                actor=service, facts=facts, context=context(values), result=result()
            )
        assert (
            accepted.classification
            is CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED
        )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="not recordable"):
                await _execution_service(session, service).record_accepted_result(
                    actor=service, facts=facts, context=context(values), result=result()
                )
        async with factory() as session:
            persisted = await _execution_service(session, service).persist_accepted(
                actor=service, facts=facts, context=context(values)
            )
        assert persisted.classification is CompilationRecoveryClassification.PERSISTED
        async with factory() as session:
            replay = await _execution_service(session, service).persist_accepted(
                actor=service, facts=facts, context=context(values)
            )
        assert replay == persisted
        async with factory() as session:
            rows = (
                await session.execute(
                    text(
                        "select (select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute'),"
                        "(select count(*) from outbox_events),"
                        "(select status from project_guide_compilation_attempts where id=:id)"
                    ),
                    {"id": requested.attempt_id},
                )
            ).one()
            await session.rollback()
        assert rows == (1, 1, 0, "compilation_persisted")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_provider_result_becomes_one_bounded_terminal_outcome(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, human_link, _grant = await _seed_human(clean_postgres_database, values)
    human_actor = ActorIdentityFacts(human, human_link, PublicActorKind.HUMAN)
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
            await _execution_service(session, service).fence_dispatch(
                actor=service, facts=facts
            )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="failure code"):
                await _execution_service(session, service).record_invalid_result(
                    actor=service, facts=facts, failure_code="provider_exception_detail"
                )
        async with factory() as session:
            terminal = await _execution_service(session, service).record_invalid_result(
                actor=service, facts=facts, failure_code="schema_invalid"
            )
        assert terminal.classification is CompilationRecoveryClassification.INVALID_TERMINAL
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="not recordable"):
                await _execution_service(session, service).record_invalid_result(
                    actor=service, facts=facts, failure_code="schema_invalid"
                )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="cannot be dispatched"):
                await _execution_service(session, service).fence_dispatch(
                    actor=service, facts=facts
                )
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select status,failure_code,(select count(*) from audit_events "
                        "where action_id='project.guide_compilation.execute') "
                        "from project_guide_compilation_attempts where id=:id"
                    ),
                    {"id": requested.attempt_id},
                )
            ).one()
            await session.rollback()
        assert row == ("compilation_invalid_terminal", "schema_invalid", 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execution_rejects_nonfresh_session_and_durable_fact_drift(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, human_link, _grant = await _seed_human(clean_postgres_database, values)
    human_actor = ActorIdentityFacts(human, human_link, PublicActorKind.HUMAN)
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
        async with factory() as session, session.begin():
            with pytest.raises(GuideCompilationIntegrityError, match="fresh root"):
                await _execution_service(session, service).fence_dispatch(
                    actor=service, facts=facts
                )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="facts mismatch"):
                await _execution_service(session, service).fence_dispatch(
                    actor=service, facts=replace(facts, request_id=uuid4())
                )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="not ready"):
                await _execution_service(session, service).persist_accepted(
                    actor=service, facts=facts, context=context(values)
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_result_replay_requires_exact_canonical_result(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    compilation_context = context(values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            repository = GuideCompilationRepository(session)
            _outcome, attempt = await repository.reserve_attempt(
                identity(compilation_context)
            )
            accepted = await repository.accept_result(
                attempt_id=attempt.id,
                context=compilation_context,
                result=result(),
            )
        async with factory() as session, session.begin():
            replay = await GuideCompilationRepository(session).accept_result(
                attempt_id=accepted.id,
                context=compilation_context,
                result=result(),
            )
            assert replay.status == "provider_result_accepted"
        changed_finding = result().findings[0].model_copy(
            update={"message": "A different valid finding."}
        )
        changed = result().model_copy(update={"findings": (changed_finding,)})
        async with factory() as session, session.begin():
            with pytest.raises(GuideCompilationIntegrityError, match="result mismatch"):
                await GuideCompilationRepository(session).accept_result(
                    attempt_id=accepted.id,
                    context=compilation_context,
                    result=changed,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_result_rejects_context_from_another_generation(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database, generations=2)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            repository = GuideCompilationRepository(session)
            _outcome, attempt = await repository.reserve_attempt(identity(context(values)))
            with pytest.raises(GuideCompilationIntegrityError, match="result is invalid"):
                await repository.accept_result(
                    attempt_id=attempt.id,
                    context=context(values, generation=2),
                    result=result(),
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reserved_attempt_cannot_persist_without_accepted_custody(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    compilation_context = context(values)
    attempt_identity = identity(compilation_context)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            repository = GuideCompilationRepository(session)
            _outcome, attempt = await repository.reserve_attempt(attempt_identity)
            with pytest.raises(GuideCompilationIntegrityError, match="not ready"):
                await repository.persist_accepted(
                    attempt_id=attempt.id,
                    context=compilation_context,
                    expected_predecessor_id=None,
                    actor=service_actor(values),
                    facts=persistence_facts(values, attempt.id, attempt_identity),
                    authorization_decision_event_id=uuid4(),
                )
    finally:
        await engine.dispose()
