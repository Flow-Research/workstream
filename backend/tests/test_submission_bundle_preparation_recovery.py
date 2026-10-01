"""Command recovery distinguishes checked failure, unavailable custody and authority."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
from app.core.identifiers import new_record_id

import pytest

from app.adapters.artifacts import CheckerPhaseService
from tests.checkers.execution.support import forbidden_post_submission
from fastapi import HTTPException
from starlette.requests import Request

import app.modules.artifacts.submission_admission as submission_admission_module
from app.api.routes.artifact_submissions import prepare_submission_bundle
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationRejected, SubmissionBundlePreparationUnavailable,
    SubmissionBundlePreparationInfrastructureUnavailable, SubmissionBundlePreparationResult,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict, PreSubmitEvidencePersistenceResult,
)
from app.modules.artifacts.submission_admission import PreparedSubmissionBundlePreparationCommand
from tests.artifact_store_helpers import artifact_byte_stream
from tests.test_submission_bundle_admission import _actor, _transaction


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
    runtime = SimpleNamespace(
        preparation=SimpleNamespace(prepare=AsyncMock(side_effect=prepare_bytes)),
        inspector=object(),
        catalogue=object(),
        materialization=SimpleNamespace(prepare_authorization=AsyncMock(return_value=object())),
        evidence=SimpleNamespace(
            reserve=AsyncMock(return_value=object()),
            execute_reserved=AsyncMock(
                return_value=PreSubmitEvidencePersistenceResult(
                    evidence=SimpleNamespace(evidence_set_id=evidence_id),
                    pass_capability=None, failure_audit=None,
                    execution=SimpleNamespace(eligible=eligible),
                )
            ),
        ),
        durable_put=object(),
    )

    runtime.checker_service = CheckerPhaseService(
        pre_submission=runtime.evidence,
        post_submission=forbidden_post_submission(),
    )
    runtime.checker_service.evaluate_pre_submission = AsyncMock(
        wraps=runtime.checker_service.evaluate_pre_submission,
    )
    return runtime


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
        commitment=object(),
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
        Mock(return_value=object()),
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
        with pytest.raises(SubmissionBundlePreparationRejected, match="pre_submission_checker_failed"):
            await command.prepare(request)
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
