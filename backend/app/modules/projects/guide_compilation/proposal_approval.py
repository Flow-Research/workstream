"""Atomic pre-policy approval using existing reservation and CHECKERS compilers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import validate_project_guide_compilation_result
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorizationFacts,
    GuideProposalAuthorizationLocator,
    PreparedGuideProposalOperation,
)
from app.modules.checkers.api.policy_compilation import (
    CompiledPreSubmitCheckerPolicy, PreSubmissionPolicyCompilationPort,
)
from app.modules.checkers.api.pre_submit import (
    EffectivePreSubmissionPlanLineage,
    EffectivePreSubmissionExecutionPlan,
)
from app.modules.projects.api.guide_proposals import (
    GuideProposalApprovalReceipt,
    GuideProposalError,
    GuideProposalSelection,
)
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    PreSubmitCheckerPolicy,
)
from app.modules.projects.service import MERGE_ALGORITHM_VERSION, ProjectService
from app.modules.projects.submission_policy_mutation_repository import (
    SubmissionPolicyMutationReplayRepository,
)

from .proposal_authority import proposal_resource_json, require_proposal_authority
from .custody_payloads import policy_digest
from .models import ProjectGuideProposalApproval
from .proposal_repository import GuideProposalRepository
from .request_inputs import CompilationRequestInputs


APPROVAL_ACTION = "project.submission_artifact_policy.approve"


async def approve_proposal(
    session,
    authorization,
    command,
    *,
    actor,
    request_id,
    material,
    pre_capabilities,
    post_capabilities,
    planner: PreSubmissionPolicyCompilationPort,
) -> GuideProposalApprovalReceipt:
    """Compile and persist in the caller transaction after exact authority closes."""
    target = command.target
    operation_id = uuid5(
        NAMESPACE_URL,
        f"workstream.guide-proposal-approval:{actor.actor_profile_id}:{command.idempotency_key}",
    )
    locator = GuideProposalAuthorizationLocator(
        project_id=target.project_id,
        guide_id=target.guide_id,
        compilation_id=target.compilation_id,
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        action_id=APPROVAL_ACTION,
        operation_id=operation_id,
        request_id=request_id,
    )
    repository = GuideProposalRepository(session)
    replay_repository = SubmissionPolicyMutationReplayRepository(session)
    request_digest = canonical_json_hash(command.model_dump(mode="json"))
    async with authorization.prepare_proposal_operation(locator) as prepared:
        if not isinstance(prepared, PreparedGuideProposalOperation):
            raise GuideProposalError("authority_unavailable")
        locked = await repository.lock(
            GuideProposalSelection(
                project_id=target.project_id,
                guide_id=target.guide_id,
                compilation_id=target.compilation_id,
            )
        )
        if locked.target != target:
            raise GuideProposalError("proposal_stale")
        package = await repository.package(locked)
        existing = await session.get(ProjectGuideProposalApproval, operation_id)
        if existing is not None:
            return await _replay_approval(
                existing, target, request_digest, actor, package, locator, command, prepared
            )
        if not locked.current:
            raise GuideProposalError("proposal_stale")
        _require_catalogues(target, pre_capabilities, post_capabilities)
        if (
            locked.result.status == "guide_blocked"
            or locked.view.policy is None
            or command.acknowledged_warning_hashes != package.warning_hashes
        ):
            raise GuideProposalError("approval_blocked")
        if (
            locked.view.policy.lifecycle_status != "draft"
            or package.current_approval_operation_id
            != command.expected_previous_approval_operation_id
            or package.current_approval_output_digest
            != command.expected_previous_approval_output_digest
        ):
            raise GuideProposalError("proposal_stale")
        previous = await _previous_outputs(session, command.expected_previous_approval_operation_id)
        outputs = await _compile_approval(
            session,
            locked,
            command,
            operation_id,
            material,
            pre_capabilities,
            post_capabilities,
            planner,
        )
        receipt = outputs.receipt
        facts = _facts(locator, target, request_digest, receipt, command)
        authority = await prepared.consume_new(facts)
        require_proposal_authority(authority, facts, actor, "project.effective_policy.manage")
    # A failing capability close cannot leave a policy write or reservation.
    return await _persist_approval(
        session,
        replay_repository,
        command,
        actor,
        locked,
        previous,
        outputs,
        facts,
        authority,
    )


@dataclass(frozen=True)
class _CompiledApproval:
    """Compiler outputs staged before consuming authority or changing policy rows."""

    effective_body: dict
    compiled: CompiledPreSubmitCheckerPolicy
    plan: EffectivePreSubmissionExecutionPlan
    receipt: GuideProposalApprovalReceipt


async def _compile_approval(
    session,
    locked,
    command,
    operation_id,
    material,
    pre_capabilities,
    post_capabilities,
    planner,
) -> _CompiledApproval:
    target = command.target
    inputs = CompilationRequestInputs(
        material,
        pre_capabilities,
        post_capabilities,
        ProjectGuideRuntimeConfiguration.model_validate(locked.view.attempt.runtime_configuration),
    )
    context = await inputs.context_for_setup(session, locked.view.setup)
    validate_project_guide_compilation_result(context, locked.result)
    effective_body = ProjectService(session)._merge_effective_submission_artifact_policy(
        locked.view.policy.policy_body,
    )
    effective_hash = canonical_json_hash(effective_body)
    compiled = planner.compile_policy_bundle(
        effective_policy=effective_body, effective_policy_hash=effective_hash,
    )
    effective_id, pre_id = (
        uuid5(operation_id, "effective-policy"),
        uuid5(operation_id, "pre-policy"),
    )
    version = target.guide_version
    plan = planner.compile_effective_plan(
        lineage=EffectivePreSubmissionPlanLineage(
            project_id=target.project_id,
            guide_id=target.guide_id,
            guide_version=version,
            source_snapshot_id=target.source_snapshot_id,
            source_snapshot_hash=target.source_snapshot_hash,
            effective_policy_id=effective_id,
            effective_policy_hash=effective_hash,
            pre_submit_policy_id=pre_id,
            pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
        ),
        effective_policy=effective_body,
        compiled_bundle=compiled.compiled_bundle,
    )
    if plan.catalogue_manifest_sha256 != target.pre_catalogue_manifest_hash:
        raise GuideProposalError("approval_blocked")
    # Catalogue-valid intent is not enforcement: optional policy primitives are
    # emitted only when the actual merged policy configures them. CHECKERS owns
    # that configuration validation; reconcile selections with its resulting plan.
    enforced = {
        (entry.definition_id, entry.definition_version)
        for entry in plan.entries
        if entry.checker_definition_state == "enabled"
    }
    if any(
        (binding.capability_id, binding.capability_version) not in enforced
        for binding in locked.result.pre_submit_bindings
    ):
        raise GuideProposalError("approval_blocked")
    receipt = GuideProposalApprovalReceipt(
        operation_id=operation_id,
        target_digest=target.digest,
        artifact_policy_id=target.artifact_policy_id,
        effective_policy_id=effective_id,
        effective_policy_hash=effective_hash,
        pre_submit_policy_id=pre_id,
        pre_submit_bundle_hash=compiled.compiled_bundle_hash,
        effective_pre_submit_plan_hash=plan.plan_sha256,
        acknowledged_warning_hashes=command.acknowledged_warning_hashes,
    )
    return _CompiledApproval(effective_body, compiled, plan, receipt)


async def _persist_approval(
    session,
    replay_repository,
    command,
    actor,
    locked,
    previous,
    outputs,
    facts,
    authority,
) -> GuideProposalApprovalReceipt:
    target = command.target
    operation_id = outputs.receipt.operation_id
    request_digest = facts.request_digest
    # A failing capability close cannot leave a policy write or reservation.
    resource_json = proposal_resource_json(facts)
    status, _ = await replay_repository.reserve(
        actor_profile_id=str(actor.actor_profile_id),
        identity_link_id=str(actor.identity_link_id),
        action_id=APPROVAL_ACTION,
        idempotency_key=command.idempotency_key,
        request_digest=request_digest,
        resource_context_digest=facts.digest,
        resource_context_json=resource_json,
        operation_id=operation_id,
        project_id=str(target.project_id),
        guide_id=str(target.guide_id),
        source_snapshot_id=str(target.source_snapshot_id),
        policy_id=str(target.artifact_policy_id),
        setup_generation=target.setup_generation,
    )
    if status != "claimed":
        raise GuideProposalError("operation_conflict")
    now = datetime.now(UTC)
    policy = locked.view.policy
    effective, pre = _approved_rows(policy, target, actor, previous, outputs, authority, now)
    if previous is not None:
        from app.modules.projects.models import SubmissionArtifactPolicy

        prior_policy = await session.get(
            SubmissionArtifactPolicy, previous.operation.artifact_policy_id
        )
        for row in (prior_policy, previous.effective, previous.pre):
            row.lifecycle_status = "superseded"
            row.superseded_at = now
    session.add_all((effective, pre))
    await session.flush()
    return await _commit_provenance(
        session,
        replay_repository,
        command,
        actor,
        outputs,
        facts,
        authority,
        policy,
        effective,
        pre,
    )


def _facts(locator, target, request_digest, receipt, command):
    return GuideProposalAuthorizationFacts(
        locator=locator,
        finalization_id=target.finalization_id,
        artifact_policy_id=target.artifact_policy_id,
        setup_run_id=target.setup_run_id,
        setup_generation=target.setup_generation,
        target_digest=target.digest,
        request_digest=request_digest,
        output_digest=canonical_json_hash(receipt.model_dump(mode="json")),
        current_approval_operation_id=command.expected_previous_approval_operation_id,
        current_approval_output_digest=command.expected_previous_approval_output_digest,
    )


def _require_catalogues(target, pre, post):
    if (
        not pre.available
        or (pre.catalogue_id, pre.version, pre.schema_version, pre.manifest_sha256)
        != (
            target.pre_catalogue_id,
            target.pre_catalogue_version,
            target.pre_catalogue_schema_version,
            target.pre_catalogue_manifest_hash,
        )
        or (post.catalogue_id, post.source_version, post.schema_version, post.manifest_sha256)
        != (
            target.post_catalogue_id,
            target.post_catalogue_version,
            target.post_catalogue_schema_version,
            target.post_catalogue_manifest_hash,
        )
    ):
        raise GuideProposalError("proposal_stale")


def _provenance(authority):
    return dict(
        created_by_actor_profile_id=str(authority.actor_profile_id),
        created_via_identity_link_id=str(authority.identity_link_id),
        created_by_admin_role_grant_id=authority.admin_role_grant_id,
        creation_scope_type="project",
        creation_scope_project_id=str(authority.scope_project_id),
        creation_action_id=APPROVAL_ACTION,
        creation_decision_event_id=str(authority.authorization_decision_event_id),
    )


def _set_authority(policy, authority):
    policy.approved_by_actor_profile_id = str(authority.actor_profile_id)
    policy.approved_via_identity_link_id = str(authority.identity_link_id)
    policy.approved_by_admin_role_grant_id = authority.admin_role_grant_id
    policy.approval_scope_type = "project"
    policy.approval_scope_project_id = str(authority.scope_project_id)
    policy.approval_action_id = APPROVAL_ACTION
    policy.approval_decision_event_id = str(authority.authorization_decision_event_id)


async def _previous_outputs(session, operation_id):
    if operation_id is None:
        return None
    from .approval_custody import load_approval_custody, lock_policy_approval
    from app.modules.projects.models import (
        ProjectGuide,
        GuideSourceSnapshot,
        SubmissionArtifactPolicy,
    )

    operation = await session.scalar(
        select(ProjectGuideProposalApproval).where(
            ProjectGuideProposalApproval.operation_id == operation_id,
        )
    )
    if operation is None:
        raise GuideProposalError("proposal_stale")
    custody = await load_approval_custody(session, operation.artifact_policy_id)
    if custody is None:
        raise GuideProposalError("proposal_stale")
    policy = await session.get(SubmissionArtifactPolicy, operation.artifact_policy_id)
    guide = await session.get(ProjectGuide, operation.guide_id)
    snapshot = await session.get(GuideSourceSnapshot, operation.target_json["source_snapshot_id"])
    if policy is None or guide is None or snapshot is None:
        raise GuideProposalError("proposal_stale")
    return await lock_policy_approval(
        session, guide, snapshot, policy, custody.effective, custody.pre
    )


async def _replay_approval(
    existing, target, request_digest, actor, package, locator, command, prepared
):
    """Return only the exact committed approval through current authority."""
    if (
        existing.target_digest != target.digest
        or existing.request_digest != request_digest
        or existing.actor_profile_id != str(actor.actor_profile_id)
        or existing.identity_link_id != str(actor.identity_link_id)
    ):
        raise GuideProposalError("operation_conflict")
    receipt = GuideProposalApprovalReceipt.model_validate(existing.receipt_json)
    facts = _facts(locator, target, request_digest, receipt, command)
    if facts.digest != existing.resource_context_digest:
        raise GuideProposalError("operation_conflict")
    # The request ID is transport provenance, so replay validates stored
    # committed facts through current authority rather than consuming again.
    await prepared.validate_replay(facts, UUID(existing.authorization_decision_event_id))
    return receipt


def _approved_rows(policy, target, actor, previous, outputs, authority, now):
    """Apply authorized lifecycle fields and construct canonical compiler output rows."""
    receipt, compiled = outputs.receipt, outputs.compiled
    effective_body, effective_hash = outputs.effective_body, receipt.effective_policy_hash
    effective_id, pre_id = receipt.effective_policy_id, receipt.pre_submit_policy_id
    policy.lifecycle_status = "approved"
    policy.approved_by_role = "project_manager"
    policy.approved_by_actor = str(actor.actor_profile_id)
    policy.approved_at = now
    policy.supersedes_policy_id = previous.operation.artifact_policy_id if previous else None
    _set_authority(policy, authority)
    provenance = _provenance(authority)
    effective = EffectiveProjectSubmissionArtifactPolicy(
        id=str(effective_id),
        project_id=str(target.project_id),
        guide_id=str(target.guide_id),
        guide_version=target.guide_version,
        source_snapshot_id=str(target.source_snapshot_id),
        source_snapshot_hash=target.source_snapshot_hash,
        submission_artifact_policy_id=policy.id,
        submission_artifact_policy_hash=policy.policy_hash,
        lifecycle_status="approved",
        merge_algorithm_version=MERGE_ALGORITHM_VERSION,
        effective_policy=effective_body,
        effective_policy_hash=effective_hash,
        created_by=str(actor.actor_profile_id),
        supersedes_effective_policy_id=previous.effective.id if previous else None,
        **provenance,
    )
    pre = PreSubmitCheckerPolicy(
        id=str(pre_id),
        project_id=str(target.project_id),
        guide_id=str(target.guide_id),
        guide_version=target.guide_version,
        source_snapshot_id=str(target.source_snapshot_id),
        source_snapshot_hash=target.source_snapshot_hash,
        effective_policy_id=effective.id,
        effective_policy_hash=effective_hash,
        lifecycle_status="compiled",
        compiler_version=compiled.compiler_version,
        compiled_bundle=compiled.compiled_bundle,
        compiled_bundle_hash=compiled.compiled_bundle_hash,
        checker_names=compiled.checker_names,
        checker_configs=compiled.checker_configs,
        created_by=str(actor.actor_profile_id),
        supersedes_pre_submit_checker_policy_id=previous.pre.id if previous else None,
        **provenance,
    )
    return effective, pre


async def _commit_provenance(
    session, replay_repository, command, actor, outputs, facts, authority, policy, effective, pre
):
    """Commit the existing reservation and its immutable approval provenance together."""
    target, receipt, plan = command.target, outputs.receipt, outputs.plan
    operation_id, request_digest = receipt.operation_id, facts.request_digest
    await replay_repository.complete(
        operation_id,
        actor_profile_id=str(actor.actor_profile_id),
        identity_link_id=str(actor.identity_link_id),
        action_id=APPROVAL_ACTION,
        idempotency_key=command.idempotency_key,
        request_digest=request_digest,
        resource_context_digest=facts.digest,
        setup_generation=target.setup_generation,
        response_json=receipt.model_dump(mode="json"),
        committed_policy_id=policy.id,
        committed_effective_policy_id=effective.id,
        committed_pre_submit_policy_id=pre.id,
    )
    session.add(
        ProjectGuideProposalApproval(
            operation_id=operation_id,
            project_id=str(target.project_id),
            guide_id=str(target.guide_id),
            compilation_id=target.compilation_id,
            finalization_id=target.finalization_id,
            target_json=target.model_dump(mode="json"),
            target_digest=target.digest,
            request_digest=request_digest,
            resource_context_digest=facts.digest,
            output_digest=canonical_json_hash(receipt.model_dump(mode="json")),
            receipt_json=receipt.model_dump(mode="json"),
            artifact_policy_id=policy.id,
            effective_policy_id=effective.id,
            pre_submit_policy_id=pre.id,
            approved_policy_output_digest=policy_digest(policy),
            effective_pre_submit_plan=plan.as_dict(),
            effective_pre_submit_plan_hash=plan.plan_sha256,
            prior_approval_operation_id=command.expected_previous_approval_operation_id,
            actor_profile_id=str(actor.actor_profile_id),
            identity_link_id=str(actor.identity_link_id),
            admin_role_grant_id=authority.admin_role_grant_id,
            authorization_decision_event_id=str(authority.authorization_decision_event_id),
        )
    )
    await session.flush()
    return receipt
