"""Real ART replacement comparison against one retained consumed Submission."""

from __future__ import annotations

import asyncio

from dataclasses import replace
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.adapters.checkers import evaluation_coordinator
from app.adapters.tasks import task_post_submit_outcome
from app.adapters.artifacts.local import LocalStorageAdapter
from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.interfaces.artifacts import ArtifactStoreUnavailableError
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRequest,
)
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.artifacts.models import (
    SubmissionBundleAdmission,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.tasks.api.submission_context import (
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import SubmissionDispatch
from app.adapters.tasks import task_submission_context_port
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.artifact_store_helpers import artifact_byte_stream
from tests.checkers.execution.support import live_executor, reserve
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.post_submit_routing.remediation_support import (
    no_economic_effects,
    remediation_source,
)
from tests.tasks.post_submit_routing.support import next_request, revision_archive
from tests.tasks.submission_lineage_support import _verified_admission
from tests.selected_predecessor_fixtures import (
    _snapshot, _secret_archive, _queued_selected_body, _insert_selected_reservation,
)


def _trace_provider_writes(monkeypatch: pytest.MonkeyPatch, *, operations=("put", "observe_put_result")) -> list[str]:
    calls: list[str] = []
    for operation in operations:
        original = getattr(LocalStorageAdapter, operation)

        async def traced(self, *args, _original=original, _operation=operation, **kwargs):
            calls.append(_operation)
            return await _original(self, *args, **kwargs)

        monkeypatch.setattr(LocalStorageAdapter, operation, traced)
    return calls




def _replacement_request(h, data: bytes, *, predecessor_id: UUID, idempotency_key: UUID):
    return SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            h.actor_context.actor_profile_id,
            h.actor_context.identity_link_id,
            ActorKind.HUMAN,
        ),
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        predecessor_submission_id=predecessor_id,
        revision_preparation_id=(str(h.revision_preparation_id)
                                 if getattr(h, "revision_preparation_id", None) else None),
        revision_preparation_sha256=getattr(h, "revision_preparation_sha256", None),
        idempotency_key=idempotency_key,
        summary=h.creation_request.summary,
        contributor_attestation=h.creation_request.contributor_attestation,
        media_type="application/zip",
        byte_source=artifact_byte_stream(data),
    )




async def _fixture_revision_context(h):
    """Commit the real routed checker failure before replacement intake."""
    async with h.factory() as session, session.begin():
        outcome = task_post_submit_outcome(session, h.factory)
        assert await outcome.observe_delivery_generation(h.envelope) is None
        result = await outcome.apply(h.envelope, current_generation=None)
        assert result.routing_recommendation == "needs_revision"
    async with h.factory() as session:
        source = (await session.execute(text("""
            SELECT m.id,m.submission_id,m.assignment_id,m.routing_recommendation,
              t.status AS task_status,a.status AS assignment_status,
              public.task_routing_outcome_complete(m) AS complete
            FROM public.task_post_submit_routing_manifests m
            JOIN public.workstream_tasks t ON t.id=m.task_id
            JOIN public.task_assignments a ON a.id=m.assignment_id
            WHERE m.id=:id
        """), {"id": result.routing_manifest_id})).mappings().one()
        assert source["submission_id"] == h.created.submission_id
        assert source["assignment_id"] == h.request.assignment_id
        assert source["routing_recommendation"] == source["task_status"] == "needs_revision"
        assert source["assignment_status"] == "active" and source["complete"] is True
        await no_economic_effects(session)
        from app.modules.tasks.revision.service import head_for_source
        preparation = await head_for_source(session, result.routing_manifest_id)
        assert preparation is not None
        h.revision_preparation_id = preparation.id
        h.revision_preparation_sha256 = preparation.preparation_sha256
    return result.routing_manifest_id


def _same_semantics_different_archive(data: bytes) -> bytes:
    repacked = BytesIO(data)
    with ZipFile(repacked, "a") as archive:
        archive.comment = b"different archive bytes; identical governed members"
    result = repacked.getvalue()
    assert result != data
    return result


async def _assert_dispatch_valid(h) -> None:
    async with h.factory() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT public.submission_dispatch_valid(dispatch) "
                    "FROM public.submission_dispatches dispatch "
                    "WHERE submission_id=:submission_id"
                ),
                {"submission_id": h.created.submission_id},
            )
            is True
        )


async def _forbidden_bytes():
    pytest.fail("rejected replacement consumed contributor ZIP bytes")
    yield b""


def _context_request(h) -> TaskSubmissionContextRequest:
    return TaskSubmissionContextRequest(
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        contributor_id=h.actor_context.actor_profile_id,
        predecessor_submission_id=h.created.submission_id,
    )


async def _replacement_history(h, source_id, predecessor_id):
    """Retain exact prior Submission, routing and checker evidence across replacement."""
    async with h.factory() as session:
        return (await session.execute(text("""
            SELECT (SELECT to_jsonb(s) FROM public.submissions s WHERE s.id=:prior),
              (SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m WHERE m.id=:cause),
              (SELECT to_jsonb(r) FROM public.checker_results r WHERE r.id=:result)
        """), {"prior": predecessor_id, "cause": source_id,
               "result": h.completion.reference.result_id})).one()


