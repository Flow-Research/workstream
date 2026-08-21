"""Small hidden state machine for one authorized unified compilation."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.interfaces.artifact_operations import (
    GuideSufficiencyMaterialPort,
    GuideSufficiencyMaterialUnavailable,
)
from app.interfaces.project_agents import (
    PostSubmissionCapabilityProjection,
    PreSubmissionCapabilityProjection,
    ProjectGuideAgentRuntime,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    require_complete_project_guide_compilation_result,
    validate_project_guide_compilation_result,
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
        material_factory: Callable[[AsyncSession], GuideSufficiencyMaterialPort],
        pre_submission_capabilities: PreSubmissionCapabilityProjection,
        post_submission_capabilities: PostSubmissionCapabilityProjection,
        authorization_context: GuideCompilationAuthorizationContext,
    ) -> None:
        self._session_factory = session_factory
        self._material_factory = material_factory
        self._pre_submission_capabilities = pre_submission_capabilities
        self._post_submission_capabilities = post_submission_capabilities
        self._authorization_context = authorization_context

    async def load(self, attempt_id: UUID) -> CompilationExecutionState:
        try:
            async with self._session_factory() as session:
                return await load_compilation_execution_state(session, attempt_id)
        except CompilationExecutionStateUnavailable as exc:
            raise ProjectGuideCompilationExecutionError(exc.code) from None
        except SQLAlchemyError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None

    async def context(self, state: CompilationExecutionState) -> ProjectGuideCompilationContext:
        try:
            async with self._session_factory() as session:
                return await build_project_guide_compilation_context(
                    session,
                    state=state,
                    material=self._material_factory(session),
                    pre_submission_capabilities=self._pre_submission_capabilities,
                    post_submission_capabilities=self._post_submission_capabilities,
                )
        except GuideSufficiencyMaterialUnavailable:
            raise ProjectGuideCompilationExecutionError("context_unavailable") from None
        except GuideCompilationStorageError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None
        except (GuideCompilationIntegrityError, TypeError, ValueError):
            raise ProjectGuideCompilationExecutionError("context_unavailable") from None
        except SQLAlchemyError:
            raise ProjectGuideCompilationExecutionError("storage_unavailable") from None

    async def fence(self, state: CompilationExecutionState) -> CompilationDispatchReceipt:
        async with self._authorized_service(state) as (service, actor):
            return await service.fence_dispatch(actor=actor, facts=state.preflight_facts)

    async def record_accepted(
        self,
        state: CompilationExecutionState,
        context: ProjectGuideCompilationContext,
        result: ProjectGuideCompilationResult,
    ) -> CompilationOutcomeReceipt:
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
        async with self._authorized_service(state) as (service, actor):
            return await service.record_invalid_result(
                actor=actor,
                facts=state.preflight_facts,
                failure_code=failure_code,
            )

    async def persist(
        self, state: CompilationExecutionState, context: ProjectGuideCompilationContext
    ) -> CompilationPersistenceReceipt:
        async with self._authorized_service(state) as (service, actor):
            return await service.persist_accepted(
                actor=actor,
                facts=state.preflight_facts,
                context=context,
            )

    @asynccontextmanager
    async def _authorized_service(self, state: CompilationExecutionState):
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
    material_factory: Callable[[AsyncSession], GuideSufficiencyMaterialPort],
    pre_submission_capabilities: PreSubmissionCapabilityProjection,
    post_submission_capabilities: PostSubmissionCapabilityProjection,
    authorization_context: GuideCompilationAuthorizationContext,
    runtime: ProjectGuideAgentRuntime,
) -> ProjectGuideCompilationExecutionPort:
    """Compose the hidden port from existing owner-supplied dependencies."""
    backend = SqlAlchemyGuideCompilationExecutionBackend(
        session_factory,
        material_factory=material_factory,
        pre_submission_capabilities=pre_submission_capabilities,
        post_submission_capabilities=post_submission_capabilities,
        authorization_context=authorization_context,
    )
    return HiddenGuideCompilationOrchestrator(backend, runtime)


class GuideCompilationExecutionBackend(Protocol):
    """Exact persistence/context operations required by the state machine."""

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


class HiddenGuideCompilationOrchestrator(ProjectGuideCompilationExecutionPort):
    """Drive one attempt without creating authority or retrying uncertainty."""

    def __init__(
        self,
        backend: GuideCompilationExecutionBackend,
        runtime: ProjectGuideAgentRuntime,
    ) -> None:
        self._backend = backend
        self._runtime = runtime

    async def execute(
        self, command: ProjectGuideCompilationExecutionCommand
    ) -> ProjectGuideCompilationExecutionResult:
        state = await self._backend.load(command.attempt_id)
        if state.classification in {
            CompilationRecoveryClassification.PERSISTED,
            CompilationRecoveryClassification.INVALID_TERMINAL,
            CompilationRecoveryClassification.PROVIDER_UNCERTAIN,
        }:
            return _state_result(state)

        context = await self._backend.context(state)
        if state.classification is CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED:
            return _receipt_result(await self._backend.persist(state, context))

        dispatch = await self._backend.fence(state)
        if not dispatch.dispatch_permitted:
            return _receipt_result(dispatch)
        try:
            result = await self._runtime.compile_project_guide(context)
        except ProjectGuideCompilationInvalidOutputError as exc:
            return _receipt_result(await self._backend.record_invalid(state, exc.failure_code))
        except Exception:  # noqa: BLE001 - unknown provider outcome stays unresolved
            return _receipt_result(dispatch)

        try:
            _require_valid_result(context, result)
        except (TypeError, ValueError):
            return _receipt_result(await self._backend.record_invalid(state, "schema_invalid"))

        await self._backend.record_accepted(state, context, result)
        return _receipt_result(await self._backend.persist(state, context))


def _require_valid_result(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    require_complete_project_guide_compilation_result(result)
    validate_project_guide_compilation_result(context, result)
    if result.agent_version != context.agent_version:
        raise ValueError("compilation result agent version is invalid")


def _state_result(
    state: CompilationExecutionState,
) -> ProjectGuideCompilationExecutionResult:
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
    return ProjectGuideCompilationExecutionResult(
        operation_id=receipt.operation_id,
        attempt_id=receipt.attempt_id,
        provider_idempotency_key=receipt.provider_idempotency_key,
        classification=ProjectGuideCompilationExecutionClassification(receipt.classification.value),
        compilation_id=(
            receipt.compilation_id if isinstance(receipt, CompilationPersistenceReceipt) else None
        ),
    )
