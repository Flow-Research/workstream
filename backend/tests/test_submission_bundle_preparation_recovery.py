"""Command recovery distinguishes checked failure, unavailable custody and authority."""

from tests.trusted_intake_fixtures import LocalIntakeAdapter
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from app.core.identifiers import new_record_id

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi import HTTPException
from starlette.requests import Request

import app.modules.artifacts.submission_admission as submission_admission
from app.api.routes.artifact_submissions import prepare_submission_bundle
from app.adapters.artifacts import (
    get_submission_bundle_preparation_actor,
    get_submission_bundle_preparation_command,
)
from app.main import create_app
from app.db.session import get_db_session
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationCheckFailed,
    SubmissionBundlePreparationRejected, SubmissionBundlePreparationUnavailable,
    SubmissionBundlePreparationInfrastructureUnavailable, SubmissionBundlePreparationResult,
    SubmissionBundlePreparationStatus,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
    SubmissionBundlePreparationRuntime,
)
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveFailureCode,
    SubmissionArchiveRejectedError,
)
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
    return SelectedPreSubmitExecutionFacts(
        policy_sha256="sha256:" + "1" * 64, workstream_default=default,
        required_external_count=0, external_members=(), eligible=eligible,
    )


async def _mounted_preparation_response(error: RuntimeError):
    app = create_app()
    app.dependency_overrides[get_submission_bundle_preparation_actor] = _actor
    app.dependency_overrides[get_submission_bundle_preparation_command] = lambda: SimpleNamespace(
        prepare=AsyncMock(side_effect=error)
    )
    app.dependency_overrides[get_db_session] = lambda: SimpleNamespace(
        rollback=AsyncMock()
    )
    task_id, assignment_id, key = (new_record_id() for _ in range(3))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.post(
            f"/api/v1/tasks/{task_id}/submission-bundle-preparations",
            headers={
                "Content-Type": "application/zip",
                "X-Task-Assignment-Id": str(assignment_id),
                "Idempotency-Key": str(key),
                "X-Submission-Summary": "summary",
                "X-Contributor-Attestation": "attestation",
            },
            content=b"PK\x03\x04blocked",
        )


@pytest.mark.asyncio
async def test_mounted_preparation_returns_exact_ordered_bounded_feedback() -> None:
    facts = _feedback_facts()

    response = await _mounted_preparation_response(
        SubmissionBundlePreparationCheckFailed(facts)
    )

    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == "pre_submission_checker_failed"
    assert payload["error"]["message"] == "Pre-submission checks failed"
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
async def test_mounted_preparation_returns_sanitized_archive_rejection() -> None:
    response = await _mounted_preparation_response(
        SubmissionBundlePreparationRejected("submission_archive_malformed")
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == "submission_archive_malformed"
    assert payload["error"]["code"] == "invalid_request"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {}
    assert all(
        value not in response.text
        for value in ("/tmp/", "s3://", "BadZipFile", "not-a-readable-zip")
    )


@pytest.mark.asyncio
async def test_mounted_preparation_does_not_reclassify_unexpected_failure() -> None:
    command = SimpleNamespace(
        prepare=AsyncMock(side_effect=RuntimeError("unexpected inspector failure"))
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-type", b"application/zip")],
        }
    )

    with pytest.raises(RuntimeError, match="unexpected inspector failure"):
        await prepare_submission_bundle(
            task_id=str(new_record_id()),
            request=request,
            actor=_actor(),
            command=command,
            session=SimpleNamespace(rollback=AsyncMock()),
            assignment_id=str(new_record_id()),
            idempotency_key=str(new_record_id()),
            summary="summary",
            contributor_attestation="attestation",
        )


@asynccontextmanager
async def _transaction():
    yield


