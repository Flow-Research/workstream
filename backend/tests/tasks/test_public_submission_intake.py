"""Public source intake against real TASK/ART owners and PostgreSQL."""

from __future__ import annotations

from unittest.mock import patch
from tests.trusted_intake_fixtures import LocalIntakeAdapter

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.identifiers import new_record_id
from app.api.deps.rate_controls import get_rate_control_service
from app.db.session import get_db_session
from app.main import create_app
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission
from app.modules.api_controls.service import AUTHORIZATION_READ_SCOPE, RateControlService
from app.modules.actors.models import ActorProfile
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake,
    admin_access as admin_access,
    signed_access as signed_access,
    rsa_signing_material as rsa_signing_material,
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
)
from tests.tasks.post_submit_routing.backfill_support import assert_upgrade_refuses_stale_findings
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.test_submission_predecessor_custody import (
    _fixture_revision_context,
)


@asynccontextmanager
async def _client(
    h, monkeypatch, database_url, *, subject=None, raise_app_exceptions=True,
):
    """Use real HTTP authority/storage and explicit in-process guest-rule execution."""
    actor = getattr(h, "actor_context", None) or h.context
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", database_url)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "public-intake-token")
    subject = subject or f"human-{actor.actor_profile_id}"
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", subject)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "https://issuer.example.test")
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    monkeypatch.setenv(
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET",
        "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=",
    )
    get_settings.cache_clear()
    settings_values = h.settings.model_dump()
    settings_values.update({
        "auth_provider": "dev",
        "environment": "test",
        "database_url": database_url,
        "dev_auth_token": "public-intake-token",
        "dev_auth_subject": subject,
        "dev_auth_issuer": "https://issuer.example.test",
    })
    settings = Settings(_env_file=None, **settings_values)
    assert settings.api_rate_limit_key_secret is not None
    assert settings.pagination_cursor_hmac_secret is not None
    assert settings.database_url == database_url
    rate_control = RateControlService(h.factory)
    preflight = await rate_control.consume(
        control_scope=AUTHORIZATION_READ_SCOPE,
        issuer="https://issuer.example.test",
        subject=subject,
        limit=settings.api_authorization_read_rate_limit,
        window_seconds=settings.api_authorization_read_rate_window_seconds,
        secret=settings.api_rate_limit_key_secret,
    )
    assert preflight.allowed
    app = create_app(settings)
    assert app.state.auth_configuration_valid

    async def session():
        async with h.factory() as value:
            yield value

    app.dependency_overrides[get_db_session] = session
    app.dependency_overrides[get_rate_control_service] = lambda: rate_control
    try:
        async with AsyncClient(
            transport=ASGITransport(
                app=app, raise_app_exceptions=raise_app_exceptions,
            ),
            base_url="http://testserver",
            headers={"Authorization": "Bearer public-intake-token"},
        ) as client:
            with patch("app.adapters.artifacts.trusted_submission_intake", return_value=LocalIntakeAdapter()):
                yield client
    finally:
        get_settings.cache_clear()


def _payload(request, admission_id):
    return {
        "assignment_id": str(request.assignment_id),
        "admission_id": str(admission_id),
        "predecessor_submission_id": (
            str(request.predecessor_submission_id)
            if request.predecessor_submission_id is not None else None
        ),
        "summary": request.summary,
        "contributor_attestation": request.contributor_attestation,
    }


