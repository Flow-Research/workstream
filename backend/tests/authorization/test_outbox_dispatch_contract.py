"""Proof of exact dispatcher registration, exact facts and restricted identity."""

from copy import copy, deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo
import inspect
from pathlib import Path
import pickle
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.api import (
    OutboxDispatchFacts, OutboxDispatchPhase, PreparedOutboxDispatch,
    outbox_dispatch_resource_digest,
)
from app.modules.authorization.catalogue import (
    ACTION_BY_ID, FUTURE_INTENT_REQUIRED_ACTIONS, SERVICE_ACTIONS_BY_IDENTITY,
    ActionAvailability, ActionId, ActionOwner, PermissionId, _index_service_actions,
    resolve_executable_action,
)
from app.modules.authorization.policy import ADMIN_ROLE_PERMISSIONS
from app.modules.authorization.prepared import fixed_service_action_context
from app.modules.authorization.runtime import AuthorizationDenialCode, PreparedAuthorizationUnsupported


def facts(phase=OutboxDispatchPhase.CLAIM):
    """Use fixed valid values for independently reproducible digest vectors."""
    return OutboxDispatchFacts(
        phase=phase, event_id=UUID(int=1), project_id=UUID(int=2),
        payload_digest='sha256:' + 'a' * 64, claim_generation=1, claim_owner='worker-1',
        claimed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        claim_expires_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        live_until=(datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)
                    if phase is OutboxDispatchPhase.RENEW else None),
        outcome_digest=('sha256:' + 'b' * 64 if phase is OutboxDispatchPhase.FINALIZE else None),
    )


def test_dispatch_registration_is_exact_and_active():
    """Activate only the fixed pair, with no human or foreign feature rights."""
    definition = ACTION_BY_ID[ActionId.OUTBOX_DISPATCH]
    assert (definition.permission_id, definition.owner, definition.availability) == (
        PermissionId.OUTBOX_DISPATCH, ActionOwner.AUTH_OUTBOX_01, ActionAvailability.ACTIVE,
    )
    assert SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.OUTBOX_DISPATCHER] == {ActionId.OUTBOX_DISPATCH}
    assert ActionId.OUTBOX_DISPATCH not in FUTURE_INTENT_REQUIRED_ACTIONS
    assert all(PermissionId.OUTBOX_DISPATCH not in permissions for permissions in ADMIN_ROLE_PERMISSIONS.values())
    assert all(ActionId.OUTBOX_DISPATCH not in actions for identity, actions in SERVICE_ACTIONS_BY_IDENTITY.items()
               if identity is not ServiceIdentity.OUTBOX_DISPATCHER)
    assert resolve_executable_action(ActionId.OUTBOX_DISPATCH) is definition
    rows = dict(SERVICE_ACTIONS_BY_IDENTITY)
    rows[ServiceIdentity.OUTBOX_DISPATCHER] |= {ActionId.ARTIFACT_VERIFICATION_EXECUTE}
    with pytest.raises(RuntimeError, match='matrix row mismatch'):
        _index_service_actions(rows)


def test_dispatch_facts_validate_all_phases():
    """Reject each invalid scalar independently of all other valid fields."""
    for phase in OutboxDispatchPhase:
        value = facts(phase)
        assert value.phase is phase
        with pytest.raises(FrozenInstanceError, match="cannot assign to field 'claim_generation'"):
            value.claim_generation = 2
        assert replace(value, claim_generation=2147483647, claim_owner='a' * 120)
        invalid = {
            'phase': ['claim', None], 'event_id': [str(uuid4()), None],
            'project_id': [str(uuid4()), None], 'payload_digest': ['sha256:ABC', 'private-content', None],
            'claim_generation': [0, -1, True, 1.0, 2147483648],
            'claim_owner': ['', 'x' * 121, 'bad owner', 'secret\n', None],
            'claimed_at': [datetime(2026, 1, 1), None],
            'claim_expires_at': [datetime(2026, 1, 1), value.claimed_at, value.claimed_at - timedelta(seconds=1)],
            'outcome_digest': ([None, 'private-outcome'] if phase is OutboxDispatchPhase.FINALIZE
                               else ['sha256:' + 'b' * 64]),
        }
        for field, variants in invalid.items():
            for variant in variants:
                with pytest.raises(ValueError, match='outbox dispatch .* invalid') as error:
                    replace(value, **{field: variant})
                assert 'private' not in str(error.value) and error.value.__cause__ is None
    with pytest.raises(ValueError, match='lease is invalid'):
        replace(facts(), claimed_at=datetime.min.replace(tzinfo=timezone(timedelta(hours=1))))


