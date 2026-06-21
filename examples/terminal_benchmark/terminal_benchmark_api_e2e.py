"""Run a real Terminal Benchmark fixture through the Week 1 and Week 2 APIs.

This is an example drill, not Workstream runtime code and not a required CI
test. It expects a local reviewer fixture path through
``WORKSTREAM_TERMINAL_BENCH_FIXTURE`` and writes only to a local test Postgres
database.
"""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import hashlib
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
from sqlalchemy import select

from app.db import session as db_session
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.tasks.models import AuditEvent, EvidenceItem, Submission, WorkstreamTask
from week1_api_e2e import (
    alembic_config,
    api_environment,
    find_free_port,
    flow_settings,
    issue_flow_token,
    request_json,
    wait_for_health,
)
from week2_api_e2e import (
    EXPECTED_DURABLE_CHECKERS,
    STRONG_ATTESTATION,
    assert_default_checker_set,
    assert_pre_submit_checker_set,
    checker_result,
    ensure,
    start_week2_api_server,
    wait_for_submission_checker_run,
)

FIXTURE_ENV_VAR = "WORKSTREAM_TERMINAL_BENCH_FIXTURE"
LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_DATABASE_NAMES = {"workstream_test", "test_workstream"}
ASYNC_POSTGRES_SCHEMES = {"postgresql+asyncpg"}


@dataclass(frozen=True)
class FixtureFile:
    """Real file from the Terminal Benchmark reviewer fixture."""

    artifact_name: str
    path: Path
    label: str
    notes: str


