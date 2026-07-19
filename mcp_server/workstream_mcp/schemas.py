"""Stable schemas and catalogue metadata for the contributor MCP surface."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


MCP_PROMPTS: tuple[str, ...] = ()
STABLE_REF_PATTERN_TEXT = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
STABLE_REF_PATTERN = re.compile(STABLE_REF_PATTERN_TEXT)
MAX_METADATA_DEPTH = 5
MAX_METADATA_COLLECTION_ITEMS = 100
MAX_METADATA_STRING_LENGTH = 10000
BoundedEvidenceRef = Annotated[
    str,
    Field(
        description="Evidence identifier or URI obtained from the leased review context.",
        min_length=1,
        max_length=1000,
        examples=["workstream://evidence/check-result-1"],
    ),
]

CLAIM_TASK_DESCRIPTION = (
    "Claim one task that Workstream currently offers to the authenticated contributor. "
    "Use this only after reading workstream://tasks (or a project task list) and selecting "
    "an available task_id from that resource. Do not use it to start an already claimed task, "
    "claim an arbitrary identifier, or bypass Workstream eligibility. The task must be "
    "claimable and the actor must hold the required project capability. This changes lifecycle "
    "state. A successful result has outcome 'claimed'; validation, authorization, conflict, and "
    "backend failures are MCP errors. After success, read the next_resource Task Context."
)
RELEASE_TASK_DESCRIPTION = (
    "Release a task currently claimed by the authenticated contributor when Workstream permits "
    "release. Use task_id from the prior claim result, Task Context, or Task Status; use this only "
    "while the task is releasable by this actor. Do not use it for unclaimed, completed, submitted, "
    "or another actor's task. This changes lifecycle state and may make the task available again. "
    "A successful result has outcome 'released'; validation, authorization, lifecycle, and backend "
    "failures are MCP errors. After success, read workstream://tasks for the updated queue."
)
PRE_SUBMIT_CHECK_DESCRIPTION = (
    "Evaluate a complete candidate submission packet without creating a submission or changing "
    "task lifecycle state. Use this after claiming the task, reading its Task Context, and preparing "
    "the packet; do not use it as a substitute for submit_task or before the required artifacts and "
    "attestation exist. Obtain task_id from the claim/context resources. A completed check is a "
    "successful MCP call with outcome 'passed' or 'pre_submit_check_failed'; transport, validation, "
    "authorization, and backend failures are MCP errors. Read next_resource: Task Status after a "
    "pass or Task Context after a valid failed check."
)
SUBMIT_TASK_DESCRIPTION = (
    "Submit an initial or revised contributor packet through Workstream's authoritative lifecycle. "
    "Use this only for a task claimed by the authenticated actor after reading Task Context and "
    "completing the required pre-submit checks; for a revision, follow the revision requirements in "
    "Task Status/Context. Do not use it for drafts, unchanged revisions, unclaimed tasks, or to "
    "bypass checker policy. Obtain task_id from the claim/context resources. This creates an "
    "immutable submission version and advances lifecycle state when accepted. Success has outcome "
    "'submitted'; validation, authorization, lifecycle, checker, and backend failures are MCP "
    "errors. After success, read the next_resource Task Status."
)
CLAIM_REVIEW_DESCRIPTION = (
    "Claim the single review Workstream currently offers to the authenticated reviewer. First read "
    "workstream://projects/{project_id}/current-review and use project_id and review_routing_ref "
    "exactly as returned there. Do not choose an arbitrary submission, reuse an expired offer, or "
    "claim when no review is available. The actor must have reviewer capability and the offer must "
    "still be claimable. This creates a review lease. Success has outcome 'leased_to_actor'; "
    "validation, authorization, availability, lease, and backend failures are MCP errors. After "
    "success, read the returned next_resource Review Context."
)
RELEASE_REVIEW_DESCRIPTION = (
    "Release the authenticated actor's active review lease without submitting a decision. Use "
    "review_ref from a successful claim_review result or its Review Context, and only while that "
    "lease is active and releasable. Do not use it for another actor's, expired, or completed review. "
    "This changes routing state and may return the review to Workstream's queue. Success has outcome "
    "'released'; validation, authorization, lease, and backend failures are MCP errors. After "
    "success, read the project's Current Review resource for the next offer."
)
SUBMIT_REVIEW_DESCRIPTION = (
    "Submit one final decision for the review leased to the authenticated actor. Use this only after "
    "claim_review and after reading the complete Review Context; obtain review_ref and evidence "
    "references from those results. Do not use it for an unleased, expired, completed, or "
    "self-authored review. Use 'needs_revision' only with at least one blocking finding; include "
    "evidence references when available. Acceptance permits advisory findings only. A 'reject' "
    "decision requires a bounded human reason. "
    "This records an immutable review decision and releases the lease. Success has outcome 'accept', "
    "'needs_revision', or 'reject'; validation, authorization, lease, and backend failures are MCP "
    "errors. After success, read the project's Current Review resource or the related Task Status."
)


@dataclass(frozen=True, slots=True)
class ResourceDefinition:
    """One WS-MCP-001 resource type and its supported URI templates."""

    name: str
    title: str
    description: str
    uri_templates: tuple[str, ...]
    mutating: bool = False


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One WS-MCP-001 tool."""

    name: str
    title: str
    description: str
    mutating: bool = True
    input_fields: tuple[str, ...] = ()


