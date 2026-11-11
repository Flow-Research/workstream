"""Issuer-owned email, local display names and exact identity synchronization."""
import asyncio
from typing import Any
from cryptography.hazmat.primitives.asymmetric import rsa
from app.modules.tasks.models import AuditEvent
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from app.adapters.auth.flow import FlowAuthVerifier
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.main import create_app
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.actors.service import ActorService
from auth_concurrency_support import wait_for_named_database_lock
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authentication.support import (
    issue_asymmetric_token, production_verifier_settings, jwks_transport,
)


def _profile_app(database_url, signing_material):
    """Build the app with an explicit token verifier for isolated profile tests."""
    private_key, jwk = signing_material
    settings = production_verifier_settings(database_url=database_url)
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    return private_key, settings, app


async def test_issuer_email_sync_preserves_identity_and_local_name(
    auth_database_env, rsa_signing_material,
):
    """Signed email follows issuer time; display edits and exact subjects remain local."""
    import time
    private_key, settings, app = _profile_app(auth_database_env, rsa_signing_material)
    issued = int(time.time()) - 20

    def headers(email, tick, *, subject="email-owner", name="Issuer Name"):
        """Supply the selected signed email observation through the test verifier."""
        value = issue_asymmetric_token(private_key, claims={
            "sub": subject, "email": email, "name": name, "iat": tick,
        })
        return {"Authorization": f"Bearer {value}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        first = await client.get("/api/v1/actors/me", headers=headers("first@example.test", issued))
        assert first.status_code == 200, first.text
        actor_id = first.json()["actor_profile_id"]
        assert first.json()["contact_email"] == "first@example.test"
        assert first.json()["display_name"] == "Issuer Name"
        for display_name in ("My chosen name", None):
            edited = await client.patch("/api/v1/actors/me",
                headers=headers("second@example.test", issued + 2),
                json={"display_name": display_name})
            assert edited.status_code == 200, edited.text
            assert edited.json()["contact_email"] == "second@example.test"
            for email, tick in (("first@example.test", issued), ("equal@example.test", issued + 2), (None, issued + 10)):
                read = await client.get("/api/v1/actors/me", headers=headers(email, tick, name="Changed issuer name"))
                assert read.status_code == 200, read.text
                assert read.json()["contact_email"] == "second@example.test"
                assert read.json()["display_name"] == display_name
                assert read.json()["actor_profile_id"] == actor_id
        changed = await client.get("/api/v1/actors/me", headers=headers("third@example.test", issued + 3))
        assert changed.json()["contact_email"] == "third@example.test"
        assert changed.json()["actor_profile_id"] == actor_id
        for body in ({"contact_email": "forged@example.test"}, {"contact_email": None},
                     {"display_name": "Must not persist", "contact_email": "forged@example.test"}):
            denied = await client.patch("/api/v1/actors/me", headers=headers("third@example.test", issued + 3), json=body)
            assert denied.status_code == 422, denied.text
        other = await client.get("/api/v1/actors/me", headers=headers("third@example.test", issued + 4, subject="other-owner"))
        assert other.status_code == 200, other.text
        assert other.json()["actor_profile_id"] != actor_id
        retained = await client.get("/api/v1/actors/me", headers=headers("third@example.test", issued + 3))
        assert retained.json()["display_name"] is None
        assert retained.json()["admin_roles"] == first.json()["admin_roles"] == []
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == actor_id))
        assert link.subject == "email-owner"
        assert link.email_observed_issued_at == issued + 3


@pytest.mark.parametrize("blocked", ["suspended", "revoked", "rollback"])
async def test_issuer_email_sync_does_not_survive_denial_or_failed_update(
    auth_database_env, rsa_signing_material, monkeypatch, blocked,
):
    """Prove denied access and failed writes cannot commit signed-email observations."""
    import time
    private_key, settings, app = _profile_app(auth_database_env, rsa_signing_material)
    issued = int(time.time()) - 20
    def headers(email, tick):
        """Supply the selected signed email observation through the test verifier."""
        return {"Authorization": "Bearer " + issue_asymmetric_token(private_key,
            claims={"sub": "blocked-email", "email": email, "iat": tick})}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        first = await client.get("/api/v1/actors/me", headers=headers("before@example.test", issued))
        assert first.status_code == 200, first.text
        actor_id = first.json()["actor_profile_id"]
        async with db_session.get_session_factory()() as session:
            profile = await session.get(ActorProfile, actor_id)
            link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == actor_id))
            if blocked == "suspended":
                profile.status = "suspended"
                profile.suspended_by = actor_id
                profile.suspended_at = func.now()
                profile.suspension_reason = "Test suspension"
            elif blocked == "revoked":
                link.status = "revoked"
                link.revoked_by = actor_id
                link.revoked_at = func.now()
                link.revoked_reason = "Test revocation"
            await session.commit()
        if blocked == "rollback":
            async def fail_update(self, resolved, payload):
                """Fail after synchronization to prove caller rollback removes the staged observation."""
                assert resolved.profile.contact_email == "after@example.test"
                await self._session.flush()
                raise SQLAlchemyError("injected failure after issuer synchronization")
            monkeypatch.setattr(ActorService, "update_self", fail_update)
        response = await client.patch("/api/v1/actors/me", headers=headers("after@example.test", issued + 1),
                                      json={"display_name": "Not committed"})
        assert response.status_code == (503 if blocked == "rollback" else 403), response.text
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, actor_id)
        link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == actor_id))
        assert profile.contact_email == "before@example.test"
        assert profile.display_name == first.json()["display_name"]
        assert link.email_observed_issued_at == issued