@dataclass(frozen=True)
class TerminalBenchmarkFixture:
    """Loaded Terminal Benchmark fixture paths and parsed task metadata."""

    root: Path
    fixture_id: str
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
                f"{FIXTURE_ENV_VAR} must point at an existing local fixture directory"
            )
        return root.resolve()
    raise RuntimeError(
        f"{FIXTURE_ENV_VAR} is required. Point it at one Terminal Benchmark reviewer "
        "fixture directory, for example a Termius review folder containing extracted/task.toml, "
        "one *_submission_*.zip, one review_packet_*.md, static_guard.txt, and verifier logs."
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
        match_names = [path.name for path in matches]
        raise RuntimeError(
            f"expected exactly one {label} matching {pattern!r} in fixture "
            f"{safe_label(root.name)!r}; found {len(matches)} file(s): {match_names}"
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
    """Load and validate a Terminal Benchmark reviewer fixture.

    Args:
        root: Fixture directory copied from the Termius reviewer workspace.

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
    return TerminalBenchmarkFixture(
        root=root,
        fixture_id=sanitized_fixture_id(task_toml, submission_zip),
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
        "uri": f"local://termius/{fixture.fixture_id}/{file.artifact_name}",
        "hash": sha256_token(file.path),
        "size_bytes": file.path.stat().st_size,
        "metadata": {
            "source": "terminal_benchmark_fixture",
            "fixture_id": fixture.fixture_id,
            "artifact": file.artifact_name,
        },
    }


def fixture_files(fixture: TerminalBenchmarkFixture) -> list[FixtureFile]:
    """Return the real fixture files submitted as artifacts and evidence."""
    return [
        FixtureFile(
            "submission.zip",
            fixture.submission_zip,
            "original submission zip",
            "original reviewer-side submission archive",
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
            "static guard output captured by the reviewer",
        ),
        FixtureFile(
            "review_packet.md",
            fixture.review_packet,
            "automated review packet",
            "AutoEval and reviewer packet evidence",
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
            "Real Terminal Benchmark reviewer fixture with "
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
        "required_files": ["submission.zip", "task.toml", "static_guard.txt", "review_packet.md"],
        "required_evidence": [
            "evidence references",
        ],
    }


def guide_payload(fixture: TerminalBenchmarkFixture, run_id: str) -> dict:
    """Build a project guide around the Terminal Benchmark fixture contract."""
    metadata = fixture.metadata
    return {
        "version": "v1",
        "content_markdown": (
            f"# Terminal Benchmark Guide {run_id}\n\n"
            "This guide models the Terminal Benchmark reviewer fixture contract captured "
            "by this packet for a real "
            f"Terminal Benchmark task: `{fixture.fixture_id}`.\n\n"
            "A reviewable packet must carry the task configuration, original "
            "submission archive, static guard output, AutoEval or review packet "
            "evidence, and verifier logs."
        ),
        "required_task_fields": [
            "title",
            "description",
            "acceptance_criteria",
            "required_files",
            "required_evidence",
        ],
        "required_submission_fields": [
            "summary",
            "artifact_hash_manifest",
            "evidence_items",
            "worker_attestation",
        ],
        "task_instructions": (
            "Use the Terminal Benchmark task packet and evidence bundle to evaluate "
            "whether the submitted task is structurally reviewable."
        ),
        "output_requirements": (
            "Submission packets must include local, R2, or S3 references with sha256 "
            "hash tokens for every required artifact and evidence item."
        ),
        "acceptance_criteria": "All required Terminal Benchmark packet files are present.",
        "rejection_criteria": "A required packet file or evidence item is missing.",
        "reviewer_rubric": (
            "Check task packet completeness, static guard evidence, and verifier logs "
            "before any human review decision."
        ),
        "forbidden_actions": "Do not include credentials, secrets, or private platform data.",
        "required_skills": list(dict.fromkeys(metadata["tags"])),
        "difficulty_scale": {metadata["difficulty"]: 2},
        "estimated_time_policy": {
            "expert_minutes": metadata["expert_time_estimate_min"],
            "junior_minutes": metadata["junior_time_estimate_min"],
        },
        "common_rejection_reasons": ["missing static guard", "missing verifier evidence"],
        "evidence_policy": {
            "required": [
                "static_guard.txt",
                "review_packet.md",
                "oracle_test.log",
                "starter_m1_test.log",
            ]
        },
        "unacceptable_work_policy": "Unverifiable or incomplete task packets are not reviewable.",
        "change_summary": "Initial Terminal Benchmark real-world guide",
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


def submission_payload(
    fixture: TerminalBenchmarkFixture,
    run_id: str,
    suffix: str,
    *,
    include_static_guard: bool,
) -> dict:
    """Build a submission packet from real Terminal Benchmark fixture files."""
    files = fixture_files(fixture)
    if not include_static_guard:
        files = [file for file in files if file.artifact_name != "static_guard.txt"]
    return {
        "summary": (
            f"Terminal Benchmark {fixture.fixture_id} packet {suffix} from real "
            "reviewer-side fixture evidence."
        ),
        "package_uri": f"local://termius/{fixture.fixture_id}/submission.zip",
        "package_hash": sha256_token(fixture.submission_zip),
        "artifact_hash_manifest": [artifact_entry(file) for file in files],
        "worker_attestation": STRONG_ATTESTATION,
        "evidence_items": [evidence_entry(file, fixture) for file in files[1:]],
    }


def expected_manifest(payload: dict) -> list[dict]:
    """Return the exact manifest persisted for a submitted payload."""
    return [
        {
            "artifact": entry["artifact"],
            "hash": entry["hash"],
            "size_bytes": entry["size_bytes"],
            "notes": entry["notes"],
        }
        for entry in payload["artifact_hash_manifest"]
    ]


def expected_evidence(payload: dict) -> list[dict]:
    """Return exact evidence fields expected to persist for a submitted payload."""
    return [
        {
            "type": entry["type"],
            "label": entry["label"],
            "uri": entry["uri"],
            "hash": entry["hash"],
            "size_bytes": entry["size_bytes"],
            "metadata": entry["metadata"],
        }
        for entry in payload["evidence_items"]
    ]


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
    fixture: TerminalBenchmarkFixture,
    run_id: str,
) -> dict:
    """Create a Workstream project and active guide from a Terminal Benchmark fixture."""
    project = await request_json(
        client,
        "POST",
        "/api/v1/projects",
        manager_token,
        {
            "name": f"Terminal Benchmark Real API {run_id}",
            "slug": f"terminal-benchmark-real-api-{run_id}",
            "description": "Real Terminal Benchmark fixture used as Workstream API evidence.",
            "base_amount": "25.00",
            "currency": "USD",
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
    active = await request_json(
        client,
        "POST",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        manager_token,
    )
    ensure(active["guide"]["version"] == "v1", "Terminal Benchmark guide did not activate v1")
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
    ensure(screened["locked_guide_version"] == "v1", "screening did not lock guide v1")
    ensure(
        {
            screened["locked_checker_policy_version"],
            screened["locked_review_policy_version"],
            screened["locked_revision_policy_version"],
            screened["locked_payment_policy_version"],
        }
        == {"v1"},
        "screening did not lock every policy version",
    )
    await request_json(
        client,
        "POST",
        f"/api/v1/tasks/{task['id']}/release",
        manager_token,
        {"reason": f"Terminal Benchmark {suffix} release"},
    )
    # Current v0.1 has no canonical worker-profile provisioning API. This demo
    # route is used only to bootstrap the real task lifecycle drill.
    profile = await request_json(
        client,
        "POST",
        "/api/v1/demo/worker-profile",
        worker_token,
        {"skill_tags": list(dict.fromkeys(fixture.metadata["tags"]))},
        201,
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
    return started


async def submit_lock_and_wait(
    client: httpx.AsyncClient,
    *,
    manager_token: str,
    worker_token: str,
    task_id: str,
    payload: dict,
) -> tuple[dict, dict, dict]:
    """Submit, lock, and wait for the automatic checker run."""
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
    run = await wait_for_submission_checker_run(client, manager_token, submission["id"])
    return submission, locked, run


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


async def assert_database_invariants(scenarios: list[dict]) -> None:
    """Verify the real API drill persisted the expected durable state."""
    async with db_session.get_session_factory()() as session:
        for scenario in scenarios:
            task = await session.get(WorkstreamTask, scenario["task_id"])
            submission = await session.get(Submission, scenario["submission_id"])
            checker_run = await session.get(CheckerRun, scenario["checker_run_id"])
            ensure(task is not None, f"{scenario['name']} task missing")
            ensure(submission is not None, f"{scenario['name']} submission missing")
            ensure(checker_run is not None, f"{scenario['name']} checker run missing")
            ensure(submission.locked_at is not None, f"{scenario['name']} submission not locked")
            ensure(
                submission.artifact_hash_manifest == scenario["expected_manifest"],
                f"{scenario['name']} artifact manifest drifted",
            )
            ensure(
                submission.version == scenario["expected_submission_version"],
                f"{scenario['name']} submission version drifted: {submission.version}",
            )
            ensure(
                submission.supersedes_submission_id == scenario["expected_supersedes_submission_id"],
                f"{scenario['name']} superseded submission drifted",
            )
            ensure(
                checker_run.trigger_source == "submission_locked",
                f"{scenario['name']} checker run was not automatic",
            )
            ensure(
                checker_run.routing_recommendation == scenario["expected_route"],
                f"{scenario['name']} route drifted: {checker_run.routing_recommendation}",
            )
            ensure(
                checker_run.passed_count == scenario["expected_passed_count"],
                f"{scenario['name']} passed_count drifted",
            )
            ensure(
                checker_run.warning_count == scenario["expected_warning_count"],
                f"{scenario['name']} warning_count drifted",
            )
            ensure(
                checker_run.failed_count == scenario["expected_failed_count"],
                f"{scenario['name']} failed_count drifted",
            )
            ensure(
                checker_run.blocking_count == scenario["expected_blocking_count"],
                f"{scenario['name']} blocking_count drifted",
            )
            ensure(checker_run.status == "completed", f"{scenario['name']} checker incomplete")
            ensure(
                checker_run.submission_version == submission.version,
                f"{scenario['name']} checker submission version drifted",
            )
            ensure(
                checker_run.package_hash == submission.package_hash,
                f"{scenario['name']} package hash drifted",
            )
            ensure(
                {
                    task.locked_guide_version,
                    task.locked_checker_policy_version,
                    task.locked_review_policy_version,
                    task.locked_revision_policy_version,
                    task.locked_payment_policy_version,
                }
                == {"v1"},
                f"{scenario['name']} task context was not locked to v1",
            )
            ensure(
                {
                    checker_run.locked_guide_version,
                    checker_run.locked_checker_policy_version,
                    checker_run.locked_review_policy_version,
                    checker_run.locked_revision_policy_version,
                    checker_run.locked_payment_policy_version,
                }
                == {"v1"},
                f"{scenario['name']} checker context was not locked to v1",
            )

            evidence = (
                await session.scalars(
                    select(EvidenceItem).where(EvidenceItem.submission_id == submission.id)
                )
            ).all()
            actual_evidence = [
                {
                    "type": item.type,
                    "label": item.label,
                    "uri": item.uri,
                    "hash": item.hash,
                    "size_bytes": item.size_bytes,
                    "metadata": item.metadata_json,
                }
                for item in evidence
            ]
            expected = scenario["expected_evidence"]
            ensure(
                sorted(actual_evidence, key=lambda item: item["label"])
                == sorted(expected, key=lambda item: item["label"]),
                f"{scenario['name']} evidence rows drifted",
            )
            ensure(
                all(item.locked_at == submission.locked_at for item in evidence),
                f"{scenario['name']} evidence was not locked with submission",
            )

            results = (
                await session.scalars(
                    select(CheckerResult).where(CheckerResult.checker_run_id == checker_run.id)
                )
            ).all()
            ensure(
                set(result.checker_name for result in results) == EXPECTED_DURABLE_CHECKERS,
                f"{scenario['name']} durable checker set drifted",
            )
            ensure(
                checker_run.blocking_count
                == sum(1 for result in results if result.blocks_review),
                f"{scenario['name']} blocking count drifted",
            )

            events = (
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
                    for event in events
                ),
                f"{scenario['name']} expected gate event missing",
            )
    print("PASS Terminal Benchmark database invariants")


async def exercise_terminal_benchmark_api(base_url: str, env: dict[str, str]) -> None:
    """Run the Terminal Benchmark fixture through Week 1 and Week 2 API behavior."""
    fixture = load_fixture(fixture_root())
    flow_issuer, flow_audience, flow_secret = flow_settings(env)
    run_id = uuid4().hex[:8]
    manager_token = issue_flow_token(
        f"terminal-benchmark-manager-{run_id}",
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

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        await request_json(client, "GET", "/api/v1/health")
        project = await create_project_with_terminal_benchmark_guide(
            client,
            manager_token,
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
        complete_submission, complete_locked, complete_run = await submit_lock_and_wait(
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
        ensure(complete_locked["locked_at"] is not None, "complete submission did not lock")

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
            evidence_present["status"] == "passed",
            "missing-static-guard scenario should isolate artifact enforcement",
        )
        await assert_no_durable_submissions_after_precheck(
            client,
            revision_worker_token,
            revision_task["id"],
            "failed pre-submit check created durable submissions",
        )

        first_submission, first_locked, first_run = await submit_lock_and_wait(
            client,
            manager_token=manager_token,
            worker_token=revision_worker_token,
            task_id=revision_task["id"],
            payload=missing_static_guard_payload,
        )
        assert_default_checker_set(first_run)
        assert_checker_counts(first_run, passed=7, warning=0, failed=1, blocking=1)
        assert_checker_statuses(
            first_run,
            {
                **{checker_name: "passed" for checker_name in EXPECTED_DURABLE_CHECKERS},
                "check_required_files": "failed",
            },
        )
        ensure(
            first_run["routing_recommendation"] == "needs_revision",
            "missing static guard did not route to needs_revision",
        )
        ensure(
            checker_result(first_run, "check_required_files")["status"] == "failed",
            "durable required-files checker did not fail",
        )
        ensure(
            checker_result(first_run, "check_evidence_present")["status"] == "passed",
            "durable missing-static-guard scenario should isolate artifact enforcement",
        )
        await wait_for_task_status(client, manager_token, revision_task["id"], "needs_revision")
        ensure(first_locked["locked_at"] is not None, "revision v1 submission did not lock")

        fixed_payload = submission_payload(
            fixture,
            run_id,
            "fixed-static-guard",
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
        second_submission, second_locked, second_run = await submit_lock_and_wait(
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
        ensure(second_locked["locked_at"] is not None, "revision v2 submission did not lock")

    await assert_database_invariants(
        [
            {
                "name": "complete_packet",
                "task_id": complete_task["id"],
                "submission_id": complete_submission["id"],
                "checker_run_id": complete_run["id"],
                "expected_route": "allow_review",
                "expected_gate_event": "pre_review_gate_passed",
                "expected_manifest": expected_manifest(complete_payload),
                "expected_evidence": expected_evidence(complete_payload),
                "expected_submission_version": 1,
                "expected_supersedes_submission_id": None,
                "expected_passed_count": 8,
                "expected_warning_count": 0,
                "expected_failed_count": 0,
                "expected_blocking_count": 0,
            },
            {
                "name": "missing_static_guard",
                "task_id": revision_task["id"],
                "submission_id": first_submission["id"],
                "checker_run_id": first_run["id"],
                "expected_route": "needs_revision",
                "expected_gate_event": "pre_review_gate_needs_revision",
                "expected_manifest": expected_manifest(missing_static_guard_payload),
                "expected_evidence": expected_evidence(missing_static_guard_payload),
                "expected_submission_version": 1,
                "expected_supersedes_submission_id": None,
                "expected_passed_count": 7,
                "expected_warning_count": 0,
                "expected_failed_count": 1,
                "expected_blocking_count": 1,
            },
            {
                "name": "fixed_static_guard",
                "task_id": revision_task["id"],
                "submission_id": second_submission["id"],
                "checker_run_id": second_run["id"],
                "expected_route": "allow_review",
                "expected_gate_event": "pre_review_gate_passed",
                "expected_manifest": expected_manifest(fixed_payload),
                "expected_evidence": expected_evidence(fixed_payload),
                "expected_submission_version": 2,
                "expected_supersedes_submission_id": first_submission["id"],
                "expected_passed_count": 8,
                "expected_warning_count": 0,
                "expected_failed_count": 0,
                "expected_blocking_count": 0,
            },
        ]
    )

    print("Terminal Benchmark real API e2e passed")
    print("scenario_summary:")
    print(f"fixture_id={fixture.fixture_id}")
    print(f"fixture_label={safe_label(fixture.root.name)}")
    print(f"project_id={project['id']}")
    print(f"complete_task_id={complete_task['id']}")
    print(f"complete_submission_id={complete_submission['id']}")
    print(f"revision_task_id={revision_task['id']}")
    print(f"revision_v1_submission_id={first_submission['id']}")
    print(f"revision_v2_submission_id={second_submission['id']}")
    print("complete_packet=review_pending")
    print("missing_static_guard=needs_revision")
    print("fixed_static_guard=review_pending")
    print("worker_profile_setup=demo_bootstrap_not_canonical_workflow")


async def main(env: dict[str, str]) -> None:
    """Start the API server and run the Terminal Benchmark drill."""
    await db_session.dispose_engine()
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    process, log_path = start_week2_api_server(port, env)
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
    api_env = api_environment()
    assert_strict_local_database_url(api_env["WORKSTREAM_DATABASE_URL"])
    os.environ.update(api_env)
    command.upgrade(alembic_config(), "head")
    asyncio.run(main(api_env))
