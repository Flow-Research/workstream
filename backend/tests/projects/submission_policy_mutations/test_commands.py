"""Manual mutation orchestration; PostgreSQL atomicity remains separately tested."""

from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.projects import submission_policy_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.submission_policy_mutations import rows
from projects.submission_policy_mutations.fixtures import case as case, invoke, select_update


@pytest.mark.parametrize("command", ["create", "update"])
@pytest.mark.parametrize("system_scope", [False, True])
async def test_mutation_stages_exact_policy_provenance(case, command, system_scope):
    if command == "update":
        select_update(case)
    case.decision.matched_scope_project_id = None if system_scope else rows.PROJECT
    outcome = await invoke(case, command)
    policy = case.projects.add_submission_artifact_policy.await_args.args[0]
    assert not outcome.replayed
    assert policy.created_by_actor_profile_id == str(rows.ACTOR)
    assert policy.created_via_identity_link_id == str(rows.LINK)
    assert policy.created_by_admin_role_grant_id == rows.GRANT
    assert policy.created_by_service_identity is None
    assert policy.creation_scope_type == ("system" if system_scope else "project")
    assert policy.creation_scope_project_id == str(rows.PROJECT)
    assert policy.creation_action_id == f"project.submission_artifact_policy.{command}"
    assert policy.creation_decision_event_id == str(case.decision.decision_id)
    assert policy.source_material_refs == ["guide-source:item"]
    assert policy.supersedes_policy_id == (str(rows.POLICY) if command == "update" else None)
    completion = case.replay.complete.await_args.kwargs
    assert completion["response_json"] == outcome.response.model_dump(mode="json")
    assert completion["committed_policy_id"] == policy.id
    if command == "update":
        case.projects.supersede_draft_submission_artifact_policy.assert_awaited_once_with(
            str(rows.POLICY)
        )
        case.session.flush.assert_awaited_once_with()
    else:
        case.projects.supersede_draft_submission_artifact_policy.assert_not_awaited()
    case.session.commit.assert_not_awaited()
    case.session.rollback.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
async def test_mutation_binds_exact_prepared_facts(case, command):
    if command == "update":
        select_update(case)
    await invoke(case, command)
    action = module.ActionId(f"project.submission_artifact_policy.{command}")
    prefix = f"workstream:submission-policy:{{}}:{action.value}:{rows.ACTOR}:{rows.LINK}:"
    prefix += f"{rows.PROJECT}:{rows.POLICY if command == 'update' else 'create'}:{rows.KEY}"
    operation_id = uuid5(NAMESPACE_URL, prefix.format("operation"))
    committed_id = uuid5(NAMESPACE_URL, prefix.format("policy"))
    selected_id = rows.POLICY if command == "update" else committed_id
    version = "manual-v2" if command == "update" else "manual-v1"
    summary = "replacement" if command == "update" else "initial"
    prior_hash = case.predecessor.policy_hash if command == "update" else None
    body = {
        "source_snapshot_id": str(rows.SNAPSHOT),
        "policy_version": version,
        "expected_policy_hash": prior_hash,
        "policy_body": {**rows.predecessor().policy_body,
                        "maximum_archive_entries": None, "maximum_archive_size_bytes": None},
        "change_summary": summary,
    }
    path = "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies"
    route = f"PATCH {path}/{{policy_id}}" if command == "update" else f"POST {path}"
    digest = canonical_json_hash(
        {
            "domain": "workstream.submission_policy.manual.idempotency.v1",
            "action_id": action.value,
            "route": route,
            "actor_profile_id": str(rows.ACTOR),
            "identity_link_id": str(rows.LINK),
            "idempotency_key": str(rows.KEY),
            "project_id": str(rows.PROJECT),
            "guide_id": str(rows.GUIDE),
            "source_snapshot_id": str(rows.SNAPSHOT),
            "policy_id": str(selected_id),
            "successor_policy_id": str(committed_id) if command == "update" else None,
            "successor_policy_version": version,
            "body": body,
        }
    )
    expected = module.ProjectSubmissionArtifactPolicyMutationResourceContext(
        resource_type="project_submission_artifact_policy_mutation",
        resource_id=committed_id,
        operation_id=operation_id,
        request_digest=digest,
        scope_project_id=rows.PROJECT,
        guide_id=rows.GUIDE,
        guide_version="v1",
        source_snapshot_id=rows.SNAPSHOT,
        source_snapshot_hash=rows.SNAPSHOT_HASH,
        target_kind=command,
        execution_kind="human",
        policy_id=selected_id,
        policy_version="manual-v1",
        policy_generation=4,
        setup_generation=4,
        sufficiency_report_id=rows.REPORT,
        sufficiency_status="passed",
        policy_status="draft" if command == "update" else None,
        policy_digest=prior_hash,
        successor_policy_id=committed_id if command == "update" else None,
        successor_policy_version=version if command == "update" else None,
    )
    caller = module.PreparedAuthorizationInput(
        idempotency_key=rows.KEY, request_value=expected.model_dump(mode="json")
    )
    scope = module.PreparedAuthorityScope(
        kind=module.PreparedAuthorityScopeKind.PROJECT,
        project_id=rows.PROJECT,
    )
    case.prepared.prepare.assert_awaited_once_with(action, caller, scope)
    case.prepared.consume.assert_awaited_once_with(case.handle, action, caller, expected)


@pytest.mark.parametrize("command", ["create", "update"])
async def test_consume_failure_precedes_product_and_replay_effects(case, command):
    if command == "update":
        select_update(case)
    failure = RuntimeError("consume denied")

    async def deny(*_):
        case.projects.add_submission_artifact_policy.assert_not_awaited()
        case.projects.supersede_draft_submission_artifact_policy.assert_not_awaited()
        case.replay.reserve.assert_not_awaited()
        raise failure

    case.prepared.consume.side_effect = deny
    with pytest.raises(RuntimeError) as observed:
        await invoke(case, command)
    assert observed.value is failure
    case.prepared.consume.assert_awaited_once()
    case.projects.add_submission_artifact_policy.assert_not_awaited()
    case.projects.supersede_draft_submission_artifact_policy.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
async def test_changed_locked_lineage_denies_before_consume(case, command):
    if command == "update":
        select_update(case)
    initial = case.service._lineage.return_value
    case.service._lineage.side_effect = [initial, replace(initial, setup_generation=5)]
    with pytest.raises(module.SubmissionPolicyMutationConflict, match="lineage_stale"):
        await invoke(case, command)
    case.prepared.prepare.assert_awaited_once()
    case.prepared.consume.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.projects.add_submission_artifact_policy.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
@pytest.mark.parametrize("disposition", ["pending", "mismatch"])
async def test_unclaimed_replay_prevents_product_mutation(case, command, disposition):
    if command == "update":
        select_update(case)
    case.replay.reserve.return_value = (disposition, object())
    with pytest.raises(module.SubmissionPolicyMutationConflict, match=f"idempotency_{disposition}"):
        await invoke(case, command)
    case.projects.add_submission_artifact_policy.assert_not_awaited()
    case.projects.supersede_draft_submission_artifact_policy.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
