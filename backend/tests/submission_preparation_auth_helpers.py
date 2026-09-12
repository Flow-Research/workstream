"""Focused PostgreSQL setup helpers for submission-preparation AUTH proof."""

import json
from uuid import uuid4

from sqlalchemy import text

from app.modules.artifacts.authorization import PreparedSubmissionBundlePreparationAuthorization
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)


async def install_submitter_grant(connection, params) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession
    from project_create_fixtures import ensure_fixture_bootstrap

    async with AsyncSession(bind=connection, expire_on_commit=False) as session:
        bootstrap = await ensure_fixture_bootstrap(session)
        authorizer_id, admin_grant_id = bootstrap.target_actor_profile_id, bootstrap.id
    qualification_id, project_grant_id = uuid4(), uuid4()
    await connection.execute(
        text(
            "insert into project_role_qualification_snapshots "
            "(id,project_id,actor_profile_id,requested_role,skills_snapshot,"
            "reputation_snapshot,prior_project_work_refs,external_expertise_refs,"
            "captured_by_actor_profile_id,captured_by_admin_role_grant_id) values "
            "(:qualification,:project,:actor,'submitter',cast(:skills as json),"
            "cast(:reputation as json),"
            "'[]'::json,'[]'::json,:authorizer,:admin_grant)"
        ),
        {
            **params,
            "authorizer": authorizer_id,
            "qualification": qualification_id,
            "admin_grant": admin_grant_id,
            "skills": json.dumps(
                {
                    "availability": "available",
                    "reference_ids": ["skill:test"],
                    "unavailable_reason": None,
                }
            ),
            "reputation": json.dumps(
                {
                    "availability": "unavailable",
                    "reference_ids": [],
                    "unavailable_reason": "no_record",
                }
            ),
        },
    )
    await connection.execute(
        text(
            "insert into project_role_grants "
            "(id,project_id,actor_profile_id,role,status,version,grant_method,"
            "qualification_snapshot_id,granted_by_actor_profile_id,"
            "granted_by_admin_role_grant_id,grant_reason) values "
            "(:project_grant,:project,:actor,'submitter','active',1,'manual',"
            ":qualification,:authorizer,:admin_grant,'submission preparation test')"
        ),
        {
            **params,
            "authorizer": authorizer_id,
            "project_grant": project_grant_id,
            "qualification": qualification_id,
            "admin_grant": admin_grant_id,
        },
    )


async def table_counts(connection, tables) -> dict[str, int]:
    return {
        table: int(await connection.scalar(text(f"select count(*) from {table}")) or 0)
        for table in tables
    }


async def prepared_submitter_authority(session, request, actor_id, identity_link_id, project_id):
    authority = PreparedSubmissionBundlePreparationAuthorization(
        session,
        HumanAuthorizationContext(
            actor_profile_id=actor_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=identity_link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
        ),
    )
    await authority.revalidate(request=request, project_id=project_id)
    return authority
