"""Exercise public original-guide setup through a governed contribution outcome.

Run only with isolated PostgreSQL/MinIO and an owned disposable Redis broker.
The separate-runner journey compiles manager-authored rules in the production worker.
The same-host fault drill exercises explicitly recorded guide assistance.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import ExitStack, contextmanager, nullcontext
from decimal import Decimal
import hashlib
import hmac
from importlib import import_module
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    create_artifact_store_bootstrap,
)
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.artifacts.models import (
    SubmissionBundleAdmission,
)
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.checkers.execution_repository import stored_result
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_CHECK_IDS
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.artifacts.service import artifact_storage_namespace_spec
from app.modules.tasks.models import Submission, SubmissionDispatch, WorkstreamTask
from app.adapters.artifacts import trusted_submission_intake
from app.adapters.checkers import configured_external_checker_execution
from app.interfaces.external_checker_execution import ExternalCheckerServiceHealth
from app.interfaces.trusted_submission_intake import TrustedIntakeIdentity
from tests.authorization.post_submit_routing.support import provision_router
from tests.post_submit_materialization_helpers import (
    archive_with_modes,
    provision_material_services,
)
from tests.tasks.post_submit_routing.support import revision_archive
from tests.projects.guide_activation.source_fixtures import _register_external_checker_fixture
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor
from tests.tasks.invalidation_support import provision_reconciler
from tests.test_s3_artifact_store import minio_settings

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
from api_contract_e2e import (  # noqa: E402
    api_environment, configure_scripted_model_session_environment, find_free_port, flow_settings,
)


from experiments.pilot04_external_checker_runtime.public_probe_support import (  # noqa: E402
    _assert_outbox_worker_custody, _assert_task_has_no_effects, _json, _public_project,
    _require, _started_public_task, _token, _wait_outbox_acknowledged,
    _with_fixture_file, _GOVERNED_TABLES, _fixture_hashes, _assert_input_hashes, _locked_spec, _secret_archive,
)
from experiments.pilot04_external_checker_runtime.public_submission_clients import (  # noqa: E402
    ContributorClients, seeded_issuer,
)
from cli.tests.journey.runtime import (  # noqa: E402
    _interrupt_owned_groups, _live_group_members, prepare_versioned_source_bucket,
)


def _settings_digests(settings, nonce: bytes, *, cleanup_env: dict[str, str] | None = None) -> dict[str, str]:
    """Compare every resolved setting across processes without exposing values."""
    values = settings.model_dump(mode="json")
    for name in (
        "api_rate_limit_key_secret", "pagination_cursor_hmac_secret",
        "artifact_s3_access_key_id", "artifact_s3_secret_access_key",
        "artifact_s3_session_token",
    ):
        secret = getattr(settings, name)
        values[name] = None if secret is None else secret.get_secret_value()
    if cleanup_env is not None:
        values.update(
            artifact_s3_access_key_id=cleanup_env["WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID"],
            artifact_s3_secret_access_key=cleanup_env["WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY"],
            artifact_s3_session_token=None,
        )
    return {
        name: hmac.new(
            nonce, json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        for name, value in values.items()
    }


def _celery_config_mismatches(settings, worker_app=None) -> list[str]:
    if worker_app is None:
        from app.workers.celery_app import celery_app as worker_app

    expected = {
        "celery_broker_url": settings.celery_broker_url,
        "celery_result_backend_url": settings.celery_result_backend_url,
        "celery_task_always_eager": settings.celery_task_always_eager,
    }
    actual = {
        "celery_broker_url": worker_app.conf.broker_url,
        "celery_result_backend_url": worker_app.conf.result_backend,
        "celery_task_always_eager": worker_app.conf.task_always_eager,
    }
    return [name for name in expected if expected[name] != actual[name]]


def _worker_app_module(role: str, *, recorded_assistance: bool) -> str:
    if role == "guide" and recorded_assistance:
        return "experiments.pilot04_external_checker_runtime.guide_worker"
    return "app.workers.celery_app"


def _verify_child_configuration(role: str) -> int:
    """Import the same API or worker entry point and report only mismatched keys."""
    request = json.load(sys.stdin)
    nonce = bytes.fromhex(request["nonce"])
    if role == "api":
        from app.main import app

        actual = app.state.settings
    else:
        celery_app = import_module(_worker_app_module(
            role, recorded_assistance=request["recorded_assistance"],
        )).celery_app
        actual = get_settings()
    observed = _settings_digests(actual, nonce)
    expected = request["expected"]
    mismatches = sorted(
        name for name in expected.keys() | observed.keys()
        if expected.get(name) != observed.get(name)
    )
    if role != "api":
        mismatches.extend(_celery_config_mismatches(actual, celery_app))
    print(json.dumps(sorted(set(mismatches)), separators=(",", ":")))
    return 0


def _preflight_children(settings, env: dict[str, str], cleanup_env: dict[str, str], root: Path,
                        *, recorded_assistance: bool) -> None:
    """Reject API/worker drift before starting real services or public requests."""
    nonce = os.urandom(32)
    for role in ("api", "guide", "worker", "source-cleanup"):
        child_env = cleanup_env if role == "source-cleanup" else env
        expected = _settings_digests(settings, nonce, cleanup_env=cleanup_env if role == "source-cleanup" else None)
        request = json.dumps({"nonce": nonce.hex(), "expected": expected,
                              "recorded_assistance": recorded_assistance})
        with (root / f"preflight-{role}.log").open("wb") as errors:
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    "import sys; sys.path.extend(sys.argv[1:3]); "
                    "from experiments.pilot04_external_checker_runtime."
                    "run_public_journey_probe import _verify_child_configuration; "
                    "raise SystemExit(_verify_child_configuration(sys.argv[3]))",
                    str(BACKEND.parent), str(BACKEND / "tests"), role,
                ],
                cwd=BACKEND, env=child_env, input=request, text=True,
                stdout=subprocess.PIPE, stderr=errors, timeout=300, check=False,
            )
        _require(result.returncode == 0,
                 f"{role} configuration preflight failed; see private diagnostics")
        try:
            mismatches = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError(f"{role} configuration preflight returned invalid evidence") from exc
        _require(not mismatches,
                 f"{role} configuration differs from parent: {', '.join(mismatches)}")


def _process(command: list[str], *, env: dict[str, str], log: Path) -> subprocess.Popen:
    with log.open("wb") as output:
        return subprocess.Popen(
            command, cwd=BACKEND, env=env, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True,
        )


WORKER_ROLES = (
    ("guide", "workstream.project_setup"),
    ("project-control", "workstream.project_control"),
    ("artifacts", "workstream.artifacts"),
    ("outbox-scan", "workstream.outbox_scan"),
    ("outbox", "workstream.outbox"),
    ("finalization", "workstream.submission_finalization"),
    ("source-cleanup", "workstream.source_cleanup"),
)


def _start_worker(env: dict[str, str], root: Path, role: str, queue: str,
                  generation: int = 1, *, launch=None, recorded_assistance=False) -> tuple[subprocess.Popen, str]:
    """Start one owned prefork worker for exactly one registered workload queue."""
    hostname = f"first-journey-{role}-{uuid4().hex}@localhost"
    celery_app = _worker_app_module(role, recorded_assistance=recorded_assistance)
    process = (launch or _process)([
        sys.executable, "-m", "celery", "-A", celery_app,
        "worker", "--pool=prefork", "--concurrency=1",
        f"--queues={queue}", "--hostname", hostname,
        "--without-gossip", "--without-mingle", "--without-heartbeat",
        "--loglevel=ERROR",
    ], env=env, log=root / f"{role}-worker-{generation}.log")
    return process, hostname


def _source_cleanup_environment(env: dict[str, str], settings) -> dict[str, str]:
    """Give only the deletion worker its explicitly supplied separate principal."""
    from app.modules.artifacts.api.submission_cleanup import SubmissionSourceCleanupProfile

    profile = SubmissionSourceCleanupProfile.model_validate(
        settings.submission_source_cleanup_profile
    )
    upload_key = settings.artifact_s3_access_key_id
    _require(upload_key is not None
             and profile.upload_principal == upload_key.get_secret_value(),
             "source cleanup profile does not identify the upload principal")
    cleanup_key = env.get("WORKSTREAM_CLI_JOURNEY_CLEANUP_ACCESS_KEY_ID")
    _require(bool(cleanup_key) and cleanup_key != profile.upload_principal,
             "source cleanup requires a distinct provider principal")
    secret_name = env.get("WORKSTREAM_CLI_JOURNEY_CLEANUP_SECRET_FILE")
    secret_file = Path(secret_name) if secret_name else None
    _require(secret_file is not None and secret_file.is_absolute()
             and not secret_file.is_symlink() and secret_file.is_file()
             and stat.S_IMODE(secret_file.stat().st_mode) == 0o600
             and 0 < secret_file.stat().st_size <= 4096,
             "source cleanup requires a private credential file")
    cleanup_env = dict(env)
    cleanup_env["WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID"] = cleanup_key
    cleanup_env["WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY"] = secret_file.read_text(encoding="ascii")
    for setting in ("WORKSTREAM_ARTIFACT_S3_SESSION_TOKEN", "WORKSTREAM_CLI_JOURNEY_CLEANUP_ACCESS_KEY_ID",
                    "WORKSTREAM_CLI_JOURNEY_CLEANUP_SECRET_FILE"):
        cleanup_env.pop(setting, None)
    return cleanup_env


def _require_source_runtime_window(settings):
    """Use canonical supplied transport bounds; never inherit an obsolete90s override."""
    from app.modules.artifacts.api.submission_command import SubmissionExecutionProfile
    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.modules.checkers.api.source_contracts import source_contracts_context

    _require(settings.submission_execution_profile is not None,
             "supply an explicit source execution profile before qualification")
    profile = SubmissionExecutionProfile.model_validate(settings.submission_execution_profile,
        context=source_contracts_context(selected_pre_submit_source_contracts()))
    _require(settings.external_checker_service_timeout_seconds * 1000 >= profile.runtime.aggregate_deadline_ms,
             "source profile exceeds the configured runner request timeout")
    return profile


def _require_parser_socket(settings):
    """Require an explicitly supplied existing parser; never launch a second one."""
    path = settings.guide_document_parser_socket
    _require(path.is_absolute() and not path.is_symlink() and path.is_socket(),
             "existing guide parser socket is unavailable; supply WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET")
    return path


@contextmanager
def _owned_process_interrupts(processes: list[subprocess.Popen]):
    """Reach the owned sessions before the isolation runner's short KILL grace."""
    launching = interrupted = False

    def stop_interrupted():
        _interrupt_owned_groups(processes)
        raise KeyboardInterrupt

    def interrupt(_signum, _frame):
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        if not launching:
            stop_interrupted()

    def start(command, *, env, log):
        nonlocal launching
        launching = True
        try:
            process = _process(command, env=env, log=log)
            processes.append(process)
        finally:
            launching = False
            if interrupted:
                stop_interrupted()
        return process

    with ExitStack() as restore:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous = signal.signal(signum, interrupt)
            restore.callback(signal.signal, signum, previous)
        yield start


