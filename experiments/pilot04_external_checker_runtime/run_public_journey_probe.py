"""Exercise public original-guide setup through a governed contribution outcome.

Run only with isolated PostgreSQL/MinIO and an owned disposable Redis broker.
Inference is explicitly recorded; real Celery executes the canonical setup owners.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from decimal import Decimal
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
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
    ArtifactPutAttempt, ArtifactVerificationJob, SubmissionBundleAdmission,
)
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.checkers.execution_repository import stored_result
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_CHECK_IDS
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.artifacts.service import artifact_storage_namespace_spec
from app.modules.tasks.models import Submission, SubmissionDispatch, WorkstreamTask
from app.adapters.artifacts import trusted_submission_intake
from app.adapters.checkers import configured_external_checker_execution
from experiments.pilot04_external_checker_runtime.run_selected_end_to_end_probe import (
    _locked_spec,
    _secret_archive,
)
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
    api_environment, find_free_port, flow_settings,
)


from experiments.pilot04_external_checker_runtime.public_probe_support import (  # noqa: E402
    _assert_outbox_worker_custody, _assert_task_has_no_effects, _json, _public_project,
    _require, _started_public_task, _token, _wait_outbox_acknowledged,
    _with_fixture_file, _GOVERNED_TABLES, _fixture_hashes, _assert_input_hashes,
)


def _settings_digests(settings, nonce: bytes) -> dict[str, str]:
    """Compare every resolved setting across processes without exposing values."""
    values = settings.model_dump(mode="json")
    for name in (
        "api_rate_limit_key_secret", "pagination_cursor_hmac_secret",
        "artifact_s3_access_key_id", "artifact_s3_secret_access_key",
        "artifact_s3_session_token",
    ):
        secret = getattr(settings, name)
        values[name] = None if secret is None else secret.get_secret_value()
    return {
        name: hmac.new(
            nonce, json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        for name, value in values.items()
    }


def _celery_config_mismatches(settings) -> list[str]:
    from app.workers.celery_app import celery_app

    expected = {
        "celery_broker_url": settings.celery_broker_url,
        "celery_result_backend_url": settings.celery_result_backend_url,
        "celery_task_always_eager": settings.celery_task_always_eager,
    }
    actual = {
        "celery_broker_url": celery_app.conf.broker_url,
        "celery_result_backend_url": celery_app.conf.result_backend,
        "celery_task_always_eager": celery_app.conf.task_always_eager,
    }
    return [name for name in expected if expected[name] != actual[name]]


def _verify_child_configuration(role: str) -> int:
    """Import the same API or worker entry point and report only mismatched keys."""
    request = json.load(sys.stdin)
    nonce = bytes.fromhex(request["nonce"])
    if role == "api":
        from app.main import app

        actual = app.state.settings
    else:
        from app.workers.celery_app import celery_app  # noqa: F401

        actual = get_settings()
    observed = _settings_digests(actual, nonce)
    expected = request["expected"]
    mismatches = sorted(
        name for name in expected.keys() | observed.keys()
        if expected.get(name) != observed.get(name)
    )
    if role == "worker":
        mismatches.extend(_celery_config_mismatches(actual))
    print(json.dumps(sorted(set(mismatches)), separators=(",", ":")))
    return 0


def _preflight_children(settings, env: dict[str, str], root: Path) -> None:
    """Reject API/worker drift before starting real services or public requests."""
    nonce = os.urandom(32)
    request = json.dumps({
        "nonce": nonce.hex(), "expected": _settings_digests(settings, nonce),
    })
    for role in ("api", "worker"):
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
                cwd=BACKEND, env=env, input=request, text=True,
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


def _start_worker(env: dict[str, str], root: Path, generation: int) -> tuple[subprocess.Popen, str]:
    """Start one owned prefork worker with a distinct broker identity and log."""
    hostname = f"first-journey-{uuid4().hex}@localhost"
    process = _process([
        sys.executable, "-m", "celery", "-A",
        "experiments.pilot04_external_checker_runtime.guide_worker",
        "worker", "--pool=prefork", "--concurrency=1",
        "--queues=celery,workstream.outbox", "--hostname", hostname,
        "--without-gossip", "--without-mingle", "--without-heartbeat",
        "--loglevel=ERROR",
    ], env=env, log=root / ("worker.log" if generation == 1 else f"worker-{generation}.log"))
    return process, hostname


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


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


async def _artifact_task_state(factory, task_id: str) -> tuple[list[tuple], list[tuple]]:
    """Read only this task's put and verification disposition, never artifact data."""
    async with factory() as session:
        puts = (await session.execute(
            select(ArtifactPutAttempt.status, ArtifactPutAttempt.terminal_result_code)
            .where(ArtifactPutAttempt.task_id == task_id,
                   ArtifactPutAttempt.producer_request_type == "submission_bundle")
        )).all()
        jobs = (await session.execute(
            select(ArtifactVerificationJob.id, ArtifactVerificationJob.status,
                   ArtifactVerificationJob.terminal_result_code)
            .join(ArtifactPutAttempt,
                  ArtifactVerificationJob.originating_put_attempt_id == ArtifactPutAttempt.id)
            .where(ArtifactPutAttempt.task_id == task_id,
                   ArtifactPutAttempt.producer_request_type == "submission_bundle")
        )).all()
        return list(puts), list(jobs)


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


