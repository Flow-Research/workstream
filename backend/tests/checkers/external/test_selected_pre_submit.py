"""Selected default and project PRE images share one verified ART callback."""

from __future__ import annotations

from tests.trusted_intake_fixtures import LocalIntakeSession
from app.modules.artifacts.trusted_intake import TrustedArchiveInspector
from app.modules.artifacts.submission_materialization import _TrustedPreSubmitProcessor

from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch
import zipfile
import pytest

from app.adapters.checkers import configured_external_checker_execution
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionResponse,
    ExternalCheckerIsolationReceipt,
    ExternalCheckerMaterialGrant,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    workstream_default_input_sha256,
)
from app.modules.checkers.api.external import (
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    ExternalCheckerRegistryEntry,
    ExternalCheckerSchema,
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_result,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding,
    LockedExternalCheckerPolicies,
    LockedExternalPostSubmitPolicy,
    LockedExternalPreSubmitPolicy,
    LockedWorkstreamDefault,
)
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitAdmissionLineage,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitInfrastructureUnavailable,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitTerminalFacts,
)
from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor
from app.adapters.checkers import SelectedPreSubmitCheckerExecutionAdapter
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.selected_pre_submit_admission import (
    bind_selected_pre_submit_admission,
    build_selected_pre_submit_reservation,
    selected_pre_submit_attempt_request_digest,
)
from app.modules.artifacts.submission_admission import (
    SubmissionBundleAdmissionPublicationError,
    SubmissionBundleAdmissionPublisher,
    require_revision_preparation_acknowledgement,
)
from app.modules.artifacts.api import SubmissionBundlePreparationRejected
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
    build_submission_manifest,
    semantic_manifest_identity,
    evaluate_submission_change,
)
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationRequest,
    PreparedBundleMaterializationService,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from tests.checkers.external.support import SHA, registry_entry


async def _bytes(value: bytes):
    yield value


def _archive(primary_bytes: bytes) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in (
            ("task.toml", primary_bytes),
            ("evidence/results", b"verified\n"),
        ):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(entry, value)
    return output.getvalue()


def _hex_sha(character: str) -> str:
    return "sha256:" + character * 64


def _selected_admission_reservation():
    manifest = {"schema_version": "submission_manifest.v1", "entries": []}
    post_policy = {"schema_version": "external_post_submit_policy.v1", "entries": []}
    post_policy_sha256 = canonical_json_hash(post_policy)
    post_policy["policy_sha256"] = post_policy_sha256
    lineage = SelectedPreSubmitAdmissionLineage(
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        checker_remediation_manifest_id=None,
        guide_id=new_record_id(),
        guide_version="v2",
        source_snapshot_id=new_record_id(),
        source_snapshot_sha256=_hex_sha("1"),
        locked_guide_sha256=_hex_sha("2"),
        effective_policy_id=new_record_id(),
        effective_policy_sha256=_hex_sha("3"),
        pre_submit_policy_id=new_record_id(),
        pre_submit_policy_sha256=_hex_sha("4"),
        effective_plan_sha256=_hex_sha("5"),
        rules_sha256=_hex_sha("8"),
        external_checker_policies_sha256=_hex_sha("9"),
        post_submit_policy_sha256=post_policy_sha256,
        post_submit_policy_body=post_policy,
        locked_policy_context_hash=_hex_sha("6"),
        semantic_manifest_id=new_record_id(),
        semantic_manifest_body=manifest,
        packet_sha256=_hex_sha("7"),
        storage_scheme="s3",
    )
    selected = SelectedPreSubmitReservationFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        project_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        attempt_id=new_record_id(),
        idempotency_key=new_record_id(),
        attempt_request_digest=_hex_sha("8"),
        prepared_generation_id=new_record_id(),
        policy_sha256=lineage.effective_plan_sha256,
        default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        default_input_sha256=_hex_sha("9"),
        archive_sha256=_hex_sha("a"),
        archive_byte_count=25,
        semantic_manifest_sha256=canonical_json_hash(manifest),
        execution_budget_ms=120_000,
        admission_lineage=lineage,
    )
    return manifest, post_policy, selected


