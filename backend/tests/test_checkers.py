# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from copy import deepcopy
import math
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.checkers import compiler as checker_compiler_module
from app.modules.checkers.compiler import (
    PRE_SUBMIT_COMPILER_VERSION,
    PreSubmitCheckerCompilerError,
    build_project_pre_submit_checker_spec,
    compile_effective_project_submission_artifact_policy,
    compile_project_pre_submit_checker_spec,
    validate_compiled_pre_submit_checker_bundle,
)
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.checkers import runner as checker_runner_module
from app.modules.checkers.pre_submit_defaults import attestation_term_is_satisfied
from app.modules.checkers.runner import (
    CheckerContext,
    CheckerNameConflict,
    CheckerOutcome,
    CheckerRegistry,
    FunctionChecker,
    UnknownChecker,
    canonical_artifact_manifest_hash,
)
from app.modules.checkers.api.history import CheckerRoutingRecommendation
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.post_submit_policy import (
    DEFAULT_DURABLE_CHECKERS,
    POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
    PostSubmitCheckerCompilerError,
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
    parse_locked_post_submit_checker_policy_body,
)
from app.modules.tasks.models import AuditEvent, EvidenceItem, Submission, WorkstreamTask
from tests.test_tasks import (
    auth_headers,
    set_dev_actor,
)
from project_create_fixtures import (
    grant_system_project_manager,
)


@pytest.fixture
def checker_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def checker_client(checker_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        admission = await client.get("/api/v1/actors/me", headers=auth_headers())
        assert admission.status_code == 200, admission.text
        async with db_session.get_session_factory()() as session:
            await grant_system_project_manager(
                session,
                issuer="flow-test",
                subject="project-manager-subject",
            )
            await session.commit()
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
                    run.status,
                    run.is_current_for_submission,
                    run.failure_code,
                    run.failure_message,
                    run.queued_at,
                    run.started_at,
                    run.completed_at,
                    run.created_at,
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


def _current_locked_test_facts() -> dict:
    """Supply real current lock types to orchestration tests, without PaymentPolicy."""
    from tests.checkers.post_submit.support import request

    facts = request().expected_context.model_dump(mode="json")
    return {
        "locked_guide_version": facts["guide_version"],
        "locked_guide_source_snapshot_id": facts["source_id"],
        "locked_guide_source_snapshot_hash": facts["source_hash"],
        "locked_effective_project_submission_artifact_policy_id": facts["effective_policy_id"],
        "locked_effective_project_submission_artifact_policy_hash": facts["effective_policy_hash"],
        "locked_pre_submit_checker_policy_id": facts["pre_policy_id"],
        "locked_pre_submit_checker_bundle_hash": facts["pre_policy_hash"],
        "locked_post_submit_checker_policy_id": facts["post_policy_id"],
        "locked_post_submit_checker_policy_version": facts["post_policy_version"],
        "locked_post_submit_checker_policy_hash": facts["post_policy_hash"],
        "locked_review_policy_id": facts["review_policy_id"],
        "locked_review_policy_generation": facts["review_generation"],
        "locked_review_policy_hash": facts["review_hash"],
        "locked_revision_policy_id": facts["revision_policy_id"],
        "locked_revision_policy_generation": facts["revision_generation"],
        "locked_revision_policy_hash": facts["revision_hash"],
    }


def _canonical_test_post_policy():
    project_id = "11111111-1111-4111-8111-111111111111"
    return compile_project_post_submit_checker_spec(
        project_id=project_id,
        guide_version="v1",
        spec=build_project_post_submit_checker_spec(project_id=project_id, guide_version="v1"),
    )


def _validate_test_post_body(body):
    parsed = parse_locked_post_submit_checker_policy_body(
        body,
        project_id=body["project_id"],
        guide_version=body["guide_version"],
        policy_hash=canonical_json_hash(body),
    )

    parsed.validate_catalogue(current_post_submit_catalogue())
    return parsed


def test_locked_post_submit_policy_parser_uses_persisted_body_hash() -> None:
    compiled = _canonical_test_post_policy()
    parsed = parse_locked_post_submit_checker_policy_body(
        compiled.policy_body, project_id=str(compiled.project_id),
        guide_version=compiled.guide_version, policy_hash=compiled.policy_hash,
    )
    assert parsed == compiled
    with pytest.raises(ValueError, match="policy hash is invalid"):
        parse_locked_post_submit_checker_policy_body(
            compiled.policy_body, project_id=str(compiled.project_id),
            guide_version=compiled.guide_version, policy_hash="sha256:" + "0" * 64,
        )


def test_post_submit_compiler_accepts_default_only_policy() -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="11111111-1111-4111-8111-111111111111",
        guide_version="v1",
    )

    compiled = compile_project_post_submit_checker_spec(
        project_id="11111111-1111-4111-8111-111111111111",
        guide_version="v1",
        spec=spec,
    )

    assert compiled.compiler_version == "workstream-post-submit-compiler"
    assert compiled.policy_body["compiler_version"] == compiled.compiler_version
    assert compiled.required_checkers == []
    assert compiled.warning_checkers == []
    assert compiled.execution_checkers == DEFAULT_DURABLE_CHECKERS
    assert compiled.default_checkers == DEFAULT_DURABLE_CHECKERS
    assert [entry["checker_id"] for entry in compiled.policy_body["entries"]] == DEFAULT_DURABLE_CHECKERS
    assert compiled.policy_hash == canonical_json_hash(compiled.policy_body)
    assert list(compiled.blocking_severities) == ["critical", "high"]


