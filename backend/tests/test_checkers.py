# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.permissions import PermissionDenied
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.checkers import compiler as checker_compiler_module
from app.modules.checkers import service as checker_service_module
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
from app.modules.checkers.schemas import CheckerRoutingRecommendation
from app.modules.checkers.service import (
    PRE_REVIEW_GATE_RUNNING_TIMEOUT,
    PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
    PRE_REVIEW_GATE_SYSTEM_ISSUER,
    PRE_REVIEW_GATE_TRIGGER_SOURCE,
    CheckerConflict,
    CheckerExecutionBlocked,
    CheckerPolicyInvalid,
    CheckerRunNotFound,
    CheckerService,
    CheckerSubmissionNotFound,
    CheckerTaskNotFound,
    pre_review_gate_system_actor,
)
from app.modules.projects.models import PostSubmitCheckerPolicy
from app.modules.projects.post_submit_policy import (
    DEFAULT_DURABLE_CHECKERS,
    POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
    POST_SUBMIT_COMPILER_VERSION,
    POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
    POST_SUBMIT_V01_DEFAULT_CHECKERS,
    PostSubmitCheckerCompilerError,
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
    parse_locked_post_submit_checker_policy_body,
)
from app.modules.tasks.models import AuditEvent, EvidenceItem, Submission, WorkstreamTask
from app.modules.tasks.schemas import SubmissionCreate
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
from project_create_fixtures import (
    activate_guide_for_downstream_test,
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
        admission = await client.get("/api/v1/auth/me", headers=auth_headers())
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
        "compiler_version": POST_SUBMIT_COMPILER_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": list(DEFAULT_DURABLE_CHECKERS),
        "required_checkers": ["project_required_checker"],
        "warning_checkers": [],
        "execution_checkers": [
            *DEFAULT_DURABLE_CHECKERS,
            "project_required_checker",
        ],
        "blocking_severities": ["critical", "high"],
    }
    policy_hash = canonical_json_hash(body)

    parsed = parse_locked_post_submit_checker_policy_body(
        body,
        project_id="project-id",
        guide_version="v1",
        policy_hash=policy_hash,
    )

    assert parsed.default_checkers == DEFAULT_DURABLE_CHECKERS
    assert parsed.execution_checkers == [
        *DEFAULT_DURABLE_CHECKERS,
        "project_required_checker",
    ]


def test_post_submit_compiler_accepts_default_only_policy() -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="project-id",
        guide_version="v1",
    )

    compiled = compile_project_post_submit_checker_spec(
        project_id="project-id",
        guide_version="v1",
        spec=spec,
    )

    assert compiled.compiler_version == POST_SUBMIT_COMPILER_VERSION
    assert compiled.policy_body["compiler_version"] == compiled.compiler_version
    assert compiled.required_checkers == []
    assert compiled.warning_checkers == []
    assert compiled.execution_checkers == DEFAULT_DURABLE_CHECKERS
    assert compiled.policy_body["default_checkers"] == DEFAULT_DURABLE_CHECKERS
    assert compiled.policy_body["execution_checkers"] == DEFAULT_DURABLE_CHECKERS
    assert compiled.policy_hash == canonical_json_hash(compiled.policy_body)
    assert compiled.blocking_severities == ["critical", "high"]


def test_post_submit_compiler_canonicalizes_project_specific_checker_spec() -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="project-id",
        guide_version="v1",
        required_checkers=[
            "check_acceptance_criteria_present",
            "check_low_quality_generated_artifacts",
        ],
        warning_checkers=[],
        blocking_severities=["critical", "high", "medium"],
    )

    compiled = compile_project_post_submit_checker_spec(
        project_id="project-id",
        guide_version="v1",
        spec=spec,
    )

    assert compiled.required_checkers == [
        "check_acceptance_criteria_present",
        "check_low_quality_generated_artifacts",
    ]
    assert compiled.execution_checkers == [
        *DEFAULT_DURABLE_CHECKERS,
        "check_acceptance_criteria_present",
    ]
    assert compiled.blocking_severities == ["critical", "high", "medium"]


