"""Approved AUTH composition-root exposure for projection ports."""

from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
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
