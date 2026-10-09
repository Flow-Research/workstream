"""Dependency-safe public API for the TASKS business module."""

from app.modules.tasks.api.accepted_effects import (
    TaskAcceptedEffectsFence,
    TaskAcceptedEffectsPort,
    TaskAcceptedPreparation,
    TaskAcceptedEffectsRequest,
    TaskAcceptedEffectsResult,
    TaskAcceptedEffectsUnavailable,
)
from app.modules.tasks.api.post_submit_routing import (
    TaskPostSubmitManifestFacts, TaskPostSubmitSourceProposal, TaskRoutingSourcePreparation,
    task_post_submit_source_digest,
    TaskRoutingSelection, TaskRoutingRequestFacts, task_routing_request_digest,
)

from app.modules.tasks.api.transition_audit import (
    TaskPolicyLineage,
    TaskTransitionAuditPort,
    TaskTransitionFacts,
)

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
)

from app.modules.tasks.api.ready_queue import (
    TaskQueueCursor,
    ReadyTaskPage,
    ReadyTaskQueuePort,
    TaskQueueRequest,
    ReadyTaskSummary,
    LockedTaskCompensationUnavailable,
    TaskCompensationAward,
    TaskCompensationTerms,
    TaskContributionTerms,
)

from app.modules.tasks.api.management_queue import (
    ManagementTaskPage,
    ManagementTaskQueuePort,
    ManagementTaskSummary,
    OperationalTaskPage,
    OperationalTaskQueuePort,
    OperationalTaskSummary,
)

from app.modules.tasks.api.task_detail import (
    ContributorTaskDetail,
    ContributorTaskDetailRequest,
    ContributorTaskDetailPort,
    ManagementTaskDetail,
    ManagementTaskDetailRequest,
    ManagementTaskDetailPort,
)

from app.modules.tasks.api.audit_evidence import (
    AuditTaskEvidence,
    AuditTaskEvidencePage,
    AuditTaskEvidencePort,
    AuditTaskEvidenceRequest,
    TaskEvidenceCursor,
    TaskEvidenceInvalid,
)

__all__ = (
    "AuditTaskEvidence",
    "AuditTaskEvidencePage",
    "AuditTaskEvidencePort",
    "AuditTaskEvidenceRequest",
    "TaskEvidenceCursor",
    "TaskEvidenceInvalid",
    "ContributorTaskDetail",
    "ContributorTaskDetailRequest",
    "ContributorTaskDetailPort",
    "ManagementTaskDetail",
    "ManagementTaskDetailRequest",
    "ManagementTaskDetailPort",
    "ManagementTaskPage",
    "ManagementTaskQueuePort",
    "ManagementTaskSummary",
    "OperationalTaskPage",
    "OperationalTaskQueuePort",
    "OperationalTaskSummary",
    "TaskAcceptedEffectsPort",
    "TaskAcceptedEffectsFence",
    "TaskAcceptedPreparation",
    "TaskAcceptedEffectsRequest",
    "TaskAcceptedEffectsResult",
    "TaskAcceptedEffectsUnavailable",
    "TaskPolicyLineage",
    "TaskPostSubmitManifestFacts", "TaskPostSubmitSourceProposal", "TaskRoutingSourcePreparation",
    "task_post_submit_source_digest",
    "TaskRoutingSelection",
    "TaskRoutingRequestFacts",
    "task_routing_request_digest",
    "TaskQueueCursor",
    "ReadyTaskPage",
    "ReadyTaskQueuePort",
    "TaskQueueRequest",
    "ReadyTaskSummary",
    "LockedTaskCompensationUnavailable",
    "TaskCompensationAward",
    "TaskCompensationTerms",
    "TaskContributionTerms",
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
)
