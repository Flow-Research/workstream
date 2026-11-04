"""PostgreSQL proofs for checker-retry authority ordering and revocation."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Engine

from app.adapters.audit import task_transition_audit
from app.adapters.checkers import checker_retry_service
from app.adapters.outbox import outbox_append
from app.adapters.tasks import task_commands
from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.admin_service import AdminRoleGrantService
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.checker_retry_authorization import (
    PreparedCheckerRetryAuthorization,
)
from app.modules.authorization.domain.audit import (
    AuthorizationDecision,
    AuthorizationDenialCode,
)
from app.modules.authorization.domain.checker_retry import (
    CheckerRetryPrepareDenialResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AdminRoleGrantResourceContext,
    AuthorizationDenied,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from app.modules.authorization.schemas import (
    AdminRoleGrantRevokeRequest,
    AuthorityOperation,
    derive_reason_digest,
)
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    CheckerRetryPreparation,
    CheckerRetrySource,
)
from app.modules.audit.schemas import LifecycleAuditEventType
from app.modules.checkers.models import CheckerRetryReceipt, CheckerRun, CheckerSubmissionFence
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.outbox.api import OutboxAppendInput
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import AuditEvent, TaskCommandReceipt
from app.modules.tasks.api import TaskAuthorityDenied
from app.modules.tasks.repository import TaskRepository
from auth_concurrency_support import wait_for_named_database_lock
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authentication.support import issue_asymmetric_token
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)
from tests.authorization.admin_access.support import create_project
from tests.checkers.execution.test_checker_retry import (
    _command,
    _failed_source,
    _operator_for,
    _recovery_paths,
)
from tests.test_artifact_admission import _context


def _checker_projection_columns(selected_columns) -> set[str]:
    columns = set()
    for selected in selected_columns:
        column = getattr(selected, "element", selected)
        if getattr(getattr(column, "table", None), "name", None) in {
            "checker_runs", "checker_retry_receipts",
        }:
            columns.add(selected.name)
    return columns


def test_checker_projection_probe_unwraps_labels_and_detects_private_columns():
    selected = select(
        CheckerRun.project_id.label("project_id"),
        CheckerRun.request_json.label("request_json"),
        CheckerRetryReceipt.id.label("retry_receipt_id"),
    ).selected_columns
    assert _checker_projection_columns(selected) == {
        "project_id", "request_json", "retry_receipt_id",
    }


@pytest.mark.asyncio
async def test_retry_prepare_denial_requires_original_source_and_current_identity():
    actor_id, link_id, key = new_record_id(), new_record_id(), new_record_id()
    source = CheckerRetrySource(
        project_id=new_record_id(), task_id=new_record_id(),
        assignment_id=new_record_id(), submission_id=new_record_id(),
        submission_version=1, source_run_id=new_record_id(),
        source_request_id=new_record_id(), source_request_digest="sha256:" + "0" * 64,
        source_result_id=new_record_id(), source_result_digest="sha256:" + "1" * 64,
        source_finalize_evidence_id=new_record_id(), source_generation=1,
        failure_code="material_unavailable",
    )
    preparation = CheckerRetryPreparation(
        actor_profile_id=actor_id,
        request_key=key,
        reason="Restore verified checker infrastructure",
        source=source,
    )
    context = HumanAuthorizationContext(
        actor_profile_id=actor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=key,
        correlation_id=key,
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=key,
        request_value=preparation.model_dump(mode="json"),
    )
    resource = CheckerRetryPrepareDenialResourceContext(
        resource_id=source.source_run_id,
        project_id=source.project_id,
        identity_link_id=link_id,
        preparation=preparation,
    )
    assert PreparedAuthorizationService._scope_from_resource(
        ActionId.OPERATIONS_CHECKER_RETRY, resource,
    ) == PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM)

    class DenialAuthorization:
        calls = 0

        async def _complete_prepared_denial(
            self, consumer_token, action_id, final_resource, denial_code,
        ):
            assert consumer_token is token
            assert action_id is ActionId.OPERATIONS_CHECKER_RETRY
            assert final_resource is resource
            assert denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            self.calls += 1
            raise AuthorizationDenied(AuthorizationDecision(
                decision_id=new_record_id(),
                action_id=action_id,
                permission_id=PermissionId.OPERATIONS_CHECKER_RETRY,
                allowed=False,
                denial_code=denial_code,
                resource_type=resource.resource_type,
                resource_id=resource.resource_id,
                resource_context_digest=canonical_json_hash(
                    resource.model_dump(mode="json")
                ),
                matched_authority_kind=None,
                revalidated=False,
                request_id=key,
                correlation_id=key,
            ))

    token = object()
    authorization = DenialAuthorization()
    service = object.__new__(PreparedAuthorizationService)
    service._context = context
    service._authorization = authorization
    service._consumer_token = token
    denial = PreparedAuthorizationUnsupported(
        AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    )
    other_source = source.model_copy(update={
        "project_id": new_record_id(),
        "source_run_id": new_record_id(),
    })
    other_preparation = preparation.model_copy(update={"source": other_source})

    for mismatched in (
        resource.model_copy(update={"identity_link_id": new_record_id()}),
        CheckerRetryPrepareDenialResourceContext(
            resource_id=other_source.source_run_id,
            project_id=other_source.project_id,
            identity_link_id=link_id,
            preparation=other_preparation,
        ),
        resource.model_copy(update={"resource_id": new_record_id()}),
    ):
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await service.deny_unsupported(
                ActionId.OPERATIONS_CHECKER_RETRY,
                caller_input,
                mismatched,
                denial,
            )
    assert authorization.calls == 0

    with pytest.raises(AuthorizationDenied):
        await service.deny_unsupported(
            ActionId.OPERATIONS_CHECKER_RETRY,
            caller_input,
            resource,
            denial,
        )
    assert authorization.calls == 1

async def _assert_project_manager_concealed(admin_access, h, discovery_path, retry_path):
    project_grant = await admin_access.signed.grant(
        admin_access.admin,
        admin_access.target,
        role="project_manager",
        project_id=h.request.project_id,
    )
    denied_statements = []

    def capture_denied(_conn, _cursor, statement, _parameters, _context, _many):
        denied_statements.append(statement)

    event.listen(Engine, "before_cursor_execute", capture_denied)
    try:
        denied = await admin_access.signed.client.get(
            discovery_path, headers=admin_access.target.headers,
        )
    finally:
        event.remove(Engine, "before_cursor_execute", capture_denied)
    assert denied.status_code == 404, denied.text
    assert not any(
        table in statement.lower()
        for statement in denied_statements
        for table in ("checker_runs", "checker_retry_receipts")
    )
    denied_retry = await admin_access.signed.client.post(
        retry_path,
        headers=admin_access.target.headers | {"Idempotency-Key": str(new_record_id())},
        json={"reason": "Restore verified checker infrastructure"},
    )
    assert denied_retry.status_code == 404, denied_retry.text
    async with h.factory() as session:
        assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
        assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
    return project_grant


async def _operator_discovery(admin_access, h, discovery_path):
    system_grant = await admin_access.signed.grant(
        admin_access.admin, admin_access.target,
    )
    selected_columns = []

    def capture_projection(_conn, _cursor, _statement, _parameters, context, _many):
        compiled = getattr(context, "compiled", None)
        selected = getattr(getattr(compiled, "statement", None), "selected_columns", ())
        if selected is not None:
            selected_columns.extend(selected)

    event.listen(Engine, "before_cursor_execute", capture_projection)
    try:
        page = await admin_access.signed.client.get(
            discovery_path, headers=admin_access.target.headers,
        )
    finally:
        event.remove(Engine, "before_cursor_execute", capture_projection)
    assert page.status_code == 200, page.text
    body = page.json()
    assert set(body) == {"project_id", "items", "next_cursor"}
    assert body["project_id"] == str(h.request.project_id)
    assert body["next_cursor"] is None and len(body["items"]) == 1
    item = body["items"][0]
    assert set(item) == {
        "source", "recovery_state", "created_at", "completed_at",
        "retry_receipt_id", "successor", "model_recovery_candidates",
    }
    assert item["recovery_state"] == "eligible"
    assert item["retry_receipt_id"] is None and item["successor"] is None
    assert item["model_recovery_candidates"] == []
    assert item["source"] == {
        "project_id": str(h.request.project_id),
        "task_id": str(h.request.task_id),
        "submission_id": str(h.request.submission_id),
        "submission_version": h.request.submission_version,
        "source_run_id": str(h.created.evaluation_attempt_id),
        "source_request_id": str(h.request.evaluation_request_id),
        "source_request_digest": h.request.request_sha256,
        "source_result_id": str(h.created.evaluation_result_id),
        "source_result_digest": item["source"]["source_result_digest"],
        "source_finalize_evidence_id": item["source"]["source_finalize_evidence_id"],
        "source_generation": 1,
        "failure_code": "material_unavailable",
    }
    assert all(
        private not in page.text
        for private in (
            "request_json", "result_json", "material_custody", "package_uri",
            "selected_post_submit_policy_body",
        )
    )
    checker_columns = _checker_projection_columns(selected_columns)
    assert checker_columns
    assert not checker_columns & {
        "request_json", "result_json", "material_custody",
        "selected_post_submit_policy_body", "resource_json", "resource_digest",
        "authorization_decision_id", "identity_link_id", "actor_profile_id",
    }
    async with h.factory() as session:
        read_allows = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(admin_access.target.id),
            AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY_SOURCE_LIST.value,
        ).order_by(AuditEvent.id)))
        read_allow = [item for item in read_allows if item.after_facts.get("allowed")][-1]
        assert read_allow.matched_grant_id == system_grant
        assert read_allow.permission_id == "operations.status.read"
        assert read_allow.project_id == str(h.request.project_id)
        assert read_allow.resource_type == "project"
        assert read_allow.resource_id == str(h.request.project_id)
    return system_grant, item


async def _assert_concealed_discovery_principals(
    admin_access, h, discovery_path, retry_path,
):
    service_subject = "checker-recovery-reader-" + uuid4().hex
    provisioned = await admin_access.signed.client.post(
        "/api/v1/service-actors",
        headers=admin_access.admin.headers | {"Idempotency-Key": str(new_record_id())},
        json={
            "service_identity": ServiceIdentity.REVIEW_PROJECTION.value,
            "subject": service_subject,
            "reason": "Prove fixed services cannot discover checker retry sources",
        },
    )
    assert provisioned.status_code == 201, provisioned.text
    service_token = issue_asymmetric_token(
        admin_access.signed.private_key,
        scope="workstream:service",
        claims={
            "sub": service_subject,
            "subject_kind": "service",
            "roles": ["operator"],
        },
    )
    revoked_actor = await admin_access.signed.actor("revoked-recovery-operator")
    await admin_access.signed.grant(
        admin_access.admin, revoked_actor, role="operator",
    )
    async with h.factory() as session:
        link_id = await session.scalar(select(ActorIdentityLink.id).where(
            ActorIdentityLink.actor_profile_id == str(revoked_actor.id)
        ))
    revoked = await admin_access.signed.client.post(
        f"/api/v1/actor-identity-links/{link_id}/revoke",
        headers=admin_access.admin.headers | {"Idempotency-Key": str(new_record_id())},
        json={"reason": "Withdraw checker recovery discovery identity"},
    )
    assert revoked.status_code == 200, revoked.text
    async with h.factory() as session:
        before = (
            await session.scalar(select(func.count()).select_from(CheckerRun)),
            await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            await session.scalar(select(func.count()).select_from(OutboxEvent)),
        )
    missing_discovery, _missing_retry = _recovery_paths(
        h, project_id=new_record_id(),
    )
    requests = (
        (missing_discovery, admin_access.target.headers),
        (discovery_path, {"Authorization": f"Bearer {service_token}"}),
        (discovery_path, revoked_actor.headers),
    )
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        service_retry = await admin_access.signed.client.post(
            retry_path,
            headers={
                "Authorization": f"Bearer {service_token}",
                "Idempotency-Key": str(new_record_id()),
            },
            json={"reason": "Restore verified checker infrastructure"},
        )
        responses = [
            await admin_access.signed.client.get(path, headers=headers)
            for path, headers in requests
        ]
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    responses.append(service_retry)
    assert all(response.status_code == 404 for response in responses)
    assert all(
        str(h.created.evaluation_attempt_id) not in response.text
        and h.request.request_sha256 not in response.text
        for response in responses
    )
    assert not any(
        table in statement.lower()
        for statement in statements
        for table in (
            "checker_runs", "checker_retry_receipts", "checker_submission_fences",
            "workstream_tasks", "task_assignments", "submissions",
        )
    )
    async with h.factory() as session:
        after = (
            await session.scalar(select(func.count()).select_from(CheckerRun)),
            await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            await session.scalar(select(func.count()).select_from(OutboxEvent)),
        )
    assert after == before


async def _wrong_project_refuses_before_task_lock(admin_access, h):
    wrong_project = await create_project("Foreign recovery selector")
    _wrong_discovery, wrong_retry = _recovery_paths(h, project_id=wrong_project)
    async with h.factory.begin() as blocker:
        await blocker.execute(
            text("SELECT id FROM workstream_tasks WHERE id=:task FOR UPDATE"),
            {"task": str(h.request.task_id)},
        )
        wrong = await asyncio.wait_for(
            admin_access.signed.client.post(
                wrong_retry,
                headers=admin_access.target.headers
                | {"Idempotency-Key": str(new_record_id())},
                json={"reason": "Restore verified checker infrastructure"},
            ),
            timeout=5,
        )
    assert wrong.status_code == 404, wrong.text
    return wrong_retry


async def _assert_internal_reservation_failure_rolls_back(
    admin_access, h, retry_path, monkeypatch,
):
    original = EvaluationCoordinator._reserve_after_task_lock

    async def mismatched(coordinator, request, *, terminal_source_id):
        reserved = await original(
            coordinator, request, terminal_source_id=terminal_source_id,
        )
        return reserved.model_copy(update={"request_digest": "sha256:" + "f" * 64})

    async with h.factory() as session:
        before = (
            await session.scalar(select(func.count()).select_from(CheckerRun)),
            await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            await session.scalar(select(func.count()).select_from(OutboxEvent)),
            await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
            )),
        )
    with monkeypatch.context() as patch:
        patch.setattr(EvaluationCoordinator, "_reserve_after_task_lock", mismatched)
        failed = await admin_access.signed.client.post(
            retry_path,
            headers=admin_access.target.headers
            | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Restore verified checker infrastructure"},
        )
    assert failed.status_code == 503, failed.text
    assert failed.json()["error"]["code"] == "checker_recovery_unavailable"
    assert failed.json()["error"]["retryable"] is True
    async with h.factory() as session:
        after = (
            await session.scalar(select(func.count()).select_from(CheckerRun)),
            await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            await session.scalar(select(func.count()).select_from(OutboxEvent)),
            await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
            )),
        )
        fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
    assert after == before
    assert fence.current_run_id == str(h.created.evaluation_attempt_id)


async def _assert_real_audit_failure_rolls_back(admin_access, h, retry_path):
    key = new_record_id()
    headers = admin_access.target.headers | {"Idempotency-Key": str(key)}
    payload = {"reason": "Restore verified checker infrastructure"}
    async with h.factory() as session:
        evidence_before = tuple(await session.scalars(select(AuditEvent.id).where(
            AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
        ).order_by(AuditEvent.id)))
    async with h.factory.begin() as session:
        await session.execute(text("""
            CREATE FUNCTION test_public_checker_retry_audit_failure()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'public checker retry audit insert rejected'
                USING ERRCODE='23514';
            END $$
        """))
        await session.execute(text("""
            CREATE TRIGGER test_public_checker_retry_audit_failure
            BEFORE INSERT ON audit_events FOR EACH ROW
            WHEN (NEW.event_type='CheckerRetryRequested')
            EXECUTE FUNCTION test_public_checker_retry_audit_failure()
        """))
    failed = await admin_access.signed.client.post(retry_path, headers=headers, json=payload)
    assert failed.status_code == 503, failed.text
    async with h.factory() as session:
        assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
        assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        assert tuple(await session.scalars(select(AuditEvent.id).where(
            AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
        ).order_by(AuditEvent.id))) == evidence_before
        fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
        assert fence.current_run_id == str(h.created.evaluation_attempt_id)
    async with h.factory.begin() as session:
        await session.execute(text(
            "DROP TRIGGER test_public_checker_retry_audit_failure ON audit_events"
        ))
        await session.execute(text("DROP FUNCTION test_public_checker_retry_audit_failure()"))
    return headers, payload


async def _create_and_replay(admin_access, h, retry_path, headers, payload, item, grant):
    created = await admin_access.signed.client.post(retry_path, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    result = created.json()
    assert result["source"] == item["source"]
    assert result["successor"]["generation"] == 2
    async with h.factory() as session:
        committed = {
            "runs": await session.scalar(select(func.count()).select_from(CheckerRun)),
            "receipts": await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            "events": await session.scalar(select(func.count()).select_from(OutboxEvent)),
            "business_audits": await session.scalar(select(func.count()).select_from(
                AuditEvent
            ).where(
                AuditEvent.event_type == LifecycleAuditEventType.CHECKER_RETRY_REQUESTED.value
            )),
        }
        original_allows = [entry for entry in await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(admin_access.target.id),
            AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value,
        ).order_by(AuditEvent.id)) if entry.after_facts.get("allowed")]
        assert len(original_allows) == 1
        original_allow_ids = tuple(entry.id for entry in original_allows)
    replay = await admin_access.signed.client.post(retry_path, headers=headers, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json() == result
    before_stale_retry = await _retry_facts(h)
    stale_retry = await admin_access.signed.client.post(
        retry_path,
        headers=admin_access.target.headers | {"Idempotency-Key": str(new_record_id())},
        json=payload,
    )
    assert stale_retry.status_code == 404, stale_retry.text
    assert stale_retry.json()["error"]["code"] == "checker_recovery_source_not_found"
    assert await _retry_facts(h) == before_stale_retry
    async with h.factory() as session:
        assert committed == {
            "runs": await session.scalar(select(func.count()).select_from(CheckerRun)),
            "receipts": await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            "events": await session.scalar(select(func.count()).select_from(OutboxEvent)),
            "business_audits": await session.scalar(select(func.count()).select_from(
                AuditEvent
            ).where(
                AuditEvent.event_type == LifecycleAuditEventType.CHECKER_RETRY_REQUESTED.value
            )),
        }
        allows = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(admin_access.target.id),
            AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value,
        ).order_by(AuditEvent.id)))
        allows = [entry for entry in allows if entry.after_facts.get("allowed")]
        assert tuple(entry.id for entry in allows) == original_allow_ids
        assert all(
            entry.matched_grant_id == grant
            and entry.permission_id == "operations.checker.retry"
            and entry.project_id == str(h.request.project_id)
            and entry.resource_type == "checker_run"
            and entry.resource_id == str(h.created.evaluation_attempt_id)
            for entry in allows
        )
    return result


async def _assert_conflict_retried_and_revoked(
    admin_access, h, discovery_path, retry_path, wrong_retry, headers, payload, result, grant,
):
    conflict = await admin_access.signed.client.post(
        retry_path, headers=headers, json={"reason": "A different recovery assertion"},
    )
    assert conflict.status_code == 409, conflict.text
    wrong_replay = await admin_access.signed.client.post(
        wrong_retry, headers=headers, json=payload,
    )
    assert wrong_replay.status_code == 404, wrong_replay.text
    page = await admin_access.signed.client.get(
        discovery_path, headers=admin_access.target.headers,
    )
    assert page.status_code == 200, page.text
    retried = page.json()["items"][0]
    assert retried["recovery_state"] == "retried"
    assert retried["retry_receipt_id"] == result["receipt_id"]
    assert retried["successor"] == result["successor"]
    revoked = await admin_access.signed.revoke(
        admin_access.admin, grant, reason="End terminal checker recovery duty",
    )
    assert revoked.status_code == 200, revoked.text
    refused_read = await admin_access.signed.client.get(
        discovery_path, headers=admin_access.target.headers,
    )
    refused_replay = await admin_access.signed.client.post(
        retry_path, headers=headers, json=payload,
    )
    assert refused_read.status_code == refused_replay.status_code == 404
    async with h.factory() as session:
        decisions = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(admin_access.target.id),
            AuditEvent.action_id.in_((
                ActionId.OPERATIONS_CHECKER_RETRY_SOURCE_LIST.value,
                ActionId.OPERATIONS_CHECKER_RETRY.value,
            )),
        )))
        denials = [entry for entry in decisions if entry.after_facts.get("allowed") is False]
        assert {
            ActionId.OPERATIONS_CHECKER_RETRY_SOURCE_LIST.value,
            ActionId.OPERATIONS_CHECKER_RETRY.value,
        }.issubset({entry.action_id for entry in denials})
        assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1


async def test_public_operator_discovers_retries_replays_and_observes_revocation(
    tmp_path, auth_database_env, monkeypatch, admin_access,
):
    async with _failed_source(tmp_path, auth_database_env, monkeypatch) as (h, _delivery):
        discovery_path, retry_path = _recovery_paths(h)
        project_grant = await _assert_project_manager_concealed(
            admin_access, h, discovery_path, retry_path,
        )
        system_grant, item = await _operator_discovery(admin_access, h, discovery_path)
        await _assert_concealed_discovery_principals(
            admin_access, h, discovery_path, retry_path,
        )
        wrong_retry = await _wrong_project_refuses_before_task_lock(admin_access, h)
        await _assert_internal_reservation_failure_rolls_back(
            admin_access, h, retry_path, monkeypatch,
        )
        headers, payload = await _assert_real_audit_failure_rolls_back(
            admin_access, h, retry_path,
        )
        result = await _create_and_replay(
            admin_access, h, retry_path, headers, payload, item, system_grant,
        )
        await _assert_conflict_retried_and_revoked(
            admin_access, h, discovery_path, retry_path, wrong_retry,
            headers, payload, result, system_grant,
        )
        assert project_grant != system_grant


async def test_public_retry_real_outbox_conflict_is_retryable_and_rolls_back(
    tmp_path, auth_database_env, monkeypatch, admin_access,
):
    async with _failed_source(tmp_path, auth_database_env, monkeypatch) as (h, _delivery):
        await admin_access.signed.grant(admin_access.admin, admin_access.target)
        _discovery_path, retry_path = _recovery_paths(h)
        async with h.factory.begin() as session:
            await outbox_append(session).append(OutboxAppendInput(
                event_type="RetryCollision", event_version=1,
                aggregate_type="submission", aggregate_id=h.request.submission_id,
                project_id=h.request.project_id,
                correlation_id=str(h.created.evaluation_attempt_id),
                idempotency_key=(
                    "checker-retry:" + str(h.created.evaluation_attempt_id)
                ),
                payload={"collision": "reserved by another producer"},
            ))
        async with h.factory() as session:
            before = (
                await session.scalar(select(func.count()).select_from(CheckerRun)),
                await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
                await session.scalar(select(func.count()).select_from(OutboxEvent)),
                await session.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
                )),
            )
        failed = await admin_access.signed.client.post(
            retry_path,
            headers=admin_access.target.headers
            | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Restore verified checker infrastructure"},
        )
        assert failed.status_code == 503, failed.text
        assert failed.json()["error"]["code"] == "checker_recovery_unavailable"
        assert failed.json()["error"]["retryable"] is True
        assert "reserved by another producer" not in failed.text
        async with h.factory() as session:
            after = (
                await session.scalar(select(func.count()).select_from(CheckerRun)),
                await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
                await session.scalar(select(func.count()).select_from(OutboxEvent)),
                await session.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
                )),
            )
            fence = await session.get(
                CheckerSubmissionFence, str(h.request.submission_id)
            )
        assert after == before
        assert fence.current_run_id == str(h.created.evaluation_attempt_id)


async def _named_retry(h, operator, name, *, named=None, backend_pids=None):
    async with h.factory.begin() as session:
        await session.execute(
            text("select set_config('application_name', :name, true)"), {"name": name}
        )
        if backend_pids is not None:
            backend_pids.append(await session.scalar(text("select pg_backend_pid()")))
        if named is not None:
            named.set()
        return await checker_retry_service(session, operator).retry(_command(h, operator))


async def _named_claim(h, operator, name):
    key = operator.request_id
    async with h.factory() as session:
        await session.execute(
            text("select set_config('application_name', :name, false)"), {"name": name}
        )
        await session.commit()
        try:
            return await task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, operator),
                audit=task_transition_audit(session),
                actor_profile_id=operator.actor_profile_id,
                settings=get_settings(),
            ).claim(
                h.request.task_id,
                "Claim cannot replace a submitted assignment",
                idempotency_key=key,
            )
        finally:
            await session.rollback()
            await session.execute(
                text("select set_config('application_name', '', false)")
            )
            await session.commit()


async def _retry_facts(h):
    async with h.factory() as session:
        fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
        return (
            await session.scalar(select(func.count()).select_from(CheckerRun)),
            await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            await session.scalar(select(func.count()).select_from(OutboxEvent)),
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)
            ),
            str(fence.current_run_id),
        )


async def _revocation_setup(h, operator):
    async with h.factory() as session:
        grant = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.target_actor_profile_id == str(operator.actor_profile_id),
                AdminRoleGrant.role == "operator",
                AdminRoleGrant.status == "active",
            )
        )
        assert grant is not None
        revoker_link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == grant.granted_by_actor_profile_id,
                ActorIdentityLink.status == "active",
            )
        )
        assert revoker_link is not None
        grant_id = grant.id
        revoker_actor_id = grant.granted_by_actor_profile_id
        revoker_link_id = revoker_link.id
    key = new_record_id()
    revoker = _context(
        actor_profile_id=UUID(revoker_actor_id),
        identity_link_id=UUID(revoker_link_id),
    ).model_copy(update={"request_id": key, "correlation_id": key})
    return grant_id, revoker


async def _named_revoke(h, grant_id, revoker, name, *, named=None, backend_pids=None):
    reason = "Revoke Operator authority during checker recovery"
    request = AdminRoleGrantRevokeRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        grant_id=grant_id,
        reason_digest=derive_reason_digest(reason),
    )
    async with h.factory.begin() as session:
        await session.execute(
            text("select set_config('application_name', :name, true)"), {"name": name}
        )
        if backend_pids is not None:
            backend_pids.append(await session.scalar(text("select pg_backend_pid()")))
        if named is not None:
            named.set()
        service = AdminRoleGrantService(session)
        reservation = await service.reserve(
            idempotency_key=revoker.request_id,
            actor_profile_id=revoker.actor_profile_id,
            request=request,
        )
        assert reservation.outcome == "claimed"
        decision = await AuthorizationService(session, revoker).require(
            ActionId.ADMIN_ROLE_GRANT_REVOKE,
            AdminRoleGrantResourceContext(
                resource_type="admin_role_grant", resource_id=grant_id
            ),
        )
        return await service.complete_revoke(
            claim=reservation.claim,
            request=request,
            decision=decision,
            actor_profile_id=revoker.actor_profile_id,
            reason=reason,
        )


async def test_task_wait_holds_no_retry_authority_custody(
    tmp_path, isolated_database_env, monkeypatch
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _):
        operator = await _operator_for(h)
        name = f"checker-retry-task-wait-{new_record_id().hex}"
        async with h.factory.begin() as holder:
            assert await TaskRepository(holder).lock_project_task(
                h.request.project_id, h.request.task_id
            ) is not None
            call = asyncio.create_task(_named_retry(h, operator, name))
            try:
                await asyncio.wait_for(
                    wait_for_named_database_lock(isolated_database_env, name), 30
                )
                async with h.factory.begin() as probe:
                    assert await probe.scalar(
                        select(AuthorityControl)
                        .where(AuthorityControl.id == 1)
                        .with_for_update(nowait=True)
                    ) is not None
                    assert await probe.scalar(
                        select(ActorProfile)
                        .where(ActorProfile.id == str(operator.actor_profile_id))
                        .with_for_update(nowait=True)
                    ) is not None
                    assert await probe.scalar(
                        select(ActorIdentityLink)
                        .where(ActorIdentityLink.id == str(operator.identity_link_id))
                        .with_for_update(nowait=True)
                    ) is not None
                    grant = await probe.scalar(
                        select(AdminRoleGrant)
                        .where(
                            AdminRoleGrant.target_actor_profile_id
                            == str(operator.actor_profile_id),
                            AdminRoleGrant.status == "active",
                        )
                        .with_for_update(nowait=True)
                    )
                    assert grant is not None
                assert await _retry_facts(h) == (
                    1,
                    0,
                    1,
                    0,
                    str(h.created.evaluation_attempt_id),
                )
            except BaseException:
                call.cancel()
                await asyncio.gather(call, return_exceptions=True)
                raise
        created = await asyncio.wait_for(call, 60)
        assert created.successor.generation == 2
        assert (await _retry_facts(h))[:4] == (2, 1, 2, 1)


@pytest.mark.parametrize("first", ["retry", "claim"])
async def test_retry_and_claim_keep_task_before_authority(
    tmp_path, isolated_database_env, monkeypatch, first
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _):
        operator = await _operator_for(h)
        claim_key = new_record_id()
        claim_actor = operator.model_copy(
            update={"request_id": claim_key, "correlation_id": claim_key}
        )
        held, release = asyncio.Event(), asyncio.Event()
        holder_name = f"checker-{first}-authority-holder"
        waiter_name = f"checker-{first}-task-wait-{new_record_id().hex}"
        reached_authority: list[str] = []
        original = AdminAuthorizationRepository.lock_request_actor

        async def pause_holder(repository, *args, **kwargs):
            locked = await original(repository, *args, **kwargs)
            task = asyncio.current_task()
            assert task is not None
            reached_authority.append(task.get_name())
            if task.get_name() == holder_name:
                held.set()
                await release.wait()
            return locked

        invoke = {
            "retry": lambda name: _named_retry(h, operator, name),
            "claim": lambda name: _named_claim(h, claim_actor, name),
        }
        second = "claim" if first == "retry" else "retry"
        tasks = []
        with monkeypatch.context() as patch:
            patch.setattr(AdminAuthorizationRepository, "lock_request_actor", pause_holder)
            try:
                tasks.append(asyncio.create_task(invoke[first](holder_name), name=holder_name))
                await asyncio.wait_for(held.wait(), 30)
                tasks.append(asyncio.create_task(invoke[second](waiter_name), name=waiter_name))
                await asyncio.wait_for(
                    wait_for_named_database_lock(isolated_database_env, waiter_name), 30
                )
                assert waiter_name not in reached_authority
                release.set()
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 90
                )
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        assert sum(not isinstance(result, BaseException) for result in results) == 1
        assert sum(isinstance(result, TaskAuthorityDenied) for result in results) == 1, [
            type(result).__name__ for result in results
        ]
        assert (await _retry_facts(h))[:4] == (2, 1, 2, 1)
        async with h.factory() as session:
            assert await session.scalar(
                select(func.count())
                .select_from(TaskCommandReceipt)
                .where(TaskCommandReceipt.idempotency_key == claim_key)
            ) == 0


@pytest.mark.parametrize("first", ["retry", "revoke"])
async def test_retry_and_operator_revocation_commit_one_authorized_order(
    tmp_path, isolated_database_env, monkeypatch, first
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _):
        operator = await _operator_for(h)
        grant_id, revoker = await _revocation_setup(h, operator)
        held, release = asyncio.Event(), asyncio.Event()
        retry_name = f"checker-retry-revoc-{first}-{new_record_id().hex}"
        revoke_name = f"checker-grant-revoc-{first}-{new_record_id().hex}"
        assert max(len(retry_name), len(revoke_name)) <= 63
        named = {"retry": asyncio.Event(), "revoke": asyncio.Event()}
        backend_pids: dict[str, list[int]] = {"retry": [], "revoke": []}
        original_consume = PreparedCheckerRetryAuthorization.consume
        original_revoke = AdminRoleGrantService.complete_revoke

        async def pause_retry(authority, handle, facts, successor):
            receipt = await original_consume(authority, handle, facts, successor)
            if first == "retry":
                held.set()
                await release.wait()
            return receipt

        async def pause_revoke(service, **kwargs):
            response = await original_revoke(service, **kwargs)
            if first == "revoke":
                held.set()
                await release.wait()
            return response

        calls = []
        with monkeypatch.context() as patch:
            patch.setattr(PreparedCheckerRetryAuthorization, "consume", pause_retry)
            patch.setattr(AdminRoleGrantService, "complete_revoke", pause_revoke)
            try:
                if first == "retry":
                    calls.append(asyncio.create_task(_named_retry(
                        h, operator, retry_name,
                        named=named["retry"], backend_pids=backend_pids["retry"],
                    )))
                else:
                    calls.append(
                        asyncio.create_task(
                            _named_revoke(
                                h, grant_id, revoker, revoke_name,
                                named=named["revoke"], backend_pids=backend_pids["revoke"],
                            )
                        )
                    )
                await asyncio.wait_for(held.wait(), 30)
                if first == "retry":
                    calls.append(
                        asyncio.create_task(
                            _named_revoke(
                                h, grant_id, revoker, revoke_name,
                                named=named["revoke"], backend_pids=backend_pids["revoke"],
                            )
                        )
                    )
                    waiter_name = revoke_name
                    waiter_role = "revoke"
                else:
                    calls.append(asyncio.create_task(_named_retry(
                        h, operator, retry_name,
                        named=named["retry"], backend_pids=backend_pids["retry"],
                    )))
                    waiter_name = retry_name
                    waiter_role = "retry"
                await asyncio.wait_for(named[waiter_role].wait(), 30)
                assert len(backend_pids[first]) == len(backend_pids[waiter_role]) == 1
                observer = asyncio.create_task(
                    wait_for_named_database_lock(
                        isolated_database_env, waiter_name,
                        expected_waiter_pid=backend_pids[waiter_role][0],
                        expected_blocker_pid=backend_pids[first][0],
                    )
                )
                try:
                    done, _ = await asyncio.wait(
                        {observer, calls[-1]}, timeout=30,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if observer in done:
                        await observer
                    elif calls[-1] in done:
                        result = await asyncio.gather(calls[-1], return_exceptions=True)
                        pytest.fail(f"contender finished before named lock: {result[0]!r}")
                    else:
                        pytest.fail("contender did not reach the named lock")
                finally:
                    observer.cancel()
                    await asyncio.gather(observer, return_exceptions=True)
                release.set()
                results = await asyncio.wait_for(
                    asyncio.gather(*calls, return_exceptions=True), 90
                )
            finally:
                release.set()
                for call in calls:
                    if not call.done():
                        call.cancel()
                await asyncio.gather(*calls, return_exceptions=True)
        async with h.factory() as session:
            grant = await session.get(AdminRoleGrant, grant_id)
            assert grant.status == "revoked" and grant.version == 2
        if first == "retry":
            assert all(not isinstance(result, BaseException) for result in results)
            assert (await _retry_facts(h))[:4] == (2, 1, 2, 1)
        else:
            assert sum(isinstance(result, CheckerExecutionUnavailable) for result in results) == 1
            assert (await _retry_facts(h)) == (
                1,
                0,
                1,
                0,
                str(h.created.evaluation_attempt_id),
            )
