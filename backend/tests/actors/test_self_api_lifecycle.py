# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

import asyncio
from app.core.identifiers import new_record_id

from httpx import AsyncClient
import pytest
from sqlalchemy import func, select, text

from app.api.deps.auth import get_auth_verification_result
from app.db import session as db_session
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
)
from app.modules.actors.service import (
    ActorService,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.tasks.models import AuditEvent
from app.schemas.auth import (
    AuthVerificationResult,
)

from tests.actors.support import auth_headers, verified_token
from auth_concurrency_support import wait_for_named_database_lock


@pytest.fixture
async def suspended_actor(actor_client):
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert created.status_code == 200
    actor_profile_id = created.json()["actor_profile_id"]
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, actor_profile_id)
        profile.status = "suspended"
        profile.suspended_by = actor_profile_id
        profile.suspended_at = func.now()
        profile.suspension_reason = "security response"
        await session.commit()
    return actor_profile_id


async def test_suspended_profile_is_not_readable(actor_client, suspended_actor):
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, suspended_actor)
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == suspended_actor,
        ))
        before = (profile.last_seen_at, link.last_verified_at)
    read = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert read.status_code == 403
    assert read.json()["error"]["code"] == "actor_suspended"
    assert "actor_profile_id" not in read.json()
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, suspended_actor)
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == suspended_actor,
        ))
        assert (profile.last_seen_at, link.last_verified_at) == before
        assert profile.status == "suspended"
        denial = await session.scalar(select(AuditEvent).where(
            AuditEvent.action_id == ActionId.ACTOR_PROFILE_READ_SELF.value,
            AuditEvent.denial_code == "actor_suspended",
        ))
        assert denial is not None and denial.resource_id == suspended_actor


async def test_suspended_profile_is_not_mutable(actor_client, suspended_actor):
    response = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json={"display_name": "Blocked"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "actor_suspended"
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, suspended_actor)
        assert profile.display_name is None
        denial = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action_id == ActionId.ACTOR_PROFILE_UPDATE_SELF.value,
                AuditEvent.denial_code == "actor_suspended",
            )
        )
    assert denial is not None
    assert denial.resource_id == suspended_actor


async def test_revoked_identity_link_is_denied_by_actor_api(
    actor_client: AsyncClient,
) -> None:
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert created.status_code == 200
    actor_profile_id = created.json()["actor_profile_id"]
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == actor_profile_id)
        )
        assert link is not None
        verified_at = link.last_verified_at
        link.status = "revoked"
        link.revoked_by = actor_profile_id
        link.revoked_at = func.now()
        link.revoked_reason = "security response"
        await session.commit()

    denied = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "identity_link_revoked"
    async with db_session.get_session_factory()() as session:
        persisted_link = await session.scalar(
            select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == actor_profile_id)
        )
        assert persisted_link.last_verified_at == verified_at
        denial = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action_id == ActionId.ACTOR_PROFILE_READ_SELF.value,
                AuditEvent.denial_code == "identity_link_revoked",
            )
        )
    assert denial is not None


async def test_deactivated_actor_is_denied_by_actor_self_api(
    actor_client: AsyncClient,
) -> None:
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert created.status_code == 200
    actor_profile_id = created.json()["actor_profile_id"]
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, actor_profile_id)
        assert profile is not None
        seen_at = profile.last_seen_at
        profile.status = "deactivated"
        profile.deactivated_by = actor_profile_id
        profile.deactivated_at = func.now()
        profile.deactivation_reason = "operator decision"
        await session.commit()

    denied = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "actor_deactivated"
    async with db_session.get_session_factory()() as session:
        persisted_profile = await session.get(ActorProfile, actor_profile_id)
        assert persisted_profile.last_seen_at == seen_at
        denial = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action_id == ActionId.ACTOR_PROFILE_READ_SELF.value,
                AuditEvent.denial_code == "actor_deactivated",
            )
        )
    assert denial is not None


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        ("service", "service_actor_not_provisioned"),
        ("agent", "unsupported_subject_kind"),
        ("space", "unsupported_subject_kind"),
    ],
)
async def test_nonhuman_actor_self_api_denials_create_nothing(
    actor_client: AsyncClient,
    kind: str,
    expected_code: str,
) -> None:
    async def verification_override() -> AuthVerificationResult:
        return AuthVerificationResult(
            token=verified_token(f"http-{kind}", kind=kind),
        )

    actor_client._transport.app.dependency_overrides[get_auth_verification_result] = (  # type: ignore[attr-defined]
        verification_override
    )
    response = await actor_client.get("/api/v1/actors/me", headers=auth_headers())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == expected_code
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.entity_type == "authorization_decision")
            )
            == 0
        )


async def test_revocation_wins_synchronized_actor_update_recheck(
    actor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    actor_database_env: str,
) -> None:
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    actor_profile_id = created.json()["actor_profile_id"]
    lock_attempted = asyncio.Event()
    waiter_name = f"actor-revocation-{new_record_id().hex}"
    waiter_pids, hook_failures = [], []
    original_lock = ActorService.lock_actor_self_for_authorization

    async def observed_lock(self, resolved):
        try:
            waiter_pids.append(await self._session.scalar(text("select pg_backend_pid()")))
            await self._session.execute(
                text("select set_config('application_name', :name, true)"), {"name": waiter_name}
            )
            lock_attempted.set()
            return await original_lock(self, resolved)
        except Exception as exc:
            hook_failures.append(exc)
            raise
        finally:
            lock_attempted.set()

    monkeypatch.setattr(ActorService, "lock_actor_self_for_authorization", observed_lock)
    async with db_session.get_session_factory()() as revoker:
        link = await revoker.scalar(
            select(ActorIdentityLink)
            .where(ActorIdentityLink.actor_profile_id == actor_profile_id)
            .with_for_update()
        )
        assert link is not None
        blocker_pid = await revoker.scalar(text("select pg_backend_pid()"))
        link.status = "revoked"
        link.revoked_by = actor_profile_id
        link.revoked_at = func.now()
        link.revoked_reason = "security response"
        patch_task = asyncio.create_task(
            actor_client.patch(
                "/api/v1/actors/me",
                headers=auth_headers(),
                json={"display_name": "Must Not Persist"},
            )
        )
        try:
            await asyncio.wait_for(lock_attempted.wait(), timeout=5)
            if hook_failures:
                raise AssertionError("actor lock observation hook failed") from hook_failures[0]
            assert waiter_pids[0] != blocker_pid
            await asyncio.wait_for(
                wait_for_named_database_lock(
                    actor_database_env,
                    waiter_name,
                    expected_waiter_pid=waiter_pids[0],
                    expected_blocker_pid=blocker_pid,
                ),
                timeout=5,
            )
            assert not patch_task.done()
            await revoker.commit()
            denied = await asyncio.wait_for(patch_task, timeout=5)
        except Exception:
            if hook_failures:
                raise AssertionError("actor lock observation hook failed") from hook_failures[0]
            raise
        finally:
            if not patch_task.done():
                patch_task.cancel()
            await asyncio.gather(patch_task, return_exceptions=True)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "identity_link_revoked"
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, actor_profile_id)
        denial = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action_id == ActionId.ACTOR_PROFILE_UPDATE_SELF.value,
                AuditEvent.denial_code == "identity_link_revoked",
            )
        )
    assert profile is not None and profile.display_name is None
    assert denial is not None and denial.after_facts == {"allowed": False}
