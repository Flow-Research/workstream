"""Pure exact-value proofs for hidden post-submit routing preparation."""

from datetime import timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.domain.audit import (
    AuthorizationDecision,
    MatchedAuthorityKind,
)
from app.modules.authorization.domain.post_submit_routing import (
    AutomatedAcceptanceConsequence,
    CheckerRemediationConsequence,
    HumanAdmissionConsequence,
    PostSubmitRoutingResourceContext,
    parse_post_submit_routing_prepare,
    post_submit_routing_prepare_matches,
    post_submit_routing_prepare_values,
    post_submit_routing_resource_digest,
)
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.authorization.runtime import PreparedAuthorizationInput
from app.modules.authorization.post_submit_routing_authorization import _PreparedRouting
from app.modules.authorization.prepared import FixedServicePreparedAuthorization
from app.modules.tasks.api.post_submit_routing import TaskRoutingRequestFacts
from app.adapters.tasks.routing_acceptance import _PreparedAdapter
from tests.tasks.post_submit_routing.contract_fixtures import SHA_A, SHA_B

from tests.authorization.post_submit_routing.support import (
    accepted_effects_for,
    changed_request,
    resource_for,
)


@pytest.mark.parametrize(
    ("human_review_required", "recommendation"),
    ((True, "allow_review"), (False, "allow_review"),
     (True, "needs_revision"), (False, "needs_revision")),
)
def test_valid_policy_branch_resources(human_review_required, recommendation):
    resource = resource_for(
        human_review_required=human_review_required,
        routing_recommendation=recommendation,
    )

    assert resource.source.human_review_required is human_review_required
    assert resource.resource_id == resource.request.routing_manifest_id == resource.source.id
    assert resource.scope_project_id == resource.request.project_id == resource.source.project_id
    assert resource.claim.event_id == resource.request.completion_event_id
    assert resource.validate_identity() is resource
    if recommendation == "needs_revision":
        assert resource.consequence == CheckerRemediationConsequence()
    elif human_review_required:
        assert resource.consequence == HumanAdmissionConsequence()
    else:
        assert isinstance(resource.consequence, AutomatedAcceptanceConsequence)
        assert resource.consequence.task_effects == accepted_effects_for(resource.source).model_copy(
            update={
                "final_acceptance_id": resource.consequence.task_effects.final_acceptance_id
            }
        )


@pytest.mark.parametrize("recovering", [False, True])
async def test_routing_adapter_serializes_only_present_recovery_provenance(recovering):
    """New recovery metadata must not drop retained null source facts."""
    from app.adapters.auth import _PreparedTaskRoutingAdapter
    from app.modules.tasks.api.post_submit_routing import TaskRoutingSourcePreparation

    resource = resource_for()
    child = resource.claim.model_copy(update={"event_id": new_record_id()}) if recovering else None
    captured = []
    replays = []
    decision_id = new_record_id()

    async def consume(value):
        captured.append(value)
        return SimpleNamespace(
            authorization_decision_event_id=decision_id,
            actor_profile_id=resource.router_actor_id,
            actor_identity_link_id=resource.router_identity_link_id,
        )

    async def validate_replay(value, *receipt_ids):
        replays.append((value, receipt_ids))

    adapter = _PreparedTaskRoutingAdapter(SimpleNamespace(
        actor_profile_id=resource.router_actor_id,
        identity_link_id=resource.router_identity_link_id,
        consume=consume,
        validate_replay=validate_replay,
    ))
    source = TaskRoutingSourcePreparation(source=resource.source, request=resource.request)
    retained = await adapter.consume(
        source,
        resource.claim, None, None, reconciliation_claim=child,
    )
    context = json.loads(retained.context_json)
    expected = resource.model_dump(mode="json", exclude={"reconciliation_claim"})
    if child is not None:
        expected["reconciliation_claim"] = child.model_dump(mode="json")
    assert context == expected
    assert "predecessor_submission_id" in context["source"]
    assert context["source"]["predecessor_submission_id"] is None
    assert "predecessor_submission_version" in context["source"]
    assert context["source"]["predecessor_submission_version"] is None
    assert captured[0].claim == resource.claim
    assert captured[0].reconciliation_claim == child
    await adapter.validate_replay(source, retained, None, None)
    assert replays == [(
        captured[0], (decision_id, resource.router_actor_id, resource.router_identity_link_id)
    )]


