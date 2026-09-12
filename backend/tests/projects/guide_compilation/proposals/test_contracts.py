"""Bounded exact proposal inputs and canonical correction feedback."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval,
    GuideProposalCorrection,
    GuideProposalTarget,
)

from .contract_support import HASH, target_values

POLICY_FIELDS = (
    "artifact_policy_id",
    "artifact_policy_hash",
    "artifact_projection_operation_id",
    "artifact_projection_output_digest",
)


@pytest.mark.parametrize("field", POLICY_FIELDS)
def test_ready_target_rejects_each_independently_missing_policy_field(field):
    values = target_values()
    assert GuideProposalTarget(**values).artifact_policy_id is not None
    values[field] = None
    with pytest.raises(ValidationError, match="complete or absent"):
        GuideProposalTarget(**values)


@pytest.mark.parametrize("field", POLICY_FIELDS)
def test_blocked_target_rejects_each_independently_populated_policy_field(field):
    ready = target_values()
    values = ready | dict.fromkeys(POLICY_FIELDS)
    assert GuideProposalTarget(**values).artifact_policy_id is None
    values[field] = ready[field]
    with pytest.raises(ValidationError, match="complete or absent"):
        GuideProposalTarget(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_previous_approval_operation_id", uuid4()),
        ("expected_previous_approval_output_digest", HASH),
    ],
)
def test_replacement_requires_both_prior_identity_fields(field, value):
    with pytest.raises(ValidationError, match="complete or absent"):
        GuideProposalApproval(
            target=GuideProposalTarget(**target_values()), idempotency_key=uuid4(), **{field: value}
        )


@pytest.mark.parametrize("reason", ["", "   ", "bad\x00reason", "\ud800", "a" * 4001])
def test_correction_rejects_empty_unsafe_or_oversized_feedback(reason):
    with pytest.raises(ValidationError):
        GuideProposalCorrection(
            target=GuideProposalTarget(**target_values()), idempotency_key=uuid4(), reason=reason
        )


def test_correction_normalizes_unicode_and_whitespace_without_changing_meaning():
    command = GuideProposalCorrection(
        target=GuideProposalTarget(**target_values()),
        idempotency_key=uuid4(),
        reason="  Cafe\u0301\ncheck\tpages  ",
    )
    assert command.reason == "Café\ncheck\tpages"


async def test_default_authority_denies_before_any_product_read():
    from types import SimpleNamespace
    from app.modules.authorization.api import ActorIdentityFacts, ActorKind
    from app.modules.projects.api.guide_proposals import GuideProposalError, GuideProposalSelection
    from app.modules.projects.guide_compilation.proposal_service import GuideProposalService

    session = SimpleNamespace(
        in_transaction=lambda: True,
        in_nested_transaction=lambda: False,
        new=(),
        dirty=(),
        deleted=(),
    )
    actor = ActorIdentityFacts(uuid4(), uuid4(), ActorKind.HUMAN)
    with pytest.raises(GuideProposalError, match="authority_unavailable"):
        await GuideProposalService(session).review_package(
            GuideProposalSelection(
                project_id=uuid4(),
                guide_id=uuid4(),
                compilation_id=uuid4(),
            ),
            actor=actor,
            request_id=uuid4(),
        )
