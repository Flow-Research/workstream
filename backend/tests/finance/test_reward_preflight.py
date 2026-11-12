"""Read-only diagnostics over real owner effects and isolated retained corruption."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from scripts.finance_reward_preflight import (
    BLOCKERS,
    PreflightUnavailable,
    collect_snapshot,
    read_only_snapshot,
    reward_preflight,
)
from tests.contributions.records.support import authorized_submitter_source
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
    outcome_snapshot,
)
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.test_submission_predecessor_custody import _fixture_revision_context


async def report(*, sample_limit=100):
    return await reward_preflight(db_session.get_engine(), sample_limit=sample_limit)


async def test_empty_supported_database(isolated_database_env):
    result = await report()
    assert result["cutover_blockers_present"] is False
    assert result["cutover_fence_held"] is False
    assert all(item["total_count"] == 0 for item in result["categories"].values())
    assert set(BLOCKERS) <= result["categories"].keys()
    assert all(item == {"present": False} for item in result["optional_inventory"].values())


async def test_snapshot_rejects_writes_and_does_not_repair_data(isolated_database_env):
    engine = db_session.get_engine()
    async with read_only_snapshot(engine) as connection:
        before = await collect_snapshot(connection)
        with pytest.raises(DBAPIError, match="read-only"):
            async with connection.begin_nested():
                await connection.execute(text("UPDATE public.workstream_tasks SET title=title"))
        after = await collect_snapshot(connection)
        assert after == before
    assert (await report())["categories"] == before["categories"]


async def test_unfenced_read_write_connection_is_rejected(isolated_database_env):
    async with db_session.get_engine().connect() as connection:
        with pytest.raises(PreflightUnavailable, match="read_only_snapshot_required"):
            await collect_snapshot(connection)


@pytest.mark.parametrize("limit", [0, 101, True, 1.0])
async def test_sample_limit_is_bounded_before_inventory(isolated_database_env, limit):
    with pytest.raises(ValueError, match="sample_limit"):
        await report(sample_limit=limit)


async def test_live_v1_then_accepted_dual_awards_are_inventory_not_rewritten(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
):
    async with authorized_routing_source(
        tmp_path,
        isolated_database_env,
        contribution_awards=("money", "project_points"),
    ) as h:
        initial = await report()
        assert initial["cutover_blockers_present"] is True
        for category in ("live_v1_tasks", "live_v1_assignments", "live_v1_submissions"):
            assert initial["categories"][category]["total_count"] == 1
            assert initial["categories"][category]["blocks_cutover"] is True
        async with h.factory() as session, session.begin():
            await apply_outcome(session, h, 2)
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        retained = await report(sample_limit=1)
        assert retained["cutover_blockers_present"] is False
        assert retained["categories"]["retained_contributions"]["total_count"] == 1
        awards = retained["categories"]["retained_awards"]
        assert awards["total_count"] == 2 and len(awards["sample_ids"]) == 1
        assert awards["truncated"] is True
        assert retained["categories"]["dual_award_contributions"]["total_count"] == 1
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before


async def test_real_pending_revision_blocks_cutover(tmp_path, isolated_database_env):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        result = await report()
        category = result["categories"]["live_v1_revision_preparations"]
        assert category["blocks_cutover"] is True
        assert category["sample_ids"] == [str(h.revision_preparation_id)]


# Test-only restoration of corrupt retained data. Physical FKs and CHECKs remain
# enforced. These schema-owning tests establish diagnostic sensitivity, never
# claim that current product guards allow these writes.
CORRUPTIONS = [
    (
        "acceptance_source_anomalies",
        [
            (
                "final_acceptances",
                "UPDATE public.final_acceptances SET recorded_by=accepted_submitter_id",
            ),
        ],
    ),
    (
        "contribution_source_anomalies",
        [
            (
                "contribution_records",
                "UPDATE public.contribution_records SET artifact_hash='sha256:' || repeat('a',64)",
            ),
        ],
    ),
    (
        "award_source_anomalies",
        [
            ("compensation_awards", "UPDATE public.compensation_awards SET quantity=quantity+1"),
        ],
    ),
    (
        "award_completeness_anomalies",
        [
            (
                "compensation_awards",
                "DELETE FROM public.compensation_awards WHERE instrument_type='money'",
            ),
        ],
    ),
    (
        "acceptance_contribution_gaps",
        [
            ("compensation_awards", "DELETE FROM public.compensation_awards"),
            ("contribution_records", "DELETE FROM public.contribution_records"),
        ],
    ),
]


@pytest.mark.postgres_schema_contract
@pytest.mark.parametrize("category,changes", CORRUPTIONS, ids=[item[0] for item in CORRUPTIONS])
async def test_retained_corruption_cannot_escape_diagnostic(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    category,
    changes,
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        assert (await report())["categories"][category]["total_count"] == 0
        async with h.factory() as session, session.begin():
            for table, statement in changes:
                await session.execute(text(f"ALTER TABLE public.{table} DISABLE TRIGGER USER"))
                changed = await session.execute(text(statement))
                assert changed.rowcount > 0
                await session.execute(text(f"ALTER TABLE public.{table} ENABLE TRIGGER USER"))
        result = await report()
        assert result["categories"][category]["total_count"] > 0
        assert result["categories"][category]["blocks_cutover"] is True
        assert result["cutover_blockers_present"] is True


@pytest.mark.postgres_schema_contract
async def test_unknown_schema_is_not_a_clean_bill_of_health(isolated_database_env):
    async with db_session.get_engine().begin() as connection:
        await connection.execute(text("UPDATE public.alembic_version SET version_num='unknown'"))
    with pytest.raises(PreflightUnavailable, match="unsupported_schema_revision"):
        await report()
