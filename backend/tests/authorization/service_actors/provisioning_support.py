"""Small read helpers for public service-actor provisioning tests."""

from dataclasses import dataclass
from typing import Any

from httpx import Response
from sqlalchemy import func, select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.models import (
    AdminRoleGrant,
    AuthorityIdempotencyRecord,
    ProjectRoleGrant,
)
from tests.authentication.support import issue_asymmetric_token
from tests.authorization.admin_access.support import AdminAccess


@dataclass(frozen=True)
class PersistedServiceActor:
    """Exact joined actor/link facts persisted by public provisioning."""

    profile_id: str
    actor_kind: str
    profile_status: str
    service_identity: str
    provisioning_method: str
    created_by: str
    profile_last_seen_at: Any
    link_id: str
    issuer: str
    subject: str
    subject_kind: str
    link_status: str
    linked_by: str
    link_last_verified_at: Any


def provisioning_payload(
    identity: ServiceIdentity, subject: str, reason: str = "Bind the verifier to its exact subject"
) -> dict[str, str]:
    return {"service_identity": identity.value, "subject": subject, "reason": reason}


async def provision(
    access: AdminAccess,
    key: str,
    payload: dict[str, str],
) -> Response:
    return await access.signed.client.post(
        "/api/v1/service-actors",
        headers=access.admin.headers | {"Idempotency-Key": key},
        json=payload,
    )


async def service_records() -> tuple[PersistedServiceActor, ...]:
    async with db_session.get_session_factory()() as session:
        rows = (
            await session.execute(
                select(
                    ActorProfile.id,
                    ActorProfile.actor_kind,
                    ActorProfile.status,
                    ActorProfile.service_identity,
                    ActorProfile.provisioning_method,
                    ActorProfile.created_by,
                    ActorProfile.last_seen_at,
                    ActorIdentityLink.id,
                    ActorIdentityLink.issuer,
                    ActorIdentityLink.subject,
                    ActorIdentityLink.subject_kind,
                    ActorIdentityLink.status,
                    ActorIdentityLink.linked_by,
                    ActorIdentityLink.last_verified_at,
                )
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(ActorProfile.actor_kind == "service")
                .order_by(ActorProfile.id)
            )
        ).all()
    return tuple(PersistedServiceActor(*row) for row in rows)


async def service_records_for_identity(
    identity: ServiceIdentity,
) -> tuple[PersistedServiceActor, ...]:
    return tuple(row for row in await service_records() if row.service_identity == identity.value)


async def service_records_for_subject(subject: str) -> tuple[PersistedServiceActor, ...]:
    return tuple(row for row in await service_records() if row.subject == subject)


async def actor_record_counts() -> tuple[int, int]:
    async with db_session.get_session_factory()() as session:
        profiles = int(await session.scalar(select(func.count()).select_from(ActorProfile)) or 0)
        links = int(await session.scalar(select(func.count()).select_from(ActorIdentityLink)) or 0)
        return profiles, links


def signed_subject_headers(
    access: AdminAccess,
    subject: str,
    *,
    subject_kind: str = "service",
    scope: str = "workstream:service",
) -> dict[str, str]:
    token = issue_asymmetric_token(
        access.signed.private_key,
        subject_kind=subject_kind,
        scope=scope,
        claims={"sub": subject, "jti": str(new_record_id())},
    )
    return {"Authorization": f"Bearer {token}"}


async def service_actor_authority_counts(
    rows: tuple[PersistedServiceActor, ...],
) -> tuple[int, int, int]:
    profile_ids = tuple(row.profile_id for row in rows)
    async with db_session.get_session_factory()() as session:
        admin_grants = int(
            await session.scalar(
                select(func.count())
                .select_from(AdminRoleGrant)
                .where(AdminRoleGrant.target_actor_profile_id.in_(profile_ids))
            )
            or 0
        )
        project_grants = int(
            await session.scalar(
                select(func.count())
                .select_from(ProjectRoleGrant)
                .where(ProjectRoleGrant.actor_profile_id.in_(profile_ids))
            )
            or 0
        )
        pending = int(
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.status == "pending")
            )
            or 0
        )
    return admin_grants, project_grants, pending
