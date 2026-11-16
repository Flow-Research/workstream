"""Fulfillment AUTH binds disjoint resources and the actual reporting principal."""

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.audit_targets import project_authority_audit_target
from app.modules.authorization.domain.fulfillment_evidence import (
    fulfillment_evidence_action_matches, fulfillment_evidence_resource,
    fulfillment_evidence_resource_digest, parse_fulfillment_evidence_binding,
)
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentExceptionAuthorityFacts, FulfillmentReportAuthorityFacts,
    FulfillmentReportLookupAuthorityFacts, FulfillmentSourceReadAuthorityFacts,
)


def _source():
    actor = new_record_id()
    return dict(
        source_instance_id=new_record_id(), fulfillment_root_id=new_record_id(),
        award_id=new_record_id(), project_id=new_record_id(), adapter_binding_id=new_record_id(),
        binding_actor_id=actor, reporter_actor_id=actor, reporter_identity_link_id=new_record_id(),
        source_award_digest="sha256:" + "a" * 64, obligation_digest="sha256:" + "b" * 64,
        admission_generation=1,
    )


def _resources():
    source = _source()
    event = new_record_id()
    return (
        (ActionId.COMPENSATION_FULFILLMENT_REPORT, FulfillmentReportAuthorityFacts(
            **source, external_event_id=event, report_digest="sha256:" + "c" * 64,
            recording_lifecycle_generation=2,
        )),
        (ActionId.COMPENSATION_FULFILLMENT_EXCEPTION_REPORT, FulfillmentExceptionAuthorityFacts(
            **source, exception_event_id=new_record_id(), original_fulfillment_event_id=event,
            exception_digest="sha256:" + "d" * 64, recording_lifecycle_generation=3,
        )),
        (ActionId.COMPENSATION_FULFILLMENT_SOURCE_READ, FulfillmentSourceReadAuthorityFacts(
            **source, observed_lifecycle_generation=3,
        )),
        (ActionId.COMPENSATION_FULFILLMENT_SOURCE_READ, FulfillmentReportLookupAuthorityFacts(
            **source, external_event_id=source["award_id"], observed_lifecycle_generation=3,
        )),
    )


@pytest.mark.parametrize("action,facts", _resources())
def test_fulfillment_authority_requires_exact_action_source_and_principal(action, facts):
    resource = fulfillment_evidence_resource(facts)
    assert parse_fulfillment_evidence_binding(action, resource.model_dump(mode="json"), ValueError) == resource
    assert authorization_resource_digest(resource) == fulfillment_evidence_resource_digest(resource)
    assert project_authority_audit_target(resource, action) == (
        str(facts.project_id), resource.resource_type, str(resource.resource_id),
        "project", str(facts.project_id),
    )
    assert fulfillment_evidence_action_matches(
        action, resource, facts.project_id, facts.reporter_actor_id, facts.reporter_identity_link_id,
    )
    for project, actor, link in (
        (new_record_id(), facts.reporter_actor_id, facts.reporter_identity_link_id),
        (facts.project_id, new_record_id(), facts.reporter_identity_link_id),
        (facts.project_id, facts.reporter_actor_id, new_record_id()),
    ):
        assert not fulfillment_evidence_action_matches(action, resource, project, actor, link)
    for other in (
        ActionId.COMPENSATION_FULFILLMENT_REPORT,
        ActionId.COMPENSATION_FULFILLMENT_EXCEPTION_REPORT,
        ActionId.COMPENSATION_FULFILLMENT_SOURCE_READ,
    ):
        if other is not action:
            with pytest.raises(ValueError, match="invalid fulfillment evidence authority"):
                parse_fulfillment_evidence_binding(other, resource.model_dump(mode="json"), ValueError)
    with pytest.raises(ValueError, match="invalid fulfillment evidence authority"):
        parse_fulfillment_evidence_binding(action, resource.model_dump(mode="json") | {"extra": True}, ValueError)
    with pytest.raises(ValidationError):
        type(resource).model_validate(resource.model_dump() | {"resource_id": new_record_id()})