async def _ready_admission(client, factory, task_id: str, assignment_id: str,
                           contributor_token: str, archive: bytes, summary: str,
                           attestation: str, predecessor_id: str | None = None) -> str:
    from app.workers.artifacts import verify_object

    expected_input = _fixture_hashes(archive)
    key = str(uuid4())
    headers = {
        "Content-Type": "application/zip",
        "X-Task-Assignment-Id": assignment_id,
        "Idempotency-Key": key,
        "X-Submission-Summary": summary,
        "X-Contributor-Attestation": attestation,
    }
    if predecessor_id is not None:
        headers["X-Predecessor-Submission-Id"] = predecessor_id
        detail = await _json(client, "GET", f"/api/v1/tasks/{task_id}/work-context", contributor_token, 200)
        revision = detail["revision_context"]
        headers["X-Revision-Preparation-Id"] = revision["preparation_id"]
        headers["X-Revision-Preparation-Sha256"] = revision["preparation_sha256"]
    route = f"/api/v1/tasks/{task_id}/submission-bundle-preparations"
    deadline = time.monotonic() + 180
    current_status = None
    status_since = time.monotonic()
    scans_before = await _scan_audit_count(factory)
    while time.monotonic() < deadline:
        result = await _json(
            client, "POST", route, contributor_token, 202,
            headers=headers, content=archive,
        )
        status = result["submission_bundle_preparation_status"]
        _require(
            bool(result["pre_submission_results"]),
            "admitted intake omitted its feedback",
        )
        if status == "ready":
            _require(result["admission_id"] is not None, "ready intake omitted admission")
            if await _scan_audit_count(factory) > scans_before:
                async with factory() as session:
                    admission = await session.get(SubmissionBundleAdmission, result["admission_id"])
                    _assert_input_hashes(admission, expected_input)
                    selected = await session.get(SelectedPreSubmitRun, admission.selected_pre_submit_run_id)
                    _assert_input_hashes(selected, expected_input)
                return result["admission_id"]
            await asyncio.sleep(1)
            continue
        _require(result["admission_id"] is None, "unverified admission was public")
        _require(status not in {
            "conflict", "integrity_mismatch", "missing", "absent_replay_required", "stale",
        }, f"artifact preparation ended {status}")
        if status != current_status:
            current_status = status
            status_since = time.monotonic()
        now = time.monotonic()
        if now - status_since >= 60:
            puts, jobs = await _artifact_task_state(factory, task_id)
            pending = [identifier for identifier, state, _ in jobs if state == "pending"]
            if status == "object_confirmed" and len(pending) == 1:
                verification = await asyncio.to_thread(
                    verify_object.apply_async, args=(pending[0],),
                    ignore_result=False,
                )
                try:
                    await asyncio.to_thread(
                        verification.get, timeout=90, propagate=True,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        "artifact verifier task failed: "
                        f"{type(exc).__name__}/{type(exc.__cause__).__name__}; "
                        f"put_states={puts}; "
                        f"job_states={[(state, code) for _, state, code in jobs]}"
                    ) from None
                finally:
                    await asyncio.to_thread(verification.forget)
                puts, jobs = await _artifact_task_state(factory, task_id)
            raise RuntimeError(
                f"artifact preparation remained {status} after bounded worker scans; "
                f"put_states={puts}; "
                f"job_states={[(state, code) for _, state, code in jobs]}"
            )
        await asyncio.sleep(1)
    raise RuntimeError(f"artifact verification did not become ready from {current_status}")


