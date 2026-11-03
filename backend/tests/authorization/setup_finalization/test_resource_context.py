"""Complete final facts, immutable shape and private preparation binding."""

from dataclasses import FrozenInstanceError, fields, replace
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    AuthorizationDenied,
    PreparedAuthorizationInvalid,
    ProjectSetupFinalizationFacts,
    setup_finalization_authority_digest,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.project_setup_finalization import (
    ProjectSetupFinalizationResourceContext,
    finalization_resource_context,
)
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from .support import Case, DIGEST, FIELDS, alternate


def test_exact_fact_inventory():
    assert set(FIELDS) == {field.name for field in fields(ProjectSetupFinalizationFacts)}


@pytest.mark.parametrize("field", tuple(field for field in FIELDS if field != "result_schema_version"))
async def test_each_finalization_fact_is_bound(monkeypatch, field):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    changed = alternate(case.facts, field)
    assert getattr(changed, field) != getattr(case.facts, field)
    # The alternate vector and resource are valid. Original receipt disagreement
    # reaches replay validation rather than a malformed dataclass guard.
    resource = case.resource(changed)
    assert resource.facts == changed
    async with case.prepare(changed) as prepared:
        with pytest.raises(AuthorizationDenied, match="finalization authority denied"):
            await prepared.validate_replay(changed, receipt.decision_event_id)
    assert len(case.evidence.events) == 1


@pytest.mark.parametrize(
    "key",
    [
        "sufficiency_hash",
        "artifact_policy_hash",
        "requirement_inventory_hash",
        "pre_submit_hash",
        "post_submit_hash",
    ],
)
async def test_each_component_hash_is_bound(monkeypatch, key):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    hashes = dict(case.facts.component_hashes)
    hashes[key] = DIGEST
    changed = replace(case.facts, component_hashes=tuple(sorted(hashes.items())))
    async with case.prepare() as prepared:
        with pytest.raises(AuthorizationDenied):
            await prepared.validate_replay(changed, receipt.decision_event_id)


def test_current_result_and_component_schema_versions_are_closed(monkeypatch):
    case = Case(monkeypatch)
    with pytest.raises(ValueError, match="result schema is invalid"):
        replace(case.facts, result_schema_version="project_guide_check_specification.v2")
    changed = dict(case.facts.component_hashes)
    changed["schema_version"] = "project_guide_check_specification_hashes.v2"
    with pytest.raises(ValueError, match="component hash values are invalid"):
        replace(case.facts, component_hashes=tuple(sorted(changed.items())))


@pytest.mark.parametrize(
    "classification", ["draft_ready", "draft_ready_with_warnings", "guide_blocked"]
)
async def test_policy_tuple_and_transition_shape(monkeypatch, classification):
    case = Case(monkeypatch, classification)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    assert receipt.resource_context_digest == setup_finalization_authority_digest(
        case.facts, case.first.actor_profile_id, case.first.identity_link_id
    )
    event = case.evidence.events[0]
    assert event.after_facts == {
        "allowed": True,
        "resource_context_digest": receipt.resource_context_digest,
    }
    assert event.resource_id == str(case.facts.finalization_id)
    from app.modules.authorization.api import setup_finalization_preparation_identity

    request_id, correlation_id = setup_finalization_preparation_identity(
        case.facts.setup_run_id,
        case.facts.setup_generation,
        case.facts.compilation_id,
    )
    assert event.request_id == request_id
    assert event.correlation_id == correlation_id
    assert case.fixed_calls == [(request_id, correlation_id)]


@pytest.mark.parametrize("classification", ["draft_ready", "draft_ready_with_warnings"])
@pytest.mark.parametrize(
    "field",
    ["artifact_policy_id", "artifact_policy_operation_id", "artifact_policy_output_digest"],
)
def test_ready_finalization_rejects_each_missing_policy_field(monkeypatch, classification, field):
    case = Case(monkeypatch, classification)
    assert case.resource().facts == case.facts
    assert getattr(case.facts, field) is not None
    # All other facts, including the two remaining policy fields, stay valid.
    with pytest.raises(
        ValueError, match="^finalization classification and projection shape disagree$"
    ):
        replace(case.facts, **{field: None})


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_policy_id", uuid4()),
        ("artifact_policy_operation_id", uuid4()),
        ("artifact_policy_output_digest", DIGEST),
    ],
)
def test_blocked_finalization_rejects_each_populated_policy_field(monkeypatch, field, value):
    case = Case(monkeypatch, "guide_blocked")
    assert case.resource().facts == case.facts
    assert getattr(case.facts, field) is None
    # The replacement is a valid UUID/digest; only its presence violates the shape.
    with pytest.raises(
        ValueError, match="^finalization classification and projection shape disagree$"
    ):
        replace(case.facts, **{field: value})


