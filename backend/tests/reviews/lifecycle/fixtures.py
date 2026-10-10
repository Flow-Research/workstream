"""Use real Operator transitions for acceptance participant integration controls."""

import pytest

from tests.reviews.lifecycle.transition_support import command_for, transition


@pytest.fixture
async def live_acceptance_lifecycle(admin_access):
    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    await transition(await command_for(admin_access.target.id, "shadow"))
    live = await transition(await command_for(admin_access.target.id, "live"))
    assert live.generation == 2
    return admin_access
