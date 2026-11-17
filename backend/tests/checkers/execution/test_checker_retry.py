"""A real missing-artifact infrastructure result can be superseded once by an Operator."""

import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import hashlib
import json
import os

import pytest
from pydantic import SecretStr
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.checkers import checker_retry_service, evaluation_coordinator
from app.adapters.outbox import outbox_append
from app.adapters.tasks import task_post_submit_outcome
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactObjectMissingError
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.checker_retry_read import (
    CheckerRetryDiscoveryAuthorization,
)
from app.modules.authorization.checker_retry_authorization import (
    PreparedCheckerRetryAuthorization,
)
from app.modules.authorization.domain.action_groups import supports_prepared_denial
from app.modules.authorization.domain.audit import (
    AuthorizationDecision,
    AuthorizationDenialCode,
)
from app.modules.authorization.domain.audit_targets import project_authority_audit_target
from app.modules.authorization.domain.checker_retry_reads import (
    CheckerRetrySourceReadResourceContext,
)
from app.modules.authorization.domain.checker_retry import (
    CheckerRetryPrepareDenialResourceContext,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationDenied,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    PreparedAuthorizationUnsupported,
)
from app.modules.audit.schemas import (
    ActorReferenceKind, AuthorityAuditEventInput, AuthorityEventType,
    LifecycleAuditEntityType, LifecycleAuditEventInput, LifecycleAuditEventType,
    LifecycleAuditReason, LifecycleAuditReferenceKind,
)
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable, CheckerRequestConflict, CheckerRetryAuthorityDenied,
    CheckerRetryCommand,
    CheckerRetryOperationUnavailable,
    CheckerRetryPreparation, CheckerRetryRequest, CheckerRetrySource,
    CheckerRetrySourcePosition, CheckerRetrySourceQuery,
    CheckerRetrySourceUnavailable,
)
from app.modules.checkers.models import CheckerRetryReceipt, CheckerRun, CheckerSubmissionFence
from app.modules.outbox.api import (
    HandlerOutcome, OutboxAppendDisposition, OutboxAppendInput,
    OutboxAppendResult, OutboxIdempotencyConflict,
)
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import AuditEvent, TaskAssignment, WorkstreamTask
from app.modules.tasks.evaluation_delivery import EvaluationDeliveryRequestReader, EvaluationDeliveryUnavailable
from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard
from app.modules.tasks.repository import TaskRepository
from tests.post_submit_materialization_helpers import material_fixture
from tests.checkers.post_submit.support import change_request
from tests.checkers.execution.completion_fixture import completed_evidence
from tests.checkers.execution.support import live_executor, reserve
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)
from tests.reviews.lifecycle.fixtures import live_acceptance_lifecycle as live_acceptance_lifecycle
from tests.tasks.evaluation_delivery.support import delivery_fixture, outcome, state
from tests.tasks.evaluation_delivery.test_worker_materialization import _worker_port
from tests.tasks.post_submit_routing.support import source_values
from tests.tasks.post_submit_routing.outcome_support import invoked_completion
from tests.authorization.post_submit_routing.support import provision_router
from tests.test_artifact_admission import _context, _seed_human_actor


@asynccontextmanager
async def _failed_source(
    tmp_path, isolated_database_env, monkeypatch, provider="local", **material_options,
):
    """Build one real terminal missing-object result through the durable worker."""
    from app.adapters.artifacts.local import LocalStorageAdapter
    from app.adapters.artifacts.s3_compatible import S3CompatibleArtifactStore
    from app.adapters.artifacts import internal_workers

    if provider == "minio":
        from tests import test_s3_artifact_store

        monkeypatch.setattr(
            test_s3_artifact_store, "MINIO_BUCKET", os.environ["WORKSTREAM_TEST_MINIO_BUCKET"]
        )
    async with material_fixture(
        tmp_path, isolated_database_env, provider=provider, **material_options,
    ) as h:
        port = _worker_port(h, monkeypatch)

        def missing(_store, _reference, **kwargs):
            raise ArtifactObjectMissingError("controlled verified object loss")

        try:
            delivery = await delivery_fixture(h, materialization=port)
            with monkeypatch.context() as patch:
                patch.setattr(
                    LocalStorageAdapter if provider == "local" else S3CompatibleArtifactStore,
                    "open_source", missing,
                )
                initial = await delivery.delivery.deliver(
                    h.created.evaluation_event_id, h.request.project_id, "retry-source",
                )
            assert outcome(initial)["delivery_state"] == "acknowledged"
            saved = await state(h)
            assert saved["run"]["status"] == "infrastructure_failed"
            assert json.loads(saved["run"]["result_json"])["infrastructure_failure_code"] == "material_unavailable"
            async with h.factory() as session:
                assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                    OutboxEvent.event_type == "SubmissionFinalizationRequested",
                )) == 1
            yield h, delivery
        finally:
            internal_workers.shutdown_artifact_internal_runtime()


async def _operator_for(h, *, grant=True):
    operator = _context()
    async with h.factory.begin() as session:
        await _seed_human_actor(session, operator)
        if grant:
            await grant_fixture_admin_role(
                session, operator.actor_profile_id, role="operator", scope="system",
            )
    key = new_record_id()
    return operator.model_copy(update={"request_id": key, "correlation_id": key})


