"""Real invoked-completion and outcome observations, without fabricated authority."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text

from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.outbox import outbox_delivery
from app.adapters.tasks import task_post_submit_outcome
from app.modules.checkers.api.execution import COMPLETION_EVENT
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.registry import HandlerRegistry
from tests.authorization.post_submit_routing.support import provision_router
from tests.tasks.evaluation_delivery.support import delivery_fixture
from tests.tasks.post_submit_routing.test_source_preparation import routing_source


async def invoked_completion(h):
    await delivery_fixture(h)  # Provision real dispatcher authority.

    async def not_called(envelope):
        pytest.fail("this proof invokes the outcome operation, not a completion handler")

    dispatcher = outbox_delivery(
        h.factory,
        authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(COMPLETION_EVENT, 1, not_called)]),
        options=DeliveryOptions(),
    )
    claim = await dispatcher.claim(
        h.source["completion_event_id"], h.request.project_id, "routing-proof"
    )
    assert claim is not None
    h.completion_delivery = dispatcher
    envelope = await dispatcher._begin_invocation(claim)
    assert envelope is not None
    return envelope


async def outcome_snapshot(session):
    return (
        await session.execute(
            text("""
      SELECT (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_post_submit_routing_manifests r),
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.final_acceptances r),
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.contribution_records r),
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.compensation_awards r),
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.audit_events r),
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.event_id) FROM public.outbox_events r),
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.workstream_tasks r),
        (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_assignments r)
    """)
        )
    ).one()


@asynccontextmanager
async def authorized_routing_source(
    tmp_path, url, *, human_review_required=False, contribution_awards=(), **options
):
    """Provide real input and invoked delivery; the caller chooses when to apply/commit."""
    async with routing_source(
        tmp_path,
        url,
        human_review_required=human_review_required,
        contribution_awards=contribution_awards,
        **options,
    ) as h:
        await provision_router(h.factory)
        h.envelope = await invoked_completion(h)
        yield h


async def apply_outcome(session, h, generation):
    """Invoke the actual composition; never grant authority in the fixture."""
    return await task_post_submit_outcome(session, h.factory).apply(
        h.envelope, current_generation=generation
    )
