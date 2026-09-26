"""Real signed requests and narrow PostgreSQL observations for admin tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db_session
from app.core.identifiers import new_record_id
from app.modules.authorization.models import (
    AdminRoleGrant,
    AuthorityControl,
    AuthorityIdempotencyRecord,
)
from app.modules.tasks.models import AuditEvent
from project_create_fixtures import seed_historical_project
from tests.authentication.support import issue_asymmetric_token


@dataclass(frozen=True)
class SignedActor:
    id: UUID
    subject: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class SignedAccess:
    client: AsyncClient
    private_key: rsa.RSAPrivateKey
    issuer: str

    async def actor(self, label: str, *, roles: tuple[str, ...] = ()) -> SignedActor:
        subject = f"{label}-{uuid4()}"
        token = issue_asymmetric_token(
            self.private_key,
            claims={"sub": subject, "jti": str(uuid4()), "roles": list(roles)},
        )
        response = await self.client.get(
            "/api/v1/actors/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, response.text
        return SignedActor(UUID(response.json()["actor_profile_id"]), subject, token)

    async def issue(
        self, caller: SignedActor, body: dict[str, Any], *, key: str | None = None
    ) -> Response:
        return await self.client.post(
            "/api/v1/admin-role-grants",
            headers=caller.headers | {"Idempotency-Key": key or str(uuid4())},
            json=body,
        )

    async def revoke(
        self,
        caller: SignedActor,
        grant_id: str,
        *,
        key: str | None = None,
        reason: str = "End assigned authority",
    ) -> Response:
        return await self.client.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers=caller.headers | {"Idempotency-Key": key or str(uuid4())},
            json={"reason": reason},
        )

    async def grant(
        self,
        caller: SignedActor,
        target: SignedActor,
        *,
        role: str = "operator",
        project_id: UUID | None = None,
    ) -> str:
        response = await self.issue(caller, grant_body(target.id, role=role, project_id=project_id))
        assert response.status_code == 201, response.text
        return response.json()["resource_id"]


@dataclass(frozen=True)
class AdminAccess:
    signed: SignedAccess
    admin: SignedActor
    target: SignedActor
    bootstrap_grant_id: str


def grant_body(
    actor_id: UUID, *, role: str = "operator", project_id: UUID | None = None
) -> dict[str, Any]:
    return {
        "target_actor_profile_id": str(actor_id),
        "role": role,
        "scope_type": "system" if project_id is None else "project",
        "scope_project_id": None if project_id is None else str(project_id),
        "reason": "Explicit administrator assignment",
    }


async def create_project(label: str) -> UUID:
    project_id = new_record_id()
    async with db_session.get_session_factory()() as session:
        await seed_historical_project(
            session, project_id=str(project_id), name=label, slug=f"admin-{project_id}"
        )
        await session.commit()
    return project_id


@dataclass(frozen=True)
class ActorObservation:
    display_name: str | None
    updated_at: datetime
    last_seen_at: datetime
    last_verified_at: datetime


async def actor_observation(actor_id: UUID) -> ActorObservation:
    async with db_session.get_session_factory()() as session:
        return await observed_actor(session, actor_id)


async def observed_actor(session: AsyncSession, actor_id: UUID) -> ActorObservation:
    """Read this session's visible observations for an already admitted human."""
    row = (
        await session.execute(
            text(
                "select p.display_name,p.updated_at,p.last_seen_at,l.last_verified_at "
                "from actor_profiles p join actor_identity_links l "
                "on l.actor_profile_id=p.id where p.id=:actor"
            ),
            {"actor": str(actor_id)},
        )
    ).one()
    assert all(isinstance(value, datetime) for value in row[1:])
    return ActorObservation(*row)


async def seed_old_observation(actor_id: UUID) -> ActorObservation:
    async with db_session.get_session_factory()() as session:
        parameters = {"actor": str(actor_id), "old": datetime(2000, 1, 1, tzinfo=UTC)}
        await session.execute(
            text("update actor_profiles set last_seen_at=:old,updated_at=:old where id=:actor"),
            parameters,
        )
        await session.execute(
            text(
                "update actor_identity_links set last_verified_at=:old "
                "where actor_profile_id=:actor"
            ),
            parameters,
        )
        await session.commit()
    return await actor_observation(actor_id)


async def authority_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Snapshot actual stored values, not counts that could miss a rolled-back revoke."""
    async with db_session.get_session_factory()() as session:
        return await stored_authority(session)


async def stored_authority(session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    """Use the supplied transaction so late-failure proof sees actual staged rows."""
    result = {}
    for model in (AdminRoleGrant, AuthorityControl, AuthorityIdempotencyRecord, AuditEvent):
        rows = await session.execute(select(model.__table__).order_by(model.id))
        result[model.__tablename__] = [dict(row) for row in rows.mappings()]
    return result


async def authority_events(*, action: str | None = None, event_type: str | None = None):
    statement = select(AuditEvent).order_by(AuditEvent.id)
    if action is not None:
        statement = statement.where(AuditEvent.action_id == action)
    if event_type is not None:
        statement = statement.where(AuditEvent.event_type == event_type)
    async with db_session.get_session_factory()() as session:
        return list((await session.scalars(statement)).all())


def concealed_error(response: Response) -> dict[str, Any]:
    body = response.json()
    UUID(body["error"].pop("correlation_id"))
    return body


def assert_unavailable(response: Response) -> None:
    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert set(error) == {"code", "message", "retryable", "correlation_id", "details"}
    assert error["code"] == "service_unavailable"
    assert error["message"] == "Service unavailable"
    assert error["retryable"] is True
    assert error["details"] == {}
    UUID(error["correlation_id"])
