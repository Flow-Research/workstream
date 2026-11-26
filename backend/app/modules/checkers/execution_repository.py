"""Exact CHECKERS custody reads and terminal writes in an existing transaction."""

import json
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func, select

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    EvaluationReservation,
    ExecutionLease,
)
from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    PostSubmissionExecutionResult,
    validate_stored_execution_request,
    validate_stored_execution_result,
)
from app.modules.checkers.api.canonical_values import canonical_checker_bytes
from app.modules.checkers.models import (
    CheckerResult, CheckerResultFinding, CheckerRun, CheckerSubmissionFence,
)


def require_transaction(session: AsyncSession) -> None:
    """Require an existing outer transaction so custody follows caller rollback."""
    if not session.in_transaction() or session.in_nested_transaction():
        raise CheckerExecutionUnavailable("checker_caller_transaction_required")


def request_text(request: PostSubmissionExecutionRequest) -> str:
    """Serialize canonical request facts without the separately stored digest."""
    return canonical_checker_bytes(request, exclude={"request_sha256"}).decode("utf-8")


def reservation(run: CheckerRun) -> EvaluationReservation:
    """Project durable identities without granting execution authority."""
    return EvaluationReservation(
        request_id=UUID(run.evaluation_request_id),
        request_digest=run.request_digest,
        attempt_id=UUID(run.id),
        result_id=UUID(run.result_id),
        evaluation_generation=run.evaluation_generation,
    )


def stored_request(run: CheckerRun) -> PostSubmissionExecutionRequest:
    """Reconstitute and validate the stored request with its digest."""
    body = json.loads(run.request_json)
    body["request_sha256"] = run.request_digest
    return validate_stored_execution_request(
        json.dumps(body, separators=(",", ":"), sort_keys=True)
    )


def stored_result(run: CheckerRun) -> PostSubmissionExecutionResult:
    """Validate retained results against their stored request and run identities."""
    if run.result_json is None or run.result_digest is None:
        raise CheckerExecutionUnavailable("checker_result_unavailable")
    body = json.loads(run.result_json)
    body["result_digest"] = run.result_digest
    result = validate_stored_execution_result(
        json.dumps(body, separators=(",", ":"), sort_keys=True)
    )
    result.validate_request(stored_request(run))
    if (str(result.attempt_id), str(result.result_id)) != (run.id, run.result_id):
        raise CheckerExecutionUnavailable("checker_result_unavailable")
    return result


class ExecutionRepository:
    """Read and write CHECKERS custody without owning transaction commits."""

    def __init__(self, session: AsyncSession):
        """Bind repository operations to the supplied transaction session."""
        self.session = session

    async def lock_current(self, request: PostSubmissionExecutionRequest) -> CheckerRun:
        """Qualify stored owner facts before locking the single fence, then run."""
        require_transaction(self.session)
        match = (
            select(CheckerRun.id)
            .where(
                CheckerRun.id == CheckerSubmissionFence.current_run_id,
                CheckerRun.submission_id == str(request.submission_id),
                CheckerRun.task_id == str(request.task_id),
                CheckerRun.project_id == str(request.project_id),
                CheckerRun.evaluation_request_id == str(request.evaluation_request_id),
                CheckerRun.evaluation_generation == request.evaluation_generation,
                CheckerRun.request_digest == request.request_sha256,
            )
            .exists()
        )
        fence = await self.session.scalar(
            select(CheckerSubmissionFence)
            .where(
                CheckerSubmissionFence.submission_id == str(request.submission_id),
                match,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if fence is None:
            raise CheckerExecutionUnavailable("checker_current_request_unavailable")
        run = await self.session.scalar(
            select(CheckerRun)
            .where(
                CheckerRun.id == fence.current_run_id,
                CheckerRun.submission_id == str(request.submission_id),
                CheckerRun.task_id == str(request.task_id),
                CheckerRun.project_id == str(request.project_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            run is None
            or run.request_digest != request.request_sha256
            or run.request_json != request_text(request)
        ):
            raise CheckerExecutionUnavailable("checker_current_request_unavailable")
        return run

    async def now(self) -> datetime:
        """Use PostgreSQL wall time for lease decisions."""
        return await self.session.scalar(select(func.clock_timestamp()))

    async def require_lease(
        self, request: PostSubmissionExecutionRequest, lease: ExecutionLease
    ) -> CheckerRun:
        """Lock current custody and reject stale, expired or substituted leases."""
        run = await self.lock_current(request)
        if (
            run.status != "running"
            or reservation(run) != lease.reservation
            or run.worker_lease_id != str(lease.lease_id)
            or run.worker_lease_generation != lease.lease_generation
            or run.worker_lease_expires_at != lease.expires_at
            or run.worker_lease_live_until <= await self.now()
        ):
            raise CheckerExecutionUnavailable("checker_execution_lease_unavailable")
        return run

    async def write_members(self, run: CheckerRun, result: PostSubmissionExecutionResult) -> None:
        """Flush ordered closed results under the locked running parent."""
        for member in result.execution.external_members if result.execution else ():
            member_id = str(new_record_id())
            self.session.add(
                CheckerResult(
                    id=member_id,
                    checker_run_id=run.id,
                    task_id=run.task_id,
                    submission_id=run.submission_id,
                    member_order=member.order,
                    checker_name=member.requirement_id,
                    definition_version=member.result.schema_version,
                    implementation_version=member.registry_entry_digest,
                    status=member.result.verdict or "infrastructure_failed",
                    code=(
                        "passed"
                        if member.result.verdict == "passed"
                        else member.result.findings[0].code
                        if member.result.findings
                        else "invalid_output"
                    ),
                    failure_category=(
                        "none" if member.result.verdict == "passed" else "submission_structure"
                    ),
                    severity=("info" if member.result.verdict == "passed" else "error"),
                    counters=[],
                )
            )
            for finding_order, finding in enumerate(member.result.findings):
                self.session.add(
                    CheckerResultFinding(
                        id=str(new_record_id()),
                        checker_result_id=member_id,
                        checker_run_id=run.id,
                        task_id=run.task_id,
                        submission_id=run.submission_id,
                        member_order=member.order,
                        finding_order=finding_order,
                        check_id=finding.check_id,
                        code=finding.code,
                        level=finding.level,
                        path=finding.path,
                        line=finding.line,
                    )
                )
        await self.session.flush()
