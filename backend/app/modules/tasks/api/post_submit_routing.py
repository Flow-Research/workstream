"""Detached TASK source facts for authorized post-submit routing."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api.transition_audit import TaskPolicyLineage

_Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
_PositiveVersion = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]
_ByteCount = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]


class TaskPostSubmitSourceProposal(BaseModel):
    """Detached semantic source proposal; neither stored evidence nor authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    submission_version: _PositiveVersion
    assignment_id: UUID
    contributor_id: UUID
    contribution_policy_version_id: UUID
    checker_run_id: UUID
    evaluation_request_id: UUID
    request_digest: _Sha256
    evaluation_generation: _PositiveVersion
    result_id: UUID
    result_digest: _Sha256
    completion_event_id: UUID
    creation_decision_id: UUID
    binding_decision_id: UUID
    input_materialization_evidence_id: UUID
    execute_evidence_id: UUID
    finalize_evidence_id: UUID
    human_review_required: StrictBool
    replica_id: UUID
    content_sha256: _Sha256
    byte_count: _ByteCount
    semantic_manifest_sha256: _Sha256

    predecessor_submission_id: UUID | None
    predecessor_submission_version: _PositiveVersion | None
    admission_id: UUID
    binding_id: UUID
    content_id: UUID
    locked_policy: TaskPolicyLineage
    routing_recommendation: Literal["allow_review"]

    @model_validator(mode="after")
    def validate_detached_lineage(self) -> Self:
        """Keep nested policy and immediate predecessor facts internally exact."""
        if (
            self.locked_policy.locked_contribution_policy_version_id
            != self.contribution_policy_version_id
        ):
            raise ValueError("routing source contribution policy lineage differs")
        receipts = (
            self.creation_decision_id,
            self.binding_decision_id,
            self.input_materialization_evidence_id,
            self.execute_evidence_id,
            self.finalize_evidence_id,
        )
        if len(set(receipts)) != len(receipts):
            raise ValueError("routing source phase receipts are not distinct")

        has_predecessor_id = self.predecessor_submission_id is not None
        has_predecessor_version = self.predecessor_submission_version is not None
        if has_predecessor_id != has_predecessor_version:
            raise ValueError("routing source predecessor identity is incomplete")
        if self.submission_version == 1:
            if has_predecessor_id:
                raise ValueError("initial routing source has a predecessor")
            return self
        if not has_predecessor_id:
            raise ValueError("successor routing source lacks a predecessor")
        if self.predecessor_submission_id == self.submission_id:
            raise ValueError("routing source predecessor equals submission")
        if self.predecessor_submission_version != self.submission_version - 1:
            raise ValueError("routing source predecessor version is inconsistent")
        return self


class TaskPostSubmitManifestFacts(TaskPostSubmitSourceProposal):
    """Persisted source with its mandatory database-owned creation time."""

    created_at: AwareDatetime


def task_post_submit_source_digest(source: TaskPostSubmitSourceProposal) -> str:
    """Commit exact source facts except the database-assigned creation time."""
    if type(source) not in (TaskPostSubmitSourceProposal, TaskPostSubmitManifestFacts):
        raise ValueError("routing source facts are invalid")
    checked = TaskPostSubmitSourceProposal.model_validate(
        source.model_dump(mode="python", exclude={"created_at"})
    )
    return canonical_json_hash({
        "domain": "workstream.task_post_submit_source.v0.1",
        "source": checked.model_dump(mode="json", exclude={"created_at"}),
    })


__all__ = ("TaskPostSubmitSourceProposal", "TaskPostSubmitManifestFacts", "task_post_submit_source_digest",
           "TaskRoutingSelection", "TaskRoutingRequestFacts", "task_routing_request_digest",
           "TaskRoutingSourcePreparation")


class TaskRoutingSelection(BaseModel):
    """Exact completion selectors; values alone establish neither ownership nor authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: UUID
    task_id: UUID
    submission_id: UUID
    submission_version: _PositiveVersion
    checker_run_id: UUID
    evaluation_request_id: UUID
    evaluation_request_digest: _Sha256
    evaluation_generation: _PositiveVersion
    result_id: UUID
    result_digest: _Sha256
    completion_event_id: UUID
    routing_recommendation: Literal["allow_review"]


def task_routing_request_digest(selection: TaskRoutingSelection) -> str:
    """Hash semantic selectors, independently of allocated IDs and database time."""
    if type(selection) is not TaskRoutingSelection:
        raise ValueError("routing request selection is invalid")
    checked = TaskRoutingSelection.model_validate(selection.model_dump())
    return canonical_json_hash({
        "domain": "workstream.task_post_submit_route_request.v0.1",
        "action": "task.post_submit.route",
        "selection": checked.model_dump(mode="json"),
    })


class TaskRoutingRequestFacts(TaskRoutingSelection):
    """Reserved request and future source identity, never a published routing source."""

    route_operation_id: UUID
    routing_manifest_id: UUID
    route_request_digest: _Sha256
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_request_custody(self) -> Self:
        """Reject identity reuse and a digest inconsistent with the closed selectors."""
        ids = (self.route_operation_id, self.routing_manifest_id)
        if any(value.version != 7 for value in ids) or ids[0] == ids[1]:
            raise ValueError("routing request requires distinct UUIDv7 identities")
        if set(ids) & {self.evaluation_request_id, self.result_id, self.completion_event_id}:
            raise ValueError("routing request identities reuse checker identities")
        selection = TaskRoutingSelection(**self.model_dump(include=set(TaskRoutingSelection.model_fields)))
        if (
            self.route_request_digest != task_routing_request_digest(selection)
            or self.route_request_digest == self.evaluation_request_digest
        ):
            raise ValueError("routing request digest differs")
        return self


class TaskRoutingSourcePreparation(BaseModel):
    """Reserved request with matching proposed source; no publication or authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    request: TaskRoutingRequestFacts
    source: TaskPostSubmitSourceProposal

    @model_validator(mode="after")
    def matching_source(self) -> Self:
        request = TaskRoutingRequestFacts.model_validate(self.request.model_dump())
        source = TaskPostSubmitSourceProposal.model_validate(self.source.model_dump())
        if request.routing_manifest_id != source.id or request.evaluation_request_digest != source.request_digest:
            raise ValueError("routing source identity differs")
        for name in TaskRoutingSelection.model_fields:
            if name != "evaluation_request_digest" and getattr(request, name) != getattr(source, name):
                raise ValueError("routing source selection differs")
        return self
