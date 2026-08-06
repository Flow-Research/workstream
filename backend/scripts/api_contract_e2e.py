"""Run a real HTTP backend API contract flow against Postgres and local Flow tokens."""

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
from uuid import UUID, uuid4

import httpx
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import select, text

from app.db import session as db_session
from app.core.config import get_settings
from app.modules.actors.models import ActorIdentityLink
from app.modules.api_controls.service import (
    FIRST_ACCESS_SCOPE,
    RateControlService,
    rate_key_digest,
)
from app.modules.projects.models import (
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    ProjectSetupRun,
)
from app.modules.projects.post_submit_policy import (
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
)
from app.modules.projects.service import ProjectService
from app.schemas.auth import ActorContext
from run_isolated_tests import NAME_RE as DERIVED_DATABASE_NAME
from bootstrap_access_administrator import _run as run_admin_bootstrap

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

GUIDE_ARTIFACT_PIPELINE_SERVICE_IDENTITIES = (
    "workstream.artifact.put_resolver",
    "workstream.artifact.verifier",
    "workstream.artifact.scheduler",
    "workstream.artifact.binding",
    "workstream.artifact.guide_reader",
    "workstream.project.setup",
)


async def seed_active_guide_for_pre_12h_e2e(
    project_id: str,
    guide_id: str,
    manager_subject: str,
    manager_issuer: str,
) -> dict:
    """Seed downstream active state while the public activation route is unavailable."""
    async with db_session.get_session_factory()() as session:
        database_name = await session.scalar(text("select current_database()"))
        if DERIVED_DATABASE_NAME.fullmatch(str(database_name)) is None:
            raise RuntimeError("pre-12H activation seed requires an isolated E2E database")
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == manager_issuer,
                ActorIdentityLink.subject == manager_subject,
            )
        )
        if link is None:
            raise RuntimeError("pre-12H activation seed requires an admitted actor")
        actor = ActorContext(
            actor_id=str(link.actor_profile_id),
            external_subject=link.subject,
            external_issuer=link.issuer,
            roles=("project_manager",),
            claim_snapshot={},
            auth_source="flow",
            is_dev_auth=False,
        )
        await session.execute(
            text("alter table project_guides disable trigger guide_mutation_product_custody")
        )
        await session.execute(
            text("alter table project_guides disable trigger guide_lineage_lifecycle_guard")
        )
        await session.commit()
        try:
            result = await ProjectService(session).activate_guide(actor, project_id, guide_id)
            return result.model_dump(mode="json")
        finally:
            await session.rollback()
            await session.execute(
                text("alter table project_guides enable trigger guide_lineage_lifecycle_guard")
            )
            await session.execute(
                text("alter table project_guides enable trigger guide_mutation_product_custody")
            )
            await session.commit()


DEFAULT_FLOW_ISSUER = "https://auth.flow.local/e2e"
DEFAULT_FLOW_AUDIENCE = "workstream-api"
LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_DATABASE_NAMES = {"workstream_test", "test_workstream"}
ASYNC_POSTGRES_SCHEMES = {"postgresql+asyncpg"}
NONLOCAL_DATABASE_OVERRIDE_VALUE = "I_UNDERSTAND_THIS_WRITES_DATA"
TEST_MINIO_ACCESS_KEY = "workstream-minio"
TEST_MINIO_SECRET_KEY = "workstream-minio-secret-key"
STRONG_ATTESTATION = (
    "I attest this submission contains no confidential client data, credentials, "
    "secrets, tokens, passwords, API keys, private source material, source code, "
    "copied platform artifacts, or copied platform content, and it satisfies "
    "the original_work, credentials_and_secret_exclusion, real_api_originality, and "
    "human_accountability_for_agent_assisted_work policy terms."
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
    subject_kind: str = "human",
) -> str:
    """Issue a local Flow-compatible signed token for one QA actor.

    Args:
        subject: External Flow subject.
        roles: Trusted v0.1 bootstrap role claims for this actor.
        issuer: Flow issuer claim.
        audience: Flow audience claim.
        secret: HMAC secret shared with the local Flow verifier.
        issued_at: Optional issued-at timestamp override.
        expires_at: Optional expiration timestamp override.
        not_before: Optional not-before timestamp override.
        subject_kind: Canonical human or fixed-service token kind.

    Returns:
        HMAC-signed bearer token consumed by ``FlowAuthVerifier``.
    """
    now = issued_at or datetime.now(UTC)
    header = base64url_json({"alg": "HS256", "typ": "JWT"})
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "jti": f"local-e2e-{uuid4()}",
        "subject_kind": subject_kind,
        "scope": "workstream:service" if subject_kind == "service" else "workstream:access",
        "iat": int(now.timestamp()),
        "nbf": int((not_before or (now - timedelta(seconds=5))).timestamp()),
        "exp": int((expires_at or (now + timedelta(minutes=30))).timestamp()),
    }
    if subject_kind == "human":
        claims.update(
            {
                "email": f"{subject}@flow.local",
                "name": subject.replace("-", " ").title(),
                "roles": roles,
            }
        )
    payload = base64url_json(claims)
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
    env["WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART"] = "true"
    env["WORKSTREAM_CELERY_TASK_ALWAYS_EAGER"] = "true"
    env["WORKSTREAM_CELERY_BROKER_URL"] = "memory://"
    env["WORKSTREAM_CELERY_RESULT_BACKEND_URL"] = "cache+memory://"
    minio_endpoint = env.get("WORKSTREAM_TEST_MINIO_ENDPOINT")
    minio_bucket = env.get("WORKSTREAM_TEST_MINIO_BUCKET")
    minio_prefix = env.get("WORKSTREAM_TEST_MINIO_PREFIX")
    if minio_endpoint and minio_bucket and minio_prefix:
        scratch_parent = Path(env.get("RUNNER_TEMP", "/tmp"))
        env.update(
            {
                "WORKSTREAM_ARTIFACT_STORE_BACKEND": "s3_compatible",
                "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(
                    scratch_parent / "workstream-api-contract-scratch"
                ),
                "WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE": "minio",
                "WORKSTREAM_ARTIFACT_S3_REGION": "us-east-1",
                "WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL": minio_endpoint,
                "WORKSTREAM_ARTIFACT_S3_BUCKET": minio_bucket,
                "WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX": minio_prefix,
                "WORKSTREAM_ARTIFACT_S3_ADDRESSING_STYLE": "path",
                "WORKSTREAM_ARTIFACT_S3_CREDENTIAL_MODE": "local_static",
                "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID": TEST_MINIO_ACCESS_KEY,
                "WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY": TEST_MINIO_SECRET_KEY,
                "WORKSTREAM_ARTIFACT_ADMISSION_TASK_MAXIMUM_BYTES": "67108864",
                "WORKSTREAM_ARTIFACT_ADMISSION_PRODUCER_MAXIMUM_BYTES": "67108864",
                "WORKSTREAM_ARTIFACT_ADMISSION_PROJECT_MAXIMUM_BYTES": "67108864",
                "WORKSTREAM_ARTIFACT_ADMISSION_DEPLOYMENT_MAXIMUM_BYTES": "67108864",
            }
        )
    env.setdefault(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        base64.b64encode(os.urandom(32)).decode("ascii"),
    )
    env.setdefault(
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET",
        base64.b64encode(os.urandom(32)).decode("ascii"),
    )
    env["PYTHONPATH"] = str(project_root())
    return env


async def exercise_rate_control_contract(env: dict[str, str]) -> None:
    """Prove one durable denial without exposing the pseudonymous key."""
    subject = f"api-contract-rate-{uuid4()}"
    secret = SecretStr(env["WORKSTREAM_API_RATE_LIMIT_KEY_SECRET"])
    service = RateControlService()
    first = await service.consume(
        control_scope=FIRST_ACCESS_SCOPE,
        issuer=DEFAULT_FLOW_ISSUER,
        subject=subject,
        limit=1,
        window_seconds=60,
        secret=secret,
    )
    denied = await service.consume(
        control_scope=FIRST_ACCESS_SCOPE,
        issuer=DEFAULT_FLOW_ISSUER,
        subject=subject,
        limit=1,
        window_seconds=60,
        secret=secret,
    )
    assert first.allowed is True and first.request_count == 1
    assert denied.allowed is False and denied.request_count == 2
    assert 1 <= denied.retry_after <= 60

    digest = rate_key_digest(secret, FIRST_ACCESS_SCOPE, DEFAULT_FLOW_ISSUER, subject)
    async with db_session.get_session_factory()() as session:
        row = (
            await session.execute(
                text(
                    "select control_scope, key_digest, request_count "
                    "from api_rate_control_counters "
                    "where control_scope = :scope and key_digest = :digest"
                ),
                {"scope": FIRST_ACCESS_SCOPE, "digest": digest},
            )
        ).one()
        assert tuple(row) == (FIRST_ACCESS_SCOPE, digest, 2)
        await session.execute(
            text(
                "delete from api_rate_control_counters "
                "where control_scope = :scope and key_digest = :digest"
            ),
            {"scope": FIRST_ACCESS_SCOPE, "digest": digest},
        )
        await session.commit()


