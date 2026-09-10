"""Locked finalization facts and exact custody validation, without execution ports."""

from __future__ import annotations

from dataclasses import dataclass, fields
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.authorization.api import (
    FINALIZATION_ACTION,
    FINALIZATION_PERMISSION,
    FINALIZATION_RESOURCE,
    FINALIZATION_SERVICE,
    ProjectSetupFinalizationAuthorityReceipt,
    ProjectSetupFinalizationFacts,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_identity,
    setup_finalization_authority_digest,
    setup_finalization_fact_values,
    setup_finalization_facts_digest,
    setup_finalization_identity,
)
from app.modules.projects.api import (
    ProjectGuideSetupFinalizationCommand,
    ProjectGuideSetupFinalizationError,
    ProjectGuideSetupFinalizationReceipt,
)
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSufficiencyReport,
    ProjectGuide,
    ProjectSetupRun,
    SubmissionArtifactPolicy,
)
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

from .contracts import AcceptedCompilationResult
from .custody_payloads import policy_digest, report_digest, source_state
from .models import (
    ProjectGuideCompilation,
    ProjectGuideCompilationAttempt,
    ProjectGuideCompilationRequestOperation,
    ProjectGuideComponentProjectionOperation,
    ProjectGuideSetupFinalization,
)


@dataclass(frozen=True)
class LockedFinalization:
    """One locked view; repository and strict tests preserve the same owner shape."""

    attempt: ProjectGuideCompilationAttempt
    request: ProjectGuideCompilationRequestOperation
    guide: ProjectGuide
    snapshot: GuideSourceSnapshot
    setup: ProjectSetupRun
    compilation: ProjectGuideCompilation
    compilation_is_current: bool
    operations: tuple[ProjectGuideComponentProjectionOperation, ...]
    report: GuideSufficiencyReport | None
    policy: SubmissionArtifactPolicy | None


def deny() -> None:
    """Conceal every missing, foreign, stale or inconsistent source."""
    raise ProjectGuideSetupFinalizationError("source_state_unavailable")


def require_lineage(
    view: LockedFinalization, command: ProjectGuideSetupFinalizationCommand
) -> None:
    """Bind every selected row to the latest locked draft and persisted attempt."""
    a, c, s, g, snap, request = (
        view.attempt,
        view.compilation,
        view.setup,
        view.guide,
        view.snapshot,
        view.request,
    )
    if any(row is None for row in (a, c, s, g, snap, request)):
        deny()
    if (
        not view.compilation_is_current
        or c.id != command.compilation_id
        or s.id != str(command.setup_run_id)
        or s.setup_generation != command.setup_generation
        or g.id != str(command.guide_id)
        or g.project_id != str(command.project_id)
        or g.status != "draft"
        or a.status != "compilation_persisted"
        or a.persisted_compilation_id != c.id
        or c.attempt_id != a.id
        or request.attempt_id != a.id
        or s.celery_task_id != project_guide_compilation_task_id(s.id, s.setup_generation)
    ):
        deny()
    for row in (a, c, s, snap, request):
        if row.project_id != str(command.project_id) or row.guide_id != g.id:
            deny()
    for row in (a, c, s):
        if (
            row.guide_version != g.version
            or row.source_snapshot_id != snap.id
            or row.source_snapshot_hash != snap.bundle_hash
        ):
            deny()
    if snap.guide_version != g.version:
        deny()
    for row in (a, c, request):
        if row.setup_run_id != s.id or row.setup_generation != s.setup_generation:
            deny()
    if request.source_snapshot_id != snap.id or a.canonical_input_hash != c.canonical_input_hash:
        deny()


def require_source_shape(view: LockedFinalization) -> str:
    """Validate the sole queued source shape and hash it using the projection owner."""
    s = view.setup
    if (
        s.status != "queued"
        or s.current_step != "queued"
        or s.documents_ready_at is None
    ):
        deny()
    for name in (
        "error_code",
        "error_artifact_incident_id",
        "error_summary",
        "started_at",
        "finished_at",
        "post_submit_derivation_summary",
        "output_sufficiency_report_id",
        "output_submission_artifact_policy_id",
        "output_post_submit_checker_policy_id",
    ):
        if getattr(s, name) is not None:
            deny()
    return canonical_json_hash(
        {
            "domain": "workstream.project_guide_projection.source_state.v1",
            "facts": source_state(view.guide, view.snapshot, s),
        }
    )