@pytest.mark.parametrize("human_review_required", [True, False])
async def test_real_replacement_compares_consumed_predecessor_and_replays_exactly(
    tmp_path, isolated_database_env, monkeypatch, human_review_required,
):
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.submission_dispatch.test_revision_capacity import (
        _revision_http_runtime, _revision_upload_headers,
    )
    from tests.tasks.test_public_submission_intake import _client
    from tests.tasks.submission_dispatch.test_replacement_creation import _creation_snapshot

    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=human_review_required,
    ) as h:
        await _assert_dispatch_valid(h)
        source_id = await _fixture_revision_context(h)
        predecessor_id = h.created.submission_id
        immutable_before = await _replacement_history(h, source_id, predecessor_id)
        writes = _trace_provider_writes(monkeypatch, operations=(
            "begin_source_upload", "upload_source_part", "complete_source_upload", "put", "observe_put_result"))
        data = revision_archive(h.data)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            settings, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            headers = _revision_upload_headers(h)
            url = f"/api/v1/tasks/{h.request.task_id}/submissions"
            response = await client.post(url, headers=headers, content=data)
            assert response.status_code == 202, response.text
            accepted = response.json()
            operation_id = UUID(accepted["operation_id"])
            async with h.factory() as session:
                operation = await session.get(SubmissionIntakeOperation, operation_id)
                assert operation.state == "finalization_pending" and operation.finalized_submission_id is None
                assert await session.scalar(text("SELECT count(*) FROM public.submissions")) == 1
            for finalized in (False, True):
                if finalized:
                    submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
                        operation_id=operation_id, store=h.store.wrapped, namespace=h.namespace, settings=settings))
                before = await _snapshot(h)
                creation_before = await _creation_snapshot(h)
                replay = await client.post(url, headers=headers, content=data)
                assert replay.status_code == 202, replay.text
                assert replay.json() == dict(accepted, replayed=True)
                assert await _snapshot(h) == before
                assert await _creation_snapshot(h) == creation_before
                assert writes == ["begin_source_upload", "upload_source_part", "complete_source_upload"]
                assert len(calls) == 1 and not errors, errors
        async with h.factory() as session:
            operation = await session.get(SubmissionIntakeOperation, operation_id)
            assert operation.state == "finalized" and operation.finalized_submission_id == str(submission_id)
            charge = await session.get(SubmissionSourceCharge, operation_id)
            assert charge.state == "sealed" and charge.accounted_bytes == operation.raw_byte_count > 0
            predecessor_admission = await session.get(SubmissionBundleAdmission, str(h.creation_request.admission_id))
            admission = await session.get(SubmissionBundleAdmission, operation.finalized_admission_id)
            selected = await session.get(SelectedPreSubmitRun, admission.selected_pre_submit_run_id)
            assert predecessor_admission.status == admission.status == "consumed"
            assert admission.source_operation_id == str(operation_id)
            assert admission.predecessor_submission_id == str(predecessor_id)
            assert admission.predecessor_submission_version == 1
            assert admission.checker_remediation_manifest_id == source_id
            assert admission.pre_submit_evidence_set_id is None
            assert selected is not None and selected.eligible
            assert selected.request_json["default_context"]["predecessor"] == {
                "submission_id": str(predecessor_id), "submission_version": 1,
                "archive_sha256": predecessor_admission.archive_sha256,
                "semantic_manifest_sha256": predecessor_admission.semantic_manifest_sha256,
            }
            assert predecessor_admission.selected_rules_sha256 != predecessor_admission.locked_policy_context_hash
            assert selected.request_json["default_context"]["predecessor_rules_sha256"] == predecessor_admission.selected_rules_sha256
            lineage = selected.request_json["admission_lineage"]
            assert lineage["predecessor_submission_id"] == str(predecessor_id)
            assert lineage["predecessor_submission_version"] == 1
            assert lineage["checker_remediation_manifest_id"] == str(source_id)
            assert admission.archive_sha256 != predecessor_admission.archive_sha256
            assert admission.semantic_manifest_sha256 != predecessor_admission.semantic_manifest_sha256
            receipt = await session.get(SubmissionDispatch, str(submission_id))
            assert receipt.submission_version == 2 and receipt.creation_kind == "checker_remediation"
            assert receipt.checker_remediation_manifest_id == source_id
            assert await session.scalar(text(
                "SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d WHERE d.submission_id=:id"
            ), {"id": submission_id}) is True
            assert await session.scalar(text("SELECT count(*) FROM public.submissions")) == 2
            assert await session.scalar(text(
                "SELECT count(*) FROM public.submission_intake_operations WHERE idempotency_key=:key"
            ), {"key": UUID(headers["Idempotency-Key"])}) == 1
            await no_economic_effects(session)
        assert await _replacement_history(h, source_id, predecessor_id) == immutable_before


