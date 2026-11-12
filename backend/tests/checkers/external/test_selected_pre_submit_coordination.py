"""Selected PRE durable ownership stays exact before native migration proof."""

from __future__ import annotations

import json

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.modules.artifacts.schemas import SubmissionBundleArtifactAdmissionRequest
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.artifacts.models import (
    SubmissionBundleAdmission,
    SubmissionBundleDurableIntent,
)
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitExecuteFacts,
    SelectedPreSubmitAdmissionLineage,
    SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitRequestConflict,
    SelectedPreSubmitUnavailable,
)
from app.adapters.tasks import selected_pre_submit_task_guard
from app.modules.tasks.submission_context import TaskSubmissionContextService
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.checkers.selected_pre_submit_coordination import (
    SelectedPreSubmitAdmissionCapability,
    SelectedPreSubmitExecutionCapability,
    SelectedPreSubmitCoordinator,
)
from tests.checkers.external.support import SHA


_POST_POLICY_WITHOUT_DIGEST = {
    "schema_version": "external_post_submit_policy.v1",
    "entries": [],
}
_POST_POLICY_SHA256 = canonical_json_hash(_POST_POLICY_WITHOUT_DIGEST)
_POST_POLICY = _POST_POLICY_WITHOUT_DIGEST | {"policy_sha256": _POST_POLICY_SHA256}


def _reservation() -> SelectedPreSubmitReservationFacts:
    return SelectedPreSubmitReservationFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        project_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        attempt_id=new_record_id(),
        idempotency_key=new_record_id(),
        attempt_request_digest=SHA,
        prepared_generation_id=new_record_id(),
        policy_sha256="sha256:" + "1" * 64,
        default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        default_input_sha256="sha256:" + "2" * 64,
        archive_sha256="sha256:" + "3" * 64,
        archive_byte_count=1024,
        semantic_manifest_sha256="sha256:" + "4" * 64,
        execution_budget_ms=120_000,
    )


def _queued_row(reservation: SelectedPreSubmitReservationFacts) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(reservation.attempt_id),
        actor_profile_id=str(reservation.actor_profile_id),
        identity_link_id=str(reservation.identity_link_id),
        project_id=str(reservation.project_id),
        task_id=str(reservation.task_id),
        assignment_id=str(reservation.assignment_id),
        idempotency_key=str(reservation.idempotency_key),
        prepared_generation_id=str(reservation.prepared_generation_id),
        request_json=reservation.canonical_body(),
        request_digest=reservation.request_digest,
        policy_sha256=reservation.policy_sha256,
        default_behavior_sha256=reservation.default_behavior_sha256,
        default_input_sha256=reservation.default_input_sha256,
        archive_sha256=reservation.archive_sha256,
        archive_byte_count=reservation.archive_byte_count,
        semantic_manifest_sha256=reservation.semantic_manifest_sha256,
        execution_budget_ms=reservation.execution_budget_ms,
        status="queued",
        terminal_json=None,
        terminal_digest=None,
        eligible=None,
    )


@pytest.mark.asyncio
async def test_selected_pre_current_replays_only_stable_actor_key_facts() -> None:
    stored = _reservation()
    row = _queued_row(stored)
    transaction = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: transaction),
        in_nested_transaction=lambda: False,
        scalar=AsyncMock(return_value=row),
    )
    tasks = SimpleNamespace(lock_selected_pre_submit_scope=AsyncMock())
    coordinator = SelectedPreSubmitCoordinator(session, tasks=tasks)
    fresh = replace(
        stored,
        attempt_id=new_record_id(),
        prepared_generation_id=new_record_id(),
    )

    current = await coordinator.read_current(fresh)

    assert current is not None
    assert current.run_id == stored.attempt_id
    assert current.reservation == stored
    assert current.status == "queued"
    tasks.lock_selected_pre_submit_scope.assert_awaited_once_with(fresh)

    with pytest.raises(
        SelectedPreSubmitRequestConflict,
        match="selected_pre_submit_request_conflict",
    ):
        await coordinator.read_current(replace(fresh, archive_sha256="sha256:" + "f" * 64))


@pytest.mark.asyncio
async def test_selected_pre_expired_lease_read_keeps_task_first_custody() -> None:
    reservation = _reservation()
    row = _queued_row(reservation)
    row.status = "running"
    row.lease_id = str(new_record_id())
    row.lease_generation = 3
    row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    now = datetime.now(UTC)
    transaction = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: transaction),
        in_nested_transaction=lambda: False,
        scalar=AsyncMock(side_effect=[row, now]),
    )
    tasks = SimpleNamespace(lock_selected_pre_submit_scope=AsyncMock())
    coordinator = SelectedPreSubmitCoordinator(session, tasks=tasks)

    lease = await coordinator.read_expired_lease(
        run_id=reservation.attempt_id,
        facts=reservation,
    )

    assert lease.reservation == reservation
    assert lease.lease_id == UUID(row.lease_id)
    assert lease.lease_generation == 3
    assert lease.lease_expires_at == row.lease_expires_at
    tasks.lock_selected_pre_submit_scope.assert_awaited_once_with(reservation)