def compose_facts(view: LockedFinalization, source_digest: str) -> ProjectSetupFinalizationFacts:
    """Validate accepted content and its complete exact existing projection set."""
    c, a, s = view.compilation, view.attempt, view.setup
    accepted = AcceptedCompilationResult(
        canonical_result=c.canonical_result,
        result_hash=c.result_hash,
        component_hashes=c.component_hashes,
    )
    result = accepted.canonical_result
    classification = result["status"]
    expected = (
        {"guide_sufficiency"}
        if classification == "guide_blocked"
        else {"guide_sufficiency", "submission_artifact_policy"}
    )
    ops = {op.component: op for op in view.operations}
    if set(ops) != expected or len(ops) != len(view.operations):
        deny()
    report_op = ops["guide_sufficiency"]
    policy_op = ops.get("submission_artifact_policy")
    for op in view.operations:
        require_projection(view, op, source_digest, result)
    require_outputs(view, report_op, policy_op, result)
    receipt_id, operation_id, correlation_id = setup_finalization_identity(
        UUID(s.id), s.setup_generation, c.id
    )
    return ProjectSetupFinalizationFacts(
        project_id=UUID(c.project_id),
        guide_id=UUID(c.guide_id),
        guide_version=c.guide_version,
        source_snapshot_id=UUID(c.source_snapshot_id),
        source_snapshot_hash=c.source_snapshot_hash,
        setup_run_id=UUID(s.id),
        setup_generation=s.setup_generation,
        celery_task_id=UUID(s.celery_task_id),
        source_state_digest=source_digest,
        finalization_id=receipt_id,
        operation_id=operation_id,
        correlation_id=correlation_id,
        attempt_id=a.id,
        request_operation_id=view.request.operation_id,
        provider_idempotency_key=a.provider_idempotency_key,
        compilation_id=c.id,
        canonical_input_hash=c.canonical_input_hash,
        result_hash=c.result_hash,
        result_schema_version=result["schema_version"],
        compilation_agent_name=result["agent_name"],
        compilation_agent_version=result["agent_version"],
        component_hashes=tuple(sorted(c.component_hashes.items())),
        result_classification=classification,
        setup_outcome="sufficiency_blocked"
        if classification == "guide_blocked"
        else "policy_draft_ready",
        sufficiency_operation_id=report_op.operation_id,
        sufficiency_report_id=UUID(report_op.report_id),
        sufficiency_output_digest=report_op.output_digest,
        artifact_policy_operation_id=policy_op.operation_id if policy_op else None,
        artifact_policy_id=UUID(policy_op.policy_id) if policy_op else None,
        artifact_policy_output_digest=policy_op.output_digest if policy_op else None,
    )


def require_projection(view, op, source_digest, result) -> None:
    """Check immutable operation identity, all compilation lineage and pre-finalization state."""
    c, a, s = view.compilation, view.attempt, view.setup
    for name in (
        "project_id",
        "guide_id",
        "guide_version",
        "source_snapshot_id",
        "source_snapshot_hash",
        "setup_run_id",
        "setup_generation",
        "result_hash",
    ):
        if getattr(op, name) != getattr(c, name):
            deny()
    if (
        op.compilation_id != c.id
        or op.attempt_id != a.id
        or op.request_operation_id != view.request.operation_id
        or op.provider_idempotency_key != a.provider_idempotency_key
        or op.celery_task_id != s.celery_task_id
        or op.source_state_digest != source_digest
        or op.result_schema_version != result["schema_version"]
        or op.compilation_agent_name != result["agent_name"]
        or op.compilation_agent_version != result["agent_version"]
    ):
        deny()
    sufficient = op.component == "guide_sufficiency"
    factory = (
        guide_sufficiency_projection_identity if sufficient else artifact_policy_projection_identity
    )
    identity = factory(
        attempt_id=a.id,
        actor_profile_id=UUID(op.actor_profile_id),
        identity_link_id=UUID(op.identity_link_id),
    )
    if (
        op.operation_id != identity.operation_id
        or op.output_id != identity.output_id
        or op.correlation_id != identity.correlation_id
        or op.component_hash
        != c.component_hashes["sufficiency_hash" if sufficient else "artifact_policy_hash"]
    ):
        deny()


def require_outputs(view, report_op, policy_op, result) -> None:
    """Recompute business output digests and require the exact sufficiency predecessor."""
    report = view.report
    if (
        report is None
        or report_op.report_id != report.id
        or report.id != str(report_op.output_id)
        or report_op.policy_id is not None
        or report_op.prior_operation_id is not None
        or report_op.prior_output_id is not None
        or report_op.prior_output_digest is not None
        or report_digest(report) != report_op.output_digest
        or report.status
        != {
            "guide_blocked": "blocked",
            "draft_ready": "passed",
            "draft_ready_with_warnings": "passed_with_warnings",
        }[result["status"]]
        or report.project_setup_run_id != view.setup.id
        or report.setup_generation != view.setup.setup_generation
        or report.agent_material_sha256 != view.attempt.guide_material_hash
    ):
        deny()
    for output in (report, view.policy) if policy_op else (report,):
        if output is None:
            deny()
        for name in (
            "project_id",
            "guide_id",
            "guide_version",
            "source_snapshot_id",
            "source_snapshot_hash",
        ):
            if getattr(output, name) != getattr(view.compilation, name):
                deny()
    if policy_op is None:
        if view.policy is not None:
            deny()
        return
    if (
        view.policy.id != policy_op.policy_id
        or view.policy.id != str(policy_op.output_id)
        or policy_op.report_id is not None
        or policy_op.prior_operation_id != report_op.operation_id
        or policy_op.prior_output_id != report_op.output_id
        or policy_op.prior_output_digest != report_op.output_digest
        or policy_digest(view.policy) != policy_op.output_digest
        or view.policy.lifecycle_status != "draft"
        or view.policy.derivation_source != "unified_compilation"
    ):
        deny()


