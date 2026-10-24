"""Closed evidence-only facts from selected external POST images."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_serializer, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionResult,
    PostSubmitExternalCheckerMaterial,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalPostSubmitPolicy,
    selected_evaluation_context_roles,
)
from app.modules.checkers.api.canonical_values import (
    ByteCount,
    CheckerValue,
    ResourceId,
    Sha256,
    VersionNumber,
)


class SelectedPostSubmitLockedContext(CheckerValue):
    """Exact TASK and selected-policy lineage carried by a new Submission."""

    guide_version: str = Field(min_length=1, max_length=50)
    source_id: ResourceId
    source_hash: Sha256
    effective_policy_id: ResourceId
    effective_policy_hash: Sha256
    pre_policy_id: ResourceId
    pre_policy_hash: Sha256
    post_policy_id: ResourceId
    post_policy_version: str = Field(min_length=1, max_length=50)
    post_policy_hash: Sha256
    review_policy_id: ResourceId
    review_generation: VersionNumber
    review_hash: Sha256
    revision_policy_id: ResourceId
    revision_generation: VersionNumber
    revision_hash: Sha256


class SelectedPostSubmissionContent(CheckerValue):
    """Approved POST image policy plus the exact locked TASK context."""

    project_id: ResourceId
    expected_context: SelectedPostSubmitLockedContext
    policy: LockedExternalPostSubmitPolicy

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        """Require the exact approved policy digest stamped on the Submission."""
        if self.expected_context.post_policy_hash != self.policy.policy_sha256:
            raise ValueError("selected POST locked policy mismatch")
        return self


class SelectedPostSubmissionEvaluationRequest(SelectedPostSubmissionContent):
    """Hash-bound selected POST request reserved with one immutable Submission."""

    schema_version: Literal["workstream.selected_post_submit_request.v1"] = (
        "workstream.selected_post_submit_request.v1"
    )
    evaluation_request_id: ResourceId
    evaluation_generation: VersionNumber
    task_id: ResourceId
    assignment_id: ResourceId
    submission_id: ResourceId
    submission_version: VersionNumber
    content_id: ResourceId
    binding_id: ResourceId
    content_sha256: Sha256
    byte_count: ByteCount
    request_sha256: Sha256

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        """Bind the entire selected policy and native Submission identity."""
        expected = canonical_json_hash(self.model_dump(mode="json", exclude={"request_sha256"}))
        if self.request_sha256 != expected:
            raise ValueError("selected POST request digest mismatch")
        return self


def make_selected_post_submit_request(
    **fields: object,
) -> SelectedPostSubmissionEvaluationRequest:
    """Derive the selected request identity before strict validation."""
    if "request_sha256" in fields:
        raise ValueError("selected POST request identity is derived")
    candidate = SelectedPostSubmissionEvaluationRequest.model_construct(
        **fields,
        request_sha256="sha256:" + "0" * 64,
    )
    fields["request_sha256"] = canonical_json_hash(
        candidate.model_dump(mode="json", exclude={"request_sha256"})
    )
    return SelectedPostSubmissionEvaluationRequest.model_validate(fields)


@dataclass(frozen=True, slots=True)
class ExternalPostSubmitIsolationFacts:
    """Observed sandbox identity detached from the trusted service response."""

    repository: str
    platform_manifest_digest: str
    platform_manifest_media_type: str
    platform_manifest_byte_count: int
    operating_system: str
    architecture: str
    config_image_id: str
    runtime: str
    isolation_mode: str
    sandbox_uid: int
    sandbox_gid: int


@dataclass(frozen=True, slots=True)
class ExternalPostSubmitInputReceipt:
    """Retained exact context and visible input identities for one selected image."""

    configuration_sha256: str
    input_sha256: str
    evaluation_context_sha256: str
    materials: tuple[PostSubmitExternalCheckerMaterial, ...]

    def __post_init__(self) -> None:
        """Reject malformed receipts without guessing missing historical evidence."""
        from pydantic import TypeAdapter

        adapter = TypeAdapter(Sha256)
        for digest in (
            self.configuration_sha256,
            self.input_sha256,
            self.evaluation_context_sha256,
        ):
            adapter.validate_python(digest)
        if tuple(item.role for item in self.materials) not in (
            ("submission_archive",),
            ("submission_archive", "predecessor_submission_archive"),
        ):
            raise ValueError("selected POST input receipt material roles differ")


@dataclass(frozen=True, slots=True)
class ExternalPostSubmitMemberFacts:
    """One normalized POST image result in exact locked policy order."""

    order: int
    requirement_id: str
    registry_entry_id: UUID
    registry_entry_digest: str
    request_digest: str
    result: ExternalCheckerExecutionResult
    isolation: ExternalPostSubmitIsolationFacts
    input_receipt: ExternalPostSubmitInputReceipt | None = None

    @model_serializer(mode="wrap")
    def serialize_retained_fields(self, handler):
        """Omit an unselected feature without changing historical result hashes."""
        values = handler(self)
        if self.input_receipt is None:
            values.pop("input_receipt", None)
        return values

    def __post_init__(self) -> None:
        if (
            type(self.order) is not int
            or self.order < 0
            or not self.requirement_id
            or self.result.outcome != "completed"
            or self.result.request_digest != self.request_digest
            or self.result.registry_entry_id != self.registry_entry_id
            or self.result.registry_entry_digest != self.registry_entry_digest
            or self.result.phase != "post_submit"
        ):
            raise ValueError("external POST member facts are invalid")


@dataclass(frozen=True, slots=True)
class SelectedPostSubmitExecutionFacts:
    """Complete evidence-only result from every locked external POST image."""

    policy_sha256: str
    required_external_count: int
    external_members: tuple[ExternalPostSubmitMemberFacts, ...]

    def __post_init__(self) -> None:
        members = self.external_members
        if (
            type(self.policy_sha256) is not str
            or len(self.policy_sha256) != 71
            or not self.policy_sha256.startswith("sha256:")
            or type(self.required_external_count) is not int
            or self.required_external_count < 0
            or len(members) != self.required_external_count
            or tuple(item.order for item in members) != tuple(range(len(members)))
            or len({item.requirement_id for item in members}) != len(members)
        ):
            raise ValueError("selected POST execution facts are invalid")

    def canonical_body(self) -> dict[str, object]:
        """Return exact evidence and isolation without any acceptance signal."""
        return {
            "schema_version": "workstream.selected_post_submit_execution.v1",
            "policy_sha256": self.policy_sha256,
            "required_external_count": self.required_external_count,
            "external_members": [
                {
                    "order": member.order,
                    "requirement_id": member.requirement_id,
                    "registry_entry_id": str(member.registry_entry_id),
                    "registry_entry_digest": member.registry_entry_digest,
                    "request_digest": member.request_digest,
                    "result": member.result.model_dump(mode="json"),
                    "isolation": asdict(member.isolation),
                    **(
                        {
                            "input_receipt": {
                                "configuration_sha256": member.input_receipt.configuration_sha256,
                                "input_sha256": member.input_receipt.input_sha256,
                                "evaluation_context_sha256": member.input_receipt.evaluation_context_sha256,
                                "materials": [
                                    item.model_dump(mode="json")
                                    for item in member.input_receipt.materials
                                ],
                            }
                        }
                        if member.input_receipt is not None
                        else {}
                    ),
                }
                for member in self.external_members
            ],
        }

    @property
    def result_digest(self) -> str:
        """Bind every required image result and observed sandbox fact."""
        return canonical_json_hash(self.canonical_body())


class SelectedPostSubmissionEvaluationResult(CheckerValue):
    """Durable selected POST evidence envelope with no acceptance authority."""

    schema_version: Literal["workstream.selected_post_submit_result.v1"] = (
        "workstream.selected_post_submit_result.v1"
    )
    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    evaluation_generation: VersionNumber
    result_id: ResourceId
    result_digest: Sha256
    outcome: Literal["completed", "infrastructure_failed"]
    execution: SelectedPostSubmitExecutionFacts | None
    infrastructure_failure_code: (
        Literal[
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        """Separate complete external evidence from recoverable infrastructure."""
        if self.outcome == "completed":
            if self.execution is None or self.infrastructure_failure_code is not None:
                raise ValueError("selected POST completed result is invalid")
        elif self.execution is not None or self.infrastructure_failure_code is None:
            raise ValueError("selected POST infrastructure result is invalid")
        if self.result_digest != canonical_json_hash(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("selected POST result digest mismatch")
        return self

    def validate_request(self, request: SelectedPostSubmissionEvaluationRequest) -> None:
        """Bind result identity and selected policy without claiming currentness."""
        result = SelectedPostSubmissionEvaluationResult.model_validate(self)
        request = SelectedPostSubmissionEvaluationRequest.model_validate(request)
        expected_members = tuple(
            (
                order,
                entry.requirement_id,
                entry.registry.registry_entry_id,
                entry.registry.entry_digest,
                entry.registry.image_digest,
            )
            for order, entry in enumerate(request.policy.entries)
        )
        actual_members = (
            tuple(
                (
                    member.order,
                    member.requirement_id,
                    member.registry_entry_id,
                    member.registry_entry_digest,
                    member.isolation.platform_manifest_digest,
                )
                for member in result.execution.external_members
            )
            if result.execution is not None
            else ()
        )
        if (
            result.request_id,
            result.request_digest,
            result.evaluation_generation,
        ) != (
            request.evaluation_request_id,
            request.request_sha256,
            request.evaluation_generation,
        ) or (
            result.execution is not None
            and (
                result.execution.policy_sha256 != request.policy.policy_sha256
                or result.execution.required_external_count != len(expected_members)
                or actual_members != expected_members
            )
        ):
            raise ValueError("selected POST result request mismatch")
        if result.execution is not None:
            for binding, member in zip(
                request.policy.entries, result.execution.external_members, strict=True
            ):
                selected = selected_evaluation_context_roles(binding.configuration, binding.stage)
                receipt = member.input_receipt
                if (receipt is not None) != (selected is not None):
                    raise ValueError("selected POST input receipt selection differs")
                if receipt is not None:
                    current = receipt.materials[0]
                    if receipt.configuration_sha256 != binding.configuration_sha256 or (
                        current.submission_id,
                        current.submission_version,
                        current.binding_id,
                        current.content_id,
                        current.content_sha256,
                        current.byte_count,
                    ) != (
                        request.submission_id,
                        request.submission_version,
                        request.binding_id,
                        request.content_id,
                        request.content_sha256,
                        request.byte_count,
                    ):
                        raise ValueError("selected POST input receipt identity differs")
                    if len(receipt.materials) == 2:
                        prior = receipt.materials[1]
                        if (
                            "predecessor_submission_archive" not in selected
                            or prior.submission_id == current.submission_id
                            or prior.submission_version + 1 != current.submission_version
                        ):
                            raise ValueError("selected POST predecessor receipt differs")


class SelectedPostSubmitCurrentResultReference(CheckerValue):
    """Owner-issued reference to one completed selected POST result."""

    schema_version: Literal["post_submit_current_result_reference"] = (
        "post_submit_current_result_reference"
    )
    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    evaluation_generation: VersionNumber
    result_id: ResourceId
    result_digest: Sha256

    def validate_result(self, result: object) -> None:
        """Match exact completed selected result identity."""
        reference = SelectedPostSubmitCurrentResultReference.model_validate(self)
        selected = SelectedPostSubmissionEvaluationResult.model_validate(result)
        names = (
            "request_id",
            "request_digest",
            "attempt_id",
            "evaluation_generation",
            "result_id",
            "result_digest",
        )
        if selected.outcome != "completed" or any(
            getattr(reference, key) != getattr(selected, key) for key in names
        ):
            raise ValueError("selected POST current reference result mismatch")


def make_selected_post_submit_result(
    **fields: object,
) -> SelectedPostSubmissionEvaluationResult:
    """Derive the selected result identity before strict validation."""
    if "result_digest" in fields:
        raise ValueError("selected POST result identity is derived")
    candidate = SelectedPostSubmissionEvaluationResult.model_construct(
        **fields,
        result_digest="sha256:" + "0" * 64,
    )
    fields["result_digest"] = canonical_json_hash(
        candidate.model_dump(mode="json", exclude={"result_digest"})
    )
    return SelectedPostSubmissionEvaluationResult.model_validate(fields)


class SelectedPostSubmitInfrastructureUnavailable(RuntimeError):
    """Retain a recoverable POST infrastructure category, never a work verdict."""

    def __init__(self, code: str) -> None:
        if code not in {
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        }:
            raise ValueError("selected POST infrastructure failure is invalid")
        self.code = code
        super().__init__(code)


__all__ = (
    "ExternalPostSubmitIsolationFacts",
    "ExternalPostSubmitMemberFacts",
    "SelectedPostSubmitExecutionFacts",
    "SelectedPostSubmitCurrentResultReference",
    "SelectedPostSubmitInfrastructureUnavailable",
    "SelectedPostSubmitLockedContext",
    "SelectedPostSubmissionContent",
    "SelectedPostSubmissionEvaluationRequest",
    "SelectedPostSubmissionEvaluationResult",
    "make_selected_post_submit_request",
    "make_selected_post_submit_result",
)