@pytest.mark.parametrize("missing", ["admission", "run", "rules", "contradictory_evidence"])
async def test_public_replacement_requires_consumed_predecessor_rules(
    tmp_path, isolated_database_env, monkeypatch, missing,
):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime, _revision_upload_headers
    from tests.tasks.test_public_submission_intake import _client

    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        data, intercepted = revision_archive(h.data), []
        before = await _snapshot(h)
        original_scalar = AsyncSession.scalar

        async def incomplete_predecessor(session, statement, *args, **kwargs):
            value = await original_scalar(session, statement, *args, **kwargs)
            descriptions = getattr(statement, "column_descriptions", ())
            if (len(descriptions) == 1 and descriptions[0].get("expr") is SubmissionBundleAdmission
                    and "consumed_by_submission_id" in str(getattr(statement, "whereclause", ""))):
                assert value is not None and value.consumed_by_submission_id == str(h.created.submission_id)
                assert value.selected_rules_sha256 != value.locked_policy_context_hash
                intercepted.append(value.id)
                # Fault only the owner's read; retained database evidence stays immutable.
                session.expunge(value)
                if missing == "admission":
                    return None
                setattr(value, {
                    "run": "selected_pre_submit_run_id", "rules": "selected_rules_sha256",
                    "contradictory_evidence": "pre_submit_evidence_set_id",
                }[missing], new_record_id() if missing == "contradictory_evidence" else None)
            return value

        async with _client(h, monkeypatch, isolated_database_env) as client:
            _, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            headers = _revision_upload_headers(h)
            monkeypatch.setattr(AsyncSession, "scalar", incomplete_predecessor)
            response = await client.post(f"/api/v1/tasks/{h.request.task_id}/submissions",
                                         headers=headers, content=data)
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "submission_infrastructure_unavailable"
        assert intercepted == [str(h.creation_request.admission_id)]
        assert calls == [] and not errors
        assert await _snapshot(h) == before
        async with h.factory() as session:
            operation = (await session.scalars(select(SubmissionIntakeOperation).where(
                SubmissionIntakeOperation.idempotency_key == headers["Idempotency-Key"]))).one()
            assert operation.state == "failed" and operation.acceptance_receipt is None
            assert operation.finalized_submission_id is None and operation.finalization_event_id is None
            charge = await session.get(SubmissionSourceCharge, operation.id)
            assert charge.state == "sealed" and charge.accounted_bytes == len(data)
            retained = await session.get(SubmissionBundleAdmission, str(h.creation_request.admission_id))
            assert retained.selected_pre_submit_run_id is not None and retained.selected_rules_sha256 is not None
            assert retained.pre_submit_evidence_set_id is None and retained.status == "consumed"
            assert await session.scalar(text("SELECT count(*) FROM submissions")) == 1
            await no_economic_effects(session)


async def test_replacement_without_routed_cause_denied_before_bytes(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.modules.artifacts.intake.foreground_upload import ForegroundSourceUpload
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime, _revision_upload_headers
    from tests.tasks.test_public_submission_intake import _client

    async with remediation_source(tmp_path, isolated_database_env) as h:
        writes = _trace_provider_writes(monkeypatch, operations=(
            "begin_source_upload", "upload_source_part", "complete_source_upload", "put", "observe_put_result"))
        before_route = await _snapshot(h)
        data = revision_archive(h.data)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            settings, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            route = f"/api/v1/tasks/{h.request.task_id}/submissions"
            headers = {
                'Content-Type': 'application/zip', 'Idempotency-Key': str(new_record_id()),
                'X-Task-Assignment-Id': str(h.request.assignment_id),
                'X-Predecessor-Submission-Id': str(h.created.submission_id),
            }
            async with h.factory() as session:
                before_operations = await session.scalar(text('SELECT count(*) FROM submission_intake_operations'))
            async def forbidden_upload(*_args, **_kwargs):
                pytest.fail('unrouted replacement reached source upload')
            with monkeypatch.context() as guard:
                guard.setattr(ForegroundSourceUpload, 'receive', forbidden_upload)
                refused = await client.post(route, headers=headers, content=_forbidden_bytes())
            assert refused.status_code == 404, refused.text
            assert refused.json()['error']['code'] == 'submission_unavailable'
            assert await _snapshot(h) == before_route
            assert writes == [] and calls == [] and not errors
            async with h.factory() as session:
                assert await session.scalar(text('SELECT count(*) FROM submission_intake_operations')) == before_operations
            source_id = await _fixture_revision_context(h)
            accepted = await client.post(route, headers=_revision_upload_headers(h), content=data)
            assert accepted.status_code == 202, accepted.text
            assert len(calls) == 1 and not errors, errors
            assert writes == ['begin_source_upload', 'upload_source_part', 'complete_source_upload']
        submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
            operation_id=UUID(accepted.json()['operation_id']), store=h.store.wrapped,
            namespace=h.namespace, settings=settings))
        async with h.factory() as session:
            admission = (await session.execute(text(
                'SELECT checker_remediation_manifest_id,status FROM submission_bundle_admissions '
                'WHERE consumed_by_submission_id=:id'), {'id': submission_id})).one()
            assert admission.checker_remediation_manifest_id == source_id
            assert admission.status == 'consumed'


async def test_unchanged_replacement_archive_or_manifest_denied(
    tmp_path, isolated_database_env, monkeypatch,
):
    from tests.selected_predecessor_fixtures import assert_public_revision_rejection
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime, _revision_upload_headers
    from tests.tasks.test_public_submission_intake import _client

    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        retained = await _replacement_history(h, source_id, h.created.submission_id)
        provider_writes.clear()
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/tasks/{h.request.task_id}/submissions"
            for data, expected in (
                (h.data, "submission_archive_unchanged"),
                (_same_semantics_different_archive(h.data), "submission_manifest_unchanged"),
            ):
                before = await _snapshot(h)
                _, errors, calls = await _revision_http_runtime(
                    h, client, tmp_path, monkeypatch, data, outcome="rejected")
                headers = _revision_upload_headers(h)
                response = await client.post(route, headers=headers, content=data)
                await assert_public_revision_rejection(
                    h, response, UUID(headers['Idempotency-Key']), data, before, expected)
                assert len(calls) == 1 and not errors, errors
                assert provider_writes == []
                assert await _replacement_history(h, source_id, h.created.submission_id) == retained
            corrected = revision_archive(h.data)
            _, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, corrected)
            accepted = await client.post(route, headers=_revision_upload_headers(h), content=corrected)
            assert accepted.status_code == 202, accepted.text
            assert accepted.json()['status'] == 'accepted' and accepted.json()['replayed'] is False
            assert len(calls) == 1 and not errors, errors
            assert provider_writes == []