async def test_public_malformed_zip_preserves_task_and_retains_cleanup_custody(
    admission_intake, tmp_path, monkeypatch,
):
    """Malformed sealed input rejects before acceptance and remains cleanup-owned."""
    from sqlalchemy import text
    from app.adapters import artifacts as composition
    from app.adapters.checkers import SelectedPreSubmitCheckerExecutionAdapter
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.artifacts.test_submission_pre_source import _source_runtime
    from tests.test_trusted_intake import _archive

    f = admission_intake
    malformed = b"PK\x03\x04not-a-readable-zip"
    client, settings, errors, calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, malformed, "rejected",
    )
    headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
        "Idempotency-Key": str(new_record_id()),
    }
    route = f"/api/v1/tasks/{f.task}/submissions"
    response = await client.post(route, headers=headers, content=malformed)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "pre_submission_checker_failed"
    assert response.json()["error"]["details"]["eligible_to_submit"] is False
    results = response.json()["error"]["details"]["results"]
    assert any(item["source"] == "workstream_default"
               and item.get("failure_code") == "submission_archive_malformed" for item in results)
    assert not any(item["source"] == "project_external_checker" for item in results)
    status = await client.get(
        f"/api/v1/actors/me/assignments/{f.assignment}", headers=f.access.target.headers,
    )
    assert status.status_code == 200, status.text
    assignment = status.json()
    assert assignment["current_status"] == "in_progress" and assignment["next_action"] == "submit"
    assert assignment["assignment"]["latest_submission"] is None
    assert assignment["intake"]["pre_submission_results"] == results
    assert len(calls) == 1 and not errors, errors
    assert all(value not in response.text for value in (
        "/tmp/", "s3://", "not-a-readable-zip", "BadZipFile",
    ))
    async with f.factory() as session:
        assert await session.scalar(text("SELECT status FROM workstream_tasks WHERE id=:id"),
                                    {"id": f.task}) == "in_progress"
        assert await session.scalar(text("SELECT status FROM task_assignments WHERE id=:id"),
                                    {"id": f.assignment}) == "active"
        assert await session.scalar(select(func.count()).select_from(Submission)) == 0
        assert await session.scalar(select(func.count()).select_from(SubmissionBundleAdmission)) == 0
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 0
        assert await session.scalar(text("SELECT state FROM submission_intake_operations WHERE task_id=:id"),
                                    {"id": f.task}) == "rejected"
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges")) == len(malformed)
    assert not tuple(settings.artifact_scratch_root.glob("files/*"))
    assert not tuple(settings.artifact_scratch_root.glob("workspaces/*"))

    valid_bytes = _archive()
    retry_root = tmp_path / "corrected-worker"
    retry_root.mkdir()
    runtime, valid_errors = _source_runtime(valid_bytes, retry_root, "completed")
    monkeypatch.setattr(composition, "selected_pre_submit_checker_execution",
                        lambda **kwargs: SelectedPreSubmitCheckerExecutionAdapter(external_execution=runtime))
    valid = await client.post(route, headers=headers | {"Idempotency-Key": str(new_record_id())},
                              content=valid_bytes)
    assert not valid_errors, "\n".join(valid_errors)
    assert valid.status_code == 202, valid.text
    assert valid.json()["status"] == "accepted" and valid.json()["replayed"] is False


