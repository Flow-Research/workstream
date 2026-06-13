"""Run real HTTP Week 2 checker flows against Postgres and local Flow tokens."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from alembic import command
from sqlalchemy import select

from app.db import session as db_session
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.tasks.models import AuditEvent, EvidenceItem, Submission, WorkstreamTask
from week1_api_e2e import (
    alembic_config,
    api_environment,
    find_free_port,
    flow_settings,
    guide_payload,
    issue_flow_token,
    project_root,
    request_json,
    wait_for_health,
)

EXPECTED_DURABLE_CHECKERS = {
    "check_submission_packet",
    "check_policy_context_present",
    "check_evidence_present",
    "check_evidence_integrity",
    "check_required_files",
    "check_forbidden_files",
    "check_confidentiality_attestation",
    "check_low_quality_generated_artifacts",
}
EXPECTED_PRE_SUBMIT_CHECKERS = {
    "check_submission_packet",
    "check_evidence_present",
    "check_evidence_integrity",
    "check_required_files",
    "check_forbidden_files",
    "check_confidentiality_attestation",
}
LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_DATABASE_NAMES = {"workstream_test", "test_workstream"}
ASYNC_POSTGRES_SCHEMES = {"postgresql+asyncpg"}
NONLOCAL_DATABASE_OVERRIDE_VALUE = "I_UNDERSTAND_THIS_WRITES_DATA"
STRONG_ATTESTATION = (
    "I attest this submission contains no confidential client data, credentials, "
    "secrets, tokens, passwords, API keys, private source material, source code, "
    "copied platform artifacts, or copied platform content."
)


def ensure(condition: bool, message: str) -> None:
    """Raise a normal assertion error when a drill invariant is false.

    Args:
        condition: Invariant result.
        message: Failure message.
    """
    if not condition:
        raise AssertionError(message)


def assert_local_database_url(database_url: str) -> None:
    """Fail closed unless the E2E database URL is explicitly local.

    Args:
        database_url: SQLAlchemy async database URL resolved for the drill.
    """
    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")
    is_local_async_postgres = (
        parsed.scheme in ASYNC_POSTGRES_SCHEMES
        and parsed.hostname in LOCAL_DATABASE_HOSTS
        and database_name in LOCAL_DATABASE_NAMES
    )
    override = os.environ.get("WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE")
    if is_local_async_postgres or override == NONLOCAL_DATABASE_OVERRIDE_VALUE:
        return
    raise RuntimeError(
        "Refusing to run Week 2 API E2E against a non-local database. "
        "Use an async Postgres URL such as postgresql+asyncpg:// on "
        "localhost/127.0.0.1 with a local test database named "
        "workstream_test or test_workstream, or set "
        f"WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE={NONLOCAL_DATABASE_OVERRIDE_VALUE}."
    )


def start_week2_api_server(port: int, env: dict[str, str]) -> tuple[subprocess.Popen, Path]:
    """Start a real uvicorn server process for the Week 2 drill.

    Args:
        port: Localhost port for the server.
        env: Environment variables for the server process.

    Returns:
        Server process and Week 2-specific log path.
    """
    log_path = project_root() / ".week2_api_e2e_server.log"
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=project_root(),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_file.close()
    return process, log_path


def checker_result(run: dict, checker_name: str) -> dict:
    """Return one checker result from a checker run response.

    Args:
        run: Checker run response payload.
        checker_name: Checker name to find.

    Returns:
        Matching checker result payload.
    """
    for result in run["results"]:
        if result["checker_name"] == checker_name:
            return result
    raise AssertionError(f"checker result missing: {checker_name}")


def assert_default_checker_set(run: dict) -> None:
    """Assert the Week 2 durable checker set ran.

    Args:
        run: Checker run response payload.
    """
    assert_checker_set(run["results"], EXPECTED_DURABLE_CHECKERS, "default durable")


def assert_setup_checker_set(run: dict) -> None:
    """Assert the setup-defect checker set ran exactly.

    Args:
        run: Checker run response payload.
    """
    assert_checker_set(
        run["results"],
        EXPECTED_DURABLE_CHECKERS | {"check_acceptance_criteria_present"},
        "setup durable",
    )


def assert_checker_set(results: list[dict], expected: set[str], label: str) -> None:
    """Assert a checker result list matches the expected checker contract.

    Args:
        results: Checker result payloads.
        expected: Expected checker names.
        label: Human-readable checker set label.
    """
    names = [result["checker_name"] for result in results]
    duplicate_names = {checker_name for checker_name in names if names.count(checker_name) > 1}
    ensure(not duplicate_names, f"{label} checker set has duplicate results: {duplicate_names}")
    name_set = set(names)
    missing = expected.difference(name_set)
    unexpected = name_set.difference(expected)
    ensure(
        not missing and not unexpected,
        (
            f"{label} checker set drifted: "
            f"missing={sorted(missing)} unexpected={sorted(unexpected)}"
        ),
    )


def assert_pre_submit_checker_set(response: dict) -> None:
    """Assert the Week 2 pre-submit checker set ran exactly.

    Args:
        response: Pre-submit checker response payload.
    """
    assert_checker_set(response["results"], EXPECTED_PRE_SUBMIT_CHECKERS, "pre-submit")


def task_payload(run_id: str, suffix: str) -> dict:
    """Build a complete task payload for a Week 2 API scenario.

    Args:
        run_id: Unique test run id.
        suffix: Scenario suffix for source references.

    Returns:
        Task creation payload.
    """
    return {
        "title": f"Week 2 checker task {suffix}",
        "description": "Exercise Week 2 checker routing over real HTTP.",
        "task_type": "evaluation",
        "difficulty": "medium",
        "skill_tags": ["stem", "proofs"],
        "estimated_time_minutes": 45,
        "source_type": "manual",
        "source_ref": f"week2-{suffix}-{run_id}",
        "source_payload_hash": f"sha256:source-{suffix}-{run_id}",
        "acceptance_criteria": "Submission packet is complete and reviewable.",
        "rejection_criteria": "Evidence or required output is missing.",
        "required_files": ["answer.md"],
        "required_evidence": ["checker log"],
    }


def submission_payload(run_id: str, suffix: str) -> dict:
    """Build a complete submission packet payload.

    Args:
        run_id: Unique test run id.
        suffix: Scenario suffix for deterministic hashes.

    Returns:
        Submission creation payload.
    """
    return {
        "summary": f"Week 2 {suffix} packet completed.",
        "package_uri": f"local://week2/{run_id}/{suffix}/package.tar.zst",
        "package_hash": f"sha256:package-{suffix}-{run_id}",
        "artifact_hash_manifest": [
            {
                "artifact": "answer.md",
                "hash": f"sha256:answer-{suffix}-{run_id}",
                "size_bytes": 128,
                "notes": "main answer",
            }
        ],
        "worker_attestation": STRONG_ATTESTATION,
        "evidence_items": [
            {
                "type": "log",
                "label": f"checker evidence {suffix}",
                "uri": f"local://week2/{run_id}/{suffix}/checker.log",
                "hash": f"sha256:evidence-{suffix}-{run_id}",
                "size_bytes": 256,
                "metadata": {"command": "week2_api_e2e"},
            }
        ],
    }


def token_for(
    subject: str,
    roles: list[str],
    *,
    issuer: str,
    audience: str,
    secret: str,
) -> str:
    """Issue one local Flow token for the Week 2 API drill.

    Args:
        subject: External Flow subject.
        roles: Flow roles to include in the signed token.
        issuer: Expected Flow issuer.
        audience: Expected Flow audience.
        secret: Local HMAC secret.

    Returns:
        Signed local Flow bearer token.
    """
    return issue_flow_token(
        subject,
        roles,
        issuer=issuer,
        audience=audience,
        secret=secret,
    )


async def create_project_with_guide(
    client: httpx.AsyncClient,
    manager_token: str,
    run_id: str,
    suffix: str,
    required_checkers: list[str] | None = None,
) -> dict:
    """Create a project and activate a complete guide over HTTP.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        run_id: Unique test run id.
        suffix: Scenario suffix used in the project slug.
        required_checkers: Optional checker policy override.

    Returns:
        Created project payload.
    """
    project = await request_json(
        client,
        "POST",
        "/api/v1/projects",
        manager_token,
        {
            "name": f"Week 2 API {suffix} {run_id}",
            "slug": f"week2-api-{suffix}-{run_id}",
            "description": "Real Week 2 checker API lifecycle QA",
            "base_amount": "25.00",
            "currency": "USD",
        },
        201,
    )
    payload = guide_payload(run_id)
    if required_checkers is not None:
        payload["checker_policy"]["required_checkers"] = required_checkers
    guide = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides",
        manager_token,
        payload,
        201,
    )
    await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        manager_token,
    )
    return project


async def create_started_task(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    worker_token: str,
    project_id: str,
    run_id: str,
    suffix: str,
    worker_subject: str,
    flow_issuer: str,
) -> dict:
    """Create, release, claim, and start one task over HTTP.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        worker_token: Worker Flow token.
        project_id: Project id that owns the task.
        run_id: Unique test run id.
        suffix: Scenario suffix.
        worker_subject: External Flow worker subject.
        flow_issuer: Expected Flow issuer for the worker profile.

    Returns:
        Started task payload.
    """
    task = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project_id}/tasks",
        manager_token,
        task_payload(run_id, suffix),
        201,
    )
    await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/screen",
        manager_token,
        {"reason": f"{suffix} screening passed"},
    )
    await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/release",
        manager_token,
        {"reason": f"{suffix} release"},
    )
    worker_profile = await request_json(
        client,
        "POST",
        "/api/v1/demo/worker-profile",
        worker_token,
        {"skill_tags": ["stem", "proofs"]},
        201,
    )
    ensure(worker_profile["external_subject"] == worker_subject, "worker subject mismatch")
    ensure(worker_profile["external_issuer"] == flow_issuer, "worker issuer mismatch")
    await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/claim",
        worker_token,
        {"reason": f"{suffix} claim"},
    )
    started = await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/start",
        worker_token,
        {"reason": f"{suffix} start"},
    )
    ensure(started["status"] == "in_progress", "task did not start")
    return started


async def submit_lock_and_get_run(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    worker_token: str,
    task_id: str,
    payload: dict,
) -> tuple[dict, dict, dict]:
    """Submit a packet, lock it, and return the automatic checker run.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        worker_token: Worker Flow token.
        task_id: Task receiving the submission.
        payload: Submission packet payload.

    Returns:
        Created submission, locked submission, and automatic checker run payload.
    """
    submission = await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task_id}/submissions",
        worker_token,
        payload,
        201,
    )
    locked = await request_json(
        client,
        "POST",
        f"/api/v1/submissions/{submission['id']}/lock",
        manager_token,
    )
    assert_locked_submission_response(locked)
    checker_run = await wait_for_submission_checker_run(
        client,
        manager_token,
        submission["id"],
    )
    return submission, locked, checker_run


def assert_locked_submission_response(submission: dict) -> None:
    """Assert a locked submission response has complete locked context.

    Args:
        submission: Locked submission response payload.
    """
    ensure(submission["locked_at"] is not None, "locked submission missing locked_at")
    locked_versions = {
        submission["locked_guide_version"],
        submission["locked_checker_policy_version"],
        submission["locked_review_policy_version"],
        submission["locked_revision_policy_version"],
        submission["locked_payment_policy_version"],
    }
    ensure(locked_versions == {"v1"}, f"locked context drifted: {locked_versions}")
    ensure(
        all(item["locked_at"] == submission["locked_at"] for item in submission["evidence_items"]),
        "evidence item locked_at does not match submission locked_at",
    )


async def assert_lock_idempotency(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    submission_id: str,
    expected_locked_at: str,
    expected_checker_run_id: str,
) -> None:
    """Assert locking an already locked submission does not create another run.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        submission_id: Submission id to relock.
        expected_locked_at: Original lock timestamp.
        expected_checker_run_id: Original automatic checker run id.
    """
    relocked = await request_json(
        client,
        "POST",
        f"/api/v1/submissions/{submission_id}/lock",
        manager_token,
    )
    ensure(relocked["locked_at"] == expected_locked_at, "idempotent lock changed locked_at")
    runs = await request_json(
        client,
        "GET",
        f"/api/v1/submissions/{submission_id}/checker-runs",
        manager_token,
    )
    ensure(len(runs) == 1, f"idempotent lock created extra checker runs: {len(runs)}")
    ensure(runs[0]["id"] == expected_checker_run_id, "idempotent lock changed checker run")
    ensure(runs[0]["attempt_number"] == 1, "idempotent lock changed attempt number")


async def wait_for_submission_checker_run(
    client: httpx.AsyncClient,
    manager_token: str,
    submission_id: str,
) -> dict:
    """Wait for the automatic submission-locked checker run.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        submission_id: Submission id whose checker run should exist.

    Returns:
        Completed checker run payload.
    """
    last_count = 0
    for _ in range(50):
        runs = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{submission_id}/checker-runs",
            manager_token,
        )
        ensure(isinstance(runs, list), "checker run list did not return a list")
        last_count = len(runs)
        if len(runs) == 1 and runs[0]["trigger_source"] == "submission_locked":
            return await wait_for_checker_run_terminal(
                client,
                manager_token,
                runs[0]["id"],
            )
        await asyncio.sleep(0.2)
    raise AssertionError(
        "automatic checker run was not created exactly once: "
        f"submission_id={submission_id} count={last_count}"
    )


async def wait_for_checker_run_terminal(
    client: httpx.AsyncClient,
    manager_token: str,
    checker_run_id: str,
) -> dict:
    """Wait for a checker run to reach a terminal status.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        checker_run_id: Checker run id to poll.

    Returns:
        Terminal checker run payload.
    """
    terminal_statuses = {"completed", "failed"}
    checker_run: dict | None = None
    for _ in range(50):
        checker_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{checker_run_id}",
            manager_token,
        )
        if checker_run["status"] in terminal_statuses:
            return checker_run
        await asyncio.sleep(0.2)
    raise AssertionError(
        "checker run did not reach terminal status: "
        f"checker_run_id={checker_run_id} status={checker_run['status'] if checker_run else None}"
    )


async def assert_task_status(
    client: httpx.AsyncClient,
    manager_token: str,
    task_id: str,
    expected_status: str,
) -> None:
    """Assert the current task status through the API.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        task_id: Task id to read.
        expected_status: Expected task status token.
    """
    task: dict | None = None
    for _ in range(50):
        task = await request_json(client, "GET", f"/api/v1/tasks/{task_id}", manager_token)
        if task["status"] == expected_status:
            return
        await asyncio.sleep(0.2)
    raise AssertionError(
        f"expected {expected_status}, got {task['status'] if task else None}"
    )


async def break_acceptance_criteria(task_id: str) -> None:
    """Create a controlled locked task setup defect that normal APIs prevent.

    Args:
        task_id: Task id whose acceptance criteria should be removed.
    """
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, task_id)
        if task is None:
            raise AssertionError(f"task not found: {task_id}")
        task.acceptance_criteria = None
        await session.commit()


async def repair_acceptance_criteria(task_id: str) -> None:
    """Repair the controlled task setup defect before trusted checker retry.

    Args:
        task_id: Task id whose acceptance criteria should be restored.
    """
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, task_id)
        if task is None:
            raise AssertionError(f"task not found: {task_id}")
        task.acceptance_criteria = "Submission packet is complete and reviewable."
        await session.commit()


async def assert_week2_database_invariants(scenarios: list[dict]) -> None:
    """Verify Week 2 API scenarios produced exact durable database state.

    Args:
        scenarios: Scenario expectations captured from real API responses.
    """
    async with db_session.get_session_factory()() as session:
        for scenario in scenarios:
            task = await session.get(WorkstreamTask, scenario["task_id"])
            submission = await session.get(Submission, scenario["submission_id"])
            checker_run = await session.get(CheckerRun, scenario["checker_run_id"])
            ensure(task is not None, f"{scenario['name']} task missing")
            ensure(submission is not None, f"{scenario['name']} submission missing")
            ensure(checker_run is not None, f"{scenario['name']} checker run missing")

            ensure(
                task.status == scenario["expected_task_status"],
                f"{scenario['name']} task status drifted: {task.status}",
            )
            task_versions = {
                task.locked_guide_version,
                task.locked_checker_policy_version,
                task.locked_review_policy_version,
                task.locked_revision_policy_version,
                task.locked_payment_policy_version,
            }
            ensure(task_versions == {"v1"}, f"{scenario['name']} task context drifted")
            submission_versions = {
                submission.locked_guide_version,
                submission.locked_checker_policy_version,
                submission.locked_review_policy_version,
                submission.locked_revision_policy_version,
                submission.locked_payment_policy_version,
            }
            ensure(
                submission_versions == task_versions,
                f"{scenario['name']} submission context drifted",
            )
            ensure(submission.locked_at is not None, f"{scenario['name']} submission not locked")
            ensure(
                submission.locked_at.isoformat().replace("+00:00", "Z")
                == scenario["locked_at"],
                f"{scenario['name']} locked_at response/database drifted",
            )
            evidence_items = (
                await session.scalars(
                    select(EvidenceItem).where(EvidenceItem.submission_id == submission.id)
                )
            ).all()
            ensure(evidence_items, f"{scenario['name']} evidence items missing")
            ensure(
                all(item.locked_at == submission.locked_at for item in evidence_items),
                f"{scenario['name']} evidence lock drifted",
            )

            ensure(
                checker_run.routing_recommendation == scenario["expected_route"],
                f"{scenario['name']} checker route drifted",
            )
            ensure(checker_run.status == "completed", f"{scenario['name']} checker incomplete")
            ensure(
                checker_run.trigger_source == scenario["expected_trigger_source"],
                f"{scenario['name']} checker trigger drifted",
            )
            ensure(
                checker_run.attempt_number == scenario["expected_attempt"],
                f"{scenario['name']} checker attempt drifted",
            )
            ensure(
                checker_run.is_current_for_submission is scenario["expected_current"],
                f"{scenario['name']} current-run flag drifted",
            )
            ensure(
                checker_run.submission_version == submission.version,
                f"{scenario['name']} submission version drifted on checker run",
            )
            ensure(
                checker_run.package_hash == submission.package_hash,
                f"{scenario['name']} package hash drifted on checker run",
            )
            run_versions = {
                checker_run.locked_guide_version,
                checker_run.locked_checker_policy_version,
                checker_run.locked_review_policy_version,
                checker_run.locked_revision_policy_version,
                checker_run.locked_payment_policy_version,
            }
            ensure(run_versions == submission_versions, f"{scenario['name']} checker context drifted")

            results = (
                await session.scalars(
                    select(CheckerResult).where(CheckerResult.checker_run_id == checker_run.id)
                )
            ).all()
            result_names = [result.checker_name for result in results]
            duplicate_names = {
                checker_name for checker_name in result_names if result_names.count(checker_name) > 1
            }
            ensure(
                not duplicate_names,
                f"{scenario['name']} duplicate checker results persisted: {duplicate_names}",
            )
            ensure(
                set(result_names) == scenario["expected_checkers"],
                f"{scenario['name']} checker set drifted: {result_names}",
            )
            ensure(
                checker_run.passed_count
                == sum(1 for result in results if result.status == "passed"),
                f"{scenario['name']} passed count drifted",
            )
            ensure(
                checker_run.warning_count
                == sum(1 for result in results if result.status == "warning"),
                f"{scenario['name']} warning count drifted",
            )
            ensure(
                checker_run.failed_count
                == sum(1 for result in results if result.status == "failed"),
                f"{scenario['name']} failed count drifted",
            )
            ensure(
                checker_run.blocking_count
                == sum(1 for result in results if result.blocks_review),
                f"{scenario['name']} blocking count drifted",
            )

            runs = (
                await session.scalars(
                    select(CheckerRun)
                    .where(CheckerRun.submission_id == submission.id)
                    .order_by(CheckerRun.attempt_number.asc())
                )
            ).all()
            ensure(
                [run.attempt_number for run in runs] == scenario["expected_attempts"],
                f"{scenario['name']} checker attempts drifted",
            )
            ensure(
                sum(1 for run in runs if run.is_current_for_submission) == 1,
                f"{scenario['name']} current-run uniqueness drifted",
            )
            ensure(
                [run.id for run in runs if run.is_current_for_submission][0]
                == scenario["expected_current_run_id"],
                f"{scenario['name']} current run id drifted",
            )

            task_events = (
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "task",
                        AuditEvent.entity_id == task.id,
                    )
                )
            ).all()
            ensure(
                any(
                    event.event_type == scenario["expected_gate_event"]
                    and event.event_payload.get("checker_run_id") == checker_run.id
                    and event.event_payload.get("trigger_source")
                    == scenario["expected_trigger_source"]
                    for event in task_events
                ),
                f"{scenario['name']} gate audit event missing matching trigger/run payload",
            )

    print("PASS Week 2 database invariants")


async def exercise_week2_api(base_url: str, env: dict[str, str]) -> None:
    """Run real Week 2 checker flows over HTTP.

    Args:
        base_url: Real API server base URL.
        env: Runtime environment shared by the API server and token issuer.
    """
    flow_issuer, flow_audience, flow_secret = flow_settings(env)
    run_id = uuid4().hex[:8]
    manager_token = token_for(
        f"week2-manager-{run_id}",
        ["project_manager"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    reviewer_token = token_for(
        f"week2-reviewer-{run_id}",
        ["reviewer"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    unassigned_worker_token = token_for(
        f"week2-worker-unassigned-{run_id}",
        ["worker"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        await request_json(client, "GET", "/api/v1/health")

        clean_worker_subject = f"week2-worker-clean-{run_id}"
        clean_worker_token = token_for(
            clean_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        clean_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "clean",
        )
        clean_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=clean_worker_token,
            project_id=clean_project["id"],
            run_id=run_id,
            suffix="clean",
            worker_subject=clean_worker_subject,
            flow_issuer=flow_issuer,
        )
        clean_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{clean_task['id']}/submission-precheck",
            clean_worker_token,
            {"submission": submission_payload(run_id, "clean")},
        )
        ensure(clean_precheck["authoritative"] is False, "precheck must be non-authoritative")
        ensure(clean_precheck["eligible_to_submit"] is True, "clean precheck should pass")
        assert_pre_submit_checker_set(clean_precheck)
        await assert_task_status(client, manager_token, clean_task["id"], "in_progress")
        clean_precheck_submissions = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{clean_task['id']}/submissions",
            clean_worker_token,
        )
        ensure(clean_precheck_submissions == [], "clean precheck created a submission")
        clean_submission, clean_locked, clean_run = await submit_lock_and_get_run(
            client,
            manager_token=manager_token,
            worker_token=clean_worker_token,
            task_id=clean_task["id"],
            payload=submission_payload(run_id, "clean"),
        )
        assert_default_checker_set(clean_run)
        ensure(clean_run["routing_recommendation"] == "allow_review", "clean run was blocked")
        ensure(clean_run["blocking_count"] == 0, "clean run had blocking checker results")
        await assert_lock_idempotency(
            client,
            manager_token=manager_token,
            submission_id=clean_submission["id"],
            expected_locked_at=clean_locked["locked_at"],
            expected_checker_run_id=clean_run["id"],
        )
        await assert_task_status(client, manager_token, clean_task["id"], "review_pending")
        worker_clean_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{clean_run['id']}",
            clean_worker_token,
        )
        ensure(
            worker_clean_run["routing_recommendation"] == "allow_review",
            "worker clean route mismatch",
        )
        ensure(worker_clean_run["artifact_hash_manifest"] == [], "worker saw artifact manifest")
        manager_clean_runs = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{clean_submission['id']}/checker-runs",
            manager_token,
        )
        ensure(len(manager_clean_runs) == 1, "manager checker-run list count drifted")
        worker_clean_runs = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{clean_submission['id']}/checker-runs",
            clean_worker_token,
        )
        ensure(len(worker_clean_runs) == 1, "worker checker-run list count drifted")
        ensure(
            worker_clean_runs[0]["artifact_hash_manifest"] == [],
            "worker checker-run list exposed artifact manifest",
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{clean_run['id']}",
            reviewer_token,
            expected_status=403,
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{clean_submission['id']}/checker-runs",
            reviewer_token,
            expected_status=403,
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{clean_submission['id']}/checker-runs",
            unassigned_worker_token,
            expected_status=404,
        )

        revision_worker_subject = f"week2-worker-revision-{run_id}"
        revision_worker_token = token_for(
            revision_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        revision_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "revision",
        )
        revision_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=revision_worker_token,
            project_id=revision_project["id"],
            run_id=run_id,
            suffix="revision",
            worker_subject=revision_worker_subject,
            flow_issuer=flow_issuer,
        )
        missing_file_payload = submission_payload(run_id, "revision-v1")
        missing_file_payload["artifact_hash_manifest"] = [
            {
                "artifact": "other.md",
                "hash": f"sha256:other-{run_id}",
                "size_bytes": 128,
                "notes": "wrong artifact",
            }
        ]
        failed_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{revision_task['id']}/submission-precheck",
            revision_worker_token,
            {"submission": missing_file_payload},
        )
        assert_pre_submit_checker_set(failed_precheck)
        ensure(failed_precheck["eligible_to_submit"] is False, "missing file precheck passed")
        await assert_task_status(client, manager_token, revision_task["id"], "in_progress")
        revision_precheck_submissions = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{revision_task['id']}/submissions",
            revision_worker_token,
        )
        ensure(revision_precheck_submissions == [], "failed precheck created a submission")
        first_submission, first_locked, first_run = await submit_lock_and_get_run(
            client,
            manager_token=manager_token,
            worker_token=revision_worker_token,
            task_id=revision_task["id"],
            payload=missing_file_payload,
        )
        assert_default_checker_set(first_run)
        ensure(first_run["routing_recommendation"] == "needs_revision", "missing file route drifted")
        ensure(first_run["outcome_source"] == "auto_checker", "missing file source drifted")
        await assert_task_status(client, manager_token, revision_task["id"], "needs_revision")
        worker_revision_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{first_run['id']}",
            revision_worker_token,
        )
        required_file_result = checker_result(worker_revision_run, "check_required_files")
        ensure(bool(required_file_result["worker_message"]), "required-file worker message missing")
        ensure(required_file_result["metadata"] == {}, "worker saw required-file metadata")
        second_submission, second_locked, second_run = await submit_lock_and_get_run(
            client,
            manager_token=manager_token,
            worker_token=revision_worker_token,
            task_id=revision_task["id"],
            payload=submission_payload(run_id, "revision-v2"),
        )
        assert_default_checker_set(second_run)
        ensure(first_submission["version"] == 1, "first submission version drifted")
        ensure(second_submission["version"] == 2, "second submission version drifted")
        ensure(second_run["routing_recommendation"] == "allow_review", "fixed v2 did not pass")
        await assert_task_status(client, manager_token, revision_task["id"], "review_pending")

        missing_evidence_worker_subject = f"week2-worker-no-evidence-{run_id}"
        missing_evidence_worker_token = token_for(
            missing_evidence_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        missing_evidence_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "no-evidence",
        )
        missing_evidence_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=missing_evidence_worker_token,
            project_id=missing_evidence_project["id"],
            run_id=run_id,
            suffix="no-evidence",
            worker_subject=missing_evidence_worker_subject,
            flow_issuer=flow_issuer,
        )
        missing_evidence_payload = submission_payload(run_id, "no-evidence")
        missing_evidence_payload["evidence_items"] = []
        missing_evidence_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{missing_evidence_task['id']}/submission-precheck",
            missing_evidence_worker_token,
            {"submission": missing_evidence_payload},
        )
        assert_pre_submit_checker_set(missing_evidence_precheck)
        ensure(
            missing_evidence_precheck["eligible_to_submit"] is False,
            "missing evidence precheck should block submission",
        )
        await assert_task_status(client, manager_token, missing_evidence_task["id"], "in_progress")
        missing_evidence_submissions = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{missing_evidence_task['id']}/submissions",
            missing_evidence_worker_token,
        )
        ensure(missing_evidence_submissions == [], "missing evidence precheck created a submission")
        missing_evidence_precheck_result = next(
            result
            for result in missing_evidence_precheck["results"]
            if result["checker_name"] == "check_evidence_present"
        )
        ensure(
            missing_evidence_precheck_result["status"] == "failed",
            "missing evidence precheck did not fail",
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{missing_evidence_task['id']}/submissions",
            missing_evidence_worker_token,
            missing_evidence_payload,
            422,
        )

        integrity_worker_subject = f"week2-worker-integrity-{run_id}"
        integrity_worker_token = token_for(
            integrity_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        integrity_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "integrity",
        )
        integrity_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=integrity_worker_token,
            project_id=integrity_project["id"],
            run_id=run_id,
            suffix="integrity",
            worker_subject=integrity_worker_subject,
            flow_issuer=flow_issuer,
        )
        duplicate_artifact_payload = submission_payload(run_id, "integrity")
        duplicate_artifact_payload["artifact_hash_manifest"].append(
            {
                "artifact": "answer.md",
                "hash": f"sha256:duplicate-{run_id}",
                "size_bytes": 128,
                "notes": "duplicate artifact",
            }
        )
        integrity_submission, integrity_locked, integrity_run = await submit_lock_and_get_run(
            client,
            manager_token=manager_token,
            worker_token=integrity_worker_token,
            task_id=integrity_task["id"],
            payload=duplicate_artifact_payload,
        )
        assert_default_checker_set(integrity_run)
        ensure(
            integrity_run["routing_recommendation"] == "needs_revision",
            "integrity failure did not route to needs_revision",
        )
        ensure(
            checker_result(integrity_run, "check_evidence_integrity")["status"] == "failed",
            "evidence integrity checker did not fail",
        )

        attestation_worker_subject = f"week2-worker-attestation-{run_id}"
        attestation_worker_token = token_for(
            attestation_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        attestation_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "attestation",
        )
        attestation_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=attestation_worker_token,
            project_id=attestation_project["id"],
            run_id=run_id,
            suffix="attestation",
            worker_subject=attestation_worker_subject,
            flow_issuer=flow_issuer,
        )
        weak_attestation_payload = submission_payload(run_id, "attestation")
        weak_attestation_payload["worker_attestation"] = "ok"
        attestation_submission, attestation_locked, attestation_run = await submit_lock_and_get_run(
            client,
            manager_token=manager_token,
            worker_token=attestation_worker_token,
            task_id=attestation_task["id"],
            payload=weak_attestation_payload,
        )
        assert_default_checker_set(attestation_run)
        ensure(
            attestation_run["routing_recommendation"] == "needs_revision",
            "weak attestation did not route to needs_revision",
        )
        ensure(
            checker_result(attestation_run, "check_confidentiality_attestation")["status"]
            == "failed",
            "confidentiality attestation checker did not fail",
        )

        warning_worker_subject = f"week2-worker-warning-{run_id}"
        warning_worker_token = token_for(
            warning_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        warning_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "warning",
        )
        warning_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=warning_worker_token,
            project_id=warning_project["id"],
            run_id=run_id,
            suffix="warning",
            worker_subject=warning_worker_subject,
            flow_issuer=flow_issuer,
        )
        warning_payload = submission_payload(run_id, "warning")
        warning_payload["summary"] = "Completed with a placeholder note that must be reviewed."
        warning_submission, warning_locked, warning_run = await submit_lock_and_get_run(
            client,
            manager_token=manager_token,
            worker_token=warning_worker_token,
            task_id=warning_task["id"],
            payload=warning_payload,
        )
        assert_default_checker_set(warning_run)
        ensure(warning_run["routing_recommendation"] == "allow_review", "warning blocked review")
        ensure(warning_run["warning_count"] >= 1, "warning checker count missing")
        ensure(
            checker_result(warning_run, "check_low_quality_generated_artifacts")["status"]
            == "warning",
            "low-quality generated artifact checker did not warn",
        )

        forbidden_worker_subject = f"week2-worker-forbidden-{run_id}"
        forbidden_worker_token = token_for(
            forbidden_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        forbidden_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "forbidden",
        )
        forbidden_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=forbidden_worker_token,
            project_id=forbidden_project["id"],
            run_id=run_id,
            suffix="forbidden",
            worker_subject=forbidden_worker_subject,
            flow_issuer=flow_issuer,
        )
        forbidden_payload = submission_payload(run_id, "forbidden")
        forbidden_payload["artifact_hash_manifest"].append(
            {
                "artifact": "secrets/.env",
                "hash": f"sha256:forbidden-{run_id}",
                "size_bytes": 64,
                "notes": "must be blocked",
            }
        )
        forbidden_submission, forbidden_locked, forbidden_run = await submit_lock_and_get_run(
            client,
            manager_token=manager_token,
            worker_token=forbidden_worker_token,
            task_id=forbidden_task["id"],
            payload=forbidden_payload,
        )
        assert_default_checker_set(forbidden_run)
        ensure(
            forbidden_run["routing_recommendation"] == "needs_revision",
            "forbidden path did not route to needs_revision",
        )
        ensure(
            checker_result(forbidden_run, "check_forbidden_files")["status"] == "failed",
            "forbidden-file checker did not fail",
        )
        worker_forbidden_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{forbidden_run['id']}",
            forbidden_worker_token,
        )
        serialized_forbidden = str(worker_forbidden_run)
        ensure(".env" not in serialized_forbidden, "worker saw forbidden .env path")
        ensure("secrets/" not in serialized_forbidden, "worker saw forbidden directory path")
        ensure("local://" not in serialized_forbidden, "worker saw internal storage URI")

        setup_worker_subject = f"week2-worker-setup-{run_id}"
        setup_worker_token = token_for(
            setup_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        setup_project = await create_project_with_guide(
            client,
            manager_token,
            run_id,
            "setup",
            required_checkers=["check_acceptance_criteria_present"],
        )
        setup_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=setup_worker_token,
            project_id=setup_project["id"],
            run_id=run_id,
            suffix="setup",
            worker_subject=setup_worker_subject,
            flow_issuer=flow_issuer,
        )
        setup_submission = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{setup_task['id']}/submissions",
            setup_worker_token,
            submission_payload(run_id, "setup"),
            201,
        )
        await break_acceptance_criteria(setup_task["id"])
        setup_locked = await request_json(
            client,
            "POST",
            f"/api/v1/submissions/{setup_submission['id']}/lock",
            manager_token,
        )
        assert_locked_submission_response(setup_locked)
        setup_run = await wait_for_submission_checker_run(
            client,
            manager_token,
            setup_submission["id"],
        )
        assert_setup_checker_set(setup_run)
        ensure(
            setup_run["routing_recommendation"] == "task_setup_blocked",
            "task setup defect did not use internal route",
        )
        ensure(
            checker_result(setup_run, "check_acceptance_criteria_present")["status"] == "failed",
            "acceptance criteria checker did not fail",
        )
        await assert_task_status(client, manager_token, setup_task["id"], "auto_checking")
        worker_setup_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{setup_run['id']}",
            setup_worker_token,
        )
        ensure(
            worker_setup_run["routing_recommendation"] == "not_evaluated",
            "worker saw internal setup route",
        )
        ensure(worker_setup_run["results"] == [], "worker saw internal setup results")
        await repair_acceptance_criteria(setup_task["id"])
        retry = await request_json(
            client,
            "POST",
            f"/api/v1/submissions/{setup_submission['id']}/checker-runs",
            manager_token,
            {"trigger_reason": "Week 2 API setup repair"},
        )
        assert_setup_checker_set(retry)
        ensure(retry["attempt_number"] == 2, "trusted checker retry did not create attempt 2")
        ensure(
            retry["routing_recommendation"] == "allow_review",
            "trusted checker retry did not pass",
        )
        ensure(
            retry["supersedes_checker_run_id"] == setup_run["id"],
            "trusted checker retry did not supersede blocked run",
        )
        setup_runs_after_retry = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{setup_submission['id']}/checker-runs",
            manager_token,
        )
        ensure(len(setup_runs_after_retry) == 2, "trusted checker retry run count drifted")
        setup_runs_by_attempt = {
            run["attempt_number"]: run for run in setup_runs_after_retry
        }
        ensure(
            sorted(setup_runs_by_attempt) == [1, 2],
            f"trusted checker retry attempts drifted: {sorted(setup_runs_by_attempt)}",
        )
        ensure(
            setup_runs_by_attempt[1]["is_current_for_submission"] is False,
            "superseded checker run still current",
        )
        ensure(
            setup_runs_by_attempt[2]["is_current_for_submission"] is True,
            "retry checker run is not current",
        )
        ensure(
            setup_runs_by_attempt[1]["trigger_source"] == "submission_locked",
            "first setup checker trigger source drifted",
        )
        ensure(
            setup_runs_by_attempt[2]["trigger_source"] == "manual_checker_trigger",
            "retry checker trigger source drifted",
        )
        await assert_task_status(client, manager_token, setup_task["id"], "review_pending")

    setup_checker_set = EXPECTED_DURABLE_CHECKERS | {"check_acceptance_criteria_present"}
    await assert_week2_database_invariants(
        [
            {
                "name": "clean",
                "task_id": clean_task["id"],
                "submission_id": clean_submission["id"],
                "checker_run_id": clean_run["id"],
                "locked_at": clean_locked["locked_at"],
                "expected_route": "allow_review",
                "expected_task_status": "review_pending",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": clean_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_passed",
            },
            {
                "name": "missing_file_v1",
                "task_id": revision_task["id"],
                "submission_id": first_submission["id"],
                "checker_run_id": first_run["id"],
                "locked_at": first_locked["locked_at"],
                "expected_route": "needs_revision",
                "expected_task_status": "review_pending",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": first_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_needs_revision",
            },
            {
                "name": "revision_v2",
                "task_id": revision_task["id"],
                "submission_id": second_submission["id"],
                "checker_run_id": second_run["id"],
                "locked_at": second_locked["locked_at"],
                "expected_route": "allow_review",
                "expected_task_status": "review_pending",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": second_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_passed",
            },
            {
                "name": "integrity",
                "task_id": integrity_task["id"],
                "submission_id": integrity_submission["id"],
                "checker_run_id": integrity_run["id"],
                "locked_at": integrity_locked["locked_at"],
                "expected_route": "needs_revision",
                "expected_task_status": "needs_revision",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": integrity_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_needs_revision",
            },
            {
                "name": "attestation",
                "task_id": attestation_task["id"],
                "submission_id": attestation_submission["id"],
                "checker_run_id": attestation_run["id"],
                "locked_at": attestation_locked["locked_at"],
                "expected_route": "needs_revision",
                "expected_task_status": "needs_revision",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": attestation_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_needs_revision",
            },
            {
                "name": "warning",
                "task_id": warning_task["id"],
                "submission_id": warning_submission["id"],
                "checker_run_id": warning_run["id"],
                "locked_at": warning_locked["locked_at"],
                "expected_route": "allow_review",
                "expected_task_status": "review_pending",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": warning_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_passed",
            },
            {
                "name": "forbidden",
                "task_id": forbidden_task["id"],
                "submission_id": forbidden_submission["id"],
                "checker_run_id": forbidden_run["id"],
                "locked_at": forbidden_locked["locked_at"],
                "expected_route": "needs_revision",
                "expected_task_status": "needs_revision",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": forbidden_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_needs_revision",
            },
            {
                "name": "setup_blocked",
                "task_id": setup_task["id"],
                "submission_id": setup_submission["id"],
                "checker_run_id": setup_run["id"],
                "locked_at": setup_locked["locked_at"],
                "expected_route": "task_setup_blocked",
                "expected_task_status": "review_pending",
                "expected_trigger_source": "submission_locked",
                "expected_attempt": 1,
                "expected_attempts": [1, 2],
                "expected_current": False,
                "expected_current_run_id": retry["id"],
                "expected_checkers": setup_checker_set,
                "expected_gate_event": "pre_review_gate_blocked",
            },
            {
                "name": "setup_retry",
                "task_id": setup_task["id"],
                "submission_id": setup_submission["id"],
                "checker_run_id": retry["id"],
                "locked_at": setup_locked["locked_at"],
                "expected_route": "allow_review",
                "expected_task_status": "review_pending",
                "expected_trigger_source": "manual_checker_trigger",
                "expected_attempt": 2,
                "expected_attempts": [1, 2],
                "expected_current": True,
                "expected_current_run_id": retry["id"],
                "expected_checkers": setup_checker_set,
                "expected_gate_event": "pre_review_gate_passed",
            },
        ]
    )

    print("Week 2 real API e2e passed")
    print("scenario_summary:")
    print("clean=review_pending")
    print("missing_file=needs_revision")
    print("missing_evidence=pre_submit_blocked")
    print("duplicate_artifact_integrity=needs_revision")
    print("weak_attestation=needs_revision")
    print("generated_output_warning=review_pending")
    print("forbidden_path=needs_revision")
    print("task_setup_blocked=auto_checking->review_pending")
    print(f"clean_task_id={clean_task['id']}")
    print(f"clean_submission_id={clean_submission['id']}")
    print(f"revision_task_id={revision_task['id']}")
    print(f"revision_v1_submission_id={first_submission['id']}")
    print(f"revision_v2_submission_id={second_submission['id']}")
    print(f"missing_evidence_task_id={missing_evidence_task['id']}")
    print(f"integrity_task_id={integrity_task['id']}")
    print(f"attestation_task_id={attestation_task['id']}")
    print(f"warning_task_id={warning_task['id']}")
    print(f"forbidden_task_id={forbidden_task['id']}")
    print(f"setup_task_id={setup_task['id']}")


async def main(env: dict[str, str]) -> None:
    """Start the API server and exercise Week 2 checker APIs.

    Args:
        env: Environment variables for the API server.
    """
    await db_session.dispose_engine()

    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    process, log_path = start_week2_api_server(port, env)
    try:
        await wait_for_health(base_url, process, log_path)
        await exercise_week2_api(base_url, env)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    api_env = api_environment()
    assert_local_database_url(api_env["WORKSTREAM_DATABASE_URL"])
    os.environ.update(api_env)
    command.upgrade(alembic_config(), "head")
    asyncio.run(main(api_env))