async def test_blocked_replacement_precheck_preserves_revision_state(
    tmp_path, isolated_database_env, monkeypatch,
):
    from tests.selected_predecessor_fixtures import assert_public_revision_rejection
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime, _revision_upload_headers
    from tests.tasks.test_public_submission_intake import _client

    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        retained = await _replacement_history(h, source_id, h.created.submission_id)
        provider_writes.clear()
        changed_data = revision_archive(h.data)
        data = _secret_archive(changed_data)
        before = await _snapshot(h)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/tasks/{h.request.task_id}/submissions"
            _, errors, calls = await _revision_http_runtime(
                h, client, tmp_path, monkeypatch, data, outcome="rejected")
            headers = _revision_upload_headers(h) | {'X-Contributor-Attestation': ''}
            response = await client.post(route, headers=headers, content=data)
            results = await assert_public_revision_rejection(
                h, response, UUID(headers['Idempotency-Key']), data, before, 'high_confidence_secret_detected')
            assert [r['warning_code'] for r in results if r['status'] == 'warning'] == ['submission_attestation_missing']
            assert len(calls) == 1 and not errors, errors
            assert provider_writes == []
            assert await _replacement_history(h, source_id, h.created.submission_id) == retained
            _, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, changed_data)
            accepted = await client.post(route, headers=_revision_upload_headers(h), content=changed_data)
            assert accepted.status_code == 202, accepted.text
            assert accepted.json()['status'] == 'accepted' and accepted.json()['replayed'] is False
            assert len(calls) == 1 and not errors, errors
            assert provider_writes == []


async def test_replacement_dispatch_sql_rejects_cause_and_receipt_substitution(
    tmp_path, isolated_database_env, monkeypatch,
):
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.submission_dispatch.test_revision_capacity import (
        _revision_http_runtime, _revision_upload_headers,
    )
    from tests.tasks.test_public_submission_intake import _client

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        data = revision_archive(h.data)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            settings, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            response = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions",
                headers=_revision_upload_headers(h), content=data)
            assert response.status_code == 202, response.text
            assert len(calls) == 1 and not errors, errors
        submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
            operation_id=UUID(response.json()["operation_id"]), store=h.store.wrapped,
            namespace=h.namespace, settings=settings))
        async with h.factory() as session:
            dispatch_body = await session.scalar(text(
                "SELECT to_jsonb(d) FROM public.submission_dispatches d WHERE submission_id=:id"
            ), {"id": submission_id})
            assert dispatch_body["checker_remediation_manifest_id"] == str(source_id)
            validate = text(
                "SELECT public.submission_dispatch_valid("
                "pg_catalog.jsonb_populate_record(NULL::public.submission_dispatches, "
                "CAST(:body AS jsonb)))"
            )
            assert await session.scalar(validate, {"body": json.dumps(dispatch_body)}) is True
            for field, substituted in (
                ("checker_remediation_manifest_id", None),
                ("checker_remediation_manifest_id", str(new_record_id())),
                ("creation_decision_id", str(h.created.creation_decision_id)),
                ("binding_decision_id", str(h.created.binding_decision_id)),
            ):
                assert await session.scalar(
                    validate, {"body": json.dumps(dispatch_body | {field: substituted})}
                ) is False, field


