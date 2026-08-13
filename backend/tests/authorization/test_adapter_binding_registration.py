"""CP01A proof for planned adapter-binding AUTH registration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    AdapterBindingCreateFacts,
    AdapterBindingReadFacts,
    AdapterBindingResumeFacts,
    AdapterBindingSuspendFacts,
    action_id,
    adapter_binding_resource_digest,
)
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    SERVICE_ACTIONS_BY_IDENTITY,
    ActionAvailability,
    ActionId,
    ActionOwner,
    PermissionId,
    resolve_executable_action,
)

_ACTIONS = {
    ActionId.COMPENSATION_ADAPTER_BINDING_READ,
    ActionId.COMPENSATION_ADAPTER_BINDING_CREATE,
    ActionId.COMPENSATION_ADAPTER_BINDING_SUSPEND,
    ActionId.COMPENSATION_ADAPTER_BINDING_RESUME,
}


def test_cp01a_registers_only_exact_planned_binding_actions() -> None:
    for action in _ACTIONS:
        definition = ACTION_BY_ID[action]
        assert definition.permission_id is PermissionId.COMPENSATION_ADAPTER_BINDING_MANAGE
        assert definition.owner is ActionOwner.ARCH_CP01A
        assert definition.availability is ActionAvailability.PLANNED
        with pytest.raises(ValueError, match="authorization action is not active"):
            resolve_executable_action(action)

    assert "compensation.adapter_binding.retire" not in {item.value for item in ActionId}
    assert all(_ACTIONS.isdisjoint(actions) for actions in SERVICE_ACTIONS_BY_IDENTITY.values())


def test_cp01a_public_facts_are_immutable_and_validate_lifecycle_state() -> None:
    project_id = uuid4()
    binding_id = uuid4()
    read = AdapterBindingReadFacts(project_id=project_id, adapter_binding_id=binding_id)
    with pytest.raises(FrozenInstanceError):
        read.project_id = uuid4()  # type: ignore[misc]
    with pytest.raises(ValueError, match="suspension requires active"):
        AdapterBindingSuspendFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            expected_status="suspended",
        )
    with pytest.raises(ValueError, match="resumption requires suspended"):
        AdapterBindingResumeFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            expected_status="active",
        )
    with pytest.raises(ValueError, match="route_key must be"):
        AdapterBindingCreateFacts(
            project_id=project_id,
            instrument="money",
            unit="USD",
            adapter_actor_id=uuid4(),
            route_key="secret route with spaces",
        )


def test_cp01a_digest_is_deterministic_and_action_domain_separated() -> None:
    project_id = uuid4()
    binding_id = uuid4()
    read = AdapterBindingReadFacts(project_id=project_id, adapter_binding_id=binding_id)
    read_action = action_id("compensation.adapter_binding.read")
    first = adapter_binding_resource_digest(read_action, read)
    assert first == adapter_binding_resource_digest(read_action, read)
    assert first.startswith("sha256:") and len(first) == 71

    suspend = AdapterBindingSuspendFacts(
        project_id=project_id,
        adapter_binding_id=binding_id,
    )
    suspend_digest = adapter_binding_resource_digest(
        action_id("compensation.adapter_binding.suspend"), suspend
    )
    assert suspend_digest != first
    with pytest.raises(ValueError, match="does not match"):
        adapter_binding_resource_digest(read_action, suspend)


def test_cp01a_public_api_exports_exact_registration_surface() -> None:
    import app.modules.authorization.api as authorization_api

    expected = {
        "AdapterBindingCreateFacts",
        "AdapterBindingReadFacts",
        "AdapterBindingResumeFacts",
        "AdapterBindingSuspendFacts",
        "adapter_binding_resource_digest",
    }
    assert expected <= set(authorization_api.__all__)
    assert all(hasattr(authorization_api, name) for name in expected)
