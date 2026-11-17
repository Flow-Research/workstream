"""Outbound root construction matches the independently pinned wire vectors."""

from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError
import pytest

from app.core.config import Settings
from app.core.financial_wire import canonical_utc_timestamp
from app.core.identifiers import new_record_id
from app.modules.compensation.api import (
    AwardContributionFacts, AwardDefinitionFacts, CompleteAwardSetRequest,
    CompensationAwardFacts, CompensationInstrumentType,
)
from app.modules.compensation.api.fulfillment import fulfillment_obligation


@pytest.mark.parametrize("instrument", ["money", "points"])
def test_obligation_builder_matches_independent_pinned_contract(instrument):
    path = (Path(__file__).resolve().parents[2] / "app/modules/finance/contracts/fixtures"
            / f"obligation-{instrument}.json")
    expected = json.loads(path.read_text())
    contribution = AwardContributionFacts(
        id=UUID(expected["contribution_record_id"]), project_id=UUID(expected["project_id"]),
        contributor_id=UUID(expected["contributor_id"]),
        contribution_policy_version_id=UUID(expected["contribution_policy_version_id"]),
        contribution_type="accepted_submission", task_id=UUID(expected["task_id"]),
        submission_id=UUID(expected["submission_id"]),
        final_acceptance_id=UUID(expected["final_acceptance_id"]), task_size=expected["task_size"],
    )
    definition = AwardDefinitionFacts(
        id=UUID(expected["award_definition_id"]), project_id=contribution.project_id,
        contribution_policy_version_id=contribution.contribution_policy_version_id,
        contribution_type="accepted_submission",
        instrument_type=CompensationInstrumentType(expected["instrument_type"]),
        unit_code=expected["unit_code"], quantity=Decimal(expected["quantity"]),
        adapter_binding_id=UUID(expected["adapter_binding_id"]),
    )
    award = CompensationAwardFacts(
        id=UUID(expected["award_id"]), project_id=contribution.project_id,
        contribution_record_id=contribution.id, contributor_id=contribution.contributor_id,
        contribution_policy_version_id=contribution.contribution_policy_version_id,
        award_definition_id=definition.id, adapter_binding_id=definition.adapter_binding_id,
        instrument_type=definition.instrument_type, unit_code=definition.unit_code,
        quantity=definition.quantity, created_at=canonical_utc_timestamp(expected["awarded_at"]),
        correlation_id=UUID(expected["correlation_id"]),
    )
    request = CompleteAwardSetRequest(
        disposition="new", compensation_mode="compensated", contribution=contribution,
        definitions=(definition,), correlation_id=award.correlation_id, expected_generation=2,
        source_authorization_decision_id=new_record_id(), source_routing_manifest_id=new_record_id(),
    )
    assert fulfillment_obligation(
        request, award, source_instance_id=UUID(expected["source_instance_id"]),
        root_id=UUID(expected["fulfillment_root_id"]), route_key=expected["route_key"],
    ) == expected


@pytest.mark.parametrize("value", [str(uuid4()), " 019a78b0-0000-7000-8000-000000000040", True,
                                  "019A78B0-0000-7000-8000-000000000040"])
def test_source_configuration_rejects_noncanonical_or_non_v7_identity(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, source_instance_id=value)


def test_missing_source_configuration_does_not_mint_an_identity():
    assert Settings(_env_file=None, source_instance_id=None).source_instance_id is None