@pytest.mark.parametrize("field", ["project_id", "event_id"])
def test_reconciliation_claim_rejects_wrong_project_or_original_event(field):
    resource = resource_for()
    child = resource.claim.model_copy(update={"event_id": new_record_id()})
    valid = PostSubmitRoutingResourceContext(
        **(resource.model_dump() | {"reconciliation_claim": child})
    )
    assert valid.validate_identity() is valid
    changed = new_record_id() if field == "project_id" else resource.claim.event_id
    invalid = child.model_copy(update={field: changed})
    with pytest.raises(ValidationError, match="routing reconciliation claim differs"):
        PostSubmitRoutingResourceContext(
            **(resource.model_dump() | {"reconciliation_claim": invalid})
        )
    with pytest.raises(ValueError, match="routing reconciliation claim differs"):
        post_submit_routing_resource_digest(
            valid.model_copy(update={"reconciliation_claim": invalid})
        )


@pytest.mark.parametrize(
    "field", ["event_id", "payload_digest", "claim_generation", "claim_owner", "claimed_at", "claim_expires_at"],
)
def test_reconciliation_digest_binds_each_child_claim_fact(field):
    ordinary = resource_for()
    child = ordinary.claim.model_copy(update={"event_id": new_record_id()})
    resource = PostSubmitRoutingResourceContext(
        **(ordinary.model_dump() | {"reconciliation_claim": child})
    )
    digest = post_submit_routing_resource_digest(resource)
    assert digest != post_submit_routing_resource_digest(ordinary)
    value = getattr(child, field)
    changed = (
        new_record_id() if field == "event_id" else SHA_B if field == "payload_digest"
        else value + 1 if field == "claim_generation"
        else "different-child-owner" if field == "claim_owner"
        else value + timedelta(microseconds=1)
    )
    altered = PostSubmitRoutingResourceContext(**(
        resource.model_dump() | {"reconciliation_claim": child.model_copy(update={field: changed})}
    ))
    assert post_submit_routing_resource_digest(altered) != digest


@pytest.mark.parametrize("human", [True, False])
@pytest.mark.parametrize("recommendation", ["allow_review", "needs_revision"])
@pytest.mark.parametrize(("has_effects", "has_generation"), [(False, False), (True, False), (False, True), (True, True)])
def test_authorization_adapter_requires_exact_branch_inputs(human, recommendation, has_effects, has_generation):
    from app.adapters.auth import _routing_resource

    resource = resource_for(human_review_required=human, routing_recommendation=recommendation)
    from app.modules.tasks.api.post_submit_routing import TaskRoutingSourcePreparation
    source = TaskRoutingSourcePreparation(source=resource.source, request=resource.request)
    effects = accepted_effects_for(resource.source) if has_effects else None
    generation = 7 if has_generation else None
    arguments = (source, resource.claim, effects, generation, resource.router_actor_id, resource.router_identity_link_id)
    accepts = recommendation == "allow_review" and not human
    if has_effects != accepts or has_generation != accepts:
        with pytest.raises(PreparedAuthorizationHandleInvalid, match="routing consequence unavailable"):
            _routing_resource(*arguments)
    else:
        result = _routing_resource(*arguments)
        assert type(result.consequence) is type(resource.consequence)


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("project_id", new_record_id()),
        ("task_id", new_record_id()),
        ("submission_id", new_record_id()),
        ("submission_version", 2),
        ("checker_run_id", new_record_id()),
        ("evaluation_request_id", new_record_id()),
        ("evaluation_request_digest", SHA_B),
        ("evaluation_generation", 2),
        ("result_id", new_record_id()),
        ("result_digest", SHA_A),
        ("completion_event_id", new_record_id()),
    ),
)
def test_each_request_source_selector_rejects(field, changed):
    control = resource_for()
    assert control.validate_identity() is control
    mismatched = changed_request(control.request, **{field: changed})

    with pytest.raises(ValidationError, match="routing (resource identity|request source) differs"):
        PostSubmitRoutingResourceContext(
            **(control.model_dump() | {"request": mismatched})
        )

    with pytest.raises(ValidationError):
        TaskRoutingRequestFacts(
            **(
                control.request.model_dump()
                | {"routing_recommendation": "task_setup_blocked"}
            )
        )


