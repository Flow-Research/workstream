"""Command recovery distinguishes checked failure, unavailable custody and authority."""

from contextlib import asynccontextmanager
from dataclasses import asdict, replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
from app.core.identifiers import new_record_id

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.artifacts import CheckerPhaseService
from tests.checkers.execution.support import forbidden_post_submission
from fastapi import HTTPException
from starlette.requests import Request

import app.modules.artifacts.submission_admission as submission_admission_module
from app.api.routes.artifact_submissions import prepare_submission_bundle
from app.adapters.artifacts import (
    get_submission_bundle_preparation_actor,
    get_submission_bundle_preparation_command,
)
from app.main import create_app
from app.modules.artifacts.api import (
    SubmissionBundlePreparationCheckFailed,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationRejected, SubmissionBundlePreparationUnavailable,
    SubmissionBundlePreparationInfrastructureUnavailable, SubmissionBundlePreparationResult,
)
from app.modules.checkers.api import (
    PreSubmissionExecutionEntryFacts,
    PreSubmissionExecutionFacts,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict, PreSubmitEvidencePersistenceResult,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand, SubmissionBundlePreparationRuntime,
)
from tests.artifact_store_helpers import artifact_byte_stream
from tests.test_submission_bundle_admission import _actor, _transaction


def _feedback_facts(*, eligible: bool = False) -> PreSubmissionExecutionFacts:
    """Build exact canonical facts without defining another feedback contract."""
    statuses = (("passed", None, "passed"),) if eligible else (
        ("warning", None, "quality_signal_warning"),
        ("failed", "pre_submission_required_file_missing", "required_file_missing"),
        ("dependency_not_run", None, "dependency_not_run"),
    )
    return PreSubmissionExecutionFacts(
        plan_sha256="sha256:" + "1" * 64,
        eligible=eligible,
        entries=tuple(
            PreSubmissionExecutionEntryFacts(
                dispatch_authority="workstream.pre_submission_checker_catalogue",
                definition_id=f"workstream.test.{index}",
                definition_version="1.0.0",
                public_name=f"Test check {index}",
                policy_source="workstream_default",
                effective_plan_sha256="sha256:" + "1" * 64,
                rule_instance_id=None,
                locked_policy_sha256="sha256:" + "2" * 64,
                phase="default_policy",
                order=index,
                classification="advisory" if status == "warning" else "blocking",
                severity="warning" if status == "warning" else "blocking",
                checker_execution_status=status,
                failure_code=failure_code,
                message_code=message_code,
                metadata=(("finding_count", index + 1),) if not eligible else (),
            )
            for index, (status, failure_code, message_code) in enumerate(statuses)
        ),
    )