async def test_public_equal_content_finalizes_distinct_charged_sources(
    admission_intake, tmp_path, monkeypatch,
):
    """Logical deduplication preserves both retained source objects and charges."""
    from contextlib import aclosing
    from uuid import UUID

    from sqlalchemy import text

    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from app.modules.artifacts.intake.repository import SubmissionIntakeRepository
    from app.modules.artifacts.models import ArtifactBinding, ArtifactContent, ArtifactReplica
    from app.modules.tasks.models import SubmissionDispatch
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
    from tests.test_artifact_admission import _local_store
    from tests.test_trusted_intake import _archive

    f, payload = admission_intake, _archive()
    other_task, other_assignment = new_record_id(), new_record_id()
    async with f.factory.kw["bind"].begin() as connection:
        await seed_started_task_for_artifact_test(connection, dict(
            task=str(other_task), assignment=str(other_assignment), project=str(f.project),
            actor=str(f.actor.actor_profile_id),
        ))
        await connection.execute(text(
            "UPDATE task_assignments SET accepted_at=clock_timestamp() WHERE id=:id"
        ), {"id": other_assignment})

    accepted = []
    for task, assignment in ((f.task, f.assignment), (other_task, other_assignment)):
        # Give each controlled PRE worker its own scratch directory on the same source store.
        client, settings, errors, calls = await configure_source_http(
            f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, "completed",
        )
        response = await client.post(
            f"/api/v1/tasks/{task}/submissions",
            headers=f.access.target.headers | {
                "Content-Type": "application/zip", "X-Task-Assignment-Id": str(assignment),
                "Idempotency-Key": str(new_record_id()),
            },
            content=payload,
        )
        assert not errors, "\n".join(errors)
        assert response.status_code == 202, response.text
        receipt = response.json()
        assert receipt["status"] == "accepted" and receipt["replayed"] is False
        assert len(calls) == 1
        operation_id = UUID(receipt["operation_id"])
        async with f.factory() as session:
            operation = await session.get(SubmissionIntakeOperation, str(operation_id))
            assert operation.state == "finalization_pending"
            source = SubmissionIntakeRepository._sealed_source(operation)
        accepted.append((str(task), str(assignment), operation_id, source))

    results = []
    bootstrap, store = _local_store(settings, f.namespace)
    try:
        for task, assignment, operation_id, source in accepted:
            submission_id = await finalize_retained_intake(f.factory, SimpleNamespace(
                operation_id=operation_id, settings=settings, store=store, namespace=f.namespace,
            ))
            results.append((task, assignment, source, submission_id))

        replicas, contents, bindings = set(), set(), set()
        async with f.factory() as session:
            for task, assignment, source, submission_id in results:
                operation = await session.get(SubmissionIntakeOperation, str(source.location.operation_id))
                assert SubmissionIntakeRepository._sealed_source(operation) == source
                dispatch = await session.get(SubmissionDispatch, submission_id)
                assert (dispatch.task_id, dispatch.assignment_id, dispatch.submission_version) == (task, assignment, 1)
                assert dispatch.admission_id == operation.finalized_admission_id
                binding = await session.get(ArtifactBinding, dispatch.artifact_binding_id)
                admission = await session.get(SubmissionBundleAdmission, dispatch.admission_id)
                replica = await session.get(ArtifactReplica, admission.verified_replica_id)
                content = await session.get(ArtifactContent, dispatch.artifact_content_id)
                charge = await session.get(SubmissionSourceCharge, operation.id)
                assert binding.resource_type == "submission" and binding.resource_id == submission_id
                assert binding.content_id == admission.artifact_content_id == replica.content_id == content.id
                assert admission.status == "consumed" and admission.consumed_by_submission_id == submission_id
                assert admission.source_operation_id == replica.source_operation_id == operation.id
                assert replica.provider_object_ref == operation.object_ref == source.location.object_ref
                assert (content.sha256, content.byte_count) == (source.raw_sha256, len(payload))
                assert (charge.state, charge.accounted_bytes) == ("sealed", len(payload))
                replicas.add(replica.id)
                bindings.add(binding.id)
                contents.add(content.id)

        assert len(replicas) == len(bindings) == 2
        assert len(contents) == 1
        assert len({source.location.object_ref for _, _, source, _ in results}) == 2
        for _, _, source, _ in results:
            async with aclosing(store.open_source(source)) as reader:
                assert b"".join([chunk async for chunk in reader]) == payload
    finally:
        bootstrap.close()


