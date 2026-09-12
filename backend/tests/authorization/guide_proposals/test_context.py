"""Closed proposal fields, resource identity and business commitment parity."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    ActionAvailability,
    ActionOwner,
    ActionId,
)
from app.modules.authorization.domain.guide_proposals import proposal_resource
from app.modules.authorization.catalogue import GUIDE_PROPOSAL_ACTION_IDS
from app.modules.authorization.runtime import authorization_resource_digest
from tests.projects.guide_compilation.proposals.contract_support import authority_case


@pytest.mark.parametrize("action", sorted(GUIDE_PROPOSAL_ACTION_IDS))
def test_exact_resource_and_digest(action):
    _, _, facts, _ = authority_case()
    facts = replace(facts, locator=replace(facts.locator, action_id=action.value))
    resource = proposal_resource(facts)
    assert authorization_resource_digest(resource) == facts.digest
    assert resource.scope_project_id == facts.locator.project_id
    assert resource.resource_id == (
        facts.artifact_policy_id
        if action is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE
        else facts.locator.compilation_id
        if action is ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ
        else facts.locator.operation_id
    )
    assert ACTION_BY_ID[action].availability is ActionAvailability.ACTIVE
    assert ACTION_BY_ID[action].owner is ActionOwner.AUTH_12F4


@pytest.mark.parametrize(
    "patch",
    [
        {"setup_generation": True},
        {"setup_generation": 0},
        {"setup_run_id": "bad"},
        {"target_digest": "bad"},
        {"request_digest": "bad"},
        {"output_digest": "bad"},
        {"current_approval_operation_id": uuid4()},
        {"current_approval_output_digest": "sha256:" + "a" * 64},
        {"artifact_policy_id": None},
    ],
)
def test_invalid_facts_reject(patch):
    _, _, facts, _ = authority_case()
    with pytest.raises((TypeError, ValueError)):
        proposal_resource(replace(facts, **patch))


def test_current_approval_pair_and_transport_replay_digest():
    _, _, facts, _ = authority_case()
    facts = replace(
        facts,
        current_approval_operation_id=uuid4(),
        current_approval_output_digest="sha256:" + "a" * 64,
    )
    original = proposal_resource(facts)
    replay = proposal_resource(replace(facts, locator=replace(facts.locator, request_id=uuid4())))
    assert authorization_resource_digest(original) == authorization_resource_digest(replay)
    changed = proposal_resource(replace(facts, request_digest="sha256:" + "c" * 64))
    assert authorization_resource_digest(original) != authorization_resource_digest(changed)


def test_database_uuid_values_keep_exact_identity():
    from asyncpg.pgproto.pgproto import UUID as DatabaseUUID

    _, _, facts, _ = authority_case()
    persisted = replace(
        facts,
        locator=replace(
            facts.locator, compilation_id=DatabaseUUID(str(facts.locator.compilation_id))
        ),
        finalization_id=DatabaseUUID(str(facts.finalization_id)),
    )
    assert proposal_resource(persisted).facts.digest == facts.digest


def test_superseded_manual_approval_shape_is_rejected_specifically():
    import json
    from pydantic import ValidationError
    from app.modules.authorization.runtime import (
        ProjectSubmissionArtifactPolicyMutationResourceContext,
    )
    from tests.test_authorization import _submission_policy_human_prepare_inputs

    command, _ = _submission_policy_human_prepare_inputs(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE, uuid4()
    )
    digest = "sha256:" + "a" * 64
    old = dict(command.request_value) | {
        "target_kind": "approve",
        "policy_status": "draft",
        "policy_digest": digest,
        "effective_output_digest": digest,
        "compiled_pre_submit_output_digest": digest,
        "compilation": {
            "compiler_version": "v1",
            "bundle_schema_version": "v1",
            "catalogue_id": "workstream.default",
            "catalogue_version": "v1",
            "catalogue_schema_version": "v1",
            "catalogue_manifest_sha256": digest,
            "ordered_entry_identities": ["archive.identity@v1"],
            "ordered_entry_configuration_hashes": [digest],
            "disabled_catalogue_entry_ids": [],
            "disabled_catalogue_config_digest": digest,
            "compiled_bundle_hash": digest,
            "effective_plan_hash": digest,
        },
    }
    with pytest.raises(ValidationError) as rejected:
        ProjectSubmissionArtifactPolicyMutationResourceContext.model_validate_json(json.dumps(old))
    assert any(
        e["loc"] == ("target_kind",) and e["type"] == "literal_error"
        for e in rejected.value.errors()
    )
    # Valid manual drafting still has one canonical resource.
    assert (
        ProjectSubmissionArtifactPolicyMutationResourceContext.model_validate_json(
            json.dumps(command.request_value)
        ).target_kind
        == "create"
    )