def test_source_and_lookup_equal_target_ids_never_share_authority():
    resources = [fulfillment_evidence_resource(facts) for _, facts in _resources()]
    source, lookup = resources[2:]
    assert source.resource_id == lookup.resource_id
    assert authorization_resource_digest(source) != authorization_resource_digest(lookup)
    original = resources[0]
    for field in ("reporter_actor_id", "binding_actor_id", "adapter_binding_id", "source_instance_id"):
        changed = original.facts.model_dump() | {field: new_record_id()}
        substituted = fulfillment_evidence_resource(type(original.facts).model_validate(changed))
        assert authorization_resource_digest(original) != authorization_resource_digest(substituted)


@pytest.mark.asyncio
@pytest.mark.parametrize("action,facts", _resources()[:2])
async def test_replay_checks_original_allow_without_creating_replacement_authority(action, facts):
    """Retained evidence must match the authority selectors and exact source digest."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.modules.actors.api import ServiceIdentity
    from app.modules.authorization.catalogue import ACTION_BY_ID
    from app.modules.authorization.prepared_fulfillment_replay import validate_fulfillment_replay
    from app.modules.authorization.runtime import (
        ActorKind, ActorStatus, IdentityLinkStatus, PreparedAuthorizationHandleInvalid,
        ServiceAuthorizationContext,
    )

    resource = fulfillment_evidence_resource(facts)
    context = ServiceAuthorizationContext(
        actor_kind=ActorKind.SERVICE, actor_status=ActorStatus.ACTIVE,
        actor_profile_id=facts.reporter_actor_id, identity_link_id=facts.reporter_identity_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE, service_identity=ServiceIdentity.COMPENSATION_ADAPTER,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )
    decision_id = new_record_id()
    expected = dict(
        id=str(decision_id), event_domain="authority", event_type="SensitiveAuthorizationAllowed",
        actor_ref_kind="actor_profile", actor_id=str(context.actor_profile_id), action_id=action.value,
        permission_id=ACTION_BY_ID[action].permission_id.value, project_id=str(facts.project_id),
        resource_type=resource.resource_type, resource_id=str(resource.resource_id),
        target_ref_kind="project", target_ref_id=str(facts.project_id), denial_code=None,
        matched_grant_id=None, idempotency_reference=None,
        after_facts={"allowed": True, "resource_context_digest": authorization_resource_digest(resource)},
    )
    read = AsyncMock(return_value=SimpleNamespace(**expected))
    owner = SimpleNamespace(
        _validate_consumption=Mock(),
        _authorization=SimpleNamespace(_audit=SimpleNamespace(get_authority_event=read)),
    )
    issuance = SimpleNamespace(authority=SimpleNamespace(
        context=context, action_id=action, scope_project_id=facts.project_id,
    ))
    caller_input = object()
    await validate_fulfillment_replay(owner, issuance, action, caller_input, resource, decision_id)
    owner._validate_consumption.assert_called_once_with(issuance, action, caller_input, resource)
    read.assert_awaited_once_with(decision_id)
    for field, changed in (
        ("actor_id", str(new_record_id())), ("action_id", ActionId.COMPENSATION_FULFILLMENT_SOURCE_READ.value),
        ("resource_type", "compensation_fulfillment_report_lookup"),
        ("project_id", str(new_record_id())), ("event_type", "SensitiveAuthorizationDenied"),
        ("after_facts", {"allowed": True, "resource_context_digest": "sha256:" + "0" * 64}),
    ):
        read.return_value = SimpleNamespace(**(expected | {field: changed}))
        with pytest.raises(PreparedAuthorizationHandleInvalid, match="invalid retained fulfillment receipt"):
            await validate_fulfillment_replay(owner, issuance, action, caller_input, resource, decision_id)
    read.return_value = None
    with pytest.raises(PreparedAuthorizationHandleInvalid, match="invalid retained fulfillment receipt"):
        await validate_fulfillment_replay(owner, issuance, action, caller_input, resource, decision_id)

    read.reset_mock()
    owner._validate_consumption.side_effect = PreparedAuthorizationHandleInvalid("invalid root custody")
    with pytest.raises(PreparedAuthorizationHandleInvalid, match="invalid root custody"):
        await validate_fulfillment_replay(owner, issuance, action, caller_input, resource, decision_id)
    read.assert_not_awaited()
