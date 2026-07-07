"""Import domain models so Alembic can discover metadata."""

from app.modules.actors.models import ActorIdentity, ActorProfile  # noqa: F401
from app.modules.checkers.models import CheckerResult, CheckerRun  # noqa: F401
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
