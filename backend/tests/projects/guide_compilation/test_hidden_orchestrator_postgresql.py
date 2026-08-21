"""Production-boundary PostgreSQL tests for hidden unified compilation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    AuthorizationDenied,
    AuthorizationUnavailable,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.guide_compilation import (
    ProjectGuideCompilationAuthorizationAdapter,
)
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import PreparedAuthorizationUnsupported
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideCompilationExecutionError,
)
from app.modules.projects.guide_compilation.orchestrator import (
    HiddenGuideCompilationOrchestrator,
    SqlAlchemyGuideCompilationExecutionBackend,
    project_guide_compilation_execution_port,
)
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.projects.post_submit_policy import (
    project_guide_post_submission_capabilities,
)

from .helpers import context, identity, result, seed_database
from .test_authorized_request_service import _authorized_service, _request, _seed_human


class _Runtime:
    def __init__(self, outcome=result(), *, delay: float = 0) -> None:
        self.outcome = outcome
        self.delay = delay
        self.calls = 0

    async def compile_project_guide(self, _context):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _FailFirstPersist:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def persist(self, state, compilation_context):
        if not self.failed:
            self.failed = True
            raise ProjectGuideCompilationExecutionError("storage_unavailable")
        return await self.inner.persist(state, compilation_context)


def _backend(factory):
    return SqlAlchemyGuideCompilationExecutionBackend(
        factory,
        material_factory=SqlAlchemyGuideSufficiencyMaterialAdapter,
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=project_guide_post_submission_capabilities(),
        authorization_context=_fixed_service_authorization,
    )


def _port(factory, runtime):
    return project_guide_compilation_execution_port(
        factory,
        material_factory=SqlAlchemyGuideSufficiencyMaterialAdapter,
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=project_guide_post_submission_capabilities(),
        authorization_context=_fixed_service_authorization,
        runtime=runtime,
    )


async def _authorized_attempt(database_url: str, values):
    actor_id, link_id, _grant_id = await _seed_human(database_url, values)
    actor = ActorIdentityFacts(actor_id, link_id, ActorKind.HUMAN)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
    finally:
        await engine.dispose()


@asynccontextmanager
async def _fixed_service_authorization(session, state):
    facts = state.preflight_facts
    try:
        async with fixed_service_prepared_authorization(
            session,
            service_identity=ServiceIdentity.PROJECT_SETUP,
            request_id=facts.operation_id,
            correlation_id=facts.attempt_id,
        ) as authority:
            await session.rollback()
            yield (
                ProjectGuideCompilationAuthorizationAdapter.from_prepared(authority.service),
                ActorIdentityFacts(
                    authority.actor_profile_id,
                    authority.identity_link_id,
                    ActorKind.SERVICE,
                    ServiceIdentity.PROJECT_SETUP.value,
                ),
            )
    except PreparedAuthorizationUnsupported as exc:
        raise AuthorizationDenied("compilation service authority denied") from exc


@asynccontextmanager
async def _unavailable_service_authorization(_session, _state):
    raise AuthorizationUnavailable("private database detail")
    yield  # pragma: no cover - required only to define an async context manager


@pytest.mark.asyncio
async def test_hidden_command_persists_one_complete_result_and_no_projections(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime()
    try:
        port = _port(factory, runtime)
        receipt = await port.execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
        )
        assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
        assert receipt.compilation_id is not None
        assert runtime.calls == 1
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select "
                        "(select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.request'),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute'),"
                        "(select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from submission_artifact_policies),"
                        "(select count(*) from pre_submit_checker_policies),"
                        "(select count(*) from checker_policies),"
                        "(select count(*) from outbox_events)"
                    )
                )
            ).one()
            setup = (
                await session.execute(
                    text(
                        "select status,output_sufficiency_report_id,"
                        "output_submission_artifact_policy_id,"
                        "output_post_submit_checker_policy_id "
                        "from project_setup_runs where id=:id"
                    ),
                    {"id": str(values["setup_1"])},
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1, 1, 0, 0, 0, 0, 0)
        assert setup == ("queued", None, None, None)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_commands_commit_one_dispatch_and_one_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(delay=0.05)
    try:
        port = _port(factory, runtime)
        command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
        receipts = await asyncio.gather(port.execute(command), port.execute(command))
        assert runtime.calls == 1
        assert {receipt.classification for receipt in receipts} == {
            ProjectGuideCompilationExecutionClassification.PERSISTED,
            ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED,
        }
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select count(*),(select count(*) from audit_events where "
                        "action_id='project.guide_compilation.execute') from "
                        "project_guide_compilations"
                    )
                )
            ).one()
            await session.rollback()
        assert row == (1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_result_recovers_without_a_second_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_runtime = _Runtime()
    backend = _backend(factory)
    failing = _FailFirstPersist(backend)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await HiddenGuideCompilationOrchestrator(
                failing,
                first_runtime,  # type: ignore[arg-type]
            ).execute(command)
        assert failure.value.code == "storage_unavailable"
        assert first_runtime.calls == 1

        recovery_runtime = _Runtime(ProjectAgentRuntimeError("must not run"))
        receipt = await HiddenGuideCompilationOrchestrator(
            backend,
            recovery_runtime,  # type: ignore[arg-type]
        ).execute(command)
        assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
        assert recovery_runtime.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        ProjectGuideCompilationInvalidOutputError("schema_invalid"),
        ProjectGuideCompilationInvalidOutputError("unsafe_text"),
        result().model_copy(update={"agent_version": "v2"}),
    ],
)
async def test_known_invalid_output_terminalizes_without_compilation(
    clean_postgres_database: str,
    outcome,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(outcome)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        port = _port(factory, runtime)
        receipt = await port.execute(command)
        replay = await port.execute(command)
        assert (
            receipt.classification
            is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
        )
        assert replay == receipt
        assert runtime.calls == 1
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select status,failure_code,"
                        "(select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute') "
                        "from project_guide_compilation_attempts where id=:id"
                    ),
                    {"id": requested.attempt_id},
                )
            ).one()
            await session.rollback()
        assert row[0] == "compilation_invalid_terminal"
        assert row[1] in {"schema_invalid", "unsafe_text"}
        assert row[2:] == (0, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_uncertain_provider_failure_never_redispatches(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(ProjectAgentRuntimeError("transport failed"))
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        port = _port(factory, runtime)
        first = await port.execute(command)
        second = await port.execute(command)
        assert first == second
        assert (
            first.classification
            is ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED
        )
        assert runtime.calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_revoked_service_authority_is_bounded_before_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime()
    try:
        async with engine.begin() as connection:
            await connection.execute(text("alter table actor_identity_links disable trigger user"))
            await connection.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_by='test',"
                    "revoked_at=clock_timestamp(),revoked_reason='test revocation' "
                    "where id=:id"
                ),
                {"id": str(values["link"])},
            )
            await connection.execute(text("alter table actor_identity_links enable trigger user"))

        port = _port(factory, runtime)
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await port.execute(
                ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
            )
        assert failure.value.code == "service_authority_denied"
        assert runtime.calls == 0
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select status,(select count(*) from audit_events where "
                        "action_id='project.guide_compilation.execute') "
                        "from project_guide_compilation_attempts where id=:id"
                    ),
                    {"id": requested.attempt_id},
                )
            ).one()
        assert row == ("compilation_reserved", 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unavailable_authority_returns_only_the_safe_public_code(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime()
    try:
        port = project_guide_compilation_execution_port(
            factory,
            material_factory=SqlAlchemyGuideSufficiencyMaterialAdapter,
            pre_submission_capabilities=project_guide_pre_submission_capabilities(
                build_pre_submission_checker_catalogue()
            ),
            post_submission_capabilities=project_guide_post_submission_capabilities(),
            authorization_context=_unavailable_service_authorization,
            runtime=runtime,
        )
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await port.execute(
                ProjectGuideCompilationExecutionCommand(
                    attempt_id=requested.attempt_id
                )
            )
        assert failure.value.code == "service_authority_denied"
        assert str(failure.value) == "service_authority_denied"
        assert "private database detail" not in str(failure.value)
        assert runtime.calls == 0
    finally:
        await engine.dispose()
