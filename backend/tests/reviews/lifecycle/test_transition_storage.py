"""Direct PostgreSQL custody of controller, history and its actual AUTH event."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_session_factory
from tests.reviews.lifecycle.transition_support import (
    command_for, facts_for, history_row, issue_authority, publish_history, snapshot, transition,
)


async def test_retained_history_and_controller_cannot_be_rewritten(admin_access):
    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    await transition(await command_for(admin_access.target.id, "shadow"))
    before = await snapshot()
    for statement, error in (
        ("UPDATE public.joint_lifecycle_transitions SET phase='live'", "custody is immutable"),
        ("DELETE FROM public.joint_lifecycle_transitions", "custody is immutable"),
        ("TRUNCATE public.joint_lifecycle_transitions CASCADE", "custody is immutable"),
        ("UPDATE public.joint_lifecycle_release_control SET phase='live',generation=2", "transition custody invalid"),
        ("UPDATE public.joint_lifecycle_release_control SET generation=3", "transition custody invalid"),
        ("DELETE FROM public.joint_lifecycle_release_control", "custody is immutable"),
    ):
        async with get_session_factory()() as session:
            with pytest.raises(DBAPIError, match=error):
                await session.execute(text(statement))
                await session.commit()
        assert await snapshot() == before


async def test_transition_authority_and_history_cannot_commit_separately(admin_access):
    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    command = await command_for(admin_access.target.id, "shadow")
    before = await snapshot()
    async with get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="authority closure invalid"):
            await session.begin()
            await issue_authority(session, command)
            await session.commit()
    assert await snapshot() == before
    async with get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="history closure invalid"):
            await session.begin()
            receipt = await issue_authority(session, command)
            session.add(history_row(command, receipt))
            await session.commit()
    assert await snapshot() == before
    # The same operation succeeds when all three actual owners commit together.
    async with get_session_factory()() as session, session.begin():
        receipt = await issue_authority(session, command)
        await publish_history(session, history_row(command, receipt))
    assert len((await snapshot())["history"]) == 1


async def test_shadow_audit_table_cannot_substitute_a_real_receipt(admin_access):
    import json
    from app.core.identifiers import new_record_id
    from app.modules.authorization.domain.lifecycle import ReviewLifecycleActivationContract
    from app.modules.authorization.runtime import authorization_resource_digest

    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    authorized = await command_for(admin_access.target.id, "shadow")
    substituted = authorized.model_copy(update={"operation_id": new_record_id()})
    facts = facts_for(substituted)
    digest = authorization_resource_digest(ReviewLifecycleActivationContract(
        resource_id=substituted.singleton_id, facts=facts,
    ))
    before = await snapshot()
    async with get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="transition custody invalid"):
            await session.begin()
            receipt = await issue_authority(session, authorized)
            await session.execute(text("CREATE TEMP TABLE audit_events (LIKE public.audit_events)"))
            await session.execute(text(
                "INSERT INTO pg_temp.audit_events SELECT * FROM public.audit_events WHERE id=:id"
            ), {"id": receipt.decision_event_id})
            await session.execute(text(
                "UPDATE pg_temp.audit_events SET correlation_id=:operation,after_facts=CAST(:facts AS json)"
            ), {"operation": substituted.operation_id,
                "facts": json.dumps({"allowed": True, "resource_context_digest": digest})})
            # Both digests and every FK are valid; only the canonical event says
            # this receipt belongs to a different operation. No stale-hash guard
            # can mask the protected-table lookup being tested here.
            await publish_history(session, history_row(substituted, receipt, facts=facts, digest=digest))
            await session.commit()
    assert await snapshot() == before
