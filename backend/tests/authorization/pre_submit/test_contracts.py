"""Selected PRE fixed-service resources bind exact phase and durable request facts."""

from __future__ import annotations

from app.adapters.artifacts import selected_pre_submit_source_contracts

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.core.identifiers import new_record_id
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.domain.audit import (
    AuthorizationDecision,
    MatchedAuthorityKind,
)
from app.modules.authorization.domain.pre_submit import (
    EXECUTE,
    FINALIZE,
    PreSubmitResourceContext,
    parse_pre_submit_prepare,
    pre_submit_prepare_matches,
    pre_submit_prepare_values,
    pre_submit_resource,
)
from app.modules.authorization.domain.action_groups import CONTEXT_DIGEST_ACTIONS
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
)
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitExecuteFacts,
    SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)


def _reservation() -> SelectedPreSubmitReservationFacts:
    return SelectedPreSubmitReservationFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        project_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        attempt_id=new_record_id(),
        idempotency_key=new_record_id(),
        attempt_request_digest="sha256:" + "0" * 64,
        prepared_generation_id=new_record_id(),
        policy_sha256="sha256:" + "1" * 64,
        default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        default_input_sha256="sha256:" + "2" * 64,
        archive_sha256="sha256:" + "3" * 64,
        archive_byte_count=100,
        semantic_manifest_sha256="sha256:" + "4" * 64,
        execution_budget_ms=60_000,
     source_contracts=selected_pre_submit_source_contracts())


def _execute() -> SelectedPreSubmitExecuteFacts:
    return SelectedPreSubmitExecuteFacts(
        SelectedPreSubmitLeaseFacts(
            reservation=_reservation(),
            lease_id=new_record_id(),
            lease_generation=1,
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
    )


def test_selected_pre_resource_binds_phase_project_run_and_request() -> None:
    execute = _execute()
    resource = pre_submit_resource(EXECUTE, execute)
    prepared = pre_submit_prepare_values(execute.lease.reservation)

    assert resource.resource_id == execute.lease.reservation.attempt_id
    assert resource.scope_project_id == execute.lease.reservation.project_id
    assert authorization_resource_digest(resource) == execute.facts_digest
    assert {EXECUTE, FINALIZE} <= CONTEXT_DIGEST_ACTIONS
    assert pre_submit_prepare_matches(EXECUTE, prepared, resource)
    assert not pre_submit_prepare_matches(
        EXECUTE,
        prepared | {"request_digest": "sha256:" + "f" * 64},
        resource,
    )
    with pytest.raises(ValueError, match="phase"):
        PreSubmitResourceContext(
            resource_id=resource.resource_id,
            scope_project_id=resource.scope_project_id,
            action_id=FINALIZE,
            facts=execute,
        )


def test_selected_pre_resource_is_admitted_by_decision_and_audit_boundaries() -> None:
    execute = _execute()
    resource = pre_submit_resource(EXECUTE, execute)
    decision_id = new_record_id()
    decision = AuthorizationDecision(
        decision_id=decision_id,
        action_id=EXECUTE,
        permission_id=PermissionId.CHECKER_PRE_SUBMIT_EXECUTE,
        allowed=True,
        denial_code=None,
        resource_type=resource.resource_type,
        resource_id=resource.resource_id,
        resource_context_digest=execute.facts_digest,
        matched_authority_kind=MatchedAuthorityKind.FIXED_SERVICE,
        revalidated=True,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
    )

    event = AuthorityAuditEventInput(
        event_id=decision_id,
        event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
        entity_type="authorization_decision",
        entity_id=str(decision_id),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(execute.lease.reservation.actor_profile_id),
        request_id=decision.request_id,
        correlation_id=decision.correlation_id,
        permission_id=decision.permission_id,
        action_id=decision.action_id,
        project_id=str(resource.scope_project_id),
        resource_type=resource.resource_type,
        resource_id=str(resource.resource_id),
        target_ref_kind="project",
        target_ref_id=str(resource.scope_project_id),
        reason="authorization_evaluation",
        after_facts={
            "allowed": True,
            "resource_context_digest": decision.resource_context_digest,
        },
    )

    assert event.resource_type == "selected_pre_submit_run"


def test_selected_pre_finalize_and_prepare_parser_are_closed() -> None:
    execute = _execute()
    final = SelectedPreSubmitFinalizeFacts(
        lease=execute.lease,
        execution=None,
        infrastructure_failure_code="deadline_exceeded",
     source_contracts=selected_pre_submit_source_contracts())
    resource = pre_submit_resource(FINALIZE, final)
    prepared = pre_submit_prepare_values(execute.lease.reservation)

    assert pre_submit_prepare_matches(FINALIZE, prepared, resource)
    assert parse_pre_submit_prepare(
        FINALIZE, prepared, PreparedAuthorizationHandleInvalid
    ) == prepared
    with pytest.raises(
        PreparedAuthorizationHandleInvalid,
        match="invalid prepared selected PRE authority",
    ):
        parse_pre_submit_prepare(
            FINALIZE,
            prepared | {"extra": "value"},
            PreparedAuthorizationHandleInvalid,
        )
    changed = replace(
        execute.lease.reservation,
        attempt_id=new_record_id(),
    )
    assert not pre_submit_prepare_matches(
        FINALIZE, pre_submit_prepare_values(changed), resource
    )
