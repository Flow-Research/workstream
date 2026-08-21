"""Focused state-machine tests for hidden unified compilation."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
)
from app.modules.authorization.api import ProjectGuideCompilationExecutePreflightFacts
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideCompilationExecutionCommand,
)
from app.modules.projects.guide_compilation.contracts import (
    CompilationDispatchReceipt,
    CompilationExecutionState,
    CompilationOutcomeReceipt,
    CompilationPersistenceReceipt,
    CompilationRecoveryClassification,
)
from app.modules.projects.guide_compilation.orchestrator import (
    HiddenGuideCompilationOrchestrator,
)

from .helpers import context, identity, ids, persistence_facts, result


def _state(
    values: dict[str, UUID],
    classification: CompilationRecoveryClassification,
    *,
    compilation_id: UUID | None = None,
) -> CompilationExecutionState:
    attempt_id = uuid4()
    compilation_identity = identity(context(values))
    complete = persistence_facts(values, attempt_id, compilation_identity)
    names = ProjectGuideCompilationExecutePreflightFacts.__dataclass_fields__
    return CompilationExecutionState(
        identity=compilation_identity,
        preflight_facts=ProjectGuideCompilationExecutePreflightFacts(
            **{name: asdict(complete)[name] for name in names}
        ),
        classification=classification,
        compilation_id=compilation_id,
    )


class _Backend:
    def __init__(self, state: CompilationExecutionState) -> None:
        self.state = state
        self.context_value = context(
            {
                **ids(),
                "project": state.identity.project_id,
                "guide": state.identity.guide_id,
                "snapshot": state.identity.source_snapshot_id,
                "setup_1": state.identity.setup_run_id,
            }
        )
        self.calls: list[str] = []
        self.dispatch_permitted = True

    async def load(self, attempt_id):
        self.calls.append("load")
        assert attempt_id == self.state.preflight_facts.attempt_id
        return self.state

    async def context(self, state):
        self.calls.append("context")
        assert state is self.state
        return self.context_value

    async def fence(self, state):
        self.calls.append("fence")
        facts = state.preflight_facts
        return CompilationDispatchReceipt(
            operation_id=facts.operation_id,
            attempt_id=facts.attempt_id,
            provider_idempotency_key=facts.provider_idempotency_key,
            classification=CompilationRecoveryClassification.PROVIDER_UNCERTAIN,
            dispatch_permitted=self.dispatch_permitted,
        )

    async def record_accepted(self, state, context_value, result_value):
        self.calls.append("record_accepted")
        assert context_value is self.context_value
        assert result_value == result()
        facts = state.preflight_facts
        return CompilationOutcomeReceipt(
            operation_id=facts.operation_id,
            attempt_id=facts.attempt_id,
            provider_idempotency_key=facts.provider_idempotency_key,
            classification=CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED,
        )

    async def record_invalid(self, state, failure_code):
        self.calls.append(f"record_invalid:{failure_code}")
        facts = state.preflight_facts
        return CompilationOutcomeReceipt(
            operation_id=facts.operation_id,
            attempt_id=facts.attempt_id,
            provider_idempotency_key=facts.provider_idempotency_key,
            classification=CompilationRecoveryClassification.INVALID_TERMINAL,
        )

    async def persist(self, state, context_value):
        self.calls.append("persist")
        assert context_value is self.context_value
        facts = state.preflight_facts
        return CompilationPersistenceReceipt(
            operation_id=facts.operation_id,
            attempt_id=facts.attempt_id,
            provider_idempotency_key=facts.provider_idempotency_key,
            classification=CompilationRecoveryClassification.PERSISTED,
            compilation_id=uuid4(),
        )


class _Runtime:
    def __init__(self, outcome=result()) -> None:
        self.outcome = outcome
        self.calls = 0

    async def compile_project_guide(self, _context):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.mark.asyncio
async def test_reserved_attempt_calls_the_unified_runtime_once_and_persists() -> None:
    values = ids()
    state = _state(values, CompilationRecoveryClassification.RESERVED)
    backend, runtime = _Backend(state), _Runtime()

    receipt = await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=state.preflight_facts.attempt_id)
    )

    assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
    assert receipt.compilation_id is not None
    assert runtime.calls == 1
    assert backend.calls == [
        "load",
        "context",
        "fence",
        "record_accepted",
        "persist",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "classification",
    [
        CompilationRecoveryClassification.PROVIDER_UNCERTAIN,
        CompilationRecoveryClassification.INVALID_TERMINAL,
        CompilationRecoveryClassification.PERSISTED,
    ],
)
async def test_terminal_or_uncertain_state_never_rebuilds_or_redispatches(
    classification,
) -> None:
    state = _state(
        ids(),
        classification,
        compilation_id=uuid4()
        if classification is CompilationRecoveryClassification.PERSISTED
        else None,
    )
    backend, runtime = _Backend(state), _Runtime()

    receipt = await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=state.preflight_facts.attempt_id)
    )

    assert receipt.classification.value == classification.value
    assert runtime.calls == 0
    assert backend.calls == ["load"]


@pytest.mark.asyncio
async def test_accepted_recovery_rebuilds_context_but_never_calls_provider() -> None:
    state = _state(ids(), CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED)
    backend, runtime = _Backend(state), _Runtime()

    receipt = await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=state.preflight_facts.attempt_id)
    )

    assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
    assert runtime.calls == 0
    assert backend.calls == ["load", "context", "persist"]


@pytest.mark.asyncio
async def test_existing_dispatch_fence_never_calls_provider() -> None:
    state = _state(ids(), CompilationRecoveryClassification.RESERVED)
    backend, runtime = _Backend(state), _Runtime()
    backend.dispatch_permitted = False

    receipt = await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
        ProjectGuideCompilationExecutionCommand(
            attempt_id=state.preflight_facts.attempt_id
        )
    )

    assert (
        receipt.classification
        is ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED
    )
    assert runtime.calls == 0
    assert backend.calls == ["load", "context", "fence"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_failure", "expected_call"),
    [
        (
            ProjectGuideCompilationInvalidOutputError("unsafe_text"),
            "record_invalid:unsafe_text",
        ),
        (
            ProjectGuideCompilationInvalidOutputError("schema_invalid"),
            "record_invalid:schema_invalid",
        ),
    ],
)
async def test_known_invalid_output_terminalizes_without_persistence(
    provider_failure, expected_call
) -> None:
    state = _state(ids(), CompilationRecoveryClassification.RESERVED)
    backend, runtime = _Backend(state), _Runtime(provider_failure)

    receipt = await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=state.preflight_facts.attempt_id)
    )

    assert receipt.classification is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
    assert runtime.calls == 1
    assert backend.calls[-1] == expected_call
    assert "persist" not in backend.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_failure",
    [
        ProjectAgentRuntimeError("unavailable"),
        ValueError("unexpected provider value error"),
        RuntimeError("unexpected provider runtime error"),
    ],
)
async def test_provider_failure_remains_unresolved_and_never_persists(
    provider_failure: Exception,
) -> None:
    state = _state(ids(), CompilationRecoveryClassification.RESERVED)
    backend, runtime = _Backend(state), _Runtime(provider_failure)

    receipt = await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=state.preflight_facts.attempt_id)
    )

    assert (
        receipt.classification is ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED
    )
    assert backend.calls == ["load", "context", "fence"]


@pytest.mark.asyncio
async def test_incomplete_defaulted_result_is_rejected_after_provider_return() -> None:
    state = _state(ids(), CompilationRecoveryClassification.RESERVED)
    partial = ProjectGuideCompilationResult(
        status="guide_blocked",
        agent_version="v1",
    )
    backend, runtime = _Backend(state), _Runtime(partial)

    receipt = await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=state.preflight_facts.attempt_id)
    )

    assert receipt.classification is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
    assert backend.calls[-1] == "record_invalid:schema_invalid"


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_after_the_durable_fence() -> None:
    state = _state(ids(), CompilationRecoveryClassification.RESERVED)
    backend, runtime = _Backend(state), _Runtime(asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await HiddenGuideCompilationOrchestrator(backend, runtime).execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=state.preflight_facts.attempt_id)
        )
    assert backend.calls == ["load", "context", "fence"]


def test_public_command_rejects_caller_supplied_context_or_authority() -> None:
    with pytest.raises(ValidationError):
        ProjectGuideCompilationExecutionCommand(
            attempt_id=uuid4(),
            project_id=uuid4(),  # type: ignore[call-arg]
        )