RESOURCE_DEFINITIONS: tuple[ResourceDefinition, ...] = (
    ResourceDefinition(
        name="my_projects",
        title="My Projects",
        description="Projects and contributor capabilities visible to the authenticated actor.",
        uri_templates=("workstream://me/projects",),
    ),
    ResourceDefinition(
        name="my_contributions",
        title="My Contributions",
        description="Immutable contribution records visible to the authenticated actor.",
        uri_templates=(
            "workstream://me/contributions",
            "workstream://me/contributions/projects/{project_id}",
        ),
    ),
    ResourceDefinition(
        name="tasks",
        title="Tasks",
        description="Authorized task offers and actor-facing task views.",
        uri_templates=("workstream://tasks", "workstream://projects/{project_id}/tasks"),
    ),
    ResourceDefinition(
        name="task_context",
        title="Task Context",
        description="Locked guide, policy, artifact, and submission context for one claimed task.",
        uri_templates=("workstream://tasks/{task_id}/context",),
    ),
    ResourceDefinition(
        name="task_status",
        title="Task Status",
        description="Poll-safe lifecycle state and next actions for one task.",
        uri_templates=("workstream://tasks/{task_id}/status",),
    ),
    ResourceDefinition(
        name="current_review",
        title="Current Review",
        description="The single review Workstream currently offers to the authenticated actor.",
        uri_templates=("workstream://projects/{project_id}/current-review",),
    ),
    ResourceDefinition(
        name="review_context",
        title="Review Context",
        description="Submission, checker, evidence, and policy context for one leased review.",
        uri_templates=("workstream://reviews/{review_ref}/context",),
    ),
)

TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        "claim_task",
        "Claim Task",
        CLAIM_TASK_DESCRIPTION,
        input_fields=("task_id", "request_id"),
    ),
    ToolDefinition(
        "release_task",
        "Release Task",
        RELEASE_TASK_DESCRIPTION,
        input_fields=("task_id", "request_id", "reason"),
    ),
    ToolDefinition(
        "run_pre_submit_check",
        "Run Pre-Submit Check",
        PRE_SUBMIT_CHECK_DESCRIPTION,
        mutating=False,
        input_fields=("task_id", "submission", "request_id"),
    ),
    ToolDefinition(
        "submit_task",
        "Submit Task",
        SUBMIT_TASK_DESCRIPTION,
        input_fields=("task_id", "submission", "request_id"),
    ),
    ToolDefinition(
        "claim_review",
        "Claim Review",
        CLAIM_REVIEW_DESCRIPTION,
        input_fields=("project_id", "review_routing_ref", "request_id"),
    ),
    ToolDefinition(
        "release_review",
        "Release Review",
        RELEASE_REVIEW_DESCRIPTION,
        input_fields=("review_ref", "request_id"),
    ),
    ToolDefinition(
        "submit_review",
        "Submit Review",
        SUBMIT_REVIEW_DESCRIPTION,
        input_fields=("review_ref", "decision", "findings", "request_id", "reason"),
    ),
)


