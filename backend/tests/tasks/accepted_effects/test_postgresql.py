"""Real PostgreSQL TASK state, source, and lock-boundary proof."""

import pytest

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from app.modules.tasks.api import TaskAcceptedEffectsUnavailable

from .support import accepted_effects_source, participant

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


@pytest.mark.parametrize("prestate", ("review_pending", "evaluation_pending"))
async def test_new_then_exact_replay_preserves_nonterminal_task_facts(
    tmp_path, isolated_database_env, prestate
):
    """Prove TASK mechanics for either prestate, without automated authority."""
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        h.effects_request = h.effects_request.model_copy(update={
            "expected_task_status": prestate,
        })
        async with h.factory() as session, session.begin():
            await session.execute(
                text("UPDATE public.workstream_tasks SET status=:prestate WHERE id=:task_id"),
                {"prestate": prestate, "task_id": h.effects_request.task_id},
            )
        async with h.factory() as session:
            before = (
                await session.execute(
                    text(
                        """
                        SELECT t.assigned_to, a.assigned_at, a.accepted_at,
                               a.released_at, s.status AS submission_status
                        FROM public.workstream_tasks t
                        JOIN public.task_assignments a ON a.id=:assignment_id
                        JOIN public.submissions s ON s.id=:submission_id
                        WHERE t.id=:task_id
                        """
                    ),
                    h.effects_request.model_dump(),
                )
            ).mappings().one()

        async with h.factory() as session, session.begin():
            owner = participant(session)
            prepared = await owner.lock_accepted_effects(
                h.effects_request, expected_generation=2
            )
            assert prepared.disposition == "new"
            assert prepared.locked_review_policy_id == h.locked_review_policy_id
            result = await owner.apply_accepted_effects(
                h.effects_request, disposition="new", expected_generation=2
            )
            assert result.task_status == "accepted"
            assert result.assignment_status == "completed"

        async with h.factory() as session, session.begin():
            owner = participant(session)
            prepared = await owner.lock_accepted_effects(
                h.effects_request, expected_generation=2
            )
            assert prepared.disposition == "replay"
            assert await owner.apply_accepted_effects(
                h.effects_request, disposition="replay", expected_generation=2
            ) == result

        async with h.factory() as session:
            after = (
                await session.execute(
                    text(
                        """
                        SELECT t.status AS task_status, t.assigned_to,
                               a.status AS assignment_status, a.assigned_at,
                               a.accepted_at, a.released_at,
                               s.status AS submission_status
                        FROM public.workstream_tasks t
                        JOIN public.task_assignments a ON a.id=:assignment_id
                        JOIN public.submissions s ON s.id=:submission_id
                        WHERE t.id=:task_id
                        """
                    ),
                    h.effects_request.model_dump(),
                )
            ).mappings().one()
        assert after["task_status"] == "accepted"
        assert after["assignment_status"] == "completed"
        assert {key: after[key] for key in before} == dict(before)


@pytest.mark.parametrize(
    "changes",
    (
        {"submission_version": 2},
        {"submission_id": new_record_id()},
        {"assignment_id": new_record_id()},
        {"contributor_id": new_record_id()},
        {"contribution_policy_version_id": new_record_id()},
        {"content_id": new_record_id()},
    ),
)
async def test_exact_lineage_gates_reject_without_mutation(
    tmp_path, isolated_database_env, changes
):
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        changed = h.effects_request.model_copy(update=changes)
        async with h.factory() as session, session.begin():
            with pytest.raises(TaskAcceptedEffectsUnavailable):
                await participant(session).lock_accepted_effects(
                    changed, expected_generation=2
                )
        async with h.factory() as session:
            states = (
                await session.execute(
                    text(
                        "SELECT t.status, a.status FROM public.workstream_tasks t "
                        "JOIN public.task_assignments a ON a.id=:assignment_id "
                        "WHERE t.id=:task_id"
                    ),
                    h.effects_request.model_dump(),
                )
            ).one()
        assert states == ("review_pending", "active")


@pytest.mark.parametrize(
    ("task_status", "assignment_status"),
    (("accepted", "active"), ("review_pending", "completed")),
)
async def test_mixed_terminal_states_are_neither_new_nor_replay(
    tmp_path, isolated_database_env, task_status, assignment_status
):
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            await session.execute(
                text("UPDATE public.workstream_tasks SET status=:status WHERE id=:id"),
                {"status": task_status, "id": h.effects_request.task_id},
            )
            await session.execute(
                text("UPDATE public.task_assignments SET status=:status WHERE id=:id"),
                {"status": assignment_status, "id": h.effects_request.assignment_id},
            )
        async with h.factory() as session, session.begin():
            with pytest.raises(TaskAcceptedEffectsUnavailable):
                await participant(session).lock_accepted_effects(
                    h.effects_request, expected_generation=2
                )


