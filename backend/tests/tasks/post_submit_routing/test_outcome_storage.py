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
                    {"id": result["routing_manifest_id"]},
                )
                is True
            )
