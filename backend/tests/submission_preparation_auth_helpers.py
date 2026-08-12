"""Focused PostgreSQL setup helpers for submission-preparation AUTH proof."""

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
    admin_grant_id, qualification_id, project_grant_id = uuid4(), uuid4(), uuid4()
    await connection.execute(
        text(
            "insert into admin_role_grants "
            "(id,target_actor_profile_id,role,scope_type,scope_project_id,status,version,"
            "granted_by_system_principal,grant_reason) values "
            "(:admin_grant,:actor,'project_manager','project',:project,'active',1,"
            "'test','submission preparation test')"
        ),
        {**params, "admin_grant": admin_grant_id},
    )
    await connection.execute(
        text(
            "insert into project_role_qualification_snapshots "
            "(id,project_id,actor_profile_id,requested_role,skills_snapshot,"
            "reputation_snapshot,prior_project_work_refs,external_expertise_refs,"
            "captured_by_actor_profile_id,captured_by_admin_role_grant_id) values "
            "(:qualification,:project,:actor,'submitter','{}'::json,'{}'::json,"
            "'[]'::json,'[]'::json,:actor,:admin_grant)"
        ),
        {**params, "qualification": qualification_id, "admin_grant": admin_grant_id},
    )
    await connection.execute(
        text(
            "insert into project_role_grants "
            "(id,project_id,actor_profile_id,role,status,version,grant_method,"
            "qualification_snapshot_id,granted_by_actor_profile_id,"
            "granted_by_admin_role_grant_id,grant_reason) values "
            "(:project_grant,:project,:actor,'submitter','active',1,'manual',"
            ":qualification,:actor,:admin_grant,'submission preparation test')"
        ),
        {
            **params,
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