async def test_public_minimal_submission_survives_acceptance_finalization_and_replay(
    admission_intake, tmp_path, monkeypatch,
):
    """The four-input command emits no text warnings and retains its replay identity."""
    from uuid import UUID
    from sqlalchemy import text
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.test_artifact_admission import _local_store
    from tests.test_trusted_intake import _archive

    f, payload, key = admission_intake, _archive(), new_record_id()
    client, settings, errors, calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, "completed",
    )
    route = f"/api/v1/tasks/{f.task}/submissions"
    headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
        "Idempotency-Key": str(key),
    }
    first = await client.post(route, headers=headers, content=payload)
    assert not errors, "\n".join(errors)
    assert first.status_code == 202, first.text
    receipt = first.json()
    assert receipt["status"] == "accepted" and receipt["replayed"] is False
    status_path = f"/api/v1/actors/me/assignments/{f.assignment}"
    pending = await client.get(status_path, headers=f.access.target.headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()["current_status"] == "evaluation_pending"
    assert pending.json()["next_action"] == "awaiting_evaluation"
    assert pending.json()["assignment"]["task_id"] == str(f.task)
    assert pending.json()["assignment"]["assignment_id"] == str(f.assignment)
    assert pending.json()["assignment"]["latest_submission"] is None
    assert pending.json()["intake"]["pre_submission_results"] == receipt["pre_submission_results"]
    assert (await client.get(
        f"/api/v1/actors/me/assignments/{new_record_id()}", headers=f.access.target.headers,
    )).status_code == 404
    warnings = [item["warning_code"] for item in receipt["pre_submission_results"]
                if item["source"] == "workstream_default" and item["status"] == "warning"]
    assert warnings == []
    replay = await client.post(route, headers=headers, content=payload)
    assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
    changed = await client.post(route, headers=headers | {"X-Submission-Feedback": "now supplied"},
                                content=payload)
    assert changed.status_code == 409, changed.text
    assert changed.json()["error"]["code"] == "submission_idempotency_conflict"
    assert len(calls) == 1 and not errors, errors
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(Submission)) == 0

    bootstrap, store = _local_store(settings, f.namespace)
    try:
        submission_id = await finalize_retained_intake(f.factory, SimpleNamespace(
            operation_id=UUID(receipt["operation_id"]), settings=settings,
            store=store, namespace=f.namespace,
        ))
    finally:
        bootstrap.close()
    finalized = await client.get(status_path, headers=f.access.target.headers)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["assignment"]["latest_submission"]["submission_id"] == str(submission_id)
    assert finalized.json()["current_status"] == "evaluation_pending"
    replay = await client.post(route, headers=headers, content=payload)
    assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
    assert len(calls) == 1 and not errors, errors
    async with f.factory() as session:
        stored = await session.get(Submission, submission_id)
        assert stored.summary is stored.worker_attestation is stored.feedback is None
        assert await session.scalar(select(func.count()).select_from(Submission)) == 1
        admission = (await session.scalars(select(SubmissionBundleAdmission))).one()
        assert admission.status == "consumed"
        assert admission.packet_sha256 == SubmissionPacketView().sha256
        assert await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun)) == 1
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges")) == 1


async def test_public_source_submission_retains_nonblocking_feedback_on_replay(
    admission_intake, tmp_path, monkeypatch,
):
    """A passed PRE keeps coverage gaps visible through acceptance and T5."""
    from uuid import UUID
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.test_artifact_admission import _local_store
    from tests.test_trusted_intake import _archive

    coverage = {
        "check_id": "coverage.files", "code": "coverage.unreadable",
        "level": "coverage_incomplete", "message": "One file was not evaluated.",
        "path": "results/vendor.bin", "line": None,
    }
    f, payload = admission_intake, _archive()
    client, settings, errors, calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, "completed",
        project_findings=(coverage,),
    )
    route = f"/api/v1/tasks/{f.task}/submissions"
    headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
        "Idempotency-Key": str(new_record_id()),
    }
    first = await client.post(route, headers=headers, content=payload)
    assert not errors, "\n".join(errors)
    assert first.status_code == 202, first.text
    receipt = first.json()
    feedback = receipt["pre_submission_results"]
    external = [item for item in feedback if item["source"] == "project_external_checker"]
    assert [(item["status"], item["findings"]) for item in external] == [("passed", [coverage])]
    assert all(item["status"] == "passed" for item in feedback
               if item["source"] == "workstream_default" and "check_id" in item)
    replay = await client.post(route, headers=headers, content=payload)
    assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
    assert len(calls) == 1 and not errors, errors

    bootstrap, store = _local_store(settings, f.namespace)
    try:
        submission_id = await finalize_retained_intake(f.factory, SimpleNamespace(
            operation_id=UUID(receipt["operation_id"]), settings=settings,
            store=store, namespace=f.namespace,
        ))
    finally:
        bootstrap.close()
    async with f.factory() as session:
        stored = await session.get(Submission, submission_id)
        assert (stored.attempt_status, stored.decided_at) == ("evaluation_pending", None)
        pre_run = (await session.scalars(select(SelectedPreSubmitRun.id).where(
            SelectedPreSubmitRun.task_id == str(f.task),
        ))).one()
    assert len(calls) == 1 and not errors, errors
    await assert_upgrade_refuses_stale_findings(
        f.factory, store="selected_pre_submit_runs", row_id=pre_run,
    )