async def test_sql_selected_pre_reservation_rejects_superseded_checker_cause(
    tmp_path,
    isolated_database_env,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        admission_id = await _verified_admission(
            h.factory,
            h.store,
            h.namespace,
            h.settings,
            h.actor_context,
            _replacement_request(
                h,
                revision_archive(h.data),
                predecessor_id=h.created.submission_id,
                idempotency_key=new_record_id(),
            ),
        )
        positive = await _queued_selected_body(h, admission_id)
        assert positive["request_json"]["admission_lineage"][
            "checker_remediation_manifest_id"
        ] == str(source_id)
        await _insert_selected_reservation(h, positive)
        rejected = await _queued_selected_body(h, admission_id)
        await reserve(h, await next_request(h))
        before = await _snapshot(h)
        async with h.factory() as session:
            current = await session.scalar(
                text(
                    "SELECT current_run_id FROM public.checker_submission_fences WHERE submission_id=:id"
                ),
                {"id": h.created.submission_id},
            )
            routed = await session.scalar(
                text(
                    "SELECT checker_run_id FROM public.task_post_submit_routing_manifests WHERE id=:id"
                ),
                {"id": source_id},
            )
            assert current != routed
        with pytest.raises(
            IntegrityError, match="selected PRE reservation routed cause is not current"
        ) as denied:
            await _insert_selected_reservation(h, rejected)
        assert denied.value.orig.sqlstate == "23514"
        assert await _snapshot(h) == before
        async with h.factory() as session:
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "ready"
            assert admission.checker_remediation_manifest_id == source_id
            assert await session.scalar(text("SELECT count(*) FROM public.submissions")) == 1
            await no_economic_effects(session)


async def _assert_foreign_verified_admission_rejected(local, foreign, admission_id, before):
    # Keep current preparation/cause binding intact, then substitute
    # a real foreign verified PRE run to reach the original byte guard.
    async with local.factory() as session:
        foreign_run_id = await session.scalar(text("""
            SELECT a.selected_pre_submit_run_id
            FROM public.submission_bundle_admissions a
            JOIN public.submissions s ON s.submission_bundle_admission_id=a.id
            WHERE s.id=:submission
        """), {"submission": foreign.created.submission_id})
        assert foreign_run_id is not None
    with pytest.raises(
        IntegrityError, match="submission bundle admission verified lineage mismatch"
    ) as verified_mismatch:
        async with local.factory.begin() as session:
            await session.execute(text("""
                INSERT INTO public.submission_bundle_admissions
                SELECT (pg_catalog.jsonb_populate_record(
                    NULL::public.submission_bundle_admissions, to_jsonb(a)
                    || pg_catalog.jsonb_build_object(
                        'id',CAST(:new_id AS uuid),
                        'selected_pre_submit_run_id',CAST(:run AS uuid)
                    )
                )).* FROM public.submission_bundle_admissions a WHERE a.id=:id
            """), {"new_id": new_record_id(), "run": foreign_run_id, "id": admission_id})
    assert verified_mismatch.value.orig.sqlstate == "23514"
    assert await _snapshot(local) == before


async def test_sql_selected_pre_reservation_and_admission_reject_foreign_routed_cause(
    tmp_path,
    isolated_database_env,
):
    async with remediation_source(tmp_path / "local", isolated_database_env) as local:
        async with remediation_source(
            tmp_path / "foreign",
            isolated_database_env,
            provision_services=False,
            storage_settings=local.settings,
        ) as foreign:
            local_source = await _fixture_revision_context(local)
            foreign_source = await _fixture_revision_context(foreign)
            admission_id = await _verified_admission(
                local.factory,
                local.store,
                local.namespace,
                local.settings,
                local.actor_context,
                _replacement_request(
                    local,
                    revision_archive(local.data),
                    predecessor_id=local.created.submission_id,
                    idempotency_key=new_record_id(),
                ),
            )
            positive = await _queued_selected_body(local, admission_id)
            assert positive["request_json"]["admission_lineage"][
                "checker_remediation_manifest_id"
            ] == str(local_source)
            await _insert_selected_reservation(local, positive)
            rejected = await _queued_selected_body(local, admission_id, cause=foreign_source)
            before = await _snapshot(local)
            with pytest.raises(
                IntegrityError, match="selected PRE reservation routed cause is foreign"
            ) as denied:
                await _insert_selected_reservation(local, rejected)
            assert denied.value.orig.sqlstate == "23514"
            assert await _snapshot(local) == before
            with pytest.raises(
                DBAPIError, match="selected PRE request custody is immutable"
            ) as immutable:
                async with local.factory.begin() as session:
                    await session.execute(
                        text("""
                        UPDATE public.selected_pre_submit_runs
                        SET request_json=CAST(:request AS jsonb), request_digest=:digest WHERE id=:id
                    """),
                        {
                            "id": positive["id"],
                            "request": json.dumps(
                                positive["request_json"]
                                | {
                                    "admission_lineage": rejected["request_json"][
                                        "admission_lineage"
                                    ]
                                }
                            ),
                            "digest": canonical_json_hash(
                                positive["request_json"]
                                | {
                                    "admission_lineage": rejected["request_json"][
                                        "admission_lineage"
                                    ]
                                }
                            ),
                        },
                    )
            assert immutable.value.orig.sqlstate == "55000"
            assert await _snapshot(local) == before
            with pytest.raises(
                IntegrityError, match="revision admission context unavailable"
            ) as mismatch:
                async with local.factory.begin() as session:
                    await session.execute(
                        text("""
                        INSERT INTO public.submission_bundle_admissions
                        SELECT (pg_catalog.jsonb_populate_record(
                            NULL::public.submission_bundle_admissions, to_jsonb(a)
                            || pg_catalog.jsonb_build_object(
                                'id',CAST(:new_id AS uuid),
                                'checker_remediation_manifest_id',CAST(:cause AS uuid)
                            )
                        )).* FROM public.submission_bundle_admissions a WHERE a.id=:id
                    """),
                        {"new_id": new_record_id(), "cause": foreign_source, "id": admission_id},
                    )
            assert mismatch.value.orig.sqlstate == "23514"
            assert await _snapshot(local) == before
            await _assert_foreign_verified_admission_rejected(
                local, foreign, admission_id, before,
            )
            async with local.factory() as session:
                admission = await session.get(SubmissionBundleAdmission, str(admission_id))
                assert (
                    admission.status == "ready" and admission.selected_pre_submit_run_id is not None
                )
                assert admission.pre_submit_evidence_set_id is None
                assert admission.checker_remediation_manifest_id == local_source
                assert await session.scalar(text("SELECT count(*) FROM public.submissions")) == 2
                await no_economic_effects(session)


@pytest.mark.parametrize("advance_fence", [False, True])
async def test_dispatch_commit_requires_current_predecessor_checker_fence(
    tmp_path, isolated_database_env, monkeypatch, advance_fence,
):
    """T4 rejects a superseded cause despite a stale port; current T4 reaches T5."""
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.submission_dispatch.test_revision_capacity import (
        _revision_http_runtime, _revision_upload_headers,
    )
    from tests.tasks.submission_dispatch.test_replacement_creation import _creation_snapshot
    from tests.tasks.test_public_submission_intake import _client

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        async with h.factory.begin() as session:
            frozen = await task_submission_context_port(session).lock_submission_context(_context_request(h))
        assert frozen.checker_remediation_manifest_id == source_id

        class FrozenTaskContextPort:
            async def lock_submission_context(self, selected):
                assert selected == _context_request(h)
                return frozen

        operations, snapshots, staged, commit_errors = [], [], [], []
        original_accept = ForegroundIntakeAdmission.accept
        original_stage = ForegroundIntakeAdmission._accept_new

        async def accept_after_fence_change(admission, owner, *args, **kwargs):
            operations.append(owner.operation_id)
            if advance_fence:
                await reserve(h, await next_request(h))
                async with h.factory.begin() as session:
                    with pytest.raises(TaskSubmissionContextUnavailable):
                        await task_submission_context_port(session).lock_submission_context(_context_request(h))
                # Freeze only the TASK context reader. All writers and SQL guards remain real.
                monkeypatch.setattr(admission, "_contexts", lambda _session: FrozenTaskContextPort())
                monkeypatch.setattr(
                    "app.adapters.tasks.task_submission_context_port", lambda _session: FrozenTaskContextPort())
            snapshots.append(await _creation_snapshot(h))
            return await original_accept(admission, owner, *args, **kwargs)

        async def trace_staged_acceptance(admission, session, authority, repository, row, owner, *args):
            result = await original_stage(admission, session, authority, repository, row, owner, *args)
            await session.flush()
            assert row.state == "finalization_pending" and row.finalization_event_id is not None
            staged.append(owner.operation_id)
            original_commit = session.commit

            async def observed_commit():
                try:
                    await original_commit()
                except IntegrityError as exc:
                    commit_errors.append((exc.orig.sqlstate, str(exc.orig)))
                    raise

            monkeypatch.setattr(session, "commit", observed_commit)
            return result

        monkeypatch.setattr(ForegroundIntakeAdmission, "accept", accept_after_fence_change)
        monkeypatch.setattr(ForegroundIntakeAdmission, "_accept_new", trace_staged_acceptance)
        data = revision_archive(h.data)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            settings, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            response = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions",
                headers=_revision_upload_headers(h), content=data)
        assert len(calls) == 1 and not errors, errors
        assert len(operations) == 1 and staged == operations
        operation_id = operations[0]
        if advance_fence:
            assert len(commit_errors) == 1
            assert commit_errors[0][0] == "23514"
            assert "revision acceptance is no longer eligible" in commit_errors[0][1]
            assert response.status_code == 503, response.text
            assert response.json()["error"]["code"] == "submission_infrastructure_unavailable"
            after, before = await _creation_snapshot(h), snapshots[0]
            assert after[:8] == before[:8]
            assert after[8] == before[8]
            async with h.factory() as session:
                operation = await session.get(SubmissionIntakeOperation, operation_id)
                assert operation.state == "failed" and operation.acceptance_receipt is None
                assert operation.finalization_event_id is None and operation.finalized_submission_id is None
                charge = await session.get(SubmissionSourceCharge, operation_id)
                assert charge.state == "sealed" and charge.accounted_bytes == operation.raw_byte_count > 0
                assert (await session.execute(text(
                    "SELECT status,active_submission_operation_id FROM public.workstream_tasks WHERE id=:id"
                ), {"id": h.request.task_id})).one() == ("needs_revision", None)
                await no_economic_effects(session)
        else:
            assert commit_errors == []
            assert response.status_code == 202, response.text
            assert response.json()["operation_id"] == str(operation_id)
            submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
                operation_id=operation_id, store=h.store.wrapped, namespace=h.namespace, settings=settings))
            async with h.factory() as session:
                dispatch = await session.get(SubmissionDispatch, str(submission_id))
                assert dispatch.submission_version == 2
                assert dispatch.checker_remediation_manifest_id == source_id
                assert await session.scalar(text(
                    "SELECT public.submission_dispatch_valid(d) "
                    "FROM public.submission_dispatches d WHERE d.submission_id=:id"
                ), {"id": submission_id}) is True
                await no_economic_effects(session)


