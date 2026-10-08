"""Closed scalar facts convey no lifecycle or business authority."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId
from app.modules.authorization.review_contracts import ReviewLifecyclePhase
from app.modules.reviews.api.lifecycle import JointLifecycleControlFacts, JointLifecyclePhase


def test_lifecycle_snapshot_is_strict_and_frozen():
    values = dict(
        singleton_id=new_record_id(),
        phase=JointLifecyclePhase.DISABLED,
        generation=0,
        created_at=datetime.now(UTC),
    )
    facts = JointLifecycleControlFacts(**values)
    assert facts.generation == 0
    with pytest.raises(ValidationError):
        facts.generation = 1
    for replacement in (
        {"generation": True},
        {"generation": "0"},
        {"generation": -1},
        {"generation": 2**63},
        {"singleton_id": uuid4()},
        {"singleton_id": str(values["singleton_id"])},
        {"phase": JointLifecyclePhase.LIVE},
        {"phase": "disabled"},
        {"created_at": datetime.now()},
        {"authorized": True},
    ):
        with pytest.raises(ValidationError):
            JointLifecycleControlFacts(**(values | replacement))


def test_phase_projection_agrees():
    assert (
        {phase.value for phase in JointLifecyclePhase}
        == {phase.value for phase in ReviewLifecyclePhase}
        == {"disabled", "shadow", "live", "draining"}
    )
    assert (
        ACTION_BY_ID[ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE].availability
        is ActionAvailability.ACTIVE
    )
