"""Focused persistence-contract proof for adapter-binding lifecycle truth."""

import hashlib
from uuid import UUID

from app.db.base import Base
from app.modules.compensation.repository import operation_advisory_lock_key


def test_operation_fence_key_is_exact_signed_sha256_prefix() -> None:
    operation_id = UUID("12345678-1234-5678-1234-567812345678")
    prefix = hashlib.sha256(operation_id.bytes).digest()[:8]
    expected = int.from_bytes(prefix, "big", signed=True)
    assert operation_advisory_lock_key(operation_id) == expected


def test_lifecycle_event_metadata_is_append_only_shape() -> None:
    table = Base.metadata.tables["compensation_adapter_binding_lifecycle_events"]
    assert set(table.columns.keys()) == {
        "id", "operation_id", "request_digest", "project_id", "adapter_binding_id",
        "event_type", "actor_profile_id", "from_status", "to_status",
        "from_lifecycle_version", "to_lifecycle_version",
        "prior_suspension_event_id", "occurred_at",
    }
    assert {constraint.name for constraint in table.constraints} >= {
        "operation_id",
        "binding_version",
        "ck_compensation_adapter_binding_lifecycle_events_request_digest",
        "ck_compensation_adapter_binding_lifecycle_events_transition_shape",
    }
