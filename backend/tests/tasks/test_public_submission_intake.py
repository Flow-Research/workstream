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


def test_optional_public_text_keeps_metadata_and_retained_packet_bounds():
    """Empty ASCII headers normalize; retained packets keep their UTF-8 bound."""
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata

    base = {"task_id": new_record_id(), "assignment_id": new_record_id()}
    omitted = SubmissionIntakeMetadata(**base)
    empty = SubmissionIntakeMetadata(**base, summary="", contributor_attestation="")
    assert omitted.summary == omitted.contributor_attestation == ""
    assert omitted.metadata_sha256() == empty.metadata_sha256()
    assert SubmissionIntakeMetadata(**base, summary="x" * 65536).summary == "x" * 65536
    with pytest.raises(ValueError):
        SubmissionIntakeMetadata(**base, summary="x" * 65537)
    with pytest.raises(ValueError, match="printable ASCII"):
        SubmissionIntakeMetadata(**base, summary="é")
    assert SubmissionPacketView("é" * 32768, "").sha256
    with pytest.raises(ValueError, match="submission packet text is invalid"):
        SubmissionPacketView("é" * 32769, "")


async def test_public_optional_packet_text_survives_acceptance_finalization_and_replay(
    admission_intake, tmp_path, monkeypatch,
):
    """Omitted and empty headers retain warning-only packet facts through T5."""
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
    warnings = [item["warning_code"] for item in receipt["pre_submission_results"]
                if item["source"] == "workstream_default" and item["status"] == "warning"]
    assert warnings == ["submission_summary_missing", "submission_attestation_missing"]
    empty_headers = headers | {"X-Submission-Summary": "", "X-Contributor-Attestation": ""}
    replay = await client.post(route, headers=empty_headers, content=payload)
    assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
    changed = await client.post(route, headers=headers | {"X-Submission-Summary": "now supplied"},
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
    replay = await client.post(route, headers=empty_headers, content=payload)
    assert replay.status_code == 202 and replay.json() == dict(receipt, replayed=True), replay.text
    assert len(calls) == 1 and not errors, errors
    async with f.factory() as session:
        stored = await session.get(Submission, submission_id)
        assert stored.summary == stored.worker_attestation == ""
        assert await session.scalar(select(func.count()).select_from(Submission)) == 1
        admission = (await session.scalars(select(SubmissionBundleAdmission))).one()
        assert admission.status == "consumed"
        assert admission.packet_sha256 == SubmissionPacketView("", "").sha256
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
        "Idempotency-Key": str(new_record_id()), "X-Submission-Summary": "Completed work",
        "X-Contributor-Attestation": "I completed this work",
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
    denied_predecessor = await client.post(route, headers=headers | {
        "X-Predecessor-Submission-Id": str(new_record_id()),
    }, content=payload)
    assert denied_predecessor.status_code == 409, denied_predecessor.text
    assert denied_predecessor.json()["error"]["code"] == "task_submission_predecessor_changed"
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
        changed = await client.post(route, headers=headers | {"X-Submission-Summary": "changed"},
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
        assert stored.summary == headers["X-Submission-Summary"]
        assert stored.worker_attestation == headers["X-Contributor-Attestation"]
        assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
        assert await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun)) == 1
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges")) == 1
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
            "X-Predecessor-Submission-Id": str(h.created.submission_id),
            "X-Revision-Preparation-Id": str(h.revision_preparation_id),
            "X-Revision-Preparation-Sha256": h.revision_preparation_sha256,
            "X-Submission-Summary": h.creation_request.summary,
            "X-Contributor-Attestation": h.creation_request.contributor_attestation,
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
            denied = await client.post(route, headers=headers | {
                "X-Predecessor-Submission-Id": str(new_record_id()),
            }, content=payload)
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "task_submission_predecessor_changed"
            assert calls == []

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
        "X-Submission-Summary": "Completed work", "X-Contributor-Attestation": "I completed this work",
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
