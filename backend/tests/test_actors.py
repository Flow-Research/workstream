from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
import hashlib
from pathlib import Path
from typing import cast
from uuid import uuid4

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps.auth import get_auth_verification_result
from app.api.deps.rate_controls import get_rate_control_service
from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
    LegacyActorIdentity,
    LegacyWorkflowEligibility,
)
from app.modules.actors.repository import ActorRepository
from app.modules.actors.schemas import (
    ActorProfileAdminResponse,
    ActorProfileUpdateRequest,
    LegacyWorkflowEligibilityActivationRequest,
)
from app.modules.actors.service import (
    ActorDeactivated,
    ActorProfileDisabled,
    ActorService,
    IdentityLinkRevoked,
    LegacyWorkflowEligibilityCompatibility,
    ResolvedActor,
    ServiceActorNotProvisioned,
    UnsupportedSubjectKind,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.api_controls.service import RateControlDecision, RateControlUnavailableError
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import ActionId
from app.modules.tasks.models import AuditEvent
from app.schemas.auth import (
    ActorContext,
    AuthVerificationResult,
    VerifiedIssuerToken,
    actor_id_from_external_identity,
)

ISSUER = "https://identity.test"
RATE_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def test_actor_admin_response_requires_exact_service_identity_pair() -> None:
    now = datetime.now(UTC)
    common = {
        "actor_profile_id": uuid4(),
        "status": "active",
        "display_name": None,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": None,
        "suspended_at": None,
        "deactivated_at": None,
    }
    human = ActorProfileAdminResponse(
        **common,
        actor_kind="human",
        provisioning_method="automatic_first_access",
        service_identity=None,
    )
    service = ActorProfileAdminResponse(
        **common,
        actor_kind="service",
        provisioning_method="manual_service_provisioning",
        service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
    )

    assert human.service_identity is None
    assert service.service_identity is ServiceIdentity.ARTIFACT_VERIFIER
    for actor_kind, provisioning_method, service_identity in (
        ("human", "automatic_first_access", ServiceIdentity.ARTIFACT_VERIFIER),
        ("service", "manual_service_provisioning", None),
    ):
        with pytest.raises(ValidationError, match="service identity"):
            ActorProfileAdminResponse(
                **common,
                actor_kind=actor_kind,
                provisioning_method=provisioning_method,
                service_identity=service_identity,
            )


async def test_actor_admin_reads_are_bounded_and_reuse_exact_repository_lookups() -> None:
    now = datetime.now(UTC)
    actor_id, link_id = uuid4(), uuid4()
    profile = ActorProfile(
        id=str(actor_id),
        actor_kind="service",
        status="active",
        provisioning_method="manual_service_provisioning",
        service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
        display_name=None,
        contact_email="must-not-escape@example.test",
        created_by=str(uuid4()),
        created_at=now,
        updated_at=now,
        last_seen_at=None,
    )
    link = ActorIdentityLink(
        id=str(link_id),
        actor_profile_id=str(actor_id),
        issuer="private-issuer",
        subject="private-subject",
        subject_kind="service",
        status="active",
        linked_by=str(uuid4()),
        linked_at=now,
        last_verified_at=None,
    )

    class Repository:
        calls: list[tuple[str, str]] = []

        async def get_actor_profile(self, requested_id):
            self.calls.append(("profile", requested_id))
            return profile

        async def get_identity_link_for_actor(self, requested_id):
            self.calls.append(("link", requested_id))
            return link

    repository = Repository()
    service = ActorService.__new__(ActorService)
    service._repo = cast(ActorRepository, repository)

    profile_response = await service.read_admin_profile(actor_id)
    link_response = await service.read_admin_identity_link(actor_id)

    assert profile_response is not None
    assert link_response is not None
    assert repository.calls == [("profile", str(actor_id)), ("link", str(actor_id))]
    assert set(profile_response.model_dump()) == {
        "actor_profile_id",
        "actor_kind",
        "status",
        "provisioning_method",
        "service_identity",
        "display_name",
        "created_at",
        "updated_at",
        "last_seen_at",
        "suspended_at",
        "deactivated_at",
    }
    assert set(link_response.model_dump()) == {
        "identity_link_id",
        "actor_profile_id",
        "subject_kind",
        "status",
        "linked_at",
        "last_verified_at",
        "revoked_at",
        "reactivated_at",
    }
    serialized = repr((profile_response.model_dump(), link_response.model_dump()))
    assert "private-issuer" not in serialized
    assert "private-subject" not in serialized
    assert "must-not-escape@example.test" not in serialized


def test_service_identity_lock_has_a_distinct_domain_without_changing_external_keys() -> None:
    issuer = "service_identity"
    subject = "workstream.artifact.verifier"
    framed = (
        len(issuer.encode()).to_bytes(4, "big")
        + issuer.encode()
        + len(subject.encode()).to_bytes(4, "big")
        + subject.encode()
    )
    historical_external_key = int.from_bytes(
        hashlib.sha256(framed).digest()[:8],
        "big",
        signed=True,
    )

    assert ActorRepository._advisory_key(issuer, subject) == historical_external_key
    assert ActorRepository._advisory_key(subject, domain=b"\x01") != historical_external_key


@pytest.fixture
def actor_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
    reset_test_database_state,
) -> Iterator[str]:
    """Run canonical actor tests against an isolated current schema."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    monkeypatch.setenv("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", RATE_SECRET)
    set_dev_actor(monkeypatch, roles="worker", subject="actor-registry-contributor")
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())
    config = alembic_config()
    try:
        with migration_lock():
            command.downgrade(config, "base")
            try:
                command.upgrade(config, "head")
                yield postgres_database_url
            finally:
                try:
                    asyncio.run(
                        reset_test_database_state(
                            postgres_database_url,
                            include_canonical_actors=True,
                        )
                    )
                finally:
                    try:
                        asyncio.run(db_session.dispose_engine())
                    finally:
                        command.downgrade(config, "base")
    finally:
        try:
            asyncio.run(db_session.dispose_engine())
        finally:
            get_settings.cache_clear()


@pytest.fixture
async def actor_client(actor_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return config


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
    now = int(datetime.now(UTC).timestamp())
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


def legacy_actor(subject: str, roles: tuple[str, ...] = ("worker",)) -> ActorContext:
    return ActorContext(
        actor_id=actor_id_from_external_identity(ISSUER, subject),
        external_subject=subject,
        external_issuer=ISSUER,
        roles=roles,
        claim_snapshot={"roles": list(roles)},
        auth_source="dev_mock",
        is_dev_auth=True,
    )


async def test_actor_resolution_fails_closed_on_profile_or_subject_kind_drift() -> None:
    token = verified_token("actor-drift")
    link = ActorIdentityLink(
        id=str(uuid4()),
        actor_profile_id=str(uuid4()),
        issuer=token.issuer,
        subject=token.subject,
        subject_kind="human",
        status="active",
        linked_by=str(uuid4()),
        last_verified_at=datetime.now(UTC),
    )

    class Repository:
        profile = None

        async def get_identity_link(self, _issuer, _subject):
            return link

        async def get_actor_profile(self, _actor_profile_id):
            return self.profile

    repository = Repository()
    service = ActorService(object())  # type: ignore[arg-type]
    service._repo = repository  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="missing actor profile"):
        await service.find_actor_for_authorization(token)

    repository.profile = ActorProfile(
        id=link.actor_profile_id,
        actor_kind="service",
        status="active",
        provisioning_method="manual_service_provisioning",
        service_identity="workstream.artifact.verifier",
        created_by=link.actor_profile_id,
    )
    with pytest.raises(UnsupportedSubjectKind, match="does not match actor"):
        await service.find_actor_for_authorization(token)


async def test_actor_authorization_lock_rejects_disappearance_and_identity_drift() -> None:
    profile = ActorProfile(
        id=str(uuid4()),
        actor_kind="human",
        status="active",
        provisioning_method="automatic_first_access",
        created_by=str(uuid4()),
    )
    link = ActorIdentityLink(
        id=str(uuid4()),
        actor_profile_id=profile.id,
        issuer=ISSUER,
        subject="locked-actor",
        subject_kind="human",
        status="active",
        linked_by=profile.id,
        last_verified_at=datetime.now(UTC),
    )
    resolved = ResolvedActor(profile=profile, identity_link=link)

    class Repository:
        locked_profile = None
        locked_link = None
        calls: list[str] = []

        async def get_actor_profile(self, _actor_profile_id, *, for_update=False):
            assert for_update is True
            self.calls.append("profile")
            return self.locked_profile

        async def get_identity_link_by_id(self, _identity_link_id, *, for_update=False):
            assert for_update is True
            self.calls.append("link")
            return self.locked_link

    repository = Repository()
    service = ActorService(object())  # type: ignore[arg-type]
    service._repo = repository  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="profile disappeared"):
        await service.lock_actor_self_for_authorization(resolved)
    assert repository.calls == ["profile"]

    repository.locked_profile = profile
    repository.calls = []
    with pytest.raises(RuntimeError, match="link disappeared"):
        await service.lock_actor_self_for_authorization(resolved)
    assert repository.calls == ["profile", "link"]

    repository.locked_link = ActorIdentityLink(
        id=link.id,
        actor_profile_id=profile.id,
        issuer=link.issuer,
        subject="changed-subject",
        subject_kind="human",
        status="active",
        linked_by=profile.id,
        last_verified_at=datetime.now(UTC),
    )
    with pytest.raises(RuntimeError, match="identity changed"):
        await service.lock_actor_self_for_authorization(resolved)

    repository.locked_link = link
    locked = await service.lock_actor_self_for_authorization(resolved)
    assert locked.profile is profile
    assert locked.identity_link is link


async def test_actor_timestamp_touch_fails_closed_before_writes_on_missing_rows() -> None:
    profile = ActorProfile(
        id=str(uuid4()),
        actor_kind="human",
        status="active",
        provisioning_method="automatic_first_access",
        created_by=str(uuid4()),
    )
    link = ActorIdentityLink(
        id=str(uuid4()),
        actor_profile_id=profile.id,
        issuer=ISSUER,
        subject="timestamp-actor",
        subject_kind="human",
        status="active",
        linked_by=profile.id,
        last_verified_at=datetime.now(UTC),
    )
    repository = ActorRepository(object())  # type: ignore[arg-type]

    async def missing_profile(_actor_profile_id, *, for_update=False):
        assert for_update is True
        return None

    repository.get_actor_profile = missing_profile  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="profile disappeared"):
        await repository.touch_verified_actor(profile, link)

    async def locked_profile(_actor_profile_id, *, for_update=False):
        assert for_update is True
        return profile

    async def missing_link(_identity_link_id, *, for_update=False):
        assert for_update is True
        return None

    repository.get_actor_profile = locked_profile  # type: ignore[method-assign]
    repository.get_identity_link_by_id = missing_link  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="link disappeared"):
        await repository.touch_verified_actor(profile, link)


async def test_first_human_access_atomically_creates_profile_link_and_events(
    actor_database_env: str,
) -> None:
    token = verified_token("first-human")
    async with db_session.get_session_factory()() as session:
        resolved = await ActorService(session).resolve_verified_actor(
            token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )

    assert resolved.profile.id == actor_id_from_external_identity(ISSUER, token.subject)
    assert resolved.profile.actor_kind == "human"
    assert resolved.profile.status == "active"
    assert resolved.profile.provisioning_method == "automatic_first_access"
    assert resolved.identity_link.actor_profile_id == resolved.profile.id
    assert resolved.identity_link.subject_kind == "human"
    async with db_session.get_session_factory()() as session:
        events = (
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_id.in_([resolved.profile.id, resolved.identity_link.id]))
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
        ).all()
        assert {event.event_type for event in events} == {
            "ActorProfileProvisioned",
            "ActorIdentityLinked",
        }
        assert len(events) == 2
        assert all(event.idempotency_reference is None for event in events)
        assert all(event.invalidation_cause_event_id is None for event in events)


async def test_concurrent_first_access_leaves_one_profile_link_and_event_pair(
    actor_database_env: str,
) -> None:
    token = verified_token("concurrent-human")

    async def resolve():
        async with db_session.get_session_factory()() as session:
            return await ActorService(session).resolve_verified_actor(
                token,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )

    first, second = await asyncio.gather(resolve(), resolve())
    assert first.profile.id == second.profile.id
    assert first.identity_link.id == second.identity_link.id
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 1
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.event_type.in_(
                        ["ActorProfileProvisioned", "ActorIdentityLinked"]
                    )
                )
            )
            == 2
        )


async def test_repeated_verified_access_reuses_actor_and_advances_database_timestamps(
    actor_database_env: str,
) -> None:
    token = verified_token("repeat-human")
    async with db_session.get_session_factory()() as session:
        first = await ActorService(session).resolve_verified_actor(
            token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        first_profile_seen_at = first.profile.last_seen_at
        first_link_verified_at = first.identity_link.last_verified_at

    assert first_profile_seen_at is not None
    assert first_link_verified_at is not None
    await asyncio.sleep(0.01)
    async with db_session.get_session_factory()() as session:
        second = await ActorService(session).resolve_verified_actor(
            token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )

    assert second.profile.id == first.profile.id
    assert second.identity_link.id == first.identity_link.id
    assert second.profile.last_seen_at > first_profile_seen_at
    assert second.identity_link.last_verified_at > first_link_verified_at
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 1
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 1


async def test_first_access_rolls_back_profile_link_and_first_audit_on_second_audit_failure(
    actor_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = verified_token("audit-rollback-human")
    original = AuditService.add_authority_event
    calls = 0

    async def fail_second_event(self, value):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected audit failure")
        return await original(self, value)

    monkeypatch.setattr(AuditService, "add_authority_event", fail_second_event)
    async with db_session.get_session_factory()() as session:
        with pytest.raises(RuntimeError, match="injected audit failure"):
            await ActorService(session).resolve_verified_actor(
                token,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        await session.rollback()

    actor_id = actor_id_from_external_identity(ISSUER, token.subject)
    async with db_session.get_session_factory()() as session:
        assert await session.get(ActorProfile, actor_id) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ActorIdentityLink)
                .where(ActorIdentityLink.actor_profile_id == actor_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id == actor_id)
            )
            == 0
        )


@pytest.mark.parametrize("kind", ["agent", "space"])
async def test_unsupported_subject_kinds_create_nothing(
    actor_database_env: str,
    kind: str,
) -> None:
    async with db_session.get_session_factory()() as session:
        with pytest.raises(UnsupportedSubjectKind):
            await ActorService(session).resolve_verified_actor(
                verified_token(f"unsupported-{kind}", kind=kind),
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0


async def test_unknown_service_creates_nothing(actor_database_env: str) -> None:
    async with db_session.get_session_factory()() as session:
        with pytest.raises(ServiceActorNotProvisioned):
            await ActorService(session).resolve_verified_actor(
                verified_token("unknown-service", kind="service"),
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0


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
    response = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json={"display_name": "Contributor One", "contact_email": "one@example.test"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Contributor One"
    assert response.json()["contact_email"] == "one@example.test"

    unknown = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json={"status": "active"},
    )
    assert unknown.status_code == 422
    empty = await actor_client.patch("/api/v1/actors/me", headers=auth_headers(), json={})
    assert empty.status_code == 422


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

    async def fail_update(*_args, **_kwargs):
        raise SQLAlchemyError("injected database failure")

    monkeypatch.setattr(ActorService, "update_self", fail_update)
    response = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json={"display_name": "Not persisted"},
    )

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


async def test_actor_self_evidence_failure_is_retryable_and_rolls_back_touch(
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

    async def fail_evidence(*_args, **_kwargs):
        raise SQLAlchemyError("injected evidence failure")

    monkeypatch.setattr(AuditService, "add_authority_event", fail_evidence)
    response = await actor_client.get("/api/v1/actors/me", headers=auth_headers())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert response.json()["error"]["retryable"] is True
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


async def test_suspended_profile_is_readable_but_not_mutable(
    actor_client: AsyncClient,
) -> None:
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    actor_profile_id = created.json()["actor_profile_id"]
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, actor_profile_id)
        profile.status = "suspended"
        profile.suspended_by = actor_profile_id
        profile.suspended_at = func.now()
        profile.suspension_reason = "security response"
        await session.commit()

    read = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert read.status_code == 200
    assert read.json()["status"] == "suspended"
    patch = await actor_client.patch(
        "/api/v1/actors/me",
        headers=auth_headers(),
        json={"display_name": "Blocked"},
    )
    assert patch.status_code == 403
    assert patch.json()["error"]["code"] == "actor_suspended"
    async with db_session.get_session_factory()() as session:
        denial = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action_id == ActionId.ACTOR_PROFILE_UPDATE_SELF.value,
                AuditEvent.denial_code == "actor_suspended",
            )
        )
    assert denial is not None
    assert denial.resource_id == actor_profile_id


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
        link.status = "revoked"
        link.revoked_by = actor_profile_id
        link.revoked_at = func.now()
        link.revoked_reason = "security response"
        await session.commit()

    denied = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "identity_link_revoked"
    async with db_session.get_session_factory()() as session:
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
        profile.status = "deactivated"
        profile.deactivated_by = actor_profile_id
        profile.deactivated_at = func.now()
        profile.deactivation_reason = "operator decision"
        await session.commit()

    denied = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "actor_deactivated"
    async with db_session.get_session_factory()() as session:
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
            legacy=None,
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
) -> None:
    created = await actor_client.get("/api/v1/actors/me", headers=auth_headers())
    actor_profile_id = created.json()["actor_profile_id"]
    lock_attempted = asyncio.Event()
    original_lock = ActorService.lock_actor_self_for_authorization

    async def observed_lock(self, resolved):
        lock_attempted.set()
        return await original_lock(self, resolved)

    monkeypatch.setattr(ActorService, "lock_actor_self_for_authorization", observed_lock)
    async with db_session.get_session_factory()() as revoker:
        link = await revoker.scalar(
            select(ActorIdentityLink)
            .where(ActorIdentityLink.actor_profile_id == actor_profile_id)
            .with_for_update()
        )
        assert link is not None
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
        await lock_attempted.wait()
        await revoker.commit()

    denied = await patch_task
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

    eligibility = await actor_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": ["stem"]},
    )
    assert eligibility.status_code == 200, eligibility.text
    async with db_session.get_session_factory()() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "legacy_workflow_eligibility_activated"
            )
        )
        assert event is not None
        assert event.external_issuer == issuer
        assert event.external_subject == subject


def test_verified_identity_rejects_values_above_persisted_provenance_bound() -> None:
    with pytest.raises(ValidationError):
        verified_token("s" * 201)
    with pytest.raises(ValidationError):
        now = int(datetime.now(UTC).timestamp())
        VerifiedIssuerToken(
            issuer="i" * 201,
            subject="subject",
            audience=("workstream",),
            expires_at=now + 300,
            issued_at=now,
            token_id="oversized-issuer",
            subject_kind="human",
            scopes=frozenset({"workstream:access"}),
        )


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


async def test_legacy_activation_writes_only_compatibility_metadata(
    actor_database_env: str,
) -> None:
    actor = legacy_actor("legacy-intake")
    async with db_session.get_session_factory()() as session:
        await ActorService(session).resolve_verified_actor(
            verified_token("legacy-intake"),
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        response = await ActorService(session).activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["STEM", "stem"]),
        )
    assert response.status == "active"
    assert response.skill_tags == ["stem"]
    async with db_session.get_session_factory()() as session:
        assert await session.get(LegacyActorIdentity, actor.actor_id) is not None
        eligibility = await session.scalar(
            select(LegacyWorkflowEligibility).where(
                LegacyWorkflowEligibility.actor_id == actor.actor_id
            )
        )
        assert eligibility is not None
        assert eligibility.profile_metadata == {"source": "legacy_worker_profile_api"}
        table_names = set(
            await session.scalars(
                text("select tablename from pg_tables where schemaname=current_schema()")
            )
        )
        assert "admin_role_grants" in table_names
        assert await session.scalar(text("select count(*) from admin_role_grants")) == 0
        assert "project_role_grants" not in table_names


async def test_repeated_legacy_activation_updates_one_row_and_audits_only_changes(
    actor_database_env: str,
) -> None:
    actor = legacy_actor("legacy-repeat")
    async with db_session.get_session_factory()() as session:
        await ActorService(session).resolve_verified_actor(
            verified_token("legacy-repeat"),
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        service = ActorService(session)
        first = await service.activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["stem"]),
        )
        changed = await service.activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["data"]),
        )
        unchanged = await service.activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["data"]),
        )

    assert first.id == changed.id == unchanged.id
    assert first.skill_tags == ["stem"]
    assert changed.skill_tags == unchanged.skill_tags == ["data"]
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(LegacyWorkflowEligibility).where(
                    LegacyWorkflowEligibility.actor_id == actor.actor_id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.entity_type == "legacy_workflow_eligibility",
                    AuditEvent.actor_id == actor.actor_id,
                )
            )
            == 2
        )


async def test_concurrent_legacy_activation_serializes_payloads_and_actual_audits(
    actor_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = legacy_actor("legacy-concurrent-activation")
    async with db_session.get_session_factory()() as session:
        await ActorService(session).resolve_verified_actor(
            verified_token("legacy-concurrent-activation"),
            request_id=uuid4(),
            correlation_id=uuid4(),
        )

    async with (
        db_session.get_session_factory()() as first_session,
        db_session.get_session_factory()() as second_session,
    ):
        await ActorRepository(first_session).lock_external_identity(
            actor.external_issuer,
            actor.external_subject,
        )
        original_lock = ActorRepository.lock_external_identity
        second_lock_reached = asyncio.Event()

        async def observed_lock(
            repository: ActorRepository,
            issuer: str,
            subject: str,
        ) -> None:
            if repository._session is second_session:
                second_lock_reached.set()
            await original_lock(repository, issuer, subject)

        monkeypatch.setattr(ActorRepository, "lock_external_identity", observed_lock)
        second_activation = asyncio.create_task(
            ActorService(second_session).activate_legacy_workflow_eligibility(
                actor,
                LegacyWorkflowEligibilityActivationRequest(skill_tags=["second"]),
            )
        )
        await asyncio.wait_for(second_lock_reached.wait(), timeout=1)
        assert not second_activation.done()

        first = await ActorService(first_session).activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["first"]),
        )
        second = await second_activation

    assert first.skill_tags == ["first"]
    assert second.skill_tags == ["second"]
    assert first.id == second.id
    async with db_session.get_session_factory()() as session:
        eligibility = await session.scalar(
            select(LegacyWorkflowEligibility).where(
                LegacyWorkflowEligibility.actor_id == actor.actor_id
            )
        )
        assert eligibility is not None
        assert eligibility.skill_tags == ["second"]
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.entity_type == "legacy_workflow_eligibility",
                    AuditEvent.actor_id == actor.actor_id,
                )
            )
            == 2
        )


async def test_existing_actor_and_legacy_negative_states_fail_closed(
    actor_database_env: str,
) -> None:
    """Exercise revoked, deactivated, service, and compatibility state branches."""
    human_token = verified_token("revoked-human")
    async with db_session.get_session_factory()() as session:
        resolved = await ActorService(session).resolve_verified_actor(
            human_token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        resolved.identity_link.status = "revoked"
        resolved.identity_link.revoked_by = resolved.profile.id
        resolved.identity_link.revoked_at = func.now()
        resolved.identity_link.revoked_reason = "security response"
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IdentityLinkRevoked):
            await ActorService(session).find_verified_actor(human_token)

    deactivated_token = verified_token("deactivated-human")
    async with db_session.get_session_factory()() as session:
        deactivated = await ActorService(session).resolve_verified_actor(
            deactivated_token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        deactivated.profile.status = "deactivated"
        deactivated.profile.deactivated_by = deactivated.profile.id
        deactivated.profile.deactivated_at = func.now()
        deactivated.profile.deactivation_reason = "operator decision"
        await session.commit()
        with pytest.raises(ActorDeactivated):
            await ActorService(session).update_self(
                deactivated,
                ActorProfileUpdateRequest(display_name="Blocked"),
            )

    service_token = verified_token("known-service", kind="service")
    service_actor_id = actor_id_from_external_identity(ISSUER, service_token.subject)
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                ActorProfile(
                    id=service_actor_id,
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity="workstream.artifact.verifier",
                    created_by="workstream:system:test",
                    last_seen_at=None,
                ),
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=service_actor_id,
                    issuer=ISSUER,
                    subject=service_token.subject,
                    subject_kind="service",
                    status="active",
                    linked_by="workstream:system:test",
                    last_verified_at=None,
                ),
            ]
        )
        await session.commit()
        service = ActorService(session)
        with pytest.raises(ServiceActorNotProvisioned):
            await service.resolve_verified_actor(
                service_token,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        with pytest.raises(ServiceActorNotProvisioned):
            await service.resolve_actor_for_authorization(
                service_token,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        persisted = await service.find_actor_for_authorization(service_token)
        assert persisted is not None
        assert persisted.profile.last_seen_at is None
        assert persisted.identity_link.last_verified_at is None

    legacy = legacy_actor("disabled-legacy")
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                LegacyActorIdentity(
                    actor_id=legacy.actor_id,
                    external_subject=legacy.external_subject,
                    external_issuer=legacy.external_issuer,
                    last_seen_roles=["worker"],
                    last_claim_snapshot={},
                    auth_source="dev_mock",
                    is_dev_auth=True,
                ),
                LegacyWorkflowEligibility(
                    id=str(uuid4()),
                    actor_id=legacy.actor_id,
                    profile_type="worker",
                    status="disabled",
                    skill_tags=[],
                    scope_type="global",
                    scope_id="global",
                    profile_metadata={},
                ),
            ]
        )
        await session.commit()
        with pytest.raises(ActorProfileDisabled):
            await ActorService(session).activate_legacy_workflow_eligibility(
                legacy,
                LegacyWorkflowEligibilityActivationRequest(skill_tags=[]),
            )
        compatibility = LegacyWorkflowEligibilityCompatibility(session)
        assert await compatibility.get_active_submitter_eligibility(legacy.actor_id) is None
        assert await compatibility.get_active_submitter_eligibility(str(uuid4())) is None
