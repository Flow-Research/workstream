"""Public locked-policy values and controlled repository guard contracts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.projects.api import (
    CanonicalJsonObject,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)


def _request():
    return ProjectLockedPolicyContextRequest(
        project_id=uuid4(),
        guide_version="initial",
        source_snapshot_id=uuid4(),
        source_snapshot_hash="sha256:" + "1" * 64,
        effective_policy_id=uuid4(),
        effective_policy_hash="sha256:" + "2" * 64,
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
    )


def test_project_locked_policy_copies_nested_input() -> None:
    source = {"nested": {"values": [1, 2]}}
    canonical = CanonicalJsonObject.from_mapping(source)
    cast(dict[str, Any], source["nested"])["values"] = [3]
    assert canonical.value == '{"nested":{"values":[1,2]}}'


def test_project_locked_policy_hash_retains_copied_input() -> None:
    source = {"nested": {"values": [1, 2]}}
    canonical = CanonicalJsonObject.from_mapping(source)
    cast(dict[str, Any], source["nested"])["values"] = [3]
    assert canonical.sha256 == canonical_json_hash({"nested": {"values": [1, 2]}})


def test_project_locked_policy_exposes_no_mutable_projection() -> None:
    assert not hasattr(CanonicalJsonObject.from_mapping({}), "as_dict")


@pytest.mark.parametrize("value", ('{"z":1,"a":2}', "not-json"))
def test_project_locked_policy_rejects_noncanonical_json(value: str) -> None:
    with pytest.raises(ValueError, match="canonical JSON object is invalid"):
        CanonicalJsonObject(value)


def test_project_locked_policy_rejects_non_mapping_input() -> None:
    with pytest.raises(ValueError, match="canonical JSON object is invalid"):
        CanonicalJsonObject.from_mapping(cast(Any, []))


def test_project_locked_policy_rejects_unbounded_failure_code() -> None:
    with pytest.raises(ValueError, match="failure code is invalid"):
        ProjectLockedPolicyContextUnavailable(cast(Any, "unbounded"))


def test_project_locked_policy_preserves_bounded_failure_code() -> None:
    unavailable = ProjectLockedPolicyContextUnavailable("project_locked_policy_context_changed")
    assert unavailable.code == "project_locked_policy_context_changed"
    assert str(unavailable) == "project_locked_policy_context_changed"


def test_project_locked_policy_rejects_empty_guide_version() -> None:
    request = _request()
    with pytest.raises(ValueError, match="guide version is empty"):
        replace(request, guide_version=" ")


def test_project_locked_policy_rejects_malformed_digest() -> None:
    request = _request()
    with pytest.raises(ValueError, match="hash is invalid"):
        replace(request, effective_policy_hash="sha256:invalid")


@pytest.mark.parametrize("semantics_format", ("v1", "v2"))
def test_context_preserves_persisted_review_semantics(semantics_format):
    """The projection validates retained business hashes using their canonical owner."""
    from types import SimpleNamespace
    from app.modules.projects.api.guide_activation import GuidePolicySelection
    from app.modules.projects.locked_policy_projection import _policy_body
    from app.modules.projects.policy_lineage import ReviewPolicySemantics, policy_digest

    semantics = ReviewPolicySemantics(
        review_preference_window_seconds=3600,
        review_lease_duration_seconds=1800,
        allowed_decisions=("accept", "needs_revision", "reject"),
    )
    identity = uuid4()
    digest = policy_digest("review", semantics, review_semantics_format=semantics_format)
    guide = SimpleNamespace(project_id=str(uuid4()), version="retained-guide")
    policy = SimpleNamespace(
        id=str(identity),
        project_id=guide.project_id,
        guide_version=guide.version,
        policy_generation=1,
        policy_hash=digest,
        semantics_status="complete",
        semantics_format=semantics_format,
        **semantics.model_dump(),
    )
    selection = GuidePolicySelection(policy_id=identity, generation=1, policy_hash=digest)
    expected = CanonicalJsonObject.from_mapping(semantics.model_dump(mode="json"))
    assert _policy_body("review", policy, selection, guide) == expected
    policy.human_review_required = False
    with pytest.raises(ValueError):
        _policy_body("review", policy, selection, guide)


def test_project_context_contract_does_not_cycle_agent_port_import():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import app.interfaces.project_agents"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
