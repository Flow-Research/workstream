"""Immutable reviewer storage and atomic routed submitter economics."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from tests.tasks.post_submit_routing.outcome_support import (
    authorized_routing_source,
    apply_outcome,
    outcome_snapshot,
)
from .support import (
    reviewer_contribution_source,
    authorized_submitter_source,
    insert_record,
    insert_award,
    award_values,
    rows,
    retire_policy_and_suspend_bindings,
)

pytestmark = pytest.mark.postgres_schema_contract


async def reject_record(session, record, message, **changes):
    with pytest.raises(DBAPIError, match=message):
        async with session.begin_nested():
            await insert_record(session, record, **changes)


async def reject_award(session, award, message, **changes):
    with pytest.raises(DBAPIError, match=message):
        async with session.begin_nested():
            await insert_award(session, award, **changes)


@pytest.mark.parametrize("decision", ["accept", "needs_revision", "reject"])
async def test_review_contribution_sources(tmp_path, isolated_database_env, decision):
    async with reviewer_contribution_source(
        tmp_path, isolated_database_env, decision=decision
    ) as h:
        async with h.factory() as session, session.begin():
            await reject_record(
                session,
                h.reviewer_record,
                "ck_contribution_records_source_shape",
                source_task_assignment_id=h.request.assignment_id,
            )
            await insert_record(session, h.reviewer_record)
            await reject_record(session, h.reviewer_record, "uq_contribution_records_source_review_id", id=new_record_id())
        async with h.factory() as session:
            stored = await rows(session, "contribution_records")
            assert len(stored) == 1
            assert {
                key: value for key, value in stored[0].items() if key != "created_at"
            } == h.reviewer_record.model_dump(mode="json")
            assert await rows(session, "final_acceptances") == []
            assert await rows(session, "compensation_awards") == []
            assert len(await rows(session, "reviews")) == 1


@pytest.mark.parametrize("retired", [False, True])
async def test_reviewer_frozen_awards(tmp_path, isolated_database_env, retired):
    async with reviewer_contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        if retired:
            await retire_policy_and_suspend_bindings(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
            awards = await award_values(session, h.reviewer_record)
            assert {a["instrument_type"] for a in awards} == {"money", "project_points"}
            for award in awards:
                await insert_award(session, award)
        async with h.factory() as session:
            actual = (
                (
                    await session.execute(
                        text("""SELECT w.*,d.quantity AS quantity_expected,
                d.unit_code AS unit_expected,d.adapter_binding_id AS binding_expected,
                d.contribution_policy_version_id AS policy_expected,d.contribution_type AS kind_expected
              FROM public.compensation_awards w JOIN public.contribution_award_definitions d ON d.id=w.award_definition_id""")
                    )
                )
                .mappings()
                .all()
            )
            assert len(actual) == 2
            for a in actual:
                assert (
                    a["quantity"]
                    == a["quantity_expected"]
                    == (
                        Decimal("2.125000000000000001")
                        if a["instrument_type"] == "money"
                        else Decimal("7")
                    )
                )
                assert a["unit_code"] == a["unit_expected"]
                assert a["adapter_binding_id"] == a["binding_expected"]
                assert a["contribution_policy_version_id"] == a["policy_expected"]
                assert a["kind_expected"] == "completed_review"
                assert str(a["contributor_id"]) == str(h.reviewer_record.contributor_id)


async def test_review_contribution_foreign_source_substitutions(tmp_path, isolated_database_env):
    async with reviewer_contribution_source(tmp_path, isolated_database_env) as h:
        async with reviewer_contribution_source(
            tmp_path / "foreign",
            isolated_database_env,
            provision_services=False,
            storage_settings=h.settings,
        ) as foreign:
            async with h.factory() as session:
                for field in (
                    "project_id",
                    "task_id",
                    "submission_id",
                    "contributor_id",
                    "contribution_policy_version_id",
                    "source_review_id",
                    "source_review_lease_id",
                ):
                    value = getattr(foreign.reviewer_record, field)
                    assert value != getattr(h.reviewer_record, field)
                    await reject_record(
                        session, h.reviewer_record, "contribution .* mismatch", **{field: value}
                    )
                await reject_record(
                    session,
                    h.reviewer_record,
                    "contribution .* mismatch",
                    artifact_hash="sha256:" + "0" * 64,
                )
                assert await rows(session, "contribution_records") == []
                await insert_record(session, h.reviewer_record)
                await session.commit()


async def test_reviewer_award_definition_substitution(tmp_path, isolated_database_env):
    async with reviewer_contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
            money, points = await award_values(session, h.reviewer_record)
        async with h.factory() as session:
            for change in (
                {"quantity": money["quantity"] + Decimal("0.000000000000000001")},
                {"unit_code": "EUR"},
                {"adapter_binding_id": points["adapter_binding_id"]},
                {"award_definition_id": points["award_definition_id"]},
                {"instrument_type": "project_points", "quantity": Decimal("7"), "unit_code": "PTS"},
            ):
                await reject_award(session, money, "award frozen definition mismatch", **change)
            await reject_award(
                session, money, "award contribution lineage mismatch", contributor_id=h.submitter_id
            )
            definition = await session.scalar(text(
                "SELECT pg_get_functiondef('public.guard_compensation_award()'::regprocedure)"
            ))
            predicate = "AND definition.quantity=NEW.quantity"
            assert definition.count(predicate) == 1
            await session.execute(text(definition.replace(predicate, "")))
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                await reject_award(
                    session,
                    money,
                    "award frozen definition mismatch",
                    quantity=money["quantity"] + 1,
                )
            await session.rollback()
        async with reviewer_contribution_source(
            tmp_path / "foreign",
            isolated_database_env,
            paid=True,
            provision_services=False,
            storage_settings=h.settings,
        ) as foreign:
            async with h.factory() as session:
                foreign_money = (await award_values(session, foreign.reviewer_record))[0]
                for change in (
                    {"project_id": foreign_money["project_id"]},
                    {
                        "contribution_policy_version_id": foreign_money[
                            "contribution_policy_version_id"
                        ]
                    },
                ):
                    await reject_award(
                        session, money, "award contribution lineage mismatch", **change
                    )
                await reject_award(session, money, "award frozen definition mismatch",
                                   award_definition_id=foreign_money["award_definition_id"],
                                   adapter_binding_id=foreign_money["adapter_binding_id"])
                await insert_award(session, money)
                await insert_award(session, points)
                await session.commit()
        async with h.factory() as session, session.begin():
            await reject_award(session, money, "uq_compensation_awards", id=new_record_id())


async def test_unpaid_routed_contribution_rejects_award(
    tmp_path, isolated_database_env, live_acceptance_lifecycle
):
    async with authorized_submitter_source(tmp_path, isolated_database_env) as h:
        async with reviewer_contribution_source(
            tmp_path / "paid",
            isolated_database_env,
            paid=True,
            provision_services=False,
            storage_settings=h.settings,
        ) as paid:
            async with h.factory() as session:
                foreign = (await award_values(session, paid.reviewer_record))[0]
                source = h.submitter_record
                await reject_award(
                    session,
                    foreign,
                    "unpaid contribution cannot receive an award",
                    project_id=source.project_id,
                    contribution_record_id=source.id,
                    contributor_id=source.contributor_id,
                    contribution_policy_version_id=source.contribution_policy_version_id,
                )
                assert await rows(session, "compensation_awards") == []


async def test_reviewer_record_and_award_clock(tmp_path, isolated_database_env):
    async with reviewer_contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        async with h.factory() as session, session.begin():
            before = await session.scalar(text("SELECT clock_timestamp()"))
            await insert_record(
                session, h.reviewer_record, created_at=datetime(2000, 1, 1, tzinfo=UTC)
            )
            for award in await award_values(session, h.reviewer_record):
                await insert_award(session, award, created_at=datetime(2000, 1, 1, tzinfo=UTC))
            after = await session.scalar(text("SELECT clock_timestamp()"))
            for table in ("contribution_records", "compensation_awards"):
                times = await session.scalars(text(f"SELECT created_at FROM public.{table}"))
                assert all(before <= value <= after for value in times)


async def test_routed_contribution_and_awards_are_immutable(
    tmp_path, isolated_database_env, live_acceptance_lifecycle
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        for table in ("contribution_records", "compensation_awards"):
            for sql in (
                f"UPDATE public.{table} SET created_at=clock_timestamp()",
                f"DELETE FROM public.{table}",
                f"TRUNCATE public.{table} CASCADE",
            ):
                async with h.factory() as session:
                    with pytest.raises(DBAPIError, match="immutable"):
                        async with session.begin():
                            await session.execute(text(sql))
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before


@pytest.mark.parametrize("kind", ["contribution", "award"])
@pytest.mark.parametrize("commit_first", [True, False])
async def test_reviewer_source_and_award_uniqueness_race(
    tmp_path, isolated_database_env, kind, commit_first
):
    from tests.reviews.packet.test_repository import wait_for_blocker

    async with reviewer_contribution_source(
        tmp_path, isolated_database_env, paid=kind == "award"
    ) as h:
        async with h.factory() as session:
            award = (
                (await award_values(session, h.reviewer_record))[0]
                if kind == "award"
                else None
            )
            if award:
                await insert_record(session, h.reviewer_record)
                await session.commit()
        first_id = h.reviewer_record.id if kind == "contribution" else award["id"]
        duplicate_id = new_record_id()
        ready = asyncio.Future()

        async def insert_candidate(session, identity):
            if kind == "contribution":
                await insert_record(session, h.reviewer_record, id=identity)
            else:
                await insert_award(session, award, id=identity)

        async def competitor():
            async with h.factory() as session:
                ready.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
                if commit_first:
                    with pytest.raises(DBAPIError, match="uq_.*"):
                        await insert_candidate(session, duplicate_id)
                else:
                    await insert_candidate(session, duplicate_id)
                    await session.commit()

        async with h.factory() as first:
            await insert_candidate(first, first_id)
            contender = asyncio.create_task(competitor())
            try:
                await wait_for_blocker(h.factory, await ready)
                await (first.commit() if commit_first else first.rollback())
                await asyncio.wait_for(contender, 10)
            finally:
                await first.rollback()
                if not contender.done():
                    contender.cancel()
                await asyncio.gather(contender, return_exceptions=True)
        async with h.factory() as session:
            table = "contribution_records" if kind == "contribution" else "compensation_awards"
            assert [r["id"] for r in await rows(session, table)] == [
                str(first_id if commit_first else duplicate_id)
            ]


@pytest.mark.parametrize("remove_guard", [False, True])
async def test_routed_accepted_submission_requires_complete_awards(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
    remove_guard,
):
    from app.modules.compensation.awards.participant import CompensationAwardParticipant
    from app.modules.contributions.records.participant import SubmitterContributionParticipant

    async with authorized_routing_source(
        tmp_path, isolated_database_env, contribution_awards=("money", "project_points")
    ) as h:
        original = CompensationAwardParticipant.complete_award_set

        async def incomplete(owner, request):
            return await original(
                owner, request.model_copy(update={"definitions": request.definitions[:1]})
            )

        async with h.factory() as session:
            before = await outcome_snapshot(session)
        with monkeypatch.context() as patch:
            patch.setattr(CompensationAwardParticipant, "complete_award_set", incomplete)
            patch.setattr(
                SubmitterContributionParticipant,
                "_require_exact_awards",
                staticmethod(lambda *args: None),
            )
            async with h.factory() as session:
                await session.begin()
                if remove_guard:
                    await session.execute(
                        text(
                            "DROP TRIGGER accepted_submission_award_set_from_contribution ON public.contribution_records"
                        )
                    )
                    await session.execute(
                        text(
                            "DROP TRIGGER accepted_submission_award_set_from_award ON public.compensation_awards"
                        )
                    )
                await apply_outcome(session, h, 2)
                assert len(await rows(session, "compensation_awards")) == 1

                async def assert_reject():
                    with pytest.raises(DBAPIError, match="incomplete award set"):
                        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

                if remove_guard:
                    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                        await assert_reject()
                else:
                    await assert_reject()
                await session.rollback()
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            assert len((await apply_outcome(session, h, 2)).economic.award_ids) == 2


async def test_uncommitted_acceptance_and_contribution_parents_are_invisible(
    tmp_path, isolated_database_env, live_acceptance_lifecycle,
):
    import json
    from app.modules.contributions.records.schemas import ContributionRecordInput
    async with authorized_routing_source(tmp_path, isolated_database_env, contribution_awards=("money",)) as h:
        async with h.factory() as parent:
            await parent.begin()
            pending = await apply_outcome(parent, h, 2)
            value = await parent.scalar(text("SELECT to_jsonb(c) FROM public.contribution_records c WHERE id=:id"),
                {"id": pending.economic.contribution_record_id})
            value.pop("created_at")
            record = ContributionRecordInput.model_validate_json(json.dumps(value))
            awards = await award_values(parent, record)
            assert len(awards) == 1
            async with h.factory() as child:
                with pytest.raises(DBAPIError, match="contribution submitter source mismatch"):
                    async with child.begin():
                        await child.execute(text("SET LOCAL statement_timeout='2s'"))
                        await insert_record(child, record, id=new_record_id())
            async with h.factory() as child:
                with pytest.raises(DBAPIError, match="award contribution lineage mismatch"):
                    async with child.begin():
                        await child.execute(text("SET LOCAL statement_timeout='2s'"))
                        await insert_award(child, awards[0])
            await parent.rollback()
        async with h.factory() as session:
            assert await rows(session, "contribution_records") == []
            assert await rows(session, "compensation_awards") == []
        async with h.factory() as session, session.begin():
            assert len((await apply_outcome(session, h, 2)).economic.award_ids) == 1
