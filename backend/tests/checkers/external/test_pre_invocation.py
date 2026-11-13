"""Receipt contract proof with synthetic, unqualified provider observations."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitFinalizeFacts, SelectedPreSubmitInvocationReceipt,
    SelectedPreSubmitInvocationResult, SelectedPreSubmitLeaseFacts,
)
from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation


def receipt_body(lease, *, outcome="completed", reason=None, managed=False):
    request = lease.reservation
    profile = request.runtime_profile.model_dump(mode="json")
    runtime = {"provider": "managed" if managed else "smolvm", "version": "test-only", "profile": profile}
    cleanup = {"obligation_id": "test-invocation", "disposition": "destroyed"}
    if managed:
        runtime["deployment_sha256"] = "sha256:" + "b" * 64
        cleanup["provider_receipt_sha256"] = "sha256:" + "c" * 64
    else:
        runtime.update(binary_sha256="sha256:" + "b" * 64, guest_sha256="sha256:" + "c" * 64)
        cleanup["journal_sha256"] = "sha256:" + "d" * 64
    return {
        "schema_version": "workstream.pre_submit_invocation.v1",
        "adapter_provider_key": "managed_test" if managed else "unix_socket",
        "operation": "execute_pre", "phase": "pre_submit",
        "invocation": {
            "operation": "execute_pre", "run_id": str(request.attempt_id),
            "source_operation_id": str(request.source.location.operation_id),
            "request_digest": request.request_digest, "source_sha256": request.source.source_sha256(),
            "profile_sha256": canonical_json_hash(profile),
            "image_digest": request.policy.entries[0].registry.image_digest,
            "config_image_id": "sha256:" + "a" * 64,
            "lease_id": str(lease.lease_id), "lease_generation": lease.lease_generation,
        },
        "provider_invocation_id": "test-invocation", "outcome": outcome, "reason": reason,
        "runtime": runtime, "cleanup": cleanup,
        "timings_ms": {"admission": 1, "preparation": 2, "execution": 3, "cleanup": 4, "total": 10},
    }


@pytest.fixture
def lease():
    request = _source_reservation()
    return SelectedPreSubmitLeaseFacts(request, new_record_id(), 1, request.pre_deadline_at)


@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("disposition", ["destroyed", "pending"])
@pytest.mark.parametrize("outcome,reason", [
    ("infrastructure_failure", "capacity_exceeded"), ("deadline_exceeded", "deadline_exceeded"),
])
def test_received_failure_retains_receipt_in_authority_digest(lease, managed, disposition, outcome, reason):
    body = receipt_body(lease, outcome=outcome, reason=reason, managed=managed)
    body["cleanup"]["disposition"] = disposition
    receipt = SelectedPreSubmitInvocationReceipt.model_validate_json(json.dumps(body))
    result = SelectedPreSubmitInvocationResult(receipt, None)
    result.validate_lease(lease)
    assert SelectedPreSubmitInvocationResult.from_canonical_body(result.canonical_body()) == result
    facts = SelectedPreSubmitFinalizeFacts(lease, None, receipt, reason)
    assert facts.facts_digest != replace(facts, invocation_receipt=None).facts_digest
    changed = deepcopy(body)
    changed["cleanup"]["disposition"] = "pending" if disposition == "destroyed" else "destroyed"
    other = SelectedPreSubmitInvocationReceipt.model_validate_json(json.dumps(changed))
    assert replace(facts, invocation_receipt=other).facts_digest != facts.facts_digest


@pytest.mark.parametrize("field", ["run_id", "source_operation_id", "request_digest", "source_sha256",
                                   "profile_sha256", "image_digest", "lease_id", "lease_generation"])
def test_invocation_cannot_move_between_requests_or_leases(lease, field):
    body = receipt_body(lease, outcome="infrastructure_failure", reason="invalid_output")
    body["invocation"][field] = (2 if field == "lease_generation" else str(new_record_id())
                                 if field.endswith("_id") else "sha256:" + "f" * 64)
    with pytest.raises(ValueError):
        SelectedPreSubmitInvocationReceipt.model_validate_json(json.dumps(body)).validate_lease(lease)


@pytest.mark.parametrize("change", ["negative", "boolean", "overflow", "sum", "extra", "wrong_cleanup", "outcome"])
def test_receipt_rejects_malformed_observations(lease, change):
    body = receipt_body(lease)
    if change in {"negative", "boolean", "overflow"}:
        body["timings_ms"]["total"] = {"negative": -1, "boolean": True, "overflow": 14400001}[change]
    elif change == "sum":
        body["timings_ms"]["total"] = 9
    elif change == "extra":
        body["cleanup"]["path"] = "/host/private"
    elif change == "wrong_cleanup":
        body["cleanup"]["obligation_id"] = "other-invocation"
    else:
        body["reason"] = "invalid_output"
    with pytest.raises(ValueError):
        SelectedPreSubmitInvocationReceipt.model_validate_json(json.dumps(body))


@pytest.mark.parametrize("managed", [False, True])
def test_completed_worker_is_bound_to_provider_receipt(managed):
    from app.modules.checkers.api.selected_pre_submit import ExternalPreSubmitManagedIsolationFacts
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_completed_execution

    request = _source_reservation()
    execution = _source_completed_execution(request)
    lease = SelectedPreSubmitLeaseFacts(request, execution.lease_id, execution.lease_generation, request.pre_deadline_at)
    body = receipt_body(lease, managed=managed)
    if managed:
        member = execution.external_members[0]
        isolation = ExternalPreSubmitManagedIsolationFacts(
            provider="managed", platform_manifest_digest=member.isolation.platform_manifest_digest,
            config_image_id=member.isolation.config_image_id, deployment_sha256=body["runtime"]["deployment_sha256"],
        )
        execution = replace(execution, external_members=(replace(member, isolation=isolation),))
    receipt = SelectedPreSubmitInvocationReceipt.model_validate_json(json.dumps(body))
    SelectedPreSubmitInvocationResult(receipt, execution).validate_lease(lease)
    assert SelectedPreSubmitFinalizeFacts(lease, execution, receipt, None).execution == execution
    body["invocation"]["config_image_id"] = "sha256:" + "f" * 64
    forged = SelectedPreSubmitInvocationReceipt.model_validate_json(json.dumps(body))
    with pytest.raises(ValueError, match="image configuration"):
        SelectedPreSubmitInvocationResult(forged, execution).validate_lease(lease)
    with pytest.raises(ValueError):
        SelectedPreSubmitInvocationResult(receipt, None)


@pytest.mark.parametrize("version,status", [
    ("v2", "queued"), ("v2", "running"), ("v2", "completed"),
    ("v2", "infrastructure_failed"), ("v3", "completed"), ("v3", "infrastructure_failed"),
])
def test_source_reads_preserve_schema_and_reject_rebound_columns(version, status):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from app.modules.checkers.api.selected_pre_submit import (
        HistoricalSourcePreSubmitTerminal, SelectedPreSubmitTerminalFacts, SelectedPreSubmitUnavailable,
    )
    from app.modules.checkers.selected_pre_submit_reads import _view
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_completed_execution

    request = _source_reservation()
    execution = _source_completed_execution(request)
    lease = SelectedPreSubmitLeaseFacts(request, execution.lease_id, execution.lease_generation, request.pre_deadline_at)
    now = datetime.now(UTC)
    terminal = None
    if status in {"completed", "infrastructure_failed"}:
        failed = status == "infrastructure_failed"
        values = dict(lease=lease, outcome=status, execution=None if failed else execution,
                      infrastructure_failure_code="capacity_exceeded" if failed else None,
                      queued_at=now, started_at=now, completed_at=now)
        if version == "v2":
            terminal = HistoricalSourcePreSubmitTerminal(**values)
        else:
            body = receipt_body(lease, outcome="infrastructure_failure" if failed else "completed",
                                reason="capacity_exceeded" if failed else None)
            terminal = SelectedPreSubmitTerminalFacts(**values,
                invocation_receipt=SelectedPreSubmitInvocationReceipt.model_validate_json(json.dumps(body)))
    row = SimpleNamespace(
        **{key: str(getattr(request, key)) for key in (
            "actor_profile_id", "identity_link_id", "project_id", "task_id", "assignment_id", "idempotency_key")},
        **{key: getattr(request, key) for key in (
            "policy_sha256", "default_behavior_sha256", "archive_sha256", "archive_byte_count", "execution_budget_ms")},
        id=str(request.attempt_id), source_operation_id=str(request.source.location.operation_id),
        request_json=request.canonical_body(), request_digest=request.request_digest,
        prepared_generation_id=None, default_input_sha256=None, semantic_manifest_sha256=None,
        execute_evidence_id=str(new_record_id()) if status != "queued" else None,
        finalize_evidence_id=str(new_record_id()) if terminal else None,
        status=status, terminal_json=terminal.canonical_body() if terminal else None,
        terminal_digest=terminal.terminal_digest if terminal else None,
        lease_id=str(lease.lease_id) if status != "queued" else None,
        lease_generation=lease.lease_generation if status != "queued" else 0,
        lease_expires_at=lease.lease_expires_at if status != "queued" else None,
        eligible=True if status == "completed" else None,
        queued_at=now, started_at=now if status != "queued" else None,
        completed_at=now if terminal else None,
    )
    assert _view(row).terminal == terminal
    if terminal is None:
        original = row.lease_generation
        row.lease_generation = -1
        with pytest.raises(SelectedPreSubmitUnavailable):
            _view(row)
        row.lease_generation = original
    row.source_operation_id = str(new_record_id())
    with pytest.raises(SelectedPreSubmitUnavailable):
        _view(row)


def test_python_decodes_shared_production_rust_wire_fixture():
    from datetime import datetime
    from pathlib import Path
    from uuid import UUID
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitReservationFacts

    path = Path(__file__).resolve().parents[4] / "external_checkers/workstream-checker-service/tests/fixtures/pre_invocation.json"
    fixture = json.loads(path.read_text())
    import os
    emitted = os.environ.get("WORKSTREAM_PRE_RECEIPT_WIRE_FILE")
    wire = json.loads(Path(emitted).read_bytes()) if emitted else fixture["wire"]
    assert wire == fixture["wire"]
    assert "adapter_provider_key" not in wire
    request = SelectedPreSubmitReservationFacts.from_canonical_body(fixture["reservation"])
    lease = SelectedPreSubmitLeaseFacts(
        request, UUID(wire["invocation"]["lease_id"]), wire["invocation"]["lease_generation"],
        datetime.fromisoformat(fixture["lease_expires_at"]),
    )
    # The real Unix-socket adapter attaches its trusted factory identity.
    result = SelectedPreSubmitInvocationResult.from_canonical_body(wire | {"adapter_provider_key": "unix_socket"})
    result.validate_lease(lease)
    assert result.execution.eligible and result.receipt.cleanup.disposition == "destroyed"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["received_failure", "wrong_factory", "wrong_family", "cancelled"])
async def test_managed_port_retains_receipt_and_enforces_selected_factory(lease, case):
    import asyncio
    from app.interfaces.external_services import ExternalServiceAdapterIdentity
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitInfrastructureUnavailable
    from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor

    body = receipt_body(lease, managed=case != "wrong_family",
        outcome="cancelled" if case == "cancelled" else "infrastructure_failure",
        reason="cancelled" if case == "cancelled" else "capacity_exceeded")
    body["adapter_provider_key"] = "managed_test"
    body["cleanup"]["disposition"] = "pending"
    result = SelectedPreSubmitInvocationResult.from_canonical_body(body | {"execution": None})
    grant = object()

    class ManagedAdapter:
        @property
        def pre_runtime_provider(self):
            return "managed"

        identity = ExternalServiceAdapterIdentity("external_checker_execution",
            "other_provider" if case == "wrong_factory" else "managed_test")

        async def execute_pre(self, actual_lease, actual_grant):
            assert actual_lease == lease and actual_grant is grant
            return result

    processor = SelectedPreSubmitProcessor(lease=lease, execution=ManagedAdapter())
    if case == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await processor.process(grant)
    elif case in {"wrong_factory", "wrong_family"}:
        with pytest.raises(SelectedPreSubmitInfrastructureUnavailable, match="invalid_output"):
            await processor.process(grant)
    else:
        assert await processor.process(grant) == result
        assert "journal_sha256" not in result.receipt.canonical_body()["cleanup"]