class RequestIdInput(BaseModel):
    """Common idempotency input for mutating MCP tools."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID = Field(
        description=(
            "Idempotency UUID. Create a new UUID for each new logical operation; reuse it only "
            "when retrying the exact same operation and inputs; never reuse it for another task, "
            "review, or action."
        ),
        examples=["11111111-1111-4111-8111-111111111111"],
    )


class ClaimTaskInput(RequestIdInput):
    """Input for claim_task."""

    task_id: str = Field(
        description="Opaque task identifier returned by a Workstream task resource.",
        min_length=1,
        max_length=100,
        examples=["scenario-task-1"],
    )

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str) -> str:
        """Validate a task identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "task_id")


class ReleaseTaskInput(RequestIdInput):
    """Input for release_task."""

    task_id: str = Field(
        description="Opaque task identifier returned by a prior claim or task resource.",
        min_length=1,
        max_length=100,
        examples=["scenario-task-1"],
    )
    reason: str | None = Field(
        default=None,
        description="Optional concise reason for releasing the task.",
        max_length=1000,
        examples=["Unable to complete within the current assignment window."],
    )

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str) -> str:
        """Validate a task identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "task_id")


class ArtifactHashEntryInput(BaseModel):
    """One declared artifact hash in a contributor submission packet."""

    model_config = ConfigDict(extra="forbid")

    artifact: str = Field(
        description="Stable artifact path or identifier inside the submitted package.",
        min_length=1,
        max_length=1000,
        examples=["reports/check-results.json"],
    )
    hash: str = Field(
        description="Content hash including its algorithm prefix.",
        min_length=1,
        max_length=128,
        examples=["sha256:abc123"],
    )
    size_bytes: int | None = Field(
        default=None,
        description="Optional artifact size in bytes.",
        ge=0,
        examples=[2048],
    )
    notes: str | None = Field(
        default=None,
        description="Optional information needed to interpret this artifact entry.",
        max_length=10000,
        examples=["Generated by the required pre-submit test suite."],
    )


class EvidenceItemInput(BaseModel):
    """One contributor-supplied evidence reference."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "log",
        "screenshot",
        "test_result",
        "package",
        "diff",
        "note",
        "external_reference",
    ] = Field(
        description="Evidence kind used by Workstream and reviewers to interpret the item.",
        examples=["test_result"],
    )
    label: str = Field(
        description="Short human-readable evidence label.",
        min_length=1,
        max_length=200,
        examples=["MCP validation suite"],
    )
    uri: str | None = Field(
        default=None,
        description="Optional retrievable URI for the evidence item.",
        max_length=1000,
        examples=["flow://artifacts/check-results.json"],
    )
    hash: str | None = Field(
        default=None,
        description="Optional content hash including its algorithm prefix.",
        max_length=128,
        examples=["sha256:def456"],
    )
    size_bytes: int | None = Field(
        default=None,
        description="Optional evidence size in bytes.",
        ge=0,
        examples=[4096],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional bounded JSON metadata; never place credentials here.",
        max_length=100,
        examples=[{"suite": "pytest", "passed": 82}],
    )

    @field_validator("metadata")
    @classmethod
    def bound_metadata_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject deeply nested or oversized arbitrary evidence metadata."""
        _validate_bounded_metadata(value)
        return value


class SubmissionInput(BaseModel):
    """The Workstream submission packet accepted by existing Submitter APIs."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        description="Concise account of the completed work and its result.",
        min_length=1,
        max_length=10000,
        examples=["Implemented the contributor MCP contract and passed its validation suite."],
    )
    package_uri: str | None = Field(
        default=None,
        description="Optional Workstream/Flow retrievable URI for the immutable package.",
        max_length=1000,
        examples=["flow://packages/submission-123"],
    )
    package_hash: str = Field(
        description="Hash of the complete submitted package, including algorithm prefix.",
        min_length=1,
        max_length=128,
        examples=["sha256:abc123"],
    )
    artifact_hash_manifest: list[ArtifactHashEntryInput] = Field(
        description="Non-empty manifest of submitted artifacts and their content hashes.",
        min_length=1,
        max_length=1000,
        examples=[[{"artifact": "result.txt", "hash": "sha256:def456"}]],
    )
    worker_attestation: str = Field(
        description="Contributor attestation that the packet is complete and accurately described.",
        min_length=1,
        max_length=20000,
        examples=["I attest that this submission is complete and the evidence is accurate."],
    )
    evidence_items: list[EvidenceItemInput] = Field(
        default_factory=list,
        description="Optional evidence supporting the submission and checker evaluation.",
        max_length=1000,
        examples=[[{"type": "test_result", "label": "MCP tests"}]],
    )


