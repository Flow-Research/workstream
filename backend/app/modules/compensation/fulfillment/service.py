"""Flush-only fulfillment roots under the caller's existing REV custody."""

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.compensation.api.awards import (
    CompleteAwardSetRequest, CompensationAwardConflict, CompensationAwardFacts,
)
from app.modules.compensation.api.fulfillment import (
    CompensationFulfillmentFence, CompensationFulfillmentReadinessPort,
    OBLIGATION_DELIVERY_EVENT, fulfillment_obligation,
)
from app.modules.compensation.fulfillment.models import CompensationFulfillmentRoot
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.outbox.api import (
    OutboxAppendDisposition, OutboxAppendInput, OutboxAppendPort, OutboxIdempotencyConflict,
)


class CompensationFulfillmentReadiness:
    """One configured source, permanently anchored by committed roots."""

    def __init__(self, session: AsyncSession, source_instance_id: UUID | None):
        self._session, self._source = session, source_instance_id

    async def require_source_ready(self) -> UUID:
        source = self._source
        if (not isinstance(source, UUID) or source.version != 7
                or not self._session.in_transaction() or self._session.in_nested_transaction()):
            raise CompensationAwardConflict("compensation_source_unavailable")
        different = await self._session.scalar(select(CompensationFulfillmentRoot.id).where(
            CompensationFulfillmentRoot.source_instance_id != source,
        ).limit(1))
        if different is not None:
            raise CompensationAwardConflict("compensation_source_unavailable")
        return source


def _event(root_id: UUID, award: CompensationAwardFacts, generation: int,
           source_award_digest: str, obligation_digest: str) -> OutboxAppendInput:
    return OutboxAppendInput(
        event_type=OBLIGATION_DELIVERY_EVENT, event_version=1,
        aggregate_type="compensation_fulfillment", aggregate_id=root_id,
        project_id=award.project_id, correlation_id=str(award.correlation_id),
        idempotency_key=f"compensation.fulfillment:{root_id}",
        payload={
            "fulfillment_root_id": str(root_id), "award_id": str(award.id),
            "adapter_binding_id": str(award.adapter_binding_id),
            "admission_generation": generation, "source_award_digest": source_award_digest,
            "obligation_digest": obligation_digest,
        },
    )


class CompensationFulfillmentParticipant:
    """Complete one immutable root/event per award, or require exact replay."""

    def __init__(self, session: AsyncSession, *, fence: CompensationFulfillmentFence,
                 outbox: OutboxAppendPort, source: CompensationFulfillmentReadinessPort):
        self._session, self._fence, self._outbox, self._source = session, fence, outbox, source

    async def require_custody(self, request: CompleteAwardSetRequest) -> None:
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise CompensationAwardConflict("compensation_fulfillment_unavailable")
        facts = await self._fence.acquire(request.expected_generation)
        if (type(facts.generation) is not int or facts.generation != request.expected_generation
                or (request.disposition == "new" and facts.new_effects_enabled is not True)):
            raise CompensationAwardConflict("compensation_fulfillment_unavailable")

    async def _historical_binding_route(self, award: CompensationAwardFacts) -> str:
        """Read original immutable identity, including a suspended binding."""
        route = await self._session.scalar(select(ProjectCompensationAdapterBinding.route_key).where(
            ProjectCompensationAdapterBinding.id == award.adapter_binding_id,
            ProjectCompensationAdapterBinding.project_id == str(award.project_id),
            ProjectCompensationAdapterBinding.instrument_type == award.instrument_type.value,
        ))
        if route is None:
            raise CompensationAwardConflict("compensation_fulfillment_conflict")
        return route

    async def complete(self, request: CompleteAwardSetRequest,
                       awards: tuple[CompensationAwardFacts, ...]) -> None:
        await self.require_custody(request)
        if not awards:
            return
        source = await self._source.require_source_ready()
        for award in awards:
            route = await self._historical_binding_route(award)
            root = await self._session.scalar(select(CompensationFulfillmentRoot).where(
                CompensationFulfillmentRoot.award_id == award.id,
            ).execution_options(populate_existing=True))
            if request.disposition == "replay":
                await self._require_replay(request, award, root, source, route)
                continue
            if root is not None:
                raise CompensationAwardConflict("compensation_fulfillment_conflict")
            root_id = new_record_id()
            ordinal = await self._session.scalar(select(
                func.coalesce(func.max(CompensationFulfillmentRoot.ordinal), 0) + 1,
            ))
            body = fulfillment_obligation(request, award, source_instance_id=source,
                                          root_id=root_id, route_key=route)
            try:
                appended = await self._outbox.append(_event(
                    root_id, award, request.expected_generation,
                    body["source_award_digest"], body["obligation_digest"],
                ))
            except OutboxIdempotencyConflict as exc:
                raise CompensationAwardConflict("compensation_fulfillment_conflict") from exc
            if appended.disposition is not OutboxAppendDisposition.CREATED:
                raise CompensationAwardConflict("compensation_fulfillment_conflict")
            self._session.add(CompensationFulfillmentRoot(
                id=root_id, award_id=award.id, project_id=str(award.project_id), ordinal=ordinal,
                admission_generation=request.expected_generation, source_instance_id=source,
                adapter_binding_id=award.adapter_binding_id, route_key=route,
                source_final_acceptance_id=request.contribution.final_acceptance_id,
                source_authorization_decision_id=request.source_authorization_decision_id,
                source_routing_manifest_id=request.source_routing_manifest_id,
                source_award_digest=body["source_award_digest"], obligation_digest=body["obligation_digest"],
                obligation_body=body, initial_outbox_event_id=appended.event_id,
            ))
            await self._session.flush()

    async def _require_replay(self, request, award, root, source, route) -> None:
        if root is None:
            raise CompensationAwardConflict("compensation_fulfillment_conflict")
        body = fulfillment_obligation(request, award, source_instance_id=source,
                                      root_id=root.id, route_key=route)
        if (root.project_id != str(award.project_id) or root.source_instance_id != source
                or root.adapter_binding_id != award.adapter_binding_id or root.route_key != route
                or root.source_final_acceptance_id != request.contribution.final_acceptance_id
                or root.source_authorization_decision_id != request.source_authorization_decision_id
                or root.source_routing_manifest_id != request.source_routing_manifest_id
                or root.obligation_body != body or root.source_award_digest != body["source_award_digest"]
                or root.obligation_digest != body["obligation_digest"]
                or await self._session.scalar(text(
                    "SELECT public.compensation_fulfillment_root_is_valid(r) "
                    "FROM public.compensation_fulfillment_roots r WHERE r.id=:id"
                ), {"id": root.id}) is not True):
            raise CompensationAwardConflict("compensation_fulfillment_conflict")
        try:
            await self._outbox.require_existing(root.initial_outbox_event_id, _event(
                root.id, award, root.admission_generation, root.source_award_digest, root.obligation_digest,
            ))
        except OutboxIdempotencyConflict as exc:
            raise CompensationAwardConflict("compensation_fulfillment_conflict") from exc