def test_post_submit_compiler_canonicalizes_project_specific_checker_spec() -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="11111111-1111-4111-8111-111111111111",
        guide_version="v1",
        required_checkers=[
            "check_acceptance_criteria_present",
        ],
        warning_checkers=[],
        blocking_severities=["critical", "high", "medium"],
    )

    compiled = compile_project_post_submit_checker_spec(
        project_id="11111111-1111-4111-8111-111111111111",
        guide_version="v1",
        spec=spec,
    )

    assert compiled.required_checkers == [
        "check_acceptance_criteria_present",
    ]
    assert compiled.execution_checkers == [
        *DEFAULT_DURABLE_CHECKERS,
        "check_acceptance_criteria_present",
    ]
    assert list(compiled.blocking_severities) == ["critical", "high", "medium"]


def test_post_submit_compiler_rejects_unknown_checker_name() -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="11111111-1111-4111-8111-111111111111",
        guide_version="v1",
        required_checkers=["missing_checker"],
    )

    with pytest.raises(PostSubmitCheckerCompilerError, match="selection is unavailable"):
        compile_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_non_object_spec() -> None:
    spec: Any = []

    with pytest.raises(PostSubmitCheckerCompilerError, match="spec shape"):
        compile_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_tuple_spec_lists() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "11111111-1111-4111-8111-111111111111",
        "guide_version": "v1",
        "required_checkers": ("check_acceptance_criteria_present",),
        "warning_checkers": [],
        "blocking_severities": ["critical", "high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="required_checkers"):
        compile_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_duplicate_checker_names() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "11111111-1111-4111-8111-111111111111",
        "guide_version": "v1",
        "required_checkers": [
            "check_acceptance_criteria_present",
            "check_acceptance_criteria_present",
        ],
        "warning_checkers": [],
        "blocking_severities": ["critical", "high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="duplicate checker"):
        compile_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_conflicting_checker_classification() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "11111111-1111-4111-8111-111111111111",
        "guide_version": "v1",
        "required_checkers": ["check_acceptance_criteria_present"],
        "warning_checkers": ["check_acceptance_criteria_present"],
        "blocking_severities": ["critical", "high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="conflicting checker"):
        compile_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_warning_only_default_checker_override() -> None:
    with pytest.raises(PostSubmitCheckerCompilerError, match="default checkers"):
        build_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            warning_checkers=["check_submission_packet"],
        )


def test_post_submit_compiler_rejects_raw_spec_warning_only_default_checker_override() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "11111111-1111-4111-8111-111111111111",
        "guide_version": "v1",
        "required_checkers": [],
        "warning_checkers": ["check_submission_packet"],
        "blocking_severities": ["critical", "high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="default checkers"):
        compile_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_raw_spec_blocking_severity_downgrade() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "11111111-1111-4111-8111-111111111111",
        "guide_version": "v1",
        "required_checkers": [],
        "warning_checkers": [],
        "blocking_severities": ["high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="blocking severities"):
        compile_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            spec=spec,
        )


@pytest.mark.parametrize(
    "blocking_severities",
    [[], ["critical"], ["high"]],
)
def test_post_submit_compiler_rejects_blocking_severity_downgrade(
    blocking_severities: list[str],
) -> None:
    with pytest.raises(PostSubmitCheckerCompilerError, match="blocking severities"):
        build_project_post_submit_checker_spec(
            project_id="11111111-1111-4111-8111-111111111111",
            guide_version="v1",
            blocking_severities=blocking_severities,
        )


@pytest.mark.parametrize(
    "default_checkers",
    [
        list(DEFAULT_DURABLE_CHECKERS[:-1]),
        list(reversed(DEFAULT_DURABLE_CHECKERS)),
        [*DEFAULT_DURABLE_CHECKERS[:-1], "renamed_default_checker"],
        [*DEFAULT_DURABLE_CHECKERS, "extra_default_checker"],
    ],
)
def test_locked_post_submit_policy_validation_rejects_default_checker_drift(default_checkers: list[str]) -> None:
    body = _canonical_test_post_policy().policy_body
    by_name = {entry["checker_id"]: entry for entry in body["entries"]}
    template = body["entries"][0]
    body["entries"] = [by_name.get(name, {**template, "checker_id": name}) for name in default_checkers]
    with pytest.raises(ValueError):
        _validate_test_post_body(body)


@pytest.mark.parametrize(
    "drifted_defaults",
    [
        list(DEFAULT_DURABLE_CHECKERS[:-1]),
        list(reversed(DEFAULT_DURABLE_CHECKERS)),
        [*DEFAULT_DURABLE_CHECKERS[:-1], "renamed_default_checker"],
        [*DEFAULT_DURABLE_CHECKERS, "extra_default_checker"],
    ],
)
def test_locked_post_submit_policy_validation_rejects_self_consistent_default_drift(drifted_defaults: list[str]) -> None:
    body = _canonical_test_post_policy().policy_body
    template = body["entries"][0]
    body["entries"] = [{**template, "checker_id": name} for name in drifted_defaults]
    # Recomputed digest proves the canonical catalogue rejects changed defaults.
    with pytest.raises(ValueError):
        _validate_test_post_body(body)


def test_locked_post_submit_policy_validation_rejects_unsupported_compiler_version() -> None:
    body = _canonical_test_post_policy().policy_body
    body["compiler_version"] = "unsupported"
    with pytest.raises(ValueError, match="compiler_version"):
        _validate_test_post_body(body)


@pytest.mark.parametrize(
    ("required_checkers", "warning_checkers", "execution_checkers"),
    [
        (
            ["check_acceptance_criteria_present"],
            ["check_acceptance_criteria_present"],
            [*DEFAULT_DURABLE_CHECKERS, "check_acceptance_criteria_present"],
        ),
        ([], ["check_submission_packet"], list(DEFAULT_DURABLE_CHECKERS)),
    ],
)
def test_locked_post_submit_policy_validation_rejects_conflicting_classifications(
    required_checkers: list[str], warning_checkers: list[str], execution_checkers: list[str],
) -> None:
    body = _canonical_test_post_policy().policy_body
    template = {**body["entries"][0], "checker_id": "check_acceptance_criteria_present"}
    if required_checkers:
        body["entries"] = body["entries"][:-1] + [{**template, "classification": "project_required"},
                            {**template, "classification": "project_warning"}]
    else:
        body["entries"][0]["classification"] = "project_warning"
    with pytest.raises(ValueError, match="duplicate entries|classification mismatch"):
        _validate_test_post_body(body)


@pytest.mark.parametrize(
    "blocking_severities",
    [[], ["critical"], ["high"]],
)
def test_locked_post_submit_policy_validation_rejects_blocking_severity_downgrade(blocking_severities: list[str]) -> None:
    body = _canonical_test_post_policy().policy_body
    body["blocking_severities"] = blocking_severities
    with pytest.raises(ValueError, match="blocking_severities"):
        _validate_test_post_body(body)


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
    spec["rules"] = [rule for rule in spec["rules"] if rule["primitive"] != "require_file"]

    with pytest.raises(PreSubmitCheckerCompilerError, match="require_file"):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_pre_submit_compiler_rejects_skipped_evidence_coverage() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "4" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    for rule in spec["rules"]:
        if rule["primitive"] == "require_minimum_evidence":
            rule["config"]["evidence_paths"] = []

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
        canonical_json_hash({"score": math.nan})


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


def test_manifest_hash_rejects_incomplete_entries() -> None:
    for manifest in ([{"artifact": "answer.md"}], [{"hash": "sha256:a"}]):
        with pytest.raises(ValueError, match="require artifact and hash"):
            canonical_artifact_manifest_hash(manifest)


def test_evidence_integrity_reports_each_untrusted_reference_shape() -> None:
    traversal = checker_runner_module._evidence_integrity_outcome(
        [{"artifact": "../secret.txt", "hash": "sha256:a"}],
        [],
    )
    malformed_hash = checker_runner_module._evidence_integrity_outcome(
        [{"artifact": "answer.md", "hash": "md5:a"}],
        [],
    )
    missing_evidence_hash = checker_runner_module._evidence_integrity_outcome(
        [{"artifact": "answer.md", "hash": "sha256:a"}],
        [{"label": "proof", "uri": "s3://bucket/proof", "hash": None}],
    )

    assert traversal.blocks_review is True
    assert "integrity_error" in traversal.metadata
    assert malformed_hash.metadata == {"invalid_artifact_count": 1}
    assert missing_evidence_hash.metadata == {"missing_evidence_hash_count": 1}


def test_required_file_checker_handles_empty_invalid_and_missing_contracts() -> None:
    no_requirement = checker_runner_module._required_files_outcome([], [])
    invalid = checker_runner_module._required_files_outcome(["../answer.md"], [])
    missing = checker_runner_module._required_files_outcome(
        ["answer.md"],
        [{"artifact": "notes.md", "hash": "sha256:notes"}],
    )

    assert no_requirement.status == "passed"
    assert invalid.blocks_review is True
    assert "relative artifact paths" in (invalid.worker_suggested_fix or "")
    assert missing.metadata == {"missing_required_files": ["answer.md"]}


def test_forbidden_file_checker_classifies_without_leaking_paths() -> None:
    outcome = checker_runner_module._forbidden_files_outcome(
        [
            {"artifact": "../ignored"},
            {"artifact": "config/.env"},
            {"artifact": "keys/client.pem"},
            {"artifact": "build/debug.tmp"},
        ],
        [],
        ["*.tmp"],
    )

    assert outcome.blocks_review is True
    assert outcome.metadata == {
        "forbidden_categories": [
            "forbidden_file_suffix",
            "forbidden_path_segment",
            "forbidden_policy_pattern",
        ]
    }
    assert "client.pem" not in outcome.message


def test_packet_shape_reports_all_required_fields_without_echoing_values() -> None:
    outcome = checker_runner_module._packet_shape_outcome("", "", [])

    assert outcome.blocks_review is True
    assert outcome.metadata == {
        "missing_fields": ["summary", "package_hash", "artifact_hash_manifest"]
    }


def test_artifact_path_and_pattern_normalization_fail_closed() -> None:
    assert checker_runner_module._normalize_artifact_path("./folder//answer.md") == (
        "folder/answer.md"
    )
    with pytest.raises(ValueError, match="relative and non-empty"):
        checker_runner_module._normalize_artifact_path("/absolute.txt")
    assert not checker_runner_module._path_matches_forbidden_pattern("answer.md", "")


@pytest.mark.asyncio
async def test_policy_context_checker_blocks_incomplete_lock_without_exposing_details() -> None:
    from dataclasses import replace
    from app.modules.checkers.api import ObservedPostSubmitContext
    from app.modules.checkers.post_submit_implementations import detached_checker_context
    from tests.checkers.post_submit.support import request
    source = request()
    context = detached_checker_context(source)
    assert (await checker_runner_module.check_policy_context_present(context)).status == "passed"
    observed = source.structural_input.observed_context.model_dump()
    observed["pre_policy_id"] = None
    outcome = await checker_runner_module.check_policy_context_present(
        replace(context, observed_context=ObservedPostSubmitContext(**observed))
    )
    assert outcome.status == "failed"
    assert outcome.worker_visible is False
    assert outcome.routing_recommendation == "task_setup_blocked"
    assert outcome.metadata == {"invalid_context": ["pre_policy_id"]}


def test_attestation_and_policy_projection_helpers_preserve_required_only_rules() -> None:
    policy = {
        "required_artifacts": [
            {"path": "answer.md", "required": True},
            {"path": "optional.md", "required": False},
        ],
        "required_evidence": [
            {"key": "proof", "required": True},
            {"key": "optional", "required": False},
        ],
        "forbidden_artifacts": [{"pattern": "*.key"}, {"pattern": ""}],
        "attestation_terms": ["original work", ""],
    }

    assert checker_runner_module._required_artifact_paths(policy) == ["answer.md"]
    assert checker_runner_module._required_evidence_keys(policy) == ["proof"]
    assert checker_runner_module._forbidden_artifact_patterns(policy) == ["*.key"]
    assert checker_runner_module._required_attestation_terms(policy) == ["original work"]
    assert checker_runner_module._required_artifact_paths(None) == []
    assert checker_runner_module._required_evidence_keys(None) == []
    assert checker_runner_module._forbidden_artifact_patterns(None) == []
    assert checker_runner_module._required_attestation_terms(None) == []
    assert attestation_term_is_satisfied("anything", "")
    assert attestation_term_is_satisfied(
        "i_confirm_original_work",
        "original work",
    )
    assert not attestation_term_is_satisfied(
        "i_confirm_original_work",
        "client confidentiality",
    )


@pytest.mark.asyncio
async def test_checker_registry_preserves_policy_order_and_rejects_name_drift() -> None:
    from app.modules.checkers.api.post_submit_catalogue import structural_definition
    registry = CheckerRegistry()
    async def outcome(name: str) -> CheckerOutcome:
        return CheckerOutcome(name, "passed", "info", f"{name} passed")
    policy = _canonical_test_post_policy()
    for name in policy.execution_checkers:
        registry.register(FunctionChecker(name, lambda _context, name=name: outcome(name)),
                          definition=structural_definition(name))
    results = await registry.run(cast(CheckerContext, object()), policy.entries)
    assert [result.checker_name for result in results] == policy.execution_checkers
    name = policy.execution_checkers[0]
    with pytest.raises(CheckerNameConflict, match="already registered"):
        registry.register(FunctionChecker(name, lambda _context: outcome(name)),
                          definition=structural_definition(name))
    with pytest.raises(UnknownChecker, match="missing, unknown"):
        registry.require_registered({"unknown", "missing"})


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"schema_version": "invalid"}, "schema version"),
        ({"compiler_version": "invalid"}, "compiler version"),
        ({"primitives_version": "invalid"}, "primitives version"),
        ({"effective_policy_hash": "sha256:other"}, "policy hash mismatch"),
        ({"rules": []}, "requires rules"),
    ],
)
def test_compiled_checker_bundle_rejects_envelope_drift(
    mutation: dict[str, Any],
    message: str,
) -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "d" * 64
    compiled = compile_effective_project_submission_artifact_policy(
        effective_policy,
        effective_policy_hash,
    )
    bundle = deepcopy(compiled.compiled_bundle)
    bundle.update(mutation)

    with pytest.raises(PreSubmitCheckerCompilerError, match=message):
        validate_compiled_pre_submit_checker_bundle(
            effective_policy,
            effective_policy_hash,
            bundle,
            compiler_version=compiled.compiler_version,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"schema_version": "invalid"}, "schema version"),
        ({"effective_policy_hash": "sha256:other"}, "policy hash mismatch"),
        ({"rules": []}, "requires rules"),
    ],
)
def test_checker_spec_rejects_envelope_drift(
    mutation: dict[str, Any],
    message: str,
) -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "e" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    spec.update(mutation)

    with pytest.raises(PreSubmitCheckerCompilerError, match=message):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"severity": "low"}, "invalid severity"),
        ({"policy_fields": []}, "lacks policy trace"),
        ({"policy_fields": [None]}, "invalid policy trace"),
        ({"config": []}, "config must be an object"),
    ],
)
def test_checker_spec_rejects_ambiguous_rule_shape(
    mutation: dict[str, Any],
    message: str,
) -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "f" * 64
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    spec["rules"][0].update(mutation)

    with pytest.raises(PreSubmitCheckerCompilerError, match=message):
        compile_project_pre_submit_checker_spec(effective_policy, effective_policy_hash, spec)


