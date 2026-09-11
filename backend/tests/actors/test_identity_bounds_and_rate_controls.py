# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations


from httpx import AsyncClient
from pydantic import ValidationError
import pytest
from sqlalchemy import func, select

from app.api.deps.rate_controls import get_rate_control_service
from app.db import session as db_session
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
)
from app.modules.api_controls.service import RateControlDecision, RateControlUnavailableError
from app.modules.tasks.models import AuditEvent
from app.schemas.auth import (
    VerifiedIssuerToken,
)

from tests.actors.support import set_dev_actor, auth_headers, verified_token


async def test_actor_api_accepts_verifier_identity_bounds(
    actor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issuer = ("https://identity.test/" + "i" * 200)[:200]
    subject = "s" * 200
    set_dev_actor(monkeypatch, roles="worker", subject=subject, issuer=issuer)

    response = await actor_client.get("/api/v1/actors/me", headers=auth_headers())

    assert response.status_code == 200, response.text
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == issuer,
                ActorIdentityLink.subject == subject,
            )
        )
        assert link is not None


async def test_identity_bounds_preserve_private_canonical_provisioning_evidence(actor_client, monkeypatch):
    issuer = ("https://identity.test/" + "i" * 200)[:200]
    subject = "s" * 200
    set_dev_actor(monkeypatch, roles="worker", subject=subject, issuer=issuer)
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert created.status_code == 200
    async with db_session.get_session_factory()() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "ActorProfileProvisioned",
                AuditEvent.actor_id == created.json()["actor_profile_id"],
            )
        )
        assert event is not None
        assert event.external_issuer is None
        assert event.external_subject is None
        assert event.actor_roles == []
        assert event.claim_snapshot == {}


@pytest.mark.parametrize("field", ["issuer", "subject"])
def test_verified_identity_rejects_values_above_persisted_provenance_bound(field):
    values = verified_token("subject").model_dump()
    values[field] = "s" * 201
    with pytest.raises(ValidationError) as observed:
        VerifiedIssuerToken(**values)
    assert observed.value.errors()[0]["loc"] == (field,)


async def test_first_access_rate_limit_denies_without_actor_write(
    actor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeniedRateControl:
        async def consume(self, **_kwargs):
            return RateControlDecision(allowed=False, request_count=2, retry_after=30)

    actor_client._transport.app.dependency_overrides[get_rate_control_service] = (  # type: ignore[attr-defined]
        lambda: DeniedRateControl()
    )
    set_dev_actor(monkeypatch, roles="worker", subject="rate-denied-human")
    response = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 0


async def test_first_access_rate_control_unavailable_fails_closed(
    actor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableRateControl:
        async def consume(self, **_kwargs):
            raise RateControlUnavailableError("unavailable")

    actor_client._transport.app.dependency_overrides[get_rate_control_service] = (  # type: ignore[attr-defined]
        lambda: UnavailableRateControl()
    )
    set_dev_actor(monkeypatch, roles="worker", subject="rate-unavailable-human")
    response = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type.in_(["ActorProfileProvisioned", "ActorIdentityLinked"])
                )
            )
            == 0
        )