@pytest.mark.asyncio
async def test_selected_pre_task_guard_rechecks_exact_locked_lineage(monkeypatch) -> None:
    lineage = SelectedPreSubmitAdmissionLineage(
        predecessor_submission_id=new_record_id(),
        predecessor_submission_version=2,
        checker_remediation_manifest_id=new_record_id(),
        guide_id=new_record_id(),
        guide_version="guide-v2",
        source_snapshot_id=new_record_id(),
        source_snapshot_sha256="sha256:" + "5" * 64,
        locked_guide_sha256="sha256:" + "6" * 64,
        effective_policy_id=new_record_id(),
        effective_policy_sha256="sha256:" + "7" * 64,
        pre_submit_policy_id=new_record_id(),
        pre_submit_policy_sha256="sha256:" + "8" * 64,
        effective_plan_sha256="sha256:" + "9" * 64,
        rules_sha256="sha256:" + "d" * 64,
        external_checker_policies_sha256=SHA,
        post_submit_policy_sha256=_POST_POLICY_SHA256,
        post_submit_policy_body=_POST_POLICY,
        locked_policy_context_hash="sha256:" + "a" * 64,
        semantic_manifest_id=new_record_id(),
        semantic_manifest_body={"schema_version": "test"},
        packet_sha256="sha256:" + "b" * 64,
        storage_scheme="s3",
    )
    reservation = replace(
        _reservation(),
        policy_sha256=lineage.effective_plan_sha256,
        semantic_manifest_sha256=canonical_json_hash(lineage.semantic_manifest_body),
        admission_lineage=lineage,
    )
    locked = SimpleNamespace(
        project_id=reservation.project_id,
        guide_version=lineage.guide_version,
        source_snapshot_id=lineage.source_snapshot_id,
        source_snapshot_hash=lineage.source_snapshot_sha256,
        effective_policy_id=lineage.effective_policy_id,
        effective_policy_hash=lineage.effective_policy_sha256,
        pre_submit_policy_id=lineage.pre_submit_policy_id,
        pre_submit_policy_bundle_hash=lineage.pre_submit_policy_sha256,
    )
    context = SimpleNamespace(
        task_id=reservation.task_id,
        assignment_id=reservation.assignment_id,
        contributor_id=reservation.actor_profile_id,
        checker_remediation_manifest_id=(lineage.checker_remediation_manifest_id),
        predecessor=SimpleNamespace(
            submission_id=lineage.predecessor_submission_id,
            version=lineage.predecessor_submission_version,
        ),
        locked_project_context=locked,
    )

    async def lock(_repository, request):
        assert request.task_id == reservation.task_id
        return context

    monkeypatch.setattr(TaskSubmissionContextService, "lock_submission_context", lock)
    guard = selected_pre_submit_task_guard(SimpleNamespace())
    await guard.lock_selected_pre_submit_scope(reservation)

    context.checker_remediation_manifest_id = new_record_id()
    with pytest.raises(RuntimeError, match="selected PRE TASK custody changed"):
        await guard.lock_selected_pre_submit_scope(reservation)
    context.checker_remediation_manifest_id = lineage.checker_remediation_manifest_id

    locked.pre_submit_policy_bundle_hash = "sha256:" + "c" * 64
    with pytest.raises(RuntimeError, match="selected PRE TASK custody changed"):
        await guard.lock_selected_pre_submit_scope(reservation)


def test_selected_pre_model_compiles_complete_owner_and_authority_custody() -> None:
    sql = str(CreateTable(SelectedPreSubmitRun.__table__).compile(dialect=postgresql.dialect()))
    for value in (
        "fk_selected_pre_run_task_project",
        "fk_selected_pre_run_assignment",
        "execute_evidence_id",
        "finalize_evidence_id",
        "execution_budget_ms",
    ):
        assert value in sql
    assert "pre_submit_execution_attempts" not in sql

    intent_sql = str(
        CreateTable(SubmissionBundleDurableIntent.__table__).compile(dialect=postgresql.dialect())
    )
    admission_sql = str(
        CreateTable(SubmissionBundleAdmission.__table__).compile(dialect=postgresql.dialect())
    )
    for compiled in (intent_sql, admission_sql):
        assert "selected_pre_submit_run_id" in compiled
        assert "pre_submit_lineage" in compiled
    for value in (
        "semantic_manifest_body",
        "packet_sha256",
        "effective_plan_sha256",
        "pre_submit_policy_sha256",
    ):
        assert value in admission_sql


def test_selected_pre_admission_capability_is_exact_and_single_use() -> None:
    reservation = _reservation()
    owner = SimpleNamespace(_capability=None)
    run_id = new_record_id()
    terminal = SimpleNamespace(
        lease=SimpleNamespace(reservation=reservation),
        terminal_digest="sha256:" + "5" * 64,
    )
    capability = SelectedPreSubmitAdmissionCapability._issued(
        owner=owner,
        run_id=run_id,
        terminal=terminal,
    )
    owner._capability = capability
    values = {
        "run_id": run_id,
        "terminal_digest": terminal.terminal_digest,
        "attempt_id": reservation.attempt_id,
        "prepared_generation_id": reservation.prepared_generation_id,
        "archive_sha256": reservation.archive_sha256,
        "semantic_manifest_sha256": reservation.semantic_manifest_sha256,
    }
    with pytest.raises(
        SelectedPreSubmitUnavailable, match="selected_pre_submit_admission_unavailable"
    ):
        capability.consume(**(values | {"semantic_manifest_sha256": "sha256:" + "6" * 64}))
    assert capability.consume(**values) == run_id
    with pytest.raises(SelectedPreSubmitUnavailable):
        capability.consume(**values)


def test_selected_pre_execution_capability_is_exact_and_single_use() -> None:
    from datetime import UTC, datetime

    reservation = _reservation()
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation,
        lease_id=new_record_id(),
        lease_generation=1,
        lease_expires_at=datetime.now(UTC),
    )
    owner = SimpleNamespace(_execution_capability=None)
    capability = SelectedPreSubmitExecutionCapability._issued(
        owner=owner,
        run_id=reservation.attempt_id,
        lease=lease,
    )
    owner._execution_capability = capability
    with pytest.raises(
        SelectedPreSubmitUnavailable, match="selected_pre_submit_execution_unavailable"
    ):
        capability.consume(run_id=new_record_id(), lease=lease)
    assert (
        capability.consume(
            run_id=reservation.attempt_id,
            lease=lease,
        )
        == lease
    )
    with pytest.raises(SelectedPreSubmitUnavailable):
        capability.consume(run_id=reservation.attempt_id, lease=lease)