def start_api_server(port: int, env: dict[str, str]) -> tuple[subprocess.Popen, Path]:
    """Start a real uvicorn server process.

    Args:
        port: Localhost port for the server.
        env: Environment variables for the server process.

    Returns:
        Server process and log path.
    """
    log_path = project_root() / ".api_contract_e2e_server.log"
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
    deadline = time.monotonic() + 60
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
    idempotency_key: str | None = None,
    if_match: str | None = None,
) -> dict | list:
    """Call one API endpoint and assert its status.

    Args:
        client: Real HTTP client.
        method: HTTP method.
        path: API path.
        token: Optional Flow bearer token.
        payload: Optional JSON payload.
        expected_status: Expected HTTP status code.
        idempotency_key: Optional UUID replay key for mutation boundaries.
        if_match: Optional exact HTTP policy selector precondition.

    Returns:
        Parsed JSON response body.

    Raises:
        AssertionError: If the response status does not match.
    """
    request_id = str(uuid4())
    correlation_id = str(uuid4())
    headers = {} if token is None else auth_headers(token)
    headers.update({"X-Request-ID": request_id, "X-Correlation-ID": correlation_id})
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    if if_match is not None:
        headers["If-Match"] = if_match
    response = await client.request(
        method,
        path,
        headers=headers,
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
    if response.headers.get("x-request-id") != request_id:
        raise AssertionError(f"{method} {path} did not preserve the request ID")
    if response.headers.get("x-correlation-id") != correlation_id:
        raise AssertionError(f"{method} {path} did not preserve the correlation ID")
    if expected_status >= 400:
        if (
            not isinstance(body, dict)
            or body.get("error", {}).get("correlation_id") != correlation_id
        ):
            raise AssertionError(f"{method} {path} returned invalid error context")
    print(f"PASS {method} {path} -> {response.status_code}")
    return body


async def provision_guide_artifact_pipeline_services(
    client: httpx.AsyncClient,
    manager_token: str,
    run_id: str,
) -> None:
    """Provision the exact fixed principals used by the real guide pipeline."""
    for service_identity in GUIDE_ARTIFACT_PIPELINE_SERVICE_IDENTITIES:
        response = await client.post(
            "/api/v1/service-actors",
            headers=auth_headers(manager_token)
            | {
                "Idempotency-Key": str(uuid4()),
                "X-Request-ID": str(uuid4()),
                "X-Correlation-ID": str(uuid4()),
            },
            json={
                "service_identity": service_identity,
                "subject": f"real-api-{service_identity.removeprefix('workstream.')}-{run_id}",
                "reason": "Real API guide artifact pipeline authority proof",
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["service_identity"] == service_identity
        assert body["actor_status"] == "active"


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
        if len(runs) == 1 and runs[0]["trigger_source"] == "submission_finalized":
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


def assert_checker_run_result_integrity(checker_run: dict, expected_names: set[str]) -> None:
    """Assert checker result uniqueness and counters through API-visible data.

    Args:
        checker_run: Checker run response returned by the HTTP API.
        expected_names: Exact checker names required for the run.
    """
    results = checker_run["results"]
    names = [result["checker_name"] for result in results]
    ensure(set(names) == expected_names, f"checker set drifted: {set(names)}")
    ensure(len(names) == len(set(names)), f"duplicate checker results returned: {names}")
    ensure(
        checker_run["warning_count"]
        == sum(1 for result in results if result["status"] == "warning"),
        "checker warning count does not match returned results",
    )
    ensure(
        checker_run["failed_count"] == sum(1 for result in results if result["status"] == "failed"),
        "checker failed count does not match returned results",
    )
    ensure(
        checker_run["blocking_count"] == sum(1 for result in results if result["blocks_review"]),
        "checker blocking count does not match returned results",
    )
    ensure(
        checker_run["passed_count"] == sum(1 for result in results if result["status"] == "passed"),
        "checker passed count does not match returned results",
    )


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
        "Refusing to run API contract E2E against a non-local database. "
        "Use an async Postgres URL such as postgresql+asyncpg:// on "
        "localhost/127.0.0.1 with a local test database named "
        "workstream_test, test_workstream, or workstream_test_<12 lowercase hex>, or set "
        f"WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE={NONLOCAL_DATABASE_OVERRIDE_VALUE}."
    )


def assert_isolated_database_url(database_url: str) -> None:
    """Require this destructive drill to use an isolated derived test database."""
    assert_local_database_url(database_url)
    database_name = urlparse(database_url).path.lstrip("/")
    if DERIVED_DATABASE_NAME.fullmatch(database_name) is None:
        raise RuntimeError(
            "Refusing to run API contract E2E against a persistent test database. "
            "Use scripts/run_isolated_tests.py to provide an isolated derived database."
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
        "content_markdown": (
            f"# Real API Guide {run_id}\n\n"
            "Complete the real API task. Submit an artifact manifest and "
            "reviewable evidence. Do not include credentials or private source "
            "data."
        ),
        "change_summary": "Initial real API guide",
    }


async def configure_policy_boundaries(
    client: httpx.AsyncClient,
    token: str,
    project_id: str,
    guide_id: str,
    guide_version: str,
) -> None:
    """Configure both policies through their sole active HTTP boundaries.

    Args:
        client: Real HTTP client.
        token: Project Manager Flow bearer token.
        project_id: Project whose draft guide is configured.
        guide_id: Exact draft guide receiving both policies.
        guide_version: Guide version used by the direct PaymentPolicy fixture.
    """
    await request_json(
        client,
        "PUT",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/review-policy",
        token,
        {
            "review_preference_window_seconds": 3600,
            "review_lease_duration_seconds": 1800,
            "max_active_review_leases_per_reviewer": 1,
            "self_review_allowed": False,
            "reject_policy": "close_task",
            "finding_evidence_requirement": "optional",
            "requires_second_review": False,
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": ["issue", "required_fix"],
        },
        idempotency_key=str(uuid4()),
        if_match='"no-current-policy"',
    )
    await request_json(
        client,
        "PUT",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/revision-policy",
        token,
        {
            "max_revision_rounds": 7,
            "revision_deadline_hours": 48,
            "allowed_resubmission_states": ["needs_revision"],
            "reviewer_reassignment_rule": "same reviewer preferred",
        },
        idempotency_key=str(uuid4()),
        if_match='"no-current-policy"',
    )
    async with db_session.get_session_factory()() as session:
        session.add(
            PaymentPolicy(
                id=str(uuid4()),
                project_id=project_id,
                guide_version=guide_version,
                base_amount="25.00",
                currency="USD",
                payout_type="fixed",
                revision_payment_rule="none",
                rejection_payment_rule="none",
                accepted_payment_rule="pay base amount",
            )
        )
        await session.commit()


def sha256_token(seed: str) -> str:
    """Return a platform-shaped sha256 token for deterministic E2E fixtures.

    Args:
        seed: Stable seed material.

    Returns:
        Hash token shaped as ``sha256:<64 lowercase hex>``.
    """
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def submission_artifact_policy_body() -> dict:
    """Build the project submission artifact policy used by the API contract drill.

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
    diagnostic_reader_token: str,
    contributor_token: str,
    service_token: str,
    role_claim_only_token: str,
    wrong_project_manager_token: str,
    manager_subject: str,
    project_id: str,
    guide_id: str,
    run_id: str,
    *,
    post_submit_required_checkers: list[str] | None = None,
    post_submit_warning_checkers: list[str] | None = None,
    post_submit_blocking_severities: list[str] | None = None,
) -> dict:
    """Create the guide-source, sufficiency, and approved policy bundle.

    Args:
        client: HTTP client pointed at the running API.
        manager_token: Flow token with project manager role.
        diagnostic_reader_token: Token bound to the local Project Manager grant.
        contributor_token: Human token without Project Manager authority.
        service_token: Service token concealed from the public human boundary.
        role_claim_only_token: Human PM role claim without a local grant.
        wrong_project_manager_token: Human with a PM grant for another project.
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
        diagnostic_reader_token,
        {
            "items": [
                {
                    "source_kind": "inline_markdown",
                    "source_label": f"guide-{run_id}.md",
                    "ingestion_adapter": "manual_import",
                    "media_type": "text/markdown",
                }
            ]
        },
        201,
        idempotency_key=str(uuid4()),
    )
    for item in snapshot["items"]:
        payload = (
            json.dumps({"guide_source": item["source_label"]}, sort_keys=True).encode()
            if item["media_type"] == "application/json"
            else f"# {item['source_label']}\nBounded verified guide material.\n".encode()
        )
        upload = await client.post(
            f"/api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots/"
            f"{snapshot['id']}/items/{item['id']}/artifact",
            headers={
                "Authorization": f"Bearer {diagnostic_reader_token}",
                "Idempotency-Key": str(uuid4()),
                "Content-Type": item["media_type"] or "application/octet-stream",
            },
            content=payload,
        )
        ensure(upload.status_code == 202, f"guide source upload failed: {upload.text}")
    # The hosted contract drill intentionally has no broker-backed worker.
    # Drive the canonical async worker adapters on this process's event loop so
    # SQLAlchemy connections never cross loops. Each adapter still consumes
    # its exact fixed-service authority and provider-neutral ART boundary.
    from app.adapters.artifacts.internal_workers import (
        continue_guide_setup_after_verification,
        run_artifact_internal_operation,
        scan_artifact_pending_work,
    )

    async def publish_put_attempt(attempt_id: str) -> None:
        await run_artifact_internal_operation("put", UUID(attempt_id))

    async def publish_verification_job(job_id: str) -> None:
        identifier = UUID(job_id)
        await run_artifact_internal_operation("verification", identifier)
        await continue_guide_setup_after_verification(identifier)

    published_work = 0
    for _ in range(8):
        published_generation = await scan_artifact_pending_work(
            publish_put_attempt,
            publish_verification_job,
        )
        published_work += published_generation
        if published_generation == 0:
            break
    else:
        raise AssertionError("guide artifact worker did not drain bounded committed work")
    ensure(published_work > 0, "guide artifact worker found no committed work")
    queued_setup = await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest",
        diagnostic_reader_token,
    )
    setup_worker_result = None
    if queued_setup["status"] == "queued":
        from app.interfaces.project_agents import (
            GuideSufficiencyAgentResult,
            SubmissionArtifactPolicyDerivationResult,
        )
        from app.modules.projects import service as project_service_module
        from app.modules.projects import (
            sufficiency_mutation_service as sufficiency_mutation_service_module,
        )
        from app.workers.project_setup import run_pre_submit_setup_pipeline

        class E2EProjectGuideAgentRuntime:
            """Deterministic agent boundary for the isolated real-API drill."""

            async def analyze_guide_sufficiency(self, _material):
                return GuideSufficiencyAgentResult(
                    status="guide_sufficient",
                    findings=[],
                    summary="Verified guide material is sufficient for the API drill.",
                    agent_version="api-contract-e2e-v0.1",
                )

            async def derive_submission_artifact_policy(self, material, sufficiency_report):
                return SubmissionArtifactPolicyDerivationResult(
                    policy_version=(
                        f"agent-{material.source_snapshot_hash.removeprefix('sha256:')[:12]}"
                    ),
                    policy_body=submission_artifact_policy_body(),
                    change_summary=(
                        "Derived from verified guide material after "
                        f"{sufficiency_report.agent_name} review."
                    ),
                    agent_version="api-contract-e2e-v0.1",
                )

        agent_runtime = E2EProjectGuideAgentRuntime()
        project_service_module.get_project_guide_agent_runtime = lambda: agent_runtime
        sufficiency_mutation_service_module.get_project_guide_agent_runtime = lambda: agent_runtime
        setup_worker_result = await asyncio.to_thread(
            run_pre_submit_setup_pipeline,
            project_id,
            guide_id,
            snapshot["id"],
            queued_setup["id"],
            queued_setup["setup_generation"],
        )
    setup_run = None
    for _ in range(120):
        setup_response = await client.get(
            f"/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest",
            headers=auth_headers(diagnostic_reader_token),
        )
        if setup_response.status_code == 404:
            await asyncio.sleep(1.0)
            continue
        ensure(
            setup_response.status_code == 200,
            f"guide setup run lookup failed: {setup_response.text}",
        )
        setup_run = setup_response.json()
        if setup_run["status"] in {"policy_draft_ready", "sufficiency_blocked", "setup_blocked"}:
            break
        await asyncio.sleep(1.0)
    ensure(setup_run is not None, "guide setup run was not observable")
    ensure(
        setup_run["status"] == "policy_draft_ready",
        "verified guide setup did not produce a draft policy: "
        f"run={json.dumps(setup_run, sort_keys=True)} "
        f"worker={json.dumps(setup_worker_result, sort_keys=True)}",
    )
    report = await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/"
        f"{setup_run['output_sufficiency_report_id']}",
        diagnostic_reader_token,
    )
    reports = await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        diagnostic_reader_token,
    )
    ensure(isinstance(reports, list), "sufficiency report list did not return a list")
    ensure(len(reports) == 1, f"expected one sufficiency report, got {len(reports)}")
    ensure(reports[0]["id"] == report["id"], "sufficiency report list returned wrong report")
    await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report['id']}",
        diagnostic_reader_token,
    )
    policy = await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/"
        f"{setup_run['output_submission_artifact_policy_id']}",
        diagnostic_reader_token,
    )
    policies = await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        diagnostic_reader_token,
    )
    ensure(isinstance(policies, list), "submission artifact policy list did not return a list")
    ensure(len(policies) == 1, f"expected one submission artifact policy, got {len(policies)}")
    ensure(policies[0]["id"] == policy["id"], "submission policy list returned wrong policy")
    await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy['id']}",
        diagnostic_reader_token,
    )
    manual_create_key = str(uuid4())
    manual_payload = {
        "source_snapshot_id": snapshot["id"],
        "policy_version": "e2e-manual-v1",
        "policy_body": submission_artifact_policy_body(),
        "change_summary": "Manual policy authorization E2E.",
    }
    manual_path = f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies"
    await request_json(
        client,
        "POST",
        manual_path,
        contributor_token,
        manual_payload,
        expected_status=404,
        idempotency_key=str(uuid4()),
    )
    await request_json(
        client,
        "POST",
        manual_path,
        service_token,
        manual_payload,
        expected_status=403,
        idempotency_key=str(uuid4()),
    )
    for denied_token in (role_claim_only_token, wrong_project_manager_token):
        await request_json(
            client,
            "POST",
            manual_path,
            denied_token,
            manual_payload,
            expected_status=404,
            idempotency_key=str(uuid4()),
        )
    missing_key = await client.post(
        manual_path,
        headers=auth_headers(manager_token),
        json=manual_payload,
    )
    ensure(missing_key.status_code == 422, "missing manual policy key was not rejected")
    invalid_key = await client.post(
        manual_path,
        headers=auth_headers(manager_token) | {"Idempotency-Key": "not-a-uuid"},
        json=manual_payload,
    )
    ensure(invalid_key.status_code == 422, "invalid manual policy key was not rejected")
    manual_policy = await request_json(
        client,
        "POST",
        manual_path,
        manager_token,
        manual_payload,
        expected_status=201,
        idempotency_key=manual_create_key,
    )
    manual_replay = await request_json(
        client,
        "POST",
        manual_path,
        manager_token,
        manual_payload,
        expected_status=201,
        idempotency_key=manual_create_key,
    )
    ensure(manual_replay == manual_policy, "manual policy create replay drifted")
    manual_update_key = str(uuid4())
    manual_update_payload = {
        "expected_policy_hash": manual_policy["policy_hash"],
        "successor_policy_version": "e2e-manual-v2",
        "policy_body": submission_artifact_policy_body(),
        "change_summary": "Manual policy replacement authorization E2E.",
    }
    manual_update_path = f"{manual_path}/{manual_policy['id']}"
    for invalid_headers, invalid_payload in (
        (auth_headers(manager_token), manual_update_payload),
        (
            auth_headers(manager_token) | {"Idempotency-Key": "not-a-uuid"},
            manual_update_payload,
        ),
        (
            auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            {"successor_policy_version": "e2e-manual-v2"},
        ),
        (
            auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            {
                "expected_policy_hash": "not-a-digest",
                "successor_policy_version": "e2e-manual-v2",
            },
        ),
        (
            auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            {"expected_policy_hash": manual_policy["policy_hash"]},
        ),
    ):
        invalid_update = await client.patch(
            manual_update_path,
            headers=invalid_headers,
            json=invalid_payload,
        )
        ensure(
            invalid_update.status_code == 422,
            f"invalid manual policy update precondition was not rejected: {invalid_update.text}",
        )
    manual_successor = await request_json(
        client,
        "PATCH",
        manual_update_path,
        manager_token,
        manual_update_payload,
        idempotency_key=manual_update_key,
    )
    manual_update_replay = await request_json(
        client,
        "PATCH",
        manual_update_path,
        manager_token,
        manual_update_payload,
        idempotency_key=manual_update_key,
    )
    ensure(manual_update_replay == manual_successor, "manual policy update replay drifted")
    ensure(
        manual_successor["supersedes_policy_id"] == manual_policy["id"],
        "manual policy replacement lost predecessor custody",
    )
    await request_json(
        client,
        "PATCH",
        f"{manual_path}/{manual_successor['id']}",
        manager_token,
        {
            **manual_update_payload,
            "expected_policy_hash": "sha256:" + ("0" * 64),
            "successor_policy_version": "e2e-manual-v3",
        },
        expected_status=409,
        idempotency_key=str(uuid4()),
    )
    effective_policy = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/"
        f"{policy['id']}/approve",
        manager_token,
        {"approval_note": "Approved for API contract real API drill."},
    )
    await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy",
        manager_token,
        expected_status=404,
    )
    await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy",
        manager_token,
        expected_status=404,
    )
    await create_approved_post_submit_policy_ci_bridge(
        project_id=project_id,
        guide_id=guide_id,
        manager_subject=manager_subject,
        source_snapshot=snapshot,
        sufficiency_report=report,
        submission_artifact_policy=policy,
        effective_policy=effective_policy,
        required_checkers=post_submit_required_checkers,
        warning_checkers=post_submit_warning_checkers,
        blocking_severities=post_submit_blocking_severities,
    )
    return effective_policy


