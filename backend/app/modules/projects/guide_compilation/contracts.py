"""Strict internal values for durable unified guide compilation."""

from __future__ import annotations

from enum import StrEnum
import json
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import (
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    canonical_project_guide_compilation_context_bytes,
    validate_project_guide_compilation_result,
)


class CompilationAttemptStatus(StrEnum):
    """Closed provider-attempt states persisted by the crash fence."""

    RESERVED = "reserved"
    PROVIDER_UNCERTAIN = "provider_uncertain"
    ACCEPTED = "accepted"
    INVALID_TERMINAL = "invalid_terminal"
    PERSISTED = "persisted"


class CompilationRecoveryClassification(StrEnum):
    """Bounded hidden recovery outcomes safe for operator inspection."""

    RESERVED = "reserved"
    PROVIDER_UNCERTAIN = "provider_uncertain"
    ACCEPTED_NOT_PERSISTED = "accepted_not_persisted"
    PERSISTED = "persisted"
    INVALID_TERMINAL = "invalid_terminal"


class CompilationAttemptIdentity(BaseModel):
    """Complete immutable identity of one logical provider attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    guide_id: UUID
    guide_version: str = Field(min_length=1, max_length=50)
    source_snapshot_id: UUID
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    setup_run_id: UUID
    setup_generation: int = Field(ge=1)
    canonical_input_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    guide_material_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_catalogue_id: str = Field(min_length=1, max_length=160)
    pre_catalogue_version: str = Field(min_length=1, max_length=100)
    pre_catalogue_schema_version: str = Field(min_length=1, max_length=160)
    pre_catalogue_manifest_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    post_catalogue_id: str = Field(min_length=1, max_length=160)
    post_catalogue_version: str = Field(min_length=1, max_length=100)
    post_catalogue_schema_version: str = Field(min_length=1, max_length=160)
    post_catalogue_manifest_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    agent_identity: str = Field(min_length=1, max_length=100)
    agent_version: str = Field(min_length=1, max_length=100)
    instruction_version: str = Field(min_length=1, max_length=100)

    @classmethod
    def from_context(
        cls, context: ProjectGuideCompilationContext, *, agent_version: str
    ) -> CompilationAttemptIdentity:
        """Derive server-owned identity from one strict provider context."""
        material = context.material
        return cls(
            project_id=UUID(material.project_id),
            guide_id=UUID(material.guide_id),
            guide_version=material.guide_version,
            source_snapshot_id=UUID(material.source_snapshot_id),
            source_snapshot_hash=material.source_snapshot_hash,
            setup_run_id=context.setup_run_id,
            setup_generation=context.setup_generation,
            canonical_input_hash=canonical_json_hash(
                json.loads(canonical_project_guide_compilation_context_bytes(context))
            ),
            guide_material_hash=material.canonical_payload_sha256,
            pre_catalogue_id=context.pre_submission_capabilities.catalogue_id,
            pre_catalogue_version=context.pre_submission_capabilities.version,
            pre_catalogue_schema_version=context.pre_submission_capabilities.schema_version,
            pre_catalogue_manifest_hash=context.pre_submission_capabilities.manifest_sha256,
            post_catalogue_id=context.post_submission_capabilities.catalogue_id,
            post_catalogue_version=context.post_submission_capabilities.source_version,
            post_catalogue_schema_version=context.post_submission_capabilities.schema_version,
            post_catalogue_manifest_hash=context.post_submission_capabilities.manifest_sha256,
            agent_identity=context.agent_identity,
            agent_version=agent_version,
            instruction_version=context.instruction_version,
        )

    def provider_idempotency_key(self) -> UUID:
        """Derive the only provider key permitted for this exact identity."""
        return uuid5(
            NAMESPACE_URL,
            "workstream.project-guide-compilation-attempt.v1:"
            + canonical_json_hash(self.model_dump(mode="json")),
        )


class CompilationComponentHashes(BaseModel):
    """Named canonical hashes for every independently projected component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sufficiency_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    requirement_inventory_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_submit_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    post_submit_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    capability_suggestions_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    setup_notes_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AcceptedCompilationResult(BaseModel):
    """Canonical accepted provider output retained across a crash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_result: dict[str, Any]
    result_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    component_hashes: CompilationComponentHashes

    @model_validator(mode="after")
    def validate_hashes(self) -> AcceptedCompilationResult:
        """Reject reconstructed accepted output whose bytes drift."""
        expected = accepted_compilation_result(
            ProjectGuideCompilationResult.model_validate(self.canonical_result)
        )
        if self.result_hash != expected.result_hash or self.component_hashes != expected.component_hashes:
            raise ValueError("accepted compilation result hashes are invalid")
        return self


def accepted_compilation_result(result: ProjectGuideCompilationResult) -> AcceptedCompilationResult:
    """Canonicalize and hash all unified compilation result components."""
    body = result.model_dump(mode="json")
    artifact = body["submission_artifact_policy"]
    return AcceptedCompilationResult.model_construct(
        canonical_result=body,
        result_hash=canonical_json_hash(body),
        component_hashes=CompilationComponentHashes(
            sufficiency_hash=canonical_json_hash(
                {"status": body["status"], "findings": body["findings"]}
            ),
            artifact_policy_hash=canonical_json_hash(artifact),
            requirement_inventory_hash=canonical_json_hash(
                {"requirements": body["requirements"]}
            ),
            pre_submit_hash=canonical_json_hash(
                {"pre_submit_bindings": body["pre_submit_bindings"]}
            ),
            post_submit_hash=canonical_json_hash(
                {"post_submit_bindings": body["post_submit_bindings"]}
            ),
            capability_suggestions_hash=canonical_json_hash(
                {"capability_suggestions": body["capability_suggestions"]}
            ),
            setup_notes_hash=canonical_json_hash({"setup_notes": body["setup_notes"]}),
        ),
    )


def validate_accepted_compilation_result(
    *,
    identity: CompilationAttemptIdentity,
    context: ProjectGuideCompilationContext,
    accepted: AcceptedCompilationResult,
) -> ProjectGuideCompilationResult:
    """Revalidate stored untrusted output against freshly loaded context."""
    current = CompilationAttemptIdentity.from_context(
        context, agent_version=identity.agent_version
    )
    if identity != current:
        raise ValueError("compilation context no longer matches the attempt")
    result = ProjectGuideCompilationResult.model_validate(accepted.canonical_result)
    validate_project_guide_compilation_result(context, result)
    if accepted != accepted_compilation_result(result):
        raise ValueError("accepted compilation result no longer matches its hashes")
    return result
