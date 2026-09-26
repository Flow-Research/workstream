# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

import time
from datetime import UTC, datetime
from app.core.identifiers import new_record_id

import pytest

from app.core.config import get_settings
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.schemas.auth import (
    VerifiedIssuerToken,
)

ISSUER = "https://identity.test"
RATE_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def resolved_actor(*, subject="controlled-actor", actor_id=None):
    """Build separate ORM-shaped rows for controlled owner-port proof, not SQL."""
    actor_id = actor_id or str(new_record_id())
    return ResolvedActor(
        profile=ActorProfile(
            id=actor_id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by=actor_id,
        ),
        identity_link=ActorIdentityLink(
            id=str(new_record_id()),
            actor_profile_id=actor_id,
            issuer=ISSUER,
            subject=subject,
            subject_kind="human",
            status="active",
            linked_by=actor_id,
            last_verified_at=datetime.now(UTC),
        ),
    )


def set_dev_actor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    roles: str,
    subject: str,
    token: str = "actor-token",
    issuer: str = ISSUER,
) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", token)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", subject)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", issuer)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", roles)
    get_settings.cache_clear()


def auth_headers(token: str = "actor-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def verified_token(subject: str, *, kind: str = "human") -> VerifiedIssuerToken:
    now = time.time_ns() // 1_000_000_000
    return VerifiedIssuerToken(
        issuer=ISSUER,
        subject=subject,
        audience=("workstream",),
        expires_at=now + 300,
        issued_at=now,
        token_id=f"token-{subject}",
        subject_kind=kind,
        scopes=frozenset({"workstream:access" if kind == "human" else "workstream:service"}),
    )
