from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.checkers.compiler import (
    PRE_SUBMIT_COMPILER_VERSION,
    PreSubmitCheckerCompilerError,
    build_project_pre_submit_checker_spec,
    compile_effective_project_submission_artifact_policy,
    compile_project_pre_submit_checker_spec,
)
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.checkers.runner import canonical_artifact_manifest_hash
from app.modules.checkers.schemas import CheckerRoutingRecommendation
from app.modules.projects.models import PostSubmitCheckerPolicy
from app.modules.projects.post_submit_policy import (
    POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
    parse_locked_post_submit_checker_policy_body,
)
from app.modules.tasks.models import AuditEvent, EvidenceItem, Submission, WorkstreamTask
from tests.test_tasks import (
    auth_headers,
    complete_guide_payload,
    complete_submission_payload,
    create_active_project,
    create_policy_bundle_for_guide,
    create_started_task,
    load_post_submit_checker_policy,
    seed_worker_profile,
    set_dev_actor,
)


@pytest.fixture
def checker_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())

    config = alembic_config()
    with migration_lock():
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield postgres_database_url
        command.downgrade(config, "base")
    asyncio.run(db_session.dispose_engine())
    get_settings.cache_clear()


@pytest.fixture
async def checker_client(checker_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


def alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return config


async def task_side_effect_snapshot(task_id: str) -> dict:
    """Capture durable task-scoped rows that denied requests must not change."""
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
            "task_assigned_to": None if task is None else task.assigned_to,
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


def test_locked_post_submit_policy_parser_uses_persisted_body_hash() -> None:
    body = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": ["legacy_default_checker"],
        "required_checkers": ["project_required_checker"],
        "warning_checkers": [],
        "execution_checkers": ["legacy_default_checker", "project_required_checker"],
        "blocking_severities": ["high"],
    }
    policy_hash = canonical_json_hash(body)

    parsed = parse_locked_post_submit_checker_policy_body(
        body,
        project_id="project-id",
        guide_version="v1",
        policy_hash=policy_hash,
    )

    assert parsed.default_checkers == ["legacy_default_checker"]
    assert parsed.execution_checkers == [
        "legacy_default_checker",
        "project_required_checker",
    ]


def test_checker_models_are_registered_for_alembic_metadata() -> None:
    expected_tables = {"checker_runs", "checker_results"}

    assert expected_tables.issubset(Base.metadata.tables)
    assert db_models.CheckerRun is CheckerRun
    assert db_models.CheckerResult is CheckerResult


def test_checker_routing_recommendation_schema_uses_canonical_routing_tokens() -> None:
    adapter = TypeAdapter(CheckerRoutingRecommendation)

    assert adapter.validate_python("checker_retry") == "checker_retry"
    assert adapter.validate_python("task_setup_blocked") == "task_setup_blocked"
    with pytest.raises(ValidationError):
        adapter.validate_python("operator" + "_retry")