def _stop_process(process: subprocess.Popen | None) -> None:
    """Reap a whole owned worker group even if its leader already exited."""
    if process is None:
        return
    group_id = process.pid
    if _live_group_members(group_id):
        try:
            os.killpg(group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 10
    while _live_group_members(group_id) and time.monotonic() < deadline:
        time.sleep(0.1)
    if _live_group_members(group_id):
        try:
            os.killpg(group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    while _live_group_members(group_id) and time.monotonic() < deadline:
        time.sleep(0.1)
    _require(not _live_group_members(group_id), "owned worker retained live children")
    process.wait(timeout=1)


def _stop_owned_processes(processes: tuple[subprocess.Popen | None, ...]) -> None:
    """Attempt every owned group even when one group fails to stop."""
    failures = []
    for process in processes:
        try:
            _stop_process(process)
        except Exception as error:
            failures.append(error)
    if failures:
        raise RuntimeError("owned journey worker cleanup failed") from failures[0]


async def _wait_api(origin: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 300
    async with httpx.AsyncClient(timeout=2) as client:
        while time.monotonic() < deadline:
            _require(process.poll() is None, "public API exited before readiness")
            try:
                if (await client.get(origin + "/api/v1/health")).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.25)
    raise RuntimeError("public API did not become ready")


async def _wait_worker(process: subprocess.Popen, hostname: str) -> None:
    from app.workers.celery_app import celery_app

    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        _require(process.poll() is None, "prefork worker exited before readiness")
        pong = await asyncio.to_thread(
            celery_app.control.ping, destination=[hostname], timeout=0.5
        )
        if pong:
            return
        await asyncio.sleep(0.2)
    raise RuntimeError("prefork worker did not become ready")


async def _scan_audit_count(factory) -> int:
    async with factory() as session:
        return await session.scalar(text(
            "SELECT count(*) FROM public.audit_events "
            "WHERE action_id='artifact.pending_work.scan'"
        ))


async def _wait_beat_scan(factory, process: subprocess.Popen, before: int) -> None:
    """Require a real scheduled scanner audit before public intake begins."""
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        _require(process.poll() is None, "Celery Beat exited before scheduled scan")
        if await _scan_audit_count(factory) > before:
            return
        await asyncio.sleep(2)
    raise RuntimeError("Celery Beat did not dispatch an authorized artifact scan")


async def _provision_runtime_services(factory) -> None:
    async with factory() as session, session.begin():
        for identity in (ServiceIdentity.OUTBOX_DISPATCHER,
                         ServiceIdentity.ARTIFACT_SCHEDULER,
                         ServiceIdentity.ARTIFACT_SOURCE_CLEANUP,
                         ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                         ServiceIdentity.ARTIFACT_VERIFIER,
                         ServiceIdentity.ARTIFACT_GUIDE_READER, ServiceIdentity.PROJECT_SETUP):
            existing = await session.scalar(select(ActorProfile.id).where(
                ActorProfile.service_identity == identity.value
            ))
            if existing is not None:
                continue
            actor_id = str(new_record_id())
            session.add(ActorProfile(
                id=actor_id, actor_kind="service", status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=identity.value,
                created_by=actor_id,
            ))
            session.add(ActorIdentityLink(
                id=str(new_record_id()), actor_profile_id=actor_id,
                issuer="workstream.internal", subject=identity.value,
                subject_kind="service", status="active", linked_by="workstream:system:bootstrap",
            ))


async def _project_effects_snapshot(session, project_id: UUID) -> dict[str, tuple[str, ...]]:
    """Compare complete retained owner facts without logging their private contents."""
    rows = {}
    for table in _GOVERNED_TABLES:
        values = (await session.scalars(text(
            f"SELECT to_jsonb(t) FROM public.{table} t WHERE project_id=:project"
        ), {"project": str(project_id)})).all()
        rows[table] = tuple(sorted(json.dumps(value, sort_keys=True) for value in values))
    return rows


async def _wait_known_retry(factory, event_id: UUID, project_id: UUID,
                            task_id: str, submission_id: str, *,
                            prior_effects: dict[str, tuple[str, ...]] | None = None,
                            prior_route_audits: int = 0) -> None:
    """Observe one safe non-live attempt from ordinary scheduled delivery."""
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        async with factory() as session:
            event = await session.get(OutboxEvent, event_id)
            if event.delivery_state == "retryable":
                attempt = await session.get(
                    OutboxDeliveryAttempt, (event_id, event.attempt_count)
                )
                receipt = json.loads(attempt.outcome_json)
                _require(event.attempt_count == 1
                         and event.last_error_code == "RETRY_REQUESTED"
                         and receipt["delivery_state"] == "retryable"
                         and receipt["error_code"] == "RETRY_REQUESTED"
                         and receipt["invocation_unknown"] is False
                         and event.next_attempt_at is not None,
                         "non-live completion did not record one known safe retry")
                await _assert_outbox_worker_custody(session, event, project_id)
                task = await session.get(WorkstreamTask, task_id)
                submission = await session.get(Submission, submission_id)
                _require(task.status == "evaluation_pending"
                         and submission.status == "submitted"
                         and submission.attempt_status == "evaluation_pending"
                         and submission.decided_at is None,
                         "non-live completion changed Task or Submission")
                effects = await _project_effects_snapshot(session, project_id)
                _require(effects == (prior_effects or {name: () for name in _GOVERNED_TABLES}),
                         "non-live retry changed project governed effects")
                await _assert_task_has_no_effects(session, task_id)
                _require(await session.scalar(text(
                    "SELECT count(*) FROM public.audit_events "
                    "WHERE project_id=:project AND action_id='task.post_submit.route'"
                ), {"project": str(project_id)}) == prior_route_audits,
                         "non-live retry retained routing authorization")
                return
            if event.delivery_state in {"acknowledged", "dead_letter", "cancelled"}:
                raise RuntimeError("non-live completion escaped the safe retry path")
        await asyncio.sleep(0.3)
    raise RuntimeError("Beat-discovered non-live completion did not become retryable")


async def _wait_revoked_completion(factory, event_id: UUID, project_id: UUID) -> None:
    """Require a scheduled second attempt to close after late router revocation."""
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        async with factory() as session:
            event = await session.get(OutboxEvent, event_id)
            _require(event is not None, "late-revocation completion is missing")
            if event.delivery_state == "dead_letter":
                attempts = (await session.scalars(select(OutboxDeliveryAttempt).where(
                    OutboxDeliveryAttempt.event_id == event_id
                ).order_by(OutboxDeliveryAttempt.claim_generation))).all()
                _require(event.attempt_count == 2 and len(attempts) == 2
                         and event.last_error_code == "INVOKE_OUTCOME_UNKNOWN"
                         and event.next_attempt_at is None,
                         "late authority refusal did not close the exact due retry")
                first, second = (json.loads(item.outcome_json) for item in attempts)
                _require(first["delivery_state"] == "retryable"
                         and first["error_code"] == "RETRY_REQUESTED"
                         and first["invocation_unknown"] is False
                         and second["delivery_state"] == "dead_letter"
                         and second["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
                         and second["invocation_unknown"] is True
                         and attempts[0].claim_owner != attempts[1].claim_owner,
                         "late authority refusal lost restart-separated attempt custody")
                await _assert_outbox_worker_custody(session, event, project_id)
                return
            if event.delivery_state in {"acknowledged", "cancelled"}:
                raise RuntimeError("revoked router completion escaped closed refusal")
        await asyncio.sleep(0.3)
    raise RuntimeError("Beat-discovered revoked completion did not close after restart")


async def _outbox_snapshot(factory, event_id: UUID) -> tuple:
    """Capture exact retained delivery facts around a duplicate broker message."""
    async with factory() as session:
        event = await session.get(OutboxEvent, event_id)
        _require(event is not None and event.delivery_state == "acknowledged",
                 "completion event is not acknowledged before duplicate delivery")
        attempts = (await session.scalars(
            select(OutboxDeliveryAttempt).where(
                OutboxDeliveryAttempt.event_id == event_id
            ).order_by(OutboxDeliveryAttempt.claim_generation)
        )).all()
        _require(len(attempts) == event.attempt_count,
                 "completion attempt history is incomplete")
        return (
            tuple(getattr(event, column.name) for column in OutboxEvent.__table__.columns),
            tuple(tuple(getattr(attempt, column.name)
                        for column in OutboxDeliveryAttempt.__table__.columns)
                  for attempt in attempts),
        )


async def _wait_outbox_due(factory, event_id: UUID) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        async with factory() as session:
            due = await session.scalar(text(
                "SELECT clock_timestamp() >= next_attempt_at "
                "FROM public.outbox_events WHERE event_id=:event"
            ), {"event": str(event_id)})
        if due:
            return
        await asyncio.sleep(0.2)
    raise RuntimeError("known safe outbox retry did not become due")


def _source_headers(assignment_id, archive, key, feedback=None):
    """Build the exact initial or revision wire inputs."""
    headers = {
        "Content-Type": "application/zip", "Content-Length": str(len(archive)),
        "X-Task-Assignment-Id": assignment_id, "Idempotency-Key": key,
    }
    if feedback is not None:
        headers["X-Submission-Feedback"] = feedback
    return headers


async def _finalized_source_evidence(factory, accepted, progress, expected_input):
    """Observe real T5 lineage and immutable bytes; never inject a worker or verifier."""
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitTerminalFacts

    async with factory() as session:
        operation = await session.get(SubmissionIntakeOperation, accepted["operation_id"])
        _require(operation and operation.state == "finalized"
                 and operation.finalized_submission_id == progress["submission_id"],
                 "public progress differs from retained finalization")
        admission = await session.get(SubmissionBundleAdmission, operation.finalized_admission_id)
        selected = await session.get(SelectedPreSubmitRun, operation.selected_pre_submit_run_id)
        _require(selected is not None and admission and admission.status == "consumed"
                 and admission.source_operation_id == operation.id
                 and admission.consumed_by_submission_id == progress["submission_id"]
                 and admission.selected_pre_submit_run_id == selected.id,
                 "finalized source admission differs from accepted custody")
        _assert_input_hashes(admission, expected_input)
        terminal = SelectedPreSubmitTerminalFacts.from_canonical_body(
            selected.terminal_json, source_contracts=selected_pre_submit_source_contracts())
        _require(terminal.execution and terminal.execution.eligible
                 and terminal.terminal_digest == operation.selected_pre_submit_terminal_sha256
                 and terminal.execution.observed_source.raw_sha256 == expected_input["archive_sha256"]
                 and terminal.execution.manifest_sha256 == expected_input["semantic_manifest_sha256"],
                 "retained PRE differs from the exact submitted ZIP")
        event_id, project_id = UUID(operation.finalization_event_id), UUID(operation.project_id)
        admission_id = admission.id
    await _wait_outbox_acknowledged(factory, event_id, project_id)
    return {"submission_id": progress["submission_id"], "submission_version": progress["submission_version"],
            "evaluation_request_id": progress["evaluation_request_id"], "admission_id": admission_id}


async def _await_finalized_source(client, factory, task_id, assignment_id, token, context, archive):
    """Read exact public operation progress until actual worker finalization closes."""
    accepted = context["acceptance_receipt"]
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        progress = await _json(client, "GET", f"/api/v1/tasks/{task_id}/submission-operations", token, 200,
                              params={"operation_id": accepted["operation_id"]})
        _require(progress["operation_id"] == accepted["operation_id"]
                 and progress["task_id"] == task_id and progress["assignment_id"] == assignment_id
                 and progress["idempotency_key"] == context["idempotency_key"],
                 "public finalization progress substituted command selectors")
        _require(not progress["operationally_stalled"]
                 and progress["operation_state"] in {"finalization_pending", "finalized"},
                 "accepted source finalization failed or stalled; stop without another command")
        if progress["operation_state"] == "finalized":
            _require(progress["submission_id"] and progress["submission_version"]
                     and progress["evaluation_request_id"], "finalized progress omitted exact Submission selectors")
            return await _finalized_source_evidence(factory, accepted, progress, _fixture_hashes(archive))
        await asyncio.sleep(1)
    raise RuntimeError("source finalization did not complete; no worker task was injected")


async def _replay_source_submission(client, task_id, assignment_id, token, archive, saved):
    """Replay the original command and let ART recover its frozen selection."""
    headers = _source_headers(assignment_id, archive, saved["idempotency_key"], saved["feedback"])
    repeated = await _json(client, "POST", f"/api/v1/tasks/{task_id}/submissions", token, 202,
                           headers=headers, content=archive)
    _require(repeated == dict(saved["acceptance_receipt"], replayed=True),
             "public accepted source replay changed its exact receipt")


async def _submit(client, factory, *, task_id: str, assignment_id: str,
                  contributor_token: str, archive: bytes, feedback: str | None = None,
                  submit_zip=None, replay_zip=None) -> dict:
    headers = _source_headers(assignment_id, archive, str(uuid4()), feedback)
    if submit_zip is None:
        accepted = await _json(client, "POST", f"/api/v1/tasks/{task_id}/submissions", contributor_token, 202,
                               headers=headers, content=archive)
    else:
        accepted = await submit_zip(archive, headers["Idempotency-Key"])
    _require(accepted["task_id"] == task_id and accepted["assignment_id"] == assignment_id
             and accepted["status"] == "accepted" and accepted["replayed"] is False
             and accepted["pre_submission_results"], "raw ZIP command returned an invalid accepted receipt")
    context = {"operation_id": accepted["operation_id"], "acceptance_receipt": accepted,
               "idempotency_key": headers["Idempotency-Key"], "feedback": feedback}
    if replay_zip is None:
        await _replay_source_submission(client, task_id, assignment_id, contributor_token, archive, context)
    else:
        replayed = await replay_zip(archive, context["idempotency_key"])
        _require(replayed == dict(accepted, replayed=True), "connected submission replay changed its receipt")
    return context | await _await_finalized_source(
        client, factory, task_id, assignment_id, contributor_token, context, archive)


async def _complete_post(factory, *, submission_id: str,
                         project_id: UUID, recommendation: str,
                         finding_code: str | None = None,
                         deliver_completion: bool = True, successor=None) -> tuple[str, UUID]:
    async with factory() as session:
        dispatch = await session.get(SubmissionDispatch, submission_id)
        _require(dispatch is not None, "atomic Submission dispatch is absent")
        request_event_id = dispatch.evaluation_event_id
        attempt_id = dispatch.evaluation_attempt_id
    if successor is not None:
        request_event_id, attempt_id = successor.event_id, successor.run_id
    await _wait_outbox_acknowledged(factory, request_event_id, project_id)
    async with factory() as session:
        run = await session.get(CheckerRun, attempt_id)
        _require(run.status == "completed" and run.completion_event_id is not None,
                 "selected POST did not retain completion")
        _require(run.routing_recommendation == recommendation,
                 "selected POST recommendation differs from fixture finding")
        result = stored_result(run)
        _require(result.execution is not None,
                 "selected POST lacks completed external evidence")
        members = result.execution.external_members
        _require(len(members) == 1, "selected POST did not execute one project image")
        findings = [finding.code for finding in members[0].result.findings]
        _require(findings == ([finding_code] if finding_code else []),
                 "selected POST finding differs from fixture rule")
        completion_id = run.completion_event_id
    if deliver_completion:
        await _wait_outbox_acknowledged(factory, completion_id, project_id)
    return str(attempt_id), completion_id


async def _assert_revision(factory, *, project_id: UUID, task_id: str,
                           submission_id: str, attempt_id: str) -> None:
    async with factory() as session:
        task = await session.get(WorkstreamTask, task_id)
        _require(task.status == "needs_revision",
                 "failed selected POST did not route the Task to needs_revision")
        source = await session.get(Submission, submission_id)
        _require(source is not None and source.status == "submitted",
                 "failed selected POST changed the immutable submitted source")
        _require(source.attempt_status == "needs_revision" and source.decided_at is not None,
                 "failed selected POST did not record the needs_revision attempt outcome")
        manifest = (await session.execute(text(
            "SELECT submission_id,checker_run_id,routing_recommendation "
            "FROM public.task_post_submit_routing_manifests "
            "WHERE project_id=:project"
        ), {"project": str(project_id)})).one()
        _require(str(manifest.submission_id) == submission_id
                 and str(manifest.checker_run_id) == attempt_id
                 and manifest.routing_recommendation == "needs_revision",
                 "revision route lost exact failed checker lineage")
        for table in ("final_acceptances", "contribution_records",
                      "compensation_awards", "reviews"):
            count = await session.scalar(text(
                f"SELECT count(*) FROM public.{table} WHERE project_id=:project"
            ), {"project": str(project_id)})
            _require(count == 0, "revision minted final or economic evidence")


async def _assert_outcome(factory, *, guide_source, project_id: UUID, task_id: str,
                          submission_id: str, initial_submission_id: str,
                          contributor_id: UUID,
                          human_review_required: bool, expected_awards: int,
                          expected_submissions: int, expected_inputs: dict) -> dict:
    async with factory() as session:
        task = await session.get(WorkstreamTask, task_id)
        submission = await session.get(Submission, submission_id)
        _require(task.status == ("review_pending" if human_review_required else "accepted"),
                 "governed Task outcome differs")
        _require(submission is not None and submission.submission_bundle_admission_id is not None,
                 "Submission lacks consumed immutable admission")
        _require(submission.attempt_status == ("review_pending" if human_review_required else "accepted")
                 and (submission.decided_at is None) == human_review_required,
                 "governed Submission attempt outcome differs")
        for field, expected in guide_source.evidence["locked_context"].items():
            _require(str(getattr(task, field)) == str(expected)
                     and str(getattr(submission, field)) == str(expected),
                     f"{field} differs from the public guide approval")
        _require(str(task.locked_contribution_policy_version_id)
                 == guide_source.activation["contribution_policy_version_id"],
                 "Task did not retain the publicly published ContributionPolicy")
        _require(submission.locked_post_submit_checker_policy_hash == task.locked_post_submit_checker_policy_hash,
                 "Submission POST policy differs from locked Task")
        _require(submission.contribution_policy_version_id == task.locked_contribution_policy_version_id,
                 "Submission contribution policy differs from locked Task")
        dispatch = await session.get(SubmissionDispatch, submission_id)
        _require(dispatch is not None, "governed Submission lost its atomic dispatch")
        if human_review_required:
            source = await session.get(Submission, initial_submission_id)
            source_admission = await session.get(
                SubmissionBundleAdmission, source.submission_bundle_admission_id
            ) if source is not None else None
            replacement_admission = await session.get(
                SubmissionBundleAdmission, submission.submission_bundle_admission_id
            )
            _require(source is not None and source.version == 1
                     and submission.version == 2
                     and submission.supersedes_submission_id == initial_submission_id
                     and source_admission is not None
                     and source_admission.status == "consumed"
                     and source_admission.consumed_by_submission_id == initial_submission_id
                     and source_admission.consumed_by_submission_version == 1
                     and replacement_admission is not None
                     and replacement_admission.status == "consumed"
                     and replacement_admission.consumed_by_submission_id == submission_id
                     and replacement_admission.consumed_by_submission_version == 2
                     and replacement_admission.predecessor_submission_id == initial_submission_id
                     and replacement_admission.predecessor_submission_version == 1
                     and source_admission.archive_sha256 != replacement_admission.archive_sha256
                     and dispatch.creation_kind == "checker_remediation"
                     and dispatch.checker_remediation_manifest_id
                     == replacement_admission.checker_remediation_manifest_id,
                     "replacement lost exact failed predecessor custody")
        admission = await session.get(
            SubmissionBundleAdmission, submission.submission_bundle_admission_id
        )
        _require(admission is not None and admission.status == "consumed"
                 and admission.consumed_by_submission_id == submission_id,
                 "governed Submission lost its consumed admission")
        for identifier, expected in expected_inputs.items():
            retained = await session.get(Submission, identifier)
            retained_admission = await session.get(SubmissionBundleAdmission, retained.submission_bundle_admission_id)
            _assert_input_hashes(retained_admission, expected)
        counts = {}
        for name in ("submissions", "final_acceptances", "contribution_records",
                     "compensation_awards", "reviews"):
            counts[name] = await session.scalar(text(
                "SELECT count(*) FROM public.submissions s "
                "JOIN public.workstream_tasks t ON t.id=s.task_id "
                "WHERE t.project_id=:project"
                if name == "submissions" else
                f"SELECT count(*) FROM public.{name} WHERE project_id=:project"
            ), {"project": str(project_id)})
        _require(counts == {
            "submissions": expected_submissions,
            "final_acceptances": int(not human_review_required),
            "contribution_records": int(not human_review_required),
            "compensation_awards": expected_awards,
            "reviews": 0,
        }, "governed record counts differ")
        if not human_review_required:
            row = (await session.execute(text(
                "SELECT c.id,c.contributor_id,c.submission_id,c.source_review_id,"
                "c.source_final_acceptance_id,c.source_task_assignment_id,c.artifact_hash,"
                "c.contribution_policy_version_id,f.acceptance_source "
                "FROM public.contribution_records c JOIN public.final_acceptances f "
                "ON f.id=c.source_final_acceptance_id WHERE c.project_id=:project"
            ), {"project": str(project_id)})).one()
            _require(
                str(row.contributor_id) == str(contributor_id)
                and str(row.submission_id) == submission_id
                and row.source_review_id is None
                and row.source_final_acceptance_id is not None
                and row.source_task_assignment_id is not None
                and row.artifact_hash == admission.archive_sha256
                and str(row.contribution_policy_version_id) == str(submission.contribution_policy_version_id)
                and row.acceptance_source == "task_post_submit_route",
                "submitter ContributionRecord lost its exact source or artifact lineage",
            )
        if expected_awards:
            award = (await session.execute(text(
                "SELECT contribution_record_id,contributor_id,contribution_policy_version_id,"
                "instrument_type,unit_code,quantity FROM public.compensation_awards "
                "WHERE project_id=:project"
            ), {"project": str(project_id)})).one()
            _require(
                str(award.contribution_record_id) == str(row.id)
                and str(award.contributor_id) == str(contributor_id)
                and str(award.contribution_policy_version_id)
                == str(submission.contribution_policy_version_id)
                and award.instrument_type == "project_points"
                and award.unit_code == "PTS"
                and award.quantity == Decimal("7"),
                "conditional award differs from the locked contribution policy",
            )
        return counts | {"task_status": task.status}


async def _late_revocation_trial(client, factory, env, *, project_id: UUID,
                                 accepted_task_id: str, manager_token: str,
                                 contributor_token: str, operator_id: UUID,
                                 archive: bytes,
                                 stop_worker: Callable[[], None],
                                 start_worker: Callable[[], Awaitable[None]]) -> dict:
    """Revoke routing authority after real POST I/O and a known non-live retry."""
    from tests.reviews.lifecycle.transition_support import command_for, transition

    async with factory() as session:
        prior_effects = await _project_effects_snapshot(session, project_id)
        prior_route_audits = await session.scalar(text(
            "SELECT count(*) FROM public.audit_events "
            "WHERE project_id=:project AND action_id='task.post_submit.route'"
        ), {"project": str(project_id)})
    for phase in ("draining", "disabled", "shadow"):
        await transition(await command_for(operator_id, phase))

    task_id, assignment_id = await _started_public_task(
        client, project_id=str(project_id), manager_token=manager_token,
        contributor_token=contributor_token, source_ref="local-ticket-late-revocation",
    )
    saved = await _submit(
        client, factory, task_id=task_id, assignment_id=assignment_id,
        contributor_token=contributor_token,
        archive=_with_fixture_file(archive, "late-revocation-trial.txt"),
    )
    attempt_id, completion_id = await _complete_post(
        factory, submission_id=saved["submission_id"], project_id=project_id,
        recommendation="allow_review", deliver_completion=False,
    )
    await _wait_known_retry(
        factory, completion_id, project_id, task_id, saved["submission_id"],
        prior_effects=prior_effects, prior_route_audits=prior_route_audits,
    )
    stop_worker()
    async with factory() as session:
        held = await session.get(OutboxEvent, completion_id)
        _require(held.delivery_state == "retryable" and held.attempt_count == 1,
                 "late completion advanced before the worker stopped")

    administrator, _ = await seed_review_actor(
        factory, None, role="access_administrator", scope="system", issuer=seeded_issuer(env),
    )
    async with factory() as session:
        router_link = await session.scalar(
            select(ActorIdentityLink.id).join(
                ActorProfile, ActorIdentityLink.actor_profile_id == ActorProfile.id
            ).where(ActorProfile.service_identity
                    == ServiceIdentity.TASK_POST_SUBMIT_ROUTER.value)
        )
        _require(router_link is not None, "provisioned routing service link is absent")
    revoked = await _json(
        client, "POST", f"/api/v1/actor-identity-links/{router_link}/revoke",
        _token(env, administrator), 200,
        headers={"Idempotency-Key": str(uuid4())},
        json={"reason": "Exercise late post-check routing authority refusal"},
    )
    _require(revoked["resource_type"] == "actor_identity_link"
             and revoked["resource_id"] == str(router_link),
             "public revocation did not name the fixed router link")
    async with factory() as session:
        link = await session.get(ActorIdentityLink, router_link)
        _require(link.status == "revoked", "public router-link revocation did not persist")
    await transition(await command_for(operator_id, "live"))
    await _wait_outbox_due(factory, completion_id)
    await start_worker()
    await _wait_revoked_completion(factory, completion_id, project_id)
    async with factory() as session:
        task = await session.get(WorkstreamTask, task_id)
        submission = await session.get(Submission, saved["submission_id"])
        run = await session.get(CheckerRun, attempt_id)
        prior_task = await session.get(WorkstreamTask, accepted_task_id)
        _require(task.status == "evaluation_pending"
                 and submission.status == "submitted"
                 and run.status == "completed"
                 and prior_task.status == "accepted",
                 "late revocation changed a task, Submission, or completed checker result")
        await _assert_task_has_no_effects(session, task_id)
        _require(await _project_effects_snapshot(session, project_id) == prior_effects,
                 "late revocation changed the first task's governed evidence")
    return {"task_id": task_id, "submission_id": saved["submission_id"],
            "checker_run_id": attempt_id, "completion_event_id": str(completion_id),
            "outbox_state": "dead_letter", "routing_authority": "revoked_after_post_result"}


async def _one_mode(client, factory, env, *,
                    human_review_required: bool, operator_id: UUID | None,
                    stop_worker: Callable[[], None] | None = None,
                    start_worker: Callable[[], Awaitable[None]] | None = None, fault_root=None,
                    operator_token=None, clients: ContributorClients | None = None,
                    exercise_faults: bool = True, manager_authored: bool = False) -> dict:
    from experiments.pilot04_external_checker_runtime.public_hosted_attachment import HostedAttachment

    attachment = env if isinstance(env, HostedAttachment) else None
    awards = () if human_review_required or attachment else ("project_points",)
    from app.workers.outbox import deliver_event

    compilation, contributor, manager_token, contributor_token = await _public_project(
        client, factory, env, human_review_required=human_review_required, manager_authored=manager_authored,
    )
    project_id = str(compilation.project_id)
    approved_guide = await _json(
        client, "GET", f"/api/v1/projects/{project_id}/contributor-guide", contributor_token, 200,
    )
    _require(approved_guide["guide_id"] == str(compilation.guide_id)
             and approved_guide["documents"], "preclaim project guide does not match the approved originals")
    if clients is not None:
        await clients.guide(contributor, contributor_token, project_id, approved_guide)
    task_id, assignment_id = await _started_public_task(
        client, project_id=project_id, manager_token=manager_token,
        contributor_token=contributor_token, source_ref="local-ticket-1", approved_guide=approved_guide,
    )

    async def submit_zip(archive, key, *, using, failed=False):
        if clients is None:
            return await _json(
                client, "POST", f"/api/v1/tasks/{task_id}/submissions", contributor_token, 422 if failed else 202,
                headers=_source_headers(assignment_id, archive, key), content=archive,
            )
        return await clients.submit(contributor, contributor_token, task_id, assignment_id,
                                    key, archive, client=using, failed=failed)

    archive = archive_with_modes("evidence/results", compilation.project_id)
    bad = await submit_zip(_secret_archive(archive), str(uuid4()), using="cli", failed=True)
    _require(bad["error"]["code"] == "pre_submission_checker_failed",
             "public intake did not return checker feedback")
    default_details = bad["error"]["details"]
    default_results = [item for item in default_details["results"]
                       if item["source"] == "workstream_default"]
    _require(
        default_details["eligible_to_submit"] is False
        and [item["check_id"] for item in default_results]
        == list(WORKSTREAM_DEFAULT_CHECK_IDS)
        and [
            (item["status"], item["failure_code"], item["finding_count"])
            for item in default_results
        ] == [
            ("passed", None, 0),
            ("passed", None, 0),
            ("failed", "high_confidence_secret_detected", 1),
            ("passed", None, 0),
        ],
        "public default PRE feedback did not identify the injected private key",
    )
    external_bad = await submit_zip(_with_fixture_file(archive, "project-rejected.txt"), str(uuid4()),
                                    using="mcp", failed=True)
    results = external_bad["error"]["details"]["results"]
    external = [item for item in results
                if item["source"] == "project_external_checker"]
    _require(external_bad["error"]["code"] == "pre_submission_checker_failed"
             and len(external) == 1 and external[0]["status"] == "failed"
             and [finding["code"] for finding in external[0]["findings"]]
             == ["probe.project_rule_failed"]
             and all(item.get("failure_code") is None for item in results
                     if item["source"] == "workstream_default"),
             "public external PRE rejection did not preserve passing defaults")
    status_path = f"/api/v1/actors/me/assignments/{assignment_id}"
    rejected = await _json(client, "GET", status_path, contributor_token, 200)
    if clients is not None:
        await clients.status(contributor, contributor_token, assignment_id, rejected)
    _require(rejected["current_status"] == "in_progress"
             and rejected["assignment"]["latest_submission"] is None
             and rejected["next_action"] == "submit"
             and rejected["intake"]["pre_submission_results"] == results,
             "the exact assignment lost its rejected ZIP feedback")
    async with factory() as session:
        _require(await session.scalar(select(func.count()).select_from(Submission).where(
            Submission.task_id == task_id
        )) == 0, "failed intake created a Submission")

    async def fail_post_launch():
        from experiments.pilot04_external_checker_runtime.public_node_faults import node_command
        await node_command(fault_root, "project_fail_all")

    first_archive = (_with_fixture_file(archive, "post-rejected.txt")
                     if human_review_required else archive)
    inject_post_fault = not human_review_required and fault_root is not None
    if inject_post_fault:
        _require(stop_worker is not None and start_worker is not None, "POST fault requires owned worker controls")
        stop_worker()
    try:
        saved = await _submit(
            client, factory, task_id=task_id, assignment_id=assignment_id,
            contributor_token=contributor_token, archive=first_archive,
            submit_zip=lambda archive, key: submit_zip(archive, key, using="cli" if human_review_required else "mcp"),
            replay_zip=lambda archive, key: submit_zip(archive, key, using="mcp" if human_review_required else "cli"),
        )
        if inject_post_fault:
            await fail_post_launch()
    finally:
        if inject_post_fault:
            await start_worker()
    submission_path = f"/api/v1/tasks/{task_id}/submissions"
    history = await _json(client, "GET", submission_path, contributor_token, 200)
    _require([item["id"] for item in history["items"]] == [saved["submission_id"]],
             "public submission history differs")
    first_submission_id = saved["submission_id"]
    expected_inputs = {first_submission_id: _fixture_hashes(first_archive)}
    successor = post_retry = None
    if not human_review_required and fault_root:
        from experiments.pilot04_external_checker_runtime.public_runtime_trials import retry_post_outage
        successor, post_retry = await retry_post_outage(
            client, factory, first_submission_id, compilation.project_id, operator_token, fault_root,
        )
    first_attempt_id, completion_id = await _complete_post(
        factory, submission_id=first_submission_id,
        project_id=compilation.project_id,
        recommendation="needs_revision" if human_review_required else "allow_review",
        finding_code="probe.post_rule_failed" if human_review_required else None,
        deliver_completion=human_review_required or not exercise_faults, successor=successor,
    )
    attempt_id = first_attempt_id
    if human_review_required:
        await _assert_revision(
            factory, project_id=compilation.project_id,
            task_id=task_id, submission_id=first_submission_id,
            attempt_id=first_attempt_id,
        )
        revision = await _json(client, "GET", status_path, contributor_token, 200)
        if clients is not None:
            await clients.status(contributor, contributor_token, assignment_id, revision)
        _require(revision["current_status"] == "needs_revision"
                 and revision["next_action"] == "revise"
                 and revision["feedback_submission_id"] == first_submission_id
                 and any(finding["worker_message"] and finding["status"] == "failed"
                         for finding in revision["post_submission_results"]),
                 "the exact assignment lost its governed revision feedback")
        replacement_archive = revision_archive(archive)
        saved = await _submit(
            client, factory, task_id=task_id, assignment_id=assignment_id,
            contributor_token=contributor_token,
            archive=replacement_archive,
            submit_zip=lambda archive, key: submit_zip(archive, key, using="mcp"),
            replay_zip=lambda archive, key: submit_zip(archive, key, using="cli"),
        )
        expected_inputs[saved["submission_id"]] = _fixture_hashes(replacement_archive)
        _require(saved["submission_version"] == 2,
                 "public checker remediation did not create version 2")
        history = await _json(client, "GET", submission_path, contributor_token, 200)
        _require([item["id"] for item in history["items"]]
                 == [first_submission_id, saved["submission_id"]],
                 "public revision history lost exact predecessor order")
        attempt_id, completion_id = await _complete_post(
            factory, submission_id=saved["submission_id"],
            project_id=compilation.project_id, recommendation="allow_review",
        )
    elif exercise_faults:
        await _wait_known_retry(
            factory, completion_id, compilation.project_id,
            task_id, first_submission_id,
        )
        _require(stop_worker is not None and start_worker is not None,
                 "prefork restart control is absent")
        stop_worker()
        if attachment:
            await attachment.transition('live')
        else:
            from tests.reviews.lifecycle.transition_support import command_for, transition
            await transition(await command_for(operator_id, "live"))
        await _wait_outbox_due(factory, completion_id)
        await start_worker()
        await _wait_outbox_acknowledged(factory, completion_id,
                                       compilation.project_id)
        async with factory() as session:
            event = await session.get(OutboxEvent, completion_id)
            _require(event.delivery_state == "acknowledged"
                     and event.attempt_count == 2,
                     "known safe retry did not commit once after authorized live transition")
    outcome = await _assert_outcome(
        factory, guide_source=compilation, project_id=compilation.project_id, task_id=task_id,
        submission_id=saved["submission_id"], initial_submission_id=first_submission_id,
        contributor_id=contributor.actor_profile_id,
        human_review_required=human_review_required,
        expected_awards=len(awards),
        expected_submissions=2 if human_review_required else 1, expected_inputs=expected_inputs,
    )
    if not human_review_required:
        exported = await _json(
            client, "GET", "/api/v1/actors/me/contributions",
            contributor_token, 200,
            params={"project_id": project_id},
        )
        _require(len(exported["items"]) == 1, "public self contribution is absent")
        item = exported["items"][0]
        _require(item["submission_id"] == saved["submission_id"]
                 and item["acceptance_source"] == "task_post_submit_route"
                 and [(award["instrument"], award["unit"], Decimal(award["quantity"]))
                 for award in item["awards"]] == ([("project_points", "PTS", Decimal("7"))] if awards else []),
                 "public contribution source or award set differs")
    final_status = await _json(client, "GET", status_path, contributor_token, 200)
    if clients is not None:
        await clients.status(contributor, contributor_token, assignment_id, final_status)
    if human_review_required:
        _require(final_status["current_status"] == "review_pending" and final_status["accepted_evidence"] is None,
                 "the exact assignment changed required human-review custody")
    else:
        evidence = final_status["accepted_evidence"]
        _require(final_status["current_status"] == "accepted" and evidence
                 and evidence["submission_id"] == saved["submission_id"]
                 and evidence["artifact_hash"] == expected_inputs[saved["submission_id"]]["archive_sha256"]
                 and len(evidence["awards"]) == len(awards),
                 "the exact assignment differs from accepted artifact and award evidence")
    # Arm hosted task events before duplicate publication. The local fixture
    # has a result backend; neither path changes the production worker.
    before_delivery = await _outbox_snapshot(factory, completion_id)
    if attachment:
        duplicate_receipt = await attachment.deliver_duplicate(completion_id, project_id)
        duplicate_result = duplicate_receipt['result']
        duplicate_task_id = duplicate_receipt['task_id']
    else:
        duplicate = await asyncio.to_thread(deliver_event.apply_async,
                                          args=(str(completion_id), project_id), ignore_result=False)
        duplicate_task_id = duplicate.id
        try:
            duplicate_result = await asyncio.to_thread(
                duplicate.get, timeout=120, propagate=True,
            )
        finally:
            await asyncio.to_thread(duplicate.forget)
    _require(duplicate_result == {"status": "delivery_unavailable"},
             "prefork child did not refuse duplicate completion delivery")
    _require(await _outbox_snapshot(factory, completion_id) == before_delivery,
             "duplicate completion changed retained OUTBOX custody")
    again = await _assert_outcome(
        factory, guide_source=compilation, project_id=compilation.project_id, task_id=task_id,
        submission_id=saved["submission_id"], initial_submission_id=first_submission_id,
        contributor_id=contributor.actor_profile_id,
        human_review_required=human_review_required,
        expected_awards=len(awards),
        expected_submissions=2 if human_review_required else 1, expected_inputs=expected_inputs,
    )
    _require(again == outcome, "duplicate completion changed governed outcome")
    late_revocation = None
    if exercise_faults and not human_review_required and attachment is None:
        late_revocation = await _late_revocation_trial(
            client, factory, env, project_id=compilation.project_id,
            accepted_task_id=task_id, manager_token=manager_token,
            contributor_token=contributor_token, operator_id=operator_id,
            archive=archive,
            stop_worker=stop_worker, start_worker=start_worker,
        )
    return {
        "project_id": project_id,
        "guide_setup": compilation.evidence,
        "task_id": task_id,
        "submission_id": saved["submission_id"],
        "initial_submission_id": first_submission_id,
        "review_mode": "human" if human_review_required else "automatic",
        "intake_failure_code": bad["error"]["code"],
        "external_pre_failure_code": "probe.project_rule_failed",
        "selected_pre_runs": await _pre_runs(factory, task_id),
        "post_runtime_retry": post_retry,
        "selected_post_attempt_ids": (
            [first_attempt_id, attempt_id] if human_review_required else [attempt_id]
        ),
        "outcome": outcome,
        "submitted_inputs": expected_inputs,
        'duplicate_delivery': {
            'task_id': duplicate_task_id,
            'observation': 'scoped_worker_events' if attachment else 'result_backend',
        },
        "late_revocation": late_revocation,
    }


async def _pre_runs(factory, task_id: str) -> list[str]:
    async with factory() as session:
        return list(await session.scalars(select(SelectedPreSubmitRun.status).where(
            SelectedPreSubmitRun.task_id == task_id
        ).order_by(SelectedPreSubmitRun.queued_at)))


async def _overlap_consumer(host, queue, enabled):
    """Change only the named proof worker's consumption of its own queue."""
    from app.workers.celery_app import celery_app

    control = celery_app.control.add_consumer if enabled else celery_app.control.cancel_consumer
    replies = await asyncio.to_thread(control, queue, destination=[host], reply=True, timeout=3)
    _require(len(replies) == 1 and set(replies[0]) == {host} and "ok" in replies[0][host],
             "owned overlap worker did not confirm its queue transition")


async def _overlap_snapshot(observer, custody):
    process = await asyncio.create_subprocess_exec(
        str(observer), custody["config_sha256"], custody["service_sha256"],
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=6)
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
    _require(process.returncode == 0 and len(stdout) <= 65_536, "native overlap observer failed")
    value = json.loads(stdout)
    _require(set(value) == {"checker_pid", "config_sha256", "service_sha256", "leases", "post_grants"}
             and value["config_sha256"] == custody["config_sha256"]
             and value["service_sha256"] == custody["service_sha256"]
             and type(value["checker_pid"]) is int and value["checker_pid"] > 0,
             "native overlap observation differs from the reviewed node")
    return value


def _overlap_post(snapshot, expected_grant):
    background = [lease for lease in snapshot["leases"] if lease["pre"] is None]
    grants = snapshot["post_grants"]
    if len(background) == len(grants) == 1 and background[0]["populated"] is True and all(
        grants[0].get(key) == value for key, value in expected_grant.items()
    ):
        return background[0], grants[0]
    return None


async def _assert_overlap_parked(factory, submission_id):
    async with factory() as session:
        dispatch = await session.get(SubmissionDispatch, submission_id)
        event = await session.get(OutboxEvent, dispatch.evaluation_event_id)
        run = await session.get(CheckerRun, dispatch.evaluation_attempt_id)
        _require(event.delivery_state == "pending" and event.attempt_count == 0
                 and run.status == "queued" and run.worker_lease_generation == 0,
                 "parked POST escaped its dedicated consumer boundary")
        return str(event.event_id)


async def _run_admission_overlap(client, factory, env, root, observer, custody, hosts):
    """Observe a selected POST, independently bounded selected PRE, and exact T5."""
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from app.workers.outbox import scan_pending
    from app.workers.outbox_topology import FINALIZATION_QUEUE, OUTBOX_QUEUE

    guide, _, manager, token = await _public_project(
        client, factory, env, human_review_required=True, manager_authored=True, hold_post=True,
    )
    project = str(guide.project_id)
    tasks = [await _started_public_task(client, project_id=project, manager_token=manager,
             contributor_token=token, source_ref=f"admission-overlap-{role}")
             for role in ("post", "t5", "pre")]
    post_task, t5_task, pre_task = tasks
    archive = archive_with_modes("evidence/results", guide.project_id)
    pre_archive = _with_fixture_file(archive, "admission-overlap-pre.txt")
    _require(len({task_id for task_id, _ in tasks}) == 3, "overlap requires three distinct tasks")

    async def accept(task, payload):
        task_id, assignment_id = task
        key = str(uuid4())
        accepted = await _json(client, "POST", f"/api/v1/tasks/{task_id}/submissions", token, 202,
                               headers=_source_headers(assignment_id, payload, key), content=payload)
        _require(accepted["status"] == "accepted" and accepted["replayed"] is False
                 and accepted["task_id"] == task_id and accepted["assignment_id"] == assignment_id
                 and accepted["pre_submission_results"], "overlap received incorrect source acceptance")
        return {"acceptance_receipt": accepted, "idempotency_key": key}

    await _overlap_consumer(hosts["outbox"], OUTBOX_QUEUE, False)
    post = await _submit(client, factory, task_id=post_task[0], assignment_id=post_task[1],
                         contributor_token=token, archive=archive)
    await _assert_overlap_parked(factory, post["submission_id"])
    await _overlap_consumer(hosts["finalization"], FINALIZATION_QUEUE, False)
    t5_context = await accept(t5_task, archive)
    t5_operation_id = t5_context["acceptance_receipt"]["operation_id"]
    async with factory() as session:
        t5_operation = await session.get(SubmissionIntakeOperation, t5_operation_id)
        t5_event = await session.get(OutboxEvent, UUID(t5_operation.finalization_event_id))
        _require(t5_operation.state == "finalization_pending" and t5_operation.finalized_submission_id is None
                 and t5_event.delivery_state == "pending" and t5_event.attempt_count == 0,
                 "T5 completed before the overlap fixture released it")
        t5_event_id = str(t5_event.event_id)

    initial = await _overlap_snapshot(observer, custody)
    _require(initial["leases"] == initial["post_grants"] == [], "overlap node did not start idle")
    # Let the dedicated scanner stage any remaining publications while both owners
    # are parked. A prior Beat scan may already have staged either exact event.
    scan = await asyncio.to_thread(scan_pending.apply_async, ignore_result=False)
    try:
        scanned = await asyncio.to_thread(scan.get, timeout=30, propagate=True)
        _require(type(scanned) is dict and set(scanned) == {"selected", "published"}
                 and type(scanned["selected"]) is int and type(scanned["published"]) is int
                 and 0 <= scanned["published"] <= scanned["selected"],
                 "owned scanner did not return a valid terminal result")
    finally:
        await asyncio.to_thread(scan.forget)
    (root / "source.sha256").write_text(_fixture_hashes(pre_archive)["archive_sha256"] + "\n")
    pre = asyncio.create_task(accept(pre_task, pre_archive))
    try:
        async with asyncio.timeout(30):
            while not (root / "pre-dispatch.json").is_file():
                _require(not pre.done(), "PRE exited before the native dispatch barrier")
                await asyncio.sleep(0.05)
        expected_pre = json.loads((root / "pre-dispatch.json").read_text())
        _require(len({post["operation_id"], t5_operation_id, expected_pre["source_operation_id"]}) == 3,
                 "overlap reused a source operation")
        await _overlap_consumer(hosts["outbox"], OUTBOX_QUEUE, True)

        expected_post = {"project_id": project, "task_id": post_task[0], "submission_id": post["submission_id"],
                         "evaluation_request_id": post["evaluation_request_id"]}
        async with asyncio.timeout(60):
            while (held := _overlap_post(await _overlap_snapshot(observer, custody), expected_post)) is None:
                _require(not pre.done(), "PRE exhausted its original lease before POST held capacity")
                await asyncio.sleep(0.15)
        post_lease, post_grant = held
        async with factory() as session:
            run = await session.get(CheckerRun, post_grant["attempt_id"])
            _require(run is not None and run.status == "running" and run.worker_lease_id == post_grant["lease_id"]
                     and run.worker_lease_generation == 1, "native POST is not the retained selected attempt")
        await _overlap_consumer(hosts["outbox"], OUTBOX_QUEUE, False)
        released = time.monotonic()
        (root / "release-pre").touch(exist_ok=False)

        async def require_held_post():
            snapshot = await _overlap_snapshot(observer, custody)
            _require(snapshot["checker_pid"] == initial["checker_pid"]
                     and _overlap_post(snapshot, expected_post) == held,
                     "selected POST released Background capacity before the overlap was proved")
            return snapshot

        async with asyncio.timeout(20):
            while True:
                overlap = await require_held_post()
                admitted = [lease for lease in overlap["leases"] if lease["pre"] == expected_pre]
                if admitted:
                    break
                await asyncio.sleep(0.15)
            pre_lease, = admitted
            _require(pre_lease["name"] != post_lease["name"] and pre_lease["epoch"] == post_lease["epoch"],
                     "PRE did not reserve independently on the same admission epoch")
            await _overlap_consumer(hosts["finalization"], FINALIZATION_QUEUE, True)
            t5 = await _await_finalized_source(client, factory, *t5_task, token, t5_context, archive)
            async with factory() as session:
                t5_event = await session.get(OutboxEvent, UUID(t5_event_id))
                _require(t5_event.delivery_state == "acknowledged" and t5_event.attempt_count == 1,
                         "overlap T5 did not acknowledge the original delivery once")
            proved = await require_held_post()
            _require(any(lease["name"] == pre_lease["name"] and lease["pre"] == expected_pre
                         and lease["epoch"] == pre_lease["epoch"]
                         and lease["journal_sha256"] == pre_lease["journal_sha256"] for lease in proved["leases"]),
                     "selected PRE released its reservation before T5 acknowledged")
        t5_post_event = await _assert_overlap_parked(factory, t5["submission_id"])
        pre_context = await pre
        elapsed = time.monotonic() - released
        pre_acceptance = pre_context["acceptance_receipt"]
        _require(pre_acceptance["operation_id"] == expected_pre["source_operation_id"],
                 "accepted PRE operation differs from the admitted native lease")
        selected = await _await_finalized_source(client, factory, *pre_task, token, pre_context, pre_archive)
        async with factory() as session:
            pre_run = await session.get(SelectedPreSubmitRun, expected_pre["run_id"])
            receipt = pre_run.terminal_json["invocation_receipt"]
            _require(receipt["provider_invocation_id"] == pre_lease["name"]
                     and receipt["cleanup"]["journal_sha256"] == pre_lease["journal_sha256"]
                     and receipt["cleanup"]["disposition"] == "destroyed"
                     and receipt["timings_ms"]["total"] <= 120_000,
                     "completed PRE did not retain exact bounded native reservation evidence")
        await _assert_overlap_parked(factory, selected["submission_id"])
        await _assert_overlap_parked(factory, t5["submission_id"])
        post_attempt, completion = await _complete_post(
            factory, submission_id=post["submission_id"], project_id=guide.project_id,
            recommendation="allow_review", deliver_completion=False,
        )
        _require(post_attempt == post_grant["attempt_id"], "completed POST differs from the held run")
        return {"fixture_post_mode": "deadline", "post_lease": post_lease, "post_grant": post_grant,
                "pre_lease": pre_lease, "pre_seconds_after_release": round(elapsed, 3),
                "pre_runtime_ms": receipt["timings_ms"]["total"],
                "pre": selected, "t5_operation_id": t5_operation_id, "t5_event_id": t5_event_id,
                "t5": t5, "t5_post_parked_event_id": t5_post_event, "post_completion_event_id": str(completion),
                "checker_pid": initial["checker_pid"]}
    finally:
        if not pre.done():
            pre.cancel()
        await asyncio.gather(pre, return_exceptions=True)


def _read_runner_configuration(node_config: Path, root: Path, custody: dict, *, separate_runner: bool) -> dict:
    """Bind a copied baseline config or the exact locally supervised wrapper."""
    _require(custody['source_tree'] == subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=BACKEND, text=True).strip(), 'custody source differs')
    raw = node_config.read_bytes()
    service_config = json.loads(raw)
    _require(isinstance(service_config.get('pre'), dict)
             and isinstance(service_config['pre'].get('reserved_capacity'), dict),
             'public proof requires an explicit PRE reservation')
    if separate_runner:
        _require(service_config == custody['node_config']
                 and 'sha256:' + hashlib.sha256(raw).hexdigest() == custody['config_sha256']
                 and service_config['smol']['binary_sha256'] == custody['smol_sha256'],
                 'separate runner configuration differs from reviewed custody')
        return service_config
    from experiments.pilot04_external_checker_runtime.public_node_faults import validate_fault_capacity
    validate_fault_capacity(service_config)
    original_config = json.loads(json.dumps(service_config))
    wrapper = root / 'node-control/runtime-wrapper'
    _require(service_config['smol']['binary'] == str(wrapper)
             and service_config['smol']['binary_sha256'] == custody['wrapper_sha256']
             and 'sha256:' + hashlib.sha256(wrapper.read_bytes()).hexdigest() == custody['wrapper_sha256'],
             'fault wrapper differs from independently supplied source custody')
    original_config['smol']['binary'] = custody['node_config']['smol']['binary']
    original_config['smol']['binary_sha256'] = custody['node_config']['smol']['binary_sha256']
    _require(original_config == custody['node_config'], 'node configuration differs from expected custody')
    _require(json.loads((root / 'node-control/node-binding.json').read_text()) == custody,
             'host binary/config validation receipt differs from expected custody')
    return service_config


def _require_runner_health(execution: ExternalCheckerServiceHealth, intake: TrustedIntakeIdentity,
                           expected_cache_count: int) -> None:
    """Compare authenticated readiness with the independently verified runner configuration."""
    _require((execution.runtime, execution.isolation_mode)
             == (intake.runtime, intake.isolation_mode)
             == ("smolvm", "smol-microvm"), "typed capability health identities disagree")
    # Health reports a count. The reviewed configuration binds the exact project manifest.
    _require(execution.cached_platform_manifests == expected_cache_count,
             "live execution cache count differs from reviewed runner configuration")


async def run(database_url: str, image_reference: str, node_config: Path,
              broker_url: str, root: Path, expected_custody: Path,
              clients: ContributorClients | None = None, *, separate_runner: bool = False,
              policy_case: str = "both", overlap_observer: Path | None = None) -> dict:
    _require(policy_case in {"both", "human", "automatic"}, "unknown policy qualification case")
    _require(policy_case == "both" or separate_runner, "single policy case requires separate runner")
    _require(overlap_observer is None or (separate_runner and policy_case == "both"),
             "native admission overlap requires its own separate-runner proof")
    if overlap_observer is not None:
        overlap_observer = overlap_observer.resolve(strict=True)
        _require(overlap_observer.is_file() and os.access(overlap_observer, os.X_OK),
                 "native admission observer must be executable")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    _require(not separate_runner or clients is not None, 'separate runner proof needs both clients')
    custody = json.loads(expected_custody.read_text())
    service_config = _read_runner_configuration(node_config, root, custody, separate_runner=separate_runner)
    if overlap_observer is not None:
        _require(service_config["smol"]["maximum_parallel"] == 2
                 and service_config["pre"]["reserved_capacity"]["slots"] == 1,
                 "native overlap requires exactly one PRE and one Background slot")
    _require((service_config["runtime"], service_config["isolation_mode"])
             == ("smolvm", "smol-microvm"), "public drill requires the provisioned Smol node")
    repository, digest = image_reference.rsplit("@", 1)
    images = [entry for entry in service_config["cache"]
              if entry["repository"] == repository and entry["platform_manifest_digest"] == digest]
    _require(len(images) == 1, "project image is absent or ambiguous in node cache")
    image = images[0]
    bucket = os.environ["WORKSTREAM_TEST_MINIO_BUCKET"]
    prefix = os.environ["WORKSTREAM_TEST_MINIO_PREFIX"]
    scratch = root / "artifact-scratch" if separate_runner else Path(service_config["material_root"])
    intake_images = [entry for entry in service_config["cache"]
                     if entry["platform_manifest_digest"]
                     == service_config["trusted_intake"]["platform_manifest_digest"]]
    _require(len(intake_images) == 1, "trusted intake image is absent or ambiguous")
    intake_image = intake_images[0]
    settings = minio_settings(private_prefix=prefix).model_copy(update={
        "artifact_s3_bucket": bucket,
        "artifact_scratch_root": scratch,
        "artifact_scratch_minimum_free_bytes": 0,
        "artifact_intake_image_digest": intake_image["platform_manifest_digest"],
        "artifact_intake_config_digest": intake_image["config_image_id"],
    })
    bootstrap = create_artifact_store_bootstrap(settings)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    bootstrap.close()
    os.environ["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env = api_environment()
    env.update({
        "WORKSTREAM_DATABASE_URL": database_url,
        "WORKSTREAM_E2E_FLOW_ISSUER": "https://identity.flowresearch.tech",
        "WORKSTREAM_FLOW_AUTH_ISSUER": "https://identity.flowresearch.tech",
        "WORKSTREAM_CELERY_BROKER_URL": broker_url,
        "WORKSTREAM_CELERY_RESULT_BACKEND_URL": broker_url,
        "WORKSTREAM_CELERY_TASK_ALWAYS_EAGER": "false",
        "WORKSTREAM_SUBMISSION_FEEDBACK_EMAIL_ENABLED": "false",
        "WORKSTREAM_ARTIFACT_PENDING_WORK_SCAN_INTERVAL_SECONDS": "10",
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(scratch),
        "WORKSTREAM_ARTIFACT_SCRATCH_MINIMUM_FREE_BYTES": "0",
        "WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST": intake_image["platform_manifest_digest"],
        "WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST": intake_image["config_image_id"],
        "PYTHONPATH": os.pathsep.join(map(str, (BACKEND, BACKEND / "tests", BACKEND.parent))),
    })
    recorded_assistance = not separate_runner
    if recorded_assistance:
        configure_scripted_model_session_environment(env)
    env.pop("OPENAI_API_KEY", None)
    # Native workload checks use qualified fixture actors, without email effects.
    env.pop("WORKSTREAM_RESEND_API_KEY_FILE", None)
    os.environ.pop("WORKSTREAM_RESEND_API_KEY_FILE", None)
    if clients is not None:
        env = clients.setup_authority(env)
        os.environ.pop("WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET", None)
        os.environ.pop("WORKSTREAM_E2E_FLOW_SECRET", None)
    # Infrastructure prerequisites and broker publication use the same
    # isolated database and provider settings as the API and worker children.
    for key, value in env.items():
        if key.startswith("WORKSTREAM_"):
            os.environ[key] = value
    os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()
    runtime_settings = get_settings()
    _require(runtime_settings.database_url == database_url,
             "API/worker database differs from isolated fixture")
    if clients is None:
        issuer, audience, flow_secret = flow_settings(env)
        _require(runtime_settings.flow_auth_issuer == issuer
                 and runtime_settings.flow_auth_audience == audience
                 and runtime_settings.flow_auth_local_hmac_secret == flow_secret,
                 "API Flow verifier differs from local test signer")
    else:
        _require(runtime_settings.token_issuer == clients.identity.issuer
                 and runtime_settings.token_audience == "workstream-api"
                 and runtime_settings.token_algorithms == "RS256"
                 and runtime_settings.flow_auth_local_hmac_secret is None,
                 "API Flow verifier differs from the connected issuer fixture")
    _require(runtime_settings.api_rate_limit_key_secret is not None
             and runtime_settings.pagination_cursor_hmac_secret is not None,
             "API rate/cursor signing configuration is absent")
    _require(runtime_settings.celery_broker_url == broker_url
             and runtime_settings.celery_task_always_eager is False,
             "worker broker configuration is not durable")
    _require(runtime_settings.artifact_pending_work_scan_interval_seconds == 10,
             "Beat artifact scan interval differs from isolated drill")
    _require(runtime_settings.artifact_scratch_root == scratch
             and runtime_settings.artifact_scratch_minimum_free_bytes == 0,
             "API/worker scratch configuration differs from fixture")
    _require(runtime_settings.external_runner_host is not None
             and runtime_settings.submission_execution_profile is not None,
             "supply explicit remote TLS runner and source execution profile before qualification")
    source_profile = _require_source_runtime_window(runtime_settings)
    _require(runtime_settings.submission_source_cleanup_profile is not None,
             "supply explicit source cleanup profile for the dedicated worker")
    cleanup_env = _source_cleanup_environment(env, runtime_settings)
    env.pop("WORKSTREAM_CLI_JOURNEY_CLEANUP_ACCESS_KEY_ID", None)
    env.pop("WORKSTREAM_CLI_JOURNEY_CLEANUP_SECRET_FILE", None)
    _require_parser_socket(runtime_settings)
    for field in (
        "artifact_store_backend", "artifact_s3_provider_profile", "artifact_s3_region",
        "artifact_s3_endpoint_url", "artifact_s3_bucket", "artifact_s3_private_prefix",
        "artifact_s3_addressing_style", "artifact_s3_credential_mode",
        "artifact_s3_access_key_id", "artifact_s3_secret_access_key", "artifact_s3_session_token",
    ):
        _require(getattr(runtime_settings, field) == getattr(settings, field),
                 "API/worker artifact provider configuration differs from fixture")
    runtime_bootstrap = create_artifact_store_bootstrap(runtime_settings)
    try:
        runtime_namespace = artifact_storage_namespace_spec(
            runtime_settings, runtime_bootstrap
        )
    finally:
        runtime_bootstrap.close()
    _require(runtime_namespace.namespace_fingerprint == namespace.namespace_fingerprint,
             "API/worker artifact namespace differs from approved fixture")
    parent_celery_mismatches = _celery_config_mismatches(runtime_settings)
    _require(not parent_celery_mismatches,
             "parent broker configuration differs from resolved Settings: "
             + ", ".join(parent_celery_mismatches))
    await asyncio.to_thread(prepare_versioned_source_bucket, env, lane="guide_journey")
    _preflight_children(runtime_settings, env, cleanup_env, root, recorded_assistance=recorded_assistance)

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    api = worker = beat = mcp = None
    workers: list[subprocess.Popen] = []
    worker_hosts = {}
    processes: list[subprocess.Popen] = []
    signals = ExitStack()
    worker_generation = 0

    def stop_owned_worker() -> None:
        _require(worker is not None and worker.poll() is None,
                 "POST effect worker was not running before restart")
        _stop_process(worker)
        _require(worker.poll() is not None, "old POST effect worker did not exit")
        workers.remove(worker)
        processes.remove(worker)

    async def start_owned_worker() -> None:
        nonlocal worker, worker_generation
        _require(worker is None or worker.poll() is not None,
                 "POST effect worker was not stopped before restart")
        previous_pid = worker.pid if worker is not None else None
        worker_generation += 1
        worker, hostname = _start_worker(env, root, "outbox", "workstream.outbox",
                                         worker_generation, launch=launch)
        workers.append(worker)
        _require(worker.pid != previous_pid, "restart reused the old POST worker process")
        await _wait_worker(worker, hostname)

    try:
        launch = signals.enter_context(_owned_process_interrupts(processes))
        await provision_material_services(factory, artifacts=True, checker=True)
        await provision_router(factory)
        await provision_reconciler(factory)
        await _provision_runtime_services(factory)
        for phase in ("pre_submit", "post_submit"):
            await _register_external_checker_fixture(factory, _locked_spec(
                phase, image, hold_post=overlap_observer is not None,
            ))
        operator, _ = await seed_review_actor(factory, None, role="operator", scope="system", issuer=seeded_issuer(env))
        from tests.reviews.lifecycle.transition_support import command_for, transition
        await transition(await command_for(operator.actor_profile_id, "shadow"))
        if separate_runner:
            await transition(await command_for(operator.actor_profile_id, "live"))

        intake_health = await trusted_submission_intake(runtime_settings).health()
        execution_health = await configured_external_checker_execution(runtime_settings).health()
        _require_runner_health(execution_health, intake_health, len(service_config["cache"]))
        port = find_free_port()
        origin = f"http://127.0.0.1:{port}"
        api_module, api_env = "app.main:app", env
        if overlap_observer is not None:
            overlap_root = root / "admission-overlap"
            overlap_root.mkdir(mode=0o700)
            api_module = "experiments.pilot04_external_checker_runtime.public_intake_observer:app"
            api_env = env | {"WORKSTREAM_PROBE_INTAKE_TRACE": str(overlap_root / "adapter.jsonl"),
                             "WORKSTREAM_PROBE_PRE_BARRIER": str(overlap_root)}
        api = launch([
            sys.executable, "-m", "uvicorn",
            api_module,
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "error", "--no-access-log",
        ], env=api_env, log=root / "api.log")
        await _wait_api(origin, api)
        if clients is not None:
            clients.configure_processes(origin, find_free_port())
            mcp = launch([str(clients.mcp_executable)], env=clients.mcp_env, log=root / "mcp.log")
            await clients.wait_ready(mcp)
        starting_workers = []
        for role, queue in WORKER_ROLES:
            process, hostname = _start_worker(
                cleanup_env if role == "source-cleanup" else env, root, role, queue, launch=launch,
                recorded_assistance=recorded_assistance,
            )
            workers.append(process)
            starting_workers.append((process, hostname))
            worker_hosts[role] = hostname
            if role == "outbox":
                worker = process
                worker_generation = 1
        for process, hostname in starting_workers:
            await _wait_worker(process, hostname)
        scans_before_beat = await _scan_audit_count(factory)
        beat = launch([
            sys.executable, "-m", "celery", "-A", "app.workers.celery_app",
            "beat", "--loglevel=ERROR",
            "--schedule", str(root / "beat-schedule"),
        ], env=env, log=root / "beat.log")
        await _wait_beat_scan(factory, beat, scans_before_beat)
        async with httpx.AsyncClient(base_url=origin, timeout=(source_profile.upload_total_seconds
                + runtime_settings.external_checker_service_timeout_seconds), trust_env=False) as client:
            fault_root = None if separate_runner else root / "node-control"
            intake_trials = runtime_trials = None
            if fault_root is not None:
                from experiments.pilot04_external_checker_runtime.public_intake_trials import public_intake_trials
                from experiments.pilot04_external_checker_runtime.public_runtime_trials import public_runtime_trials
                intake_trials = await public_intake_trials(
                    client, factory, env, fault_root, stop_worker=stop_owned_worker, start_worker=start_owned_worker)
                _require((fault_root / "supervisor-ready").exists(), "owned node supervisor is absent")
                runtime_trials = await public_runtime_trials(client, factory, env, fault_root,
                    stop_worker=stop_owned_worker, start_worker=start_owned_worker, operator_token=_token(env, operator))
            true = false = admission_overlap = None
            if overlap_observer is not None:
                admission_overlap = await _run_admission_overlap(
                    client, factory, env, overlap_root, overlap_observer, custody, worker_hosts,
                )
            if overlap_observer is None and policy_case in {"both", "human"}:
                true = await _one_mode(client, factory, env,
                                   human_review_required=True,
                                   operator_id=operator.actor_profile_id, clients=clients,
                                   exercise_faults=not separate_runner, manager_authored=separate_runner)
                if separate_runner:
                    _write_policy_receipt(root, "human", true, custody, bucket=bucket, prefix=prefix)
            if overlap_observer is None and policy_case in {"both", "automatic"}:
                false = await _one_mode(client, factory, env,
                                    human_review_required=False,
                                    operator_id=operator.actor_profile_id,
                                    stop_worker=stop_owned_worker,
                                    start_worker=start_owned_worker, fault_root=fault_root,
                                    operator_token=_token(env, operator), clients=clients,
                                    exercise_faults=not separate_runner, manager_authored=separate_runner)
                if separate_runner:
                    _write_policy_receipt(root, "automatic", false, custody, bucket=bucket, prefix=prefix)
        _require(api.poll() is None and beat.poll() is None
                 and all(process.poll() is None for process in workers),
                 "API, dedicated prefork worker, or Beat exited during public journey")
        _require(mcp is None or mcp.poll() is None, "installed MCP exited during public journey")
        return {"tree_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=BACKEND
        ).strip(), "runtime": "smolvm/smol-microvm", "image_digest": image["platform_manifest_digest"],
                "trusted_intake_image_digest": intake_health.image_digest,
                "trusted_intake_config_digest": intake_health.config_digest,
                "public_api": True, "prefork_worker": True, "prefork_finalization_worker": True,
                "dedicated_worker_queues": [queue for _, queue in WORKER_ROLES],
                "maximum_parallel": service_config["smol"]["maximum_parallel"],
                "pre_reserved_capacity": service_config["pre"]["reserved_capacity"],
                "separate_runner": separate_runner,
                "completed_policy_cases": [name for name, outcome in (("human", true), ("automatic", false))
                                           if outcome is not None],
                "scheduled_artifact_scans": True,
                "public_original_guide_setup": True,
                "connected_submitter_clients": ["cli", "mcp"] if clients is not None and overlap_observer is None else [],
                "recorded_inference": recorded_assistance,
                "custody": {key: custody[key] for key in (
                    'source_tree', 'config_sha256', 'service_sha256', 'smol_sha256', 'guest_sha256',
                ) + (() if separate_runner else ('wrapper_sha256',))},
                "runtime_trials": runtime_trials, "intake_trials": intake_trials,
                "human": true, "automatic": false} | (
                    {"admission_overlap": admission_overlap} if overlap_observer is not None else {}
                )
    finally:
        try:
            _stop_owned_processes(tuple(reversed(processes)))
        finally:
            try:
                for schedule_file in root.glob("beat-schedule*"):
                    schedule_file.unlink()
            finally:
                signals.close()
                await engine.dispose()


def _write_policy_receipt(
    root: Path, case: str, result: dict, custody: dict, *, bucket: str, prefix: str,
) -> None:
    """Retain a completed case without claiming the other case or overall cleanup."""
    selected = {key: custody[key] for key in (
        "source_tree", "config_sha256", "service_sha256", "smol_sha256", "guest_sha256",
    )}
    with (root / f"policy-{case}.json").open("x", encoding="utf-8") as stream:
        json.dump({"completed_policy_case": case, "custody": selected, "result": result,
                   "separate_runner": True, "connected_submitter_clients": ["cli", "mcp"],
                   "minio_bucket": bucket, "minio_prefix": prefix,
                   "overall_cleanup_requires_separate_receipt": True,
                   "terminal_probe_exit_requires_separate_receipt": True}, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("WORKSTREAM_TEST_DATABASE_URL"))
    parser.add_argument("--image-reference")
    parser.add_argument("--node-config", type=Path, help="Owned provisioned Smol node configuration")
    parser.add_argument("--broker-url")
    parser.add_argument("--expected-custody", type=Path)
    parser.add_argument("--work-dir", type=Path,
                        help="Unique private directory retaining API and worker diagnostics")
    parser.add_argument("--cli-executable", type=Path, help="Built CLI for connected submitter verification")
    parser.add_argument("--mcp-executable", type=Path, help="Installed MCP for connected submitter verification")
    parser.add_argument("--separate-runner", action="store_true",
                        help="Use baseline remote runner custody without local host fault controls")
    parser.add_argument("--policy-case", choices=("both", "human", "automatic"), default="both",
                        help="Qualify one independent policy case on the separate runner, or both")
    parser.add_argument("--admission-overlap-observer", type=Path,
                        help="Run only the separate-runner overlap proof with this read-only native observer")
    parser.add_argument('--hosted-attachment', type=Path,
                        help='Private attachment manifest for an existing hosted API/worker/Beat')
    parser.add_argument('--hosted-model-post', type=Path,
                        help='Private model qualification input; requires hosted attachment and completed actor bootstrap')
    args = parser.parse_args()
    if not args.database_url:
        parser.error("isolated --database-url or WORKSTREAM_TEST_DATABASE_URL is required")
    if args.hosted_model_post and not args.hosted_attachment:
        parser.error('model POST qualification requires explicit hosted attachment')
    if bool(args.cli_executable) != bool(args.mcp_executable):
        parser.error("connected submitter verification requires both client executables")
    if args.separate_runner and not args.cli_executable:
        parser.error("the separate runner proof requires both client executables")
    if args.policy_case != "both" and not args.separate_runner:
        parser.error("a single policy case requires --separate-runner")
    if args.admission_overlap_observer and (not args.separate_runner or args.policy_case != "both"):
        parser.error("admission overlap requires --separate-runner and chooses its own proof")
    if args.hosted_attachment:
        if (not args.broker_url or args.image_reference or args.node_config
                or args.work_dir or args.expected_custody or args.cli_executable or args.mcp_executable
                or args.separate_runner):
            parser.error('hosted attachment requires broker URL and excludes local launch arguments')
        from experiments.pilot04_external_checker_runtime.public_hosted_attachment import HostedAttachment, run as attach
        attachment = HostedAttachment.read(args.hosted_attachment)
        value = asyncio.run(attach(attachment, args.database_url, args.broker_url, args.hosted_model_post)
                            if args.hosted_model_post else attach(attachment, args.database_url, args.broker_url))
        print(json.dumps(value, sort_keys=True, separators=(',', ':')))
        return 0
    if not args.image_reference or not args.node_config or not args.broker_url or not args.expected_custody:
        parser.error("full drill requires image, node config, and broker URL")
    workspace = (nullcontext(args.work_dir) if args.work_dir else
                 tempfile.TemporaryDirectory(prefix="ws-pilot04-public-"))
    with workspace as directory, ExitStack() as cleanup:
        clients = None
        if args.cli_executable:
            clients = ContributorClients(args.cli_executable, args.mcp_executable, Path(directory) / "submitter-clients")
            cleanup.callback(clients.identity.close)
        value = asyncio.run(run(
            args.database_url, args.image_reference, args.node_config,
            args.broker_url, Path(directory), args.expected_custody, clients, separate_runner=args.separate_runner,
            policy_case=args.policy_case, overlap_observer=args.admission_overlap_observer,
        ))
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
