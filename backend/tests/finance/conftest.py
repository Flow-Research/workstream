"""Reuse real signed authority fixtures for explicitly named integration tests."""

from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access,
    admin_access as admin_access,
)
from tests.reviews.lifecycle.fixtures import live_acceptance_lifecycle as live_acceptance_lifecycle


import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from tests.authentication.support import issue_asymmetric_token
from tests.tasks.post_submit_routing.outcome_support import authorized_routing_source, apply_outcome


@pytest.fixture
async def fulfillment_api_source(tmp_path, isolated_database_env, live_acceptance_lifecycle):
    """Real public Flow service provisioning and an owner-earned paid root."""
    access = live_acceptance_lifecycle
    subject = f"fulfillment-{new_record_id()}"
    provisioned = await access.signed.client.post("/api/v1/service-actors",
        headers=access.admin.headers | {"Idempotency-Key": str(new_record_id())},
        json={"service_identity": ServiceIdentity.COMPENSATION_ADAPTER.value,
              "subject": subject, "reason": "Verify original-bound fulfillment evidence"})
    assert provisioned.status_code == 201, provisioned.text
    token = issue_asymmetric_token(access.signed.private_key, subject_kind="service",
        scope="workstream:service", claims={"sub": subject, "jti": str(new_record_id())})
    async with authorized_routing_source(tmp_path, isolated_database_env,
                                         contribution_awards=("money",)) as source:
        async with source.factory() as session, session.begin():
            result = await apply_outcome(session, source, 2)
            assert result.economic is not None
        async with source.factory() as session:
            source.obligation = await session.scalar(text(
                "SELECT obligation_body FROM public.compensation_fulfillment_roots"))
            assert source.obligation is not None
        source.client = access.signed.client
        source.headers = {"Authorization": f"Bearer {token}"}
        source.access = access
        yield source