def test_post_submit_compiler_rejects_unknown_checker_name() -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="project-id",
        guide_version="v1",
        required_checkers=["missing_checker"],
    )

    with pytest.raises(PostSubmitCheckerCompilerError, match="unregistered checker"):
        compile_project_post_submit_checker_spec(
            project_id="project-id",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_non_object_spec() -> None:
    spec: Any = []

    with pytest.raises(PostSubmitCheckerCompilerError, match="spec shape"):
        compile_project_post_submit_checker_spec(
            project_id="project-id",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_tuple_spec_lists() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "required_checkers": ("check_acceptance_criteria_present",),
        "warning_checkers": [],
        "blocking_severities": ["critical", "high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="required_checkers"):
        compile_project_post_submit_checker_spec(
            project_id="project-id",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_duplicate_checker_names() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "project-id",
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
            project_id="project-id",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_conflicting_checker_classification() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "required_checkers": ["check_acceptance_criteria_present"],
        "warning_checkers": ["check_acceptance_criteria_present"],
        "blocking_severities": ["critical", "high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="conflicting checker"):
        compile_project_post_submit_checker_spec(
            project_id="project-id",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_warning_only_default_checker_override() -> None:
    with pytest.raises(PostSubmitCheckerCompilerError, match="default checkers"):
        build_project_post_submit_checker_spec(
            project_id="project-id",
            guide_version="v1",
            warning_checkers=["check_submission_packet"],
        )


def test_post_submit_compiler_rejects_raw_spec_warning_only_default_checker_override() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "required_checkers": [],
        "warning_checkers": ["check_submission_packet"],
        "blocking_severities": ["critical", "high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="default checkers"):
        compile_project_post_submit_checker_spec(
            project_id="project-id",
            guide_version="v1",
            spec=spec,
        )


def test_post_submit_compiler_rejects_raw_spec_blocking_severity_downgrade() -> None:
    spec = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "required_checkers": [],
        "warning_checkers": [],
        "blocking_severities": ["high"],
    }

    with pytest.raises(PostSubmitCheckerCompilerError, match="blocking severities"):
        compile_project_post_submit_checker_spec(
            project_id="project-id",
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
            project_id="project-id",
            guide_version="v1",
            blocking_severities=blocking_severities,
        )


@pytest.mark.parametrize(
    "default_checkers",
    [
        list(POST_SUBMIT_V01_DEFAULT_CHECKERS[:-1]),
        list(reversed(POST_SUBMIT_V01_DEFAULT_CHECKERS)),
        [*POST_SUBMIT_V01_DEFAULT_CHECKERS[:-1], "renamed_default_checker"],
        [*POST_SUBMIT_V01_DEFAULT_CHECKERS, "extra_default_checker"],
    ],
)
def test_locked_post_submit_policy_parser_rejects_default_checker_drift(
    default_checkers: list[str],
) -> None:
    body = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "compiler_version": POST_SUBMIT_COMPILER_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": default_checkers,
        "required_checkers": [],
        "warning_checkers": [],
        "execution_checkers": list(POST_SUBMIT_V01_DEFAULT_CHECKERS),
        "blocking_severities": ["critical", "high"],
    }
    policy_hash = canonical_json_hash(body)

    with pytest.raises(ValueError, match="policy body is invalid"):
        parse_locked_post_submit_checker_policy_body(
            body,
            project_id="project-id",
            guide_version="v1",
            policy_hash=policy_hash,
        )


@pytest.mark.parametrize(
    "drifted_defaults",
    [
        list(POST_SUBMIT_V01_DEFAULT_CHECKERS[:-1]),
        list(reversed(POST_SUBMIT_V01_DEFAULT_CHECKERS)),
        [*POST_SUBMIT_V01_DEFAULT_CHECKERS[:-1], "renamed_default_checker"],
        [*POST_SUBMIT_V01_DEFAULT_CHECKERS, "extra_default_checker"],
    ],
)
def test_locked_post_submit_policy_parser_rejects_self_consistent_default_drift(
    drifted_defaults: list[str],
) -> None:
    body = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "compiler_version": POST_SUBMIT_COMPILER_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": drifted_defaults,
        "required_checkers": [],
        "warning_checkers": [],
        "execution_checkers": list(drifted_defaults),
        "blocking_severities": ["critical", "high"],
    }
    policy_hash = canonical_json_hash(body)

    with pytest.raises(ValueError, match="policy body is invalid"):
        parse_locked_post_submit_checker_policy_body(
            body,
            project_id="project-id",
            guide_version="v1",
            policy_hash=policy_hash,
        )


def test_locked_post_submit_policy_parser_uses_v01_snapshot_not_current_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.projects import post_submit_policy as post_submit_policy_module

    original_v01_body = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "compiler_version": POST_SUBMIT_COMPILER_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": list(POST_SUBMIT_V01_DEFAULT_CHECKERS),
        "required_checkers": [],
        "warning_checkers": [],
        "execution_checkers": list(POST_SUBMIT_V01_DEFAULT_CHECKERS),
        "blocking_severities": ["critical", "high"],
    }
    later_defaults = [*POST_SUBMIT_V01_DEFAULT_CHECKERS, "check_acceptance_criteria_present"]
    invented_v01_body = {
        **original_v01_body,
        "default_checkers": later_defaults,
        "execution_checkers": later_defaults,
    }

    monkeypatch.setattr(post_submit_policy_module, "DEFAULT_DURABLE_CHECKERS", later_defaults)

    parsed = parse_locked_post_submit_checker_policy_body(
        original_v01_body,
        project_id="project-id",
        guide_version="v1",
        policy_hash=canonical_json_hash(original_v01_body),
    )
    assert parsed.default_checkers == list(POST_SUBMIT_V01_DEFAULT_CHECKERS)

    with pytest.raises(ValueError, match="policy body is invalid"):
        parse_locked_post_submit_checker_policy_body(
            invented_v01_body,
            project_id="project-id",
            guide_version="v1",
            policy_hash=canonical_json_hash(invented_v01_body),
        )


def test_locked_post_submit_policy_parser_rejects_unsupported_compiler_version() -> None:
    body = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "compiler_version": "workstream-post-submit-compiler-v9",
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": list(DEFAULT_DURABLE_CHECKERS),
        "required_checkers": [],
        "warning_checkers": [],
        "execution_checkers": list(DEFAULT_DURABLE_CHECKERS),
        "blocking_severities": ["critical", "high"],
    }
    policy_hash = canonical_json_hash(body)

    with pytest.raises(ValueError, match="policy body is invalid"):
        parse_locked_post_submit_checker_policy_body(
            body,
            project_id="project-id",
            guide_version="v1",
            policy_hash=policy_hash,
        )


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
def test_locked_post_submit_policy_parser_rejects_conflicting_classifications(
    required_checkers: list[str],
    warning_checkers: list[str],
    execution_checkers: list[str],
) -> None:
    body = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "compiler_version": POST_SUBMIT_COMPILER_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": list(DEFAULT_DURABLE_CHECKERS),
        "required_checkers": required_checkers,
        "warning_checkers": warning_checkers,
        "execution_checkers": execution_checkers,
        "blocking_severities": ["critical", "high"],
    }
    policy_hash = canonical_json_hash(body)

    with pytest.raises(ValueError, match="policy body is invalid"):
        parse_locked_post_submit_checker_policy_body(
            body,
            project_id="project-id",
            guide_version="v1",
            policy_hash=policy_hash,
        )


@pytest.mark.parametrize(
    "blocking_severities",
    [[], ["critical"], ["high"]],
)
def test_locked_post_submit_policy_parser_rejects_blocking_severity_downgrade(
    blocking_severities: list[str],
) -> None:
    body = {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "compiler_version": POST_SUBMIT_COMPILER_VERSION,
        "project_id": "project-id",
        "guide_version": "v1",
        "default_checkers": list(DEFAULT_DURABLE_CHECKERS),
        "required_checkers": [],
        "warning_checkers": [],
        "execution_checkers": list(DEFAULT_DURABLE_CHECKERS),
        "blocking_severities": blocking_severities,
    }
    policy_hash = canonical_json_hash(body)

    with pytest.raises(ValueError, match="policy body is invalid"):
        parse_locked_post_submit_checker_policy_body(
            body,
            project_id="project-id",
            guide_version="v1",
            policy_hash=policy_hash,
        )


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
    detail_schema = schema["paths"]["/api/v1/checker-runs/{checker_run_id}"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
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


def test_packet_limits_and_packaging_return_actionable_failures() -> None:
    file_limit = checker_runner_module._size_limit_outcome(
        [{"artifact": "large.bin", "size_bytes": 11}],
        {"maximum_file_size_bytes": 10},
    )
    package_limit = checker_runner_module._size_limit_outcome(
        [
            {"artifact": "one.bin", "size_bytes": 6},
            {"artifact": "two.bin", "size_bytes": 5},
        ],
        {"maximum_package_size_bytes": 10},
    )
    payload = SimpleNamespace(package_uri=None)
    required_package = checker_runner_module._packaging_outcome(
        cast(Any, payload),
        {"packaging": {"package_required": True}},
    )
    payload.package_uri = "s3://bucket/work.tar"
    invalid_format = checker_runner_module._packaging_outcome(
        cast(Any, payload),
        {"packaging": {"allowed_package_formats": ["zip"]}},
    )

    assert file_limit is not None
    assert file_limit.metadata == {"oversized_artifacts": ["large.bin"]}
    assert package_limit is not None
    assert package_limit.metadata == {"known_manifest_size_bytes": 11}
    assert required_package is not None and required_package.blocks_review
    assert invalid_format is not None
    assert invalid_format.metadata == {"allowed_package_formats": ["zip"]}


def test_packet_shape_reports_all_required_fields_without_echoing_values() -> None:
    outcome = checker_runner_module._packet_shape_outcome("", "", [])

    assert outcome.blocks_review is True
    assert outcome.metadata == {
        "missing_fields": ["summary", "package_hash", "artifact_hash_manifest"]
    }


def test_pre_submit_packet_applies_required_storage_size_and_package_rules() -> None:
    payload = SimpleNamespace(
        summary="complete",
        package_hash="sha256:package",
        worker_attestation="",
        package_uri="ftp://bucket/work.zip",
    )
    manifest = [{"artifact": "answer.md", "hash": "sha256:a", "size_bytes": 11}]

    missing_base_packet = checker_runner_module._pre_submit_packet_outcome(
        cast(
            Any,
            SimpleNamespace(
                summary="",
                package_hash="",
                worker_attestation="",
                package_uri=None,
            ),
        ),
        [],
        [],
        {},
    )

    missing_field = checker_runner_module._pre_submit_packet_outcome(
        cast(Any, payload),
        manifest,
        [],
        {
            "required_packet_fields": ["worker_attestation"],
            "allowed_storage_schemes": ["s3"],
        },
    )
    payload.worker_attestation = "original work"
    invalid_storage = checker_runner_module._pre_submit_packet_outcome(
        cast(Any, payload),
        manifest,
        [],
        {"allowed_storage_schemes": ["s3"]},
    )
    payload.package_uri = "s3://bucket/work.zip"
    oversized = checker_runner_module._pre_submit_packet_outcome(
        cast(Any, payload),
        manifest,
        [],
        {
            "allowed_storage_schemes": ["s3"],
            "maximum_file_size_bytes": 10,
        },
    )
    wrong_package = checker_runner_module._pre_submit_packet_outcome(
        cast(Any, payload),
        [{"artifact": "answer.md", "hash": "sha256:a", "size_bytes": 1}],
        [],
        {
            "allowed_storage_schemes": ["s3"],
            "packaging": {"allowed_package_formats": ["tar"]},
        },
    )

    assert missing_base_packet.metadata == {
        "missing_fields": ["summary", "package_hash", "artifact_hash_manifest"]
    }
    assert missing_field.metadata == {"missing_fields": ["worker_attestation"]}
    assert invalid_storage.metadata == {"invalid_storage_refs": ["ftp://bucket/work.zip"]}
    assert oversized.metadata == {"oversized_artifacts": ["answer.md"]}
    assert wrong_package.metadata == {"allowed_package_formats": ["tar"]}


def test_artifact_path_and_pattern_normalization_fail_closed() -> None:
    assert checker_runner_module._normalize_artifact_path("./folder//answer.md") == (
        "folder/answer.md"
    )
    with pytest.raises(ValueError, match="relative and non-empty"):
        checker_runner_module._normalize_artifact_path("/absolute.txt")
    assert not checker_runner_module._path_matches_forbidden_pattern("answer.md", "")


@pytest.mark.asyncio
async def test_policy_context_checker_blocks_incomplete_lock_without_exposing_details() -> None:
    lock_fields = {
        "locked_guide_version": "v1",
        "locked_post_submit_checker_policy_id": "post-1",
        "locked_post_submit_checker_policy_version": "v1",
        "locked_post_submit_checker_policy_hash": "sha256:post",
        "locked_review_policy_id": "review-1",
        "locked_review_policy_generation": 1,
        "locked_review_policy_hash": "sha256:review",
        "locked_revision_policy_id": "revision-1",
        "locked_revision_policy_generation": 1,
        "locked_revision_policy_hash": "sha256:revision",
        "locked_payment_policy_version": "v1",
        "locked_guide_source_snapshot_id": "snapshot-1",
        "locked_guide_source_snapshot_hash": "sha256:snapshot",
        "locked_effective_project_submission_artifact_policy_id": "effective-1",
        "locked_effective_project_submission_artifact_policy_hash": "sha256:effective",
        "locked_pre_submit_checker_policy_id": "pre-1",
        "locked_pre_submit_checker_bundle_hash": None,
    }
    context = CheckerContext(
        task=cast(Any, None),
        submission=cast(Any, SimpleNamespace(**lock_fields)),
        required_checker_names=frozenset(),
        warning_checker_names=frozenset(),
        blocking_severities=frozenset(),
    )

    outcome = await checker_runner_module.check_policy_context_present(context)

    assert outcome.blocks_review is True
    assert outcome.worker_visible is False
    assert outcome.metadata == {"missing_context": ["locked_pre_submit_checker_bundle_hash"]}


@pytest.mark.asyncio
async def test_pre_submit_feedback_rejects_unsupported_compiled_checker_name() -> None:
    payload = SubmissionCreate.model_validate(complete_submission_payload())

    with pytest.raises(UnknownChecker, match="unsupported checker names: unknown_checker"):
        await checker_runner_module.pre_submit_static_feedback(
            cast(Any, SimpleNamespace()),
            payload,
            {},
            ["unknown_checker"],
        )


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
    registry = CheckerRegistry()

    async def outcome(name: str) -> CheckerOutcome:
        return CheckerOutcome(name, "passed", "info", f"{name} passed")

    for name in ("first", "second"):
        registry.register(FunctionChecker(name, lambda _context, name=name: outcome(name)))

    context = cast(CheckerContext, object())
    results = await registry.run(context, ["second", "first"])

    assert registry.names() == {"first", "second"}
    assert [result.checker_name for result in results] == ["second", "first"]
    with pytest.raises(CheckerNameConflict, match="already registered"):
        registry.register(FunctionChecker("first", lambda _context: outcome("first")))
    with pytest.raises(UnknownChecker, match="missing, unknown"):
        registry.require_registered({"unknown", "missing"})


def _valid_effective_checker_policy() -> dict[str, Any]:
    return {
        "required_packet_fields": ["summary"],
        "allowed_storage_schemes": ["s3"],
        "attestation_terms": ["original_work"],
        "artifact_hash_algorithm": "sha256",
        "manifest_required": True,
        "artifact_hash_required": True,
        "maximum_file_size_bytes": 10,
        "maximum_package_size_bytes": 20,
        "packaging": {"package_required": True, "allowed_package_formats": ["zip"]},
        "required_artifacts": [
            {"path": "answer.md", "key": "answer", "required": True, "hash_required": True}
        ],
        "required_evidence": [{"key": "proof", "label": "Proof", "required": True}],
        "forbidden_artifacts": [{"pattern": "*.key", "reason": "secret"}],
    }


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("required_packet_fields", "summary"),
        ("allowed_storage_schemes", [1]),
        ("attestation_terms", None),
        ("artifact_hash_algorithm", "md5"),
        ("manifest_required", "yes"),
        ("artifact_hash_required", 1),
        ("maximum_file_size_bytes", True),
        ("maximum_package_size_bytes", -1),
        ("packaging", []),
        ("required_artifacts", "answer.md"),
        ("required_evidence", [{"key": ""}]),
        ("forbidden_artifacts", [{"pattern": "*.key", "severity": 1}]),
    ],
)
def test_effective_checker_policy_shape_rejects_non_executable_rules(
    field: str,
    invalid_value: Any,
) -> None:
    policy = deepcopy(_valid_effective_checker_policy())
    policy[field] = invalid_value

    assert CheckerService._effective_policy_shape_is_valid(policy) is False