def test_checker_run_openapi_documents_worker_safe_public_response_schema() -> None:
    schema = create_app().openapi()
    public_schema = schema["components"]["schemas"]["CheckerRunPublicResponse"]
    public_properties = set(public_schema["properties"])
    forbidden_properties = {
        "trigger_source",
        "routing_recommendation",
        "outcome_source",
        "triggered_by",
        "trigger_reason",
        "audit_event_id",
        "locked_post_submit_checker_policy_id",
        "locked_post_submit_checker_policy_version",
        "locked_post_submit_checker_policy_hash",
        "locked_post_submit_checker_policy_body",
        "failure_message",
    }

    assert forbidden_properties.isdisjoint(public_properties)
    detail_schema = schema["paths"]["/api/v1/checker-runs/{checker_run_id}"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    list_schema = schema["paths"]["/api/v1/submissions/{submission_id}/checker-runs"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert detail_schema["$ref"] == "#/components/schemas/CheckerRunPublicResponse"
    assert list_schema["items"]["$ref"] == "#/components/schemas/CheckerRunPublicResponse"


async def test_checker_migration_creates_expected_tables(checker_database_env: str) -> None:
    async with db_session.get_engine().connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    assert {"checker_runs", "checker_results"}.issubset(table_names)


def test_checker_run_current_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in CheckerRun.__table__.indexes
        if index.name == "uq_checker_runs_current_per_submission"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "is_current_for_submission = true" in postgres_compiled


def test_checker_run_binds_to_locked_post_submit_policy_context() -> None:
    expected_constraints = {
        "fk_checker_runs_locked_post_submit_policy_hash": [
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
        "fk_checker_runs_submission_locked_post_submit_policy_hash": [
            "submission_id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
    }

    for constraint_name, local_columns in expected_constraints.items():
        constraint = next(
            constraint
            for constraint in CheckerRun.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )
        assert [column.name for column in constraint.columns] == local_columns
    assert "ck_checker_runs_post_submit_policy_lock_complete" in {
        constraint.name for constraint in CheckerRun.__table__.constraints
    }


def test_artifact_manifest_hash_is_stable_and_rejects_duplicates() -> None:
    first = [
        {"artifact": "b.txt", "hash": "sha256:b", "size_bytes": 2, "notes": None},
        {"hash": "sha256:a", "artifact": "a.txt", "notes": "main", "size_bytes": 1},
    ]
    second = [
        {"size_bytes": 1, "notes": "main", "artifact": "a.txt", "hash": "sha256:a"},
        {"notes": None, "artifact": "b.txt", "hash": "sha256:b", "size_bytes": 2},
    ]

    assert canonical_artifact_manifest_hash(first) == canonical_artifact_manifest_hash(second)

    with pytest.raises(ValueError, match="duplicate artifact"):
        canonical_artifact_manifest_hash(
            [
                {"artifact": "a.txt", "hash": "sha256:a"},
                {"artifact": "a.txt", "hash": "sha256:b"},
            ]
        )


def compiler_effective_policy() -> dict:
    """Return a minimal effective project policy for compiler tests."""
    default_policy = {
        "required_packet_fields": ["summary", "artifact_hash_manifest", "worker_attestation"],
        "required_artifacts": [],
        "required_evidence": [],
        "forbidden_artifacts": [
            {"pattern": ".env", "source": "workstream_default", "severity": "blocking"},
        ],
        "attestation_terms": ["original_work"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": None,
        "maximum_package_size_bytes": None,
        "packaging": {},
    }
    project_policy = {
        "schema_version": "project_submission_artifact_policy.v1",
        "required_artifacts": [
            {
                "key": "answer",
                "path": "outputs/answer.md",
                "hash_required": True,
                "required": True,
                "description": "Answer artifact.",
            }
        ],
        "required_evidence": [
            {
                "key": "work_evidence",
                "label": "Work evidence",
                "hash_required": True,
                "required": True,
                "description": "Evidence for the answer.",
            }
        ],
        "forbidden_artifacts": [
            {"pattern": "*.tmp", "reason": "Temporary files are not reviewable."},
        ],
        "attestation_terms": ["project_specific_originality"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": False},
    }
    return {
        "schema_version": "effective_project_submission_artifact_policy.v1",
        "merge_algorithm_version": "workstream_default_merge.v1",
        "workstream_default_policy": default_policy,
        "project_policy": project_policy,
        "required_packet_fields": default_policy["required_packet_fields"],
        "required_artifacts": project_policy["required_artifacts"],
        "required_evidence": project_policy["required_evidence"],
        "forbidden_artifacts": [
            *default_policy["forbidden_artifacts"],
            *project_policy["forbidden_artifacts"],
        ],
        "attestation_terms": [
            *default_policy["attestation_terms"],
            *project_policy["attestation_terms"],
        ],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": False},
    }


def test_pre_submit_compiler_emits_stable_approved_project_bundle() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "1" * 64

    first = compile_effective_project_submission_artifact_policy(
        effective_policy,
        effective_policy_hash,
    )
    second = compile_effective_project_submission_artifact_policy(
        effective_policy,
        effective_policy_hash,
    )

    assert first.compiler_version == PRE_SUBMIT_COMPILER_VERSION
    assert first.compiled_bundle == second.compiled_bundle
    assert first.compiled_bundle_hash == second.compiled_bundle_hash
    assert first.compiled_bundle["effective_policy_hash"] == effective_policy_hash
    assert {
        "validate_submission_packet",
        "require_manifest_field",
        "verify_hash",
        "require_file",
        "require_minimum_evidence",
        "forbid_artifact",
        "require_attestation",
    }.issubset({rule["primitive"] for rule in first.compiled_bundle["rules"]})
    assert "check_required_files" in first.checker_names
    assert "check_evidence_present" in first.checker_names


def test_pre_submit_compiler_rejects_unknown_primitive() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "2" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    spec["rules"].append(
        {
            "primitive": "run_arbitrary_python",
            "severity": "blocking",
            "policy_fields": ["required_artifacts"],
            "config": {},
        }
    )

    with pytest.raises(PreSubmitCheckerCompilerError, match="unknown primitive"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_omitted_required_artifact_coverage() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "3" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    spec["rules"] = [
        rule
        for rule in spec["rules"]
        if rule["primitive"] != "require_file"
    ]

    with pytest.raises(PreSubmitCheckerCompilerError, match="require_file"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_skipped_evidence_coverage() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "4" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "require_minimum_evidence":
            rule["config"]["evidence_keys"] = []

    with pytest.raises(PreSubmitCheckerCompilerError, match="required evidence"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_weakened_default_severity() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "5" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "verify_hash":
            rule["severity"] = "warning"

    with pytest.raises(PreSubmitCheckerCompilerError, match="weakens severity"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_escalated_warning_only_rule() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "c" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "warn_low_quality_generated_artifact":
            rule["severity"] = "blocking"

    with pytest.raises(PreSubmitCheckerCompilerError, match="warning-only"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_configured_warning_only_rule() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "c" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "warn_low_quality_generated_artifact":
            rule["config"] = {"threshold": "strict"}

    with pytest.raises(PreSubmitCheckerCompilerError, match="warning-only rule"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_canonical_json_hash_rejects_non_finite_numbers() -> None:
    with pytest.raises(ValueError):
        canonical_json_hash({"score": float("nan")})


def test_pre_submit_compiler_rejects_missing_workstream_defaults() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "6" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "forbid_artifact":
            rule["config"]["patterns"] = ["*.tmp"]

    with pytest.raises(PreSubmitCheckerCompilerError, match="forbidden artifacts"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_untraceable_policy_fields() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "7" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "require_file":
            rule["policy_fields"] = ["required_artifacts", "operator_override"]

    with pytest.raises(PreSubmitCheckerCompilerError, match="untraceable policy fields"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_weakened_size_limits() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "8" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "limit_file_size":
            rule["config"]["maximum_file_size_bytes"] = 2_000_000

    with pytest.raises(PreSubmitCheckerCompilerError, match="file size"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_weakened_package_limits() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "9" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "limit_package_size":
            rule["config"]["maximum_package_size_bytes"] = 6_000_000

    with pytest.raises(PreSubmitCheckerCompilerError, match="package size"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_weakened_packaging_config() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy["packaging"] = {
        "package_required": True,
        "allowed_package_formats": ["zip"],
    }
    effective_policy_hash = "sha256:" + "a" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "require_packaging":
            rule["config"]["package_required"] = False

    with pytest.raises(PreSubmitCheckerCompilerError, match="packaging"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_untraceable_extra_rules() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "b" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    spec["rules"].append(
        {
            "primitive": "require_packaging",
            "severity": "blocking",
            "policy_fields": ["packaging"],
            "config": {"package_required": True},
        }
    )

    with pytest.raises(PreSubmitCheckerCompilerError, match="untraceable primitive"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


async def lock_submission_and_get_auto_run(
    client: AsyncClient,
    submission_id: str,
) -> tuple[dict, dict]:
    """Lock a submission and return the automatic pre-review checker run.

    Args:
        client: API client using the current test actor.
        submission_id: Submission id to lock.

    Returns:
        Locked submission payload and the first automatic checker run payload.
    """
    locked = await client.post(
        f"/api/v1/submissions/{submission_id}/lock",
        headers=auth_headers(),
    )
    assert locked.status_code == 200, locked.text

    listed = await client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    runs = listed.json()
    assert len(runs) == 1
    assert runs[0]["trigger_source"] == "submission_locked"
    assert runs[0]["attempt_number"] == 1
    return locked.json(), runs[0]


async def create_checker_trial_project(
    client: AsyncClient,
    slug: str,
    required_checkers: list[str] | None = None,
) -> dict:
    """Create and activate a project guide for one checker trial scenario.

    Args:
        client: API client using the current project manager actor.
        slug: Unique project slug for this scenario.
        required_checkers: Optional locked required checker policy names.

    Returns:
        Created project response payload.
    """
    project_response = await client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "description": "Project for the Chunk 10 checker trial.",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    guide_payload = complete_guide_payload()
    if required_checkers is not None:
        guide_payload["post_submit_checker_policy"]["required_checkers"] = required_checkers
    guide_response = await client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    await create_policy_bundle_for_guide(client, project["id"], guide_response.json()["id"])
    activation_response = await client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_response.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 200, activation_response.text
    return project


async def test_pre_submit_check_returns_feedback_without_durable_run(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"].append(
        {
            "artifact": "answer.md",
            "hash": "sha256:duplicate",
            "size_bytes": 129,
            "notes": "duplicate",
        }
    )

    response = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": payload},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["authoritative"] is False
    assert body["status"] == "failed"
    assert body["eligible_to_submit"] is False
    result_names = {result["checker_name"] for result in body["results"]}
    assert {
        "check_submission_packet",
        "check_evidence_present",
        "check_evidence_integrity",
        "check_required_files",
        "check_forbidden_files",
        "check_confidentiality_attestation",
    }.issubset(result_names)
    assert any(
        result["checker_name"] == "check_evidence_integrity"
        and result["would_block_if_submitted"] is True
        for result in body["results"]
    )

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(CheckerRun.__table__.select())).all()
    assert rows == []


async def test_pre_submit_chunk8_matrix_flags_missing_evidence_and_warning(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["evidence_items"] = []
    payload["summary"] = "Completed the proof evaluation with a placeholder note."

    response = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": payload},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["authoritative"] is False
    assert body["status"] == "failed"
    assert body["eligible_to_submit"] is False
    result_by_name = {result["checker_name"]: result for result in body["results"]}
    assert result_by_name["check_evidence_present"]["status"] == "failed"
    assert result_by_name["check_evidence_present"]["would_block_if_submitted"] is True
    assert result_by_name["check_required_files"]["status"] == "passed"
    assert result_by_name["check_forbidden_files"]["status"] == "passed"
    assert result_by_name["check_confidentiality_attestation"]["status"] == "passed"
    assert result_by_name["check_low_quality_generated_artifacts"]["status"] == "warning"
    assert (
        result_by_name["check_low_quality_generated_artifacts"]["would_block_if_submitted"]
        is False
    )

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(CheckerRun.__table__.select())).all()
    assert rows == []


async def test_locked_submission_checker_run_persists_results_and_allows_review(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["status"] == "completed"
    assert body["trigger_source"] == "submission_locked"
    assert body["routing_recommendation"] == "allow_review"
    assert body["outcome_source"] == "none"
    assert body["submission_version"] == 1
    assert body["locked_checker_policy_version"] == "v1"
    expected_post_submit_policy = await load_post_submit_checker_policy(project["id"])
    assert body["locked_post_submit_checker_policy_id"] == expected_post_submit_policy["id"]
    assert body["locked_post_submit_checker_policy_version"] == "v1"
    assert body["locked_post_submit_checker_policy_hash"] == expected_post_submit_policy["policy_hash"]
    assert body["artifact_manifest_hash"].startswith("sha256:")
    assert body["audit_event_id"]
    assert body["passed_count"] >= 8
    assert body["blocking_count"] == 0
    assert {
        "check_submission_packet",
        "check_policy_context_present",
        "check_evidence_present",
        "check_evidence_integrity",
        "check_required_files",
        "check_forbidden_files",
        "check_confidentiality_attestation",
        "check_low_quality_generated_artifacts",
    }.issubset({result["checker_name"] for result in body["results"]})

    listed = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [body["id"]]

    async with db_session.get_session_factory()() as session:
        audit = await session.get(AuditEvent, body["audit_event_id"])
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, created.json()["id"])
        checker_run = await session.get(CheckerRun, body["id"])
    assert audit is not None
    assert audit.event_type == "checker_run_triggered"
    assert audit.entity_id == created.json()["id"]
    assert audit.reason == "submission locked pre-review gate"
    assert audit.event_payload["submission_version"] == 1
    assert audit.event_payload["trigger_source"] == "submission_locked"
    assert (
        audit.event_payload["locked_post_submit_checker_policy_hash"]
        == expected_post_submit_policy["policy_hash"]
    )
    assert task is not None
    assert task.status == "review_pending"
    assert submission is not None
    assert checker_run is not None
    assert task.locked_post_submit_checker_policy_id == expected_post_submit_policy["id"]
    assert submission.locked_post_submit_checker_policy_id == expected_post_submit_policy["id"]
    assert checker_run.locked_post_submit_checker_policy_id == expected_post_submit_policy["id"]
    assert (
        task.locked_post_submit_checker_policy_hash
        == submission.locked_post_submit_checker_policy_hash
        == checker_run.locked_post_submit_checker_policy_hash
        == expected_post_submit_policy["policy_hash"]
    )
    audit_response = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit_response.status_code == 200, audit_response.text
    audit_events = {event["event_type"]: event for event in audit_response.json()}
    assert "pre_review_gate_started" in audit_events
    assert "pre_review_gate_passed" in audit_events
    assert audit_events["pre_review_gate_started"]["event_payload"]["trigger_source"] == (
        "submission_locked"
    )
    assert audit_events["pre_review_gate_passed"]["event_payload"]["trigger_source"] == (
        "submission_locked"
    )


async def test_database_rejects_missing_submission_post_submit_policy_context(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, created.json()["id"])
        assert submission is not None
        submission.locked_post_submit_checker_policy_id = None
        submission.locked_post_submit_checker_policy_version = None
        submission.locked_post_submit_checker_policy_hash = None
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, created.json()["id"])
        runs = (
            await session.execute(
                select(CheckerRun).where(CheckerRun.submission_id == created.json()["id"])
            )
        ).scalars().all()
        results = (
            await session.execute(
                select(CheckerResult).where(CheckerResult.submission_id == created.json()["id"])
            )
        ).scalars().all()
    assert task is not None
    assert task.status == "submitted"
    assert submission is not None
    assert submission.locked_at is None
    assert runs == []
    assert results == []


async def test_checker_run_uses_locked_post_submit_policy_body_after_setup_mutation(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, created.json()["id"])
        assert submission is not None
        locked_body = dict(submission.locked_post_submit_checker_policy_body or {})
        policy = await session.scalar(
            select(PostSubmitCheckerPolicy).where(
                PostSubmitCheckerPolicy.project_id == project["id"],
                PostSubmitCheckerPolicy.guide_version == "v1",
            )
        )
        assert policy is not None
        policy.required_checkers = [
            "check_policy_context_present",
            "check_acceptance_criteria_present",
        ]
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/lock",
        headers=auth_headers(),
    )

    assert locked.status_code == 200, locked.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, created.json()["id"])
        runs = (
            await session.execute(
                select(CheckerRun).where(CheckerRun.submission_id == created.json()["id"])
            )
        ).scalars().all()
        results = (
            await session.execute(
                select(CheckerResult).where(CheckerResult.submission_id == created.json()["id"])
            )
        ).scalars().all()
    assert task is not None
    assert task.status == "review_pending"
    assert submission is not None
    assert submission.locked_at is not None
    assert submission.locked_post_submit_checker_policy_body == locked_body
    assert len(runs) == 1
    assert runs[0].locked_post_submit_checker_policy_body == locked_body
    assert "check_acceptance_criteria_present" not in locked_body["required_checkers"]
    assert "check_acceptance_criteria_present" not in locked_body["execution_checkers"]
    assert "check_evidence_present" in locked_body["default_checkers"]
    assert "check_evidence_present" in locked_body["execution_checkers"]
    assert "check_required_files" in locked_body["execution_checkers"]
    assert "check_acceptance_criteria_present" not in {
        result.checker_name for result in results
    }
    assert results != []


async def test_lock_submission_rejects_malformed_locked_post_submit_policy_body_without_side_effects(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, created.json()["id"])
        assert task is not None
        assert submission is not None
        corrupted_body = dict(submission.locked_post_submit_checker_policy_body or {})
        corrupted_body["required_checkers"] = [
            "check_policy_context_present",
            "check_evidence_present",
        ]
        task.locked_post_submit_checker_policy_body = corrupted_body
        submission.locked_post_submit_checker_policy_body = corrupted_body
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/lock",
        headers=auth_headers(),
    )

    assert locked.status_code == 422
    assert "locked post-submit checker policy" in locked.json()["detail"]
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, created.json()["id"])
        runs = (
            await session.execute(
                select(CheckerRun).where(CheckerRun.submission_id == created.json()["id"])
            )
        ).scalars().all()
        results = (
            await session.execute(
                select(CheckerResult).where(CheckerResult.submission_id == created.json()["id"])
            )
        ).scalars().all()
        audit_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id.in_([started_task["id"], created.json()["id"]])
                )
            )
        ).scalars().all()

    assert task is not None
    assert task.status == "submitted"
    assert submission is not None
    assert submission.locked_at is None
    assert runs == []
    assert results == []
    assert "submission_locked" not in {event.event_type for event in audit_events}
    assert "checker_run_triggered" not in {event.event_type for event in audit_events}


async def test_database_rejects_mismatched_submission_post_submit_policy_context(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, created.json()["id"])
        assert submission is not None
        submission.locked_post_submit_checker_policy_hash = "sha256:" + "0" * 64
        with pytest.raises(IntegrityError):
            await session.commit()

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, created.json()["id"])
        runs = (
            await session.execute(
                select(CheckerRun).where(CheckerRun.submission_id == created.json()["id"])
            )
        ).scalars().all()
        results = (
            await session.execute(
                select(CheckerResult).where(CheckerResult.submission_id == created.json()["id"])
            )
        ).scalars().all()
    assert task is not None
    assert task.status == "submitted"
    assert submission is not None
    assert submission.locked_at is None
    assert submission.locked_post_submit_checker_policy_hash != "sha256:" + "0" * 64
    assert runs == []
    assert results == []


async def test_locked_submission_checker_run_enforces_required_evidence_key(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        evidence = await session.scalar(
            select(EvidenceItem).where(EvidenceItem.submission_id == created.json()["id"])
        )
        assert evidence is not None
        evidence.metadata_json = {"policy_key": "other_evidence"}
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    evidence_result = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_evidence_present"
    )
    assert evidence_result["status"] == "failed"
    assert "checker_log" in evidence_result["metadata"]["missing_required_evidence"]
    assert body["routing_recommendation"] == "needs_revision"


async def test_locked_submission_checker_run_enforces_project_attestation_terms(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, created.json()["id"])
        assert submission is not None
        submission.worker_attestation = (
            "I attest this submission contains no confidential client data, credentials, secrets, "
            "tokens, passwords, API keys, private source material, source code, copied platform "
            "artifacts, or copied platform content."
        )
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    attestation_result = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_confidentiality_attestation"
    )
    assert attestation_result["status"] == "failed"
    assert "original_work" in attestation_result["metadata"]["missing_attestation_terms"]
    assert "task_test_originality" in attestation_result["metadata"]["missing_attestation_terms"]
    assert body["routing_recommendation"] == "needs_revision"


async def test_checker_run_retry_supersedes_previous_current_run(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, first = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    second = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "retry run"},
    )

    assert second.status_code == 200, second.text
    assert second.json()["attempt_number"] == 2
    assert second.json()["supersedes_checker_run_id"] == first["id"]
    listed = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert [item["attempt_number"] for item in listed.json()] == [1, 2]
    assert listed.json()[0]["is_current_for_submission"] is False
    assert listed.json()[1]["is_current_for_submission"] is True


async def test_duplicate_artifact_fails_before_submission_row(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"].append(
        {
            "artifact": "answer.md",
            "hash": "sha256:duplicate",
            "size_bytes": 129,
            "notes": "duplicate",
        }
    )
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 422, created.text
    detail = created.json()
    assert detail["code"] == "pre_submission_checker_failed"
    duplicate_result = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_evidence_integrity"
    )
    assert duplicate_result["status"] == "failed"
    assert duplicate_result["would_block_if_submitted"] is True
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        checker_runs = (await session.execute(select(CheckerRun))).scalars().all()
    assert task is not None
    assert task.status == "in_progress"
    assert submissions == []
    assert checker_runs == []


async def test_chunk8_missing_required_file_fails_pre_submit_without_submission(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"] = [
        {
            "artifact": "other.md",
            "hash": "sha256:other-v1",
            "size_bytes": 128,
            "notes": "wrong artifact",
        }
    ]
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 422, created.text
    detail = created.json()
    assert detail["code"] == "pre_submission_checker_failed"
    required_files = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_required_files"
    )
    assert required_files["status"] == "failed"
    assert required_files["would_block_if_submitted"] is True
    assert "missing required artifact files" in required_files["worker_message"]


async def test_chunk8_default_blocking_checker_survives_empty_blocking_severities(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Empty Blocking Severity Project",
            "slug": "empty-blocking-severity-project",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
    guide_payload["post_submit_checker_policy"]["required_checkers"] = ["check_policy_context_present"]
    guide_payload["post_submit_checker_policy"]["blocking_severities"] = []
    guide_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    await create_policy_bundle_for_guide(
        checker_client,
        project["id"],
        guide_response.json()["id"],
    )
    activation_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_response.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 200, activation_response.text
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"] = [
        {
            "artifact": "other.md",
            "hash": "sha256:other-v1",
            "size_bytes": 128,
            "notes": "wrong artifact",
        }
    ]
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 422, created.text
    detail = created.json()
    assert detail["code"] == "pre_submission_checker_failed"
    required_files = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_required_files"
    )
    assert required_files["status"] == "failed"
    assert required_files["would_block_if_submitted"] is True


async def test_chunk8_forbidden_file_blocks_without_worker_path_leakage(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"].append(
        {
            "artifact": "secrets/.env",
            "hash": "sha256:env-v1",
            "size_bytes": 64,
            "notes": "should be removed",
        }
    )
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 422, created.text
    detail = created.json()
    assert detail["code"] == "pre_submission_checker_failed"
    forbidden = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_forbidden_files"
    )
    assert forbidden["status"] == "failed"
    assert forbidden["would_block_if_submitted"] is True
    assert ".env" not in forbidden["worker_message"]
    assert "secrets/" not in forbidden["worker_message"]
    assert "local://" not in forbidden["worker_message"]


async def test_chunk8_confidentiality_attestation_blocks_generic_text(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["worker_attestation"] = "ok"
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 422, created.text
    detail = created.json()
    assert detail["code"] == "pre_submission_checker_failed"
    attestation = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_confidentiality_attestation"
    )
    assert attestation["status"] == "failed"
    assert attestation["would_block_if_submitted"] is True
    assert "confidentiality attestation" in attestation["worker_message"]


async def test_chunk8_low_quality_generated_artifacts_warns_without_blocking(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["summary"] = "Completed the proof evaluation with a placeholder note to revise."
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "allow_review"
    assert body["outcome_source"] == "none"
    assert body["warning_count"] >= 1
    low_quality = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_low_quality_generated_artifacts"
    )
    assert low_quality["status"] == "warning"
    assert low_quality["blocks_review"] is False


async def test_checker_caused_revision_resubmits_fixed_version_through_api(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_checker_trial_project(
        checker_client,
        "checker-caused-revision-project",
        required_checkers=["check_low_quality_generated_artifacts"],
    )
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
    v1_payload["summary"] = "Completed the proof evaluation with TODO placeholder notes."
    precheck_v1 = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": v1_payload},
    )
    assert precheck_v1.status_code == 200, precheck_v1.text
    assert precheck_v1.json()["eligible_to_submit"] is True

    v1 = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v1_payload,
    )
    assert v1.status_code == 201, v1.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, v1_run = await lock_submission_and_get_auto_run(checker_client, v1.json()["id"])
    assert v1_run["routing_recommendation"] == "needs_revision"
    assert v1_run["outcome_source"] == "auto_checker"
    low_quality = next(
        result
        for result in v1_run["results"]
        if result["checker_name"] == "check_low_quality_generated_artifacts"
    )
    assert low_quality["status"] == "failed"
    assert low_quality["blocks_review"] is True
    assert low_quality["worker_message"]
    assert low_quality["worker_suggested_fix"]

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        v1_submission = await session.get(Submission, v1.json()["id"])
        gate_events = (
            (
                await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.entity_type == "task", AuditEvent.entity_id == started_task["id"])
                    .order_by(AuditEvent.created_at)
                )
            )
            .scalars()
            .all()
        )
        pre_submit_policy_id = task.locked_pre_submit_checker_policy_id if task else None
        pre_submit_bundle_hash = task.locked_pre_submit_checker_bundle_hash if task else None
        post_submit_policy_hash = task.locked_post_submit_checker_policy_hash if task else None
        post_submit_policy_body = dict(task.locked_post_submit_checker_policy_body or {}) if task else {}
    assert task is not None
    assert task.status == "needs_revision"
    assert v1_submission is not None
    assert v1_submission.version == 1
    assert v1_submission.package_hash == "sha256:package-v1"
    assert ("submitted", "evaluation_pending") in {
        (event.from_status, event.to_status) for event in gate_events
    }
    assert ("evaluation_pending", "needs_revision") in {
        (event.from_status, event.to_status) for event in gate_events
    }
    v1_revision_events = [
        event for event in gate_events if event.event_type == "pre_review_gate_needs_revision"
    ]
    assert v1_revision_events
    assert any(
        event.event_payload.get("checker_run_id") == v1_run["id"]
        and event.event_payload.get("outcome_source") == "auto_checker"
        and event.event_payload.get("review_decision_id") is None
        for event in v1_revision_events
    )

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    worker_run = await checker_client.get(
        f"/api/v1/checker-runs/{v1_run['id']}",
        headers=auth_headers(),
    )
    assert worker_run.status_code == 200, worker_run.text
    worker_body = worker_run.json()
    assert "routing_recommendation" not in worker_body
    assert "outcome_source" not in worker_body
    worker_low_quality = next(
        result
        for result in worker_body["results"]
        if result["checker_name"] == "check_low_quality_generated_artifacts"
    )
    assert worker_low_quality["id"]
    assert worker_low_quality["status"] == "failed"
    assert worker_low_quality["severity"] == "high"
    assert worker_low_quality["worker_message"]
    assert worker_low_quality["worker_suggested_fix"]
    assert "routing_recommendation" not in worker_run.text
    assert "outcome_source" not in worker_run.text
    worker_audit = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert worker_audit.status_code == 200, worker_audit.text
    worker_gate_events = [
        event
        for event in worker_audit.json()
        if event["event_type"] == "post_submit_checks_processing"
    ]
    assert worker_gate_events
    assert all(event["actor_id"] is None for event in worker_gate_events)
    assert all(event["external_subject"] is None for event in worker_gate_events)
    assert all(event["external_issuer"] is None for event in worker_gate_events)
    assert all(event["actor_roles"] == [] for event in worker_gate_events)
    assert all(event["auth_source"] is None for event in worker_gate_events)
    assert all(event["is_dev_auth"] is None for event in worker_gate_events)
    assert "pre_review_gate_needs_revision" not in worker_audit.text
    assert "outcome_source" not in worker_audit.text
    assert "review_decision_id" not in worker_audit.text

    await seed_worker_profile("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    denied_before = await task_side_effect_snapshot(started_task["id"])
    denied_precheck = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": complete_submission_payload("sha256:intruder-package")},
    )
    denied_submit = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload("sha256:intruder-package"),
    )
    denied_submissions = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    denied_run = await checker_client.get(
        f"/api/v1/checker-runs/{v1_run['id']}",
        headers=auth_headers(),
    )
    denied_audit = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert denied_precheck.status_code == 404
    assert denied_submit.status_code == 404
    assert denied_submissions.status_code == 404
    assert denied_run.status_code == 404
    assert denied_audit.status_code == 404
    assert await task_side_effect_snapshot(started_task["id"]) == denied_before

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    v2_payload = complete_submission_payload("sha256:package-v2")
    v2_payload["summary"] = "Completed the proof evaluation with task-specific final notes."
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"
    precheck_v2 = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": v2_payload},
    )
    assert precheck_v2.status_code == 200, precheck_v2.text
    assert precheck_v2.json()["eligible_to_submit"] is True
    v2 = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v2_payload,
    )
    assert v2.status_code == 201, v2.text
    assert v2.json()["version"] == 2
    assert v2.json()["supersedes_submission_id"] == v1.json()["id"]

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    stale_run = await checker_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "stale v1 retry"},
    )
    assert stale_run.status_code == 409
    _, v2_run = await lock_submission_and_get_auto_run(checker_client, v2.json()["id"])
    assert v2_run["routing_recommendation"] == "allow_review"
    assert v2_run["outcome_source"] == "none"

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        persisted_v1 = await session.get(Submission, v1.json()["id"])
        persisted_v2 = await session.get(Submission, v2.json()["id"])
        task_events = (
            (
                await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.entity_type == "task", AuditEvent.entity_id == started_task["id"])
                    .order_by(AuditEvent.created_at)
                )
            )
            .scalars()
            .all()
        )
    assert task is not None
    assert task.status == "review_pending"
    assert task.locked_pre_submit_checker_policy_id == pre_submit_policy_id
    assert task.locked_pre_submit_checker_bundle_hash == pre_submit_bundle_hash
    assert task.locked_post_submit_checker_policy_hash == post_submit_policy_hash
    assert task.locked_post_submit_checker_policy_body == post_submit_policy_body
    assert persisted_v1 is not None
    assert persisted_v1.version == 1
    assert persisted_v1.package_hash == "sha256:package-v1"
    assert persisted_v2 is not None
    assert persisted_v2.version == 2
    assert persisted_v2.supersedes_submission_id == persisted_v1.id
    assert ("needs_revision", "submitted") in {
        (event.from_status, event.to_status) for event in task_events
    }
    assert ("submitted", "evaluation_pending") in {
        (event.from_status, event.to_status) for event in task_events
    }
    assert ("evaluation_pending", "review_pending") in {
        (event.from_status, event.to_status) for event in task_events
    }