class CandidateSubmissionInput(RequestIdInput):
    """Input for run_pre_submit_check and submit_task."""

    task_id: str = Field(
        description="Opaque task identifier returned by a claim or task resource.",
        min_length=1,
        max_length=100,
        examples=["scenario-task-1"],
    )
    submission: SubmissionInput = Field(
        description="Complete candidate packet matching the locked Task Context requirements."
    )

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str) -> str:
        """Validate a task identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "task_id")


class ClaimReviewInput(RequestIdInput):
    """Input for claim_review."""

    project_id: str = Field(
        description="Project identifier from the Current Review resource URI/result.",
        min_length=1,
        max_length=100,
        examples=["scenario-project-1"],
    )
    review_routing_ref: str = Field(
        description="Opaque routing reference returned by the Current Review resource.",
        min_length=1,
        max_length=200,
        examples=["scenario-review-route-1"],
    )

    @field_validator("project_id", "review_routing_ref")
    @classmethod
    def normalize_string_ids(cls, value: str, info: Any) -> str:
        """Validate review claim identifiers used as URI or HTTP path segments."""
        return normalize_stable_ref(value, info.field_name)


class ReleaseReviewInput(RequestIdInput):
    """Input for release_review."""

    review_ref: str = Field(
        description="Opaque review identifier returned by claim_review or Review Context.",
        min_length=1,
        max_length=200,
        examples=["scenario-review-1"],
    )

    @field_validator("review_ref")
    @classmethod
    def normalize_review_ref(cls, value: str) -> str:
        """Validate a review identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "review_ref")


class ReviewFindingInput(BaseModel):
    """Portable, actionable finding supplied with a human review decision."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        description="Specific, actionable review finding explaining what must change or why it fails.",
        min_length=1,
        max_length=4000,
        examples=["The submitted manifest omits the required checker report."],
    )
    finding_kind: Literal["blocking", "advisory"] = Field(
        description="Lifecycle meaning of the finding: blocking or advisory.",
        examples=["blocking"],
    )
    category: str | None = Field(
        default=None,
        description="Optional stable category for grouping the finding.",
        max_length=100,
        examples=["missing_evidence"],
    )
    evidence_refs: list[BoundedEvidenceRef] = Field(
        default_factory=list,
        description="Evidence references from Review Context that support this finding.",
        max_length=100,
        examples=[["workstream://evidence/check-result-1"]],
    )


class SubmitReviewInput(RequestIdInput):
    """Input for submit_review."""

    review_ref: str = Field(
        description="Opaque review identifier returned by claim_review or Review Context.",
        min_length=1,
        max_length=200,
        examples=["scenario-review-1"],
    )
    decision: Literal["accept", "needs_revision", "reject"] = Field(
        description=(
            "Final review decision. needs_revision requires at least one blocking finding; reject "
            "requires a bounded human reason; accept permits advisory findings only."
        ),
        examples=["needs_revision"],
    )
    findings: list[ReviewFindingInput] = Field(
        default_factory=list,
        description=(
            "Actionable findings supporting the decision; needs_revision requires at least one "
            "blocking finding, while accept permits advisory findings only."
        ),
        max_length=100,
        examples=[
            [
                {
                    "summary": "Add the missing checker report.",
                    "finding_kind": "blocking",
                }
            ]
        ],
    )
    reason: str | None = Field(
        default=None,
        description="Bounded human reason required for reject; omit for other decisions.",
        min_length=1,
        max_length=4000,
        examples=["The submission does not satisfy the governing acceptance criteria."],
    )

    @field_validator("review_ref")
    @classmethod
    def normalize_review_ref(cls, value: str) -> str:
        """Validate a review identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "review_ref")

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        """Normalize an optional rejection reason and reject whitespace-only values."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_rejection_reason(self) -> SubmitReviewInput:
        """Require rationale for rejection without inventing structured findings."""
        if self.decision == "reject" and self.reason is None:
            raise ValueError("reject requires a bounded human reason")
        if self.decision != "reject" and self.reason is not None:
            raise ValueError("reason is only valid for reject")
        if self.decision == "accept" and any(
            finding.finding_kind == "blocking" for finding in self.findings
        ):
            raise ValueError("accept permits advisory findings only")
        return self


class OperationResult(BaseModel):
    """Structured MCP operation result."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    outcome: str
    workstream_ref: str | None = None
    next_resource: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str