def test_effective_checker_policy_shape_accepts_complete_policy() -> None:
    assert CheckerService._effective_policy_shape_is_valid(_valid_effective_checker_policy())
    assert CheckerService._effective_policy_shape_is_valid([]) is False


@pytest.mark.parametrize(
    "rules",
    [
        ["answer.md"],
        [{"path": ""}],
        [{"path": "answer.md", "required": "yes"}],
        [{"path": "answer.md", "hash_required": 1}],
        [{"path": "answer.md", "description": 3}],
    ],
)
def test_artifact_rule_validation_rejects_ambiguous_rules(rules: list[Any]) -> None:
    assert not CheckerService._artifact_rule_list(
        rules,
        required_key="path",
        optional_keys={"description"},
    )


def test_packaging_validation_rejects_ambiguous_rules() -> None:
    assert not CheckerService._packaging_shape_is_valid([])
    assert not CheckerService._packaging_shape_is_valid({"package_required": "yes"})
    assert not CheckerService._packaging_shape_is_valid({"allowed_package_formats": [1]})
    assert CheckerService._packaging_shape_is_valid(
        {"package_required": False, "allowed_package_formats": ["zip"]}
    )


def _checker_outcome(
    name: str,
    *,
    status: str = "passed",
    severity: str = "info",
    blocks_review: bool = False,
    routing: str | None = None,
    worker_visible: bool = True,
) -> CheckerOutcome:
    return CheckerOutcome(
        checker_name=name,
        status=status,
        severity=severity,
        message=f"{name} message",
        blocks_review=blocks_review,
        worker_visible=worker_visible,
        routing_recommendation=routing,
    )


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        ([_checker_outcome("ok")], "allow_review"),
        ([_checker_outcome("blocked", blocks_review=True)], "needs_revision"),
        ([_checker_outcome("setup", routing="task_setup_blocked")], "task_setup_blocked"),
        (
            [
                _checker_outcome("setup", routing="task_setup_blocked"),
                _checker_outcome("retry", routing="checker_retry"),
            ],
            "checker_retry",
        ),
    ],
)
def test_checker_routing_uses_fail_closed_priority(
    outcomes: list[CheckerOutcome],
    expected: str,
) -> None:
    assert CheckerService._routing_recommendation_for_outcomes(outcomes) == expected


def test_blocking_policy_escalates_required_warning_and_preserves_optional_warning() -> None:
    context = CheckerContext(
        task=cast(Any, None),
        submission=cast(Any, None),
        required_checker_names=frozenset({"required"}),
        warning_checker_names=frozenset({"optional"}),
        blocking_severities=frozenset({"critical"}),
    )
    outcomes = [
        _checker_outcome("required", status="warning", severity="medium"),
        _checker_outcome("optional", status="warning", severity="medium"),
        _checker_outcome("critical", status="failed", severity="critical"),
    ]

    required, optional, critical = CheckerService._apply_blocking_policy(outcomes, context)

    assert (required.status, required.severity, required.blocks_review) == (
        "failed",
        "high",
        True,
    )
    assert required.worker_suggested_fix == (
        "Resolve this required checker finding before review can continue."
    )
    assert required.metadata == {"required_checker_warning_escalated": True}
    assert (optional.status, optional.blocks_review) == ("warning", False)
    assert critical.blocks_review is True


def test_blocking_policy_does_not_expose_fix_for_hidden_required_warning() -> None:
    context = CheckerContext(
        task=cast(Any, None),
        submission=cast(Any, None),
        required_checker_names=frozenset({"hidden"}),
        warning_checker_names=frozenset(),
        blocking_severities=frozenset(),
    )

    [adjusted] = CheckerService._apply_blocking_policy(
        [_checker_outcome("hidden", status="warning", severity="low", worker_visible=False)],
        context,
    )

    assert adjusted.blocks_review is True
    assert adjusted.worker_suggested_fix is None


def test_checker_transition_guard_maps_invalid_transition() -> None:
    CheckerService._ensure_transition_allowed("submitted", "evaluation_pending")
    with pytest.raises(CheckerExecutionBlocked):
        CheckerService._ensure_transition_allowed("draft", "accepted")


@pytest.mark.asyncio
async def test_worker_pre_submit_check_requires_checkable_task_state() -> None:
    actor = pre_review_gate_system_actor().model_copy(
        update={
            "actor_id": "worker-1",
            "external_subject": "worker-1",
            "external_issuer": "flow",
            "roles": ("worker",),
            "auth_source": "flow",
        }
    )
    service = object.__new__(CheckerService)
    service._get_task_for_actor = AsyncMock(
        return_value=SimpleNamespace(id="task-1", status="available")
    )

    with pytest.raises(CheckerExecutionBlocked, match="must be in progress"):
        await service.pre_submit_check(actor, "task-1", cast(Any, object()))


@pytest.mark.asyncio
async def test_pre_submit_check_summarizes_blocking_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    actor = pre_review_gate_system_actor()
    task = SimpleNamespace(id="task-1", status="in_progress")
    service = object.__new__(CheckerService)
    service._get_task_for_actor = AsyncMock(return_value=task)
    service._load_locked_pre_submit_context = AsyncMock(
        return_value=(
            SimpleNamespace(effective_policy={"manifest_required": True}),
            SimpleNamespace(checker_names=["required"]),
        )
    )
    monkeypatch.setattr(
        checker_service_module,
        "pre_submit_static_feedback",
        AsyncMock(return_value=[_checker_outcome("required", blocks_review=True)]),
    )

    response = await service.pre_submit_check(actor, "task-1", cast(Any, object()))

    assert response.status == "failed"
    assert response.eligible_to_submit is False
    assert response.results[0].would_block_if_submitted is True


@pytest.mark.asyncio
async def test_pre_submit_check_maps_unregistered_locked_checker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(CheckerService)
    service._get_task_for_actor = AsyncMock(
        return_value=SimpleNamespace(id="task-1", status="in_progress")
    )
    service._load_locked_pre_submit_context = AsyncMock(
        return_value=(
            SimpleNamespace(effective_policy={}),
            SimpleNamespace(checker_names=["unknown"]),
        )
    )
    monkeypatch.setattr(
        checker_service_module,
        "pre_submit_static_feedback",
        AsyncMock(side_effect=UnknownChecker("unknown")),
    )

    with pytest.raises(CheckerPolicyInvalid, match="unregistered checker"):
        await service.pre_submit_check(
            pre_review_gate_system_actor(),
            "task-1",
            cast(Any, object()),
        )


def _locked_post_submit_context() -> tuple[SimpleNamespace, SimpleNamespace]:
    body = {"schema_version": "invalid"}
    task = SimpleNamespace(
        project_id="project-1",
        locked_post_submit_checker_policy_id="post-1",
        locked_post_submit_checker_policy_version="v1",
        locked_post_submit_checker_policy_hash="sha256:post",
        locked_post_submit_checker_policy_body=body,
    )
    submission = SimpleNamespace(
        locked_post_submit_checker_policy_id="post-1",
        locked_post_submit_checker_policy_version="v1",
        locked_post_submit_checker_policy_hash="sha256:post",
        locked_post_submit_checker_policy_body=body,
    )
    return task, submission


@pytest.mark.asyncio
async def test_locked_post_submit_policy_rejects_incomplete_and_mismatched_locks() -> None:
    service = object.__new__(CheckerService)
    task, submission = _locked_post_submit_context()
    submission.locked_post_submit_checker_policy_id = None
    with pytest.raises(CheckerPolicyInvalid, match="context is incomplete"):
        await service._load_locked_post_submit_policy(cast(Any, task), cast(Any, submission))

    task, submission = _locked_post_submit_context()
    task.locked_post_submit_checker_policy_hash = "sha256:other"
    with pytest.raises(CheckerPolicyInvalid, match="does not match task lock"):
        await service._load_locked_post_submit_policy(cast(Any, task), cast(Any, submission))


