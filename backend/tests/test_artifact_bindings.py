"""Focused proof for ART-owned ready-admission consumption and binding."""

from __future__ import annotations
from submission_context_fixtures import submission_context_facts


from datetime import UTC, datetime
from dataclasses import replace
from app.modules.checkers.api import SubmissionPacketView
from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID
from app.core.identifiers import new_record_id
from tests.test_submission_manifest import _archive, _manifest

import pytest

from app.modules.artifacts.api.submission_admission import ConsumedSubmissionAdmissionRequest
from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionError,
    SubmissionAdmissionConsumptionRequest,
)
from app.modules.artifacts.submission_bindings import (
    SubmissionAdmissionConsumptionService,
)
from app.modules.tasks.api import (
    TaskLockedProjectContextReferences,
)


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _request(*, submission_id=None) -> SubmissionAdmissionConsumptionRequest:
    references = TaskLockedProjectContextReferences(locked_contribution_policy_version_id=UUID(int=100),
        project_id=new_record_id(),
        guide_version="1",
        source_snapshot_id=new_record_id(),
        source_snapshot_hash=_sha("1"),
        effective_policy_id=new_record_id(),
        effective_policy_hash=_sha("2"),
        pre_submit_policy_id=new_record_id(),
        pre_submit_policy_bundle_hash=_sha("3"),
    )
    return SubmissionAdmissionConsumptionRequest(
        accepted_operation_id=new_record_id(),
        packet_sha256=SubmissionPacketView("Prepared summary", "Prepared attestation").sha256,
        admission_id=new_record_id(),
        submission_id=submission_id or new_record_id(),
        submission_version=1,
        task_context=submission_context_facts(submitter_contribution_policy_version_id=UUID(int=100),
            task_id=new_record_id(),
            assignment_id=new_record_id(),
            contributor_id=new_record_id(),
            status="in_progress",
            kind="initial",
            predecessor=None,
            locked_project_context=references,
        ),
    )


def _lineage(request: SubmissionAdmissionConsumptionRequest):
    context = request.task_context
    refs = context.locked_project_context
    manifest = _manifest(_archive([("answer.txt", b"verified")]))
    content_id = str(new_record_id())
    policy_body = {"schema_version": "external_post_submit_policy.v1", "entries": []}
    policy = LockedExternalPostSubmitPolicy.model_validate({
        **policy_body, "policy_sha256": canonical_json_hash(policy_body),
    })
    admission = SimpleNamespace(
        source_operation_id=str(request.accepted_operation_id),
        id=str(request.admission_id),
        status="ready",
        actor_profile_id=str(context.contributor_id),
        project_id=str(refs.project_id),
        task_id=str(context.task_id),
        assignment_id=str(context.assignment_id),
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        checker_remediation_manifest_id=None,
        revision_preparation_id=None,
        revision_preparation_sha256=None,
        pre_submit_evidence_set_id=None,
        selected_pre_submit_run_id=str(new_record_id()),
        identity_link_id=str(new_record_id()),
        artifact_content_id=content_id,
        locked_policy_context_hash=_sha("5"),
        semantic_manifest_id=str(new_record_id()),
        semantic_manifest_sha256=manifest.sha256,
        semantic_manifest_body=manifest.as_dict(),
        packet_sha256=request.packet_sha256,
        effective_plan_sha256=_sha("6"),
        selected_rules_sha256=_sha("7"),
        selected_post_submit_policy_body=policy.model_dump(mode="json"),
        selected_post_submit_policy_sha256=policy.policy_sha256,
        archive_sha256=_sha("4"),
        archive_byte_count=9,
        consumed_at=None,
        consumed_by_submission_id=None,
        consumed_by_submission_version=None,
        stale_at=None,
        stale_reason=None,
        guide_version=refs.guide_version,
        source_snapshot_id=str(refs.source_snapshot_id),
        source_snapshot_sha256=refs.source_snapshot_hash,
        effective_policy_id=str(refs.effective_policy_id),
        effective_policy_sha256=refs.effective_policy_hash,
        pre_submit_policy_id=str(refs.pre_submit_policy_id),
        pre_submit_policy_sha256=refs.pre_submit_policy_bundle_hash,
        guide_id=str(new_record_id()),
    )
    content = SimpleNamespace(
        id=content_id,
        sha256=admission.archive_sha256,
        byte_count=admission.archive_byte_count,
    )
    return admission, content


