"""Run a real HTTP Week 1 API flow against Postgres and local Flow tokens."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.db import session as db_session
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.projects.models import (
    CheckerPolicy,
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSufficiencyReport,
    PaymentPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.tasks.models import (
    AuditEvent,
    EvidenceItem,
    Submission,
    TaskAssignment,
    WorkstreamTask,
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
DEFAULT_FLOW_ISSUER = "https://auth.flow.local/e2e"
DEFAULT_FLOW_AUDIENCE = "workstream-api"
LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_DATABASE_NAMES = {"workstream_test", "test_workstream"}
ASYNC_POSTGRES_SCHEMES = {"postgresql+asyncpg"}
NONLOCAL_DATABASE_OVERRIDE_VALUE = "I_UNDERSTAND_THIS_WRITES_DATA"
STRONG_ATTESTATION = (
    "I attest this submission contains no confidential client data, credentials, "
    "secrets, tokens, passwords, API keys, private source material, source code, "
    "copied platform artifacts, or copied platform content."
)


def base64url_json(payload: dict) -> str:
    """Encode a JSON payload as an unpadded base64url segment.

    Args:
        payload: JSON-serializable payload.

    Returns:
        Encoded JWT segment.
    """
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def base64url_bytes(payload: bytes) -> str:
    """Encode bytes as an unpadded base64url segment.

    Args:
        payload: Raw bytes to encode.

    Returns:
        Encoded JWT segment.
    """
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def flow_settings(env: dict[str, str]) -> tuple[str, str, str]:
    """Resolve local Flow settings from the runtime environment.

    Args:
        env: Runtime environment used by the API server and client.

    Returns:
        Issuer, audience, and HMAC secret used for local Flow tokens.
    """
    return (
        env.get("WORKSTREAM_E2E_FLOW_ISSUER", DEFAULT_FLOW_ISSUER),
        env.get("WORKSTREAM_E2E_FLOW_AUDIENCE", DEFAULT_FLOW_AUDIENCE),
        env.get("WORKSTREAM_E2E_FLOW_SECRET", f"local-flow-e2e-{uuid4().hex}"),
    )


def issue_flow_token(
    subject: str,
    roles: list[str],
    *,
    issuer: str,
    audience: str,
    secret: str,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    not_before: datetime | None = None,
) -> str:
    """Issue a local Flow-compatible signed token for one QA actor.

    Args:
        subject: External Flow subject.
        roles: Workstream roles granted by Flow for this actor.
        issuer: Flow issuer claim.
        audience: Flow audience claim.
        secret: HMAC secret shared with the local Flow verifier.
        issued_at: Optional issued-at timestamp override.
        expires_at: Optional expiration timestamp override.
        not_before: Optional not-before timestamp override.

    Returns:
        HMAC-signed bearer token consumed by ``FlowAuthVerifier``.
    """
    now = issued_at or datetime.now(UTC)
    header = base64url_json({"alg": "HS256", "typ": "JWT"})
    payload = base64url_json(
        {
            "iss": issuer,
            "aud": audience,
            "sub": subject,
            "email": f"{subject}@flow.local",
            "name": subject.replace("-", " ").title(),
            "roles": roles,
            "iat": int(now.timestamp()),
            "nbf": int((not_before or (now - timedelta(seconds=5))).timestamp()),
            "exp": int((expires_at or (now + timedelta(minutes=30))).timestamp()),
        }
    )
    signed_content = f"{header}.{payload}".encode()
    signature = hmac.new(secret.encode(), signed_content, hashlib.sha256).digest()
    return f"{header}.{payload}.{base64url_bytes(signature)}"


def auth_headers(token: str) -> dict[str, str]:
    """Build a bearer authorization header.

    Args:
        token: Flow bearer token.

    Returns:
        HTTP authorization header.
    """
    return {"Authorization": f"Bearer {token}"}


def project_root() -> Path:
    """Return the backend project root.

    Returns:
        Absolute backend project path.
    """
    return Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    """Create Alembic configuration for the backend project.

    Returns:
        Alembic configuration pointing at the local backend migration folder.
    """
    root = project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


def find_free_port() -> int:
    """Find an available localhost TCP port.

    Returns:
        Available port number.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def api_environment() -> dict[str, str]:
    """Build environment variables for the real API server.

    Returns:
        Environment configured for local Flow auth and Postgres.
    """
    env = os.environ.copy()
    env.setdefault(
        "WORKSTREAM_DATABASE_URL",
        "postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test",
    )
    flow_issuer, flow_audience, flow_secret = flow_settings(env)
    env["WORKSTREAM_E2E_FLOW_SECRET"] = flow_secret
    env["WORKSTREAM_AUTH_PROVIDER"] = "flow"
    env["WORKSTREAM_ENVIRONMENT"] = "local"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = flow_issuer
    env["WORKSTREAM_FLOW_AUTH_AUDIENCE"] = flow_audience
    env["WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET"] = flow_secret
    env["WORKSTREAM_ENABLE_DEMO_ROUTES"] = "true"
    env["PYTHONPATH"] = str(project_root())
    return env


