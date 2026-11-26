"""Current invocation and call-stable private evidence custody."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    EvaluationTaskGuard,
    ExecutionLease,
)
from app.modules.model_usage.api import (
    ModelCallCurrentExecutionPort,
    ModelCallExecutionFacts,
    ModelCallUnavailable,
    ModelEvidenceCustodyPort,
    ModelEvidenceSelector,
    ModelPaidSlotKey,
    ModelRecoverySourcePort,
)
from app.modules.checkers.api.output_custody import (
    CheckerOutputReservation,
    CheckerOutputSelector,
    CheckerOutputSlot,
    CheckerOutputTaskCustodyPort,
    CheckerOutputUnavailable,
)
from app.modules.checkers.execution_repository import (
    ExecutionRepository,
    require_transaction,
    reservation,
    stored_request,
)
from app.modules.checkers.models import CheckerRun


class ModelCallCurrentExecution:
    """Check the exact locked project binding before any paid effect is reserved."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        tasks: EvaluationTaskGuard,
        recovery: ModelRecoverySourcePort,
    ):
        self._session, self._tasks, self._recovery = session, tasks, recovery

    @staticmethod
    def _require_binding(request, slot: ModelPaidSlotKey) -> None:
        if request.assignment_id != slot.assignment_id or (
            slot.project_id,
            slot.submission_id,
            slot.submission_version,
        ) != (request.project_id, request.submission_id, request.submission_version):
            raise ModelCallUnavailable("model_call_execution_unavailable")
        bindings = [
            binding
            for binding in request.policy.entries
            if binding.requirement_id == slot.requirement_id
            and binding.registry.entry_digest == slot.registry_entry_digest
            and binding.configuration_sha256 == slot.configuration_sha256
        ]
        if len(bindings) != 1:
            raise ModelCallUnavailable("model_call_binding_unavailable")
        configuration = bindings[0].configuration
        if (
            configuration.get("model_profile_id") != str(slot.profile_id)
            or type(configuration.get("model_profile_version")) is not int
            or configuration.get("model_profile_version") != slot.profile_version
            or configuration.get("model_profile_digest") != slot.profile_digest
        ):
            raise ModelCallUnavailable("model_call_profile_unavailable")

    async def require_current(
        self,
        facts: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
    ) -> datetime:
        """Read immutable request facts, then lock TASK before the CHECKERS fence."""
        require_transaction(self._session)
        facts = ModelCallExecutionFacts.model_validate(facts)
        slot = ModelPaidSlotKey.model_validate(slot)
        run = await self._session.scalar(
            select(CheckerRun)
            .where(
                CheckerRun.id == str(facts.checker_run_id),
                CheckerRun.project_id == str(facts.project_id),
                CheckerRun.task_id == str(facts.task_id),
                CheckerRun.submission_id == str(facts.submission_id),
                CheckerRun.submission_version == facts.submission_version,
                CheckerRun.evaluation_request_id == str(facts.evaluation_request_id),
                CheckerRun.evaluation_generation == facts.evaluation_generation,
            )
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise ModelCallUnavailable("model_call_execution_unavailable")
        request = stored_request(run)
        if request.assignment_id != facts.assignment_id:
            raise ModelCallUnavailable("model_call_execution_unavailable")
        self._require_binding(request, slot)
        try:
            if not await self._tasks.lock_evaluation_scope(request):
                raise ModelCallUnavailable("model_call_execution_unavailable")
            await ExecutionRepository(self._session).require_lease(
                request,
                ExecutionLease(
                    reservation=reservation(run),
                    lease_id=facts.worker_lease_id,
                    lease_generation=facts.worker_lease_generation,
                    expires_at=facts.worker_lease_expires_at,
                ),
            )
        except CheckerExecutionUnavailable:
            raise ModelCallUnavailable("model_call_execution_unavailable") from None
        if run.worker_lease_live_until is None:
            raise ModelCallUnavailable("model_call_execution_unavailable")
        return run.worker_lease_live_until

    async def require_recovery_current(
        self, slot: ModelPaidSlotKey, parent_attempt_id: UUID
    ) -> None:
        """Lock current TASK/Submission custody for a terminal source, without a lease."""
        require_transaction(self._session)
        slot = ModelPaidSlotKey.model_validate(slot)
        try:
            source = await self._recovery.recovery_owner(slot, parent_attempt_id)
        except ModelCallUnavailable:
            raise ModelCallUnavailable("model_call_recovery_unavailable") from None
        run = await self._session.get(CheckerRun, str(source.checker_run_id))
        if (
            run is None
            or run.task_id != str(source.task_id)
            or run.status != "infrastructure_failed"
            or run.failure_code is None
            or run.completed_at is None
        ):
            raise ModelCallUnavailable("model_call_recovery_unavailable")
        try:
            request = stored_request(run)
        except (CheckerExecutionUnavailable, ValueError):
            raise ModelCallUnavailable("model_call_recovery_unavailable") from None
        if (
            source.execution.checker_run_id != UUID(run.id)
            or source.execution.task_id != source.task_id
        ):
            raise ModelCallUnavailable("model_call_recovery_unavailable")
        self._require_binding(request, slot)
        try:
            if not await self._tasks.lock_evaluation_scope(request):
                raise ModelCallUnavailable("model_call_recovery_unavailable")
        except CheckerExecutionUnavailable:
            raise ModelCallUnavailable("model_call_recovery_unavailable") from None


class CheckerOutputReservations:
    """Resolve two bounded ART roles under one immutable paid call identity."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        current: ModelCallCurrentExecutionPort,
        tasks: CheckerOutputTaskCustodyPort,
        model: ModelEvidenceCustodyPort,
    ):
        self._session, self._current = session, current
        self._tasks, self._model = tasks, model

    async def resolve(self, selector: CheckerOutputSelector) -> CheckerOutputReservation:
        """Requests require current execution; late responses retain effect custody."""
        require_transaction(self._session)
        selector = CheckerOutputSelector.model_validate(selector)
        if selector.execution is not None:
            await self._current.require_current(selector.execution, selector.paid_slot)
        else:
            await self._tasks.lock_model_evidence_scope(selector)
        try:
            reservation = await self._model.resolve_evidence(
                ModelEvidenceSelector(
                    paid_slot=selector.paid_slot,
                    task_id=selector.task_id,
                    model_call_slot_id=selector.model_call_slot_id,
                    model_call_attempt_id=selector.model_call_attempt_id,
                    role=selector.slot_key,
                    content_sha256=selector.content_sha256,
                )
            )
        except ModelCallUnavailable:
            raise CheckerOutputUnavailable("checker_output_reservation_unavailable") from None
        return CheckerOutputReservation(
            selector=selector,
            slot=CheckerOutputSlot(key=selector.slot_key, maximum_bytes=reservation.maximum_bytes),
        )
