"""Public admission-backed intake against real TASK/ART owners and PostgreSQL."""

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

from app.core.api_controls import StructuredHTTPException
from app.core.config import Settings, get_settings
from app.core.identifiers import new_record_id
from app.api.deps.rate_controls import get_rate_control_service
from app.db.session import get_db_session
from app.main import create_app
from app.modules.artifacts.models import ArtifactPutAttempt, SubmissionBundleAdmission
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.router import create_admission_backed_submission
from app.modules.tasks.schemas import AdmissionBackedSubmissionCreate
from app.modules.api_controls.service import AUTHORIZATION_READ_SCOPE, RateControlService
from app.modules.actors.models import ActorProfile
from tests.tasks.test_submission_lineage import _prepared_packet
from tests.test_artifact_admission import _context, _seed_human_actor
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.post_submit_routing.backfill_support import assert_upgrade_refuses_stale_findings
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_lineage_support import _verified_admission, _verify_put_attempt
from tests.test_submission_predecessor_custody import (
    _fixture_revision_context, _replacement_request,
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


async def test_public_malformed_zip_returns_bounded_422_without_effects(
    isolated_database_env, tmp_path, monkeypatch,
):
    """Reject unreadable contributor bytes before PRE, provider, or lifecycle effects."""
    async with _prepared_packet(isolated_database_env, tmp_path, verify=False) as h:
        route = f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations"
        headers = {
            "Content-Type": "application/zip",
            "X-Task-Assignment-Id": str(h.assignment_id),
            "Idempotency-Key": str(new_record_id()),
            "X-Submission-Summary": h.preparation_request.summary,
            "X-Contributor-Attestation": h.preparation_request.contributor_attestation,
        }
        counted_models = (
            Submission,
            SubmissionBundleAdmission,
            SelectedPreSubmitRun,
            CheckerRun,
            ArtifactPutAttempt,
            OutboxEvent,
        )

        async with _client(
            h,
            monkeypatch,
            isolated_database_env,
            raise_app_exceptions=False,
        ) as client:
            async with h.factory() as session:
                before_count_values = []
                for model in counted_models:
                    before_count_values.append(
                        await session.scalar(select(func.count()).select_from(model))
                    )
                before_counts = tuple(before_count_values)
                task = await session.get(WorkstreamTask, str(h.task_id))
                assignment = await session.get(TaskAssignment, str(h.assignment_id))
                before_state = (task.status, assignment.status)

            from app.adapters.artifacts.local import LocalStorageAdapter
            from app.modules.artifacts.selected_pre_submit_execution import (
                SelectedPreSubmitExecutionService,
            )

            async def unexpected_effect(*_args, **_kwargs):
                raise AssertionError("archive rejection reached checker or provider effects")

            with monkeypatch.context() as patch:
                patch.setattr(LocalStorageAdapter, "put", unexpected_effect)
                patch.setattr(
                    SelectedPreSubmitExecutionService, "execute", unexpected_effect,
                )
                response = await client.post(
                    route,
                    headers=headers,
                    content=b"PK\x03\x04not-a-readable-zip",
                )

            async with h.factory() as session:
                after_count_values = []
                for model in counted_models:
                    after_count_values.append(
                        await session.scalar(select(func.count()).select_from(model))
                    )
                after_counts = tuple(after_count_values)
                task = await session.get(WorkstreamTask, str(h.task_id))
                assignment = await session.get(TaskAssignment, str(h.assignment_id))
                after_state = (task.status, assignment.status)

            assert after_counts == before_counts
            assert after_state == before_state == ("in_progress", "active")
            assert not tuple((h.settings.artifact_scratch_root / "files").iterdir())
            assert not tuple((h.settings.artifact_scratch_root / "workspaces").iterdir())
            assert response.status_code == 422, response.text
            payload = response.json()
            assert payload["detail"] == "submission_archive_malformed"
            assert payload["error"] == {
                "code": "invalid_request",
                "message": "Invalid request",
                "details": {},
                "correlation_id": response.headers["X-Correlation-ID"],
                "retryable": False,
            }
            rendered = response.text
            assert all(
                value not in rendered
                for value in ("/tmp/", "s3://", "not-a-readable-zip", "BadZipFile")
            )

            valid = await client.post(
                route,
                headers=headers | {"Idempotency-Key": str(new_record_id())},
                content=h.archive_bytes,
            )
            assert valid.status_code == 202, valid.text
            assert valid.json()["submission_bundle_preparation_status"] == (
                "stored_pending_verification"
            )


def test_optional_public_text_keeps_packet_utf8_byte_limit():
    """The new nullable body still uses the existing exact packet byte bound."""
    base = {"admission_id": str(new_record_id()), "assignment_id": str(new_record_id())}
    assert set(AdmissionBackedSubmissionCreate.model_json_schema()["required"]) == {
        "admission_id", "assignment_id",
    }
    for value in (None, ""):
        packet = AdmissionBackedSubmissionCreate.model_validate(
            base | {"summary": value, "contributor_attestation": value}
        )
        assert packet.summary == value
        assert packet.contributor_attestation == value
    omitted = AdmissionBackedSubmissionCreate.model_validate(base)
    assert omitted.summary is None and omitted.contributor_attestation is None
    canonical = SubmissionCreationRequest(
        admission_id=new_record_id(), task_id=new_record_id(),
        assignment_id=new_record_id(), contributor_id=new_record_id(),
        predecessor_submission_id=None, summary="", contributor_attestation="",
    )
    assert SubmissionPacketView(
        canonical.summary, canonical.contributor_attestation,
    ).sha256 == SubmissionPacketView("", "").sha256
    assert SubmissionPacketView("é" * 32768, "").sha256
    with pytest.raises(ValueError, match="submission packet text is invalid"):
        SubmissionPacketView("é" * 32769, "")


async def test_public_optional_packet_text_round_trips_through_ready_admission(
    isolated_database_env, tmp_path, monkeypatch,
):
    """Omitted, null and empty POST text match PRE's warning-only empty packet."""
    async with _prepared_packet(isolated_database_env, tmp_path) as h:
        preparation_route = f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations"
        creation_route = f"/api/v1/tasks/{h.task_id}/submissions"
        key = new_record_id()
        headers = {
            "Content-Type": "application/zip",
            "X-Task-Assignment-Id": str(h.assignment_id),
            "Idempotency-Key": str(key),
        }
        async with _client(h, monkeypatch, isolated_database_env) as client:
            prepared = await client.post(
                preparation_route, headers=headers, content=h.archive_bytes,
            )
            assert prepared.status_code == 202, prepared.text
            assert prepared.json()["submission_bundle_preparation_status"] == "stored_pending_verification"
            assert prepared.json()["admission_id"] is None
            admission_id = await _verify_put_attempt(
                h.factory, h.store, h.namespace, h.settings,
                prepared.json()["put_attempt_id"],
            )
            ready = await client.post(
                preparation_route,
                headers=headers | {
                    "X-Submission-Summary": "",
                    "X-Contributor-Attestation": "",
                },
                content=h.archive_bytes,
            )
            assert ready.status_code == 202, ready.text
            assert ready.json()["submission_bundle_preparation_status"] == "ready"
            assert ready.json()["admission_id"] == str(admission_id)
            assert ready.json()["replayed"] is True

            async with h.factory() as session:
                selected = await session.scalar(
                    select(SelectedPreSubmitRun).where(
                        SelectedPreSubmitRun.idempotency_key == str(key)
                    )
                )
                assert selected is not None
                default = selected.terminal_json["execution"]["workstream_default"]
                assert default["eligible"] is True
                assert [warning["code"] for warning in default["warnings"]] == [
                    "submission_summary_missing", "submission_attestation_missing",
                ]

            empty = _payload(h.creation, admission_id)
            empty.pop("summary")
            empty.pop("contributor_attestation")
            created = await client.post(creation_route, json=empty)
            assert created.status_code == 201, created.text
            result = created.json()
            for value in (None, ""):
                replay_packet = empty | {
                    "summary": value,
                    "contributor_attestation": value,
                }
                replay = await client.post(creation_route, json=replay_packet)
                assert replay.status_code == 201, replay.text
                assert replay.json() == result

            changed = empty | {"summary": "now supplied"}
            denied = await client.post(creation_route, json=changed)
            assert denied.status_code == 404, denied.text
            assert denied.json()["error"]["code"] == "submission_unavailable"

        async with h.factory() as session:
            stored = await session.get(Submission, result["submission_id"])
            assert stored.summary == ""
            assert stored.worker_attestation == ""
            assert await session.scalar(select(func.count()).select_from(Submission)) == 1
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "consumed"
            assert admission.packet_sha256 == SubmissionPacketView("", "").sha256


async def test_public_preparation_returns_nonblocking_feedback_on_success_and_replay(
    isolated_database_env, tmp_path, monkeypatch,
):
    """An admitted attempt keeps its coverage gap visible; replay returns it unchanged."""
    from app.adapters.checkers import _ConfiguredExternalCheckerExecution
    from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitExecutionService
    from tests.checkers.execution.support import ControlledSelectedExecution
    from tests.checkers.external.support import pre_registry_spec

    coverage = {
        "check_id": "coverage.files", "code": "coverage.unreadable",
        "level": "coverage_incomplete", "message": "One file was not evaluated.",
        "path": "results/vendor.bin", "line": None,
    }
    project_checker = ControlledSelectedExecution(verdict="passed", findings=(coverage,))

    async def locked_image(_adapter, request, grant):
        return await project_checker.execute(request, grant)

    monkeypatch.setattr(_ConfiguredExternalCheckerExecution, "execute", locked_image)
    async with _prepared_packet(
        isolated_database_env, tmp_path, pre_submit_registry_spec=pre_registry_spec(),
    ) as h:
        route = f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations"
        headers = {
            "Content-Type": "application/zip",
            "X-Task-Assignment-Id": str(h.assignment_id),
            "Idempotency-Key": str(new_record_id()),
            "X-Submission-Summary": h.preparation_request.summary,
            "X-Contributor-Attestation": h.preparation_request.contributor_attestation,
        }
        async with _client(h, monkeypatch, isolated_database_env) as client:
            prepared = await client.post(route, headers=headers, content=h.archive_bytes)
            assert prepared.status_code == 202, prepared.text
            feedback = prepared.json()["pre_submission_results"]
            external = [item for item in feedback if item["source"] == "project_external_checker"]
            assert [(item["status"], item["findings"]) for item in external] == [("passed", [coverage])]
            assert all(
                item["status"] == "passed" for item in feedback
                if item["source"] == "workstream_default" and "check_id" in item
            )
            admission_id = await _verify_put_attempt(
                h.factory, h.store, h.namespace, h.settings, prepared.json()["put_attempt_id"],
            )
            checked = len(project_checker.requests)

            async def no_new_checker(*_args, **_kwargs):
                raise AssertionError("exact replay invoked selected PRE again")

            with monkeypatch.context() as patch:
                patch.setattr(SelectedPreSubmitExecutionService, "execute", no_new_checker)
                ready = await client.post(route, headers=headers, content=h.archive_bytes)
            assert ready.status_code == 202, ready.text
            assert ready.json()["submission_bundle_preparation_status"] == "ready"
            assert ready.json()["replayed"] is True
            assert ready.json()["pre_submission_results"] == feedback

            # Intake feedback never decides the outcome: the attempt awaits evaluation.
            created = await client.post(
                f"/api/v1/tasks/{h.task_id}/submissions",
                json=_payload(h.preparation_request, admission_id),
            )
            assert created.status_code == 201, created.text
        async with h.factory() as session:
            stored = await session.get(Submission, created.json()["submission_id"])
            assert (stored.attempt_status, stored.decided_at) == ("evaluation_pending", None)
            pre_run = await session.scalar(select(SelectedPreSubmitRun.id).where(
                SelectedPreSubmitRun.task_id == str(h.task_id),
            ))
        assert len(project_checker.requests) == checked
        await assert_upgrade_refuses_stale_findings(
            h.factory, store="selected_pre_submit_runs", row_id=pre_run,
        )


async def test_public_submission_infrastructure_error_is_retryable_only_for_sql():
    """A broken command composition must not be reported as transient storage."""
    actor = SimpleNamespace(actor_profile_id=new_record_id())
    payload = AdmissionBackedSubmissionCreate(
        admission_id=new_record_id(), assignment_id=new_record_id(),
        summary="test", contributor_attestation="test",
    )
    command = SimpleNamespace(create=AsyncMock(side_effect=SQLAlchemyError("database unavailable")))
    with pytest.raises(StructuredHTTPException) as failure:
        await create_admission_backed_submission(new_record_id(), payload, actor, command)
    assert failure.value.status_code == 503
    assert failure.value.error_code == "submission_infrastructure_unavailable"
    assert failure.value.retryable is True

    command.create.side_effect = RuntimeError("invalid composition")
    with pytest.raises(RuntimeError, match="invalid composition"):
        await create_admission_backed_submission(new_record_id(), payload, actor, command)


async def test_public_initial_submission_replays_and_recovers_ready_upload(
    isolated_database_env, tmp_path, monkeypatch,
):
    async with _prepared_packet(isolated_database_env, tmp_path) as h:
        route = f"/api/v1/tasks/{h.task_id}/submissions"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            duplicate = await client.post(
                f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations",
                headers=[
                    ("Authorization", "Bearer public-intake-token"),
                    ("Content-Type", "application/zip"),
                    ("X-Task-Assignment-Id", str(h.assignment_id)),
                    ("Idempotency-Key", str(h.preparation_request.idempotency_key)),
                    ("Idempotency-Key", str(h.preparation_request.idempotency_key)),
                ],
                content=h.archive_bytes,
            )
            assert duplicate.status_code == 422, duplicate.text
            assert duplicate.json()["error"]["code"] == "submission_preparation_headers_invalid"

            # Losing a ready response can be recovered with the exact ZIP and key.
            from app.adapters.artifacts.local import LocalStorageAdapter
            from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitExecutionService

            async def no_new_put(*_args, **_kwargs):
                raise AssertionError("ready replay invoked a second provider PUT")

            async def no_new_checker(*_args, **_kwargs):
                raise AssertionError("ready replay invoked selected PRE again")

            with monkeypatch.context() as patch:
                patch.setattr(LocalStorageAdapter, "put", no_new_put)
                patch.setattr(SelectedPreSubmitExecutionService, "execute", no_new_checker)
                prepared = await client.post(
                    f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations",
                    headers={
                        "Content-Type": "application/zip",
                        "X-Task-Assignment-Id": str(h.assignment_id),
                        "Idempotency-Key": str(h.preparation_request.idempotency_key),
                        "X-Submission-Summary": h.preparation_request.summary,
                        "X-Contributor-Attestation": h.preparation_request.contributor_attestation,
                    },
                    content=h.archive_bytes,
                )
            assert prepared.status_code == 202, prepared.text
            assert prepared.json()["submission_bundle_preparation_status"] == "ready"
            assert prepared.json()["admission_id"] == str(h.admission_id)
            assert prepared.json()["replayed"] is True

            foreign_context = _context()
            async with h.factory.begin() as session:
                await _seed_human_actor(session, foreign_context)
                task = await session.get(WorkstreamTask, str(h.task_id))
                await install_submitter_grant(await session.connection(), {
                    "project": task.project_id,
                    "actor": str(foreign_context.actor_profile_id),
                })
            with monkeypatch.context() as foreign_patch:
                async with _client(
                    h, foreign_patch, isolated_database_env,
                    subject=f"human-{foreign_context.actor_profile_id}"
                ) as foreign:
                    denied_actor = await foreign.post(route, json=_payload(h.creation, h.admission_id))
                    assert denied_actor.status_code == 404, denied_actor.text
                    assert denied_actor.json()["error"]["code"] == "submission_unavailable"

            uncaused = _payload(h.creation, h.admission_id)
            uncaused["predecessor_submission_id"] = str(new_record_id())
            denied_predecessor = await client.post(route, json=uncaused)
            assert denied_predecessor.status_code == 409, denied_predecessor.text
            assert denied_predecessor.json()["error"]["code"] == "task_submission_predecessor_changed"

            client_owned = _payload(h.creation, h.admission_id)
            client_owned["package_uri"] = "s3://caller-controlled/bundle.zip"
            denied_uri = await client.post(route, json=client_owned)
            assert denied_uri.status_code == 422, denied_uri.text

            created = await client.post(route, json=_payload(h.creation, h.admission_id))
            assert created.status_code == 201, created.text
            result = created.json()
            assert result["admission_id"] == str(h.admission_id)
            assert result["submission_version"] == 1
            assert result["submission_id"]

            replay = await client.post(route, json=_payload(h.creation, h.admission_id))
            assert replay.status_code == 201, replay.text
            assert replay.json() == result

            changed = _payload(h.creation, h.admission_id)
            changed["summary"] += " changed"
            denied = await client.post(route, json=changed)
            assert denied.status_code == 404, denied.text
            assert denied.json()["error"]["code"] == "submission_unavailable"

            history = await client.get(f"/api/v1/tasks/{h.task_id}/submissions")
            assert history.status_code == 200, history.text
            assert [item["id"] for item in history.json()["items"]] == [result["submission_id"]]

            async with h.factory.begin() as session:
                profile = await session.get(ActorProfile, str(h.context.actor_profile_id))
                profile.status = "suspended"
                profile.suspended_by = "intake-test"
                profile.suspended_at = datetime.now(UTC)
                profile.suspension_reason = "test suspension"
            revoked = await client.post(route, json=_payload(h.creation, h.admission_id))
            assert revoked.status_code == 404, revoked.text
            assert revoked.json()["error"]["code"] == "submission_unavailable"

        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(Submission)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) >= 1
            assert await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun)) == 1
            assert await session.scalar(select(func.count()).select_from(ArtifactPutAttempt).where(
                ArtifactPutAttempt.producer_request_type == "submission_bundle"
            )) == 1
            admission = await session.get(SubmissionBundleAdmission, str(h.admission_id))
            assert admission.status == "consumed"