def start_api_server(port: int, env: dict[str, str]) -> tuple[subprocess.Popen, Path]:
    """Start a real uvicorn server process.

    Args:
        port: Localhost port for the server.
        env: Environment variables for the server process.

    Returns:
        Server process and log path.
    """
    log_path = project_root() / ".week1_api_e2e_server.log"
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


async def wait_for_health(base_url: str, process: subprocess.Popen, log_path: Path) -> None:
    """Wait until the real API server responds to health checks.

    Args:
        base_url: API server base URL.
        process: Uvicorn subprocess.
        log_path: Server log path used for diagnostics.

    Raises:
        RuntimeError: If the server exits or does not become healthy.
    """
    deadline = time.monotonic() + 20
    async with httpx.AsyncClient(base_url=base_url, timeout=5) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"API server exited early:\n{log_path.read_text()}")
            try:
                response = await client.get("/api/v1/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise RuntimeError(f"API server did not become healthy:\n{log_path.read_text()}")


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    token: str | None = None,
    payload: dict | None = None,
    expected_status: int = 200,
) -> dict | list:
    """Call one API endpoint and assert its status.

    Args:
        client: Real HTTP client.
        method: HTTP method.
        path: API path.
        token: Optional Flow bearer token.
        payload: Optional JSON payload.
        expected_status: Expected HTTP status code.

    Returns:
        Parsed JSON response body.

    Raises:
        AssertionError: If the response status does not match.
    """
    response = await client.request(
        method,
        path,
        headers={} if token is None else auth_headers(token),
        json=payload,
    )
    if response.status_code != expected_status:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise AssertionError(
            f"{method} {path} expected {expected_status}, got {response.status_code}: {body}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AssertionError(
            f"{method} {path} returned non-JSON response: {response.text!r}"
        ) from exc
    if not isinstance(body, dict | list):
        raise AssertionError(f"{method} {path} returned non-JSON payload: {body!r}")
    print(f"PASS {method} {path} -> {response.status_code}")
    return body


async def wait_for_submission_checker_run(
    client: httpx.AsyncClient,
    manager_token: str,
    submission_id: str,
) -> dict:
    """Wait for exactly one automatic checker run after submission lock.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        submission_id: Locked submission id.

    Returns:
        Completed checker run response.
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
            run = await request_json(
                client,
                "GET",
                f"/api/v1/checker-runs/{runs[0]['id']}",
                manager_token,
            )
            if run["status"] == "completed":
                return run
        await asyncio.sleep(0.2)
    raise AssertionError(f"expected one automatic checker run, got {last_count}")


async def wait_for_task_status(
    client: httpx.AsyncClient,
    manager_token: str,
    task_id: str,
    expected_status: str,
) -> dict:
    """Wait for a task to reach an expected status through the API.

    Args:
        client: Real HTTP client.
        manager_token: Project manager Flow token.
        task_id: Task id to poll.
        expected_status: Expected status token.

    Returns:
        Task response at the expected status.
    """
    task: dict | None = None
    for _ in range(50):
        task = await request_json(client, "GET", f"/api/v1/tasks/{task_id}", manager_token)
        if task["status"] == expected_status:
            return task
        await asyncio.sleep(0.2)
    raise AssertionError(
        f"expected task status {expected_status}, got {task['status'] if task else None}"
    )


def ensure(condition: bool, message: str) -> None:
    """Raise a normal assertion error when a system invariant is false.

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
        "Refusing to run Week 1 API E2E against a non-local database. "
        "Use an async Postgres URL such as postgresql+asyncpg:// on "
        "localhost/127.0.0.1 with a local test database named "
        "workstream_test or test_workstream, or set "
        f"WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE={NONLOCAL_DATABASE_OVERRIDE_VALUE}."
    )


