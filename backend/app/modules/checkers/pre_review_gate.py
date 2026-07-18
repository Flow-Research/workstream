"""Shared contracts for the automatic pre-review checker gate."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.modules.tasks.models import AuditEvent
from app.schemas.auth import ActorContext

REQUESTER_PROVENANCE_KEYS = (
    "requester_actor_id",
    "requester_external_subject",
    "requester_external_issuer",
    "requester_auth_source",
)


def requester_provenance_payload(actor: ActorContext) -> dict[str, str]:
    """Build minimal requester provenance safe to send through worker queues."""
    audit = actor.audit_context()
    return {
        "requester_actor_id": audit.actor_id,
        "requester_external_subject": audit.external_subject,
        "requester_external_issuer": audit.external_issuer,
        "requester_auth_source": audit.auth_source,
    }


def sanitize_requester_provenance(payload: dict[str, Any]) -> dict[str, str]:
    """Keep only bounded requester provenance accepted from queue payloads."""
    sanitized: dict[str, str] = {}
    for key in REQUESTER_PROVENANCE_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            sanitized[key] = value.strip()[:300]
    return sanitized


def requester_provenance_from_audit_event(event: AuditEvent) -> dict[str, str]:
    """Project audit actor identity into the requester-provenance contract."""
    return {
        "requester_actor_id": event.actor_id,
        "requester_external_subject": event.external_subject,
        "requester_external_issuer": event.external_issuer,
        "requester_auth_source": event.auth_source,
    }


def find_submission_requester_provenance(
    events: Sequence[AuditEvent],
    *,
    submission_id: str,
    event_type: str,
) -> dict[str, str] | None:
    """Find requester provenance from the latest matching submission audit event."""
    for event in reversed(events):
        if event.event_type != event_type:
            continue
        if event.event_payload.get("submission_id") != submission_id:
            continue
        return requester_provenance_from_audit_event(event)
    return None


def requester_provenance_matches(
    *,
    expected: dict[str, str],
    received: dict[str, Any],
) -> bool:
    """Return whether received queue provenance agrees with persisted audit."""
    return all(received.get(key) == value for key, value in expected.items())