async def create_approved_post_submit_policy_ci_bridge(
    *,
    project_id: str,
    guide_id: str,
    manager_subject: str,
    source_snapshot: dict,
    sufficiency_report: dict,
    submission_artifact_policy: dict,
    effective_policy: dict,
    required_checkers: list[str] | None = None,
    warning_checkers: list[str] | None = None,
    blocking_severities: list[str] | None = None,
) -> dict:
    """Persist a temporary approved post-submit policy for CI contract drills.

    WS-POL-002-02 builds derivation and compilation, while WS-POL-002-03 owns
    the server approval API. The CI API-contract drill still needs an active
    guide to exercise task/submission/checker APIs without requiring external
    agent credentials. This helper is therefore a test-only activation bridge:
    all prerequisite records are created through the public API first, the real
    trusted compiler builds the policy body, and the direct DB write is limited
    to the generated policy approval plus setup-ledger marker that
    WS-POL-002-03 will replace.
    """
    guide_version = effective_policy["guide_version"]
    spec = build_project_post_submit_checker_spec(
        project_id=project_id,
        guide_version=guide_version,
        required_checkers=(
            ["check_policy_context_present"] if required_checkers is None else required_checkers
        ),
        warning_checkers=[] if warning_checkers is None else warning_checkers,
        blocking_severities=blocking_severities,
    )
    compiled = compile_project_post_submit_checker_spec(
        project_id=project_id,
        guide_version=guide_version,
        spec=spec,
    )
    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy["id"],
                PreSubmitCheckerPolicy.lifecycle_status == "compiled",
            )
        )
        ensure(
            pre_submit_checker_policy is not None,
            "compiled pre-submit checker policy was not created during approval",
        )
        post_submit_policy = PostSubmitCheckerPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide_version,
            source_snapshot_id=source_snapshot["id"],
            source_snapshot_hash=source_snapshot["bundle_hash"],
            effective_policy_id=effective_policy["id"],
            effective_policy_hash=effective_policy["effective_policy_hash"],
            pre_submit_checker_policy_id=pre_submit_checker_policy.id,
            pre_submit_checker_bundle_hash=pre_submit_checker_policy.compiled_bundle_hash,
            required_checkers=compiled.required_checkers,
            warning_checkers=compiled.warning_checkers,
            blocking_severities=compiled.blocking_severities,
            policy_hash=compiled.policy_hash,
            policy_body=compiled.policy_body,
            lifecycle_status="approved",
            approved_by_role="project_manager",
            approved_by_actor=manager_subject,
            approved_at=datetime.now(UTC),
            created_by=manager_subject,
        )
        setup_run = await session.scalar(
            select(ProjectSetupRun).where(
                ProjectSetupRun.project_id == project_id,
                ProjectSetupRun.guide_id == guide_id,
                ProjectSetupRun.source_snapshot_id == source_snapshot["id"],
            )
        )
        ensure(setup_run is not None, "verified project setup run was not created")
        setup_run.status = "post_submit_policy_compiled"
        setup_run.current_step = "post_submit_checker_policy_compilation"
        setup_run.output_sufficiency_report_id = sufficiency_report["id"]
        setup_run.output_submission_artifact_policy_id = submission_artifact_policy["id"]
        setup_run.output_post_submit_checker_policy_id = post_submit_policy.id
        setup_run.post_submit_derivation_summary = {
            "status": "compiled",
            "post_submit_checker_policy_id": post_submit_policy.id,
            "required_checkers": post_submit_policy.required_checkers,
            "warning_checkers": post_submit_policy.warning_checkers,
            "blocking_severities": post_submit_policy.blocking_severities,
        }
        setup_run.error_code = None
        setup_run.error_summary = None
        session.add(post_submit_policy)
        await session.commit()
        return {"id": post_submit_policy.id, "policy_hash": post_submit_policy.policy_hash}


