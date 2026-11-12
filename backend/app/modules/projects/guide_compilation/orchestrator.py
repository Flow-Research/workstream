"""Small hidden state machine for one authorized unified compilation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from workstream_external_services import ExternalServiceAdapterError
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideAgentRuntime,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    project_guide_compilation_prompt_bytes,
    require_complete_project_guide_compilation_result,
    validate_project_guide_compilation_result,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.interfaces.setup_model_proxy import (
    SetupModelDispatchPort,
    SetupModelProxySubject,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    AuthorizationDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
    ProjectGuideCompilationAuthorizationPort,
)
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideCompilationExecutionError,
    ProjectGuideCompilationExecutionPort,
    ProjectGuideCompilationExecutionResult,
)
from app.modules.projects.api.guide_documents import (
    GuideDocumentManifestPort,
    GuideDocumentToolsFactory,
    GuideDocumentUnavailable,
    GuideRuntimeCapabilities,
)

from .context import build_project_guide_compilation_context
from .contracts import (
    CompilationDispatchReceipt,
    CompilationExecutionState,
    CompilationOutcomeReceipt,
    CompilationPersistenceReceipt,
    CompilationRecoveryClassification,
    uses_metered_setup_model_custody,
)
from .repository import GuideCompilationIntegrityError, GuideCompilationStorageError
from .service import (
    CompilationExecutionStateUnavailable,
    GuideCompilationService,
    load_compilation_execution_state,
)


class GuideCompilationAuthorizationContext(Protocol):
    """One caller-owned fixed-service AUTH composition.

    Implementations translate private AUTH composition failures into the public
    authorization errors declared by ``app.modules.authorization.api``.
    """

    def __call__(
        self,
        session: AsyncSession,
        state: CompilationExecutionState,
    ) -> AbstractAsyncContextManager[
        tuple[ProjectGuideCompilationAuthorizationPort, ActorIdentityFacts]
    ]: ...


class SqlAlchemyGuideCompilationExecutionBackend:
    """Bind the state machine to its existing typed owner ports."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        material_factory: Callable[[AsyncSession], GuideDocumentManifestPort],
        authorization_context: GuideCompilationAuthorizationContext,
        document_tools_factory: GuideDocumentToolsFactory,
        model_session_factory: Callable[
            [SetupModelProxySubject | None, ProjectGuideRuntimeConfiguration],
            AbstractAsyncContextManager[SetupModelDispatchPort | None],
        ] | None = None,
    ) -> None:
        """Store the owner-supplied ports used by each short transaction."""
        self._session_factory = session_factory
        self._material_factory = material_factory
        self._authorization_context = authorization_context
        self._document_tools_factory = document_tools_factory
        self._model_session_factory = model_session_factory or _no_model_session
        self._model_session_configured = model_session_factory is not None

    @asynccontextmanager
    async def capabilities(self, state, context):
        """Issue resources only from the orchestrator's winning dispatch branch."""
        model_subject = (
            _setup_model_subject(state, context.runtime_configuration)
            if self._model_session_configured
            else None
        )
        async with (
            self._document_tools_factory(
                state.preflight_facts.attempt_id,
                context.material,
                context.runtime_configuration,
            ) as tools,
            self._model_session_factory(model_subject, context.runtime_configuration) as model,
        ):
            yield GuideRuntimeCapabilities(tools=tools, model=model)

    async def load(self, attempt_id: UUID) -> CompilationExecutionState:
        """Load one exact attempt and translate storage failures safely."""
        try:
            async with self._session_factory() as session:
                return await load_compilation_execution_state(session, attempt_id)
        except CompilationExecutionStateUnavailable as exc:
            raise ProjectGuideCompilationExecutionError(exc.code) from None
        except SQLAlchemyError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None

    async def context(self, state: CompilationExecutionState) -> ProjectGuideCompilationContext:
        """Rebuild the immutable provider context for the selected attempt."""
        try:
            async with self._session_factory() as session:
                return await build_project_guide_compilation_context(
                    session,
                    state=state,
                    material=self._material_factory(session),
                )
        except GuideDocumentUnavailable:
            raise ProjectGuideCompilationExecutionError("context_unavailable") from None
        except GuideCompilationStorageError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None
        except (GuideCompilationIntegrityError, TypeError, ValueError):
            raise ProjectGuideCompilationExecutionError("context_unavailable") from None
        except SQLAlchemyError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None

    async def fence(self, state: CompilationExecutionState) -> CompilationDispatchReceipt:
        """Commit the one-shot provider-dispatch fence under service authority."""
        async with self._authorized_service(state) as (service, actor):
            return await service.fence_dispatch(actor=actor, facts=state.preflight_facts)

    async def release_no_inference(
        self, state: CompilationExecutionState, *, stale_before: datetime | None = None
    ) -> bool:
        """Reopen a no-inference fence so a transient failure stays retryable."""
        async with self._authorized_service(state) as (service, actor):
            return await service.release_no_inference_dispatch(
                actor=actor, facts=state.preflight_facts, stale_before=stale_before
            )

    async def record_accepted(
        self,
        state: CompilationExecutionState,
        context: ProjectGuideCompilationContext,
        result: ProjectGuideCompilationResult,
    ) -> CompilationOutcomeReceipt:
        """Record one validated provider result without persisting projections."""
        async with self._authorized_service(state) as (service, actor):
            return await service.record_accepted_result(
                actor=actor,
                facts=state.preflight_facts,
                context=context,
                result=result,
            )

    async def record_invalid(
        self, state: CompilationExecutionState, failure_code: str
    ) -> CompilationOutcomeReceipt:
        """Record one known invalid result as a terminal attempt outcome."""
        async with self._authorized_service(state) as (service, actor):
            return await service.record_invalid_result(
                actor=actor,
                facts=state.preflight_facts,
                failure_code=failure_code,
            )

    async def persist(
        self, state: CompilationExecutionState, context: ProjectGuideCompilationContext
    ) -> CompilationPersistenceReceipt:
        """Persist the already-accepted compilation under fresh authority."""
        async with self._authorized_service(state) as (service, actor):
            return await service.persist_accepted(
                actor=actor,
                facts=state.preflight_facts,
                context=context,
            )

    @asynccontextmanager
    async def _authorized_service(self, state: CompilationExecutionState):
        """Yield the fixed-service coordinator and hide internal AUTH failures."""
        try:
            async with self._session_factory() as session:
                async with self._authorization_context(session, state) as (
                    authorization,
                    actor,
                ):
                    yield GuideCompilationService(session, authorization), actor
        except (
            AuthorizationDenied,
            AuthorizationUnavailable,
            PreparedAuthorizationInvalid,
        ):
            raise ProjectGuideCompilationExecutionError("service_authority_denied") from None
        except GuideCompilationStorageError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None
        except GuideCompilationIntegrityError:
            raise ProjectGuideCompilationExecutionError("context_unavailable") from None
        except SQLAlchemyError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None


