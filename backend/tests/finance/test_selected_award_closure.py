"""Native selected-award closure survives omissions and valid wrong-tier inserts."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.compensation.api import CompleteAwardSetResult
from app.modules.compensation.awards.participant import CompensationAwardParticipant
from app.modules.contributions.records.models import ContributionRecord
from app.modules.contributions.records.participant import SubmitterContributionParticipant
from tests.contributions.records.support import award_values, insert_award
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome, authorized_routing_source, outcome_snapshot,
)


async def test_selected_award_closure_and_sole_award_constraint(
    tmp_path, isolated_database_env, monkeypatch, live_acceptance_lifecycle,
):
    async with authorized_routing_source(tmp_path, isolated_database_env,
                                         contribution_awards=("money",)) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)

        async def omit_award(_owner, _request):
            return CompleteAwardSetResult(awards=())

        for mode in ("missing", "wrong_immediate", "wrong_deferred", "complete"):
            with monkeypatch.context() as patch:
                # Isolate the database boundary from the two owner checks.
                if mode != "complete":
                    patch.setattr(CompensationAwardParticipant, "complete_award_set", omit_award)
                    patch.setattr(SubmitterContributionParticipant, "_require_exact_awards", staticmethod(lambda *args: None))
                async with h.factory() as session:
                    await session.begin()
                    try:
                        result = await apply_outcome(session, h, 2)
                        record = await session.get(ContributionRecord, result.economic.contribution_record_id)
                        values = await award_values(session, record)
                        assert len(values) == 1
                        selected = values[0]
                        assert await session.scalar(text("SELECT count(*) FROM public.compensation_awards")) == (1 if mode == "complete" else 0)
                        assert await session.scalar(text("SELECT public.accepted_submission_award_set_is_complete(:id)"),
                                                    {"id": record.id}) is (mode == "complete")
                        if mode == "missing":
                            with pytest.raises(DBAPIError, match="incomplete award set"):
                                await session.execute(text("SET CONSTRAINTS accepted_submission_award_set_from_contribution IMMEDIATE"))
                        elif mode.startswith("wrong"):
                            large = (await session.execute(text("""SELECT id AS award_definition_id,
                                adapter_binding_id,instrument_type,unit_code,quantity
                                FROM public.contribution_award_definitions
                                WHERE contribution_policy_version_id=:policy AND task_size='large'"""),
                                {"policy": record.contribution_policy_version_id})).mappings().one()
                            assert large["award_definition_id"] != selected["award_definition_id"]
                            wrong = selected | dict(large)
                            if mode == "wrong_immediate":
                                with pytest.raises(DBAPIError, match="award differs from submission selection"):
                                    await insert_award(session, wrong)
                            else:
                                # Fault injection proves deferred closure independently of the INSERT guard.
                                trigger = await session.scalar(text("SELECT tgname FROM pg_trigger WHERE tgrelid='public.compensation_awards'::regclass "
                                    "AND tgfoid='public.guard_compensation_award()'::regprocedure"))
                                assert trigger and trigger.replace("_", "").isalnum()
                                await session.execute(text(f'ALTER TABLE public.compensation_awards DISABLE TRIGGER "{trigger}"'))
                                await insert_award(session, wrong)
                                with pytest.raises(DBAPIError, match="incomplete award set"):
                                    await session.execute(text("SET CONSTRAINTS accepted_submission_award_set_from_contribution IMMEDIATE"))
                        else:
                            with pytest.raises(DBAPIError, match="uq_compensation_award_contribution"):
                                async with session.begin_nested():
                                    await insert_award(session, selected, id=new_record_id())
                            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                            await session.commit()
                    finally:
                        await session.rollback()
            if mode != "complete":
                async with h.factory() as session:
                    assert await outcome_snapshot(session) == before
                    assert await session.scalar(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='D'")) == 0
        async with h.factory() as session, session.begin():
            assert list(await session.scalars(text("SELECT award_definition_id FROM public.compensation_awards"))) == [selected["award_definition_id"]]
            replay = await apply_outcome(session, h, 2)
            assert replay.replayed and replay.economic.contribution_record_id == record.id
