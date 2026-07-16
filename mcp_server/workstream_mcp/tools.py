"""Mutating MCP tool handlers."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from workstream_mcp.auth import RequestContext, redact_context_secrets
from workstream_mcp.errors import WorkstreamMCPError
from workstream_mcp.gateway import ContributorGateway
from workstream_mcp.schemas import (
    CandidateSubmissionInput,
    ClaimReviewInput,
    ClaimTaskInput,
    OperationResult,
    ReleaseReviewInput,
    ReleaseTaskInput,
    SubmitReviewInput,
)


async def claim_task(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Claim responsibility for a task without starting a second transition."""
    parsed = _validate_input(context, ClaimTaskInput, task_id=task_id, request_id=request_id)
    if isinstance(parsed, dict):
        return parsed
    try:
        data = await gateway.claim_task(
            context,
            task_id=parsed.task_id,
            request_id=parsed.request_id,
        )
        return _safe_result(
            context,
            OperationResult(
                operation="claim_task",
                outcome="claimed",
                workstream_ref=parsed.task_id,
                next_resource=f"workstream://tasks/{parsed.task_id}/context",
                data={"task_claim": data},
                summary="Task claimed. Read Task Context before performing the work.",
            ).model_dump(),
        )
    except WorkstreamMCPError as exc:
        return _safe_result(context, exc.to_result())


