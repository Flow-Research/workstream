"""Detached revision inputs for an already authorized POST materialization."""

from typing import Annotated, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from app.modules.tasks.api.post_submit_routing import TaskRoutingSelection
from app.modules.tasks.api.submission_context import TaskSubmissionContextKind

Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Version = Annotated[StrictInt, Field(gt=0)]


class TaskEvaluationRevisionRequest(BaseModel):
    """Exact current Submission and ART's consumed preparation selector; no authority."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version: Version
    admission_id: UUID
    preparation_id: UUID | None
    preparation_sha256: Sha256 | None

    @model_validator(mode="after")
    def preparation_shape(self) -> Self:
        """Reject a partial reference instead of selecting a mutable latest head."""
        if (self.preparation_id is None) != (self.preparation_sha256 is None):
            raise ValueError("revision preparation selector is incomplete")
        return self


class EvaluationSubmissionReference(BaseModel):
    """Immutable TASK ownership and ART references without storage coordinates."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    submission_id: UUID
    submission_version: Version
    admission_id: UUID
    binding_id: UUID
    content_id: UUID


class EvaluationRevisionSource(BaseModel):
    """Exact consumed context and the immutable result that requested this revision."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )

    preparation_id: UUID
    preparation_sha256: Sha256
    routing_manifest_id: UUID
    revision_round: Annotated[StrictInt, Field(ge=0)]
    evaluation: TaskRoutingSelection


class TaskEvaluationRevisionContext(BaseModel):
    """Initial/revision distinction within an assignment, not global version counting."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )

    kind: TaskSubmissionContextKind
    current: EvaluationSubmissionReference
    predecessor: EvaluationSubmissionReference | None
    source: EvaluationRevisionSource | None

    @model_validator(mode="after")
    def exact_predecessor(self) -> Self:
        """Keep another assignment's work and unrelated feedback out of this context."""
        if self.kind == "initial":
            if self.predecessor is not None or self.source is not None:
                raise ValueError("initial evaluation has revision material")
            return self
        prior, source, current = self.predecessor, self.source, self.current
        if prior is None or source is None:
            raise ValueError("revision evaluation lacks its exact source")
        if (
            (prior.project_id, prior.task_id, prior.assignment_id, prior.contributor_id)
            != (current.project_id, current.task_id, current.assignment_id, current.contributor_id)
            or prior.submission_id == current.submission_id
            or prior.submission_version + 1 != current.submission_version
            or (
                source.evaluation.project_id,
                source.evaluation.task_id,
                source.evaluation.submission_id,
                source.evaluation.submission_version,
            )
            != (prior.project_id, prior.task_id, prior.submission_id, prior.submission_version)
            or source.evaluation.routing_recommendation != "needs_revision"
        ):
            raise ValueError("revision evaluation source differs")
        return self


class TaskEvaluationRevisionPort(Protocol):
    """Read TASK facts under the caller's AUTH/current-execution custody and transaction."""

    async def read(
        self,
        request: TaskEvaluationRevisionRequest,
    ) -> TaskEvaluationRevisionContext:
        """Return exact detached facts; never grant byte access or mutation authority."""
        ...
