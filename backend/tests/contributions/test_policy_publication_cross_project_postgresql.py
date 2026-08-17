"""Real-row cross-project isolation proof for policy finalization."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.adapters.compensation import policy_adapter_binding_port
from app.adapters.projects import project_contribution_policy_eligibility_port
from app.db import session as db_session
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyPublishRequest,
    ContributionPolicyRetireRequest,
)
from app.modules.contributions.models import ContributionPolicyLifecycleEvent
from app.modules.contributions.service import ContributionPolicyService
from tests.contributions.policy_test_support import AllowAuthorization
from tests.contributions.test_policy_integration_postgresql import (
    _exercise_policy,
    _policy_database_env,  # noqa: F401
    _seed_project_only,
)


@pytest.mark.asyncio
async def test_cross_project_finalization_conceals_real_foreign_rows(
    policy_database_env: str,
) -> None:
    del policy_database_env
    owner_project, created, _, published = await _exercise_policy()
    foreign_project = UUID(await _seed_project_only())
    authorization = AllowAuthorization(created.actor_profile_id)
    before = len(authorization.consumed)
    async with db_session.get_session_factory()() as session:
        service = ContributionPolicyService(
            session,
            read_authorization=authorization,
            mutation_authorization=authorization,
            projects=project_contribution_policy_eligibility_port(session),
            bindings=policy_adapter_binding_port(session),
        )
        for request in (
            ContributionPolicyPublishRequest(
                operation_id=uuid4(),
                actor_profile_id=created.actor_profile_id,
                project_id=foreign_project,
                contribution_policy_id=created.contribution_policy_id,
                contribution_policy_version_id=published.contribution_policy_version_id,
            ),
            ContributionPolicyRetireRequest(
                operation_id=uuid4(),
                actor_profile_id=created.actor_profile_id,
                project_id=foreign_project,
                contribution_policy_id=created.contribution_policy_id,
                contribution_policy_version_id=published.contribution_policy_version_id,
            ),
        ):
            with pytest.raises(ContributionPolicyConflict, match="not_found"):
                async with session.begin():
                    if isinstance(request, ContributionPolicyPublishRequest):
                        await service.publish(request)
                    else:
                        await service.retire(request)
    assert len(authorization.consumed) == before
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ContributionPolicyLifecycleEvent)
                .where(ContributionPolicyLifecycleEvent.project_id == str(owner_project))
            )
            == 3
        )