async def _submit(client, factory, *, task_id: str, assignment_id: str,
                  contributor_token: str, archive: bytes, summary: str,
                  attestation: str, predecessor_id: str | None, before_create=None) -> dict:
    admission_id = await _ready_admission(
        client, factory, task_id, assignment_id, contributor_token,
        archive, summary, attestation, predecessor_id,
    )
    if before_create is not None:
        await before_create()
    route = f"/api/v1/tasks/{task_id}/submissions"
    packet = {
        "assignment_id": assignment_id,
        "admission_id": admission_id,
        "predecessor_submission_id": predecessor_id,
        "summary": summary,
        "contributor_attestation": attestation,
    }
    saved = await _json(client, "POST", route, contributor_token, 201, json=packet)
    repeated = await _json(client, "POST", route, contributor_token, 201, json=packet)
    _require(saved == repeated, "public Submission replay changed receipt")
    _require(saved["admission_id"] == admission_id,
             "Submission consumed another admission")
    return saved


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
                                 archive: bytes, summary: str, attestation: str,
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
        summary=summary, attestation=attestation, predecessor_id=None,
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
        factory, None, role="access_administrator", scope="system"
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
                    start_worker: Callable[[], Awaitable[None]] | None = None, fault_root=None, operator_token=None) -> dict:
    awards = () if human_review_required else ("project_points",)
    from app.workers.outbox import deliver_event

    compilation, contributor, manager_token, contributor_token = await _public_project(
        client, factory, env, human_review_required=human_review_required,
    )
    project_id = str(compilation.project_id)
    task_id, assignment_id = await _started_public_task(
        client, project_id=project_id, manager_token=manager_token,
        contributor_token=contributor_token, source_ref="local-ticket-1",
    )

    archive = archive_with_modes("evidence/results", compilation.project_id)
    summary = "Completed the governed task with required evidence."
    attestation = (
        "I confirm no confidential client data, credentials, or copied source "
        "material is included in this submission; rights_confirmed."
    )
    bad = await _json(
        client, "POST", f"/api/v1/tasks/{task_id}/submission-bundle-preparations",
        contributor_token, 422,
        headers={
            "Content-Type": "application/zip",
            "X-Task-Assignment-Id": assignment_id,
            "Idempotency-Key": str(uuid4()),
            "X-Submission-Summary": summary,
            "X-Contributor-Attestation": attestation,
        },
        content=_secret_archive(archive),
    )
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
    external_bad = await _json(
        client, "POST", f"/api/v1/tasks/{task_id}/submission-bundle-preparations",
        contributor_token, 422,
        headers={
            "Content-Type": "application/zip",
            "X-Task-Assignment-Id": assignment_id,
            "Idempotency-Key": str(uuid4()),
            "X-Submission-Summary": summary,
            "X-Contributor-Attestation": attestation,
        },
        content=_with_fixture_file(archive, "project-rejected.txt"),
    )
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
    async with factory() as session:
        _require(await session.scalar(select(func.count()).select_from(Submission).where(
            Submission.task_id == task_id
        )) == 0, "failed intake created a Submission")

    async def fail_post_launch():
        from experiments.pilot04_external_checker_runtime.public_node_faults import node_command
        await node_command(fault_root, "project_fail_all")

    first_archive = (_with_fixture_file(archive, "post-rejected.txt")
                     if human_review_required else archive)
    saved = await _submit(
        client, factory, task_id=task_id, assignment_id=assignment_id,
        contributor_token=contributor_token, archive=first_archive,
        summary=summary, attestation=attestation, predecessor_id=None,
        before_create=fail_post_launch if not human_review_required and fault_root else None,
    )
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
        deliver_completion=human_review_required, successor=successor,
    )
    attempt_id = first_attempt_id
    if human_review_required:
        await _assert_revision(
            factory, project_id=compilation.project_id,
            task_id=task_id, submission_id=first_submission_id,
            attempt_id=first_attempt_id,
        )
        replacement_archive = revision_archive(archive)
        saved = await _submit(
            client, factory, task_id=task_id, assignment_id=assignment_id,
            contributor_token=contributor_token,
            archive=replacement_archive, summary=summary,
            attestation=attestation, predecessor_id=first_submission_id,
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
    else:
        await _wait_known_retry(
            factory, completion_id, compilation.project_id,
            task_id, first_submission_id,
        )
        _require(stop_worker is not None and start_worker is not None,
                 "prefork restart control is absent")
        stop_worker()
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
                 for award in item["awards"]] == [("project_points", "PTS", Decimal("7"))],
                 "public contribution source or award set differs")
    # A result for this one probe publish proves the prefork child consumed
    # the duplicate; the production task still ignores results by default.
    before_delivery = await _outbox_snapshot(factory, completion_id)
    duplicate = await asyncio.to_thread(
        deliver_event.apply_async,
        args=(str(completion_id), project_id),
        ignore_result=False,
    )
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
    if not human_review_required:
        late_revocation = await _late_revocation_trial(
            client, factory, env, project_id=compilation.project_id,
            accepted_task_id=task_id, manager_token=manager_token,
            contributor_token=contributor_token, operator_id=operator_id,
            archive=archive, summary=summary, attestation=attestation,
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
        "late_revocation": late_revocation,
    }


