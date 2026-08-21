"""Small hidden state machine for one authorized unified compilation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideAgentRuntime,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    require_complete_project_guide_compilation_result,
    validate_project_guide_compilation_result,
)
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideCompilationExecutionPort,
    ProjectGuideCompilationExecutionResult,
)

from .contracts import (
    CompilationDispatchReceipt,
    CompilationExecutionState,
    CompilationOutcomeReceipt,
    CompilationPersistenceReceipt,
    CompilationRecoveryClassification,
)


class GuideCompilationExecutionBackend(Protocol):
    """Exact persistence/context operations required by the state machine."""

    async def load(self, attempt_id: UUID) -> CompilationExecutionState: ...

    async def context(
        self, state: CompilationExecutionState
    ) -> ProjectGuideCompilationContext: ...

    async def fence(
        self, state: CompilationExecutionState
    ) -> CompilationDispatchReceipt: ...

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
        if (
            state.classification
            is CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED
        ):
            return _receipt_result(await self._backend.persist(state, context))

        dispatch = await self._backend.fence(state)
        if not dispatch.dispatch_permitted:
            return _receipt_result(dispatch)
        try:
            result = await self._runtime.compile_project_guide(context)
            _require_valid_result(context, result)
        except ProjectGuideCompilationInvalidOutputError as exc:
            return _receipt_result(
                await self._backend.record_invalid(state, exc.failure_code)
            )
        except ValueError:
            return _receipt_result(
                await self._backend.record_invalid(state, "schema_invalid")
            )
        except ProjectAgentRuntimeError:
            return _receipt_result(dispatch)

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
        classification=ProjectGuideCompilationExecutionClassification(
            state.classification.value
        ),
        compilation_id=state.compilation_id,
    )


def _receipt_result(
    receipt: CompilationDispatchReceipt
    | CompilationOutcomeReceipt
    | CompilationPersistenceReceipt,
) -> ProjectGuideCompilationExecutionResult:
    return ProjectGuideCompilationExecutionResult(
        operation_id=receipt.operation_id,
        attempt_id=receipt.attempt_id,
        provider_idempotency_key=receipt.provider_idempotency_key,
        classification=ProjectGuideCompilationExecutionClassification(
            receipt.classification.value
        ),
        compilation_id=(
            receipt.compilation_id
            if isinstance(receipt, CompilationPersistenceReceipt)
            else None
        ),
    )