async def release_task(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
    request_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Release a claimed task when Workstream permits release."""
    parsed = _validate_input(
        context,
        ReleaseTaskInput,
        task_id=task_id,
        request_id=request_id,
        reason=reason,
    )
    if isinstance(parsed, dict):
        return parsed
    try:
        data = await gateway.release_task(
            context,
            task_id=parsed.task_id,
            request_id=parsed.request_id,
            reason=parsed.reason,
        )
        return _safe_result(
            context,
            OperationResult(
                operation="release_task",
                outcome="released",
                workstream_ref=parsed.task_id,
                next_resource="workstream://tasks",
                data={"task_release": data},
                summary="Task release was accepted by Workstream.",
            ).model_dump(),
        )
    except WorkstreamMCPError as exc:
        return _safe_result(context, exc.to_result())


async def run_pre_submit_check(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
    submission: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    """Run pre-submit feedback without creating a submission."""
    parsed = _validate_input(
        context,
        CandidateSubmissionInput,
        task_id=task_id,
        submission=submission,
        request_id=request_id,
    )
    if isinstance(parsed, dict):
        return parsed
    try:
        data = await gateway.run_pre_submit_check(
            context,
            task_id=parsed.task_id,
            submission=parsed.submission,
            request_id=parsed.request_id,
        )
        passed = data.get("status") == "passed" or data.get("eligible_to_submit") is True
        return _safe_result(
            context,
            OperationResult(
                operation="run_pre_submit_check",
                outcome="passed" if passed else "pre_submit_check_failed",
                workstream_ref=parsed.task_id,
                next_resource=(
                    f"workstream://tasks/{parsed.task_id}/status"
                    if passed
                    else f"workstream://tasks/{parsed.task_id}/context"
                ),
                data={"pre_submit_check": data},
                summary=(
                    "Candidate packet passed pre-submit checks."
                    if passed
                    else "Candidate packet did not pass pre-submit checks."
                ),
            ).model_dump(),
        )
    except WorkstreamMCPError as exc:
        return _safe_result(context, exc.to_result())


async def submit_task(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
    submission: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    """Submit an initial or revised packet through the same operation."""
    parsed = _validate_input(
        context,
        CandidateSubmissionInput,
        task_id=task_id,
        submission=submission,
        request_id=request_id,
    )
    if isinstance(parsed, dict):
        return parsed
    try:
        data = await gateway.submit_task(
            context,
            task_id=parsed.task_id,
            submission=parsed.submission,
            request_id=parsed.request_id,
        )
        submission_ref = data.get("id") if isinstance(data, dict) else None
        return _safe_result(
            context,
            OperationResult(
                operation="submit_task",
                outcome="submitted",
                workstream_ref=submission_ref or parsed.task_id,
                next_resource=f"workstream://tasks/{parsed.task_id}/status",
                data={"submission": data},
                summary="Submission was accepted by Workstream.",
            ).model_dump(),
        )
    except WorkstreamMCPError as exc:
        return _safe_result(context, exc.to_result())


async def claim_review(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    project_id: str,
    review_routing_ref: str,
    request_id: str,
) -> dict[str, Any]:
    """Claim the currently offered review."""
    parsed = _validate_input(
        context,
        ClaimReviewInput,
        project_id=project_id,
        review_routing_ref=review_routing_ref,
        request_id=request_id,
    )
    if isinstance(parsed, dict):
        return parsed
    try:
        data = await gateway.claim_review(
            context,
            project_id=parsed.project_id,
            review_routing_ref=parsed.review_routing_ref,
            request_id=parsed.request_id,
        )
        review_ref = data.get("review_ref")
        return _safe_result(
            context,
            OperationResult(
                operation="claim_review",
                outcome="leased_to_actor",
                workstream_ref=review_ref,
                next_resource=data.get("next_resource"),
                data={"review_claim": data},
                summary="Review leased to the current actor.",
            ).model_dump(),
        )
    except WorkstreamMCPError as exc:
        return _safe_result(context, exc.to_result())


async def release_review(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    review_ref: str,
    request_id: str,
) -> dict[str, Any]:
    """Release the actor's current review lease."""
    parsed = _validate_input(
        context,
        ReleaseReviewInput,
        review_ref=review_ref,
        request_id=request_id,
    )
    if isinstance(parsed, dict):
        return parsed
    try:
        data = await gateway.release_review(
            context,
            review_ref=parsed.review_ref,
            request_id=parsed.request_id,
        )
        return _safe_result(
            context,
            OperationResult(
                operation="release_review",
                outcome="released",
                workstream_ref=parsed.review_ref,
                next_resource=None,
                data={"review_release": data},
                summary="Review lease was released.",
            ).model_dump(),
        )
    except WorkstreamMCPError as exc:
        return _safe_result(context, exc.to_result())


async def submit_review(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    review_ref: str,
    decision: str,
    findings: list[dict[str, Any]],
    request_id: str,
) -> dict[str, Any]:
    """Submit one human review decision."""
    parsed = _validate_input(
        context,
        SubmitReviewInput,
        review_ref=review_ref,
        decision=decision,
        findings=findings,
        request_id=request_id,
    )
    if isinstance(parsed, dict):
        return parsed
    try:
        data = await gateway.submit_review(
            context,
            review_ref=parsed.review_ref,
            decision=parsed.decision,
            findings=parsed.findings,
            request_id=parsed.request_id,
        )
        return _safe_result(
            context,
            OperationResult(
                operation="submit_review",
                outcome=parsed.decision,
                workstream_ref=parsed.review_ref,
                next_resource=None,
                data={"review_decision": data},
                summary="Review decision was accepted.",
            ).model_dump(),
        )
    except WorkstreamMCPError as exc:
        return _safe_result(context, exc.to_result())


def _safe_result(context: RequestContext, result: dict[str, Any]) -> dict[str, Any]:
    """Redact bearer material from every MCP tool result."""
    return redact_context_secrets(result, context)


def _validate_input(
    context: RequestContext,
    schema: type[Any],
    **values: Any,
) -> Any | dict[str, Any]:
    """Validate tool inputs before they reach a gateway."""
    try:
        return schema.model_validate(values)
    except ValidationError as exc:
        return _safe_result(
            context,
            {
                "error": {
                    "code": "invalid_tool_input",
                    "message": "Tool input failed validation.",
                    "retryable": False,
                    "correlation_id": context.correlation_id,
                    "next_resource": None,
                    "details": {"validation_errors": exc.errors(include_input=False)},
                }
            },
        )
