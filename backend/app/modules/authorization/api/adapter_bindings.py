"""Public AUTH facts for planned compensation adapter-binding actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import TypeAlias
from uuid import UUID

from .action_ids import ActionId

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")
_ROUTE_KEY = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,119}\Z")


def _require_token(name: str, value: str) -> None:
    """Reject values outside the bounded canonical-token grammar."""
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{name} must be a bounded canonical token")


def _require_uuid(name: str, value: UUID) -> None:
    """Reject identifiers that are not already parsed UUID values."""
    if not isinstance(value, UUID):
        raise ValueError(f"{name} must be a UUID")


def _require_route_key(value: str) -> None:
    """Enforce the canonical compensation adapter route-key grammar."""
    if not isinstance(value, str) or not _ROUTE_KEY.fullmatch(value) or ".." in value:
        raise ValueError("route_key must be canonical and traversal-free")


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingReadFacts:
    """Exact project and binding identity for a planned binding read."""

    project_id: UUID
    adapter_binding_id: UUID

    def __post_init__(self) -> None:
        """Validate the exact project and binding identifiers."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("adapter_binding_id", self.adapter_binding_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingCreateFacts:
    """Server-owned facts for one planned binding creation."""

    project_id: UUID
    instrument: str
    unit: str
    adapter_actor_id: UUID
    route_key: str

    def __post_init__(self) -> None:
        """Validate the binding creation identity and routing facts."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("adapter_actor_id", self.adapter_actor_id)
        _require_token("instrument", self.instrument)
        _require_token("unit", self.unit)
        _require_route_key(self.route_key)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingSuspendFacts:
    """Exact active binding targeted by a planned suspension."""

    project_id: UUID
    adapter_binding_id: UUID
    expected_status: str = "active"

    def __post_init__(self) -> None:
        """Require an exact active binding as the suspension target."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("adapter_binding_id", self.adapter_binding_id)
        if self.expected_status != "active":
            raise ValueError("suspension requires active binding status")


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingResumeFacts:
    """Exact suspended binding targeted by a planned resumption."""

    project_id: UUID
    adapter_binding_id: UUID
    expected_status: str = "suspended"

    def __post_init__(self) -> None:
        """Require an exact suspended binding as the resumption target."""
        _require_uuid("project_id", self.project_id)
        _require_uuid("adapter_binding_id", self.adapter_binding_id)
        if self.expected_status != "suspended":
            raise ValueError("resumption requires suspended binding status")


AdapterBindingFacts: TypeAlias = (
    AdapterBindingReadFacts
    | AdapterBindingCreateFacts
    | AdapterBindingSuspendFacts
    | AdapterBindingResumeFacts
)

_FACT_TYPE_BY_ACTION = {
    "compensation.adapter_binding.read": AdapterBindingReadFacts,
    "compensation.adapter_binding.create": AdapterBindingCreateFacts,
    "compensation.adapter_binding.suspend": AdapterBindingSuspendFacts,
    "compensation.adapter_binding.resume": AdapterBindingResumeFacts,
}


def adapter_binding_resource_digest(action_id: ActionId, facts: AdapterBindingFacts) -> str:
    """Hash one exact action and its immutable adapter-binding facts."""
    action = str(action_id)
    expected_type = _FACT_TYPE_BY_ACTION.get(action)
    if expected_type is None or type(facts) is not expected_type:
        raise ValueError("adapter-binding action does not match resource facts")
    canonical = json.dumps(
        {
            "domain": "workstream.authorization.adapter_binding.v1",
            "action_id": action,
            "resource_type": "compensation_adapter_binding",
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