async def test_foreign_predecessor_stops_at_task_context_before_art_effects(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.modules.artifacts.intake.foreground_upload import ForegroundSourceUpload
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime, _revision_upload_headers
    from tests.tasks.test_public_submission_intake import _client

    async with remediation_source(tmp_path / "local", isolated_database_env) as local:
        async with remediation_source(
            tmp_path / "foreign", isolated_database_env, provision_services=False,
            storage_settings=local.settings,
        ) as foreign:
            await _assert_dispatch_valid(local)
            await _assert_dispatch_valid(foreign)
            local_source = await _fixture_revision_context(local)
            foreign_source = await _fixture_revision_context(foreign)
            async with local.factory.begin() as session:
                contexts, own = task_submission_context_port(session), _context_request(local)
                assert (await contexts.lock_submission_context(own)).checker_remediation_manifest_id == local_source
                for field, value in (
                    ("task_id", foreign.request.task_id), ("assignment_id", foreign.request.assignment_id),
                    ("contributor_id", foreign.actor_context.actor_profile_id),
                    ("predecessor_submission_id", foreign.created.submission_id),
                ):
                    with pytest.raises(TaskSubmissionContextUnavailable):
                        await contexts.lock_submission_context(replace(own, **{field: value}))
            writes = _trace_provider_writes(monkeypatch, operations=(
                "begin_source_upload", "upload_source_part", "complete_source_upload", "put", "observe_put_result"))
            data = revision_archive(local.data)
            async with _client(local, monkeypatch, isolated_database_env) as client:
                settings, errors, calls = await _revision_http_runtime(
                    local, client, tmp_path / "local", monkeypatch, data)
                baseline = await _snapshot(local)
                async with local.factory() as session:
                    intake_before = await session.scalar(text("SELECT count(*) FROM public.submission_intake_operations"))
                async def forbidden_upload(*_args, **_kwargs):
                    pytest.fail("foreign predecessor reached ART upload")
                headers = _revision_upload_headers(local)
                with monkeypatch.context() as guard:
                    guard.setattr(ForegroundSourceUpload, "receive", forbidden_upload)
                    refused = await client.post(
                        f"/api/v1/tasks/{local.request.task_id}/submissions",
                        headers=headers | {"X-Predecessor-Submission-Id": str(foreign.created.submission_id)},
                        content=_forbidden_bytes())
                assert refused.status_code == 409, refused.text
                assert refused.json()["error"]["code"] == "task_submission_predecessor_changed"
                assert await _snapshot(local) == baseline and writes == [] and calls == []
                async with local.factory() as session:
                    assert await session.scalar(text("SELECT count(*) FROM public.submission_intake_operations")) == intake_before
                accepted = await client.post(
                    f"/api/v1/tasks/{local.request.task_id}/submissions",
                    headers=_revision_upload_headers(local), content=data)
                assert accepted.status_code == 202, accepted.text
                assert len(calls) == 1 and not errors, errors
            submission_id = await finalize_retained_intake(local.factory, SimpleNamespace(
                operation_id=UUID(accepted.json()["operation_id"]), store=local.store.wrapped,
                namespace=local.namespace, settings=settings))
            async with local.factory() as session:
                body = await session.scalar(text(
                    "SELECT to_jsonb(d) FROM public.submission_dispatches d WHERE submission_id=:id"
                ), {"id": submission_id})
                assert body["checker_remediation_manifest_id"] == str(local_source)
                validate = text(
                    "SELECT public.submission_dispatch_valid("
                    "pg_catalog.jsonb_populate_record(NULL::public.submission_dispatches, CAST(:body AS jsonb)))"
                )
                assert await session.scalar(validate, {"body": json.dumps(body)}) is True
                assert await session.scalar(validate, {"body": json.dumps(
                    body | {"checker_remediation_manifest_id": str(foreign_source)}
                )}) is False
                await no_economic_effects(session)


@pytest.mark.parametrize("outcome", ["infrastructure_failed", "completed"])
async def test_nonremediation_outcome_cannot_authorize_replacement_before_bytes(
    tmp_path,
    isolated_database_env,
    monkeypatch,
    outcome,
):
    from app.modules.artifacts.intake.foreground_upload import ForegroundSourceUpload
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime
    from tests.tasks.test_public_submission_intake import _client

    provider_writes = _trace_provider_writes(monkeypatch, operations=(
        "begin_source_upload", "upload_source_part", "complete_source_upload", "put", "observe_put_result"))
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        failed_reads = []
        with monkeypatch.context() as failure:
            if outcome == "infrastructure_failed":

                async def unavailable(*_args, **_kwargs):
                    failed_reads.append(True)
                    raise ArtifactStoreUnavailableError("selected input unavailable")
                    yield b""  # Preserve ArtifactStore.open's async-iterator port.

                failure.setattr(h.store, "open_source", unavailable)
            result = await live_executor(h).evaluate_post_submission(h.request)
        assert bool(failed_reads) == (outcome == "infrastructure_failed")
        assert result.outcome == outcome
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(result.attempt_id))
            assert run.status == outcome
            assert run.routing_recommendation == (
                "not_evaluated" if outcome == "infrastructure_failed" else "allow_review"
            )
        before = await _snapshot(h)
        provider_writes.clear()
        async with h.factory() as session:
            before_operations = await session.scalar(text("SELECT count(*) FROM submission_intake_operations"))

        async def forbidden_upload(*_args, **_kwargs):
            pytest.fail("nonremediation replacement reached source upload")

        async with _client(h, monkeypatch, isolated_database_env) as client:
            _, errors, calls = await _revision_http_runtime(
                h, client, tmp_path, monkeypatch, revision_archive(h.data))
            monkeypatch.setattr(ForegroundSourceUpload, "receive", forbidden_upload)
            refused = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions",
                headers={
                    "Content-Type": "application/zip", "Idempotency-Key": str(new_record_id()),
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                }, content=_forbidden_bytes())
            assert refused.status_code == 404, refused.text
            assert refused.json()["error"]["code"] == "submission_unavailable"
            assert calls == [] and not errors
        assert await _snapshot(h) == before
        assert provider_writes == []
        async with h.factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == before_operations
            await no_economic_effects(session)


