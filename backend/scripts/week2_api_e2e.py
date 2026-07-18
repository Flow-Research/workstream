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
from api_contract_e2e import (
    DERIVED_DATABASE_NAME,
    alembic_config,
    api_environment as contract_api_environment,
    create_policy_bundle_for_guide,
    find_free_port,
    flow_settings,
    guide_payload,
    issue_flow_token,
    project_root,
    request_json,
    sha256_token,
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
    "check_low_quality_generated_artifacts",
}
DATABASE_URL_ENV = "WORKSTREAM_DATABASE_URL"
TEST_DATABASE_URL_ENV = "WORKSTREAM_TEST_DATABASE_URL"
LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_DATABASE_NAMES = {"workstream_test", "test_workstream"}
ASYNC_POSTGRES_SCHEMES = {"postgresql+asyncpg"}
NONLOCAL_DATABASE_OVERRIDE_VALUE = "I_UNDERSTAND_THIS_WRITES_DATA"
STRONG_ATTESTATION = (
    "I attest this submission contains no confidential client data, credentials, "
    "secrets, tokens, passwords, API keys, private source material, source code, "
    "copied platform artifacts, or copied platform content, and it satisfies "
    "the original_work, credentials_and_secret_exclusion, real_api_originality, and "
    "human_accountability_for_agent_assisted_work policy terms."
)


def ensure(condition: bool, message: str) -> None:
    """Raise a normal assertion error when a drill invariant is false.

    Args:
        condition: Invariant result.
        message: Failure message.
    """
    if not condition:
        raise AssertionError(message)


def api_environment() -> dict[str, str]:
    """Build the API environment and honor the contract's test DB variable."""
    env = contract_api_environment()
    test_database_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if test_database_url:
        env[DATABASE_URL_ENV] = test_database_url
    return env


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
        and (
            database_name in LOCAL_DATABASE_NAMES
            or DERIVED_DATABASE_NAME.fullmatch(database_name) is not None
        )
    )
    override = os.environ.get("WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE")
    if is_local_async_postgres or override == NONLOCAL_DATABASE_OVERRIDE_VALUE:
        return
    raise RuntimeError(
        "Refusing to run Week 2 API E2E against a non-local database. "
        "Use an async Postgres URL such as postgresql+asyncpg:// on "
        "localhost/127.0.0.1 with a local test database named "
        "workstream_test, test_workstream, or workstream_test_<12 lowercase hex>, or set "
        f"WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE={NONLOCAL_DATABASE_OVERRIDE_VALUE}."
    )


def start_backend_api_server(port: int, env: dict[str, str]) -> tuple[subprocess.Popen, Path]:
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
        "source_payload_hash": sha256_token(f"source:{suffix}:{run_id}"),
        "acceptance_criteria": "Submission packet is complete and reviewable.",
        "rejection_criteria": "Evidence or required output is missing.",
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
        "package_hash": sha256_token(f"package:{suffix}:{run_id}"),
        "artifact_hash_manifest": [
            {
                "artifact": "answer.md",
                "hash": sha256_token(f"answer:{suffix}:{run_id}"),
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
                "hash": sha256_token(f"evidence:{suffix}:{run_id}"),
                "size_bytes": 256,
                "metadata": {
                    "command": "week2_api_e2e",
                    "required_evidence_key": "checker_log",
                },
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
        roles: Trusted v0.1 bootstrap role claims for the signed token.
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
    manager_subject: str,
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
        },
        201,
    )
    guide = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides",
        manager_token,
        guide_payload(run_id),
        201,
    )
    await create_policy_bundle_for_guide(
        client,
        manager_token,
        manager_subject,
        project["id"],
        guide["id"],
        run_id,
        post_submit_required_checkers=required_checkers,
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
        "/api/v1/workers/me/profile",
        worker_token,
        {"skill_tags": ["stem", "proofs"]},
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


async def submit_and_get_automatic_run(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    worker_token: str,
    task_id: str,
    payload: dict,
) -> tuple[dict, dict, dict]:
    """Submit a packet and return the automatic checker run.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token used for operator visibility.
        worker_token: Worker Flow token.
        task_id: Task receiving the submission.
        payload: Submission packet payload.

    Returns:
        Created/locked submission, same locked response, and automatic checker run payload.
    """
    submission = await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task_id}/submissions",
        worker_token,
        payload,
        201,
    )
    ensure(submission["finalized_at"] is not None, "created submission missing finalized_at")
    finalized = await request_json(
        client,
        "GET",
        f"/api/v1/submissions/{submission['id']}",
        manager_token,
    )
    assert_finalized_submission_versions(finalized)
    checker_run = await wait_for_submission_checker_run(
        client,
        manager_token,
        submission["id"],
    )
    return submission, finalized, checker_run