def guide_payload(run_id: str) -> dict:
    """Build a complete project guide payload.

    Args:
        run_id: Unique QA run id.

    Returns:
        Project guide payload.
    """
    return {
        "version": "v1",
        "content_markdown": f"# Real API Guide {run_id}",
        "required_task_fields": [
            "title",
            "description",
            "acceptance_criteria",
            "required_evidence",
        ],
        "required_submission_fields": ["summary", "evidence", "worker_attestation"],
        "task_instructions": "Complete the real API task.",
        "output_requirements": "Submit artifact manifest and evidence.",
        "acceptance_criteria": "Submission packet is complete.",
        "rejection_criteria": "Evidence is missing.",
        "reviewer_rubric": "Review packet completeness.",
        "forbidden_actions": "No credentials or private source data.",
        "required_skills": ["stem"],
        "difficulty_scale": {"medium": 2},
        "estimated_time_policy": {"default_minutes": 45},
        "common_rejection_reasons": ["missing evidence"],
        "evidence_policy": {"required": ["log"]},
        "unacceptable_work_policy": "Copied or unverifiable work.",
        "change_summary": "Initial real API guide",
        "checker_policy": {
            "required_checkers": ["check_policy_context_present"],
            "warning_checkers": [],
            "blocking_severities": ["high"],
        },
        "review_policy": {
            "requires_second_review": False,
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": ["issue", "required_fix"],
            "sla_hours": 24,
        },
        "revision_policy": {
            "max_revision_rounds": 7,
            "revision_deadline_hours": 48,
            "auto_reject_after_limit": True,
            "allowed_resubmission_states": ["needs_revision"],
            "reviewer_reassignment_rule": "same reviewer preferred",
        },
        "payment_policy": {
            "base_amount": "25.00",
            "currency": "USD",
            "payout_type": "fixed",
            "revision_payment_rule": "none",
            "rejection_payment_rule": "none",
            "accepted_payment_rule": "pay base amount",
        },
    }


def sha256_token(seed: str) -> str:
    """Return a platform-shaped sha256 token for deterministic E2E fixtures.

    Args:
        seed: Stable seed material.

    Returns:
        Hash token shaped as ``sha256:<64 lowercase hex>``.
    """
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


async def load_pre_submit_checker_policy(effective_policy: dict) -> dict:
    """Load the project pre-submit checker policy compiled during approval."""
    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy["id"]
            )
        )
        ensure(pre_submit_checker_policy is not None, "pre-submit checker policy missing")
        ensure(
            pre_submit_checker_policy.lifecycle_status == "compiled",
            "pre-submit checker policy was not compiled during approval",
        )
        return {
            "compiled_bundle": pre_submit_checker_policy.compiled_bundle,
            "compiled_bundle_hash": pre_submit_checker_policy.compiled_bundle_hash,
        }


