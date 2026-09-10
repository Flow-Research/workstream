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
    ProjectGuideSetupFinalizationCommand,
    ProjectGuideSetupFinalizationReceipt,
    ProjectGuideSetupFinalizationError,
    ProjectGuideSetupFinalizationPort,
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

from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

__all__ = (
    "project_guide_compilation_task_id",
    "ProjectGuideSetupFinalizationCommand",
    "ProjectGuideSetupFinalizationReceipt",
    "ProjectGuideSetupFinalizationError",
    "ProjectGuideSetupFinalizationPort",
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
