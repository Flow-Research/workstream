"""Bounded exact proposal inputs and canonical correction feedback."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.projects.api.compilation_identity import CompilationComponentHashes
from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval,
    GuideProposalCorrection,
    GuideProposalTarget,
)

HASH = "sha256:" + "a" * 64
POLICY_FIELDS = (
    "artifact_policy_id",
    "artifact_policy_hash",
    "artifact_projection_operation_id",
    "artifact_projection_output_digest",
)


def target_values():
    return dict(
        project_id=uuid4(),
        guide_id=uuid4(),
        compilation_id=uuid4(),
        guide_version="1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash=HASH,
        setup_run_id=uuid4(),
        setup_generation=1,
        finalization_id=uuid4(),
        finalization_facts_digest=HASH,
        result_hash=HASH,
        component_hashes={name: HASH for name in CompilationComponentHashes.model_fields},
        pre_catalogue_id="pre",
        pre_catalogue_version="1",
        pre_catalogue_schema_version="1",
        pre_catalogue_manifest_hash=HASH,
        post_catalogue_id="post",
        post_catalogue_version="1",
        post_catalogue_schema_version="1",
        post_catalogue_manifest_hash=HASH,
        artifact_policy_id=uuid4(),
        artifact_policy_hash=HASH,
        artifact_projection_operation_id=uuid4(),
        artifact_projection_output_digest=HASH,
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
