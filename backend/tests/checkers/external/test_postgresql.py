"""Real PostgreSQL authority, replay, rollback and append-only registry proof."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.checker_registry_authorization import (
    ExternalCheckerRegistryAuthorizationAdapter,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistrationAuthorityFacts,
    ExternalCheckerRegistryConflict,
    ExternalCheckerRegistryUnavailable,
    make_external_checker_registration_request,
)
from app.modules.checkers.external_registry import ExternalCheckerRegistryService
from app.modules.checkers.models import ExternalCheckerRegistryEntryRecord
from tests.checkers.external.support import registration_request, registry_spec


async def _context(access, operation_id):
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == str(access.target.id)
            )
        )
    return HumanAuthorizationContext(
        actor_profile_id=access.target.id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=UUID(link.id),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=operation_id,
    )


async def _register(access, request):
    context = await _context(access, request.operation_id)
    async with db_session.get_session_factory()() as session, session.begin():
        authority = ExternalCheckerRegistryAuthorizationAdapter(
            AuthorizationService(session, context)
        )
        return await ExternalCheckerRegistryService(session, authority).register(request)


async def _snapshot() -> tuple[list[dict], list[dict]]:
    async with db_session.get_session_factory()() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "select id,registration_operation_id,entry_digest,"
                        "authorization_decision_event_id from "
                        "external_checker_registry_entries order by id"
                    )
                )
            )
            .mappings()
            .all()
        )
        events = (
            (
                await session.execute(
                    text(
                        "select id,actor_id,matched_grant_id,action_id,permission_id,"
                        "project_id,resource_type,resource_id,target_ref_kind,"
                        "target_ref_id,correlation_id,after_facts from audit_events "
                        "where action_id='checker.registry.register' order by id"
                    )
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows], [dict(row) for row in events]


def _raw_values(request, authorization_decision_event_id, *, entry_digest=None):
    spec = request.spec
    values = {
        "id": request.registry_entry_id,
        "registration_operation_id": request.operation_id,
        "request_digest": request.request_digest,
        "capability_id": spec.capability_id,
        "capability_version": spec.capability_version,
        "phase": spec.phase,
        "image_digest": spec.image_digest,
        "entry_digest": entry_digest or spec.spec_digest,
        "registered_by_actor_profile_id": request.actor_profile_id,
        "authorization_decision_event_id": authorization_decision_event_id,
        **spec.resources.model_dump(),
    }
    for prefix, schema in (
        ("configuration", spec.configuration_schema),
        ("input", spec.input_schema),
        ("output", spec.output_schema),
    ):
        values.update(
            {
                f"{prefix}_schema_id": schema.schema_id,
                f"{prefix}_schema_version": schema.schema_version,
                f"{prefix}_schema_sha256": schema.schema_sha256,
                f"{prefix}_schema_document": schema.document,
            }
        )
    return values


@pytest.mark.asyncio
async def test_real_operator_registration_replay_conflict_and_rollback(admin_access) -> None:
    grant_id = await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    request = registration_request(actor_profile_id=admin_access.target.id)

    first = await _register(admin_access, request)
    replay = await _register(admin_access, request)
    assert replay == first
    rows, events = await _snapshot()
    assert len(rows) == 1 and len(events) == 2
    assert rows[0]["authorization_decision_event_id"] == events[0]["id"]
    assert all(event["matched_grant_id"] == grant_id for event in events)
    assert all(event["permission_id"] == "operations.reconcile.run" for event in events)
    assert all(event["project_id"] is None for event in events)
    assert all(event["resource_type"] == "external_checker_registry_entry" for event in events)
    assert all(event["after_facts"]["allowed"] is True for event in events)

    conflict = registration_request(actor_profile_id=admin_access.target.id)
    conflict = conflict.model_copy(update={"spec": request.spec})
    with pytest.raises(ExternalCheckerRegistryConflict):
        await _register(admin_access, conflict)
    after_conflict = await _snapshot()
    assert after_conflict[0] == rows
    assert len(after_conflict[1]) == 2

    rollback = registration_request(
        "post_submit", actor_profile_id=admin_access.target.id
    )
    context = await _context(admin_access, rollback.operation_id)
    with pytest.raises(RuntimeError, match="force rollback"):
        async with db_session.get_session_factory()() as session, session.begin():
            authority = ExternalCheckerRegistryAuthorizationAdapter(
                AuthorizationService(session, context)
            )
            await ExternalCheckerRegistryService(session, authority).register(rollback)
            raise RuntimeError("force rollback")
    assert await _snapshot() == after_conflict

    response = await admin_access.signed.revoke(admin_access.admin, grant_id)
    assert response.status_code == 200
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await _register(admin_access, request)
    assert await _snapshot() == after_conflict


@pytest.mark.asyncio
async def test_exact_concurrent_registration_serializes_to_one_row(admin_access) -> None:
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    request = registration_request(actor_profile_id=admin_access.target.id)

    first, second = await asyncio.gather(
        _register(admin_access, request),
        _register(admin_access, request),
    )

    assert first == second
    rows, events = await _snapshot()
    assert len(rows) == 1
    assert len(events) == 2


@pytest.mark.asyncio
async def test_wrong_admin_role_is_concealed_without_allow_or_registry_row(admin_access) -> None:
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="audit_authority"
    )
    request = registration_request(actor_profile_id=admin_access.target.id)
    with pytest.raises(
        ExternalCheckerRegistryUnavailable,
        match="external_checker_registry_unavailable",
    ):
        await _register(admin_access, request)
    rows, events = await _snapshot()
    assert rows == []
    assert events == []


@pytest.mark.asyncio
async def test_registry_rejects_update_delete_truncate_and_unauthorized_insert(
    admin_access,
) -> None:
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    request = registration_request(actor_profile_id=admin_access.target.id)
    await _register(admin_access, request)

    for statement in (
        "update external_checker_registry_entries set capability_version='v2'",
        "delete from external_checker_registry_entries",
        "truncate external_checker_registry_entries",
    ):
        async with db_session.get_session_factory()() as session:
            with pytest.raises(DBAPIError, match="external checker registry is immutable"):
                async with session.begin():
                    await session.execute(text(statement))

    spec = registry_spec("post_submit")
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "insert into external_checker_registry_entries "
                        "select :id,:operation,request_digest,capability_id,"
                        "capability_version,'post_submit',image_digest,"
                        "configuration_schema_id,configuration_schema_version,"
                        "configuration_schema_sha256,configuration_schema_document,"
                        "'external_checker_post_submit_input',input_schema_version,"
                        "input_schema_sha256,input_schema_document,output_schema_id,"
                        "output_schema_version,output_schema_sha256,output_schema_document,"
                        "cpu_millis,memory_bytes,deadline_ms,maximum_output_bytes,"
                        ":digest,registered_by_actor_profile_id,:authority,clock_timestamp() "
                        "from external_checker_registry_entries limit 1"
                    ),
                    {
                        "id": new_record_id(),
                        "operation": uuid4(),
                        "digest": spec.spec_digest,
                        "authority": uuid4(),
                    },
                )

    duplicate = make_external_checker_registration_request(
        actor_profile_id=admin_access.target.id,
        operation_id=uuid4(),
        registry_entry_id=new_record_id(),
        spec=request.spec,
    )
    context = await _context(admin_access, duplicate.operation_id)
    with pytest.raises(DBAPIError, match="registry_identity"):
        async with db_session.get_session_factory()() as session, session.begin():
            authority = ExternalCheckerRegistryAuthorizationAdapter(
                AuthorizationService(session, context)
            )
            receipt = await authority.authorize_registration(
                ExternalCheckerRegistrationAuthorityFacts(
                    actor_profile_id=duplicate.actor_profile_id,
                    operation_id=duplicate.operation_id,
                    registry_entry_id=duplicate.registry_entry_id,
                    request_digest=duplicate.request_digest,
                    entry_digest=duplicate.spec.spec_digest,
                )
            )
            await session.execute(
                insert(ExternalCheckerRegistryEntryRecord).values(
                    **_raw_values(
                        duplicate,
                        receipt.authorization_decision_event_id,
                    )
                )
            )


@pytest.mark.asyncio
async def test_direct_insert_with_real_authority_but_substituted_digest_rolls_back(
    admin_access,
) -> None:
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    request = registration_request(actor_profile_id=admin_access.target.id)
    context = await _context(admin_access, request.operation_id)

    with pytest.raises(DBAPIError, match="registry authority closure invalid"):
        async with db_session.get_session_factory()() as session, session.begin():
            authority = ExternalCheckerRegistryAuthorizationAdapter(
                AuthorizationService(session, context)
            )
            receipt = await authority.authorize_registration(
                ExternalCheckerRegistrationAuthorityFacts(
                    actor_profile_id=request.actor_profile_id,
                    operation_id=request.operation_id,
                    registry_entry_id=request.registry_entry_id,
                    request_digest=request.request_digest,
                    entry_digest=request.spec.spec_digest,
                )
            )
            await session.execute(
                insert(ExternalCheckerRegistryEntryRecord).values(
                    **_raw_values(
                        request,
                        receipt.authorization_decision_event_id,
                        entry_digest="sha256:" + "0" * 64,
                    )
                )
            )

    assert await _snapshot() == ([], [])
