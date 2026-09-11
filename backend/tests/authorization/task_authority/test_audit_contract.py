"""Task lifecycle evidence has closed transitions and exact decision references."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.audit.schemas import (
    ActorReferenceKind, AuthorityAuditEventInput, AuthorityEventType,
    LifecycleAuditEntityType as Entity,
    LifecycleAuditEventInput,
    LifecycleAuditEventType as Event,
    LifecycleAuditReason as Reason,
    LifecycleAuditReferenceKind as Reference,
)
from app.modules.authorization.catalogue import (
    ACTION_DEFINITIONS, ActionAvailability, ActionId, PermissionId,
)
from tests.authorization.catalogue_fixtures import AUDIT_ALLOWED_ACTION_VALUES
from tests.test_audit import _authority_input


def test_action_aware_audit_input_enforces_mapping_and_action_availability() -> None:
    denied = _authority_input(
        AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
        permission_id="artifact.binding.read",
        action_id="artifact.binding.read",
        denial_code="permission_not_granted",
    )
    assert (denied.action_id, denied.permission_id) == (ActionId.ARTIFACT_BINDING_READ, PermissionId.ARTIFACT_BINDING_READ)
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
    assert {action.value for action in allowed_action_ids} == AUDIT_ALLOWED_ACTION_VALUES
    artifact_allowed = _authority_input(
        AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
        permission_id=PermissionId.ARTIFACT_VERIFICATION_EXECUTE,
        action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
        after_facts={"allowed": True, "resource_context_digest": "sha256:" + "a" * 64},
    )
    assert artifact_allowed.after_facts["resource_context_digest"] == "sha256:" + "a" * 64
    with pytest.raises(TypeError, match="invalid authority audit input"):
        _authority_input(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
            permission_id=PermissionId.ARTIFACT_VERIFICATION_EXECUTE,
            action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
            after_facts={"allowed": True, "resource_context_digest": "not-a-digest"},
        )
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
            permission_id=PermissionId.ACTOR_PROFILE_READ_SELF,
            action_id=ActionId.ACTOR_PROFILE_READ_SELF,
            reason="authorization_policy_denial",
            denial_code="permission_not_granted",
        )


def event_fields():
    task_id = uuid4()
    return dict(
        event_id=uuid4(),
        entity_type=Entity.TASK,
        entity_id=task_id,
        event_type=Event.TASK_CLAIMED,
        actor_id=uuid4(),
        reason=Reason.STATE_CHANGED,
        from_status="ready",
        to_status="claimed",
        references={
            Reference.TASK: task_id,
            Reference.PROJECT: uuid4(),
            Reference.ASSIGNMENT: uuid4(),
            Reference.AUTHORIZATION_DECISION: uuid4(),
        },
    )


@pytest.mark.parametrize(
    "event,before,after,reason",
    [
        (Event.TASK_CLAIMED, "ready", "claimed", None),
        (Event.TASK_STARTED, "claimed", "in_progress", "Begin assigned work"),
        (Event.TASK_START_OVERRIDDEN, "claimed", "in_progress", "Authorized operator intervention"),
    ],
)
def test_task_event_preserves_exact_transition_and_reason(event, before, after, reason):
    value = LifecycleAuditEventInput(
        **(
            event_fields()
            | dict(
                event_type=event,
                from_status=before,
                to_status=after,
                task_reason=reason,
            )
        )
    )
    assert value.task_reason == reason
    assert value.event_type is event
    assert value.references[Reference.AUTHORIZATION_DECISION]


@pytest.mark.parametrize(
    "change",
    [
        {"to_status": "in_progress"},
        {"from_status": "claimed"},
        {"task_reason": " "},
        {"task_reason": "x" * 1001},
        {
            "event_type": Event.TASK_START_OVERRIDDEN,
            "from_status": "claimed",
            "to_status": "in_progress",
        },
    ],
)
def test_task_event_rejects_wrong_transition_or_unbounded_reason(change):
    with pytest.raises(ValidationError):
        LifecycleAuditEventInput(**(event_fields() | change))


@pytest.mark.parametrize("reference", [Reference.AUTHORIZATION_DECISION, Reference.ASSIGNMENT])
def test_task_event_requires_assignment_and_authorization_evidence(reference):
    fields = event_fields()
    fields["references"].pop(reference)
    with pytest.raises(ValidationError, match="exact canonical references"):
        LifecycleAuditEventInput(**fields)
