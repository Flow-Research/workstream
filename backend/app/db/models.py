"""Register the complete model graph for runtime database composition and Alembic."""

from app.modules.actors.models import (  # noqa: F401
    ActorIdentityLink,
    ActorProfile,
    LegacyActorIdentity,
    LegacyWorkflowEligibility,
)
from app.modules.api_controls.models import ApiRateControlCounter  # noqa: F401
from app.modules.artifacts.models import (  # noqa: F401
    ArtifactBinding,
    ArtifactContent,
    GuideSourceArtifactBinding,
    GuideSourceArtifactIncident,
    GuideSourceExtractedContent,
    GuideSourceExtractionAttempt,
    GuideSourceExtractionRetryBudget,
    GuideSourceExtractionUsage,
    GuideSourceFormatClassification,
    ArtifactOperationReceipt,
    ArtifactReplica,
    ArtifactRecoveryAttempt,
    PreSubmitEvidenceResult,
    PreSubmitEvidenceSet,
    SubmissionBundleDurableIntent,
)
from app.modules.authorization.models import (  # noqa: F401
    AdminRoleGrant,
    AuthorityControl,
    AuthorityIdempotencyRecord,
    ProjectRoleGrant,
    ProjectRoleQualificationSnapshot,
)
from app.modules.checkers.models import (  # noqa: F401
    CheckerResult,
    CheckerRun,
    CheckerSubmissionFence,
    ExternalCheckerRegistryEntryRecord,
)
from app.modules.compensation.models import (  # noqa: F401
    CompensationAdapterBindingLifecycleEvent,
    ProjectCompensationAdapterBinding,
)
from app.modules.contributions.models import (  # noqa: F401
    ContributionAwardDefinition,
    ContributionPolicy,
    ContributionPolicyVersion,
    ContributionPolicyLifecycleEvent,
    ContributionRule,
    Iso4217CurrencyCode,
    ProjectCompensationUnit,
)
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent  # noqa: F401
from app.modules.projects.models import (  # noqa: F401
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSufficiencyReport,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
    ProjectSetupRun,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.guide_compilation.models import (  # noqa: F401
    ProjectGuideSetupFinalization,
    ProjectGuideComponentProjectionOperation,
    ProjectGuideCompilation,
    ProjectGuideCompilationAttempt,
)
from app.modules.projects.guide_compilation.models import (  # noqa: F401
    ProjectGuideProposalApproval,
    ProjectGuideProposalCorrection,
)
from app.modules.reviews.models import (  # noqa: F401
    ReviewAdmissionIdempotencyRecord,
    ReviewLease,
    ReviewQueueEntry,
)
from app.modules.tasks.models import (  # noqa: F401
    AuditEvent,
    EvidenceItem,
    Submission,
    TaskAssignment,
    WorkstreamTask,
)
from app.modules.tasks.post_submit_routing.models import (  # noqa: F401
    TaskPostSubmitRoutingManifest,
    TaskRoutingRequest,
)

from app.modules.projects.guide_compilation.models import (  # noqa: F401
    ProjectGuideRuntimeAllocation, ProjectGuideDocumentAccess,
)

from app.modules.projects.post_policy.models import PostPolicyOperation  # noqa: F401

from app.modules.reviews.packet.models import ReviewPacketManifest, ReviewPacketGuideItem  # noqa: F401

from app.modules.reviews.decision.models import (  # noqa: F401
    FindingResolution,
    Review,
    ReviewDecisionRequest,
    ReviewFinding,
)

from app.modules.reviews.acceptance.models import FinalAcceptance  # noqa: F401

from app.modules.contributions.records.models import ContributionRecord  # noqa: F401
from app.modules.compensation.awards.models import CompensationAward  # noqa: F401

from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl  # noqa: F401
