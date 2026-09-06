"""Diagnostic resource facts, independent digests and exact owner delegation."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.diagnostic_read_fixtures import (
    attach_post_submit_policy, make_diagnostic_case, read_diagnostic,
)

READ_CASES = [
    pytest.param(ActionId.PROJECT_SETUP_RUN_READ, "setup_run",
                 "lock_latest_project_setup_run", False, id="setup-run"),
    pytest.param(ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST, "sufficiency_report_collection",
                 "lock_guide_sufficiency_reports", True, id="sufficiency-list"),
    pytest.param(ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ, "sufficiency_report",
                 "lock_guide_sufficiency_report", False, id="sufficiency-read"),
    pytest.param(ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
                 "submission_artifact_policy_collection", "lock_submission_artifact_policies",
                 True, id="submission-policy-list"),
    pytest.param(ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ, "submission_artifact_policy",
                 "lock_submission_artifact_policy_diagnostic", False, id="submission-policy-read"),
    pytest.param(ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
                 "post_submit_checker_policy_setup", "lock_latest_project_setup_run",
                 False, id="post-submit-setup"),
]


def _expected_stamp(row: SimpleNamespace) -> dict[str, Any]:
    """Declare the six diagnostic binding fields independently of the composer."""
    return {
        "id": row.id, "project_id": row.project_id, "guide_id": row.guide_id,
        "guide_version": row.guide_version, "source_snapshot_id": row.source_snapshot_id,
        "source_snapshot_hash": row.source_snapshot_hash,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action,kind,method,is_collection", READ_CASES)
async def test_diagnostic_read_binds_exact_facts(
    action: ActionId, kind: str, method: str, is_collection: bool,
) -> None:
    """Bind the selected result to every non-digest authorization fact."""
    case = make_diagnostic_case()

    result = await read_diagnostic(case, action)

    if action is ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ:
        assert result == (case.target, None)
    elif is_collection:
        assert result is getattr(case.repository, method).return_value
    else:
        assert result is case.target
    case.authorization.require.assert_awaited_once()
    called_action, context = case.authorization.require.await_args.args
    assert called_action is action
    assert context.model_dump(mode="json", exclude={"target_binding_digest"}) == {
        "resource_type": "project_diagnostic",
        "resource_id": case.guide_id if is_collection else case.target_id,
        "scope_project_id": case.project_id, "guide_id": case.guide_id,
        "guide_version": "v1", "target_kind": kind,
        "project_exists": True, "guide_exists": True, "target_exists": True,
        "source_snapshot_id": None if is_collection else case.target.source_snapshot_id,
        "source_snapshot_hash": None if is_collection else case.target.source_snapshot_hash,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action,kind,method,is_collection", READ_CASES)
async def test_diagnostic_read_binds_exact_digest(
    action: ActionId, kind: str, method: str, is_collection: bool,
) -> None:
    """A merely well-formed hash cannot substitute for the selected row digest."""
    case = make_diagnostic_case()
    expected = canonical_json_hash([_expected_stamp(case.target)])

    await read_diagnostic(case, action)

    case.authorization.require.assert_awaited_once()
    assert case.authorization.require.await_args.args[1].target_binding_digest == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("action,kind,method,is_collection", READ_CASES)
async def test_diagnostic_read_calls_exact_owner_port(
    action: ActionId, kind: str, method: str, is_collection: bool,
) -> None:
    """Verify exact owner selectors, not database lock acquisition."""
    case = make_diagnostic_case()
    args = (case.project_id, case.guide_id, "v1")
    if action in {
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
    }:
        args = (case.target_id, *args)

    await read_diagnostic(case, action)

    case.repository.get_project.assert_awaited_once_with(case.project_id, for_update=True)
    case.repository.lock_project_guide.assert_awaited_once_with(case.guide_id)
    getattr(case.repository, method).assert_awaited_once_with(*args)
    for name, port in vars(case.repository).items():
        if name not in {"get_project", "lock_project_guide", method}:
            port.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("action,method", [
    (ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST, "lock_guide_sufficiency_reports"),
    (ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST, "lock_submission_artifact_policies"),
])
async def test_empty_diagnostic_collection_remains_readable(action: ActionId, method: str) -> None:
    """An empty scoped list is not a missing guide or missing diagnostic target."""
    case = make_diagnostic_case()
    getattr(case.repository, method).return_value = []

    result = await read_diagnostic(case, action)

    assert result == []
    case.authorization.require.assert_awaited_once()
    context = case.authorization.require.await_args.args[1]
    assert context.target_exists is True
    assert str(context.resource_id) == case.guide_id
    assert context.target_binding_digest == canonical_json_hash([])
    assert context.source_snapshot_id is None
    assert context.source_snapshot_hash is None


@pytest.mark.asyncio
async def test_post_submit_diagnostic_binds_both_rows() -> None:
    """A setup diagnostic with output binds both the run and exact policy row."""
    case = make_diagnostic_case()
    policy = attach_post_submit_policy(case)
    expected = canonical_json_hash([_expected_stamp(case.target), _expected_stamp(policy)])

    result = await read_diagnostic(case, ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ)

    assert result == (case.target, policy)
    case.repository.lock_post_submit_checker_policy.assert_awaited_once_with(policy.id)
    case.authorization.require.assert_awaited_once()
    assert case.authorization.require.await_args.args[1].target_binding_digest == expected