TaskIdParameter = Annotated[
    str,
    Field(
        description="Opaque task identifier obtained from a Workstream task resource or claim result.",
        min_length=1,
        max_length=100,
        pattern=STABLE_REF_PATTERN_TEXT,
        examples=["scenario-task-1"],
    ),
]
ProjectIdParameter = Annotated[
    str,
    Field(
        description="Opaque project identifier obtained from My Projects or Current Review.",
        min_length=1,
        max_length=100,
        pattern=STABLE_REF_PATTERN_TEXT,
        examples=["scenario-project-1"],
    ),
]
ReviewRoutingRefParameter = Annotated[
    str,
    Field(
        description="Exact routing reference returned by the project's Current Review resource.",
        min_length=1,
        max_length=200,
        pattern=STABLE_REF_PATTERN_TEXT,
        examples=["scenario-review-route-1"],
    ),
]
ReviewRefParameter = Annotated[
    str,
    Field(
        description="Opaque review identifier returned by claim_review or Review Context.",
        min_length=1,
        max_length=200,
        pattern=STABLE_REF_PATTERN_TEXT,
        examples=["scenario-review-1"],
    ),
]
RequestIdParameter = Annotated[
    UUID,
    Field(
        description=(
            "Idempotency UUID. Create a new UUID for every new logical operation. Reuse the same "
            "UUID only when retrying the exact same operation with identical inputs. Never reuse "
            "it for a different task, review, or action."
        ),
        examples=["11111111-1111-4111-8111-111111111111"],
    ),
]
ReleaseReasonParameter = Annotated[
    str | None,
    Field(
        description="Optional concise reason for releasing the task; omit when no reason is needed.",
        max_length=1000,
        examples=["Unable to complete within the current assignment window."],
    ),
]
SubmissionParameter = Annotated[
    SubmissionInput,
    Field(
        description=(
            "Complete candidate submission packet prepared from the locked Task Context. "
            "Provide the same packet when retrying with the same request_id."
        ),
        examples=[
            {
                "summary": "Implemented the requested contributor MCP change.",
                "package_uri": "flow://packages/submission-123",
                "package_hash": "sha256:abc123",
                "artifact_hash_manifest": [
                    {"artifact": "result.txt", "hash": "sha256:def456"}
                ],
                "worker_attestation": "I attest that this packet is complete.",
                "evidence_items": [
                    {"type": "test_result", "label": "MCP validation suite"}
                ],
            }
        ],
    ),
]
ReviewDecisionParameter = Annotated[
    Literal["accept", "needs_revision", "reject"],
    Field(
        description=(
            "Final decision for the leased review. needs_revision requires one or more actionable "
            "findings; reject requires a bounded human reason."
        ),
        examples=["needs_revision"],
    ),
]
ReviewFindingsParameter = Annotated[
    list[ReviewFindingInput],
    Field(
        description=(
            "Actionable findings based on Review Context evidence. Required and non-empty for "
            "needs_revision, with at least one blocking finding; accept permits advisory findings "
            "only; at most 100 findings."
        ),
        max_length=100,
        examples=[
            [
                {
                    "summary": "Add the required checker report to the artifact manifest.",
                    "finding_kind": "blocking",
                    "category": "missing_evidence",
                    "evidence_refs": ["workstream://evidence/check-result-1"],
                }
            ]
        ],
    ),
]
ReviewReasonParameter = Annotated[
    str | None,
    Field(
        description="Bounded human reason required for reject; omit for other decisions.",
        min_length=1,
        max_length=4000,
        examples=["The submission does not satisfy the governing acceptance criteria."],
    ),
]