def project_guide_compilation_execution_port(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    material_factory: Callable[[AsyncSession], GuideDocumentManifestPort],
    authorization_context: GuideCompilationAuthorizationContext,
    runtime_factory: Callable[[ProjectGuideRuntimeConfiguration], ProjectGuideAgentRuntime],
    document_tools_factory: GuideDocumentToolsFactory,
    model_session_factory: Callable[
        [SetupModelProxySubject | None, ProjectGuideRuntimeConfiguration],
        AbstractAsyncContextManager[SetupModelDispatchPort | None],
    ] | None = None,
) -> ProjectGuideCompilationExecutionPort:
    """Compose the hidden port from existing owner-supplied dependencies."""
    backend = SqlAlchemyGuideCompilationExecutionBackend(
        session_factory,
        material_factory=material_factory,
        authorization_context=authorization_context,
        document_tools_factory=document_tools_factory,
        model_session_factory=model_session_factory,
    )
    return GuideCompilationOrchestrator(backend, runtime_factory)


@asynccontextmanager
async def _no_model_session(_subject, _configuration):
    """Keep provider-free and isolated owner tests free of production composition."""
    yield None


def _setup_model_subject(
    state: CompilationExecutionState,
    configuration: ProjectGuideRuntimeConfiguration,
) -> SetupModelProxySubject | None:
    """Project exact attempt/profile lineage into the shared model capability."""
    if not configuration.uses_inference:
        return None
    if (
        configuration.model_profile_id is None
        or configuration.model_profile_version is None
        or configuration.model_profile_digest is None
    ):
        raise ProjectGuideCompilationExecutionError("runtime_unavailable")
    return SetupModelProxySubject(
        compilation_attempt_id=UUID(str(state.preflight_facts.attempt_id)),
        project_id=UUID(str(state.identity.project_id)),
        guide_id=UUID(str(state.identity.guide_id)),
        source_snapshot_id=UUID(str(state.identity.source_snapshot_id)),
        setup_run_id=UUID(str(state.identity.setup_run_id)),
        setup_generation=state.identity.setup_generation,
        runtime_configuration_hash=configuration.sha256,
        profile_id=configuration.model_profile_id,
        profile_version=configuration.model_profile_version,
        profile_digest=configuration.model_profile_digest,
        provider=configuration.model_provider,
        api=configuration.model_api,
        model=configuration.model,
    )


