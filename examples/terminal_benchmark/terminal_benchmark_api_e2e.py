"""Run real Terminal Benchmark source material through the current API contracts.

This is an example drill, not Workstream runtime code and not a required CI
test. It expects a local reference source-material path through
``WORKSTREAM_TERMINAL_BENCH_FIXTURE`` and writes only to a local test Postgres
database.
"""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
BACKEND_SCRIPTS_ROOT = BACKEND_ROOT / "scripts"
for import_root in (BACKEND_ROOT, BACKEND_SCRIPTS_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import httpx
from alembic import command

from app.db import session as db_session
from api_contract_e2e import (
    alembic_config,
    api_environment,
    create_approved_post_submit_policy_ci_bridge,
    find_free_port,
    flow_settings,
    issue_flow_token,
    request_json as api_contract_request_json,
    wait_for_health,
)
from week2_api_e2e import (
    EXPECTED_DURABLE_CHECKERS,
    STRONG_ATTESTATION,
    assert_default_checker_set,
    assert_pre_submit_checker_set,
    checker_result,
    ensure,
    start_backend_api_server,
    wait_for_submission_checker_run,
)

FIXTURE_ENV_VAR = "WORKSTREAM_TERMINAL_BENCH_FIXTURE"
GUIDE_ROOT_ENV_VAR = "WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT"
PRINT_RAW_LOCAL_IDS_ENV_VAR = "WORKSTREAM_TERMINAL_BENCH_PRINT_RAW_LOCAL_IDS"
LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_DATABASE_NAMES = {"workstream_test", "test_workstream"}
ASYNC_POSTGRES_SCHEMES = {"postgresql+asyncpg"}
PROJECT_SETUP_HTTP_TIMEOUT_SECONDS = 1800.0
REQUIRED_OPENAI_AGENT_SDK_ENV = (
    "OPENAI_API_KEY",
    "WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL",
)
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
FIXTURE_ID_PATTERN = re.compile(r"\bterminal-benchmark-[0-9a-fA-F]{12,}\b")
SHA256_VALUE_PATTERN = re.compile(r"\bsha256:[A-Za-z0-9._:-]+")
LOCAL_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users|tmp|var|private)/[^\s'\"),]+")


@dataclass(frozen=True)
class FixtureFile:
    """Real file from the Terminal Benchmark reference fixture."""

    artifact_name: str
    path: Path
    label: str
    notes: str


@dataclass(frozen=True)
class TerminalBenchmarkFixture:
    """Loaded Terminal Benchmark fixture paths and parsed task metadata."""

    root: Path
    fixture_id: str
    project_guide: Path
    reviewer_program: Path
    task_toml: Path
    submission_zip: Path
    static_guard: Path
    review_packet: Path
    docker_build_log: Path
    oracle_log: Path
    starter_log: Path
    metadata: dict
    environment: dict
    steps: list[dict]


def fixture_root() -> Path:
    """Resolve the real Terminal Benchmark fixture directory."""
    configured = os.environ.get(FIXTURE_ENV_VAR)
    if configured:
        root = Path(configured).expanduser()
        if not root.is_dir():
            raise RuntimeError(
                f"{FIXTURE_ENV_VAR} must point at an existing local source-material directory"
            )
        return root.resolve()
    raise RuntimeError(
        f"{FIXTURE_ENV_VAR} is required. Point it at one Terminal Benchmark "
        "source-material directory, for example a prepared fixture directory containing extracted/task.toml, "
        "one *_submission_*.zip, one review_packet_*.md, static_guard.txt, and verifier logs."
    )


def guide_root(fixture_root_path: Path) -> Path:
    """Resolve the Terminal Benchmark reference root containing guide/program material."""
    configured = os.environ.get(GUIDE_ROOT_ENV_VAR)
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend([fixture_root_path, fixture_root_path.parent])

    for candidate in candidates:
        project_guide = candidate / "PROJECT_GUIDE.md"
        reviewer_program = candidate / "REVIEWER_PROGRAM.md"
        if project_guide.is_file() and reviewer_program.is_file():
            return candidate.resolve()
    raise RuntimeError(
        f"could not find PROJECT_GUIDE.md and REVIEWER_PROGRAM.md. Set {GUIDE_ROOT_ENV_VAR} "
        "to the local Terminal Benchmark reference root."
    )


def require_openai_agent_sdk_environment(env: dict[str, str]) -> None:
    """Require the OpenAI Agents SDK runtime for this real API drill."""
    missing = [name for name in REQUIRED_OPENAI_AGENT_SDK_ENV if not env.get(name)]
    if missing:
        raise RuntimeError(
            "Terminal Benchmark API drill requires the OpenAI Agents SDK adapter. "
            f"Set required environment variables: {', '.join(missing)}"
        )


def require_single_fixture_match(root: Path, pattern: str, label: str) -> Path:
    """Return exactly one fixture file matching a pattern.

    Args:
        root: Fixture directory.
        pattern: Glob pattern relative to ``root``.
        label: Human-readable fixture file label for errors.

    Returns:
        The only matching fixture file.

    Raises:
        RuntimeError: If zero or multiple files match.
    """
    matches = sorted(root.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one {label} matching {pattern!r} in fixture "
            f"<redacted-fixture-label>; found {len(matches)} file(s)"
        )
    return matches[0]


def sanitized_fixture_id(task_toml: Path, submission_zip: Path) -> str:
    """Build a stable non-path fixture id from real fixture file hashes."""
    raw = f"{sha256_token(task_toml)}:{sha256_token(submission_zip)}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"terminal-benchmark-{digest}"


def safe_label(value: str) -> str:
    """Return a conservative display label for trusted fixture metadata."""
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")[:120] or "terminal-benchmark"


def public_evidence_value(value: str, placeholder: str, env: dict[str, str]) -> str:
    """Return raw local ids only when explicitly requested for local debugging."""
    if env.get(PRINT_RAW_LOCAL_IDS_ENV_VAR) == "1":
        return value
    return placeholder


def public_safe_exception_message(exc: Exception) -> str:
    """Return an exception summary without local ids or source fingerprints."""
    message = str(exc) or exc.__class__.__name__
    message = UUID_PATTERN.sub("<redacted-id>", message)
    message = FIXTURE_ID_PATTERN.sub("<redacted-fixture-id>", message)
    message = SHA256_VALUE_PATTERN.sub("sha256:<redacted>", message)
    message = LOCAL_PATH_PATTERN.sub("<redacted-local-path>", message)
    return f"{exc.__class__.__name__}: {message}"


def public_safe_script_failure_message(exc: Exception) -> str:
    """Return a generic top-level failure that cannot expose local transcript data."""
    return (
        f"{exc.__class__.__name__}: Terminal Benchmark API drill failed. "
        "Raw local failure details are hidden by default; set "
        f"{PRINT_RAW_LOCAL_IDS_ENV_VAR}=1 for local debugging."
    )


async def request_json(*args, **kwargs) -> dict:
    """Call the shared API helper without leaking raw request paths by default."""
    if os.environ.get(PRINT_RAW_LOCAL_IDS_ENV_VAR) == "1":
        return await api_contract_request_json(*args, **kwargs)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return await api_contract_request_json(*args, **kwargs)
    except Exception as exc:
        raise RuntimeError(public_safe_exception_message(exc)) from None


async def wait_for_submission_checker_run_public_safe(
    client: httpx.AsyncClient,
    manager_token: str,
    submission_id: str,
) -> dict:
    """Wait for a checker run without leaking local ids on failure by default."""
    if os.environ.get(PRINT_RAW_LOCAL_IDS_ENV_VAR) == "1":
        return await wait_for_submission_checker_run(client, manager_token, submission_id)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return await wait_for_submission_checker_run(client, manager_token, submission_id)
    except Exception as exc:
        raise RuntimeError(public_safe_exception_message(exc)) from None


def assert_strict_local_database_url(database_url: str) -> None:
    """Fail closed unless the drill targets local async Postgres test databases only."""
    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")
    is_local_async_postgres = (
        parsed.scheme in ASYNC_POSTGRES_SCHEMES
        and parsed.hostname in LOCAL_DATABASE_HOSTS
        and database_name in LOCAL_DATABASE_NAMES
        and not parsed.query
        and not parsed.params
        and not parsed.fragment
    )
    if is_local_async_postgres:
        return
    raise RuntimeError(
        "Refusing to run Terminal Benchmark API E2E against a non-local test database. "
        "This drill writes real project/task/submission/checker rows and only supports "
        "postgresql+asyncpg:// on localhost/127.0.0.1 with database name "
        "workstream_test or test_workstream and no URL query parameters."
    )


def load_fixture(root: Path) -> TerminalBenchmarkFixture:
    """Load and validate a Terminal Benchmark reference fixture.

    Args:
        root: Prepared fixture directory copied from Terminal Benchmark reference material.

    Returns:
        Parsed fixture paths and metadata.
    """
    task_toml = root / "extracted" / "task.toml"
    submission_zip = require_single_fixture_match(root, "*_submission_*.zip", "submission zip")
    review_packet = require_single_fixture_match(root, "review_packet_*.md", "review packet")
    required_paths = [
        task_toml,
        root / "static_guard.txt",
        root / "docker_build.log",
        root / "oracle_test.log",
        root / "starter_m1_test.log",
    ]
    missing = [path.name for path in required_paths if not path.exists()]
    if missing:
        raise RuntimeError(f"fixture is missing required files: {missing}")

    with task_toml.open("rb") as file:
        task_config = tomllib.load(file)
    guide_material_root = guide_root(root)
    return TerminalBenchmarkFixture(
        root=root,
        fixture_id=sanitized_fixture_id(task_toml, submission_zip),
        project_guide=guide_material_root / "PROJECT_GUIDE.md",
        reviewer_program=guide_material_root / "REVIEWER_PROGRAM.md",
        task_toml=task_toml,
        submission_zip=submission_zip,
        static_guard=root / "static_guard.txt",
        review_packet=review_packet,
        docker_build_log=root / "docker_build.log",
        oracle_log=root / "oracle_test.log",
        starter_log=root / "starter_m1_test.log",
        metadata=dict(task_config["metadata"]),
        environment=dict(task_config["environment"]),
        steps=list(task_config["steps"]),
    )


def sha256_token(path: Path) -> str:
    """Hash one real fixture file using Workstream's structural token shape."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def safe_ref_segment(value: str) -> str:
    """Return a safe opaque source-ref segment from fixture identity."""
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return normalized or "fixture"


def policy_key(value: str) -> str:
    """Return a stable policy key from human-readable fixture labels."""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return normalized.strip("_")


def text_excerpt(path: Path, *, limit: int = 4000) -> str | None:
    """Read a bounded text excerpt for source-snapshot material."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None
    if not text:
        return None
    return text[:limit]


def text_content(path: Path) -> str:
    """Read full trusted local setup material for the guide body."""
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def artifact_entry(file: FixtureFile) -> dict:
    """Build one submission artifact manifest entry from a real file."""
    return {
        "artifact": file.artifact_name,
        "hash": sha256_token(file.path),
        "size_bytes": file.path.stat().st_size,
        "notes": file.notes,
    }


def evidence_entry(file: FixtureFile, fixture: TerminalBenchmarkFixture) -> dict:
    """Build one evidence reference from a real fixture file."""
    return {
        "type": "log",
        "label": file.label,
        "uri": f"local://terminal-benchmark/{fixture.fixture_id}/{file.artifact_name}",
        "hash": sha256_token(file.path),
        "size_bytes": file.path.stat().st_size,
        "metadata": {
            "source": "terminal_benchmark_fixture",
            "fixture_id": fixture.fixture_id,
            "artifact": file.artifact_name,
            "policy_key": policy_key(file.label),
        },
    }


def fixture_files(fixture: TerminalBenchmarkFixture) -> list[FixtureFile]:
    """Return the real fixture files submitted as artifacts and evidence."""
    return [
        FixtureFile(
            "submission.zip",
            fixture.submission_zip,
            "original submission zip",
            "original submission archive",
        ),
        FixtureFile(
            "task.toml",
            fixture.task_toml,
            "task configuration",
            "Terminal Benchmark task configuration",
        ),
        FixtureFile(
            "static_guard.txt",
            fixture.static_guard,
            "platform static guard output",
            "static guard output captured with the fixture",
        ),
        FixtureFile(
            "review_packet.md",
            fixture.review_packet,
            "automated review packet",
            "AutoEval and review packet evidence",
        ),
        FixtureFile(
            "docker_build.log",
            fixture.docker_build_log,
            "docker build log",
            "container build evidence",
        ),
        FixtureFile(
            "oracle_test.log",
            fixture.oracle_log,
            "oracle verifier log",
            "oracle verifier execution evidence",
        ),
        FixtureFile(
            "starter_m1_test.log",
            fixture.starter_log,
            "starter verifier log",
            "starter verifier execution evidence",
        ),
    ]


def task_payload(fixture: TerminalBenchmarkFixture, run_id: str, suffix: str) -> dict:
    """Build one Workstream task from a real Terminal Benchmark task.toml."""
    metadata = fixture.metadata
    tags = list(dict.fromkeys([*metadata["tags"], *metadata["languages"]]))
    source_hash = sha256_token(fixture.task_toml)
    milestone_count = metadata["number_of_milestones"]
    return {
        "title": f"Terminal Benchmark {fixture.fixture_id} {suffix}",
        "description": (
            "Real Terminal Benchmark reference fixture with "
            f"{milestone_count} milestones, languages={metadata['languages']}, "
            f"category={metadata['category']}."
        ),
        "task_type": "terminal_benchmark",
        "difficulty": metadata["difficulty"],
        "skill_tags": tags,
        "estimated_time_minutes": int(metadata["expert_time_estimate_min"]),
        "source_type": "manual",
        "source_ref": f"terminal-benchmark/{fixture.fixture_id}/{suffix}/{run_id}",
        "source_payload_hash": source_hash,
        "external_task_id": fixture.fixture_id,
        "acceptance_criteria": (
            "Submission packet must include the original zip, task.toml, static guard "
            "output, review packet, build log, and verifier evidence."
        ),
        "rejection_criteria": (
            "Missing required Terminal Benchmark artifacts or evidence blocks review."
        ),
    }


def guide_payload(fixture: TerminalBenchmarkFixture, run_id: str) -> dict:
    """Build a project guide around the Terminal Benchmark fixture contract."""
    project_guide = text_content(fixture.project_guide)
    reviewer_program = text_content(fixture.reviewer_program)
    task_toml = text_content(fixture.task_toml)
    review_packet = text_content(fixture.review_packet)
    return {
        "version": "v1",
        "content_markdown": (
            f"# Terminal Benchmark Guide {run_id}\n\n"
            f"Fixture: `{fixture.fixture_id}`\n\n"
            "## Terminal Benchmark Project Guide\n\n"
            f"{project_guide}\n\n"
            "## Terminal Benchmark Reference Program\n\n"
            f"{reviewer_program}\n\n"
            "## Selected Terminal Benchmark Task TOML\n\n"
            "```toml\n"
            f"{task_toml}\n"
            "```\n\n"
            "## Selected Review Packet\n\n"
            f"{review_packet}"
        ),
        "change_summary": "Initial Terminal Benchmark real-world guide",
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


def submission_payload(
    fixture: TerminalBenchmarkFixture,
    run_id: str,
    suffix: str,
    *,
    include_static_guard: bool,
    low_quality_signal: bool = False,
) -> dict:
    """Build a submission packet from real Terminal Benchmark fixture files."""
    files = fixture_files(fixture)
    if not include_static_guard:
        files = [file for file in files if file.artifact_name != "static_guard.txt"]
    summary = (
        f"Terminal Benchmark {fixture.fixture_id} packet {suffix} from real "
        "reference fixture evidence."
    )
    if low_quality_signal:
        summary += " Placeholder sample output requires reviewer revision."
    return {
        "summary": summary,
        "package_uri": f"local://terminal-benchmark/{fixture.fixture_id}/submission.zip",
        "package_hash": sha256_token(fixture.submission_zip),
        "artifact_hash_manifest": [artifact_entry(file) for file in files],
        "worker_attestation": STRONG_ATTESTATION,
        "evidence_items": [evidence_entry(file, fixture) for file in files[1:]],
    }


def source_snapshot_payload(fixture: TerminalBenchmarkFixture) -> dict:
    """Build an opaque guide-source snapshot from real fixture material."""
    fixture_segment = safe_ref_segment(fixture.fixture_id)
    source_files = [
        ("project_guide", "PROJECT_GUIDE.md", fixture.project_guide, "text/markdown"),
        ("reviewer_program", "REVIEWER_PROGRAM.md", fixture.reviewer_program, "text/markdown"),
        ("task_material", "task.toml", fixture.task_toml, "text/toml"),
        ("submission_archive", "submission.zip", fixture.submission_zip, "application/zip"),
        ("review_packet", "review_packet.md", fixture.review_packet, "text/markdown"),
        ("static_guard", "static_guard.txt", fixture.static_guard, "text/plain"),
        ("build_log", "docker_build.log", fixture.docker_build_log, "text/plain"),
        ("verifier_log", "oracle_test.log", fixture.oracle_log, "text/plain"),
        ("verifier_log", "starter_m1_test.log", fixture.starter_log, "text/plain"),
    ]
    return {
        "items": [
            {
                "source_kind": source_kind,
                "durable_ref": f"import:/fixtures/{fixture_segment}/{artifact_name}",
                "ingestion_adapter": "manual_fixture_import",
                "content_hash": sha256_token(path),
                "content_cid": None,
                "media_type": media_type,
                "content_excerpt": text_excerpt(path),
            }
            for source_kind, artifact_name, path, media_type in source_files
        ]
    }


def terminal_benchmark_submission_artifact_policy_body(
    fixture: TerminalBenchmarkFixture,
) -> dict:
    """Build the exact project artifact policy used by this example fixture."""
    files = fixture_files(fixture)
    evidence_files = files[1:]
    return {
        "required_artifacts": [
            {
                "key": policy_key(file.artifact_name),
                "path": file.artifact_name,
                "hash_required": True,
                "required": True,
                "description": file.notes,
            }
            for file in files
        ],
        "required_evidence": [
            {
                "key": policy_key(file.label),
                "label": file.label,
                "hash_required": True,
                "required": True,
                "description": file.notes,
            }
            for file in evidence_files
        ],
        "forbidden_artifacts": [],
        "attestation_terms": [
            "original_work",
            "credentials_and_secret_exclusion",
            "real_api_originality",
            "human_accountability_for_agent_assisted_work",
        ],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": None,
        "maximum_package_size_bytes": None,
        "packaging": {
            "package_required": True,
            "allowed_package_formats": ["zip"],
        },
    }


def assert_checker_counts(
    run: dict,
    *,
    passed: int,
    warning: int,
    failed: int,
    blocking: int,
) -> None:
    """Assert the checker run aggregate counters are exact."""
    ensure(run["passed_count"] == passed, f"passed_count drifted: {run['passed_count']}")
    ensure(run["warning_count"] == warning, f"warning_count drifted: {run['warning_count']}")
    ensure(run["failed_count"] == failed, f"failed_count drifted: {run['failed_count']}")
    ensure(run["blocking_count"] == blocking, f"blocking_count drifted: {run['blocking_count']}")


def assert_checker_statuses(run: dict, expected: dict[str, str]) -> None:
    """Assert exact checker result statuses by checker name."""
    actual = {result["checker_name"]: result["status"] for result in run["results"]}
    ensure(actual == expected, f"checker statuses drifted: expected={expected} actual={actual}")


async def assert_no_durable_submissions_after_precheck(
    client: httpx.AsyncClient,
    worker_token: str,
    task_id: str,
    message: str,
) -> None:
    """Assert pre-submit feedback did not create durable submission records."""
    submissions = await request_json(
        client,
        "GET",
        f"/api/v1/tasks/{task_id}/submissions",
        worker_token,
    )
    ensure(submissions == [], message)


async def create_project_with_terminal_benchmark_guide(
    client: httpx.AsyncClient,
    manager_token: str,
    manager_subject: str,
    fixture: TerminalBenchmarkFixture,
    run_id: str,
) -> dict:
    """Create a project and activate it through the temporary CI bridge path."""
    project = await request_json(
        client,
        "POST",
        "/api/v1/projects",
        manager_token,
        {
            "name": f"Terminal Benchmark Real API {run_id}",
            "slug": f"terminal-benchmark-real-api-{run_id}",
            "description": "Real Terminal Benchmark fixture used as Workstream API evidence.",
        },
        201,
    )
    guide = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides",
        manager_token,
        guide_payload(fixture, run_id),
        201,
    )
    snapshot = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots",
        manager_token,
        source_snapshot_payload(fixture),
        201,
    )
    sufficiency = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots/"
        f"{snapshot['id']}/run-sufficiency-agent",
        manager_token,
        expected_status=201,
    )
    if sufficiency["status"] == "passed_with_warnings":
        sufficiency = await request_json(
            client,
            "POST",
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports/"
            f"{sufficiency['id']}/acknowledge-warnings",
            manager_token,
            {"acknowledgement_note": "Example fixture warnings reviewed by project manager."},
        )
    ensure(
        sufficiency["status"] in {"passed", "passed_with_warnings"},
        f"guide sufficiency did not pass: {sufficiency['status']}",
    )
    derived = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots/"
        f"{snapshot['id']}/derive-submission-artifact-policy",
        manager_token,
        expected_status=201,
    )
    ensure(
        derived["derivation_source"] == "agent_derivation",
        "policy derivation agent did not create an agent-derived draft policy",
    )
    manual_policy = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        manager_token,
        {
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1-terminal-benchmark-admin",
            "policy_body": terminal_benchmark_submission_artifact_policy_body(fixture),
            "change_summary": (
                "Admin-reviewed exact Terminal Benchmark artifact policy derived from "
                "the guide source snapshot and real fixture material."
            ),
        },
        201,
    )
    effective = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{manual_policy['id']}/approve",
        manager_token,
        {"approval_note": "Approved exact Terminal Benchmark intake contract."},
    )
    ensure(
        effective["source_snapshot_hash"] == snapshot["bundle_hash"],
        "effective policy did not bind to the guide source snapshot",
    )
    pre_submit_checker_policy = await request_json(
        client,
        "GET",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/pre-submit-checker-policy",
        manager_token,
    )
    await create_approved_post_submit_policy_ci_bridge(
        project_id=project["id"],
        guide_id=guide["id"],
        manager_subject=manager_subject,
        source_snapshot=snapshot,
        sufficiency_report=sufficiency,
        submission_artifact_policy=manual_policy,
        effective_policy=effective,
        pre_submit_checker_policy=pre_submit_checker_policy,
        required_checkers=[
            "check_policy_context_present",
            "check_low_quality_generated_artifacts",
        ],
        warning_checkers=[],
        blocking_severities=["critical", "high", "medium"],
    )
    active = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        manager_token,
    )
    ensure(active["guide"]["version"] == "v1", "Terminal Benchmark guide did not activate v1")
    ensure(
        active["guide_source_snapshot"]["bundle_hash"] == snapshot["bundle_hash"],
        "active guide did not bind to source snapshot",
    )
    ensure(
        active["effective_submission_artifact_policy"]["effective_policy_hash"]
        == effective["effective_policy_hash"],
        "active guide did not bind to effective project policy",
    )
    ensure(
        active["pre_submit_checker_policy"]["compiled_bundle_hash"],
        "active guide missing compiled pre-submit checker bundle",
    )
    return project


