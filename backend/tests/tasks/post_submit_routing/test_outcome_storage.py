"""SQL rejects altered authority facts while the genuine outcome remains usable."""

from copy import deepcopy

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
    outcome_snapshot,
)


@pytest.mark.usefixtures("live_acceptance_lifecycle")
async def test_incomplete_or_crossed_outcome_rejected(tmp_path, isolated_database_env, monkeypatch):
    import app.modules.tasks.post_submit_routing.outcome as owner

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        original = owner._manifest
        # Alter one retained field only. The actual allow event and every other
        # candidate fact remain intact, so no invalid shape can mask the guard.
        paths = (
            ("source", "creation_decision_id"),
            ("source", "binding_decision_id"),
            ("source", "input_materialization_evidence_id"),
            ("request", "route_operation_id"),
            ("claim", "claim_owner"),
            ("consequence", "authorized_lifecycle_generation"),
            ("consequence", "task_effects", "final_acceptance_id"),
            ("router_actor_id",),
            ("router_identity_link_id",),
        )
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        for path in paths:

            def altered(*args):
                row = original(*args)
                context = deepcopy(row.authority_context)
                value = context
                for key in path[:-1]:
                    value = value[key]
                prior = value[path[-1]]
                value[path[-1]] = prior + 1 if isinstance(prior, int) else str(new_record_id())
                row.authority_context = context
                return row

            with monkeypatch.context() as patch:
                patch.setattr(owner, "_manifest", altered)
                async with h.factory() as session:
                    with pytest.raises(
                        DBAPIError, match="routing source authority context mismatch"
                    ):
                        async with session.begin():
                            await apply_outcome(session, h, 2)
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            result = await apply_outcome(session, h, 2)
            assert (
                await session.scalar(
                    text(
                        "SELECT public.task_routing_context_valid(m) FROM public.task_post_submit_routing_manifests m WHERE id=:id"
                    ),
                    {"id": result.routing_manifest_id},
                )
                is True
            )


async def test_routing_event_excludes_administrative_idempotency_reference(
    tmp_path, isolated_database_env, monkeypatch
):
    """SQL and replay independently reject an unrelated AUTH mutation reference."""
    from types import SimpleNamespace

    from app.modules.audit.service import AuditService
    from app.modules.authorization.catalogue import ActionId
    from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
    from app.modules.authorization.domain.audit import AuthorizationEvidenceUnavailable

    async with authorized_routing_source(
        tmp_path, isolated_database_env, human_review_required=True
    ) as h:
        insert = AuditService.add_authority_event
        read = AuditService.get_authority_event
        async with h.factory() as session:
            before = await outcome_snapshot(session)

        async def altered_insert(owner, value):
            if value.action_id == ActionId.TASK_POST_SUBMIT_ROUTE:
                from app.core.hashing import canonical_json_hash
                from app.modules.audit.schemas import ActorReferenceKind
                from app.modules.authorization.repository import AuthorityIdempotencyRepository
                from app.modules.authorization.schemas import AuthorityOperation

                # A real pending reservation satisfies the composite actor FK;
                # it is never committed or presented as mutation authority.
                reservation = await AuthorityIdempotencyRepository(session).reserve(
                    idempotency_key=new_record_id(),
                    actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                    actor_ref=value.actor_ref,
                    operation=AuthorityOperation.SERVICE_ACTOR_CREATE,
                    request_digest=canonical_json_hash({"probe": "wrong-protocol"}),
                )
                value = value.model_copy(update={"idempotency_reference": reservation.claim.record_id})
            return await insert(owner, value)

        for isolate_receipt_guard in (False, True):
            with monkeypatch.context() as patch:
                patch.setattr(AuditService, "add_authority_event", altered_insert)
                async with h.factory() as session:
                    expected = DBAPIError if isolate_receipt_guard else AuthorizationEvidenceUnavailable
                    message = "routing source authority context mismatch" if isolate_receipt_guard else "authorization evidence unavailable"
                    with pytest.raises(expected, match=message) as caught:
                        async with session.begin():
                            if isolate_receipt_guard:
                                # Isolate receipt validation from the canonical
                                # insert guard. Rollback restores this trigger.
                                await session.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_validate_idempotency"))
                            await apply_outcome(session, h, None)
                    if not isolate_receipt_guard:
                        assert "invalid authority idempotency event" in str(caught.value.__cause__)
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before
                assert await session.scalar(text("SELECT tgenabled::text FROM pg_trigger WHERE tgrelid='public.audit_events'::regclass AND tgname='audit_events_validate_idempotency'")) == "O"

        async with h.factory() as session, session.begin():
            result = await apply_outcome(session, h, None)
        async with h.factory() as session:
            retained = await session.execute(text("""
                SELECT a.idempotency_reference, a.request_id, a.correlation_id, q.route_operation_id
                FROM public.task_post_submit_routing_manifests m
                JOIN public.audit_events a ON a.id=m.authorization_decision_id
                JOIN public.task_post_submit_routing_requests q ON q.routing_manifest_id=m.id
                WHERE m.id=:id
            """), {"id": result.routing_manifest_id})
            admin_reference, request_id, correlation_id, operation_id = retained.one()
            assert admin_reference is None
            assert request_id == correlation_id == operation_id
            assert operation_id != h.request.evaluation_request_id
            committed = await outcome_snapshot(session)

        for replacement in (str(new_record_id()),):
            async def altered_read(owner, event_id):
                event = await read(owner, event_id)
                if event is not None and event.action_id == ActionId.TASK_POST_SUBMIT_ROUTE.value:
                    # Copy the actual event, changing only this field. Do not dirty
                    # its ORM row: the replay assertion must reach AUTH, not SQL.
                    return SimpleNamespace(**(vars(event) | {"idempotency_reference": replacement}))
                return event

            with monkeypatch.context() as patch:
                patch.setattr(AuditService, "get_authority_event", altered_read)
                async with h.factory() as session, session.begin():
                    with pytest.raises(PreparedAuthorizationHandleInvalid, match="invalid retained routing receipt"):
                        await apply_outcome(session, h, None)
            async with h.factory() as session:
                assert await outcome_snapshot(session) == committed
        async with h.factory() as session, session.begin():
            assert await apply_outcome(session, h, None) == result.model_copy(update={"replayed": True})
