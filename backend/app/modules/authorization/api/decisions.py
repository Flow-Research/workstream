"""Stable immutable decisions returned by public authorization ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from .action_ids import ActionId, PermissionId


class DecisionOutcome(StrEnum):
    """Closed public authorization outcomes."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    """A bounded decision reference without evaluator or database internals."""

    decision_id: UUID
    action_id: ActionId
    permission_id: PermissionId
    outcome: DecisionOutcome
    denial_code: str | None = None

    def __post_init__(self) -> None:
        """Require denial detail only for denied decisions."""
        has_denial = self.denial_code is not None
        if has_denial != (self.outcome is DecisionOutcome.DENY):
            raise ValueError("denial code must match decision outcome")