def submission_artifact_policy_body() -> dict:
    """Build the project submission artifact policy used by the Week 1 drill.

    Returns:
        Machine-readable artifact policy payload.
    """
    return {
        "required_artifacts": [
            {
                "key": "answer",
                "path": "answer.md",
                "hash_required": True,
                "required": True,
                "description": "Main answer artifact.",
            }
        ],
        "required_evidence": [
            {
                "key": "checker_log",
                "label": "checker log",
                "hash_required": True,
                "required": True,
                "description": "Evidence item used by the reviewer.",
            }
        ],
        "forbidden_artifacts": [],
        "attestation_terms": ["real_api_originality"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": False},
    }


async def create_policy_bundle_for_guide(
    client: httpx.AsyncClient,
    manager_token: str,
    project_id: str,
    guide_id: str,
    run_id: str,
) -> dict:
    """Create the guide-source, sufficiency, and approved policy bundle.

    Args:
        client: HTTP client pointed at the running API.
        manager_token: Flow token with project manager role.
        project_id: Project id that owns the guide.
        guide_id: Guide id to bind.
        run_id: Unique run id used for deterministic source hashes.

    Returns:
        Effective project submission artifact policy response.
    """
    snapshot = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots",
        manager_token,
        {
            "items": [
                {
                    "source_kind": "inline_markdown",
                    "durable_ref": f"inline:/week1/{run_id}/guide",
                    "ingestion_adapter": "manual_import",
                    "content_hash": sha256_token(f"{run_id}:guide"),
                    "media_type": "text/markdown",
                }
            ]
        },
        201,
    )
    await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        manager_token,
        {
            "source_snapshot_id": snapshot["id"],
            "status": "passed",
            "findings": [],
            "summary": "Guide is sufficient for the Week 1 real API drill.",
        },
        201,
    )
    policy = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        manager_token,
        {
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": submission_artifact_policy_body(),
        },
        201,
    )
    effective_policy = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/"
        f"{policy['id']}/approve",
        manager_token,
        {"approval_note": "Approved for Week 1 real API drill."},
    )
    await load_pre_submit_checker_policy(effective_policy)
    return effective_policy


