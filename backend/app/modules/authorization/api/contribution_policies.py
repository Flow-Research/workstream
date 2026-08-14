"""Public AUTH facts for planned ContributionPolicy actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import TypeAlias
from uuid import UUID

from .action_ids import ActionId

_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _require_uuid(name: str, value: UUID) -> None:
    """Reject identifiers that are not already parsed UUID values."""
    if not isinstance(value, UUID):
        raise ValueError(f"{name} must be a UUID")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyReadFacts:
    """Exact policy identity and optional immutable version identity."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID | None = None

    def __post_init__(self) -> None:
        """Validate the project, policy, and optional version identifiers."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("contribution_policy_id", self.contribution_policy_id)
        if self.contribution_policy_version_id is not None:
            _require_uuid(
                "contribution_policy_version_id", self.contribution_policy_version_id
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyCreateDraftFacts:
    """Exact project policy collection targeted by draft creation."""

    project_id: UUID

    def __post_init__(self) -> None:
        """Validate the project collection identifier."""
        _require_uuid("project_id", self.project_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyUpdateDraftFacts:
    """Exact draft version targeted by an update."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    expected_status: str = "draft"

    def __post_init__(self) -> None:
        """Validate exact draft ownership and lifecycle state."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("contribution_policy_id", self.contribution_policy_id)
        _require_uuid("contribution_policy_version_id", self.contribution_policy_version_id)
        if self.expected_status != "draft":
            raise ValueError("policy update requires draft version status")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyPublishFacts:
    """Complete draft content and binding lineage targeted by publication."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    rules_and_definitions_digest: str
    adapter_binding_ids: tuple[UUID, ...]
    expected_status: str = "draft"

    def __post_init__(self) -> None:
        """Require canonical content digest, binding order, and draft state."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("contribution_policy_id", self.contribution_policy_id)
        _require_uuid("contribution_policy_version_id", self.contribution_policy_version_id)
        if not isinstance(self.rules_and_definitions_digest, str) or not _SHA256.fullmatch(
            self.rules_and_definitions_digest
        ):
            raise ValueError("rules_and_definitions_digest must be canonical sha256")
        if not isinstance(self.adapter_binding_ids, tuple) or any(
            not isinstance(value, UUID) for value in self.adapter_binding_ids
        ):
            raise ValueError("adapter_binding_ids must be a UUID tuple")
        canonical_ids = tuple(sorted(self.adapter_binding_ids, key=str))
        if self.adapter_binding_ids != canonical_ids or len(set(canonical_ids)) != len(
            canonical_ids
        ):
            raise ValueError("adapter_binding_ids must be sorted and unique")
        if self.expected_status != "draft":
            raise ValueError("policy publication requires draft version status")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionPolicyRetireFacts:
    """Exact published policy version targeted by retirement."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    expected_status: str = "published"

    def __post_init__(self) -> None:
        """Validate exact published ownership and lifecycle state."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("contribution_policy_id", self.contribution_policy_id)
        _require_uuid("contribution_policy_version_id", self.contribution_policy_version_id)
        if self.expected_status != "published":
            raise ValueError("policy retirement requires published version status")


ContributionPolicyFacts: TypeAlias = (
    ContributionPolicyReadFacts
    | ContributionPolicyCreateDraftFacts
    | ContributionPolicyUpdateDraftFacts
    | ContributionPolicyPublishFacts
    | ContributionPolicyRetireFacts
)

_FACT_TYPE_BY_ACTION = {
    "contribution.policy.read": ContributionPolicyReadFacts,
    "contribution.policy.create_draft": ContributionPolicyCreateDraftFacts,
    "contribution.policy.update_draft": ContributionPolicyUpdateDraftFacts,
    "contribution.policy.publish": ContributionPolicyPublishFacts,
    "contribution.policy.retire": ContributionPolicyRetireFacts,
}


def contribution_policy_resource_digest(
    action_id: ActionId, facts: ContributionPolicyFacts
) -> str:
    """Hash one exact action and its immutable ContributionPolicy facts."""
    action = str(action_id)
    expected_type = _FACT_TYPE_BY_ACTION.get(action)
    if expected_type is None or type(facts) is not expected_type:
        raise ValueError("ContributionPolicy action does not match resource facts")
    canonical = json.dumps(
        {
            "domain": "workstream.authorization.contribution_policy.v1",
            "action_id": action,
            "resource_type": "contribution_policy",
            "facts": _json_facts(facts),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _json_facts(facts: ContributionPolicyFacts) -> dict[str, object]:
    """Convert immutable typed facts to canonical JSON scalar collections."""
    return {
        key: (
            [str(item) for item in value]
            if isinstance(value, tuple)
            else str(value)
            if isinstance(value, UUID)
            else value
        )
        for key, value in asdict(facts).items()
    }