def require_authority(authority, facts) -> None:
    """Reject wrong type or any incorrect authority receipt field before mutation."""
    if not isinstance(authority, ProjectSetupFinalizationAuthorityReceipt):
        raise ProjectGuideSetupFinalizationError("service_authority_denied")
    if (
        authority.action_id != FINALIZATION_ACTION
        or authority.permission_id != FINALIZATION_PERMISSION
        or authority.service_identity != FINALIZATION_SERVICE
        or authority.scope_project_id != facts.project_id
        or authority.resource_type != FINALIZATION_RESOURCE
        or authority.resource_id != facts.finalization_id
        or authority.resource_context_digest
        != setup_finalization_authority_digest(
            facts, authority.actor_profile_id, authority.identity_link_id
        )
    ):
        raise ProjectGuideSetupFinalizationError("service_authority_denied")


def require_replay(view, row, facts) -> None:
    """Compare every stored fact, custody digest and the exact database-owned post-state."""
    for field in fields(facts):
        actual = getattr(row, "id" if field.name == "finalization_id" else field.name)
        expected = getattr(facts, field.name)
        if field.name == "component_hashes":
            expected = dict(expected)
        elif isinstance(expected, UUID) and isinstance(actual, str):
            expected = str(expected)
        if actual != expected:
            deny()
    if (
        row.facts_digest != setup_finalization_facts_digest(facts)
        or row.authority_resource_digest
        != setup_finalization_authority_digest(
            facts, UUID(row.actor_profile_id), UUID(row.identity_link_id)
        )
        or row.service_identity != FINALIZATION_SERVICE
        or row.action_id != FINALIZATION_ACTION
        or row.permission_id != FINALIZATION_PERMISSION
        or row.scope_type != "project"
        or row.scope_project_id != str(facts.project_id)
    ):
        deny()
    s = view.setup
    if (
        s.status != facts.setup_outcome
        or s.current_step != diagnostic_step(facts.setup_outcome)
        or s.output_sufficiency_report_id != str(facts.sufficiency_report_id)
        or s.output_submission_artifact_policy_id
        != (str(facts.artifact_policy_id) if facts.artifact_policy_id else None)
        or s.finished_at is None
        or row.created_at is None
        or s.finished_at != row.created_at
    ):
        deny()


def diagnostic_step(outcome: str) -> str:
    """Return a diagnostic step, never a second lifecycle status."""
    return (
        "guide_sufficiency"
        if outcome == "sufficiency_blocked"
        else "submission_artifact_policy_derivation"
    )


def new_row(facts, authority) -> ProjectGuideSetupFinalization:
    """Build the immutable product receipt after prepared authority has closed."""
    values = setup_finalization_fact_values(facts)
    values["id"] = facts.finalization_id
    del values["finalization_id"]
    for name in (
        "operation_id",
        "correlation_id",
        "attempt_id",
        "request_operation_id",
        "provider_idempotency_key",
        "compilation_id",
        "sufficiency_operation_id",
        "artifact_policy_operation_id",
    ):
        values[name] = getattr(facts, name)
    return ProjectGuideSetupFinalization(
        **values,
        facts_digest=setup_finalization_facts_digest(facts),
        authority_resource_digest=authority.resource_context_digest,
        authorization_decision_event_id=str(authority.decision_event_id),
        actor_profile_id=str(authority.actor_profile_id),
        identity_link_id=str(authority.identity_link_id),
        service_identity=authority.service_identity,
        action_id=authority.action_id,
        permission_id=authority.permission_id,
        scope_type="project",
        scope_project_id=str(facts.project_id),
    )


def public_receipt(row) -> ProjectGuideSetupFinalizationReceipt:
    """Return only the explicitly bounded immutable public result."""
    return ProjectGuideSetupFinalizationReceipt(
        finalization_id=row.id,
        **{
            name: getattr(row, name)
            for name in ProjectGuideSetupFinalizationReceipt.model_fields
            if name != "finalization_id"
        },
    )