def test_checker_spec_rejects_duplicate_primitive_and_hash_algorithm_drift() -> None:
    effective_policy = compiler_effective_policy()
    effective_policy_hash = "sha256:" + "1" * 64
    duplicate = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    duplicate["rules"].append(deepcopy(duplicate["rules"][0]))

    with pytest.raises(PreSubmitCheckerCompilerError, match="duplicate primitive"):
        compile_project_pre_submit_checker_spec(
            effective_policy,
            effective_policy_hash,
            duplicate,
        )

    hash_drift = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    next(rule for rule in hash_drift["rules"] if rule["primitive"] == "verify_hash")[
        "config"
    ]["algorithm"] = "md5"
    with pytest.raises(PreSubmitCheckerCompilerError, match="hash algorithm"):
        compile_project_pre_submit_checker_spec(
            effective_policy,
            effective_policy_hash,
            hash_drift,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("packaging", [], "packaging must be an object"),
        ("required_artifacts", {}, "required_artifacts must be a list"),
        ("required_evidence", ["proof"], "required_evidence entries are invalid"),
    ],
)
def test_checker_policy_rejects_non_executable_collection_shapes(
    field: str,
    value: Any,
    message: str,
) -> None:
    policy = compiler_effective_policy()
    policy[field] = value

    with pytest.raises(PreSubmitCheckerCompilerError, match=message):
        checker_compiler_module._expected_primitives(policy)


@pytest.mark.parametrize(
    "old_checker_name",
    ["check_evidence_references_present", "check_artifact_manifest_integrity"],
)
def test_old_checker_name_blocks_post_submit_compilation_without_alias(
    old_checker_name: str,
) -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="00000000-0000-0000-0000-000000000001",
        guide_version="v1",
        required_checkers=[old_checker_name],
    )

    with pytest.raises(PostSubmitCheckerCompilerError, match="post-submit project selection is unavailable"):
        compile_project_post_submit_checker_spec(
            project_id="00000000-0000-0000-0000-000000000001",
            guide_version="v1",
            spec=spec,
        )