async def exercise_week1_api(base_url: str, env: dict[str, str]) -> None:
    """Run the real Project -> Task -> Submission Week 1 API flow.

    Args:
        base_url: Real API server base URL.
        env: Runtime environment shared by the API server and token issuer.
    """
    flow_issuer, flow_audience, flow_secret = flow_settings(env)
    run_id = uuid4().hex[:8]
    manager_token = issue_flow_token(
        f"real-api-project-manager-{run_id}",
        ["project_manager"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    worker_subject = f"real-api-worker-{run_id}"
    worker_token = issue_flow_token(
        worker_subject,
        ["worker"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    unassigned_worker_token = issue_flow_token(
        f"real-api-unassigned-worker-{run_id}",
        ["worker"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    reviewer_token = issue_flow_token(
        f"real-api-reviewer-{run_id}",
        ["reviewer"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    invalid_token = (
        issue_flow_token(
            f"real-api-invalid-{run_id}",
            ["worker"],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
        )[:-8]
        + "tampered"
    )
    wrong_issuer_token = issue_flow_token(
        f"real-api-wrong-issuer-{run_id}",
        ["worker"],
        issuer="https://auth.flow.local/wrong",
        audience=flow_audience,
        secret=flow_secret,
    )
    wrong_audience_token = issue_flow_token(
        f"real-api-wrong-audience-{run_id}",
        ["worker"],
        issuer=flow_issuer,
        audience="wrong-audience",
        secret=flow_secret,
    )
    expired_token = issue_flow_token(
        f"real-api-expired-{run_id}",
        ["worker"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
        issued_at=datetime.now(UTC) - timedelta(hours=1),
        expires_at=datetime.now(UTC) - timedelta(minutes=30),
    )
    future_nbf_token = issue_flow_token(
        f"real-api-future-nbf-{run_id}",
        ["worker"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
        not_before=datetime.now(UTC) + timedelta(minutes=30),
    )

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        await request_json(client, "GET", "/health")
        await request_json(client, "GET", "/api/v1/health")
        await request_json(client, "GET", "/api/v1/auth/me", expected_status=401)
        await request_json(client, "GET", "/api/v1/auth/me", invalid_token, expected_status=401)
        await request_json(client, "GET", "/api/v1/auth/me", wrong_issuer_token, expected_status=401)
        await request_json(client, "GET", "/api/v1/auth/me", wrong_audience_token, expected_status=401)
        await request_json(client, "GET", "/api/v1/auth/me", expired_token, expected_status=401)
        await request_json(client, "GET", "/api/v1/auth/me", future_nbf_token, expected_status=401)
        manager = await request_json(client, "GET", "/api/v1/auth/me", manager_token)
        assert manager["auth_source"] == "flow"
        assert manager["is_dev_auth"] is False
        assert manager["roles"] == ["project_manager"]

        project = await request_json(
            client,
            "POST",
            "/api/v1/projects",
            manager_token,
            {
                "name": f"Week 1 Real API {run_id}",
                "slug": f"week1-real-api-{run_id}",
                "description": "Real Week 1 API lifecycle QA",
                "base_amount": "25.00",
                "currency": "USD",
            },
            201,
        )
        await request_json(client, "GET", f"/api/v1/projects/{project['id']}", manager_token)

        guide = await request_json(
            client,
            "POST",
            f"/api/v1/projects/{project['id']}/guides",
            manager_token,
            guide_payload(run_id),
            201,
        )
        patched_guide = await request_json(
            client,
            "PATCH",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
            manager_token,
            {"change_summary": "Patched before activation through real API"},
        )
        assert patched_guide["change_summary"] == "Patched before activation through real API"
        await create_policy_bundle_for_guide(
            client,
            manager_token,
            project["id"],
            guide["id"],
            run_id,
        )
        active = await request_json(
            client,
            "POST",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
            manager_token,
        )
        assert active["guide"]["version"] == "v1"
        await request_json(
            client,
            "PATCH",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
            manager_token,
            {"change_summary": "Illegal active guide edit"},
            409,
        )
        await request_json(client, "GET", f"/api/v1/projects/{project['id']}/active-guide", manager_token)
        await request_json(
            client,
            "POST",
            f"/api/v1/projects/{project['id']}/tasks",
            worker_token,
            {
                "title": "Worker must not create task",
                "description": "Unauthorized task create probe.",
                "source_type": "manual",
                "acceptance_criteria": "Must fail.",
                "required_evidence": ["log"],
            },
            403,
        )

        task = await request_json(
            client,
            "POST",
            f"/api/v1/projects/{project['id']}/tasks",
            manager_token,
            {
                "title": "Real API task",
                "description": "Exercise the full Week 1 API lifecycle over HTTP.",
                "task_type": "evaluation",
                "difficulty": "medium",
                "skill_tags": ["stem", "proofs"],
                "estimated_time_minutes": 45,
                "source_type": "manual",
                "source_ref": f"real-api-{run_id}",
                "source_payload_hash": f"sha256:source-{run_id}",
                "acceptance_criteria": "Submission packet is complete.",
                "rejection_criteria": "Evidence is missing.",
                "required_files": ["answer.md"],
                "required_evidence": ["checker log"],
            },
            201,
        )
        await request_json(client, "GET", f"/api/v1/tasks/{task['id']}", manager_token)
        screened = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{task['id']}/screen",
            manager_token,
            {"reason": "real API screening passed"},
        )
        assert {
            screened["locked_guide_version"],
            screened["locked_checker_policy_version"],
            screened["locked_review_policy_version"],
            screened["locked_revision_policy_version"],
            screened["locked_payment_policy_version"],
        } == {"v1"}
        assert screened["base_amount"] == "25.00"
        assert screened["currency"] == "USD"
        assert screened["payout_type"] == "fixed"
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{task['id']}/release",
            manager_token,
            {"reason": "real API release"},
        )

        worker = await request_json(client, "GET", "/api/v1/auth/me", worker_token)
        assert worker["roles"] == ["worker"]
        worker_profile = await request_json(
            client,
            "POST",
            "/api/v1/demo/worker-profile",
            worker_token,
            {"skill_tags": ["stem", "proofs"]},
            201,
        )
        assert worker_profile["external_subject"] == worker_subject
        assert worker_profile["external_issuer"] == flow_issuer
        assert worker_profile["status"] == "active"
        assert set(worker_profile["skill_tags"]) == {"stem", "proofs"}
        await request_json(client, "GET", f"/api/v1/tasks/{task['id']}", worker_token)
        await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}",
            unassigned_worker_token,
            expected_status=200,
        )
        claim = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{task['id']}/claim",
            worker_token,
            {"reason": "real worker claim"},
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}",
            unassigned_worker_token,
            expected_status=404,
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{task['id']}/start",
            worker_token,
            {"reason": "real worker start"},
        )
        submission = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{task['id']}/submissions",
            worker_token,
            {
                "summary": "Real API packet completed.",
                "package_uri": f"local://packages/token=build-{run_id}.tar.zst",
                "package_hash": f"sha256:package-{run_id}",
                "artifact_hash_manifest": [
                    {
                        "artifact": "answer.md",
                        "hash": f"sha256:answer-{run_id}",
                        "size_bytes": 128,
                        "notes": "real API artifact",
                    }
                ],
                "worker_attestation": STRONG_ATTESTATION,
                "evidence_items": [
                    {
                        "type": "log",
                        "label": "real API evidence",
                        "uri": f"s3://workstream-e2e/reports/user@team-{run_id}.log",
                        "hash": f"sha256:evidence-{run_id}",
                        "size_bytes": 256,
                        "metadata": {"command": "week1_api_e2e"},
                    }
                ],
            },
            201,
        )
        assert {
            submission["locked_guide_version"],
            submission["locked_checker_policy_version"],
            submission["locked_review_policy_version"],
            submission["locked_revision_policy_version"],
            submission["locked_payment_policy_version"],
        } == {"v1"}
        await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{task['id']}/submissions",
            manager_token,
            {
                "summary": "Manager cannot submit for worker.",
                "package_hash": f"sha256:manager-package-{run_id}",
                "artifact_hash_manifest": [
                    {"artifact": "answer.md", "hash": f"sha256:manager-answer-{run_id}"}
                ],
                "worker_attestation": STRONG_ATTESTATION,
                "evidence_items": [],
            },
            403,
        )
        await request_json(client, "GET", f"/api/v1/tasks/{task['id']}/submissions", worker_token)
        await request_json(client, "GET", f"/api/v1/submissions/{submission['id']}", worker_token)
        await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{submission['id']}",
            unassigned_worker_token,
            expected_status=404,
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/submissions/{submission['id']}/lock",
            worker_token,
            expected_status=403,
        )
        locked = await request_json(
            client,
            "POST",
            f"/api/v1/submissions/{submission['id']}/lock",
            manager_token,
        )
        assert locked["locked_at"] is not None
        assert all(item["locked_at"] == locked["locked_at"] for item in locked["evidence_items"])
        checker_run = await wait_for_submission_checker_run(client, manager_token, submission["id"])
        assert checker_run["routing_recommendation"] == "allow_review"
        assert {result["checker_name"] for result in checker_run["results"]} == EXPECTED_DURABLE_CHECKERS
        await wait_for_task_status(client, manager_token, task["id"], "review_pending")
        audit_events = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/audit-events",
            manager_token,
        )
        audit_transitions = {
            (event["event_type"], event["from_status"], event["to_status"])
            for event in audit_events
        }
        for expected_transition in {
            ("task_created", None, "draft"),
            ("task_status_changed", "draft", "screening"),
            ("task_status_changed", "screening", "ready"),
            ("task_status_changed", "ready", "claimed"),
            ("task_status_changed", "claimed", "in_progress"),
            ("submission_created", "in_progress", "submitted"),
            ("submission_locked", "submitted", "submitted"),
            ("pre_review_gate_started", "submitted", "auto_checking"),
            ("pre_review_gate_passed", "auto_checking", "review_pending"),
        }:
            assert expected_transition in audit_transitions
        worker_audit_events = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/audit-events",
            worker_token,
        )
        assert all(event["claim_snapshot"] == {} for event in worker_audit_events)
        assert all(
            "artifact_hash_manifest" not in event["event_payload"]
            for event in worker_audit_events
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}",
            reviewer_token,
            expected_status=403,
        )

    await assert_week1_database_invariants(
        project_id=project["id"],
        guide_id=guide["id"],
        task_id=task["id"],
        assignment_id=claim["assignment"]["id"],
        submission_id=submission["id"],
        worker_subject=worker_subject,
        flow_issuer=flow_issuer,
    )

    print("Week 1 real API e2e passed")
    print(f"project_id={project['id']}")
    print(f"guide_id={guide['id']}")
    print(f"task_id={task['id']}")
    print(f"assignment_id={claim['assignment']['id']}")
    print(f"submission_id={submission['id']}")
    print(f"submission_locked_at={locked['locked_at']}")


