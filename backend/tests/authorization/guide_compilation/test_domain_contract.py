"""Focused domain proof for compilation resource and PREP guards."""

from dataclasses import asdict
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.api import project_guide_compilation_request_resource_digest
from app.modules.authorization.domain.guide_compilation import (
    ProjectGuideCompilationExecuteResourceContext,
    ProjectGuideCompilationRequestResourceContext,
    persisted_result_digest,
    request_authority_digest,
)
from app.modules.authorization.domain.prepared_compilation import (
    parse_prepared_compilation,
    prepared_compilation_matches,
)
from app.modules.authorization.domain.prepared_service import (
    is_project_setup_scope,
    project_setup_resource_matches,
)
from app.modules.authorization.guide_compilation import _execute_context, _request_context
from app.modules.authorization.runtime import (
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    PreparedAuthorizationHandleInvalid,
    SystemResourceContext,
)

from .test_adapter_contract import _actor, _request


def test_request_context_rejects_an_operation_selector_mismatch() -> None:
    resource = _request_context(_request())
    with pytest.raises(ValidationError, match="must match operation"):
        ProjectGuideCompilationRequestResourceContext(
            **{**resource.model_dump(), "resource_id": uuid4()}
        )


def test_execute_context_requires_phase_appropriate_result_digest() -> None:
    request = _request()
    values = {**asdict(request), "attempt_id": uuid4(), "provider_idempotency_key": uuid4()}
    from app.modules.authorization.api import ProjectGuideCompilationExecutePreflightFacts

    resource = _execute_context(ProjectGuideCompilationExecutePreflightFacts(**values), phase="preflight")
    with pytest.raises(ValidationError, match="requires exact result digest"):
        ProjectGuideCompilationExecuteResourceContext(
            **{**resource.model_dump(), "result_resource_digest": "sha256:" + "a" * 64}
        )


def test_request_digest_requires_a_grant_and_binds_it() -> None:
    actor, facts = _actor(), _request()
    resource = _request_context(facts)
    assert request_authority_digest(
        resource,
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        grant_id=None,
    ) is None
    grant_id = uuid4()
    first = request_authority_digest(
        resource,
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        grant_id=grant_id,
    )
    second = request_authority_digest(
        resource,
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        grant_id=uuid4(),
    )
    assert first != second
    assert first == project_guide_compilation_request_resource_digest(actor, grant_id, facts)


def test_prepared_parser_round_trips_exact_request_and_rejects_bad_uuid() -> None:
    resource = _request_context(_request())
    binding = parse_prepared_compilation(
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST, resource.model_dump(mode="json")
    )
    assert prepared_compilation_matches(
        binding["guide_compilation_context"],
        binding["guide_compilation_resource_digest"],
        resource,
    )
    assert parse_prepared_compilation(ActionId.PROJECT_CREATE, {}) == {}
    with pytest.raises(PreparedAuthorizationHandleInvalid, match="invalid prepared"):
        parse_prepared_compilation(
            ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
            {**resource.model_dump(mode="json"), "guide_id": "invalid"},
        )


def test_project_setup_scope_and_resource_guard_are_action_specific() -> None:
    facts = _request()
    from app.modules.authorization.api import ProjectGuideCompilationExecutePreflightFacts

    execute = _execute_context(
        ProjectGuideCompilationExecutePreflightFacts(
            **asdict(facts), attempt_id=uuid4(), provider_idempotency_key=uuid4()
        ),
        phase="preflight",
    )
    scope = PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.PROJECT, project_id=facts.project_id
    )
    assert is_project_setup_scope(ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE, scope)
    assert project_setup_resource_matches(
        ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE, execute, facts.project_id
    )
    assert not project_setup_resource_matches(
        ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE, execute, uuid4()
    )
    unrelated = SystemResourceContext(resource_type="system", resource_id="workstream:system")
    assert project_setup_resource_matches(ActionId.PROJECT_CREATE, unrelated, None) is None
    assert persisted_result_digest(execute) is None


def test_compilation_resource_contexts_reject_scalar_coercion() -> None:
    attempt_id = uuid4()
    with pytest.raises(ValidationError):
        ProjectGuideCompilationExecuteResourceContext(
            resource_type="project_guide_compilation_attempt",
            resource_id=attempt_id,
            scope_project_id=uuid4(),
            guide_id=uuid4(),
            source_snapshot_id=uuid4(),
            setup_run_id=uuid4(),
            setup_generation="1",
            attempt_id=attempt_id,
            provider_idempotency_key=uuid4(),
            phase="preflight",
            request_facts_digest="sha256:" + "a" * 64,
        )
