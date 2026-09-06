"""Independent diagnostic composer guards; these mocks do not prove AUTH denial."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.catalogue import ActionId
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.diagnostic_read_fixtures import (
    attach_post_submit_policy, make_diagnostic_case, read_diagnostic,
)


def _assert_concealed(case: SimpleNamespace, action: ActionId) -> None:
    """One authorization request contains no diagnostic record or digest facts."""
    case.authorization.require.assert_awaited_once()
    called_action, context = case.authorization.require.await_args.args
    assert called_action is action
    assert str(context.scope_project_id) == case.project_id
    assert context.target_exists is False
    assert context.target_binding_digest is None
    assert context.source_snapshot_id is None
    assert context.source_snapshot_hash is None


@pytest.mark.asyncio
async def test_unsupported_diagnostic_action_short_circuits() -> None:
    """An unrelated action cannot begin resource lookup or authorization."""
    case = make_diagnostic_case()

    with pytest.raises(ValueError, match="unsupported project diagnostic read action"):
        await read_diagnostic(case, ActionId.PROJECT_READ)

    for port in vars(case.repository).values():
        port.assert_not_awaited()
    case.authorization.require.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing-project", "missing-guide", "foreign-guide"])
async def test_invalid_diagnostic_parent_conceals_target(invalid: str) -> None:
    """Each parent guard must deny even though a valid diagnostic record exists."""
    case = make_diagnostic_case()
    if invalid == "missing-project":
        case.repository.get_project.return_value = None
    elif invalid == "missing-guide":
        case.repository.lock_project_guide.return_value = None
    else:
        case.guide.project_id = str(uuid4())

    with pytest.raises(RuntimeError, match="missing diagnostic authorization unexpectedly allowed"):
        await read_diagnostic(case, ActionId.PROJECT_SETUP_RUN_READ)

    _assert_concealed(case, ActionId.PROJECT_SETUP_RUN_READ)
    if invalid == "missing-project":
        case.repository.lock_project_guide.assert_not_awaited()
    case.repository.lock_latest_project_setup_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_diagnostic_record_is_concealed() -> None:
    """Valid parents do not turn an absent setup run into an available target."""
    case = make_diagnostic_case()
    case.repository.lock_latest_project_setup_run.return_value = None

    with pytest.raises(RuntimeError, match="missing diagnostic authorization unexpectedly allowed"):
        await read_diagnostic(case, ActionId.PROJECT_SETUP_RUN_READ)

    _assert_concealed(case, ActionId.PROJECT_SETUP_RUN_READ)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["project_id", "guide_id"])
async def test_foreign_diagnostic_record_is_concealed(field: str) -> None:
    """A controlled foreign record fails the composer guard, not a query filter."""
    case = make_diagnostic_case()
    setattr(case.target, field, str(uuid4()))

    with pytest.raises(RuntimeError, match="missing diagnostic authorization unexpectedly allowed"):
        await read_diagnostic(case, ActionId.PROJECT_SETUP_RUN_READ)

    _assert_concealed(case, ActionId.PROJECT_SETUP_RUN_READ)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [
    "missing", "project_id", "guide_id", "guide_version", "source_snapshot_id", "source_snapshot_hash",
])
async def test_post_submit_diagnostic_rejects_invalid_policy(field: str) -> None:
    """Each policy lineage mismatch independently conceals the setup diagnostic."""
    case = make_diagnostic_case()
    policy = attach_post_submit_policy(case)
    if field == "missing":
        case.repository.lock_post_submit_checker_policy.return_value = None
    else:
        value = f"sha256:{'b' * 64}" if field == "source_snapshot_hash" else str(uuid4())
        setattr(policy, field, value)
    action = ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ

    with pytest.raises(RuntimeError, match="missing diagnostic authorization unexpectedly allowed"):
        await read_diagnostic(case, action)

    case.repository.lock_post_submit_checker_policy.assert_awaited_once_with(policy.id)
    _assert_concealed(case, action)


@pytest.mark.asyncio
async def test_diagnostic_read_propagates_authorizer_exception() -> None:
    """Valid diagnostic data cannot escape when its authorizer raises."""
    case = make_diagnostic_case()
    failure = RuntimeError("authorizer sentinel")
    case.authorization.require.side_effect = failure

    with pytest.raises(RuntimeError) as raised:
        await read_diagnostic(case, ActionId.PROJECT_SETUP_RUN_READ)

    assert raised.value is failure
    case.authorization.require.assert_awaited_once()
    action, context = case.authorization.require.await_args.args
    assert action is ActionId.PROJECT_SETUP_RUN_READ
    assert context.target_exists is True
    assert str(context.resource_id) == case.target_id
