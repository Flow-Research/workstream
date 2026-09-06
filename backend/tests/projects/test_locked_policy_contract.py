"""Public locked-policy values and controlled repository guard contracts."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.projects.api import (
    CanonicalJsonObject,
    ProjectLockedPolicyContextFacts,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository


def _project_locked_policy_rows(
    *,
    guide_status: str = "active",
    effective_status: str = "approved",
    pre_submit_status: str = "compiled",
) -> tuple[ProjectLockedPolicyContextRequest, tuple[SimpleNamespace, ...]]:
    """Build one internally consistent locked PROJECT lineage."""
    project_id, guide_id, snapshot_id, effective_id, pre_submit_id = (uuid4() for _ in range(5))
    manifest = {"items": [{"name": "guide.md"}], "schema_version": "v1"}
    effective_body = {"allowed": ["zip"], "limits": {"max_bytes": 1024}}
    compiled_bundle = {"rules": [{"primitive": "zip_safety"}]}
    snapshot_hash = canonical_json_hash(manifest)
    effective_hash = canonical_json_hash(effective_body)
    bundle_hash = canonical_json_hash(compiled_bundle)
    request = ProjectLockedPolicyContextRequest(
        project_id=project_id,
        guide_version="v1",
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        effective_policy_id=effective_id,
        effective_policy_hash=effective_hash,
        pre_submit_policy_id=pre_submit_id,
        pre_submit_policy_bundle_hash=bundle_hash,
    )
    rows = (
        SimpleNamespace(id=str(project_id), status="active"),
        SimpleNamespace(
            id=str(guide_id),
            project_id=str(project_id),
            version="v1",
            status=guide_status,
        ),
        SimpleNamespace(
            id=str(snapshot_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version="v1",
            manifest_json=manifest,
            bundle_hash=snapshot_hash,
        ),
        SimpleNamespace(
            id=str(effective_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version="v1",
            source_snapshot_id=str(snapshot_id),
            source_snapshot_hash=snapshot_hash,
            effective_policy=effective_body,
            effective_policy_hash=effective_hash,
            lifecycle_status=effective_status,
        ),
        SimpleNamespace(
            id=str(pre_submit_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version="v1",
            source_snapshot_id=str(snapshot_id),
            source_snapshot_hash=snapshot_hash,
            effective_policy_id=str(effective_id),
            effective_policy_hash=effective_hash,
            lifecycle_status=pre_submit_status,
            compiler_version="pre-submit-v1",
            compiled_bundle=compiled_bundle,
            compiled_bundle_hash=bundle_hash,
        ),
    )
    return request, rows



def test_project_locked_policy_copies_nested_input() -> None:
    source = {"nested": {"values": [1, 2]}}
    canonical = CanonicalJsonObject.from_mapping(source)
    cast(dict[str, Any], source["nested"])["values"] = [3]
    assert canonical.value == '{"nested":{"values":[1,2]}}'


def test_project_locked_policy_hash_matches_canonical_input() -> None:
    source = {"nested": {"values": [1, 2]}}
    assert CanonicalJsonObject.from_mapping(source).sha256 == canonical_json_hash(source)


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
    request, _rows = _project_locked_policy_rows()
    with pytest.raises(ValueError, match="guide version is empty"):
        replace(request, guide_version=" ")


def test_project_locked_policy_rejects_malformed_digest() -> None:
    request, _rows = _project_locked_policy_rows()
    with pytest.raises(ValueError, match="hash is invalid"):
        replace(request, effective_policy_hash="sha256:invalid")


def _valid_public_facts() -> ProjectLockedPolicyContextFacts:
    request, rows = _project_locked_policy_rows()
    return ProjectLockedPolicyContextFacts(
        project_id=request.project_id,
        guide_id=UUID(rows[1].id),
        guide_version="v1",
        guide_status="active",
        source_snapshot_id=request.source_snapshot_id,
        source_snapshot_hash=request.source_snapshot_hash,
        effective_policy_id=request.effective_policy_id,
        effective_policy_hash=request.effective_policy_hash,
        effective_policy_status="approved",
        effective_policy=CanonicalJsonObject.from_mapping(rows[3].effective_policy),
        pre_submit_policy_id=request.pre_submit_policy_id,
        pre_submit_policy_bundle_hash=request.pre_submit_policy_bundle_hash,
        pre_submit_policy_status="compiled",
        pre_submit_compiler_version="pre-submit-v1",
        compiled_pre_submit_bundle=CanonicalJsonObject.from_mapping(rows[4].compiled_bundle),
    )


def test_project_locked_policy_rejects_invalid_fact_status() -> None:
    with pytest.raises(ValueError, match="facts are invalid"):
        replace(_valid_public_facts(), guide_status=cast(Any, "draft"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guide_status", "effective_status", "pre_submit_status"),
    (("active", "approved", "compiled"), ("superseded", "superseded", "superseded")),
)
async def test_locked_policy_repository_resolves_exact_current_and_superseded_policy(
    guide_status: str,
    effective_status: str,
    pre_submit_status: str,
) -> None:
    """Resolve exact valid historical lineage without selecting successors."""
    request, rows = _project_locked_policy_rows(
        guide_status=guide_status,
        effective_status=effective_status,
        pre_submit_status=pre_submit_status,
    )
    statements: list[Any] = []

    class Session:
        def __init__(self) -> None:
            self.rows = iter(rows)

        async def scalar(self, statement: Any) -> Any:
            statements.append(statement)
            return next(self.rows)

    facts = await ProjectLockedPolicyRepository(cast(Any, Session())).lock_locked_policy_context(
        request
    )
    assert facts == ProjectLockedPolicyContextFacts(
        project_id=request.project_id,
        guide_id=UUID(rows[1].id),
        guide_version="v1",
        guide_status=cast(Any, guide_status),
        source_snapshot_id=request.source_snapshot_id,
        source_snapshot_hash=request.source_snapshot_hash,
        effective_policy_id=request.effective_policy_id,
        effective_policy_hash=request.effective_policy_hash,
        effective_policy_status=cast(Any, effective_status),
        effective_policy=CanonicalJsonObject.from_mapping(rows[3].effective_policy),
        pre_submit_policy_id=request.pre_submit_policy_id,
        pre_submit_policy_bundle_hash=request.pre_submit_policy_bundle_hash,
        pre_submit_policy_status=cast(Any, pre_submit_status),
        pre_submit_compiler_version="pre-submit-v1",
        compiled_pre_submit_bundle=CanonicalJsonObject.from_mapping(rows[4].compiled_bundle),
    )
    assert len(statements) == 5
    assert all("FOR UPDATE" in str(statement) for statement in statements)
    assert all(
        statement.get_execution_options().get("populate_existing") is True
        for statement in statements
    )



@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    (
        "draft",
        "inactive_project",
        "pending",
        "hash",
        "cross_project",
        "effective_link",
        "non_canonical",
        "invalid_guide_id",
        "snapshot_array",
        "effective_array",
        "bundle_array",
    ),
)
async def test_locked_policy_repository_rejects_invalid_lineage(
    failure: str,
) -> None:
    """Fail closed for draft, pending, drifted, or cross-project lineage."""
    request, rows = _project_locked_policy_rows()
    if failure == "draft":
        rows[1].status = "draft"
    elif failure == "inactive_project":
        rows[0].status = "draft"
    elif failure == "pending":
        rows[4].lifecycle_status = "pending_compilation"
    elif failure == "hash":
        rows[3].effective_policy = {"allowed": ["tar"]}
    elif failure == "cross_project":
        rows[2].project_id = str(uuid4())
    elif failure == "effective_link":
        rows[4].effective_policy_id = str(uuid4())
    elif failure == "non_canonical":
        rows[3].effective_policy = {"invalid": float("nan")}
    elif failure == "invalid_guide_id":
        rows[1].id = "invalid-guide-id"
        rows[2].guide_id = rows[1].id
        rows[3].guide_id = rows[1].id
        rows[4].guide_id = rows[1].id
    elif failure == "snapshot_array":
        drift_hash = canonical_json_hash(cast(Any, []))
        request = replace(request, source_snapshot_hash=drift_hash)
        rows[2].manifest_json = []
        rows[2].bundle_hash = drift_hash
        rows[3].source_snapshot_hash = drift_hash
        rows[4].source_snapshot_hash = drift_hash
    elif failure == "effective_array":
        drift_hash = canonical_json_hash(cast(Any, []))
        request = replace(request, effective_policy_hash=drift_hash)
        rows[3].effective_policy = []
        rows[3].effective_policy_hash = drift_hash
        rows[4].effective_policy_hash = drift_hash
    else:
        drift_hash = canonical_json_hash(cast(Any, []))
        request = replace(request, pre_submit_policy_bundle_hash=drift_hash)
        rows[4].compiled_bundle = []
        rows[4].compiled_bundle_hash = drift_hash

    class Session:
        def __init__(self) -> None:
            self.rows = iter(rows)

        async def scalar(self, _statement: Any) -> Any:
            return next(self.rows)

    with pytest.raises(
        ProjectLockedPolicyContextUnavailable,
        match="project_locked_policy_context_changed",
    ):
        await ProjectLockedPolicyRepository(cast(Any, Session())).lock_locked_policy_context(
            request
        )