def test_revision_acknowledgement_changes_selected_request_and_retains_old_bytes() -> None:
    """A new acknowledgement is frozen; old selected requests keep their digest."""
    _, _, retained = _selected_admission_reservation()
    old_body = retained.canonical_body()
    assert SelectedPreSubmitReservationFacts.from_canonical_body(old_body).canonical_body() == old_body
    assert "revision_preparation_id" not in old_body["admission_lineage"]

    predecessor_id, manifest_id, preparation_id = (
        new_record_id(), new_record_id(), new_record_id()
    )
    acknowledged = replace(
        retained.admission_lineage,
        predecessor_submission_id=predecessor_id,
        predecessor_submission_version=1,
        checker_remediation_manifest_id=manifest_id,
        revision_preparation_id=preparation_id,
        revision_preparation_sha256=_hex_sha("b"),
    )
    selected = replace(retained, admission_lineage=acknowledged)
    body = selected.canonical_body()
    assert body["admission_lineage"]["revision_preparation_id"] == str(preparation_id)
    assert body["admission_lineage"]["revision_preparation_sha256"] == _hex_sha("b")
    assert SelectedPreSubmitReservationFacts.from_canonical_body(body).request_digest == selected.request_digest
    null_ack = dict(body)
    null_ack["admission_lineage"] = dict(body["admission_lineage"])
    null_ack["admission_lineage"]["revision_preparation_id"] = None
    with pytest.raises(ValueError, match="selected PRE admission lineage is invalid"):
        SelectedPreSubmitReservationFacts.from_canonical_body(null_ack)

    request = dict(
        actor_profile_id=selected.actor_profile_id,
        identity_link_id=selected.identity_link_id,
        task_id=selected.task_id,
        assignment_id=selected.assignment_id,
        predecessor_submission_id=predecessor_id,
        idempotency_key=selected.idempotency_key,
        archive_sha256=selected.archive_sha256,
        archive_byte_count=selected.archive_byte_count,
        packet_sha256=acknowledged.packet_sha256,
    )
    without_ack = selected_pre_submit_attempt_request_digest(**request)
    with_ack = selected_pre_submit_attempt_request_digest(
        **request, revision_preparation_id=preparation_id,
        revision_preparation_sha256=_hex_sha("b"),
    )
    assert without_ack != with_ack
    with pytest.raises(ValueError, match="incomplete"):
        selected_pre_submit_attempt_request_digest(
            **request, revision_preparation_id=preparation_id,
        )
    with pytest.raises(ValueError, match="selected PRE admission lineage is invalid"):
        replace(retained.admission_lineage, revision_preparation_id=preparation_id,
                revision_preparation_sha256=_hex_sha("b"))


def test_revision_acknowledgement_requires_exact_current_preparation() -> None:
    """The explicit pair is required for revisions and forbidden on initial intake."""
    predecessor_id, manifest_id, preparation_id = (
        new_record_id(), new_record_id(), new_record_id()
    )
    revision = SimpleNamespace(
        preparation_id=preparation_id,
        preparation_sha256=_hex_sha("c"),
        source_submission_id=predecessor_id,
        source_routing_manifest_id=manifest_id,
    )
    task = SimpleNamespace(
        predecessor=SimpleNamespace(submission_id=predecessor_id),
        checker_remediation_manifest_id=manifest_id,
        revision_context=revision,
    )
    request = SimpleNamespace(
        revision_preparation_id=str(preparation_id),
        revision_preparation_sha256=_hex_sha("c"),
    )
    require_revision_preparation_acknowledgement(task, request)
    with pytest.raises(SubmissionBundlePreparationRejected, match="revision_context_changed"):
        require_revision_preparation_acknowledgement(
            task, SimpleNamespace(revision_preparation_id=str(new_record_id()),
                                  revision_preparation_sha256=_hex_sha("c")),
        )
    with pytest.raises(SubmissionBundlePreparationRejected, match="revision_acknowledgement_required"):
        require_revision_preparation_acknowledgement(
            task, SimpleNamespace(revision_preparation_id=None,
                                  revision_preparation_sha256=None),
        )
    with pytest.raises(SubmissionBundlePreparationRejected, match="revision_acknowledgement_invalid"):
        require_revision_preparation_acknowledgement(
            SimpleNamespace(predecessor=None), request,
        )


def _selected_admission_publisher_fixture(selected):
    terminal = {
        "request_digest": selected.request_digest,
        "outcome": "completed",
        "execution": {"eligible": True},
    }
    attempt = SimpleNamespace(
        id=str(new_record_id()),
        producer_request_type="submission_bundle",
        producer_ref=str(selected.actor_profile_id),
        project_id=str(selected.project_id),
        task_id=str(selected.task_id),
        sha256=selected.archive_sha256,
        byte_count=selected.archive_byte_count,
        media_type="application/zip",
        replica_id=str(new_record_id()),
        receipt_id=str(new_record_id()),
    )
    job = SimpleNamespace(
        id=str(new_record_id()),
        originating_put_attempt_id=attempt.id,
        replica_id=attempt.replica_id,
        execution_generation=2,
    )
    intent = SimpleNamespace(
        id=str(new_record_id()),
        pre_submit_evidence_set_id=None,
        selected_pre_submit_run_id=str(selected.attempt_id),
        selected_request_json=selected.canonical_body(),
        selected_request_digest=selected.request_digest,
        selected_terminal_json=terminal,
        selected_terminal_digest=canonical_json_hash(terminal),
    )
    replica = SimpleNamespace(
        id=attempt.replica_id,
        content_id=str(new_record_id()),
        verification_state="verified",
        availability_state="available",
        integrity_state="valid",
    )
    content = SimpleNamespace(
        id=replica.content_id,
        sha256=attempt.sha256,
        byte_count=attempt.byte_count,
    )
    verification = SimpleNamespace(
        id=str(new_record_id()),
        verification_job_id=job.id,
        execution_generation=job.execution_generation,
        outcome="verified",
        observed_sha256=attempt.sha256,
        observed_byte_count=attempt.byte_count,
    )
    session = SimpleNamespace(
        no_autoflush=nullcontext(),
        execute=AsyncMock(
            return_value=SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(
                    producer_request_type="submission_bundle",
                    selected_request_json=selected.canonical_body(),
                )
            )
        ),
        scalar=AsyncMock(
            side_effect=[
                job,
                attempt,
                intent,
                None,
                replica,
                verification,
                content,
                SimpleNamespace(id=attempt.receipt_id),
                datetime.now(UTC),
            ]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )
    return session, job, verification, intent