def assert_finalized_submission_versions(submission: dict) -> None:
    """Assert a locked submission response has expected version stamps.

    Args:
        submission: Locked submission response payload.
    """
    ensure(submission["finalized_at"] is not None, "locked submission missing finalized_at")
    locked_versions = {
        submission["locked_guide_version"],
        submission["locked_review_policy_version"],
        submission["locked_revision_policy_version"],
        submission["locked_payment_policy_version"],
    }
    ensure(locked_versions == {"v1"}, f"locked context drifted: {locked_versions}")
    ensure(
        all(item["finalized_at"] == submission["finalized_at"] for item in submission["evidence_items"]),
        "evidence item finalized_at does not match submission finalized_at",
    )


async def assert_finalize_idempotency(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    submission_id: str,
    expected_finalized_at: str,
    expected_checker_run_id: str,
) -> None:
    """Assert repair-checking an already locked submission does not create another run.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        submission_id: Submission id to repair-check.
        expected_finalized_at: Original lock timestamp exposed as finalized_at.
        expected_checker_run_id: Original automatic checker run id.
    """
    refinalized = await request_json(
        client,
        "POST",
        f"/api/v1/submissions/{submission_id}/finalize",
        manager_token,
    )
    ensure(refinalized["finalized_at"] == expected_finalized_at, "idempotent finalize changed finalized_at")
    runs = await request_json(
        client,
        "GET",
        f"/api/v1/submissions/{submission_id}/checker-runs",
        manager_token,
    )
    ensure(len(runs) == 1, f"idempotent finalize created extra checker runs: {len(runs)}")
    ensure(runs[0]["id"] == expected_checker_run_id, "idempotent finalize changed checker run")
    ensure(runs[0]["attempt_number"] == 1, "idempotent finalize changed attempt number")


