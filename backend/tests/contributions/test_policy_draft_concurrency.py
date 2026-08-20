"""PostgreSQL concurrency proof for one open policy draft per project."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.adapters.projects import project_contribution_policy_eligibility_port
from app.db import session as db_session
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyCreateDraftRequest,
)
from app.modules.contributions.models import ContributionPolicyVersion
from app.modules.contributions.service import ContributionPolicyService
from test_contributions import _seed_project
from tests.contributions.policy_test_support import AllowAuthorization
from tests.contributions.test_policy_integration_postgresql import (
    _policy_database_env as _policy_database_env_fixture,  # noqa: F401
)


async def _run_distinct_create_race() -> tuple[int, int, int]:
    project, creator, *_ = await _seed_project()
    project_id, actor_id = UUID(project), UUID(creator)
    authorizations = (AllowAuthorization(actor_id), AllowAuthorization(actor_id))

    async def create(index: int) -> bool:
        async with db_session.get_session_factory()() as session:
            try:
                async with session.begin():
                    service = ContributionPolicyService(
                        session,
                        read_authorization=authorizations[index],
                        mutation_authorization=authorizations[index],
                        projects=project_contribution_policy_eligibility_port(session),
                    )
                    await service.create_draft(
                        ContributionPolicyCreateDraftRequest(
                            operation_id=uuid4(),
                            actor_profile_id=actor_id,
                            project_id=project_id,
                            name="Concurrent policy",
                        )
                    )
            except ContributionPolicyConflict:
                return False
        return True

    outcomes = await asyncio.gather(create(0), create(1))
    async with db_session.get_session_factory()() as session:
        drafts = await session.scalar(
            select(func.count())
            .select_from(ContributionPolicyVersion)
            .where(
                ContributionPolicyVersion.project_id == str(project_id),
                ContributionPolicyVersion.status == "draft",
            )
        )
    return sum(outcomes), sum(len(item.consumed) for item in authorizations), drafts or 0


@pytest.mark.asyncio
async def test_distinct_create_race_allows_one_open_draft(
    policy_database_env: str,
) -> None:
    del policy_database_env
    successes, _, drafts = await _run_distinct_create_race()
    assert (successes, drafts) == (1, 1)


@pytest.mark.asyncio
async def test_distinct_create_race_allows_one_authorization_consumption(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, consumptions, _ = await _run_distinct_create_race()
    assert consumptions == 1
