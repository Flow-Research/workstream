"""Command recovery distinguishes checked failure, unavailable custody and authority."""

from app.adapters.artifacts import selected_pre_submit_source_contracts


from types import SimpleNamespace
from unittest.mock import AsyncMock
from app.core.identifiers import new_record_id

import pytest
from httpx import ASGITransport, AsyncClient


from app.api.deps.authorization import get_authorization_actor_identity
from app.adapters.artifacts import get_submission_intake_command
from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from app.main import create_app
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256, WORKSTREAM_DEFAULT_CHECK_IDS,
    WorkstreamDefaultCheckerResult,
)
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitExecutionFacts
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
def _actor():
    return ActorIdentityFacts(new_record_id(), new_record_id(), ActorKind.HUMAN)


def _feedback_facts(*, eligible: bool = False) -> SelectedPreSubmitExecutionFacts:
    """Use the sole selected default result shape for sanitized HTTP feedback."""
    checks = tuple({
        "check_id": check_id,
        "status": ("passed" if eligible or index < 2 else "failed" if index == 2 else "not_run"),
        "failure_code": "high_confidence_secret_detected" if not eligible and index == 2 else None,
        "finding_count": 1 if not eligible and index == 2 else 0,
    } for index, check_id in enumerate(WORKSTREAM_DEFAULT_CHECK_IDS))
    default = WorkstreamDefaultCheckerResult(
        behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        eligible=eligible, checks=checks,
        warnings=({"code": "submission_summary_missing"}, {"code": "submission_attestation_missing"}),
    )
    from dataclasses import replace
    from tests.checkers.external.test_selected_pre_submit_coordination import (
        _source_completed_execution, _source_reservation,
    )
    execution = _source_completed_execution(_source_reservation())
    return replace(
        execution, workstream_default=default, eligible=eligible,
        external_members=execution.external_members if eligible else (),
        source_contracts=selected_pre_submit_source_contracts(),
    )


async def _mounted_submission_response(error=None, *, command=None, packet_text=True):
    app = create_app()
    app.dependency_overrides[get_authorization_actor_identity] = _actor
    command = command or SimpleNamespace(submit=AsyncMock(side_effect=error))
    app.dependency_overrides[get_submission_intake_command] = lambda: command
    task_id, assignment_id, key = (new_record_id() for _ in range(3))
    headers = {
        "Content-Type": "application/zip",
        "X-Task-Assignment-Id": str(assignment_id),
        "Idempotency-Key": str(key),
    }
    if packet_text:
        headers["X-Submission-Feedback"] = "feedback"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.post(
            f"/api/v1/tasks/{task_id}/submissions",
            headers=headers, content=b"PK\x03\x04blocked",
        )


@pytest.mark.asyncio
async def test_mounted_submission_returns_exact_ordered_bounded_feedback() -> None:
    facts = _feedback_facts()

    response = await _mounted_submission_response(
        SubmissionIntakeFailure("pre_submission_checker_failed",
                                pre_submission_results=public_pre_submission_results(facts))
    )

    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == "pre_submission_checker_failed"
    assert payload["error"]["message"] == "pre_submission_checker_failed"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {
        "status": "failed",
        "eligible_to_submit": False,
        "results": [
            {"source": "workstream_default", **check.model_dump(mode="json")}
            for check in facts.workstream_default.checks
        ] + [
            {"source": "workstream_default", "status": "warning", "warning_code": warning.code}
            for warning in facts.workstream_default.warnings
        ],
    }
    rendered = response.text
    assert all(value not in rendered for value in ("/tmp/", "s3://", "task.toml"))
    assert all(value not in rendered for value in ("accept", "needs_revision", "reject"))


@pytest.mark.asyncio
async def test_mounted_submission_returns_sanitized_archive_rejection() -> None:
    response = await _mounted_submission_response(
        SubmissionIntakeFailure("submission_packet_invalid")
    )

    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == "submission_packet_invalid"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {}
    assert all(
        value not in response.text
        for value in ("/tmp/", "s3://", "BadZipFile", "not-a-readable-zip")
    )


@pytest.mark.asyncio
async def test_mounted_submission_does_not_reclassify_unexpected_failure() -> None:
    from starlette.requests import Request
    from app.api.routes.artifact_submissions import submit_source
    from app.api.submission_intake import SubmissionIntakeHeaders
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata

    metadata = SubmissionIntakeMetadata(task_id=new_record_id(), assignment_id=new_record_id())
    command = SimpleNamespace(submit=AsyncMock(side_effect=RuntimeError("unexpected inspector failure")))
    with pytest.raises(RuntimeError, match="unexpected inspector failure"):
        await submit_source(
            task_id=metadata.task_id, request=Request({"type": "http", "headers": []}),
            headers=SubmissionIntakeHeaders(metadata, new_record_id(), None),
            actor=_actor(), command=command,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status_code,retryable", (
    ("submission_operation_in_progress", 409, False),
    ("submission_unavailable", 404, False),
    ("submission_outcome_unknown", 503, True),
    ("submission_upload_timeout", 408, False),
    ("submission_infrastructure_unavailable", 503, True),
    ("submission_capacity_exceeded", 429, True),
    ("submission_archive_limit_exceeded", 413, False),
))
async def test_mounted_submission_preserves_non_feedback_error_boundaries(
    code, status_code, retryable,
) -> None:
    response = await _mounted_submission_response(SubmissionIntakeFailure(code))
    assert response.status_code == status_code
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == code
    assert payload["error"]["retryable"] is retryable
    assert payload["error"]["details"] == {}
    assert "results" not in payload["error"]["details"]


@pytest.mark.asyncio
async def test_mounted_submission_keeps_missing_optional_packet_text_warning_only() -> None:
    """Missing summary and attestation reach PRE as empty warning-only values."""
    from datetime import UTC, datetime

    async def accept(metadata, chunks, **kwargs):
        return {
            "operation_id": new_record_id(), "task_id": metadata.task_id,
            "assignment_id": metadata.assignment_id, "status": "accepted",
            "accepted_at": datetime.now(UTC), "task_status_at_acceptance": "evaluation_pending",
            "processing_stage_at_acceptance": "finalization_pending", "replayed": False,
            "pre_submission_results": public_pre_submission_results(_feedback_facts(eligible=True)),
        }

    command = SimpleNamespace(submit=AsyncMock(side_effect=accept))
    response = await _mounted_submission_response(command=command, packet_text=False)
    assert response.status_code == 202
    submitted = command.submit.await_args.args[0]
    assert submitted.summary == ""
    assert submitted.contributor_attestation == ""
    warnings = [item["warning_code"] for item in response.json()["pre_submission_results"]
                if item["status"] == "warning"]
    assert warnings == ["submission_summary_missing", "submission_attestation_missing"]