class OperationSuccessBase(BaseModel):
    """Common validated output fields for successful MCP tool executions."""

    model_config = ConfigDict(extra="forbid")

    operation: str = Field(description="Stable Workstream MCP operation name.")
    outcome: str = Field(description="Valid business outcome produced by the completed operation.")
    workstream_ref: str | None = Field(
        description="Primary Workstream identifier created or affected by the operation."
    )
    next_resource: str | None = Field(
        description="Resource URI the agent should read next, or null when no single URI applies."
    )
    summary: str = Field(description="Short agent-facing explanation of the completed outcome.")


class PreSubmitCheckGatewayResponse(BaseModel):
    """Validated response contract for the existing Workstream checker API."""

    model_config = ConfigDict(extra="allow", strict=True)

    task_id: str
    authoritative: StrictBool
    status: Literal["passed", "failed"]
    eligible_to_submit: bool
    results: list[dict[str, Any]]

    @model_validator(mode="after")
    def require_coherent_eligibility(self) -> PreSubmitCheckGatewayResponse:
        """Require status and eligibility to describe the same completed outcome."""
        if self.authoritative is not False:
            raise ValueError("pre-submit checker response must be non-authoritative")
        expected_eligibility = self.status == "passed"
        if self.eligible_to_submit is not expected_eligibility:
            raise ValueError("checker status and submission eligibility disagree")
        return self


class ClaimTaskData(BaseModel):
    """Authoritative task-claim payload returned by Workstream."""

    task_claim: dict[str, Any] = Field(description="Workstream task and assignment claim data.")


class ClaimTaskResult(OperationSuccessBase):
    """Successful claim_task result."""

    operation: Literal["claim_task"] = Field(description="Operation that produced this result.")
    outcome: Literal["claimed"] = Field(description="The task was claimed by this actor.")
    workstream_ref: str = Field(description="Claimed task identifier.")
    next_resource: str = Field(description="Task Context URI to read before performing work.")
    data: ClaimTaskData = Field(description="Authoritative claim details.")


class ReleaseTaskData(BaseModel):
    """Authoritative task-release payload returned by Workstream."""

    task_release: dict[str, Any] = Field(description="Workstream task release data.")


class ReleaseTaskResult(OperationSuccessBase):
    """Successful release_task result."""

    operation: Literal["release_task"] = Field(description="Operation that produced this result.")
    outcome: Literal["released"] = Field(description="The task claim was released.")
    workstream_ref: str = Field(description="Released task identifier.")
    next_resource: str = Field(description="Tasks resource URI to read after release.")
    data: ReleaseTaskData = Field(description="Authoritative release details.")


class PreSubmitCheckData(BaseModel):
    """Authoritative checker payload returned by Workstream."""

    pre_submit_check: dict[str, Any] = Field(
        description="Checker status, findings, and submission eligibility data."
    )


class PreSubmitCheckResult(OperationSuccessBase):
    """Completed run_pre_submit_check result, including valid failed checks."""

    operation: Literal["run_pre_submit_check"] = Field(
        description="Operation that produced this result."
    )
    outcome: Literal["passed", "pre_submit_check_failed"] = Field(
        description="Completed checker outcome; a failed check is a valid business result."
    )
    workstream_ref: str = Field(description="Checked task identifier.")
    next_resource: str = Field(description="Task Status or Task Context URI to read next.")
    data: PreSubmitCheckData = Field(description="Authoritative checker details.")


