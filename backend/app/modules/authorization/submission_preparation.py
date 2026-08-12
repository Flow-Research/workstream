"""Strict AUTH-owned resource facts for contributor bundle preparation."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)


class SubmissionBundlePreparationRequestContext(BaseModel):
    """Contributor selectors known before reading submission bytes."""
    model_config = _STRICT_FROZEN
    scope_project_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None


class SubmissionBundlePreparationPreflightResourceContext(
    SubmissionBundlePreparationRequestContext
):
    """Exact selectors revalidated before submission bytes are read."""
    resource_type: Literal["submission_bundle_preparation_preflight"]
    resource_id: UUID


class SubmissionBundlePreparationResourceContext(SubmissionBundlePreparationRequestContext):
    """Exact final contributor, policy, evidence, and artifact facts."""
    resource_type: Literal["submission_bundle_preparation"]
    resource_id: UUID
    predecessor_submission_version: int | None = Field(default=None, ge=1)
    pre_submit_evidence_set_id: UUID
    prepared_generation_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_policy_id: UUID
    effective_policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_submit_policy_id: UUID
    pre_submit_policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_plan_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    semantic_manifest_id: UUID
    semantic_manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    archive_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    archive_byte_count: int = Field(ge=0)
    media_type: Literal["application/zip"]
    storage_scheme: Literal["local", "s3"]
    operation_identity: str = Field(min_length=1)
    replay_durable_intent_id: UUID | None

    @model_validator(mode="after")
    def require_exact_identity_and_predecessor(self):
        """Require a complete generation and predecessor identity."""
        if self.resource_id != self.prepared_generation_id:
            raise ValueError("submission preparation resource must match generation")
        if (self.predecessor_submission_id is None) != (
            self.predecessor_submission_version is None
        ):
            raise ValueError("submission predecessor identity is incomplete")
        return self


def parse_submission_preparation(
    raw: dict,
) -> tuple[dict, str, dict | None, str | None]:
    """Parse caller facts once and return canonical request/final bindings."""
    value = dict(raw)
    for field in (
        "scope_project_id",
        "actor_profile_id",
        "identity_link_id",
        "task_id",
        "assignment_id",
    ):
        value[field] = UUID(str(value[field]))
    if value.get("predecessor_submission_id") is not None:
        value["predecessor_submission_id"] = UUID(str(value["predecessor_submission_id"]))
    request = SubmissionBundlePreparationRequestContext.model_validate(
        {field: value[field] for field in SubmissionBundlePreparationRequestContext.model_fields}
    )
    request_context = request.model_dump(mode="json")
    request_digest = canonical_json_hash({"submission_bundle_preparation": request_context})
    if "prepared_generation_id" not in value:
        return request_context, request_digest, None, None
    for field in (
        "pre_submit_evidence_set_id",
        "prepared_generation_id",
        "guide_id",
        "source_snapshot_id",
        "effective_policy_id",
        "pre_submit_policy_id",
        "semantic_manifest_id",
    ):
        value[field] = UUID(str(value[field]))
    if value.get("replay_durable_intent_id") is not None:
        value["replay_durable_intent_id"] = UUID(str(value["replay_durable_intent_id"]))
    final = SubmissionBundlePreparationResourceContext(
        resource_type="submission_bundle_preparation",
        resource_id=value["prepared_generation_id"],
        **value,
    )
    final_context = final.model_dump(mode="json")
    final_digest = canonical_json_hash(
        {"resource_context": final.model_dump(mode="json", exclude_none=True)}
    )
    return request_context, request_digest, final_context, final_digest


def parse_submission_preparation_or_invalid(raw: dict, invalid_error):
    """Map parsing errors to the opaque prepared-handle failure."""
    try:
        return parse_submission_preparation(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise invalid_error("invalid prepared authorization handle") from exc


def submission_preparation_binding_fields(values: tuple) -> dict:
    """Name canonical preparation values for the PREP binding record."""
    request_context, request_digest, final_context, final_digest = values
    return {
        "submission_preparation_context": request_context,
        "submission_preparation_resource_digest": request_digest,
        "submission_preparation_final_context": final_context,
        "submission_preparation_final_digest": final_digest,
    }


def submission_preparation_binding_matches(
    *,
    request_context: dict | None,
    request_digest: str | None,
    final_context: dict | None,
    final_digest: str | None,
    resource: SubmissionBundlePreparationPreflightResourceContext
    | SubmissionBundlePreparationResourceContext,
) -> bool:
    """Require the consumed facts to equal the prepared request or final facts."""
    if isinstance(resource, SubmissionBundlePreparationResourceContext):
        context = resource.model_dump(mode="json")
        digest = canonical_json_hash(
            {"resource_context": resource.model_dump(mode="json", exclude_none=True)}
        )
        return final_context == context and final_digest == digest
    context = SubmissionBundlePreparationRequestContext.model_validate(
        {
            field: getattr(resource, field)
            for field in SubmissionBundlePreparationRequestContext.model_fields
        }
    ).model_dump(mode="json")
    return request_context == context and request_digest == canonical_json_hash(
        {"submission_bundle_preparation": context}
    )
