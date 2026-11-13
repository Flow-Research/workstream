"""Real AUTH prepared/read evidence for intake operations, not ART T1 admission."""
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.authorization.api.submission_intake import (
    IntakeAuthorityDenied, IntakeOperationReadFacts, IntakeReservationAuthorityFacts, IntakeReservationPreflightFacts,
    IntakeAcceptanceAuthorityFacts,
)
from app.modules.authorization.submission_intake import SubmissionIntakeAuthorization
from app.modules.tasks.models import AuditEvent
from tests.authorization.admin_access.support import create_project
from tests.authorization.task_authority.test_postgresql import context, grant, project_manager


def reservation(ctx, project):
    return IntakeReservationAuthorityFacts(
        operation_id=new_record_id(), project_id=project, task_id=new_record_id(),
        assignment_id=new_record_id(), actor_profile_id=ctx.actor_profile_id,
        identity_link_id=ctx.identity_link_id, idempotency_key=new_record_id(),
        metadata_sha256="sha256:" + "a" * 64, locked_context_sha256="sha256:" + "b" * 64,
        task_status="in_progress",
    )


@pytest.fixture
async def intake_authority(admin_access):
    project = await create_project("Intake authority")
    manager = await project_manager(admin_access, project)
    grant_id = await grant(admin_access, manager, project)
    return admin_access, project, grant_id, await context(admin_access)


async def test_intake_authority_exact_audit_rollback_and_single_use(intake_authority):
    _, project, grant_id, ctx = intake_authority
    facts = reservation(ctx, project)
    async with db_session.get_session_factory()() as session:
        authority = SubmissionIntakeAuthorization(session, ctx)
        try:
            async with session.begin():
                await authority.lock_actor(ctx.actor_profile_id, ctx.identity_link_id)
                handle = await authority.prepare(facts)
                decision = await authority.consume(handle, facts)
            row = await session.get(AuditEvent, str(decision))
            assert (row.action_id, row.permission_id, row.matched_grant_id) == (
                "submission.intake.reserve", "submission.create", grant_id)
            assert (row.resource_type, row.resource_id, row.target_ref_kind, row.target_ref_id) == (
                "submission_operation", str(facts.operation_id), "submission_operation", str(facts.operation_id))
            assert row.project_id == str(project) and row.after_facts["allowed"] is True
            assert set(row.after_facts) == {"allowed", "resource_context_digest"}
            await session.rollback()
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin():
                    await authority.consume(handle, facts)
            async with session.begin():
                pending = await authority.prepare(facts)
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin():
                    await authority.consume(pending, facts)
            async with session.begin():
                rolled_back = await authority.consume(await authority.prepare(facts), facts)
                await session.rollback()
            assert await session.get(AuditEvent, str(rolled_back)) is None
        finally:
            authority.close()


@pytest.mark.parametrize("field", ["operation_id", "task_id", "assignment_id", "idempotency_key",
                                    "actor_profile_id", "identity_link_id", "metadata_sha256", "locked_context_sha256"])
async def test_intake_authority_substitution_cannot_consume(intake_authority, field):
    _, project, _, ctx = intake_authority
    facts = reservation(ctx, project)
    changed = replace(facts, **{field: "sha256:" + "c" * 64 if field.endswith("sha256") else new_record_id()})
    async with db_session.get_session_factory()() as session:
        authority = SubmissionIntakeAuthorization(session, ctx)
        try:
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin():
                    handle = await authority.prepare(facts)
                    await authority.consume(handle, changed)
            assert not list(await session.scalars(select(AuditEvent).where(AuditEvent.request_id == str(ctx.request_id))))
        finally:
            authority.close()


