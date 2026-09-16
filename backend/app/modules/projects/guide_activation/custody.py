"""Read frozen activation custody without rechecking mutable CON eligibility."""

from uuid import UUID

from sqlalchemy import select

from app.modules.projects.api.guide_activation import (
    GuideActivationAuthorityReceipt,
    GuideActivationFacts,
    GuideActivationReceipt,
)
from app.modules.projects.models import GuideMutationIdempotencyRecord

ACTION = "project.guide.activate"


def activation_custody(record, *, request_id: UUID):
    """Validate the sole ledger's immutable receipt, locator and consumed authority."""
    receipt = GuideActivationReceipt.model_validate(record.response_json)
    body = record.activation_facts_json
    facts = GuideActivationFacts.model_validate(
        {
            **body,
            "locator": {**body["locator"], "request_id": request_id},
        }
    )
    authority = GuideActivationAuthorityReceipt.model_validate(record.activation_authority_json)
    if (
        record.status != "committed"
        or record.action_id != ACTION
        or record.request_digest != receipt.command.digest
        or record.operation_id != receipt.operation_id
        or record.operation_generation != receipt.activation_generation
        or record.idempotency_key != receipt.command.idempotency_key
        or record.setup_run_id is not None
        or facts.receipt != receipt
        or facts.resource_json() != body
        or facts.digest != record.resource_context_digest
        or str(facts.locator.project_id) != record.project_id
        or str(facts.locator.guide_id) != record.resource_id
        or str(facts.locator.actor_profile_id) != record.actor_profile_id
        or str(facts.locator.identity_link_id) != record.identity_link_id
        or facts.locator.operation_id != receipt.operation_id
        or facts.locator.project_id != receipt.command.target.proposal.project_id
        or facts.locator.guide_id != receipt.command.target.proposal.guide_id
    ):
        raise ValueError("guide activation custody mismatch")
    require_authority(authority, facts)
    return receipt, facts, authority


def require_authority(authority, facts):
    """A nominal consumed receipt must bind the exact actor, scope and facts."""
    if type(authority) is not GuideActivationAuthorityReceipt or (
        authority.actor_profile_id != facts.locator.actor_profile_id
        or authority.identity_link_id != facts.locator.identity_link_id
        or authority.scope_project_id != facts.locator.project_id
        or authority.resource_context_digest != facts.digest
    ):
        raise ValueError("guide activation authority mismatch")


async def load_guide_activation(session, guide):
    """Require persisted exact binding; historical unbound rows are unavailable."""
    if guide.activation_operation_id is None:
        raise ValueError("guide activation binding unavailable")
    record = await session.scalar(
        select(GuideMutationIdempotencyRecord).where(
            GuideMutationIdempotencyRecord.operation_id == guide.activation_operation_id,
        ).execution_options(populate_existing=True)
    )
    if record is None:
        raise ValueError("guide activation binding unavailable")
    receipt, _, _ = activation_custody(record, request_id=record.operation_id)
    command = receipt.command
    if (
        record.resource_id != guide.id
        or record.project_id != guide.project_id
        or command.target.proposal.guide_version != guide.version
        or guide.mutation_generation != receipt.activation_generation
        or guide.contribution_policy_id != command.contribution_policy_id
        or guide.contribution_policy_version_id != command.contribution_policy_version_id
        or guide.effective_at != receipt.effective_at
        or guide.approved_by != record.actor_profile_id
        or guide.status not in {"active", "superseded"}
    ):
        raise ValueError("guide activation binding mismatch")
    for kind in ("review", "revision"):
        selected = getattr(command, kind)
        if (
            getattr(guide, f"selected_{kind}_policy_id"),
            getattr(guide, f"selected_{kind}_policy_generation"),
            getattr(guide, f"selected_{kind}_policy_hash"),
        ) != (
            str(selected.policy_id),
            selected.generation,
            selected.policy_hash,
        ):
            raise ValueError("guide activation policy selection mismatch")
    return receipt
