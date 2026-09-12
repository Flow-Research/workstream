"""Shared validation and canonical evidence encoding for proposal decisions."""

from uuid import UUID

from app.modules.authorization.api import ActorKind
from app.modules.authorization.api.guide_proposal_review import GuideProposalAuthorityReceipt
from app.modules.projects.api.guide_proposals import GuideProposalError


def require_proposal_authority(receipt, facts, actor, permission: str) -> None:
    """Reject a copied, foreign or incomplete authority receipt before product writes."""
    if (
        not isinstance(receipt, GuideProposalAuthorityReceipt)
        or actor.actor_kind is not ActorKind.HUMAN
        or receipt.actor_profile_id != actor.actor_profile_id
        or receipt.identity_link_id != actor.identity_link_id
        or receipt.scope_project_id != facts.locator.project_id
        or receipt.action_id != facts.locator.action_id
        or receipt.permission_id != permission
        or receipt.resource_context_digest != facts.digest
        or not isinstance(receipt.admin_role_grant_id, UUID)
        or not isinstance(receipt.authorization_decision_event_id, UUID)
    ):
        raise GuideProposalError("authority_unavailable")


def proposal_resource_json(facts):
    from dataclasses import asdict
    import json

    values = json.loads(json.dumps(asdict(facts), default=str))
    del values["locator"]["request_id"]
    return values
