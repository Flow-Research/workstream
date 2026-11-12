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
