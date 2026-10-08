"""Real Operator authority, immutable phase history and rollback."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from sqlalchemy.exc import DBAPIError

from app.db.session import get_session_factory
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from app.modules.reviews.lifecycle.models import JointLifecycleTransition
from app.modules.tasks.models import AuditEvent
from tests.reviews.lifecycle.transition_support import command_for, controller, snapshot, transition


async def test_operator_transitions_and_response_loss_replay(admin_access):
    access = admin_access
    grant = await access.signed.grant(access.admin, access.target)
    receipts = []
    commands = []
    for phase in ("shadow", "live", "draining", "disabled", "shadow", "disabled"):
        command = await command_for(access.target.id, phase)
        commands.append(command)
        receipt = await transition(command)
        receipts.append(receipt)
        assert receipt.generation == len(receipts)
        assert receipt.phase == phase
    before = await snapshot()
    # Replay the original generation-zero request after several transitions.
    assert await transition(commands[0]) == receipts[0]
    assert await snapshot() == before
    async with get_session_factory()() as session:
        rows = list(await session.scalars(select(JointLifecycleTransition).order_by(JointLifecycleTransition.generation)))
        assert len(rows) == 6
        for row, command in zip(rows, commands, strict=True):
            event = await session.get(AuditEvent, row.authorization_decision_event_id)
            assert event.matched_grant_id == grant
            assert event.actor_id == str(access.target.id)
            assert event.resource_id == str(command.singleton_id)
            assert event.correlation_id == str(command.operation_id)
            assert event.after_facts == {"allowed": True, "resource_context_digest": row.resource_context_digest}


async def test_invalid_edge_stale_generation_deadline_and_manifest_rollback(admin_access):
    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    original = await command_for(admin_access.target.id, "shadow")
    before = await snapshot()
    for changes in (
        {"target_phase": "live"}, {"expected_generation": 1},
        {"deadline": original.deadline - timedelta(days=1)},
        {"reviewed_manifest_digest": "sha256:" + "0" * 64},
    ):
        from app.modules.reviews.api.lifecycle import JointLifecyclePhase
        if "target_phase" in changes:
            changes["target_phase"] = JointLifecyclePhase(changes["target_phase"])
        command = original.model_copy(update=changes)
        with pytest.raises(JointLifecycleUnavailable):
            await transition(command)
        assert await snapshot() == before
    assert (await transition(original)).generation == 1


async def test_caller_rollback_removes_authority_history_and_phase(admin_access):
    grant = await admin_access.signed.grant(admin_access.admin, admin_access.target)
    command = await command_for(admin_access.target.id, "shadow")
    before = await snapshot()
    async with get_session_factory()() as session:
        await session.begin()
        await controller(session, command).transition(command)
        # The lifecycle-only NO KEY UPDATE lock still excludes suspension,
        # identity unlinking and grant revocation until the caller finishes.
        for table, identifier in (
            ("actor_profiles", command.actor_profile_id),
            ("actor_identity_links", command.identity_link_id),
            ("admin_role_grants", grant),
        ):
            async with get_session_factory()() as contender:
                with pytest.raises(DBAPIError, match="could not obtain lock"):
                    await contender.execute(text(
                        f"SELECT id FROM public.{table} WHERE id=:id FOR UPDATE NOWAIT"
                    ), {"id": identifier})
        await session.rollback()
    assert await snapshot() == before
    assert (await transition(command)).generation == 1


async def test_no_operator_revoked_operator_and_operation_collision(admin_access):
    from app.modules.authorization.runtime import PreparedAuthorizationUnsupported

    command = await command_for(admin_access.target.id, "shadow")
    before = await snapshot()
    with pytest.raises(PreparedAuthorizationUnsupported):
        await transition(command)
    assert await snapshot() == before
    grant = await admin_access.signed.grant(admin_access.admin, admin_access.target)
    receipt = await transition(command)
    before = await snapshot()
    with pytest.raises(JointLifecycleUnavailable, match="conflicts"):
        await transition(command.model_copy(update={"reason": "different request"}))
    assert await snapshot() == before
    assert await transition(command) == receipt
    response = await admin_access.signed.revoke(admin_access.admin, grant)
    assert response.status_code == 200, response.text
    before = await snapshot()
    with pytest.raises(PreparedAuthorizationUnsupported):
        await transition(command)
    assert await snapshot() == before


async def test_transition_replay_does_not_issue_sql_writes(admin_access):
    from sqlalchemy import event

    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    command = await command_for(admin_access.target.id, "shadow")
    async with get_session_factory()() as clock:
        now = await clock.scalar(text("SELECT pg_catalog.clock_timestamp()"))
    command = command.model_copy(update={"deadline": now + timedelta(seconds=5)})
    original = await transition(command)
    async with get_session_factory()() as clock:
        now = await clock.scalar(text("SELECT pg_catalog.clock_timestamp()"))
    await asyncio.sleep(max(0, (command.deadline - now).total_seconds()) + 0.05)
    engine = get_session_factory().kw["bind"].sync_engine
    writes = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        assert await transition(command) == original
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert writes == []