async def test_chunk8_task_setup_blocked_takes_priority_over_worker_revision(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Task Setup Checker Project",
            "slug": "task-setup-checker-project",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
    guide_payload["post_submit_checker_policy"]["required_checkers"] = [
        "check_acceptance_criteria_present"
    ]
    guide_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    await create_policy_bundle_for_guide(
        checker_client,
        project["id"],
        guide_response.json()["id"],
    )
    activation_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_response.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 200, activation_response.text
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = None
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "task_setup_blocked"
    assert body["outcome_source"] == "auto_checker"
    setup_result = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_acceptance_criteria_present"
    )
    assert setup_result["status"] == "failed"
    assert setup_result["blocks_review"] is True
    assert setup_result["worker_visible"] is False
    assert "worker_message" not in setup_result
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "evaluation_pending"
    manager_audit = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert manager_audit.status_code == 200, manager_audit.text
    manager_events = {event["event_type"]: event for event in manager_audit.json()}
    assert "pre_review_gate_blocked" in manager_events
    assert manager_events["pre_review_gate_blocked"]["event_payload"]["routing_recommendation"] == (
        "task_setup_blocked"
    )
    assert manager_events["pre_review_gate_blocked"]["event_payload"]["trigger_source"] == (
        "submission_locked"
    )

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    worker_read = await checker_client.get(
        f"/api/v1/checker-runs/{body['id']}",
        headers=auth_headers(),
    )
    assert worker_read.status_code == 200, worker_read.text
    worker_body = worker_read.json()
    assert "routing_recommendation" not in worker_body
    assert "outcome_source" not in worker_body
    assert worker_body["passed_count"] == 0
    assert worker_body["warning_count"] == 0
    assert worker_body["failed_count"] == 0
    assert worker_body["blocking_count"] == 0
    assert worker_body["results"] == []
    assert "task_setup_blocked" not in worker_read.text
    assert "acceptance_criteria" not in worker_read.text

    worker_audit = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert worker_audit.status_code == 200, worker_audit.text
    assert "task_setup_blocked" not in worker_audit.text
    assert "acceptance_criteria" not in worker_audit.text
    assert "routing_recommendation" not in worker_audit.text
    assert "checker_run_id" not in worker_audit.text
    worker_gate_events = [
        event
        for event in worker_audit.json()
        if event["event_type"] == "post_submit_checks_processing"
    ]
    assert worker_gate_events
    assert all(event["actor_id"] is None for event in worker_gate_events)
    assert all(event["external_subject"] is None for event in worker_gate_events)
    assert all(event["external_issuer"] is None for event in worker_gate_events)
    assert all(event["actor_roles"] == [] for event in worker_gate_events)
    assert all(event["auth_source"] is None for event in worker_gate_events)
    assert all(event["is_dev_auth"] is None for event in worker_gate_events)

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = "Worker output must satisfy the project rubric."
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    retry = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "task setup repaired"},
    )
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["attempt_number"] == 2
    assert retry_body["supersedes_checker_run_id"] == body["id"]
    assert retry_body["routing_recommendation"] == "allow_review"
    assert retry_body["trigger_source"] == "manual_checker_trigger"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "review_pending"


