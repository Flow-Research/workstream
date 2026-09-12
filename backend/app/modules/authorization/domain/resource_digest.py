"""Canonical exact-resource digests shared by kernel decisions and prepared bindings."""

from pydantic import BaseModel
from app.modules.authorization.domain.guide_proposals import GuideProposalResourceContext

from app.modules.authorization.domain.guide_compilation import persisted_result_digest
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectGuideProjectionResourceContext,
    projection_resource_digest,
)
from app.modules.authorization.domain.project_setup_finalization import (
    ProjectSetupFinalizationResourceContext,
    finalization_resource_digest,
)
from app.core.hashing import canonical_json_hash


def authorization_resource_digest(resource: BaseModel) -> str:
    """Preserve purpose-specific public digest parity and canonical fallback custody."""
    if type(resource) is GuideProposalResourceContext:
        resource.validate_identity()
        return resource.facts.digest
    if isinstance(resource, ProjectSetupFinalizationResourceContext):
        return finalization_resource_digest(resource)
    if isinstance(resource, ProjectGuideProjectionResourceContext):
        return projection_resource_digest(resource)
    if exact_digest := persisted_result_digest(resource):
        return exact_digest
    return canonical_json_hash(
        {"resource_context": resource.model_dump(mode="json", exclude_none=True)}
    )
