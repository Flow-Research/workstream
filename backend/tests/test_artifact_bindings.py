"""Focused proof for ART-owned ready-admission consumption and binding."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionError,
    SubmissionAdmissionConsumptionRequest,
)
from app.modules.artifacts.submission_bindings import (
    SubmissionAdmissionConsumptionService,
)
from app.modules.tasks.api import (
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
)


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _request(*, submission_id=None) -> SubmissionAdmissionConsumptionRequest:
    references = TaskLockedProjectContextReferences(
        project_id=uuid4(),
        guide_version="1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash=_sha("1"),
        effective_policy_id=uuid4(),
        effective_policy_hash=_sha("2"),
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash=_sha("3"),
    )
    return SubmissionAdmissionConsumptionRequest(
        admission_id=uuid4(),
        submission_id=submission_id or uuid4(),
        submission_version=1,
        task_context=TaskSubmissionContextFacts(
            task_id=uuid4(),
            assignment_id=uuid4(),
            contributor_id=uuid4(),
            status="in_progress",
            kind="initial",
            predecessor=None,
            locked_project_context=references,
        ),
    )


def _lineage(request: SubmissionAdmissionConsumptionRequest):
    context = request.task_context
    refs = context.locked_project_context
    content_id = str(uuid4())
    evidence_id = str(uuid4())
    admission = SimpleNamespace(
        id=str(request.admission_id),
        status="ready",
        actor_profile_id=str(context.contributor_id),
        project_id=str(refs.project_id),
        task_id=str(context.task_id),
        assignment_id=str(context.assignment_id),
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        pre_submit_evidence_set_id=evidence_id,
        artifact_content_id=content_id,
        archive_sha256=_sha("4"),
        archive_byte_count=9,
        consumed_at=None,
        consumed_by_submission_id=None,
        stale_at=None,
        stale_reason=None,
    )
    evidence = SimpleNamespace(
        id=evidence_id,
        project_id=admission.project_id,
        task_id=admission.task_id,
        assignment_id=admission.assignment_id,
        guide_version=refs.guide_version,
        source_snapshot_id=str(refs.source_snapshot_id),
        source_snapshot_sha256=refs.source_snapshot_hash,
        effective_policy_id=str(refs.effective_policy_id),
        locked_artifact_policy_sha256=refs.effective_policy_hash,
        pre_submit_policy_id=str(refs.pre_submit_policy_id),
        locked_checker_policy_sha256=refs.pre_submit_policy_bundle_hash,
        terminal_status="passed",
        eligible=True,
    )
    content = SimpleNamespace(
        id=content_id,
        sha256=admission.archive_sha256,
        byte_count=admission.archive_byte_count,
    )
    return admission, evidence, content


class _Allow:
    def __init__(self) -> None:
        self.authorize = AsyncMock()
        self.consume = AsyncMock()


class _DenyFinal(_Allow):
    def __init__(self) -> None:
        super().__init__()
        self.consume = AsyncMock(
            side_effect=SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_unavailable"
            )
        )


def _session(*values):
    return SimpleNamespace(
        in_transaction=lambda: True,
        in_nested_transaction=lambda: False,
        scalar=AsyncMock(side_effect=values),
        add=Mock(),
        flush=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_default_consumption_denies_before_admission_disclosure() -> None:
    request = _request()
    session = _session()

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_unavailable",
    ):
        await SubmissionAdmissionConsumptionService(session).consume(request)

    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_ready_admission_creates_exact_binding_and_consumes_once() -> None:
    request = _request()
    admission, evidence, content = _lineage(request)
    now = datetime.now(UTC)
    session = _session(admission, evidence, content, None, now)

    authority = _Allow()
    result = await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    binding = session.add.call_args.args[0]
    assert result.status == "consumed"
    assert result.replayed is False
    assert result.binding_id.hex == binding.id.replace("-", "")
    assert binding.resource_type == "submission"
    assert binding.resource_id == str(request.submission_id)
    assert binding.logical_role == "submission_bundle_original"
    assert binding.scope_version == 1
    assert binding.content_id == admission.artifact_content_id
    assert admission.consumed_by_submission_id == str(request.submission_id)
    assert admission.consumed_at == now
    facts = authority.consume.await_args.args[0]
    assert facts.admission_id == request.admission_id
    assert facts.submission_id == request.submission_id
    assert facts.content_id == result.content_id
    assert facts.sha256 == admission.archive_sha256
    assert facts.byte_count == admission.archive_byte_count
    session.flush.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_final_authority_denial_leaves_ready_admission_unchanged() -> None:
    request = _request()
    admission, evidence, content = _lineage(request)
    authority = _DenyFinal()
    session = _session(admission, evidence, content, None)

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_unavailable",
    ):
        await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    assert admission.status == "ready"
    assert admission.consumed_at is None
    assert admission.consumed_by_submission_id is None
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_proven_task_lineage_change_marks_ready_admission_stale() -> None:
    request = _request()
    admission, evidence, content = _lineage(request)
    evidence.source_snapshot_sha256 = _sha("9")
    now = datetime.now(UTC)
    session = _session(admission, evidence, content, now)

    authority = _Allow()
    result = await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    assert result.status == "stale"
    assert result.binding_id is None
    assert admission.stale_reason == "locked_submission_context_changed"
    assert admission.stale_at == now
    authority.consume.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_broken_art_lineage_denies_without_staling_admission() -> None:
    request = _request()
    admission, evidence, content = _lineage(request)
    content.sha256 = _sha("9")
    session = _session(admission, evidence, content)

    authority = _Allow()
    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_unavailable",
    ):
        await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    assert admission.status == "ready"
    assert admission.stale_at is None
    assert admission.stale_reason is None
    authority.consume.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_matching_consumed_admission_replays_exact_binding() -> None:
    request = _request()
    admission, _, _ = _lineage(request)
    admission.status = "consumed"
    admission.consumed_by_submission_id = str(request.submission_id)
    binding = SimpleNamespace(id=str(uuid4()), content_id=admission.artifact_content_id)
    session = _session(admission, binding)

    authority = _Allow()
    result = await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    assert result.status == "consumed"
    assert result.replayed is True
    assert result.binding_id.hex == binding.id.replace("-", "")
    assert authority.consume.await_args.args[0].submission_id == request.submission_id
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumed_admission_rejects_different_submission() -> None:
    request = _request()
    admission, _, _ = _lineage(request)
    admission.status = "consumed"
    admission.consumed_by_submission_id = str(uuid4())
    session = _session(admission)

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_already_consumed",
    ):
        await SubmissionAdmissionConsumptionService(session, _Allow()).consume(request)

    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_admission_is_terminal_without_art_mutation() -> None:
    request = _request()
    admission, _, _ = _lineage(request)
    admission.status = "stale"
    admission.stale_at = datetime.now(UTC)
    admission.stale_reason = "locked_submission_context_changed"
    session = _session(admission)

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_stale",
    ):
        await SubmissionAdmissionConsumptionService(session, _Allow()).consume(request)

    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumption_requires_caller_owned_root_transaction() -> None:
    request = _request()
    session = _session()
    session.in_transaction = lambda: False

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_unavailable",
    ):
        await SubmissionAdmissionConsumptionService(session, _Allow()).consume(request)

    session.scalar.assert_not_awaited()
