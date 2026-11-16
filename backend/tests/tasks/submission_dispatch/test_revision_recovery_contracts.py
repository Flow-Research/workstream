"""Exact fixed-service recovery authority, distinct from human PM repair."""

import pytest

from app.core.identifiers import new_record_id
from app.modules.audit.schemas import (
    LifecycleAuditEntityType, LifecycleAuditEventInput, LifecycleAuditEventType,
    LifecycleAuditReason, LifecycleAuditReferenceKind,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.audit_targets import project_authority_audit_target
from app.modules.authorization.domain.prepared_service import fixed_service_resource_matches
from app.modules.authorization.domain.revision_recovery import (
    RevisionRecoveryResourceContext, parse_revision_recovery_binding,
)
from app.modules.tasks.api.revision_recovery import RECOVERY_REASON


def _resource():
    manifest = new_record_id()
    contributor = new_record_id()
    return RevisionRecoveryResourceContext(
        resource_id=new_record_id(), scope_project_id=new_record_id(),
        actor_profile_id=new_record_id(), identity_link_id=new_record_id(),
        task_status="needs_revision", assigned_to=contributor,
        assignment_id=new_record_id(), assignment_contributor_id=contributor,
        locked_context_hash="sha256:" + "a" * 64,
        reason=RECOVERY_REASON, idempotency_key=manifest,
        request_digest="sha256:" + "b" * 64,
        revision_routing_manifest_id=manifest,
    )


def test_recovery_authority_binds_only_exact_service_source():
    resource = _resource()
    assert project_authority_audit_target(resource, ActionId.TASK_REVISION_RECOVER) == (
        str(resource.scope_project_id), "project", str(resource.scope_project_id),
        "project", str(resource.scope_project_id),
    )
    decoded = parse_revision_recovery_binding(
        ActionId.TASK_REVISION_RECOVER, resource.model_dump(mode="json"), ValueError,
    )
    assert decoded == resource
    assert fixed_service_resource_matches(
        ActionId.TASK_REVISION_RECOVER, resource, resource.scope_project_id,
        None, None, None,
        actor_profile_id=resource.actor_profile_id, identity_link_id=resource.identity_link_id,
    ) is True
    assert fixed_service_resource_matches(
        ActionId.TASK_REVISION_RECOVER, resource,
        new_record_id(), None, None, None,
        actor_profile_id=resource.actor_profile_id, identity_link_id=resource.identity_link_id,
    ) is False
    for change in (
        {"reason": "ordinary PM repair"},
        {"idempotency_key": str(new_record_id())},
        {"revision_routing_manifest_id": None},
        {"assigned_to": str(new_record_id())},
        {"revision_preparation_id": str(new_record_id())},
    ):
        with pytest.raises(ValueError):
            parse_revision_recovery_binding(
                ActionId.TASK_REVISION_RECOVER,
                resource.model_dump(mode="json") | change, ValueError,
            )
    assert parse_revision_recovery_binding(
        ActionId.TASK_REVISION_EXPIRE, resource.model_dump(mode="json"), ValueError,
    ) is None


def test_existing_preparation_recovery_uses_its_exact_natural_key():
    resource = _resource()
    preparation_id = new_record_id()
    value = resource.model_dump(mode="json") | {
        "revision_preparation_id": str(preparation_id),
        "revision_preparation_sha256": "sha256:" + "c" * 64,
        "idempotency_key": str(preparation_id),
    }
    decoded = parse_revision_recovery_binding(ActionId.TASK_REVISION_RECOVER, value, ValueError)
    assert decoded.revision_preparation_id == decoded.idempotency_key == preparation_id
    for key in (str(resource.revision_routing_manifest_id), str(new_record_id())):
        with pytest.raises(ValueError, match="invalid revision recovery authority"):
            parse_revision_recovery_binding(
                ActionId.TASK_REVISION_RECOVER, value | {"idempotency_key": key}, ValueError,
            )


def test_recovery_audit_pairs_service_digest_with_expiry_event_only():
    task = new_record_id()
    references = {
        LifecycleAuditReferenceKind.PROJECT: new_record_id(),
        LifecycleAuditReferenceKind.TASK: task,
        LifecycleAuditReferenceKind.ASSIGNMENT: new_record_id(),
        LifecycleAuditReferenceKind.SUBMISSION: new_record_id(),
        LifecycleAuditReferenceKind.ROUTING_MANIFEST: new_record_id(),
        LifecycleAuditReferenceKind.REVISION_PREPARATION: new_record_id(),
        LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: new_record_id(),
    }
    fields = dict(
        event_id=new_record_id(), entity_type=LifecycleAuditEntityType.TASK,
        entity_id=task,
        event_type=LifecycleAuditEventType.TASK_REVISION_CONTEXT_REPAIRED,
        actor_id=new_record_id(), reason=LifecycleAuditReason.FACT_RECORDED,
        task_reason=RECOVERY_REASON,
    )
    assert LifecycleAuditEventInput(**fields, references=references).authorization_resource_digest is None
    service_references = references | {LifecycleAuditReferenceKind.OUTBOX_EVENT: new_record_id()}
    digest = "sha256:" + "a" * 64
    assert LifecycleAuditEventInput(
        **fields, references=service_references, authorization_resource_digest=digest,
    ).authorization_resource_digest == digest
    with pytest.raises(ValueError, match="paired authority"):
        LifecycleAuditEventInput(**fields, references=references, authorization_resource_digest=digest)
    with pytest.raises(ValueError, match="paired authority"):
        LifecycleAuditEventInput(**fields, references=service_references)