async def test_source_superseded_during_zip_read_refuses_acceptance(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime, _revision_upload_headers
    from tests.tasks.test_public_submission_intake import _client

    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        async with h.factory.begin() as session:
            current = await task_submission_context_port(session).lock_submission_context(_context_request(h))
            assert current.checker_remediation_manifest_id == source_id
        before = await _snapshot(h)
        provider_writes.clear()
        opened = []
        data = revision_archive(h.data)

        async def superseding_bytes():
            opened.append(True)
            await reserve(h, await next_request(h))
            yield data

        async with _client(h, monkeypatch, isolated_database_env) as client:
            _, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            headers = _revision_upload_headers(h) | {"Content-Length": str(len(data))}
            response = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions",
                headers=headers, content=superseding_bytes())
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "submission_unavailable"
        assert opened == [True]
        assert calls == [] and not errors
        assert await _snapshot(h) == before
        assert provider_writes == []
        async with h.factory.begin() as session:
            operation = (await session.scalars(select(SubmissionIntakeOperation).where(
                SubmissionIntakeOperation.idempotency_key == headers["Idempotency-Key"]))).one()
            assert operation.state == "failed" and operation.acceptance_receipt is None
            assert operation.finalization_event_id is None and operation.finalized_submission_id is None
            charge = await session.get(SubmissionSourceCharge, operation.id)
            assert charge.state == "sealed" and charge.accounted_bytes == len(data)
            assert operation.raw_byte_count == len(data)
            assert await session.scalar(text("SELECT count(*) FROM submissions")) == 1
            await no_economic_effects(session)
            with pytest.raises(TaskSubmissionContextUnavailable):
                await task_submission_context_port(session).lock_submission_context(_context_request(h))


async def _predecessor_fence_snapshot(h, source_id):
    """Observe immutable predecessor routing and its current checker generation."""
    async with h.factory() as session:
        return (await session.execute(text("""
            SELECT f.current_run_id,
              (SELECT count(*) FROM public.checker_runs WHERE submission_id=:prior),
              (SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m WHERE m.id=:source)
            FROM public.checker_submission_fences f WHERE f.submission_id=:prior
        """), {"prior": h.created.submission_id, "source": source_id})).one()


