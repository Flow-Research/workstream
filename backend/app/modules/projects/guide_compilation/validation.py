"""Revalidation helpers for untrusted durable compilation values."""

from __future__ import annotations

from uuid import UUID

from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    ProjectGuideCompilationExecutePersistFacts,
    project_guide_compilation_execute_resource_digest,
)

from .contracts import (
    AcceptedCompilationResult,
    CompilationAttemptIdentity,
    CompilationComponentHashes,
)
from .models import ProjectGuideCompilationAttempt

TERMINAL_FAILURE_CODES = frozenset(
    {"context_mismatch", "hash_mismatch", "schema_invalid", "unsafe_text"}
)


def identity_from_attempt(attempt: ProjectGuideCompilationAttempt) -> CompilationAttemptIdentity:
    """Reconstruct the strict identity held by a locked attempt."""
    return CompilationAttemptIdentity(
        project_id=UUID(attempt.project_id),
        guide_id=UUID(attempt.guide_id),
        guide_version=attempt.guide_version,
        source_snapshot_id=UUID(attempt.source_snapshot_id),
        source_snapshot_hash=attempt.source_snapshot_hash,
        setup_run_id=UUID(attempt.setup_run_id),
        setup_generation=attempt.setup_generation,
        canonical_input_hash=attempt.canonical_input_hash,
        guide_material_hash=attempt.guide_material_hash,
        pre_catalogue_id=attempt.pre_catalogue_id,
        pre_catalogue_version=attempt.pre_catalogue_version,
        pre_catalogue_schema_version=attempt.pre_catalogue_schema_version,
        pre_catalogue_manifest_hash=attempt.pre_catalogue_manifest_hash,
        post_catalogue_id=attempt.post_catalogue_id,
        post_catalogue_version=attempt.post_catalogue_version,
        post_catalogue_schema_version=attempt.post_catalogue_schema_version,
        post_catalogue_manifest_hash=attempt.post_catalogue_manifest_hash,
        agent_identity=attempt.agent_identity,
        agent_version=attempt.agent_version,
        instruction_version=attempt.instruction_version,
    )


def accepted_from_attempt(attempt: ProjectGuideCompilationAttempt) -> AcceptedCompilationResult:
    """Parse complete accepted custody or fail closed."""
    if (
        attempt.canonical_result is None
        or attempt.result_hash is None
        or attempt.component_hashes is None
    ):
        raise ValueError("accepted compilation result is incomplete")
    return AcceptedCompilationResult(
        canonical_result=attempt.canonical_result,
        result_hash=attempt.result_hash,
        component_hashes=attempt.component_hashes,
    )


def validate_persistence_authority(
    *,
    attempt: ProjectGuideCompilationAttempt,
    accepted: AcceptedCompilationResult,
    actor: ActorIdentityFacts,
    facts: ProjectGuideCompilationExecutePersistFacts,
    expected_predecessor_id: UUID | None,
) -> None:
    """Bind fixed-service custody to exact attempt and accepted hashes."""
    identity = identity_from_attempt(attempt)
    expected_hashes = CompilationComponentHashes(
        sufficiency_hash=facts.sufficiency_component_hash,
        artifact_policy_hash=facts.artifact_policy_component_hash,
        requirement_inventory_hash=facts.requirement_inventory_component_hash,
        pre_submit_hash=facts.pre_submit_policy_component_hash,
        post_submit_hash=facts.post_submit_policy_component_hash,
        capability_suggestions_hash=facts.capability_suggestions_component_hash,
        setup_notes_hash=facts.setup_notes_component_hash,
    )
    if (
        actor.actor_kind is not ActorKind.SERVICE
        or actor.service_identity != "workstream.project.setup"
        or facts.attempt_id != attempt.id
        or facts.provider_idempotency_key != attempt.provider_idempotency_key
        or facts.project_id != identity.project_id
        or facts.guide_id != identity.guide_id
        or facts.guide_version != identity.guide_version
        or facts.source_snapshot_id != identity.source_snapshot_id
        or facts.source_snapshot_hash != identity.source_snapshot_hash
        or facts.canonical_input_hash != identity.canonical_input_hash
        or facts.guide_material_hash != identity.guide_material_hash
        or facts.setup_run_id != identity.setup_run_id
        or facts.setup_generation != identity.setup_generation
        or facts.pre_catalogue_id != identity.pre_catalogue_id
        or facts.pre_catalogue_version != identity.pre_catalogue_version
        or facts.pre_catalogue_schema_version != identity.pre_catalogue_schema_version
        or facts.pre_catalogue_manifest_hash != identity.pre_catalogue_manifest_hash
        or facts.post_catalogue_id != identity.post_catalogue_id
        or facts.post_catalogue_version != identity.post_catalogue_version
        or facts.post_catalogue_schema_version != identity.post_catalogue_schema_version
        or facts.post_catalogue_manifest_hash != identity.post_catalogue_manifest_hash
        or facts.agent_identity != identity.agent_identity
        or facts.agent_version != identity.agent_version
        or facts.instruction_version != identity.instruction_version
        or facts.expected_predecessor_compilation_id != expected_predecessor_id
        or facts.result_hash != accepted.result_hash
        or expected_hashes != accepted.component_hashes
        or facts.resource_context_digest
        != project_guide_compilation_execute_resource_digest(actor, facts)
    ):
        raise ValueError("compilation persistence authority mismatch")


def validate_terminal_failure_code(value: str) -> str:
    """Return one bounded allowlisted terminal reason."""
    if value not in TERMINAL_FAILURE_CODES:
        raise ValueError("compilation failure code is invalid")
    return value
