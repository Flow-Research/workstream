"""Real B6 requests, dispatcher authority and exact persisted execution observations."""

import json
from types import SimpleNamespace

from sqlalchemy import select, func

from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.tasks import evaluation_request_handler
from app.adapters.outbox import outbox_delivery
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.checkers.api.execution import COMPLETION_EVENT, REQUEST_EVENT
from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.registry import HandlerRegistry
from app.modules.tasks.models import AuditEvent
from tests.outbox.conftest import Harness


async def delivery_fixture(h, *, options=None, materialization=None):
    """Provision the real dispatcher; feature identities come from material_fixture."""
    async with h.factory() as session, session.begin():
        if await session.scalar(select(ActorProfile.id).where(
            ActorProfile.service_identity == ServiceIdentity.OUTBOX_DISPATCHER.value,
        )) is None:
            actor_id = str(new_record_id())
            session.add(ActorProfile(
                id=actor_id, actor_kind="service", status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=ServiceIdentity.OUTBOX_DISPATCHER.value, created_by=actor_id,
            ))
            await session.flush()
            session.add(ActorIdentityLink(
                id=str(new_record_id()), actor_profile_id=actor_id, issuer="workstream.internal",
                subject=ServiceIdentity.OUTBOX_DISPATCHER.value, subject_kind="service",
                status="active", linked_by="workstream:system:bootstrap",
            ))
    handler = evaluation_request_handler(
        sessions=h.factory,
        materialization=h.service if materialization is None else materialization,
    )
    delivery = outbox_delivery(
        h.factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(REQUEST_EVENT, 1, handler)]),
        options=options or DeliveryOptions(),
    )
    return SimpleNamespace(handler=handler, delivery=delivery)


async def invoked(h, d):
    claim = await d.delivery.claim(h.created.evaluation_event_id, h.request.project_id, "request-proof")
    assert claim is not None
    envelope = await d.delivery._begin_invocation(claim)
    assert envelope is not None
    return envelope


async def claimed_envelope(h, claim):
    """Reuse the shared fixture's stored envelope read, without invoking it."""
    return await Harness(h.factory, h.request.project_id).envelope(claim)


async def state(h):
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(h.created.evaluation_attempt_id))
        return {
            "run": {key: getattr(run, key) for key in (
                "id", "status", "worker_lease_id", "worker_lease_generation",
                "execute_evidence_id", "finalize_evidence_id", "result_json", "result_digest",
                "material_custody", "completion_event_id",
            )},
            "members": await session.scalar(select(func.count()).select_from(CheckerResult).where(
                CheckerResult.checker_run_id == run.id,
            )),
            "events": await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.project_id == str(h.request.project_id),
                OutboxEvent.event_type == COMPLETION_EVENT,
            )),
            "allows": list(await session.scalars(select(AuditEvent.id).where(
                AuditEvent.project_id == str(h.request.project_id),
                AuditEvent.action_id.in_(["checker.post_submit.execute", "checker.post_submit.finalize"]),
            ).order_by(AuditEvent.id))),
        }


def outcome(receipt):
    return json.loads(receipt.outcome_json)