def _command(h, operator):
    return CheckerRetryCommand(
        project_id=h.request.project_id,
        source_run_id=h.created.evaluation_attempt_id,
        request_key=operator.request_id,
        reason="Verified artifact storage has been restored",
    )


def _recovery_paths(h, *, project_id=None):
    selected_project = project_id or h.request.project_id
    base = f"/api/v1/operations/projects/{selected_project}"
    return (
        f"{base}/checker-retry-sources",
        f"{base}/checker-runs/{h.created.evaluation_attempt_id}/retry",
    )


async def test_recovery_cursor_binds_project_limit_and_stable_position():
    class Allow:
        def __init__(self):
            self.resources = []

        async def require(self, _action, resource):
            self.resources.append(resource)

    authority = Allow()
    adapter = CheckerRetryDiscoveryAuthorization(
        authority,
        SecretStr(base64.b64encode(bytes(range(32))).decode("ascii")),
    )
    query = CheckerRetrySourceQuery(
        project_id=new_record_id(), limit=25, cursor=None,
    )
    position = CheckerRetrySourcePosition(
        created_at=datetime.now(UTC), source_run_id=new_record_id(),
    )
    cursor = adapter.encode(query, position)
    decoded = await adapter.authorize_and_decode(
        query.model_copy(update={"cursor": cursor})
    )
    assert decoded == position
    for changed in (
        query.model_copy(update={"project_id": new_record_id(), "cursor": cursor}),
        query.model_copy(update={"limit": 26, "cursor": cursor}),
    ):
        with pytest.raises(ValueError, match="invalid checker retry discovery cursor"):
            await adapter.authorize_and_decode(changed)
    assert len(authority.resources) == 3
    assert len({resource.request_digest for resource in authority.resources}) == 3


def test_recovery_read_builds_canonical_project_decision_and_audit_event():
    """The recovery page reuses AUTH's closed project evidence vocabulary."""
    project_id = new_record_id()
    actor_id = new_record_id()
    decision_id = new_record_id()
    request_id = new_record_id()
    digest = "sha256:" + "1" * 64
    resource = CheckerRetrySourceReadResourceContext(
        resource_id=project_id,
        scope_project_id=project_id,
        request_digest=digest,
    )
    decision = AuthorizationDecision(
        decision_id=decision_id,
        action_id=ActionId.OPERATIONS_CHECKER_RETRY_SOURCE_LIST,
        permission_id=PermissionId.OPERATIONS_STATUS_READ,
        allowed=False,
        denial_code=AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        resource_type=resource.resource_type,
        resource_id=resource.resource_id,
        resource_context_digest=digest,
        matched_authority_kind=None,
        revalidated=True,
        request_id=request_id,
        correlation_id=request_id,
    )
    target = project_authority_audit_target(resource, decision.action_id)
    assert target == (
        str(project_id), "project", str(project_id), "project", str(project_id),
    )
    event = AuthorityAuditEventInput(
        event_id=decision_id,
        event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
        entity_type="authorization_decision",
        entity_id=str(decision_id),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        request_id=request_id,
        correlation_id=request_id,
        permission_id=decision.permission_id,
        action_id=decision.action_id,
        project_id=target[0],
        resource_type=target[1],
        resource_id=target[2],
        target_ref_kind=target[3],
        target_ref_id=target[4],
        reason="authorization_evaluation",
        denial_code=decision.denial_code.value,
        after_facts={"allowed": False, "resource_context_digest": digest},
    )
    assert event.resource_type == "project"
    assert event.permission_id is PermissionId.OPERATIONS_STATUS_READ


async def test_retry_prepare_unsupported_is_exact_typed_denial():
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

    class Prepared:
        def __init__(self):
            self.closed = 0
            self.resource = None

        async def prepare(self, *_args):
            raise PreparedAuthorizationUnsupported(
                AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            )

        async def deny_unsupported(self, action, caller_input, resource, denial):
            assert action is ActionId.OPERATIONS_CHECKER_RETRY
            assert caller_input.idempotency_key == key
            assert denial.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            self.resource = resource
            raise AuthorizationDenied(AuthorizationDecision(
                decision_id=new_record_id(),
                action_id=ActionId.OPERATIONS_CHECKER_RETRY,
                permission_id=PermissionId.OPERATIONS_CHECKER_RETRY,
                allowed=False,
                denial_code=AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
                resource_type=resource.resource_type,
                resource_id=resource.resource_id,
                resource_context_digest=canonical_json_hash(resource.model_dump(mode="json")),
                matched_authority_kind=None,
                revalidated=False,
                request_id=key,
                correlation_id=key,
            ))

        def close(self):
            self.closed += 1

    prepared = Prepared()
    owner = object.__new__(PreparedCheckerRetryAuthorization)
    owner._context = context
    owner._service = prepared
    with pytest.raises(
        CheckerRetryAuthorityDenied,
        match="checker_retry_authority_unavailable",
    ) as denied:
        await owner.prepare(preparation)
    assert isinstance(denied.value.__cause__, AuthorizationDenied)
    assert prepared.closed == 1
    assert type(prepared.resource) is CheckerRetryPrepareDenialResourceContext
    assert supports_prepared_denial(
        ActionId.OPERATIONS_CHECKER_RETRY, prepared.resource,
    )
    assert project_authority_audit_target(
        prepared.resource, ActionId.OPERATIONS_CHECKER_RETRY,
    ) == (
        str(source.project_id), "checker_run", str(source.source_run_id),
        "project", str(source.project_id),
    )


