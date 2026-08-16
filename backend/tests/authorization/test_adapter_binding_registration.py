"""CP01A registration and CP01C fact-correction proof."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationDenialCode,
    AuthorizationDenied,
    IdentityLinkStatus,
    ProjectReadResourceContext,
    ServiceAuthorizationContext,
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


@pytest.mark.asyncio
async def test_target_only_identity_denies_without_matrix_key_error() -> None:
    actor_id, project_id = uuid4(), uuid4()
    context = ServiceAuthorizationContext(
        actor_profile_id=actor_id,
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=ServiceIdentity.COMPENSATION_ADAPTER,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    service = AuthorizationService(object(), context)  # type: ignore[arg-type]
    service._audit = SimpleNamespace(add_authority_event=AsyncMock())  # type: ignore[assignment]
    resource = ProjectReadResourceContext(
        resource_type="project",
        resource_id=project_id,
        scope_project_id=project_id,
        project_exists=True,
        project_status="active",
    )

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.PROJECT_READ, resource)

    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED


def test_cp01c_public_facts_are_immutable_and_validate_lifecycle_state() -> None:
    project_id = uuid4()
    binding_id = uuid4()
    read = AdapterBindingReadFacts(project_id=project_id, adapter_binding_id=binding_id)
    with pytest.raises(FrozenInstanceError):
        read.project_id = uuid4()  # type: ignore[misc]
    with pytest.raises(ValueError, match="suspension requires active"):
        AdapterBindingSuspendFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            expected_lifecycle_version=1,
            expected_status="suspended",
        )
    with pytest.raises(ValueError, match="resumption requires suspended"):
        AdapterBindingResumeFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            expected_lifecycle_version=2,
            expected_status="active",
        )
    for version in (True, 0, -1, 1.5, "1"):
        with pytest.raises(ValueError, match="expected_lifecycle_version"):
            AdapterBindingSuspendFacts(
                project_id=project_id,
                adapter_binding_id=binding_id,
                expected_lifecycle_version=version,  # type: ignore[arg-type]
            )
        with pytest.raises(ValueError, match="expected_lifecycle_version"):
            AdapterBindingResumeFacts(
                project_id=project_id,
                adapter_binding_id=binding_id,
                expected_lifecycle_version=version,  # type: ignore[arg-type]
            )
    for route_key in ("1adapter", "adapter..secret", "a" * 121, "secret route"):
        with pytest.raises(ValueError, match="route_key must be canonical"):
            AdapterBindingCreateFacts(
                project_id=project_id,
                adapter_binding_id=binding_id,
                instrument_type="money",
                adapter_actor_id=uuid4(),
                route_key=route_key,
            )
    with pytest.raises(ValueError, match="adapter_binding_id must be a UUID"):
        AdapterBindingCreateFacts(
            project_id=project_id,
            adapter_binding_id=str(binding_id),  # type: ignore[arg-type]
            instrument_type="money",
            adapter_actor_id=uuid4(),
            route_key="adapter.primary",
        )
    with pytest.raises(ValueError, match="instrument_type must be a bounded canonical token"):
        AdapterBindingCreateFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            instrument_type=" ",
            adapter_actor_id=uuid4(),
            route_key="adapter.primary",
        )

    actor_id = uuid4()
    create = AdapterBindingCreateFacts(
        project_id=project_id,
        adapter_binding_id=binding_id,
        instrument_type="money",
        adapter_actor_id=actor_id,
        route_key="a" * 120,
    )
    assert create.adapter_binding_id == binding_id
    assert create.adapter_actor_id == actor_id
    assert create.instrument_type == "money"
    assert create.route_key == "a" * 120
    assert not hasattr(create, "unit")


def test_cp01c_digest_is_deterministic_and_action_domain_separated() -> None:
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
        expected_lifecycle_version=1,
    )
    suspend_digest = adapter_binding_resource_digest(
        action_id("compensation.adapter_binding.suspend"), suspend
    )
    assert suspend_digest != first
    assert suspend_digest != adapter_binding_resource_digest(
        action_id("compensation.adapter_binding.suspend"),
        AdapterBindingSuspendFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            expected_lifecycle_version=2,
        ),
    )
    resume_action = action_id("compensation.adapter_binding.resume")
    assert adapter_binding_resource_digest(
        resume_action,
        AdapterBindingResumeFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            expected_lifecycle_version=1,
        ),
    ) != adapter_binding_resource_digest(
        resume_action,
        AdapterBindingResumeFacts(
            project_id=project_id,
            adapter_binding_id=binding_id,
            expected_lifecycle_version=2,
        ),
    )
    with pytest.raises(ValueError, match="does not match"):
        adapter_binding_resource_digest(read_action, suspend)

    create_action = action_id("compensation.adapter_binding.create")
    actor_id = uuid4()
    create = AdapterBindingCreateFacts(
        project_id=project_id,
        adapter_binding_id=binding_id,
        instrument_type="money",
        adapter_actor_id=actor_id,
        route_key="adapter.primary",
    )
    other_binding = AdapterBindingCreateFacts(
        project_id=project_id,
        adapter_binding_id=uuid4(),
        instrument_type="money",
        adapter_actor_id=actor_id,
        route_key="adapter.primary",
    )
    assert adapter_binding_resource_digest(
        create_action, create
    ) != adapter_binding_resource_digest(create_action, other_binding)
    other_instrument_type = AdapterBindingCreateFacts(
        project_id=project_id,
        adapter_binding_id=binding_id,
        instrument_type="project_points",
        adapter_actor_id=actor_id,
        route_key="adapter.primary",
    )
    assert adapter_binding_resource_digest(
        create_action, create
    ) != adapter_binding_resource_digest(create_action, other_instrument_type)


def test_cp01c_rejects_retired_create_fact_shape() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument 'unit'"):
        AdapterBindingCreateFacts(
            project_id=uuid4(),
            adapter_binding_id=uuid4(),
            instrument_type="money",
            unit="USD",  # type: ignore[call-arg]
            adapter_actor_id=uuid4(),
            route_key="adapter.primary",
        )
    with pytest.raises(TypeError, match="unexpected keyword argument 'instrument'"):
        AdapterBindingCreateFacts(
            project_id=uuid4(),
            adapter_binding_id=uuid4(),
            instrument="money",  # type: ignore[call-arg]
            adapter_actor_id=uuid4(),
            route_key="adapter.primary",
        )


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