@pytest.mark.parametrize("case", ["missing", "reviewer", "foreign", "revoked", "admin"])
async def test_intake_reserve_and_read_require_exact_current_submitter(admin_access, case):
    project = await create_project("Intake denial")
    if case == "admin":
        await admin_access.signed.grant(admin_access.admin, admin_access.target, role="project_manager", project_id=project)
    elif case != "missing":
        grant_project = await create_project("Other intake project") if case == "foreign" else project
        manager = await project_manager(admin_access, grant_project)
        grant_id = await grant(admin_access, manager, grant_project, "reviewer" if case == "reviewer" else "submitter")
        if case == "revoked":
            response = await admin_access.signed.client.post(
                f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke",
                headers=manager.headers | {"Idempotency-Key": str(new_record_id())},
                json={"reason": "Withdraw intake grant"})
            assert response.status_code == 200, response.text
    ctx = await context(admin_access)
    facts = reservation(ctx, project)
    read = IntakeOperationReadFacts(facts.operation_id, project, facts.task_id, ctx.actor_profile_id)
    for method, value in (("preflight", preflight_facts(facts)), ("prepare", facts),
                          ("prepare_acceptance", replace(acceptance(ctx, project), operation_id=facts.operation_id)),
                          ("authorize_read", read)):
        async with db_session.get_session_factory()() as session:
            authority = SubmissionIntakeAuthorization(session, ctx)
            try:
                with pytest.raises(IntakeAuthorityDenied) as caught:
                    async with session.begin():
                        await getattr(authority, method)(value)
                assert await authority.restage_denial(caught.value)
                await session.commit()
                rows = list(await session.scalars(select(AuditEvent).where(AuditEvent.request_id == str(ctx.request_id))))
                assert rows and all(row.after_facts["allowed"] is False for row in rows)
                assert all(row.resource_id == str(facts.operation_id) for row in rows)
            finally:
                authority.close()


async def test_intake_read_has_no_new_submission_status_or_original_link_dependency(intake_authority):
    _, project, _, ctx = intake_authority
    facts = reservation(ctx, project)
    # AUTH reads only resolved historical owner/project, not current TASK eligibility.
    read = IntakeOperationReadFacts(facts.operation_id, project, facts.task_id, ctx.actor_profile_id)
    async with db_session.get_session_factory()() as session:
        authority = SubmissionIntakeAuthorization(session, ctx)
        try:
            async with session.begin():
                decision = await authority.authorize_read(read)
            row = await session.get(AuditEvent, str(decision))
            assert row.action_id == "task.submission_operation.read" and row.permission_id == "submission.read_own"
            assert row.resource_id == str(facts.operation_id)
            await session.rollback()
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin_nested():
                    await authority.authorize_read(read)
            await session.rollback()
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin():
                    await authority.authorize_read(replace(read, actor_profile_id=new_record_id()))
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin():
                    await authority.lock_actor(ctx.actor_profile_id, new_record_id())
        finally:
            authority.close()


async def test_intake_revoked_current_link_cannot_reserve_or_read(intake_authority):
    _, project, _, ctx = intake_authority
    facts = reservation(ctx, project)
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE actor_identity_links SET status='revoked',revoked_by=:actor,"
                "revoked_at=clock_timestamp(),revoked_reason='intake proof' WHERE id=:link"
            ), {"actor": str(ctx.actor_profile_id), "link": str(ctx.identity_link_id)})
        authority = SubmissionIntakeAuthorization(session, ctx)
        try:
            for method, args in (
                ("lock_actor", (ctx.actor_profile_id, ctx.identity_link_id)),
                ("prepare", (facts,)),
                ("authorize_read", (IntakeOperationReadFacts(facts.operation_id, project, facts.task_id, ctx.actor_profile_id),)),
            ):
                with pytest.raises(IntakeAuthorityDenied):
                    async with session.begin():
                        await getattr(authority, method)(*args)
        finally:
            authority.close()


def preflight_facts(facts):
    return IntakeReservationPreflightFacts(**{
        field.name: getattr(facts, field.name) for field in fields(IntakeReservationPreflightFacts)
    })