def test_retry_reason_rejects_ascii_del_at_all_typed_boundaries():
    source = CheckerRetrySource(
        project_id=new_record_id(), task_id=new_record_id(),
        assignment_id=new_record_id(), submission_id=new_record_id(),
        submission_version=1, source_run_id=new_record_id(),
        source_request_id=new_record_id(), source_request_digest="sha256:" + "0" * 64,
        source_result_id=new_record_id(), source_result_digest="sha256:" + "1" * 64,
        source_finalize_evidence_id=new_record_id(), source_generation=1,
        failure_code="material_unavailable",
    )
    actor_id, key = new_record_id(), new_record_id()
    valid = "Restore verified checker infrastructure"
    assert CheckerRetryCommand(
        project_id=source.project_id, source_run_id=source.source_run_id,
        request_key=key, reason=valid,
    ).reason == valid
    assert CheckerRetryPreparation(
        actor_profile_id=actor_id, request_key=key, reason=valid, source=source,
    ).reason == valid
    assert CheckerRetryRequest(reason=valid).reason == valid
    with pytest.raises(ValueError, match="checker retry reason is invalid"):
        CheckerRetryCommand(
            project_id=source.project_id, source_run_id=source.source_run_id,
            request_key=key, reason=valid + "\x7f",
        )
    with pytest.raises(ValueError, match="checker retry reason is invalid"):
        CheckerRetryPreparation(
            actor_profile_id=actor_id, request_key=key, reason=valid + "\x7f", source=source,
        )
    run_id = new_record_id()
    audit = {
        "event_id": new_record_id(),
        "entity_type": LifecycleAuditEntityType.CHECKER_RUN,
        "entity_id": run_id,
        "event_type": LifecycleAuditEventType.CHECKER_RETRY_REQUESTED,
        "actor_id": actor_id,
        "reason": LifecycleAuditReason.FACT_RECORDED,
        "authorization_resource_digest": "sha256:" + "2" * 64,
        "references": {
            LifecycleAuditReferenceKind.PROJECT: source.project_id,
            LifecycleAuditReferenceKind.TASK: source.task_id,
            LifecycleAuditReferenceKind.ASSIGNMENT: source.assignment_id,
            LifecycleAuditReferenceKind.SUBMISSION: source.submission_id,
            LifecycleAuditReferenceKind.CHECKER_RUN: run_id,
            LifecycleAuditReferenceKind.SOURCE_CHECKER_RUN: source.source_run_id,
            LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: new_record_id(),
            LifecycleAuditReferenceKind.OUTBOX_EVENT: new_record_id(),
        },
    }
    assert LifecycleAuditEventInput(**audit, operator_reason=valid).operator_reason == valid
    with pytest.raises(ValueError, match="invalid Operator reason"):
        LifecycleAuditEventInput(**audit, operator_reason=valid + "\x7f")
    with pytest.raises(ValueError, match="checker retry reason is invalid"):
        CheckerRetryRequest(reason=valid + "\x7f")


def _copied_audit_event(event, **changes):
    values = {
        column.name: getattr(event, column.name)
        for column in AuditEvent.__table__.columns
    }
    return AuditEvent(**(values | changes))