def test_selected_pre_authority_digests_bind_lease_and_infrastructure_outcome() -> None:
    from datetime import UTC, datetime, timedelta

    reservation = _reservation()
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation,
        lease_id=new_record_id(),
        lease_generation=1,
        lease_expires_at=datetime.now(UTC),
    )
    execution = SelectedPreSubmitExecuteFacts(lease)
    changed = SelectedPreSubmitExecuteFacts(
        SelectedPreSubmitLeaseFacts(
            reservation=reservation,
            lease_id=lease.lease_id,
            lease_generation=2,
            lease_expires_at=lease.lease_expires_at + timedelta(seconds=1),
        )
    )
    terminal = SelectedPreSubmitFinalizeFacts(
        lease=lease,
        execution=None,
        infrastructure_failure_code="deadline_exceeded",
    )

    assert execution.facts_digest != changed.facts_digest
    assert (
        terminal.facts_digest
        != SelectedPreSubmitFinalizeFacts(
            lease=lease,
            execution=None,
            infrastructure_failure_code="material_unavailable",
        ).facts_digest
    )
    with pytest.raises(ValueError, match="outcome"):
        SelectedPreSubmitFinalizeFacts(
            lease=lease,
            execution=None,
            infrastructure_failure_code=None,
        )


def test_selected_pre_request_binds_complete_later_admission_lineage() -> None:
    manifest = {"schema_version": "submission_manifest.v1", "entries": []}
    digest = canonical_json_hash(manifest)
    lineage = SelectedPreSubmitAdmissionLineage(
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        checker_remediation_manifest_id=None,
        guide_id=new_record_id(),
        guide_version="locked-v1",
        source_snapshot_id=new_record_id(),
        source_snapshot_sha256=SHA,
        locked_guide_sha256=SHA,
        effective_policy_id=new_record_id(),
        effective_policy_sha256=SHA,
        pre_submit_policy_id=new_record_id(),
        pre_submit_policy_sha256=SHA,
        effective_plan_sha256="sha256:" + "1" * 64,
        rules_sha256="sha256:" + "2" * 64,
        external_checker_policies_sha256=SHA,
        post_submit_policy_sha256=_POST_POLICY_SHA256,
        post_submit_policy_body=_POST_POLICY,
        locked_policy_context_hash=SHA,
        semantic_manifest_id=new_record_id(),
        semantic_manifest_body=manifest,
        packet_sha256=SHA,
        storage_scheme="s3",
    )
    reservation = replace(
        _reservation(),
        policy_sha256=lineage.effective_plan_sha256,
        semantic_manifest_sha256=digest,
        admission_lineage=lineage,
    )

    assert reservation.canonical_body()["admission_lineage"] == lineage.canonical_body()
    assert (
        SelectedPreSubmitReservationFacts.from_canonical_body(reservation.canonical_body())
        == reservation
    )
    assert (
        reservation.request_digest
        != replace(
            reservation,
            admission_lineage=replace(lineage, packet_sha256="sha256:" + "9" * 64),
        ).request_digest
    )
    with pytest.raises(ValueError, match="reservation"):
        replace(reservation, semantic_manifest_sha256=SHA)


def test_submission_artifact_request_selects_exactly_one_pre_lineage() -> None:
    selected_id = new_record_id()
    request = SubmissionBundleArtifactAdmissionRequest(
        pre_submit_evidence_set_id=None,
        custody=object(),
        replay_durable_intent_id=None,
        selected_pre_submit_run_id=selected_id,
        selected_terminal_digest=SHA,
    )
    assert request.selected_pre_submit_run_id == selected_id
    with pytest.raises(ValueError, match="lineage"):
        SubmissionBundleArtifactAdmissionRequest(
            pre_submit_evidence_set_id=new_record_id(),
            custody=object(),
            replay_durable_intent_id=None,
            selected_pre_submit_run_id=selected_id,
            selected_terminal_digest=SHA,
        )
    with pytest.raises(ValueError, match="lineage"):
        replace(request, selected_terminal_digest=None)


def test_selected_ready_admission_binds_selected_run() -> None:
    run_id = new_record_id()
    admission = SimpleNamespace(
        id=str(new_record_id()),
        pre_submit_evidence_set_id=None,
        selected_pre_submit_run_id=str(run_id),
        artifact_content_id=str(new_record_id()),
        actor_profile_id=str(new_record_id()),
        identity_link_id=str(new_record_id()),
        project_id=str(new_record_id()),
        task_id=str(new_record_id()),
        assignment_id=str(new_record_id()),
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        checker_remediation_manifest_id=None,
        guide_id=str(new_record_id()),
        guide_version="v1",
        source_snapshot_id=str(new_record_id()),
        source_snapshot_sha256=SHA,
        effective_policy_id=str(new_record_id()),
        effective_policy_sha256=SHA,
        pre_submit_policy_id=str(new_record_id()),
        pre_submit_policy_sha256=SHA,
        selected_post_submit_policy_sha256=_POST_POLICY_SHA256,
        selected_post_submit_policy_body=_POST_POLICY,
        locked_policy_context_hash=SHA,
        semantic_manifest_id=str(new_record_id()),
        semantic_manifest_sha256=SHA,
        archive_sha256=SHA,
        archive_byte_count=42,
    )
    content = SimpleNamespace(
        id=admission.artifact_content_id,
        sha256=admission.archive_sha256,
        byte_count=admission.archive_byte_count,
    )
    request = SimpleNamespace(
        admission_id=UUID(admission.id),
        submission_id=new_record_id(),
        submission_version=1,
    )

    assert SubmissionAdmissionConsumptionService._art_lineage_is_intact(admission, content)
    facts = SubmissionAdmissionConsumptionService._authority_facts(admission, request)
    assert facts.evidence_set_id is None
    assert facts.selected_pre_submit_run_id == run_id