async def test_intake_preflight_has_no_allow_or_consumable_handle(intake_authority):
    _, project, _, ctx = intake_authority
    facts = reservation(ctx, project)
    selectors = preflight_facts(facts)
    async with db_session.get_session_factory()() as session:
        authority = SubmissionIntakeAuthorization(session, ctx)
        try:
            async with session.begin():
                await authority.lock_actor(ctx.actor_profile_id, ctx.identity_link_id)
                assert await authority.preflight(selectors) is None
                assert not list(await session.scalars(select(AuditEvent).where(
                    AuditEvent.request_id == str(ctx.request_id))))
                with pytest.raises(IntakeAuthorityDenied):
                    await authority.prepare(selectors)
                # Only complete locked-context facts may produce reservation authority.
                decision = await authority.consume(await authority.prepare(facts), facts)
            row = await session.get(AuditEvent, str(decision))
            assert row.after_facts["allowed"] is True
        finally:
            authority.close()


def acceptance(ctx, project):
    return IntakeAcceptanceAuthorityFacts(
        **asdict(reservation(ctx, project)),
        foreground_lease_id=new_record_id(), foreground_lease_generation=1,
        selected_pre_submit_run_id=new_record_id(),
        selected_pre_submit_request_sha256="sha256:" + "c" * 64,
        selected_pre_submit_terminal_sha256="sha256:" + "d" * 64,
        source_sha256="sha256:" + "e" * 64,
        semantic_manifest_sha256="sha256:" + "f" * 64,
        accepted_context_sha256="sha256:" + "1" * 64,
        receipt_sha256="sha256:" + "2" * 64,
        accepted_at=datetime.now(timezone.utc),
        predecessor_submission_id=None, predecessor_submission_version=None,
        checker_remediation_manifest_id=None,
    )


async def test_acceptance_authority_retains_exact_operation_receipt(intake_authority):
    _, project, grant_id, ctx = intake_authority
    facts = acceptance(ctx, project)
    async with db_session.get_session_factory()() as session:
        authority = SubmissionIntakeAuthorization(session, ctx)
        try:
            async with session.begin():
                await authority.lock_actor(ctx.actor_profile_id, ctx.identity_link_id)
                handle = await authority.prepare_acceptance(facts)
                decision = await authority.consume_acceptance(handle, facts)
            async with session.begin():
                await authority.authorize_read(IntakeOperationReadFacts(
                    facts.operation_id, project, facts.task_id, ctx.actor_profile_id))
                await authority.validate_acceptance_receipt(facts, decision)
                row = await session.get(AuditEvent, str(decision))
                assert row.action_id == "submission.create"
                assert row.matched_grant_id == grant_id
                assert row.resource_id == str(facts.operation_id)
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin():
                    await authority.consume_acceptance(handle, facts)
            with pytest.raises(IntakeAuthorityDenied):
                async with session.begin():
                    await authority.validate_acceptance_receipt(
                        replace(facts, receipt_sha256="sha256:" + "3" * 64), decision)
        finally:
            authority.close()


@pytest.mark.parametrize("field", [
    "operation_id", "idempotency_key", "foreground_lease_id", "foreground_lease_generation",
    "selected_pre_submit_run_id", "selected_pre_submit_request_sha256",
    "selected_pre_submit_terminal_sha256", "source_sha256", "semantic_manifest_sha256",
    "accepted_context_sha256", "receipt_sha256",
])
async def test_acceptance_authority_rejects_changed_custody(intake_authority, field):
    _, project, _, ctx = intake_authority
    facts = acceptance(ctx, project)
    changed_value = ("sha256:" + "9" * 64 if field.endswith("sha256") else
                     2 if field == "foreground_lease_generation" else new_record_id())
    async with db_session.get_session_factory()() as session:
        authority = SubmissionIntakeAuthorization(session, ctx)
        try:
            async with session.begin():
                handle = await authority.prepare_acceptance(facts)
                with pytest.raises(IntakeAuthorityDenied):
                    await authority.consume_acceptance(handle, replace(facts, **{field: changed_value}))
                await session.rollback()
            assert not list(await session.scalars(select(AuditEvent).where(
                AuditEvent.request_id == str(ctx.request_id))))
        finally:
            authority.close()
