"""Selected PRE durable ownership stays exact before native migration proof."""

from __future__ import annotations

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
    async with AsyncSession() as session, session.begin():
        coordinator = SelectedPreSubmitCoordinator(session, tasks=tasks)
        with pytest.raises(TypeError, match="reservation facts are invalid"):
            await coordinator.reserve(request)
    tasks.lock_selected_pre_submit_scope.assert_not_awaited()
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
