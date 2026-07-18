from __future__ import annotations

from collections import UserDict
from collections.abc import Mapping
import json
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4
import warnings

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import (
    ACTION_DEFINITIONS,
    ActionAvailability,
    ActionId,
    PermissionId,
)
from app.modules.tasks.models import AuditEvent


def _assert_value_not_retained(value: object, forbidden: str, seen: set[int] | None = None) -> None:
    """Traverse public exception state and prove rejected input is absent."""
    seen = seen or set()
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, str):
        assert forbidden not in value
    elif isinstance(value, BaseException):
        for item in (value.args, vars(value), value.__cause__, value.__context__):
            _assert_value_not_retained(item, forbidden, seen)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _assert_value_not_retained(key, forbidden, seen)
            _assert_value_not_retained(item, forbidden, seen)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _assert_value_not_retained(item, forbidden, seen)


@pytest.fixture
def audit_database_env(postgres_database_url: str, migration_lock) -> str:
    """Ensure audit tests do not inherit another migration test's schema state."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    with migration_lock():
        command.upgrade(config, "head")
    return postgres_database_url


@pytest.fixture
async def audit_factory(audit_database_env: str):
    """Provide independent sessions over the isolated migrated database."""
    engine = create_async_engine(audit_database_env)
    async with engine.connect() as connection:
        existing = set(
            (
                await connection.execute(
                    text("select id from audit_events where event_domain = 'authority'")
                )
            ).scalars()
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            created = (
                set(
                    (
                        await connection.execute(
                            text("select id from audit_events where event_domain = 'authority'")
                        )
                    ).scalars()
                )
                - existing
            )
            if created:
                await connection.execute(text("lock table audit_events in access exclusive mode"))
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger audit_events_reject_update_delete"
                    )
                )
                await connection.execute(delete(AuditEvent).where(AuditEvent.id.in_(created)))
                await connection.execute(
                    text(
                        "alter table audit_events enable trigger audit_events_reject_update_delete"
                    )
                )
        await engine.dispose()


def _authority_input(event_type: AuthorityEventType, **overrides) -> AuthorityAuditEventInput:
    event_id = overrides.pop("event_id", uuid4())
    defaults = {
        AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED: {
            "entity_type": "authorization_decision",
            "reason": "authorization_evaluation",
            "after_facts": {"allowed": True},
        },
        AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED: {
            "entity_type": "authorization_decision",
            "reason": "authorization_evaluation",
            "after_facts": {"allowed": False},
        },
        AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED: {
            "entity_type": "authority_invalidation",
            "reason": "authority_state_changed",
            "before_facts": {"effective": True},
            "after_facts": {"effective": False},
        },
    }[event_type]
    values = {
        "event_id": event_id,
        "event_type": event_type,
        "entity_id": str(event_id),
        "actor_ref_kind": ActorReferenceKind.SYSTEM_PRINCIPAL,
        "actor_ref": "workstream:system:bootstrap",
        "request_id": uuid4(),
        "correlation_id": uuid4(),
        "permission_id": "actor.profile.read_any",
        **defaults,
    }
    values.update(overrides)
    return AuthorityAuditEventInput(**values)


def test_action_aware_audit_input_enforces_mapping_and_action_availability() -> None:
    denied = _authority_input(
        AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
        permission_id="artifact.binding.read",
        action_id="artifact.binding.read",
        denial_code="permission_not_granted",
    )
    assert denied.action_id is ActionId.ARTIFACT_BINDING_READ
    assert denied.permission_id is PermissionId.ARTIFACT_BINDING_READ

    with pytest.raises(ValidationError, match="action permission"):
        _authority_input(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
            permission_id="artifact.replica.read",
            action_id="artifact.binding.read",
            denial_code="permission_not_granted",
        )
    with pytest.raises(ValidationError, match="new permission requires"):
        _authority_input(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
            permission_id="artifact.binding.read",
            action_id=None,
            denial_code="permission_not_granted",
        )
    allowed_action_ids: set[ActionId] = set()
    for definition in ACTION_DEFINITIONS:
        if definition.availability is ActionAvailability.PLANNED:
            with pytest.raises(ValidationError, match="planned action"):
                _authority_input(
                    AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
                    permission_id=definition.permission_id,
                    action_id=definition.action_id,
                )
        else:
            allowed = _authority_input(
                AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
                permission_id=definition.permission_id,
                action_id=definition.action_id,
            )
            assert allowed.action_id is not None
            allowed_action_ids.add(allowed.action_id)
    assert allowed_action_ids == {
        ActionId.ACTOR_PROFILE_READ_SELF,
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
        ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
        ActionId.ADMIN_ROLE_GRANT_LIST,
        ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
        ActionId.ACTOR_PROFILE_READ,
            ActionId.ACTOR_IDENTITY_LINK_READ,
            ActionId.ACTOR_SERVICE_PROVISION,
            ActionId.ACTOR_PROFILE_SUSPEND,
            ActionId.ACTOR_PROFILE_REACTIVATE,
            ActionId.ACTOR_PROFILE_DEACTIVATE,
        }
    with pytest.raises(TypeError, match="invalid authority audit input"):
        _authority_input(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
            permission_id="artifact.binding.read",
            action_id="unknown.action",
            denial_code="permission_not_granted",
        )
    event_id = uuid4()
    with pytest.raises(ValidationError, match="action requires authorization decision"):
        AuthorityAuditEventInput(
            event_id=event_id,
            event_type=AuthorityEventType.ADMIN_ROLE_GRANT_ISSUE_DENIED,
            entity_type="admin_role_grant",
            entity_id=str(uuid4()),
            actor_ref_kind=ActorReferenceKind.SYSTEM_PRINCIPAL,
            actor_ref="workstream:system:bootstrap",
            request_id=uuid4(),
            correlation_id=uuid4(),
            permission_id="actor.profile.read_self",
            action_id="actor.profile.read_self",
            reason="authorization_policy_denial",
            denial_code="permission_not_granted",
        )


async def test_planned_action_denial_persists_with_bounded_mapping(audit_factory) -> None:
    value = _authority_input(
        AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
        permission_id="artifact.binding.read",
        action_id="artifact.binding.read",
        denial_code="permission_not_granted",
    )
    async with audit_factory() as session:
        stored = await AuditService(session).add_authority_event(value)
        await session.commit()

    assert stored.action_id == "artifact.binding.read"
    assert stored.permission_id == "artifact.binding.read"


def _authority_event_matrix() -> list[dict]:
    """Return every closed event with one valid and one fact-invalid shape."""
    project_id = str(uuid4())
    system_active = {
        "status": "active",
        "role": "access_administrator",
        "scope_type": "system",
        "effective": True,
    }
    project_active = {
        "status": "active",
        "role": "submitter",
        "scope_type": "project",
        "scope_id": project_id,
        "effective": True,
    }

    def row(event_type, entity_type, reason, before, after, invalid_after, **extra):
        event_id = uuid4()
        return {
            "event_id": event_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": str(event_id)
            if entity_type in {"authorization_decision", "authority_invalidation"}
            else str(uuid4()),
            "actor_ref_kind": ActorReferenceKind.SYSTEM_PRINCIPAL,
            "actor_ref": "workstream:system:bootstrap",
            "request_id": uuid4(),
            "correlation_id": uuid4(),
            "reason": reason,
            "before_facts": before,
            "after_facts": after,
            "invalid_patch": {"after_facts": invalid_after},
            **extra,
        }

    rows = [
        row(
            AuthorityEventType.ACTOR_PROFILE_PROVISIONED,
            "actor_profile",
            "automatic_first_access",
            None,
            {
                "status": "active",
                "subject_kind": "human",
                "provisioning_method": "automatic_first_access",
            },
            {
                "status": "active",
                "subject_kind": "service",
                "provisioning_method": "automatic_first_access",
            },
        ),
        row(
            AuthorityEventType.SERVICE_ACTOR_PROVISIONED,
            "actor_profile",
            "manual_service_provisioning",
            None,
            {
                "status": "active",
                "subject_kind": "service",
                "provisioning_method": "manual_service_provisioning",
            },
            {
                "status": "active",
                "subject_kind": "human",
                "provisioning_method": "manual_service_provisioning",
            },
        ),
        row(
            AuthorityEventType.ACTOR_IDENTITY_LINKED,
            "actor_identity_link",
            "identity_lifecycle_change",
            None,
            {"status": "active", "subject_kind": "human"},
            {"status": "revoked", "subject_kind": "human"},
        ),
        row(
            AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED,
            "actor_identity_link",
            "identity_lifecycle_change",
            {"status": "active"},
            {"status": "revoked"},
            {"status": "active"},
        ),
        row(
            AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED,
            "actor_identity_link",
            "identity_lifecycle_change",
            {"status": "revoked"},
            {"status": "active"},
            {"status": "suspended"},
        ),
        row(
            AuthorityEventType.ACTOR_PROFILE_SUSPENDED,
            "actor_profile",
            "security_response",
            {"status": "active"},
            {"status": "suspended"},
            {"status": "deactivated"},
        ),
        row(
            AuthorityEventType.ACTOR_PROFILE_REACTIVATED,
            "actor_profile",
            "administrative_correction",
            {"status": "suspended"},
            {"status": "active"},
            {"status": "deactivated"},
        ),
        row(
            AuthorityEventType.ACTOR_PROFILE_DEACTIVATED,
            "actor_profile",
            "security_response",
            {"status": "active"},
            {"status": "deactivated"},
            {"status": "suspended"},
        ),
        row(
            AuthorityEventType.INITIAL_ACCESS_ADMIN_BOOTSTRAPPED,
            "admin_role_grant",
            "initial_access_bootstrap",
            None,
            system_active,
            system_active | {"effective": False},
        ),
        row(
            AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,
            "admin_role_grant",
            "authority_assignment",
            None,
            system_active,
            system_active | {"status": "revoked"},
        ),
        row(
            AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED,
            "admin_role_grant",
            "authority_revocation",
            system_active,
            system_active | {"status": "revoked", "effective": False},
            system_active | {"role": "operator", "status": "revoked", "effective": False},
        ),
        row(
            AuthorityEventType.ADMIN_ROLE_GRANT_ISSUE_DENIED,
            "admin_role_grant",
            "authorization_policy_denial",
            None,
            None,
            {"allowed": False},
            denial_code="admin_role_grant_exists",
        ),
        row(
            AuthorityEventType.LAST_ACCESS_ADMIN_OPERATION_DENIED,
            "admin_role_grant",
            "authorization_policy_denial",
            None,
            None,
            {"allowed": False},
            denial_code="last_access_administrator",
        ),
        row(
            AuthorityEventType.PROJECT_ROLE_QUALIFICATION_CAPTURED,
            "qualification_snapshot",
            "qualification_evidence_captured",
            None,
            {"status": "captured"},
            {"status": "active"},
            project_id=project_id,
        ),
        row(
            AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
            "project_role_grant",
            "authority_assignment",
            None,
            project_active,
            {
                "status": "active",
                "role": "submitter",
                "scope_type": "system",
                "effective": True,
            },
            project_id=project_id,
        ),
        row(
            AuthorityEventType.PROJECT_ROLE_GRANT_REPLACED,
            "project_role_grant",
            "authority_replacement",
            project_active,
            project_active | {"role": "reviewer"},
            project_active | {"scope_id": str(uuid4()), "role": "reviewer"},
            project_id=project_id,
        ),
        row(
            AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED,
            "project_role_grant",
            "authority_revocation",
            project_active,
            project_active | {"status": "revoked", "effective": False},
            project_active | {"role": "reviewer", "status": "revoked", "effective": False},
            project_id=project_id,
        ),
        row(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
            "authorization_decision",
            "authorization_evaluation",
            None,
            {"allowed": True},
            {"allowed": False},
            permission_id="actor.profile.read_any",
        ),
        row(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
            "authorization_decision",
            "authorization_evaluation",
            None,
            {"allowed": False},
            {"allowed": True},
            permission_id="actor.profile.read_any",
            denial_code="actor_suspended",
        ),
    ]
    rows[11]["invalid_patch"] = {"denial_code": None}
    rows[12]["invalid_patch"] = {"denial_code": None}
    rows.append(
        row(
            AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
            "authority_invalidation",
            "authority_state_changed",
            {"effective": True},
            {"effective": False},
            {"effective": True},
            invalidation_cause_event_id=rows[0]["event_id"],
            invalidation_target_kind="actor_profile",
            invalidation_target_ref=str(uuid4()),
        )
    )
    return rows


def _authority_sql_values(candidate: dict) -> dict:
    """Convert one shared matrix row into direct-SQL bind values."""
    value = candidate.copy()
    value.pop("invalid_patch", None)
    optional = (
        "target_actor_ref_kind",
        "target_actor_ref",
        "matched_grant_id",
        "permission_id",
        "project_id",
        "resource_type",
        "resource_id",
        "target_ref_kind",
        "target_ref_id",
        "denial_code",
        "idempotency_reference",
        "invalidation_cause_event_id",
        "invalidation_target_kind",
        "invalidation_target_ref",
    )
    return {
        **{key: value.get(key) for key in optional},
        "id": str(value["event_id"]),
        "entity_type": value["entity_type"],
        "entity_id": value["entity_id"],
        "event_type": value["event_type"].value,
        "actor_ref_kind": value["actor_ref_kind"].value,
        "actor_id": value["actor_ref"],
        "request_id": str(value["request_id"]),
        "correlation_id": str(value["correlation_id"]),
        "reason": value["reason"],
        "invalidation_cause_event_id": str(value["invalidation_cause_event_id"])
        if value.get("invalidation_cause_event_id") is not None
        else None,
        "before_facts": json.dumps(value["before_facts"])
        if value.get("before_facts") is not None
        else None,
        "after_facts": json.dumps(value["after_facts"])
        if value.get("after_facts") is not None
        else None,
    }


def test_authority_input_rejects_unbounded_or_inconsistent_evidence() -> None:
    secret = "secret-bearer-value"

    class HostileMapping(Mapping):
        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            raise RuntimeError(secret)

        def __len__(self):
            return 1

    payload = _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED).model_dump(
        mode="json"
    ) | {"raw_token": secret}
    constructors = (
        lambda value: AuthorityAuditEventInput(**value),
        AuthorityAuditEventInput.model_validate,
    )
    mappings = (payload, UserDict(payload), MappingProxyType(payload))
    for constructor in constructors:
        for mapping in mappings:
            with pytest.raises(TypeError, match="invalid authority audit input") as caught:
                constructor(mapping)
            _assert_value_not_retained(caught.value, secret)
    with pytest.raises(TypeError, match="invalid authority audit input") as caught:
        AuthorityAuditEventInput.model_validate_json(json.dumps(payload))
    _assert_value_not_retained(caught.value, secret)
    with pytest.raises(TypeError, match="invalid authority audit input") as caught:
        AuthorityAuditEventInput.model_validate(HostileMapping())
    _assert_value_not_retained(caught.value, secret)

    safe = _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED).model_dump(
        mode="json"
    )
    safe_python = _authority_input(
        AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED
    ).model_dump()

    class ChangingMapping(Mapping):
        def __init__(self):
            self.iterations = 0

        def __getitem__(self, key):
            return safe_python[key] if key in safe_python else secret

        def __iter__(self):
            self.iterations += 1
            keys = (
                safe_python
                if self.iterations == 1
                else safe_python | {"raw_token": secret}
            )
            return iter(keys)

        def __len__(self):
            return len(safe_python)

    class HostileBytearray(bytearray):
        def decode(self, *args, **kwargs):
            raise RuntimeError(secret)

    class LyingBytearray(bytearray):
        def decode(self, *args, **kwargs):
            return json.dumps(safe)

    class ChangingFacts(Mapping):
        def __init__(self):
            self.iterations = 0

        def __getitem__(self, key):
            return True if key == "allowed" else secret

        def __iter__(self):
            self.iterations += 1
            return iter(("allowed",) if self.iterations == 1 else ("raw_token",))

        def __len__(self):
            return 1

        def __repr__(self):
            return f"<{secret}>"

    changing = ChangingMapping()
    assert AuthorityAuditEventInput.model_validate(changing).event_type == safe_python["event_type"]
    assert changing.iterations == 1
    changing_facts = ChangingFacts()
    with warnings.catch_warnings(record=True) as caught_warnings:
        normalized = AuthorityAuditEventInput.model_validate(
            safe_python | {"after_facts": changing_facts}
        )
    assert normalized.after_facts == {"allowed": True}
    assert changing_facts.iterations == 1
    assert caught_warnings == []
    assert (
        AuthorityAuditEventInput.model_validate_json(json.dumps(safe)).model_dump(mode="json")
        == safe
    )
    duplicate = json.dumps(safe).replace(
        '"allowed": true',
        '"allowed": false, "allowed": true, "raw_token": "secret-bearer-value"',
    )
    for raw in (
        "{secret-bearer-value",
        '"secret-bearer-value"',
        '["secret-bearer-value"]',
        "0",
        "true",
        "false",
        "null",
        duplicate,
    ):
        for document in (raw, raw.encode(), bytearray(raw.encode())):
            with pytest.raises(TypeError, match="invalid authority audit input") as caught:
                AuthorityAuditEventInput.model_validate_json(document)
            _assert_value_not_retained(caught.value, secret)
    for document in (HostileBytearray(b"{}"), LyingBytearray(duplicate.encode())):
        with pytest.raises(TypeError, match="invalid authority audit input") as caught:
            AuthorityAuditEventInput.model_validate_json(document)
        _assert_value_not_retained(caught.value, secret)

    for patch, forbidden in (
        (
            {
                "actor_ref_kind": ActorReferenceKind.LEGACY_ACTOR,
                "actor_ref": "provider@example.com",
            },
            "provider@example.com",
        ),
        ({"after_facts": {"allowed": "secret-bearer-value"}}, secret),
        ({"after_facts": {"allowed": {"secret": secret}}}, secret),
        (
            {"after_facts": {"decision_code": "https://issuer.example/private"}},
            "https://issuer.example/private",
        ),
        ({"reason": "secret-bearer-value"}, secret),
        ({"entity_type": "secret-bearer-value"}, secret),
        ({"permission_id": [secret]}, secret),
        ({"action_id": [secret]}, secret),
    ):
        candidate = safe | patch
        for constructor in constructors:
            with pytest.raises(TypeError, match="invalid authority audit input") as caught:
                constructor(candidate)
            _assert_value_not_retained(caught.value, forbidden)
        with pytest.raises(TypeError, match="invalid authority audit input") as caught:
            AuthorityAuditEventInput.model_validate_json(json.dumps(candidate))
        _assert_value_not_retained(caught.value, forbidden)
    with pytest.raises(ValidationError, match="resource ID requires"):
        _authority_input(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
            resource_id=str(uuid4()),
        )
    with pytest.raises(ValidationError, match="invalid denied authorization"):
        _authority_input(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
            denial_code="actor_suspended",
            idempotency_reference=uuid4(),
        )
    with pytest.raises(ValidationError, match="invalidation evidence"):
        _authority_input(AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED)
    target_id = str(uuid4())
    issued = _authority_input(
        AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
        permission_id="admin_role.grant",
        resource_type="actor_profile",
        resource_id=target_id,
        invalidation_cause_event_id=uuid4(),
        invalidation_target_kind="actor_profile",
        invalidation_target_ref=target_id,
        before_facts={"effective": False},
        after_facts={"effective": True},
    )
    assert issued.before_facts == {"effective": False}
    with pytest.raises(ValidationError, match="invalidation direction"):
        _authority_input(
            AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
            permission_id="admin_role.grant",
            resource_type="actor_profile",
            resource_id=target_id,
            invalidation_cause_event_id=uuid4(),
            invalidation_target_kind="actor_profile",
            invalidation_target_ref=target_id,
        )
    event_id = uuid4()
    with pytest.raises(ValidationError, match="own event"):
        _authority_input(
            AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
            event_id=event_id,
            permission_id=None,
            invalidation_cause_event_id=event_id,
            invalidation_target_kind="actor_profile",
            invalidation_target_ref=str(uuid4()),
        )


def test_authority_input_enforces_grant_scope_matrix() -> None:
    """Grant evidence cannot contradict role, project, or replacement scope."""
    source = _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED).model_dump()
    event_id = uuid4()
    project_id = str(uuid4())
    source.update(
        event_id=event_id,
        event_type=AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,
        entity_type="admin_role_grant",
        entity_id=str(uuid4()),
        permission_id=None,
        reason="authority_assignment",
        project_id=project_id,
        after_facts={
            "status": "active",
            "role": "project_manager",
            "scope_type": "project",
            "scope_id": project_id,
            "effective": True,
        },
    )
    assert AuthorityAuditEventInput.model_validate(source).project_id == project_id

    for patch in (
        {"after_facts": source["after_facts"] | {"role": "access_administrator"}},
        {"after_facts": source["after_facts"] | {"scope_id": str(uuid4())}},
        {"project_id": None},
    ):
        with pytest.raises(ValidationError, match="facts|scope"):
            AuthorityAuditEventInput.model_validate(source | patch)

    replacement = source | {
        "event_type": AuthorityEventType.PROJECT_ROLE_GRANT_REPLACED,
        "entity_type": "project_role_grant",
        "reason": "authority_replacement",
        "before_facts": {
            "status": "active",
            "role": "submitter",
            "scope_type": "project",
            "scope_id": project_id,
            "effective": True,
        },
        "after_facts": {
            "status": "active",
            "role": "reviewer",
            "scope_type": "project",
            "scope_id": str(uuid4()),
            "effective": True,
        },
    }
    with pytest.raises(ValidationError, match="scope"):
        AuthorityAuditEventInput.model_validate(replacement)
    with pytest.raises(ValidationError, match="project resource"):
        AuthorityAuditEventInput.model_validate(
            source
            | {
                "resource_type": "project",
                "resource_id": str(uuid4()),
            }
        )


async def test_authority_event_matrix_preserves_shapes_and_requires_idempotency_links(
    audit_factory,
) -> None:
    """Preserve 05A shapes while 05B-linked mutations fail closed without a claim."""
    insert = text(
        "insert into audit_events "
        "(id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot, "
        "auth_source, is_dev_auth, event_payload, event_domain, event_version, actor_ref_kind, "
        "request_id, correlation_id, target_actor_ref_kind, target_actor_ref, matched_grant_id, "
        "permission_id, project_id, resource_type, resource_id, target_ref_kind, target_ref_id, "
        "reason, denial_code, idempotency_reference, invalidation_cause_event_id, "
        "invalidation_target_kind, invalidation_target_ref, before_facts, after_facts) values "
        "(:id, :entity_type, :entity_id, :event_type, :actor_id, '[]', '{}', "
        "'local_authority', false, '{}', 'authority', 1, :actor_ref_kind, :request_id, "
        ":correlation_id, :target_actor_ref_kind, :target_actor_ref, :matched_grant_id, "
        ":permission_id, :project_id, :resource_type, :resource_id, :target_ref_kind, "
        ":target_ref_id, :reason, :denial_code, :idempotency_reference, "
        ":invalidation_cause_event_id, :invalidation_target_kind, :invalidation_target_ref, "
        "cast(:before_facts as json), cast(:after_facts as json))"
    )
    cases = _authority_event_matrix()
    assert {case["event_type"] for case in cases} == set(AuthorityEventType)
    linked = {
        AuthorityEventType.SERVICE_ACTOR_PROVISIONED,
        AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,
        AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED,
        AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
        AuthorityEventType.PROJECT_ROLE_GRANT_REPLACED,
        AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED,
        AuthorityEventType.ACTOR_PROFILE_SUSPENDED,
        AuthorityEventType.ACTOR_PROFILE_REACTIVATED,
        AuthorityEventType.ACTOR_PROFILE_DEACTIVATED,
        AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED,
        AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED,
        AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
    }

    async with audit_factory() as session:
        for case in cases:
            candidate = {key: value for key, value in case.items() if key != "invalid_patch"}
            assert (
                AuthorityAuditEventInput.model_validate(candidate).event_type == case["event_type"]
            )
            if case["event_type"] in linked:
                with pytest.raises(IntegrityError, match="idempotency reference"):
                    await session.execute(insert, _authority_sql_values(candidate))
                await session.rollback()
            else:
                await session.execute(insert, _authority_sql_values(candidate))
                await session.commit()

        for case in cases:
            event_id = uuid4()
            candidate = {
                **{key: value for key, value in case.items() if key != "invalid_patch"},
                **case["invalid_patch"],
                "event_id": event_id,
            }
            if candidate["entity_type"] in {"authorization_decision", "authority_invalidation"}:
                candidate["entity_id"] = str(event_id)
            with pytest.raises(ValidationError):
                AuthorityAuditEventInput.model_validate(candidate)
            with pytest.raises(IntegrityError):
                await session.execute(insert, _authority_sql_values(candidate))
            await session.rollback()


async def test_authority_service_readmits_mutated_inputs_without_retention(audit_factory) -> None:
    """The service never forwards post-validation mutations to SQLAlchemy."""
    secret = "secret-bearer-value"

    class HostileFacts(Mapping):
        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            raise RuntimeError(secret)

        def __len__(self):
            return 1

        def __repr__(self):
            return f"<{secret}>"

    class ChangingFacts(Mapping):
        def __init__(self):
            self.iterations = 0

        def __getitem__(self, key):
            return True if key == "allowed" else secret

        def __iter__(self):
            self.iterations += 1
            return iter(("allowed",) if self.iterations == 1 else ("raw_token",))

        def __len__(self):
            return 1

        def __repr__(self):
            return f"<{secret}>"

    values = [
        _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED),
        _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED),
        _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED),
    ]
    values[0].actor_ref = secret
    values[1].after_facts["allowed"] = secret
    values[2].after_facts = HostileFacts()
    valid_hostile_repr = _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED)
    changing_facts = ChangingFacts()
    valid_hostile_repr.after_facts = changing_facts

    async with audit_factory() as session:
        for value in values:
            with warnings.catch_warnings(record=True) as caught_warnings:
                with pytest.raises(TypeError, match="invalid authority audit input") as caught:
                    await AuditService(session).add_authority_event(value)
            _assert_value_not_retained(caught.value, secret)
            assert caught_warnings == []
            assert await session.get(AuditEvent, str(value.event_id)) is None
        with warnings.catch_warnings(record=True) as caught_warnings:
            stored = await AuditService(session).add_authority_event(valid_hostile_repr)
        assert stored.after_facts == {"allowed": True}
        assert changing_facts.iterations == 1
        assert caught_warnings == []


async def test_authority_writer_persists_typed_privacy_neutral_events(audit_factory) -> None:
    future_idempotency = uuid4()
    project_id = str(uuid4())
    allowed = _authority_input(
        AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
        project_id=project_id,
        resource_type="project",
        resource_id=project_id,
    )
    denied = _authority_input(
        AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
        denial_code="permission_not_granted",
    )
    invalidation = _authority_input(
        AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
        permission_id=None,
        invalidation_cause_event_id=allowed.event_id,
        invalidation_target_kind="actor_profile",
        invalidation_target_ref=str(uuid4()),
        idempotency_reference=future_idempotency,
    )

    async with audit_factory() as session:
        service = AuditService(session)
        stored = [await service.add_authority_event(value) for value in (allowed, denied)]
        await session.commit()
        stored_values = [
            {
                "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "event_domain": event.event_domain,
                "event_version": event.event_version,
                "external_subject": event.external_subject,
                "external_issuer": event.external_issuer,
                "actor_roles": event.actor_roles,
                "claim_snapshot": event.claim_snapshot,
                "event_payload": event.event_payload,
                "auth_source": event.auth_source,
                "is_dev_auth": event.is_dev_auth,
                "idempotency_reference": event.idempotency_reference,
            }
            for event in stored
        ]
        with pytest.raises(IntegrityError, match="idempotency reference"):
            await service.add_authority_event(invalidation)
        await session.rollback()

    assert [event["event_type"] for event in stored_values] == [
        "SensitiveAuthorizationAllowed",
        "SensitiveAuthorizationDenied",
    ]
    assert all(event["occurred_at"] is not None for event in stored_values)
    for event in stored_values:
        assert event["event_domain"] == "authority"
        assert event["event_version"] == 1
        assert event["external_subject"] is None
        assert event["external_issuer"] is None
        assert event["actor_roles"] == []
        assert event["claim_snapshot"] == {}
        assert event["event_payload"] == {}
        assert event["auth_source"] == "local_authority"
        assert event["is_dev_auth"] is False
    assert stored_values[0]["idempotency_reference"] is None
    assert future_idempotency is not None


async def test_legacy_writer_and_reader_remain_compatible(audit_factory) -> None:
    event = AuditEvent(
        id=str(uuid4()),
        entity_type="task",
        entity_id=str(uuid4()),
        event_type="task_created",
        from_status=None,
        to_status="draft",
        actor_id="legacy-actor",
        external_subject="opaque-subject",
        external_issuer="https://issuer.example.test",
        actor_roles=["project_manager"],
        claim_snapshot={"bounded": True},
        auth_source="verified_token",
        is_dev_auth=False,
        event_payload={"source_type": "manual"},
    )
    async with audit_factory() as session:
        repository = AuditRepository(session)
        stored = await repository.add_audit_event(event)
        await session.commit()
        listed = await repository.list_audit_events("task", event.entity_id)

    assert listed == [stored]
    assert stored.event_domain == "legacy_lifecycle"
    assert stored.event_version is None
    assert stored.occurred_at is None
    assert stored.event_payload == {"source_type": "manual"}


async def test_authority_event_rollback_leaves_no_row(audit_factory) -> None:
    value = _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED)
    async with audit_factory() as session:
        await AuditService(session).add_authority_event(value)
        await session.rollback()
    async with audit_factory() as session:
        assert await session.get(AuditEvent, str(value.event_id)) is None


async def test_authority_invalidation_requires_an_existing_authority_cause(audit_factory) -> None:
    legacy_id = str(uuid4())
    invalidation = _authority_input(
        AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
        permission_id=None,
        invalidation_cause_event_id=uuid4(),
        invalidation_target_kind="actor_profile",
        invalidation_target_ref=str(uuid4()),
    )
    async with audit_factory() as session:
        with pytest.raises(ValueError, match="existing authority event"):
            await AuditService(session).add_authority_event(invalidation)
        await AuditRepository(session).add_audit_event(
            AuditEvent(
                id=legacy_id,
                entity_type="task",
                entity_id=str(uuid4()),
                event_type="task_created",
                actor_id="legacy",
                external_subject="opaque",
                external_issuer="https://issuer.test",
                actor_roles=[],
                claim_snapshot={},
                auth_source="verified_token",
                is_dev_auth=False,
                event_payload={},
            )
        )
        invalidation.invalidation_cause_event_id = UUID(legacy_id)
        with pytest.raises(ValueError, match="existing authority event"):
            await AuditService(session).add_authority_event(invalidation)
        assert await session.get(AuditEvent, str(invalidation.event_id)) is None


async def test_legacy_repository_rejects_unvalidated_authority_rows(audit_factory) -> None:
    raw = AuditEvent(
        id=str(uuid4()),
        entity_type="actor",
        entity_id=str(uuid4()),
        event_type="SensitiveAuthorizationAllowed",
        actor_id="provider@example.com",
        actor_roles=[],
        claim_snapshot={},
        auth_source="local_authority",
        is_dev_auth=False,
        event_payload={},
        event_domain="authority",
    )
    async with audit_factory() as session:
        with pytest.raises(ValueError, match="typed audit service"):
            await AuditRepository(session).add_audit_event(raw)
        assert raw not in session


async def test_database_rejects_malformed_and_mutated_audit_rows(audit_factory) -> None:
    value = _authority_input(AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED)
    legacy_id = str(uuid4())
    async with audit_factory() as session:
        await AuditService(session).add_authority_event(value)
        await AuditRepository(session).add_audit_event(
            AuditEvent(
                id=legacy_id,
                entity_type="task",
                entity_id=str(uuid4()),
                event_type="task_created",
                actor_id="legacy-actor",
                external_subject="opaque-subject",
                external_issuer="https://issuer.example.test",
                actor_roles=[],
                claim_snapshot={},
                auth_source="verified_token",
                is_dev_auth=False,
                event_payload={},
            )
        )
        await session.commit()

    async with audit_factory() as session:
        for event_id in (str(value.event_id), legacy_id):
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(
                    text("update audit_events set reason = 'changed' where id = :id"),
                    {"id": event_id},
                )
            await session.rollback()
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(
                    text("delete from audit_events where id = :id"),
                    {"id": event_id},
                )
            await session.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text("truncate table audit_events cascade"))
        await session.rollback()
        rows = (
            await session.execute(
                text(
                    "select id, reason, event_domain from audit_events "
                    "where id in (:authority_id, :legacy_id) order by id"
                ),
                {"authority_id": str(value.event_id), "legacy_id": legacy_id},
            )
        ).all()
        assert {(row.id, row.reason, row.event_domain) for row in rows} == {
            (str(value.event_id), "authorization_evaluation", "authority"),
            (legacy_id, None, "legacy_lifecycle"),
        }

        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "insert into audit_events "
                    "(id, entity_type, entity_id, event_type, actor_id, actor_roles, "
                    "claim_snapshot, auth_source, is_dev_auth, event_payload, event_domain) "
                    "values (:id, 'actor', :entity_id, 'SensitiveAuthorizationAllowed', "
                    "'legacy', '[]', '{}', 'local_authority', false, '{}', 'authority')"
                ),
                {"id": str(uuid4()), "entity_id": str(uuid4())},
            )
        await session.rollback()
        insert = text(
            "insert into audit_events "
            "(id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot, "
            "auth_source, is_dev_auth, event_payload, event_domain, event_version, actor_ref_kind, "
            "request_id, correlation_id, permission_id, reason, after_facts) values "
            "(:id, :entity_type, :id, 'SensitiveAuthorizationAllowed', :actor_id, '[]', '{}', "
            "'local_authority', false, '{}', 'authority', 1, :actor_kind, :request_id, "
            ":correlation_id, :permission_id, :reason, cast(:facts as json))"
        )
        for patch in (
            {"actor_kind": "legacy_actor", "actor_id": "provider@example.com"},
            {"facts": '{"decision_code":"https://issuer.test"}'},
            {"facts": '{"allowed":"secret-bearer-value"}'},
            {"facts": '{"allowed":false,"allowed":true}'},
            {"entity_type": "provider@example.com"},
            {"id": "secret-bearer-value"},
            {"permission_id": "secret-bearer-value"},
            {"reason": "secret-bearer-value"},
        ):
            with pytest.raises(IntegrityError):
                values = {
                    "id": str(uuid4()),
                    "actor_id": "workstream:system:bootstrap",
                    "actor_kind": "system_principal",
                    "request_id": str(uuid4()),
                    "correlation_id": str(uuid4()),
                    "entity_type": "authorization_decision",
                    "permission_id": "actor.profile.read_any",
                    "reason": "authorization_evaluation",
                    "facts": '{"allowed":true}',
                }
                values.update(patch)
                await session.execute(
                    insert,
                    values,
                )
            await session.rollback()
        grant_insert = text(
            "insert into audit_events "
            "(id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot, "
            "auth_source, is_dev_auth, event_payload, event_domain, event_version, actor_ref_kind, "
            "request_id, correlation_id, project_id, resource_type, resource_id, reason, "
            "after_facts) values "
            "(:id, 'admin_role_grant', :entity_id, 'AdminRoleGrantIssued', "
            "'workstream:system:bootstrap', '[]', '{}', 'local_authority', false, '{}', "
            "'authority', 1, 'system_principal', :request_id, :correlation_id, :project_id, "
            ":resource_type, :resource_id, 'authority_assignment', cast(:facts as json))"
        )
        project_id = str(uuid4())

        def grant_values(facts: str, *, scope_project_id: str | None = project_id) -> dict:
            return {
                "id": str(uuid4()),
                "entity_id": str(uuid4()),
                "request_id": str(uuid4()),
                "correlation_id": str(uuid4()),
                "project_id": scope_project_id,
                "resource_type": "project" if scope_project_id is not None else None,
                "resource_id": scope_project_id,
                "facts": facts,
            }

        valid_facts = json.dumps(
            {
                "status": "active",
                "role": "project_manager",
                "scope_type": "project",
                "scope_id": project_id,
                "effective": True,
            }
        )
        with pytest.raises(IntegrityError, match="idempotency reference"):
            await session.execute(grant_insert, grant_values(valid_facts))
        await session.rollback()
        system_facts = json.dumps(
            {
                "status": "active",
                "role": "access_administrator",
                "scope_type": "system",
                "effective": True,
            }
        )
        with pytest.raises(IntegrityError, match="idempotency reference"):
            await session.execute(grant_insert, grant_values(system_facts, scope_project_id=None))
        await session.rollback()
        for values in (
            grant_values(valid_facts.replace(project_id, str(uuid4()))),
            grant_values(valid_facts) | {"resource_id": str(uuid4())},
            grant_values(valid_facts.replace("project_manager", "access_administrator")),
            grant_values(
                json.dumps(
                    {
                        "status": "active",
                        "role": "project_manager",
                        "scope_type": "system",
                        "effective": True,
                    }
                )
            ),
        ):
            with pytest.raises(IntegrityError):
                await session.execute(grant_insert, values)
            await session.rollback()
        invalidation_insert = text(
            "insert into audit_events (id, entity_type, entity_id, event_type, actor_id, "
            "actor_roles, claim_snapshot, auth_source, is_dev_auth, event_payload, event_domain, "
            "event_version, actor_ref_kind, request_id, correlation_id, invalidation_cause_event_id, "
            "invalidation_target_kind, invalidation_target_ref, reason, before_facts, after_facts) "
            "values (:id, 'authority_invalidation', :id, "
            "'AuthorityInvalidationRequested', 'workstream:system:bootstrap', '[]', '{}', "
            "'local_authority', false, '{}', 'authority', 1, 'system_principal', :request_id, "
            ":correlation_id, :cause_id, 'actor_profile', :target_ref, "
            "'authority_state_changed', '{\"effective\": true}', '{\"effective\": false}')"
        )
        for cause_id in (str(uuid4()), legacy_id):
            with pytest.raises(IntegrityError):
                await session.execute(
                    invalidation_insert,
                    {
                        "id": str(uuid4()),
                        "request_id": str(uuid4()),
                        "correlation_id": str(uuid4()),
                        "cause_id": cause_id,
                        "target_ref": str(uuid4()),
                    },
                )
            await session.rollback()
        self_id = str(uuid4())
        with pytest.raises(IntegrityError):
            await session.execute(
                invalidation_insert,
                {
                    "id": self_id,
                    "request_id": str(uuid4()),
                    "correlation_id": str(uuid4()),
                    "cause_id": self_id,
                    "target_ref": str(uuid4()),
                },
            )
        await session.rollback()