async def test_retry_sql_rejects_unreceipted_terminal_supersession(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        direct_successor = change_request(
            h.request, evaluation_request_id=new_record_id(), evaluation_generation=2,
        )
        with pytest.raises(IntegrityError, match="terminal checker infrastructure retry requires Operator receipt"):
            async with h.factory.begin() as session:
                await evaluation_coordinator(session).reserve_current_evaluation(direct_successor)
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2


async def test_retry_sql_rejects_crossed_receipt_with_real_authority_participants(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        captured = []
        original_add = AsyncSession.add

        def omit_only_receipt(session, value):
            if isinstance(value, CheckerRetryReceipt):
                captured.append(value)
                return
            return original_add(session, value)

        substitutions = (
            ("reason", "crossed Operator reason"),
            ("request_key", str(new_record_id())),
            ("source_result_id", str(new_record_id())),
            ("successor_run_id", str(command.source_run_id)),
            ("event_id", h.created.evaluation_event_id),
            ("authorization_decision_id", None),
        )
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "add", omit_only_receipt)
            for field, crossed in substitutions:
                captured.clear()
                with pytest.raises(IntegrityError, match="checker retry receipt closure invalid|terminal checker infrastructure retry requires Operator receipt"):
                    async with h.factory.begin() as session:
                        created = await checker_retry_service(session, operator).retry(command)
                        assert len(captured) == 1
                        receipt = captured[0]
                        values = {
                            column.name: getattr(receipt, column.name)
                            for column in CheckerRetryReceipt.__table__.columns
                            if column.name != "created_at"
                        }
                        values[field] = (
                            str(created.source.source_finalize_evidence_id)
                            if field == "authorization_decision_id" else crossed
                        )
                        await session.execute(insert(CheckerRetryReceipt).values(**values))
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(command.source_run_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
        async with h.factory.begin() as session:
            valid = await checker_retry_service(session, operator).retry(command)
        assert valid.successor.generation == 2


async def test_retry_sql_rejects_noncanonical_authority_resource_even_with_matching_raw_hash(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        captured = []
        original_add = AsyncSession.add

        def omit_only_receipt(session, value):
            if isinstance(value, CheckerRetryReceipt):
                captured.append(value)
                return
            return original_add(session, value)

        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "add", omit_only_receipt)
            with pytest.raises(IntegrityError, match="resource_json_digest"):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, operator).retry(_command(h, operator))
                    assert len(captured) == 1
                    receipt = captured[0]
                    values = {
                        column.name: getattr(receipt, column.name)
                        for column in CheckerRetryReceipt.__table__.columns
                        if column.name != "created_at"
                    }
                    authority_id = str(new_record_id())
                    initiation_id = str(new_record_id())
                    resource = json.loads(receipt.resource_json)
                    resource["resource_context"]["successor"]["audit_event_id"] = initiation_id
                    values["resource_json"] = " " + json.dumps(
                        resource, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                    )
                    values["resource_digest"] = "sha256:" + hashlib.sha256(
                        values["resource_json"].encode("utf-8")
                    ).hexdigest()
                    authority = await session.get(AuditEvent, receipt.authorization_decision_id)
                    initiation = await session.get(AuditEvent, receipt.audit_event_id)
                    assert authority is not None and initiation is not None
                    references = dict(initiation.event_payload["references"])
                    references["authorization_decision_id"] = authority_id
                    session.add(_copied_audit_event(
                        authority, id=authority_id, entity_id=authority_id,
                        after_facts={"allowed": True, "resource_context_digest": values["resource_digest"]},
                    ))
                    session.add(_copied_audit_event(
                        initiation, id=initiation_id,
                        event_payload={
                            **initiation.event_payload,
                            "references": references,
                            "authorization_resource_digest": values["resource_digest"],
                        },
                    ))
                    await session.flush()
                    values["authorization_decision_id"] = authority_id
                    values["audit_event_id"] = initiation_id
                    await session.execute(insert(CheckerRetryReceipt).values(**values))
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
        async with h.factory.begin() as session:
            valid = await checker_retry_service(session, operator).retry(_command(h, operator))
        assert valid.successor.generation == 2


async def test_retry_sql_actor_status_validation_preserves_fresh_historical_replay(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        async with h.factory() as session:
            await session.begin()
            valid = text("select public.checker_retry_receipt_valid(:receipt_id)")
            assert await session.scalar(valid, {"receipt_id": created.receipt_id}) is True
            await session.execute(text("""
                update actor_profiles set status='suspended', suspended_by='test',
                  suspended_at=clock_timestamp(), suspension_reason='test'
                where id=:actor_id
            """), {"actor_id": operator.actor_profile_id})
            assert await session.scalar(valid, {"receipt_id": created.receipt_id}) is False
            await session.rollback()
        async with h.factory.begin() as session:
            assert await checker_retry_service(session, operator).retry(command) == created


async def test_retry_sql_rejects_outbox_payload_with_false_digest(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.modules.outbox.service import OutboxService

    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        false_digest = "sha256:" + "0" * 64

        async def false_digest_append(service, event):
            event_id = new_record_id()
            await service._repository._session.execute(insert(OutboxEvent).values(
                event_id=event_id, event_type=event.event_type,
                event_version=event.event_version, aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id, project_id=str(event.project_id),
                correlation_id=event.correlation_id,
                causation_event_id=event.causation_event_id,
                idempotency_key=event.idempotency_key,
                payload=event.payload, payload_digest=false_digest,
            ))
            return OutboxAppendResult(
                event_id=event_id, disposition=OutboxAppendDisposition.CREATED,
                payload_digest=false_digest, occurred_at=datetime.now(UTC),
            )

        with monkeypatch.context() as patch:
            patch.setattr(OutboxService, "append", false_digest_append)
            with pytest.raises(IntegrityError, match="checker retry receipt closure invalid|terminal checker infrastructure retry requires Operator receipt"):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, operator).retry(command)
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
        async with h.factory.begin() as session:
            valid = await checker_retry_service(session, operator).retry(command)
        assert valid.successor.generation == 2


async def test_retry_without_operator_grant_denies_without_effects(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h, grant=False)
        with pytest.raises(CheckerExecutionUnavailable, match="checker_retry_authority_unavailable"):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(_command(h, operator))
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
            assert await session.scalar(select(func.count()).select_from(
                AuditEvent
            ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0


async def test_retry_caller_rollback_removes_whole_successor(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        with pytest.raises(RuntimeError, match="planned caller rollback"):
            async with h.factory.begin() as session:
                staged = await checker_retry_service(session, operator).retry(_command(h, operator))
                assert staged.successor.generation == 2
                raise RuntimeError("planned caller rollback")
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
            assert await session.get(CheckerRun, str(staged.successor.run_id)) is None
            assert await session.get(AuditEvent, str(staged.authorization_decision_id)) is None


async def test_retry_audit_failure_removes_whole_successor(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        async with h.factory.begin() as session:
            await session.execute(text("CREATE SEQUENCE test_checker_retry_audit_attempt"))
            await session.execute(text("""
                CREATE FUNCTION test_checker_retry_audit_failure() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                  IF NOT EXISTS (SELECT 1 FROM audit_events
                    WHERE action_id='operations.checker.retry'
                      AND event_type='SensitiveAuthorizationAllowed') THEN
                    RAISE EXCEPTION 'checker retry AUTH was not staged before audit'
                      USING ERRCODE='23514';
                  END IF;
                  PERFORM nextval('test_checker_retry_audit_attempt');
                  RAISE EXCEPTION 'checker retry audit insert rejected' USING ERRCODE='23514';
                END $$
            """))
            await session.execute(text("""
                CREATE TRIGGER test_checker_retry_audit_failure
                BEFORE INSERT ON audit_events FOR EACH ROW
                WHEN (NEW.event_type='CheckerRetryRequested')
                EXECUTE FUNCTION test_checker_retry_audit_failure()
            """))
        try:
            with pytest.raises(IntegrityError, match="checker retry audit insert rejected"):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, operator).retry(_command(h, operator))
            async with h.factory() as session:
                assert (await session.execute(text(
                    "SELECT last_value,is_called FROM test_checker_retry_audit_attempt"
                ))).one() == (1, True)
                assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
                assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
                assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
                fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
                assert fence.current_run_id == str(h.created.evaluation_attempt_id)
                assert await session.scalar(select(func.count()).select_from(
                    AuditEvent
                ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0
                assert await session.scalar(select(func.count()).select_from(
                    AuditEvent
                ).where(AuditEvent.event_type == "CheckerRetryRequested")) == 0
        finally:
            async with h.factory.begin() as session:
                await session.execute(text("DROP TRIGGER test_checker_retry_audit_failure ON audit_events"))
                await session.execute(text("DROP FUNCTION test_checker_retry_audit_failure()"))
                await session.execute(text("DROP SEQUENCE test_checker_retry_audit_attempt"))
        async with h.factory.begin() as session:
            valid = await checker_retry_service(session, operator).retry(_command(h, operator))
        assert valid.successor.generation == 2


async def test_retry_real_outbox_conflict_rolls_back_successor(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            await outbox_append(session).append(OutboxAppendInput(
                event_type="RetryCollision", event_version=1,
                aggregate_type="submission", aggregate_id=h.request.submission_id,
                project_id=h.request.project_id,
                correlation_id=str(command.source_run_id),
                idempotency_key="checker-retry:" + str(command.source_run_id),
                payload={"collision": "reserved by another producer"},
            ))
        with pytest.raises(
            CheckerRetryOperationUnavailable,
            match="checker_retry_outbox_unavailable",
        ) as raised:
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(command)
        assert isinstance(raised.value.__cause__, OutboxIdempotencyConflict)
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(command.source_run_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 3
            assert await session.scalar(select(func.count()).select_from(
                AuditEvent
            ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_retry_known_missing_object_dispatches_new_generation(
    tmp_path, isolated_database_env, monkeypatch, provider,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch, provider) as (h, delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        assert created.source.source_run_id == command.source_run_id
        assert created.successor.generation == h.request.evaluation_generation + 1
        assert created.successor.run_id != created.source.source_run_id
        async with h.factory() as session:
            source = await session.get(CheckerRun, str(command.source_run_id))
            successor = await session.get(CheckerRun, str(created.successor.run_id))
            receipt = await session.get(CheckerRetryReceipt, str(created.receipt_id))
            assert source.status == "infrastructure_failed"
            assert successor.status == "queued"
            assert receipt.source_result_digest == source.result_digest
            assert receipt.successor_request_digest == successor.request_digest
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 3
            authorization = await session.get(AuditEvent, str(created.authorization_decision_id))
            assert authorization.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
            assert authorization.project_id == str(h.request.project_id)
            assert authorization.resource_id == str(command.source_run_id)
            assert authorization.after_facts["resource_context_digest"] == receipt.resource_digest
            audit = await session.get(AuditEvent, str(created.successor.audit_event_id))
            assert audit.project_id is None
            assert audit.event_payload["references"]["project_id"] == str(h.request.project_id)
            assert audit.event_payload["references"]["source_checker_run_id"] == str(command.source_run_id)
            assert audit.event_payload["authorization_resource_digest"] == receipt.resource_digest
        delivered = await delivery.delivery.deliver(
            created.successor.event_id, h.request.project_id, "retry-successor",
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        async with h.factory() as session:
            successor = await session.get(CheckerRun, str(created.successor.run_id))
            assert successor.status == "completed"


async def test_retry_response_loss_and_later_generation_replay(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        async with h.factory.begin() as session:
            replay = await checker_retry_service(session, operator).retry(command)
        assert replay == created
        with pytest.raises(CheckerRequestConflict, match="checker_retry_request_conflict"):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(command.model_copy(update={
                    "reason": "Different reason under the same request key",
                }))
        second_key = new_record_id()
        second_context = operator.model_copy(update={
            "request_id": second_key, "correlation_id": second_key,
        })
        with pytest.raises(CheckerExecutionUnavailable):
            async with h.factory.begin() as session:
                await checker_retry_service(session, second_context).retry(
                    command.model_copy(update={"request_key": second_key})
                )
        delivered = await delivery.delivery.deliver(
            created.successor.event_id, h.request.project_id, "retry-successor",
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        later_request = change_request(
            h.request, evaluation_request_id=new_record_id(), evaluation_generation=3,
        )
        async with h.factory.begin() as session:
            later = await evaluation_coordinator(session).reserve_current_evaluation(later_request)
        assert later.evaluation_generation == 3
        assert later.attempt_id != created.successor.run_id

        async def retained_effects():
            async with h.factory() as session:
                fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
                runs = tuple((await session.scalars(select(CheckerRun.id).order_by(CheckerRun.id))).all())
                receipts = tuple((await session.scalars(
                    select(CheckerRetryReceipt.id).order_by(CheckerRetryReceipt.id)
                )).all())
                events = tuple((await session.scalars(
                    select(OutboxEvent.event_id).order_by(OutboxEvent.event_id)
                )).all())
                decisions = tuple((await session.scalars(select(AuditEvent.id).where(
                    AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value,
                ))).all())
                initiations = tuple((await session.scalars(select(AuditEvent.id).where(
                    AuditEvent.event_type == "CheckerRetryRequested",
                ))).all())
                return fence.current_run_id, runs, receipts, events, decisions, initiations

        before = await retained_effects()
        assert before[0] == str(later.attempt_id)
        assert set(before[1]) == {
            str(command.source_run_id), str(created.successor.run_id), str(later.attempt_id),
        }
        assert tuple(map(len, before[2:])) == (1, 4, 1, 1)
        async with h.factory.begin() as session:
            historical_replay = await checker_retry_service(session, operator).retry(command)
        assert historical_replay == created
        assert await retained_effects() == before
        async with h.factory() as session:
            source = await session.get(CheckerRun, str(command.source_run_id))
            successor = await session.get(CheckerRun, str(created.successor.run_id))
            assert source.status == "infrastructure_failed"
            assert successor.status == "completed"
            assert await session.get(CheckerRun, str(later.attempt_id)) is not None
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 4


async def test_retry_replays_after_real_auto_acceptance_but_new_key_denies(
    tmp_path, isolated_database_env, monkeypatch, live_acceptance_lifecycle,
):
    async with _failed_source(
        tmp_path, isolated_database_env, monkeypatch, human_review_required=False,
    ) as (h, delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        delivered = await delivery.delivery.deliver(
            created.successor.event_id, h.request.project_id, "accepted-retry-successor",
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        async with h.factory.begin() as session:
            accepted = await session.execute(text(
                "UPDATE public.task_assignments SET accepted_at=clock_timestamp() "
                "WHERE id=:id AND accepted_at IS NULL"
            ), {"id": str(h.request.assignment_id)})
            assert accepted.rowcount == 1
        h.source = {}
        h.source = await source_values(h, run_id=created.successor.run_id)
        await provision_router(h.factory)
        completion = await invoked_completion(h)
        async with h.factory() as session, session.begin():
            routed = await task_post_submit_outcome(session, h.factory).apply(
                completion, current_generation=2,
            )
            assert routed.final_acceptance_id is not None

        async def durable_state():
            async with h.factory() as session:
                task = await session.get(WorkstreamTask, str(h.request.task_id))
                assignment = await session.get(TaskAssignment, str(h.request.assignment_id))
                fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
                return (
                    task.status, assignment.status, fence.current_run_id,
                    await session.scalar(select(func.count()).select_from(CheckerRun)),
                    await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
                    await session.scalar(select(func.count()).select_from(OutboxEvent)),
                    await session.scalar(select(func.count()).select_from(AuditEvent).where(
                        AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value,
                    )),
                )

        before = await durable_state()
        assert before[:5] == (
            "accepted", "completed", str(created.successor.run_id), 2, 1,
        )
        opens = len(h.store.opens)
        async with h.factory.begin() as session:
            replay = await checker_retry_service(session, operator).retry(command)
        assert replay == created

        another_key = new_record_id()
        another_operator = operator.model_copy(update={
            "request_id": another_key, "correlation_id": another_key,
        })
        reached = False
        original = TaskEvaluationGuard.lock_terminal_retry_scope

        async def observed(guard, request):
            nonlocal reached
            reached = True
            return await original(guard, request)

        with monkeypatch.context() as patch:
            patch.setattr(TaskEvaluationGuard, "lock_terminal_retry_scope", observed)
            with pytest.raises(
                CheckerRetrySourceUnavailable,
                match="checker_retry_source_unavailable",
            ):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, another_operator).retry(
                        command.model_copy(update={"request_key": another_key})
                    )
        assert reached and len(h.store.opens) == opens
        assert await durable_state() == before


async def test_retry_handler_rejects_crossed_event_and_payload_before_execution(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, delivery):
        operator = await _operator_for(h)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(_command(h, operator))
        claim = await delivery.delivery.claim(
            created.successor.event_id, h.request.project_id, "retry-crossed-envelope",
        )
        assert claim is not None
        envelope = await delivery.delivery._begin_invocation(claim)
        assert envelope is not None
        before, opens = await state(h), len(h.store.opens)
        async with h.factory() as session, session.begin():
            reader = EvaluationDeliveryRequestReader(session, evaluation_coordinator(session))
            exact = await reader.read(envelope)
            assert exact.evaluation_request_id == created.successor.request_id
            crossed = []
            for field, value in (
                ("request_id", str(new_record_id())),
                ("retry_receipt_id", str(new_record_id())),
            ):
                payload = json.loads(envelope.payload_json)
                payload[field] = value
                crossed.append(envelope.model_copy(update={
                    "payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    "claim": envelope.claim.model_copy(update={
                        "payload_digest": canonical_json_hash(payload),
                    }),
                }))
            crossed.append(envelope.model_copy(update={
                "claim": envelope.claim.model_copy(update={
                    "event_id": h.created.evaluation_event_id,
                }),
            }))
            for field, value in (
                ("event_type", "OtherEvaluationRequested"),
                ("event_version", 2),
                ("aggregate_type", "task"),
                ("aggregate_id", new_record_id()),
                ("correlation_id", str(new_record_id())),
                ("causation_event_id", new_record_id()),
                ("idempotency_key", "checker-retry:crossed"),
            ):
                crossed.append(envelope.model_copy(update={field: value}))
            crossed.append(envelope.model_copy(update={
                "claim": envelope.claim.model_copy(update={
                    "payload_digest": canonical_json_hash({"crossed": True}),
                }),
            }))
            for mixed in crossed:
                with pytest.raises(EvaluationDeliveryUnavailable, match="evaluation_delivery_unavailable"):
                    await reader.read(mixed)
                assert await delivery.handler(mixed) is HandlerOutcome.REJECT
        assert await state(h) == before and len(h.store.opens) == opens


@pytest.mark.parametrize("same_key", [True, False])
async def test_independent_sessions_wait_for_task_and_commit_one_retry(
    tmp_path, isolated_database_env, monkeypatch, same_key,
):
    from app.adapters.artifacts.local import LocalStorageAdapter
    from app.adapters.artifacts import internal_workers

    async with material_fixture(tmp_path, isolated_database_env) as h:
        port = _worker_port(h, monkeypatch)

        def missing(_store, _reference, **kwargs):
            raise ArtifactObjectMissingError("controlled verified object loss")

        try:
            delivery = await delivery_fixture(h, materialization=port)
            with monkeypatch.context() as patch:
                patch.setattr(LocalStorageAdapter, "open_source", missing)
                initial = await delivery.delivery.deliver(
                    h.created.evaluation_event_id, h.request.project_id, "concurrent-source",
                )
            assert outcome(initial)["delivery_state"] == "acknowledged"
            assert (await state(h))["run"]["status"] == "infrastructure_failed"

            operator = _context()
            async with h.factory.begin() as session:
                await _seed_human_actor(session, operator)
                await grant_fixture_admin_role(
                    session, operator.actor_profile_id, role="operator", scope="system",
                )
            key = new_record_id()
            operator = operator.model_copy(update={"request_id": key, "correlation_id": key})
            command = CheckerRetryCommand(
                project_id=h.request.project_id,
                source_run_id=h.created.evaluation_attempt_id,
                request_key=key, reason="Restore verified checker infrastructure",
            )
            other_key = key if same_key else new_record_id()
            other_operator = operator.model_copy(update={
                "request_id": other_key, "correlation_id": other_key,
            })
            other_command = command.model_copy(update={"request_key": other_key})

            arrivals: set[int] = set()
            both_arrived = asyncio.Event()
            original_replay = TaskEvaluationGuard.lock_retry_replay_scope
            original_new = TaskEvaluationGuard.lock_terminal_retry_scope

            async def mark_then(method, guard, request):
                arrivals.add(id(guard))
                if len(arrivals) >= 2:
                    both_arrived.set()
                return await method(guard, request)

            async def replay_gate(guard, request):
                return await mark_then(original_replay, guard, request)

            async def new_gate(guard, request):
                return await mark_then(original_new, guard, request)

            async def invoke(context, request):
                async with h.factory.begin() as session:
                    return await checker_retry_service(session, context).retry(request)

            with monkeypatch.context() as patch:
                patch.setattr(TaskEvaluationGuard, "lock_retry_replay_scope", replay_gate)
                patch.setattr(TaskEvaluationGuard, "lock_terminal_retry_scope", new_gate)
                async with h.factory.begin() as holder:
                    assert await TaskRepository(holder).lock_project_task(
                        h.request.project_id, h.request.task_id,
                    ) is not None
                    calls = [
                        asyncio.create_task(invoke(operator, command)),
                        asyncio.create_task(invoke(other_operator, other_command)),
                    ]
                    try:
                        await asyncio.wait_for(both_arrived.wait(), 30)
                        assert all(not call.done() for call in calls)
                        async with h.factory() as observer:
                            assert await observer.scalar(
                                select(func.count()).select_from(CheckerRetryReceipt)
                            ) == 0
                            assert await observer.scalar(select(func.count()).select_from(
                                AuditEvent
                            ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0
                    except BaseException:
                        for call in calls:
                            call.cancel()
                        await asyncio.gather(*calls, return_exceptions=True)
                        raise
                first, second = await asyncio.gather(*calls, return_exceptions=True)
            if same_key:
                assert first == second and not isinstance(first, BaseException)
            else:
                outcomes = (first, second)
                assert sum(not isinstance(result, BaseException) for result in outcomes) == 1
                assert sum(isinstance(result, CheckerExecutionUnavailable) for result in outcomes) == 1
            async with h.factory() as session:
                assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
                assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 3
                assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value,
                )) == 1
        finally:
            internal_workers.shutdown_artifact_internal_runtime()


async def _assert_nonterminal_source_reaches_guard(h, monkeypatch, expected_status):
    operator = await _operator_for(h)
    command = _command(h, operator)
    before_opens = len(h.store.opens)
    async with h.factory() as session:
        before_events = await session.scalar(select(func.count()).select_from(OutboxEvent))
        assert (await session.get(CheckerRun, str(command.source_run_id))).status == expected_status
    reached = False
    original = TaskEvaluationGuard.lock_terminal_retry_scope

    async def observed(guard, request):
        nonlocal reached
        await original(guard, request)
        reached = True

    with monkeypatch.context() as patch:
        patch.setattr(TaskEvaluationGuard, "lock_terminal_retry_scope", observed)
        with pytest.raises(CheckerExecutionUnavailable, match="checker_retry_source_unavailable"):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(command)
    assert reached and len(h.store.opens) == before_opens
    async with h.factory() as session:
        assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before_events


async def test_queued_source_reaches_valid_task_guard_then_refuses_terminal_retry(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await _assert_nonterminal_source_reaches_guard(h, monkeypatch, "queued")


async def test_running_source_reaches_valid_task_guard_then_refuses_terminal_retry(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        lease, replay = await live_executor(h)._claim(h.request)
        assert replay is None and lease.reservation.attempt_id == h.created.evaluation_attempt_id
        await _assert_nonterminal_source_reaches_guard(h, monkeypatch, "running")


@pytest.mark.parametrize("recommendation", ["allow_review", "needs_revision"])
async def test_completed_source_reaches_valid_task_guard_then_refuses_terminal_retry(
    tmp_path, isolated_database_env, monkeypatch, recommendation,
):
    async with completed_evidence(tmp_path, isolated_database_env, recommendation) as h:
        assert h.result.outcome == "completed" and h.run.routing_recommendation == recommendation
        await _assert_nonterminal_source_reaches_guard(h, monkeypatch, "completed")


async def test_expired_unfinished_transport_reclaims_same_run_without_retry_receipt(
    tmp_path, isolated_database_env, monkeypatch,
):
    import app.modules.checkers.execution as execution

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        with monkeypatch.context() as patch:
            patch.setattr(executor, "_execution_budget_seconds", lambda _request: 1)
            patch.setattr(execution, "SELECTED_POST_FINALIZATION_MARGIN_MS", 9_000)
            first, replay = await executor._claim(h.request)
        assert replay is None
        async with h.factory() as session:
            await session.execute(text(
                "SELECT pg_sleep(GREATEST(EXTRACT(EPOCH FROM "
                "CAST(:expiry AS timestamptz)-clock_timestamp()),0)+0.05)"
            ), {"expiry": first.expires_at})
            assert await session.scalar(text("SELECT clock_timestamp()>=:expiry"),
                                        {"expiry": first.expires_at})
        second, replay = await executor._claim(h.request)
        assert replay is None
        assert second.reservation == first.reservation
        assert second.lease_generation == first.lease_generation + 1
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(first.reservation.attempt_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0


async def test_retry_fences_failed_source_from_stale_worker_and_current_result(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        executor = live_executor(h)
        lease, replay = await executor._claim(h.request)
        assert lease is None and replay is not None
        operator = await _operator_for(h)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(_command(h, operator))
        with pytest.raises(CheckerExecutionUnavailable, match="checker_current_request_unavailable"):
            await executor._claim(h.request)
        async with h.factory.begin() as session:
            with pytest.raises(CheckerExecutionUnavailable, match="checker_current_request_unavailable"):
                await evaluation_coordinator(session).read_current_result(h.request)
        async with h.factory() as session:
            source = await session.get(CheckerRun, str(h.created.evaluation_attempt_id))
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert source.status == "infrastructure_failed" and source.completion_event_id is None
            assert fence.current_run_id == str(created.successor.run_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