def _limits() -> ArtifactPreparationLimits:
    return ArtifactPreparationLimits(
        aggregate_reserved_bytes=2 * HARD_MAXIMUM_ARTIFACT_BYTES,
        maximum_files=2,
        maximum_concurrency=2,
        minimum_free_bytes=0,
        reservation_ttl_seconds=30,
        total_deadline_seconds=10,
        cleanup_margin_seconds=5,
        stream_buffer_bytes=1024,
        maximum_source_bytes=1024 * 1024,
        maximum_workspace_entries=2_000,
    )


class _PreparedHandle:
    pass


async def _request(
    tmp_path: Path,
    *,
    primary_bytes: bytes = b"[task]\nname='proof'\n",
):
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=_limits())
    preparation = ArtifactPreparationService(manager)
    prepared = await preparation.prepare(
        _bytes(_archive(primary_bytes)), media_type="application/zip"
    )
    intake = LocalIntakeSession(inspector)
    inspection = await prepared.inspect(TrustedArchiveInspector(intake, prepared.commitment))
    manifest = build_submission_manifest(inspection)
    policy = _policy()
    packet = SubmissionPacketView(
        summary="Completed exact project work.", contributor_attestation="rights_confirmed",
    )
    _, _, seed = _selected_admission_reservation()
    default_input = WorkstreamDefaultCheckerInput(
        archive_sha256=prepared.commitment.sha256,
        archive_byte_count=prepared.commitment.byte_count,
        archive_media_type="application/zip",
        semantic_manifest_sha256=manifest.sha256,
        entries=tuple(SubmissionMaterialEntry(
            item.normalized_path, item.entry_type.value, item.byte_count,
            item.sha256, item.executable,
        ) for item in manifest.entries),
        predecessor=None, predecessor_exists=False, current_predecessor=None,
        current_rules_sha256=seed.admission_lineage.rules_sha256,
        predecessor_rules_sha256=None, packet=packet,
    )
    reservation = replace(
        seed,
        prepared_generation_id=prepared.generation_id,
        policy_sha256=policy.policy_sha256,
        default_input_sha256=workstream_default_input_sha256(default_input),
        archive_sha256=prepared.commitment.sha256,
        archive_byte_count=prepared.commitment.byte_count,
        semantic_manifest_sha256=manifest.sha256,
        admission_lineage=replace(
            seed.admission_lineage,
            effective_plan_sha256=policy.policy_sha256,
            semantic_manifest_id=semantic_manifest_identity(manifest.sha256),
            semantic_manifest_body=manifest.as_dict(), packet_sha256=packet.sha256,
        ),
    )
    request = PreparedBundleMaterializationRequest(
        prepared_authorization=cast(PreparedAuthorizationHandle, _PreparedHandle()),
        task_id=reservation.task_id, assignment_id=reservation.assignment_id,
        submission_artifact_policy_id=reservation.admission_lineage.effective_policy_id,
        checker_policy_id=reservation.admission_lineage.pre_submit_policy_id,
        predecessor_submission_version=None, checker_remediation_manifest_id=None,
        prepared_artifact=prepared, inspection=inspection, manifest=manifest,
        change_gate=evaluate_submission_change(
            commitment=prepared.commitment, manifest=manifest,
            predecessor=None, predecessor_exists=False,
        ),
        packet=packet, external_policy=policy, default_checker_input=default_input,
        selected_reservation=reservation, intake=intake,
    )
    return request, inspector, manager, preparation


def _processor(*, request, policy, default_input, identity, material, grants, execution):
    checker = SelectedPreSubmitProcessor(
        policy=policy, default_input=default_input, identity=identity,
        material=material, execution=execution,
    )
    request = replace(request, default_checker_input=default_input, external_policy=policy,
                      selected_reservation=replace(request.selected_reservation,
                          policy_sha256=policy.policy_sha256,
                          admission_lineage=replace(request.selected_reservation.admission_lineage,
                              effective_plan_sha256=policy.policy_sha256, packet_sha256=default_input.packet.sha256),
                          default_input_sha256=workstream_default_input_sha256(default_input)))
    return _TrustedPreSubmitProcessor(request=request, checker=checker,
                                      limits=SubmissionArchiveLimits(), grants=grants)


