"""Contract tests for deterministic unified-compilation projections."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
)
from app.modules.authorization.api import (
    ArtifactPolicyProjectionFacts,
    GuideSufficiencyProjectionFacts,
    ProjectGuideProjectionAuthorityReceipt,
    ProjectGuideProjectionIdentity,
    ProjectGuideProjectionLocator,
    artifact_policy_projection_facts_digest,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_facts_digest,
    guide_sufficiency_projection_identity,
    projection_authority_digest,
)
from app.modules.projects.api import (
    ProjectGuideProjectionCommand,
    ProjectGuideProjectionReceipt,
)
from app.modules.projects.guide_compilation.projections import (
    _policy_body,
    _policy_digest,
    _report_digest,
    _report_payload,
)
from app.modules.projects.service import PolicySetupBlocked

from .helpers import SHA256, result


def _common_facts() -> dict:
    return {
        "project_id": uuid4(),
        "attempt_id": uuid4(),
        "request_operation_id": uuid4(),
        "provider_idempotency_key": uuid4(),
        "compilation_id": uuid4(),
        "guide_id": uuid4(),
        "guide_version": "v1",
        "source_snapshot_id": uuid4(),
        "source_snapshot_hash": SHA256,
        "setup_run_id": uuid4(),
        "setup_generation": 1,
        "celery_task_id": uuid4(),
        "source_state_digest": SHA256,
        "result_hash": SHA256,
        "component_hash": SHA256,
        "result_schema_version": "project_guide_compilation_result.v1",
        "compilation_agent_name": "ProjectGuideCompilationAgent",
        "compilation_agent_version": "v1",
    }


def test_public_projection_contracts_are_closed_and_hash_bound() -> None:
    """Reject extra input and malformed receipt digests."""
    attempt_id = uuid4()
    assert ProjectGuideProjectionCommand(attempt_id=attempt_id).attempt_id == attempt_id
    with pytest.raises(ValidationError):
        ProjectGuideProjectionCommand(attempt_id=attempt_id, component="other")
    with pytest.raises(ValidationError):
        ProjectGuideProjectionReceipt(
            operation_id=uuid4(),
            attempt_id=attempt_id,
            component="guide_sufficiency",
            output_id=uuid4(),
            output_digest="not-a-digest",
            disposition="projected",
        )


def test_projection_identities_and_digests_are_component_specific() -> None:
    """Keep operation, output, facts, and authority domains disjoint."""
    attempt_id, actor_id, link_id = uuid4(), uuid4(), uuid4()
    sufficiency_identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id,
        actor_profile_id=actor_id,
        identity_link_id=link_id,
    )
    policy_identity = artifact_policy_projection_identity(
        attempt_id=attempt_id,
        actor_profile_id=actor_id,
        identity_link_id=link_id,
    )
    assert len(
        {
            sufficiency_identity.operation_id,
            sufficiency_identity.correlation_id,
            sufficiency_identity.output_id,
            policy_identity.operation_id,
            policy_identity.correlation_id,
            policy_identity.output_id,
        }
    ) == 6

    common = _common_facts() | {"attempt_id": attempt_id}
    sufficiency = GuideSufficiencyProjectionFacts(
        **common,
        material_sha256=SHA256,
        material_byte_count=123,
        report_id=sufficiency_identity.output_id,
        report_content_digest=SHA256,
    )
    policy = ArtifactPolicyProjectionFacts(
        **common,
        prior_operation_id=sufficiency_identity.operation_id,
        sufficiency_report_id=sufficiency_identity.output_id,
        sufficiency_report_digest=SHA256,
        policy_id=policy_identity.output_id,
        policy_content_digest=SHA256,
    )
    sufficiency_digest = guide_sufficiency_projection_facts_digest(sufficiency)
    policy_digest = artifact_policy_projection_facts_digest(policy)
    assert sufficiency_digest != policy_digest
    assert projection_authority_digest(
        component="guide_sufficiency",
        identity=sufficiency_identity,
        project_id=cast(UUID, common["project_id"]),
        facts_digest=sufficiency_digest,
    ) != projection_authority_digest(
        component="submission_artifact_policy",
        identity=policy_identity,
        project_id=cast(UUID, common["project_id"]),
        facts_digest=policy_digest,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("setup_generation", 0),
        ("material_byte_count", -1),
        ("source_snapshot_hash", "not-a-digest"),
        ("attempt_id", "not-a-uuid"),
        ("guide_version", 1),
    ],
)
def test_projection_facts_reject_wrong_scalar_types(
    field: str, value: object
) -> None:
    """Reject malformed counters, digests, identifiers, and text facts."""
    facts = _common_facts() | {
        "material_sha256": SHA256,
        "material_byte_count": 123,
        "report_id": uuid4(),
        "report_content_digest": SHA256,
        field: value,
    }
    with pytest.raises(ValueError):
        GuideSufficiencyProjectionFacts(**facts)


def test_projection_locator_identity_and_receipt_fail_closed() -> None:
    """Keep caller, service identity, and evidence receipts nominal and exact."""
    attempt_id, actor_id, link_id = uuid4(), uuid4(), uuid4()
    with pytest.raises(ValueError):
        ProjectGuideProjectionLocator(
            project_id=cast(UUID, "bad"), attempt_id=attempt_id
        )
    identity_values = {
        "operation_id": uuid4(),
        "correlation_id": uuid4(),
        "output_id": uuid4(),
        "actor_profile_id": actor_id,
        "identity_link_id": link_id,
    }
    with pytest.raises(ValueError):
        ProjectGuideProjectionIdentity(
            **identity_values | {"actor_profile_id": cast(UUID, "bad")}
        )
    with pytest.raises(ValueError):
        ProjectGuideProjectionIdentity(
            **identity_values, service_identity="other.service"
        )
    receipt = {
        "decision_event_id": uuid4(),
        "actor_profile_id": actor_id,
        "identity_link_id": link_id,
        "service_identity": "workstream.project.setup",
        "resource_context_digest": SHA256,
    }
    for field, value in (
        ("decision_event_id", "bad"),
        ("service_identity", "other.service"),
        ("resource_context_digest", "bad"),
    ):
        with pytest.raises(ValueError):
            ProjectGuideProjectionAuthorityReceipt(**(receipt | {field: value}))

    identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id,
        actor_profile_id=actor_id,
        identity_link_id=link_id,
    )
    with pytest.raises(ValueError, match="component is invalid"):
        projection_authority_digest(
            component=cast(str, "unknown"),
            identity=identity,
            project_id=uuid4(),
            facts_digest=SHA256,
        )


def test_report_and_policy_transforms_are_exact() -> None:
    """Project the v1 result without model calls or best-effort repair."""
    compiled = result()
    report = _report_payload(compiled, str(uuid4()))
    assert report.status == "passed"
    assert report.summary is None
    assert [finding.model_dump(mode="json") for finding in report.findings] == [
        {
            "severity": "info",
            "code": "guide.ready",
            "message": "Guide is complete.",
            "location": None,
        }
    ]
    policy = _policy_body(
        cast(AsyncSession, None), compiled.submission_artifact_policy
    )
    assert policy["required_artifacts"] == [
        {
            "key": "required-artifact-001",
            "path": "submission",
            "hash_required": True,
            "required": True,
            "description": None,
        }
    ]
    assert policy["packaging"] == {
        "package_required": True,
        "allowed_package_formats": ["zip"],
    }
    assert policy["allowed_storage_schemes"] == ["local", "r2", "s3"]


@pytest.mark.parametrize(
    "proposal",
    [
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_artifacts=("C:artifact",),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_evidence=("Not canonical",),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            attestation_terms=("x" * 101,),
        ),
    ],
)
def test_policy_projection_rejects_unprojectable_legacy_v1_values(
    proposal: SubmissionArtifactPolicyProposal,
) -> None:
    """Fail closed rather than truncating or rewriting persisted v1 text."""
    with pytest.raises((PolicySetupBlocked, ValueError)):
        _policy_body(cast(AsyncSession, None), proposal)


def test_blocked_result_maps_only_to_a_blocked_report() -> None:
    """Keep the policy component absent for a blocked compilation."""
    blocked = ProjectGuideCompilationResult.model_validate(
        result().model_dump(mode="json")
        | {"status": "guide_blocked", "submission_artifact_policy": None}
    )
    report = _report_payload(blocked, str(uuid4()))
    assert report.status == "blocked"
    assert blocked.submission_artifact_policy is None


def test_missing_replay_outputs_never_have_a_canonical_digest() -> None:
    """Ensure replay validation cannot treat a missing product row as intact."""
    assert _report_digest(None) is None
    assert _policy_digest(None) is None
