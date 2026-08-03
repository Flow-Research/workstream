"""Focused proof for immutable review/revision policy identity."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId
from app.modules.projects.policy_lineage import (
    ReviewPolicySemantics,
    RevisionPolicySemantics,
    policy_digest,
    require_complete_policy,
)


def test_xint003_02a_policy_digests_are_typed_and_domain_separated() -> None:
    review = ReviewPolicySemantics(
        review_preference_window_seconds=3600,
        review_lease_duration_seconds=1800,
        allowed_decisions=("accept", "needs_revision", "reject"),
    )
    revision = RevisionPolicySemantics(
        max_revision_rounds=3,
        revision_deadline_hours=48,
        allowed_resubmission_states=("needs_revision",),
    )

    review_hash = policy_digest("review", review)
    revision_hash = policy_digest("revision", revision)

    assert review_hash.startswith("sha256:")
    assert revision_hash.startswith("sha256:")
    assert review_hash != revision_hash


@pytest.mark.parametrize(
    ("status", "policy_hash", "values"),
    [
        ("legacy_incomplete", "sha256:" + "a" * 64, {"lease": None}),
        ("complete", None, {"lease": 1800}),
        ("complete", "sha256:" + "a" * 64, {"lease": None}),
    ],
)
def test_xint003_02a_incomplete_historical_policy_fails_closed(
    status: str, policy_hash: str | None, values: dict[str, int | None]
) -> None:
    with pytest.raises(ValueError, match="policy semantics are incomplete"):
        require_complete_policy(
            kind="review",
            status=status,  # type: ignore[arg-type]
            policy_hash=policy_hash,
            semantic_values=values,
        )


def test_xint003_02a_complete_policy_is_ready() -> None:
    semantics = ReviewPolicySemantics(
        review_preference_window_seconds=3600,
        review_lease_duration_seconds=1800,
        allowed_decisions=("accept", "needs_revision", "reject"),
    )
    require_complete_policy(
        kind="review",
        status="complete",
        policy_hash=policy_digest("review", semantics),
        semantic_values=semantics.model_dump(mode="python"),
    )


def test_xint003_02a_complete_policy_rejects_digest_mismatch() -> None:
    semantics = ReviewPolicySemantics(
        review_preference_window_seconds=3600,
        review_lease_duration_seconds=1800,
        allowed_decisions=("accept", "needs_revision", "reject"),
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        require_complete_policy(
            kind="review",
            status="complete",
            policy_hash="sha256:" + "a" * 64,
            semantic_values=semantics.model_dump(mode="python"),
        )


def test_xint003_02a_optional_revision_reassignment_remains_complete() -> None:
    semantics = RevisionPolicySemantics(
        max_revision_rounds=3,
        revision_deadline_hours=48,
        allowed_resubmission_states=("needs_revision",),
        reviewer_reassignment_rule=None,
    )
    require_complete_policy(
        kind="revision",
        status="complete",
        policy_hash=policy_digest("revision", semantics),
        semantic_values=semantics.model_dump(mode="python"),
    )


def test_xint003_02a_fixed_v01_review_guards_cannot_be_weakened() -> None:
    with pytest.raises(ValidationError):
        ReviewPolicySemantics(
            review_preference_window_seconds=3600,
            review_lease_duration_seconds=1800,
            max_active_review_leases_per_reviewer=2,  # type: ignore[arg-type]
            allowed_decisions=("accept",),
        )
    with pytest.raises(ValidationError):
        ReviewPolicySemantics(
            review_preference_window_seconds=3600,
            review_lease_duration_seconds=1800,
            self_review_allowed=True,  # type: ignore[arg-type]
            allowed_decisions=("accept",),
        )


def test_xint003_02b_policy_actions_are_narrowly_active() -> None:
    assert (
        ACTION_BY_ID[ActionId.PROJECT_REVIEW_POLICY_UPDATE].availability
        is ActionAvailability.ACTIVE
    )
    assert (
        ACTION_BY_ID[ActionId.PROJECT_REVISION_POLICY_UPDATE].availability
        is ActionAvailability.ACTIVE
    )