def _retained_v1(name="selected_pre_v1"):
    """Fixed pre-cutover bytes; never regenerated from the live request schema."""
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent / "fixtures" / f"{name}.json").read_text())



def _retained_row(retained):
    """Complete indexed columns beside one independently frozen v1 record."""
    terminal = retained["terminal"]
    values = dict(retained["request"])
    values.update(
        id=values["attempt_id"], request_json=retained["request"],
        request_digest=retained["request_digest"], status=terminal["outcome"],
        terminal_json=terminal, terminal_digest=retained["terminal_digest"],
        eligible=terminal["execution"]["eligible"] if terminal["execution"] is not None else None,
        lease_id=terminal["lease_id"], lease_generation=terminal["lease_generation"],
    )
    values.update({key: datetime.fromisoformat(terminal[key]) for key in (
        "queued_at", "started_at", "completed_at", "lease_expires_at",
    )})
    return SimpleNamespace(**values)

@pytest.mark.parametrize("name", ["selected_pre_v1", "selected_pre_v1_completed"])
def test_historical_pre_decoder_preserves_exact_request_and_terminal_bytes(name):
    from app.modules.checkers.api.historical_selected_pre_submit import (
        HistoricalSelectedPreSubmitReservation, HistoricalSelectedPreSubmitTerminal,
    )
    from app.modules.checkers.selected_pre_submit_reads import _view

    retained = _retained_v1(name)
    request = HistoricalSelectedPreSubmitReservation.from_canonical_body(retained["request"])
    terminal = HistoricalSelectedPreSubmitTerminal.from_canonical_body(retained["terminal"])
    assert request.canonical_body() == retained["request"]
    assert request.request_digest == retained["request_digest"]
    assert terminal.canonical_body() == retained["terminal"]
    assert terminal.terminal_digest == retained["terminal_digest"]
    row = _retained_row(retained)
    view = _view(row)
    assert type(view.terminal) is HistoricalSelectedPreSubmitTerminal
    assert view.terminal.canonical_body() == retained["terminal"]
    row.terminal_digest = "sha256:" + "f" * 64
    with pytest.raises(SelectedPreSubmitUnavailable):
        _view(row)


@pytest.mark.asyncio
async def test_historical_pre_values_cannot_become_live_reservation_or_lease():
    from app.modules.checkers.api.historical_selected_pre_submit import HistoricalSelectedPreSubmitReservation

    request = HistoricalSelectedPreSubmitReservation.from_canonical_body(_retained_v1()["request"])
    from sqlalchemy.ext.asyncio import AsyncSession

    tasks = SimpleNamespace(lock_selected_pre_submit_scope=AsyncMock())
    sources = SimpleNamespace(lock_pre_source=AsyncMock())
    async with AsyncSession() as session, session.begin():
        coordinator = SelectedPreSubmitCoordinator(session, tasks=tasks, sources=sources)
        with pytest.raises(TypeError, match="reservation facts are invalid"):
            await coordinator.reserve(request)
    tasks.lock_selected_pre_submit_scope.assert_not_awaited()
    sources.lock_pre_source.assert_not_awaited()
    with pytest.raises(ValueError, match="lease facts are invalid"):
        SelectedPreSubmitLeaseFacts(request, new_record_id(), 1, datetime.now(UTC))


@pytest.mark.parametrize("field", ["request_digest", "queue_latency_ms", "execution_latency_ms"])
def test_historical_pre_decoder_rejects_changed_binding_or_timing(field):
    from app.modules.checkers.api.historical_selected_pre_submit import HistoricalSelectedPreSubmitTerminal

    body = _retained_v1()["terminal"]
    body[field] = "sha256:" + "f" * 64 if field == "request_digest" else body[field] + 1
    with pytest.raises(ValueError):
        HistoricalSelectedPreSubmitTerminal.from_canonical_body(body)


@pytest.mark.parametrize("field,value", [
    ("actor_profile_id", "01900000-0000-7000-8000-999999999999"),
    ("identity_link_id", "01900000-0000-7000-8000-999999999999"),
    ("project_id", "01900000-0000-7000-8000-999999999999"),
    ("task_id", "01900000-0000-7000-8000-999999999999"),
    ("assignment_id", "01900000-0000-7000-8000-999999999999"),
    ("archive_sha256", "sha256:" + "f" * 64),
    ("archive_byte_count", 999),
    ("request_digest", "sha256:" + "f" * 64),
    ("lease_id", "01900000-0000-7000-8000-999999999999"),
    ("lease_generation", 2),
    ("status", "completed"),
    ("eligible", True),
    ("completed_at", datetime(2026, 1, 2, tzinfo=UTC)),
])
def test_historical_pre_read_rejects_foreign_row_selectors_and_facts(field, value):
    from app.modules.checkers.selected_pre_submit_reads import _view

    row = _retained_row(_retained_v1())
    setattr(row, field, value)
    with pytest.raises(SelectedPreSubmitUnavailable):
        _view(row)


def test_historical_pre_decoder_rejects_an_unknown_outcome():
    from app.modules.checkers.api.historical_selected_pre_submit import HistoricalSelectedPreSubmitTerminal

    body = _retained_v1()["terminal"]
    body["outcome"] = "unknown"
    with pytest.raises(ValueError):
        HistoricalSelectedPreSubmitTerminal.from_canonical_body(body)


@pytest.mark.parametrize("status", ["queued", "running"])
def test_historical_nonterminal_pre_remains_readable_without_inventing_an_outcome(status):
    from app.modules.checkers.selected_pre_submit_reads import _view

    row = _retained_row(_retained_v1())
    row.status = status
    row.terminal_json = row.terminal_digest = row.completed_at = row.eligible = None
    if status == "queued":
        row.started_at = row.lease_id = row.lease_expires_at = None
        row.lease_generation = 0
    view = _view(row)
    assert view.status == status and view.terminal is None and view.completed_at is None


