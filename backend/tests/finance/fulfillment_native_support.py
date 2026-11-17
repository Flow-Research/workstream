"""Direct SQL probes with genuine request AUTH and held REV; never product code.

These helpers deliberately bypass the application writer and its RC gate. They
do not replace token verification, source custody, authority consumption or the
installed database checks. Invalid probes must leave the caller root rolled back.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, text

from app.core.identifiers import new_record_id
from app.modules.compensation.fulfillment.models import (
    CompensationFulfillmentException, CompensationFulfillmentReceipt, CompensationFulfillmentRoot,
)
from app.modules.compensation.models import ProjectCompensationAdapterBinding


async def native_source(owner, award_id):
    row = (await owner._session.execute(select(
        CompensationFulfillmentRoot, ProjectCompensationAdapterBinding.adapter_actor_id,
    ).join(ProjectCompensationAdapterBinding,
        ProjectCompensationAdapterBinding.id == CompensationFulfillmentRoot.adapter_binding_id,
    ).where(CompensationFulfillmentRoot.award_id == award_id))).one()
    assert row[0].source_instance_id == owner._source
    return row


@asynccontextmanager
async def native_custody(owner, source):
    async with owner._lifecycle.hold_current() as (current, held):
        await held.require_source(current.generation, owner._source)
        yield source[0], source[1], current.generation


@asynccontextmanager
async def native_authority(owner, custody, value, digest, *, exception):
    root, actor, generation = custody
    facts = owner._facts(root, actor, value, digest, generation, exception=exception)
    async with owner._authorization.prepare(facts) as authority:
        decision = await authority.consume_new()
        assert await owner._session.scalar(text("SELECT count(*) FROM audit_events "
            "WHERE id=:id AND event_type='SensitiveAuthorizationAllowed'"),
            {"id": decision.authorization_decision_id}) == 1
        values = owner._row_source(root, decision, generation) | {
            "id": new_record_id(), "evidence_ordinal": 999,
            "received_at": datetime(2000, 1, 1, tzinfo=UTC),
        }
        if exception:
            original = await owner._session.scalar(select(CompensationFulfillmentReceipt).where(
                CompensationFulfillmentReceipt.fulfillment_root_id == root.id,
                CompensationFulfillmentReceipt.reported_status == "fulfilled",
            ))
            assert original is not None
            values.update(exception_event_id=UUID(value["exception_event_id"]),
                original_receipt_id=original.id,
                original_fulfillment_event_id=UUID(value["original_fulfillment_event_id"]),
                kind=value["kind"], exception_body=value, exception_digest=digest)
        else:
            values.update(external_event_id=UUID(value["external_event_id"]),
                reported_status=value["reported_status"], report_body=value, report_digest=digest)
        yield values


async def insert_native(owner, values, *, exception):
    table = (CompensationFulfillmentException if exception else CompensationFulfillmentReceipt).__table__
    return (await owner._session.execute(insert(table).values(**values).returning(
        table.c.id, table.c.evidence_ordinal, table.c.received_at,
    ))).one()