@pytest.mark.parametrize(
    "field",
    (
        "resource_id",
        "scope_project_id",
        "request.routing_manifest_id",
        "source.id",
        "source.project_id",
        "source.completion_event_id",
        "claim.project_id",
        "claim.event_id",
    ),
)
def test_each_resource_and_claim_identity_rejects(field):
    control = resource_for()
    assert control.validate_identity() is control
    values = control.model_dump()
    if "." in field:
        parent, nested_field = field.split(".")
        values[parent][nested_field] = new_record_id()
    else:
        values[field] = new_record_id()
    with pytest.raises(ValidationError, match="routing resource identity differs"):
        PostSubmitRoutingResourceContext(**values)


def test_acceptance_identity_requires_uuid7():
    control = resource_for(human_review_required=False)
    assert control.validate_identity() is control
    assert control.consequence.task_effects.final_acceptance_id.version == 7
    values = control.model_dump()
    values["consequence"]["task_effects"]["final_acceptance_id"] = uuid4()
    with pytest.raises(ValidationError, match="routing acceptance requires UUIDv7 identity"):
        PostSubmitRoutingResourceContext(**values)


def test_exclusive_branch_consequences():
    human = resource_for(human_review_required=True)
    automated = resource_for(human_review_required=False)
    remediation = resource_for(routing_recommendation="needs_revision")
    assert human.validate_identity() is human
    assert automated.validate_identity() is automated
    assert remediation.validate_identity() is remediation

    with pytest.raises(ValidationError, match="routing consequence differs from review policy"):
        PostSubmitRoutingResourceContext(
            **(
                human.model_dump()
                | {
                    "consequence": AutomatedAcceptanceConsequence(
                        authorized_lifecycle_generation=2,
                        task_effects=accepted_effects_for(human.source),
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="routing consequence differs from review policy"):
        PostSubmitRoutingResourceContext(
            **(automated.model_dump() | {"consequence": HumanAdmissionConsequence()})
        )
    for consequence in (
        HumanAdmissionConsequence(),
        AutomatedAcceptanceConsequence(
            authorized_lifecycle_generation=2,
            task_effects=accepted_effects_for(remediation.source),
        ),
    ):
        with pytest.raises(
            ValidationError, match="routing consequence differs from recommendation"
        ):
            PostSubmitRoutingResourceContext(
                **(remediation.model_dump() | {"consequence": consequence})
            )


@pytest.mark.parametrize(
    "field",
    (
        "project_id",
        "task_id",
        "assignment_id",
        "submission_id",
        "submission_version",
        "contributor_id",
        "contribution_policy_version_id",
        "content_id",
        "content_sha256",
    ),
)
def test_each_consequence_identity_rejects(field):
    control = resource_for(human_review_required=False)
    consequence = control.consequence
    assert isinstance(consequence, AutomatedAcceptanceConsequence)
    value = getattr(consequence.task_effects, field)
    changed = value + 1 if type(value) is int else SHA_B if field == "content_sha256" else new_record_id()
    effects = consequence.task_effects.model_copy(update={field: changed})

    with pytest.raises(ValidationError, match="routing acceptance identity differs"):
        PostSubmitRoutingResourceContext(
            **(
                control.model_dump()
                | {
                    "consequence": AutomatedAcceptanceConsequence(
                        authorized_lifecycle_generation=2, task_effects=effects
                    )
                }
            )
        )

    with pytest.raises(ValidationError, match="routing acceptance source state differs"):
        PostSubmitRoutingResourceContext(
            **(
                control.model_dump()
                | {
                    "consequence": AutomatedAcceptanceConsequence(
                        authorized_lifecycle_generation=2,
                        task_effects=consequence.task_effects.model_copy(
                            update={"expected_task_status": "review_pending"}
                        ),
                    )
                }
            )
        )


def test_prepare_parse_and_match_exact_request():
    resource = resource_for()
    values = post_submit_routing_prepare_values(resource.request)
    assert set(values) == {"routing_request"}
    parsed = parse_post_submit_routing_prepare(
        ActionId.TASK_POST_SUBMIT_ROUTE, values, PreparedAuthorizationHandleInvalid
    )
    assert parsed == resource.request
    assert post_submit_routing_prepare_matches(parsed, resource)

    changed = changed_request(
        resource.request,
        created_at=resource.request.created_at + timedelta(microseconds=1),
    )
    changed_resource = PostSubmitRoutingResourceContext(
        **(resource.model_dump() | {"request": changed})
    )
    assert not post_submit_routing_prepare_matches(parsed, changed_resource)
    assert parse_post_submit_routing_prepare(
        ActionId.CHECKER_POST_SUBMIT_EXECUTE, values, PreparedAuthorizationHandleInvalid
    ) is None
    for invalid in ({}, values | {"extra": True}, {"routing_request": {}}):
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            parse_post_submit_routing_prepare(
                ActionId.TASK_POST_SUBMIT_ROUTE,
                invalid,
                PreparedAuthorizationHandleInvalid,
            )


@pytest.mark.parametrize(
    "claim_field",
    (
        "payload_digest",
        "claim_generation",
        "claim_owner",
        "claimed_at",
        "claim_expires_at",
    ),
)
def test_digest_binds_claim_and_source(claim_field):
    resource = resource_for()
    digest = post_submit_routing_resource_digest(resource)
    value = getattr(resource.claim, claim_field)
    changed = (
        SHA_B
        if claim_field == "payload_digest"
        else value + 1
        if claim_field == "claim_generation"
        else "workstream.task.post_submit_router:other"
        if claim_field == "claim_owner"
        else value + timedelta(microseconds=1)
    )
    other_claim = resource.claim.model_copy(update={claim_field: changed})
    changed_resource = PostSubmitRoutingResourceContext(
        **(resource.model_dump() | {"claim": other_claim})
    )
    assert post_submit_routing_resource_digest(changed_resource) != digest

    other_source = resource.source.model_copy(update={"replica_id": new_record_id()})
    changed_resource = PostSubmitRoutingResourceContext(
        **(resource.model_dump() | {"source": other_source})
    )
    assert post_submit_routing_resource_digest(changed_resource) != digest
    # AUTH consumes a pre-publication proposal; its digest cannot depend on
    # the database creation timestamp which does not exist yet.
    assert "created_at" not in type(resource.source).model_fields

    other_request = changed_request(
        resource.request, route_operation_id=new_record_id()
    )
    request_resource = PostSubmitRoutingResourceContext(
        **(resource.model_dump() | {"request": other_request})
    )
    assert post_submit_routing_resource_digest(request_resource) != digest


@pytest.mark.parametrize(
    "source_field",
    (
        "assignment_id",
        "contributor_id",
        "contribution_policy_version_id",
        "task_size",
        "contribution_award_definition_id",
        "execute_evidence_id",
        "finalize_evidence_id",
        "replica_id",
        "content_sha256",
        "byte_count",
        "semantic_manifest_sha256",
        "admission_id",
        "binding_id",
        "content_id",
        "locked_policy",
    ),
)
def test_digest_binds_all_source_semantics(source_field):
    resource = resource_for()
    original = post_submit_routing_resource_digest(resource)
    value = getattr(resource.source, source_field)
    if source_field == "locked_policy":
        changed = value.model_copy(update={"locked_review_policy_hash": SHA_B})
    elif source_field == "contribution_policy_version_id":
        changed = new_record_id()
    elif source_field == "content_sha256":
        changed = SHA_B
    elif source_field == "semantic_manifest_sha256":
        changed = SHA_A
    elif source_field == "task_size":
        changed = "medium" if value != "medium" else "large"
    elif source_field == "byte_count":
        changed = value + 1
    else:
        changed = new_record_id()
    updates = {source_field: changed}
    if source_field == "contribution_policy_version_id":
        updates["locked_policy"] = resource.source.locked_policy.model_copy(
            update={"locked_contribution_policy_version_id": changed}
        )
    source = resource.source.model_copy(update=updates)
    changed_resource = PostSubmitRoutingResourceContext(
        **(resource.model_dump() | {"source": source})
    )

    assert post_submit_routing_resource_digest(changed_resource) != original


def test_digest_binds_each_branch_consequence():
    human = resource_for(human_review_required=True)
    automated = resource_for(human_review_required=False)
    remediation = resource_for(routing_recommendation="needs_revision")
    original = post_submit_routing_resource_digest(automated)
    consequence = automated.consequence
    assert isinstance(consequence, AutomatedAcceptanceConsequence)
    changed = AutomatedAcceptanceConsequence(
        authorized_lifecycle_generation=2,
        task_effects=consequence.task_effects.model_copy(
            update={"final_acceptance_id": new_record_id()}
        ),
    )
    changed_resource = PostSubmitRoutingResourceContext(
        **(automated.model_dump() | {"consequence": changed})
    )

    assert post_submit_routing_resource_digest(human) != original
    assert post_submit_routing_resource_digest(remediation) != original
    assert post_submit_routing_resource_digest(changed_resource) != original


async def test_acceptance_adapter_rejects_remediation_source_before_delegation():
    class Prepared:
        async def participate(self, *_, **__):
            pytest.fail("remediation reached final acceptance")

    source = SimpleNamespace(
        source=SimpleNamespace(
            routing_recommendation="needs_revision",
            human_review_required=False,
        )
    )

    with pytest.raises(ValueError, match="false acceptance source unavailable"):
        await _PreparedAdapter(Prepared(), 1).participate(
            source, object(), object(), 1
        )


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("allowed", False),
        ("revalidated", False),
        ("denial_code", "action_unavailable"),
        ("matched_authority_kind", MatchedAuthorityKind.ACTOR_SELF),
        ("matched_grant_id", new_record_id()),
        ("matched_scope_project_id", new_record_id()),
        ("action_id", ActionId.CHECKER_POST_SUBMIT_EXECUTE),
        ("permission_id", PermissionId.CHECKER_POST_SUBMIT_EXECUTE),
        ("resource_type", "checker_run"),
        ("resource_id", new_record_id()),
        ("resource_context_digest", SHA_B),
        ("request_id", new_record_id()),
        ("correlation_id", new_record_id()),
    ),
)
def test_fixed_principal_and_decision_receipt_checks(field, changed):
    """Exercise only the explicitly value-only private receipt predicate."""
    resource = resource_for()
    actor_id, link_id = resource.router_actor_id, resource.router_identity_link_id
    caller_input = PreparedAuthorizationInput(
        idempotency_key=resource.request.route_operation_id,
        request_value=post_submit_routing_prepare_values(resource.request),
    )
    authority = FixedServicePreparedAuthorization(
        actor_profile_id=actor_id,
        identity_link_id=link_id,
        service=object(),  # type: ignore[arg-type]
    )
    prepared = _PreparedRouting(authority, object(), caller_input)
    decision = AuthorizationDecision(
        decision_id=new_record_id(),
        action_id=ActionId.TASK_POST_SUBMIT_ROUTE,
        permission_id=PermissionId.TASK_POST_SUBMIT_ROUTE,
        allowed=True,
        denial_code=None,
        resource_type=resource.resource_type,
        resource_id=resource.resource_id,
        resource_context_digest=post_submit_routing_resource_digest(resource),
        matched_authority_kind=MatchedAuthorityKind.FIXED_SERVICE,
        matched_grant_id=None,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=resource.request.route_operation_id,
        correlation_id=resource.request.route_operation_id,
    )
    receipt = prepared._receipt(decision, resource)
    assert receipt.actor_profile_id == actor_id
    assert receipt.actor_identity_link_id == link_id
    assert receipt.service_identity == "workstream.task.post_submit_router"
    assert receipt.matched_grant_id is None
    assert receipt.source.route_operation_id == resource.request.route_operation_id
    assert receipt.source.routing_manifest_id == resource.source.id

    with pytest.raises(
        PreparedAuthorizationHandleInvalid,
        match="invalid routing authorization receipt",
    ):
        prepared._receipt(decision.model_copy(update={field: changed}), resource)

    changed_source = resource.source.model_copy(update={"replica_id": new_record_id()})
    changed_resource = PostSubmitRoutingResourceContext(
        **(resource.model_dump() | {"source": changed_source})
    )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        prepared._receipt(decision, changed_resource)

    wrong_input = PreparedAuthorizationInput(
        idempotency_key=new_record_id(),
        request_value=post_submit_routing_prepare_values(resource.request),
    )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        _PreparedRouting(authority, object(), wrong_input)._receipt(decision, resource)

    changed_value_request = changed_request(
        resource.request,
        created_at=resource.request.created_at + timedelta(microseconds=1),
    )
    wrong_value = PreparedAuthorizationInput(
        idempotency_key=resource.request.route_operation_id,
        request_value=post_submit_routing_prepare_values(changed_value_request),
    )
    assert changed_value_request.route_request_digest == resource.request.route_request_digest
    with pytest.raises(
        PreparedAuthorizationHandleInvalid, match="invalid routing authorization receipt"
    ):
        _PreparedRouting(authority, object(), wrong_value)._receipt(decision, resource)


@pytest.mark.parametrize(
    "field", ("router_actor_id", "router_identity_link_id", "authorized_lifecycle_generation")
)
def test_receipt_digest_binds_principal_and_original_generation(field):
    original = resource_for(human_review_required=False)
    if field == "authorized_lifecycle_generation":
        changed = original.model_copy(
            update={
                "consequence": original.consequence.model_copy(
                    update={field: original.consequence.authorized_lifecycle_generation + 1}
                )
            }
        )
    else:
        changed = original.model_copy(update={field: new_record_id()})
    assert post_submit_routing_resource_digest(changed) != post_submit_routing_resource_digest(
        original
    )


@pytest.mark.parametrize("human", [True, False])
def test_exhaustion_authority_binds_terminal_round_and_exact_receipt(human):
    """Exhaustion is a distinct authorized consequence, including zero revisions."""
    from app.modules.authorization.domain.post_submit_routing import CheckerExhaustionConsequence

    original = resource_for(human_review_required=human, routing_recommendation="needs_revision")
    terminal = original.model_copy(update={"consequence": CheckerExhaustionConsequence(
        exhaustion_receipt_id=new_record_id(), revision_round=0, max_revision_rounds=0,
    )})
    assert terminal.validate_identity() is terminal
    assert post_submit_routing_resource_digest(terminal) != post_submit_routing_resource_digest(original)
    altered = terminal.model_copy(update={"consequence": terminal.consequence.model_copy(update={
        "max_revision_rounds": 1,
    })})
    with pytest.raises(ValueError):
        post_submit_routing_resource_digest(altered)
    another = terminal.model_copy(update={"consequence": terminal.consequence.model_copy(update={
        "exhaustion_receipt_id": new_record_id(),
    })})
    assert post_submit_routing_resource_digest(another) != post_submit_routing_resource_digest(terminal)
