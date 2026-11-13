"""Valid same-policy tier IDs cannot replace exact copied reward evidence."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.modules.contributions.api import ContributionParticipationUnavailable
from app.modules.contributions.records.repository import SubmitterContributionRepository
from tests.finance.test_selected_reward_journey import selected_public_work


async def test_same_policy_wrong_tier_copy_rejected(tmp_path, isolated_database_env, monkeypatch):
    async with selected_public_work(tmp_path, isolated_database_env, monkeypatch,
                                    human_review_required=False) as h:
        async with h.factory() as session, session.begin():
            policy, selected = (await session.execute(text("""SELECT contribution_policy_version_id,
                contribution_award_definition_id FROM public.submissions WHERE id=:id"""),
                {"id": h.created.submission_id})).one()
            large = await session.scalar(text("""SELECT id FROM public.contribution_award_definitions
                WHERE contribution_policy_version_id=:policy AND contribution_type='accepted_submission'
                  AND task_size='large'"""), {"policy": policy})
            assert large is not None and large != selected
            owner = SubmitterContributionRepository(session)
            valid = await owner.get_frozen_rule(h.request.project_id, policy, "medium", selected)
            assert len(valid.definitions) == 1 and valid.definitions[0].id == selected
            with pytest.raises(ContributionParticipationUnavailable):
                await owner.get_frozen_rule(h.request.project_id, policy, "medium", large)
            before = await session.scalar(text("SELECT to_jsonb(a) FROM public.task_assignments a WHERE id=:id"),
                                          {"id": h.assignment_id})
            with pytest.raises(DBAPIError, match="assignment reward selection differs"):
                async with session.begin_nested():
                    await session.execute(text("UPDATE public.task_assignments SET submitter_award_definition_id=:large WHERE id=:id"),
                                          {"large": large, "id": h.assignment_id})
            assert await session.scalar(text("SELECT to_jsonb(a) FROM public.task_assignments a WHERE id=:id"),
                                        {"id": h.assignment_id}) == before
            with pytest.raises(DBAPIError, match="dispatched submission facts are immutable"):
                async with session.begin_nested():
                    await session.execute(text("UPDATE public.submissions SET contribution_award_definition_id=:large WHERE id=:id"),
                                          {"large": large, "id": h.created.submission_id})
            assert await session.scalar(text("SELECT contribution_award_definition_id FROM public.submissions WHERE id=:id"),
                                        {"id": h.created.submission_id}) == selected


async def test_ready_admission_selection_is_immutable_on_status_transition(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.core.identifiers import new_record_id
    from tests.finance import test_selected_reward_journey as journey

    original_verify = journey._verify_put_attempt
    observed = {}

    async def inspect_ready(factory, *args):
        admission_id = await original_verify(factory, *args)
        async with factory() as session, session.begin():
            before = await session.scalar(text("SELECT to_jsonb(a) FROM public.submission_bundle_admissions a WHERE id=:id"),
                                          {"id": admission_id})
            assert before["status"] == "ready" and before["task_size"] == "medium"
            large = await session.scalar(text("SELECT id FROM public.contribution_award_definitions "
                "WHERE contribution_policy_version_id=:policy AND task_size='large'"),
                {"policy": before["contribution_policy_version_id"]})
            assert large is not None and str(large) != before["contribution_award_definition_id"]
            for field, value in (("task_size", "large"), ("contribution_award_definition_id", large),
                                 ("contribution_policy_version_id", new_record_id())):
                with pytest.raises(DBAPIError, match="admission lineage is immutable"):
                    async with session.begin_nested():
                        await session.execute(text(f"UPDATE public.submission_bundle_admissions SET status='stale', "
                            f"stale_at=clock_timestamp(),stale_reason='Invalid selection change',{field}=:value WHERE id=:id"),
                            {"id": admission_id, "value": value})
                assert await session.scalar(text("SELECT to_jsonb(a) FROM public.submission_bundle_admissions a WHERE id=:id"),
                                            {"id": admission_id}) == before
            observed.update(id=admission_id, before=before)
        return admission_id

    monkeypatch.setattr(journey, "_verify_put_attempt", inspect_ready)
    async with selected_public_work(tmp_path, isolated_database_env, monkeypatch,
                                    human_review_required=False) as h:
        async with h.factory() as session:
            consumed = await session.scalar(text("SELECT to_jsonb(a) FROM public.submission_bundle_admissions a WHERE id=:id"),
                                            {"id": observed["id"]})
            assert consumed["status"] == "consumed"
            assert consumed["consumed_by_submission_id"] == str(h.created.submission_id)
            assert {field: consumed[field] for field in ("task_size", "contribution_policy_version_id", "contribution_award_definition_id")} == {
                field: observed["before"][field] for field in ("task_size", "contribution_policy_version_id", "contribution_award_definition_id")}
