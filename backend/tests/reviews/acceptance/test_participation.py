"""Real authorized automatic acceptance and complete frozen economic facts."""

import json

import pytest
from sqlalchemy import text

from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from tests.tasks.post_submit_routing.outcome_support import (
    authorized_routing_source,
    apply_outcome,
    outcome_snapshot,
)

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


@pytest.mark.parametrize(
    "instruments",
    [(), ("money",), ("money", "project_points")],
    ids=("unpaid", "one-award", "two-awards"),
)
async def test_authorized_acceptance_creates_and_exactly_replays_complete_effects(
    tmp_path,
    isolated_database_env,
    instruments,
):
    async with authorized_routing_source(
        tmp_path, isolated_database_env, contribution_awards=instruments
    ) as h:
        async with h.factory() as session, session.begin():
            created = await apply_outcome(session, h, 2)
        async with h.factory() as session:
            before = await outcome_snapshot(session)
            row = (
                (
                    await session.execute(
                        text("""
              SELECT to_jsonb(f) AS acceptance, to_jsonb(c) AS contribution, to_jsonb(m) AS manifest,
                t.status AS task_status,a.status AS assignment_status
              FROM public.final_acceptances f
              JOIN public.task_post_submit_routing_manifests m ON m.final_acceptance_id=f.id
              JOIN public.contribution_records c ON c.source_final_acceptance_id=f.id
              JOIN public.workstream_tasks t ON t.id=f.task_id
              JOIN public.task_assignments a ON a.id=c.source_task_assignment_id
              WHERE f.id=:id
            """),
                        {"id": created["final_acceptance_id"]},
                    )
                )
                .mappings()
                .one()
            )
            f, c, m = row["acceptance"], row["contribution"], row["manifest"]
            s = m["authority_context"]["source"]
            assert row["task_status"] == "accepted" and row["assignment_status"] == "completed"
            assert f == dict(
                id=str(created["final_acceptance_id"]),
                project_id=s["project_id"],
                task_id=s["task_id"],
                submission_id=s["submission_id"],
                acceptance_source="task_post_submit_route",
                source_review_id=None,
                source_routing_manifest_id=s["id"],
                accepted_submitter_id=s["contributor_id"],
                recorded_by=m["router_actor_id"],
                policy_context_ref=s["locked_policy"]["locked_review_policy_id"],
                source_authorization_decision_id=m["authorization_decision_id"],
                accepted_at=f["accepted_at"],
            )
            assert f["accepted_at"] is not None
            assert c["id"] == str(created["economic"].contribution_record_id)
            for field in (
                "project_id",
                "task_id",
                "submission_id",
                "contributor_id",
                "contribution_policy_version_id",
            ):
                assert c[field] == s[field]
            assert c["contribution_type"] == "accepted_submission"
            assert c["source_final_acceptance_id"] == f["id"]
            assert c["source_task_assignment_id"] == s["assignment_id"]
            assert c["source_review_id"] is None and c["source_review_lease_id"] is None
            assert c["artifact_hash"] == s["content_sha256"]
            awards = (
                (
                    await session.execute(
                        text("""
              SELECT w.id,w.instrument_type,w.quantity,w.unit_code,w.created_at,
                d.quantity AS expected_quantity,d.unit_code AS expected_unit,
                w.award_definition_id=d.id AND w.adapter_binding_id=d.adapter_binding_id
                  AND w.contribution_policy_version_id=d.contribution_policy_version_id AS exact_definition
              FROM public.compensation_awards w JOIN public.contribution_award_definitions d ON d.id=w.award_definition_id
              WHERE w.contribution_record_id=:id ORDER BY w.instrument_type
            """),
                        {"id": created["economic"].contribution_record_id},
                    )
                )
                .mappings()
                .all()
            )
            assert {w["instrument_type"] for w in awards} == set(instruments)
            assert tuple(w["id"] for w in awards) == created["economic"].award_ids
            assert all(
                w["exact_definition"]
                and w["quantity"] == w["expected_quantity"]
                and w["unit_code"] == w["expected_unit"]
                and w["created_at"]
                for w in awards
            )
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
        async with h.factory() as session, session.begin():
            replayed = await apply_outcome(session, h, 2)
            assert replayed == created | {"replayed": True}
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before


async def test_foreign_stored_completion_cannot_use_another_invocation(
    tmp_path, isolated_database_env
):
    async with authorized_routing_source(tmp_path / "local", isolated_database_env) as h:
        async with authorized_routing_source(
            tmp_path / "foreign",
            isolated_database_env,
            storage_settings=h.settings,
            provision_services=False,
        ) as foreign:
            assert h.request.project_id != foreign.request.project_id
            async with h.factory() as session:
                before = await outcome_snapshot(session)
            # Both selections exist; the claim still belongs to the original event.
            payload = json.loads(foreign.envelope.payload_json)
            from app.adapters.tasks import task_post_submit_outcome

            async with h.factory() as session:
                with pytest.raises(
                    TaskRoutingRequestUnavailable, match="routing invocation unavailable"
                ):
                    async with session.begin():
                        await task_post_submit_outcome(session, h.factory).apply(
                            h.envelope.model_copy(update={"payload_json": json.dumps(payload)}),
                            current_generation=2,
                        )
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before