@pytest.mark.parametrize("changed", ["lineage", "member", "default"])
def test_historical_completed_pre_rejects_changed_nested_evidence(changed):
    from app.modules.checkers.api.historical_selected_pre_submit import HistoricalSelectedPreSubmitTerminal

    body = _retained_v1("selected_pre_v1_completed")["terminal"]
    assert body["reservation"]["admission_lineage"] is not None
    assert len(body["execution"]["external_members"]) == 1
    if changed == "lineage":
        body["reservation"]["admission_lineage"]["packet_sha256"] = "sha256:" + "f" * 64
    elif changed == "member":
        body["execution"]["external_members"][0]["result"]["request_digest"] = "sha256:" + "f" * 64
    else:
        body["execution"]["workstream_default"]["checks"].pop()
    with pytest.raises(ValueError):
        HistoricalSelectedPreSubmitTerminal.from_canonical_body(body)


def _source_reservation() -> SelectedPreSubmitReservationFacts:
    """Build a source-first request with explicit test-only execution limits."""
    from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
    from app.modules.artifacts.api.submission_intake import (
        SealedSubmissionSource, SubmissionSourceLocation,
    )
    from app.modules.checkers.api.default_checker import WorkstreamDefaultContext
    from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitRuntimeProfile
    from tests.checkers.external.test_selected_pre_submit import _policy

    policy = _policy()
    packet = SubmissionPacketView(summary="", contributor_attestation="")
    retained = _retained_v1("selected_pre_v1_completed")
    lineage_body = dict(retained["request"]["admission_lineage"])
    for name in ("semantic_manifest_id", "semantic_manifest_body"):
        lineage_body.pop(name)
    lineage_body.update(
        predecessor_submission_id=None, predecessor_submission_version=None,
        checker_remediation_manifest_id=None, effective_plan_sha256=policy.policy_sha256,
        packet_sha256=packet.sha256,
    )
    lineage = SelectedPreSubmitAdmissionLineage.from_canonical_body(lineage_body)
    return SelectedPreSubmitReservationFacts(
        actor_profile_id=new_record_id(), identity_link_id=new_record_id(),
        project_id=new_record_id(), task_id=new_record_id(), assignment_id=new_record_id(),
        attempt_id=new_record_id(), idempotency_key=new_record_id(),
        source=SealedSubmissionSource(
            location=SubmissionSourceLocation(
                operation_id=new_record_id(), namespace_id="primary",
                namespace_fingerprint=SHA, provider_profile="local-v2",
            ), provider_generation="test-generation", raw_sha256=SHA,
            raw_byte_count=1024, sealed_upload_fence=1,
        ),
        metadata_sha256=SHA, locked_context_sha256=SHA,
        foreground_lease_id=new_record_id(), foreground_lease_generation=1,
        pre_deadline_at=datetime.now(UTC) + timedelta(seconds=120),
        policy=policy,
        default_context=WorkstreamDefaultContext(
            predecessor=None, predecessor_exists=False, current_predecessor=None,
            current_rules_sha256=lineage.rules_sha256, predecessor_rules_sha256=None,
            packet=packet,
        ),
        runtime_profile=SelectedPreSubmitRuntimeProfile(
            profile_id="test-only", platform_root_sha256=SHA, cpu_millis=2000,
            memory_bytes=2 * 1024**3, temporary_disk_bytes=4 * 1024**3,
            maximum_processes=64, maximum_output_bytes=1024 * 1024,
            maximum_log_bytes=1024 * 1024, aggregate_deadline_ms=120_000,
            archive_limits=SubmissionArchiveLimits(maximum_inspection_seconds=60),
        ), admission_lineage=lineage,
    )


def test_source_first_reservation_round_trip_without_derived_inputs() -> None:
    request = _source_reservation()
    body = request.canonical_body()
    assert SelectedPreSubmitReservationFacts.from_canonical_body(body) == request
    assert body["source_sha256"] == request.source.source_sha256()
    assert not {"prepared_generation_id", "default_input_sha256", "semantic_manifest_sha256"} & body.keys()
    assert "semantic_manifest_body" not in body["admission_lineage"]
    assert "lease_expires_at" not in body


@pytest.mark.parametrize("field", [
    "provider_generation", "raw_sha256", "raw_byte_count", "sealed_upload_fence",
])
def test_source_first_reservation_rejects_substituted_source(field: str) -> None:
    request = _source_reservation()
    body = request.canonical_body()
    body["source"][field] = {
        "provider_generation": "other", "raw_sha256": "sha256:" + "1" * 64,
        "raw_byte_count": 1025, "sealed_upload_fence": 2,
    }[field]
    with pytest.raises(ValueError):
        SelectedPreSubmitReservationFacts.from_canonical_body(body)


@pytest.mark.parametrize("field", [
    "prepared_generation_id", "default_input_sha256", "semantic_manifest_sha256",
    "lease_expires_at",
])
def test_source_first_reservation_rejects_unobserved_or_mutable_facts(field: str) -> None:
    body = _source_reservation().canonical_body()
    body[field] = SHA
    with pytest.raises(ValueError):
        SelectedPreSubmitReservationFacts.from_canonical_body(body)


def test_source_first_reservation_binds_packet_and_hard_deadline() -> None:
    request = _source_reservation()
    assert replace(request, pre_deadline_at=request.pre_deadline_at + timedelta(seconds=1)).request_digest != request.request_digest
    with pytest.raises(ValueError):
        replace(request, pre_deadline_at=datetime.now())
    from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
    with pytest.raises(ValueError):
        replace(request, default_context=replace(
            request.default_context, packet=SubmissionPacketView("substituted", ""),
        ))