class GuideCompilationExecutionBackend(Protocol):
    """Exact persistence/context operations required by the state machine."""

    def capabilities(
        self, state: CompilationExecutionState, context: ProjectGuideCompilationContext
    ) -> AbstractAsyncContextManager[GuideRuntimeCapabilities]: ...

    async def load(self, attempt_id: UUID) -> CompilationExecutionState: ...

    async def context(self, state: CompilationExecutionState) -> ProjectGuideCompilationContext: ...

    async def fence(self, state: CompilationExecutionState) -> CompilationDispatchReceipt: ...

    async def release_no_inference(
        self, state: CompilationExecutionState, *, stale_before: datetime | None = None
    ) -> bool: ...

    async def record_accepted(
        self,
        state: CompilationExecutionState,
        context: ProjectGuideCompilationContext,
        result: ProjectGuideCompilationResult,
    ) -> CompilationOutcomeReceipt: ...

    async def record_invalid(
        self, state: CompilationExecutionState, failure_code: str
    ) -> CompilationOutcomeReceipt: ...

    async def persist(
        self, state: CompilationExecutionState, context: ProjectGuideCompilationContext
    ) -> CompilationPersistenceReceipt: ...


class GuideCompilationOrchestrator(ProjectGuideCompilationExecutionPort):
    """Drive one attempt without creating authority or retrying uncertainty."""

    def __init__(
        self,
        backend: GuideCompilationExecutionBackend,
        runtime_factory: Callable[[ProjectGuideRuntimeConfiguration], ProjectGuideAgentRuntime],
    ) -> None:
        """Bind the durable backend to the single provider runtime."""
        self._backend = backend
        self._runtime_factory = runtime_factory

    async def execute(
        self, command: ProjectGuideCompilationExecutionCommand
    ) -> ProjectGuideCompilationExecutionResult:
        """Execute or safely recover one previously authorized attempt."""
        state = await self._backend.load(command.attempt_id)
        resuming_metered = _metered_setup_resume(state)
        recovered = await self._recover(state)
        if recovered is not None:
            return recovered

        context = await self._backend.context(state)
        runtime = None
        try:
            if (
                context.runtime_configuration.uses_inference
                and len(project_guide_compilation_prompt_bytes(context))
                > context.runtime_configuration.maximum_manifest_bytes
            ):
                # The model prompt limit does not apply when no inference request is built.
                raise ValueError("configured prompt limit exceeded")
            runtime = self._runtime_factory(context.runtime_configuration)
            if runtime.identity != context.runtime_configuration.adapter_identity:
                raise ValueError("runtime identity mismatch")
            runtime.admit_execution()
        except (ExternalServiceAdapterError, ProjectAgentRuntimeError, ValueError):
            if runtime is not None:
                await runtime.aclose()
            raise ProjectGuideCompilationExecutionError("runtime_unavailable") from None
        try:
            dispatch = None if resuming_metered else await self._backend.fence(state)
            if dispatch is not None and not dispatch.dispatch_permitted:
                raced_state = await self._backend.load(command.attempt_id)
                recovered = await self._recover(raced_state)
                if recovered is None:
                    raise ProjectGuideCompilationExecutionError("context_unavailable")
                return recovered
            terminal_receipt = None
            accepted = False
            try:
                async with self._backend.capabilities(state, context) as capabilities:
                    try:
                        result = await runtime.compile_project_guide(context, capabilities)
                    except ProjectGuideCompilationInvalidOutputError as exc:
                        terminal_receipt = await self._backend.record_invalid(
                            state, exc.failure_code
                        )
                    else:
                        try:
                            _require_valid_result(context, result)
                        except (TypeError, ValueError):
                            terminal_receipt = await self._backend.record_invalid(
                                state, "schema_invalid"
                            )
                        else:
                            await self._backend.record_accepted(state, context, result)
                            accepted = True
            except asyncio.CancelledError:
                if (
                    terminal_receipt is None
                    and not accepted
                    and not context.runtime_configuration.uses_inference
                ):
                    # Reopen before propagating so cancellation cannot strand the attempt.
                    with suppress(Exception):
                        await asyncio.shield(self._backend.release_no_inference(state))
                raise
            except Exception:  # noqa: BLE001 - preserve known evidence across cleanup failure
                if terminal_receipt is None and not accepted:
                    if not context.runtime_configuration.uses_inference:
                        # No model call exists to be uncertain about; reopen and retry.
                        await self._backend.release_no_inference(state)
                        raise ProjectGuideCompilationExecutionError("runtime_unavailable") from None
                    if dispatch is not None:
                        return _receipt_result(dispatch)
                    return _state_result(await self._backend.load(command.attempt_id))
            if terminal_receipt is not None:
                return _receipt_result(terminal_receipt)
            return _receipt_result(await self._backend.persist(state, context))
        finally:
            await runtime.aclose()

    async def _recover(
        self, state: CompilationExecutionState
    ) -> ProjectGuideCompilationExecutionResult | None:
        """Return a durable result without provider I/O, or select dispatch."""
        if state.classification is CompilationRecoveryClassification.PROVIDER_UNCERTAIN and (
            (configuration := state.runtime_configuration) is not None
            and not configuration.uses_inference
        ):
            # A no-inference fence left by a crashed or cancelled worker guards no
            # model call. Reopen it once its run deadline has passed.
            stale_before = datetime.now(UTC) - timedelta(seconds=configuration.timeout_seconds)
            if await self._backend.release_no_inference(state, stale_before=stale_before):
                return None
        if state.classification is CompilationRecoveryClassification.PROVIDER_UNCERTAIN and (
            _metered_setup_resume(state)
        ):
            return None
        if state.classification in {
            CompilationRecoveryClassification.PERSISTED,
            CompilationRecoveryClassification.INVALID_TERMINAL,
            CompilationRecoveryClassification.PROVIDER_UNCERTAIN,
        }:
            return _state_result(state)
        if state.classification is CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED:
            context = await self._backend.context(state)
            return _receipt_result(await self._backend.persist(state, context))
        return None


