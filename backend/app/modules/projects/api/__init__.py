"""Dependency-safe public API for the PROJECTS business module."""

from app.modules.projects.api.compensation_binding import (
    ProjectCompensationBindingEligibilityFacts,
    ProjectCompensationBindingEligibilityPort,
    ProjectCompensationBindingUnavailable,
)
from app.modules.projects.api.contribution_policy import (
    ProjectContributionPolicyEligibilityFacts,
    ProjectContributionPolicyEligibilityPort,
    ProjectContributionPolicyUnavailable,
)
from app.modules.projects.api.guide_compilation import (
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideCompilationExecutionError,
    ProjectGuideCompilationExecutionErrorCode,
    ProjectGuideCompilationExecutionPort,
    ProjectGuideCompilationExecutionResult,
)
from app.modules.projects.api.guide_compilation_projections import (
    ArtifactPolicyProjectionPort,
    GuideSufficiencyProjectionPort,
    ProjectGuideProjectionCommand,
    ProjectGuideProjectionComponent,
    ProjectGuideProjectionError,
    ProjectGuideProjectionErrorCode,
    ProjectGuideProjectionReceipt,
)
from app.modules.projects.api.locked_policy import (
    CanonicalJsonObject,
    ProjectLockedPolicyContextFacts,
    ProjectLockedPolicyContextPort,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
    ProjectLockedPolicyEffectiveStatus,
    ProjectLockedPolicyFailure,
    ProjectLockedPolicyGuideStatus,
    ProjectLockedPolicyPreSubmitStatus,
)

__all__ = (
    "CanonicalJsonObject",
    "ProjectCompensationBindingEligibilityFacts",
    "ProjectCompensationBindingEligibilityPort",
    "ProjectCompensationBindingUnavailable",
    "ProjectContributionPolicyEligibilityFacts",
    "ProjectContributionPolicyEligibilityPort",
    "ProjectContributionPolicyUnavailable",
    "ProjectGuideCompilationExecutionClassification",
    "ProjectGuideCompilationExecutionCommand",
    "ProjectGuideCompilationExecutionError",
    "ProjectGuideCompilationExecutionErrorCode",
    "ProjectGuideCompilationExecutionPort",
    "ProjectGuideCompilationExecutionResult",
    "ArtifactPolicyProjectionPort",
    "GuideSufficiencyProjectionPort",
    "ProjectGuideProjectionCommand",
    "ProjectGuideProjectionComponent",
    "ProjectGuideProjectionError",
    "ProjectGuideProjectionErrorCode",
    "ProjectGuideProjectionReceipt",
    "ProjectLockedPolicyContextFacts",
    "ProjectLockedPolicyContextPort",
    "ProjectLockedPolicyContextRequest",
    "ProjectLockedPolicyContextUnavailable",
    "ProjectLockedPolicyEffectiveStatus",
    "ProjectLockedPolicyFailure",
    "ProjectLockedPolicyGuideStatus",
    "ProjectLockedPolicyPreSubmitStatus",
)