def _open_input_schema() -> ExternalCheckerSchema:
    document = {"type": "object"}
    return ExternalCheckerSchema(
        schema_id=PRE_SUBMIT_INPUT_SCHEMA_ID,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def _policy() -> LockedExternalPreSubmitPolicy:
    values = registry_entry().model_dump()
    values["input_schema"] = _open_input_schema()
    # The immutable entry digest includes the input schema.
    spec = {
        key: value
        for key, value in values.items()
        if key
        not in {
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        }
    }
    spec["input_schema"] = values["input_schema"].model_dump(mode="json")
    values["entry_digest"] = external_checker_json_hash(spec)
    registry = ExternalCheckerRegistryEntry.model_validate(values)
    binding = LockedExternalCheckerBinding(
        requirement_id="project.archive_rules",
        stage="pre_submit",
        registry=registry,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
    )
    default = LockedWorkstreamDefault()
    body = {
        "schema_version": "external_pre_submit_policy.v1",
        "workstream_default": default.model_dump(mode="json"),
        "entries": [binding.model_dump(mode="json")],
    }
    return LockedExternalPreSubmitPolicy(
        workstream_default=default,
        entries=(binding,),
        policy_sha256=canonical_json_hash(body),
    )


def _empty_policy() -> LockedExternalPreSubmitPolicy:
    default = LockedWorkstreamDefault()
    body = {
        "schema_version": "external_pre_submit_policy.v1",
        "workstream_default": default.model_dump(mode="json"),
        "entries": [],
    }
    return LockedExternalPreSubmitPolicy(
        workstream_default=default,
        entries=(),
        policy_sha256=canonical_json_hash(body),
    )


def _policies() -> LockedExternalCheckerPolicies:
    pre = _policy()
    post_body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [],
    }
    post = LockedExternalPostSubmitPolicy(
        entries=(),
        policy_sha256=canonical_json_hash(post_body),
    )
    body = {
        "schema_version": "external_checker_policies.v1",
        "pre_submit": pre.model_dump(mode="json"),
        "post_submit": post.model_dump(mode="json"),
    }
    return LockedExternalCheckerPolicies(
        pre_submit=pre,
        post_submit=post,
        policies_sha256=canonical_json_hash(body),
    )


class _GrantIssuer:
    def __init__(self) -> None:
        self.requests = []

    @contextmanager
    def issue(self, request, _workspace):
        self.requests.append(request)
        yield ExternalCheckerMaterialGrant(
            grant_id="extract_" + "a" * 32,
            binding_digest="sha256:" + "b" * 64,
        )


class _Execution:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.requests = []

    async def execute(self, request, _grant):
        self.requests.append(request)
        findings = (
            ()
            if self.verdict == "passed"
            else (
                {
                    "check_id": "project_rule",
                    "code": "project_rule_failed",
                    "level": "error",
                    "message": "Project rule failed.",
                },
            )
        )
        result = make_external_checker_execution_result(
            request_digest=request.request_digest,
            registry_entry_id=request.registry.registry_entry_id,
            registry_entry_digest=request.registry.entry_digest,
            phase="pre_submit",
            outcome="completed",
            verdict=self.verdict,
            findings=findings,
            infrastructure_failure_code=None,
        )
        return ExternalCheckerExecutionResponse(
            result=result,
            isolation=ExternalCheckerIsolationReceipt(
                repository="registry.example/workstream/checker",
                platform_manifest_digest=request.registry.image_digest,
                platform_manifest_media_type=("application/vnd.oci.image.manifest.v1+json"),
                platform_manifest_byte_count=1024,
                operating_system="linux",
                architecture="amd64",
                config_image_id=SHA,
                runtime="runsc",
                isolation_mode="gvisor",
                sandbox_uid=65532,
                sandbox_gid=65532,
            ),
        )