@pytest.mark.asyncio
async def test_locked_post_submit_policy_rejects_missing_row_and_invalid_hash() -> None:
    service = object.__new__(CheckerService)
    task, submission = _locked_post_submit_context()
    service._project_repo = cast(
        Any,
        SimpleNamespace(get_post_submit_checker_policy_by_id=AsyncMock(return_value=None)),
    )
    with pytest.raises(CheckerPolicyInvalid, match="policy is invalid"):
        await service._load_locked_post_submit_policy(cast(Any, task), cast(Any, submission))

    policy = SimpleNamespace(
        project_id="project-1",
        guide_version="v1",
        policy_hash="sha256:post",
    )
    service._project_repo = cast(
        Any,
        SimpleNamespace(get_post_submit_checker_policy_by_id=AsyncMock(return_value=policy)),
    )
    with pytest.raises(CheckerPolicyInvalid, match="policy hash is invalid"):
        await service._load_locked_post_submit_policy(cast(Any, task), cast(Any, submission))


def _checker_run_for_redaction(routing: str = "allow_review") -> SimpleNamespace:
    now = datetime.now(UTC)
    visible = SimpleNamespace(
        id="result-visible",
        checker_run_id="run-1",
        task_id="task-1",
        submission_id="submission-1",
        checker_name="visible",
        status="passed",
        severity="info",
        blocks_review=False,
        message="internal visible detail",
        worker_message="safe detail",
        worker_suggested_fix=None,
        worker_evidence_refs=[],
        worker_visible=True,
        metadata_json={"internal": True},
        created_at=now,
    )
    hidden = SimpleNamespace(**(vars(visible) | {
        "id": "result-hidden",
        "checker_name": "hidden",
        "worker_visible": False,
    }))
    return SimpleNamespace(
        id="run-1",
        task_id="task-1",
        submission_id="submission-1",
        submission_version=1,
        trigger_source="manual_checker_trigger",
        status="completed",
        routing_recommendation=routing,
        outcome_source="auto_checker" if routing != "allow_review" else "none",
        triggered_by="actor-1",
        triggered_by_subject="subject-1",
        triggered_by_issuer="issuer-1",
        trigger_auth_source="flow",
        trigger_reason="verify",
        audit_event_id="audit-1",
        attempt_number=1,
        supersedes_checker_run_id=None,
        is_current_for_submission=True,
        locked_guide_version="v1",
        locked_post_submit_checker_policy_id="post-policy-1",
        locked_post_submit_checker_policy_version="v1",
        locked_post_submit_checker_policy_hash="sha256:post",
        locked_review_policy_id="review-1",
        locked_review_policy_generation=1,
        locked_review_policy_hash="sha256:review",
        locked_revision_policy_id="revision-1",
        locked_revision_policy_generation=1,
        locked_revision_policy_hash="sha256:revision",
        locked_payment_policy_version="v1",
        package_hash="sha256:package",
        artifact_hash_manifest=[{"artifact": "answer.md", "hash": "sha256:answer"}],
        artifact_manifest_hash="sha256:manifest",
        passed_count=1,
        warning_count=0,
        failed_count=0,
        blocking_count=0,
        queued_at=now,
        started_at=now,
        completed_at=now,
        failure_code=None,
        failure_message=None,
        created_at=now,
        results=[visible, hidden],
    )


def test_checker_run_response_redacts_internal_fields_by_actor_access() -> None:
    service = object.__new__(CheckerService)
    actor = pre_review_gate_system_actor()

    admin = service._run_response_for_actor(
        actor,
        cast(Any, _checker_run_for_redaction()),
        has_checker_admin_access=True,
    )
    worker = service._run_response_for_actor(
        actor,
        cast(Any, _checker_run_for_redaction()),
        has_checker_admin_access=False,
    )
    hidden_route = service._run_response_for_actor(
        actor,
        cast(Any, _checker_run_for_redaction("checker_retry")),
        has_checker_admin_access=False,
    )

    assert len(admin.results) == 2
    assert admin.results[0].message == "internal visible detail"
    assert admin.results[0].metadata == {"internal": True}
    assert admin.triggered_by == "actor-1"
    assert [result.checker_name for result in worker.results] == ["visible"]
    assert worker.results[0].message is None
    assert worker.results[0].metadata == {}
    assert worker.triggered_by is None
    assert worker.routing_recommendation is None
    assert hidden_route.results == []
    assert hidden_route.passed_count == 0


@pytest.mark.parametrize(
    ("status", "started_at", "expected"),
    [
        ("queued", datetime.now(UTC) - timedelta(hours=1), False),
        ("running", None, False),
        ("running", datetime.now(UTC), False),
        (
            "running",
            datetime.now(UTC).replace(tzinfo=None)
            - PRE_REVIEW_GATE_RUNNING_TIMEOUT
            - timedelta(seconds=1),
            True,
        ),
    ],
)
def test_stale_automatic_gate_detection_is_bounded(
    status: str,
    started_at: datetime | None,
    expected: bool,
) -> None:
    run = SimpleNamespace(
        status=status,
        started_at=started_at,
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
    )
    service = object.__new__(CheckerService)

    assert service._is_stale_running_pre_review_gate(cast(Any, run)) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [False, True])
async def test_gate_enqueue_failure_commits_only_successful_transition(succeeded: bool) -> None:
    calls: list[str] = []

    class Session:
        async def commit(self) -> None:
            calls.append("commit")

        async def rollback(self) -> None:
            calls.append("rollback")

    class Repository:
        async def mark_automatic_gate_enqueue_failed(self, **kwargs: Any) -> bool:
            assert kwargs["checker_run_id"] == "run-1"
            assert kwargs["failure_code"] == "pre_review_gate_enqueue_failed"
            return succeeded

    service = object.__new__(CheckerService)
    service._session = cast(Any, Session())
    service._checker_repo = cast(Any, Repository())

    assert await service.mark_pre_review_gate_enqueue_failed("run-1") is succeeded
    assert calls == ["commit" if succeeded else "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [False, True])
async def test_gate_repair_dispatch_commits_only_successful_claim(claimed: bool) -> None:
    calls: list[str] = []

    class Session:
        async def commit(self) -> None:
            calls.append("commit")

        async def rollback(self) -> None:
            calls.append("rollback")

    class Repository:
        async def claim_queued_automatic_gate_repair_dispatch(self, **kwargs: Any) -> bool:
            assert kwargs["checker_run_id"] == "run-1"
            assert kwargs["claimed_trigger_reason"].endswith("repair redispatch claimed")
            return claimed

    service = object.__new__(CheckerService)
    service._session = cast(Any, Session())
    service._checker_repo = cast(Any, Repository())

    assert await service.claim_pre_review_gate_repair_dispatch("run-1") is claimed
    assert calls == ["commit" if claimed else "rollback"]


@pytest.mark.asyncio
async def test_manual_checker_run_persists_policy_adjusted_outcomes() -> None:
    actor = pre_review_gate_system_actor()
    submission = SimpleNamespace(
        id="submission-1",
        task_id="task-1",
        locked_at=datetime.now(UTC),
        artifact_hash_manifest=[{"artifact": "answer.md", "hash": "sha256:answer"}],
    )
    task = SimpleNamespace(id="task-1", status="submitted")
    persisted = _checker_run_for_redaction()
    built_run = SimpleNamespace(id="run-1")
    captured: dict[str, Any] = {}

    class Session:
        async def commit(self) -> None:
            captured["committed"] = True

        async def rollback(self) -> None:
            raise AssertionError("successful checker run must not roll back")

    class TaskRepository:
        async def get_latest_submission_for_task(self, task_id: str) -> Any:
            assert task_id == "task-1"
            return submission

    class CheckerRepository:
        async def get_current_run_for_submission(self, submission_id: str) -> None:
            assert submission_id == "submission-1"
            return None

        async def add_run(self, checker_run: Any) -> Any:
            assert checker_run is built_run
            captured["added"] = checker_run
            return checker_run

        async def get_run(self, checker_run_id: str) -> Any:
            assert checker_run_id == "run-1"
            return persisted

    class Registry:
        def require_registered(self, names: set[str]) -> None:
            assert names == {"required"}

        async def run(self, context: CheckerContext, names: list[str]) -> list[CheckerOutcome]:
            assert names == ["required"]
            assert context.effective_policy == {"manifest_required": True}
            return [_checker_outcome("required", status="warning", severity="medium")]

    service = object.__new__(CheckerService)
    service._session = cast(Any, Session())
    service._task_repo = cast(Any, TaskRepository())
    service._checker_repo = cast(Any, CheckerRepository())
    service._registry = cast(Any, Registry())
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task_for_actor = AsyncMock(return_value=task)
    service._ensure_checker_trigger_authorized = lambda *_args: None
    service._load_locked_post_submit_policy = AsyncMock(
        return_value=SimpleNamespace(
            execution_checkers=["required"],
            required_checkers=["required"],
            warning_checkers=[],
            blocking_severities=["high"],
        )
    )
    service._load_locked_pre_submit_context = AsyncMock(
        return_value=(SimpleNamespace(effective_policy={"manifest_required": True}), object())
    )
    service._enter_evaluation_pending = AsyncMock()
    service._write_checker_audit = AsyncMock(return_value=SimpleNamespace(id="audit-1"))

    def build_run(**kwargs: Any) -> Any:
        captured["build"] = kwargs
        return built_run

    service._build_checker_run = build_run
    service._apply_pre_review_gate_result = AsyncMock()
    response = object()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, response)

    result = await service.run_submission_checkers(
        actor,
        "submission-1",
        "operator verification",
    )

    assert result is response
    assert captured["committed"] is True
    assert captured["added"] is built_run
    assert captured["build"]["outcomes"][0].status == "failed"
    assert captured["build"]["outcomes"][0].blocks_review is True
    assert captured["build"]["attempt_number"] == 1
    assert captured["build"]["artifact_manifest_hash"].startswith("sha256:")
    service._enter_evaluation_pending.assert_awaited_once()
    service._apply_pre_review_gate_result.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_checker_run_blocks_while_automatic_gate_is_unfinished() -> None:
    actor = pre_review_gate_system_actor()
    submission = SimpleNamespace(
        id="submission-1",
        task_id="task-1",
        locked_at=datetime.now(UTC),
    )
    task = SimpleNamespace(id="task-1", status="submitted")
    current = SimpleNamespace(
        status="queued",
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
    )
    service = object.__new__(CheckerService)
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task_for_actor = AsyncMock(return_value=task)
    service._ensure_checker_trigger_authorized = lambda *_args: None
    service._task_repo = cast(
        Any,
        SimpleNamespace(get_latest_submission_for_task=AsyncMock(return_value=submission)),
    )
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_current_run_for_submission=AsyncMock(return_value=current)),
    )

    with pytest.raises(CheckerExecutionBlocked, match="must be repaired"):
        await service.run_submission_checkers(actor, "submission-1", "manual retry")