async def test_issuer_email_sync_serializes_against_stale_profile_edit(
    auth_database_env, rsa_signing_material,
):
    """An independent stale session waits, then preserves newer issuer email and local clear."""
    import time
    from app.modules.actors.schemas import ActorProfileUpdateRequest
    private_key, settings, app = _profile_app(auth_database_env, rsa_signing_material)
    issued = int(time.time()) - 20
    async def verified(email, tick):
        """Build one bounded identity observation for the concurrent refresh proof."""
        return (await app.state.auth_verifier.verify(issue_asymmetric_token(private_key,
            claims={"sub": "racing-email", "email": email, "iat": tick}))).token
    older = await verified("old@example.test", issued)
    newer = await verified("new@example.test", issued + 1)
    async with db_session.get_session_factory()() as initial:
        admitted = await ActorService(initial).resolve_verified_actor(
            older, request_id=new_record_id(), correlation_id=new_record_id())
        actor_id = admitted.profile.id
    async with db_session.get_session_factory()() as first, db_session.get_session_factory()() as second:
        one, two = ActorService(first), ActorService(second)
        # Load both before either changes the row, exercising stale ORM state as well.
        first_actor = await one.find_actor_for_authorization(newer)
        stale_actor = await two.find_actor_for_authorization(older)
        assert first_actor is not None and stale_actor is not None
        await one.synchronize_identity_email(first_actor, newer)
        waiter_name = "profile-email-waiter"
        await second.execute(text("select set_config('application_name', :name, true)"), {"name": waiter_name})
        async def old_token_patch():
            """Apply a local name edit with an older token while another refresh holds custody."""
            refreshed = await two.synchronize_identity_email(stale_actor, older)
            await two.update_self(refreshed, ActorProfileUpdateRequest(display_name=None))
            await second.commit()
        contender = asyncio.create_task(old_token_patch())
        try:
            await asyncio.wait_for(wait_for_named_database_lock(auth_database_env, waiter_name), timeout=10)
            assert not contender.done()
            await first.commit()
            await asyncio.wait_for(contender, timeout=10)
        finally:
            if not contender.done():
                contender.cancel()
            await asyncio.gather(contender, return_exceptions=True)
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, actor_id)
        link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == actor_id))
        assert profile.contact_email == "new@example.test"
        assert profile.display_name is None
        assert link.email_observed_issued_at == issued + 1


async def test_signed_flow_token_authorizes_actor_self_read_and_update(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    """Exercise real signed self access while keeping identity metadata out of audit evidence."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    app = create_app(settings)
    app.state.auth_verifier = verifier
    token = issue_asymmetric_token(
        private_key,
        claims={
            "sub": "signed-self-actor",
            "jti": "signed-self-token", "email": "signed@example.test",
            "roles": ["admin", "project_manager", "reviewer"],
        },
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        read = await client.get(
            "/api/v1/actors/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        updated = await client.patch(
            "/api/v1/actors/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"display_name": "Signed Contributor"},
        )

    assert read.status_code == 200, read.text
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "Signed Contributor"
    assert updated.json()["contact_email"] == "signed@example.test"
    assert updated.json()["admin_roles"] == []
    assert updated.json()["project_role_grants"] == []
    async with db_session.get_session_factory()() as session:
        events = (
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "authorization_decision")
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
        ).all()
    assert [(event.action_id, event.permission_id, event.after_facts) for event in events] == [
        ("actor.profile.read_self", "actor.profile.read_self", {"allowed": True}),
        ("actor.profile.update_self", "actor.profile.update_self", {"allowed": True}),
    ]
    serialized = repr([event.event_payload for event in events])
    assert "signed@example.test" not in serialized
    assert token not in serialized


