"""Authorized transitions for the existing atomic-participant lifecycle scope."""

import json
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.reviews.api.lifecycle import (
    JointLifecyclePhase, JointLifecycleUnavailable, LifecycleTransitionAuthorization,
    LifecycleTransitionCommand, LifecycleTransitionFacts, LifecycleTransitionReceipt,
)
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl, JointLifecycleTransition

# This reviewed scope is not production routing availability. Its composition
# inventory tests must change before adding any asynchronous acceptance writer.
FIRST_CONTRIBUTION_MANIFEST_DIGEST = canonical_json_hash({
    "participants": ["reviews.acceptance", "tasks.accepted_effects", "contributions.records"],
    "new_effects": "live_root_transaction",
    "replay": "current_generation_select_only",
    "live_readiness": "no_pre_authority_final_acceptances",
    "unavailable": ["production_routing", "human_review", "fulfillment_admission", "payment_delivery"],
})
_EDGES = frozenset({
    ("disabled", "shadow"), ("shadow", "live"), ("shadow", "disabled"),
    ("live", "draining"), ("draining", "disabled"),
})


class JointLifecycleController:
    """Flush-only REV owner; the shared fence precedes AUTH principal custody."""

    def __init__(self, session: AsyncSession, *, authorization: LifecycleTransitionAuthorization):
        self._session = session
        self._authorization = authorization
        self._fence = PostgresJointLifecycleMutationFence(session)

    async def transition(self, command: LifecycleTransitionCommand) -> LifecycleTransitionReceipt:
        """Commit control, history and exact AUTH together, or let the caller roll back."""
        checked = LifecycleTransitionCommand.model_validate(command)
        current = await self._fence.lock_controller()
        async with self._authorization.lock_scope(checked) as authority:
            history = await self._session.scalar(select(JointLifecycleTransition).where(
                JointLifecycleTransition.operation_id == checked.operation_id,
            ))
            if history is not None:
                retained = LifecycleTransitionFacts.model_validate_json(
                    json.dumps(history.facts_json),
                )
                if retained.command != checked or current.singleton_id != history.singleton_id:
                    raise JointLifecycleUnavailable("lifecycle operation conflicts")
                await authority.validate_replay(retained, UUID(history.authorization_decision_event_id))
                return _receipt(history)

            now = await self._session.scalar(select(func.clock_timestamp()))
            if (
                current.singleton_id != checked.singleton_id
                or current.generation != checked.expected_generation
                or current.phase != checked.current_phase
                or (current.phase, checked.target_phase) not in _EDGES
                or checked.reviewed_manifest_digest != FIRST_CONTRIBUTION_MANIFEST_DIGEST
                or now >= checked.deadline
            ):
                raise JointLifecycleUnavailable("lifecycle transition unavailable")
            # Source custody is mandatory. Existing valid outcomes do not prevent
            # a later shutdown/restart; incomplete retained authority still does.
            retained_acceptance = bool(
                await self._session.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM public.final_acceptances f "
                        "LEFT JOIN public.task_post_submit_routing_manifests m ON m.id=f.source_routing_manifest_id "
                        "WHERE m.id IS NULL OR NOT public.task_routing_receipt_valid(m))"
                    )
                )
            )
            if checked.target_phase == JointLifecyclePhase.LIVE and retained_acceptance:
                raise JointLifecycleUnavailable("pre-authority acceptance blocks lifecycle readiness")
            facts = LifecycleTransitionFacts(
                command=checked,
                observations_digest=canonical_json_hash({
                    "singleton_id": str(current.singleton_id),
                    "generation": current.generation, "phase": current.phase.value,
                    "retained_pre_authority_acceptance": retained_acceptance,
                    "manifest": FIRST_CONTRIBUTION_MANIFEST_DIGEST,
                }),
            )
            receipt = await authority.consume_new(facts)
            row = JointLifecycleTransition(
                id=new_record_id(), operation_id=checked.operation_id,
                singleton_id=current.singleton_id, generation=current.generation + 1,
                previous_phase=current.phase.value, phase=checked.target_phase.value,
                facts_json=facts.model_dump(mode="json"),
                resource_context_digest=receipt.resource_context_digest,
                authorization_decision_event_id=str(receipt.decision_event_id),
            )
            self._session.add(row)
            await self._session.flush()
            control = await self._session.get(
                JointLifecycleReleaseControl, current.singleton_id, populate_existing=True,
            )
            control.phase, control.generation, control.transition_id = row.phase, row.generation, row.id
            await self._session.flush()
            return _receipt(row)


def _receipt(row: JointLifecycleTransition) -> LifecycleTransitionReceipt:
    return LifecycleTransitionReceipt(
        operation_id=row.operation_id, singleton_id=row.singleton_id,
        generation=row.generation, phase=JointLifecyclePhase(row.phase),
        authorization_decision_event_id=UUID(row.authorization_decision_event_id),
        created_at=row.created_at,
    )
