"""Real grants and exact public paths for the three locked-context audiences."""

KINDS = {
    "management": ("", "project.task.locked_context.read", "project_manager", "Management"),
    "operational": ("/operations", "operations.task.locked_context.read", "operator", "Operational"),
    "audit": ("/audit", "audit.task.locked_context.read", "audit_authority", "Audit"),
}


def path(kind, project, task):
    return f"/api/v1{KINDS[kind][0]}/projects/{project}/tasks/{task}/locked-context"


async def grant_for(access, project, kind, *, system=False):
    return await access.signed.grant(
        access.admin, access.target, role=KINDS[kind][2],
        project_id=None if system or kind == "operational" else project,
    )


async def grant_development_context_roles(factory):
    """Give the existing admitted development manager real audience grants."""
    from app.core.identifiers import new_record_id
    from app.modules.authorization.models import AdminRoleGrant
    from tests.project_create_fixtures import grant_system_project_manager
    async with factory() as session, session.begin():
        link, manager = await grant_system_project_manager(session, issuer="flow-test", subject="project-manager-subject")
        for role in ("operator", "audit_authority"):
            session.add(AdminRoleGrant(
                id=new_record_id(), target_actor_profile_id=link.actor_profile_id,
                role=role, scope_type="system", scope_project_id=None, status="active", version=1,
                granted_by_actor_profile_id=manager.granted_by_actor_profile_id,
                granted_by_admin_role_grant_id=manager.granted_by_admin_role_grant_id,
                grant_reason="Historical locked-context public read fixture",
            ))
