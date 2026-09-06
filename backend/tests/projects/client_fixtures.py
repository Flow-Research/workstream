"""PROJECT-owned API client, settings isolation and authority prerequisites."""

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl


@pytest.fixture
def project_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "project-token")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "project-manager-subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "flow-test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "project_manager")
    monkeypatch.setenv("WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART", "false")
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://")
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()



@pytest.fixture(autouse=True)
def clear_project_settings_cache_after_test() -> Iterator[None]:
    """Prevent test-local environment overrides from surviving in Settings."""
    try:
        yield
    finally:
        get_settings.cache_clear()



@pytest.fixture
async def project_client(project_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        admission = await client.get("/api/v1/auth/me", headers=auth_headers())
        assert admission.status_code == 200, admission.text
        actor_id, _link_id, grantor_id = await ensure_access_administrator_bootstrap()
        async with db_session.get_session_factory()() as session:
            link = await session.scalar(
                select(ActorIdentityLink).where(
                    ActorIdentityLink.issuer == "flow-test",
                    ActorIdentityLink.subject == "project-manager-subject",
                )
            )
            assert link is not None
            session.add(
                AdminRoleGrant(
                    id=uuid4(),
                    target_actor_profile_id=link.actor_profile_id,
                    role="project_manager",
                    scope_type="system",
                    scope_project_id=None,
                    status="active",
                    version=1,
                    granted_by_actor_profile_id=actor_id,
                    granted_by_admin_role_grant_id=grantor_id,
                    grant_reason="Project test system-scoped manager authority",
                )
            )
            setup_profile_id = str(uuid4())
            session.add(
                ActorProfile(
                    id=setup_profile_id,
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=ServiceIdentity.PROJECT_SETUP.value,
                    created_by=str(actor_id),
                )
            )
            session.add(
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=setup_profile_id,
                    issuer="flow-test",
                    subject="workstream-project-setup-test-service",
                    subject_kind="service",
                    status="active",
                    linked_by=str(actor_id),
                )
            )
            await session.commit()
        yield client



def auth_headers(token: str = "project-token") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": str(uuid4()),
    }



async def ensure_access_administrator_bootstrap() -> tuple[UUID, UUID, UUID]:
    """Return the default actor and its idempotent bootstrap grant."""
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == "flow-test",
                ActorIdentityLink.subject == "project-manager-subject",
            )
        )
        assert link is not None
        grant = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.target_actor_profile_id == link.actor_profile_id,
                AdminRoleGrant.role == "access_administrator",
                AdminRoleGrant.status == "active",
            )
        )
        if grant is None:
            grant = AdminRoleGrant(
                id=uuid4(),
                target_actor_profile_id=link.actor_profile_id,
                role="access_administrator",
                scope_type="system",
                scope_project_id=None,
                status="active",
                version=1,
                granted_by_system_principal="workstream:system:bootstrap",
                grant_reason="AUTH route fixture",
            )
            session.add(grant)
            control = await session.get(AuthorityControl, 1)
            assert control is not None
            control.bootstrap_completed = True
            control.bootstrap_grant_id = grant.id
            control.version = 1
            await session.commit()
        return link.actor_profile_id, link.id, grant.id
