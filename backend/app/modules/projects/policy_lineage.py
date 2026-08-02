"""Canonical immutable review and revision policy lineage helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.hashing import canonical_json_hash


PolicySemanticsStatus = Literal["complete", "legacy_incomplete"]


class ReviewPolicySemantics(BaseModel):
    """Complete v0.1 review-policy facts frozen into downstream work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_preference_window_seconds: int = Field(gt=0)
    review_lease_duration_seconds: int = Field(gt=0)
    max_active_review_leases_per_reviewer: Literal[1] = 1
    self_review_allowed: Literal[False] = False
    reject_policy: Literal["close_task"] = "close_task"
    finding_evidence_requirement: Literal[
        "optional", "required_for_blocking", "required_for_all"
    ] = "optional"
    requires_second_review: bool = False
    allowed_decisions: tuple[Literal["accept", "needs_revision", "reject"], ...]
    minimum_finding_fields: tuple[str, ...] = ()


class RevisionPolicySemantics(BaseModel):
    """Complete v0.1 human-revision policy facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_revision_rounds: int = Field(gt=0)
    revision_deadline_hours: int = Field(gt=0)
    allowed_resubmission_states: tuple[Literal["needs_revision"], ...]
    reviewer_reassignment_rule: str | None = None


def policy_digest(kind: Literal["review", "revision"], semantics: BaseModel) -> str:
    """Return the domain-separated digest for one complete policy version."""
    return canonical_json_hash(
        {
            "domain": f"workstream.{kind}_policy.v1",
            "semantics": semantics.model_dump(mode="json"),
        }
    )


def require_complete_policy(
    *,
    kind: Literal["review", "revision"],
    status: PolicySemanticsStatus,
    policy_hash: str | None,
    semantic_values: dict[str, Any],
) -> None:
    """Fail closed when semantics are incomplete or their digest is not exact."""
    if status != "complete" or policy_hash is None:
        raise ValueError("policy semantics are incomplete")
    model = ReviewPolicySemantics if kind == "review" else RevisionPolicySemantics
    try:
        semantics = model.model_validate(semantic_values)
    except ValidationError as exc:
        raise ValueError("policy semantics are incomplete") from exc
    if policy_digest(kind, semantics) != policy_hash:
        raise ValueError("policy semantics digest mismatch")
