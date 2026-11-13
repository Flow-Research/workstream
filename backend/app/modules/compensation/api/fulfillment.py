"""Current fulfillment identity and immutable obligation construction."""

from datetime import UTC
import json
from typing import Protocol
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.compensation.api.awards import CompleteAwardSetRequest, CompensationAwardFacts
from app.modules.compensation.api.fulfillment_contracts import SOURCE_AWARD_KEYS, decode_obligation
from app.core.financial_wire import format_award_quantity

OBLIGATION_DELIVERY_EVENT = "compensation.obligation.deliver"


class CompensationFulfillmentReadinessPort(Protocol):
    """Configured local identity, checked against existing immutable roots."""

    async def require_source_ready(self) -> UUID:
        """Refuse missing identity or a different source on this deployment."""
        ...


class CompensationFulfillmentLifecycleFacts(Protocol):
    @property
    def generation(self) -> int:
        ...

    @property
    def new_effects_enabled(self) -> bool:
        ...


class CompensationFulfillmentFence(Protocol):
    """Consumer view of the canonical held fence, never separate authority."""

    async def acquire(self, expected_generation: int) -> CompensationFulfillmentLifecycleFacts:
        """Require the current caller root or raise CompensationAwardConflict."""
        ...


def fulfillment_obligation(
    request: CompleteAwardSetRequest, award: CompensationAwardFacts,
    *, source_instance_id: UUID, root_id: UUID, route_key: str,
) -> dict:
    """Construct and independently decode the one current outbound contract."""
    if source_instance_id.version != 7 or root_id.version != 7:
        raise ValueError("fulfillment source and root require UUIDv7")
    contribution = request.contribution
    body = {
        "contract_version": 1,
        "source_instance_id": str(source_instance_id), "fulfillment_root_id": str(root_id),
        "award_id": str(award.id), "project_id": str(award.project_id),
        "contributor_id": str(award.contributor_id),
        "contribution_record_id": str(award.contribution_record_id),
        "contribution_type": contribution.contribution_type,
        "task_id": str(contribution.task_id), "submission_id": str(contribution.submission_id),
        "final_acceptance_id": str(contribution.final_acceptance_id), "review_id": None,
        "contribution_policy_version_id": str(award.contribution_policy_version_id),
        "award_definition_id": str(award.award_definition_id), "task_size": contribution.task_size,
        "adapter_binding_id": str(award.adapter_binding_id), "route_key": route_key,
        "instrument_type": award.instrument_type.value, "unit_code": award.unit_code,
        "quantity": format_award_quantity(award.quantity),
        "awarded_at": award.created_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "correlation_id": str(award.correlation_id),
    }
    body["source_award_digest"] = canonical_json_hash({key: body[key] for key in SOURCE_AWARD_KEYS})
    body["obligation_digest"] = canonical_json_hash(body)
    return decode_obligation(json.dumps(body).encode("utf-8"))