async def test_chunk10_checker_trial_runs_sample_submissions_through_real_api(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trial_cases = [
        {
            "slug": "chunk10-clean-packet",
            "worker_subject": "chunk10-worker-clean",
            "payload": complete_submission_payload(),
            "create_status": 201,
            "route": "allow_review",
            "task_status": "review_pending",
            "checker_name": "check_submission_packet",
            "checker_status": "passed",
            "worker_route": "allow_review",
        },
        {
            "slug": "chunk10-missing-required-file",
            "worker_subject": "chunk10-worker-missing-file",
            "payload": {
                **complete_submission_payload(),
                "artifact_hash_manifest": [
                    {
                        "artifact": "other.md",
                        "hash": "sha256:other-v1",
                        "size_bytes": 128,
                        "notes": "wrong artifact",
                    }
                ],
            },
            "create_status": 422,
            "route": "pre_submission_checker_failed",
            "checker_name": "check_required_files",
            "checker_status": "failed",
        },
        {
            "slug": "chunk10-forbidden-file-path",
            "worker_subject": "chunk10-worker-forbidden-file",
            "payload": {
                **complete_submission_payload(),
                "artifact_hash_manifest": [
                    *complete_submission_payload()["artifact_hash_manifest"],
                    {
                        "artifact": "secrets/.env",
                        "hash": "sha256:env-v1",
                        "size_bytes": 64,
                        "notes": "must be removed",
                    },
                ],
            },
            "create_status": 422,
            "route": "pre_submission_checker_failed",
            "checker_name": "check_forbidden_files",
            "checker_status": "failed",
        },
        {
            "slug": "chunk10-weak-confidentiality",
            "worker_subject": "chunk10-worker-attestation",
            "payload": {
                **complete_submission_payload(),
                "worker_attestation": "ok",
            },
            "create_status": 422,
            "route": "pre_submission_checker_failed",
            "checker_name": "check_confidentiality_attestation",
            "checker_status": "failed",
        },
    ]

    for case in trial_cases:
        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
        project = await create_checker_trial_project(checker_client, case["slug"])
        started_task = await create_started_task(
            checker_client,
            project["id"],
            monkeypatch,
            subject=case["worker_subject"],
        )
        created = await checker_client.post(
            f"/api/v1/tasks/{started_task['id']}/submissions",
            headers=auth_headers(),
            json=case["payload"],
        )
        assert created.status_code == case["create_status"], created.text
        if case["create_status"] == 422:
            detail = created.json()
            assert detail["code"] == case["route"]
            target_result = next(
                result
                for result in detail["details"]["results"]
                if result["checker_name"] == case["checker_name"]
            )
            assert target_result["status"] == case["checker_status"]
            async with db_session.get_session_factory()() as session:
                submissions = (
                    await session.execute(
                        select(Submission).where(Submission.task_id == started_task["id"])
                    )
                ).scalars().all()
                task = await session.get(WorkstreamTask, started_task["id"])
            assert submissions == []
            assert task is not None
            assert task.status == "in_progress"
            continue

        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
        _, manager_run = await lock_submission_and_get_auto_run(
            checker_client,
            created.json()["id"],
        )
        assert manager_run["routing_recommendation"] == case["route"]
        target_result = next(
            result
            for result in manager_run["results"]
            if result["checker_name"] == case["checker_name"]
        )
        assert target_result["status"] == case["checker_status"]

        async with db_session.get_session_factory()() as session:
            task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        assert task.status == case["task_status"]

        set_dev_actor(monkeypatch, roles="worker", subject=case["worker_subject"])
        worker_read = await checker_client.get(
            f"/api/v1/checker-runs/{manager_run['id']}",
            headers=auth_headers(),
        )
        assert worker_read.status_code == 200, worker_read.text
        worker_body = worker_read.json()
        assert "routing_recommendation" not in worker_body
        assert "outcome_source" not in worker_body
        worker_result = next(
            result
            for result in worker_body["results"]
            if result["checker_name"] == case["checker_name"]
        )
        assert worker_result["status"] == case["checker_status"]
        assert worker_result["metadata"] == {}
        if case["route"] == "needs_revision":
            assert worker_result["worker_message"]
            assert worker_result["worker_suggested_fix"]
        if case["checker_name"] == "check_forbidden_files":
            assert ".env" not in worker_read.text
            assert "secrets/" not in worker_read.text
            assert "local://" not in worker_read.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    project = await create_checker_trial_project(
        checker_client,
        "chunk10-task-setup-defect",
        required_checkers=["check_acceptance_criteria_present"],
    )
    started_task = await create_started_task(
        checker_client,
        project["id"],
        monkeypatch,
        subject="chunk10-worker-task-setup",
    )
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = None
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, blocked_run = await lock_submission_and_get_auto_run(
        checker_client,
        created.json()["id"],
    )
    assert blocked_run["routing_recommendation"] == "task_setup_blocked"
    setup_result = next(
        result
        for result in blocked_run["results"]
        if result["checker_name"] == "check_acceptance_criteria_present"
    )
    assert setup_result["status"] == "failed"
    assert setup_result["worker_visible"] is False

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "evaluation_pending"

    set_dev_actor(monkeypatch, roles="worker", subject="chunk10-worker-task-setup")
    worker_blocked_read = await checker_client.get(
        f"/api/v1/checker-runs/{blocked_run['id']}",
        headers=auth_headers(),
    )
    assert worker_blocked_read.status_code == 200, worker_blocked_read.text
    worker_blocked_body = worker_blocked_read.json()
    assert "trigger_source" not in worker_blocked_body
    assert "routing_recommendation" not in worker_blocked_body
    assert "outcome_source" not in worker_blocked_body
    assert worker_blocked_body["results"] == []
    assert "task_setup_blocked" not in worker_blocked_read.text
    assert "submission_locked" not in worker_blocked_read.text
    assert "manual_checker_trigger" not in worker_blocked_read.text
    assert "acceptance_criteria" not in worker_blocked_read.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = "Worker output must satisfy the project rubric."
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    retry = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "task setup repaired during Chunk 10 trial"},
    )
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["attempt_number"] == 2
    assert retry_body["supersedes_checker_run_id"] == blocked_run["id"]
    assert retry_body["routing_recommendation"] == "allow_review"
    assert retry_body["trigger_source"] == "manual_checker_trigger"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "review_pending"


