"""Real PostgreSQL proof for hidden source-neutral submitter participation."""

import pytest

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.compensation.api import (
    AwardContributionFacts,
    AwardDefinitionFacts,
    CompleteAwardSetRequest,
    CompensationAwardFacts,
    CompensationInstrumentType,
    CompensationAwardConflict,
)
from app.modules.compensation.awards.participant import CompensationAwardParticipant
from app.modules.contributions.api import (
    ContributionParticipationConflict,
    SubmitterContributionFacts,
)
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from tests.contributions.records.support import (
    award_values,
    authorized_submitter_source,
    rows,
)

from .support import participant, request_for

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


@pytest.mark.parametrize(
    "instruments",
    [(), ("money",), ("project_points",), ("money", "project_points")],
    ids=("unpaid", "money", "points", "money-and-points"),
)
async def test_create_and_exact_replay_all_frozen_award_shapes(
    tmp_path, isolated_database_env, instruments
):
    async with authorized_submitter_source(
        tmp_path, isolated_database_env, contribution_awards=instruments
    ) as h:
        request = request_for(h, acceptance_disposition="replay")
        created = h.participation
        async with h.factory() as session, session.begin():
            replayed = await participant(session).participate_submitter(
                request.model_copy(update={"acceptance_disposition": "replay"})
            )

        assert replayed == created
        assert created.contribution.source_final_acceptance_id == h.acceptance.id
        assert (
            created.contribution.source_task_assignment_id
            == h.submitter_record.source_task_assignment_id
        )
        assert created.contribution.artifact_hash == h.submitter_record.artifact_hash
        assert {award.instrument_type.value for award in created.awards} == set(instruments)
        async with h.factory() as session:
            record = (
                (
                    await session.execute(
                        text("""
                SELECT * FROM public.contribution_records
                WHERE id=:record_id
            """),
                        {"record_id": created.contribution.id},
                    )
                )
                .mappings()
                .one()
            )
            stored_contribution = SubmitterContributionFacts(
                id=record["id"],
                project_id=record["project_id"],
                task_id=record["task_id"],
                submission_id=record["submission_id"],
                contributor_id=record["contributor_id"],
                source_final_acceptance_id=record["source_final_acceptance_id"],
                source_task_assignment_id=record["source_task_assignment_id"],
                artifact_hash=record["artifact_hash"],
                contribution_policy_version_id=record["contribution_policy_version_id"],
                created_at=record["created_at"],
            )
            assert stored_contribution == created.contribution
            assert record["contribution_type"] == "accepted_submission"
            assert record["source_review_id"] is None
            assert record["source_review_lease_id"] is None
            stored = (
                (
                    await session.execute(
                        text("""
                SELECT a.*, d.quantity AS definition_quantity,
                  d.unit_code AS definition_unit,
                  d.adapter_binding_id AS definition_binding,
                  d.contribution_policy_version_id AS definition_policy,
                  d.project_id AS definition_project,
                  d.contribution_type AS definition_type,
                  d.instrument_type AS definition_instrument
                FROM public.compensation_awards a
                JOIN public.contribution_award_definitions d ON d.id=a.award_definition_id
                WHERE a.contribution_record_id=:record_id
                ORDER BY a.instrument_type
            """),
                        {"record_id": created.contribution.id},
                    )
                )
                .mappings()
                .all()
            )
            assert len(stored) == len(instruments)
            stored_awards = tuple(
                CompensationAwardFacts(
                    id=award["id"],
                    project_id=award["project_id"],
                    contribution_record_id=award["contribution_record_id"],
                    contributor_id=award["contributor_id"],
                    contribution_policy_version_id=award["contribution_policy_version_id"],
                    award_definition_id=award["award_definition_id"],
                    adapter_binding_id=award["adapter_binding_id"],
                    instrument_type=CompensationInstrumentType(award["instrument_type"]),
                    unit_code=award["unit_code"],
                    quantity=award["quantity"],
                    created_at=award["created_at"],
                    correlation_id=award["correlation_id"],
                )
                for award in stored
            )
            assert stored_awards == created.awards
            for award in stored:
                assert award["quantity"] == award["definition_quantity"]
                assert award["unit_code"] == award["definition_unit"]
                assert award["adapter_binding_id"] == award["definition_binding"]
                assert award["contribution_policy_version_id"] == award["definition_policy"]
                assert award["project_id"] == award["definition_project"]
                assert award["instrument_type"] == award["definition_instrument"]
                assert award["definition_type"] == "accepted_submission"
                assert award["correlation_id"] == request.correlation_id
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM public.contribution_records "
                        "WHERE contribution_type='completed_review'"
                    )
                )
                == 0
            )