async def _mounted_preparation_response(error: RuntimeError):
    app = create_app()
    app.dependency_overrides[get_submission_bundle_preparation_actor] = _actor
    app.dependency_overrides[get_submission_bundle_preparation_command] = lambda: SimpleNamespace(
        prepare=AsyncMock(side_effect=error)
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
        "results": json.loads(json.dumps([asdict(entry) for entry in facts.entries])),
    }
    rendered = response.text
    assert all(value not in rendered for value in ("/tmp/", "s3://", "task.toml"))
    assert all(value not in rendered for value in ("accept", "needs_revision", "reject"))


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
    with pytest.raises(ValueError, match="require eligible false"):
        SubmissionBundlePreparationCheckFailed(
            replace(_feedback_facts(), eligible=eligible)  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status_code,detail", (
    (SubmissionBundlePreparationRejected("submission_bundle_preparation_context_changed"),
     409,"submission_bundle_preparation_context_changed"),
    (PreparedSubmissionBundlePreparationCommand._evidence_failure(
        PreSubmitEvidenceConflict("pre_submit_attempt_result_unavailable")),
     503,"pre_submission_checked_custody_unavailable"),
    (PreparedSubmissionBundlePreparationCommand._evidence_failure(
        PreSubmitEvidenceConflict("pre_submit_attempt_member_invalid")),
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
            assignment_id=str(new_record_id()),
            idempotency_key=str(new_record_id()),
            summary="summary",
            contributor_attestation="attestation",
        )

    assert failure.value.status_code == status_code
    assert failure.value.detail == detail



def _preparation_replay_runtime(prepare_bytes, evidence_id, *, eligible):
    """Supply bounded ART outcome doubles for command routing proof."""
    evidence = SimpleNamespace(
        reserve=AsyncMock(return_value=object()),
        execute_reserved=AsyncMock(return_value=PreSubmitEvidencePersistenceResult(
            evidence=SimpleNamespace(evidence_set_id=evidence_id),
            pass_capability=None, failure_audit=None,
            execution=SimpleNamespace(
                eligible=eligible,
                checker_facts=_feedback_facts(eligible=eligible),
            ),
        )),
    )
    checker_service = CheckerPhaseService(
        pre_submission=evidence, post_submission=forbidden_post_submission(),
    )
    checker_service.evaluate_pre_submission = AsyncMock(wraps=checker_service.evaluate_pre_submission)
    from app.modules.checkers.api import PostSubmissionEvaluationContent
    from tests.checkers.post_submit.support import request as evaluation_request
    content = evaluation_request().model_dump(include=set(PostSubmissionEvaluationContent.model_fields))
    return SubmissionBundlePreparationRuntime(
        evaluation_content=Mock(return_value=PostSubmissionEvaluationContent(**content)),
        checker_service=checker_service,
        preparation=SimpleNamespace(prepare=AsyncMock(side_effect=prepare_bytes)),
        inspector=object(),
        catalogue=object(),
        materialization=SimpleNamespace(prepare_authorization=AsyncMock(return_value=object())),
        evidence=evidence,
        durable_put=object(),
    )


async def _assert_blocked_feedback(command, request, runtime) -> None:
    with pytest.raises(
        SubmissionBundlePreparationCheckFailed,
        match="pre_submission_checker_failed",
    ) as failure:
        await command.prepare(request)
    assert (
        failure.value.facts
        == runtime.evidence.execute_reserved.return_value.execution.checker_facts
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ("completed", "blocked", "unresolved", "no_continuation", "corrupt_evidence"))
async def test_hidden_preparation_replays_persisted_checked_custody(monkeypatch, outcome) -> None:
    actor_id, task_id, assignment_id = new_record_id(), new_record_id(), new_record_id()
    evidence_id = new_record_id()
    expected = SubmissionBundlePreparationResult(
        put_attempt_id=new_record_id(),
        admission_id=new_record_id(),
        submission_bundle_preparation_status="ready",
        replayed=True,
    )
    locked = SimpleNamespace(effective_policy_id=new_record_id(), pre_submit_policy_id=new_record_id())
    prepared = SimpleNamespace(
        commitment=SimpleNamespace(sha256="sha256:" + "a" * 64),
        inspect=AsyncMock(return_value=object()),
        close=AsyncMock(),
    )
    events: list[str] = []

    async def prepare_bytes(*_args, **_kwargs):
        events.append("prepare_bytes")
        return prepared

    async def revalidate(**_kwargs):
        events.append("revalidate")

    runtime = _preparation_replay_runtime(prepare_bytes, evidence_id, eligible=outcome != "blocked")

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    monkeypatch.setattr(
        submission_admission_module,
        "build_submission_manifest",
        Mock(return_value=SimpleNamespace(file_facts=Mock(return_value=()))),
    )
    monkeypatch.setattr(
        submission_admission_module,
        "evaluate_submission_change",
        Mock(return_value=object()),
    )
    project_id = new_record_id()
    authority = SimpleNamespace(
        preflight=AsyncMock(), revalidate=AsyncMock(side_effect=revalidate), close=Mock()
    )
    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(begin=_transaction),
        authority=authority,
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=runtime_factory,
    )
    command._lock_context = AsyncMock(
        return_value=(
            SimpleNamespace(
                predecessor=None,
                locked_project_context=SimpleNamespace(project_id=project_id),
            ),
            locked,
        )
    )
    command._compile_plan = Mock(return_value=object())
    command._load_predecessor = AsyncMock(return_value=None)
    command._existing_durable_result = AsyncMock(return_value=expected)

    request = SubmissionBundlePreparationRequest(
            actor=ActorIdentityFacts(
                actor_profile_id=actor_id,
                identity_link_id=new_record_id(),
                actor_kind=ActorKind.HUMAN,
            ),
            request_id=new_record_id(),
            correlation_id=new_record_id(),
            task_id=task_id,
            assignment_id=assignment_id,
            predecessor_submission_id=None,
            idempotency_key=new_record_id(),
            summary="summary",
            contributor_attestation="attestation",
            media_type="application/zip",
            byte_source=artifact_byte_stream(b"PK\x03\x04replay"),
        )
    if outcome in {"unresolved", "corrupt_evidence"}:
        runtime.evidence.reserve.side_effect = PreSubmitEvidenceConflict(
            "pre_submit_attempt_outcome_unresolved" if outcome == "unresolved"
            else "pre_submit_attempt_result_digest_invalid"
        )
    if outcome == "no_continuation":
        command._existing_durable_result.return_value = None
    if outcome == "completed":
        runtime.evidence.reserve.return_value = runtime.evidence.execute_reserved.return_value
        assert await command.prepare(request) == expected
    elif outcome == "blocked":
        await _assert_blocked_feedback(command, request, runtime)
        command._existing_durable_result.assert_not_awaited()
    else:
        code = ("pre_submission_attempt_outcome_unresolved" if outcome == "unresolved"
                else "pre_submission_checked_custody_unavailable")
        with pytest.raises(SubmissionBundlePreparationInfrastructureUnavailable, match=code):
            await command.prepare(request)
    runtime.preparation.prepare.assert_awaited_once()
    assert authority.revalidate.await_args_list == [
        call(request=request, project_id=project_id),
        call(request=request, project_id=project_id),
    ]
    assert events[:2] == ["revalidate", "prepare_bytes"]
    runtime.evidence.reserve.assert_awaited_once()
    if outcome in {"unresolved", "corrupt_evidence"}:
        runtime.checker_service.evaluate_pre_submission.assert_not_awaited()
    else:
        runtime.checker_service.evaluate_pre_submission.assert_awaited_once()
        phase_request, selection = runtime.checker_service.evaluate_pre_submission.await_args.args
        assert phase_request.prepared_authorization is None
        assert selection is runtime.evidence.reserve.return_value
    if outcome in {"completed", "unresolved", "corrupt_evidence"}:
        runtime.evidence.execute_reserved.assert_not_awaited()
    else:
        runtime.evidence.execute_reserved.assert_awaited_once()
    prepared.close.assert_awaited_once()
    authority.close.assert_called_once_with()
