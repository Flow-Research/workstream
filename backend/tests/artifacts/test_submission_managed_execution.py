"""Controlled managed PRE through real public source custody, T4 and OUTBOX T5."""

from contextlib import aclosing
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text
from workstream_external_services import ExternalServiceAdapterIdentity

from app.adapters.artifacts import selected_pre_submit_source_contracts
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_manifest import build_submission_manifest
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
from app.modules.checkers.api.default_checker import workstream_default_input_sha256
from app.modules.checkers.api.external import make_external_checker_execution_result
from app.modules.checkers.api.selected_pre_submit import (
    ExternalPreSubmitManagedIsolationFacts, ExternalPreSubmitMemberFacts,
    SelectedPreSubmitExecutionFacts, SelectedPreSubmitInvocationResult,
    SelectedPreSubmitTerminalFacts, derive_selected_pre_submit_default_input,
    derive_selected_pre_submit_input,
)
from app.modules.checkers.default_checker import evaluate_verified_archive
from tests.artifacts.test_submission_foreground_command import (
    admission_intake as admission_intake, admin_access as admin_access,
    signed_access as signed_access, rsa_signing_material as rsa_signing_material,
    auth_database_env as auth_database_env, clear_settings_cache as clear_settings_cache,
    configure_source_http,
)
from tests.checkers.external.test_pre_invocation import receipt_body
from tests.retained_material_fixtures import finalize_retained_intake
from tests.test_artifact_admission import _local_store
from tests.test_trusted_intake import _archive, _WORKER


class ManagedExecution:
    """Test-only provider uses canonical worker rules, never native observations."""

    identity = ExternalServiceAdapterIdentity("external_checker_execution", "managed_test")
    pre_runtime_provider = "managed"

    def __init__(self, payload, root):
        self.payload, self.root = payload, root
        self.calls, self.closed, self.cleaned = 0, False, False

    async def execute_pre(self, lease, grant):
        self.calls += 1
        async with aclosing(grant.open_source(lease=lease)) as source:
            data = b"".join([chunk async for chunk in source])
        self.closed = True
        assert data == self.payload
        assert len(data) == lease.reservation.source.raw_byte_count
        assert "sha256:" + hashlib.sha256(data).hexdigest() == lease.reservation.source.raw_sha256
        with TemporaryDirectory(dir=self.root) as directory:
            archive, workspace = Path(directory) / "source.zip", Path(directory) / "tree"
            archive.write_bytes(data)
            workspace.mkdir(mode=0o700)
            inspector = SubmissionArchiveInspector(lease.reservation.runtime_profile.archive_limits)
            with archive.open("rb") as stream:
                inspection = inspector.inspect(stream)
                manifest = build_submission_manifest(inspection)
                args = dict(manifest_body=manifest.as_dict(), manifest_sha256=manifest.sha256,
                            source_contracts=selected_pre_submit_source_contracts())
                value = derive_selected_pre_submit_default_input(lease, **args)
                with inspector._projected_tree(stream, workspace, expected=inspection) as tree:
                    default = evaluate_verified_archive(value, _WORKER._Material(tree))
            assert default.eligible
            _, request = derive_selected_pre_submit_input(lease, **args)
            selected = lease.reservation.policy.entries[0]
            result = make_external_checker_execution_result(
                request_digest=request.request_digest, registry_entry_id=selected.registry.registry_entry_id,
                registry_entry_digest=selected.registry.entry_digest, phase="pre_submit",
                outcome="completed", verdict="passed", findings=(), infrastructure_failure_code=None,
            )
            body = receipt_body(lease, managed=True)
            member = ExternalPreSubmitMemberFacts(
                order=0, requirement_id=selected.requirement_id,
                registry_entry_id=selected.registry.registry_entry_id,
                registry_entry_digest=selected.registry.entry_digest,
                request_digest=request.request_digest, result=result,
                isolation=ExternalPreSubmitManagedIsolationFacts(
                    provider="managed", platform_manifest_digest=selected.registry.image_digest,
                    config_image_id=body["invocation"]["config_image_id"],
                    deployment_sha256=body["runtime"]["deployment_sha256"],
                ),
            )
            facts = SelectedPreSubmitExecutionFacts(
                request_digest=lease.reservation.request_digest, lease_id=lease.lease_id,
                lease_generation=lease.lease_generation, observed_source=lease.reservation.source,
                manifest_body=manifest.as_dict(), manifest_sha256=manifest.sha256,
                default_input_sha256=workstream_default_input_sha256(value),
                policy_sha256=lease.reservation.policy_sha256, workstream_default=default,
                required_external_count=1, external_members=(member,), eligible=True,
                source_contracts=selected_pre_submit_source_contracts(),
            )
        self.cleaned = not Path(directory).exists()
        self.result = SelectedPreSubmitInvocationResult.from_canonical_body(
            body | {"execution": facts.canonical_body()},
            source_contracts=selected_pre_submit_source_contracts(),
        )
        self.lease = lease
        return self.result


