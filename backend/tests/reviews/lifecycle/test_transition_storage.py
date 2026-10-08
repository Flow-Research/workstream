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


@pytest.mark.parametrize("principal", ["actor", "link", "grant"])
async def test_closure_rejects_independently_inactive_authority(admin_access, principal):
    grant = await admin_access.signed.grant(admin_access.admin, admin_access.target)
    command = await command_for(admin_access.target.id, "shadow")
    before = await snapshot()
    statements = {
        "actor": ("actor_profiles", command.actor_profile_id,
            "status='suspended',suspended_by='storage-proof',suspended_at=clock_timestamp(),suspension_reason='Suspended'"),
        "link": ("actor_identity_links", command.identity_link_id,
            "status='revoked',revoked_by='storage-proof',revoked_at=clock_timestamp(),revoked_reason='Revoked'"),
        "grant": ("admin_role_grants", grant,
            "status='revoked',version=2,revoked_by_actor_profile_id=:admin,revoked_by_admin_role_grant_id=:admin_grant,revoked_reason='Revoked',revoked_at=clock_timestamp()"),
    }
    table, identifier, update = statements[principal]
    async with get_session_factory()() as session:
        await session.begin()
        receipt = await issue_authority(session, command)
        await publish_history(session, history_row(command, receipt))
        await session.execute(text(f"UPDATE public.{table} SET {update} WHERE id=:id"), {
            "id": identifier, "admin": admin_access.admin.id,
            "admin_grant": admin_access.bootstrap_grant_id,
        })
        assert await session.scalar(text(f"SELECT status FROM public.{table} WHERE id=:id"), {
            "id": identifier,
        }) != "active"
        # Valid audit facts, digests, identities and history have already been
        # written. Only the independently changed principal state can deny now.
        with pytest.raises(DBAPIError, match="joint lifecycle authority closure invalid"):
            await session.commit()
    assert await snapshot() == before
    assert (await transition(command)).generation == 1


async def test_committed_authority_receipt_cannot_be_changed_or_manufactured(admin_access):
    from app.core.identifiers import new_record_id

    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    command = await command_for(admin_access.target.id, "shadow")
    receipt = await transition(command)
    before = await snapshot()
    for field, value in (("request_id", new_record_id()),
                         ("matched_grant_id", admin_access.bootstrap_grant_id)):
        async with get_session_factory()() as session:
            with pytest.raises(DBAPIError, match="audit events are append-only"):
                await session.execute(text(f"UPDATE public.audit_events SET {field}=:value WHERE id=:id"), {
                    "value": value, "id": receipt.authorization_decision_event_id,
                })
                await session.commit()
        assert await snapshot() == before
    # Turning a different retained allow into this exact lifecycle shape must
    # also reject; an INSERT-only closure cannot see such an UPDATE.
    async with get_session_factory()() as session:
        target = await session.scalar(text(
            "SELECT id FROM public.audit_events WHERE event_type='SensitiveAuthorizationAllowed' "
            "AND action_id <> 'review.lifecycle.activation.manage' ORDER BY id LIMIT 1"
        ))
        assert target is not None
        fields = list((await session.execute(text("SELECT * FROM public.audit_events LIMIT 1"))).keys())
        columns = ",".join('"' + key + '"' for key in fields if key != "id")
        with pytest.raises(DBAPIError, match="audit events are append-only"):
            await session.execute(text(f"UPDATE public.audit_events SET ({columns})="
                f"(SELECT {columns} FROM public.audit_events WHERE id=:source) WHERE id=:target"), {
                "source": receipt.authorization_decision_event_id, "target": target,
            })
            await session.commit()
    assert await snapshot() == before
    assert await transition(command) == receipt
