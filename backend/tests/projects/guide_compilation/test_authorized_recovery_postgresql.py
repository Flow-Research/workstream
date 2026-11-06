"""Durable recovery classifications never invent provider certainty."""

from __future__ import annotations

from tests.projects.guide_compilation.helpers import runtime_configuration

from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
from dataclasses import replace
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import pytest
from .runtime_fixtures import record_attempt_document_access

from app.modules.authorization.api import ActorIdentityFacts, ActorKind, AuthorizationDenied
from app.modules.projects.guide_compilation.contracts import (
    CompilationRecoveryClassification,
)
from app.modules.projects.guide_compilation.diagnostics import compilation_setup_response
from app.modules.projects.guide_compilation.repository import (
    GuideCompilationIntegrityError,
    GuideCompilationRepository,
)
from app.modules.projects.models import ProjectSetupRun

from .helpers import acknowledge_requested_setup
from .helpers import context, identity, result, seed_database, service_actor
from .test_authorized_execution_service import _execution_service, _preflight
from .test_authorized_request_service import _authorized_service, _request, _seed_human


async def _recovery_snapshot(
    factory: async_sessionmaker[AsyncSession], attempt_id: UUID
) -> tuple[int, int, int, int, int, str]:
    """Return the retained facts that an uncertain replay must not change."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "select "
                    "(select count(*) from project_guide_compilation_request_operations) "
                    "as operation_count,"
                    "(select count(*) from project_guide_compilation_attempts) "
                    "as attempt_count,"
                    "(select count(*) from project_guide_compilations) "
                    "as compilation_count,"
                    "(select count(*) from audit_events where action_id="
                    "'project.guide_compilation.execute') as execute_audit_count,"
                    "(select count(*) from outbox_events) as outbox_count,"
                    "(select status from project_guide_compilation_attempts where id=:id) "
                    "as attempt_status"
                ),
                {"id": attempt_id},
            )
        ).one()
        await session.rollback()
    return (
        int(row.operation_count),
        int(row.attempt_count),
        int(row.compilation_count),
        int(row.execute_audit_count),
        int(row.outbox_count),
        str(row.attempt_status),
    )


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
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=human_actor,
                facts=_request(values),
                identity=identity(context(values)),
                runtime_configuration=runtime_configuration(),
            )
        await acknowledge_requested_setup(factory, requested)
        facts = _preflight(values, requested.attempt_id, requested.operation_id)
        async with factory() as session:
            first = await _execution_service(session, service).fence_dispatch(
                actor=service, facts=facts
            )
        before_replay = await _recovery_snapshot(factory, requested.attempt_id)
        async with factory() as restarted_session:
            recovered = await _execution_service(restarted_session, service).fence_dispatch(
                actor=service, facts=facts
            )
        after_replay = await _recovery_snapshot(factory, requested.attempt_id)
        assert first.dispatch_permitted is True
        assert recovered.dispatch_permitted is False
        assert recovered.model_dump(exclude={"dispatch_permitted"}) == first.model_dump(
            exclude={"dispatch_permitted"}
        )
        assert recovered.classification is CompilationRecoveryClassification.PROVIDER_UNCERTAIN
        assert before_replay == (
            1,
            1,
            0,
            0,
            0,
            "compilation_provider_uncertain",
        )
        assert after_replay == before_replay
        async with factory() as session:
            setup = await session.get(ProjectSetupRun, str(values["setup_1"]))
            diagnostic = await compilation_setup_response(session, setup)
            assert diagnostic.status == "provider_outcome_unresolved"
            assert diagnostic.error_code == "provider_outcome_unresolved"
            assert diagnostic.error_summary == (
                "The provider outcome is unresolved; no further invocation is permitted."
            )
            assert diagnostic.finished_at is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_uncertain_restart_requires_current_service_authority(
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
            first = await _execution_service(session, service).fence_dispatch(
                actor=service, facts=facts
            )
        assert first.dispatch_permitted is True
        before_revocation = await _recovery_snapshot(factory, requested.attempt_id)

        async with engine.begin() as connection:
            await connection.execute(text("alter table actor_identity_links disable trigger user"))
            await connection.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_by='test',"
                    "revoked_at=clock_timestamp(),revoked_reason='test revocation' "
                    "where id=:id"
                ),
                {"id": str(service.identity_link_id)},
            )
            await connection.execute(text("alter table actor_identity_links enable trigger user"))

        async with factory() as restarted_session:
            with pytest.raises(AuthorizationDenied):
                await _execution_service(restarted_session, service).fence_dispatch(
                    actor=service, facts=facts
                )
        after_denial = await _recovery_snapshot(factory, requested.attempt_id)
        assert before_revocation == (
            1,
            1,
            0,
            0,
            0,
            "compilation_provider_uncertain",
        )
        assert after_denial == before_revocation
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
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=actor,
                facts=facts,
                identity=identity(context(values)),
                runtime_configuration=runtime_configuration(),
            )
        changed = replace(facts, instruction_version="v2")
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="compilation request input mismatch"):
                await _authorized_service(session, actor).authorize_request(
                    origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                    actor=actor,
                    facts=changed,
                    identity=identity(context(values)).model_copy(
                        update={"instruction_version": "v2"}
                    ),
                    runtime_configuration=runtime_configuration(),
                )
            # Locked original input validation rejects drift before replay classification.
            assert (await session.execute(text(
                "select (select count(*) from project_guide_compilation_attempts),"
                "(select count(*) from project_guide_compilation_request_operations),"
                "(select count(*) from audit_events where action_id="
                "'project.guide_compilation.request')"
            ))).one() == (1, 1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repeated_terminal_transitions_preserve_one_attempt(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            repository = GuideCompilationRepository(session)
            _outcome, attempt = await repository.reserve_attempt(
                identity(context(values)), runtime_configuration=runtime_configuration()
            )
            uncertain = await repository.mark_provider_uncertain(attempt.id)
            assert await repository.mark_provider_uncertain(attempt.id) == uncertain
            assert await repository.recovery_classification(attempt.id) == (
                "provider_outcome_unresolved"
            )
        await record_attempt_document_access(factory, attempt.id, context(values))
        async with factory() as session, session.begin():
            repository = GuideCompilationRepository(session)
            terminal = await repository.mark_invalid_terminal(
                attempt_id=attempt.id, failure_code="schema_invalid"
            )
            assert (
                await repository.mark_invalid_terminal(
                    attempt_id=attempt.id, failure_code="schema_invalid"
                )
                == terminal
            )
            with pytest.raises(GuideCompilationIntegrityError, match="accepted transition"):
                await repository.accept_result(
                    attempt_id=attempt.id,
                    context=context(values),
                    result=result(),
                )
    finally:
        await engine.dispose()
