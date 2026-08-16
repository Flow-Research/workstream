"""Public closed identity vocabulary owned by ACTORS."""

from enum import StrEnum, unique


@unique
class ServiceIdentity(StrEnum):
    """Stable local names for the closed v0.1 service principals."""

    ARTIFACT_VERIFIER = "workstream.artifact.verifier"
    ARTIFACT_PUT_RESOLVER = "workstream.artifact.put_resolver"
    ARTIFACT_SCHEDULER = "workstream.artifact.scheduler"
    ARTIFACT_BINDING = "workstream.artifact.binding"
    ARTIFACT_GUIDE_READER = "workstream.artifact.guide_reader"
    ARTIFACT_MATERIALIZER = "workstream.artifact.materializer"
    ARTIFACT_CHECKER_OUTPUT = "workstream.artifact.checker_output"
    PROJECT_SETUP = "workstream.project.setup"
    REVIEW_PREFERENCE_EXPIRY = "workstream.review.preference_expiry"
    REVIEW_LEASE_EXPIRY = "workstream.review.lease_expiry"
    REVIEW_AUTHORITY_INVALIDATION_RECONCILIATION = (
        "workstream.review.authority_invalidation_reconciliation"
    )
    REVIEW_RECONCILIATION = "workstream.review.reconciliation"
    REVIEW_ARTIFACT_REFERENCE_RECONCILIATION = (
        "workstream.review.artifact_reference_reconciliation"
    )
    REVIEW_PROJECTION = "workstream.review.projection"
    COMPENSATION_ADAPTER = "workstream.compensation.adapter"


SERVICE_IDENTITIES = frozenset(ServiceIdentity)
SERVICE_IDENTITY_VALUES = tuple(identity.value for identity in ServiceIdentity)

__all__ = (
    "SERVICE_IDENTITIES",
    "SERVICE_IDENTITY_VALUES",
    "ServiceIdentity",
)
