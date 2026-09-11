"""Dependency-safe public API for the TASKS business module."""

from app.modules.tasks.api.transition_audit import TaskTransitionAuditPort, TaskTransitionFacts

from app.modules.tasks.api.authorization import (
    TaskAuthorizationPort,
    TaskAuthorityDenied,
    TaskAuthorityFacts,
    TaskAuthorityOperation,
)

from app.modules.tasks.api.submission_context import (
    SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
    TaskSubmissionContextFailure,
    TaskSubmissionContextKind,
    TaskSubmissionContextPort,
    TaskSubmissionContextRequest,
    TaskSubmissionContextStatus,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.api.submission_command import (
    SubmissionCreationAuthorizationPort,
    SubmissionCreationAuthorityFacts,
    SubmissionCreationPreparationFacts,
    SubmissionCreationCommand,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    SubmissionCreationUnavailable,
    SubmissionArtifactAdmissionPort,
    SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult,
)

__all__ = (
    "TaskTransitionAuditPort",
    "TaskTransitionFacts",
    "TaskAuthorizationPort",
    "TaskAuthorityDenied",
    "TaskAuthorityFacts",
    "TaskAuthorityOperation",
    "SubmissionPredecessorFacts",
    "TaskLockedProjectContextReferences",
    "TaskSubmissionContextFacts",
    "TaskSubmissionContextFailure",
    "TaskSubmissionContextKind",
    "TaskSubmissionContextPort",
    "TaskSubmissionContextRequest",
    "TaskSubmissionContextStatus",
    "TaskSubmissionContextUnavailable",
    "SubmissionCreationAuthorizationPort",
    "SubmissionCreationAuthorityFacts",
    "SubmissionCreationPreparationFacts",
    "SubmissionCreationCommand",
    "SubmissionCreationRequest",
    "SubmissionCreationResult",
    "SubmissionCreationUnavailable",
    "SubmissionArtifactAdmissionPort",
    "SubmissionArtifactAdmissionRequest",
    "SubmissionArtifactAdmissionResult",
)
