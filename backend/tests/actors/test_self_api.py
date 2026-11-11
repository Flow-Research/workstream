# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations


from httpx import AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db import session as db_session
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
)
from app.modules.actors.service import (
    ActorService,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import ActionId
from app.modules.tasks.models import AuditEvent

from tests.actors.support import set_dev_actor, auth_headers


async def test_actors_me_returns_contributor_without_token_role_authority(
    actor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_dev_actor(
        monkeypatch,
        roles="admin,project_manager,worker,reviewer",
        subject="role-heavy-human",
    )
    response = await actor_client.get("/api/v1/actors/me", headers=auth_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actor_kind"] == "human"
    assert body["domains"] == ["contributor"]
    assert body["admin_roles"] == []
    assert body["project_role_grants"] == []
    assert "issuer" not in body and "subject" not in body and "roles" not in body


async def test_patch_actors_me_updates_only_display_fields(
    actor_client: AsyncClient,
) -> None:
    """Prove self updates edit display name while preserving issuer-owned email."""
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert created.status_code == 200
    actor_id = created.json()["actor_profile_id"]
    preserved_columns = [
        column.name
        for column in ActorProfile.__table__.columns
        if column.name not in {"display_name", "updated_at", "last_seen_at"}
    ]
    async with db_session.get_session_factory()() as session:
        before = await session.get(ActorProfile, actor_id)
        before_fields = {name: getattr(before, name) for name in preserved_columns}
    response = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json={"display_name": "Contributor One"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Contributor One"
    assert response.json()["contact_email"] == created.json()["contact_email"]
    async with db_session.get_session_factory()() as session:
        after = await session.get(ActorProfile, actor_id)
        assert after.display_name == "Contributor One"
        assert after.contact_email == created.json()["contact_email"]
        assert {name: getattr(after, name) for name in preserved_columns} == before_fields


@pytest.mark.parametrize("body", [{"status": "active"}, {}, {"contact_email": "other@example.test"}, {"contact_email": None}, {"display_name": "Blocked", "contact_email": "other@example.test"}])
async def test_patch_actors_me_rejects_invalid_field_sets(actor_client, body):
    response = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json=body,
    )
    assert response.status_code == 422


async def test_patch_actors_me_maps_database_failure_to_retryable_unavailable(
    actor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert created.status_code == 200
    actor_id = created.json()["actor_profile_id"]
    async with db_session.get_session_factory()() as session:
        timestamps_before = (
            await session.execute(
                select(ActorProfile.last_seen_at, ActorIdentityLink.last_verified_at)
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(ActorProfile.id == actor_id)
            )
        ).one()

    reached_staged_failure = False

    async def fail_update(self, resolved, payload):
        nonlocal reached_staged_failure
        assert resolved.profile.last_seen_at > timestamps_before[0]
        assert resolved.identity_link.last_verified_at > timestamps_before[1]
        assert (
            await self._session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action_id == ActionId.ACTOR_PROFILE_UPDATE_SELF.value)
            )
            == 1
        )
        reached_staged_failure = True
        raise SQLAlchemyError("injected database failure")

    monkeypatch.setattr(ActorService, "update_self", fail_update)
    response = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json={"display_name": "Not persisted"},
    )

    assert reached_staged_failure
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert response.json()["error"]["retryable"] is True
    async with db_session.get_session_factory()() as session:
        update_evidence = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action_id == ActionId.ACTOR_PROFILE_UPDATE_SELF.value)
        )
        timestamps_after = (
            await session.execute(
                select(ActorProfile.last_seen_at, ActorIdentityLink.last_verified_at)
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(ActorProfile.id == actor_id)
            )
        ).one()
    assert update_evidence == 0
    assert timestamps_after == timestamps_before


async def test_actor_self_evidence_failure_is_retryable_before_touch(
    actor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert created.status_code == 200
    actor_id = created.json()["actor_profile_id"]
    async with db_session.get_session_factory()() as session:
        timestamps_before = (
            await session.execute(
                select(ActorProfile.last_seen_at, ActorIdentityLink.last_verified_at)
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(ActorProfile.id == actor_id)
            )
        ).one()

    touch_calls = []
    original_touch = ActorService.touch_after_authorization

    async def observe_touch(self, resolved):
        touch_calls.append(resolved.profile.id)
        return await original_touch(self, resolved)

    async def fail_evidence(*_args, **_kwargs):
        raise SQLAlchemyError("injected evidence failure")

    monkeypatch.setattr(ActorService, "touch_after_authorization", observe_touch)
    monkeypatch.setattr(AuditService, "add_authority_event", fail_evidence)
    response = await actor_client.get("/api/v1/actors/me", headers=auth_headers())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert response.json()["error"]["retryable"] is True
    assert touch_calls == []
    async with db_session.get_session_factory()() as session:
        timestamps_after = (
            await session.execute(
                select(ActorProfile.last_seen_at, ActorIdentityLink.last_verified_at)
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(ActorProfile.id == actor_id)
            )
        ).one()
    assert timestamps_after == timestamps_before


async def test_missing_bearer_has_no_actor_self_decision_evidence(
    actor_client: AsyncClient,
) -> None:
    response = await actor_client.get("/api/v1/actors/me")
    assert response.status_code == 401
    async with db_session.get_session_factory()() as session:
        decisions = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "authorization_decision")
        )
    assert decisions == 0