def _execution_context(request, policy):
    identity = PreSubmitExternalCheckerIdentity(
        project_id=request.selected_reservation.project_id,
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        prepared_generation_id=request.prepared_artifact.generation_id,
        attempt_id=new_record_id(),
        attempt_request_digest=SHA,
        effective_plan_sha256=policy.policy_sha256,
    )
    material = PreSubmitExternalCheckerMaterial(
        role="submission_archive",
        prepared_generation_id=identity.prepared_generation_id,
        attempt_id=identity.attempt_id,
        attempt_request_digest=identity.attempt_request_digest,
        archive_sha256=request.prepared_artifact.commitment.sha256,
        archive_byte_count=request.prepared_artifact.commitment.byte_count,
        semantic_manifest_sha256=request.manifest.sha256,
        media_type="application/zip",
    )
    entries = tuple(
        SubmissionMaterialEntry(
            item.normalized_path,
            item.entry_type.value,
            item.byte_count,
            item.sha256,
            item.executable,
        )
        for item in request.manifest.entries
    )
    default_input = WorkstreamDefaultCheckerInput(
        archive_sha256=material.archive_sha256,
        archive_byte_count=material.archive_byte_count,
        archive_media_type=material.media_type,
        semantic_manifest_sha256=material.semantic_manifest_sha256,
        entries=entries,
        predecessor=None,
        predecessor_exists=False,
        current_predecessor=None,
        current_rules_sha256=request.selected_reservation.admission_lineage.rules_sha256,
        predecessor_rules_sha256=None,
        packet=SubmissionPacketView(summary="", contributor_attestation=""),
    )
    return identity, material, default_input


def _assert_terminal_round_trip(identity, policy, default_input, material, result) -> None:
    now = datetime.now(UTC)
    reservation = SelectedPreSubmitReservationFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        project_id=identity.project_id,
        task_id=identity.task_id,
        assignment_id=identity.assignment_id,
        attempt_id=identity.attempt_id,
        idempotency_key=new_record_id(),
        attempt_request_digest=identity.attempt_request_digest,
        prepared_generation_id=identity.prepared_generation_id,
        policy_sha256=policy.policy_sha256,
        default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        default_input_sha256=workstream_default_input_sha256(default_input),
        archive_sha256=material.archive_sha256,
        archive_byte_count=material.archive_byte_count,
        semantic_manifest_sha256=material.semantic_manifest_sha256,
        execution_budget_ms=120_000,
    )
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation,
        lease_id=new_record_id(),
        lease_generation=1,
        lease_expires_at=now + timedelta(minutes=2),
    )
    terminal = SelectedPreSubmitTerminalFacts(
        lease=lease,
        outcome="completed",
        execution=result,
        infrastructure_failure_code=None,
        queued_at=now,
        started_at=now + timedelta(milliseconds=25),
        completed_at=now + timedelta(milliseconds=75),
    )
    assert terminal.canonical_body()["queue_latency_ms"] == 25
    assert terminal.canonical_body()["execution_latency_ms"] == 50
    assert terminal.canonical_body()["request_digest"] == reservation.request_digest
    assert terminal.terminal_digest == canonical_json_hash(terminal.canonical_body())
    assert SelectedPreSubmitTerminalFacts.from_canonical_body(terminal.canonical_body()) == terminal
    changed_terminal = terminal.canonical_body() | {"queue_latency_ms": 26}
    with pytest.raises(ValueError, match="terminal facts"):
        SelectedPreSubmitTerminalFacts.from_canonical_body(changed_terminal)


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict,eligible", [("passed", True), ("failed", False)])
async def test_selected_pre_runs_default_then_locked_external_image(
    tmp_path, verdict: str, eligible: bool
) -> None:
    request, inspector, manager, preparation = await _request(tmp_path)
    policy = _policy()
    identity, material, default_input = _execution_context(request, policy)
    grants, execution = _GrantIssuer(), _Execution(verdict)
    processor = _processor(
        request=request,
        policy=policy,
        default_input=default_input,
        identity=identity,
        material=material,
        grants=grants,
        execution=execution,
    )
    try:
        result = await preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count,
        )
        assert result.eligible is eligible
        assert result.workstream_default.eligible
        assert [item.code for item in result.workstream_default.warnings] == [
            "submission_summary_missing",
            "submission_attestation_missing",
        ]
        assert len(result.external_members) == 1
        assert result.external_members[0].result.verdict == verdict
        assert len(grants.requests) == len(execution.requests) == 1
        assert grants.requests[0].request_digest == execution.requests[0].request_digest
        assert result.result_digest == canonical_json_hash(result.canonical_body())
        _assert_terminal_round_trip(identity, policy, default_input, material, result)
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
async def test_selected_pre_only_requires_project_runtime_for_locked_external_images(
    tmp_path, external: bool
) -> None:
    request, inspector, manager, preparation = await _request(tmp_path)
    policy = _policy() if external else _empty_policy()
    identity, material, default_input = _execution_context(request, policy)
    grants = _GrantIssuer()
    processor = _processor(
        request=request,
        policy=policy,
        default_input=default_input,
        identity=identity,
        material=material,
        grants=grants,
        execution=configured_external_checker_execution(Settings()),
    )
    try:
        if external:
            with pytest.raises(SelectedPreSubmitInfrastructureUnavailable) as failure:
                await preparation._process_prepared_submission(
                    request.prepared_artifact,
                    processor,
                    reserved_bytes=request.manifest.total_expanded_bytes,
                    maximum_entries=request.manifest.entry_count,
                )
            assert failure.value.code == "implementation_unavailable"
            assert len(grants.requests) == 1
        else:
            result = await preparation._process_prepared_submission(
                request.prepared_artifact,
                processor,
                reserved_bytes=request.manifest.total_expanded_bytes,
                maximum_entries=request.manifest.entry_count,
            )
            assert result.eligible is True
            assert result.required_external_count == 0
            assert result.external_members == ()
            assert grants.requests == []
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [False, True])
async def test_selected_pre_terminal_publishes_self_contained_ready_admission(
    replacement: bool,
) -> None:
    manifest, post_policy, selected = _selected_admission_reservation()
    if replacement:
        selected = replace(
            selected,
            admission_lineage=replace(
                selected.admission_lineage,
                predecessor_submission_id=new_record_id(),
                predecessor_submission_version=1,
                checker_remediation_manifest_id=new_record_id(),
            ),
        )
    lineage = selected.admission_lineage
    assert (
        SelectedPreSubmitAdmissionLineage.from_canonical_body(lineage.canonical_body()) == lineage
    )
    session, job, verification, _ = _selected_admission_publisher_fixture(selected)
    task_contexts = SimpleNamespace(lock_retained_submission_parents=AsyncMock())
    publisher = SubmissionBundleAdmissionPublisher(session)
    retained_parents = await publisher.lock_retained_submission_parents(
        verification_job_id=job.id,
        task_contexts=task_contexts,
    )

    admission = await publisher.publish_verified(
        verification_job_id=job.id,
        verification_receipt_id=verification.id,
        retained_parents=retained_parents,
    )

    task_contexts.lock_retained_submission_parents.assert_awaited_once_with(
        retained_parents
    )
    assert retained_parents is not None
    assert retained_parents.project_id == selected.project_id
    assert retained_parents.task_id == selected.task_id
    assert retained_parents.assignment_id == selected.assignment_id
    assert retained_parents.contributor_id == selected.actor_profile_id
    assert admission.checker_remediation_manifest_id == (
        str(lineage.checker_remediation_manifest_id) if replacement else None
    )
    assert admission.pre_submit_evidence_set_id is None
    assert admission.selected_pre_submit_run_id == str(selected.attempt_id)
    assert admission.packet_sha256 == selected.admission_lineage.packet_sha256
    assert admission.semantic_manifest_body == manifest
    assert (
        admission.selected_post_submit_policy_sha256
        == selected.admission_lineage.post_submit_policy_sha256
    )
    assert admission.selected_post_submit_policy_body == post_policy