async def test_worker_can_read_only_worker_visible_checker_result_fields(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, run = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    read = await checker_client.get(
        f"/api/v1/checker-runs/{run['id']}",
        headers=auth_headers(),
    )

    assert read.status_code == 200, read.text
    body = read.json()
    assert "trigger_source" not in body
    assert "routing_recommendation" not in body
    assert "outcome_source" not in body
    assert "failure_message" not in body
    assert "triggered_by" not in body
    assert "triggered_by_subject" not in body
    assert "triggered_by_issuer" not in body
    assert "trigger_auth_source" not in body
    assert "trigger_reason" not in body
    assert "audit_event_id" not in body
    assert "locked_guide_version" not in body
    assert "locked_checker_policy_version" not in body
    assert "locked_post_submit_checker_policy_id" not in body
    assert "locked_post_submit_checker_policy_version" not in body
    assert "locked_post_submit_checker_policy_hash" not in body
    assert "locked_post_submit_checker_policy_body" not in body
    assert "locked_review_policy_version" not in body
    assert "locked_revision_policy_version" not in body
    assert "locked_payment_policy_version" not in body
    assert "package_hash" not in body
    assert "artifact_hash_manifest" not in body
    assert "artifact_manifest_hash" not in body
    assert "submission_locked" not in read.text
    assert "manual_checker_trigger" not in read.text
    assert body["results"]
    assert all("message" not in result for result in body["results"])
    assert all(result["metadata"] == {} for result in body["results"])
    assert all(result["worker_visible"] is True for result in body["results"])

    listed = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    listed_body = listed.json()
    assert len(listed_body) == 1
    listed_run = listed_body[0]
    assert listed_run["id"] == run["id"]
    assert "trigger_source" not in listed_run
    assert "routing_recommendation" not in listed_run
    assert "outcome_source" not in listed_run
    assert "failure_message" not in listed_run
    assert "triggered_by" not in listed_run
    assert "trigger_reason" not in listed_run
    assert "audit_event_id" not in listed_run
    assert "locked_post_submit_checker_policy_id" not in listed_run
    assert "locked_post_submit_checker_policy_version" not in listed_run
    assert "locked_post_submit_checker_policy_hash" not in listed_run
    assert "locked_post_submit_checker_policy_body" not in listed_run
    assert "artifact_hash_manifest" not in listed_run
    assert "artifact_manifest_hash" not in listed_run
    assert "submission_locked" not in listed.text
    assert "manual_checker_trigger" not in listed.text


async def test_worker_cannot_see_hidden_checker_results(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, run = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    async with db_session.get_session_factory()() as session:
        session.add(
            CheckerResult(
                id="hidden-result",
                checker_run_id=run["id"],
                task_id=started_task["id"],
                submission_id=created.json()["id"],
                checker_name="internal_hidden_checker",
                status="failed",
                severity="high",
                blocks_review=True,
                message="internal stack and private path",
                worker_message=None,
                worker_suggested_fix=None,
                worker_evidence_refs=[],
                worker_visible=False,
                metadata_json={"private_path": "local://private/hidden"},
            )
        )
        await session.commit()

    manager_read = await checker_client.get(
        f"/api/v1/checker-runs/{run['id']}",
        headers=auth_headers(),
    )
    assert manager_read.status_code == 200, manager_read.text
    assert "internal_hidden_checker" in {
        result["checker_name"] for result in manager_read.json()["results"]
    }

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    worker_read = await checker_client.get(
        f"/api/v1/checker-runs/{run['id']}",
        headers=auth_headers(),
    )
    assert worker_read.status_code == 200, worker_read.text
    worker_names = {result["checker_name"] for result in worker_read.json()["results"]}
    assert "internal_hidden_checker" not in worker_names


async def test_checker_endpoints_reject_unassigned_worker_and_fake_result_payloads(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["status"] = "completed"
    payload["routing_recommendation"] = "allow_review"
    payload["outcome_source"] = "auto_checker"
    payload["trigger_source"] = "submission_locked"
    payload["review_decision_id"] = "fake-review-decision"
    payload["checker_retry"] = True
    payload["task_setup_blocked"] = True
    payload["allow_review"] = True
    payload["review_decision"] = "accept"
    payload["locked_guide_version"] = "v999"
    payload["locked_pre_submit_checker_policy_id"] = "fake-policy"
    payload["locked_pre_submit_checker_bundle_hash"] = "sha256:fake"
    payload["results"] = [{"checker_name": "fake", "status": "passed"}]

    rejected_payload_snapshot = await task_side_effect_snapshot(started_task["id"])
    fake_precheck = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": payload},
    )
    assert fake_precheck.status_code == 422
    fake_submission = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert fake_submission.status_code == 422
    assert await task_side_effect_snapshot(started_task["id"]) == rejected_payload_snapshot

    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    fake_run = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={
            "trigger_reason": "manual checker dry run",
            "status": "completed",
            "routing_recommendation": "allow_review",
            "results": [{"checker_name": "fake", "status": "passed"}],
        },
    )
    assert fake_run.status_code == 422
    blank_reason = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "   "},
    )
    assert blank_reason.status_code == 422

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    worker_run = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "worker tries to trigger"},
    )
    assert worker_run.status_code == 403

    await seed_worker_profile("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    denied = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": complete_submission_payload()},
    )
    assert denied.status_code == 404

    set_dev_actor(monkeypatch, roles="auditor", subject="auditor-subject")
    no_role_existing = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    no_role_missing = await checker_client.get(
        "/api/v1/submissions/00000000-0000-0000-0000-000000000000/checker-runs",
        headers=auth_headers(),
    )
    assert no_role_existing.status_code == 403
    assert no_role_missing.status_code == 403

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(select(CheckerRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].trigger_source == "submission_locked"


async def test_stale_locked_submission_cannot_receive_checker_run(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    first_payload = complete_submission_payload()
    first = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=first_payload,
    )
    assert first.status_code == 201, first.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_first = await checker_client.post(
        f"/api/v1/submissions/{first.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert locked_first.status_code == 200, locked_first.text
    first_runs = await checker_client.get(
        f"/api/v1/submissions/{first.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert first_runs.status_code == 200, first_runs.text
    assert first_runs.json()[0]["routing_recommendation"] == "allow_review"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        await session.commit()
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    second_payload = complete_submission_payload("sha256:package-v2")
    second_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"
    second = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=second_payload,
    )
    assert second.status_code == 201, second.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    stale_run = await checker_client.post(
        f"/api/v1/submissions/{first.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "stale run"},
    )

    assert stale_run.status_code == 409
    assert "latest submission" in stale_run.json()["detail"]

    _, second_run = await lock_submission_and_get_auto_run(checker_client, second.json()["id"])
    assert second_run["submission_version"] == 2
    assert second_run["trigger_source"] == "submission_locked"
    assert second_run["routing_recommendation"] == "allow_review"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "review_pending"

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(
                select(Submission).where(Submission.id == first.json()["id"])
            )
        ).scalars().all()
    assert submissions[0].version == 1


@pytest.mark.parametrize(
    "old_checker_name",
    ["check_evidence_references_present", "check_artifact_manifest_integrity"],
)
async def test_old_checker_name_blocks_guide_activation_without_alias(
    checker_client: AsyncClient,
    old_checker_name: str,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Old Checker Name Project",
            "slug": "old-checker-name-project",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
    guide_payload["post_submit_checker_policy"]["required_checkers"] = [old_checker_name]
    guide_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    await create_policy_bundle_for_guide(
        checker_client,
        project["id"],
        guide_response.json()["id"],
    )
    activation_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_response.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 422, activation_response.text
    assert "unregistered checker policy names" in activation_response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(CheckerRun.__table__.select())).all()
    assert rows == []