async def test_missing_replay_conflicts_and_outer_commit_leaves_no_economic_facts(
    tmp_path, isolated_database_env
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        request = request_for(
            h, acceptance_disposition="replay", final_acceptance_id=new_record_id()
        )
        async with h.factory() as session:
            before = {
                name: await rows(session, name)
                for name in ("contribution_records", "compensation_awards")
            }
        async with h.factory() as session, session.begin():
            with pytest.raises(ContributionParticipationConflict):
                await participant(session).participate_submitter(request)
        async with h.factory() as session:
            assert {name: await rows(session, name) for name in before} == before


async def test_new_against_existing_exact_facts_conflicts_without_replay(
    tmp_path, isolated_database_env
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        request = request_for(h, acceptance_disposition="new")
        created = h.participation

        async with h.factory() as session, session.begin():
            with pytest.raises(ContributionParticipationConflict):
                await participant(session).participate_submitter(request)

        async with h.factory() as session:
            stored_records = await rows(session, "contribution_records")
            stored_awards = await rows(session, "compensation_awards")
            assert [row["id"] for row in stored_records] == [str(created.contribution.id)]
            assert {row["id"] for row in stored_awards} == {
                str(award.id) for award in created.awards
            }


async def test_retired_policy_and_suspended_bindings_keep_frozen_awards_due(
    tmp_path, isolated_database_env
):
    async with authorized_submitter_source(
        tmp_path, isolated_database_env, paid=True, retire_before_outcome=True
    ) as h:
        assert {award.instrument_type.value for award in h.participation.awards} == {
            "money",
            "project_points",
        }


async def test_exact_replay_rejects_each_changed_source_fact_and_real_foreign_source(
    tmp_path, isolated_database_env
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        async with authorized_submitter_source(
            tmp_path / "foreign",
            isolated_database_env,
            paid=True,
            provision_services=False,
            storage_settings=h.settings,
        ) as foreign:
            original = request_for(h, acceptance_disposition="replay")
            foreign_request = request_for(
                foreign,
                acceptance_disposition="replay",
                correlation_id=original.correlation_id,
            )
            created = h.participation
            replay = original.model_copy(update={"acceptance_disposition": "replay"})

            conflict_fields = (
                "task_id",
                "submission_id",
                "task_assignment_id",
                "contributor_id",
            )
            for field in conflict_fields:
                async with h.factory() as session, session.begin():
                    with pytest.raises(ContributionParticipationConflict):
                        await participant(session).participate_submitter(
                            replay.model_copy(update={field: getattr(foreign_request, field)})
                        )
            changed_digest = "sha256:" + (
                "0" * 64 if original.artifact_hash != "sha256:" + "0" * 64 else "1" * 64
            )
            async with h.factory() as session, session.begin():
                with pytest.raises(ContributionParticipationConflict):
                    await participant(session).participate_submitter(
                        replay.model_copy(update={"artifact_hash": changed_digest})
                    )
            for field in ("project_id", "contribution_policy_version_id"):
                async with h.factory() as session, session.begin():
                    with pytest.raises(
                        RuntimeError, match="contribution_participation_unavailable"
                    ):
                        await participant(session).participate_submitter(
                            replay.model_copy(update={field: getattr(foreign_request, field)})
                        )
            async with h.factory() as session, session.begin():
                with pytest.raises(ContributionParticipationConflict):
                    await participant(session).participate_submitter(
                        replay.model_copy(
                            update={"final_acceptance_id": foreign_request.final_acceptance_id}
                        )
                    )
                assert len(await rows(session, "contribution_records")) == 2
                assert len(await rows(session, "compensation_awards")) == 4
            assert created.contribution.id is not None


async def test_paid_correlation_conflicts_but_unpaid_replay_is_honest(
    tmp_path, isolated_database_env
):
    async with authorized_submitter_source(
        tmp_path / "paid", isolated_database_env, paid=True
    ) as paid:
        paid_request = request_for(paid, acceptance_disposition="replay")
        created = paid.participation
        async with paid.factory() as session, session.begin():
            with pytest.raises(ContributionParticipationConflict):
                await participant(session).participate_submitter(
                    paid_request.model_copy(
                        update={
                            "acceptance_disposition": "replay",
                            "correlation_id": new_record_id(),
                        }
                    )
                )
        async with paid.factory() as session:
            assert len(await rows(session, "compensation_awards")) == len(created.awards) == 2

    async with authorized_submitter_source(
        tmp_path / "unpaid",
        isolated_database_env,
        provision_services=False,
        storage_settings=paid.settings,
    ) as unpaid:
        first_request = request_for(unpaid, acceptance_disposition="replay")
        first = unpaid.participation
        async with unpaid.factory() as session, session.begin():
            second = await participant(session).participate_submitter(
                first_request.model_copy(
                    update={
                        "acceptance_disposition": "replay",
                        "correlation_id": new_record_id(),
                    }
                )
            )
        assert second == first
        assert second.awards == ()


async def test_partial_same_transaction_replay_rejects_without_backfill(
    tmp_path, isolated_database_env, monkeypatch
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        request = request_for(h, acceptance_disposition="replay")
        async with h.factory() as session:
            await session.begin()
            await PostgresJointLifecycleMutationFence(session).acquire(2)
            expected_awards = await award_values(session, h.submitter_record)
            # Isolate replay from storage immutability; this corruption never commits.
            await session.execute(
                text(
                    "ALTER TABLE public.compensation_awards DISABLE TRIGGER compensation_award_immutable"
                )
            )
            await session.execute(
                text("DELETE FROM public.compensation_awards WHERE id=:id"),
                {"id": h.participation.awards[1].id},
            )
            with pytest.raises(ContributionParticipationConflict):
                await participant(session).participate_submitter(request)
            assert len(await rows(session, "compensation_awards")) == 1

            owner = CompensationAwardParticipant(session)
            definitions = tuple(
                AwardDefinitionFacts(
                    id=award["award_definition_id"],
                    project_id=h.submitter_record.project_id,
                    contribution_policy_version_id=(
                        h.submitter_record.contribution_policy_version_id
                    ),
                    contribution_type="accepted_submission",
                    instrument_type=CompensationInstrumentType(award["instrument_type"]),
                    unit_code=award["unit_code"],
                    quantity=award["quantity"],
                    adapter_binding_id=award["adapter_binding_id"],
                )
                for award in expected_awards
            )
            rule_request = CompleteAwardSetRequest(
                disposition="replay",
                compensation_mode="compensated",
                contribution=AwardContributionFacts(
                    id=h.submitter_record.id,
                    project_id=h.submitter_record.project_id,
                    contributor_id=h.submitter_record.contributor_id,
                    contribution_policy_version_id=h.submitter_record.contribution_policy_version_id,
                    contribution_type="accepted_submission",
                ),
                definitions=definitions,
                correlation_id=request.correlation_id,
            )
            with pytest.raises(CompensationAwardConflict):
                await owner.complete_award_set(rule_request)
            assert len(await rows(session, "compensation_awards")) == 1

            monkeypatch.setattr(
                CompensationAwardParticipant,
                "_require_exact_complete_set",
                staticmethod(lambda request, awards: None),
            )
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(CompensationAwardConflict):
                    await owner.complete_award_set(rule_request)
            await session.rollback()
