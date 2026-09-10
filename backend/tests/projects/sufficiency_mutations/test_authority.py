"""Decision-shape and exact PREP composition proof, not AUTH evaluator proof."""

from uuid import UUID

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.authorization.runtime import AuthorizationDenialCode
from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.commands import invoke
from projects.sufficiency_mutations.fixtures import case as case


@pytest.mark.parametrize(
    "field,value",
    [
        ("matched_authority_kind", module.MatchedAuthorityKind.FIXED_SERVICE),
        ("matched_grant_id", None),
        ("matched_scope_project_id", UUID(int=99)),
    ],
)
async def test_human_authority_requires_matching_grant(case, field, value):
    setattr(case.decision, field, value)
    with pytest.raises(RuntimeError, match="lacked Project Manager authority"):
        case.service._prove_human(case.decision, rows.PROJECT)


async def test_prepare_forwards_exact_unsupported_denial(case):
    caller, resource = object(), object()
    action = module.ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
    failure = module.PreparedAuthorizationUnsupported(
        AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    )
    case.prepared.prepare.side_effect = failure
    denial = RuntimeError("authorization denied")
    case.prepared.deny_unsupported.side_effect = denial
    with pytest.raises(RuntimeError) as observed:
        await case.service._prepare(case.prepared, action, caller, rows.PROJECT, resource)
    assert observed.value is denial
    case.prepared.deny_unsupported.assert_awaited_once_with(action, caller, resource, failure)


@pytest.mark.parametrize(
    "command,action,target,suffix,body",
    [
        (
            "create",
            "project.guide_sufficiency_report.create",
            "report",
            "sufficiency-reports",
            {
                "source_snapshot_id": str(rows.SNAPSHOT),
                "status": "passed",
                "findings": [],
                "summary": "Assessment",
            },
        ),
        (
            "ack",
            "project.guide_sufficiency.warnings.acknowledge",
            "warning_acknowledgement",
            "sufficiency-reports/{report_id}/acknowledge-warnings",
            {"acknowledgement_note": "Understood"},
        ),
    ],
)
async def test_mutation_passes_exact_prepared_context(case, command, action, target, suffix, body):
    await invoke(case, command)
    reserve = case.replay.reserve.await_args.kwargs
    selected_action, caller, scope = case.prepared.prepare.await_args.args
    case.prepared.prepare.assert_awaited_once_with(selected_action, caller, scope)
    handle, consumed_action, consumed_caller, resource = case.prepared.consume.await_args.args
    report_id = case.replay.complete.await_args.kwargs["report_id"]
    replay_value = {
        "action_id": action,
        "route": "POST /api/v1/projects/{project_id}/guides/{guide_id}/" + suffix,
        "actor_profile_id": str(rows.ACTOR),
        "identity_link_id": str(rows.LINK),
        "idempotency_key": str(rows.KEY),
        "project_id": str(rows.PROJECT),
        "guide_id": str(rows.GUIDE),
        "report_id": str(rows.REPORT) if command == "ack" else None,
        "source_snapshot_id": str(rows.SNAPSHOT),
        "body": body,
        "execution_kind": "human",
        "setup_service_custody": None,
    }
    digest = canonical_json_hash(
        {"domain": "workstream.guide_sufficiency.idempotency.v1", **replay_value}
    )
    stale = rows.STALE_HASH
    assert selected_action.value == consumed_action.value == action
    assert handle is case.handle and consumed_caller is caller
    assert scope == module.PreparedAuthorityScope(
        kind=module.PreparedAuthorityScopeKind.PROJECT, project_id=rows.PROJECT
    )
    assert caller.idempotency_key == rows.KEY
    assert caller.request_value == {
        **replay_value,
        "report_id": report_id,
        "guide_version": "v1",
        "source_snapshot_hash": rows.SNAPSHOT_HASH,
        "operation_id": str(reserve["operation_id"]),
        "request_digest": digest,
        "target_kind": target,
        "setup_generation": 1,
        "stale_output_digest": stale,
        "material_digest": None,
    }
    assert resource.model_dump(mode="json") == {
        "resource_type": "project_guide_sufficiency_mutation",
        "resource_id": report_id or str(rows.SNAPSHOT),
        "operation_id": str(reserve["operation_id"]),
        "request_digest": digest,
        "scope_project_id": str(rows.PROJECT),
        "guide_id": str(rows.GUIDE),
        "guide_version": "v1",
        "source_snapshot_id": str(rows.SNAPSHOT),
        "source_snapshot_hash": rows.SNAPSHOT_HASH,
        "target_kind": target,
        "execution_kind": "human",
        "sufficiency_report_id": report_id,
        "setup_generation": 1,
        "stale_output_digest": stale,
        "material_digest": None,
        "setup_service_custody": None,
    }