@pytest.mark.asyncio
async def test_automatic_gate_queue_persists_one_current_claim() -> None:
    submission = SimpleNamespace(
        id="submission-1",
        task_id="task-1",
        version=3,
        locked_at=datetime.now(UTC),
        locked_guide_version="v1",
        locked_post_submit_checker_policy_id="post-1",
        locked_post_submit_checker_policy_version="v1",
        locked_post_submit_checker_policy_hash="sha256:post",
        locked_post_submit_checker_policy_body={"execution_checkers": []},
        locked_review_policy_id="review-1",
        locked_review_policy_generation=1,
        locked_review_policy_hash="sha256:review",
        locked_revision_policy_id="revision-1",
        locked_revision_policy_generation=1,
        locked_revision_policy_hash="sha256:revision",
        locked_payment_policy_version="v1",
        package_hash="sha256:package",
        artifact_hash_manifest=[{"artifact": "answer.md", "hash": "sha256:answer"}],
    )
    task = SimpleNamespace(id="task-1")
    stored: dict[str, Any] = {}

    class Session:
        async def commit(self) -> None:
            stored["committed"] = True

        async def rollback(self) -> None:
            raise AssertionError("new automatic gate must not roll back")

    class TaskRepository:
        async def get_latest_submission_for_task(self, task_id: str) -> Any:
            assert task_id == "task-1"
            return submission

    class CheckerRepository:
        async def get_current_run_for_submission(self, submission_id: str) -> None:
            assert submission_id == "submission-1"
            return None

        async def add_run(self, checker_run: Any) -> Any:
            stored["run"] = checker_run
            return checker_run

        async def get_run(self, checker_run_id: str) -> Any:
            assert checker_run_id == stored["run"].id
            return stored["run"]

    service = object.__new__(CheckerService)
    service._session = cast(Any, Session())
    service._task_repo = cast(Any, TaskRepository())
    service._checker_repo = cast(Any, CheckerRepository())
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task_for_actor = AsyncMock(return_value=task)
    response = object()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, response)

    result, should_enqueue = await service.ensure_automatic_pre_review_gate_queued(
        "submission-1"
    )

    assert result is response
    assert should_enqueue is True
    assert stored["committed"] is True
    assert stored["run"].status == "queued"
    assert stored["run"].submission_version == 3
    assert stored["run"].triggered_by == PRE_REVIEW_GATE_SYSTEM_ACTOR_ID
    assert stored["run"].artifact_manifest_hash.startswith("sha256:")


@pytest.mark.asyncio
@pytest.mark.parametrize("force_enqueue", [False, True])
async def test_automatic_gate_queue_reuses_existing_queued_claim(force_enqueue: bool) -> None:
    submission = SimpleNamespace(id="submission-1", task_id="task-1", locked_at=datetime.now(UTC))
    current = SimpleNamespace(
        status="queued",
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
    )
    service = object.__new__(CheckerService)
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task_for_actor = AsyncMock(return_value=SimpleNamespace(id="task-1"))
    service._task_repo = cast(
        Any,
        SimpleNamespace(get_latest_submission_for_task=AsyncMock(return_value=submission)),
    )
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_current_run_for_submission=AsyncMock(return_value=current)),
    )
    response = object()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, response)

    result, should_enqueue = await service.ensure_automatic_pre_review_gate_queued(
        "submission-1",
        force_enqueue_queued=force_enqueue,
    )

    assert result is response
    assert should_enqueue is force_enqueue


@pytest.mark.asyncio
async def test_automatic_gate_queue_requeues_failed_current_claim() -> None:
    submission = SimpleNamespace(id="submission-1", task_id="task-1", locked_at=datetime.now(UTC))
    current = SimpleNamespace(id="run-1", status="failed")
    persisted = SimpleNamespace(id="run-1", status="queued")
    service = object.__new__(CheckerService)
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task_for_actor = AsyncMock(return_value=SimpleNamespace(id="task-1"))
    service._task_repo = cast(
        Any,
        SimpleNamespace(get_latest_submission_for_task=AsyncMock(return_value=submission)),
    )
    service._checker_repo = cast(
        Any,
        SimpleNamespace(
            get_current_run_for_submission=AsyncMock(return_value=current),
            get_run=AsyncMock(return_value=persisted),
        ),
    )
    service._replace_stale_running_pre_review_gate = AsyncMock(return_value=None)
    service._requeue_failed_pre_review_gate_if_needed = AsyncMock(return_value=True)
    service._session = cast(Any, SimpleNamespace(refresh=AsyncMock()))
    response = object()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, response)

    result, should_enqueue = await service.ensure_automatic_pre_review_gate_queued(
        "submission-1"
    )

    assert result is response
    assert should_enqueue is True
    service._replace_stale_running_pre_review_gate.assert_awaited_once_with(current)
    service._requeue_failed_pre_review_gate_if_needed.assert_awaited_once_with(current)
    service._session.refresh.assert_awaited_once_with(persisted)


@pytest.mark.asyncio
@pytest.mark.parametrize("winner_exists", [False, True])
async def test_automatic_gate_queue_reconciles_concurrent_insert(winner_exists: bool) -> None:
    submission = SimpleNamespace(
        id="submission-1",
        task_id="task-1",
        version=1,
        locked_at=datetime.now(UTC),
        locked_guide_version="v1",
        locked_post_submit_checker_policy_id="post-1",
        locked_post_submit_checker_policy_version="v1",
        locked_post_submit_checker_policy_hash="sha256:post",
        locked_post_submit_checker_policy_body={},
        locked_review_policy_id="review-1",
        locked_review_policy_generation=1,
        locked_review_policy_hash="sha256:review",
        locked_revision_policy_id="revision-1",
        locked_revision_policy_generation=1,
        locked_revision_policy_hash="sha256:revision",
        locked_payment_policy_version="v1",
        package_hash="sha256:package",
        artifact_hash_manifest=[],
    )
    winner = SimpleNamespace(id="winner") if winner_exists else None

    class Repository:
        def __init__(self) -> None:
            self.current_calls = 0

        async def get_current_run_for_submission(self, _submission_id: str) -> Any:
            self.current_calls += 1
            return None if self.current_calls == 1 else winner

        async def add_run(self, _checker_run: Any) -> Any:
            raise IntegrityError("insert", {}, Exception("unique current run"))

    service = object.__new__(CheckerService)
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task_for_actor = AsyncMock(return_value=SimpleNamespace(id="task-1"))
    service._task_repo = cast(
        Any,
        SimpleNamespace(get_latest_submission_for_task=AsyncMock(return_value=submission)),
    )
    service._checker_repo = cast(Any, Repository())
    service._session = cast(
        Any,
        SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock()),
    )
    response = object()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, response)

    if winner_exists:
        assert await service.ensure_automatic_pre_review_gate_queued("submission-1") == (
            response,
            False,
        )
    else:
        with pytest.raises(CheckerConflict, match="conflicted with another attempt"):
            await service.ensure_automatic_pre_review_gate_queued("submission-1")
    service._session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_queued_gate_rejects_non_system_actor_and_missing_claim() -> None:
    actor = pre_review_gate_system_actor().model_copy(
        update={"actor_id": "caller", "auth_source": "flow"}
    )
    service = object.__new__(CheckerService)
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_run=AsyncMock(return_value=None)),
    )

    with pytest.raises(PermissionDenied, match="only the pre-review gate system actor"):
        await service.run_queued_pre_review_gate(actor, "run-1", requester_provenance={})
    with pytest.raises(CheckerRunNotFound, match="checker run not found"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance={},
        )


@pytest.mark.asyncio
async def test_queued_gate_rejects_non_current_or_foreign_claim() -> None:
    candidate = SimpleNamespace(
        is_current_for_submission=False,
        trigger_source="manual_checker_trigger",
    )
    service = object.__new__(CheckerService)
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_run=AsyncMock(return_value=candidate)),
    )

    with pytest.raises(CheckerExecutionBlocked, match="not an automatic pre-review gate"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance={},
        )


@pytest.mark.asyncio
async def test_queued_gate_reports_running_claim_after_atomic_claim_loses() -> None:
    checker_run = SimpleNamespace(
        status="running",
        is_current_for_submission=True,
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
    )
    service = object.__new__(CheckerService)
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_run=AsyncMock(return_value=checker_run)),
    )
    service._claim_queued_pre_review_gate = AsyncMock(return_value=False)
    service._session = cast(Any, SimpleNamespace(refresh=AsyncMock()))

    with pytest.raises(CheckerConflict, match="already running"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance={},
        )


