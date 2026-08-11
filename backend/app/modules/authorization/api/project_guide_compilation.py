"""Public AUTH contract for hidden unified project-guide compilation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import hashlib
import json
import re
from typing import Protocol, TypeVar
from uuid import UUID

from .facts import ActorIdentityFacts

_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")
_UUID_FIELDS = frozenset(
    {
        "project_id",
        "guide_id",
        "source_snapshot_id",
        "setup_run_id",
        "operation_id",
        "request_id",
        "idempotency_key",
        "expected_predecessor_compilation_id",
        "attempt_id",
        "provider_idempotency_key",
    }
)


def _validate_common(value: object) -> None:
    """Validate bounded scalar values without importing product code."""
    for field in fields(value):
        item = getattr(value, field.name)
        if field.name == "expected_predecessor_compilation_id" and item is None:
            continue
        if field.name == "setup_generation":
            if type(item) is not int or item <= 0:
                raise ValueError("setup generation must be positive")
            continue
        if field.name in _UUID_FIELDS:
            if not isinstance(item, UUID):
                raise ValueError(f"{field.name} must be a UUID")
            continue
        if field.name.endswith(("_hash", "_digest")):
            if not isinstance(item, str) or not _HASH.fullmatch(item):
                raise ValueError(f"{field.name} must be a canonical SHA-256 digest")
            continue
        if not isinstance(item, str) or not _TOKEN.fullmatch(item):
            raise ValueError(f"{field.name} must be a bounded canonical token")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectGuideCompilationRequestFacts:
    """Exact lineage and configuration facts for one request/recovery."""

    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    canonical_input_hash: str
    guide_material_hash: str
    setup_run_id: UUID
    setup_generation: int
    operation_id: UUID
    request_id: UUID
    idempotency_key: UUID
    pre_catalogue_id: str
    pre_catalogue_version: str
    pre_catalogue_schema_version: str
    pre_catalogue_manifest_hash: str
    post_catalogue_id: str
    post_catalogue_version: str
    post_catalogue_schema_version: str
    post_catalogue_manifest_hash: str
    agent_identity: str
    agent_version: str
    instruction_version: str
    expected_predecessor_compilation_id: UUID | None = None

    def __post_init__(self) -> None:
        _validate_common(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectGuideCompilationExecutePreflightFacts(ProjectGuideCompilationRequestFacts):
    """Exact reserved attempt facts checked before future provider I/O."""

    attempt_id: UUID
    provider_idempotency_key: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectGuideCompilationExecutePersistFacts(ProjectGuideCompilationExecutePreflightFacts):
    """Exact accepted-result hashes consumed with immutable persistence."""

    result_hash: str
    sufficiency_component_hash: str
    artifact_policy_component_hash: str
    requirement_inventory_component_hash: str
    pre_submit_policy_component_hash: str
    post_submit_policy_component_hash: str
    capability_suggestions_component_hash: str
    setup_notes_component_hash: str
    resource_context_digest: str


def project_guide_compilation_execute_resource_digest(
    actor: ActorIdentityFacts,
    facts: ProjectGuideCompilationExecutePersistFacts,
) -> str:
    """Hash the complete public AUTH resource context for final persistence."""
    fact_values = asdict(facts)
    fact_values.pop("resource_context_digest")
    canonical = json.dumps(
        {
            "action_id": "project.guide_compilation.execute",
            "actor_profile_id": str(actor.actor_profile_id),
            "identity_link_id": str(actor.identity_link_id),
            "service_identity": actor.service_identity,
            "facts": {
                key: str(value) if isinstance(value, UUID) else value
                for key, value in fact_values.items()
            },
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def project_guide_compilation_request_resource_digest(
    actor: ActorIdentityFacts,
    grant_id: UUID,
    facts: ProjectGuideCompilationRequestFacts,
) -> str:
    """Hash the complete Project Manager request/recovery authority context."""
    if actor.actor_kind.value != "human" or actor.service_identity is not None:
        raise ValueError("compilation requests require a human actor")
    if not isinstance(grant_id, UUID):
        raise ValueError("grant_id must be a UUID")
    facts_digest = project_guide_compilation_facts_digest(facts)
    return project_guide_compilation_request_authority_digest(
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        grant_id=grant_id,
        project_id=facts.project_id,
        operation_id=facts.operation_id,
        request_facts_digest=facts_digest,
    )


def project_guide_compilation_facts_digest(
    facts: ProjectGuideCompilationRequestFacts,
) -> str:
    """Hash the complete dependency-free compilation facts envelope."""
    canonical = json.dumps(
        {
            "domain": "workstream.project_guide_compilation.facts.v1",
            "facts": {
                key: str(value) if isinstance(value, UUID) else value
                for key, value in asdict(facts).items()
            },
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def project_guide_compilation_request_authority_digest(
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
    grant_id: UUID,
    project_id: UUID,
    operation_id: UUID,
    request_facts_digest: str,
) -> str:
    """Hash server-selected request authority with caller-owned facts."""
    canonical = json.dumps(
        {
            "action_id": "project.guide_compilation.request",
            "permission_id": "project.guide_compilation.request",
            "resource_type": "project_guide_compilation_request",
            "resource_id": str(operation_id),
            "scope_project_id": str(project_id),
            "actor_profile_id": str(actor_profile_id),
            "identity_link_id": str(identity_link_id),
            "project_manager_grant_id": str(grant_id),
            "request_facts_digest": request_facts_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


PreparedHandleT = TypeVar("PreparedHandleT")


class ProjectGuideCompilationAuthorizationPort(Protocol[PreparedHandleT]):
    """Prepare and consume exact inactive compilation authority."""

    async def prepare_request(
        self, *, actor: ActorIdentityFacts, facts: ProjectGuideCompilationRequestFacts
    ) -> PreparedHandleT: ...

    async def consume_request(
        self,
        *,
        handle: PreparedHandleT,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
    ) -> UUID: ...

    async def authorize_execute_preflight(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
    ) -> None: ...

    async def prepare_execute_persist(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
    ) -> PreparedHandleT: ...

    async def consume_execute_persist(
        self,
        *,
        handle: PreparedHandleT,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
    ) -> UUID: ...
