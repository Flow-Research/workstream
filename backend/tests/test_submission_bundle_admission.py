"""Focused custody and ordering proof for submission-bundle durable intent."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict,
    PreSubmitEvidenceService,
    PreSubmitPassCapability,
)
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.schemas import (
    ArtifactAdmissionResult,
    ArtifactAuthorityDeniedError,
    SubmissionBundleArtifactAdmissionRequest,
)
from app.modules.artifacts.submission_authorization import (
    DenySubmissionBundlePreparedAuthorization,
)
from app.modules.artifacts.submission_admission import (
    SubmissionBundleDurablePutRequest,
    SubmissionBundleDurablePutService,
)
from app.modules.artifacts.service import ArtifactAdmissionService
from app.modules.artifacts.submission_custody import SubmissionBundlePreparedCustody
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from tests.artifact_store_helpers import artifact_byte_stream, artifact_preparation_limits


def _sha(character: str) -> str:
    return "sha256:" + character * 64


async def _prepared(tmp_path):
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=artifact_preparation_limits(),
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        artifact_byte_stream(b"PK\x03\x04checked submission"),
        media_type="application/zip",
    )
    return manager, prepared


def _capability(prepared, evidence_set_id):
    service = PreSubmitEvidenceService(SimpleNamespace())
    return service._mint_pass_capability(
        evidence_set_id=evidence_set_id,
        prepared_generation_id=prepared.generation_id,
        predecessor_submission_id=None,
        effective_plan_sha256=_sha("7"),
        archive_sha256=prepared.commitment.sha256,
        semantic_manifest_sha256=_sha("2"),
        storage_scheme="s3",
    )


@pytest.mark.asyncio
async def test_durable_put_admits_in_transaction_then_publishes(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    evidence_set_id = uuid4()
    state = {"transaction": True}
    transaction = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: transaction),
        in_nested_transaction=lambda: False,
        in_transaction=lambda: state["transaction"],
    )
    admission_result = ArtifactAdmissionResult(
        attempt_id=uuid4(),
        status="prepared",
        operation_identity=_sha("3"),
        request_digest=_sha("4"),
        charge_ids=(uuid4(),),
        replayed=False,
    )

    async def admit(request, **values):
        assert state["transaction"] is True
        assert type(request) is SubmissionBundleArtifactAdmissionRequest
        assert request.pre_submit_evidence_set_id == evidence_set_id
        assert request.custody.prepared_generation_id == prepared.generation_id
        assert type(request.custody.pass_capability) is PreSubmitPassCapability
        assert values["existing_transaction"] is True
        return admission_result

    admission = SimpleNamespace(admit=admit)
    storage = SimpleNamespace(
        execute_committed_put=AsyncMock(return_value="object_confirmed"),
        resume_committed_put=AsyncMock(),
    )
    service = SubmissionBundleDurablePutService(
        session=session,
        admission=admission,
        storage=storage,
        authorization=object(),
    )
    handle = object.__new__(PreparedAuthorizationHandle)
    try:
        retained, selected_evidence_id, durable = await service.admit_in_transaction(
            SubmissionBundleDurablePutRequest(
                prepared_authorization=handle,
                prepared_artifact=prepared,
                pass_capability=_capability(prepared, evidence_set_id),
            )
        )
        storage.execute_committed_put.assert_not_awaited()
        state["transaction"] = False
        result = await service.publish_after_commit(
            retained,
            selected_evidence_id,
            durable,
        )
        assert result.pre_submit_evidence_set_id == evidence_set_id
        assert result.status == "object_confirmed"
        storage.execute_committed_put.assert_awaited_once()
        storage.resume_committed_put.assert_not_awaited()
        with pytest.raises(RuntimeError, match="prepared artifact is closed"):
            _ = prepared.generation_id
    finally:
        await prepared.close()
        manager.close()


def test_pass_capability_rejects_direct_construction() -> None:
    with pytest.raises(TypeError, match="can only be created by pre-submit evidence"):
        PreSubmitPassCapability(
            evidence_set_id=uuid4(),
            prepared_generation_id=uuid4(),
            predecessor_submission_id=None,
            effective_plan_sha256=_sha("7"),
            archive_sha256=_sha("1"),
            semantic_manifest_sha256=_sha("2"),
            storage_scheme="s3",
        )


def test_pass_capability_rejects_unregistered_service_owner() -> None:
    with pytest.raises(TypeError, match="can only be created by pre-submit evidence"):
        PreSubmitPassCapability._from_evidence_service(
            owner=object.__new__(PreSubmitEvidenceService),
            binding=object(),
            evidence_set_id=uuid4(),
            prepared_generation_id=uuid4(),
            predecessor_submission_id=None,
            effective_plan_sha256=_sha("7"),
            archive_sha256=_sha("1"),
            semantic_manifest_sha256=_sha("2"),
            storage_scheme="s3",
        )


def test_submission_custody_rejects_direct_construction() -> None:
    with pytest.raises(TypeError, match="requires live prepared work"):
        SubmissionBundlePreparedCustody()


def test_submission_request_rejects_evidence_without_live_custody() -> None:
    request = SubmissionBundleArtifactAdmissionRequest(
        pre_submit_evidence_set_id=uuid4(),
        custody=object(),
        replay_durable_intent_id=None,
    )
    with pytest.raises(TypeError, match="prepared custody is unavailable"):
        _ = request.source


def test_replay_lineage_includes_policy_catalogue_and_manifest_identity() -> None:
    values = {
        "actor_profile_id": str(uuid4()),
        "identity_link_id": str(uuid4()),
        "project_id": str(uuid4()),
        "task_id": str(uuid4()),
        "assignment_id": str(uuid4()),
        "predecessor_submission_id": None,
        "predecessor_submission_version": None,
        "archive_sha256": _sha("1"),
        "archive_byte_count": 10,
        "semantic_manifest_id": str(uuid4()),
        "semantic_manifest_sha256": _sha("2"),
        "guide_id": str(uuid4()),
        "guide_version": "1",
        "source_snapshot_id": str(uuid4()),
        "source_snapshot_sha256": _sha("3"),
        "locked_guide_sha256": _sha("4"),
        "effective_policy_id": str(uuid4()),
        "locked_artifact_policy_sha256": _sha("5"),
        "pre_submit_policy_id": str(uuid4()),
        "locked_checker_policy_sha256": _sha("6"),
        "effective_plan_sha256": _sha("7"),
        "catalogue_id": "workstream.default",
        "catalogue_version": "1",
        "catalogue_manifest_sha256": _sha("8"),
        "storage_scheme": "s3",
        "terminal_status": "passed",
        "eligible": True,
        "result_count": 2,
        "result_manifest_sha256": _sha("9"),
    }
    original = SimpleNamespace(**values)
    for field, changed in {
        "semantic_manifest_id": str(uuid4()),
        "locked_guide_sha256": _sha("a"),
        "effective_policy_id": str(uuid4()),
        "pre_submit_policy_id": str(uuid4()),
        "catalogue_id": "other.catalogue",
        "catalogue_version": "2",
        "catalogue_manifest_sha256": _sha("b"),
    }.items():
        drifted = SimpleNamespace(**{**values, field: changed})
        assert ArtifactAdmissionService._submission_replay_lineage(
            original
        ) != ArtifactAdmissionService._submission_replay_lineage(drifted)


@pytest.mark.asyncio
async def test_concurrent_pass_capability_consumption_has_one_winner(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    capability = _capability(prepared, uuid4())

    def consume() -> bool:
        try:
            capability.consume(
                prepared_generation_id=prepared.generation_id,
                predecessor_submission_id=None,
                effective_plan_sha256=capability.effective_plan_sha256,
                archive_sha256=prepared.commitment.sha256,
                semantic_manifest_sha256=capability.semantic_manifest_sha256,
                storage_scheme=capability.storage_scheme,
            )
        except PreSubmitEvidenceConflict:
            return False
        return True

    try:
        outcomes = await asyncio.gather(
            asyncio.to_thread(consume),
            asyncio.to_thread(consume),
        )
        assert sorted(outcomes) == [False, True]
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_fresh_checked_custody_resumes_existing_committed_intent(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    evidence_set_id = uuid4()
    replay_intent_id = uuid4()
    state = {"transaction": True}
    admission_result = ArtifactAdmissionResult(
        attempt_id=uuid4(),
        status="absent_replay_required",
        operation_identity=_sha("3"),
        request_digest=_sha("4"),
        charge_ids=(uuid4(),),
        replayed=True,
    )

    async def admit(request, **values):
        assert request.replay_durable_intent_id == replay_intent_id
        return admission_result

    storage = SimpleNamespace(
        execute_committed_put=AsyncMock(),
        resume_committed_put=AsyncMock(return_value="object_confirmed"),
    )
    service = SubmissionBundleDurablePutService(
        session=SimpleNamespace(
            sync_session=SimpleNamespace(get_transaction=lambda: SimpleNamespace(is_active=True)),
            in_nested_transaction=lambda: False,
            in_transaction=lambda: state["transaction"],
        ),
        admission=SimpleNamespace(admit=admit),
        storage=storage,
        authorization=object(),
    )
    try:
        retained, selected_evidence_id, durable = await service.admit_in_transaction(
            SubmissionBundleDurablePutRequest(
                prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                prepared_artifact=prepared,
                pass_capability=_capability(prepared, evidence_set_id),
                replay_durable_intent_id=replay_intent_id,
            )
        )
        state["transaction"] = False
        result = await service.publish_after_commit(
            retained,
            selected_evidence_id,
            durable,
        )
        assert result.replayed is True
        storage.resume_committed_put.assert_awaited_once()
        storage.execute_committed_put.assert_not_awaited()
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_durable_put_rejects_capability_replay_before_admission(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    capability = _capability(prepared, uuid4())
    capability.consume(
        prepared_generation_id=prepared.generation_id,
        predecessor_submission_id=None,
        effective_plan_sha256=capability.effective_plan_sha256,
        archive_sha256=prepared.commitment.sha256,
        semantic_manifest_sha256=capability.semantic_manifest_sha256,
        storage_scheme=capability.storage_scheme,
    )
    admission = SimpleNamespace(admit=AsyncMock())
    service = SubmissionBundleDurablePutService(
        session=SimpleNamespace(
            sync_session=SimpleNamespace(get_transaction=lambda: SimpleNamespace(is_active=True)),
            in_nested_transaction=lambda: False,
            in_transaction=lambda: True,
        ),
        admission=admission,
        storage=SimpleNamespace(),
        authorization=object(),
    )
    try:
        with pytest.raises(PreSubmitEvidenceConflict):
            await service.admit_in_transaction(
                SubmissionBundleDurablePutRequest(
                    prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                    prepared_artifact=prepared,
                    pass_capability=capability,
                )
            )
        admission.admit.assert_not_awaited()
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_deny_submission_authority_fails_closed() -> None:
    with pytest.raises(ArtifactAuthorityDeniedError):
        await DenySubmissionBundlePreparedAuthorization().consume(
            prepared_authorization=object.__new__(PreparedAuthorizationHandle),
            facts=object(),
        )
