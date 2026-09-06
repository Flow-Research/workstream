"""Exact PROJECT policy-read composition; no AUTH kernel or database claims."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.projects.authorization_reads import authorize_project_policy_read
from app.modules.projects.service import GuideActivationBlocked, ProjectService
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.policy_read_fixtures import _PolicyReadRepository

POLICY_ACTIONS = [
    pytest.param(ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ, id="effective"),
    pytest.param(ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ, id="pre-submit"),
]


async def _read(repository: _PolicyReadRepository, authorization: Any, action: ActionId) -> Any:
    """Invoke the real composer with controlled owner rows."""
    return await authorize_project_policy_read(
        authorization=authorization,
        repository=cast(Any, repository),
        action_id=action,
        project_id=repository.project_id,
        guide_id=repository.guide_id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", POLICY_ACTIONS)
async def test_policy_read_binds_exact_target_facts(action: ActionId) -> None:
    """Bind the exact returned row to all authorization resource facts."""
    repository = _PolicyReadRepository()
    authorization = SimpleNamespace(require=AsyncMock())
    checker = (
        repository.checker
        if action is ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ else None
    )
    target = checker if checker is not None else repository.effective

    result = await _read(repository, authorization, action)

    assert result is target
    authorization.require.assert_awaited_once()
    called_action, context = authorization.require.await_args.args
    assert called_action is action
    assert context.model_dump(mode="json", exclude={"target_binding_digest"}) == {
        "resource_type": "project_policy_read",
        "resource_id": target.id,
        "scope_project_id": repository.project_id,
        "guide_id": repository.guide_id,
        "guide_version": "v1",
        "guide_status": "active",
        "target_kind": "pre_submit_checker_policy" if checker is not None else "effective_policy",
        "project_exists": True,
        "project_status": "active",
        "guide_exists": True,
        "target_exists": True,
        "source_snapshot_id": repository.snapshot.id,
        "source_snapshot_hash": repository.snapshot.bundle_hash,
        "effective_policy_id": repository.effective.id,
        "effective_policy_hash": repository.effective.effective_policy_hash,
        "effective_policy_status": "approved",
        "checker_policy_id": checker.id if checker is not None else None,
        "checker_policy_status": "compiled" if checker is not None else None,
        "checker_bundle_hash": checker.compiled_bundle_hash if checker is not None else None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action", POLICY_ACTIONS)
async def test_policy_read_binds_exact_digest(action: ActionId) -> None:
    """Reject a well-formed digest that does not represent the selected chain."""
    repository = _PolicyReadRepository()
    authorization = SimpleNamespace(require=AsyncMock())
    expected = canonical_json_hash({
        "guide": [repository.guide.id, "v1", "active"],
        "snapshot": [repository.snapshot.id, repository.snapshot.bundle_hash],
        "effective": [
            repository.effective.id, repository.effective.effective_policy_hash, "approved",
        ],
        "submission": [repository.submission.id, repository.submission.policy_hash],
        "checker": (
            [repository.checker.id, "compiled", repository.checker.compiled_bundle_hash]
            if action is ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ else None
        ),
    })

    await _read(repository, authorization, action)

    authorization.require.assert_awaited_once()
    assert authorization.require.await_args.args[1].target_binding_digest == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row,field,action",
    [
        pytest.param("guide", "status", ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
                     id="draft-guide"),
        pytest.param("effective", "guide_id",
                     ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
                     id="wrong-effective-guide"),
        pytest.param("checker", "source_snapshot_hash",
                     ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
                     id="stale-checker-snapshot"),
    ],
)
async def test_policy_read_rejects_changed_lineage(row: str, field: str, action: ActionId) -> None:
    """The real composer rejects invalid lineage even if authorization allows."""
    repository = _PolicyReadRepository()
    authorization = SimpleNamespace(require=AsyncMock())
    value = "draft" if field == "status" else (
        str(uuid4()) if field == "guide_id" else f"sha256:{'f' * 64}"
    )
    setattr(getattr(repository, row), field, value)

    with pytest.raises(RuntimeError, match="missing policy authorization unexpectedly allowed"):
        await _read(repository, authorization, action)

    authorization.require.assert_awaited_once()
    assert authorization.require.await_args.args[0] is action
    context = authorization.require.await_args.args[1]
    assert context.target_exists is False
    assert context.target_binding_digest is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", POLICY_ACTIONS)
async def test_policy_read_propagates_authorizer_exception(action: ActionId) -> None:
    """A valid target cannot be returned after the authorizer raises."""
    repository = _PolicyReadRepository()
    failure = RuntimeError("sentinel authorizer exception")
    authorization = SimpleNamespace(require=AsyncMock(side_effect=failure))

    with pytest.raises(RuntimeError) as raised:
        await _read(repository, authorization, action)

    assert raised.value is failure
    authorization.require.assert_awaited_once()
    assert authorization.require.await_args.args[0] is action
    assert authorization.require.await_args.args[1].target_exists is True


def test_activation_readiness_normalizes_hash_valid_malformed_policy_body() -> None:
    repository = _PolicyReadRepository()
    repository.submission.derivation_source = "manual"
    service = ProjectService(cast(Any, None))

    with pytest.raises(GuideActivationBlocked, match="policy body is invalid"):
        service.validate_activation_ready(
            repository.guide,
            repository.snapshot,
            repository.sufficiency,
            repository.submission,
            repository.effective,
            repository.checker,
            repository.post_submit,
            repository.review,
            repository.revision,
            None,
            require_payment_policy=False,
        )
