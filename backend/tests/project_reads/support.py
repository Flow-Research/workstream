"""Project Manager, Finance and other-role callers on the shared task harness."""

from app.db import session as db_session
from tests.contributor_reads.support import OWNER, get_ok, status_of, submitted_case
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.test_tasks import actor_id, auth_headers, set_dev_actor

# task_client grants MANAGER a system Project Manager role.
MANAGER = "project-manager-subject"
EXACT_MANAGER, FINANCE, OPERATOR, AUDITOR = (
    "exact-project-manager", "finance-authority-subject", "operator-subject", "audit-authority-subject",
)
PROJECTS = "/api/v1/projects"

__all__ = (
    "AUDITOR", "EXACT_MANAGER", "FINANCE", "MANAGER", "OPERATOR", "OWNER",
    "as_admin", "as_manager", "get_ok", "project_path", "status_of", "submitted_case",
)


def project_path(project, suffix=""):
    """The public path of one project-wide read."""
    return f"{PROJECTS}/{project}{suffix}"


async def as_admin(client, monkeypatch, subject, role, *, project=None):
    """Admit ``subject`` and give it one stored admin grant, exact-project unless ``project`` is None."""
    set_dev_actor(monkeypatch, roles="", subject=subject)
    admitted = await client.get("/api/v1/actors/me", headers=auth_headers())
    assert admitted.status_code == 200, admitted.text
    async with db_session.get_session_factory()() as session, session.begin():
        await grant_fixture_admin_role(
            session, await actor_id(subject), role=role,
            scope="system" if project is None else "project", project_id=project,
        )
    return admitted.json()["actor_profile_id"]


def as_manager(monkeypatch, subject=MANAGER):
    """Switch back to an already granted manager; token roles grant nothing."""
    set_dev_actor(monkeypatch, roles="", subject=subject)