class SubmitTaskData(BaseModel):
    """Authoritative submission payload returned by Workstream."""

    submission: dict[str, Any] = Field(description="Created immutable submission version data.")


class SubmitTaskResult(OperationSuccessBase):
    """Successful submit_task result."""

    operation: Literal["submit_task"] = Field(description="Operation that produced this result.")
    outcome: Literal["submitted"] = Field(description="Workstream accepted the submission version.")
    workstream_ref: str = Field(description="Submission identifier, or task identifier when absent.")
    next_resource: str = Field(description="Task Status URI to poll after submission.")
    data: SubmitTaskData = Field(description="Authoritative submission details.")


class ClaimReviewData(BaseModel):
    """Authoritative review-claim payload returned by Workstream."""

    review_claim: dict[str, Any] = Field(description="Review lease and routing data.")


class ClaimReviewResult(OperationSuccessBase):
    """Successful claim_review result."""

    operation: Literal["claim_review"] = Field(description="Operation that produced this result.")
    outcome: Literal["leased_to_actor"] = Field(description="The review was leased to this actor.")
    workstream_ref: str = Field(description="Leased review identifier.")
    next_resource: str = Field(description="Review Context URI to read after claiming the review.")
    data: ClaimReviewData = Field(description="Authoritative review lease details.")


class ReleaseReviewData(BaseModel):
    """Authoritative review-release payload returned by Workstream."""

    review_release: dict[str, Any] = Field(description="Released review lease data.")


class ReleaseReviewResult(OperationSuccessBase):
    """Successful release_review result."""

    operation: Literal["release_review"] = Field(description="Operation that produced this result.")
    outcome: Literal["released"] = Field(description="The active review lease was released.")
    workstream_ref: str = Field(description="Released review identifier.")
    next_resource: None = Field(
        description="No single URI is returned; read the project's Current Review resource."
    )
    data: ReleaseReviewData = Field(description="Authoritative review release details.")


class SubmitReviewData(BaseModel):
    """Authoritative review-decision payload returned by Workstream."""

    review_decision: dict[str, Any] = Field(description="Recorded review decision data.")


class SubmitReviewResult(OperationSuccessBase):
    """Successful submit_review result."""

    operation: Literal["submit_review"] = Field(description="Operation that produced this result.")
    outcome: Literal["accept", "needs_revision", "reject"] = Field(
        description="Immutable review decision accepted by Workstream."
    )
    workstream_ref: str = Field(description="Reviewed review identifier.")
    next_resource: None = Field(
        description="No single URI is returned; read Current Review or related Task Status."
    )
    data: SubmitReviewData = Field(description="Authoritative review decision details.")


def normalize_stable_ref(value: str, field_name: str) -> str:
    """Validate an opaque Workstream reference carried in one path segment."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if normalized in {".", ".."}:
        raise ValueError(f"{field_name} must not be a relative path segment")
    if not STABLE_REF_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, dot, underscore, colon, or hyphen"
        )
    return normalized


def _validate_bounded_metadata(value: Any, *, depth: int = 0) -> None:
    """Bound arbitrary evidence metadata before it reaches a gateway."""
    if depth > MAX_METADATA_DEPTH:
        raise ValueError("metadata nesting exceeds the supported depth")
    if isinstance(value, str):
        if len(value) > MAX_METADATA_STRING_LENGTH:
            raise ValueError("metadata string exceeds the supported length")
        return
    if isinstance(value, dict):
        if len(value) > MAX_METADATA_COLLECTION_ITEMS:
            raise ValueError("metadata object has too many entries")
        for key, item in value.items():
            _validate_bounded_metadata(key, depth=depth + 1)
            _validate_bounded_metadata(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_METADATA_COLLECTION_ITEMS:
            raise ValueError("metadata list has too many items")
        for item in value:
            _validate_bounded_metadata(item, depth=depth + 1)
        return
    if value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("metadata must contain JSON-compatible values")
