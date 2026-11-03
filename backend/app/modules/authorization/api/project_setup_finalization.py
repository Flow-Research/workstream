"""Dependency-free, unavailable-by-default setup finalization authority contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, fields
import hashlib
import json
import re
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RETAINED_COMPONENT_KEYS = frozenset(
    {
        "sufficiency_hash",
        "artifact_policy_hash",
        "requirement_inventory_hash",
        "pre_submit_hash",
        "post_submit_hash",
        "capability_suggestions_hash",
        "setup_notes_hash",
    }
)
_COMPONENT_KEYS = (_RETAINED_COMPONENT_KEYS - {
    "capability_suggestions_hash", "setup_notes_hash"
}) | {"schema_version"}
_CURRENT_RESULT_SCHEMA = "project_guide_check_specification.v1"
_CURRENT_HASH_SCHEMA = "project_guide_check_specification_hashes.v1"
FINALIZATION_ACTION = "project.setup_run.update"
FINALIZATION_PERMISSION = "project.guide.manage"
FINALIZATION_SERVICE = "workstream.project.setup"
FINALIZATION_RESOURCE = "project_guide_setup_finalization"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectSetupFinalizationLocator:
    """Stable natural selector known before PROJECTS takes owner locks."""

    project_id: UUID
    setup_run_id: UUID
    setup_generation: int
    compilation_id: UUID

    def __post_init__(self) -> None:
        """Require parsed identities."""
        if not all(
            isinstance(value, UUID)
            for value in (self.project_id, self.setup_run_id, self.compilation_id)
        ) or type(self.setup_generation) is not int or self.setup_generation <= 0:
            raise ValueError("finalization locator IDs must be UUIDs")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectSetupFinalizationFacts:
    """Exact immutable facts recomposed under the product serialization locks."""

    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    celery_task_id: UUID
    source_state_digest: str
    operation_id: UUID
    correlation_id: UUID
    finalization_id: UUID
    attempt_id: UUID
    request_operation_id: UUID
    provider_idempotency_key: UUID
    compilation_id: UUID
    canonical_input_hash: str
    result_hash: str
    result_schema_version: str
    compilation_agent_name: str
    compilation_agent_version: str
    component_hashes: tuple[tuple[str, str], ...]
    result_classification: str
    setup_outcome: str
    sufficiency_operation_id: UUID
    sufficiency_report_id: UUID
    sufficiency_output_digest: str
    artifact_policy_operation_id: UUID | None
    artifact_policy_id: UUID | None
    artifact_policy_output_digest: str | None

    def __post_init__(self) -> None:
        """Reject malformed scalars and partial or mismatched policy custody."""
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "component_hashes":
                _validate_components(value, self.result_schema_version)
            elif field.name == "setup_generation":
                if type(value) is not int or value <= 0:
                    raise ValueError("setup generation must be positive")
            elif value is None and field.name.startswith("artifact_policy_"):
                continue
            elif field.name.endswith(("_hash", "_digest")):
                if not isinstance(value, str) or not _HASH.fullmatch(value):
                    raise ValueError(f"{field.name} must be a canonical digest")
            elif field.name.endswith("_id") or field.name == "provider_idempotency_key":
                if not isinstance(value, UUID):
                    raise ValueError(f"{field.name} must be a UUID")
            elif not isinstance(value, str) or not value.strip() or len(value) > 160:
                raise ValueError(f"{field.name} must be a bounded string")
        if any(value.version != 7 for value in (self.finalization_id, self.operation_id)):
            raise ValueError("finalization record identities must be UUIDv7")
        policy = (
            self.artifact_policy_operation_id,
            self.artifact_policy_id,
            self.artifact_policy_output_digest,
        )
        if self.result_classification == "guide_blocked":
            valid = self.setup_outcome == "sufficiency_blocked" and all(x is None for x in policy)
        else:
            valid = (
                self.result_classification in {"draft_ready", "draft_ready_with_warnings"}
                and self.setup_outcome == "policy_draft_ready"
                and all(x is not None for x in policy)
            )
        if not valid:
            raise ValueError("finalization classification and projection shape disagree")


def _validate_components(value: object, result_schema: str) -> None:
    """Keep all component hashes deeply immutable and canonically ordered."""
    if not isinstance(value, tuple) or any(
        not isinstance(item, tuple) or len(item) != 2 for item in value
    ):
        raise ValueError("component hashes must be immutable pairs")
    if result_schema == _CURRENT_RESULT_SCHEMA:
        keys = _COMPONENT_KEYS
    elif result_schema == "project_guide_compilation_result.v1":
        # Retained receipt facts remain hash-verifiable; consume_new rejects this format.
        keys = _RETAINED_COMPONENT_KEYS
    else:
        raise ValueError("result schema is invalid")
    if len(value) != len(keys) or {item[0] for item in value} != keys:
        raise ValueError("component hash keys are invalid")
    if value != tuple(sorted(value)) or any(
        (item[1] != _CURRENT_HASH_SCHEMA if item[0] == "schema_version" else
         not isinstance(item[1], str) or not _HASH.fullmatch(item[1])) for item in value
    ):
        raise ValueError("component hash values are invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectSetupFinalizationAuthorityReceipt:
    """Complete authority envelope checked by PROJECTS before product mutation."""

    decision_event_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: str
    action_id: str
    permission_id: str
    scope_project_id: UUID
    resource_type: str
    resource_id: UUID
    resource_context_digest: str

    def __post_init__(self) -> None:
        """Validate receipt representation without replacing product agreement checks."""
        for name in (
            "decision_event_id",
            "actor_profile_id",
            "identity_link_id",
            "scope_project_id",
            "resource_id",
        ):
            if not isinstance(getattr(self, name), UUID):
                raise ValueError("authority receipt identifiers must be UUIDs")
        if not isinstance(self.resource_context_digest, str) or not _HASH.fullmatch(
            self.resource_context_digest
        ):
            raise ValueError("authority receipt digest is invalid")


class PreparedSetupFinalization(ABC):
    """Nominal process-local handle; concrete AUTH binding belongs to AUTH-12B2."""

    __slots__ = ()

    def __reduce_ex__(self, _protocol):
        """Never serialize or reconstruct prepared authority."""
        raise TypeError("prepared finalization authority is process-local")

    def __copy__(self):
        """Never copy prepared authority."""
        raise TypeError("prepared finalization authority cannot be copied")

    def __deepcopy__(self, _memo):
        """Never deepcopy prepared authority."""
        raise TypeError("prepared finalization authority cannot be copied")

    @abstractmethod
    async def consume_new(
        self, facts: ProjectSetupFinalizationFacts
    ) -> ProjectSetupFinalizationAuthorityReceipt:
        """Consume once within the issuing session and root transaction."""

    @abstractmethod
    async def validate_replay(
        self, facts: ProjectSetupFinalizationFacts, stored_decision_id: UUID
    ) -> None:
        """Validate current service authority and exact stored decision without consumption."""


class SetupFinalizationAuthorizationPort(Protocol):
    """Prepare and close one purpose-specific capability, exactly once in finally."""

    def prepare_setup_finalization(
        self, locator: ProjectSetupFinalizationLocator
    ) -> AbstractAsyncContextManager[PreparedSetupFinalization]: ...


def setup_finalization_preparation_identity(
    setup_run_id: UUID, setup_generation: int, compilation_id: UUID
) -> tuple[UUID, UUID]:
    """Derive non-row AUTH request/correlation selectors for natural custody."""
    if (
        not isinstance(setup_run_id, UUID)
        or not isinstance(compilation_id, UUID)
        or type(setup_generation) is not int
        or setup_generation <= 0
    ):
        raise ValueError("finalization identity seed is invalid")
    seed = f"{setup_run_id}:{setup_generation}:{compilation_id}"
    return (
        uuid5(NAMESPACE_URL, f"workstream.project-guide-setup-finalization:operation:{seed}"),
        uuid5(NAMESPACE_URL, f"workstream.project-guide-setup-finalization:correlation:{seed}"),
    )


def setup_finalization_fact_values(facts: ProjectSetupFinalizationFacts) -> dict:
    """Encode every key, including explicit nulls and named component hashes."""
    return {
        field.name: (
            str(value)
            if isinstance(value := getattr(facts, field.name), UUID)
            else dict(value)
            if field.name == "component_hashes"
            else value
        )
        for field in fields(facts)
    }


def _digest(domain: str, facts: dict) -> str:
    """Use the repository canonical JSON convention without runtime dependencies."""
    body = json.dumps(
        {"domain": domain, "facts": facts},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def setup_finalization_facts_digest(facts: ProjectSetupFinalizationFacts) -> str:
    """Hash the entire locked finalization fact vector."""
    return _digest(
        "workstream.project_guide_setup_finalization.facts.v1",
        setup_finalization_fact_values(facts),
    )


def setup_finalization_authority_digest(
    facts: ProjectSetupFinalizationFacts, actor_profile_id: UUID, identity_link_id: UUID
) -> str:
    """Bind exact product facts to fixed service authority and finalization resource."""
    return _digest(
        "workstream.project_guide_setup_finalization.authority.v1",
        {
            "action_id": FINALIZATION_ACTION,
            "permission_id": FINALIZATION_PERMISSION,
            "resource_type": FINALIZATION_RESOURCE,
            "resource_id": str(facts.finalization_id),
            "scope_project_id": str(facts.project_id),
            "actor_profile_id": str(actor_profile_id),
            "identity_link_id": str(identity_link_id),
            "service_identity": FINALIZATION_SERVICE,
            "facts_digest": setup_finalization_facts_digest(facts),
        },
    )


__all__ = (
    "FINALIZATION_ACTION",
    "FINALIZATION_PERMISSION",
    "FINALIZATION_SERVICE",
    "FINALIZATION_RESOURCE",
    "PreparedSetupFinalization",
    "SetupFinalizationAuthorizationPort",
    "ProjectSetupFinalizationLocator",
    "ProjectSetupFinalizationFacts",
    "ProjectSetupFinalizationAuthorityReceipt",
    "setup_finalization_preparation_identity",
    "setup_finalization_fact_values",
    "setup_finalization_facts_digest",
    "setup_finalization_authority_digest",
)
