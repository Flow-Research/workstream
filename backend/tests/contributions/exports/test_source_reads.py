"""Real hidden source/owner projection proof; public AUTH evidence remains separate."""

from uuid import uuid4

import pytest

from app.adapters.compensation import contribution_award_read_port, contributor_award_totals_port
from app.adapters.reviews import final_acceptance_read_port
from app.adapters.tasks import contribution_task_evidence_port
from app.modules.contributions.api.records import ContributionReadRequest
from app.modules.contributions.records.pagination import ContributionExportCursorCodec
from app.modules.contributions.records.read_repository import ContributionReadRepository
from tests.contributions.records.support import authorized_submitter_source, rows


@pytest.mark.parametrize("instruments", [(), ("money",), ("project_points",)])
async def test_projection_reads_actual_immutable_source_and_complete_awards(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, instruments,
):
    async with authorized_submitter_source(
        tmp_path, isolated_database_env, contribution_awards=instruments,
    ) as h:
        async with h.factory() as session:
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            before = {table: await rows(session, table) for table in
                      ("contribution_records", "compensation_awards", "final_acceptances")}
            page = await ContributionReadRepository(
                session, cursor_codec=ContributionExportCursorCodec(b"r" * 32),
            ).read(ContributionReadRequest(
                audience="self", actor_profile_id=h.actor_context.actor_profile_id,
            ))
            record, = page.records
            assert page.next_cursor is None
            assert record.id == h.submitter_record.id
            assert record.source_final_acceptance_id == h.acceptance.id
            assert {definition.instrument for definition in record.award_definitions} == set(instruments)
            awards = await contribution_award_read_port(session).read_contribution_awards((record.id,))
            assert {award.instrument_type.value for award in awards} == set(instruments)
            assert {(award.award_definition_id, award.quantity) for award in awards} == {
                (definition.id, definition.quantity) for definition in record.award_definitions
            }
            acceptance, = await final_acceptance_read_port(session).read_final_acceptances(
                ((record.project_id, record.source_final_acceptance_id),),
            )
            assert acceptance.accepted_at == h.acceptance.accepted_at
            assert acceptance.source_routing_manifest_id == h.acceptance.source_routing_manifest_id
            task, = await contribution_task_evidence_port(session).read_contribution_tasks(
                ((record.project_id, record.task_id),),
            )
            assert task.task_id == record.task_id
            assert {table: await rows(session, table) for table in before} == before
            await session.rollback()


async def test_award_totals_sum_the_contributors_real_awards_in_the_selected_projects(
    tmp_path, isolated_database_env, live_acceptance_lifecycle,
):
    async with authorized_submitter_source(
        tmp_path, isolated_database_env, contribution_awards=("money",),
    ) as h:
        async with h.factory() as session:
            record = h.submitter_record
            awards = await contribution_award_read_port(session).read_contribution_awards((record.id,))
            expected = {}
            for award in awards:
                key = (award.instrument_type.value, award.unit_code)
                expected[key] = expected.get(key, 0) + award.quantity
            totals = contributor_award_totals_port(session)
            selected = await totals.read_award_totals(record.contributor_id, frozenset({record.project_id}))
            assert len(expected) == 1
            assert {(item.instrument_type, item.unit_code): item.quantity for item in selected} == expected
            assert [(item.instrument_type, item.unit_code) for item in selected] == sorted(expected)
            assert await totals.read_award_totals(uuid4(), frozenset({record.project_id})) == ()
            assert await totals.read_award_totals(record.contributor_id, frozenset({uuid4()})) == ()
            await session.rollback()
