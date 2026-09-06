"""Service-level guide readiness guards; parser and merge behavior remain controlled."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.modules.projects import service as project_service_module
from app.modules.projects.service import GuideActivationBlocked, ProjectService


@pytest.fixture(autouse=True)
def clear_settings_after_test() -> Iterator[None]:
    """Preserve the originating module's settings-cache cleanup."""
    try:
        yield
    finally:
        get_settings.cache_clear()


def _post_submit_policy(
    guide: SimpleNamespace,
    snapshot: SimpleNamespace,
    effective: SimpleNamespace,
    pre_submit: SimpleNamespace,
) -> SimpleNamespace:
    """Bind post-submit readiness to the same guide and pre-submit lineage."""
    return SimpleNamespace(
        id=str(uuid4()),
        project_id=guide.project_id,
        guide_id=guide.id,
        guide_version="v1",
        source_snapshot_id=snapshot.id,
        source_snapshot_hash=snapshot.bundle_hash,
        effective_policy_id=effective.id,
        effective_policy_hash=effective.effective_policy_hash,
        pre_submit_checker_policy_id=pre_submit.id,
        pre_submit_checker_bundle_hash=pre_submit.compiled_bundle_hash,
        lifecycle_status="approved",
        approved_by_role="project_manager",
        approved_by_actor="actor-1",
        approved_at=datetime.now(UTC),
        policy_body={"required_checkers": ["archive_safety"]},
        policy_hash=f"sha256:{'b' * 64}",
        required_checkers=["archive_safety"],
        warning_checkers=[],
        blocking_severities=["error"],
    )


def _review_and_revision_policies() -> tuple[SimpleNamespace, SimpleNamespace]:
    """Supply complete review/revision facts without executing either lifecycle."""
    review = SimpleNamespace(
        semantics_status="complete",
        policy_hash=f"sha256:{'c' * 64}",
        review_preference_window_seconds=60,
        review_lease_duration_seconds=60,
        max_active_review_leases_per_reviewer=1,
        self_review_allowed=False,
        reject_policy="allowed",
        finding_evidence_requirement="required",
        requires_second_review=False,
        allowed_decisions=["accept", "needs_revision", "reject"],
        minimum_finding_fields=["summary"],
    )
    revision = SimpleNamespace(
        semantics_status="complete",
        policy_hash=f"sha256:{'d' * 64}",
        max_revision_rounds=2,
        revision_deadline_hours=24,
        allowed_resubmission_states=["needs_revision"],
        reviewer_reassignment_rule="same_reviewer",
    )
    return review, revision


def _activation_ready_bundle() -> dict[str, Any]:
    """Build one internally consistent activation bundle for fast boundary tests."""
    project_id, guide_id, snapshot_id = (str(uuid4()) for _ in range(3))
    snapshot_hash = f"sha256:{'a' * 64}"
    submission_body = {"allowed_extensions": [".zip"]}
    submission_hash = canonical_json_hash(submission_body)
    effective_body = {"allowed_extensions": [".zip"], "max_bytes": 10}
    effective_hash = canonical_json_hash(effective_body)
    checker_bundle = {"checks": ["archive_safety"]}
    checker_hash = canonical_json_hash(checker_bundle)
    guide = SimpleNamespace(id=guide_id, project_id=project_id, version="v1")
    snapshot = SimpleNamespace(
        id=snapshot_id,
        project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        bundle_hash=snapshot_hash,
    )
    sufficiency = SimpleNamespace(
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        status="passed",
        warnings_acknowledged_by_actor=None,
        warnings_acknowledged_at=None,
        warnings_acknowledged_by_role=None,
    )
    submission = SimpleNamespace(
        id=str(uuid4()),
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        lifecycle_status="approved",
        derivation_source="manual",
        policy_body=submission_body,
        policy_hash=submission_hash,
        approved_by_actor="actor-1",
        approved_at=datetime.now(UTC),
        approved_by_role="project_manager",
    )
    effective = SimpleNamespace(
        id=str(uuid4()),
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        lifecycle_status="approved",
        effective_policy=effective_body,
        effective_policy_hash=effective_hash,
        submission_artifact_policy_id=submission.id,
        submission_artifact_policy_hash=submission_hash,
    )
    pre_submit = SimpleNamespace(
        id=str(uuid4()),
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        effective_policy_id=effective.id,
        effective_policy_hash=effective_hash,
        lifecycle_status="compiled",
        compiled_bundle=checker_bundle,
        compiled_bundle_hash=checker_hash,
    )
    post_submit = _post_submit_policy(guide, snapshot, effective, pre_submit)
    review, revision = _review_and_revision_policies()
    payment = SimpleNamespace(
        base_amount=Decimal("1.00"),
        currency="USD",
        payout_type="fixed",
        accepted_payment_rule="pay base amount",
    )
    return {
        "guide": guide,
        "source_snapshot": snapshot,
        "sufficiency_report": sufficiency,
        "submission_artifact_policy": submission,
        "effective_policy": effective,
        "pre_submit_checker_policy": pre_submit,
        "post_submit_checker_policy": post_submit,
        "review_policy": review,
        "revision_policy": revision,
        "payment_policy": payment,
    }


def _set_activation_fact(bundle: dict[str, Any], fact: str, value: Any) -> None:
    target_name, attribute = fact.split(".", 1)
    setattr(bundle[target_name], attribute, value)


