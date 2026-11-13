"""Closed inputs and deny-before-work validation, without database claims."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.compensation.api import (
    AwardContributionFacts,
    AwardDefinitionFacts,
    CompleteAwardSetRequest,
    CompensationInstrumentType,
)
from app.modules.contributions.api import (
    ContributionParticipationUnavailable,
    SubmitterParticipationRequest,
)
from app.modules.contributions.records.participant import SubmitterContributionParticipant


def request():
    return SubmitterParticipationRequest(
        acceptance_disposition="new",
        project_id=new_record_id(),
        task_id=new_record_id(),
        submission_id=new_record_id(),
        final_acceptance_id=new_record_id(),
        task_assignment_id=new_record_id(),
        contributor_id=new_record_id(),
        contribution_policy_version_id=new_record_id(),
        task_size="small", contribution_award_definition_id=None,
        artifact_hash="sha256:" + "a" * 64,
        correlation_id=new_record_id(),
        expected_generation=0,
        source_authorization_decision_id=new_record_id(),
        source_routing_manifest_id=new_record_id(),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"acceptance_disposition": "repair"},
        {"task_size": None},
        {"task_size": "Medium"},
        {"contribution_award_definition_id": str(new_record_id())},
        {"project_id": "01900000-0000-7000-8000-000000000001"},
        {"expected_generation": True},
        {"expected_generation": -1},
        {"artifact_hash": "unverified"},
        {"source_review_id": new_record_id()},
    ],
)
async def test_invalid_constructed_input_rejects_before_fence_or_owner_work(change):
    original = request()
    with pytest.raises(ValidationError):
        SubmitterParticipationRequest(**(original.model_dump() | change))
    forged = original.model_copy(update=change)
    session, fence, awards = AsyncMock(), AsyncMock(), AsyncMock()
    participant = SubmitterContributionParticipant(session, fence=fence, awards=awards)
    with pytest.raises(ContributionParticipationUnavailable):
        await participant.participate_submitter(forged)
    assert session.mock_calls == []
    assert fence.mock_calls == []
    assert awards.mock_calls == []


def test_acceptance_disposition_is_required_without_a_compatibility_default():
    values = request().model_dump()
    values.pop("acceptance_disposition")
    with pytest.raises(ValidationError):
        SubmitterParticipationRequest(**values)


def award_request():
    contribution = AwardContributionFacts(
        id=new_record_id(),
        project_id=new_record_id(),
        contributor_id=new_record_id(),
        contribution_policy_version_id=new_record_id(),
        contribution_type="accepted_submission",
        task_id=new_record_id(), submission_id=new_record_id(),
        final_acceptance_id=new_record_id(), task_size="small",
    )
    definition = AwardDefinitionFacts(
        id=new_record_id(),
        project_id=contribution.project_id,
        contribution_policy_version_id=contribution.contribution_policy_version_id,
        contribution_type="accepted_submission",
        instrument_type=CompensationInstrumentType.MONEY,
        unit_code="USD",
        quantity=Decimal("2.125000000000000001"),
        adapter_binding_id=new_record_id(),
    )
    return CompleteAwardSetRequest(
        disposition="new",
        compensation_mode="compensated",
        contribution=contribution,
        definitions=(definition,),
        correlation_id=new_record_id(),
        expected_generation=2,
        source_authorization_decision_id=new_record_id(), source_routing_manifest_id=new_record_id(),
    )


def test_award_contract_rejects_incomplete_duplicate_and_foreign_definitions():
    valid = award_request()
    assert valid.definitions[0].quantity == Decimal("2.125000000000000001")
    changes = [
        {"definitions": ()},
        {"compensation_mode": "unpaid"},
        {"definitions": valid.definitions * 2},
    ]
    for field in ("project_id", "contribution_policy_version_id"):
        changes.append(
            {"definitions": (valid.definitions[0].model_copy(update={field: new_record_id()}),)}
        )
    for change in changes:
        with pytest.raises(ValidationError):
            CompleteAwardSetRequest.model_validate(valid.model_copy(update=change))
    unpaid = CompleteAwardSetRequest.model_validate(
        valid.model_copy(
            update={"compensation_mode": "unpaid", "definitions": ()},
        )
    )
    assert unpaid.definitions == ()
    with pytest.raises(ValidationError):
        AwardDefinitionFacts.model_validate(
            valid.definitions[0].model_copy(
                update={"quantity": 2.125},
            )
        )