def _post_reservation_runtime_case():
    actor = _actor()
    request = SubmissionBundlePreparationRequest(
        actor=actor,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        predecessor_submission_id=None,
        idempotency_key=new_record_id(),
        summary="summary",
        contributor_attestation="attestation",
        media_type="application/zip",
        byte_source=SimpleNamespace(),
    )
    prepared = SimpleNamespace(
        generation_id=new_record_id(),
        commitment=SimpleNamespace(sha256="sha256:" + "1" * 64, byte_count=100),
        inspect=AsyncMock(return_value=object()),
        close=AsyncMock(),
    )
    policy = SimpleNamespace(policy_sha256="sha256:" + "a" * 64)
    selected = SimpleNamespace(
        policy=policy,
        default_input=object(),
        change_gate=object(),
    )
    reservation = SimpleNamespace(attempt_id=new_record_id())
    materialization = SimpleNamespace(
        prepare_selected_authorization=AsyncMock(return_value=object()),
        authorize_inspected=AsyncMock(),
    )
    coordinator = SimpleNamespace(
        read_current=AsyncMock(return_value=None),
        reserve=AsyncMock(return_value=reservation.attempt_id),
    )
    later_failure = SubmissionArchiveRejectedError(
        SubmissionArchiveFailureCode.INTEGRITY_FAILURE
    )
    selected_execution = SimpleNamespace(
        execute=AsyncMock(side_effect=later_failure),
    )
    durable_put = SimpleNamespace(
        admit_in_transaction=AsyncMock(),
        publish_after_commit=AsyncMock(),
    )
    runtime = SubmissionBundlePreparationRuntime(
        preparation=SimpleNamespace(prepare=AsyncMock(return_value=prepared)),
        intake=LocalIntakeAdapter(), archive_limits=SubmissionArchiveLimits(),
        materialization=materialization,
        durable_put=durable_put,
        selected_coordinator=coordinator,
        selected_execution=selected_execution,
        storage_scheme="s3",
        artifact_deadline_ms=120_000,
    )
    return SimpleNamespace(
        request=request,
        prepared=prepared,
        policy=policy,
        selected=selected,
        reservation=reservation,
        materialization=materialization,
        coordinator=coordinator,
        later_failure=later_failure,
        selected_execution=selected_execution,
        durable_put=durable_put,
        runtime=runtime,
    )


def _post_reservation_command(case, monkeypatch):
    @asynccontextmanager
    async def runtime_factory():
        yield case.runtime

    authority = SimpleNamespace(
        preflight=AsyncMock(),
        transaction=_transaction,
        close=Mock(),
    )
    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(begin=_transaction),
        authority=authority,
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=runtime_factory,
    )
    task = SimpleNamespace(
        predecessor=None,
        checker_remediation_manifest_id=None,
        revision_context=None,
    )
    project = SimpleNamespace(
        effective_policy_id=new_record_id(),
        pre_submit_policy_id=new_record_id(),
        external_checker_policies=SimpleNamespace(value="{}"),
    )
    command._lock_authorized_context = AsyncMock(return_value=(task, project))
    command._load_predecessor = AsyncMock(return_value=None)
    command._load_predecessor_rules = AsyncMock(return_value=None)
    monkeypatch.setattr(
        submission_admission,
        "LockedExternalCheckerPolicies",
        SimpleNamespace(
            model_validate_json=Mock(
                return_value=SimpleNamespace(pre_submit=case.policy)
            )
        ),
    )
    monkeypatch.setattr(
        submission_admission,
        "build_submission_manifest",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        submission_admission,
        "bind_selected_pre_submit_admission",
        Mock(return_value=case.selected),
    )
    monkeypatch.setattr(
        submission_admission,
        "build_selected_pre_submit_reservation",
        Mock(return_value=case.reservation),
    )
    monkeypatch.setattr(
        submission_admission,
        "selected_pre_submit_attempt_request_digest",
        Mock(return_value="sha256:" + "2" * 64),
    )
    monkeypatch.setattr(
        submission_admission,
        "selected_pre_submit_execution_budget_ms",
        Mock(return_value=60_000),
    )
    return command, authority