@pytest.mark.parametrize(
    ("fact", "value", "message"),
    [
        ("source_snapshot.project_id", "other", "snapshot project mismatch"),
        ("source_snapshot.guide_id", "other", "snapshot is not current"),
        ("sufficiency_report.source_snapshot_id", "other", "stale snapshot"),
        ("sufficiency_report.source_snapshot_hash", "other", "snapshot hash mismatch"),
        ("sufficiency_report.status", "blocked", "blocking gaps"),
        (
            "submission_artifact_policy.lifecycle_status",
            "draft",
            "approved submission artifact policy",
        ),
        ("submission_artifact_policy.source_snapshot_id", "other", "bound to a stale snapshot"),
        ("submission_artifact_policy.source_snapshot_hash", "other", "snapshot hash mismatch"),
        ("submission_artifact_policy.policy_hash", f"sha256:{'e' * 64}", "body hash mismatch"),
        ("submission_artifact_policy.approved_by_actor", None, "approval provenance"),
        ("submission_artifact_policy.approved_by_role", "submitter", "approver role is invalid"),
        ("effective_policy.lifecycle_status", "draft", "effective.*not approved"),
        ("effective_policy.source_snapshot_id", "other", "effective.*stale snapshot"),
        ("effective_policy.source_snapshot_hash", "other", "effective.*hash mismatch"),
        ("effective_policy.effective_policy_hash", f"sha256:{'e' * 64}", "body hash mismatch"),
        ("effective_policy.submission_artifact_policy_id", "other", "wrong policy"),
        ("effective_policy.submission_artifact_policy_hash", "other", "hash provenance mismatch"),
        ("pre_submit_checker_policy.source_snapshot_id", "other", "pre-submit.*stale snapshot"),
        ("pre_submit_checker_policy.source_snapshot_hash", "other", "pre-submit.*hash mismatch"),
        ("pre_submit_checker_policy.effective_policy_id", "other", "wrong effective policy"),
        ("pre_submit_checker_policy.effective_policy_hash", "other", "bundle provenance mismatch"),
        ("pre_submit_checker_policy.lifecycle_status", "draft", "compiled project pre-submit"),
        ("pre_submit_checker_policy.compiled_bundle_hash", "", "compiled bundle hash is required"),
        ("pre_submit_checker_policy.compiled_bundle", {}, "compiled bundle is required"),
        ("post_submit_checker_policy.guide_id", "other", "post-submit.*guide mismatch"),
        (
            "post_submit_checker_policy.source_snapshot_id",
            "other",
            "post-submit.*snapshot mismatch",
        ),
        ("post_submit_checker_policy.effective_policy_id", "other", "wrong effective policy"),
        ("post_submit_checker_policy.pre_submit_checker_policy_id", "other", "wrong pre-submit"),
        (
            "post_submit_checker_policy.pre_submit_checker_bundle_hash",
            "other",
            "pre-submit hash mismatch",
        ),
        ("post_submit_checker_policy.lifecycle_status", "compiled", "approved post-submit"),
        ("post_submit_checker_policy.approved_by_actor", None, "approval provenance"),
        ("post_submit_checker_policy.approved_by_role", "submitter", "approval role is invalid"),
        ("review_policy.allowed_decisions", [], "allowed decisions"),
        ("review_policy.allowed_decisions", ["maybe"], "invalid decisions"),
        ("revision_policy.max_revision_rounds", 0, "revision policy is incomplete"),
        (
            "revision_policy.allowed_resubmission_states",
            ["accepted"],
            "invalid resubmission states",
        ),
        ("payment_policy.base_amount", Decimal("-1"), "payment policy is incomplete"),
        ("payment_policy.currency", "", "payment policy is incomplete"),
    ],
)
def test_activation_readiness_rejects_broken_chain_fact(
    monkeypatch: pytest.MonkeyPatch,
    fact: str,
    value: Any,
    message: str,
) -> None:
    bundle = _activation_ready_bundle()
    _set_activation_fact(bundle, fact, value)
    service = ProjectService(cast(Any, None))
    monkeypatch.setattr(
        service,
        "_merge_effective_submission_artifact_policy",
        lambda _body: deepcopy(bundle["effective_policy"].effective_policy),
    )
    monkeypatch.setattr(
        project_service_module,
        "parse_locked_post_submit_checker_policy_body",
        lambda *_args, **_kwargs: SimpleNamespace(
            required_checkers=["archive_safety"],
            warning_checkers=[],
            blocking_severities=["error"],
            execution_checkers=[],
        ),
    )
    monkeypatch.setattr(
        project_service_module,
        "require_complete_policy",
        lambda **_kwargs: None,
    )

    with pytest.raises(GuideActivationBlocked, match=message):
        service.validate_activation_ready(**bundle)


def test_activation_readiness_accepts_complete_chain_without_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _activation_ready_bundle()
    service = ProjectService(cast(Any, None))
    monkeypatch.setattr(
        service,
        "_merge_effective_submission_artifact_policy",
        lambda _body: deepcopy(bundle["effective_policy"].effective_policy),
    )
    monkeypatch.setattr(
        project_service_module,
        "parse_locked_post_submit_checker_policy_body",
        lambda *_args, **_kwargs: SimpleNamespace(
            required_checkers=["archive_safety"],
            warning_checkers=[],
            blocking_severities=["error"],
            execution_checkers=[],
        ),
    )
    monkeypatch.setattr(project_service_module, "require_complete_policy", lambda **_: None)

    bundle["payment_policy"] = None
    service.validate_activation_ready(**bundle, require_payment_policy=False)
