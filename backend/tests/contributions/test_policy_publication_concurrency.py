"""Real PostgreSQL fence proofs for ContributionPolicy publication."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.adapters.compensation import policy_adapter_binding_port
from app.adapters.projects import project_contribution_policy_eligibility_port
from app.db import session as db_session
from app.modules.contributions.api import ContributionPolicyPublishRequest
from app.modules.contributions.service import ContributionPolicyService
from tests.contributions.policy_test_support import AllowAuthorization
from tests.contributions.test_policy_integration_postgresql import (
    _policy_database_env,  # noqa: F401
)
from tests.test_contributions import _add_rule, _draft_policy, _seed_project


class _BlockingAuthorization(AllowAuthorization):
    def __init__(self, actor_id: UUID) -> None:
        super().__init__(actor_id)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def consume_contribution_policy_mutation(self, prepared, facts):
        self.entered.set()
        await self.release.wait()
        return await super().consume_contribution_policy_mutation(prepared, facts)


async def _complete_draft(
    *, reverse_rule_insertion: bool = False
) -> tuple[ContributionPolicyPublishRequest, UUID, str]:
    project, creator, _, binding, _ = await _seed_project()
    policy, version = await _draft_policy(project, creator)
    rules = (
        (("completed_review", "unpaid", None), ("accepted_submission", "compensated", binding))
        if reverse_rule_insertion
        else (("accepted_submission", "compensated", binding), ("completed_review", "unpaid", None))
    )
    for contribution_type, mode, binding_id in rules:
        await _add_rule(version, project, contribution_type, mode, binding_id=binding_id)
    return (
        ContributionPolicyPublishRequest(
            operation_id=uuid4(),
            actor_profile_id=UUID(creator),
            project_id=UUID(project),
            contribution_policy_id=policy,
            contribution_policy_version_id=version,
        ),
        binding,
        project,
    )


async def _start_paused_publication(request: ContributionPolicyPublishRequest):
    authorization = _BlockingAuthorization(request.actor_profile_id)
    session = db_session.get_session_factory()()
    transaction = session.begin()
    await transaction.__aenter__()
    service = ContributionPolicyService(
        session,
        read_authorization=authorization,
        mutation_authorization=authorization,
        projects=project_contribution_policy_eligibility_port(session),
        bindings=policy_adapter_binding_port(session),
    )
    task = asyncio.create_task(service.publish(request))
    await asyncio.wait_for(authorization.entered.wait(), timeout=5)
    return authorization, session, transaction, task


async def _finish_publication(authorization, session, transaction, task) -> None:
    authorization.release.set()
    await task
    await transaction.__aexit__(None, None, None)
    await session.close()


async def _assert_write_waits(request, statement: str, parameters: dict) -> None:
    authorization, session, transaction, task = await _start_paused_publication(request)
    try:
        async with db_session.get_session_factory()() as contender, contender.begin():
            await contender.execute(text("set local lock_timeout='100ms'"))
            with pytest.raises(DBAPIError):
                await contender.execute(text(statement), parameters)
    finally:
        await _finish_publication(authorization, session, transaction, task)


@pytest.mark.asyncio
async def test_child_mutation_waits_for_publication_graph_fence(
    policy_database_env: str,
) -> None:
    del policy_database_env
    request, _, _ = await _complete_draft()
    await _assert_write_waits(
        request,
        "update contribution_rules set compensation_mode=compensation_mode "
        "where contribution_policy_version_id=:version",
        {"version": request.contribution_policy_version_id},
    )


@pytest.mark.asyncio
async def test_binding_suspension_waits_for_publication_owner_fence(
    policy_database_env: str,
) -> None:
    del policy_database_env
    request, binding, _ = await _complete_draft()
    await _assert_write_waits(
        request,
        "update project_compensation_adapter_bindings "
        "set lifecycle_version=lifecycle_version where id=:binding",
        {"binding": binding},
    )


@pytest.mark.asyncio
async def test_unit_retirement_waits_for_publication_owner_fence(
    policy_database_env: str,
) -> None:
    del policy_database_env
    request, _, project = await _complete_draft()
    await _assert_write_waits(
        request,
        "update project_compensation_units set status=status "
        "where project_id=:project and instrument_type='money' and unit_code='USD'",
        {"project": project},
    )


@pytest.mark.asyncio
async def test_competing_publications_serialize_before_authorization(
    policy_database_env: str,
) -> None:
    del policy_database_env
    request, _, _ = await _complete_draft()
    authorization, session, transaction, task = await _start_paused_publication(request)
    contender_auth = AllowAuthorization(request.actor_profile_id)
    try:
        async with db_session.get_session_factory()() as contender, contender.begin():
            await contender.execute(text("set local lock_timeout='100ms'"))
            service = ContributionPolicyService(
                contender,
                read_authorization=contender_auth,
                mutation_authorization=contender_auth,
                projects=project_contribution_policy_eligibility_port(contender),
                bindings=policy_adapter_binding_port(contender),
            )
            with pytest.raises(DBAPIError):
                await service.publish(
                    ContributionPolicyPublishRequest(
                        operation_id=uuid4(),
                        actor_profile_id=request.actor_profile_id,
                        project_id=request.project_id,
                        contribution_policy_id=request.contribution_policy_id,
                        contribution_policy_version_id=request.contribution_policy_version_id,
                    )
                )
        assert contender_auth.prepared == []
    finally:
        await _finish_publication(authorization, session, transaction, task)


@pytest.mark.asyncio
async def test_reverse_ordered_graphs_use_one_lock_order(
    policy_database_env: str,
) -> None:
    del policy_database_env
    request, _, _ = await _complete_draft(reverse_rule_insertion=True)
    authorization = AllowAuthorization(request.actor_profile_id)
    async with db_session.get_session_factory()() as session, session.begin():
        service = ContributionPolicyService(
            session,
            read_authorization=authorization,
            mutation_authorization=authorization,
            projects=project_contribution_policy_eligibility_port(session),
            bindings=policy_adapter_binding_port(session),
        )
        await service.publish(request)
    assert len(authorization.consumed) == 1