async def create_started_terminal_benchmark_task(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    worker_token: str,
    worker_subject: str,
    flow_issuer: str,
    project_id: str,
    fixture: TerminalBenchmarkFixture,
    run_id: str,
    suffix: str,
) -> dict:
    """Create, screen, release, claim, and start a Terminal Benchmark task."""
    task = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project_id}/tasks",
        manager_token,
        task_payload(fixture, run_id, suffix),
        201,
    )
    await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/screen",
        manager_token,
        {"reason": f"Terminal Benchmark {suffix} screening"},
    )
    screened = await request_json(client, "GET", f"/api/v1/tasks/{task['id']}", manager_token)
    ensure(screened["locked_guide_version"] == "v1", "screening did not stamp guide v1")
    locked_context = await request_json(
        client,
        "GET",
        f"/api/v1/tasks/{task['id']}/locked-context",
        manager_token,
    )
    ensure(
        {
            locked_context["locked_post_submit_checker_policy_version"],
            locked_context["locked_review_policy_version"],
            locked_context["locked_revision_policy_version"],
            locked_context["locked_payment_policy_version"],
        }
        == {"v1"},
        "screening did not stamp every policy version",
    )
    await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/release",
        manager_token,
        {"reason": f"Terminal Benchmark {suffix} release"},
    )
    profile = await request_json(
        client,
        "POST",
        "/api/v1/workers/me/profile",
        worker_token,
        {"skill_tags": list(dict.fromkeys(fixture.metadata["tags"]))},
    )
    ensure(profile["external_subject"] == worker_subject, "worker profile subject drifted")
    ensure(profile["external_issuer"] == flow_issuer, "worker profile issuer drifted")
    await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/claim",
        worker_token,
        {"reason": f"Terminal Benchmark {suffix} claim"},
    )
    started = await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/start",
        worker_token,
        {"reason": f"Terminal Benchmark {suffix} start"},
    )
    ensure(started["status"] == "in_progress", "Terminal Benchmark task did not start")
    started["operator_locked_context"] = locked_context
    return started


