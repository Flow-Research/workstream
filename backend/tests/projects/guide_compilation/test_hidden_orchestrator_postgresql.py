"""Production-boundary PostgreSQL tests for hidden unified compilation."""

from __future__ import annotations

from app.modules.checkers.catalogue import project_guide_pre_submission_capabilities

from tests.projects.guide_compilation.helpers import runtime_configuration

from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    guide_document_manifest_port,
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
    GuideCompilationOrchestrator,
    SqlAlchemyGuideCompilationExecutionBackend,
    project_guide_compilation_execution_port,
)
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
)
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue

from .helpers import context, identity, result, seed_database
from .runtime_fixtures import document_access, record_scripted_document_access
from .test_authorized_request_service import _authorized_service, _request, _seed_human


class _Runtime:
    identity = runtime_configuration().adapter_identity

    def __init__(self, outcome=result(), *, delay: float = 0) -> None:
        self.outcome = outcome
        self.delay = delay
        self.calls = 0

    def admit_execution(self):
        pass

    async def aclose(self):
        pass

    async def compile_project_guide(self, _context, capabilities):
        self.calls += 1
        await record_scripted_document_access(_context, capabilities)
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


class _DelayedFence:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def fence(self, state):
        self.waiting.set()
        await self.release.wait()
        return await self.inner.fence(state)


def _backend(factory):
    return SqlAlchemyGuideCompilationExecutionBackend(
        factory,
        material_factory=guide_document_manifest_port,
        document_access_factory=document_access,
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=current_post_submit_catalogue(),
        authorization_context=_fixed_service_authorization,
    )


def _port(factory, runtime):
    return project_guide_compilation_execution_port(
        factory,
        material_factory=guide_document_manifest_port,
        document_access_factory=document_access,
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=current_post_submit_catalogue(),
        authorization_context=_fixed_service_authorization,
        runtime_factory=lambda configuration: runtime,
    )


async def _authorized_attempt(database_url: str, values):
    actor_id, link_id, _grant_id = await _seed_human(database_url, values)
    actor = ActorIdentityFacts(actor_id, link_id, ActorKind.HUMAN)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await _authorized_service(session, actor).authorize_request(
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
                runtime_configuration=runtime_configuration(),
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
@pytest.mark.parametrize(
    ("winner_outcome", "expected_classification", "expected_compilations"),
    [
        (
            result(),
            ProjectGuideCompilationExecutionClassification.PERSISTED,
            1,
        ),
        (
            ProjectGuideCompilationInvalidOutputError("schema_invalid"),
            ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL,
            0,
        ),
    ],
)
async def test_loser_fencing_after_winner_converges_without_second_provider_call(
    clean_postgres_database: str,
    winner_outcome,
    expected_classification: ProjectGuideCompilationExecutionClassification,
    expected_compilations: int,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    backend = _backend(factory)
    delayed = _DelayedFence(backend)
    winner_runtime = _Runtime(winner_outcome)
    loser_runtime = _Runtime(ProjectAgentRuntimeError("must not run"))
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        loser = asyncio.create_task(
            GuideCompilationOrchestrator(
                delayed,
                lambda configuration: loser_runtime,
            ).execute(command)
        )
        await delayed.waiting.wait()
        winner = await GuideCompilationOrchestrator(
            backend,
            lambda configuration: winner_runtime,
        ).execute(command)
        delayed.release.set()
        recovered = await loser

        assert winner.classification is expected_classification
        assert recovered == winner
        assert winner_runtime.calls == 1
        assert loser_runtime.calls == 0
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
        assert counts == (expected_compilations, expected_compilations)
    finally:
        delayed.release.set()
        await engine.dispose()


@pytest.mark.asyncio
async def test_loser_persists_an_accepted_winner_without_second_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    backend = _backend(factory)
    delayed = _DelayedFence(backend)
    winner_runtime = _Runtime()
    loser_runtime = _Runtime(ProjectAgentRuntimeError("must not run"))
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        loser = asyncio.create_task(
            GuideCompilationOrchestrator(
                delayed,
                lambda configuration: loser_runtime,
            ).execute(command)
        )
        await delayed.waiting.wait()
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await GuideCompilationOrchestrator(
                _FailFirstPersist(backend),
                lambda configuration: winner_runtime,
            ).execute(command)
        assert failure.value.code == "storage_unavailable"

        delayed.release.set()
        recovered = await loser

        assert recovered.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
        assert recovered.compilation_id is not None
        assert winner_runtime.calls == 1
        assert loser_runtime.calls == 0
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
        delayed.release.set()
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
            await GuideCompilationOrchestrator(
                failing,
                lambda configuration: first_runtime,
            ).execute(command)
        assert failure.value.code == "storage_unavailable"
        assert first_runtime.calls == 1

        recovery_runtime = _Runtime(ProjectAgentRuntimeError("must not run"))
        receipt = await GuideCompilationOrchestrator(
            backend,
            lambda configuration: recovery_runtime,
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
            material_factory=guide_document_manifest_port,
        document_access_factory=document_access,
            pre_submission_capabilities=project_guide_pre_submission_capabilities(
                build_pre_submission_checker_catalogue()
            ),
            post_submission_capabilities=current_post_submit_catalogue(),
            authorization_context=_unavailable_service_authorization,
            runtime_factory=lambda configuration: runtime,
        )
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await port.execute(
                ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
            )
        assert failure.value.code == "service_authority_denied"
        assert str(failure.value) == "service_authority_denied"
        assert "private database detail" not in str(failure.value)
        assert runtime.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, failure_code", [
    ("malformed", "schema_invalid"), ("schema", "schema_invalid"), ("unsafe", "schema_invalid"),
])
async def test_sdk_parser_rejection_persists_terminal_without_reinvocation(
    clean_postgres_database, monkeypatch, kind, failure_code,
):
    """Real SDK rejection persists its exact terminal class and replay makes no call."""
    import json
    from types import SimpleNamespace
    from agents import Runner
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime

    from agents import _debug
    monkeypatch.setattr(_debug, "DONT_LOG_MODEL_DATA", True)
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    payload = result().model_dump(mode="json")
    if kind == "schema":
        payload["status"] = "not-a-status"
    if kind == "unsafe":
        payload["findings"] = [{"severity": "info", "code": "bad", "message": "token=secret123"}]
    raw = "{invalid" if kind == "malformed" else json.dumps(payload)
    calls = []

    async def run(agent, *args, **kwargs):
        calls.append(1)
        return SimpleNamespace(final_output=agent.output_type.validate_json(raw))

    monkeypatch.setattr(Runner, "run", run)

    class ScriptedWorkspace:
        container_id = "cntr_scripted"

        def __init__(self, client, configuration, manifest, capabilities):
            self.context = SimpleNamespace(material=manifest)
            self.capabilities = capabilities

        async def start(self):
            await record_scripted_document_access(self.context, self.capabilities)

        async def close(self):
            await self.capabilities.documents.close()

    monkeypatch.setattr(
        "app.adapters.project_agents.openai_agent_sdk.OpenAIGuideWorkspace", ScriptedWorkspace,
    )
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        port = _port(factory, OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()))
        first = await port.execute(command)
        assert first.classification is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
        assert await port.execute(command) == first
        assert calls == [1]
        async with factory() as session:
            row = (await session.execute(text(
                "select status,failure_code,canonical_result, "
                "(select count(*) from project_guide_compilations) "
                "from project_guide_compilation_attempts where id=:id"
            ), {"id": requested.attempt_id})).one()
        assert row == ("compilation_invalid_terminal", failure_code, None, 0)
    finally:
        await engine.dispose()
