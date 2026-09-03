"""Exact projection resource and digest behavior."""

from dataclasses import fields, replace
from uuid import UUID, uuid4

import pytest

from app.modules.authorization.api import (
    artifact_policy_projection_facts_digest,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_facts_digest,
    guide_sufficiency_projection_identity,
    projection_authority_digest,
)
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectGuideProjectionResourceContext,
    parse_projection_prepare,
    projection_context_matches,
    projection_prepare_context,
    projection_prepare_matches,
    projection_resource_context,
    projection_resource_digest,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.api import ProjectGuideProjectionLocator
from app.modules.authorization.runtime import ProjectGuideSufficiencyMutationResourceContext

from .support import policy_facts, sufficiency_facts


@pytest.mark.parametrize("component", ("guide_sufficiency", "submission_artifact_policy"))
def test_projection_resource_digests_match_public_contract(component: str) -> None:
    project_id, attempt_id, actor_id, link_id = (uuid4() for _ in range(4))
    identity = (
        guide_sufficiency_projection_identity(
            attempt_id=attempt_id, actor_profile_id=actor_id, identity_link_id=link_id
        )
        if component == "guide_sufficiency"
        else artifact_policy_projection_identity(
            attempt_id=attempt_id, actor_profile_id=actor_id, identity_link_id=link_id
        )
    )
    facts = (
        sufficiency_facts(project_id, attempt_id)
        if component == "guide_sufficiency"
        else policy_facts(project_id, attempt_id)
    )
    resource = projection_resource_context(component, identity, facts)
    facts_digest = (
        guide_sufficiency_projection_facts_digest(facts)
        if component == "guide_sufficiency"
        else artifact_policy_projection_facts_digest(facts)
    )
    assert projection_resource_digest(resource) == projection_authority_digest(
        component=component,
        identity=identity,
        project_id=project_id,
        facts_digest=facts_digest,
    )


def test_projection_prepare_binds_complete_authority() -> None:
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    identity = guide_sufficiency_projection_identity(
        attempt_id=locator.attempt_id,
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
    )
    prepared = projection_prepare_context("guide_sufficiency", locator, identity)
    resource = projection_resource_context(
        "guide_sufficiency",
        identity,
        sufficiency_facts(locator.project_id, locator.attempt_id),
    )
    assert projection_prepare_matches(prepared.model_dump(mode="json"), resource)


def test_projection_prepare_cannot_consume_a_legacy_resource_kind() -> None:
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    identity = guide_sufficiency_projection_identity(
        attempt_id=locator.attempt_id,
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
    )
    prepared = projection_prepare_context("guide_sufficiency", locator, identity)
    legacy = ProjectGuideSufficiencyMutationResourceContext.model_construct(
        resource_type="project_guide_sufficiency_mutation",
        resource_id=uuid4(),
        scope_project_id=locator.project_id,
        execution_kind="setup_service",
    )
    assert not projection_context_matches(prepared.model_dump(mode="json"), legacy)
    projection = projection_resource_context(
        "guide_sufficiency",
        identity,
        sufficiency_facts(locator.project_id, locator.attempt_id),
    )
    assert not projection_context_matches(None, projection)


def test_projection_facts_digest_cannot_be_forged() -> None:
    project_id, attempt_id = uuid4(), uuid4()
    identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id,
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
    )
    facts = sufficiency_facts(project_id, attempt_id)
    resource = projection_resource_context("guide_sufficiency", identity, facts)
    with pytest.raises(ValueError, match="digest"):
        resource.model_copy(update={"facts_digest": "sha256:" + "b" * 64}).__class__(
            **{
                **resource.model_dump(),
                "facts_digest": "sha256:" + "b" * 64,
            }
        )


def test_projection_components_cannot_swap_authority() -> None:
    project_id, attempt_id = uuid4(), uuid4()
    identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id,
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
    )
    with pytest.raises(ValueError, match="do not match"):
        projection_resource_context(
            "guide_sufficiency", identity, policy_facts(project_id, attempt_id)
        )


def test_projection_resource_rejects_incomplete_facts() -> None:
    project_id, attempt_id = uuid4(), uuid4()
    identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id, actor_profile_id=uuid4(), identity_link_id=uuid4()
    )
    resource = projection_resource_context(
        "guide_sufficiency", identity, sufficiency_facts(project_id, attempt_id)
    )
    values = resource.model_dump()
    values["projection_facts"].pop("report_id")
    with pytest.raises(ValueError, match="incomplete"):
        ProjectGuideProjectionResourceContext(**values)


def test_projection_resource_rejects_wrong_project() -> None:
    project_id, attempt_id = uuid4(), uuid4()
    identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id, actor_profile_id=uuid4(), identity_link_id=uuid4()
    )
    resource = projection_resource_context(
        "guide_sufficiency", identity, sufficiency_facts(project_id, attempt_id)
    )
    values = resource.model_dump()
    values["scope_project_id"] = uuid4()
    with pytest.raises(ValueError, match="project identity"):
        ProjectGuideProjectionResourceContext(**values)


def test_projection_resource_rejects_wrong_resource_identity() -> None:
    project_id, attempt_id = uuid4(), uuid4()
    identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id, actor_profile_id=uuid4(), identity_link_id=uuid4()
    )
    resource = projection_resource_context(
        "guide_sufficiency", identity, sufficiency_facts(project_id, attempt_id)
    )
    with pytest.raises(ValueError, match="resource identity"):
        ProjectGuideProjectionResourceContext(**{**resource.model_dump(), "resource_id": uuid4()})


def test_projection_prepare_parser_is_closed_and_action_bound() -> None:
    assert parse_projection_prepare(ActionId.PROJECT_READ, {}) == {}
    with pytest.raises(ValueError, match="invalid projection preparation"):
        parse_projection_prepare(
            ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
            {"binding_kind": "project_guide_projection"},
        )
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    identity = guide_sufficiency_projection_identity(
        attempt_id=locator.attempt_id,
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
    )
    value = projection_prepare_context("guide_sufficiency", locator, identity).model_dump(
        mode="json"
    )
    with pytest.raises(ValueError, match="does not match"):
        parse_projection_prepare(ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE, value)


@pytest.mark.parametrize("component", ("guide_sufficiency", "submission_artifact_policy"))
def test_every_projection_fact_field_changes_the_bound_digest(component: str) -> None:
    project_id, attempt_id = uuid4(), uuid4()
    facts = (
        sufficiency_facts(project_id, attempt_id)
        if component == "guide_sufficiency"
        else policy_facts(project_id, attempt_id)
    )
    digest = (
        guide_sufficiency_projection_facts_digest
        if component == "guide_sufficiency"
        else artifact_policy_projection_facts_digest
    )
    original = digest(facts)
    for field in fields(facts):
        value = getattr(facts, field.name)
        if isinstance(value, UUID):
            changed = uuid4()
        elif type(value) is int:
            changed = value + 1
        elif isinstance(value, str) and value.startswith("sha256:"):
            changed = "sha256:" + "b" * 64
        else:
            changed = value + "-changed"
        assert digest(replace(facts, **{field.name: changed})) != original