@pytest.mark.asyncio
async def test_selected_pre_publication_requires_exact_retained_task_identity() -> None:
    _, _, selected = _selected_admission_reservation()
    session, job, verification, intent = _selected_admission_publisher_fixture(selected)
    task_contexts = SimpleNamespace(lock_retained_submission_parents=AsyncMock())
    publisher = SubmissionBundleAdmissionPublisher(session)
    retained_parents = await publisher.lock_retained_submission_parents(
        verification_job_id=job.id,
        task_contexts=task_contexts,
    )
    assert retained_parents is not None
    intent.selected_request_json = replace(
        selected,
        actor_profile_id=new_record_id(),
    ).canonical_body()

    with pytest.raises(
        SubmissionBundleAdmissionPublicationError,
        match="retained TASK identity changed",
    ):
        await publisher.publish_verified(
            verification_job_id=job.id,
            verification_receipt_id=verification.id,
            retained_parents=retained_parents,
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_selected_pre_publication_requires_task_port_before_terminal_reads() -> None:
    _, _, selected = _selected_admission_reservation()
    session, job, _, _ = _selected_admission_publisher_fixture(selected)

    with pytest.raises(RuntimeError, match="TASK composition is unavailable"):
        await SubmissionBundleAdmissionPublisher(
            session
        ).lock_retained_submission_parents(
            verification_job_id=job.id,
            task_contexts=None,
        )

    session.scalar.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_selected_pre_task_lock_failure_propagates_before_terminal_reads() -> None:
    _, _, selected = _selected_admission_reservation()
    session, job, _, _ = _selected_admission_publisher_fixture(selected)
    task_contexts = SimpleNamespace(
        lock_retained_submission_parents=AsyncMock(
            side_effect=RuntimeError("injected TASK database failure")
        )
    )

    with pytest.raises(RuntimeError, match="injected TASK database failure"):
        await SubmissionBundleAdmissionPublisher(
            session
        ).lock_retained_submission_parents(
            verification_job_id=job.id,
            task_contexts=task_contexts,
        )

    session.scalar.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_selected_pre_default_secret_blocker_precedes_external_image(
    tmp_path,
) -> None:
    request, inspector, manager, preparation = await _request(
        tmp_path,
        primary_bytes=b"-----BEGIN OPENSSH PRIVATE KEY-----\nencoded",
    )
    policy = _policy()
    identity = PreSubmitExternalCheckerIdentity(
        project_id=request.selected_reservation.project_id,
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        prepared_generation_id=request.prepared_artifact.generation_id,
        attempt_id=new_record_id(),
        attempt_request_digest=SHA,
        effective_plan_sha256=policy.policy_sha256,
    )
    material = PreSubmitExternalCheckerMaterial(
        role="submission_archive",
        prepared_generation_id=identity.prepared_generation_id,
        attempt_id=identity.attempt_id,
        attempt_request_digest=identity.attempt_request_digest,
        archive_sha256=request.prepared_artifact.commitment.sha256,
        archive_byte_count=request.prepared_artifact.commitment.byte_count,
        semantic_manifest_sha256=request.manifest.sha256,
        media_type="application/zip",
    )
    entries = tuple(
        SubmissionMaterialEntry(
            item.normalized_path,
            item.entry_type.value,
            item.byte_count,
            item.sha256,
            item.executable,
        )
        for item in request.manifest.entries
    )
    execution = _Execution("passed")
    grants = _GrantIssuer()
    processor = _processor(
        request=request,
        policy=policy,
        default_input=WorkstreamDefaultCheckerInput(
            archive_sha256=material.archive_sha256,
            archive_byte_count=material.archive_byte_count,
            archive_media_type=material.media_type,
            semantic_manifest_sha256=material.semantic_manifest_sha256,
            entries=entries,
            predecessor=None,
            predecessor_exists=False,
            current_predecessor=None,
            current_rules_sha256=request.selected_reservation.admission_lineage.rules_sha256,
            predecessor_rules_sha256=None,
            packet=request.packet,
        ),
        identity=identity,
        material=material,
        grants=grants,
        execution=execution,
    )
    try:
        result = await preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count,
        )
        assert result.eligible is False
        assert result.workstream_default.checks[2].failure_code == (
            "high_confidence_secret_detected"
        )
        assert result.external_members == ()
        assert grants.requests == []
        assert execution.requests == []
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.asyncio
async def test_selected_admission_binds_unchanged_work_to_current_task_rules(
    tmp_path,
) -> None:
    request, _inspector, manager, _preparation = await _request(tmp_path)
    policies = _policies()
    project_id = request.selected_reservation.project_id
    actor_profile_id = new_record_id()
    identity_link_id = new_record_id()
    assignment_id = new_record_id()
    guide_id = new_record_id()
    source_snapshot_id = new_record_id()
    effective_policy_id = new_record_id()
    pre_submit_policy_id = new_record_id()
    predecessor = SubmissionCanonicalPredecessor(
        submission_id=new_record_id(),
        submission_version=1,
        archive_sha256=request.prepared_artifact.commitment.sha256,
        semantic_manifest_sha256=request.manifest.sha256,
    )
    task = SimpleNamespace(
        contributor_id=actor_profile_id,
        task_id=request.task_id,
        assignment_id=assignment_id,
        checker_remediation_manifest_id=new_record_id(),
        revision_context=SimpleNamespace(preparation_id=new_record_id(), preparation_sha256=SHA),
        predecessor=SimpleNamespace(
            submission_id=predecessor.submission_id,
            version=predecessor.submission_version,
        ),
        locked_project_context=SimpleNamespace(project_id=project_id),
        locked_policy=SimpleNamespace(
            model_dump=lambda **_kwargs: {
                "locked_guide_version": "v1",
                "locked_pre_submit_checker_bundle_hash": SHA,
            }
        ),
    )
    project = SimpleNamespace(
        project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        source_snapshot_id=source_snapshot_id,
        source_snapshot_hash=SHA,
        effective_policy_id=effective_policy_id,
        effective_policy_hash=SHA,
        pre_submit_policy_id=pre_submit_policy_id,
        pre_submit_policy_bundle_hash=SHA,
        external_checker_policies=SimpleNamespace(
            value=json.dumps(
                policies.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
    )
    try:
        bound = bind_selected_pre_submit_admission(
            task=task,
            project=project,
            commitment=request.prepared_artifact.commitment,
            manifest=request.manifest,
            predecessor=predecessor,
            predecessor_rules_sha256="sha256:" + "d" * 64,
            predecessor_exists=True,
            packet=request.packet,
        )
        assert bound.change_gate.outcome.value == "unchanged"
        assert bound.default_input.predecessor is not None
        assert bound.default_input.predecessor_rules_sha256 == "sha256:" + "d" * 64
        assert bound.default_input.current_rules_sha256 == bound.rules_sha256
        assert bound.policy.policy_sha256 == policies.pre_submit.policy_sha256
        reservation = build_selected_pre_submit_reservation(
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            task=task,
            project=project,
            prepared_generation_id=request.prepared_artifact.generation_id,
            attempt_id=new_record_id(),
            idempotency_key=new_record_id(),
            attempt_request_digest=SHA,
            commitment=request.prepared_artifact.commitment,
            manifest=request.manifest,
            packet=request.packet,
            selected=bound,
            storage_scheme="s3",
            execution_budget_ms=120_000,
        )
        assert reservation.admission_lineage is not None
        assert reservation.admission_lineage.semantic_manifest_body == (request.manifest.as_dict())
        assert reservation.admission_lineage.packet_sha256 == request.packet.sha256
        assert reservation.admission_lineage.revision_preparation_id == task.revision_context.preparation_id
        assert reservation.admission_lineage.revision_preparation_sha256 == task.revision_context.preparation_sha256
        assert reservation.admission_lineage.checker_remediation_manifest_id == (
            task.checker_remediation_manifest_id
        )
        assert reservation.admission_lineage.predecessor_submission_id == (
            predecessor.submission_id
        )
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.asyncio
async def test_selected_factory_uses_request_bound_art_grant(tmp_path) -> None:
    request, inspector, manager, preparation = await _request(tmp_path)
    reservation = request.selected_reservation
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation, lease_id=new_record_id(), lease_generation=1,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    transaction = True
    session = SimpleNamespace(in_transaction=lambda: transaction)

    class CommittedAuthority:
        def __init__(self):
            self.calls = 0

        def consume(self, *, run_id, lease):
            assert not transaction
            assert run_id == reservation.attempt_id
            assert lease == expected_lease
            assert self.calls == 0
            self.calls += 1
            return lease

    from app.interfaces.trusted_submission_intake import TrustedDefaultBinding
    expected_binding = TrustedDefaultBinding(
        attempt_id=reservation.attempt_id,
        attempt_request_digest=reservation.request_digest,
        policy_sha256=reservation.policy_sha256,
        semantic_manifest_sha256=reservation.semantic_manifest_sha256,
        default_input_sha256=reservation.default_input_sha256,
    )
    evaluate_default = request.intake.evaluate_default

    async def bound_default(binding, value):
        # The fake is an assertion oracle at the committed owner seam. The
        # guest itself has no independent access to the reservation database.
        assert binding == expected_binding
        assert execution.requests == []
        return await evaluate_default(binding, value)

    request.intake.evaluate_default = bound_default
    expected_lease = lease
    committed = CommittedAuthority()
    execution = _Execution("passed")
    authority = SimpleNamespace(
        prepare=AsyncMock(return_value=object()),
        consume=AsyncMock(),
    )
    service = PreparedBundleMaterializationService(
        session=session,
        authorization=authority,
        preparation=preparation,
        checker_execution=SelectedPreSubmitCheckerExecutionAdapter(
            external_execution=execution,
        ),
        storage_scheme="s3", archive_limits=SubmissionArchiveLimits(),
    )
    try:
        await service.authorize_inspected(request)
        assert authority.consume.await_count == 1
        assert execution.requests == []
        transaction = False
        # A substituted default packet must fail before byte access or grants,
        # even when the committed lease is otherwise exact.
        process = AsyncMock()
        with patch.object(preparation, "_process_prepared_submission", process):
            with pytest.raises(SelectedPreSubmitInfrastructureUnavailable) as refusal:
                await service.materialize_selected_pre_submit(
                    replace(
                        request,
                        prepared_authorization=None,
                        default_checker_input=replace(
                            request.default_checker_input,
                            packet=SubmissionPacketView("Changed packet", "rights_confirmed"),
                        ),
                    ),
                    run_id=reservation.attempt_id, lease=lease,
                    execution_authority=CommittedAuthority(),
                )
            assert refusal.value.code == "material_unavailable"
            process.assert_not_awaited()
            assert execution.requests == []
            for changed_reservation in (
                replace(reservation, attempt_id=new_record_id()),
                replace(reservation, attempt_request_digest="sha256:" + "f" * 64),
            ):
                with pytest.raises(SelectedPreSubmitInfrastructureUnavailable) as refusal:
                    await service.materialize_selected_pre_submit(
                        replace(request, selected_reservation=changed_reservation),
                        run_id=reservation.attempt_id, lease=lease,
                        execution_authority=CommittedAuthority(),
                    )
                assert refusal.value.code == "material_unavailable"
                process.assert_not_awaited()
                assert request.intake.default_bindings == []
                assert execution.requests == []
        result = await service.materialize_selected_pre_submit(
            replace(request, prepared_authorization=None),
            run_id=reservation.attempt_id, lease=lease, execution_authority=committed,
        )
        assert result.eligible is True
        assert request.intake.default_bindings == [expected_binding]
        assert committed.calls == 1
        assert len(execution.requests) == 1
        assert execution.requests[0].identity.attempt_id == reservation.attempt_id
        assert execution.requests[0].materials[0].archive_sha256 == (
            request.prepared_artifact.commitment.sha256
        )
    finally:
        await request.prepared_artifact.close()
        manager.close()