@pytest.mark.asyncio
async def test_queued_gate_reports_claim_removed_after_atomic_claim() -> None:
    candidate = SimpleNamespace(
        is_current_for_submission=True,
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
    )
    responses = iter([candidate, None])
    service = object.__new__(CheckerService)
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_run=AsyncMock(side_effect=lambda _run_id: next(responses))),
    )
    service._claim_queued_pre_review_gate = AsyncMock(return_value=True)

    with pytest.raises(CheckerRunNotFound, match="checker run not found"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance={},
        )


@pytest.mark.asyncio
async def test_queued_gate_executes_locked_policy_and_persists_completion() -> None:
    actor = pre_review_gate_system_actor()
    requester = {
        "requester_actor_id": "requester-1",
        "requester_external_subject": "subject-1",
        "requester_external_issuer": "issuer-1",
        "requester_auth_source": "flow",
    }
    checker_run = SimpleNamespace(
        id="run-1",
        submission_id="submission-1",
        attempt_number=2,
        trigger_reason="automatic gate",
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
        is_current_for_submission=True,
        status="queued",
    )
    submission = SimpleNamespace(
        id="submission-1",
        task_id="task-1",
        locked_at=datetime.now(UTC),
        artifact_hash_manifest=[{"artifact": "answer.md", "hash": "sha256:answer"}],
    )
    task = SimpleNamespace(id="task-1", status="submitted")
    calls: list[str] = []

    class Session:
        async def refresh(self, value: Any) -> None:
            assert value is checker_run
            calls.append("refresh")

        async def commit(self) -> None:
            calls.append("commit")

        async def rollback(self) -> None:
            raise AssertionError("successful queued gate must not roll back")

    class Repository:
        async def get_run(self, checker_run_id: str) -> Any:
            assert checker_run_id == "run-1"
            return checker_run

    class TaskRepository:
        async def get_latest_submission_for_task(self, task_id: str) -> Any:
            assert task_id == "task-1"
            return submission

    class Registry:
        def require_registered(self, names: set[str]) -> None:
            assert names == {"required"}

        async def run(self, context: CheckerContext, names: list[str]) -> list[CheckerOutcome]:
            assert names == ["required"]
            assert context.effective_policy == {"manifest_required": True}
            return [_checker_outcome("required", status="warning", severity="medium")]

    service = object.__new__(CheckerService)
    service._session = cast(Any, Session())
    service._checker_repo = cast(Any, Repository())
    service._task_repo = cast(Any, TaskRepository())
    service._registry = cast(Any, Registry())
    service._claim_queued_pre_review_gate = AsyncMock(return_value=True)
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task_for_actor = AsyncMock(return_value=task)
    service._submission_requester_provenance = AsyncMock(return_value=requester)
    service._assert_pre_review_gate_claim_still_current = AsyncMock()
    service._enter_evaluation_pending = AsyncMock()
    service._load_locked_post_submit_policy = AsyncMock(
        return_value=SimpleNamespace(
            execution_checkers=["required"],
            required_checkers=["required"],
            warning_checkers=[],
            blocking_severities=["high"],
        )
    )
    service._load_locked_pre_submit_context = AsyncMock(
        return_value=(SimpleNamespace(effective_policy={"manifest_required": True}), object())
    )
    service._write_checker_audit = AsyncMock(return_value=SimpleNamespace(id="audit-1"))
    service._complete_claimed_checker_run = AsyncMock()
    service._apply_pre_review_gate_result = AsyncMock()
    response = object()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, response)

    result = await service.run_queued_pre_review_gate(
        actor,
        "run-1",
        requester_provenance=requester,
    )

    assert result is response
    assert calls == ["refresh", "commit"]
    service._enter_evaluation_pending.assert_awaited_once()
    service._complete_claimed_checker_run.assert_awaited_once()
    completed = service._complete_claimed_checker_run.await_args.kwargs
    assert completed["outcomes"][0].status == "failed"
    assert completed["outcomes"][0].blocks_review is True
    assert completed["artifact_manifest_hash"].startswith("sha256:")
    assert service._assert_pre_review_gate_claim_still_current.await_count == 2


def _queued_gate_failure_service(
    *,
    submission: SimpleNamespace | None = None,
    task: SimpleNamespace | None = None,
    latest_submission: SimpleNamespace | None = None,
) -> tuple[CheckerService, SimpleNamespace, SimpleNamespace, dict[str, str]]:
    requester = {
        "requester_actor_id": "requester-1",
        "requester_external_subject": "subject-1",
        "requester_external_issuer": "issuer-1",
        "requester_auth_source": "flow",
    }
    checker_run = SimpleNamespace(
        id="run-1",
        submission_id="submission-1",
        attempt_number=1,
        trigger_reason="automatic gate",
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
        is_current_for_submission=True,
        status="queued",
    )
    resolved_submission = submission or SimpleNamespace(
        id="submission-1",
        task_id="task-1",
        locked_at=datetime.now(UTC),
        artifact_hash_manifest=[{"artifact": "answer.md", "hash": "sha256:answer"}],
    )
    resolved_task = task or SimpleNamespace(id="task-1", status="submitted")
    resolved_latest = latest_submission if latest_submission is not None else resolved_submission

    service = object.__new__(CheckerService)
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_run=AsyncMock(return_value=checker_run)),
    )
    service._task_repo = cast(
        Any,
        SimpleNamespace(
            get_latest_submission_for_task=AsyncMock(return_value=resolved_latest),
        ),
    )
    service._session = cast(
        Any,
        SimpleNamespace(
            refresh=AsyncMock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        ),
    )
    service._claim_queued_pre_review_gate = AsyncMock(return_value=True)
    service._get_submission = AsyncMock(return_value=resolved_submission)
    service._get_task_for_actor = AsyncMock(return_value=resolved_task)
    service._fail_claimed_pre_review_gate = AsyncMock()
    service._submission_requester_provenance = AsyncMock(return_value=requester)
    service._assert_pre_review_gate_claim_still_current = AsyncMock()
    service._enter_evaluation_pending = AsyncMock()
    service._load_locked_post_submit_policy = AsyncMock(
        return_value=SimpleNamespace(
            execution_checkers=["required"],
            required_checkers=["required"],
            warning_checkers=[],
            blocking_severities=["high"],
        )
    )
    service._load_locked_pre_submit_context = AsyncMock(
        return_value=(SimpleNamespace(effective_policy={"manifest_required": True}), object())
    )
    service._registry = cast(
        Any,
        SimpleNamespace(
            require_registered=lambda _names: None,
            run=AsyncMock(return_value=[_checker_outcome("required")]),
        ),
    )
    service._write_checker_audit = AsyncMock(return_value=SimpleNamespace(id="audit-1"))
    service._complete_claimed_checker_run = AsyncMock()
    service._apply_pre_review_gate_result = AsyncMock()
    service._fail_running_pre_review_gate_by_id = AsyncMock()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, object())
    return service, checker_run, resolved_submission, requester


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condition", "message", "failure_code"),
    [
        ("unlocked", "must be locked", "submission_not_locked"),
        ("stale", "only latest submission", "stale_submission_version"),
        ("bad_status", "submitted or in checker gate", "task_status_not_checkable"),
    ],
)
async def test_queued_gate_fails_claim_for_stale_submission_state(
    condition: str,
    message: str,
    failure_code: str,
) -> None:
    submission = SimpleNamespace(
        id="submission-1",
        task_id="task-1",
        locked_at=None if condition == "unlocked" else datetime.now(UTC),
        artifact_hash_manifest=[],
    )
    task = SimpleNamespace(
        id="task-1",
        status="draft" if condition == "bad_status" else "submitted",
    )
    latest = SimpleNamespace(id="newer-submission") if condition == "stale" else submission
    service, _run, _submission, requester = _queued_gate_failure_service(
        submission=submission,
        task=task,
        latest_submission=latest,
    )

    with pytest.raises(CheckerExecutionBlocked, match=message):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance=requester,
        )

    assert service._fail_claimed_pre_review_gate.await_args.kwargs["failure_code"] == failure_code


@pytest.mark.asyncio
async def test_queued_gate_fails_claim_when_locked_audit_provenance_is_missing() -> None:
    service, _run, _submission, requester = _queued_gate_failure_service()
    service._submission_requester_provenance = AsyncMock(
        side_effect=CheckerExecutionBlocked("submission lock audit provenance is missing")
    )

    with pytest.raises(CheckerExecutionBlocked, match="audit provenance is missing"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance=requester,
        )

    assert service._fail_claimed_pre_review_gate.await_args.kwargs["failure_code"] == (
        "submission_lock_audit_missing"
    )


@pytest.mark.asyncio
async def test_queued_gate_rejects_requester_provenance_mismatch() -> None:
    service, _run, _submission, requester = _queued_gate_failure_service()

    with pytest.raises(CheckerExecutionBlocked, match="did not match"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance=requester | {"requester_actor_id": "attacker"},
        )

    assert service._fail_claimed_pre_review_gate.await_args.kwargs["failure_code"] == (
        "requester_provenance_mismatch"
    )


@pytest.mark.asyncio
async def test_queued_gate_records_invalid_locked_policy_failure() -> None:
    service, _run, _submission, requester = _queued_gate_failure_service()
    service._load_locked_post_submit_policy = AsyncMock(
        side_effect=CheckerPolicyInvalid("locked policy invalid")
    )

    with pytest.raises(CheckerPolicyInvalid, match="locked policy invalid"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance=requester,
        )

    assert service._fail_claimed_pre_review_gate.await_args.kwargs["failure_code"] == (
        "pre_review_gate_execution_failed"
    )


