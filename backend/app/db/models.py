"""Import domain models so Alembic can discover metadata."""

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
    ArtifactOperationReceipt,
    ArtifactReplica,
    ArtifactUploadItem,
    ArtifactUploadSession,
)
from app.modules.authorization.models import (  # noqa: F401
    AdminRoleGrant,
    AuthorityControl,
    AuthorityIdempotencyRecord,
)
from app.modules.checkers.models import CheckerResult, CheckerRun  # noqa: F401
from app.modules.outbox.models import OutboxEvent  # noqa: F401
from app.modules.projects.models import (  # noqa: F401
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSufficiencyReport,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
    ProjectSetupRun,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.tasks.models import (  # noqa: F401
    AuditEvent,
    EvidenceItem,
    Submission,
    TaskAssignment,
    WorkstreamTask,
)