def _source_guard(request):
    from app.modules.artifacts.api.submission_intake import SubmissionIntakePreSourceFacts
    return SimpleNamespace(lock_pre_source=AsyncMock(return_value=SubmissionIntakePreSourceFacts(
        source=request.source, project_id=request.project_id, task_id=request.task_id,
        assignment_id=request.assignment_id, actor_profile_id=request.actor_profile_id,
        identity_link_id=request.identity_link_id, metadata_sha256=request.metadata_sha256,
        locked_context_sha256=request.locked_context_sha256,
        lease_id=request.foreground_lease_id, lease_generation=request.foreground_lease_generation,
        lease_expires_at=request.pre_deadline_at, pre_deadline_at=request.pre_deadline_at,
    )))


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [
    "metadata_sha256", "locked_context_sha256", "actor_profile_id", "identity_link_id",
    "assignment_id", "project_id", "task_id", "lease_id", "lease_generation",
    "pre_deadline_at",
])
async def test_source_first_reserve_checks_live_custody_before_checker_rows(field) -> None:
    request = _source_reservation()
    sources = _source_guard(request)
    current = sources.lock_pre_source.return_value
    changed = ("sha256:" + "b" * 64 if field.endswith("sha256") else
               2 if field == "lease_generation" else
               request.pre_deadline_at + timedelta(seconds=1) if field == "pre_deadline_at"
               else new_record_id())
    sources.lock_pre_source.return_value = current.model_copy(update={field: changed})
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: SimpleNamespace(is_active=True)),
        in_nested_transaction=lambda: False, scalar=AsyncMock(), execute=AsyncMock(),
    )
    tasks = SimpleNamespace(lock_selected_pre_submit_scope=AsyncMock())
    coordinator = SelectedPreSubmitCoordinator(session, tasks=tasks, sources=sources)
    with pytest.raises(SelectedPreSubmitUnavailable, match="source_changed"):
        await coordinator.reserve(request)
    tasks.lock_selected_pre_submit_scope.assert_awaited_once_with(request)
    session.execute.assert_not_awaited()
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_first_claim_caps_lease_at_existing_hard_deadline() -> None:
    request = _source_reservation()
    now = request.pre_deadline_at - timedelta(seconds=2)
    row = SimpleNamespace(
        **{name: str(getattr(request, name)) for name in (
            "actor_profile_id", "identity_link_id", "project_id", "task_id",
            "assignment_id", "idempotency_key")},
        id=str(request.attempt_id), source_operation_id=str(request.source.location.operation_id),
        prepared_generation_id=None, default_input_sha256=None, semantic_manifest_sha256=None,
        policy_sha256=request.policy_sha256, default_behavior_sha256=request.default_behavior_sha256,
        archive_sha256=request.archive_sha256, archive_byte_count=request.archive_byte_count,
        execution_budget_ms=request.execution_budget_ms, request_json=request.canonical_body(),
        request_digest=request.request_digest, status="queued", lease_generation=0,
    )
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: SimpleNamespace(is_active=True)),
        in_nested_transaction=lambda: False, scalar=AsyncMock(side_effect=[row, now]),
        flush=AsyncMock(),
    )
    async def consume(facts):
        return SimpleNamespace(facts_digest=facts.facts_digest, evidence_id=new_record_id())
    coordinator = SelectedPreSubmitCoordinator(
        session, tasks=SimpleNamespace(lock_selected_pre_submit_scope=AsyncMock()),
        sources=_source_guard(request),
    )
    authority = SimpleNamespace(consume=AsyncMock(side_effect=consume))
    lease = await coordinator.claim(run_id=request.attempt_id, facts=request, authority=authority)
    assert lease.lease_expires_at == request.pre_deadline_at
    assert row.started_at == now


def test_source_first_lease_cannot_extend_aggregate_deadline() -> None:
    request = _source_reservation()
    with pytest.raises(ValueError, match="lease facts"):
        SelectedPreSubmitLeaseFacts(
            reservation=request, lease_id=new_record_id(), lease_generation=1,
            lease_expires_at=request.pre_deadline_at + timedelta(microseconds=1),
        )


def test_source_first_policy_requires_exactly_one_project_image() -> None:
    from tests.checkers.external.test_selected_pre_submit import _empty_policy
    with pytest.raises(ValueError, match="locked context"):
        replace(_source_reservation(), policy=_empty_policy())


def test_source_first_profile_rejects_archive_time_beyond_aggregate() -> None:
    from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
    request = _source_reservation()
    with pytest.raises(ValueError, match="locked context"):
        replace(request, runtime_profile=request.runtime_profile.model_copy(update={
            "archive_limits": SubmissionArchiveLimits(maximum_inspection_seconds=121),
        }))


