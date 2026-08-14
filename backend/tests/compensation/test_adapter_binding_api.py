"""Focused public-contract proof for hidden adapter-binding behavior."""

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.modules.compensation.api import (
    AdapterBindingCreateRequest,
    AdapterBindingReadRequest,
    AdapterBindingResumeRequest,
    AdapterBindingSuspendRequest,
)


@pytest.mark.parametrize(
    "route_key", ("", "1adapter", "adapter/path", "adapter..secret", "ü", "a" * 121)
)
def test_create_request_rejects_noncanonical_route_key(route_key: str) -> None:
    with pytest.raises(ValueError, match="route_key"):
        AdapterBindingCreateRequest(
            operation_id=uuid4(),
            actor_profile_id=uuid4(),
            project_id=uuid4(),
            instrument_type="money",
            adapter_actor_id=uuid4(),
            route_key=route_key,
        )


def test_mutation_requests_are_immutable_and_require_positive_version() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        AdapterBindingResumeRequest(
            operation_id=uuid4(),
            actor_profile_id=uuid4(),
            project_id=uuid4(),
            adapter_binding_id=uuid4(),
            expected_lifecycle_version=0,
        )
    request = AdapterBindingResumeRequest(
        operation_id=uuid4(),
        actor_profile_id=uuid4(),
        project_id=uuid4(),
        adapter_binding_id=uuid4(),
        expected_lifecycle_version=1,
    )
    with pytest.raises(FrozenInstanceError):
        request.expected_lifecycle_version = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("request_type", "values"),
    (
        (AdapterBindingCreateRequest, {"operation_id": "bad", "instrument_type": "money", "adapter_actor_id": uuid4(), "route_key": "adapter.primary"}),
        (AdapterBindingReadRequest, {"adapter_binding_id": "bad"}),
        (AdapterBindingSuspendRequest, {"operation_id": uuid4(), "adapter_binding_id": "bad", "expected_lifecycle_version": 1}),
        (AdapterBindingResumeRequest, {"operation_id": uuid4(), "adapter_binding_id": "bad", "expected_lifecycle_version": 1}),
    ),
)
def test_public_requests_reject_non_uuid_selectors(request_type, values) -> None:
    with pytest.raises(ValueError, match="must be a UUID"):
        request_type(actor_profile_id=uuid4(), project_id=uuid4(), **values)


def test_create_request_rejects_unknown_instrument_type() -> None:
    with pytest.raises(ValueError, match="instrument_type"):
        AdapterBindingCreateRequest(
            operation_id=uuid4(), actor_profile_id=uuid4(), project_id=uuid4(),
            instrument_type="credits",  # type: ignore[arg-type]
            adapter_actor_id=uuid4(), route_key="adapter.primary",
        )
