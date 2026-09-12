"""Allocate one immutable correction successor without dispatching provider work."""

from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import ProjectGuideCorrectionFeedback
from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorizationFacts,
    GuideProposalAuthorizationLocator,
    PreparedGuideProposalOperation,
)
from app.modules.projects.api.guide_proposals import (
    GuideProposalCorrectionReceipt,
    GuideProposalError,
    GuideProposalSelection,
)
from app.modules.projects.models import ProjectSetupRun

from .correction_feedback import correction_feedback
from .proposal_authority import proposal_resource_json, require_proposal_authority
from .models import ProjectGuideProposalCorrection
from .proposal_repository import GuideProposalRepository


async def request_proposal_correction(
    session,
    authorization,
    command,
    *,
    actor,
    request_id,
) -> GuideProposalCorrectionReceipt:
    """Preserve the finalized predecessor and stop at committed successor intent."""
    target = command.target
    operation_id = uuid5(
        NAMESPACE_URL,
        f"workstream.guide-proposal-correction:{actor.actor_profile_id}:{command.idempotency_key}",
    )
    locator = GuideProposalAuthorizationLocator(
        project_id=target.project_id,
        guide_id=target.guide_id,
        compilation_id=target.compilation_id,
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        action_id="project.guide_compilation.correction.request",
        operation_id=operation_id,
        request_id=request_id,
    )
    repository = GuideProposalRepository(session)
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
        existing = await session.scalar(
            select(ProjectGuideProposalCorrection)
            .where(
                ProjectGuideProposalCorrection.operation_id == operation_id,
            )
            .with_for_update()
        )
        if existing is not None:
            return await _replay_correction(
                session,
                existing,
                target,
                request_digest,
                locator,
                actor,
                prepared,
            )
        if not locked.current:
            raise GuideProposalError("proposal_stale")
        successor_id = uuid5(operation_id, "setup-successor")
        feedback = ProjectGuideCorrectionFeedback(
            operation_id=operation_id,
            predecessor_compilation_id=target.compilation_id,
            predecessor_result_hash=target.result_hash,
            target_digest=target.digest,
            reason=command.reason,
        )
        receipt = GuideProposalCorrectionReceipt(
            operation_id=operation_id,
            target_digest=target.digest,
            successor_setup_run_id=successor_id,
            successor_setup_generation=target.setup_generation + 1,
            feedback_hash=canonical_json_hash(feedback.model_dump(mode="json")),
        )
        approval = await repository.current_approval(target.guide_id)
        facts = GuideProposalAuthorizationFacts(
            locator=locator,
            finalization_id=target.finalization_id,
            artifact_policy_id=target.artifact_policy_id,
            setup_run_id=target.setup_run_id,
            setup_generation=target.setup_generation,
            target_digest=target.digest,
            request_digest=request_digest,
            output_digest=canonical_json_hash(receipt.model_dump(mode="json")),
            current_approval_operation_id=approval.operation_id if approval else None,
            current_approval_output_digest=approval.output_digest if approval else None,
        )
        authority = await prepared.consume_new(facts)
        require_proposal_authority(authority, facts, actor, "project.guide_compilation.request")
    return await _persist_correction(session, command, actor, locked, receipt, facts, authority)


async def _replay_correction(session, existing, target, request_digest, locator, actor, prepared):
    """Revalidate retained output custody and current authority without another successor."""
    if (
        existing.target_digest != target.digest
        or existing.request_digest != request_digest
        or existing.actor_profile_id != str(actor.actor_profile_id)
        or existing.identity_link_id != str(actor.identity_link_id)
    ):
        raise GuideProposalError("operation_conflict")
    correction_feedback(existing)
    receipt = GuideProposalCorrectionReceipt.model_validate(existing.receipt_json)
    successor = await session.get(ProjectSetupRun, str(receipt.successor_setup_run_id))
    if (
        successor is None
        or successor.id != existing.successor_setup_run_id
        or successor.project_id != str(target.project_id)
        or successor.guide_id != str(target.guide_id)
        or successor.source_snapshot_id != str(target.source_snapshot_id)
        or successor.source_snapshot_hash != target.source_snapshot_hash
        or successor.setup_generation != target.setup_generation + 1
        or receipt.feedback_hash != existing.feedback_hash
    ):
        raise GuideProposalError("operation_conflict")
    stored = existing.resource_context_json
    facts = GuideProposalAuthorizationFacts(
        locator=locator,
        finalization_id=target.finalization_id,
        artifact_policy_id=target.artifact_policy_id,
        setup_run_id=target.setup_run_id,
        setup_generation=target.setup_generation,
        target_digest=target.digest,
        request_digest=request_digest,
        output_digest=canonical_json_hash(receipt.model_dump(mode="json")),
        current_approval_operation_id=UUID(stored["current_approval_operation_id"])
        if stored["current_approval_operation_id"]
        else None,
        current_approval_output_digest=stored["current_approval_output_digest"],
    )
    if facts.digest != existing.resource_context_digest:
        raise GuideProposalError("operation_conflict")
    await prepared.validate_replay(facts, UUID(existing.authorization_decision_event_id))
    return receipt


async def _persist_correction(session, command, actor, locked, receipt, facts, authority):
    """Persist successor intent only after the prepared authority context closes."""
    target, operation_id = command.target, receipt.operation_id
    successor_id, request_digest = receipt.successor_setup_run_id, facts.request_digest
    locator = facts.locator
    session.add(
        ProjectSetupRun(
            id=str(successor_id),
            project_id=str(target.project_id),
            guide_id=str(target.guide_id),
            guide_version=target.guide_version,
            source_snapshot_id=str(target.source_snapshot_id),
            source_snapshot_hash=target.source_snapshot_hash,
            setup_generation=receipt.successor_setup_generation,
            documents_ready_at=locked.view.setup.documents_ready_at,
            status="correction_requested",
            current_step="correction_requested",
            created_by=str(actor.actor_profile_id),
            authorized_by_actor_profile_id=str(actor.actor_profile_id),
            authorized_via_identity_link_id=str(actor.identity_link_id),
            authorized_by_admin_role_grant_id=authority.admin_role_grant_id,
            authorization_scope_type="project",
            authorization_scope_project_id=str(target.project_id),
            authorization_action_id=locator.action_id,
            authorization_decision_event_id=str(authority.authorization_decision_event_id),
        )
    )
    await session.flush()
    session.add(
        ProjectGuideProposalCorrection(
            operation_id=operation_id,
            idempotency_key=command.idempotency_key,
            project_id=str(target.project_id),
            guide_id=str(target.guide_id),
            compilation_id=target.compilation_id,
            finalization_id=target.finalization_id,
            target_json=target.model_dump(mode="json"),
            target_digest=target.digest,
            request_digest=request_digest,
            resource_context_digest=facts.digest,
            resource_context_json=proposal_resource_json(facts),
            output_digest=facts.output_digest,
            receipt_json=receipt.model_dump(mode="json"),
            reason=command.reason,
            feedback_hash=receipt.feedback_hash,
            successor_setup_run_id=str(successor_id),
            successor_setup_generation=receipt.successor_setup_generation,
            actor_profile_id=str(actor.actor_profile_id),
            identity_link_id=str(actor.identity_link_id),
            admin_role_grant_id=authority.admin_role_grant_id,
            authorization_decision_event_id=str(authority.authorization_decision_event_id),
        )
    )
    await session.flush()
    return receipt