async def _pre_runs(factory, task_id: str) -> list[str]:
    async with factory() as session:
        return list(await session.scalars(select(SelectedPreSubmitRun.status).where(
            SelectedPreSubmitRun.task_id == task_id
        ).order_by(SelectedPreSubmitRun.queued_at)))


async def run(database_url: str, image_reference: str, node_config: Path,
              broker_url: str, root: Path, expected_custody: Path) -> dict:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    custody = json.loads(expected_custody.read_text())
    _require(custody['source_tree'] == subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=BACKEND, text=True).strip(), 'custody source differs')
    service_config = json.loads(node_config.read_text())
    _require(service_config["smol"].get("maximum_parallel") == 1,
             "public proof requires a one-slot node")
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
    _require((service_config["runtime"], service_config["isolation_mode"])
             == ("smolvm", "smol-microvm"), "public drill requires the provisioned Smol node")
    repository, digest = image_reference.rsplit("@", 1)
    images = [entry for entry in service_config["cache"]
              if entry["repository"] == repository and entry["platform_manifest_digest"] == digest]
    _require(len(images) == 1, "project image is absent or ambiguous in node cache")
    image = images[0]
    bucket = os.environ["WORKSTREAM_TEST_MINIO_BUCKET"]
    prefix = os.environ["WORKSTREAM_TEST_MINIO_PREFIX"]
    scratch = Path(service_config["material_root"])
    socket_path = Path(service_config["socket_path"])
    intake_images = [entry for entry in service_config["cache"]
                     if entry["platform_manifest_digest"]
                     == service_config["trusted_intake"]["platform_manifest_digest"]]
    _require(len(intake_images) == 1, "trusted intake image is absent or ambiguous")
    intake_image = intake_images[0]
    settings = minio_settings(private_prefix=prefix).model_copy(update={
        "artifact_s3_bucket": bucket,
        "artifact_scratch_root": scratch,
        "artifact_scratch_minimum_free_bytes": 0,
        "external_checker_service_socket": socket_path,
        "external_checker_material_root": scratch,
        "external_checker_service_timeout_seconds": 90.0,
        "artifact_intake_service_socket": socket_path,
        "artifact_intake_image_digest": intake_image["platform_manifest_digest"],
        "artifact_intake_config_digest": intake_image["config_image_id"],
    })
    bootstrap = create_artifact_store_bootstrap(settings, activation_guard=None)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    bootstrap.close()
    os.environ["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env = api_environment()
    env.update({
        "WORKSTREAM_DATABASE_URL": database_url,
        "WORKSTREAM_PROBE_INTAKE_TRACE": str(root / "intake-trace.jsonl"),
        "WORKSTREAM_E2E_FLOW_ISSUER": "https://identity.flowresearch.tech",
        "WORKSTREAM_FLOW_AUTH_ISSUER": "https://identity.flowresearch.tech",
        "WORKSTREAM_CELERY_BROKER_URL": broker_url,
        "WORKSTREAM_CELERY_RESULT_BACKEND_URL": broker_url,
        "WORKSTREAM_CELERY_TASK_ALWAYS_EAGER": "false",
        "WORKSTREAM_ARTIFACT_PENDING_WORK_SCAN_INTERVAL_SECONDS": "10",
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(scratch),
        "WORKSTREAM_ARTIFACT_SCRATCH_MINIMUM_FREE_BYTES": "0",
        "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET": str(socket_path),
        "WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT": str(scratch),
        "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_TIMEOUT_SECONDS": "90",
        "WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET": str(socket_path),
        "WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST": intake_image["platform_manifest_digest"],
        "WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST": intake_image["config_image_id"],
        "PYTHONPATH": os.pathsep.join(map(str, (BACKEND, BACKEND / "tests", BACKEND.parent))),
    })
    env.pop("OPENAI_API_KEY", None)
    # Infrastructure prerequisites and broker publication use the same
    # isolated database and provider settings as the API and worker children.
    for key, value in env.items():
        if key.startswith("WORKSTREAM_"):
            os.environ[key] = value
    os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()
    runtime_settings = get_settings()
    issuer, audience, flow_secret = flow_settings(env)
    _require(runtime_settings.database_url == database_url,
             "API/worker database differs from isolated fixture")
    _require(runtime_settings.flow_auth_issuer == issuer
             and runtime_settings.flow_auth_audience == audience
             and runtime_settings.flow_auth_local_hmac_secret == flow_secret,
             "API Flow verifier differs from local test signer")
    _require(runtime_settings.api_rate_limit_key_secret is not None
             and runtime_settings.pagination_cursor_hmac_secret is not None,
             "API rate/cursor signing configuration is absent")
    _require(runtime_settings.celery_broker_url == broker_url
             and runtime_settings.celery_task_always_eager is False,
             "worker broker configuration is not durable")
    _require(runtime_settings.artifact_pending_work_scan_interval_seconds == 10,
             "Beat artifact scan interval differs from isolated drill")
    _require(runtime_settings.artifact_scratch_root == scratch
             and runtime_settings.artifact_scratch_minimum_free_bytes == 0
             and runtime_settings.external_checker_service_socket == socket_path
             and runtime_settings.external_checker_material_root == scratch,
             "API/worker scratch or checker service configuration differs from fixture")
    for field in (
        "artifact_store_backend", "artifact_s3_provider_profile", "artifact_s3_region",
        "artifact_s3_endpoint_url", "artifact_s3_bucket", "artifact_s3_private_prefix",
        "artifact_s3_addressing_style", "artifact_s3_credential_mode",
        "artifact_s3_access_key_id", "artifact_s3_secret_access_key",
    ):
        _require(getattr(runtime_settings, field) == getattr(settings, field),
                 "API/worker artifact provider configuration differs from fixture")
    runtime_bootstrap = create_artifact_store_bootstrap(runtime_settings, activation_guard=None)
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
    _preflight_children(runtime_settings, env, root)

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    api = worker = beat = None
    worker_generation = 0

    def stop_owned_worker() -> None:
        _require(worker is not None and worker.poll() is None,
                 "prefork worker was not running before restart")
        _stop_process(worker)
        _require(worker.poll() is not None, "old prefork worker did not exit")

    async def start_owned_worker() -> None:
        nonlocal worker, worker_generation
        _require(worker is None or worker.poll() is not None,
                 "prefork worker was not stopped before restart")
        previous_pid = worker.pid if worker is not None else None
        worker_generation += 1
        worker, hostname = _start_worker(env, root, worker_generation)
        _require(worker.pid != previous_pid, "restart reused the old worker process")
        await _wait_worker(worker, hostname)

    try:
        await provision_material_services(factory, artifacts=True, checker=True)
        await provision_router(factory)
        await provision_reconciler(factory)
        await _provision_runtime_services(factory)
        for phase in ("pre_submit", "post_submit"):
            await _register_external_checker_fixture(factory, _locked_spec(phase, image))
        operator, _ = await seed_review_actor(factory, None, role="operator", scope="system")
        from tests.reviews.lifecycle.transition_support import command_for, transition
        await transition(await command_for(operator.actor_profile_id, "shadow"))

        intake_health = await trusted_submission_intake(runtime_settings).health()
        execution_health = await configured_external_checker_execution(runtime_settings).health()
        _require((execution_health.runtime, execution_health.isolation_mode)
                 == (intake_health.runtime, intake_health.isolation_mode)
                 == ("smolvm", "smol-microvm"), "typed capability health identities disagree")
        port = find_free_port()
        origin = f"http://127.0.0.1:{port}"
        api = _process([
            sys.executable, "-m", "uvicorn",
            "experiments.pilot04_external_checker_runtime.public_intake_observer:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "error", "--no-access-log",
        ], env=env, log=root / "api.log")
        await _wait_api(origin, api)
        await start_owned_worker()
        scans_before_beat = await _scan_audit_count(factory)
        beat = _process([
            sys.executable, "-m", "celery", "-A", "app.workers.celery_app",
            "beat", "--loglevel=ERROR",
            "--schedule", str(root / "beat-schedule"),
        ], env=env, log=root / "beat.log")
        await _wait_beat_scan(factory, beat, scans_before_beat)
        async with httpx.AsyncClient(base_url=origin, timeout=90) as client:
            from experiments.pilot04_external_checker_runtime.public_intake_trials import public_intake_trials
            intake_trials = await public_intake_trials(
                client, factory, env, root / "intake-trace.jsonl", root / "node-control")
            from experiments.pilot04_external_checker_runtime.public_runtime_trials import public_runtime_trials
            fault_root = root / "node-control"
            _require((fault_root / "supervisor-ready").exists(), "owned node supervisor is absent")
            runtime_trials = await public_runtime_trials(client, factory, env, fault_root)
            true = await _one_mode(client, factory, env,
                                   human_review_required=True,
                                   operator_id=operator.actor_profile_id)
            false = await _one_mode(client, factory, env,
                                    human_review_required=False,
                                    operator_id=operator.actor_profile_id,
                                    stop_worker=stop_owned_worker,
                                    start_worker=start_owned_worker, fault_root=fault_root,
                                    operator_token=_token(env, operator))
        _require(api.poll() is None and worker.poll() is None and beat.poll() is None,
                 "API, prefork worker, or Beat exited during public journey")
        return {"tree_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=BACKEND
        ).strip(), "runtime": "smolvm/smol-microvm", "image_digest": image["platform_manifest_digest"],
                "trusted_intake_image_digest": intake_health.image_digest,
                "trusted_intake_config_digest": intake_health.config_digest,
                "public_api": True, "prefork_worker": True, "maximum_parallel": 1,
                "scheduled_artifact_scans": True,
                "public_original_guide_setup": True,
                "recorded_inference": True,
                "custody": {key: custody[key] for key in (
                    'source_tree', 'config_sha256', 'service_sha256', 'smol_sha256', 'guest_sha256', 'wrapper_sha256')},
                "runtime_trials": runtime_trials, "intake_trials": intake_trials, "human": true, "automatic": false}
    finally:
        _stop_process(beat)
        for schedule_file in root.glob("beat-schedule*"):
            schedule_file.unlink()
        _stop_process(worker)
        _stop_process(api)
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("WORKSTREAM_TEST_DATABASE_URL"))
    parser.add_argument("--image-reference")
    parser.add_argument("--node-config", type=Path, help="Owned provisioned Smol node configuration")
    parser.add_argument("--broker-url")
    parser.add_argument("--expected-custody", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path,
                        help="Unique private directory retaining API and worker diagnostics")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("isolated --database-url or WORKSTREAM_TEST_DATABASE_URL is required")
    if not args.image_reference or not args.node_config or not args.broker_url:
        parser.error("full drill requires image, node config, and broker URL")
    workspace = (nullcontext(args.work_dir) if args.work_dir else
                 tempfile.TemporaryDirectory(prefix="ws-pilot04-public-"))
    with workspace as directory:
        value = asyncio.run(run(
            args.database_url, args.image_reference, args.node_config,
            args.broker_url, Path(directory), args.expected_custody,
        ))
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
