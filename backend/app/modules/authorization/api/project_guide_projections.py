"""Dependency-free AUTH contracts for hidden guide-compilation projections."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, fields
import hashlib
import json
import re
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SERVICE_IDENTITY = "workstream.project.setup"
_SUFFICIENCY_COMPONENT = "guide_sufficiency"
_POLICY_COMPONENT = "submission_artifact_policy"


def _uuid(kind: str, attempt_id: UUID, component: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"workstream.project-guide-projection:{kind}:{attempt_id}:{component}",
    )


def _canonical_hash(domain: str, facts: object) -> str:
    body = {
        "domain": domain,
        "facts": {
            field.name: (
                str(value) if isinstance(value := getattr(facts, field.name), UUID) else value
            )
            for field in fields(facts)
        },
    }
    encoded = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_facts(value: object) -> None:
    for field in fields(value):
        item = getattr(value, field.name)
        if field.name in {"setup_generation", "material_byte_count"}:
            if type(item) is not int or item < 0 or (
                field.name == "setup_generation" and item == 0
            ):
                raise ValueError(f"{field.name} is invalid")
        elif field.name.endswith(("_hash", "_digest", "_sha256")):
            if not isinstance(item, str) or not _HASH.fullmatch(item):
                raise ValueError(f"{field.name} must be a canonical SHA-256 digest")
        elif field.name.endswith("_id") or field.name in {
            "project_id",
            "attempt_id",
            "provider_idempotency_key",
        }:
            if not isinstance(item, UUID):
                raise ValueError(f"{field.name} must be a UUID")
        elif item is not None and not isinstance(item, str):
            raise ValueError(f"{field.name} must be a string or null")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectGuideProjectionLocator:
    """Minimal server locator supplied before AUTH acquires its locks."""

    project_id: UUID
    attempt_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, UUID) or not isinstance(self.attempt_id, UUID):
            raise ValueError("projection locator IDs must be UUIDs")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectGuideProjectionIdentity:
    """AUTH-issued immutable identity for one projection operation."""

    operation_id: UUID
    correlation_id: UUID
    output_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: str = _SERVICE_IDENTITY

    def __post_init__(self) -> None:
        for item in (
            self.operation_id,
            self.correlation_id,
            self.output_id,
            self.actor_profile_id,
            self.identity_link_id,
        ):
            if not isinstance(item, UUID):
                raise ValueError("projection identity IDs must be UUIDs")
        if self.service_identity != _SERVICE_IDENTITY:
            raise ValueError("projection service identity is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class GuideSufficiencyProjectionFacts:
    """Complete locked product facts for one sufficiency projection."""

    project_id: UUID
    attempt_id: UUID
    request_operation_id: UUID
    provider_idempotency_key: UUID
    compilation_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    celery_task_id: UUID
    source_state_digest: str
    result_hash: str
    component_hash: str
    result_schema_version: str
    compilation_agent_name: str
    compilation_agent_version: str
    material_sha256: str
    material_byte_count: int
    report_id: UUID
    report_content_digest: str

    def __post_init__(self) -> None:
        _validate_facts(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactPolicyProjectionFacts:
    """Complete locked product facts for one artifact-policy projection."""

    project_id: UUID
    attempt_id: UUID
    request_operation_id: UUID
    provider_idempotency_key: UUID
    compilation_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    celery_task_id: UUID
    source_state_digest: str
    result_hash: str
    component_hash: str
    result_schema_version: str
    compilation_agent_name: str
    compilation_agent_version: str
    prior_operation_id: UUID
    sufficiency_report_id: UUID
    sufficiency_report_digest: str
    policy_id: UUID
    policy_content_digest: str

    def __post_init__(self) -> None:
        _validate_facts(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectGuideProjectionAuthorityReceipt:
    """Bounded authority receipt returned after one successful consumption."""

    decision_event_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: str
    resource_context_digest: str

    def __post_init__(self) -> None:
        for item in (
            self.decision_event_id,
            self.actor_profile_id,
            self.identity_link_id,
        ):
            if not isinstance(item, UUID):
                raise ValueError("projection authority receipt IDs must be UUIDs")
        if self.service_identity != _SERVICE_IDENTITY:
            raise ValueError("projection service identity is invalid")
        if not isinstance(self.resource_context_digest, str) or not _HASH.fullmatch(
            self.resource_context_digest
        ):
            raise ValueError("projection resource digest is invalid")


class PreparedGuideSufficiencyProjection(Protocol):
    """Single-use sufficiency authority held only inside one transaction."""

    @property
    def identity(self) -> ProjectGuideProjectionIdentity: ...

    async def consume_new(
        self, facts: GuideSufficiencyProjectionFacts
    ) -> ProjectGuideProjectionAuthorityReceipt: ...

    async def validate_replay(
        self, facts: GuideSufficiencyProjectionFacts, stored_decision_id: UUID
    ) -> None: ...


class PreparedArtifactPolicyProjection(Protocol):
    """Single-use policy authority held only inside one transaction."""

    @property
    def identity(self) -> ProjectGuideProjectionIdentity: ...

    async def consume_new(
        self, facts: ArtifactPolicyProjectionFacts
    ) -> ProjectGuideProjectionAuthorityReceipt: ...

    async def validate_replay(
        self, facts: ArtifactPolicyProjectionFacts, stored_decision_id: UUID
    ) -> None: ...


class GuideSufficiencyProjectionAuthorizationPort(Protocol):
    """Prepare fixed-service authority for only the sufficiency projection."""

    def prepare_sufficiency_projection(
        self, locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedGuideSufficiencyProjection]: ...


class ArtifactPolicyProjectionAuthorizationPort(Protocol):
    """Prepare fixed-service authority for only the policy projection."""

    def prepare_artifact_policy_projection(
        self, locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedArtifactPolicyProjection]: ...


def guide_sufficiency_projection_identity(
    *, attempt_id: UUID, actor_profile_id: UUID, identity_link_id: UUID
) -> ProjectGuideProjectionIdentity:
    """Derive the fixed identity for one sufficiency projection."""
    return _projection_identity(
        attempt_id, _SUFFICIENCY_COMPONENT, actor_profile_id, identity_link_id
    )


def artifact_policy_projection_identity(
    *, attempt_id: UUID, actor_profile_id: UUID, identity_link_id: UUID
) -> ProjectGuideProjectionIdentity:
    """Derive the fixed identity for one artifact-policy projection."""
    return _projection_identity(
        attempt_id, _POLICY_COMPONENT, actor_profile_id, identity_link_id
    )


def _projection_identity(
    attempt_id: UUID, component: str, actor_profile_id: UUID, identity_link_id: UUID
) -> ProjectGuideProjectionIdentity:
    return ProjectGuideProjectionIdentity(
        operation_id=_uuid("operation", attempt_id, component),
        correlation_id=_uuid("correlation", attempt_id, component),
        output_id=_uuid("output", attempt_id, component),
        actor_profile_id=actor_profile_id,
        identity_link_id=identity_link_id,
    )


def guide_sufficiency_projection_facts_digest(
    facts: GuideSufficiencyProjectionFacts,
) -> str:
    """Hash the exact sufficiency projection facts."""
    return _canonical_hash(
        "workstream.project_guide_sufficiency_projection.facts.v1", facts
    )


def artifact_policy_projection_facts_digest(
    facts: ArtifactPolicyProjectionFacts,
) -> str:
    """Hash the exact artifact-policy projection facts."""
    return _canonical_hash(
        "workstream.project_submission_artifact_policy_projection.facts.v1", facts
    )


def projection_authority_digest(
    *,
    component: str,
    identity: ProjectGuideProjectionIdentity,
    project_id: UUID,
    facts_digest: str,
) -> str:
    """Hash the fixed-service authority envelope for one component."""
    if component == _SUFFICIENCY_COMPONENT:
        action_id = "project.guide_sufficiency.run"
        permission_id = "project.guide.manage"
        resource_type = "project_guide_sufficiency_projection"
        domain = "workstream.project_guide_sufficiency_projection.authority.v1"
    elif component == _POLICY_COMPONENT:
        action_id = "project.submission_artifact_policy.derive"
        permission_id = "project.effective_policy.manage"
        resource_type = "project_submission_artifact_policy_projection"
        domain = "workstream.project_submission_artifact_policy_projection.authority.v1"
    else:
        raise ValueError("projection component is invalid")
    return _canonical_hash(
        domain,
        _AuthorityFacts(
            action_id=action_id,
            permission_id=permission_id,
            resource_type=resource_type,
            resource_id=identity.operation_id,
            scope_project_id=project_id,
            actor_profile_id=identity.actor_profile_id,
            identity_link_id=identity.identity_link_id,
            service_identity=identity.service_identity,
            facts_digest=facts_digest,
        ),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _AuthorityFacts:
    action_id: str
    permission_id: str
    resource_type: str
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: str
    facts_digest: str


__all__ = (
    "ArtifactPolicyProjectionAuthorizationPort",
    "ArtifactPolicyProjectionFacts",
    "GuideSufficiencyProjectionAuthorizationPort",
    "GuideSufficiencyProjectionFacts",
    "PreparedArtifactPolicyProjection",
    "PreparedGuideSufficiencyProjection",
    "ProjectGuideProjectionAuthorityReceipt",
    "ProjectGuideProjectionIdentity",
    "ProjectGuideProjectionLocator",
    "artifact_policy_projection_facts_digest",
    "artifact_policy_projection_identity",
    "guide_sufficiency_projection_facts_digest",
    "guide_sufficiency_projection_identity",
    "projection_authority_digest",
)