def test_renewal_binds_a_later_live_time_without_changing_original_claim():
    original = facts(OutboxDispatchPhase.INVOKE)
    renewed = facts(OutboxDispatchPhase.RENEW)
    assert renewed.claimed_at == original.claimed_at
    assert renewed.claim_expires_at == original.claim_expires_at
    assert outbox_dispatch_resource_digest(renewed) != outbox_dispatch_resource_digest(
        replace(renewed, live_until=renewed.live_until + timedelta(seconds=1))
    )
    for invalid in (None, original.claim_expires_at, original.claimed_at):
        with pytest.raises(ValueError):
            replace(renewed, live_until=invalid)
    with pytest.raises(ValueError, match="renewal time"):
        replace(original, live_until=renewed.live_until)


@pytest.mark.parametrize("field", ["claimed_at", "claim_expires_at"])
@pytest.mark.parametrize("failure", ["raises", "invalid_offset"])
def test_dispatch_lease_sanitizes_timezone_failures(field, failure):
    """One hostile timestamp cannot expose arbitrary timezone exception content."""
    class InvalidTimezone(tzinfo):
        def utcoffset(self, _value):
            if failure == "raises":
                raise RuntimeError("private-tz-secret")
            return "private-tz-secret"

    timestamp = datetime(2026, 1, 1, 0, 1, tzinfo=InvalidTimezone())
    with pytest.raises(ValueError) as error:
        replace(facts(), **{field: timestamp})
    assert str(error.value) == "outbox dispatch lease is invalid"
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


def test_dispatch_digest_matches_canonical_envelope():
    """Lock the exact action/permission/service/resource/phase envelope bytes."""
    digest = outbox_dispatch_resource_digest(facts())
    assert digest == 'sha256:b124914b9b954742d357c30a847b46a873fbe9d5c0060fa70472bf0bc76f57ea'


def test_dispatch_digest_binds_every_fact():
    """Exact envelope vector and independent substitutions protect hash binding."""
    value = facts()
    digest = outbox_dispatch_resource_digest(value)
    substitutions = {
        'phase': OutboxDispatchPhase.INVOKE, 'event_id': UUID(int=3), 'project_id': UUID(int=4),
        'payload_digest': 'sha256:' + 'c' * 64, 'claim_generation': 2, 'claim_owner': 'worker-2',
        'claimed_at': value.claimed_at + timedelta(seconds=1),
        'claim_expires_at': value.claim_expires_at + timedelta(seconds=1),
    }
    for field, changed in substitutions.items():
        assert outbox_dispatch_resource_digest(replace(value, **{field: changed})) != digest, field
    final = facts(OutboxDispatchPhase.FINALIZE)
    assert outbox_dispatch_resource_digest(final) != digest
    assert outbox_dispatch_resource_digest(replace(final, outcome_digest='sha256:'+'c'*64)) != outbox_dispatch_resource_digest(final)
    assert outbox_dispatch_resource_digest(replace(value,
        claimed_at=value.claimed_at.astimezone(timezone(timedelta(hours=2))),
        claim_expires_at=value.claim_expires_at.astimezone(timezone(timedelta(hours=-3))),
    )) == digest
    with pytest.raises(ValueError, match='facts are invalid'):
        outbox_dispatch_resource_digest({})
    forged = facts()
    object.__setattr__(forged, 'claim_generation', True)
    with pytest.raises(ValueError, match='facts are invalid'):
        outbox_dispatch_resource_digest(forged)


def test_dispatch_prepared_contract_is_nominal_and_process_local():
    """The abstract API issues no authority; even concrete test handles cannot copy."""
    assert inspect.isabstract(PreparedOutboxDispatch)
    with pytest.raises(TypeError):
        PreparedOutboxDispatch()

    class NeverAuthorizes(PreparedOutboxDispatch):
        async def consume(self, facts):
            raise AssertionError('test handle cannot authorize')

    handle = NeverAuthorizes()
    for transfer in (pickle.dumps, copy, deepcopy):
        with pytest.raises(TypeError, match='process-local'):
            transfer(handle)


