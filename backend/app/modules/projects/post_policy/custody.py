"""Validate retained post-policy content and operation relations without substitution."""

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.external_policy import (
    LockedExternalPostSubmitPolicy,
    validate_stored_external_post_policy,
)
from app.modules.authorization.api import ActorKind
from app.modules.authorization.api.post_policy import PostPolicyAuthorityReceipt
from app.modules.projects.api.guide_proposals import (
    GuideProposalApprovalReceipt,
    GuideProposalCorrectionReceipt,
    GuideProposalError,
)
from app.modules.projects.guide_compilation.retained_evidence import retained_target
from app.modules.projects.api.post_policy import (
    PostPolicyReceipt,
    PostPolicyTarget,
    post_policy_derive_authorization_selector,
    post_policy_human_authorization_selector,
)

from .models import PostPolicyOperation


@dataclass(frozen=True)
class PostPolicyCustody:
    """One policy and its exact immutable receipts; no current-successor substitution."""

    target: PostPolicyTarget
    compiled: LockedExternalPostSubmitPolicy
    projection: PostPolicyOperation
    approval: PostPolicyOperation | None
    correction: PostPolicyOperation | None


def _retained_receipt(raw):
    """Expose old stored POST identities only to private custody checks."""
    if not isinstance(raw, dict) or set(raw) != {"operation_id", "kind", "target", "correction"}:
        raise GuideProposalError("proposal_unavailable")
    target_json = raw["target"]
    if not isinstance(target_json, dict) or set(target_json) != {
        "proposal",
        "upstream",
        "upstream_output_digest",
        "policy_id",
        "projection_operation_id",
        "policy_hash",
        "predecessor_policy_id",
    }:
        raise GuideProposalError("proposal_unavailable")
    try:
        proposal = retained_target(target_json["proposal"])
        upstream = GuideProposalApprovalReceipt.model_validate(target_json["upstream"])
        if (
            upstream.target_digest != proposal.digest
            or upstream.artifact_policy_id != proposal.artifact_policy_id
            or canonical_json_hash(target_json["upstream"]) != target_json["upstream_output_digest"]
        ):
            raise ValueError("retained upstream approval mismatch")
        target = SimpleNamespace(
            proposal=proposal,
            upstream=upstream,
            upstream_output_digest=target_json["upstream_output_digest"],
            policy_id=UUID(target_json["policy_id"]),
            projection_operation_id=UUID(target_json["projection_operation_id"]),
            policy_hash=target_json["policy_hash"],
            predecessor_policy_id=(
                UUID(target_json["predecessor_policy_id"])
                if target_json["predecessor_policy_id"]
                else None
            ),
            digest=canonical_json_hash(target_json),
        )
        correction = (
            GuideProposalCorrectionReceipt.model_validate(raw["correction"])
            if raw["correction"] is not None
            else None
        )
        if (raw["kind"] == "correction") != (correction is not None) or (
            correction is not None and correction.target_digest != proposal.digest
        ):
            raise ValueError("retained correction receipt mismatch")
        return SimpleNamespace(
            operation_id=UUID(raw["operation_id"]),
            kind=raw["kind"],
            target=target,
            correction=correction,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GuideProposalError("proposal_unavailable") from exc


def operation_receipt(operation: PostPolicyOperation) -> PostPolicyReceipt:
    """Recompute every stored commitment before trusting a replay or disclosure."""
    retained = (
        isinstance(operation.target_json, dict)
        and isinstance(operation.target_json.get("proposal"), dict)
        and "pre_catalogue_id" in operation.target_json["proposal"]
    )
    receipt = (
        _retained_receipt(operation.receipt_json)
        if retained
        else PostPolicyReceipt.model_validate(operation.receipt_json)
    )
    target = receipt.target
    facts = operation.resource_context_json
    action = (
        "project.post_submit_checker_policy."
        + {
            "derive": "derive",
            "approve": "approve",
            "correction": "correction.request",
        }[operation.kind]
    )
    selector_id = (
        post_policy_derive_authorization_selector(operation.upstream_approval_operation_id)
        if operation.kind == "derive"
        else post_policy_human_authorization_selector(
            UUID(operation.actor_profile_id), operation.idempotency_key, operation.kind
        )
    )
    expected_facts = {
        "locator": dict(
            project_id=operation.project_id,
            guide_id=operation.guide_id,
            compilation_id=str(operation.compilation_id),
            actor_profile_id=operation.actor_profile_id,
            identity_link_id=operation.identity_link_id,
            action_id=action,
            operation_id=str(selector_id),
        ),
        "policy_id": operation.policy_id,
        "finalization_id": str(target.proposal.finalization_id),
        "setup_run_id": str(target.proposal.setup_run_id),
        "setup_generation": target.proposal.setup_generation,
        "upstream_approval_operation_id": str(target.upstream.operation_id),
        "upstream_approval_output_digest": target.upstream_output_digest,
        "guide_version": target.proposal.guide_version,
        "source_snapshot_id": str(target.proposal.source_snapshot_id),
        "source_snapshot_hash": target.proposal.source_snapshot_hash,
        "result_hash": target.proposal.result_hash,
        "post_component_hash": target.proposal.component_hashes.post_submit_hash,
        "requirement_inventory_hash": target.proposal.component_hashes.requirement_inventory_hash,
        "effective_policy_id": str(target.upstream.effective_policy_id),
        "effective_policy_hash": target.upstream.effective_policy_hash,
        "pre_submit_policy_id": str(target.upstream.pre_submit_policy_id),
        "pre_submit_bundle_hash": target.upstream.pre_submit_bundle_hash,
        "projection_operation_id": str(target.projection_operation_id),
        "lifecycle_status": facts.get("lifecycle_status"),
        "policy_hash": target.policy_hash,
        "target_digest": target.digest,
        "request_digest": operation.request_digest,
        "output_digest": operation.output_digest,
    }
    if retained:
        expected_facts["catalogue_manifest_hash"] = target.proposal.post_catalogue_manifest_hash
    if (
        receipt.operation_id != operation.operation_id
        or receipt.kind != operation.kind
        or (operation.receipt_json["target"] if retained else target.model_dump(mode="json"))
        != operation.target_json
        or target.digest != operation.target_digest
        or canonical_json_hash(operation.request_json) != operation.request_digest
        or canonical_json_hash(operation.receipt_json) != operation.output_digest
        or canonical_json_hash(facts) != operation.resource_context_digest
        or str(target.policy_id) != operation.policy_id
        or str(target.proposal.project_id) != operation.project_id
        or str(target.proposal.guide_id) != operation.guide_id
        or target.proposal.compilation_id != operation.compilation_id
        or target.upstream.operation_id != operation.upstream_approval_operation_id
        or (
            facts.get("lifecycle_status")
            not in ({"compiled", "approved"} if operation.kind == "correction" else {"compiled"})
        )
        or facts != expected_facts
    ):
        raise GuideProposalError("proposal_unavailable")
    return receipt


async def load_post_policy_custody(session, policy) -> PostPolicyCustody:
    """Require complete projection/approval/supersession evidence, even for reads."""
    operations = {
        row.kind: row
        for row in await session.scalars(
            select(PostPolicyOperation)
            .where(PostPolicyOperation.policy_id == policy.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    projection = operations.get("derive")
    if projection is None or policy.projection_operation_id != projection.operation_id:
        raise GuideProposalError("proposal_unavailable")
    target = operation_receipt(projection).target
    compiled = validate_stored_external_post_policy(policy.policy_body)
    if (
        compiled.policy_sha256 != policy.policy_hash
        or policy.required_checkers != [item.registry.capability_id for item in compiled.entries]
        or policy.warning_checkers != []
        or policy.blocking_severities != ["critical", "high"]
    ):
        raise GuideProposalError("proposal_unavailable")
    expected = {
        "project_id": str(target.proposal.project_id),
        "guide_id": str(target.proposal.guide_id),
        "guide_version": target.proposal.guide_version,
        "source_snapshot_id": str(target.proposal.source_snapshot_id),
        "source_snapshot_hash": target.proposal.source_snapshot_hash,
        "effective_policy_id": str(target.upstream.effective_policy_id),
        "effective_policy_hash": target.upstream.effective_policy_hash,
        "pre_submit_checker_policy_id": str(target.upstream.pre_submit_policy_id),
        "pre_submit_checker_bundle_hash": target.upstream.pre_submit_bundle_hash,
        "policy_hash": target.policy_hash,
        "supersedes_policy_id": str(target.predecessor_policy_id)
        if target.predecessor_policy_id
        else None,
    }
    if any(getattr(policy, key) != value for key, value in expected.items()):
        raise GuideProposalError("proposal_unavailable")
    approval, correction = operations.get("approve"), operations.get("correction")
    for operation in (approval, correction):
        if operation and operation_receipt(operation).target.digest != target.digest:
            raise GuideProposalError("proposal_unavailable")
    if (
        policy.approval_operation_id != (approval.operation_id if approval else None)
        or (policy.approved_at is not None) != (approval is not None)
        or (policy.lifecycle_status == "approved" and approval is None)
        or (policy.lifecycle_status == "compiled" and approval is not None)
        or (policy.lifecycle_status == "superseded")
        != (policy.supersession_operation_id is not None)
        or (policy.lifecycle_status == "superseded") != (policy.superseded_at is not None)
    ):
        raise GuideProposalError("proposal_unavailable")
    if policy.lifecycle_status == "superseded":
        successor = await session.get(
            PostPolicyOperation, policy.supersession_operation_id, populate_existing=True
        )
        if successor is None:
            raise GuideProposalError("proposal_unavailable")
        receipt = operation_receipt(successor)
        if not (
            (successor.kind == "correction" and successor is correction)
            or (
                successor.kind == "derive"
                and receipt.target.predecessor_policy_id == UUID(policy.id)
            )
        ):
            raise GuideProposalError("proposal_unavailable")
    return PostPolicyCustody(target, compiled, projection, approval, correction)


def require_post_authority(receipt, facts, actor):
    """Reject forged or cross-action receipts before any product write."""
    derive = facts.locator.action_id == "project.post_submit_checker_policy.derive"
    if (
        not isinstance(receipt, PostPolicyAuthorityReceipt)
        or receipt.actor_profile_id != actor.actor_profile_id
        or receipt.identity_link_id != actor.identity_link_id
        or receipt.scope_project_id != facts.locator.project_id
        or receipt.action_id != facts.locator.action_id
        or receipt.permission_id != "project.effective_policy.manage"
        or receipt.resource_context_digest != facts.digest
        or not isinstance(receipt.authorization_decision_event_id, UUID)
        or (
            derive
            and (
                actor.actor_kind is not ActorKind.SERVICE
                or actor.service_identity != "workstream.project.setup"
                or receipt.service_identity != "workstream.project.setup"
                or receipt.admin_role_grant_id is not None
            )
        )
        or (
            not derive
            and (
                actor.actor_kind is not ActorKind.HUMAN
                or receipt.service_identity is not None
                or not isinstance(receipt.admin_role_grant_id, UUID)
            )
        )
    ):
        raise GuideProposalError("authority_unavailable")


def validate_activation_post_policy(
    guide,
    source_snapshot,
    effective_policy,
    pre_submit_checker_policy,
    post_submit_checker_policy,
    approval_custody,
    post_policy_custody,
):
    """Validate the exact post-policy portion of active-guide readiness."""
    if post_submit_checker_policy is None:
        raise ValueError("post-submit checker policy is required")
    if post_submit_checker_policy.guide_id != guide.id:
        raise ValueError("post-submit checker policy guide mismatch")
    if post_submit_checker_policy.source_snapshot_id != source_snapshot.id:
        raise ValueError("post-submit checker policy snapshot mismatch")
    if post_submit_checker_policy.source_snapshot_hash != source_snapshot.bundle_hash:
        raise ValueError("post-submit checker policy snapshot hash mismatch")
    if post_submit_checker_policy.effective_policy_id != effective_policy.id:
        raise ValueError("post-submit checker policy is bound to the wrong effective policy")
    if post_submit_checker_policy.effective_policy_hash != effective_policy.effective_policy_hash:
        raise ValueError("post-submit checker policy effective hash mismatch")
    if post_submit_checker_policy.pre_submit_checker_policy_id != pre_submit_checker_policy.id:
        raise ValueError(
            "post-submit checker policy is bound to the wrong pre-submit checker policy"
        )
    if (
        post_submit_checker_policy.pre_submit_checker_bundle_hash
        != pre_submit_checker_policy.compiled_bundle_hash
    ):
        raise ValueError("post-submit checker policy pre-submit hash mismatch")
    if post_submit_checker_policy.lifecycle_status != "approved":
        raise ValueError("approved post-submit checker policy is required")
    if (
        post_policy_custody is None
        or post_policy_custody.approval is None
        or post_submit_checker_policy.approval_operation_id
        != post_policy_custody.approval.operation_id
        or post_submit_checker_policy.projection_operation_id
        != post_policy_custody.projection.operation_id
        or post_submit_checker_policy.approved_at is None
        or post_policy_custody.target.upstream.operation_id
        != approval_custody.operation.operation_id
        or post_policy_custody.target.policy_hash != post_submit_checker_policy.policy_hash
    ):
        raise ValueError("post-submit checker approval custody is required")
    try:
        parsed = validate_stored_external_post_policy(post_submit_checker_policy.policy_body)
        if (
            parsed.policy_sha256 != post_submit_checker_policy.policy_hash
            or post_submit_checker_policy.required_checkers
            != [item.registry.capability_id for item in parsed.entries]
            or post_submit_checker_policy.warning_checkers != []
            or post_submit_checker_policy.blocking_severities != ["critical", "high"]
        ):
            raise ValueError("external post policy sidecars differ")
    except ValueError as exc:
        raise ValueError("post-submit checker policy hash is invalid") from exc