async def test_public_submission_infrastructure_error_is_retryable_only_for_sql():
    """Known database failure is bounded; a programming defect is not relabeled."""
    from app.adapters.artifacts import ConfiguredSubmissionCommand
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure
    actor = SimpleNamespace(actor_profile_id=new_record_id(), identity_link_id=new_record_id())
    command = ConfiguredSubmissionCommand(settings=None, sessions=None, context=actor)
    command._submit = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    arguments = dict(actor_id=actor.actor_profile_id, identity_link_id=actor.identity_link_id,
                     idempotency_key=new_record_id(), declared_raw_bytes=None)
    with pytest.raises(SubmissionIntakeFailure) as failure:
        await command.submit(None, None, **arguments)
    assert failure.value.code == "submission_infrastructure_unavailable"
    command._submit.side_effect = RuntimeError("invalid composition")
    with pytest.raises(RuntimeError, match="invalid composition"):
        await command.submit(None, None, **arguments)


async def test_public_initial_submission_replays_and_recovers_accepted_upload(
    admission_intake, tmp_path, monkeypatch,
):
    """Lost acceptance recovers without upload/PRE and retains current authority."""
    from uuid import UUID
    from sqlalchemy import text
    from app.adapters.artifacts.local import LocalStorageAdapter
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.authorization.task_authority.test_postgresql import grant
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.test_artifact_admission import _local_store
    from tests.test_trusted_intake import _archive

    f, payload = admission_intake, _archive()
    client, settings, errors, calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, "completed",
    )
    route = f"/api/v1/tasks/{f.task}/submissions"
    headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
        "Idempotency-Key": str(new_record_id()), "X-Submission-Feedback": "Completed work",
    }
    duplicate = await client.post(route, headers=list(headers.items()) + [
        ("Idempotency-Key", headers["Idempotency-Key"]),
    ], content=payload)
    assert duplicate.status_code == 422, duplicate.text
    assert duplicate.json()["error"]["code"] == "submission_packet_invalid"

    foreign = await f.access.signed.actor("foreign-submission-contributor")
    await grant(SimpleNamespace(signed=f.access.signed, target=foreign), f.manager, f.project)
    denied_actor = await client.post(route, headers=headers | foreign.headers, content=payload)
    assert denied_actor.status_code == 404, denied_actor.text
    assert denied_actor.json()["error"]["code"] == "submission_unavailable"
    denied_assignment = await client.post(route, headers=headers | {
        "X-Task-Assignment-Id": str(new_record_id()),
    }, content=payload)
    assert denied_assignment.status_code == 404, denied_assignment.text
    assert denied_assignment.json()["error"]["code"] == "submission_unavailable"
    denied_uri = await client.post(route, headers=headers | {"Content-Type": "application/json"},
                                  json={"package_uri": "s3://caller-controlled/bundle.zip"})
    assert denied_uri.status_code == 415, denied_uri.text
    assert denied_uri.json()["error"]["code"] == "submission_media_type_unsupported"
    assert calls == []
    async with f.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 0
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges")) == 0

    first = await client.post(route, headers=headers, content=payload)
    assert not errors, "\n".join(errors)
    assert first.status_code == 202, first.text
    receipt = first.json()
    assert receipt["status"] == "accepted" and receipt["replayed"] is False

    async def no_new_upload(*args, **kwargs):
        raise AssertionError("accepted replay invoked another provider upload")

    with monkeypatch.context() as replay_patch:
        replay_patch.setattr(LocalStorageAdapter, "begin_source_upload", no_new_upload)
        replay_patch.setattr(LocalStorageAdapter, "upload_source_part", no_new_upload)
        replay_patch.setattr(LocalStorageAdapter, "complete_source_upload", no_new_upload)
        replay = await client.post(route, headers=headers, content=payload)
        assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
        changed_payload = _archive(content=b"modified work")
        assert changed_payload != payload and len(changed_payload) == len(payload)
        changed_body = await client.post(route, headers=headers, content=changed_payload)
        assert changed_body.status_code == 409, changed_body.text
        assert changed_body.json()["error"]["code"] == "submission_idempotency_conflict"
        changed = await client.post(route, headers=headers | {"X-Submission-Feedback": "changed"},
                                    content=payload)
        assert changed.status_code == 409, changed.text
        assert changed.json()["error"]["code"] == "submission_idempotency_conflict"
        foreign_replay = await client.post(route, headers=headers | foreign.headers, content=payload)
        assert foreign_replay.status_code == 404, foreign_replay.text
        assert foreign_replay.json()["error"]["code"] == "submission_unavailable"
    assert len(calls) == 1 and not errors, errors
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(Submission)) == 0

    bootstrap, store = _local_store(settings, f.namespace)
    try:
        submission_id = await finalize_retained_intake(f.factory, SimpleNamespace(
            operation_id=UUID(receipt["operation_id"]), settings=settings,
            store=store, namespace=f.namespace,
        ))
    finally:
        bootstrap.close()
    replay = await client.post(route, headers=headers, content=payload)
    assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
    history = await client.get(route, headers=f.access.target.headers)
    assert history.status_code == 200, history.text
    assert [item["id"] for item in history.json()["items"]] == [str(submission_id)]
    assert history.json()["items"][0]["feedback"] == headers["X-Submission-Feedback"]
    assert history.json()["items"][0]["summary"] is None
    async with f.factory.begin() as session:
        profile = await session.get(ActorProfile, str(f.actor.actor_profile_id))
        profile.status = "suspended"
        profile.suspended_by = "intake-test"
        profile.suspended_at = datetime.now(UTC)
        profile.suspension_reason = "test suspension"
    revoked = await client.post(route, headers=headers, content=payload)
    assert revoked.status_code == 404, revoked.text
    assert revoked.json()["error"]["code"] == "submission_unavailable"
    assert len(calls) == 1 and not errors, errors
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(Submission)) == 1
        stored = await session.get(Submission, submission_id)
        assert stored.version == 1
        assert stored.feedback == headers["X-Submission-Feedback"]
        assert stored.summary is stored.worker_attestation is None
        assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
        assert await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun)) == 1
        charge = (await session.execute(text(
            "SELECT operation_id,state,accounted_bytes FROM submission_source_charges"
        ))).one()
        assert tuple(charge) == (UUID(receipt["operation_id"]), "sealed", len(payload))
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 1
        admission = (await session.scalars(select(SubmissionBundleAdmission))).one()
        assert admission.status == "consumed"
        assert stored.submission_bundle_admission_id == admission.id