async def _assert_pending_handoff_checker_guard(h, prior_request, successor, monkeypatch):
    """Exact historical replay remains read-only; a stale TASK guard cannot insert."""
    from app.db.errors import integrity_constraint_name
    from app.modules.checkers.api.execution import CheckerRequestConflict
    from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard

    replay = await reserve(h, prior_request)
    assert replay.attempt_id == h.completion.reference.attempt_id
    assert replay.result_id == h.completion.reference.result_id
    original = TaskEvaluationGuard.lock_evaluation_scope
    async def stale_guard(guard, request):
        assert request == successor
        assert await original(guard, request) is False
        return True
    with monkeypatch.context() as patch:
        patch.setattr(TaskEvaluationGuard, "lock_evaluation_scope", stale_guard)
        with pytest.raises(CheckerRequestConflict) as denied:
            await reserve(h, successor)
    database_error = denied.value.__context__
    assert isinstance(database_error, IntegrityError)
    assert database_error.orig.sqlstate == "23514"
    assert integrity_constraint_name(database_error) == "ck_checker_pending_submission_current"


async def test_replacement_holds_task_custody_against_successor_generation(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.submission_dispatch.test_revision_capacity import _revision_http_runtime, _revision_upload_headers
    from tests.tasks.submission_dispatch.test_revision_expiry import _wait_for_staged_submission
    from tests.tasks.test_public_submission_intake import _client

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        prior_request = h.request
        successor = await next_request(h)
        prior = await _predecessor_fence_snapshot(h, source_id)
        held, release = asyncio.Event(), asyncio.Event()
        creator_pid, operations = [], []
        original = ForegroundIntakeAdmission._accept_new

        async def pause_staged_acceptance(admission, session, authority, repository, row, owner, *args):
            result = await original(admission, session, authority, repository, row, owner, *args)
            await session.flush()
            assert row.state == "finalization_pending"
            creator_pid.append(await session.scalar(text("SELECT pg_backend_pid()")))
            operations.append(owner.operation_id)
            held.set()
            await asyncio.wait_for(release.wait(), 30)
            return result

        waiter_name = "replacement-successor-" + new_record_id().hex
        async def reserve_successor():
            async with h.factory() as session, session.begin():
                await session.execute(text("SELECT set_config('application_name',:name,true)"), {"name": waiter_name})
                return await evaluation_coordinator(session).reserve_current_evaluation(successor)

        data = revision_archive(h.data)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            settings, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            with monkeypatch.context() as patch:
                patch.setattr(ForegroundIntakeAdmission, "_accept_new", pause_staged_acceptance)
                creator = asyncio.create_task(client.post(
                    f"/api/v1/tasks/{h.request.task_id}/submissions",
                    headers=_revision_upload_headers(h), content=data))
                waiter = None
                try:
                    await _wait_for_staged_submission(held, creator, timeout=60)
                    waiter = asyncio.create_task(reserve_successor())
                    await asyncio.wait_for(wait_for_named_database_lock(
                        isolated_database_env, waiter_name, expected_blocker_pid=creator_pid[0]), 15)
                    async with h.factory() as observer:
                        waiting_query = await observer.scalar(text(
                            "SELECT query FROM pg_stat_activity WHERE application_name=:name AND wait_event_type='Lock'"
                        ), {"name": waiter_name})
                    assert waiting_query is not None and "workstream_tasks" in waiting_query
                    assert not waiter.done()
                    release.set()
                    accepted = await asyncio.wait_for(creator, 60)
                    assert accepted.status_code == 202, accepted.text
                    with pytest.raises(CheckerExecutionUnavailable, match="checker_reservation_scope_unavailable"):
                        await asyncio.wait_for(waiter, 30)
                finally:
                    release.set()
                    for pending in (creator, waiter):
                        if pending is not None and not pending.done():
                            pending.cancel()
                    await asyncio.gather(*(pending for pending in (creator, waiter) if pending is not None), return_exceptions=True)
        assert len(calls) == 1 and not errors, errors
        await _assert_pending_handoff_checker_guard(h, prior_request, successor, monkeypatch)
        assert await _predecessor_fence_snapshot(h, source_id) == prior
        async with h.factory() as session:
            operation = await session.get(SubmissionIntakeOperation, operations[0])
            assert operation.state == "finalization_pending" and operation.finalized_submission_id is None
            assert await session.scalar(text(
                "SELECT count(*) FROM public.submissions WHERE task_id=:task"
            ), {"task": h.request.task_id}) == 1
        submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
            operation_id=operations[0], store=h.store.wrapped, namespace=h.namespace, settings=settings))
        async with h.factory() as session:
            operation = await session.get(SubmissionIntakeOperation, operations[0])
            admission = await session.get(SubmissionBundleAdmission, operation.finalized_admission_id)
            assert admission.status == "consumed"
            for table in ("submissions", "submission_dispatches"):
                assert await session.scalar(text(f"SELECT count(*) FROM public.{table} WHERE task_id=:task"),
                                            {"task": h.request.task_id}) == 2
            assert await session.scalar(text(
                "SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d WHERE d.submission_id=:id"
            ), {"id": submission_id}) is True
            assert await session.scalar(text("SELECT status FROM public.workstream_tasks WHERE id=:task"),
                                        {"task": h.request.task_id}) == "evaluation_pending"
            await no_economic_effects(session)
        assert await _predecessor_fence_snapshot(h, source_id) == prior