async def wait_for_submission_checker_run(
    client: httpx.AsyncClient,
    manager_token: str,
    submission_id: str,
) -> dict:
    """Wait for the automatic locked-submission checker run.

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
        if len(runs) == 1 and runs[0]["trigger_source"] == "submission_finalized":
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


async def task_side_effect_snapshot(task_id: str) -> dict:
    """Capture task-scoped persisted rows for no-side-effect assertions.

    Args:
        task_id: Task id whose durable side effects should be captured.

    Returns:
        Stable snapshot of task, submission, checker, and audit rows.
    """
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, task_id)
        submissions = (
            await session.scalars(
                select(Submission).where(Submission.task_id == task_id).order_by(Submission.id)
            )
        ).all()
        submission_ids = [submission.id for submission in submissions]
        evidence_items = []
        if submission_ids:
            evidence_items = (
                await session.scalars(
                    select(EvidenceItem)
                    .where(EvidenceItem.submission_id.in_(submission_ids))
                    .order_by(EvidenceItem.id)
                )
            ).all()
        checker_runs = (
            await session.scalars(
                select(CheckerRun).where(CheckerRun.task_id == task_id).order_by(CheckerRun.id)
            )
        ).all()
        checker_results = (
            await session.scalars(
                select(CheckerResult)
                .where(CheckerResult.task_id == task_id)
                .order_by(CheckerResult.id)
            )
        ).all()
        audit_events = (
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "task", AuditEvent.entity_id == task_id)
                .order_by(AuditEvent.id)
            )
        ).all()
        submission_audit_events = []
        if submission_ids:
            submission_audit_events = (
                await session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.entity_type == "submission",
                        AuditEvent.entity_id.in_(submission_ids),
                    )
                    .order_by(AuditEvent.id)
                )
            ).all()
        return {
            "task_status": None if task is None else task.status,
            "submissions": [
                (
                    submission.id,
                    submission.version,
                    submission.status,
                    submission.package_hash,
                    submission.supersedes_submission_id,
                )
                for submission in submissions
            ],
            "evidence_items": [
                (item.id, item.submission_id, item.type, item.hash) for item in evidence_items
            ],
            "checker_runs": [
                (
                    run.id,
                    run.submission_id,
                    run.submission_version,
                    run.attempt_number,
                    run.routing_recommendation,
                )
                for run in checker_runs
            ],
            "checker_results": [
                (result.id, result.checker_run_id, result.checker_name, result.status)
                for result in checker_results
            ],
            "audit_events": [
                (
                    event.id,
                    event.event_type,
                    event.from_status,
                    event.to_status,
                    event.event_payload,
                )
                for event in audit_events
            ],
            "submission_audit_events": [
                (
                    event.id,
                    event.entity_id,
                    event.event_type,
                    event.from_status,
                    event.to_status,
                    event.event_payload,
                )
                for event in submission_audit_events
            ],
        }


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
                task.status == scenario["expected_final_task_status"],
                f"{scenario['name']} final task status drifted: {task.status}",
            )
            task_versions = {
                task.locked_guide_version,
                task.locked_review_policy_version,
                task.locked_revision_policy_version,
                task.locked_payment_policy_version,
            }
            ensure(task_versions == {"v1"}, f"{scenario['name']} task context drifted")
            ensure(
                task.locked_post_submit_checker_policy_id is not None
                and task.locked_post_submit_checker_policy_version == "v1"
                and task.locked_post_submit_checker_policy_hash is not None,
                f"{scenario['name']} task post-submit policy lock missing",
            )
            ensure(
                task.locked_guide_source_snapshot_id is not None
                and task.locked_guide_source_snapshot_hash is not None,
                f"{scenario['name']} task guide-source snapshot lock missing",
            )
            ensure(
                task.locked_effective_project_submission_artifact_policy_id is not None
                and task.locked_effective_project_submission_artifact_policy_hash is not None,
                f"{scenario['name']} task effective project policy lock missing",
            )
            ensure(
                task.locked_pre_submit_checker_policy_id is not None
                and task.locked_pre_submit_checker_bundle_hash is not None,
                f"{scenario['name']} task pre-submit checker lock missing",
            )
            submission_versions = {
                submission.locked_guide_version,
                submission.locked_review_policy_version,
                submission.locked_revision_policy_version,
                submission.locked_payment_policy_version,
            }
            ensure(
                submission_versions == task_versions,
                f"{scenario['name']} submission context drifted",
            )
            ensure(
                submission.locked_post_submit_checker_policy_id
                == task.locked_post_submit_checker_policy_id,
                f"{scenario['name']} submission post-submit policy id drifted",
            )
            ensure(
                submission.locked_post_submit_checker_policy_version
                == task.locked_post_submit_checker_policy_version,
                f"{scenario['name']} submission post-submit policy version drifted",
            )
            ensure(
                submission.locked_post_submit_checker_policy_hash
                == task.locked_post_submit_checker_policy_hash,
                f"{scenario['name']} submission post-submit policy hash drifted",
            )
            ensure(
                submission.locked_guide_source_snapshot_id
                == task.locked_guide_source_snapshot_id
                and submission.locked_guide_source_snapshot_hash
                == task.locked_guide_source_snapshot_hash,
                f"{scenario['name']} submission guide-source snapshot drifted",
            )
            ensure(
                submission.locked_effective_project_submission_artifact_policy_id
                == task.locked_effective_project_submission_artifact_policy_id
                and submission.locked_effective_project_submission_artifact_policy_hash
                == task.locked_effective_project_submission_artifact_policy_hash,
                f"{scenario['name']} submission effective project policy drifted",
            )
            ensure(
                submission.locked_pre_submit_checker_policy_id
                == task.locked_pre_submit_checker_policy_id
                and submission.locked_pre_submit_checker_bundle_hash
                == task.locked_pre_submit_checker_bundle_hash,
                f"{scenario['name']} submission pre-submit checker lock drifted",
            )
            ensure(submission.locked_at is not None, f"{scenario['name']} submission not finalized")
            ensure(
                submission.locked_at.isoformat().replace("+00:00", "Z")
                == scenario["finalized_at"],
                f"{scenario['name']} finalized_at response/database drifted",
            )
            evidence_items = (
                await session.scalars(
                    select(EvidenceItem).where(EvidenceItem.submission_id == submission.id)
                )
            ).all()
            ensure(evidence_items, f"{scenario['name']} evidence items missing")
            ensure(
                all(item.locked_at == submission.locked_at for item in evidence_items),
                f"{scenario['name']} evidence finalize timestamp drifted",
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
                checker_run.locked_review_policy_version,
                checker_run.locked_revision_policy_version,
                checker_run.locked_payment_policy_version,
            }
            ensure(run_versions == submission_versions, f"{scenario['name']} checker context drifted")
            ensure(
                checker_run.locked_post_submit_checker_policy_id
                == submission.locked_post_submit_checker_policy_id,
                f"{scenario['name']} checker post-submit policy id drifted",
            )
            ensure(
                checker_run.locked_post_submit_checker_policy_version
                == submission.locked_post_submit_checker_policy_version,
                f"{scenario['name']} checker post-submit policy version drifted",
            )
            ensure(
                checker_run.locked_post_submit_checker_policy_hash
                == submission.locked_post_submit_checker_policy_hash,
                f"{scenario['name']} checker post-submit policy hash drifted",
            )

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
            expected_task_transitions = scenario.get("expected_task_transitions", [])
            actual_task_transitions = {
                (event.from_status, event.to_status) for event in task_events
            }
            for transition in expected_task_transitions:
                ensure(
                    tuple(transition) in actual_task_transitions,
                    f"{scenario['name']} missing task transition: {transition}",
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
    manager_subject = f"week2-manager-{run_id}"
    manager_token = token_for(
        manager_subject,
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
            manager_subject,
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
        ensure(
            clean_precheck["eligible_to_submit"] is True,
            f"clean precheck should pass: {clean_precheck}",
        )
        assert_pre_submit_checker_set(clean_precheck)
        await assert_task_status(client, manager_token, clean_task["id"], "in_progress")
        clean_precheck_submissions = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{clean_task['id']}/submissions",
            clean_worker_token,
        )
        ensure(clean_precheck_submissions == [], "clean precheck created a submission")
        clean_submission, clean_finalized, clean_run = await submit_and_get_automatic_run(
            client,
            manager_token=manager_token,
            worker_token=clean_worker_token,
            task_id=clean_task["id"],
            payload=submission_payload(run_id, "clean"),
        )
        assert_default_checker_set(clean_run)
        ensure(clean_run["routing_recommendation"] == "allow_review", "clean run was blocked")
        ensure(clean_run["blocking_count"] == 0, "clean run had blocking checker results")
        await assert_finalize_idempotency(
            client,
            manager_token=manager_token,
            submission_id=clean_submission["id"],
            expected_finalized_at=clean_finalized["finalized_at"],
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
            "routing_recommendation" not in worker_clean_run,
            "worker saw internal routing recommendation",
        )
        ensure("outcome_source" not in worker_clean_run, "worker saw internal outcome source")
        ensure("trigger_source" not in worker_clean_run, "worker saw internal trigger source")
        ensure(
            "locked_post_submit_checker_policy_hash" not in worker_clean_run,
            "worker saw locked post-submit checker policy hash",
        )
        ensure("artifact_hash_manifest" not in worker_clean_run, "worker saw artifact manifest")
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
            "artifact_hash_manifest" not in worker_clean_runs[0],
            "worker checker-run list exposed artifact manifest",
        )
        ensure(
            "routing_recommendation" not in worker_clean_runs[0],
            "worker checker-run list exposed routing recommendation",
        )
        ensure(
            "locked_post_submit_checker_policy_hash" not in worker_clean_runs[0],
            "worker checker-run list exposed locked post-submit checker policy hash",
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

        trusted_retry_worker_subject = f"week2-worker-trusted-retry-{run_id}"
        trusted_retry_worker_token = token_for(
            trusted_retry_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        trusted_retry_project = await create_project_with_guide(
            client,
            manager_token,
            manager_subject,
            run_id,
            "trusted-retry",
        )
        trusted_retry_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=trusted_retry_worker_token,
            project_id=trusted_retry_project["id"],
            run_id=run_id,
            suffix="trusted-retry",
            worker_subject=trusted_retry_worker_subject,
            flow_issuer=flow_issuer,
        )
        (
            trusted_retry_submission,
            trusted_retry_finalized,
            trusted_retry_initial_run,
        ) = await submit_and_get_automatic_run(
            client,
            manager_token=manager_token,
            worker_token=trusted_retry_worker_token,
            task_id=trusted_retry_task["id"],
            payload=submission_payload(run_id, "trusted-retry"),
        )
        assert_default_checker_set(trusted_retry_initial_run)
        ensure(
            trusted_retry_initial_run["routing_recommendation"] == "allow_review",
            "trusted retry initial run did not pass",
        )
        await assert_task_status(
            client,
            manager_token,
            trusted_retry_task["id"],
            "review_pending",
        )
        trusted_retry_run = await request_json(
            client,
            "POST",
            f"/api/v1/submissions/{trusted_retry_submission['id']}/checker-runs",
            manager_token,
            {"trigger_reason": "Week 2 trusted review-pending retry"},
            200,
        )
        assert_default_checker_set(trusted_retry_run)
        ensure(
            trusted_retry_run["attempt_number"] == 2,
            "trusted review-pending retry did not create attempt 2",
        )
        ensure(
            trusted_retry_run["routing_recommendation"] == "allow_review",
            "trusted review-pending retry did not pass",
        )
        ensure(
            trusted_retry_run["supersedes_checker_run_id"] == trusted_retry_initial_run["id"],
            "trusted review-pending retry did not supersede initial run",
        )
        await assert_task_status(
            client,
            manager_token,
            trusted_retry_task["id"],
            "review_pending",
        )
        trusted_retry_runs = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{trusted_retry_submission['id']}/checker-runs",
            manager_token,
        )
        ensure(len(trusted_retry_runs) == 2, "trusted retry run count drifted")
        trusted_retry_runs_by_attempt = {
            run["attempt_number"]: run for run in trusted_retry_runs
        }
        ensure(
            trusted_retry_runs_by_attempt[1]["is_current_for_submission"] is False,
            "trusted retry initial run still current",
        )
        ensure(
            trusted_retry_runs_by_attempt[2]["is_current_for_submission"] is True,
            "trusted retry run is not current",
        )
        ensure(
            trusted_retry_runs_by_attempt[2]["trigger_source"] == "manual_checker_trigger",
            "trusted retry trigger source drifted",
        )
        worker_trusted_retry_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{trusted_retry_run['id']}",
            trusted_retry_worker_token,
        )
        ensure(
            "trigger_source" not in worker_trusted_retry_run,
            "worker saw trusted retry trigger source",
        )
        ensure(
            "routing_recommendation" not in worker_trusted_retry_run,
            "worker saw trusted retry route",
        )
        ensure(
            "artifact_hash_manifest" not in worker_trusted_retry_run,
            "worker saw trusted retry artifact manifest",
        )
        ensure(
            "manual_checker_trigger" not in str(worker_trusted_retry_run),
            "worker saw trusted retry internal trigger label",
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
            manager_subject,
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
                "hash": sha256_token(f"other:{run_id}"),
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
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{revision_task['id']}/submissions",
            revision_worker_token,
            missing_file_payload,
            422,
        )
        revision_blocked_create_snapshot = await task_side_effect_snapshot(revision_task["id"])
        ensure(
            revision_blocked_create_snapshot["submissions"] == [],
            "blocked submission create persisted a submission",
        )
        ensure(
            revision_blocked_create_snapshot["checker_runs"] == [],
            "blocked submission create persisted a checker run",
        )
        ensure(
            revision_blocked_create_snapshot["checker_results"] == [],
            "blocked submission create persisted a checker result",
        )
        ensure(
            revision_blocked_create_snapshot["submission_audit_events"] == [],
            "blocked submission create persisted submission audit events",
        )
        ensure(
            all(
                event[1] not in {"submission_created", "submission_finalized", "checker_run_triggered"}
                for event in revision_blocked_create_snapshot["audit_events"]
            ),
            "blocked submission create persisted task submission/checker audit events",
        )

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
            manager_subject,
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
            manager_subject,
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
                "hash": sha256_token(f"duplicate:{run_id}"),
                "size_bytes": 128,
                "notes": "duplicate artifact",
            }
        )
        integrity_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{integrity_task['id']}/submission-precheck",
            integrity_worker_token,
            {"submission": duplicate_artifact_payload},
        )
        assert_pre_submit_checker_set(integrity_precheck)
        ensure(
            integrity_precheck["eligible_to_submit"] is False,
            "duplicate artifact precheck should block submission",
        )
        ensure(
            next(
                result
                for result in integrity_precheck["results"]
                if result["checker_name"] == "check_evidence_integrity"
            )["status"]
            == "failed",
            "duplicate artifact precheck did not fail integrity",
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{integrity_task['id']}/submissions",
            integrity_worker_token,
            duplicate_artifact_payload,
            422,
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
            manager_subject,
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
        attestation_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{attestation_task['id']}/submission-precheck",
            attestation_worker_token,
            {"submission": weak_attestation_payload},
        )
        assert_pre_submit_checker_set(attestation_precheck)
        ensure(
            attestation_precheck["eligible_to_submit"] is False,
            "weak attestation precheck should block submission",
        )
        ensure(
            next(
                result
                for result in attestation_precheck["results"]
                if result["checker_name"] == "check_confidentiality_attestation"
            )["status"]
            == "failed",
            "weak attestation precheck did not fail confidentiality",
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{attestation_task['id']}/submissions",
            attestation_worker_token,
            weak_attestation_payload,
            422,
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
            manager_subject,
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
        warning_submission, warning_finalized, warning_run = await submit_and_get_automatic_run(
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

        checker_revision_worker_subject = f"week2-worker-checker-revision-{run_id}"
        checker_revision_worker_token = token_for(
            checker_revision_worker_subject,
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )
        checker_revision_project = await create_project_with_guide(
            client,
            manager_token,
            manager_subject,
            run_id,
            "checker-revision",
            required_checkers=["check_low_quality_generated_artifacts"],
        )
        checker_revision_task = await create_started_task(
            client,
            manager_token=manager_token,
            worker_token=checker_revision_worker_token,
            project_id=checker_revision_project["id"],
            run_id=run_id,
            suffix="checker-revision",
            worker_subject=checker_revision_worker_subject,
            flow_issuer=flow_issuer,
        )
        checker_revision_v1_payload = submission_payload(run_id, "checker-revision-v1")
        checker_revision_v1_payload["summary"] = (
            "Completed the project evaluation with TODO placeholder notes."
        )
        checker_revision_v1_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{checker_revision_task['id']}/submission-precheck",
            checker_revision_worker_token,
            {"submission": checker_revision_v1_payload},
        )
        assert_pre_submit_checker_set(checker_revision_v1_precheck)
        ensure(
            checker_revision_v1_precheck["eligible_to_submit"] is True,
            "checker-caused revision precheck should not block before submission",
        )
        (
            checker_revision_v1_submission,
            checker_revision_v1_finalized,
            checker_revision_v1_run,
        ) = await submit_and_get_automatic_run(
            client,
            manager_token=manager_token,
            worker_token=checker_revision_worker_token,
            task_id=checker_revision_task["id"],
            payload=checker_revision_v1_payload,
        )
        assert_default_checker_set(checker_revision_v1_run)
        ensure(
            checker_revision_v1_run["routing_recommendation"] == "needs_revision",
            "required post-submit checker did not route to needs_revision",
        )
        ensure(
            checker_revision_v1_run["outcome_source"] == "auto_checker",
            "checker-caused revision did not stamp auto_checker outcome source",
        )
        checker_revision_v1_result = checker_result(
            checker_revision_v1_run,
            "check_low_quality_generated_artifacts",
        )
        ensure(
            checker_revision_v1_result["status"] == "failed",
            "required low-quality checker did not fail",
        )
        ensure(
            checker_revision_v1_result["blocks_review"] is True,
            "required low-quality checker did not block review",
        )
        ensure(
            checker_revision_v1_result["worker_message"],
            "checker-caused revision missing worker message",
        )
        ensure(
            checker_revision_v1_result["worker_suggested_fix"],
            "checker-caused revision missing suggested fix",
        )
        await assert_task_status(
            client,
            manager_token,
            checker_revision_task["id"],
            "needs_revision",
        )
        checker_revision_worker_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{checker_revision_v1_run['id']}",
            checker_revision_worker_token,
        )
        ensure(
            "routing_recommendation" not in checker_revision_worker_run,
            "worker saw internal revision route",
        )
        ensure(
            "outcome_source" not in checker_revision_worker_run,
            "worker saw internal revision outcome source",
        )
        ensure(
            "artifact_hash_manifest" not in checker_revision_worker_run,
            "worker saw revision artifact manifest",
        )
        checker_revision_worker_result = checker_result(
            checker_revision_worker_run,
            "check_low_quality_generated_artifacts",
        )
        ensure(
            checker_revision_worker_result["id"],
            "worker-visible revision result missing stable id",
        )
        ensure(
            checker_revision_worker_result["status"] == "failed",
            "worker-visible revision result status drifted",
        )
        ensure(
            checker_revision_worker_result["severity"] == "high",
            "worker-visible revision result severity drifted",
        )
        ensure(
            checker_revision_worker_result["worker_message"],
            "worker-visible revision result missing message",
        )
        ensure(
            checker_revision_worker_result["worker_suggested_fix"],
            "worker-visible revision result missing suggested fix",
        )
        checker_revision_audit = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{checker_revision_task['id']}/audit-events",
            manager_token,
        )
        ensure(
            any(
                event["event_type"] == "pre_review_gate_needs_revision"
                and event["event_payload"].get("checker_run_id")
                == checker_revision_v1_run["id"]
                and event["event_payload"].get("outcome_source") == "auto_checker"
                and event["event_payload"].get("review_decision_id") is None
                for event in checker_revision_audit
            ),
            "checker-caused revision audit event missing review_decision_id null",
        )
        await request_json(
            client,
            "POST",
            "/api/v1/workers/me/profile",
            unassigned_worker_token,
            {"skill_tags": ["stem", "proofs"]},
        )
        denied_snapshot = await task_side_effect_snapshot(checker_revision_task["id"])
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{checker_revision_task['id']}/submission-precheck",
            unassigned_worker_token,
            {"submission": submission_payload(run_id, "checker-intruder")},
            404,
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{checker_revision_task['id']}/submissions",
            unassigned_worker_token,
            submission_payload(run_id, "checker-intruder"),
            404,
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{checker_revision_task['id']}/submissions",
            unassigned_worker_token,
            expected_status=404,
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{checker_revision_v1_run['id']}",
            unassigned_worker_token,
            expected_status=404,
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{checker_revision_task['id']}/audit-events",
            unassigned_worker_token,
            expected_status=404,
        )
        ensure(
            await task_side_effect_snapshot(checker_revision_task["id"]) == denied_snapshot,
            "denied non-owner calls created task side effects",
        )

        malicious_payload = submission_payload(run_id, "checker-malicious")
        malicious_payload.update(
            {
                "allow_review": True,
                "checker_retry": True,
                "locked_guide_version": "v999",
                "locked_pre_submit_checker_bundle_hash": "sha256:fake",
                "locked_pre_submit_checker_policy_id": "fake-policy",
                "outcome_source": "auto_checker",
                "review_decision": "accept",
                "review_decision_id": "fake-review-decision",
                "routing_recommendation": "allow_review",
                "task_setup_blocked": True,
                "trigger_source": "submission_finalized",
            }
        )
        malicious_snapshot = await task_side_effect_snapshot(checker_revision_task["id"])
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{checker_revision_task['id']}/submission-precheck",
            checker_revision_worker_token,
            {"submission": malicious_payload},
            422,
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{checker_revision_task['id']}/submissions",
            checker_revision_worker_token,
            malicious_payload,
            422,
        )
        ensure(
            await task_side_effect_snapshot(checker_revision_task["id"]) == malicious_snapshot,
            "malicious internal-field payload created task side effects",
        )

        checker_revision_v2_payload = submission_payload(run_id, "checker-revision-v2")
        checker_revision_v2_payload["summary"] = (
            "Completed the project evaluation with task-specific final evidence."
        )
        checker_revision_v2_payload["artifact_hash_manifest"][0]["hash"] = sha256_token(
            f"answer:checker-revision-v2-fixed:{run_id}"
        )
        checker_revision_v2_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{checker_revision_task['id']}/submission-precheck",
            checker_revision_worker_token,
            {"submission": checker_revision_v2_payload},
        )
        assert_pre_submit_checker_set(checker_revision_v2_precheck)
        ensure(
            checker_revision_v2_precheck["eligible_to_submit"] is True,
            "fixed revision precheck should pass",
        )
        checker_revision_v2_submission = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{checker_revision_task['id']}/submissions",
            checker_revision_worker_token,
            checker_revision_v2_payload,
            201,
        )
        ensure(
            checker_revision_v2_submission["version"] == 2,
            "fixed revision did not create submission version 2",
        )
        ensure(
            checker_revision_v2_submission["supersedes_submission_id"]
            == checker_revision_v1_submission["id"],
            "fixed revision did not supersede v1",
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/submissions/{checker_revision_v1_submission['id']}/checker-runs",
            manager_token,
            {"trigger_reason": "Week 2 stale revision retry"},
            409,
        )
        checker_revision_v2_finalized = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{checker_revision_v2_submission['id']}",
            manager_token,
        )
        assert_finalized_submission_versions(checker_revision_v2_finalized)
        checker_revision_v2_run = await wait_for_submission_checker_run(
            client,
            manager_token,
            checker_revision_v2_submission["id"],
        )
        assert_default_checker_set(checker_revision_v2_run)
        ensure(
            checker_revision_v2_run["routing_recommendation"] == "allow_review",
            "fixed revision did not reach review",
        )
        ensure(
            checker_revision_v2_run["outcome_source"] == "none",
            "fixed revision outcome source drifted",
        )
        await assert_task_status(
            client,
            manager_token,
            checker_revision_task["id"],
            "review_pending",
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
            manager_subject,
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
                "hash": sha256_token(f"forbidden:{run_id}"),
                "size_bytes": 64,
                "notes": "must be blocked",
            }
        )
        forbidden_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{forbidden_task['id']}/submission-precheck",
            forbidden_worker_token,
            {"submission": forbidden_payload},
        )
        assert_pre_submit_checker_set(forbidden_precheck)
        ensure(
            forbidden_precheck["eligible_to_submit"] is False,
            "forbidden path precheck should block submission",
        )
        ensure(
            next(
                result
                for result in forbidden_precheck["results"]
                if result["checker_name"] == "check_forbidden_files"
            )["status"]
            == "failed",
            "forbidden path precheck did not fail forbidden-file checker",
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{forbidden_task['id']}/submissions",
            forbidden_worker_token,
            forbidden_payload,
            422,
        )

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
            manager_subject,
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
        await break_acceptance_criteria(setup_task["id"])
        setup_submission = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{setup_task['id']}/submissions",
            setup_worker_token,
            submission_payload(run_id, "setup"),
            201,
        )
        setup_finalized = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{setup_submission['id']}",
            manager_token,
        )
        assert_finalized_submission_versions(setup_finalized)
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
        await assert_task_status(client, manager_token, setup_task["id"], "evaluation_pending")
        worker_setup_run = await request_json(
            client,
            "GET",
            f"/api/v1/checker-runs/{setup_run['id']}",
            setup_worker_token,
        )
        ensure(
            "routing_recommendation" not in worker_setup_run,
            "worker saw internal setup route",
        )
        ensure("outcome_source" not in worker_setup_run, "worker saw internal setup outcome")
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
            setup_runs_by_attempt[1]["trigger_source"] == "submission_finalized",
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
                "finalized_at": clean_finalized["finalized_at"],
                "expected_route": "allow_review",
                "expected_final_task_status": "review_pending",
                "expected_trigger_source": "submission_finalized",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": clean_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_passed",
                "expected_task_transitions": [
                    ("submitted", "evaluation_pending"),
                    ("evaluation_pending", "review_pending"),
                ],
            },
            {
                "name": "warning",
                "task_id": warning_task["id"],
                "submission_id": warning_submission["id"],
                "checker_run_id": warning_run["id"],
                "finalized_at": warning_finalized["finalized_at"],
                "expected_route": "allow_review",
                "expected_final_task_status": "review_pending",
                "expected_trigger_source": "submission_finalized",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": warning_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_passed",
                "expected_task_transitions": [
                    ("submitted", "evaluation_pending"),
                    ("evaluation_pending", "review_pending"),
                ],
            },
            {
                "name": "trusted_retry",
                "task_id": trusted_retry_task["id"],
                "submission_id": trusted_retry_submission["id"],
                "checker_run_id": trusted_retry_run["id"],
                "finalized_at": trusted_retry_finalized["finalized_at"],
                "expected_route": "allow_review",
                "expected_final_task_status": "review_pending",
                "expected_trigger_source": "manual_checker_trigger",
                "expected_attempt": 2,
                "expected_attempts": [1, 2],
                "expected_current": True,
                "expected_current_run_id": trusted_retry_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_passed",
                "expected_task_transitions": [
                    ("submitted", "evaluation_pending"),
                    ("evaluation_pending", "review_pending"),
                    ("review_pending", "evaluation_pending"),
                ],
            },
            {
                "name": "checker_caused_revision",
                "task_id": checker_revision_task["id"],
                "submission_id": checker_revision_v1_submission["id"],
                "checker_run_id": checker_revision_v1_run["id"],
                "finalized_at": checker_revision_v1_finalized["finalized_at"],
                "expected_route": "needs_revision",
                "expected_final_task_status": "review_pending",
                "expected_trigger_source": "submission_finalized",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": checker_revision_v1_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_needs_revision",
                "expected_task_transitions": [
                    ("submitted", "evaluation_pending"),
                    ("evaluation_pending", "needs_revision"),
                ],
            },
            {
                "name": "fixed_resubmission",
                "task_id": checker_revision_task["id"],
                "submission_id": checker_revision_v2_submission["id"],
                "checker_run_id": checker_revision_v2_run["id"],
                "finalized_at": checker_revision_v2_finalized["finalized_at"],
                "expected_route": "allow_review",
                "expected_final_task_status": "review_pending",
                "expected_trigger_source": "submission_finalized",
                "expected_attempt": 1,
                "expected_attempts": [1],
                "expected_current": True,
                "expected_current_run_id": checker_revision_v2_run["id"],
                "expected_checkers": EXPECTED_DURABLE_CHECKERS,
                "expected_gate_event": "pre_review_gate_passed",
                "expected_task_transitions": [
                    ("needs_revision", "submitted"),
                    ("submitted", "evaluation_pending"),
                    ("evaluation_pending", "review_pending"),
                ],
            },
            {
                "name": "setup_blocked",
                "task_id": setup_task["id"],
                "submission_id": setup_submission["id"],
                "checker_run_id": setup_run["id"],
                "finalized_at": setup_finalized["finalized_at"],
                "expected_route": "task_setup_blocked",
                "expected_final_task_status": "review_pending",
                "expected_trigger_source": "submission_finalized",
                "expected_attempt": 1,
                "expected_attempts": [1, 2],
                "expected_current": False,
                "expected_current_run_id": retry["id"],
                "expected_checkers": setup_checker_set,
                "expected_gate_event": "pre_review_gate_blocked",
                "expected_task_transitions": [
                    ("submitted", "evaluation_pending"),
                    ("evaluation_pending", "review_pending"),
                ],
            },
            {
                "name": "setup_retry",
                "task_id": setup_task["id"],
                "submission_id": setup_submission["id"],
                "checker_run_id": retry["id"],
                "finalized_at": setup_finalized["finalized_at"],
                "expected_route": "allow_review",
                "expected_final_task_status": "review_pending",
                "expected_trigger_source": "manual_checker_trigger",
                "expected_attempt": 2,
                "expected_attempts": [1, 2],
                "expected_current": True,
                "expected_current_run_id": retry["id"],
                "expected_checkers": setup_checker_set,
                "expected_gate_event": "pre_review_gate_passed",
                "expected_task_transitions": [
                    ("submitted", "evaluation_pending"),
                    ("evaluation_pending", "review_pending"),
                ],
            },
        ]
    )

    print("Week 2 real API e2e passed")
    print("scenario_summary:")
    print("clean=review_pending")
    print("missing_file=pre_submit_blocked")
    print("missing_evidence=pre_submit_blocked")
    print("duplicate_artifact_integrity=pre_submit_blocked")
    print("weak_attestation=pre_submit_blocked")
    print("generated_output_warning=review_pending")
    print("trusted_retry=review_pending->evaluation_pending->review_pending")
    print("checker_caused_revision=needs_revision")
    print("fixed_resubmission=review_pending")
    print("forbidden_path=pre_submit_blocked")
    print("task_setup_blocked=evaluation_pending->review_pending")
    print(f"clean_task_id={clean_task['id']}")
    print(f"clean_submission_id={clean_submission['id']}")
    print(f"missing_file_task_id={revision_task['id']}")
    print(f"missing_evidence_task_id={missing_evidence_task['id']}")
    print(f"integrity_task_id={integrity_task['id']}")
    print(f"attestation_task_id={attestation_task['id']}")
    print(f"warning_task_id={warning_task['id']}")
    print(f"trusted_retry_task_id={trusted_retry_task['id']}")
    print(f"trusted_retry_submission_id={trusted_retry_submission['id']}")
    print(f"checker_revision_task_id={checker_revision_task['id']}")
    print(f"checker_revision_v1_submission_id={checker_revision_v1_submission['id']}")
    print(f"checker_revision_v2_submission_id={checker_revision_v2_submission['id']}")
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
    process, log_path = start_backend_api_server(port, env)
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
