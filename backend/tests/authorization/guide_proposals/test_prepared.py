"""Real shared PREP guards; storage-independent identity/evidence fixtures."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.actors.api import ServiceIdentity

from app.modules.authorization.api import AuthorizationDenied, PreparedAuthorizationInvalid
from app.modules.authorization.catalogue import ActionId, GUIDE_PROPOSAL_ACTION_IDS
from app.modules.authorization.api.guide_proposal_review import GuideProposalAuthorityReceipt
from .support import Case


@pytest.mark.parametrize("action", sorted(GUIDE_PROPOSAL_ACTION_IDS))
async def test_current_pm_exact_resource_and_one_use(monkeypatch, action):
    case = Case(monkeypatch, action.value)
    async with case.prepare() as handle:
        receipt = await case.consume(handle)
        with pytest.raises(PreparedAuthorizationInvalid):
            await case.consume(handle)
    with pytest.raises(PreparedAuthorizationInvalid):
        await case.consume(handle)
    assert len(case.events) == 1
    assert case.events[0].after_facts == {
        "allowed": True,
        "resource_context_digest": case.facts.digest,
    }
    assert case.events[0].correlation_id == str(case.facts.locator.operation_id)
    assert case.last_filters["exact_project_scope"] is True
    assert {str(r) for r in case.last_filters["allowed_roles"]} == {"project_manager"}
    if action is ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ:
        assert receipt is None
    else:
        assert isinstance(receipt, GuideProposalAuthorityReceipt)
        assert receipt.admin_role_grant_id == case.grant.id
        assert receipt.resource_context_digest == case.facts.digest


@pytest.mark.parametrize("action", sorted(GUIDE_PROPOSAL_ACTION_IDS))
@pytest.mark.parametrize(
    "principal",
    [
        "operator",
        "audit_authority",
        "contributor",
        "revoked",
        "foreign",
        "system",
        "suspended",
        "link_revoked",
    ],
)
async def test_uncovered_principals_deny_before_disclosure(monkeypatch, action, principal):
    case = Case(monkeypatch, action.value)
    if principal == "revoked":
        case.grant.status = "revoked"
    elif principal == "foreign":
        case.grant.scope_project_id = str(uuid4())
    elif principal == "system":
        case.grant.scope_type = "system"
    elif principal == "suspended":
        case.actor_status = "suspended"
    elif principal == "link_revoked":
        case.link_status = "revoked"
    else:
        case.role = principal
    with pytest.raises(AuthorizationDenied):
        async with case.prepare():
            pytest.fail("uncovered authority prepared")
    assert case.events == []


@pytest.mark.parametrize(
    "field",
    [
        "project_id",
        "guide_id",
        "compilation_id",
        "actor_profile_id",
        "identity_link_id",
        "operation_id",
        "request_id",
    ],
)
async def test_locator_substitution_rejects_without_allow(monkeypatch, field):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        changed = replace(case.facts, locator=replace(case.facts.locator, **{field: uuid4()}))
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.consume_new(changed)
    assert case.events == []


@pytest.mark.parametrize(
    "action",
    ["project.submission_artifact_policy.approve", "project.guide_compilation.correction.request"],
)
async def test_replay_rechecks_authority_and_allows_new_transport(monkeypatch, action):
    case = Case(monkeypatch, action)
    async with case.prepare() as handle:
        receipt = await handle.consume_new(case.facts)
    new_request = uuid4()
    replay = replace(case.facts, locator=replace(case.facts.locator, request_id=new_request))
    context = case.context.model_copy(update={"request_id": new_request})
    async with case.prepare(facts=replay, context=context) as handle:
        await handle.validate_replay(replay, receipt.authorization_decision_event_id)
    assert len(case.events) == 1
    case.grant.status = "revoked"
    with pytest.raises(AuthorizationDenied):
        async with case.prepare(facts=replay, context=context):
            pytest.fail("revoked replay prepared")


@pytest.mark.parametrize(
    "field",
    [
        "correlation_id",
        "actor_id",
        "project_id",
        "permission_id",
        "action_id",
        "resource_id",
        "target_ref_id",
        "request_id",
        "matched_grant_id",
        "after_facts",
    ],
)
async def test_retained_event_substitution_rejects(monkeypatch, field):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        receipt = await handle.consume_new(case.facts)
    setattr(case.events[0], field, {} if field == "after_facts" else "invalid")
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.validate_replay(case.facts, receipt.authorization_decision_event_id)
    assert len(case.events) == 1


@pytest.mark.parametrize(
    "fault", ["transaction", "nested", "foreign_issuer", "request", "actor", "link"]
)
async def test_request_session_and_issuer_custody(monkeypatch, fault):
    from types import SimpleNamespace

    case = Case(monkeypatch)
    if fault in {"request", "actor", "link"}:
        field = {"request": "request_id", "actor": "actor_profile_id", "link": "identity_link_id"}[
            fault
        ]
        with pytest.raises(AuthorizationDenied):
            async with case.prepare(context=case.context.model_copy(update={field: uuid4()})):
                pytest.fail("mismatched identity prepared")
    else:
        async with case.prepare() as handle:
            if fault == "transaction":
                case.session.root = SimpleNamespace(is_active=True)
            elif fault == "nested":
                case.session.in_nested_transaction = lambda: True
            else:
                async with case.prepare() as other:
                    handle._handle = other._handle
            with pytest.raises(PreparedAuthorizationInvalid):
                await handle.consume_new(case.facts)
    assert case.events == []


@pytest.mark.parametrize("action", sorted(GUIDE_PROPOSAL_ACTION_IDS))
async def test_direct_kernel_cannot_bypass_preparation(monkeypatch, action):
    from app.modules.authorization.domain.guide_proposals import proposal_resource
    from app.modules.authorization.runtime import AuthorizationDenied as KernelDenied
    from app.modules.authorization import guide_proposal_authorization as adapters

    case = Case(monkeypatch, action.value)
    kernel = adapters.AuthorizationService(case.session, case.context, admin_repository=case)
    with pytest.raises(KernelDenied):
        await kernel.require(action, proposal_resource(case.facts))
    assert not any(e.after_facts.get("allowed") for e in case.events)




@pytest.mark.parametrize("identity", list(ServiceIdentity))
@pytest.mark.parametrize("action", sorted(GUIDE_PROPOSAL_ACTION_IDS))
async def test_each_service_is_denied(monkeypatch, action, identity):
    from app.modules.authorization.runtime import ServiceAuthorizationContext, ActorKind

    case = Case(monkeypatch, action.value)
    context = ServiceAuthorizationContext(
        **(
            case.context.model_dump()
            | {
                "actor_kind": ActorKind.SERVICE,
                "service_identity": identity,
            }
        )
    )
    with pytest.raises(AuthorizationDenied):
        async with case.prepare(context=context):
            pytest.fail("service prepared manager authority")
    assert case.events == []