@pytest.mark.parametrize("timestamp", ("accepted_at", "released_at"))
async def test_assignment_timestamp_preconditions_are_required(
    tmp_path, isolated_database_env, timestamp
):
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        assignment = (
            "accepted_at=NULL"
            if timestamp == "accepted_at"
            else "released_at=clock_timestamp()"
        )
        async with h.factory() as session, session.begin():
            await session.execute(
                text(
                    f"UPDATE public.task_assignments SET {assignment} WHERE id=:id"
                ),
                {"id": h.effects_request.assignment_id},
            )
        async with h.factory() as session, session.begin():
            with pytest.raises(TaskAcceptedEffectsUnavailable):
                await participant(session).lock_accepted_effects(
                    h.effects_request, expected_generation=2
                )


async def test_apply_rechecks_acceptance_disposition(
    tmp_path, isolated_database_env
):
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            owner = participant(session)
            assert (
                await owner.lock_accepted_effects(
                    h.effects_request, expected_generation=2
                )
            ).disposition == "new"
            with pytest.raises(TaskAcceptedEffectsUnavailable):
                await owner.apply_accepted_effects(
                    h.effects_request,
                    disposition="replay",
                    expected_generation=2,
                )


async def test_foreign_project_is_rejected_before_the_actual_task_row_is_locked(
    tmp_path, isolated_database_env
):
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        foreign = h.effects_request.model_copy(update={"project_id": new_record_id()})
        async with h.factory() as first:
            await first.begin()
            with pytest.raises(TaskAcceptedEffectsUnavailable):
                await participant(first).lock_accepted_effects(
                    foreign, expected_generation=2
                )
            async with h.factory() as second, second.begin():
                locked = await second.scalar(
                    text(
                        "SELECT id FROM public.workstream_tasks "
                        "WHERE id=:id FOR UPDATE NOWAIT"
                    ),
                    {"id": h.effects_request.task_id},
                )
                assert locked == h.effects_request.task_id
            await first.rollback()


@pytest.mark.parametrize(
    ("table", "field"),
    (
        ("workstream_tasks", "task_id"),
        ("task_assignments", "assignment_id"),
        ("submissions", "submission_id"),
    ),
)
async def test_preparation_retains_each_owner_lock_until_caller_rollback(
    tmp_path, isolated_database_env, table, field
):
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as first:
            await first.begin()
            await participant(first).lock_accepted_effects(
                h.effects_request, expected_generation=2
            )
            async with h.factory() as second:
                await second.begin()
                with pytest.raises(DBAPIError, match="could not obtain lock"):
                    await second.execute(
                        text(f"SELECT id FROM public.{table} WHERE id=:id FOR UPDATE NOWAIT"),
                        {"id": getattr(h.effects_request, field)},
                    )
                await second.rollback()
            await first.rollback()


async def test_stored_true_policy_manifest_cannot_prove_automated_source(tmp_path, isolated_database_env):
    from uuid import UUID
    from tests.tasks.post_submit_routing.outcome_support import authorized_routing_source, apply_outcome
    from app.modules.tasks.api import TaskAcceptedEffectsRequest

    async with authorized_routing_source(tmp_path, isolated_database_env, human_review_required=True) as h:
        async with h.factory() as session, session.begin():
            result = await apply_outcome(session, h, None)
        async with h.factory() as session, session.begin():
            manifest = await session.scalar(text("SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m WHERE id=:id"),
                {"id":result["routing_manifest_id"]})
            source = manifest["authority_context"]["source"]
            automated = TaskAcceptedEffectsRequest(
                **{key:UUID(source[key]) for key in ("project_id","task_id","assignment_id","submission_id", "contributor_id","contribution_policy_version_id","content_id")},
                submission_version=source["submission_version"],content_sha256=source["content_sha256"],
                final_acceptance_id=new_record_id(),expected_task_status="evaluation_pending")
            with pytest.raises(TaskAcceptedEffectsUnavailable):
                await participant(session).require_routing_source(
                    automated,result["routing_manifest_id"],
                    source_authorization_decision_id=result["authorization_decision_id"],
                    recorded_by=UUID(manifest["router_actor_id"]),
                    locked_review_policy_id=UUID(source["locked_policy"]["locked_review_policy_id"]),
                    expected_generation=2,disposition="new")
            assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 0


async def test_canonical_fence_rejects_missing_nested_and_stale_generation(
    tmp_path, isolated_database_env
):
    async with accepted_effects_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
                await participant(session).lock_accepted_effects(
                    h.effects_request, expected_generation=2
                )
            assert not session.in_transaction()

        async with h.factory() as session, session.begin():
            async with session.begin_nested():
                with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
                    await participant(session).lock_accepted_effects(
                        h.effects_request, expected_generation=2
                    )

        async with h.factory() as session, session.begin():
            with pytest.raises(JointLifecycleUnavailable, match="generation changed"):
                await participant(session).lock_accepted_effects(
                    h.effects_request, expected_generation=1
                )