class _Allow:
    def __init__(self) -> None:
        self.authorize = AsyncMock()
        self.consume = AsyncMock(return_value=new_record_id())
        self.validate_replay = AsyncMock()


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
        execute=AsyncMock(),
        add=Mock(),
        get=AsyncMock(),
        flush=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_explicit_denial_precedes_admission_disclosure() -> None:
    request = _request()
    session = _session()

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_unavailable",
    ):
        authority = _Allow()
        authority.authorize.side_effect = SubmissionAdmissionConsumptionError("submission_bundle_admission_unavailable")
        await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_ready_admission_creates_exact_binding_and_consumes_once() -> None:
    request = _request()
    admission, content = _lineage(request)
    now = datetime.now(UTC)
    session = _session(admission, content, None, now)

    authority = _Allow()
    result = await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    custody_call = session.execute.await_args_list[0]
    assert "require_source_submission_admission" in str(custody_call.args[0])
    assert custody_call.args[1] == {"id": admission.id}
    binding = session.add.call_args_list[0].args[0]
    assert result.status == "consumed"
    assert result.replayed is False
    assert result.binding_id.hex == binding.id.replace("-", "")
    assert binding.resource_type == "submission"
    assert binding.resource_id == str(request.submission_id)
    assert binding.logical_role == "submission_bundle_original"
    assert binding.scope_version == 1
    assert binding.content_id == admission.artifact_content_id
    assert admission.consumed_by_submission_id == str(request.submission_id)
    assert admission.consumed_by_submission_version == request.submission_version
    assert admission.consumed_at == now
    facts = authority.consume.await_args.args[0]
    assert facts.admission_id == request.admission_id
    assert facts.evidence_set_id is None
    assert facts.selected_pre_submit_run_id == UUID(admission.selected_pre_submit_run_id)
    assert facts.actor_profile_id == request.task_context.contributor_id
    assert facts.identity_link_id.hex == admission.identity_link_id.replace("-", "")
    assert facts.project_id == request.task_context.locked_project_context.project_id
    assert facts.task_id == request.task_context.task_id
    assert facts.assignment_id == request.task_context.assignment_id
    assert facts.predecessor_submission_id is None
    assert facts.predecessor_submission_version is None
    assert facts.submission_id == request.submission_id
    assert facts.submission_version == request.submission_version
    assert facts.guide_id.hex == admission.guide_id.replace("-", "")
    assert facts.guide_version == admission.guide_version
    assert facts.source_snapshot_id.hex == admission.source_snapshot_id.replace("-", "")
    assert facts.source_snapshot_sha256 == admission.source_snapshot_sha256
    assert facts.effective_policy_id.hex == admission.effective_policy_id.replace("-", "")
    assert facts.effective_policy_sha256 == admission.effective_policy_sha256
    assert facts.pre_submit_policy_id.hex == admission.pre_submit_policy_id.replace("-", "")
    assert facts.pre_submit_policy_sha256 == admission.pre_submit_policy_sha256
    assert facts.locked_policy_context_hash == admission.locked_policy_context_hash
    assert facts.semantic_manifest_id.hex == admission.semantic_manifest_id.replace("-", "")
    assert facts.semantic_manifest_sha256 == admission.semantic_manifest_sha256
    assert facts.content_id == result.content_id
    assert facts.sha256 == admission.archive_sha256
    assert facts.byte_count == admission.archive_byte_count
    assert facts.logical_role == "submission_bundle_original"
    assert session.flush.await_count == 2
    receipt = session.add.call_args_list[1].args[0]
    assert receipt.admission_id == str(request.admission_id)
    assert receipt.binding_id == str(result.binding_id)
    assert receipt.decision_id == str(result.binding_decision_id)
    assert result.binding_decision_id == authority.consume.return_value


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["foreign", "missing", "historical_ready"])
async def test_source_admission_rejects_foreign_or_missing_accepted_operation(operation):
    request = _request()
    admission, content = _lineage(request)
    session, authority = _session(admission, content, None, datetime.now(UTC)), _Allow()
    changed = replace(request, accepted_operation_id=new_record_id() if operation == "foreign" else None)
    if operation == "historical_ready":
        admission.source_operation_id = None
    with pytest.raises(SubmissionAdmissionConsumptionError, match="submission_bundle_admission_unavailable"):
        await SubmissionAdmissionConsumptionService(session, authority).consume(changed)
    assert session.scalar.await_count == 1
    session.execute.assert_not_awaited()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    authority.consume.assert_not_awaited()
    assert admission.status == "ready" and admission.consumed_by_submission_id is None