async def assert_week1_database_invariants(
    *,
    project_id: str,
    guide_id: str,
    task_id: str,
    assignment_id: str,
    submission_id: str,
    worker_subject: str,
    flow_issuer: str,
) -> None:
    """Verify Week 1 API calls produced the expected durable database state.

    Args:
        project_id: Created project id.
        guide_id: Activated guide id.
        task_id: Created task id.
        assignment_id: Active assignment id.
        submission_id: Locked submission id.
        worker_subject: External Flow subject for the worker.
        flow_issuer: External Flow issuer for the local token.
    """
    async with db_session.get_session_factory()() as session:
        project = await session.get(Project, project_id)
        guide = await session.get(ProjectGuide, guide_id)
        task = await session.get(WorkstreamTask, task_id)
        assignment = await session.get(TaskAssignment, assignment_id)
        submission = await session.get(Submission, submission_id)

        ensure(project is not None, "project was not persisted")
        ensure(guide is not None, "guide was not persisted")
        ensure(task is not None, "task was not persisted")
        ensure(assignment is not None, "assignment was not persisted")
        ensure(submission is not None, "submission was not persisted")

        ensure(project.status == "active", f"project status drifted: {project.status}")
        ensure(guide.status == "active", f"guide status drifted: {guide.status}")
        ensure(guide.version == "v1", f"guide version drifted: {guide.version}")
        ensure(guide.approved_by is not None, "active guide missing approver")
        ensure(guide.effective_at is not None, "active guide missing effective_at")

        for model, label in [
            (CheckerPolicy, "checker policy"),
            (ReviewPolicy, "review policy"),
            (RevisionPolicy, "revision policy"),
            (PaymentPolicy, "payment policy"),
        ]:
            policy = await session.scalar(
                select(model).where(model.project_id == project_id, model.guide_version == "v1")
            )
            ensure(policy is not None, f"{label} missing for active guide")

        snapshot = await session.scalar(
            select(GuideSourceSnapshot).where(
                GuideSourceSnapshot.project_id == project_id,
                GuideSourceSnapshot.guide_id == guide_id,
                GuideSourceSnapshot.guide_version == "v1",
            )
        )
        ensure(snapshot is not None, "guide source snapshot missing for active guide")
        sufficiency_report = await session.scalar(
            select(GuideSufficiencyReport).where(
                GuideSufficiencyReport.project_id == project_id,
                GuideSufficiencyReport.guide_id == guide_id,
                GuideSufficiencyReport.source_snapshot_id == snapshot.id,
            )
        )
        ensure(sufficiency_report is not None, "sufficiency report missing for active guide")
        ensure(sufficiency_report.status == "passed", "sufficiency report did not pass")
        submission_policy = await session.scalar(
            select(SubmissionArtifactPolicy).where(
                SubmissionArtifactPolicy.project_id == project_id,
                SubmissionArtifactPolicy.guide_id == guide_id,
                SubmissionArtifactPolicy.source_snapshot_id == snapshot.id,
                SubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        ensure(submission_policy is not None, "approved submission artifact policy missing")
        effective_policy = await session.scalar(
            select(EffectiveProjectSubmissionArtifactPolicy).where(
                EffectiveProjectSubmissionArtifactPolicy.project_id == project_id,
                EffectiveProjectSubmissionArtifactPolicy.guide_id == guide_id,
                EffectiveProjectSubmissionArtifactPolicy.source_snapshot_id == snapshot.id,
                EffectiveProjectSubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        ensure(effective_policy is not None, "effective project submission artifact policy missing")
        ensure(
            effective_policy.submission_artifact_policy_id == submission_policy.id,
            "effective policy is not bound to the approved submission artifact policy",
        )
        ensure(
            effective_policy.source_snapshot_hash == snapshot.bundle_hash,
            "effective policy source snapshot hash drifted",
        )
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy.id,
                PreSubmitCheckerPolicy.lifecycle_status == "compiled",
            )
        )
        ensure(pre_submit_checker_policy is not None, "pre-submit checker policy missing")
        ensure(
            pre_submit_checker_policy.effective_policy_hash
            == effective_policy.effective_policy_hash,
            "pre-submit checker policy effective hash drifted",
        )
        ensure(
            pre_submit_checker_policy.compiled_bundle_hash is not None,
            "pre-submit checker compiled bundle hash missing",
        )

        locked_versions = {
            task.locked_guide_version,
            task.locked_checker_policy_version,
            task.locked_review_policy_version,
            task.locked_revision_policy_version,
            task.locked_payment_policy_version,
        }
        ensure(locked_versions == {"v1"}, f"task locked versions drifted: {locked_versions}")
        ensure(task.status == "review_pending", f"task status drifted: {task.status}")
        ensure(task.assigned_to == assignment.worker_id, "task assignment pointer drifted")
        ensure(assignment.status == "active", f"assignment status drifted: {assignment.status}")
        ensure(assignment.accepted_at is not None, "assignment missing accepted_at")

        ensure(submission.version == 1, f"submission version drifted: {submission.version}")
        ensure(submission.status == "submitted", f"submission status drifted: {submission.status}")
        ensure(submission.locked_at is not None, "submission was not locked")
        ensure(submission.worker_id == assignment.worker_id, "submission worker drifted")
        ensure(submission.supersedes_submission_id is None, "first submission supersedes another")
        submission_versions = {
            submission.locked_guide_version,
            submission.locked_checker_policy_version,
            submission.locked_review_policy_version,
            submission.locked_revision_policy_version,
            submission.locked_payment_policy_version,
        }
        ensure(submission_versions == {"v1"}, f"submission locked versions drifted: {submission_versions}")

        evidence_items = (
            await session.scalars(
                select(EvidenceItem).where(EvidenceItem.submission_id == submission_id)
            )
        ).all()
        ensure(len(evidence_items) == 1, f"expected 1 evidence item, got {len(evidence_items)}")
        ensure(evidence_items[0].locked_at is not None, "evidence item was not locked")

        checker_runs = (
            await session.scalars(
                select(CheckerRun).where(CheckerRun.submission_id == submission_id)
            )
        ).all()
        ensure(len(checker_runs) == 1, f"expected 1 checker run, got {len(checker_runs)}")
        checker_run = checker_runs[0]
        ensure(checker_run.trigger_source == "submission_locked", "checker trigger source drifted")
        ensure(checker_run.status == "completed", f"checker status drifted: {checker_run.status}")
        ensure(checker_run.routing_recommendation == "allow_review", "checker route drifted")
        ensure(checker_run.is_current_for_submission is True, "checker run is not current")
        ensure(checker_run.attempt_number == 1, "first checker attempt number drifted")
        ensure(checker_run.locked_guide_version == submission.locked_guide_version, "checker guide lock drifted")
        ensure(checker_run.package_hash == submission.package_hash, "checker package hash drifted")

        results = (
            await session.scalars(
                select(CheckerResult).where(CheckerResult.checker_run_id == checker_run.id)
            )
        ).all()
        result_names = [result.checker_name for result in results]
        duplicate_names = {
            checker_name for checker_name in result_names if result_names.count(checker_name) > 1
        }
        ensure(not duplicate_names, f"duplicate checker results persisted: {duplicate_names}")
        ensure(
            set(result_names) == EXPECTED_DURABLE_CHECKERS,
            f"checker result set drifted: {result_names}",
        )
        ensure(checker_run.passed_count == len(results), "checker passed count drifted")
        ensure(checker_run.warning_count == 0, "unexpected checker warnings")
        ensure(checker_run.failed_count == 0, "unexpected checker failures")
        ensure(checker_run.blocking_count == 0, "unexpected checker blockers")

        audit_events = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.entity_type == "task", AuditEvent.entity_id == task_id)
            )
        ).all()
        event_types = [event.event_type for event in audit_events]
        for required_event in [
            "task_created",
            "task_status_changed",
            "submission_created",
            "submission_locked",
            "pre_review_gate_started",
            "pre_review_gate_passed",
        ]:
            ensure(required_event in event_types, f"audit event missing: {required_event}")
        ensure(
            any(event.external_subject == worker_subject for event in audit_events),
            "worker subject missing from task audit trail",
        )
        ensure(
            all(event.external_issuer == flow_issuer for event in audit_events),
            "audit issuer drifted",
        )

    print("PASS Week 1 database invariants")


async def main(env: dict[str, str]) -> None:
    """Start the API server and exercise every Week 1 API.

    Args:
        env: Environment variables for the API server.
    """
    await db_session.dispose_engine()

    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    process, log_path = start_api_server(port, env)
    try:
        await wait_for_health(base_url, process, log_path)
        await exercise_week1_api(base_url, env)
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
