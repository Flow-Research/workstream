"""Valid signed API setup; tests own each mutation and its assertions."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
import pytest

from app.adapters.auth.flow import FlowAuthVerifier
from app.db import session as db_session
from app.main import create_app
from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests.authentication.support import production_verifier_settings, jwks_transport
from tests.authorization.admin_access.support import AdminAccess, SignedAccess


@pytest.fixture
async def signed_access(auth_database_env, rsa_signing_material) -> AsyncIterator[SignedAccess]:
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    assert settings.token_issuer is not None
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield SignedAccess(client, private_key, settings.token_issuer)
    finally:
        await db_session.dispose_engine()


@pytest.fixture
async def admin_access(signed_access: SignedAccess) -> AdminAccess:
    admin = await signed_access.actor("administrator", roles=("viewer",))
    target = await signed_access.actor("target", roles=("admin",))
    code, result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, result
    assert result == {
        "result_code": "bootstrapped",
        "actor_profile_id": str(admin.id),
        "grant_id": result["grant_id"],
        "changed": True,
    }
    return AdminAccess(signed_access, admin, target, result["grant_id"])