async def submit_and_wait_for_automatic_gate(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    worker_token: str,
    task_id: str,
    payload: dict,
) -> tuple[dict, dict, dict]:
    """Submit and wait for the automatic checker run."""
    submission = await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task_id}/submissions",
        worker_token,
        payload,
        201,
    )
    run = await wait_for_submission_checker_run_public_safe(
        client,
        manager_token,
        submission["id"],
    )
    return submission, submission, run


async def wait_for_task_status(
    client: httpx.AsyncClient,
    manager_token: str,
    task_id: str,
    expected_status: str,
) -> dict:
    """Wait for a task to reach a status through the real API."""
    task: dict | None = None
    for _ in range(50):
        task = await request_json(client, "GET", f"/api/v1/tasks/{task_id}", manager_token)
        if task["status"] == expected_status:
            return task
        await asyncio.sleep(0.2)
    raise AssertionError(
        f"expected task status {expected_status}, got {task['status'] if task else None}"
    )


async def assert_finalize_gate_audit(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    requester_subject: str,
    flow_issuer: str,
    task_id: str,
    checker_run_id: str,
    expected_gate_event: str,
) -> None:
    """Assert submission-lock and checker gate audit events through the API."""
    audit_events = await request_json(
        client,
        "GET",
        f"/api/v1/tasks/{task_id}/audit-events",
        manager_token,
    )
    finalized_event = next(
        event for event in audit_events if event["event_type"] == "submission_finalized"
    )
    ensure(
        finalized_event["external_subject"] == requester_subject,
        "submission_finalized requester subject drifted",
    )
    ensure(
        finalized_event["external_issuer"] == flow_issuer,
        "submission_finalized requester issuer drifted",
    )
    requester_actor_id = finalized_event["actor_id"]
    ensure(
        requester_actor_id and requester_actor_id != "workstream-system:pre-review-gate",
        "submission_finalized used the system actor as requester",
    )
    gate_event = next(event for event in audit_events if event["event_type"] == expected_gate_event)
    ensure(
        gate_event["actor_id"] == "workstream-system:pre-review-gate",
        f"{expected_gate_event} did not use the pre-review gate system actor",
    )
    ensure(
        gate_event["external_subject"] == "workstream-system:pre-review-gate",
        f"{expected_gate_event} system subject drifted",
    )
    ensure(gate_event["external_issuer"] == "workstream", f"{expected_gate_event} issuer drifted")
    ensure(
        gate_event["auth_source"] == "workstream_system",
        f"{expected_gate_event} auth source drifted",
    )
    ensure(
        gate_event["event_payload"]["requester_actor_id"] == requester_actor_id,
        f"{expected_gate_event} requester actor provenance drifted",
    )
    ensure(
        gate_event["event_payload"]["requester_external_subject"] == requester_subject,
        f"{expected_gate_event} requester subject provenance drifted",
    )
    ensure(
        gate_event["event_payload"]["requester_external_issuer"] == flow_issuer,
        f"{expected_gate_event} requester issuer provenance drifted",
    )
    ensure(
        gate_event["event_payload"]["checker_run_id"] == checker_run_id,
        f"{expected_gate_event} checker run provenance drifted",
    )
    ensure(
        gate_event["event_payload"]["trigger_source"] == "submission_finalized",
        f"{expected_gate_event} trigger source drifted",
    )