async def exercise_api_contract(base_url: str, env: dict[str, str]) -> None:
    """Run the real Project -> Task -> Submission API contract flow.

    Args:
        base_url: Real API server base URL.
        env: Runtime environment shared by the API server and token issuer.
    """
    flow_issuer, flow_audience, flow_secret = flow_settings(env)
    run_id = uuid4().hex[:8]
    manager_subject = f"real-api-project-manager-{run_id}"
    manager_token = issue_flow_token(
        manager_subject,
        ["project_manager"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    project_reader_token = issue_flow_token(
        f"real-api-project-reader-{run_id}",
        [],
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
    untrusted_service_token = issue_flow_token(
        f"real-api-untrusted-service-{run_id}",
        [],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
        subject_kind="service",
    )
    role_claim_only_token = issue_flow_token(
        f"real-api-role-claim-only-{run_id}",
        ["project_manager"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    wrong_project_manager_token = issue_flow_token(
        f"real-api-wrong-project-manager-{run_id}",
        [],
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
        openapi = await request_json(client, "GET", "/openapi.json")
        read_actions = {
            path: item["get"]["x-workstream-action-id"]
            for path, item in openapi["paths"].items()
            if path
            in {
                "/api/v1/projects/{project_id}/contributor-candidates",
                "/api/v1/projects/{project_id}/role-grants",
                "/api/v1/projects/{project_id}/role-grants/{grant_id}",
                "/api/v1/projects/{project_id}",
                "/api/v1/actors/me/authorization-context",
                "/api/v1/projects/{project_id}/active-guide",
                "/api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy",
                "/api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy",
            }
        }
        assert read_actions == {
            "/api/v1/projects/{project_id}/contributor-candidates": (
                "project.contributor_candidate.list"
            ),
            "/api/v1/projects/{project_id}/role-grants": "project_role_grant.list",
            "/api/v1/projects/{project_id}/role-grants/{grant_id}": ("project_role_grant.read"),
            "/api/v1/projects/{project_id}": "project.read",
            "/api/v1/actors/me/authorization-context": ("actor.authorization_context.read"),
            "/api/v1/projects/{project_id}/active-guide": "project.active_guide.read",
            "/api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy": (
                "project.effective_submission_artifact_policy.read"
            ),
            "/api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy": (
                "project.pre_submit_checker_policy.read"
            ),
        }
        sufficiency_actions = {
            path: openapi["paths"][path]["post"]["x-workstream-action-id"]
            for path in {
                "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
                "/api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots/"
                "{source_snapshot_id}/run-sufficiency-agent",
                "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/"
                "{report_id}/acknowledge-warnings",
            }
        }
        assert sufficiency_actions == {
            "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports": (
                "project.guide_sufficiency_report.create"
            ),
            "/api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots/"
            "{source_snapshot_id}/run-sufficiency-agent": "project.guide_sufficiency.run",
            "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/"
            "{report_id}/acknowledge-warnings": ("project.guide_sufficiency.warnings.acknowledge"),
        }
        submission_policy_path = (
            "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies"
        )
        submission_policy_item_path = submission_policy_path + "/{policy_id}"
        assert (
            openapi["paths"][submission_policy_path]["post"]["x-workstream-action-id"]
            == "project.submission_artifact_policy.create"
        )
        assert (
            openapi["paths"][submission_policy_item_path]["patch"]["x-workstream-action-id"]
            == "project.submission_artifact_policy.update"
        )
        assert (
            openapi["paths"]["/api/v1/projects/{project_id}/role-grants"]["post"][
                "x-workstream-action-id"
            ]
            == "project_role_grant.issue"
        )
        assert (
            openapi["paths"]["/api/v1/projects"]["post"]["x-workstream-action-id"]
            == "project.create"
        )
        assert (
            openapi["paths"]["/api/v1/projects/{project_id}/role-grants/{grant_id}/revoke"]["post"][
                "x-workstream-action-id"
            ]
            == "project_role_grant.revoke"
        )
        await request_json(client, "GET", "/api/v1/auth/me", expected_status=401)
        await request_json(client, "GET", "/api/v1/auth/me", invalid_token, expected_status=401)
        await request_json(
            client, "GET", "/api/v1/auth/me", wrong_issuer_token, expected_status=401
        )
        await request_json(
            client, "GET", "/api/v1/auth/me", wrong_audience_token, expected_status=401
        )
        await request_json(client, "GET", "/api/v1/auth/me", expired_token, expected_status=401)
        await request_json(client, "GET", "/api/v1/auth/me", future_nbf_token, expected_status=401)
        manager = await request_json(client, "GET", "/api/v1/auth/me", manager_token)
        assert manager["auth_source"] == "flow"
        assert manager["is_dev_auth"] is False
        assert manager["roles"] == ["project_manager"]

        manager_profile = await request_json(
            client,
            "GET",
            "/api/v1/actors/me",
            manager_token,
        )
        bootstrap_code, bootstrap = await run_admin_bootstrap(
            manager_profile["actor_profile_id"],
            execute=True,
        )
        assert bootstrap_code == 0
        assert bootstrap["result_code"] == "bootstrapped"
        project_reader_profile = await request_json(
            client,
            "GET",
            "/api/v1/actors/me",
            project_reader_token,
        )
        creator_system_grant = await client.post(
            "/api/v1/admin-role-grants",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": project_reader_profile["actor_profile_id"],
                "role": "project_manager",
                "scope_type": "system",
                "reason": "Real API project creation authority proof",
            },
        )
        assert creator_system_grant.status_code == 201, creator_system_grant.text
        service_payload = {
            "service_identity": "workstream.review.projection",
            "subject": f"real-api-review-projection-{run_id}",
            "reason": "Real HTTP controlled service provisioning proof",
        }
        fixed_service_token = issue_flow_token(
            service_payload["subject"],
            [],
            issuer=flow_issuer,
            audience=flow_audience,
            secret=flow_secret,
            subject_kind="service",
        )
        unprovisioned_service = await client.get(
            "/api/v1/actors/me",
            headers=auth_headers(fixed_service_token),
        )
        assert unprovisioned_service.status_code == 403
        assert unprovisioned_service.json()["error"]["code"] == "service_actor_not_provisioned"
        service_headers = auth_headers(manager_token) | {
            "Idempotency-Key": str(uuid4()),
            "X-Request-ID": str(uuid4()),
            "X-Correlation-ID": str(uuid4()),
        }
        provisioned_service = await client.post(
            "/api/v1/service-actors",
            headers=service_headers,
            json=service_payload,
        )
        assert provisioned_service.status_code == 201, provisioned_service.text
        provisioned_body = provisioned_service.json()
        assert provisioned_body["service_identity"] == service_payload["service_identity"]
        assert provisioned_body["actor_status"] == "active"
        assert service_payload["subject"] not in provisioned_service.text
        replayed_service = await client.post(
            "/api/v1/service-actors",
            headers=service_headers,
            json=service_payload,
        )
        assert replayed_service.status_code == 201, replayed_service.text
        assert replayed_service.json() == provisioned_body
        service_actor_id = provisioned_body["actor_profile_id"]
        service_admin_profile = await request_json(
            client,
            "GET",
            f"/api/v1/actors/{service_actor_id}",
            manager_token,
        )
        service_admin_link = await request_json(
            client,
            "GET",
            f"/api/v1/actors/{service_actor_id}/identity-links",
            manager_token,
        )
        assert service_admin_profile["service_identity"] == service_payload["service_identity"]
        assert service_admin_profile["actor_kind"] == "service"
        assert service_admin_profile["last_seen_at"] is None
        assert service_admin_link["subject_kind"] == "service"
        assert service_admin_link["last_verified_at"] is None
        admitted_service = await client.get(
            "/api/v1/actors/me",
            headers=auth_headers(fixed_service_token),
        )
        assert admitted_service.status_code == 403
        assert admitted_service.json()["error"]["code"] == "permission_not_granted"
        serialized_service_reads = json.dumps(
            [service_admin_profile, service_admin_link],
            sort_keys=True,
        )
        assert service_payload["subject"] not in serialized_service_reads
        assert flow_issuer not in serialized_service_reads

        lifecycle_reason = "Real HTTP service profile lifecycle proof"
        suspended_service = await client.post(
            f"/api/v1/actors/{service_actor_id}/suspend",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": lifecycle_reason},
        )
        assert suspended_service.status_code == 200, suspended_service.text
        assert suspended_service.json() == {
            "resource_type": "actor_profile",
            "resource_id": service_actor_id,
            "version": None,
            "http_status": 200,
        }
        assert lifecycle_reason not in suspended_service.text
        suspended_service_admission = await client.get(
            "/api/v1/actors/me",
            headers=auth_headers(fixed_service_token),
        )
        assert suspended_service_admission.status_code == 403
        assert suspended_service_admission.json()["error"]["code"] == "actor_suspended"
        reactivated_service = await client.post(
            f"/api/v1/actors/{service_actor_id}/reactivate",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Real HTTP service profile correction"},
        )
        assert reactivated_service.status_code == 200, reactivated_service.text
        reactivated_service_admission = await client.get(
            "/api/v1/actors/me",
            headers=auth_headers(fixed_service_token),
        )
        assert reactivated_service_admission.status_code == 403
        assert reactivated_service_admission.json()["error"]["code"] == "permission_not_granted"

        service_link_id = service_admin_link["identity_link_id"]
        link_lifecycle_key = str(uuid4())
        link_lifecycle_reason = "Real HTTP service identity-link lifecycle proof"
        revoked_service_link = await client.post(
            f"/api/v1/actor-identity-links/{service_link_id}/revoke",
            headers=auth_headers(manager_token) | {"Idempotency-Key": link_lifecycle_key},
            json={"reason": link_lifecycle_reason},
        )
        assert revoked_service_link.status_code == 200, revoked_service_link.text
        assert revoked_service_link.json() == {
            "resource_type": "actor_identity_link",
            "resource_id": service_link_id,
            "version": None,
            "http_status": 200,
        }
        assert link_lifecycle_reason not in revoked_service_link.text
        revoked_service_admission = await client.get(
            "/api/v1/actors/me",
            headers=auth_headers(fixed_service_token),
        )
        assert revoked_service_admission.status_code == 403
        assert revoked_service_admission.json()["error"]["code"] == "identity_link_revoked"
        replayed_service_link = await client.post(
            f"/api/v1/actor-identity-links/{service_link_id}/revoke",
            headers=auth_headers(manager_token) | {"Idempotency-Key": link_lifecycle_key},
            json={"reason": link_lifecycle_reason},
        )
        assert replayed_service_link.status_code == 200, replayed_service_link.text
        assert replayed_service_link.json() == revoked_service_link.json()
        mismatched_service_link = await client.post(
            f"/api/v1/actor-identity-links/{service_link_id}/revoke",
            headers=auth_headers(manager_token) | {"Idempotency-Key": link_lifecycle_key},
            json={"reason": "Different link lifecycle request"},
        )
        assert mismatched_service_link.status_code == 409, mismatched_service_link.text
        assert mismatched_service_link.json()["error"]["code"] == "idempotency_mismatch"
        conflicting_service_link = await client.post(
            f"/api/v1/actor-identity-links/{service_link_id}/revoke",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Conflicting link lifecycle request"},
        )
        assert conflicting_service_link.status_code == 409, conflicting_service_link.text
        assert conflicting_service_link.json()["error"]["code"] == "identity_link_already_revoked"
        repaired_service_link = await client.post(
            f"/api/v1/actor-identity-links/{service_link_id}/reactivate",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Real HTTP service identity-link correction"},
        )
        assert repaired_service_link.status_code == 200, repaired_service_link.text
        repaired_service_link_view = await request_json(
            client,
            "GET",
            f"/api/v1/actors/{service_actor_id}/identity-links",
            manager_token,
        )
        assert repaired_service_link_view["status"] == "active"
        assert repaired_service_link_view["last_verified_at"] is None
        repaired_service_admission = await client.get(
            "/api/v1/actors/me",
            headers=auth_headers(fixed_service_token),
        )
        assert repaired_service_admission.status_code == 403
        assert repaired_service_admission.json()["error"]["code"] == "permission_not_granted"

        deactivated_service = await client.post(
            f"/api/v1/actors/{service_actor_id}/deactivate",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Real HTTP terminal service profile response"},
        )
        assert deactivated_service.status_code == 200, deactivated_service.text
        terminal_service = await client.post(
            f"/api/v1/actors/{service_actor_id}/reactivate",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Terminal profiles remain terminal"},
        )
        assert terminal_service.status_code == 409, terminal_service.text
        assert terminal_service.json()["error"]["code"] == "actor_deactivated_terminal"

        await provision_guide_artifact_pipeline_services(client, manager_token, run_id)

        project_response = await client.post(
            "/api/v1/projects",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": str(uuid4())},
            json={
                "name": f"API Contract Real API {run_id}",
                "slug": f"api-contract-real-api-{run_id}",
                "description": "Real backend API contract lifecycle QA",
            },
        )
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()
        wrong_scope_project = await request_json(
            client,
            "POST",
            "/api/v1/projects",
            project_reader_token,
            {
                "name": f"Wrong Scope Project {run_id}",
                "slug": f"wrong-scope-project-{run_id}",
                "description": "Exact-project authorization isolation proof",
            },
            expected_status=201,
            idempotency_key=str(uuid4()),
        )
        wrong_scope_profile = await request_json(
            client,
            "GET",
            "/api/v1/actors/me",
            wrong_project_manager_token,
        )
        wrong_scope_grant = await client.post(
            "/api/v1/admin-role-grants",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": wrong_scope_profile["actor_profile_id"],
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": wrong_scope_project["id"],
                "reason": "Real API wrong-project PM isolation proof",
            },
        )
        assert wrong_scope_grant.status_code == 201, wrong_scope_grant.text
        creator_revoke = await client.post(
            f"/api/v1/admin-role-grants/{creator_system_grant.json()['resource_id']}/revoke",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Creation proof complete; restore bounded reader"},
        )
        assert creator_revoke.status_code == 200, creator_revoke.text
        await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}",
            manager_token,
            expected_status=404,
        )
        project_manager_grant = await client.post(
            "/api/v1/admin-role-grants",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": project_reader_profile["actor_profile_id"],
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": project["id"],
                "reason": "Real API project-role read authority proof",
            },
        )
        assert project_manager_grant.status_code == 201, project_manager_grant.text
        project_identity = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}",
            project_reader_token,
        )
        assert project_identity == project
        actor_context = await request_json(
            client,
            "GET",
            f"/api/v1/actors/me/authorization-context?project_id={project['id']}",
            project_reader_token,
        )
        assert actor_context["project_id"] == project["id"]
        assert actor_context["admin_roles"] == ["project_manager"]
        assert actor_context["project_roles"] == []
        assert actor_context["effective_action_ids"] == [
            "project.contributor_candidate.list",
            "project.guide_sufficiency_report.list",
            "project.guide_sufficiency_report.read",
            "project.post_submit_checker_policy_setup.read",
            "project.read",
            "project.setup_run.read",
            "project.submission_artifact_policy.list",
            "project.submission_artifact_policy.read",
            "project_role_grant.issue",
            "project_role_grant.list",
            "project_role_grant.read",
            "project_role_grant.revoke",
        ]
        candidates = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/contributor-candidates?limit=1",
            project_reader_token,
        )
        assert set(candidates) == {"items", "next_cursor"}
        grants = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/role-grants?limit=1",
            project_reader_token,
        )
        assert grants == {"items": [], "next_cursor": None}
        missing_grant = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/role-grants/{uuid4()}",
            project_reader_token,
            expected_status=404,
        )
        missing_project = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{uuid4()}/role-grants/{uuid4()}",
            project_reader_token,
            expected_status=404,
        )
        assert missing_grant["error"]["code"] == missing_project["error"]["code"]
        assert missing_grant["error"]["message"] == missing_project["error"]["message"]

        guide = await request_json(
            client,
            "POST",
            f"/api/v1/projects/{project['id']}/guides",
            project_reader_token,
            guide_payload(run_id),
            201,
            idempotency_key=str(uuid4()),
        )
        await configure_policy_boundaries(
            client,
            project_reader_token,
            project["id"],
            guide["id"],
            guide["version"],
        )
        patched_guide = await request_json(
            client,
            "PATCH",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
            project_reader_token,
            {"change_summary": "Patched before activation through real API"},
            idempotency_key=str(uuid4()),
        )
        assert patched_guide["change_summary"] == "Patched before activation through real API"
        await create_policy_bundle_for_guide(
            client,
            manager_token,
            project_reader_token,
            worker_token,
            untrusted_service_token,
            role_claim_only_token,
            wrong_project_manager_token,
            manager_subject,
            project["id"],
            guide["id"],
            run_id,
        )
        await request_json(
            client,
            "POST",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
            manager_token,
            expected_status=404,
        )
        active = await seed_active_guide_for_pre_12h_e2e(
            project["id"], guide["id"], manager_subject, flow_issuer
        )
        assert active["guide"]["version"] == "v1"
        active_actor_context = await request_json(
            client,
            "GET",
            f"/api/v1/actors/me/authorization-context?project_id={project['id']}",
            project_reader_token,
        )
        assert {
            "project.active_guide.read",
            "project.effective_submission_artifact_policy.read",
            "project.pre_submit_checker_policy.read",
        }.issubset(active_actor_context["effective_action_ids"])
        await request_json(
            client,
            "PATCH",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
            project_reader_token,
            {"change_summary": "Illegal active guide edit"},
            409,
            idempotency_key=str(uuid4()),
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/active-guide",
            project_reader_token,
        )
        visible_effective_policy = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
            "effective-submission-artifact-policy",
            project_reader_token,
        )
        ensure(
            visible_effective_policy["guide_id"] == guide["id"],
            "active effective policy read returned the wrong guide",
        )
        visible_checker_policy = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/pre-submit-checker-policy",
            project_reader_token,
        )
        ensure(
            visible_checker_policy["effective_policy_id"] == visible_effective_policy["id"],
            "active checker policy read returned the wrong effective policy",
        )
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
                "description": "Exercise the full backend API contract lifecycle over HTTP.",
                "task_type": "evaluation",
                "difficulty": "medium",
                "skill_tags": ["stem", "proofs"],
                "estimated_time_minutes": 45,
                "source_type": "manual",
                "source_ref": f"real-api-{run_id}",
                "source_payload_hash": f"sha256:source-{run_id}",
                "acceptance_criteria": "Submission packet is complete.",
                "rejection_criteria": "Evidence is missing.",
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
        assert screened["locked_guide_version"] == "v1"
        assert screened["locked_review_policy_generation"] == 1
        assert screened["locked_review_policy_hash"].startswith("sha256:")
        assert screened["locked_revision_policy_generation"] == 1
        assert screened["locked_revision_policy_hash"].startswith("sha256:")
        assert screened["locked_payment_policy_version"] == "v1"
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
        canonical_actor = await request_json(
            client,
            "GET",
            "/api/v1/actors/me",
            worker_token,
        )
        assert canonical_actor["actor_kind"] == "human"
        assert canonical_actor["domains"] == ["contributor"]
        assert canonical_actor["admin_roles"] == []
        assert canonical_actor["project_role_grants"] == []
        assert "issuer" not in canonical_actor
        assert "subject" not in canonical_actor
        assert "roles" not in canonical_actor
        worker_admin_profile = await request_json(
            client,
            "GET",
            f"/api/v1/actors/{canonical_actor['actor_profile_id']}",
            manager_token,
        )
        worker_admin_link = await request_json(
            client,
            "GET",
            f"/api/v1/actors/{canonical_actor['actor_profile_id']}/identity-links",
            manager_token,
        )
        assert worker_admin_profile["actor_kind"] == "human"
        assert worker_admin_profile["service_identity"] is None
        assert worker_admin_link["subject_kind"] == "human"
        serialized_worker_reads = json.dumps(
            [worker_admin_profile, worker_admin_link],
            sort_keys=True,
        )
        assert worker_subject not in serialized_worker_reads
        assert flow_issuer not in serialized_worker_reads
        updated_actor = await request_json(
            client,
            "PATCH",
            "/api/v1/actors/me",
            worker_token,
            {"display_name": "Real API Contributor"},
        )
        assert updated_actor["display_name"] == "Real API Contributor"
        assert updated_actor["admin_roles"] == []
        assert updated_actor["project_role_grants"] == []
        worker_profile = await request_json(
            client,
            "POST",
            "/api/v1/workers/me/profile",
            worker_token,
            {"skill_tags": ["stem", "proofs"]},
        )
        assert worker_profile["external_subject"] == worker_subject
        assert worker_profile["external_issuer"] == flow_issuer
        assert worker_profile["status"] == "active"
        assert set(worker_profile["skill_tags"]) == {"stem", "proofs"}
        role_issue_key = str(uuid4())
        role_issue_body = {
            "target_actor_profile_id": canonical_actor["actor_profile_id"],
            "role": "submitter",
            "qualification": {
                "skills_snapshot": {
                    "availability": "available",
                    "reference_ids": ["skill:api-contract"],
                    "unavailable_reason": None,
                },
                "reputation_snapshot": {
                    "availability": "unavailable",
                    "reference_ids": [],
                    "unavailable_reason": "no_record",
                },
                "prior_project_work_refs": [],
                "external_expertise_refs": [],
            },
            "reason": "Real API independent submitter authority",
        }
        issued_role = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": role_issue_key},
            json=role_issue_body,
        )
        assert issued_role.status_code == 201, issued_role.text
        role_grant_id = issued_role.json()["id"]
        candidates = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/contributor-candidates?limit=100",
            project_reader_token,
        )
        assert {"actor_profile_id", "display_name"} == set(candidates["items"][0])
        grants = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/role-grants?status=active&role=submitter",
            project_reader_token,
        )
        assert [item["id"] for item in grants["items"]] == [role_grant_id]
        grant = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/role-grants/{role_grant_id}",
            project_reader_token,
        )
        assert set(grant) == {
            "id",
            "project_id",
            "actor_profile_id",
            "role",
            "status",
            "version",
            "grant_method",
            "qualification_snapshot",
            "granted_by_actor_profile_id",
            "granted_by_admin_role_grant_id",
            "granted_at",
            "grant_reason",
            "revoked_by_actor_profile_id",
            "revoked_at",
            "revoked_reason",
        }
        assert set(grant["qualification_snapshot"]) == {
            "id",
            "requested_role",
            "skills_snapshot",
            "reputation_snapshot",
            "prior_project_work_refs",
            "external_expertise_refs",
            "captured_by_actor_profile_id",
            "captured_by_admin_role_grant_id",
            "captured_at",
        }
        assert set(grant["qualification_snapshot"]["skills_snapshot"]) == {
            "availability",
            "reference_ids",
            "unavailable_reason",
        }
        assert set(grant["qualification_snapshot"]["reputation_snapshot"]) == {
            "availability",
            "reference_ids",
            "unavailable_reason",
        }
        assert grant["revoked_by_actor_profile_id"] is None
        assert grant["revoked_at"] is None
        assert grant["revoked_reason"] is None
        suspended_role_target = await client.post(
            f"/api/v1/actors/{canonical_actor['actor_profile_id']}/suspend",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Prove suspended targets cannot retain irremovable authority"},
        )
        assert suspended_role_target.status_code == 200, suspended_role_target.text
        role_revoke_key = str(uuid4())
        role_revoke_body = {"reason": "Real API submitter authority removal"}
        revoked_role = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{role_grant_id}/revoke",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": role_revoke_key},
            json=role_revoke_body,
        )
        assert revoked_role.status_code == 200, revoked_role.text
        assert revoked_role.json()["status"] == "revoked"
        reactivated_role_target = await client.post(
            f"/api/v1/actors/{canonical_actor['actor_profile_id']}/reactivate",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Restore API contract contributor after revocation proof"},
        )
        assert reactivated_role_target.status_code == 200, reactivated_role_target.text
        historical_role = await request_json(
            client,
            "GET",
            f"/api/v1/projects/{project['id']}/role-grants/{role_grant_id}",
            project_reader_token,
        )
        assert historical_role["status"] == "revoked"
        revoke_replay = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{role_grant_id}/revoke",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": role_revoke_key},
            json=role_revoke_body,
        )
        assert revoke_replay.status_code == 200, revoke_replay.text
        second_revoke = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{role_grant_id}/revoke",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": str(uuid4())},
            json=role_revoke_body,
        )
        assert second_revoke.status_code == 409, second_revoke.text
        assert second_revoke.json()["error"]["code"] == "project_role_grant_already_revoked"
        issue_after_revoke = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": role_issue_key},
            json=role_issue_body,
        )
        assert issue_after_revoke.status_code == 409, issue_after_revoke.text
        assert (
            issue_after_revoke.json()["error"]["code"] == "project_role_grant_replay_state_changed"
        )
        link_case_body = role_issue_body | {
            "role": "reviewer",
            "reason": "Prove link lifecycle cannot make authority irremovable",
        }
        link_case_issue = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": str(uuid4())},
            json=link_case_body,
        )
        assert link_case_issue.status_code == 201, link_case_issue.text
        revoked_target_link = await client.post(
            f"/api/v1/actor-identity-links/{worker_admin_link['identity_link_id']}/revoke",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Prove revoked-link grant removal"},
        )
        assert revoked_target_link.status_code == 200, revoked_target_link.text
        link_case_revoke = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{link_case_issue.json()['id']}/revoke",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Remove reviewer authority after target link revocation"},
        )
        assert link_case_revoke.status_code == 200, link_case_revoke.text
        repaired_target_link = await client.post(
            f"/api/v1/actor-identity-links/{worker_admin_link['identity_link_id']}/reactivate",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Restore API contract contributor identity link"},
        )
        assert repaired_target_link.status_code == 200, repaired_target_link.text
        removed_project_manager = await client.post(
            f"/api/v1/admin-role-grants/{project_manager_grant.json()['resource_id']}/revoke",
            headers=auth_headers(manager_token) | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Prove mutation replay reauthorizes current project authority"},
        )
        assert removed_project_manager.status_code == 200, removed_project_manager.text
        concealed_replay = await client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{role_grant_id}/revoke",
            headers=auth_headers(project_reader_token) | {"Idempotency-Key": role_revoke_key},
            json=role_revoke_body,
        )
        assert concealed_replay.status_code == 404, concealed_replay.text
        concealed_replay_error = concealed_replay.json()["error"]
        assert {
            key: value for key, value in concealed_replay_error.items() if key != "correlation_id"
        } == {
            key: value for key, value in missing_grant["error"].items() if key != "correlation_id"
        }
        await request_json(client, "GET", f"/api/v1/tasks/{task['id']}", worker_token)
        ready_work_context = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/work-context",
            worker_token,
        )
        ensure(
            ready_work_context["guide"]["version"] == "v1",
            "worker work context did not use locked guide v1",
        )
        ensure(
            ready_work_context["lifecycle"]["next_actions"] == ["claim"],
            "ready worker context did not expose claim as next action",
        )
        ensure(
            "locked_guide_source_snapshot_hash"
            not in json.dumps(ready_work_context, sort_keys=True),
            "worker work context leaked source snapshot hash",
        )
        for private_field in (
            "source_ref",
            "source_payload_hash",
            "import_batch_id",
            "external_task_id",
            "created_by",
            "assigned_to",
        ):
            ensure(
                private_field not in ready_work_context["task"],
                f"worker work context leaked {private_field}",
            )
        submission_requirements = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/submission-requirements",
            worker_token,
        )
        ensure(
            submission_requirements["required_artifacts"][0]["path"] == "answer.md",
            "submission requirements did not expose the locked artifact path",
        )
        ensure(
            submission_requirements["required_evidence"][0]["key"] == "checker_log",
            "submission requirements did not expose the locked evidence key",
        )
        ensure(
            submission_requirements["artifact_hash_algorithm"] == "sha256",
            "submission requirements did not expose platform hash algorithm",
        )
        ensure(
            submission_requirements["required_packet_fields"]
            == [
                "summary",
                "package_hash",
                "artifact_hash_manifest",
                "worker_attestation",
            ],
            "submission requirements did not expose exact submission request fields",
        )
        ensure(
            "compiled_bundle" not in json.dumps(submission_requirements, sort_keys=True),
            "submission requirements leaked compiled checker bundle",
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/locked-context",
            worker_token,
            expected_status=403,
        )
        locked_context = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/locked-context",
            manager_token,
        )
        ensure(
            locked_context["locked_guide_source_snapshot_hash"].startswith("sha256:"),
            "operator locked context omitted source snapshot hash",
        )
        ensure(
            locked_context["locked_pre_submit_checker_bundle_hash"].startswith("sha256:"),
            "operator locked context omitted pre-submit checker hash",
        )
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
        ensure(
            claim["assignment"]["contributor_id"] == canonical_actor["actor_profile_id"],
            "task claim did not return canonical contributor attribution",
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
        active_work_context = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/work-context",
            worker_token,
        )
        ensure(
            active_work_context["lifecycle"]["can_submit"] is True,
            "in-progress worker context did not expose submit readiness",
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
                        "metadata": {
                            "command": "api_contract_e2e",
                            "required_evidence_key": "checker_log",
                        },
                    }
                ],
            },
            201,
        )
        ensure(
            submission["contributor_id"] == canonical_actor["actor_profile_id"],
            "submission did not return canonical contributor attribution",
        )
        for internal_field in (
            "artifact_hash_manifest",
            "package_hash",
            "worker_attestation",
            "locked_guide_version",
            "locked_review_policy_id",
            "locked_review_policy_generation",
            "locked_review_policy_hash",
            "locked_revision_policy_id",
            "locked_revision_policy_generation",
            "locked_revision_policy_hash",
            "locked_payment_policy_version",
            "locked_post_submit_checker_policy_hash",
        ):
            assert internal_field not in submission
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
        locked = await request_json(
            client,
            "GET",
            f"/api/v1/submissions/{submission['id']}",
            manager_token,
        )
        assert locked["finalized_at"] is not None
        assert locked["locked_guide_version"] == "v1"
        assert locked["locked_review_policy_id"] == screened["locked_review_policy_id"]
        assert locked["locked_review_policy_generation"] == 1
        assert locked["locked_review_policy_hash"] == screened["locked_review_policy_hash"]
        assert locked["locked_revision_policy_id"] == screened["locked_revision_policy_id"]
        assert locked["locked_revision_policy_generation"] == 1
        assert locked["locked_revision_policy_hash"] == screened["locked_revision_policy_hash"]
        assert locked["locked_payment_policy_version"] == "v1"
        assert all(
            item["finalized_at"] == locked["finalized_at"] for item in locked["evidence_items"]
        )
        checker_run = await wait_for_submission_checker_run(client, manager_token, submission["id"])
        assert checker_run["routing_recommendation"] == "allow_review"
        assert checker_run["triggered_by"] == "workstream-system:pre-review-gate"
        assert checker_run["triggered_by_subject"] == "workstream-system:pre-review-gate"
        assert checker_run["triggered_by_issuer"] == "workstream"
        assert checker_run["trigger_auth_source"] == "workstream_system"
        assert_checker_run_result_integrity(checker_run, EXPECTED_DURABLE_CHECKERS)
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
            ("submission_finalized", "submitted", "submitted"),
            ("pre_review_gate_started", "submitted", "evaluation_pending"),
            ("pre_review_gate_passed", "evaluation_pending", "review_pending"),
        }:
            assert expected_transition in audit_transitions
        finalized_event = next(
            event for event in audit_events if event["event_type"] == "submission_finalized"
        )
        assert finalized_event["external_subject"] == worker_subject
        assert finalized_event["external_issuer"] == flow_issuer
        assert finalized_event["auth_source"] == "flow"
        assert (
            finalized_event["event_payload"]["finalized_at"].replace("+00:00", "Z")
            == locked["finalized_at"]
        )
        requester_actor_id = finalized_event["actor_id"]
        assert requester_actor_id
        assert requester_actor_id != "workstream-system:pre-review-gate"
        for event_type in ("pre_review_gate_started", "pre_review_gate_passed"):
            gate_event = next(event for event in audit_events if event["event_type"] == event_type)
            assert gate_event["actor_id"] == "workstream-system:pre-review-gate"
            assert gate_event["external_subject"] == "workstream-system:pre-review-gate"
            assert gate_event["external_issuer"] == "workstream"
            assert gate_event["auth_source"] == "workstream_system"
            assert gate_event["event_payload"]["requester_actor_id"] == requester_actor_id
            assert gate_event["event_payload"]["requester_external_subject"] == worker_subject
            assert gate_event["event_payload"]["requester_external_issuer"] == flow_issuer
            assert gate_event["event_payload"]["requester_auth_source"] == "flow"
            assert gate_event["event_payload"]["trigger_source"] == "submission_finalized"
        worker_audit_events = await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}/audit-events",
            worker_token,
        )
        assert all(event["claim_snapshot"] == {} for event in worker_audit_events)
        assert all(
            "artifact_hash_manifest" not in event["event_payload"] for event in worker_audit_events
        )
        await request_json(
            client,
            "GET",
            f"/api/v1/tasks/{task['id']}",
            reviewer_token,
            expected_status=403,
        )

    print("API contract real API e2e passed")
    print(f"project_id={project['id']}")
    print(f"guide_id={guide['id']}")
    print(f"task_id={task['id']}")
    print(f"assignment_id={claim['assignment']['id']}")
    print(f"submission_id={submission['id']}")
    print(f"submission_finalized_at={locked['finalized_at']}")


async def main(env: dict[str, str]) -> None:
    """Start the API server and exercise the backend API contract.

    Args:
        env: Environment variables for the API server.
    """
    await db_session.dispose_engine()
    await exercise_rate_control_contract(env)

    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    process, log_path = start_api_server(port, env)
    try:
        await wait_for_health(base_url, process, log_path)
        await exercise_api_contract(base_url, env)
    except BaseException:
        print(log_path.read_text(encoding="utf-8"), file=sys.stderr)
        raise
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    api_env = api_environment()
    assert_isolated_database_url(api_env["WORKSTREAM_DATABASE_URL"])
    os.environ.update(api_env)
    get_settings.cache_clear()
    command.upgrade(alembic_config(), "head")
    asyncio.run(main(api_env))
