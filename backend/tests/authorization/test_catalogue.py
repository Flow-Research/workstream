"""Exact closed catalogue and proposal actions' unavailable-by-default status."""

from collections import Counter

import pytest

from app.modules.authorization.catalogue import (
    ACTION_IDS, ACTION_DEFINITIONS, ACTION_BY_ID, PERMISSION_IDS,
    HISTORICAL_PERMISSION_IDS, NEW_PERMISSION_IDS, ActionId, PermissionId,
    ActionOwner, ActionAvailability, resolve_executable_action,
)
from tests.authorization.catalogue_fixtures import ART_CUSTODY_EXPECTATIONS, REV_CUSTODY_EXPECTATIONS


def test_closed_permission_and_action_catalogue_is_exact_and_non_executable() -> None:
    from tests.authorization.catalogue_fixtures import (
        historical_permissions, new_permissions, expected
    )
    assert {item.value for item in HISTORICAL_PERMISSION_IDS} == historical_permissions
    assert {item.value for item in NEW_PERMISSION_IDS} == new_permissions
    assert {item.value for item in PERMISSION_IDS} == historical_permissions | new_permissions
    assert len(ACTION_IDS) == len(ACTION_DEFINITIONS) == len(ACTION_BY_ID) == 116
    assert set(ACTION_BY_ID) == ACTION_IDS
    assert {definition.owner for definition in ACTION_DEFINITIONS} == set(ActionOwner)
    assert {
        definition.action_id.value: (
            definition.permission_id.value,
            definition.owner.value,
        )
        for definition in ACTION_DEFINITIONS
    } == expected
    assert {
        action: (
            ACTION_BY_ID[ActionId(action)].permission_id.value,
            ACTION_BY_ID[ActionId(action)].owner.value,
            ACTION_BY_ID[ActionId(action)].availability.value,
        )
        for action in ART_CUSTODY_EXPECTATIONS
    } == ART_CUSTODY_EXPECTATIONS
    assert {
        action: (
            ACTION_BY_ID[ActionId(action)].permission_id.value,
            ACTION_BY_ID[ActionId(action)].owner.value,
            ACTION_BY_ID[ActionId(action)].availability.value,
        )
        for action in REV_CUSTODY_EXPECTATIONS
    } == REV_CUSTODY_EXPECTATIONS
    assert {
        owner: sum(definition.owner is owner for definition in ACTION_DEFINITIONS)
        for owner in {
            ActionOwner.AUTH_ART_02D_OPERATOR,
            ActionOwner.AUTH_ART_02D_INTERNAL,
            ActionOwner.XINT_002_04B,
            ActionOwner.XINT_002_06A,
            ActionOwner.AUTH_ART_05,
            ActionOwner.AUTH_ART_06A,
            ActionOwner.AUTH_ART_06B,
            ActionOwner.XINT_002_04A,
            ActionOwner.XINT_002_05A,
            ActionOwner.XINT_002_07,
        }
    } == {
        ActionOwner.AUTH_ART_02D_OPERATOR: 8,
        ActionOwner.AUTH_ART_02D_INTERNAL: 3,
        ActionOwner.XINT_002_04B: 1,
        ActionOwner.XINT_002_06A: 1,
        ActionOwner.AUTH_ART_05: 1,
        ActionOwner.AUTH_ART_06A: 1,
        ActionOwner.AUTH_ART_06B: 2,
        ActionOwner.XINT_002_04A: 1,
        ActionOwner.XINT_002_05A: 1,
        ActionOwner.XINT_002_07: 2,
    }
    assert all(not owner.value.startswith("WS-ART-") for owner in ActionOwner)
    assert {
        owner: sum(definition.owner is owner for definition in ACTION_DEFINITIONS)
        for owner in {
            ActionOwner.AUTH_REV_05,
            ActionOwner.AUTH_REV_06,
            ActionOwner.AUTH_REV_07,
            ActionOwner.AUTH_REV_08,
            ActionOwner.AUTH_REV_09A,
            ActionOwner.AUTH_REV_11,
            ActionOwner.AUTH_REV_12,
            ActionOwner.XINT_003_08A,
            ActionOwner.XINT_003_08B,
        }
    } == {
        ActionOwner.AUTH_REV_05: 2,
        ActionOwner.AUTH_REV_06: 5,
        ActionOwner.AUTH_REV_07: 3,
        ActionOwner.AUTH_REV_08: 1,
        ActionOwner.AUTH_REV_09A: 1,
        ActionOwner.AUTH_REV_11: 5,
        ActionOwner.AUTH_REV_12: 2,
        ActionOwner.XINT_003_08A: 3,
        ActionOwner.XINT_003_08B: 1,
    }
    assert all(not owner.value.startswith("WS-REV-") for owner in ActionOwner)
    assert Counter(definition.availability for definition in ACTION_DEFINITIONS) == {
        ActionAvailability.ACTIVE: 71,
        ActionAvailability.PLANNED: 45,
    }
    assert resolve_executable_action(ActionId.ACTOR_PROFILE_READ_SELF).permission_id is PermissionId.ACTOR_PROFILE_READ_SELF
    with pytest.raises(ValueError, match="not active"):
        resolve_executable_action(ActionId.REVIEW_QUEUE_READ)
    with pytest.raises(TypeError):
        ACTION_BY_ID[ActionId.ACTOR_PROFILE_READ_SELF] = ACTION_DEFINITIONS[0]


@pytest.mark.parametrize("action", [
    ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ,
    ActionId.PROJECT_GUIDE_COMPILATION_CORRECTION_REQUEST,
])
def test_proposal_actions_remain_planned_without_executable_authority(action):
    assert ACTION_BY_ID[action].availability is ActionAvailability.PLANNED
    with pytest.raises(ValueError, match="not active"):
        resolve_executable_action(action)
