"""Public command failure boundaries require no database or authority fixture."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentEvidenceInvalid, FulfillmentEvidenceUnavailable,
)
from app.modules.compensation.fulfillment.evidence_service import FulfillmentEvidenceService
from tests.finance.test_fulfillment_contracts import encode, fixture


@pytest.mark.parametrize("family", ("report", "exception"))
@pytest.mark.parametrize("boundary", ("path", "event", "transaction"))
async def test_command_refuses_substituted_identity_or_missing_transaction_before_authority(family, boundary):
    is_exception = family == "exception"
    value = fixture("exception-after-fulfillment.json" if is_exception else "report-money-fulfilled.json")
    award_id = UUID(value["award_id"])
    event_id = UUID(value["exception_event_id" if is_exception else "external_event_id"])
    if boundary == "path":
        award_id = new_record_id()
    elif boundary == "event":
        event_id = new_record_id()
    async with AsyncSession() as session:
        # No engine and no usable ports: any locator or authority call would fail.
        service = FulfillmentEvidenceService(session, source_instance_id=new_record_id(),
            actor_profile_id=new_record_id(), identity_link_id=new_record_id(),
            authorization=object(), lifecycle=object())
        expected = FulfillmentEvidenceUnavailable if boundary == "transaction" else FulfillmentEvidenceInvalid
        with pytest.raises(expected):
            await getattr(service, family)(award_id, event_id, encode(value))
        assert not session.in_transaction()


@pytest.mark.parametrize("operation", ("source_evidence", "lookup"))
async def test_read_requires_root_transaction_before_locator_or_authority(operation):
    async with AsyncSession() as session:
        service = FulfillmentEvidenceService(session, source_instance_id=new_record_id(),
            actor_profile_id=new_record_id(), identity_link_id=new_record_id(),
            authorization=object(), lifecycle=object())
        args = (new_record_id(),) if operation == "source_evidence" else (new_record_id(), new_record_id())
        with pytest.raises(FulfillmentEvidenceUnavailable, match="requires_read_committed"):
            await getattr(service, operation)(*args)
        assert not session.in_transaction()