async def test_public_checker_remediation_uses_exact_predecessor(
    isolated_database_env, tmp_path, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        request = _replacement_request(
            h, revision_archive(h.data),
            predecessor_id=h.created.submission_id,
            idempotency_key=new_record_id(),
        )
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context, request,
        )
        route = f"/api/v1/tasks/{request.task_id}/submissions"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            wrong = _payload(request, admission_id)
            wrong["predecessor_submission_id"] = str(new_record_id())
            denied = await client.post(route, json=wrong)
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "task_submission_predecessor_changed"

            created = await client.post(route, json=_payload(request, admission_id))
            assert created.status_code == 201, created.text
            result = created.json()
            assert result["submission_version"] == 2

            replay = await client.post(route, json=_payload(request, admission_id))
            assert replay.status_code == 201 and replay.json() == result

        async with h.factory() as session:
            successor = await session.get(Submission, result["submission_id"])
            assert successor.supersedes_submission_id == str(h.created.submission_id)
            assert successor.submission_bundle_admission_id == str(admission_id)


async def test_confirmed_intake_deadline_persists_terminal_failure_and_replays(
    isolated_database_env, tmp_path, monkeypatch,
):
    """A drained PRE timeout commits failure once without admission or Submission."""
    from app.modules.artifacts.models import SubmissionBundleDurableIntent
    from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor

    async with _prepared_packet(isolated_database_env, tmp_path, verify=False) as h:
        calls = 0

        async def deadline_after_intake(self, material, default):
            nonlocal calls
            calls += 1
            assert default.eligible
            assert material.entries
            # ART has exported, evaluated default and awaited intake.close()
            # before invoking this project processor. Exercise its TimeoutError
            # conversion without changing the production deadline or finalizer.
            raise TimeoutError("project operation deadline")

        monkeypatch.setattr(SelectedPreSubmitProcessor, "process", deadline_after_intake)
        key = new_record_id()
        headers = {
            "Content-Type": "application/zip",
            "X-Task-Assignment-Id": str(h.assignment_id),
            "Idempotency-Key": str(key),
            "X-Submission-Summary": h.preparation_request.summary,
            "X-Contributor-Attestation": h.preparation_request.contributor_attestation,
        }
        route = f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            first = await client.post(route, headers=headers, content=h.archive_bytes)
            assert first.status_code == 503, first.text
            assert first.json()["detail"] == "deadline_exceeded"
            async with h.factory() as session:
                run = (await session.scalars(select(SelectedPreSubmitRun).where(
                    SelectedPreSubmitRun.idempotency_key == str(key)
                ))).one()
                assert run.status == "infrastructure_failed"
                assert run.terminal_json["outcome"] == "infrastructure_failed"
                assert run.terminal_json["infrastructure_failure_code"] == "deadline_exceeded"
                assert run.terminal_json["execution"] is None and run.eligible is None
                assert run.execute_evidence_id and run.finalize_evidence_id
                retained = (run.id, run.terminal_digest, run.finalize_evidence_id)
                for model in (SubmissionBundleDurableIntent, SubmissionBundleAdmission):
                    assert await session.scalar(select(func.count()).select_from(model).where(
                        model.selected_pre_submit_run_id == run.id
                    )) == 0
                assert await session.scalar(select(func.count()).select_from(Submission).where(
                    Submission.task_id == str(h.task_id)
                )) == 0
            replay = await client.post(route, headers=headers, content=h.archive_bytes)
            assert replay.status_code == 503 and replay.json()["detail"] == "deadline_exceeded"
        assert calls == 1
        async with h.factory() as session:
            run = (await session.scalars(select(SelectedPreSubmitRun).where(
                SelectedPreSubmitRun.idempotency_key == str(key)
            ))).one()
            assert (run.id, run.terminal_digest, run.finalize_evidence_id) == retained
