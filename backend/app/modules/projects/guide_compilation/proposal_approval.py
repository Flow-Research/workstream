"""Atomic pre-policy approval using existing reservation and CHECKERS compilers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorizationFacts,
    GuideProposalAuthorizationLocator,
    PreparedGuideProposalOperation,
)
from app.modules.checkers.api.policy_custody import CompiledPreSubmitCheckerPolicy
from app.modules.checkers.api.external import ExternalCheckerRegistryPort
from app.modules.model_usage.api import ModelProfileReaderPort
from app.modules.checkers.api.external_policy import (
    ExternalCheckerPolicyCompileRequest,
    ExternalCheckerPolicyError,
    LockedExternalCheckerPolicies,
    compile_external_checker_policy_bundle,
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


APPROVAL_ACTION = "project.submission_artifact_policy.approve"


def approval_authorization_selector(actor_profile_id: UUID, idempotency_key: UUID) -> UUID:
    """Stable non-row selector used only to prepare approval authority."""
    return uuid5(
        NAMESPACE_URL,
        f"workstream.guide-proposal-approval:{actor_profile_id}:{idempotency_key}",
    )


async def approve_proposal(
    session,
    authorization,
    command,
    *,
    actor,
    request_id,
    registry: ExternalCheckerRegistryPort,
    profiles: ModelProfileReaderPort | None = None,
) -> GuideProposalApprovalReceipt:
    """Compile and persist in the caller transaction after exact authority closes."""
    target = command.target
    selector_id = approval_authorization_selector(actor.actor_profile_id, command.idempotency_key)
    locator = GuideProposalAuthorizationLocator(
        project_id=target.project_id,
        guide_id=target.guide_id,
        compilation_id=target.compilation_id,
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        action_id=APPROVAL_ACTION,
        operation_id=selector_id,
        request_id=request_id,
    )
    repository = GuideProposalRepository(session)
    replay_repository = SubmissionPolicyMutationReplayRepository(session)
    request_digest = canonical_json_hash(command.model_dump(mode="json"))
    async with authorization.prepare_proposal_operation(locator) as prepared:
        if not isinstance(prepared, PreparedGuideProposalOperation):
            raise GuideProposalError("authority_unavailable")
        locked, package, existing = await _lock_approval_selection(
            session,
            repository,
            replay_repository,
            command,
            actor,
        )
        if existing is not None:
            return await _replay_approval(
                existing, target, request_digest, actor, package, locator, command, prepared
            )
        previous = await _validate_new_approval(
            session,
            locked,
            package,
            command,
        )
        outputs = await _compile_approval(
            session,
            locked,
            command,
            new_record_id(),
            registry,
            profiles,
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


async def _lock_approval_selection(
    session,
    repository,
    replay_repository,
    command,
    actor,
):
    """Lock exact proposal lineage and classify its human replay namespace."""
    target = command.target
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
    reservation = await replay_repository.find_human_namespace(
        actor_profile_id=str(actor.actor_profile_id),
        idempotency_key=command.idempotency_key,
    )
    existing = (
        await session.get(ProjectGuideProposalApproval, reservation.operation_id)
        if reservation is not None
        else None
    )
    if reservation is not None and existing is None:
        raise GuideProposalError("operation_conflict")
    return locked, package, existing


async def _validate_new_approval(
    session,
    locked,
    package,
    command,
):
    """Validate current proposal and predecessor facts before compiling outputs."""
    if not locked.current:
        raise GuideProposalError("proposal_stale")
    if (
        locked.result.status == "guide_blocked"
        or locked.view.policy is None
        or command.acknowledged_warning_hashes != package.warning_hashes
    ):
        raise GuideProposalError("approval_blocked")
    if (
        locked.view.policy.lifecycle_status != "draft"
        or package.current_approval_operation_id != command.expected_previous_approval_operation_id
        or package.current_approval_output_digest
        != command.expected_previous_approval_output_digest
    ):
        raise GuideProposalError("proposal_stale")
    return await _previous_outputs(session, command.expected_previous_approval_operation_id)


@dataclass(frozen=True)
class _CompiledApproval:
    """Compiler outputs staged before consuming authority or changing policy rows."""

    effective_body: dict
    compiled: CompiledPreSubmitCheckerPolicy
    policies: LockedExternalCheckerPolicies
    receipt: GuideProposalApprovalReceipt


async def _compile_approval(
    session,
    locked,
    command,
    operation_id,
    registry,
    profiles,
) -> _CompiledApproval:
    target = command.target
    effective_body = ProjectService(session)._merge_effective_submission_artifact_policy(
        locked.view.policy.policy_body,
    )
    effective_hash = canonical_json_hash(effective_body)
    try:
        policies = await compile_external_checker_policy_bundle(
            ExternalCheckerPolicyCompileRequest(
                pre_submit_attachments=command.pre_submit_attachments,
                post_submit_attachments=command.post_submit_attachments,
            ),
            registry,
            project_id=target.project_id,
            profiles=profiles,
        )
    except (ExternalCheckerPolicyError, ValueError) as exc:
        raise GuideProposalError("approval_blocked") from exc
    external_pre = policies.pre_submit
    compiled = CompiledPreSubmitCheckerPolicy(
        compiler_version="external_checker_policy.v1",
        compiled_bundle=external_pre.model_dump(mode="json"),
        compiled_bundle_hash=external_pre.policy_sha256,
        checker_names=[
            external_pre.workstream_default.checker_id,
            *(entry.registry.capability_id for entry in external_pre.entries),
        ],
        checker_configs={
            entry.requirement_id: entry.configuration for entry in external_pre.entries
        },
    )
    effective_id, pre_id = new_record_id(), new_record_id()
    receipt = GuideProposalApprovalReceipt(
        operation_id=operation_id,
        target_digest=target.digest,
        artifact_policy_id=target.artifact_policy_id,
        effective_policy_id=effective_id,
        effective_policy_hash=effective_hash,
        pre_submit_policy_id=pre_id,
        pre_submit_bundle_hash=compiled.compiled_bundle_hash,
        effective_pre_submit_plan_hash=policies.policies_sha256,
        acknowledged_warning_hashes=command.acknowledged_warning_hashes,
    )
    return _CompiledApproval(effective_body, compiled, policies, receipt)


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
    target, receipt = command.target, outputs.receipt
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
            request_json=command.model_dump(mode="json"),
            target_digest=target.digest,
            request_digest=request_digest,
            resource_context_digest=facts.digest,
            output_digest=canonical_json_hash(receipt.model_dump(mode="json")),
            receipt_json=receipt.model_dump(mode="json"),
            artifact_policy_id=policy.id,
            effective_policy_id=effective.id,
            pre_submit_policy_id=pre.id,
            approved_policy_output_digest=policy_digest(policy),
            effective_pre_submit_plan=outputs.policies.model_dump(mode="json"),
            effective_pre_submit_plan_hash=outputs.policies.policies_sha256,
            prior_approval_operation_id=command.expected_previous_approval_operation_id,
            actor_profile_id=str(actor.actor_profile_id),
            identity_link_id=str(actor.identity_link_id),
            admin_role_grant_id=authority.admin_role_grant_id,
            authorization_decision_event_id=str(authority.authorization_decision_event_id),
        )
    )
    await session.flush()
    return receipt