async def test_managed_completion_preserves_public_source_acceptance_and_finalization(
    admission_intake, tmp_path, monkeypatch,
):
    f, payload, key = admission_intake, _archive(), new_record_id()
    runtime = ManagedExecution(payload, tmp_path)
    client, settings, errors, calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, "completed",
        external_execution=runtime,
    )
    url = f"/api/v1/tasks/{f.task}/submissions"
    headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
        "Idempotency-Key": str(key), "Content-Length": str(len(payload)),
    }
    first = await client.post(url, headers=headers, content=payload)
    assert not errors, errors
    assert first.status_code == 202, first.text
    accepted, operation_id = first.json(), UUID(first.json()["operation_id"])
    assert runtime.calls == len(calls) == 1 and runtime.closed and runtime.cleaned
    receipt = runtime.result.receipt.canonical_body()
    assert receipt["runtime"]["provider"] == "managed"
    assert set(receipt["runtime"]) == {"provider", "version", "deployment_sha256", "profile"}
    assert set(receipt["cleanup"]) == {"obligation_id", "provider_receipt_sha256", "disposition"}
    assert receipt["cleanup"]["disposition"] == "destroyed"
    assert set(runtime.result.execution.external_members[0].isolation.__dataclass_fields__) == {
        "provider", "platform_manifest_digest", "config_image_id", "deployment_sha256",
    }
    async with f.factory() as session:
        row = (await session.execute(text("SELECT source_operation_id, terminal_json, terminal_digest "
            "FROM selected_pre_submit_runs WHERE id=:id"), {"id": calls[0]})).one()
        terminal = SelectedPreSubmitTerminalFacts.from_canonical_body(
            row.terminal_json, source_contracts=selected_pre_submit_source_contracts(),
        )
        assert row.source_operation_id == operation_id
        assert terminal.terminal_digest == row.terminal_digest
        assert terminal.execution == runtime.result.execution
        assert terminal.invocation_receipt == runtime.result.receipt
        assert public_pre_submission_results(terminal.execution) == accepted["pre_submission_results"]
        assert await session.scalar(text("SELECT count(*) FROM submissions WHERE task_id=:id"), {"id": f.task}) == 0
    for changed in ("deployment", "source"):
        forged = json.loads(json.dumps(runtime.result.canonical_body()))
        if changed == "deployment":
            forged["execution"]["external_members"][0]["isolation"]["deployment_sha256"] = "sha256:" + "f" * 64
        else:
            forged["invocation"]["source_sha256"] = "sha256:" + "f" * 64
        with pytest.raises(ValueError):
            SelectedPreSubmitInvocationResult.from_canonical_body(
                forged, source_contracts=selected_pre_submit_source_contracts(),
            ).validate_lease(runtime.lease, source_contracts=selected_pre_submit_source_contracts())
    before = await client.post(url, headers=headers, content=payload)
    assert before.status_code == 202 and before.json() == dict(accepted, replayed=True), before.text
    bootstrap, store = _local_store(settings, f.namespace)
    try:
        submission_id = await finalize_retained_intake(f.factory, SimpleNamespace(
            operation_id=operation_id, settings=settings, store=store, namespace=f.namespace,
        ))
    finally:
        bootstrap.close()
    after = await client.post(url, headers=headers, content=payload)
    assert after.status_code == 202 and after.json() == dict(accepted, replayed=True), after.text
    assert runtime.calls == len(calls) == 1
    async with f.factory() as session:
        admission = (await session.execute(text("SELECT status, source_operation_id FROM "
            "submission_bundle_admissions WHERE consumed_by_submission_id=:id"), {"id": submission_id})).one()
        assert (admission.status, admission.source_operation_id) == ("consumed", operation_id)
        for table in ("submissions", "submission_dispatches", "checker_runs"):
            assert await session.scalar(text(f"SELECT count(*) FROM {table} WHERE task_id=:id"), {"id": f.task}) == 1
        assert await session.scalar(text("SELECT count(*) FROM artifact_bindings WHERE resource_id=:id"),
                                    {"id": submission_id}) == 1
        assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE project_id=:id "
            "AND event_type='PostSubmissionEvaluationRequested'"), {"id": f.project}) == 1