@pytest.mark.asyncio
async def test_post_reservation_archive_failure_remains_recoverable(
    monkeypatch,
) -> None:
    """A later projection failure must retain its reserved PRE recovery owner."""
    case = _post_reservation_runtime_case()
    command, authority = _post_reservation_command(case, monkeypatch)

    with pytest.raises(SubmissionArchiveRejectedError) as failure:
        await command.prepare(case.request)

    assert failure.value is case.later_failure
    case.materialization.authorize_inspected.assert_awaited_once()
    case.coordinator.reserve.assert_awaited_once_with(case.reservation)
    case.selected_execution.execute.assert_awaited_once()
    case.durable_put.admit_in_transaction.assert_not_awaited()
    case.durable_put.publish_after_commit.assert_not_awaited()
    case.prepared.close.assert_awaited_once()
    authority.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status_code,detail",
    (
        (
            SubmissionBundlePreparationRejected(
                "submission_bundle_preparation_context_changed"
            ),
            409,
            "submission_bundle_preparation_context_changed",
        ),
        (
            SubmissionBundlePreparationUnavailable(
                "submission bundle preparation is unavailable"
            ),
            404,
            "Task not found",
        ),
        (
            SubmissionBundlePreparationInfrastructureUnavailable(
                "pre_submission_attempt_outcome_unresolved"
            ),
            503,
            "pre_submission_attempt_outcome_unresolved",
        ),
        (
            SubmissionBundlePreparationInfrastructureUnavailable("deadline_exceeded"),
            503,
            "deadline_exceeded",
        ),
    ),
)
async def test_mounted_preparation_preserves_non_feedback_error_boundaries(
    error, status_code, detail,
) -> None:
    response = await _mounted_preparation_response(error)

    assert response.status_code == status_code
    payload = response.json()
    assert payload["detail"] == detail
    assert payload["error"]["details"] == {}
    assert "results" not in payload["error"]["details"]


@pytest.mark.parametrize("eligible", (True, 0, None))
def test_blocked_feedback_rejects_noncanonical_or_non_false_facts(eligible) -> None:
    with pytest.raises(TypeError, match="feedback facts are invalid"):
        SubmissionBundlePreparationCheckFailed(object())  # type: ignore[arg-type]
    from dataclasses import fields

    original = _feedback_facts()
    forged = object.__new__(SelectedPreSubmitExecutionFacts)
    for field in fields(original):
        object.__setattr__(forged, field.name, getattr(original, field.name))
    object.__setattr__(forged, "eligible", eligible)
    with pytest.raises(ValueError, match="require eligible false"):
        SubmissionBundlePreparationCheckFailed(forged)


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status_code,detail", (
    (SubmissionBundlePreparationRejected("submission_bundle_preparation_context_changed"),
     409,"submission_bundle_preparation_context_changed"),
    (SubmissionBundlePreparationInfrastructureUnavailable("pre_submission_checked_custody_unavailable"),
     503,"pre_submission_checked_custody_unavailable"),
    (SubmissionBundlePreparationInfrastructureUnavailable("pre_submission_attempt_outcome_unresolved"),
     503,"pre_submission_attempt_outcome_unresolved"),
    (SubmissionBundlePreparationUnavailable("submission bundle preparation is unavailable"),
     404,"Task not found"),
))
async def test_hidden_preparation_maps_context_custody_and_authority_distinctly(
    error, status_code, detail,
) -> None:
    command = SimpleNamespace(
        prepare=AsyncMock(
            side_effect=error
        )
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-type", b"application/zip")],
        }
    )

    with pytest.raises(HTTPException) as failure:
        await prepare_submission_bundle(
            task_id=str(new_record_id()),
            request=request,
            actor=_actor(),
            command=command,
            session=SimpleNamespace(rollback=AsyncMock()),
            assignment_id=str(new_record_id()),
            idempotency_key=str(new_record_id()),
            summary="summary",
            contributor_attestation="attestation",
        )

    assert failure.value.status_code == status_code
    assert failure.value.detail == detail


@pytest.mark.asyncio
async def test_hidden_preparation_treats_missing_optional_packet_text_as_warnings() -> None:
    """Missing summary and attestation reach PRE as empty warning-only values."""
    command = SimpleNamespace(prepare=AsyncMock(return_value=SubmissionBundlePreparationResult(
        put_attempt_id=new_record_id(), admission_id=None,
        submission_bundle_preparation_status=SubmissionBundlePreparationStatus.PREPARED,
        replayed=False, pre_submission_results=(),
    )))
    request = Request({
        "type": "http", "method": "POST", "path": "/",
        "headers": [(b"content-type", b"application/zip")],
    })

    await prepare_submission_bundle(
        task_id=str(new_record_id()), request=request, actor=_actor(), command=command,
        session=SimpleNamespace(rollback=AsyncMock()),
        assignment_id=str(new_record_id()), idempotency_key=str(new_record_id()),
        summary=None, contributor_attestation=None,
    )

    prepared = command.prepare.await_args.args[0]
    assert prepared.summary == ""
    assert prepared.contributor_attestation == ""
