"""Small hidden state machine for one authorized unified compilation."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


from app.modules.projects.api.guide_documents import GuideDocumentManifestPort, GuideDocumentUnavailable
from app.interfaces.project_agents import (
    ProjectGuideAgentRuntime,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    require_complete_project_guide_compilation_result,
    validate_project_guide_compilation_result,
)
from app.modules.checkers.api.pre_submit_catalogue import (
    PreSubmissionCapabilityProjection,
)
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitCatalogue,
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

from .context import build_project_guide_compilation_context
from .contracts import (
    CompilationDispatchReceipt,
    CompilationExecutionState,
    CompilationOutcomeReceipt,
    CompilationPersistenceReceipt,
    CompilationRecoveryClassification,
)
from .repository import GuideCompilationIntegrityError, GuideCompilationStorageError
from .service import (
    CompilationExecutionStateUnavailable,
    GuideCompilationService,
    load_compilation_execution_state,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import GuideDocumentAccessFactory, GuideRuntimeCapabilities
from .runtime_resources import SqlAlchemyGuideRuntimeCustody
from app.interfaces.external_services import ExternalServiceAdapterError
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    project_guide_compilation_prompt_bytes,
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
        pre_submission_capabilities: PreSubmissionCapabilityProjection,
        post_submission_capabilities: PostSubmitCatalogue,
        authorization_context: GuideCompilationAuthorizationContext,
        document_access_factory: GuideDocumentAccessFactory,
    ) -> None:
        """Store the owner-supplied ports used by each short transaction."""
        self._session_factory = session_factory
        self._material_factory = material_factory
        self._pre_submission_capabilities = pre_submission_capabilities
        self._post_submission_capabilities = post_submission_capabilities
        self._authorization_context = authorization_context
        self._document_access_factory = document_access_factory

    @asynccontextmanager
    async def capabilities(self, state, context):
        """Issue resources only from the orchestrator's winning dispatch branch."""
        async with self._document_access_factory(
            state.preflight_facts.attempt_id, context.material, context.runtime_configuration,
        ) as documents:
            yield GuideRuntimeCapabilities(
                documents=documents,
                resources=SqlAlchemyGuideRuntimeCustody(
                    self._session_factory, state.preflight_facts.attempt_id, context.material,
                    context.runtime_configuration.runtime_key,
                ),
            )

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
                    pre_submission_capabilities=self._pre_submission_capabilities,
                    post_submission_capabilities=self._post_submission_capabilities,
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
    pre_submission_capabilities: PreSubmissionCapabilityProjection,
    post_submission_capabilities: PostSubmitCatalogue,
    authorization_context: GuideCompilationAuthorizationContext,
    runtime_factory: Callable[[ProjectGuideRuntimeConfiguration], ProjectGuideAgentRuntime],
    document_access_factory: GuideDocumentAccessFactory,
) -> ProjectGuideCompilationExecutionPort:
    """Compose the hidden port from existing owner-supplied dependencies."""
    backend = SqlAlchemyGuideCompilationExecutionBackend(
        session_factory,
        material_factory=material_factory,
        pre_submission_capabilities=pre_submission_capabilities,
        post_submission_capabilities=post_submission_capabilities,
        authorization_context=authorization_context,
        document_access_factory=document_access_factory,
    )
    return GuideCompilationOrchestrator(backend, runtime_factory)


class GuideCompilationExecutionBackend(Protocol):
    """Exact persistence/context operations required by the state machine."""

    def capabilities(self, state: CompilationExecutionState,
                     context: ProjectGuideCompilationContext) -> AbstractAsyncContextManager[GuideRuntimeCapabilities]: ...

    async def load(self, attempt_id: UUID) -> CompilationExecutionState: ...

    async def context(self, state: CompilationExecutionState) -> ProjectGuideCompilationContext: ...

    async def fence(self, state: CompilationExecutionState) -> CompilationDispatchReceipt: ...

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
        recovered = await self._recover(state)
        if recovered is not None:
            return recovered

        context = await self._backend.context(state)
        runtime = None
        try:
            if (
                len(project_guide_compilation_prompt_bytes(context))
                > context.runtime_configuration.maximum_manifest_bytes
            ):
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
            dispatch = await self._backend.fence(state)
            if not dispatch.dispatch_permitted:
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
                        terminal_receipt = await self._backend.record_invalid(state, exc.failure_code)
                    else:
                        try:
                            _require_valid_result(context, result)
                        except (TypeError, ValueError):
                            terminal_receipt = await self._backend.record_invalid(state, "schema_invalid")
                        else:
                            await self._backend.record_accepted(state, context, result)
                            accepted = True
            except Exception:  # noqa: BLE001 - preserve known evidence across cleanup failure
                if terminal_receipt is None and not accepted:
                    return _receipt_result(dispatch)
            if terminal_receipt is not None:
                return _receipt_result(terminal_receipt)
            return _receipt_result(await self._backend.persist(state, context))
        finally:
            await runtime.aclose()

    async def _recover(
        self, state: CompilationExecutionState
    ) -> ProjectGuideCompilationExecutionResult | None:
        """Return a durable result without provider I/O, or select dispatch."""
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
