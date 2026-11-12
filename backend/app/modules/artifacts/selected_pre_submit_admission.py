"""Bind selected PRE policy and default inputs to locked TASK/PROJECT custody."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
    semantic_manifest_identity,
    SubmissionChangeGateResult,
    SubmissionManifest,
    bind_submission_change,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    WorkstreamDefaultContext,
    WorkstreamDefaultPredecessor,
    workstream_default_input_body,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerPolicies,
    LockedExternalPostSubmitPolicy,
    LockedExternalPreSubmitPolicy,
)
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitAdmissionLineage,
    SelectedPreSubmitReservationFacts,
)
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.api import TaskSubmissionContextFacts


def selected_pre_submit_attempt_request_digest(
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
    task_id: UUID,
    assignment_id: UUID,
    predecessor_submission_id: UUID | None,
    idempotency_key: UUID,
    archive_sha256: str,
    archive_byte_count: int,
    packet_sha256: str,
    revision_preparation_id: UUID | None = None,
    revision_preparation_sha256: str | None = None,
) -> str:
    """Bind the public command namespace to server-observed bytes and packet."""
    if (revision_preparation_id is None) != (revision_preparation_sha256 is None):
        raise ValueError("revision preparation acknowledgement is incomplete")
    body = {
        "domain": "workstream.selected_pre_submit_attempt_request.v1",
        "actor_profile_id": str(actor_profile_id),
        "identity_link_id": str(identity_link_id),
        "task_id": str(task_id),
        "assignment_id": str(assignment_id),
        "predecessor_submission_id": (
            str(predecessor_submission_id)
            if predecessor_submission_id is not None
            else None
        ),
        "idempotency_key": str(idempotency_key),
        "archive_sha256": archive_sha256,
        "archive_byte_count": archive_byte_count,
        "packet_sha256": packet_sha256,
    }
    if revision_preparation_id is not None:
        body["revision_preparation_id"] = str(revision_preparation_id)
        body["revision_preparation_sha256"] = revision_preparation_sha256
    return canonical_json_hash(body)


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitAdmissionContext:
    """Exact selected policy, default input and non-deciding change binding."""

    policy: LockedExternalPreSubmitPolicy
    post_policy: LockedExternalPostSubmitPolicy
    policies_sha256: str
    default_input: WorkstreamDefaultCheckerInput
    change_gate: SubmissionChangeGateResult
    rules_sha256: str


def build_selected_pre_submit_reservation(
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
    task: TaskSubmissionContextFacts,
    project: ProjectLockedPolicyContextFacts,
    prepared_generation_id: UUID,
    attempt_id: UUID,
    idempotency_key: UUID,
    attempt_request_digest: str,
    commitment: ArtifactCommitment,
    manifest: SubmissionManifest,
    packet: SubmissionPacketView,
    selected: SelectedPreSubmitAdmissionContext,
    storage_scheme: str,
    execution_budget_ms: int,
) -> SelectedPreSubmitReservationFacts:
    """Bind all later ART-admission facts into the selected durable request."""
    if (
        task.contributor_id != actor_profile_id
        or task.locked_project_context.project_id != project.project_id
        or selected.policy.policy_sha256
        != canonical_json_hash(
            selected.policy.model_dump(mode="json", exclude={"policy_sha256"})
        )
    ):
        raise ValueError("selected PRE reservation context differs")
    predecessor = task.predecessor
    locked_guide_sha256 = canonical_json_hash(
        {
            "domain": "workstream.locked_task_guide.v1",
            "project_id": str(project.project_id),
            "guide_id": str(project.guide_id),
            "guide_version": project.guide_version,
            "source_snapshot_id": str(project.source_snapshot_id),
            "source_snapshot_sha256": project.source_snapshot_hash,
        }
    )
    locked_policy_context_hash = canonical_json_hash(
        {
            "guide_id": str(project.guide_id),
            "guide_version": project.guide_version,
            "source_snapshot_id": str(project.source_snapshot_id),
            "source_snapshot_sha256": project.source_snapshot_hash,
            "locked_guide_sha256": locked_guide_sha256,
            "effective_policy_id": str(project.effective_policy_id),
            "locked_artifact_policy_sha256": project.effective_policy_hash,
            "pre_submit_policy_id": str(project.pre_submit_policy_id),
            "locked_checker_policy_sha256": project.pre_submit_policy_bundle_hash,
            "effective_plan_sha256": selected.policy.policy_sha256,
        }
    )
    lineage = SelectedPreSubmitAdmissionLineage(
        predecessor_submission_id=(
            predecessor.submission_id if predecessor is not None else None
        ),
        predecessor_submission_version=(
            predecessor.version if predecessor is not None else None
        ),
        checker_remediation_manifest_id=task.checker_remediation_manifest_id,
        guide_id=project.guide_id,
        guide_version=project.guide_version,
        source_snapshot_id=project.source_snapshot_id,
        source_snapshot_sha256=project.source_snapshot_hash,
        locked_guide_sha256=locked_guide_sha256,
        effective_policy_id=project.effective_policy_id,
        effective_policy_sha256=project.effective_policy_hash,
        pre_submit_policy_id=project.pre_submit_policy_id,
        pre_submit_policy_sha256=project.pre_submit_policy_bundle_hash,
        effective_plan_sha256=selected.policy.policy_sha256,
        rules_sha256=selected.rules_sha256,
        external_checker_policies_sha256=selected.policies_sha256,
        post_submit_policy_sha256=selected.post_policy.policy_sha256,
        post_submit_policy_body=selected.post_policy.model_dump(mode="json"),
        locked_policy_context_hash=locked_policy_context_hash,
        semantic_manifest_id=semantic_manifest_identity(manifest.sha256),
        semantic_manifest_body=manifest.as_dict(),
        packet_sha256=packet.sha256,
        storage_scheme=storage_scheme,
        revision_preparation_id=(
            task.revision_context.preparation_id if task.revision_context is not None else None
        ),
        revision_preparation_sha256=(
            task.revision_context.preparation_sha256 if task.revision_context is not None else None
        ),
    )
    return SelectedPreSubmitReservationFacts(
        actor_profile_id=actor_profile_id,
        identity_link_id=identity_link_id,
        project_id=project.project_id,
        task_id=task.task_id,
        assignment_id=task.assignment_id,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
        attempt_request_digest=attempt_request_digest,
        prepared_generation_id=prepared_generation_id,
        policy_sha256=selected.policy.policy_sha256,
        default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        default_input_sha256=canonical_json_hash(
            workstream_default_input_body(selected.default_input)
        ),
        archive_sha256=commitment.sha256,
        archive_byte_count=commitment.byte_count,
        semantic_manifest_sha256=manifest.sha256,
        execution_budget_ms=execution_budget_ms,
        admission_lineage=lineage,
    )


def bind_selected_pre_submit_admission(
    *,
    task: TaskSubmissionContextFacts,
    project: ProjectLockedPolicyContextFacts,
    commitment: ArtifactCommitment,
    manifest: SubmissionManifest,
    predecessor: SubmissionCanonicalPredecessor | None,
    predecessor_rules_sha256: str | None,
    predecessor_exists: bool,
    packet: SubmissionPacketView,
) -> SelectedPreSubmitAdmissionContext:
    """Bind genuine locked policy and predecessor facts before CHECKER execution."""
    if project.project_id != task.locked_project_context.project_id:
        raise ValueError("selected PRE task and project contexts differ")
    policies = LockedExternalCheckerPolicies.model_validate_json(
        project.external_checker_policies.value
    )
    rules_sha256 = canonical_json_hash(
        {
            "schema_version": "workstream.task_checker_rules.v1",
            "task_policy": task.locked_policy.model_dump(mode="json"),
            "external_checker_policies_sha256": policies.policies_sha256,
        }
    )
    default_predecessor = (
        WorkstreamDefaultPredecessor(
            submission_id=predecessor.submission_id,
            submission_version=predecessor.submission_version,
            archive_sha256=predecessor.archive_sha256,
            semantic_manifest_sha256=predecessor.semantic_manifest_sha256,
        )
        if predecessor is not None
        else None
    )
    if (predecessor_rules_sha256 is None) != (predecessor is None):
        raise ValueError("selected PRE predecessor rules are incomplete")
    change_gate = bind_submission_change(
        commitment=commitment,
        manifest=manifest,
        predecessor=predecessor,
        predecessor_exists=predecessor_exists,
        current_predecessor=predecessor,
    )
    entries = tuple(
        SubmissionMaterialEntry(
            normalized_path=item.normalized_path,
            entry_type=item.entry_type.value,
            byte_count=item.byte_count,
            sha256=item.sha256,
            executable=item.executable,
        )
        for item in manifest.entries
    )
    return SelectedPreSubmitAdmissionContext(
        policy=policies.pre_submit,
        post_policy=policies.post_submit,
        policies_sha256=policies.policies_sha256,
        default_input=WorkstreamDefaultContext(
            predecessor=default_predecessor,
            predecessor_exists=predecessor_exists,
            current_predecessor=default_predecessor,
            current_rules_sha256=rules_sha256,
            predecessor_rules_sha256=predecessor_rules_sha256,
            packet=packet,
        ).bind_verified_input(
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            archive_media_type=commitment.media_type,
            semantic_manifest_sha256=manifest.sha256,
            entries=entries,
        ),
        change_gate=change_gate,
        rules_sha256=rules_sha256,
    )


__all__ = (
    "SelectedPreSubmitAdmissionContext",
    "bind_selected_pre_submit_admission",
    "build_selected_pre_submit_reservation",
    "selected_pre_submit_attempt_request_digest",
)