@pytest.mark.asyncio
async def test_final_authority_denial_leaves_ready_admission_unchanged() -> None:
    request = _request()
    admission, content = _lineage(request)
    authority = _DenyFinal()
    session = _session(admission, content, None)

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
    admission, content = _lineage(request)
    admission.source_snapshot_sha256 = _sha("9")
    now = datetime.now(UTC)
    session = _session(admission, content, now)

    authority = _Allow()
    result = await SubmissionAdmissionConsumptionService(session, authority).consume(request)

    assert result.status == "stale"
    assert result.material is None
    assert result.binding_id is None
    assert admission.stale_reason == "locked_submission_context_changed"
    assert admission.stale_at == now
    authority.consume.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_broken_art_lineage_denies_without_staling_admission() -> None:
    request = _request()
    admission, content = _lineage(request)
    content.sha256 = _sha("9")
    session = _session(admission, content)

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
@pytest.mark.parametrize("historical", [False, True])
async def test_matching_consumed_admission_replays_exact_binding(historical) -> None:
    request = _request()
    admission, content = _lineage(request)
    if historical:
        admission.source_operation_id = None
    admission.status = "consumed"
    decision_id = new_record_id()
    admission.consumed_by_submission_id = str(request.submission_id)
    admission.consumed_by_submission_version = request.submission_version
    binding = SimpleNamespace(id=str(new_record_id()), content_id=admission.artifact_content_id)
    session = _session(admission, content, binding)
    session.get.return_value = SimpleNamespace(binding_id=binding.id, decision_id=str(decision_id))

    authority = _Allow()
    result = await SubmissionAdmissionConsumptionService(session, authority).read_consumed(_replay_request(request))

    assert result.status == "consumed"
    assert result.replayed is True
    assert result.binding_id.hex == binding.id.replace("-", "")
    authority.consume.assert_not_awaited()
    assert authority.validate_replay.await_args.args[0].submission_id == request.submission_id
    assert authority.validate_replay.await_args.args[1] == decision_id
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumed_admission_rejects_different_submission() -> None:
    request = _request()
    admission, _ = _lineage(request)
    admission.status = "consumed"
    admission.consumed_by_submission_id = str(new_record_id())
    admission.consumed_by_submission_version = request.submission_version
    session = _session(admission)

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_already_consumed",
    ):
        await SubmissionAdmissionConsumptionService(session, _Allow()).consume(request)

    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumed_admission_rejects_wrong_submission_version() -> None:
    original = _request()
    replay = replace(original, submission_version=2)
    admission, content = _lineage(original)
    admission.status = "consumed"
    admission.consumed_by_submission_id = str(original.submission_id)
    admission.consumed_by_submission_version = original.submission_version
    session = _session(admission, content, None)

    with pytest.raises(
        SubmissionAdmissionConsumptionError,
        match="submission_bundle_admission_already_consumed",
    ):
        await SubmissionAdmissionConsumptionService(session, _Allow()).consume(replay)


@pytest.mark.asyncio
async def test_stale_admission_is_terminal_without_art_mutation() -> None:
    request = _request()
    admission, _ = _lineage(request)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["absent", "file_hash", "foreign_body"])
async def test_consumption_rejects_invalid_manifest_before_binding(corruption):
    request = _request()
    admission, content = _lineage(request)
    if corruption == "absent":
        admission.semantic_manifest_body = None
    elif corruption == "file_hash":
        admission.semantic_manifest_body["entries"][0]["sha256"] = "sha256:" + "f" * 64
    else:
        admission.semantic_manifest_body = _manifest(_archive([("foreign.txt", b"other")])).as_dict()
    session = _session(admission, content)
    authority = _Allow()
    with pytest.raises(SubmissionAdmissionConsumptionError, match="submission_bundle_admission_unavailable"):
        await SubmissionAdmissionConsumptionService(session, authority).consume(request)
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    authority.consume.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ready", "consumed"])
@pytest.mark.parametrize("field", ["summary", "contributor_attestation"])
async def test_changed_packet_denies_before_binding_or_consumed_replay(status, field):
    original = _request()
    admission, content = _lineage(original)
    admission.status = status
    if status == "consumed":
        admission.consumed_by_submission_id = str(original.submission_id)
        admission.consumed_by_submission_version = original.submission_version
    packet = SubmissionPacketView("Prepared summary", "Prepared attestation")
    changed = replace(packet, **{field: "Different valid contributor text"})
    request = replace(original, packet_sha256=changed.sha256)
    binding = SimpleNamespace(id=str(new_record_id()), content_id=admission.artifact_content_id)
    continuation = (binding,) if status == "consumed" else (None, datetime.now(UTC))
    session = _session(admission, content, *continuation)
    session.get.return_value = SimpleNamespace(binding_id=UUID(binding.id), decision_id=new_record_id())
    authority = _Allow()
    expected = "submission_bundle_admission_unavailable" if status == "ready" else "submission_bundle_admission_context_changed"
    with pytest.raises(SubmissionAdmissionConsumptionError, match=expected):
        service = SubmissionAdmissionConsumptionService(session, authority)
        if status == "ready":
            await service.consume(request)
        else:
            await service.read_consumed(_replay_request(request))
    authority.consume.assert_not_awaited()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    assert admission.status == status


def _replay_request(request):
    context = request.task_context
    return ConsumedSubmissionAdmissionRequest(
        admission_id=request.admission_id, project_id=context.locked_project_context.project_id,
        task_id=context.task_id, assignment_id=context.assignment_id, contributor_id=context.contributor_id,
        submission_id=request.submission_id, submission_version=request.submission_version,
        packet_sha256=request.packet_sha256,
    )