def _metered_setup_resume(state: CompilationExecutionState) -> bool:
    """Resume only attempts whose every provider effect is guarded by MODEL-USAGE."""
    return (
        state.classification is CompilationRecoveryClassification.PROVIDER_UNCERTAIN
        and uses_metered_setup_model_custody(state.runtime_configuration)
    )


def _require_valid_result(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Reject incomplete, inconsistent, or wrong-version provider output."""
    require_complete_project_guide_compilation_result(result)
    validate_project_guide_compilation_result(context, result)
    if result.agent_version != context.agent_version:
        raise ValueError("compilation result agent version is invalid")


def _state_result(
    state: CompilationExecutionState,
) -> ProjectGuideCompilationExecutionResult:
    """Project a durable execution state into the bounded public receipt."""
    facts = state.preflight_facts
    return ProjectGuideCompilationExecutionResult(
        operation_id=facts.operation_id,
        attempt_id=facts.attempt_id,
        provider_idempotency_key=facts.provider_idempotency_key,
        classification=ProjectGuideCompilationExecutionClassification(state.classification.value),
        compilation_id=state.compilation_id,
    )


def _receipt_result(
    receipt: CompilationDispatchReceipt | CompilationOutcomeReceipt | CompilationPersistenceReceipt,
) -> ProjectGuideCompilationExecutionResult:
    """Project an internal receipt into the bounded public result."""
    return ProjectGuideCompilationExecutionResult(
        operation_id=receipt.operation_id,
        attempt_id=receipt.attempt_id,
        provider_idempotency_key=receipt.provider_idempotency_key,
        classification=ProjectGuideCompilationExecutionClassification(receipt.classification.value),
        compilation_id=(
            receipt.compilation_id if isinstance(receipt, CompilationPersistenceReceipt) else None
        ),
    )