def _source_completed_execution(reservation):
    """Build structural result evidence; this fixture does not attest a runtime."""
    from app.modules.checkers.api.selected_pre_submit import (
        SelectedPreSubmitExecutionFacts, ExternalPreSubmitMemberFacts,
        ExternalPreSubmitIsolationFacts, derive_selected_pre_submit_input,
    )
    from app.modules.checkers.api.default_checker import (
        WorkstreamDefaultCheckerResult, workstream_default_input_sha256,
    )
    from app.modules.checkers.api.external import make_external_checker_execution_result

    retained = _retained_v1("selected_pre_v1_completed")
    old = retained["terminal"]["execution"]
    manifest = retained["request"]["admission_lineage"]["semantic_manifest_body"]
    manifest_sha256 = canonical_json_hash(manifest)
    lease = SelectedPreSubmitLeaseFacts(reservation, new_record_id(), 1, reservation.pre_deadline_at)
    value, request = derive_selected_pre_submit_input(
        lease, manifest_body=manifest, manifest_sha256=manifest_sha256,
    )
    selected = reservation.policy.entries[0]
    result = make_external_checker_execution_result(
        request_digest=request.request_digest, registry_entry_id=selected.registry.registry_entry_id,
        registry_entry_digest=selected.registry.entry_digest, phase="pre_submit",
        outcome="completed", verdict="passed", findings=(), infrastructure_failure_code=None,
    )
    return SelectedPreSubmitExecutionFacts(
        request_digest=reservation.request_digest, lease_id=lease.lease_id, lease_generation=1,
        observed_source=reservation.source, manifest_body=manifest, manifest_sha256=manifest_sha256,
        default_input_sha256=workstream_default_input_sha256(value),
        policy_sha256=reservation.policy_sha256,
        workstream_default=WorkstreamDefaultCheckerResult.model_validate(old["workstream_default"]),
        required_external_count=1, eligible=True,
        external_members=(ExternalPreSubmitMemberFacts(
            order=0, requirement_id=selected.requirement_id,
            registry_entry_id=selected.registry.registry_entry_id,
            registry_entry_digest=selected.registry.entry_digest, request_digest=request.request_digest,
            result=result, isolation=ExternalPreSubmitIsolationFacts(**(
                old["external_members"][0]["isolation"] |
                {"platform_manifest_digest": selected.registry.image_digest}
            )),
        ),),
    )


@pytest.mark.parametrize("changed", [
    None, "requirement", "registry_id", "registry_digest", "phase", "image", "missing",
])
def test_source_first_finalization_binds_actual_selected_member(changed):
    from app.modules.checkers.api.external import make_external_checker_execution_result
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitTerminalFacts

    reservation = _source_reservation()
    execution = _source_completed_execution(reservation)
    member = execution.external_members[0]
    if changed in {"registry_id", "registry_digest", "phase"}:
        field = {"registry_id": "registry_entry_id", "registry_digest": "registry_entry_digest",
                 "phase": "phase"}[changed]
        value = {"registry_id": new_record_id(), "registry_digest": "sha256:" + "f" * 64,
                 "phase": "post_submit"}[changed]
        # Rehash the forged result and agree with its echoed member identity.
        # Only the frozen reservation distinguishes it from valid evidence.
        result = make_external_checker_execution_result(
            **(member.result.model_dump(exclude={"result_digest"}) | {field: value})
        )
        member = replace(member, result=result, **({field: value} if changed != "phase" else {}))
    elif changed == "requirement":
        member = replace(member, requirement_id="another.requirement")
    elif changed == "image":
        member = replace(member, isolation=replace(
            member.isolation, platform_manifest_digest="sha256:" + "f" * 64,
        ))
    execution = replace(execution, external_members=(member,))
    if changed == "missing":
        execution = replace(execution, external_members=(), eligible=False)
    now = datetime.now(UTC)
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation, lease_id=execution.lease_id, lease_generation=execution.lease_generation,
        lease_expires_at=reservation.pre_deadline_at,
    )
    def finalize():
        return SelectedPreSubmitFinalizeFacts(lease, execution, None)
    def terminal():
        return SelectedPreSubmitTerminalFacts(lease, "completed", execution, None, now, now, now)
    if changed is None:
        assert finalize().execution == execution
        value = terminal()
        assert SelectedPreSubmitTerminalFacts.from_canonical_body(value.canonical_body()) == value
    else:
        for construct in (finalize, terminal):
            with pytest.raises(ValueError, match="execution selection"):
                construct()


def test_source_first_execution_cannot_claim_zero_required_project_checks():
    execution = _source_completed_execution(_source_reservation())
    with pytest.raises(ValueError, match="execution facts"):
        replace(execution, required_external_count=0, external_members=(), eligible=True)


def test_source_first_default_rejection_does_not_require_project_result():
    from app.modules.checkers.default_checker import evaluate_rejected_archive

    reservation = _source_reservation()
    execution = replace(
        _source_completed_execution(reservation),
        workstream_default=evaluate_rejected_archive(
            "submission_archive_malformed", packet=reservation.default_context.packet,
        ), external_members=(), eligible=False,
        manifest_body=None, manifest_sha256=None, default_input_sha256=None,
    )
    lease = SelectedPreSubmitLeaseFacts(
        reservation, execution.lease_id, execution.lease_generation, reservation.pre_deadline_at,
    )
    assert SelectedPreSubmitFinalizeFacts(lease, execution, None).execution == execution


@pytest.mark.parametrize("boundary", ["finalization", "terminal"])
def test_source_first_result_digest_revalidated_before_terminal_write(boundary):
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitTerminalFacts

    reservation = _source_reservation()
    execution = _source_completed_execution(reservation)
    member = execution.external_members[0]
    forged = member.result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    execution = replace(execution, external_members=(replace(member, result=forged),))
    lease = SelectedPreSubmitLeaseFacts(
        reservation, execution.lease_id, execution.lease_generation, reservation.pre_deadline_at,
    )
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="result digest mismatch"):
        if boundary == "finalization":
            SelectedPreSubmitFinalizeFacts(lease, execution, None)
        else:
            SelectedPreSubmitTerminalFacts(lease, "completed", execution, None, now, now, now)


