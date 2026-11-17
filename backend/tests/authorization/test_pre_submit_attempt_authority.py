"""Real fixed-service AUTH for exact sealed-source PRE reads."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.api.submission_intake import PreSubmitSourceReadFacts
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.models import AuthorityIdempotencyRecord
from app.modules.tasks.models import AuditEvent


def _facts() -> PreSubmitSourceReadFacts:
    from app.modules.artifacts.selected_pre_submit_execution import source_read_facts
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitLeaseFacts
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    reservation = _source_reservation()
    return source_read_facts(SelectedPreSubmitLeaseFacts(
        reservation, new_record_id(), 1, reservation.pre_deadline_at,
    ))


async def _seed_materializer(factory: async_sessionmaker) -> str:
    actor_id, link_id = str(new_record_id()), str(new_record_id())
    async with factory.begin() as session:
        session.add(ActorProfile(
            id=actor_id, actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.ARTIFACT_MATERIALIZER.value,
            created_by="pre-submit-authority-test",
        ))
        session.add(ActorIdentityLink(
            id=link_id, actor_profile_id=actor_id,
            issuer="https://issuer.example.test", subject=f"materializer-{actor_id}",
            subject_kind="service", status="active", linked_by="pre-submit-authority-test",
        ))
    return link_id


async def _consume(session, authority, facts, key, *, reject_wrong_generation=False):
    async with session.begin():
        handle = await authority.prepare(facts=facts, idempotency_key=key)
        if reject_wrong_generation:
            with pytest.raises(ArtifactAuthorityDeniedError, match="invalid"):
                await authority.consume(
                    prepared_authorization=handle,
                    facts=facts.model_copy(update={"execution_lease_generation": facts.execution_lease_generation + 1}),
                )
        await authority.consume(prepared_authorization=handle, facts=facts)
    return handle


async def _revoke(factory: async_sessionmaker, link_id: str) -> None:
    async with factory.begin() as session:
        await session.execute(
            update(ActorIdentityLink)
            .where(ActorIdentityLink.id == link_id)
            .values(status="revoked", revoked_by="pre-submit-authority-test",
                    revoked_at=datetime.now(UTC),
                    revoked_reason="authority revoked")
        )


async def test_real_materializer_audits_each_exact_source_read_authorization(
    clean_postgres_database: str,
) -> None:
    """Exact source read authority is rechecked and audited for every consume."""
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed_materializer(factory)
        original = _facts()
        key, request_id = uuid4(), uuid4()

        async with factory() as session:
            authority = PreparedPreSubmitMaterializationAuthorization(
                session, request_id=request_id, correlation_id=uuid4(),
            )
            try:
                inspected_handle = await _consume(
                    session, authority, original, key, reject_wrong_generation=True,
                )
                execution_handle = await _consume(session, authority, original, key)
                replay_handle = await _consume(session, authority, original, key)
            finally:
                authority.close()
        assert len({id(inspected_handle), id(execution_handle), id(replay_handle)}) == 3

        async with factory() as session:
            events = (await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action_id == ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE.value
                )
            )).all()
            assert len(events) == 3
            assert all(event.event_type == "SensitiveAuthorizationAllowed" for event in events)
            # This fixed-service read authority audits every consume; ART owns
            # durable idempotency, so AUTH has no mutation reservation for key.
            assert all(event.idempotency_reference is None for event in events)
            assert all(event.resource_id == str(original.source.location.operation_id) for event in events)
            assert len({event.id for event in events}) == 3
            assert (await session.scalars(select(AuthorityIdempotencyRecord))).all() == []
    finally:
        await engine.dispose()


@pytest.mark.parametrize("completed_consumes", (1, 2))
async def test_real_materializer_revocation_denies_next_source_read(
    clean_postgres_database: str, completed_consumes: int,
) -> None:
    """A committed earlier audit never carries authority past a revoked service link."""
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        link_id = await _seed_materializer(factory)
        facts, key, request_id = _facts(), uuid4(), uuid4()
        async with factory() as session:
            authority = PreparedPreSubmitMaterializationAuthorization(
                session, request_id=request_id, correlation_id=uuid4(),
            )
            try:
                for _ in range(completed_consumes):
                    await _consume(session, authority, facts, key)
                await _revoke(factory, link_id)
                async with session.begin():
                    with pytest.raises(ArtifactAuthorityDeniedError):
                        await authority.prepare(facts=facts, idempotency_key=key)
            finally:
                authority.close()
        async with factory() as session:
            events = (await session.scalars(select(AuditEvent).where(
                AuditEvent.action_id == ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE.value
            ))).all()
            assert len([event for event in events if event.event_type == "SensitiveAuthorizationAllowed"]) == completed_consumes
    finally:
        await engine.dispose()
