"""Bind sealed source and locked policy context before guest PRE."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata, SubmissionIntakePreSourceFacts
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
)
from app.modules.checkers.api.default_checker import (
    WorkstreamDefaultContext,
    WorkstreamDefaultPredecessor,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerPolicies,
    LockedExternalPostSubmitPolicy,
    LockedExternalPreSubmitPolicy,
)
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitAdmissionLineage,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitRuntimeProfile,
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
    """Locked policy and default context known before source inspection."""

    policy: LockedExternalPreSubmitPolicy
    post_policy: LockedExternalPostSubmitPolicy
    policies_sha256: str
    default_context: WorkstreamDefaultContext
    rules_sha256: str


def build_selected_pre_submit_reservation(
    *,
    source: SubmissionIntakePreSourceFacts,
    metadata: SubmissionIntakeMetadata,
    task: TaskSubmissionContextFacts,
    project: ProjectLockedPolicyContextFacts,
    attempt_id: UUID,
    idempotency_key: UUID,
    selected: SelectedPreSubmitAdmissionContext,
    storage_scheme: str,
    runtime_profile: SelectedPreSubmitRuntimeProfile,
) -> SelectedPreSubmitReservationFacts:
    """Bind T3's locked source to policy/context without host ZIP inspection.

    The composition must hold the source port's root and AUTH custody. Detached
    values are comparisons only; this builder grants neither reads nor execution.
    """
    references = task.locked_project_context
    packet = SubmissionPacketView(metadata.summary, metadata.contributor_attestation)
    if (
        type(source) is not SubmissionIntakePreSourceFacts
        or source.task_id != task.task_id or source.assignment_id != task.assignment_id
        or source.actor_profile_id != task.contributor_id
        or source.project_id != project.project_id
        or metadata.task_id != task.task_id or metadata.assignment_id != task.assignment_id
        or metadata.metadata_sha256() != source.metadata_sha256
        or metadata.predecessor_submission_id != (
            task.predecessor.submission_id if task.predecessor else None)
        or metadata.revision_preparation_id != (
            task.revision_context.preparation_id if task.revision_context else None)
        or metadata.revision_preparation_sha256 != (
            task.revision_context.preparation_sha256 if task.revision_context else None)
        or references.project_id != project.project_id
        or references.guide_version != project.guide_version
        or references.source_snapshot_id != project.source_snapshot_id
        or references.source_snapshot_hash != project.source_snapshot_hash
        or references.effective_policy_id != project.effective_policy_id
        or references.effective_policy_hash != project.effective_policy_hash
        or references.pre_submit_policy_id != project.pre_submit_policy_id
        or references.pre_submit_policy_bundle_hash != project.pre_submit_policy_bundle_hash
        or selected.default_context.packet != packet
        or selected.default_context.predecessor_exists != (task.predecessor is not None)
        or selected.default_context.current_predecessor != selected.default_context.predecessor
    ):
        raise ValueError("selected PRE reservation context differs")
    policies = LockedExternalCheckerPolicies.model_validate_json(project.external_checker_policies.value)
    expected_rules = canonical_json_hash({
        "schema_version": "workstream.task_checker_rules.v1",
        "task_policy": task.locked_policy.model_dump(mode="json"),
        "external_checker_policies_sha256": policies.policies_sha256,
    })
    if (selected.policy != policies.pre_submit or selected.post_policy != policies.post_submit
            or selected.policies_sha256 != policies.policies_sha256
            or selected.rules_sha256 != expected_rules
            or selected.default_context.current_rules_sha256 != expected_rules):
        raise ValueError("selected PRE policy context differs")
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
        actor_profile_id=source.actor_profile_id, identity_link_id=source.identity_link_id,
        project_id=project.project_id, task_id=task.task_id, assignment_id=task.assignment_id,
        attempt_id=attempt_id, idempotency_key=idempotency_key,
        source=source.source, metadata_sha256=source.metadata_sha256,
        locked_context_sha256=source.locked_context_sha256,
        foreground_lease_id=source.lease_id, foreground_lease_generation=source.lease_generation,
        pre_deadline_at=source.pre_deadline_at, policy=selected.policy,
        default_context=selected.default_context, runtime_profile=runtime_profile,
        admission_lineage=lineage,
    )


def bind_selected_pre_submit_admission(
    *,
    task: TaskSubmissionContextFacts,
    project: ProjectLockedPolicyContextFacts,
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
    if (predecessor_exists != (predecessor is not None)
            or (predecessor.submission_id if predecessor else None) != (
                task.predecessor.submission_id if task.predecessor else None)
            or (predecessor.submission_version if predecessor else None) != (
                task.predecessor.version if task.predecessor else None)):
        raise ValueError("selected PRE predecessor differs from locked TASK")
    return SelectedPreSubmitAdmissionContext(
        policy=policies.pre_submit,
        post_policy=policies.post_submit,
        policies_sha256=policies.policies_sha256,
        default_context=WorkstreamDefaultContext(
            predecessor=default_predecessor,
            predecessor_exists=predecessor_exists,
            current_predecessor=default_predecessor,
            current_rules_sha256=rules_sha256,
            predecessor_rules_sha256=predecessor_rules_sha256,
            packet=packet,
        ),
        rules_sha256=rules_sha256,
    )


__all__ = (
    "SelectedPreSubmitAdmissionContext",
    "bind_selected_pre_submit_admission",
    "build_selected_pre_submit_reservation",
    "selected_pre_submit_attempt_request_digest",
)