@pytest.mark.parametrize("changed", [
    "request", "lease_id", "lease_generation", "source_generation", "source_hash",
    "source_count", "source_operation", "default_input", "manifest", "missing_manifest",
    "project_request",
])
def test_source_first_completed_evidence_rejects_substitution(changed):
    from copy import deepcopy
    from app.modules.checkers.api.external import make_external_checker_execution_result

    reservation = _source_reservation()
    execution = _source_completed_execution(reservation)
    lease = SelectedPreSubmitLeaseFacts(
        reservation, execution.lease_id, execution.lease_generation, reservation.pre_deadline_at,
    )
    if changed == "request":
        execution = replace(execution, request_digest="sha256:" + "f" * 64)
    elif changed == "lease_id":
        execution = replace(execution, lease_id=new_record_id())
    elif changed == "lease_generation":
        execution = replace(execution, lease_generation=execution.lease_generation + 1)
    elif changed.startswith("source_"):
        source = execution.observed_source
        field, value = {
            "source_generation": ("provider_generation", "different-generation"),
            "source_hash": ("raw_sha256", "sha256:" + "f" * 64),
            "source_count": ("raw_byte_count", source.raw_byte_count + 1),
            "source_operation": ("location", source.location.model_copy(update={
                "operation_id": new_record_id(),
            })),
        }[changed]
        execution = replace(execution, observed_source=source.model_copy(update={field: value}))
    elif changed == "default_input":
        execution = replace(execution, default_input_sha256="sha256:" + "f" * 64)
    elif changed == "manifest":
        body = deepcopy(execution.manifest_body)
        body["entries"][0]["normalized_path"] = "../escape"
        execution = replace(execution, manifest_body=body, manifest_sha256=canonical_json_hash(body))
    elif changed == "missing_manifest":
        execution = replace(execution, manifest_body=None, manifest_sha256=None, default_input_sha256=None)
    elif changed == "project_request":
        member = execution.external_members[0]
        # Echo agreement plus a valid result digest is insufficient: the owner
        # reconstructs the request from its frozen context and parsed manifest.
        result = make_external_checker_execution_result(**(
            member.result.model_dump(exclude={"result_digest"}) |
            {"request_digest": "sha256:" + "f" * 64}
        ))
        execution = replace(execution, external_members=(replace(
            member, request_digest=result.request_digest, result=result,
        ),))
    with pytest.raises(ValueError):
        SelectedPreSubmitFinalizeFacts(lease, execution, None)


@pytest.mark.parametrize("limit", ["maximum_entries", "maximum_path_bytes", "maximum_entry_bytes"])
def test_source_first_derived_manifest_obeys_locked_limits(limit):
    from app.modules.checkers.api.selected_pre_submit import derive_selected_pre_submit_input
    from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits

    reservation = _source_reservation()
    execution = _source_completed_execution(reservation)
    profile = reservation.runtime_profile.model_copy(update={
        "archive_limits": SubmissionArchiveLimits(**{limit: 1}, maximum_inspection_seconds=60),
    })
    reservation = replace(reservation, runtime_profile=profile)
    lease = SelectedPreSubmitLeaseFacts(reservation, new_record_id(), 1, reservation.pre_deadline_at)
    with pytest.raises(ValueError):
        derive_selected_pre_submit_input(
            lease, manifest_body=execution.manifest_body, manifest_sha256=execution.manifest_sha256,
        )


@pytest.mark.parametrize("failure", ["high_confidence_secret_detected", "submission_archive_unchanged"])
def test_source_first_default_blocker_does_not_validate_unrun_project_schema(failure):
    from app.modules.checkers.api.default_checker import (
        WorkstreamDefaultCheckerResult, workstream_default_input_sha256,
    )
    from app.modules.checkers.api.external import external_checker_json_hash
    from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
    from app.modules.checkers.api.selected_pre_submit import (
        derive_selected_pre_submit_default_input, derive_selected_pre_submit_input,
    )
    from tests.checkers.external.support import registry_entry

    reservation = _source_reservation()
    execution = _source_completed_execution(reservation)
    # This registered schema requires task_version, which the PRE input does not
    # contain. Its incompatibility matters only if the selected project runs.
    binding = reservation.policy.entries[0].model_copy(update={"registry": registry_entry()})
    body = reservation.policy.model_dump(mode="json", exclude={"policy_sha256"})
    body["entries"] = [binding.model_dump(mode="json")]
    policy = LockedExternalPreSubmitPolicy.model_validate_json(json.dumps(
        body | {"policy_sha256": external_checker_json_hash(body)}
    ))
    reservation = replace(reservation, policy=policy, admission_lineage=replace(
        reservation.admission_lineage, effective_plan_sha256=policy.policy_sha256,
    ))
    if failure == "submission_archive_unchanged":
        from app.modules.checkers.api.default_checker import WorkstreamDefaultPredecessor
        predecessor = WorkstreamDefaultPredecessor(
            new_record_id(), 1, reservation.source.raw_sha256, execution.manifest_sha256,
        )
        reservation = replace(
            reservation, default_context=replace(
                reservation.default_context, predecessor=predecessor, current_predecessor=predecessor,
                predecessor_exists=True, predecessor_rules_sha256=reservation.default_context.current_rules_sha256,
            ), admission_lineage=replace(
                reservation.admission_lineage, predecessor_submission_id=predecessor.submission_id,
                predecessor_submission_version=1, checker_remediation_manifest_id=new_record_id(),
            ),
        )
    lease = SelectedPreSubmitLeaseFacts(reservation, execution.lease_id, 1, reservation.pre_deadline_at)
    default_input = derive_selected_pre_submit_default_input(
        lease, manifest_body=execution.manifest_body, manifest_sha256=execution.manifest_sha256,
    )
    with pytest.raises(ValueError):
        derive_selected_pre_submit_input(
            lease, manifest_body=execution.manifest_body, manifest_sha256=execution.manifest_sha256,
        )
    default = execution.workstream_default.model_dump()
    checks = list(default["checks"])
    index = 2 if failure == "high_confidence_secret_detected" else 3
    checks[index] = checks[index] | {"status": "failed", "failure_code": failure, "finding_count": 1}
    default.update(checks=tuple(checks), eligible=False)
    execution = replace(
        execution, request_digest=reservation.request_digest, policy_sha256=policy.policy_sha256,
        workstream_default=WorkstreamDefaultCheckerResult.model_validate(default),
        default_input_sha256=workstream_default_input_sha256(default_input), external_members=(), eligible=False,
    )
    assert SelectedPreSubmitFinalizeFacts(lease, execution, None).execution == execution
