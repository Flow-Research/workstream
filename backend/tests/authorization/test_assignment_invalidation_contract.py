"""Exact feature registration and canonical whole-resource commitment."""

from copy import copy, deepcopy
import pickle
from uuid import uuid4

import pytest

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import (
    ACTION_BY_ID, SERVICE_ACTIONS_BY_IDENTITY, ActionAvailability, ActionId,
    ActionOwner, PermissionId, _index_service_actions,
)
from app.modules.authorization.domain.assignment_invalidation import assignment_invalidation_resource
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.authorization.policy import ADMIN_ROLE_PERMISSIONS
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationAuthorityFacts, AssignmentInvalidationTarget, PreparedAssignmentInvalidation,
)


def facts():
    return AssignmentInvalidationAuthorityFacts(
        target=AssignmentInvalidationTarget(**{key: uuid4() for key in AssignmentInvalidationTarget.model_fields}),
        cause_event_id=uuid4(), delivery_event_id=uuid4(), delivery_generation=1,
        cause_digest="sha256:" + "a" * 64, invocation_digest="sha256:" + "b" * 64,
        task_status="claimed", locked_context_hash="sha256:" + "c" * 64,
    )


def substitutions(value):
    for key in AssignmentInvalidationTarget.model_fields:
        yield key, value.model_copy(update={"target": value.target.model_copy(update={key: uuid4()})})
    for key, replacement in {
        "cause_event_id": uuid4(), "delivery_event_id": uuid4(), "delivery_generation": 2,
        "cause_digest": "sha256:" + "d" * 64, "invocation_digest": "sha256:" + "e" * 64,
        "task_status": "in_progress", "locked_context_hash": "sha256:" + "f" * 64,
    }.items():
        yield key, value.model_copy(update={key: replacement})


def test_reconciler_registration_is_exact():
    action = ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE
    row = ACTION_BY_ID[action]
    assert (row.permission_id, row.owner, row.availability) == (
        PermissionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE, ActionOwner.ARCH_03C1, ActionAvailability.ACTIVE,
    )
    assert SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.TASK_ASSIGNMENT_RECONCILER] == {action}
    assert all(row.permission_id not in rights for rights in ADMIN_ROLE_PERMISSIONS.values())
    for identity, actions in SERVICE_ACTIONS_BY_IDENTITY.items():
        if identity is not ServiceIdentity.TASK_ASSIGNMENT_RECONCILER:
            assert action not in actions
            changed = dict(SERVICE_ACTIONS_BY_IDENTITY)
            changed[identity] = actions | {action}
            with pytest.raises(RuntimeError, match="matrix row mismatch"):
                _index_service_actions(changed)


def test_reconciler_resource_binds_every_fact_and_revalidates_forged_values():
    value = facts()
    resource = assignment_invalidation_resource(value)
    assert resource.resource_type == "task_authority"
    digest = authorization_resource_digest(resource)
    for field, changed in substitutions(value):
        assert authorization_resource_digest(assignment_invalidation_resource(changed)) != digest, field
    for changed in (
        value.model_copy(update={"delivery_generation": True}),
        value.model_copy(update={"task_status": "submitted"}),
        value.model_copy(update={"target": value.target.model_copy(update={"task_id": "not-uuid"})}),
    ):
        with pytest.raises(ValueError):
            assignment_invalidation_resource(changed)


def test_reconciler_preparation_is_nominal_and_process_local():
    with pytest.raises(TypeError):
        PreparedAssignmentInvalidation()

    class NeverAuthorizes(PreparedAssignmentInvalidation):
        async def consume(self, facts):
            raise AssertionError("no test authority")

    for transfer in (copy, deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="process-local"):
            transfer(NeverAuthorizes())


async def test_malformed_reconciler_input_denies_before_database():
    from app.modules.authorization.assignment_invalidation_authorization import AssignmentInvalidationAuthorizationAdapter
    from app.modules.authorization.domain.assignment_invalidation import parse_assignment_invalidation_binding
    from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationUnavailable

    with pytest.raises(AssignmentInvalidationUnavailable, match="facts invalid"):
        async with AssignmentInvalidationAuthorizationAdapter(object()).prepare_assignment_invalidation(object()):
            raise AssertionError("malformed input reached preparation")
    with pytest.raises(ValueError, match="invalid assignment reconciliation authority"):
        parse_assignment_invalidation_binding(ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE, {}, ValueError)


def test_fixed_service_bindings_preserve_both_exact_contracts():
    from app.modules.authorization.domain.prepared_service import prepared_fixed_service_bindings

    resource = assignment_invalidation_resource(facts())
    assignment = prepared_fixed_service_bindings(
        ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE, resource.model_dump(mode="json"), ValueError,
    )
    assert assignment == {"assignment_invalidation_context": resource, "outbox_dispatch_digest": None, "post_submit_prepare_context": None}
    digest = "sha256:" + "a" * 64
    assert prepared_fixed_service_bindings(ActionId.OUTBOX_DISPATCH, {"outbox_dispatch_digest": digest}, ValueError) == {
        "assignment_invalidation_context": None, "outbox_dispatch_digest": digest, "post_submit_prepare_context": None,
    }
    assert prepared_fixed_service_bindings(ActionId.ACTOR_PROFILE_READ_SELF, {}, ValueError) == {
        "assignment_invalidation_context": None, "outbox_dispatch_digest": None, "post_submit_prepare_context": None,
    }
    for action, message in (
        (ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE, "invalid assignment reconciliation authority"),
        (ActionId.OUTBOX_DISPATCH, "invalid prepared outbox authority"),
    ):
        with pytest.raises(ValueError, match=message):
            prepared_fixed_service_bindings(action, {}, ValueError)


def test_public_resource_selector_preserves_uuid_and_stable_invalid_identity():
    from uuid import NAMESPACE_URL, uuid5
    from app.modules.authorization.api import authorization_resource_selector_id
    from app.modules.authorization import runtime

    valid = uuid4()
    assert authorization_resource_selector_id("project", str(valid)) == valid
    assert authorization_resource_selector_id("project", "bad-id") == uuid5(
        NAMESPACE_URL, "workstream:project-selector:bad-id",
    )
    assert authorization_resource_selector_id("project", "bad-id") != authorization_resource_selector_id("task", "bad-id")
    assert not hasattr(runtime, "authorization_resource_selector_id")


def test_assignment_generation_matches_outbox_bounds():
    from app.modules.tasks.api.assignment_invalidation import assignment_invalidation_resource_digest

    value = facts()
    maximum = value.model_copy(update={"delivery_generation": 2147483647})
    assert assignment_invalidation_resource(maximum).facts.delivery_generation == 2147483647
    assert assignment_invalidation_resource_digest(maximum).startswith("sha256:")
    for generation in (0, 2147483648):
        changed = value.model_copy(update={"delivery_generation": generation})
        with pytest.raises(ValueError):
            assignment_invalidation_resource(changed)
        with pytest.raises(ValueError):
            assignment_invalidation_resource_digest(changed)