@pytest.mark.asyncio
async def test_dispatch_service_admission(clean_postgres_database):
    """Real persisted identities distinguish missing provisioning and foreign-action denial."""
    engine = create_async_engine(clean_postgres_database)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            async def admit(identity, action):
                return await fixed_service_action_context(session, service_identity=identity,
                    action_id=action, request_id=uuid4(), correlation_id=uuid4())

            assert await session.scalar(select(ActorProfile).where(
                ActorProfile.service_identity == ServiceIdentity.OUTBOX_DISPATCHER.value)) is None
            with pytest.raises(PreparedAuthorizationUnsupported) as missing:
                await admit(ServiceIdentity.OUTBOX_DISPATCHER, ActionId.OUTBOX_DISPATCH)
            assert missing.value.denial_code is AuthorizationDenialCode.ACTOR_NOT_FOUND
            for identity in (ServiceIdentity.OUTBOX_DISPATCHER, ServiceIdentity.ARTIFACT_VERIFIER):
                actor_id, link_id = str(new_record_id()), str(new_record_id())
                session.add(ActorProfile(id=actor_id, actor_kind='service', status='active',
                    provisioning_method='manual_service_provisioning', service_identity=identity.value,
                    created_by=actor_id))
                await session.flush()
                session.add(ActorIdentityLink(id=link_id, actor_profile_id=actor_id,
                    issuer='workstream.internal', subject=identity.value, subject_kind='service',
                    status='active', linked_by='workstream:system:bootstrap'))
            await session.commit()
            rows = (await session.execute(select(ActorProfile, ActorIdentityLink).join(
                ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id))).all()
            assert len(rows) == 2
            assert all(p.status == link.status == 'active' and p.actor_kind == link.subject_kind == 'service'
                       for p, link in rows)
            assert SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.OUTBOX_DISPATCHER] == {ActionId.OUTBOX_DISPATCH}
            assert ACTION_BY_ID[ActionId.OUTBOX_DISPATCH].availability is ActionAvailability.ACTIVE
            dispatcher = await admit(ServiceIdentity.OUTBOX_DISPATCHER, ActionId.OUTBOX_DISPATCH)
            assert dispatcher.service_identity is ServiceIdentity.OUTBOX_DISPATCHER
            active_foreign = {action for actions in SERVICE_ACTIONS_BY_IDENTITY.values() for action in actions
                              if ACTION_BY_ID[action].availability is ActionAvailability.ACTIVE
                              and action is not ActionId.OUTBOX_DISPATCH}
            assert ActionId.ARTIFACT_VERIFICATION_EXECUTE in active_foreign
            for action in active_foreign:
                assert action not in SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.OUTBOX_DISPATCHER]
                with pytest.raises(PreparedAuthorizationUnsupported) as foreign:
                    await admit(ServiceIdentity.OUTBOX_DISPATCHER, action)
                assert foreign.value.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            control = await admit(ServiceIdentity.ARTIFACT_VERIFIER, ActionId.ARTIFACT_VERIFICATION_EXECUTE)
            assert control.service_identity is ServiceIdentity.ARTIFACT_VERIFIER
    finally:
        await engine.dispose()


def test_service_identity_alias_is_removed():
    """Current executable consumers use the canonical API; no compatibility module."""
    root = Path(__file__).resolve().parents[3]
    obsolete = 'app.modules.actors.' + 'service_identities'
    assert not (root / 'backend/app/modules/actors/service_identities.py').exists()
    for directory in (root/'backend/app', root/'backend/tests'):
        for path in directory.rglob('*.py'):
            assert obsolete not in path.read_text(), path
    for path in (root/'.ci/auth-boundaries/IMPORT_LEDGER.md', root/'.ci/module-boundaries/private-edge-debt.v1.json'):
        assert obsolete not in path.read_text(), path


@pytest.mark.parametrize("field", ["resource_type", "resource_id", "scope_project_id"])
def test_outbox_resource_rejects_selector_substitution(field):
    from app.modules.authorization.domain.outbox_dispatch import outbox_dispatch_resource
    resource = outbox_dispatch_resource(facts())
    data = {**resource.model_dump(), "facts": resource.facts}
    assert type(resource).model_validate(data) == resource
    data[field] = "project" if field == "resource_type" else uuid4()
    with pytest.raises(ValueError):
        type(resource).model_validate(data)


@pytest.mark.parametrize("value", [{}, {"outbox_dispatch_digest": "bad"},
    {"outbox_dispatch_digest": "sha256:" + "0"*64, "extra": True}])
def test_prepared_dispatch_rejects_incomplete_or_extra_request_facts(value):
    from app.modules.authorization.domain.outbox_dispatch import prepared_outbox_digest
    assert prepared_outbox_digest(ActionId.ACTOR_PROFILE_READ_SELF, value, ValueError) is None
    with pytest.raises(ValueError):
        prepared_outbox_digest(ActionId.OUTBOX_DISPATCH, value, ValueError)
