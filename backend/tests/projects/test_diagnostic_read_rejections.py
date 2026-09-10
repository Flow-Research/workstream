"""Independent diagnostic composer guards; these mocks do not prove AUTH denial."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.catalogue import ActionId
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.diagnostic_read_fixtures import (
    make_diagnostic_case, read_diagnostic,
)


def _assert_concealed(
    case: SimpleNamespace, action: ActionId, *,
    project_exists: bool = True, guide_exists: bool = True,
) -> None:
    """Bind every negative authorization fact to the explicit expected context."""
    case.authorization.require.assert_awaited_once()
    called_action, context = case.authorization.require.await_args.args
    assert called_action is action
    assert action is ActionId.PROJECT_SETUP_RUN_READ
    assert context.model_dump(mode="json") == {
        "resource_type": "project_diagnostic", "resource_id": case.target_id,
        "scope_project_id": case.project_id, "guide_id": case.guide_id,
        "guide_version": "v1" if guide_exists else None,
        "target_kind": "setup_run",
        "project_exists": project_exists, "guide_exists": guide_exists,
        "target_exists": False, "target_binding_digest": None,
        "source_snapshot_id": None, "source_snapshot_hash": None,
    }


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

    _assert_concealed(
        case, ActionId.PROJECT_SETUP_RUN_READ,
        project_exists=invalid != "missing-project", guide_exists=False,
    )
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
