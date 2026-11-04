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
            target=GuideProposalTarget(**target_values()),
            pre_submit_attachments=(), post_submit_attachments=(),
            idempotency_key=uuid4(), **{field: value}
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


@pytest.mark.asyncio
async def test_correction_is_refused_for_a_manager_authored_proposal(monkeypatch):
    """Authored rules cannot absorb a correction reason; the manager must revise the guide."""
    from types import SimpleNamespace

    from app.api.deps.guide_proposal_http import proposal_http_error
    from app.modules.authorization.api.guide_proposal_review import PreparedGuideProposalOperation
    from app.modules.projects.api.guide_proposals import GuideProposalError
    from app.modules.projects.guide_compilation import proposal_correction
    from tests.projects.guide_compilation.helpers import manager_runtime_configuration

    target = GuideProposalTarget(**target_values())
    command = GuideProposalCorrection(
        target=target, idempotency_key=uuid4(), reason="Require a test report.")
    locked = SimpleNamespace(
        target=target,
        current=True,
        view=SimpleNamespace(
            attempt=SimpleNamespace(
                runtime_configuration=manager_runtime_configuration().model_dump(mode="json")
            )
        ),
    )

    class Repository:
        def __init__(self, _session):
            pass

        async def correction_for_actor_key(self, *_args):
            return None

    class Prepared(PreparedGuideProposalOperation):
        async def authorize_read(self, *_args):
            pytest.fail("authority used for a refused correction")

        async def consume_new(self, _facts):
            pytest.fail("authority consumed for a refused correction")

        async def validate_replay(self, *_args):
            pytest.fail("authority used for a refused correction")

    monkeypatch.setattr(proposal_correction, "GuideProposalRepository", Repository)
    actor = SimpleNamespace(actor_profile_id=uuid4())
    with pytest.raises(GuideProposalError, match="correction_unsupported") as caught:
        await proposal_correction.stage_proposal_correction(
            None, command, actor, None, Prepared(), locked=locked)
    response = proposal_http_error(caught.value)
    assert (response.status_code, response.detail) == (409, "correction_unsupported")
