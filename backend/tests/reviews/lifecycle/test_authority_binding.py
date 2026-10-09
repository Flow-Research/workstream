"""Actual PREP consumption rejects independent changes to the selected command."""

from datetime import timedelta

import pytest

from app.core.identifiers import new_record_id
from app.db.session import get_session_factory
from app.modules.authorization.domain.lifecycle import ReviewLifecycleActivationContract
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.reviews.api.lifecycle import JointLifecyclePhase
from tests.reviews.lifecycle.transition_support import command_for, controller, facts_for, snapshot, transition


@pytest.mark.parametrize("field", [
    "operation_id", "singleton_id", "actor_profile_id", "identity_link_id",
    "expected_generation", "current_phase", "target_phase", "deadline", "reviewed_manifest_digest", "reason",
])
async def test_prepared_command_substitution_rejects_before_allow(admin_access, field):
    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    if field == "current_phase":
        await transition(await command_for(admin_access.target.id, "shadow"))
    command = await command_for(admin_access.target.id, "live" if field == "current_phase" else "shadow")
    value = {
        "expected_generation": 1,
        "current_phase": JointLifecyclePhase.DISABLED,
        "deadline": command.deadline + timedelta(seconds=1),
        "target_phase": JointLifecyclePhase.LIVE,
        "reviewed_manifest_digest": "sha256:" + "1" * 64,
        "reason": "different selected operation",
    }.get(field, new_record_id())
    changed = command.model_copy(update={field: value})
    facts = facts_for(changed)
    # Recompute the outer resource identity so its own shape guard cannot mask
    # the actual prepared-command comparison.
    ReviewLifecycleActivationContract(resource_id=changed.singleton_id, facts=facts)
    before = await snapshot()
    async with get_session_factory()() as session:
        await session.begin()
        owner = controller(session, command)
        async with owner._authorization.lock_scope(command) as prepared:
            with pytest.raises(PreparedAuthorizationHandleInvalid, match="lifecycle"):
                await prepared.consume_new(facts)
        await session.rollback()
    assert await snapshot() == before
    assert (await transition(command)).generation == command.expected_generation + 1