async def test_public_checker_remediation_uses_exact_predecessor(
    isolated_database_env, tmp_path, monkeypatch,
):
    """A revision ZIP retains its exact failed predecessor through T4/T5 replay."""
    from uuid import UUID
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.retained_material_fixtures import finalize_retained_intake

    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        payload = revision_archive(h.data)
        route = f"/api/v1/tasks/{h.request.task_id}/submissions"
        headers = {
            "Content-Type": "application/zip",
            "X-Task-Assignment-Id": str(h.request.assignment_id),
            "Idempotency-Key": str(new_record_id()),
        }
        async with _client(h, monkeypatch, isolated_database_env) as client:
            client, settings, errors, calls = await configure_source_http(
                h.factory, client, tmp_path, monkeypatch, payload, "completed",
            )
            # The predecessor's source fixture already locked this namespace
            # to a 16 MiB test capacity; the revision must use the same profile.
            settings = settings.model_copy(update={"submission_execution_profile": {
                **settings.submission_execution_profile,
                "capacity": {"maximum_total_bytes": 16 * 1024**2},
            }})
            monkeypatch.setattr(client._transport.app.state, "settings", settings)
            created = await client.post(route, headers=headers, content=payload)
            assert not errors, "\n".join(errors)
            async with h.factory() as session:
                runs = (await session.scalars(select(SelectedPreSubmitRun))).all()
                diagnostics = [(run.status, run.terminal_json) for run in runs]
            assert created.status_code == 202, (created.text, calls, diagnostics)
            receipt = created.json()
            assert receipt["status"] == "accepted" and receipt["replayed"] is False
            replay = await client.post(route, headers=headers, content=payload)
            assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
            assert len(calls) == 1 and not errors, errors
            async with h.factory() as session:
                assert await session.scalar(select(func.count()).select_from(Submission)) == 1
            submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
                operation_id=UUID(receipt["operation_id"]), settings=settings,
                store=h.store.wrapped, namespace=h.namespace,
            ))
            replay = await client.post(route, headers=headers, content=payload)
            assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
            assert len(calls) == 1 and not errors, errors
            history = await client.get(route)
            assert history.status_code == 200, history.text
            assert {item["id"] for item in history.json()["items"]} == {
                str(h.created.submission_id), str(submission_id),
            }

        async with h.factory() as session:
            successor = await session.get(Submission, submission_id)
            assert successor.version == 2
            assert successor.supersedes_submission_id == str(h.created.submission_id)
            admission = await session.get(SubmissionBundleAdmission, successor.submission_bundle_admission_id)
            assert admission.status == "consumed"
            assert admission.source_operation_id == receipt["operation_id"]
            assert admission.selected_pre_submit_run_id == str(calls[0])
            assert await session.scalar(select(func.count()).select_from(Submission)) == 2
            assert await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun)) == 2
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 2