@pytest.mark.asyncio
async def test_queued_gate_maps_unknown_registered_checker_to_policy_failure() -> None:
    service, _run, _submission, requester = _queued_gate_failure_service()

    def reject(_names: set[str]) -> None:
        raise UnknownChecker("unregistered checker policy names: required")

    service._registry.require_registered = reject

    with pytest.raises(CheckerPolicyInvalid, match="unregistered checker"):
        await service.run_queued_pre_review_gate(
            pre_review_gate_system_actor(),
            "run-1",
            requester_provenance=requester,
        )

    assert service._fail_claimed_pre_review_gate.await_args.kwargs["failure_code"] == (
        "unknown_checker"
    )


@pytest.mark.asyncio
async def test_queued_gate_returns_completed_claim_when_atomic_claim_loses() -> None:
    actor = pre_review_gate_system_actor()
    checker_run = SimpleNamespace(
        id="run-1",
        status="completed",
        is_current_for_submission=True,
        trigger_source=PRE_REVIEW_GATE_TRIGGER_SOURCE,
        triggered_by=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_subject=PRE_REVIEW_GATE_SYSTEM_ACTOR_ID,
        triggered_by_issuer=PRE_REVIEW_GATE_SYSTEM_ISSUER,
        trigger_auth_source="workstream_system",
    )
    service = object.__new__(CheckerService)
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_run=AsyncMock(return_value=checker_run)),
    )
    service._claim_queued_pre_review_gate = AsyncMock(return_value=False)
    service._session = cast(Any, SimpleNamespace(refresh=AsyncMock()))
    response = object()
    service._run_response_for_actor = lambda *_args, **_kwargs: cast(Any, response)

    assert (
        await service.run_queued_pre_review_gate(actor, "run-1", requester_provenance={})
        is response
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_pre_review_gate_repair_snapshot_preserves_previous_state(existing: bool) -> None:
    started_at = datetime.now(UTC)
    checker_run = (
        SimpleNamespace(
            id="run-1",
            status="failed",
            failure_code="broker_error",
            failure_message="queue unavailable",
            started_at=started_at,
        )
        if existing
        else None
    )
    service = object.__new__(CheckerService)
    service._checker_repo = cast(
        Any,
        SimpleNamespace(get_current_run_for_submission=AsyncMock(return_value=checker_run)),
    )

    snapshot = await service.pre_review_gate_repair_snapshot("submission-1")

    if existing:
        assert snapshot == {
            "previous_checker_run_id": "run-1",
            "previous_status": "failed",
            "previous_failure_code": "broker_error",
            "previous_failure_message": "queue unavailable",
            "previous_started_at": started_at.isoformat(),
        }
    else:
        assert snapshot == {
            "previous_checker_run_id": None,
            "previous_status": None,
            "previous_failure_code": None,
            "previous_failure_message": None,
            "previous_started_at": None,
        }


@pytest.mark.asyncio
async def test_checker_domain_loaders_hide_missing_resources() -> None:
    actor = pre_review_gate_system_actor()
    service = object.__new__(CheckerService)
    service._task_repo = cast(
        Any,
        SimpleNamespace(
            get_submission=AsyncMock(return_value=None),
            get_task=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(CheckerSubmissionNotFound, match="submission not found"):
        await service._get_submission("missing-submission")
    with pytest.raises(CheckerTaskNotFound, match="task not found"):
        await service._get_task_for_actor(actor, "missing-task")


def test_checker_trigger_authorization_accepts_only_system_or_scoped_manager() -> None:
    system = pre_review_gate_system_actor()
    CheckerService._ensure_checker_trigger_authorized(system, cast(Any, object()))

    untrusted = system.model_copy(
        update={
            "actor_id": "caller-1",
            "external_subject": "caller-1",
            "external_issuer": "flow",
            "roles": (),
            "auth_source": "flow",
        }
    )
    with pytest.raises(PermissionDenied, match="not authorized"):
        CheckerService._ensure_checker_trigger_authorized(
            untrusted,
            cast(Any, SimpleNamespace(created_by="someone-else")),
        )


@pytest.mark.asyncio
async def test_public_checkers_fail_closed_without_effective_policy() -> None:
    context = CheckerContext(
        task=cast(Any, SimpleNamespace(acceptance_criteria="")),
        submission=cast(
            Any,
            SimpleNamespace(
                artifact_hash_manifest=[],
                evidence_items=[],
                worker_attestation="",
            ),
        ),
        required_checker_names=frozenset(),
        warning_checker_names=frozenset(),
        blocking_severities=frozenset(),
        effective_policy=None,
    )

    outcomes = [
        await checker_runner_module.check_evidence_present(context),
        await checker_runner_module.check_required_files(context),
        await checker_runner_module.check_forbidden_files(context),
        await checker_runner_module.check_confidentiality_attestation(context),
        await checker_runner_module.check_acceptance_criteria_present(context),
    ]

    assert all(outcome.blocks_review for outcome in outcomes)
    assert all(outcome.routing_recommendation == "task_setup_blocked" for outcome in outcomes)
    assert all(outcome.worker_visible is False for outcome in outcomes)


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


async def get_submission_and_automatic_pre_review_run(
    client: AsyncClient,
    submission_id: str,
) -> tuple[dict, dict]:
    """Return a locked submission and its automatic pre-review checker run.

    Args:
        client: API client using the current test actor.
        submission_id: Submission id to inspect.

    Returns:
        Submission payload and the first automatic checker run payload.
    """
    submission = await client.get(
        f"/api/v1/submissions/{submission_id}",
        headers=auth_headers(),
    )
    assert submission.status_code == 200, submission.text

    listed = await client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    runs = listed.json()
    assert len(runs) == 1
    assert runs[0]["trigger_source"] == "submission_finalized"
    assert runs[0]["attempt_number"] == 1
    return submission.json(), runs[0]


async def run_manual_checker_retry(
    client: AsyncClient,
    submission_id: str,
    reason: str = "manual checker retry",
) -> dict:
    """Run an explicit operator checker retry for a locked submission.

    Args:
        client: API client using an authorized operator actor.
        submission_id: Submission id whose locked packet should be rechecked.
        reason: Required audit reason for the manual checker trigger.

    Returns:
        The persisted checker run payload.
    """
    response = await client.post(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": reason},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trigger_source"] == "manual_checker_trigger"
    return body


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
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "description": "Project for the Chunk 10 checker trial.",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    guide_payload = complete_guide_payload()
    guide_response = await client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    await create_policy_bundle_for_guide(
        client,
        project["id"],
        guide_response.json()["id"],
        post_submit_required_checkers=required_checkers,
    )
    activation_response = await activate_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide_response.json()["id"],
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
        result_by_name["check_low_quality_generated_artifacts"][
            "would_block_if_submitted"
        ]
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
    _, body = await get_submission_and_automatic_pre_review_run(
        checker_client, created.json()["id"]
    )
    assert body["status"] == "completed"
    assert body["trigger_source"] == "submission_finalized"
    assert body["routing_recommendation"] == "allow_review"
    assert body["outcome_source"] == "none"
    assert body["submission_version"] == 1
    expected_post_submit_policy = await load_post_submit_checker_policy(project["id"])
    assert body["locked_post_submit_checker_policy_id"] == expected_post_submit_policy["id"]
    assert body["locked_post_submit_checker_policy_version"] == "v1"
    assert (
        body["locked_post_submit_checker_policy_hash"] == expected_post_submit_policy["policy_hash"]
    )
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
    assert audit.reason == "submission locked for automatic pre-review gate"
    assert audit.event_payload["submission_version"] == 1
    assert audit.event_payload["trigger_source"] == "submission_finalized"
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
    assert (
        task.locked_review_policy_id,
        task.locked_review_policy_generation,
        task.locked_review_policy_hash,
    ) == (
        submission.locked_review_policy_id,
        submission.locked_review_policy_generation,
        submission.locked_review_policy_hash,
    ) == (
        checker_run.locked_review_policy_id,
        checker_run.locked_review_policy_generation,
        checker_run.locked_review_policy_hash,
    )
    assert (
        task.locked_revision_policy_id,
        task.locked_revision_policy_generation,
        task.locked_revision_policy_hash,
    ) == (
        submission.locked_revision_policy_id,
        submission.locked_revision_policy_generation,
        submission.locked_revision_policy_hash,
    ) == (
        checker_run.locked_revision_policy_id,
        checker_run.locked_revision_policy_generation,
        checker_run.locked_revision_policy_hash,
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
        "submission_finalized"
    )
    assert audit_events["pre_review_gate_passed"]["event_payload"]["trigger_source"] == (
        "submission_finalized"
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
            (
                await session.execute(
                    select(CheckerRun).where(CheckerRun.submission_id == created.json()["id"])
                )
            )
            .scalars()
            .all()
        )
        results = (
            (
                await session.execute(
                    select(CheckerResult).where(CheckerResult.submission_id == created.json()["id"])
                )
            )
            .scalars()
            .all()
        )
    assert task is not None
    assert task.status == "review_pending"
    assert submission is not None
    assert submission.locked_at is not None
    assert len(runs) == 1
    assert results != []


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
        f"/api/v1/submissions/{created.json()['id']}/finalize",
        headers=auth_headers(),
    )

    assert locked.status_code == 200, locked.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, created.json()["id"])
        runs = (
            (
                await session.execute(
                    select(CheckerRun).where(CheckerRun.submission_id == created.json()["id"])
                )
            )
            .scalars()
            .all()
        )
        results = (
            (
                await session.execute(
                    select(CheckerResult).where(CheckerResult.submission_id == created.json()["id"])
                )
            )
            .scalars()
            .all()
        )
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
    assert "check_acceptance_criteria_present" not in {result.checker_name for result in results}
    assert results != []


async def test_submission_rejects_malformed_locked_post_submit_policy_body_without_side_effects(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        corrupted_body = dict(task.locked_post_submit_checker_policy_body or {})
        corrupted_body["required_checkers"] = [
            "check_policy_context_present",
            "check_evidence_present",
        ]
        task.locked_post_submit_checker_policy_body = corrupted_body
        await session.commit()

    rejected = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "task_locked_context_invalid"
    assert rejected.json()["details"]["field"] == "locked_post_submit_checker_policy_body"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        runs = (
            (
                await session.execute(
                    select(CheckerRun)
                    .join(Submission, CheckerRun.submission_id == Submission.id)
                    .where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        results = (
            (
                await session.execute(
                    select(CheckerResult)
                    .join(Submission, CheckerResult.submission_id == Submission.id)
                    .where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        audit_events = (
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.entity_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )

    assert task is not None
    assert task.status == "in_progress"
    assert submissions == []
    assert runs == []
    assert results == []
    assert "submission_created" not in {event.event_type for event in audit_events}
    assert "submission_finalized" not in {event.event_type for event in audit_events}
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
            (
                await session.execute(
                    select(CheckerRun).where(CheckerRun.submission_id == created.json()["id"])
                )
            )
            .scalars()
            .all()
        )
        results = (
            (
                await session.execute(
                    select(CheckerResult).where(CheckerResult.submission_id == created.json()["id"])
                )
            )
            .scalars()
            .all()
        )
    assert task is not None
    assert task.status == "review_pending"
    assert submission is not None
    assert submission.locked_at is not None
    assert submission.locked_post_submit_checker_policy_hash != "sha256:" + "0" * 64
    assert len(runs) == 1
    assert results != []


async def test_database_rejects_checker_run_with_another_tasks_submission(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    first_task = await create_started_task(checker_client, project["id"], monkeypatch)
    first = await checker_client.post(
        f"/api/v1/tasks/{first_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    second_task = await create_started_task(
        checker_client, project["id"], monkeypatch, subject="worker-two"
    )
    second = await checker_client.post(
        f"/api/v1/tasks/{second_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert first.status_code == second.status_code == 201

    async with db_session.get_session_factory()() as session:
        checker_run = await session.scalar(
            select(CheckerRun).where(CheckerRun.submission_id == first.json()["id"])
        )
        assert checker_run is not None
        checker_run.task_id = second_task["id"]
        with pytest.raises(IntegrityError):
            await session.commit()


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
    body = await run_manual_checker_retry(
        checker_client,
        created.json()["id"],
        "evidence metadata repair retry",
    )

    evidence_result = next(
        result for result in body["results"] if result["checker_name"] == "check_evidence_present"
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
    body = await run_manual_checker_retry(
        checker_client,
        created.json()["id"],
        "attestation repair retry",
    )

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
    _, first = await get_submission_and_automatic_pre_review_run(
        checker_client, created.json()["id"]
    )

    set_dev_actor(monkeypatch, roles="project_manager", subject="other-project-manager")
    wrong_manager_retry = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "wrong project manager retry"},
    )
    assert wrong_manager_retry.status_code == 404
    wrong_manager_list = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert wrong_manager_list.status_code == 404
    wrong_manager_detail = await checker_client.get(
        f"/api/v1/checker-runs/{first['id']}",
        headers=auth_headers(),
    )
    assert wrong_manager_detail.status_code == 404

    set_dev_actor(monkeypatch, roles="worker,project_manager", subject="worker-one")
    multi_role_worker_detail = await checker_client.get(
        f"/api/v1/checker-runs/{first['id']}",
        headers=auth_headers(),
    )
    assert multi_role_worker_detail.status_code == 200, multi_role_worker_detail.text
    multi_role_body = multi_role_worker_detail.json()
    assert "routing_recommendation" not in multi_role_body
    assert "trigger_source" not in multi_role_body
    assert "locked_post_submit_checker_policy_hash" not in multi_role_body
    assert "artifact_hash_manifest" not in multi_role_body

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
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
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
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


async def test_chunk8_default_blocking_checker_survives_omitted_blocking_severities(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": "Empty Blocking Severity Project",
            "slug": "empty-blocking-severity-project",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
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
        post_submit_required_checkers=["check_policy_context_present"],
        post_submit_blocking_severities=None,
    )
    activation_response = await activate_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide_response.json()["id"],
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
    _, body = await get_submission_and_automatic_pre_review_run(
        checker_client, created.json()["id"]
    )
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
    _, v1_run = await get_submission_and_automatic_pre_review_run(checker_client, v1.json()["id"])
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
                    .where(
                        AuditEvent.entity_type == "task", AuditEvent.entity_id == started_task["id"]
                    )
                    .order_by(AuditEvent.created_at)
                )
            )
            .scalars()
            .all()
        )
        pre_submit_policy_id = task.locked_pre_submit_checker_policy_id if task else None
        pre_submit_bundle_hash = task.locked_pre_submit_checker_bundle_hash if task else None
        post_submit_policy_hash = task.locked_post_submit_checker_policy_hash if task else None
        post_submit_policy_body = (
            dict(task.locked_post_submit_checker_policy_body or {}) if task else {}
        )
    assert task is not None
    assert task.status == "needs_revision"
    assert v1_submission is not None
    assert v1_submission.version == 1
    assert v1_submission.package_hash == "sha256:package-v1"
    gate_transitions = {f"{event.from_status}->{event.to_status}" for event in gate_events}
    assert "submitted->evaluation_pending" in gate_transitions
    assert "evaluation_pending->needs_revision" in gate_transitions
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
    _, v2_run = await get_submission_and_automatic_pre_review_run(checker_client, v2.json()["id"])
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
                    .where(
                        AuditEvent.entity_type == "task", AuditEvent.entity_id == started_task["id"]
                    )
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
    task_transitions = {f"{event.from_status}->{event.to_status}" for event in task_events}
    assert "needs_revision->submitted" in task_transitions
    assert "submitted->evaluation_pending" in task_transitions
    assert "evaluation_pending->review_pending" in task_transitions


async def test_chunk8_task_setup_blocked_takes_priority_over_worker_revision(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": "Task Setup Checker Project",
            "slug": "task-setup-checker-project",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
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
        post_submit_required_checkers=["check_acceptance_criteria_present"],
    )
    activation_response = await activate_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide_response.json()["id"],
    )
    assert activation_response.status_code == 200, activation_response.text
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = None
        await session.commit()

    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await get_submission_and_automatic_pre_review_run(
        checker_client, created.json()["id"]
    )
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
        "submission_finalized"
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
                    (
                        await session.execute(
                            select(Submission).where(Submission.task_id == started_task["id"])
                        )
                    )
                    .scalars()
                    .all()
                )
                task = await session.get(WorkstreamTask, started_task["id"])
            assert submissions == []
            assert task is not None
            assert task.status == "in_progress"
            continue

        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
        _, manager_run = await get_submission_and_automatic_pre_review_run(
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
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = None
        await session.commit()

    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, blocked_run = await get_submission_and_automatic_pre_review_run(
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
    assert "submission_finalized" not in worker_blocked_read.text
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
    _, run = await get_submission_and_automatic_pre_review_run(checker_client, created.json()["id"])

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
    assert "locked_post_submit_checker_policy_id" not in body
    assert "locked_post_submit_checker_policy_version" not in body
    assert "locked_post_submit_checker_policy_hash" not in body
    assert "locked_post_submit_checker_policy_body" not in body
    for field in (
        "locked_review_policy_id",
        "locked_review_policy_generation",
        "locked_review_policy_hash",
        "locked_revision_policy_id",
        "locked_revision_policy_generation",
        "locked_revision_policy_hash",
    ):
        assert field not in body
    assert "locked_payment_policy_version" not in body
    assert "package_hash" not in body
    assert "artifact_hash_manifest" not in body
    assert "artifact_manifest_hash" not in body
    assert "submission_finalized" not in read.text
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
    assert "submission_finalized" not in listed.text
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
    _, run = await get_submission_and_automatic_pre_review_run(checker_client, created.json()["id"])

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
    payload["trigger_source"] = "submission_finalized"
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
    await get_submission_and_automatic_pre_review_run(checker_client, created.json()["id"])
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
    assert rows[0].trigger_source == "submission_finalized"


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
        f"/api/v1/submissions/{first.json()['id']}/finalize",
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

    _, second_run = await get_submission_and_automatic_pre_review_run(
        checker_client, second.json()["id"]
    )
    assert second_run["submission_version"] == 2
    assert second_run["trigger_source"] == "submission_finalized"
    assert second_run["routing_recommendation"] == "allow_review"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "review_pending"

    async with db_session.get_session_factory()() as session:
        submissions = (
            (await session.execute(select(Submission).where(Submission.id == first.json()["id"])))
            .scalars()
            .all()
        )
    assert submissions[0].version == 1


@pytest.mark.parametrize(
    "old_checker_name",
    ["check_evidence_references_present", "check_artifact_manifest_integrity"],
)
def test_old_checker_name_blocks_post_submit_compilation_without_alias(
    old_checker_name: str,
) -> None:
    spec = build_project_post_submit_checker_spec(
        project_id="old-checker-name-project",
        guide_version="v1",
        required_checkers=[old_checker_name],
    )

    with pytest.raises(PostSubmitCheckerCompilerError, match="unregistered checker"):
        compile_project_post_submit_checker_spec(
            project_id="old-checker-name-project",
            guide_version="v1",
            spec=spec,
        )
