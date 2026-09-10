"""Authority-shape, replay-custody and transaction-owner delegation guards."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.modules.authorization.runtime import AuthorizationDenialCode
from app.modules.projects import submission_policy_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.submission_policy_mutations import rows
from projects.submission_policy_mutations.fixtures import case as case


@pytest.mark.parametrize(
    "field,value",
    [
        ("matched_authority_kind", module.MatchedAuthorityKind.FIXED_SERVICE),
        ("matched_grant_id", None),
        ("matched_scope_project_id", UUID(int=99)),
    ],
)
def test_human_authority_requires_covered_grant(case, field, value):
    setattr(case.decision, field, value)
    with pytest.raises(RuntimeError, match="lacked covered"):
        case.service._prove_human_authority(case.decision, rows.PROJECT)


async def test_unsupported_prepare_forwards_exact_denial(case):
    action = module.ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE
    caller, resource = object(), object()
    unsupported = module.PreparedAuthorizationUnsupported(
        AuthorizationDenialCode.ACTION_UNAVAILABLE
    )
    denial = RuntimeError("denied")
    case.prepared.prepare.side_effect = unsupported
    case.prepared.deny_unsupported.side_effect = denial
    with pytest.raises(RuntimeError) as observed:
        await case.service._prepare(case.prepared, action, caller, rows.PROJECT, resource)
    assert observed.value is denial
    case.prepared.deny_unsupported.assert_awaited_once_with(action, caller, resource, unsupported)


@pytest.mark.parametrize("operation", ["reserve", "complete"])
async def test_replay_delegates_exact_custody_without_transaction_ownership(case, operation):
    facts = rows.replay_facts()
    expected = {
        field: getattr(facts, field)
        for field in facts.__dataclass_fields__
        if field != "resource_context"
    }
    expected["resource_context_digest"] = module.authorization_resource_digest(
        facts.resource_context
    )
    expected["resource_context_json"] = facts.resource_context.model_dump(mode="json")
    if operation == "reserve":
        outcome = await case.service.reserve_replay(facts)
        assert outcome == case.replay.reserve.return_value
        case.replay.reserve.assert_awaited_once_with(**expected)
    else:
        for field in (
            "operation_id",
            "project_id",
            "guide_id",
            "source_snapshot_id",
            "policy_id",
            "resource_context_json",
        ):
            del expected[field]
        await case.service.complete_replay(
            facts, response_json={"id": str(rows.POLICY)}, committed_policy_id=str(rows.POLICY)
        )
        case.replay.complete.assert_awaited_once_with(
            rows.OPERATION,
            **expected,
            response_json={"id": str(rows.POLICY)},
            committed_policy_id=str(rows.POLICY),
            committed_effective_policy_id=None,
            committed_pre_submit_policy_id=None,
        )
    case.session.commit.assert_not_awaited()
    case.session.rollback.assert_not_awaited()


@pytest.mark.parametrize("state", ["missing", "inactive", "nested"])
async def test_replay_requires_active_root_transaction(case, state):
    if state == "missing":
        case.session.sync_session.get_transaction.return_value = None
    elif state == "inactive":
        case.session.sync_session.get_transaction.return_value.is_active = False
    else:
        case.session.in_nested_transaction.return_value = True
    with pytest.raises(RuntimeError, match="one root transaction"):
        await case.service.reserve_replay(rows.replay_facts())
    case.replay.reserve.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("action_id", "invalid", "invalid submission-policy replay action"),
        ("request_digest", "sha256:" + "c" * 64, "do not match resource context"),
        ("idempotency_key", None, "human replay custody is invalid"),
    ],
)
async def test_invalid_human_replay_facts_never_reach_repository(case, field, value, error):
    with pytest.raises(ValueError, match=error):
        await case.service.reserve_replay(replace(rows.replay_facts(), **{field: value}))
    case.replay.reserve.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value", [("execution_kind", "setup_service"), ("setup_service_custody", object())]
)
async def test_human_replay_rejects_nonhuman_resource_custody(case, field, value):
    facts = rows.replay_facts()
    resource = facts.resource_context.model_copy(update={field: value})
    with pytest.raises(ValueError, match="human replay custody is invalid"):
        await case.service.reserve_replay(replace(facts, resource_context=resource))
    case.replay.reserve.assert_not_awaited()
