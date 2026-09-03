"""Approved AUTH composition-root exposure for projection ports."""

from unittest.mock import Mock

import app.adapters.auth as auth_adapters
from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
import pytest
from app.modules.authorization.guide_compilation_projections import (
    ArtifactPolicyProjectionAuthorization,
    GuideSufficiencyProjectionAuthorization,
)


def test_projection_factories_are_exposed_only_by_auth_composition_root() -> None:
    session = object()
    assert isinstance(
        guide_sufficiency_projection_authorization(session),  # type: ignore[arg-type]
        GuideSufficiencyProjectionAuthorization,
    )
    assert isinstance(
        artifact_policy_projection_authorization(session),  # type: ignore[arg-type]
        ArtifactPolicyProjectionAuthorization,
    )


def test_compensation_factory_composes_its_existing_auth_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, context = object(), object()
    repository, kernel, prepared, port, adapter = (object() for _ in range(5))
    repository_factory = Mock(return_value=repository)
    kernel_factory = Mock(return_value=kernel)
    prepared_factory = Mock(return_value=prepared)
    port_factory = Mock(return_value=port)
    adapter_factory = Mock(return_value=adapter)
    monkeypatch.setattr(auth_adapters, "AdminAuthorizationRepository", repository_factory)
    monkeypatch.setattr(auth_adapters, "AuthorizationService", kernel_factory)
    monkeypatch.setattr(auth_adapters, "PreparedAuthorizationService", prepared_factory)
    monkeypatch.setattr(auth_adapters, "AdapterBindingAuthorizationAdapter", port_factory)
    monkeypatch.setattr(auth_adapters, "CompensationAdapterBindingAuthorization", adapter_factory)

    assert auth_adapters.compensation_adapter_binding_authorization(  # type: ignore[arg-type]
        session, context
    ) is adapter
    repository_factory.assert_called_once_with(session)
    kernel_factory.assert_called_once_with(session, context, admin_repository=repository)
    prepared_factory.assert_called_once_with(session, context, kernel, repository)
    port_factory.assert_called_once_with(kernel, prepared)
    adapter_factory.assert_called_once_with(port)
