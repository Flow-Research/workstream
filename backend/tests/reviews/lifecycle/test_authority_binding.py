"""Actual PREP consumption rejects independent changes to the selected command."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.authorization.domain.lifecycle import ReviewLifecycleActivationContract
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.reviews.api.lifecycle import JointLifecyclePhase
from tests.reviews.lifecycle.transition_support import (
    command_for, controller, facts_for, history_row, publish_history, snapshot, transition,
)


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


@pytest.mark.parametrize("clear_source", [False, True], ids=["replace", "clear"])
async def test_native_transition_cannot_change_anchored_source_even_with_new_authority(
    admin_access, clear_source,
):
    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    for phase in ("shadow", "live"):
        await transition(await command_for(admin_access.target.id, phase))
    command = await command_for(admin_access.target.id, "draining")
    source = None if clear_source else new_record_id()
    facts = facts_for(command, source_instance_id=source)
    before = await snapshot()
    async with get_session_factory()() as session:
        await session.begin()
        try:
            owner = controller(session, command)
            await owner._fence.lock_controller()
            async with owner._authorization.lock_scope(command) as prepared:
                receipt = await prepared.consume_new(facts)
                row = history_row(command, receipt, facts=facts, source_instance_id=source)
                session.add(row)
                await session.flush()
                # Valid authority and matching source observation cannot rekey the singleton.
                assert await session.scalar(text("SELECT public.joint_lifecycle_transition_valid(t) "
                    "FROM public.joint_lifecycle_transitions t WHERE id=:id"), {"id": row.id}) is True
                with pytest.raises(DBAPIError, match="transition custody invalid"):
                    await publish_history(session, row)
        finally:
            await session.rollback()
    assert await snapshot() == before


async def test_first_live_source_cannot_reuse_authority_for_another_observation(admin_access):
    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    await transition(await command_for(admin_access.target.id, "shadow"))
    command = await command_for(admin_access.target.id, "live")
    source_a, source_b = get_settings().source_instance_id, new_record_id()
    facts = facts_for(command, source_instance_id=source_a)
    before = await snapshot()
    async with get_session_factory()() as session:
        await session.begin()
        try:
            owner = controller(session, command)
            await owner._fence.lock_controller()
            async with owner._authorization.lock_scope(command) as prepared:
                receipt = await prepared.consume_new(facts)
                row = history_row(command, receipt, facts=facts, source_instance_id=source_b)
                session.add(row)
                await session.flush()
                assert await session.scalar(text("SELECT public.joint_lifecycle_transition_valid(t) "
                    "FROM public.joint_lifecycle_transitions t WHERE id=:id"), {"id": row.id}) is False
                with pytest.raises(DBAPIError, match="transition custody invalid"):
                    await publish_history(session, row)
        finally:
            await session.rollback()
    assert await snapshot() == before
    await transition(command)
    async with get_session_factory()() as session:
        assert await session.scalar(text("SELECT fulfillment_source_instance_id "
            "FROM public.joint_lifecycle_release_control")) == source_a