async def exercise_terminal_benchmark_api(base_url: str, env: dict[str, str]) -> None:
    """Run the Terminal Benchmark fixture through current API behavior."""
    fixture = load_fixture(fixture_root())
    flow_issuer, flow_audience, flow_secret = flow_settings(env)
    run_id = uuid4().hex[:8]
    manager_subject = f"terminal-benchmark-manager-{run_id}"
    manager_token = issue_flow_token(
        manager_subject,
        ["project_manager"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    complete_worker_subject = f"terminal-benchmark-worker-complete-{run_id}"
    complete_worker_token = issue_flow_token(
        complete_worker_subject,
        ["worker"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )
    revision_worker_subject = f"terminal-benchmark-worker-revision-{run_id}"
    revision_worker_token = issue_flow_token(
        revision_worker_subject,
        ["worker"],
        issuer=flow_issuer,
        audience=flow_audience,
        secret=flow_secret,
    )

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=PROJECT_SETUP_HTTP_TIMEOUT_SECONDS,
    ) as client:
        await request_json(client, "GET", "/api/v1/health")
        project = await create_project_with_terminal_benchmark_guide(
            client,
            manager_token,
            manager_subject,
            fixture,
            run_id,
        )

        complete_task = await create_started_terminal_benchmark_task(
            client,
            manager_token=manager_token,
            worker_token=complete_worker_token,
            worker_subject=complete_worker_subject,
            flow_issuer=flow_issuer,
            project_id=project["id"],
            fixture=fixture,
            run_id=run_id,
            suffix="complete",
        )
        complete_payload = submission_payload(
            fixture,
            run_id,
            "complete",
            include_static_guard=True,
        )
        complete_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{complete_task['id']}/submission-precheck",
            complete_worker_token,
            {"submission": complete_payload},
        )
        assert_pre_submit_checker_set(complete_precheck)
        ensure(complete_precheck["authoritative"] is False, "pre-submit was authoritative")
        ensure(complete_precheck["eligible_to_submit"] is True, "complete packet precheck failed")
        await assert_no_durable_submissions_after_precheck(
            client,
            complete_worker_token,
            complete_task["id"],
            "successful pre-submit check created durable submissions",
        )
        complete_submission, complete_locked, complete_run = await submit_and_wait_for_automatic_gate(
            client,
            manager_token=manager_token,
            worker_token=complete_worker_token,
            task_id=complete_task["id"],
            payload=complete_payload,
        )
        assert_default_checker_set(complete_run)
        assert_checker_counts(complete_run, passed=8, warning=0, failed=0, blocking=0)
        assert_checker_statuses(
            complete_run,
            {
                checker_name: "passed"
                for checker_name in EXPECTED_DURABLE_CHECKERS
            },
        )
        ensure(
            complete_run["routing_recommendation"] == "allow_review",
            "complete packet did not route to review",
        )
        await wait_for_task_status(client, manager_token, complete_task["id"], "review_pending")
        ensure(complete_locked["finalized_at"] is not None, "complete submission did not finalize")
        await assert_finalize_gate_audit(
            client,
            manager_token=manager_token,
            requester_subject=complete_worker_subject,
            flow_issuer=flow_issuer,
            task_id=complete_task["id"],
            checker_run_id=complete_run["id"],
            expected_gate_event="pre_review_gate_passed",
        )

        revision_task = await create_started_terminal_benchmark_task(
            client,
            manager_token=manager_token,
            worker_token=revision_worker_token,
            worker_subject=revision_worker_subject,
            flow_issuer=flow_issuer,
            project_id=project["id"],
            fixture=fixture,
            run_id=run_id,
            suffix="revision",
        )
        locked_context_fields = (
            "locked_guide_source_snapshot_hash",
            "locked_effective_project_submission_artifact_policy_hash",
            "locked_pre_submit_checker_bundle_hash",
        )
        ensure(
            all(
                complete_task["operator_locked_context"][field]
                for field in locked_context_fields
            ),
            "complete task did not stamp project policy context hashes",
        )
        ensure(
            all(
                revision_task["operator_locked_context"][field]
                for field in locked_context_fields
            ),
            "revision task did not stamp project policy context hashes",
        )
        ensure(
            {
                tuple(
                    task["operator_locked_context"][field]
                    for field in locked_context_fields
                )
                for task in (complete_task, revision_task)
            }
            == {
                tuple(
                    complete_task["operator_locked_context"][field]
                    for field in locked_context_fields
                )
            },
            "tasks under the same project did not reuse the same policy context hashes",
        )
        missing_static_guard_payload = submission_payload(
            fixture,
            run_id,
            "missing-static-guard",
            include_static_guard=False,
        )
        failed_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{revision_task['id']}/submission-precheck",
            revision_worker_token,
            {"submission": missing_static_guard_payload},
        )
        assert_pre_submit_checker_set(failed_precheck)
        ensure(
            failed_precheck["eligible_to_submit"] is False,
            "missing static guard precheck passed",
        )
        missing_required_file = next(
            result
            for result in failed_precheck["results"]
            if result["checker_name"] == "check_required_files"
        )
        ensure(missing_required_file["status"] == "failed", "required-files precheck did not fail")
        evidence_present = next(
            result
            for result in failed_precheck["results"]
            if result["checker_name"] == "check_evidence_present"
        )
        ensure(
            evidence_present["status"] == "failed",
            "missing-static-guard scenario did not enforce required evidence",
        )
        await assert_no_durable_submissions_after_precheck(
            client,
            revision_worker_token,
            revision_task["id"],
            "failed pre-submit check created durable submissions",
        )
        blocked_create = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{revision_task['id']}/submissions",
            revision_worker_token,
            missing_static_guard_payload,
            expected_status=422,
        )
        ensure(
            blocked_create["code"] == "pre_submission_checker_failed",
            "blocked submission create did not return pre_submission_checker_failed",
        )
        ensure(
            blocked_create["details"]["status"] == "failed",
            "blocked submission create did not return failed checker details",
        )
        ensure(
            blocked_create["details"]["eligible_to_submit"] is False,
            "blocked submission create returned eligible_to_submit=true",
        )
        await assert_no_durable_submissions_after_precheck(
            client,
            revision_worker_token,
            revision_task["id"],
            "blocked submission create persisted a submission",
        )

        low_quality_payload = submission_payload(
            fixture,
            run_id,
            "low-quality-v1",
            include_static_guard=True,
            low_quality_signal=True,
        )
        low_quality_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{revision_task['id']}/submission-precheck",
            revision_worker_token,
            {"submission": low_quality_payload},
        )
        assert_pre_submit_checker_set(low_quality_precheck)
        ensure(
            low_quality_precheck["eligible_to_submit"] is True,
            "low-quality warning should not block pre-submit intake",
        )
        low_quality_precheck_result = next(
            result
            for result in low_quality_precheck["results"]
            if result["checker_name"] == "check_low_quality_generated_artifacts"
        )
        ensure(
            low_quality_precheck_result["status"] == "warning",
            "low-quality pre-submit scenario did not warn",
        )
        first_submission, first_locked, first_run = await submit_and_wait_for_automatic_gate(
            client,
            manager_token=manager_token,
            worker_token=revision_worker_token,
            task_id=revision_task["id"],
            payload=low_quality_payload,
        )
        assert_default_checker_set(first_run)
        assert_checker_counts(first_run, passed=7, warning=0, failed=1, blocking=1)
        assert_checker_statuses(
            first_run,
            {
                **{checker_name: "passed" for checker_name in EXPECTED_DURABLE_CHECKERS},
                "check_low_quality_generated_artifacts": "failed",
            },
        )
        ensure(
            first_run["routing_recommendation"] == "needs_revision",
            "required low-quality checker did not route to needs_revision",
        )
        ensure(
            checker_result(first_run, "check_low_quality_generated_artifacts")["status"]
            == "failed",
            "durable low-quality checker did not fail",
        )
        ensure(
            checker_result(first_run, "check_required_files")["status"] == "passed",
            "durable low-quality scenario should keep artifact enforcement passing",
        )
        await wait_for_task_status(client, manager_token, revision_task["id"], "needs_revision")
        ensure(first_locked["finalized_at"] is not None, "revision v1 submission did not finalize")
        await assert_finalize_gate_audit(
            client,
            manager_token=manager_token,
            requester_subject=revision_worker_subject,
            flow_issuer=flow_issuer,
            task_id=revision_task["id"],
            checker_run_id=first_run["id"],
            expected_gate_event="pre_review_gate_needs_revision",
        )

        fixed_payload = submission_payload(
            fixture,
            run_id,
            "fixed-low-quality",
            include_static_guard=True,
        )
        fixed_precheck = await request_json(
            client,
            "POST",
            f"/api/v1/tasks/{revision_task['id']}/submission-precheck",
            revision_worker_token,
            {"submission": fixed_payload},
        )
        assert_pre_submit_checker_set(fixed_precheck)
        ensure(fixed_precheck["eligible_to_submit"] is True, "fixed packet precheck failed")
        second_submission, second_locked, second_run = await submit_and_wait_for_automatic_gate(
            client,
            manager_token=manager_token,
            worker_token=revision_worker_token,
            task_id=revision_task["id"],
            payload=fixed_payload,
        )
        assert_default_checker_set(second_run)
        assert_checker_counts(second_run, passed=8, warning=0, failed=0, blocking=0)
        assert_checker_statuses(
            second_run,
            {
                checker_name: "passed"
                for checker_name in EXPECTED_DURABLE_CHECKERS
            },
        )
        ensure(first_submission["version"] == 1, "first submission version drifted")
        ensure(second_submission["version"] == 2, "second submission version drifted")
        ensure(
            second_submission["supersedes_submission_id"] == first_submission["id"],
            "revision submission did not supersede v1",
        )
        ensure(
            second_run["routing_recommendation"] == "allow_review",
            "fixed Terminal Benchmark packet did not route to review",
        )
        await wait_for_task_status(client, manager_token, revision_task["id"], "review_pending")
        ensure(second_locked["finalized_at"] is not None, "revision v2 submission did not finalize")
        await assert_finalize_gate_audit(
            client,
            manager_token=manager_token,
            requester_subject=revision_worker_subject,
            flow_issuer=flow_issuer,
            task_id=revision_task["id"],
            checker_run_id=second_run["id"],
            expected_gate_event="pre_review_gate_passed",
        )

    print("Terminal Benchmark real API e2e passed")
    print("scenario_summary:")
    print(
        "redaction="
        + public_evidence_value(
            "raw_local_ids_enabled",
            "public_evidence_safe_by_default",
            env,
        )
    )
    print(
        "fixture_id="
        + public_evidence_value(fixture.fixture_id, "<redacted-fixture-id>", env)
    )
    print(
        "fixture_label="
        + public_evidence_value(safe_label(fixture.root.name), "<redacted-fixture-label>", env)
    )
    print("project_id=" + public_evidence_value(project["id"], "<redacted-id>", env))
    print("complete_task_id=" + public_evidence_value(complete_task["id"], "<redacted-id>", env))
    print(
        "complete_submission_id="
        + public_evidence_value(complete_submission["id"], "<redacted-id>", env)
    )
    print("revision_task_id=" + public_evidence_value(revision_task["id"], "<redacted-id>", env))
    print(
        "revision_v1_submission_id="
        + public_evidence_value(first_submission["id"], "<redacted-id>", env)
    )
    print(
        "revision_v2_submission_id="
        + public_evidence_value(second_submission["id"], "<redacted-id>", env)
    )
    print("complete_packet=review_pending")
    print("missing_static_guard=pre_submit_blocked_no_submission")
    print("low_quality_v1=needs_revision")
    print("fixed_low_quality_v2=review_pending")
    print("worker_profile_setup=canonical_worker_profile_api")


async def main(env: dict[str, str]) -> None:
    """Start the API server and run the Terminal Benchmark drill."""
    await db_session.dispose_engine()
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    process, log_path = start_backend_api_server(port, env)
    try:
        await wait_for_health(base_url, process, log_path)
        await exercise_terminal_benchmark_api(base_url, env)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    try:
        api_env = api_environment()
        require_openai_agent_sdk_environment(api_env)
        assert_strict_local_database_url(api_env["WORKSTREAM_DATABASE_URL"])
        os.environ.update(api_env)
        command.upgrade(alembic_config(), "head")
        asyncio.run(main(api_env))
    except Exception as exc:
        if os.environ.get(PRINT_RAW_LOCAL_IDS_ENV_VAR) == "1":
            raise
        print(public_safe_script_failure_message(exc), file=sys.stderr)
        raise SystemExit(1) from None
