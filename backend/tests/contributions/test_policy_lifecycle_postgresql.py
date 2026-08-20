"""Direct PostgreSQL rejection proof for final policy lifecycle custody."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.adapters.compensation import policy_adapter_binding_port
from app.adapters.projects import project_contribution_policy_eligibility_port
from app.modules.contributions.api import ContributionPolicyRetireRequest
from app.modules.contributions.service import ContributionPolicyService
from tests.contributions.policy_test_support import AllowAuthorization
from tests.contributions.test_policy_integration_postgresql import (
    _exercise_policy,
    _policy_database_env,  # noqa: F401
)


@pytest.mark.asyncio
async def test_database_rejects_event_without_matching_row_transition(
    policy_database_env: str,
) -> None:
    del policy_database_env
    project_id, created, _, published = await _exercise_policy()
    operation_id = uuid4()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "insert into contribution_policy_transition_custody "
                    "(operation_id,request_digest,event_type,actor_profile_id,project_id,"
                    "contribution_policy_id,contribution_policy_version_id) values "
                    "(:operation_id,:digest,'published',:actor,:project,:policy,:version)"
                ),
                {
                    "operation_id": operation_id,
                    "digest": "sha256:" + "1" * 64,
                    "actor": str(created.actor_profile_id),
                    "project": str(project_id),
                    "policy": created.contribution_policy_id,
                    "version": published.contribution_policy_version_id,
                },
            )
            await session.execute(
                text(
                    "insert into contribution_policy_lifecycle_events "
                    "(id,operation_id,publication_custody_operation_id,request_digest,"
                    "event_type,actor_profile_id,project_id,contribution_policy_id,"
                    "contribution_policy_version_id,version_number,from_policy_status,"
                    "to_policy_status,from_version_status,to_version_status) values "
                    "(:id,:operation_id,:operation_id,:digest,'published',:actor,:project,"
                    ":policy,:version,1,'draft','active','draft','published')"
                ),
                {
                    "id": uuid4(),
                    "operation_id": operation_id,
                    "digest": "sha256:" + "1" * 64,
                    "actor": str(created.actor_profile_id),
                    "project": str(project_id),
                    "policy": created.contribution_policy_id,
                    "version": published.contribution_policy_version_id,
                },
            )


@pytest.mark.asyncio
async def test_database_rejects_final_version_attribution_drift(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, _, published = await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "update contribution_policy_versions set published_at=clock_timestamp() "
                    "where id=:version"
                ),
                {"version": published.contribution_policy_version_id},
            )


@pytest.mark.asyncio
async def test_database_rejects_published_graph_mutation(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, _, published = await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "update contribution_rules set compensation_mode='unpaid' "
                    "where contribution_policy_version_id=:version"
                ),
                {"version": published.contribution_policy_version_id},
            )


@pytest.mark.asyncio
async def test_database_rejects_publication_lifecycle_skip(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, _, published = await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text("update contribution_policy_versions set status='retired' where id=:version"),
                {"version": published.contribution_policy_version_id},
            )


@pytest.mark.asyncio
async def test_database_rejects_published_version_downgrade(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, _, published = await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "update contribution_policy_versions set status='draft', "
                    "published_by=null,published_at=null where id=:version"
                ),
                {"version": published.contribution_policy_version_id},
            )


@pytest.mark.asyncio
async def test_database_rejects_retirement_with_publication_custody(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, _, published = await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "update contribution_policy_versions v set status='retired',"
                    "retired_by=c.actor_profile_id,retired_at=c.occurred_at "
                    "from contribution_policy_transition_custody c "
                    "where v.id=:version and c.operation_id="
                    "v.last_transition_operation_id"
                ),
                {"version": published.contribution_policy_version_id},
            )


@pytest.mark.asyncio
async def test_database_rejects_forged_publication_attribution(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, _, published = await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "update contribution_policy_versions set published_by=:actor where id=:version"
                ),
                {"actor": uuid4(), "version": published.contribution_policy_version_id},
            )


@pytest.mark.asyncio
async def test_database_rejects_forged_retirement_attribution(
    policy_database_env: str,
) -> None:
    del policy_database_env
    project_id, created, _, published = await _exercise_policy()
    async with db_session.get_session_factory()() as session, session.begin():
        service = ContributionPolicyService(
            session,
            read_authorization=AllowAuthorization(created.actor_profile_id),
            mutation_authorization=AllowAuthorization(created.actor_profile_id),
            projects=project_contribution_policy_eligibility_port(session),
            bindings=policy_adapter_binding_port(session),
        )
        await service.retire(
            ContributionPolicyRetireRequest(
                operation_id=uuid4(),
                actor_profile_id=created.actor_profile_id,
                project_id=project_id,
                contribution_policy_id=created.contribution_policy_id,
                contribution_policy_version_id=published.contribution_policy_version_id,
            )
        )
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text("update contribution_policy_versions set retired_by=:actor where id=:version"),
                {"actor": uuid4(), "version": published.contribution_policy_version_id},
            )


@pytest.mark.asyncio
async def test_database_rejects_stale_replacement_identity(
    policy_database_env: str,
) -> None:
    del policy_database_env
    project_id, created, _, published = await _exercise_policy()
    operation_id = uuid4()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "insert into contribution_policy_transition_custody "
                    "(operation_id,request_digest,event_type,actor_profile_id,project_id,"
                    "contribution_policy_id,contribution_policy_version_id,"
                    "prior_current_version_id) values "
                    "(:operation_id,:digest,'published',:actor,:project,:policy,:version,"
                    ":stale_prior)"
                ),
                {
                    "operation_id": operation_id,
                    "digest": "sha256:" + "2" * 64,
                    "actor": str(created.actor_profile_id),
                    "project": str(project_id),
                    "policy": created.contribution_policy_id,
                    "version": published.contribution_policy_version_id,
                    "stale_prior": uuid4(),
                },
            )


@pytest.mark.asyncio
async def test_database_rejects_incomplete_publication_graph(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, _, published = await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text(
                    "delete from contribution_rules where contribution_policy_version_id=:version"
                ),
                {"version": published.contribution_policy_version_id},
            )


async def _assert_lifecycle_history_is_immutable(
    policy_database_env: str,
    statement: str,
) -> None:
    del policy_database_env
    await _exercise_policy()
    with pytest.raises(DBAPIError):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(text(statement))


@pytest.mark.asyncio
async def test_database_rejects_lifecycle_update(policy_database_env: str) -> None:
    await _assert_lifecycle_history_is_immutable(
        policy_database_env,
        "update contribution_policy_lifecycle_events set request_digest='sha256:' || "
        "repeat('9',64)",
    )


@pytest.mark.asyncio
async def test_database_rejects_lifecycle_delete(policy_database_env: str) -> None:
    await _assert_lifecycle_history_is_immutable(
        policy_database_env, "delete from contribution_policy_lifecycle_events"
    )


@pytest.mark.asyncio
async def test_database_rejects_lifecycle_truncate(policy_database_env: str) -> None:
    await _assert_lifecycle_history_is_immutable(
        policy_database_env, "truncate contribution_policy_lifecycle_events"
    )