@pytest.mark.parametrize(
    "classification,outcome",
    [
        ("draft_ready", "sufficiency_blocked"),
        ("draft_ready_with_warnings", "sufficiency_blocked"),
        ("guide_blocked", "policy_draft_ready"),
    ],
)
def test_finalization_rejects_conflicting_classification_outcome(
    monkeypatch, classification, outcome
):
    case = Case(monkeypatch, classification)
    assert case.resource().facts == case.facts
    assert case.facts.setup_outcome != outcome
    # Retain the complete policy tuple required by the original classification.
    with pytest.raises(
        ValueError, match="^finalization classification and projection shape disagree$"
    ):
        replace(case.facts, setup_outcome=outcome)


@pytest.mark.parametrize("field", ["finalization_id", "operation_id"])
def test_finalization_record_identity_rejects_non_v7(monkeypatch, field):
    case = Case(monkeypatch)
    with pytest.raises(ValueError, match="record identities must be UUIDv7"):
        replace(case.facts, **{field: uuid4()})


@pytest.mark.parametrize(
    "field", ["project_id", "setup_run_id", "setup_generation", "compilation_id"]
)
async def test_locator_substitution_reaches_adapter_guard(monkeypatch, field):
    case = Case(monkeypatch)
    from .support import locator_for

    locator = replace(
        locator_for(case.facts),
        **{field: 2 if field == "setup_generation" else uuid4()},
    )
    async with case.adapter.prepare_setup_finalization(locator) as prepared:
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume_new(case.facts)
    assert case.evidence.events == []


@pytest.mark.parametrize(
    "field",
    [
        "actor_profile_id",
        "identity_link_id",
        "setup_run_id",
        "compilation_id",
        "project_id",
        "idempotency",
    ],
)
async def test_preparation_locator_and_principal_are_bound(monkeypatch, field):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        service = case.services[-1]
        original = prepared._input
        # Caller-supplied selectors must agree with private request custody.
        body = dict(original.request_value)
        changes = {"idempotency_key": uuid4()} if field == "idempotency" else {}
        if field != "idempotency":
            body[field] = str(uuid4())
        forged = original.model_copy(update={"request_value": body, **changes})
        scope = service._scope_from_resource(ActionId.PROJECT_SETUP_RUN_UPDATE, case.resource())
        with pytest.raises(PreparedAuthorizationHandleInvalid, match="invalid prepared"):
            await service.prepare(ActionId.PROJECT_SETUP_RUN_UPDATE, forged, scope)
        receipt = await prepared.consume_new(case.facts)
    assert len(case.evidence.events) == 1
    assert receipt.actor_profile_id == case.first.actor_profile_id


def test_resource_is_closed_and_deeply_immutable(monkeypatch):
    case = Case(monkeypatch)
    resource = case.resource()
    with pytest.raises(ValueError):
        resource.actor_profile_id = uuid4()
    with pytest.raises(FrozenInstanceError):
        resource.facts.guide_version = "forged"
    with pytest.raises(TypeError):
        resource.facts.component_hashes[0] = ("sufficiency_hash", DIGEST)
    with pytest.raises(ValueError):
        ProjectSetupFinalizationResourceContext.model_validate_json(
            resource.model_dump_json()[:-1] + ',"unknown":true}'
        )
    with pytest.raises(ValueError):
        finalization_resource_context(object(), uuid4(), uuid4())


@pytest.mark.parametrize(
    "field", ["actor_profile_id", "identity_link_id", "setup_run_id", "compilation_id"]
)
async def test_consistently_forged_public_pair_cannot_replace_private_custody(monkeypatch, field):
    from .support import locator_for
    from app.modules.authorization.domain.project_setup_finalization import (
        finalization_context_matches,
        finalization_prepare_context,
    )

    case = Case(monkeypatch)
    facts = alternate(case.facts, field) if field in {"setup_run_id", "compilation_id"} else case.facts
    actor = uuid4() if field == "actor_profile_id" else case.first.actor_profile_id
    link = uuid4() if field == "identity_link_id" else case.first.identity_link_id
    forged_resource = finalization_resource_context(facts, actor, link)
    forged_body = finalization_prepare_context(locator_for(facts), actor, link).model_dump(
        mode="json"
    )
    assert finalization_context_matches(forged_body, forged_resource)
    async with case.prepare() as prepared:
        service = case.services[-1]
        from app.modules.authorization.api import setup_finalization_preparation_identity

        request_id, _ = setup_finalization_preparation_identity(
            facts.setup_run_id, facts.setup_generation, facts.compilation_id
        )
        forged_input = prepared._input.model_copy(
            update={
                "request_value": forged_body,
                "idempotency_key": request_id,
            }
        )
        scope = service._scope_from_resource(ActionId.PROJECT_SETUP_RUN_UPDATE, forged_resource)
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await service.prepare(ActionId.PROJECT_SETUP_RUN_UPDATE, forged_input, scope)
        await prepared.consume_new(case.facts)
    assert len(case.evidence.events) == 1