async def test_confirmed_intake_deadline_persists_terminal_failure_and_replays(
    admission_intake, tmp_path, monkeypatch,
):
    """A simulated provider deadline retains exact failure/cleanup custody on replay."""
    from sqlalchemy import text
    from app.modules.artifacts.models import SubmissionBundleDurableIntent
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.test_trusted_intake import _archive

    f, payload = admission_intake, _archive()
    client, _, errors, calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, "deadline_exceeded",
    )
    route = f"/api/v1/tasks/{f.task}/submissions"
    headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
        "Idempotency-Key": str(new_record_id()),
        "X-Submission-Feedback": "Completed work",
    }
    first = await client.post(route, headers=headers, content=payload)
    assert first.status_code == 503, first.text
    assert first.json()["error"]["code"] == "submission_infrastructure_unavailable"
    async with f.factory() as session:
        run = (await session.scalars(select(SelectedPreSubmitRun))).one()
        assert run.status == "infrastructure_failed"
        assert run.terminal_json["outcome"] == "infrastructure_failed"
        assert run.terminal_json["infrastructure_failure_code"] == "deadline_exceeded"
        assert run.terminal_json["execution"] is None and run.eligible is None
        invocation = run.terminal_json["invocation_receipt"]
        assert invocation["outcome"] == invocation["reason"] == "deadline_exceeded"
        assert invocation["cleanup"]["disposition"] == "pending"
        assert run.execute_evidence_id and run.finalize_evidence_id
        retained = (run.id, run.terminal_digest, run.finalize_evidence_id, run.terminal_json)
        for model in (SubmissionBundleDurableIntent, SubmissionBundleAdmission, Submission, CheckerRun, OutboxEvent):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        row = (await session.execute(text(
            "SELECT state, failure_code FROM submission_intake_operations WHERE task_id=:id"
        ), {"id": f.task})).one()
        assert tuple(row) == ("failed", "submission_infrastructure_unavailable")
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges")) == len(payload)
        assert await session.scalar(text("SELECT status FROM workstream_tasks WHERE id=:id"), {"id": f.task}) == "in_progress"
        assert await session.scalar(text("SELECT status FROM task_assignments WHERE id=:id"), {"id": f.assignment}) == "active"
    replay = await client.post(route, headers=headers, content=payload)
    assert replay.status_code == 503, replay.text
    assert replay.json()["error"]["code"] == "submission_infrastructure_unavailable"
    assert len(calls) == 1 and not errors, errors
    async with f.factory() as session:
        run = (await session.scalars(select(SelectedPreSubmitRun))).one()
        assert (run.id, run.terminal_digest, run.finalize_evidence_id, run.terminal_json) == retained
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 1
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges")) == len(payload)
