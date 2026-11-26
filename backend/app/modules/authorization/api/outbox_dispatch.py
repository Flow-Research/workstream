"""Pure contract for phase-specific outbox dispatcher authority."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Protocol
from uuid import UUID

from .decisions import AuthorizationDecision

OUTBOX_DISPATCH_ACTION = "outbox.dispatch"
OUTBOX_DISPATCH_PERMISSION = "outbox.dispatch"
OUTBOX_DISPATCH_SERVICE = "workstream.outbox.dispatcher"
OUTBOX_DISPATCH_RESOURCE = "outbox_event"
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OWNER = re.compile(r"[A-Za-z0-9._:-]{1,120}\Z")


class OutboxDispatchPhase(StrEnum):
    """Distinct authority decisions; a prior phase cannot authorize the next."""

    CLAIM = "claim"
    INVOKE = "invoke"
    RENEW = "renew"
    FINALIZE = "finalize"


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboxDispatchFacts:
    """Proposed claim or persisted invocation/finalization facts, never authority.

    CLAIM describes the proposed next generation. INVOKE and FINALIZE require
    owner verification of the committed generation. FINALIZE binds the canonical
    typed outcome digest computed by OUTBOX, including every result/retry field.
    This value object does not establish persistence, current lease or authority.
    """

    phase: OutboxDispatchPhase
    event_id: UUID
    project_id: UUID
    payload_digest: str
    claim_generation: int
    claim_owner: str
    claimed_at: datetime
    claim_expires_at: datetime
    live_until: datetime | None = None
    outcome_digest: str | None = None

    def __post_init__(self) -> None:
        """Enforce exact storage-compatible scalars without reflecting input."""
        valid = (
            type(self.phase) is OutboxDispatchPhase
            and type(self.event_id) is UUID
            and type(self.project_id) is UUID
            and type(self.payload_digest) is str
            and _HASH.fullmatch(self.payload_digest) is not None
            and type(self.claim_generation) is int
            and 1 <= self.claim_generation <= 2147483647
            and type(self.claim_owner) is str
            and _OWNER.fullmatch(self.claim_owner) is not None
            and type(self.claimed_at) is datetime
            and type(self.claim_expires_at) is datetime
        )
        if not valid:
            raise ValueError("outbox dispatch facts are invalid")
        if self.phase is OutboxDispatchPhase.FINALIZE:
            if type(self.outcome_digest) is not str or not _HASH.fullmatch(self.outcome_digest):
                raise ValueError("outbox dispatch outcome is invalid")
        elif self.outcome_digest is not None:
            raise ValueError("outbox dispatch outcome is invalid")
        if self.phase is OutboxDispatchPhase.RENEW:
            if type(self.live_until) is not datetime:
                raise ValueError("outbox renewal time is invalid")
        elif self.live_until is not None:
            raise ValueError("outbox renewal time is invalid")
        try:
            if self.claimed_at.utcoffset() is None or self.claim_expires_at.utcoffset() is None:
                raise ValueError("naive lease timestamp")
            claimed = self.claimed_at.astimezone(timezone.utc)
            expires = self.claim_expires_at.astimezone(timezone.utc)
            if expires <= claimed:
                raise ValueError("non-positive lease interval")
            if self.live_until is not None and (
                self.live_until.utcoffset() is None
                or self.live_until.astimezone(timezone.utc) <= expires
            ):
                raise ValueError("outbox renewal time is invalid")
        except Exception:
            raise ValueError("outbox dispatch lease is invalid") from None
        object.__setattr__(self, "claimed_at", claimed)
        object.__setattr__(self, "claim_expires_at", expires)
        if self.live_until is not None:
            object.__setattr__(self, "live_until", self.live_until.astimezone(timezone.utc))


def outbox_dispatch_resource_digest(facts: OutboxDispatchFacts) -> str:
    """Hash the complete fixed authority envelope and revalidated exact facts."""
    if type(facts) is not OutboxDispatchFacts:
        raise ValueError("outbox dispatch facts are invalid")
    checked = OutboxDispatchFacts(**{field.name: getattr(facts, field.name) for field in fields(facts)})
    values = {
        field.name: (
            value.isoformat() if type(value) is datetime
            else str(value) if isinstance(value, UUID) else value
        )
        for field in fields(checked)
        if field.name != "live_until" or checked.live_until is not None
        for value in (getattr(checked, field.name),)
    }
    body = json.dumps(
        {
            "domain": "workstream.authorization.outbox_dispatch",
            "action_id": OUTBOX_DISPATCH_ACTION,
            "permission_id": OUTBOX_DISPATCH_PERMISSION,
            "service_identity": OUTBOX_DISPATCH_SERVICE,
            "resource_type": OUTBOX_DISPATCH_RESOURCE,
            "resource_id": str(checked.event_id),
            "scope_project_id": str(checked.project_id),
            "facts": values,
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


class PreparedOutboxDispatch(ABC):
    """Nominal one-phase authority implemented by the canonical AUTH/PREP owner.

    Each preparation binds its exact session/root transaction and recomposed
    phase facts before single consumption. AUTH revalidates the fixed principal;
    OUTBOX verifies locked committed ownership for invocation/finalization.
    No handle crosses commit, lease wait or handler/provider I/O.
    """

    __slots__ = ()

    def __reduce_ex__(self, _protocol):
        """Reject pickle and copying of process-local prepared authority."""
        raise TypeError("prepared outbox authority is process-local")

    @abstractmethod
    async def consume(self, facts: OutboxDispatchFacts) -> AuthorizationDecision:
        """Consume once for exactly recomposed phase/facts in the bound transaction."""
        ...


class OutboxDispatchAuthorizationPort(Protocol):
    """Session-bound composition supplies fixed identity, never a caller selector."""

    def prepare_outbox_dispatch(
        self, *, facts: OutboxDispatchFacts, request_id: UUID, correlation_id: UUID,
    ) -> AbstractAsyncContextManager[PreparedOutboxDispatch]:
        """Prepare fresh authority for this phase; no phase shares a prior handle."""
        ...
