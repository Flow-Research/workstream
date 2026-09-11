from __future__ import annotations

from project_create_fixtures import GUIDE_CREATION_CUSTODY_TRIGGERS

import asyncio
import hashlib
import inspect
import json
import types
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest  # type: ignore[import-not-found]
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from fastapi import HTTPException
from sqlalchemy.schema import CreateIndex

from project_create_fixtures import guide_example_columns, guide_snapshot_columns, seed_guide_snapshot_rows

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideMutationIdempotencyRecord,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSufficiencyReport,
    PaymentPolicy,
    PolicyMutationIdempotencyRecord,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectCreateIdempotencyRecord,
    ProjectGuide,
    ProjectSetupRun,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
    SubmissionPolicyMutationIdempotencyRecord,
)
from app.modules.projects.guide_mutation_repository import GuideMutationRepository
from app.modules.projects.submission_policy_mutation_repository import (
    SubmissionPolicyMutationReplayRepository,
)
from app.modules.projects.submission_policy_mutation_service import (
    SubmissionPolicyMutationService,
)
from app.modules.tasks.models import AuditEvent
from app.modules.authorization.models import (
    AdminRoleGrant,
    AuthorityControl,
    ProjectRoleGrant,
    ProjectRoleQualificationSnapshot,
)
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.catalogue import ActionId
from app.modules.projects import (
    api as project_setup_identity,
    repository as project_repository_module,
)
from app.modules.projects import service as project_service_module
from app.modules.projects import guide_mutation_router as guide_mutation_router_module
from app.modules.projects import setup_queue as project_setup_queue_module
from app.modules.projects.create_repository import ProjectCreateRepository
from app.modules.projects.create_router import (
    create_project as create_project_route,
    get_project_create_authorization,
    require_project_create_idempotency_key,
)
from app.modules.projects.create_service import (
    ProjectCreateIdempotencyConflict,
    ProjectCreateOutcome,
    ProjectCreateService,
)
from app.modules.projects.guide_mutation_service import GuideMutationService
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectGuideCreate,
    ProjectGuideUpdate,
    ProjectResponse,
    ProjectSetupRunResponse,
    SubmissionArtifactPolicyApprove,
    SubmissionArtifactPolicyInput,
)
from app.schemas.auth import ActorContext
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    MatchedAuthorityKind,
    PreparedAuthorizationUnsupported,
)
from app.core.permissions import PermissionDenied
from app.modules.projects.setup_queue import ProjectSetupQueueError
from app.modules.projects.service import (
    ProjectNotFound,
    ProjectService,
    ProjectServiceError,
)
from project_create_fixtures import (
    seed_active_guide_for_downstream_test,
    seed_historical_project,
)
from committed_guide_fixtures import (
    create_committed_document_fixture,
    create_compiled_report_fixture,
)
from projects.client_fixtures import (
    auth_headers,
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
    ensure_access_administrator_bootstrap,
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import (
    complete_guide_payload,
    create_project,
    add_project_manager_admin_grant,
    read_guide_source_snapshot,
    create_guide,
)
from projects.submission_policy_fixtures import (
    project_submission_artifact_policy_body,
    create_sufficiency_report,
    create_submission_artifact_policy,
    approve_submission_artifact_policy,
    load_pre_submit_checker_policy,
)
from projects.post_submit_fixtures import (
    seed_post_submit_policy_for_downstream_tests,
)
from projects.policy_bundle_fixtures import (
    create_approved_policy_bundle,
)


@pytest.mark.asyncio
async def test_project_policy_lock_queries_lock_only_policy_rows() -> None:
    statements: list[Any] = []

    class Session:
        async def scalar(self, statement: Any) -> None:
            statements.append(statement)
            return None

    repository = ProjectRepository(cast(Any, Session()))
    await repository.lock_review_policy("project-id", "v1")
    await repository.lock_revision_policy("project-id", "v1")

    rendered = [str(statement.compile(dialect=postgresql.dialect())) for statement in statements]
    assert "FOR UPDATE OF review_policies" in rendered[0]
    assert "FOR UPDATE OF project_guides" not in rendered[0]
    assert "FOR UPDATE OF revision_policies" in rendered[1]
    assert "FOR UPDATE OF project_guides" not in rendered[1]


@pytest.mark.asyncio
async def test_payment_policy_upsert_inserts_and_refreshes_new_policy() -> None:
    calls: list[tuple[str, Any]] = []

    class Session:
        def add(self, value: Any) -> None:
            calls.append(("add", value))

        async def flush(self) -> None:
            calls.append(("flush", None))

        async def refresh(self, value: Any) -> None:
            calls.append(("refresh", value))

    policy = SimpleNamespace(project_id="project-1", guide_version="v1")
    repository = ProjectRepository(cast(Any, Session()))

    async def get_missing_policy(*_args: Any) -> None:
        return None

    repository.get_payment_policy = get_missing_policy

    result = await repository.upsert_payment_policy(cast(Any, policy))

    assert result is policy
    assert calls == [("add", policy), ("flush", None), ("refresh", policy)]


@pytest.mark.asyncio
async def test_payment_policy_upsert_replaces_mutable_terms_on_existing_policy() -> None:
    refreshed: list[Any] = []

    class Session:
        async def flush(self) -> None:
            return None

        async def refresh(self, value: Any) -> None:
            refreshed.append(value)

    existing = SimpleNamespace(
        base_amount=Decimal("1"),
        currency="USD",
        payout_type="fixed",
        revision_payment_rule="old revision",
        rejection_payment_rule="old rejection",
        accepted_payment_rule="old acceptance",
    )
    replacement = SimpleNamespace(
        project_id="project-1",
        guide_version="v1",
        base_amount=Decimal("25.50"),
        currency="NGN",
        payout_type="milestone",
        revision_payment_rule="hold",
        rejection_payment_rule="void",
        accepted_payment_rule="release",
    )
    repository = ProjectRepository(cast(Any, Session()))

    async def get_existing_policy(*_args: Any) -> Any:
        return existing

    repository.get_payment_policy = get_existing_policy

    result = await repository.upsert_payment_policy(cast(Any, replacement))

    assert result is existing
    assert vars(existing) == {
        "base_amount": Decimal("25.50"),
        "currency": "NGN",
        "payout_type": "milestone",
        "revision_payment_rule": "hold",
        "rejection_payment_rule": "void",
        "accepted_payment_rule": "release",
    }
    assert refreshed == [existing]


@pytest.mark.asyncio
@pytest.mark.parametrize("exists", [False, True])
async def test_project_resolution_preserves_found_and_missing_outcomes(exists: bool) -> None:
    project = SimpleNamespace(id="project-1") if exists else None

    class Repository:
        async def get_project(self, project_id: str) -> Any:
            assert project_id == "project-1"
            return project

    service = ProjectService(cast(Any, None))
    service._repo = cast(Any, Repository())

    if exists:
        assert await service.resolve_project("project-1") is project
    else:
        with pytest.raises(ProjectNotFound, match="project not found"):
            await service.resolve_project("project-1")


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [(None, 20, 20), (10, None, 10), (10, 20, 10)],
)
def test_effective_policy_limit_merge_keeps_stricter_non_null_value(
    left: int | None,
    right: int | None,
    expected: int,
) -> None:
    service = ProjectService(cast(Any, None))

    assert service._minimum_non_null(left, right) == expected


def test_policy_identity_shape_metadata_matches_migration_contract() -> None:
    expected = {
        "ck_review_policies_review_policy_identity_shape": ReviewPolicy,
        "ck_revision_policies_revision_policy_identity_shape": RevisionPolicy,
    }
    for name, model in expected.items():
        constraint = next(item for item in model.__table__.constraints if item.name == name)
        sql = str(constraint.sqltext)
        assert "policy_generation > 0" in sql
        assert "^sha256:[0-9a-f]{64}$" in sql
        assert "complete" in sql
        assert "legacy_incomplete" in sql


class _DiagnosticStatementCaptureSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        return types.SimpleNamespace(scalars=lambda: types.SimpleNamespace(all=lambda: []))


def _project_manager_actor() -> ActorContext:
    return ActorContext(
        actor_id="actor-1",
        external_subject="subject-1",
        external_issuer="https://identity.test",
        roles=("project_manager",),
        auth_source="dev_mock",
    )


class _IdentityResponse:
    @staticmethod
    def model_validate(value: Any) -> Any:
        return value


class _RecordingSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshed: list[Any] = []

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def flush(self) -> None:
        return None

    async def refresh(self, value: Any) -> None:
        self.refreshed.append(value)


@pytest.fixture
def isolated_project_settings_cache() -> Iterator[None]:
    """Keep settings overrides from leaking when a direct setup test fails."""
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def test_submission_policy_derivation_has_no_public_project_service_seam() -> None:
    """12F3 removes role-bearing inline derivation from import reachability."""
    assert not hasattr(ProjectService, "run_submission_artifact_policy_derivation_agent")


@pytest.mark.asyncio
async def test_submission_policy_approval_builds_fresh_effective_and_checker_chain(
    monkeypatch: pytest.MonkeyPatch,
    isolated_project_settings_cache: None,
) -> None:
    project_id, guide_id, snapshot_id = (str(uuid4()) for _ in range(3))
    guide = SimpleNamespace(id=guide_id, project_id=project_id, version="v1", status="draft")
    snapshot = SimpleNamespace(id=snapshot_id, bundle_hash=f"sha256:{'a' * 64}")
    policy_body = SubmissionArtifactPolicyInput().model_dump(mode="json")
    policy = SimpleNamespace(
        id=str(uuid4()),
        project_id=project_id,
        guide_id=guide_id,
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot.bundle_hash,
        lifecycle_status="draft",
        derivation_source="manual_admin_derivation",
        policy_body=policy_body,
        policy_hash=canonical_json_hash(policy_body),
        change_summary="draft summary",
    )
    added_effective: list[Any] = []
    added_checker: list[Any] = []

    class Repository:
        async def lock_submission_artifact_policy(self, _policy_id: str) -> Any:
            return policy

        async def get_diagnostic_sufficiency_report_for_snapshot(self, _id: str) -> Any:
            return SimpleNamespace(status="passed")

        async def get_current_approved_submission_artifact_policy(self, *_: Any) -> None:
            return None

        async def get_current_pre_submit_checker_policy(self, *_: Any) -> None:
            return None

        async def get_post_submit_checker_policy(self, *_: Any) -> None:
            return None

        async def add_effective_submission_artifact_policy(self, value: Any) -> Any:
            added_effective.append(value)
            return value

        async def add_pre_submit_checker_policy(self, value: Any) -> Any:
            added_checker.append(value)
            return value

    session = _RecordingSession()
    service = ProjectService(cast(Any, session))
    service._repo = cast(Any, Repository())

    async def get_guide(*_: Any) -> Any:
        return guide

    async def get_snapshot(*_: Any) -> Any:
        return snapshot

    async def no_op(*_: Any, **__: Any) -> None:
        return None

    effective_body = {"effective": "policy"}
    service._lock_project_guide_for_setup = get_guide
    service._get_snapshot_for_guide = get_snapshot
    service._ensure_snapshot_is_latest = no_op
    service.validate_source_snapshot_integrity = no_op
    service._validate_sufficiency_report_allows_policy_approval = cast(Any, lambda *_: None)
    service._merge_effective_submission_artifact_policy = cast(Any, lambda _: effective_body)
    monkeypatch.setattr(
        project_service_module,
        "compile_effective_project_submission_artifact_policy",
        lambda *_: SimpleNamespace(
            compiler_version="compiler-v1",
            compiled_bundle={"checks": ["hash"]},
            compiled_bundle_hash=f"sha256:{'b' * 64}",
            checker_names=["hash"],
            checker_configs={"hash": {}},
        ),
    )
    monkeypatch.setattr(
        project_service_module,
        "EffectiveProjectSubmissionArtifactPolicyResponse",
        _IdentityResponse,
    )

    result = await service.approve_submission_artifact_policy(
        _project_manager_actor(),
        project_id,
        guide_id,
        policy.id,
        SubmissionArtifactPolicyApprove(approval_note="Approved manually."),
    )

    assert result is added_effective[0]
    assert policy.lifecycle_status == "approved"
    assert policy.approved_by_actor == "actor-1"
    assert policy.approved_by_role == "project_manager"
    assert policy.change_summary == "Approved manually."
    assert added_effective[0].submission_artifact_policy_id == policy.id
    assert added_checker[0].effective_policy_id == added_effective[0].id
    assert session.commits == 1
    assert session.refreshed == [added_effective[0], added_checker[0]]


def test_project_setup_queue_enqueues_exact_task_payload(
    monkeypatch: pytest.MonkeyPatch,
    isolated_project_settings_cache: None,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.workers import project_setup as worker_module

    captured: dict[str, Any] = {}
    task = worker_module.run_project_guide_compilation

    def apply_async(*, args: tuple[Any, ...], task_id: str | None = None) -> Any:
        captured.update(args=args, task_id=task_id)
        return SimpleNamespace(id="queued-task")

    monkeypatch.setattr(project_setup_queue_module, "sync_task_settings", lambda value: value)
    monkeypatch.setattr(task, "apply_async", apply_async)

    result = project_setup_queue_module.enqueue_project_guide_compilation(
        project_id="project-1",
        guide_id="guide-1",
        source_snapshot_id="snapshot-1",
        setup_run_id="run-1",
        setup_generation=3,
        task_id="stable-task",
    )
    assert captured == {
        "args": ("project-1", "guide-1", "snapshot-1", "run-1", 3),
        "task_id": "stable-task",
    }
    assert result == "queued-task"


def test_project_setup_queue_normalizes_broker_failure(
    monkeypatch: pytest.MonkeyPatch,
    isolated_project_settings_cache: None,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.workers import project_setup as worker_module

    task = worker_module.run_project_guide_compilation
    monkeypatch.setattr(project_setup_queue_module, "sync_task_settings", lambda value: value)
    monkeypatch.setattr(
        task,
        "apply_async",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("secret broker detail")),
    )

    with pytest.raises(ProjectSetupQueueError, match="could not be enqueued") as caught:
        project_setup_queue_module.enqueue_project_guide_compilation(
            project_id="project-1",
            guide_id="guide-1",
            source_snapshot_id="snapshot-1",
            setup_run_id="run-1",
            setup_generation=3,
        )
    assert "secret broker detail" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup_run", "expected"),
    [
        (SimpleNamespace(status="running", celery_task_id="existing"), "existing"),
        (SimpleNamespace(status="running", celery_task_id=None), None),
    ],
)
async def test_project_setup_dispatch_returns_terminal_state_without_publish(
    monkeypatch: pytest.MonkeyPatch,
    setup_run: Any,
    expected: str | None,
) -> None:
    class Repository:
        def __init__(self, _session: Any) -> None:
            pass

        async def lock_project_setup_run(self, _setup_run_id: str) -> Any:
            return setup_run

    class Session:
        async def commit(self) -> None:
            raise AssertionError("terminal state must not be mutated")

    monkeypatch.setattr(project_repository_module, "ProjectRepository", Repository)
    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        lambda **_: (_ for _ in ()).throw(AssertionError("must not publish")),
    )

    result = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
        cast(Any, Session()),
        project_id="project-1",
        guide_id="guide-1",
        source_snapshot_id="snapshot-1",
        setup_run_id="run-1",
        setup_generation=1,
    )

    assert result == expected


@pytest.mark.asyncio
async def test_project_setup_dispatch_rejects_missing_durable_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: Any) -> None:
            pass

        async def lock_project_setup_run(self, _setup_run_id: str) -> None:
            return None

    monkeypatch.setattr(project_repository_module, "ProjectRepository", Repository)

    with pytest.raises(ProjectSetupQueueError, match="project setup run missing before dispatch"):
        await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            cast(Any, object()),
            project_id="project-1",
            guide_id="guide-1",
            source_snapshot_id="snapshot-1",
            setup_run_id="run-1",
            setup_generation=1,
        )


@pytest.mark.asyncio
async def test_project_setup_dispatch_reuses_exact_queued_task_without_republish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = project_setup_identity.project_guide_compilation_task_id("run-1", 1)
    setup_run = SimpleNamespace(status="queued", celery_task_id=expected, updated_at=datetime.now(UTC))

    repository = SimpleNamespace(lock_project_setup_run=AsyncMock(return_value=setup_run))

    class Session:
        async def commit(self) -> None:
            raise AssertionError("existing queue custody must not be mutated")

    monkeypatch.setattr(project_repository_module, "ProjectRepository", lambda _: repository)
    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        lambda **_: (_ for _ in ()).throw(AssertionError("must not republish")),
    )

    result = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
        cast(Any, Session()),
        project_id="project-1",
        guide_id="guide-1",
        source_snapshot_id="snapshot-1",
        setup_run_id="run-1",
        setup_generation=1,
    )

    assert result == expected
    repository.lock_project_setup_run.assert_awaited_once_with("run-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_stage", ["insert", "reload"])
async def test_project_create_repository_rejects_disappeared_reservation(
    missing_stage: str,
) -> None:
    record_id = uuid4()

    class Session:
        async def scalar(self, _statement):
            return None if missing_stage == "insert" else record_id

        async def get(self, _model, _record_id):
            assert _record_id == record_id
            return None

    repository = ProjectCreateRepository(cast(Any, Session()))
    with pytest.raises(ProjectRepositoryIntegrityError, match="reservation disappeared"):
        await repository.reserve(
            actor_profile_id=str(uuid4()),
            identity_link_id=str(uuid4()),
            idempotency_key=uuid4(),
            request_digest="sha256:" + ("a" * 64),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_identity", "stored_digest", "stored_status", "expected"),
    [
        ("other-link", "sha256:" + ("a" * 64), "pending", "mismatch"),
        ("same-link", "sha256:" + ("b" * 64), "pending", "mismatch"),
        ("same-link", "sha256:" + ("a" * 64), "pending", "pending"),
        ("same-link", "sha256:" + ("a" * 64), "committed", "replayed"),
    ],
)
async def test_project_create_repository_classifies_existing_reservation(
    stored_identity: str,
    stored_digest: str,
    stored_status: str,
    expected: str,
) -> None:
    record_id = uuid4()
    record = types.SimpleNamespace(
        id=record_id,
        identity_link_id=stored_identity,
        request_digest=stored_digest,
        status=stored_status,
    )

    class Session:
        async def scalar(self, _statement):
            return record_id

        async def get(self, _model, _record_id):
            assert _record_id == record_id
            return record

    repository = ProjectCreateRepository(cast(Any, Session()))
    disposition, returned = await repository.reserve(
        actor_profile_id=str(uuid4()),
        identity_link_id="same-link",
        idempotency_key=uuid4(),
        request_digest="sha256:" + ("a" * 64),
    )
    assert disposition == expected
    assert returned is record


@pytest.mark.asyncio
async def test_project_create_repository_rejects_invalid_completion() -> None:
    class Session:
        async def scalar(self, _statement):
            return None

    repository = ProjectCreateRepository(cast(Any, Session()))
    with pytest.raises(ProjectRepositoryIntegrityError, match="invalid project reservation"):
        await repository.complete(types.SimpleNamespace(id=uuid4()))


def _project_create_payload() -> ProjectCreate:
    return ProjectCreate(name="Created project", slug="created-project", description="test")


def _project_create_response() -> ProjectResponse:
    now = datetime.now(UTC)
    return ProjectResponse(
        id=str(uuid4()),
        name="Created project",
        slug="created-project",
        description="test",
        status="draft",
        created_at=now,
        updated_at=now,
    )


def test_project_create_idempotency_dependency_rejects_invalid_header() -> None:
    request = types.SimpleNamespace(headers={"Idempotency-Key": "not-a-uuid"})

    with pytest.raises(HTTPException) as captured:
        require_project_create_idempotency_key(cast(Any, request))

    assert captured.value.status_code == 422


@pytest.mark.asyncio
async def test_project_create_authorization_dependency_preserves_exact_inputs() -> None:
    idempotency_key = uuid4()
    resolved = object()
    prepared = object()

    result = await get_project_create_authorization(
        idempotency_key,
        cast(Any, resolved),
        cast(Any, prepared),
    )

    assert result == (idempotency_key, resolved, prepared)


@pytest.mark.asyncio
@pytest.mark.parametrize("replayed", [False, True])
async def test_project_create_route_owns_commit_or_replay_rollback(
    monkeypatch: pytest.MonkeyPatch,
    replayed: bool,
) -> None:
    class Session:
        commit_count = 0
        rollback_count = 0

        async def commit(self):
            self.commit_count += 1

        async def rollback(self):
            self.rollback_count += 1

    response = _project_create_response()

    async def create(_service, _resolved, _prepared, _key, _payload):
        return ProjectCreateOutcome(response=response, replayed=replayed)

    monkeypatch.setattr(ProjectCreateService, "create", create)
    session = Session()
    returned = await create_project_route(
        _project_create_payload(),
        (uuid4(), object(), object()),  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
    )
    assert returned is response
    assert (session.commit_count, session.rollback_count) == ((0, 1) if replayed else (1, 0))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status_code", "error_code"),
    [
        (PermissionDenied("denied"), 403, None),
        (
            ProjectCreateIdempotencyConflict("idempotency_mismatch"),
            409,
            "idempotency_mismatch",
        ),
        (ProjectServiceError("unavailable"), 400, None),
    ],
)
async def test_project_create_route_translates_bounded_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status_code: int,
    error_code: str | None,
) -> None:
    async def create(_service, _resolved, _prepared, _key, _payload):
        raise failure

    monkeypatch.setattr(ProjectCreateService, "create", create)
    with pytest.raises(HTTPException) as exc_info:
        await create_project_route(
            _project_create_payload(),
            (uuid4(), object(), object()),  # type: ignore[arg-type]
            cast(Any, object()),
        )
    assert exc_info.value.status_code == status_code
    if error_code is not None:
        assert cast(Any, exc_info.value).error_code == error_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("constraint_source", "expected_code"),
    [
        (types.SimpleNamespace(constraint_name="projects_slug_key"), 409),
        (
            types.SimpleNamespace(
                constraint_name=None,
                diag=types.SimpleNamespace(constraint_name="uq_projects_slug"),
            ),
            409,
        ),
        (types.SimpleNamespace(constraint_name="other_constraint"), None),
    ],
)
async def test_project_create_route_maps_only_slug_integrity_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    constraint_source: object,
    expected_code: int | None,
) -> None:
    class Session:
        rollback_count = 0

        async def rollback(self):
            self.rollback_count += 1

    failure = IntegrityError("insert", {}, constraint_source)

    async def create(_service, _resolved, _prepared, _key, _payload):
        raise failure

    monkeypatch.setattr(ProjectCreateService, "create", create)
    session = Session()
    if expected_code is None:
        with pytest.raises(IntegrityError) as exc_info:
            await create_project_route(
                _project_create_payload(),
                (uuid4(), object(), object()),  # type: ignore[arg-type]
                session,  # type: ignore[arg-type]
            )
        assert exc_info.value is failure
    else:
        with pytest.raises(HTTPException) as exc_info:
            await create_project_route(
                _project_create_payload(),
                (uuid4(), object(), object()),  # type: ignore[arg-type]
                session,  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == expected_code
    assert session.rollback_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "project_exists", "expected_error"),
    [
        ("mismatch", True, ProjectCreateIdempotencyConflict),
        ("pending", True, ProjectCreateIdempotencyConflict),
        ("replayed", False, RuntimeError),
    ],
)
async def test_project_create_service_rejects_noncreatable_reservation_states(
    disposition: str,
    project_exists: bool,
    expected_error: type[Exception],
) -> None:
    reservation = types.SimpleNamespace(project_id=str(uuid4()))

    class Reservations:
        async def reserve(self, **_kwargs):
            return disposition, reservation

    class Projects:
        async def get_project(self, _project_id):
            return _project_create_response() if project_exists else None

    service = object.__new__(ProjectCreateService)
    service._reservations = cast(Any, Reservations())
    service._projects = cast(Any, Projects())
    resolved = types.SimpleNamespace(
        profile=types.SimpleNamespace(id=str(uuid4())),
        identity_link=types.SimpleNamespace(id=str(uuid4())),
    )
    with pytest.raises(expected_error):
        await service.create(
            resolved,
            cast(Any, object()),
            uuid4(),
            _project_create_payload(),
        )


@pytest.mark.asyncio
async def test_project_create_service_replays_existing_project() -> None:
    response = _project_create_response()
    reservation = types.SimpleNamespace(project_id=response.id)

    class Reservations:
        async def reserve(self, **_kwargs):
            return "replayed", reservation

    class Projects:
        async def get_project(self, _project_id):
            return response

    service = object.__new__(ProjectCreateService)
    service._reservations = cast(Any, Reservations())
    service._projects = cast(Any, Projects())
    resolved = types.SimpleNamespace(
        profile=types.SimpleNamespace(id=str(uuid4())),
        identity_link=types.SimpleNamespace(id=str(uuid4())),
    )
    outcome = await service.create(
        resolved,
        cast(Any, object()),
        uuid4(),
        _project_create_payload(),
    )
    assert outcome.replayed is True
    assert outcome.response == response


@pytest.mark.asyncio
async def test_project_create_service_consumes_system_authority_and_attributes_project() -> None:
    reservation = types.SimpleNamespace(
        operation_id=uuid4(),
        project_id=str(uuid4()),
        operation_generation=1,
    )
    completed = []
    added = []

    class Reservations:
        async def reserve(self, **_kwargs):
            return "claimed", reservation

        async def complete(self, record):
            completed.append(record)

    class Projects:
        async def add_project(self, project):
            now = datetime.now(UTC)
            project.created_at = now
            project.updated_at = now
            added.append(project)
            return project

    decision = types.SimpleNamespace(
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=uuid4(),
        matched_scope_project_id=None,
        decision_id=uuid4(),
    )

    class Prepared:
        async def prepare(self, *_args):
            return object()

        async def consume(self, *_args):
            return decision

    service = object.__new__(ProjectCreateService)
    service._reservations = cast(Any, Reservations())
    service._projects = cast(Any, Projects())
    actor_id, link_id = str(uuid4()), str(uuid4())
    resolved = types.SimpleNamespace(
        profile=types.SimpleNamespace(id=actor_id),
        identity_link=types.SimpleNamespace(id=link_id),
    )
    outcome = await service.create(
        resolved,
        cast(Any, Prepared()),
        uuid4(),
        _project_create_payload(),
    )
    assert outcome.replayed is False
    assert outcome.response.id == reservation.project_id
    assert completed == [reservation]
    assert added[0].created_by_actor_profile_id == actor_id
    assert added[0].created_via_identity_link_id == link_id
    assert added[0].created_by_admin_role_grant_id == decision.matched_grant_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,locked_table",
    [
        ("lock_guide_sufficiency_reports", "guide_sufficiency_reports"),
        ("lock_submission_artifact_policies", "submission_artifact_policies"),
    ],
)
async def test_project_diagnostic_collection_locks_are_bounded(
    method_name: str, locked_table: str
) -> None:
    session = _DiagnosticStatementCaptureSession()
    repository = ProjectRepository(cast(Any, session))

    await getattr(repository, method_name)(str(uuid4()), str(uuid4()), "v1")

    assert len(session.statements) == 1
    compiled = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "LIMIT 100" in compiled
    assert f"FOR UPDATE OF {locked_table}" in compiled


async def add_local_admin_role_for_default_actor(role: str, *, project_id: str | None) -> UUID:
    """Add one valid local administrative grant through the fixture grantor."""
    actor_id, _, grantor_id = await ensure_access_administrator_bootstrap()
    async with db_session.get_session_factory()() as session:
        grant = AdminRoleGrant(
            id=uuid4(),
            target_actor_profile_id=actor_id,
            role=role,
            scope_type="project" if project_id is not None else "system",
            scope_project_id=project_id,
            status="active",
            version=1,
            granted_by_actor_profile_id=actor_id,
            granted_by_admin_role_grant_id=grantor_id,
            grant_reason=f"AUTH-11C1 {role} route fixture",
        )
        session.add(grant)
        await session.commit()
        return grant.id


async def revoke_local_admin_role(grant_id: UUID) -> None:
    """Revoke one fixture grant with complete provenance."""
    async with db_session.get_session_factory()() as session:
        grant = await session.get(AdminRoleGrant, grant_id)
        assert grant is not None
        grant.status = "revoked"
        grant.version = 2
        grant.revoked_by_actor_profile_id = grant.target_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "AUTH-11C1 role matrix proof"
        grant.revoked_at = datetime.now(UTC)
        await session.commit()


async def add_project_role_for_default_actor(project_id: str, role: str) -> tuple[UUID, str]:
    """Insert reviewed local-grant fixtures for project identity route tests."""
    now = datetime.now(UTC)
    actor_id, link_id, admin_grant_id = await ensure_access_administrator_bootstrap()
    async with db_session.get_session_factory()() as session:
        snapshot = ProjectRoleQualificationSnapshot(
            id=uuid4(),
            project_id=project_id,
            actor_profile_id=actor_id,
            requested_role=role,
            skills_snapshot={
                "availability": "unavailable",
                "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            reputation_snapshot={
                "availability": "unavailable",
                "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            prior_project_work_refs=[],
            external_expertise_refs=[],
            captured_by_actor_profile_id=actor_id,
            captured_by_admin_role_grant_id=admin_grant_id,
            captured_at=now,
        )
        session.add(snapshot)
        await session.flush()
        grant = ProjectRoleGrant(
            id=uuid4(),
            project_id=project_id,
            actor_profile_id=actor_id,
            role=role,
            status="active",
            version=1,
            grant_method="manual",
            qualification_snapshot_id=snapshot.id,
            granted_by_actor_profile_id=actor_id,
            granted_by_admin_role_grant_id=admin_grant_id,
            grant_reason="AUTH-11B route fixture",
            granted_at=now,
        )
        session.add(grant)
        await session.commit()
        return grant.id, str(link_id)


@pytest.mark.asyncio
async def test_project_role_grant_repository_filters_and_uses_strict_keyset(
    project_database_env: str,
) -> None:
    project_id = uuid4()
    actor_id = uuid4()
    grantor_id = uuid4()
    admin_grant_id = uuid4()
    granted_at = datetime(2026, 7, 22, tzinfo=UTC)
    grant_ids = sorted((uuid4(), uuid4(), uuid4()), key=str)
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                ActorProfile(
                    id=str(profile_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(profile_id),
                )
                for profile_id in (actor_id, grantor_id)
            ]
        )
        session.add_all(
            [
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=str(profile_id),
                    issuer="https://identity.test",
                    subject=f"project-role-read-{profile_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(profile_id),
                    last_verified_at=granted_at,
                )
                for profile_id in (actor_id, grantor_id)
            ]
        )
        await session.flush()
        session.add(
            AdminRoleGrant(
                id=admin_grant_id,
                target_actor_profile_id=str(grantor_id),
                role="access_administrator",
                scope_type="system",
                scope_project_id=None,
                status="active",
                version=1,
                granted_by_system_principal="workstream:system:bootstrap",
                grant_reason="test bootstrap",
            )
        )
        control = await session.get(AuthorityControl, 1)
        assert control is not None
        control.bootstrap_completed = True
        control.bootstrap_grant_id = admin_grant_id
        control.version = 1
        await session.flush()
        await seed_historical_project(
            session,
            project_id=str(project_id),
            name="Authorization read project",
            slug=f"authorization-read-{project_id}",
            status="archived",
        )
        snapshots = []
        grants = []
        for index, grant_id in enumerate(grant_ids):
            role = ("submitter", "reviewer", "submitter")[index]
            snapshot_id = uuid4()
            snapshots.append(
                ProjectRoleQualificationSnapshot(
                    id=snapshot_id,
                    project_id=str(project_id),
                    actor_profile_id=str(actor_id),
                    requested_role=role,
                    skills_snapshot={
                        "availability": "available",
                        "reference_ids": [f"skill:{index}"],
                        "unavailable_reason": None,
                    },
                    reputation_snapshot={
                        "availability": "unavailable",
                        "reference_ids": [],
                        "unavailable_reason": "no_record",
                    },
                    prior_project_work_refs=[],
                    external_expertise_refs=[],
                    captured_by_actor_profile_id=str(grantor_id),
                    captured_by_admin_role_grant_id=admin_grant_id,
                    captured_at=granted_at,
                )
            )
            revoked = index == 2
            grants.append(
                ProjectRoleGrant(
                    id=grant_id,
                    project_id=str(project_id),
                    actor_profile_id=str(actor_id),
                    role=role,
                    status="revoked" if revoked else "active",
                    version=2 if revoked else 1,
                    grant_method="manual",
                    qualification_snapshot_id=snapshot_id,
                    granted_by_actor_profile_id=str(grantor_id),
                    granted_by_admin_role_grant_id=admin_grant_id,
                    grant_reason="qualified",
                    granted_at=granted_at,
                    revoked_by_actor_profile_id=(str(grantor_id) if revoked else None),
                    revoked_by_admin_role_grant_id=(admin_grant_id if revoked else None),
                    revoked_reason=("test revoke" if revoked else None),
                    revoked_at=(granted_at if revoked else None),
                )
            )
        session.add_all(snapshots)
        await session.flush()
        session.add_all(grants)
        await session.commit()

        repository = AdminAuthorizationRepository(session)
        statements: list[str] = []

        def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        engine = db_session.get_engine().sync_engine
        event.listen(engine, "before_cursor_execute", record_sql)
        try:
            first = await repository.list_project_role_grants(
                project_id=project_id,
                status=None,
                role=None,
                cursor=None,
                limit=1,
            )
        finally:
            event.remove(engine, "before_cursor_execute", record_sql)
        assert all("count(" not in statement.lower() for statement in statements)
        assert [row[0].id for row in first] == grant_ids[:2]
        second = await repository.list_project_role_grants(
            project_id=project_id,
            status=None,
            role=None,
            cursor=(first[0][0].granted_at, grant_ids[0]),
            limit=1,
        )
        assert [row[0].id for row in second] == grant_ids[1:]
        revoked = await repository.list_project_role_grants(
            project_id=project_id,
            status="revoked",
            role="submitter",
            cursor=None,
            limit=10,
        )
        assert [row[0].id for row in revoked] == [grant_ids[2]]
        missing = await repository.get_project_role_grant(
            project_id=uuid4(), grant_id=grant_ids[0],
        )
        assert missing is None


def test_project_guide_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in ProjectGuide.__table__.indexes
        if index.name == "uq_project_guides_one_active_per_project"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "status = 'active'" in postgres_compiled


def test_policy_models_do_not_enforce_mutable_current_uniqueness() -> None:
    disallowed_current_indexes = {
        "uq_sap_one_approved_per_guide",
        "uq_effective_psap_one_approved",
        "uq_pre_submit_checker_current",
    }

    for model in (
        SubmissionArtifactPolicy,
        EffectiveProjectSubmissionArtifactPolicy,
        PreSubmitCheckerPolicy,
    ):
        index_names = {index.name for index in model.__table__.indexes}

        assert index_names.isdisjoint(disallowed_current_indexes)


def test_setup_mutations_use_locked_guide_helper() -> None:
    locked_methods = [
        "approve_submission_artifact_policy",
    ]
    for method_name in locked_methods:
        source = inspect.getsource(getattr(ProjectService, method_name))

        assert "_lock_project_guide_for_setup" in source
        assert "_get_project_guide(project_id, guide_id)" not in source

    assert not hasattr(ProjectService, "run_submission_artifact_policy_derivation_agent")


def test_policy_models_have_project_guide_foreign_keys() -> None:
    expected_constraints = {
        PostSubmitCheckerPolicy: "fk_checker_policies_project_guide",
        ReviewPolicy: "fk_review_policies_project_guide",
        RevisionPolicy: "fk_revision_policies_project_guide",
        PaymentPolicy: "fk_payment_policies_project_guide",
        PreSubmitCheckerPolicy: "fk_pre_submit_checker_policies_project_guide",
    }

    for model, constraint_name in expected_constraints.items():
        constraint = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )

        assert [column.name for column in constraint.columns] == ["project_id", "guide_version"]
        assert [element.column.table.name for element in constraint.elements] == [
            "project_guides",
            "project_guides",
        ]
        assert [element.column.name for element in constraint.elements] == ["project_id", "version"]


def test_submission_artifact_policy_models_are_registered_for_alembic_metadata() -> None:
    expected_tables = {
        "guide_source_snapshots",
        "guide_source_snapshot_items",
        "guide_sufficiency_reports",
        "submission_artifact_policies",
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
    }

    assert expected_tables.issubset(Base.metadata.tables)


def test_submission_artifact_policy_models_bind_to_snapshot_hashes() -> None:
    expected_constraints = {
        GuideSufficiencyReport: "fk_guide_sufficiency_reports_source_snapshot_hash",
        SubmissionArtifactPolicy: "fk_submission_artifact_policies_source_snapshot_hash",
        EffectiveProjectSubmissionArtifactPolicy: "fk_effective_psap_source_snapshot_hash",
        PreSubmitCheckerPolicy: "fk_pre_submit_checker_policies_source_snapshot_hash",
        PostSubmitCheckerPolicy: "fk_checker_policies_source_snapshot_hash",
    }

    for model, constraint_name in expected_constraints.items():
        constraint = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )

        assert [column.name for column in constraint.columns] == [
            "source_snapshot_id",
            "source_snapshot_hash",
        ]
        assert [element.column.table.name for element in constraint.elements] == [
            "guide_source_snapshots",
            "guide_source_snapshots",
        ]
        assert [element.column.name for element in constraint.elements] == ["id", "bundle_hash"]


def test_policy_models_bind_to_denormalized_policy_hashes() -> None:
    expected_constraints = [
        (
            EffectiveProjectSubmissionArtifactPolicy,
            "fk_effective_psap_submission_policy_hash",
            ["submission_artifact_policy_id", "submission_artifact_policy_hash"],
            "submission_artifact_policies",
            ["id", "policy_hash"],
        ),
        (
            PreSubmitCheckerPolicy,
            "fk_pre_submit_checker_policies_effective_hash",
            ["effective_policy_id", "effective_policy_hash"],
            "effective_project_submission_artifact_policies",
            ["id", "effective_policy_hash"],
        ),
        (
            PostSubmitCheckerPolicy,
            "fk_checker_policies_effective_policy_hash",
            ["effective_policy_id", "effective_policy_hash"],
            "effective_project_submission_artifact_policies",
            ["id", "effective_policy_hash"],
        ),
        (
            PostSubmitCheckerPolicy,
            "fk_checker_policies_pre_submit_checker_hash",
            ["pre_submit_checker_policy_id", "pre_submit_checker_bundle_hash"],
            "pre_submit_checker_policies",
            ["id", "compiled_bundle_hash"],
        ),
    ]

    for model, constraint_name, local_columns, target_table, target_columns in expected_constraints:
        constraint = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )

        assert [column.name for column in constraint.columns] == local_columns
        assert [element.column.table.name for element in constraint.elements] == [
            target_table,
            target_table,
        ]
        assert [element.column.name for element in constraint.elements] == target_columns


def test_policy_hash_pairs_are_unique_fk_targets() -> None:
    expected_constraints = {
        PostSubmitCheckerPolicy: "uq_checker_policies_id_version_hash",
        SubmissionArtifactPolicy: "uq_submission_artifact_policies_id_hash",
        EffectiveProjectSubmissionArtifactPolicy: (
            "uq_effective_project_submission_artifact_policies_id_hash"
        ),
        PreSubmitCheckerPolicy: "uq_pre_submit_checker_policies_id_compiled_bundle_hash",
    }

    for model, constraint_name in expected_constraints.items():
        constraint = next(
            constraint
            for constraint in model.__table__.constraints
            if constraint.name == constraint_name
        )

        assert [column.name for column in constraint.columns] in (
            ["id", "guide_version", "policy_hash"],
            ["id", "policy_hash"],
            ["id", "effective_policy_hash"],
            ["id", "compiled_bundle_hash"],
        )


def test_pre_submit_checker_policy_compiled_rows_require_bundle_fields() -> None:
    constraint = next(
        constraint
        for constraint in PreSubmitCheckerPolicy.__table__.constraints
        if constraint.name is not None
        and constraint.name.endswith("ck_pre_submit_checker_policies_compiled_fields")
    )

    constraint_sql = str(constraint.sqltext)

    assert "lifecycle_status" in constraint_sql
    assert "compiled_bundle_hash" in constraint_sql
    assert "compiled_bundle_hash is not null" in constraint_sql
    assert "compiled_bundle" in constraint_sql
    assert "compiler_version" in constraint_sql
    assert "sha256" in constraint_sql


def test_submission_artifact_policy_approval_requires_provenance() -> None:
    constraint = next(
        constraint
        for constraint in SubmissionArtifactPolicy.__table__.constraints
        if constraint.name is not None
        and constraint.name.endswith("ck_submission_artifact_policies_approval_provenance")
    )

    constraint_sql = str(constraint.sqltext)

    assert "approved_by_role" in constraint_sql
    assert "admin" in constraint_sql
    assert "project_manager" in constraint_sql
    assert "approved_by_actor" in constraint_sql
    assert "approved_at" in constraint_sql


def test_post_submit_checker_policy_approval_requires_setup_role_provenance() -> None:
    constraint = next(
        constraint
        for constraint in PostSubmitCheckerPolicy.__table__.constraints
        if constraint.name is not None and constraint.name.endswith("approval_provenance")
    )

    constraint_sql = str(constraint.sqltext)

    assert "approved_by_role" in constraint_sql
    assert "admin" in constraint_sql
    assert "project_manager" in constraint_sql
    assert "approved_by_actor" in constraint_sql
    assert "approved_at" in constraint_sql


async def revoke_system_project_manager_for_default_actor() -> None:
    """Remove fixture-only creation authority before testing narrower grants."""
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == "flow-test",
                ActorIdentityLink.subject == "project-manager-subject",
            )
        )
        assert link is not None
        grant = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.target_actor_profile_id == link.actor_profile_id,
                AdminRoleGrant.role == "project_manager",
                AdminRoleGrant.scope_type == "system",
                AdminRoleGrant.status == "active",
            )
        )
        assert grant is not None
        grant.status = "revoked"
        grant.version += 1
        grant.revoked_by_actor_profile_id = grant.target_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "Remove fixture-only project creation authority"
        grant.revoked_at = datetime.now(UTC)
        await session.commit()


async def test_project_route_uses_canonical_actor_profile(
    project_client: AsyncClient,
) -> None:
    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": "Registry Proof",
            "slug": "registry-proof",
            "description": "Proves product routes observe actors directly",
        },
    )
    assert response.status_code == 201, response.text

    async with db_session.get_session_factory()() as session:
        identity_link = await session.scalar(
            select(ActorIdentityLink).where(ActorIdentityLink.subject == "project-manager-subject")
        )
        assert identity_link is not None
        profile = await session.get(ActorProfile, identity_link.actor_profile_id)

    assert profile is not None
    assert profile.actor_kind == "human"
    assert profile.status == "active"


async def test_project_create_exact_replay_and_mismatch_are_atomic(
    project_client: AsyncClient,
) -> None:
    key = str(uuid4())
    payload = {
        "name": "Idempotent Project",
        "slug": f"idempotent-project-{uuid4()}",
        "description": "Exact replay proof",
    }
    headers = auth_headers() | {"Idempotency-Key": key}
    created = await project_client.post("/api/v1/projects", headers=headers, json=payload)
    replayed = await project_client.post("/api/v1/projects", headers=headers, json=payload)
    mismatch = await project_client.post(
        "/api/v1/projects",
        headers=headers,
        json={**payload, "name": "Changed replay"},
    )
    async with db_session.get_session_factory()() as session:
        created_project = await session.get(Project, created.json()["id"])
        assert created_project is not None
        matched_grant_id = created_project.created_by_admin_role_grant_id
        assert matched_grant_id is not None
    await revoke_local_admin_role(matched_grant_id)
    replayed_after_revocation = await project_client.post(
        "/api/v1/projects", headers=headers, json=payload
    )

    assert created.status_code == replayed.status_code == 201, (
        created.text,
        replayed.text,
    )
    assert replayed.json() == created.json()
    assert replayed_after_revocation.status_code == 201
    assert replayed_after_revocation.json() == created.json()
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "idempotency_mismatch"

    async with db_session.get_session_factory()() as session:
        project = await session.get(Project, created.json()["id"])
        reservations = list(
            (
                await session.scalars(
                    select(ProjectCreateIdempotencyRecord).where(
                        ProjectCreateIdempotencyRecord.idempotency_key == UUID(key)
                    )
                )
            ).all()
        )
        project_count = await session.scalar(
            select(func.count()).select_from(Project).where(Project.slug == payload["slug"])
        )
        assert project is not None
        event = await session.get(AuditEvent, project.authorization_decision_event_id)
        allowed_event_count = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action_id == "project.create",
                AuditEvent.event_type == "SensitiveAuthorizationAllowed",
                AuditEvent.target_ref_id == project.id,
            )
        )

    assert project_count == 1
    assert len(reservations) == 1
    reservation = reservations[0]
    assert reservation.status == "committed"
    assert reservation.project_id == project.id
    assert project.creation_scope_type == "system"
    assert project.creation_action_id == "project.create"
    assert event is not None
    assert event.action_id == "project.create"
    assert event.resource_type == "project_create_operation"
    assert allowed_event_count == 1
    assert event.resource_id == str(reservation.operation_id)
    assert event.target_ref_kind == "project"
    assert event.target_ref_id == project.id


async def test_project_create_concurrent_exact_replay_commits_once(
    project_client: AsyncClient,
) -> None:
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    payload = {
        "name": "Concurrent Project",
        "slug": f"concurrent-project-{uuid4()}",
        "description": "Concurrent exact replay proof",
    }
    first, second = await asyncio.gather(
        project_client.post("/api/v1/projects", headers=headers, json=payload),
        project_client.post("/api/v1/projects", headers=headers, json=payload),
    )

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    async with db_session.get_session_factory()() as session:
        project_count = await session.scalar(
            select(func.count()).select_from(Project).where(Project.slug == payload["slug"])
        )
        replay_count = await session.scalar(
            select(func.count())
            .select_from(ProjectCreateIdempotencyRecord)
            .where(
                ProjectCreateIdempotencyRecord.idempotency_key == UUID(headers["Idempotency-Key"])
            )
        )
    assert project_count == replay_count == 1


@pytest.mark.asyncio
async def test_policy_mutation_api_commits_exact_custody_and_rejects_direct_append(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client, name="Policy custody")
    payload = complete_guide_payload()
    payload["review_policy"] = None
    payload["revision_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)
    headers = auth_headers() | {"If-Match": '"no-current-policy"'}
    body = {
        "review_preference_window_seconds": 3600,
        "review_lease_duration_seconds": 1800,
        "max_active_review_leases_per_reviewer": 1,
        "self_review_allowed": False,
        "reject_policy": "close_task",
        "finding_evidence_requirement": "optional",
        "requires_second_review": False,
        "allowed_decisions": ["accept", "needs_revision", "reject"],
        "minimum_finding_fields": ["issue", "required_fix"],
    }
    path = f"/api/v1/projects/{project['id']}/guides/{guide['id']}/review-policy"
    created = await project_client.put(path, headers=headers, json=body)
    replayed = await project_client.put(path, headers=headers, json=body)
    assert created.status_code == replayed.status_code == 200
    assert created.json() == replayed.json()

    async with db_session.get_session_factory()() as session:
        policy = await session.get(ReviewPolicy, created.json()["id"])
        assert policy is not None
        replay_count = await session.scalar(
            select(func.count())
            .select_from(PolicyMutationIdempotencyRecord)
            .where(PolicyMutationIdempotencyRecord.policy_id == policy.id)
        )
        assert replay_count == 1
        session.add(
            ReviewPolicy(
                id=str(uuid4()),
                project_id=policy.project_id,
                guide_version=policy.guide_version,
                policy_generation=2,
                policy_hash=policy.policy_hash,
                semantics_status="complete",
                supersedes_policy_id=policy.id,
                predecessor_policy_hash=policy.policy_hash,
                created_by_actor_profile_id=policy.created_by_actor_profile_id,
                created_via_identity_link_id=policy.created_via_identity_link_id,
                created_by_admin_role_grant_id=policy.created_by_admin_role_grant_id,
                creation_scope_type=policy.creation_scope_type,
                creation_scope_project_id=policy.creation_scope_project_id,
                creation_action_id=policy.creation_action_id,
                authorization_decision_event_id=policy.authorization_decision_event_id,
                review_preference_window_seconds=policy.review_preference_window_seconds,
                review_lease_duration_seconds=policy.review_lease_duration_seconds,
                max_active_review_leases_per_reviewer=(
                    policy.max_active_review_leases_per_reviewer
                ),
                self_review_allowed=policy.self_review_allowed,
                reject_policy=policy.reject_policy,
                finding_evidence_requirement=policy.finding_evidence_requirement,
                requires_second_review=policy.requires_second_review,
                allowed_decisions=policy.allowed_decisions,
                minimum_finding_fields=policy.minimum_finding_fields,
            )
        )
        with pytest.raises(DBAPIError, match="policy mutation custody mismatch"):
            await session.commit()


async def test_create_guide_never_enqueues_setup_or_runs_agents(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[dict[str, object]] = []

    def capture_enqueue(
        *,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        setup_run_id: str,
        setup_generation: int,
    ) -> str:
        """Capture queue arguments without running Celery."""
        enqueued.append(
            {
                "project_id": project_id,
                "guide_id": guide_id,
                "source_snapshot_id": source_snapshot_id,
                "setup_run_id": setup_run_id,
                "setup_generation": setup_generation,
            }
        )
        return project_setup_identity.project_guide_compilation_task_id(
            setup_run_id, setup_generation
        )

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "false")
    get_settings.cache_clear()
    from app.workers import project_setup as worker_module

    def forbidden_runtime(*args):
        pytest.fail("guide creation constructed the provider runtime")

    monkeypatch.setattr(worker_module, "create_project_guide_runtime", forbidden_runtime)
    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        capture_enqueue,
    )

    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    assert guide["project_id"] == project["id"]
    assert enqueued == []
    async with db_session.get_session_factory()() as session:
        snapshots = (
            await session.scalars(
                select(GuideSourceSnapshot).where(GuideSourceSnapshot.guide_id == guide["id"])
            )
        ).all()
        reports = (
            await session.scalars(
                select(GuideSufficiencyReport).where(GuideSufficiencyReport.guide_id == guide["id"])
            )
        ).all()
        policies = (
            await session.scalars(
                select(SubmissionArtifactPolicy).where(
                    SubmissionArtifactPolicy.guide_id == guide["id"]
                )
            )
        ).all()
        setup_runs = (
            await session.scalars(
                select(ProjectSetupRun).where(ProjectSetupRun.guide_id == guide["id"])
            )
        ).all()

    assert len(snapshots) == len(setup_runs) == 1
    assert setup_runs[0].source_snapshot_id == snapshots[0].id
    assert setup_runs[0].status == "awaiting_documents"
    assert setup_runs[0].celery_task_id is None
    assert reports == []
    assert policies == []


def test_project_setup_queue_syncs_all_setup_task_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutable Celery configuration applies to the sole unified setup task."""
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://initial")
    get_settings.cache_clear()

    from app.workers.project_setup import run_project_guide_compilation
    from app.workers import task_settings
    from app.core.config import Settings
    from app.workers.task_settings import sync_task_settings
    monkeypatch.setattr(task_settings, "get_settings", lambda: Settings(_env_file=None))

    tasks = tuple(cast(Any, task) for task in (run_project_guide_compilation,))
    original_config = {
        task: {
            "broker_url": task.app.conf.broker_url,
            "result_backend": task.app.conf.result_backend,
            "task_always_eager": task.app.conf.task_always_eager,
            "task_eager_propagates": task.app.conf.task_eager_propagates,
        }
        for task in tasks
    }
    try:
        monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://explicit")
        monkeypatch.setenv("WORKSTREAM_CELERY_RESULT_BACKEND_URL", "rpc://")
        monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "false")
        get_settings.cache_clear()
        sync_task_settings(*tasks)

        for task in tasks:
            assert task.app.conf.broker_url == "memory://explicit"
            assert task.app.conf.result_backend == "rpc://"
            assert task.app.conf.task_always_eager is False
            assert task.app.conf.task_eager_propagates is True

        monkeypatch.delenv("WORKSTREAM_CELERY_BROKER_URL", raising=False)
        monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
        get_settings.cache_clear()
        sync_task_settings(*tasks)

        for task in tasks:
            assert task.app.conf.broker_url == "memory://"
            assert task.app.conf.task_always_eager is True
            assert task.app.conf.task_eager_propagates is True
    finally:
        for task, values in original_config.items():
            for key, value in values.items():
                setattr(task.app.conf, key, value)
        get_settings.cache_clear()


async def test_get_project_rejects_token_role_when_setup_queue_is_unavailable(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token role cannot authorize project identity under any queue state."""
    project = await create_project(project_client)
    await revoke_system_project_manager_for_default_actor()
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "false")
    monkeypatch.delenv("WORKSTREAM_CELERY_BROKER_URL", raising=False)
    get_settings.cache_clear()

    response = await project_client.get(
        f"/api/v1/projects/{project['id']}",
        headers=auth_headers(),
    )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "project_authorization_resource_not_found"


def test_project_identity_projection_is_structurally_minimal_for_contributors() -> None:
    """Contributor selection cannot serialize admin-only project fields."""
    project = Project(
        id=str(uuid4()),
        name="Projection proof",
        slug="projection-proof",
        description="Admin-only project description",
        status="active",
    )
    contributor = ProjectService.project_identity_response(project, contributor_only=True)
    assert contributor.model_dump() == {
        "id": project.id,
        "name": "Projection proof",
        "status": "active",
    }
    assert "slug" not in contributor.model_dump()
    assert "description" not in contributor.model_dump()


async def test_project_identity_and_context_follow_exact_grant_and_lifecycle(
    project_client: AsyncClient,
) -> None:
    """Live routes conceal cross-project, revoked, suspended, and revoked-link access."""
    project = await create_project(project_client, name="Visible project")
    other = await create_project(project_client, name="Other project")
    await revoke_system_project_manager_for_default_actor()
    grant_id, link_id = await add_project_role_for_default_actor(project["id"], "submitter")

    identity = await project_client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers())
    assert identity.status_code == 200, identity.text
    assert identity.json() == {
        "id": project["id"],
        "name": "Visible project",
        "status": "draft",
    }
    context = await project_client.get(
        f"/api/v1/actors/me/authorization-context?project_id={project['id']}",
        headers=auth_headers(),
    )
    assert context.status_code == 200, context.text
    assert context.json()["project_roles"] == ["submitter"]
    assert context.json()["admin_roles"] == []
    assert context.json()["effective_action_ids"] == ["project.read"]

    for path in (
        f"/api/v1/projects/{other['id']}",
        f"/api/v1/actors/me/authorization-context?project_id={other['id']}",
    ):
        denied = await project_client.get(path, headers=auth_headers())
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "project_authorization_resource_not_found"

    now = datetime.now(UTC)
    async with db_session.get_session_factory()() as session:
        grant = await session.get(ProjectRoleGrant, grant_id)
        assert grant is not None
        grant.status = "revoked"
        grant.version = 2
        grant.revoked_by_actor_profile_id = grant.actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "AUTH-11B revocation proof"
        grant.revoked_at = now
        await session.commit()
    for path in (
        f"/api/v1/projects/{project['id']}",
        f"/api/v1/actors/me/authorization-context?project_id={project['id']}",
    ):
        denied = await project_client.get(path, headers=auth_headers())
        assert denied.status_code == 404

    await add_project_role_for_default_actor(project["id"], "reviewer")
    async with db_session.get_session_factory()() as session:
        link = await session.get(ActorIdentityLink, link_id)
        assert link is not None
        profile = await session.get(ActorProfile, link.actor_profile_id)
        assert profile is not None
        profile.status = "suspended"
        profile.suspended_by = profile.id
        profile.suspended_at = now
        profile.suspension_reason = "AUTH-11B stale actor proof"
        await session.commit()
    for path in (
        f"/api/v1/projects/{project['id']}",
        f"/api/v1/actors/me/authorization-context?project_id={project['id']}",
    ):
        denied = await project_client.get(path, headers=auth_headers())
        assert denied.status_code == 404

    async with db_session.get_session_factory()() as session:
        link = await session.get(ActorIdentityLink, link_id)
        assert link is not None
        profile = await session.get(ActorProfile, link.actor_profile_id)
        assert profile is not None
        profile.status = "active"
        profile.suspended_by = None
        profile.suspended_at = None
        profile.suspension_reason = None
        profile.reactivated_by = profile.id
        profile.reactivated_at = now
        profile.reactivation_reason = "AUTH-11B stale link proof setup"
        link.status = "revoked"
        link.revoked_by = profile.id
        link.revoked_at = now
        link.revoked_reason = "AUTH-11B stale link proof"
        await session.commit()
    for path in (
        f"/api/v1/projects/{project['id']}",
        f"/api/v1/actors/me/authorization-context?project_id={project['id']}",
    ):
        denied = await project_client.get(path, headers=auth_headers())
        assert denied.status_code == 404








async def test_read_guide_source_snapshot_does_not_run_agents_before_committed_documents(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()

    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    await read_guide_source_snapshot(project["id"], guide["id"])

    async with db_session.get_session_factory()() as session:
        snapshot = await session.scalar(
            select(GuideSourceSnapshot).where(GuideSourceSnapshot.guide_id == guide["id"])
        )
        report = await session.scalar(
            select(GuideSufficiencyReport).where(GuideSufficiencyReport.guide_id == guide["id"])
        )
        policy = await session.scalar(
            select(SubmissionArtifactPolicy).where(SubmissionArtifactPolicy.guide_id == guide["id"])
        )
        effective_policy = await session.scalar(
            select(EffectiveProjectSubmissionArtifactPolicy).where(
                EffectiveProjectSubmissionArtifactPolicy.guide_id == guide["id"]
            )
        )
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(PreSubmitCheckerPolicy.guide_id == guide["id"])
        )

    assert snapshot is not None
    assert report is None
    assert policy is None
    assert effective_policy is None
    assert pre_submit_checker_policy is None







def sha256_hash(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


async def test_guide_source_metadata_authority_records_exact_provenance_and_replays(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three 12D mutations retain exact authority and replay custody."""
    get_settings.cache_clear()
    project = await create_project(project_client)
    create_key = str(uuid4())
    create_headers = auth_headers() | {"Idempotency-Key": create_key}
    payload = complete_guide_payload()

    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=create_headers,
        json=payload,
    )
    replayed = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=create_headers,
        json=payload,
    )
    assert created.status_code == replayed.status_code == 201
    assert replayed.json() == created.json()
    guide = created.json()

    update_key = str(uuid4())
    updated = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers() | {"Idempotency-Key": update_key},
        json={"change_summary": "Expanded metadata."},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["change_summary"] == "Expanded metadata."

    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    blocked = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"content_markdown": "replacement source"},
    )
    metadata_update = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"change_summary": "Clarified without replacing source"},
    )
    assert blocked.status_code == 422
    assert metadata_update.status_code == 200, metadata_update.text

    async with db_session.get_session_factory()() as session:
        persisted_guide = await session.get(ProjectGuide, guide["id"])
        persisted_snapshot = await session.get(GuideSourceSnapshot, snapshot["id"])

        records = (
            await session.scalars(
                select(GuideMutationIdempotencyRecord).where(
                    GuideMutationIdempotencyRecord.project_id == project["id"]
                )
            )
        ).all()
        assert persisted_guide is not None
        assert persisted_snapshot is not None
        assert persisted_guide.last_mutation_action_id == "project.guide.update"
        assert persisted_guide.last_mutation_scope_type == "system"
        assert persisted_guide.last_mutation_scope_project_id is None
        assert persisted_guide.last_authorization_decision_event_id is not None
        assert persisted_snapshot.creation_action_id == "project.guide_source_snapshot.create"
        assert persisted_snapshot.authorization_decision_event_id is not None
        assert len(records) == 4
        assert all(record.status == "committed" for record in records)
        assert sum(record.action_id == "project.guide.create" for record in records) == 1
        assert (
            sum(record.action_id == "project.guide_source_snapshot.create" for record in records)
            == 1
        )


@pytest.mark.parametrize(
    ("identity_matches", "digest_matches", "status", "insert_wins", "expected"),
    [
        (False, True, "pending", False, "mismatch"),
        (True, False, "pending", False, "mismatch"),
        (True, True, "pending", False, "pending"),
        (True, True, "committed", False, "replayed"),
        (True, True, "pending", True, "claimed"),
    ],
)
async def test_guide_mutation_repository_classifies_existing_reservations(
    identity_matches: bool,
    digest_matches: bool,
    status: str,
    insert_wins: bool,
    expected: str,
) -> None:
    record_id = uuid4()
    identity_link_id = str(uuid4())
    request_digest = "sha256:" + "a" * 64
    record = SimpleNamespace(
        id=record_id,
        identity_link_id=identity_link_id if identity_matches else str(uuid4()),
        request_digest=request_digest if digest_matches else "sha256:" + "b" * 64,
        status=status,
    )

    class Session:
        scalar_calls = 0

        async def scalar(self, statement):
            self.scalar_calls += 1
            if self.scalar_calls == 1:
                return record
            if insert_wins:
                return statement.compile().params["id"]
            return record_id

        async def get(self, _model, selected_id):
            if not insert_wins:
                assert selected_id == record_id
            return record

    repository = GuideMutationRepository(Session())  # type: ignore[arg-type]
    assert await repository.find(str(uuid4()), "project.guide.create", uuid4()) is record
    result, selected = await repository.reserve(
        actor_profile_id=str(uuid4()),
        identity_link_id=identity_link_id,
        action_id="project.guide.create",
        idempotency_key=uuid4(),
        request_digest=request_digest,
        resource_context_digest="sha256:" + "c" * 64,
        operation_id=uuid4(),
        project_id=str(uuid4()),
        resource_id=str(uuid4()),
        operation_generation=1,
    )

    assert result == expected
    assert selected is record


@pytest.mark.parametrize("missing_stage", ["insert", "load", "complete"])
async def test_guide_mutation_repository_fails_closed_when_custody_disappears(
    missing_stage: str,
) -> None:
    record_id = uuid4()

    class Session:
        async def scalar(self, _statement):
            return None if missing_stage in {"insert", "complete"} else record_id

        async def get(self, _model, _selected_id):
            return None

    repository = GuideMutationRepository(Session())  # type: ignore[arg-type]
    with pytest.raises(ProjectRepositoryIntegrityError):
        if missing_stage == "complete":
            await repository.complete(
                SimpleNamespace(id=record_id),  # type: ignore[arg-type]
                response_json={},
            )
        else:
            await repository.reserve(
                actor_profile_id=str(uuid4()),
                identity_link_id=str(uuid4()),
                action_id="project.guide.create",
                idempotency_key=uuid4(),
                request_digest="sha256:" + "a" * 64,
                resource_context_digest="sha256:" + "b" * 64,
                operation_id=uuid4(),
                project_id=str(uuid4()),
                resource_id=str(uuid4()),
                operation_generation=1,
            )


async def test_guide_mutation_router_composes_only_key_gated_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = uuid4()
    request = object()
    result = object()
    session = object()
    rate_control = object()
    resolved = object()
    prepared = object()
    calls: list[tuple] = []

    async def resolve(current_request, current_result, current_session, current_rate):
        calls.append((current_request, current_result, current_session, current_rate))
        return resolved

    @asynccontextmanager
    async def prepared_context(current_request, current_resolved, current_session):
        calls.append((current_request, current_resolved, current_session))
        try:
            yield prepared
        finally:
            calls.append(("prepared_closed",))

    monkeypatch.setattr(guide_mutation_router_module, "resolve_authorization_actor", resolve)
    monkeypatch.setattr(
        guide_mutation_router_module,
        "prepared_authorization_service",
        prepared_context,
    )

    assert (
        await guide_mutation_router_module.guide_authorization_actor(
            key,
            request,
            result,
            session,
            rate_control,  # type: ignore[arg-type]
        )
        is resolved
    )
    dependency = guide_mutation_router_module.get_guide_prepared_authorization_service(
        request,
        resolved,
        session,  # type: ignore[arg-type]
    )
    assert await anext(dependency) is prepared
    await dependency.aclose()
    assert await guide_mutation_router_module.guide_authorization(
        key,
        resolved,
        prepared,  # type: ignore[arg-type]
    ) == (key, resolved, prepared)
    assert calls == [
        (request, result, session, rate_control),
        (request, resolved, session),
        ("prepared_closed",),
    ]


def test_guide_mutation_router_translates_bounded_service_errors() -> None:
    pending = guide_mutation_router_module._error(
        guide_mutation_router_module.GuideMutationIdempotencyConflict("idempotency_pending")
    )
    mismatch = guide_mutation_router_module._error(
        guide_mutation_router_module.GuideMutationIdempotencyConflict("idempotency_mismatch")
    )
    missing = guide_mutation_router_module._error(ProjectNotFound("project not found"))

    assert pending.status_code == 409
    assert pending.retryable is True
    assert pending.error_message == "Guide mutation is already in progress"
    assert mismatch.status_code == 409
    assert mismatch.retryable is False
    assert mismatch.error_message == "Idempotency key does not match"
    assert missing.status_code == 404
    assert missing.detail == "project not found"


async def test_guide_mutation_router_finishes_commit_and_replay_without_early_dispatch() -> None:
    class Session:
        commit_count = 0
        rollback_count = 0

        async def commit(self):
            self.commit_count += 1

        async def rollback(self):
            self.rollback_count += 1

    response = SimpleNamespace(
        project_id="project-1",
        guide_id="guide-1",
        id="snapshot-1",
    )
    session = Session()
    assert (
        await guide_mutation_router_module._finish(
            session,
            SimpleNamespace(
                replayed=False,
                setup_run_id="setup-1",
                setup_generation=7,
                response=response,
            ),
        )
        is response
    )
    assert session.commit_count == 1
    assert session.rollback_count == 0

    assert (
        await guide_mutation_router_module._finish(
            session,
            SimpleNamespace(replayed=True, setup_run_id="setup-1", response=response),
        )
        is response
    )
    assert session.rollback_count == 1
    assert session.commit_count == 1

    with pytest.raises(RuntimeError, match="committed project setup generation is unavailable"):
        await guide_mutation_router_module._finish(
            session,
            SimpleNamespace(
                replayed=False,
                setup_run_id="setup-without-generation",
                setup_generation=None,
                response=response,
            ),
        )
    assert session.rollback_count == 1
    assert session.commit_count == 1


async def test_guide_mutation_service_executes_all_three_authorized_happy_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid4()
    actor_id, link_id, grant_id = (uuid4() for _ in range(3))
    resolved = SimpleNamespace(
        profile=SimpleNamespace(id=str(actor_id)),
        identity_link=SimpleNamespace(id=str(link_id)),
    )

    class Session:
        flush_count = 0
        refresh_count = 0

        async def flush(self):
            self.flush_count += 1

        async def refresh(self, _record):
            self.refresh_count += 1

    class Repository:
        project = SimpleNamespace(id=str(project_id))
        guide = None
        snapshot = None
        items = None
        setup_run = None

        async def get_project(self, selected_id, *, for_update=False):
            assert selected_id == str(project_id)
            assert for_update is True
            return self.project

        async def get_guide_by_version(self, selected_project_id, _version):
            assert selected_project_id == str(project_id)
            return None

        async def add_guide(self, guide):
            guide.created_at = datetime.now(UTC)
            guide.updated_at = guide.created_at
            self.guide = guide

        async def lock_project_guide(self, selected_id):
            assert self.guide is not None
            assert selected_id == self.guide.id
            return self.guide

        async def lock_latest_guide_source_snapshot(self, *_args):
            return None

        async def add_guide_source_snapshot(self, snapshot, items):
            snapshot.captured_at = datetime.now(UTC)
            for item in items:
                item.created_at = snapshot.captured_at
            self.snapshot = snapshot
            self.items = items

        async def next_project_setup_generation(self, selected_guide_id):
            assert self.guide is not None
            assert selected_guide_id == self.guide.id
            return 1

        async def add_project_setup_run(self, setup_run):
            self.setup_run = setup_run

    class Replay:
        def __init__(self):
            self.completed: list[tuple] = []

        async def find(self, *_args):
            return None

        async def reserve(self, **_facts):
            return "claimed", SimpleNamespace(response_json=None)

        async def complete(self, record, **facts):
            self.completed.append((record, facts))

    class Prepared:
        prepare_count = 0
        consume_count = 0

        async def prepare(self, *_args):
            self.prepare_count += 1
            return object()

        async def consume(self, _handle, _action, _caller, resource):
            self.consume_count += 1
            return SimpleNamespace(
                matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
                matched_grant_id=grant_id,
                matched_scope_project_id=project_id,
                resource_context_digest=canonical_json_hash(resource.model_dump(mode="json")),
                decision_id=uuid4(),
            )

    session = Session()
    repository = Repository()
    replay = Replay()
    prepared = Prepared()
    service = GuideMutationService(session)
    service._repo = repository  # type: ignore[assignment]
    service._replay = replay  # type: ignore[assignment]

    created = await service.create_guide(
        resolved,
        prepared,
        uuid4(),
        project_id,
        ProjectGuideCreate.model_validate(complete_guide_payload()),
    )
    guide_id = UUID(created.response.id)
    updated = await service.update_guide(
        resolved,
        prepared,
        uuid4(),
        project_id,
        guide_id,
        ProjectGuideUpdate(change_summary="Clarified"),
    )
    assert created.replayed is updated.replayed is False
    assert updated.response.change_summary == "Clarified"
    assert created.response.documents
    assert created.setup_run_id == repository.setup_run.id
    assert prepared.prepare_count == prepared.consume_count == 3
    assert len(replay.completed) == 3
    assert session.flush_count == session.refresh_count == 1
    assert repository.snapshot is not None
    assert repository.items


class _GuideMutationTestResponse:
    @classmethod
    def model_validate(cls, value):
        return ("validated", value)


def _guide_mutation_edge_subject():
    actor_id, link_id, project_id = (uuid4() for _ in range(3))
    resolved = SimpleNamespace(
        profile=SimpleNamespace(id=str(actor_id)),
        identity_link=SimpleNamespace(id=str(link_id)),
    )

    class Replay:
        def __init__(self):
            self.record = None

        async def find(self, *_args):
            return self.record

    replay = Replay()
    service = GuideMutationService(object())
    service._replay = replay  # type: ignore[assignment]
    return resolved, project_id, replay, service


async def test_guide_mutation_service_classifies_existing_replay() -> None:
    resolved, _project_id, replay, service = _guide_mutation_edge_subject()
    replay.record = SimpleNamespace(
        identity_link_id=str(uuid4()),
        request_digest="digest",
        status="committed",
        response_json={"id": "response"},
    )
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_mismatch",
    ):
        await service._existing(
            resolved,
            ActionId.PROJECT_GUIDE_CREATE,
            uuid4(),
            "digest",
            _GuideMutationTestResponse,
        )

    replay.record = SimpleNamespace(
        identity_link_id=resolved.identity_link.id,
        request_digest="digest",
        status="pending",
        response_json=None,
    )
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_pending",
    ):
        await service._existing(
            resolved,
            ActionId.PROJECT_GUIDE_CREATE,
            uuid4(),
            "digest",
            _GuideMutationTestResponse,
        )

    replay.record.status = "committed"
    replay.record.response_json = {"id": "response"}
    existing = await service._existing(
        resolved,
        ActionId.PROJECT_GUIDE_CREATE,
        uuid4(),
        "digest",
        _GuideMutationTestResponse,
    )
    assert existing.response == ("validated", {"id": "response"})
    assert existing.replayed is True


async def test_guide_update_service_returns_exact_cached_response() -> None:
    resolved, project_id, _replay, _service = _guide_mutation_edge_subject()
    cached = SimpleNamespace(replayed=True)

    async def cached_existing(*_args):
        return cached

    cached_service = GuideMutationService(object())
    cached_service._existing = cached_existing  # type: ignore[method-assign]
    guide_id = uuid4()
    assert (
        await cached_service.update_guide(
            resolved,
            object(),
            uuid4(),
            project_id,
            guide_id,
            ProjectGuideUpdate(change_summary="cached"),
        )
        is cached
    )



def test_guide_mutation_service_classifies_reservation_outcomes() -> None:
    _resolved, _project_id, _replay, service = _guide_mutation_edge_subject()
    record = SimpleNamespace(response_json={"id": "response"})
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_mismatch",
    ):
        service._reservation_outcome("mismatch", record, _GuideMutationTestResponse)
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_pending",
    ):
        service._reservation_outcome("pending", record, _GuideMutationTestResponse)
    replayed = service._reservation_outcome("replayed", record, _GuideMutationTestResponse)
    assert replayed.response == ("validated", {"id": "response"})
    assert replayed.replayed is True


def test_guide_mutation_service_rejects_invalid_authority_proof() -> None:
    _resolved, project_id, _replay, service = _guide_mutation_edge_subject()
    with pytest.raises(RuntimeError, match="lacked Project Manager authority"):
        service._prove(
            SimpleNamespace(
                matched_authority_kind=None,
                matched_grant_id=None,
                matched_scope_project_id=None,
            ),
            project_id,
        )


async def test_guide_mutation_service_composes_unsupported_prepare_denial() -> None:
    resolved, project_id, _replay, service = _guide_mutation_edge_subject()

    class Prepared:
        def __init__(self):
            self.denied = None

        async def prepare(self, *_args):
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)

        async def deny_unsupported(self, *args):
            self.denied = args

    prepared = Prepared()
    caller, _ = service._input(
        ActionId.PROJECT_GUIDE_CREATE,
        "POST /api/v1/projects/{project_id}/guides",
        resolved,
        uuid4(),
        ProjectGuideCreate.model_validate(complete_guide_payload()),
        project_id=project_id,
        target_resource_id=uuid4(),
        operation_id=uuid4(),
    )
    assert (
        await service._prepare(
            prepared,
            ActionId.PROJECT_GUIDE_CREATE,
            caller,
            project_id,
            guide_id=None,
            target_kind="guide_create",
        )
        is None
    )
    assert prepared.denied is not None
    denial_resource = prepared.denied[2]
    assert denial_resource.scope_project_id == project_id
    assert denial_resource.requested_guide_id is None
    assert denial_resource.requested_target_kind == "guide_create"


async def test_guide_source_metadata_authority_rejects_removed_fields_and_bad_replay(
    project_client: AsyncClient,
) -> None:
    """The clean-cut schema and exact replay digest both fail closed."""
    project = await create_project(project_client)
    for retired_field in ("review_policy", "revision_policy", "payment_policy"):
        rejected = await project_client.post(
            f"/api/v1/projects/{project['id']}/guides",
            headers=auth_headers(),
            json=complete_guide_payload() | {retired_field: {}},
        )
        assert rejected.status_code == 422
        assert retired_field in rejected.text

    key = str(uuid4())
    headers = auth_headers() | {"Idempotency-Key": key}
    first = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=headers,
        json=complete_guide_payload(),
    )
    mismatch = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=headers,
        json=complete_guide_payload("v2"),
    )
    assert first.status_code == 201, first.text
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "idempotency_mismatch"

    guide = first.json()
    update_key = str(uuid4())
    update_headers = auth_headers() | {"Idempotency-Key": update_key}
    explicit_null = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=update_headers,
        json={"change_summary": None},
    )
    omitted_field = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=update_headers,
        json={},
    )
    assert explicit_null.status_code == 200, explicit_null.text
    assert omitted_field.status_code == 409
    assert omitted_field.json()["error"]["code"] == "idempotency_mismatch"


async def test_guide_source_metadata_authority_validates_key_before_actor_provisioning(
    project_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing and malformed replay custody cannot create actor identity state."""
    subject = f"guide-key-rejected-{uuid4()}"
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", subject)
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        project_id, guide_id = uuid4(), uuid4()
        requests = (
            ("post", f"/api/v1/projects/{project_id}/guides", complete_guide_payload()),
            (
                "patch",
                f"/api/v1/projects/{project_id}/guides/{guide_id}",
                {"change_summary": "must fail before actor provisioning"},
            ),
            (
                "post",
                f"/api/v1/projects/{project_id}/guides/{guide_id}/documents/{uuid4()}/content",
                {},
            ),
        )
        for method, path, payload in requests:
            for headers in (
                {"Authorization": "Bearer project-token"},
                {
                    "Authorization": "Bearer project-token",
                    "Idempotency-Key": "not-a-uuid",
                },
            ):
                response = await client.request(method, path, headers=headers, json=payload)
                assert response.status_code == 422

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(ActorIdentityLink).where(ActorIdentityLink.subject == subject)
            )
            is None
        )


async def test_create_guide_source_metadata_concurrent_replay_commits_once(
    project_client: AsyncClient,
) -> None:
    """Two simultaneous exact requests converge on one guide and response."""
    project = await create_project(project_client)
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    payload = complete_guide_payload()

    first, second = await asyncio.gather(
        project_client.post(
            f"/api/v1/projects/{project['id']}/guides",
            headers=headers,
            json=payload,
        ),
        project_client.post(
            f"/api/v1/projects/{project['id']}/guides",
            headers=headers,
            json=payload,
        ),
    )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectGuide)
                .where(
                    ProjectGuide.project_id == project["id"],
                    ProjectGuide.version == payload["version"],
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GuideMutationIdempotencyRecord)
                .where(
                    GuideMutationIdempotencyRecord.project_id == project["id"],
                    GuideMutationIdempotencyRecord.action_id == "project.guide.create",
                )
            )
            == 1
        )


async def test_guide_source_metadata_authority_enforces_exact_project_scope(
    project_client: AsyncClient,
) -> None:
    """A project-scoped Project Manager grant cannot cross into another project."""
    allowed_project = await create_project(project_client, name="Guide scope allowed")
    denied_project = await create_project(project_client, name="Guide scope denied")
    await revoke_system_project_manager_for_default_actor()
    grant_id = await add_project_manager_admin_grant(allowed_project["id"])

    allowed = await project_client.post(
        f"/api/v1/projects/{allowed_project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload(),
    )
    denied = await project_client.post(
        f"/api/v1/projects/{denied_project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload(),
    )
    assert allowed.status_code == 201, allowed.text
    assert denied.status_code == 403

    async with db_session.get_session_factory()() as session:
        guide = await session.get(ProjectGuide, allowed.json()["id"])
        assert guide is not None
        assert guide.last_mutated_by_admin_role_grant_id == grant_id
        assert guide.last_mutation_scope_type == "project"
        assert guide.last_mutation_scope_project_id == allowed_project["id"]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectGuide)
                .where(ProjectGuide.project_id == denied_project["id"])
            )
            == 0
        )
        denial = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action_id == "project.guide.create",
                AuditEvent.event_type == "SensitiveAuthorizationDenied",
                AuditEvent.target_ref_id == denied_project["id"],
            )
        )
        assert denial is not None
        assert denial.denial_code == "permission_not_granted"


async def test_guide_source_metadata_replay_cannot_cross_project_or_guide(
    project_client: AsyncClient,
) -> None:
    """The same actor/action/key/body never replays across route selectors."""
    first_project = await create_project(project_client, name="Replay first")
    second_project = await create_project(project_client, name="Replay second")
    create_key = str(uuid4())
    create_headers = auth_headers() | {"Idempotency-Key": create_key}
    first_guide_response = await project_client.post(
        f"/api/v1/projects/{first_project['id']}/guides",
        headers=create_headers,
        json=complete_guide_payload(),
    )
    crossed_create = await project_client.post(
        f"/api/v1/projects/{second_project['id']}/guides",
        headers=create_headers,
        json=complete_guide_payload(),
    )
    assert first_guide_response.status_code == 201
    assert crossed_create.status_code == 409
    assert crossed_create.json()["error"]["code"] == "idempotency_mismatch"

    first_guide = first_guide_response.json()
    second_guide = await create_guide(
        project_client, second_project["id"], complete_guide_payload("v2")
    )
    update_key = str(uuid4())
    update_headers = auth_headers() | {"Idempotency-Key": update_key}
    update_body = {"change_summary": "Selector-bound update"}
    first_update = await project_client.patch(
        f"/api/v1/projects/{first_project['id']}/guides/{first_guide['id']}",
        headers=update_headers,
        json=update_body,
    )
    crossed_update = await project_client.patch(
        f"/api/v1/projects/{second_project['id']}/guides/{second_guide['id']}",
        headers=update_headers,
        json=update_body,
    )
    assert first_update.status_code == 200
    assert crossed_update.status_code == 409
    assert crossed_update.json()["error"]["code"] == "idempotency_mismatch"



async def test_guide_creation_replay_waits_for_committed_documents(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact guide replay returns custody without dispatching before verification."""
    dispatched: list[dict[str, str]] = []

    def capture_dispatch(**facts: str) -> str:
        dispatched.append(facts)
        return project_setup_identity.project_guide_compilation_task_id(
            facts["setup_run_id"], int(facts["setup_generation"])
        )

    get_settings.cache_clear()
    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        capture_dispatch,
    )
    project = await create_project(project_client)
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    payload = complete_guide_payload()
    first = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=headers,
        json=payload,
    )
    replay = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=headers,
        json=payload,
    )
    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()
    assert dispatched == []
    async with db_session.get_session_factory()() as session:
        runs = (
            await session.scalars(
                select(ProjectSetupRun).where(
                    ProjectSetupRun.id == first.json()["setup"]["id"]
                )
            )
        ).all()
        assert len(runs) == 1
        assert runs[0].celery_task_id is None
        assert runs[0].status == "awaiting_documents"


async def test_guide_source_metadata_database_rejects_unattributed_and_mismatched_custody(
    project_client: AsyncClient,
) -> None:
    """Deferred 0045 guards reject missing or borrowed authorization evidence."""
    project = await create_project(project_client)
    async with db_session.get_session_factory()() as session:
        session.add(
            ProjectGuide(
                **guide_example_columns(),
                id=str(uuid4()),
                project_id=project["id"],
                version="unattributed",
                status="draft",
                change_summary=None,
                created_by=str(uuid4()),
            )
        )
        await session.flush()
        with pytest.raises(IntegrityError, match="new guides require mutation authority"):
            await session.commit()
        await session.rollback()

    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    async with db_session.get_session_factory()() as session:
        persisted = await session.get(ProjectGuide, guide["id"])
        assert persisted is not None
        persisted.change_summary = "Changed without fresh custody"
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(ProjectGuide, guide["id"])
        assert persisted is not None
        persisted.version = "stale-lineage-rewrite"
        with pytest.raises(IntegrityError, match="identity and lineage are immutable"):
            await session.commit()
        await session.rollback()

    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    async with db_session.get_session_factory()() as session:
        persisted_snapshot = await session.get(GuideSourceSnapshot, snapshot["id"])
        assert persisted_snapshot is not None
        persisted_snapshot.created_via_identity_link_id = str(uuid4())
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(ProjectGuide, guide["id"])
        borrowed = await session.scalar(
            select(AuditEvent).where(AuditEvent.action_id == "project.create")
        )
        assert persisted is not None
        assert borrowed is not None
        persisted.last_authorization_decision_event_id = borrowed.id
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


def test_project_setup_run_status_constraint_metadata() -> None:
    status_constraint = next(
        constraint
        for constraint in ProjectSetupRun.__table__.constraints
        if constraint.name is not None and constraint.name.endswith("ck_project_setup_runs_status")
    )

    constraint_sql = str(status_constraint.sqltext)

    for status in (
        "queued",
        "dispatch_pending",
        "enqueue_failed",
        "enqueue_identity_mismatch",
        "running_sufficiency_agent",
        "sufficiency_blocked",
        "running_policy_derivation_agent",
        "policy_draft_ready",
        "running_post_submit_derivation_agent",
        "post_submit_setup_blocked",
        "post_submit_policy_compiled",
        "setup_blocked",
        "failed",
    ):
        assert status in constraint_sql


def test_project_setup_visibility_exposes_document_readiness() -> None:
    assert "documents_ready_at" in ProjectSetupRunResponse.model_fields
    assert not {"continuation_verification_job_id", "continuation_started_at"} & ProjectSetupRunResponse.model_fields.keys()


def test_project_setup_error_summary_redacts_sensitive_diagnostics() -> None:
    service = ProjectService.__new__(ProjectService)

    unsafe_summaries = [
        "broker rejected https://storage.flow.test/signed?token=secret",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
        "Basic d29ya3N0cmVhbTpzZWNyZXQ=",
        "aws access key AKIAIOSFODNN7EXAMPLE failed",
        "failed reading projects/acme/snapshots/source.md",
        "path=/home/abiorh/workstream/private.py failed",
        'Traceback most recent call last File "/srv/app/project_setup.py", line 10',
        r"worker failed at C:\Users\alice\secret\guide.md",
        r"worker failed at \\server\share\guide.md",
        "object key s3://private-bucket/customer/path failed",
    ]

    for summary in unsafe_summaries:
        assert service._safe_project_setup_error_summary(summary) == (
            "project setup failed; inspect server logs with the setup run id"
        )

    assert service._safe_project_setup_error_summary("broker temporarily unavailable") == (
        "project setup failed; inspect server logs with the setup run id"
    )
    assert service._safe_project_setup_error_summary("   ") == "project setup failed"


async def test_project_setup_waits_for_verified_guide_material_before_outputs(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    project = await create_project(project_client)
    await add_project_manager_admin_grant(project["id"])
    guide = await create_guide(
        project_client,
        project["id"],
        {
            **complete_guide_payload(),
            "documents": complete_guide_payload()["documents"],
        },
    )

    setup_run_response = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/setup-runs/latest",
        headers=auth_headers(),
    )
    reports_response = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports",
        headers=auth_headers(),
    )
    policies_response = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
    )

    assert setup_run_response.status_code == 200, setup_run_response.text
    setup_run = setup_run_response.json()
    assert setup_run["status"] == "awaiting_documents"
    assert setup_run["current_step"] == "awaiting_documents"
    assert setup_run["celery_task_id"] is None
    assert setup_run["output_sufficiency_report_id"] is None
    assert setup_run["output_submission_artifact_policy_id"] is None
    assert setup_run["documents_ready_at"] is None
    assert "continuation_verification_job_id" not in setup_run
    assert "continuation_started_at" not in setup_run
    assert reports_response.status_code == 200
    assert reports_response.json() == []
    assert policies_response.status_code == 200
    assert policies_response.json() == []


async def test_pre_submit_visibility_requires_compiled_policy(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    await create_approved_policy_bundle(
        project_client,
        project["id"],
        guide["id"],
        compile_pre_submit_checker=False,
    )

    response = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/pre-submit-checker-policy",
        headers=auth_headers(),
    )

    assert response.status_code == 404


async def test_document_ready_setup_enqueue_failure_is_sanitized_and_retryable(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()

    def fail_enqueue(**_: object) -> str:
        raise ProjectSetupQueueError(
            "broker rejected https://storage.flow.test/signed?token=secret"
        )

    monkeypatch.setattr(
        project_setup_queue_module, "enqueue_project_guide_compilation", fail_enqueue
    )
    project = await create_project(project_client)
    guide = await create_guide(
        project_client,
        project["id"],
        {
            **complete_guide_payload(),
            "documents": complete_guide_payload()["documents"],
        },
    )

    async with db_session.get_session_factory()() as session:
        run = await session.scalar(
            select(ProjectSetupRun).where(ProjectSetupRun.guide_id == guide["id"])
        )
        assert run is not None
        source_snapshot_id = run.source_snapshot_id
        await session.commit()
        await create_committed_document_fixture(source_snapshot_id)
        from app.modules.projects.guide_setup_continuation import continue_setup_after_stored_guide_item
        from app.adapters.artifacts import guide_document_manifest_port
        await continue_setup_after_stored_guide_item(
            UUID(source_snapshot_id), session_factory=db_session.get_session_factory(),
            manifest_factory=guide_document_manifest_port,
        )

    response = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/setup-runs/latest",
        headers=auth_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "enqueue_failed"
    assert body["current_step"] == "enqueue"
    assert body["celery_task_id"] is None
    assert body["error_code"] == "ProjectSetupQueueError"
    assert body["error_summary"] == "project setup failed"
    assert "token" not in body["error_summary"]
    assert "https://" not in body["error_summary"]

    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        lambda **facts: cast(str, facts["task_id"]),
    )
    async with db_session.get_session_factory()() as session:
        task_id = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            session,
            project_id=run.project_id,
            guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id,
            setup_run_id=run.id,
            setup_generation=run.setup_generation,
        )
    expected_task_id = project_setup_identity.project_guide_compilation_task_id(
        run.id, run.setup_generation
    )
    assert task_id == expected_task_id
    async with db_session.get_session_factory()() as session:
        recovered = await session.get(ProjectSetupRun, run.id)
        assert recovered is not None
        assert recovered.status == "queued"
        assert recovered.celery_task_id == expected_task_id
        assert recovered.error_code is None


async def test_dispatch_pending_republishes_only_after_stale_cutoff(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    project = await create_project(project_client)
    guide = await create_guide(
        project_client,
        project["id"],
        {**complete_guide_payload(), "documents": complete_guide_payload()["documents"]},
    )
    published: list[str | None] = []

    def capture_enqueue(**facts: object) -> str:
        published.append(cast(str | None, facts["task_id"]))
        return cast(str, facts["task_id"])

    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        capture_enqueue,
    )
    async with db_session.get_session_factory()() as session:
        run = await session.scalar(
            select(ProjectSetupRun).where(ProjectSetupRun.guide_id == guide["id"])
        )
        assert run is not None
        run.status = "dispatch_pending"
        run.celery_task_id = project_setup_identity.project_guide_compilation_task_id(
            run.id, run.setup_generation
        )
        run.updated_at = datetime.now(UTC)
        await session.commit()
        fresh = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            session,
            project_id=run.project_id,
            guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id,
            setup_run_id=run.id,
            setup_generation=run.setup_generation,
        )
        assert fresh == run.celery_task_id
        assert published == []
        stale_updated_at = datetime.now(UTC) - timedelta(seconds=61)
        run.updated_at = stale_updated_at
        await session.commit()
        stale = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            session,
            project_id=run.project_id,
            guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id,
            setup_run_id=run.id,
            setup_generation=run.setup_generation,
        )
    assert stale == run.celery_task_id
    assert published == [run.celery_task_id]
    async with db_session.get_session_factory()() as session:
        reclaimed = await session.get(ProjectSetupRun, run.id)
        assert reclaimed is not None
        assert reclaimed.updated_at > stale_updated_at


@pytest.mark.asyncio
async def test_project_setup_worker_unexpected_error_does_not_leak_raw_exception(
    monkeypatch,
) -> None:
    from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDelivery
    from app.workers import project_setup as worker

    delivery = ProjectGuideCompilationDelivery(
        project_id=uuid4(),
        guide_id=uuid4(),
        source_snapshot_id=uuid4(),
        setup_run_id=uuid4(),
        setup_generation=1,
        task_id=uuid4(),
    )
    disposed = []

    class Engine:
        async def dispose(self):
            disposed.append(True)

    class Coordinator:
        async def run(self, received):
            assert received == delivery
            raise RuntimeError("raw-token=secret at /srv/private/guide.md")

    monkeypatch.setattr(worker, "create_async_engine", lambda *args, **kwargs: Engine())
    monkeypatch.setattr(worker, "async_sessionmaker", lambda *args, **kwargs: object())
    monkeypatch.setattr(worker, "_coordinator", lambda factory: Coordinator())
    logs = []
    monkeypatch.setattr(
        worker.logger, "warning", lambda message, **kwargs: logs.append((message, kwargs))
    )
    outcome = await worker._run_project_guide_compilation(delivery)
    assert outcome == {
        "status": "compilation_unavailable",
        "error_code": "project_guide_compilation_unavailable",
    }
    assert disposed == [True]
    assert logs == [
        (
            "project guide compilation stopped",
            {"extra": {"setup_run_id": str(delivery.setup_run_id)}},
        )
    ]
    serialized = json.dumps([outcome, logs])
    assert all(value not in serialized for value in ["raw-token", "secret", "/srv/private"])


async def test_project_setup_visibility_apis_require_active_local_grant(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    project = await create_project(project_client)
    other_project = await create_project(project_client, name="Wrong Scope")
    await add_project_manager_admin_grant(project["id"])
    await revoke_system_project_manager_for_default_actor()
    guide = await create_guide(
        project_client,
        project["id"],
        {
            **complete_guide_payload(),
            "documents": complete_guide_payload()["documents"],
        },
    )
    setup_run_response = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/setup-runs/latest",
        headers=auth_headers(),
    )
    assert setup_run_response.status_code == 200, setup_run_response.text
    setup_run = setup_run_response.json()
    diagnostic = await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        setup_run["source_snapshot_id"],
    )
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        setup_run["source_snapshot_id"],
    )
    verified_report_id = await create_compiled_report_fixture(
        diagnostic["id"], setup_run["source_snapshot_id"]
    )
    setup_run["output_sufficiency_report_id"] = verified_report_id
    setup_run["output_submission_artifact_policy_id"] = policy["id"]

    endpoints = [
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/setup-runs/latest",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports/"
        f"{setup_run['output_sufficiency_report_id']}",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{setup_run['output_submission_artifact_policy_id']}",
    ]
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "admin")
    get_settings.cache_clear()
    admin_responses = [
        await project_client.get(endpoint, headers=auth_headers()) for endpoint in endpoints
    ]
    assert [response.status_code for response in admin_responses] == [200] * len(endpoints)

    async with db_session.get_session_factory()() as session:
        grant = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.role == "project_manager",
                AdminRoleGrant.scope_project_id == project["id"],
                AdminRoleGrant.status == "active",
            )
        )
        assert grant is not None
        grant.status = "revoked"
        grant.version = 2
        grant.revoked_by_actor_profile_id = grant.target_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "AUTH-11C1 revocation proof"
        grant.revoked_at = datetime.now(UTC)
        await session.commit()

    denied = [await project_client.get(endpoint, headers=auth_headers()) for endpoint in endpoints]
    assert [response.status_code for response in denied] == [404] * len(endpoints)

    wrong_scope_grant = await add_local_admin_role_for_default_actor(
        "project_manager", project_id=other_project["id"]
    )
    wrong_scope = [
        await project_client.get(endpoint, headers=auth_headers()) for endpoint in endpoints
    ]
    assert [response.status_code for response in wrong_scope] == [404] * len(endpoints)
    await revoke_local_admin_role(wrong_scope_grant)

    operator_grant = await add_local_admin_role_for_default_actor("operator", project_id=None)
    operator = [
        await project_client.get(endpoint, headers=auth_headers()) for endpoint in endpoints
    ]
    assert [response.status_code for response in operator] == [200] * len(endpoints)
    await revoke_local_admin_role(operator_grant)

    audit_grant = await add_local_admin_role_for_default_actor(
        "audit_authority", project_id=project["id"]
    )
    audit = [await project_client.get(endpoint, headers=auth_headers()) for endpoint in endpoints]
    assert [response.status_code for response in audit] == [200] * len(endpoints)
    await revoke_local_admin_role(audit_grant)

    await add_local_admin_role_for_default_actor("finance_authority", project_id=project["id"])
    finance = [await project_client.get(endpoint, headers=auth_headers()) for endpoint in endpoints]
    assert [response.status_code for response in finance] == [404] * len(endpoints)


async def test_project_can_be_created(project_client: AsyncClient) -> None:
    project = await create_project(project_client)

    assert project["name"] == "STEM Eval"
    assert project["status"] == "draft"
    assert "base_amount" not in project
    assert "currency" not in project


async def test_project_create_rejects_payment_fields(project_client: AsyncClient) -> None:
    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": "Payment Field Project",
            "slug": "payment-field-project",
            "description": "Payment belongs to PaymentPolicy.",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 422
    assert "base_amount" in response.text
    assert "currency" in response.text


async def test_draft_guide_can_be_created(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    assert guide["version"] == "v1"
    assert guide["status"] == "draft"
    assert guide["created_by"]
    assert guide["approved_by"] is None
    assert guide["effective_at"] is None
    assert set(guide).issuperset(
        {
            "id",
            "project_id",
            "version",
            "status",
            "created_by",
            "approved_by",
            "effective_at",
        }
    )


async def test_duplicate_guide_version_returns_conflict(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    await create_guide(project_client, project["id"], complete_guide_payload("v1"))

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v1"),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "guide version already exists for project"


async def test_removed_sufficiency_agent_route_has_no_effects(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    async with db_session.get_session_factory()() as session:
        before = await session.scalar(select(func.count()).select_from(AuditEvent))
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots/"
        f"{snapshot['id']}/run-sufficiency-agent",
        headers=auth_headers(),
    )

    assert response.status_code == 404
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == before
        for table in [
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == 0


async def test_project_guide_rejects_unknown_non_contract_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["machine_policy_schema"] = {"required": ["log"]}
    payload["guide_setup_checklist"] = ["title"]
    payload["approved_by"] = "project-manager-subject"
    payload["effective_at"] = "2026-07-05T00:00:00Z"

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    for field in (
        "machine_policy_schema",
        "guide_setup_checklist",
        "approved_by",
        "effective_at",
    ):
        assert field in response.text


async def test_project_guide_update_rejects_unknown_non_contract_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    payload = {"guide_setup_checklist": ["summary"]}

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "guide_setup_checklist" in response.text



async def test_guide_documents_requires_at_least_one_uploaded_source_item(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={**complete_guide_payload(), "documents": []},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "documents"]


async def test_guide_documents_rejects_unsafe_refs(project_client: AsyncClient) -> None:
    project = await create_project(project_client)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={**complete_guide_payload(), "documents": [{"label": "https://docs.flow.test/guide.md?X-Amz-Signature=secret", "media_type": "application/pdf"}]},
    )

    assert response.status_code == 422
    assert "locator or credential material" in response.json()["detail"]


@pytest.mark.parametrize(
    "source_label",
    [
        "secretary-guide.pdf",
        "tokenizer-spec.md",
        "credentialing-guide.md",
    ],
)
async def test_guide_documents_allows_non_secret_keyword_prefixes(
    project_client: AsyncClient,
    source_label: str,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], {**complete_guide_payload(), "documents": [{"label": source_label, "media_type": "application/pdf"}]})

    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    assert source_label in {item["source_label"] for item in snapshot["items"]}


@pytest.mark.parametrize(
    "source_label",
    [
        "https://user:pass@docs.flow.test/guide.md",
        "s3://workstream-guides/token/guide.md",
        "file:///home/abiorh/guide.md",
        "inline:/../guide.md",
        "inline:C:/Users/alice/guide.md",
        "inline:C:\\Users\\alice\\guide.md",
        "import:\\\\server\\share\\guide.md",
        "import://server/share/guide.md",
        "inline://server/share/guide.md",
        "repo://server/share/guide.md",
        "import:////server/share/guide.md",
        "inline:////server/share/guide.md",
        "repo:////server/share/guide.md",
        "inline:~/guide.md",
        "repo:~/guide.md",
        "import:~/guide.md",
        "s3://workstream-guides/%74oken/guide.md",
        "s3://workstream-guides/%63redential/guide.md",
        "s3://workstream-guides/%70assword/guide.md",
        "s3://workstream-guides/%2574oken/guide.md",
        "https://docs.flow.test/.env",
        "https://docs.flow.test/%252Eenv",
        "https://docs.flow.test/config.env",
        "https://docs.flow.test/outputs/prod.env",
        "https://docs.flow.test/keys/id_rsa",
        "https://docs.flow.test/keys/deploy.pem",
        "https://docs.flow.test/.npmrc.bak",
        "https://docs.flow.test/.pypirc.old",
        "s3://bucket/private/key.pem",
        "s3://bucket/access/key/guide.md",
        "s3://bucket/api/key/guide.md",
        "s3://bucket/private/key/guide.md",
        "https://docs.flow.test/guide.md%253Ftoken%253Dsecret",
        "inline:%2Fhome%2Fabiorh%2Fguide.md",
        "repo:%2Ftmp%2Fguide.md",
        "import:%2E%2E/guide.md",
        "inline:%5CUsers%5Calice%5Cguide.md",
        "https://docs.flow.test/guide.md;v=2",
        "https://docs.flow.test/a;b/guide.md",
        "https://docs.flow.test/a%3Bb/guide.md",
        "https://docs.flow.test/a%253Bb/guide.md",
        "inline:/workspace/guide.md",
        "repo:/srv/repos/private/guide.md",
        "import:/opt/workstream/guide.md",
        "inline:/mnt/material/guide.md",
    ],
)
async def test_guide_documents_rejects_credential_and_local_refs(
    project_client: AsyncClient,
    source_label: str,
) -> None:
    project = await create_project(project_client)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={**complete_guide_payload(), "documents": [{"label": source_label, "media_type": "application/pdf"}]},
    )

    assert response.status_code == 422
    assert "locator or credential material" in response.json()["detail"]


async def test_guide_documents_rejects_unsafe_content_cid(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["documents"][0]["content_cid"] = "https://storage.flow.test/doc?token=secret"

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "extra" in response.text


async def test_guide_documents_rejects_duplicate_source_items(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["documents"][1]["label"] = payload["documents"][0]["label"]

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "duplicate source item" in response.json()["detail"]


async def test_guide_documents_rejects_unknown_request_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    top_level_payload = {**complete_guide_payload(), "client_note": "not allowed"}
    item_payload = complete_guide_payload()
    item_payload["documents"][0]["signed_url"] = "not allowed"

    top_level_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=top_level_payload,
    )
    item_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=item_payload,
    )

    assert top_level_response.status_code == 422
    assert item_response.status_code == 422
    assert "extra" in top_level_response.text
    assert "extra" in item_response.text


async def test_guide_documents_rejects_oversized_source_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["documents"][0]["label"] = "a" * 501

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "max_length" in response.text


async def test_sufficiency_report_rejects_snapshot_manifest_hash_drift(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(GuideSourceSnapshot, snapshot["id"])
        assert persisted is not None
        persisted.manifest_json = {**persisted.manifest_json, "tampered": True}
        with pytest.raises(IntegrityError, match="source snapshot content is immutable"):
            await session.commit()


async def test_submission_policy_rejects_snapshot_item_drift(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    async with db_session.get_session_factory()() as session:
        item = await session.scalar(
            select(GuideSourceSnapshotItem)
            .where(GuideSourceSnapshotItem.source_snapshot_id == snapshot["id"])
            .order_by(GuideSourceSnapshotItem.item_order)
        )
        assert item is not None
        item.source_label = "tampered-source-item"
        with pytest.raises(IntegrityError, match="snapshot items are immutable"):
            await session.commit()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="items do not match manifest"):
            await session.execute(
                text(
                    "insert into guide_source_snapshot_items "
                    "(id,source_snapshot_id,item_order,source_kind,source_label,"
                    "ingestion_adapter,media_type) "
                    "values (:id,:snapshot_id,999,'external_document',"
                    "'appended','manual','text/plain')"
                ),
                {
                    "id": str(uuid4()),
                    "snapshot_id": snapshot["id"],
                },
            )
            await session.commit()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="snapshot items are immutable"):
            await session.execute(text("truncate guide_source_snapshot_items cascade"))

    async with db_session.get_session_factory()() as session:
        item = await session.scalar(
            select(GuideSourceSnapshotItem).where(
                GuideSourceSnapshotItem.source_snapshot_id == snapshot["id"]
            )
        )
        assert item is not None
        await session.delete(item)
        with pytest.raises(IntegrityError, match="snapshot items are immutable"):
            await session.commit()




async def test_sufficiency_report_rejects_unknown_request_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    top_level_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "status": "passed",
            "findings": [],
            "summary": "Guide reviewed.",
            "raw_agent_output": "not allowed",
        },
    )
    finding_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "status": "passed_with_warnings",
            "findings": [
                {
                    "severity": "warning",
                    "code": "thin_examples",
                    "message": "Examples are thin.",
                    "prompt": "not allowed",
                }
            ],
        },
    )

    assert top_level_response.status_code == 422
    assert finding_response.status_code == 422
    assert "extra" in top_level_response.text
    assert "extra" in finding_response.text


@pytest.mark.parametrize(
    ("status", "findings", "expected_detail"),
    [
        ("blocked", [], "blocking gap findings"),
        ("passed_with_warnings", [], "warning findings"),
    ],
)
async def test_sufficiency_report_status_requires_matching_findings(
    project_client: AsyncClient,
    status: str,
    findings: list[dict],
    expected_detail: str,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "status": status,
            "findings": findings,
            "summary": "Guide reviewed.",
        },
    )

    assert response.status_code == 422
    assert expected_detail in response.json()["detail"]


async def test_manual_sufficiency_report_rejects_agent_provenance_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    rejected = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "status": "passed",
            "findings": [],
            "summary": "Manual sufficiency assessment.",
            "agent_name": "ProjectGuideSufficiencyAgent",
        },
    )

    assert rejected.status_code == 422
    assert rejected.json()["detail"][0]["loc"] == ["body", "agent_name"]

    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "status": "passed",
            "findings": [],
            "summary": "Manual sufficiency assessment.",
        },
    )

    assert created.status_code == 201, created.text


async def test_manual_sufficiency_report_exact_replay_reauthorizes_and_mismatch_conflicts(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    endpoint = f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports"
    headers = auth_headers()
    payload = {
        "source_snapshot_id": snapshot["id"],
        "status": "passed",
        "findings": [],
        "summary": "Manual sufficiency assessment.",
    }

    created = await project_client.post(endpoint, headers=headers, json=payload)
    replayed = await project_client.post(endpoint, headers=headers, json=payload)
    duplicate = await project_client.post(endpoint, headers=auth_headers(), json=payload)
    mismatch = await project_client.post(
        endpoint,
        headers=headers,
        json={**payload, "summary": "Changed assessment."},
    )

    assert created.status_code == 201, created.text
    assert replayed.status_code == 201, replayed.text
    assert replayed.json()["id"] == created.json()["id"]
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "sufficiency_report_already_exists"
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"] == "idempotency_mismatch"
    async with db_session.get_session_factory()() as session:
        reports = (
            await session.scalars(
                select(GuideSufficiencyReport).where(
                    GuideSufficiencyReport.source_snapshot_id == snapshot["id"]
                )
            )
        ).all()
    assert len(reports) == 1
    assert reports[0].creation_action_id == "project.guide_sufficiency_report.create"
    assert reports[0].created_by_actor_profile_id is not None
    assert reports[0].created_via_identity_link_id is not None
    assert reports[0].authorization_decision_event_id is not None
    assert created.json()["agent_name"] is None
    assert created.json()["agent_version"] is None


async def test_submission_artifact_policy_replay_postgres_converges_exact_reservations(
    isolated_database_env: str,
) -> None:
    """The real partial index makes concurrent exact human reservations converge."""
    engine = create_async_engine(isolated_database_env)
    ids = {name: str(uuid4()) for name in ("actor", "link", "project", "guide", "snapshot")}
    snapshot = guide_snapshot_columns(ids["snapshot"])
    digest = snapshot["bundle_hash"]
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table projects disable trigger project_creation_custody")
            )
            await connection.execute(
                text(
                    "insert into projects(id,name,slug,status) values("
                    ":project,'Replay project',:slug,'draft')"
                ),
                {**ids, "slug": f"replay-{ids['project']}"},
            )
            await connection.execute(
                text("alter table projects enable trigger project_creation_custody")
            )
            await connection.execute(
                text(
                    "insert into actor_profiles(id,actor_kind,status,provisioning_method,"
                    "created_by) values(:actor,'human','active','automatic_first_access',:actor)"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links(id,actor_profile_id,issuer,subject,"
                    "subject_kind,status,linked_by,last_verified_at) values(:link,:actor,"
                    "'https://identity.test',:actor,'human','active',:actor,clock_timestamp())"
                ),
                ids,
            )
            for table, trigger in GUIDE_CREATION_CUSTODY_TRIGGERS:
                await connection.execute(text(f"alter table {table} disable trigger {trigger}"))
            await seed_guide_snapshot_rows(connection, project_id=ids["project"], guide_id=ids["guide"],
                                          version="v1", snapshot_id=ids["snapshot"])
            for table, trigger in GUIDE_CREATION_CUSTODY_TRIGGERS:
                await connection.execute(text(f"alter table {table} enable trigger {trigger}"))

        operation_id, policy_id, key = uuid4(), str(uuid4()), uuid4()
        values = {
            "actor_profile_id": ids["actor"],
            "identity_link_id": ids["link"],
            "action_id": ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE.value,
            "idempotency_key": key,
            "request_digest": digest,
            "resource_context_digest": digest,
            "resource_context_json": {"guide_version": "v1"},
            "operation_id": operation_id,
            "project_id": ids["project"],
            "guide_id": ids["guide"],
            "source_snapshot_id": ids["snapshot"],
            "policy_id": policy_id,
            "setup_generation": 1,
        }
        factory = async_sessionmaker(engine, expire_on_commit=False)
        first = factory()
        await first.begin()
        first_result = await SubmissionPolicyMutationReplayRepository(first).reserve(**values)
        assert first_result[0] == "claimed"

        async def reserve_second():
            async with factory() as second:
                async with second.begin():
                    return await SubmissionPolicyMutationReplayRepository(second).reserve(**values)

        competing = asyncio.create_task(reserve_second())
        async with engine.connect() as observer:
            for _ in range(200):
                waiting = await observer.scalar(
                    text(
                        "select count(*) from pg_stat_activity where "
                        "wait_event_type='Lock' and state='active' and "
                        "query ilike '%submission_policy_mutation_idempotency_records%'"
                    )
                )
                if waiting:
                    break
                await asyncio.sleep(0.05)
            else:
                raise AssertionError("competing reservation never blocked")
        await first.commit()
        second_result = await asyncio.wait_for(competing, timeout=5)
        assert second_result[0] == "pending"
        assert second_result[1].operation_id == operation_id
        await first.close()
    finally:
        await engine.dispose()


async def test_source_snapshot_manifest_rejects_caller_storage_references(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    async with db_session.get_session_factory()() as session:
        persisted = await session.get(GuideSourceSnapshot, snapshot["id"])
        assert persisted is not None
        manifest = json.loads(json.dumps(persisted.manifest_json))
        for item in manifest["items"]:
            item["durable_ref"] = "caller-owned://untrusted-source"
            item["content_hash"] = "sha256:" + ("0" * 64)
        with pytest.raises(IntegrityError):
            await session.execute(
                update(GuideSourceSnapshot)
                .where(GuideSourceSnapshot.id == snapshot["id"])
                .values(manifest_json=manifest, bundle_hash=canonical_json_hash(manifest))
            )
            await session.commit()
        await session.rollback()


def test_project_agent_timeout_is_loaded_from_environment(monkeypatch) -> None:
    from app.core.project_agents import project_guide_runtime_configuration

    monkeypatch.setenv("WORKSTREAM_PROJECT_AGENT_MODEL", "test-model")
    monkeypatch.setenv("WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS", "42")
    monkeypatch.setenv("WORKSTREAM_PROJECT_AGENT_MAX_MANIFEST_BYTES", "12345")
    get_settings.cache_clear()
    try:
        configuration = project_guide_runtime_configuration(get_settings())
        assert configuration.timeout_seconds == 42
        assert configuration.maximum_manifest_bytes == 12345
        assert configuration.model == "test-model"
    finally:
        get_settings.cache_clear()


async def test_manual_submission_artifact_policy_rejects_agent_provenance_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    create_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(),
            "derivation_source": "agent_derivation",
        },
    )

    assert create_response.status_code == 422
    assert create_response.json()["detail"][0]["loc"] == ["body", "derivation_source"]

    reserved_version_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "agent-aaaaaaaaaaaaaaaaaaaaaaaa",
            "policy_body": project_submission_artifact_policy_body(),
        },
    )

    assert reserved_version_response.status_code == 422
    assert reserved_version_response.json()["detail"][0]["loc"] == ["body", "policy_version"]

    reserved_case_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "Agent-aaaaaaaaaaaaaaaaaaaaaaaa",
            "policy_body": project_submission_artifact_policy_body(),
        },
    )

    assert reserved_case_response.status_code == 422
    assert reserved_case_response.json()["detail"][0]["loc"] == ["body", "policy_version"]

    padded_version_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": " v1 ",
            "policy_body": project_submission_artifact_policy_body(),
        },
    )

    assert padded_version_response.status_code == 422
    assert padded_version_response.json()["detail"][0]["loc"] == ["body", "policy_version"]

    await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )

    update_response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=auth_headers(),
        json={
            "expected_policy_hash": policy["policy_hash"],
            "successor_policy_version": "v2",
            "derivation_agent_name": "SubmissionArtifactPolicyDerivationAgent",
        },
    )

    assert update_response.status_code == 422
    assert update_response.json()["detail"][0]["loc"] == ["body", "derivation_agent_name"]


async def test_agent_derived_policy_approval_revalidates_server_owned_provenance(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    spoofed_policy = SubmissionArtifactPolicy(
        id=str(uuid4()),
        project_id=project["id"],
        guide_id=guide["id"],
        guide_version=guide["version"],
        source_snapshot_id=snapshot["id"],
        source_snapshot_hash=snapshot["bundle_hash"],
        policy_version=f"agent-{snapshot['bundle_hash'].removeprefix('sha256:')[:24]}",
        lifecycle_status="draft",
        policy_body=project_submission_artifact_policy_body(),
        policy_hash=canonical_json_hash(project_submission_artifact_policy_body()),
        derivation_source="agent_derivation",
        source_material_refs=[],
        derivation_agent_name="ProviderControlledAgent",
        derivation_agent_version="provider-v0",
        created_by="seeded-actor",
    )
    async with db_session.get_session_factory()() as session:
        session.add(spoofed_policy)
        await session.commit()

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{spoofed_policy.id}/approve",
        headers=auth_headers(),
        json={"approval_note": "Should revalidate agent provenance."},
    )

    assert response.status_code == 422
    assert "manual policy lineage is required" in response.json()["detail"]
    async with db_session.get_session_factory()() as session:
        assert (await session.get(SubmissionArtifactPolicy, spoofed_policy.id)).lifecycle_status == "draft"


async def test_submission_artifact_policy_removed_agent_route_performs_no_runtime_calls(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    endpoint = (
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots/"
        f"{snapshot['id']}/derive-submission-artifact-policy"
    )

    first, second = await asyncio.gather(
        project_client.post(endpoint, headers=auth_headers()),
        project_client.post(endpoint, headers=auth_headers()),
    )

    assert first.status_code == 404
    assert second.status_code == 404
    async with db_session.get_session_factory()() as session:
        policies = (
            await session.scalars(
                select(SubmissionArtifactPolicy).where(
                    SubmissionArtifactPolicy.source_snapshot_id == snapshot["id"],
                    SubmissionArtifactPolicy.derivation_source == "agent_derivation",
                    SubmissionArtifactPolicy.lifecycle_status.in_(["draft", "approved"]),
                )
            )
        ).all()

    assert policies == []


async def test_submission_artifact_policy_approval_persists_effective_policy_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )

    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    assert policy["lifecycle_status"] == "draft"
    assert policy["policy_hash"].startswith("sha256:")
    assert effective["source_snapshot_id"] == snapshot["id"]
    assert effective["source_snapshot_hash"] == snapshot["bundle_hash"]
    assert effective["submission_artifact_policy_hash"] == policy["policy_hash"]
    assert effective["effective_policy_hash"].startswith("sha256:")
    assert effective["effective_policy"]["artifact_hash_algorithm"] == "sha256"

    async with db_session.get_session_factory()() as session:
        persisted_policy = await session.get(SubmissionArtifactPolicy, policy["id"])
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective["id"]
            )
        )

    assert persisted_policy is not None
    assert persisted_policy.lifecycle_status == "approved"
    assert persisted_policy.approved_by_role == "project_manager"
    assert persisted_policy.approved_by_actor == policy["created_by"]
    assert persisted_policy.approved_at is not None
    assert persisted_policy.derivation_source == "manual_admin_derivation"
    assert len(persisted_policy.source_material_refs) == len(snapshot["items"])
    assert all(
        ref.startswith("guide-document:") and "#sha256:" in ref
        for ref in persisted_policy.source_material_refs
    )
    assert pre_submit_checker_policy is not None
    assert pre_submit_checker_policy.lifecycle_status == "compiled"
    assert pre_submit_checker_policy.effective_policy_hash == effective["effective_policy_hash"]
    assert pre_submit_checker_policy.compiler_version == "workstream-pre-submit-compiler-v0.1"
    assert pre_submit_checker_policy.compiled_bundle_hash is not None
    assert (
        pre_submit_checker_policy.compiled_bundle["effective_policy_hash"]
        == (effective["effective_policy_hash"])
    )
    assert "require_file" in pre_submit_checker_policy.checker_configs


async def test_submission_artifact_policy_approval_rejects_body_hash_mismatch(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    async with db_session.get_session_factory()() as session:
        persisted = await session.get(SubmissionArtifactPolicy, policy["id"])
        assert persisted is not None
        persisted.policy_body = {
            **persisted.policy_body,
            "allowed_storage_schemes": ["local"],
        }
        await session.commit()

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "Hash mismatch must be rejected."},
    )

    assert response.status_code == 422
    assert "submission artifact policy body hash mismatch" in response.json()["detail"]


async def test_approved_submission_artifact_policy_cannot_be_updated(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
        f"submission-artifact-policies/{policy['id']}",
        headers=auth_headers(),
        json={
            "expected_policy_hash": policy["policy_hash"],
            "successor_policy_version": "v2",
            "change_summary": "Attempt to mutate approved policy.",
        },
    )

    assert response.status_code == 409
    assert "immutable" in response.json()["detail"]


async def test_submission_artifact_policy_creation_requires_sufficiency_report(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(),
            "change_summary": "Should require sufficiency first.",
        },
    )

    assert response.status_code == 422
    assert "sufficiency report is required" in response.json()["detail"]


async def test_submission_artifact_policy_create_rejects_diagnostic_only_sufficiency(
    project_client: AsyncClient,
) -> None:
    """A human diagnostic report cannot substitute for setup-owned sufficiency."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "manual-v1",
            "policy_body": project_submission_artifact_policy_body(),
        },
    )
    assert response.status_code == 422
    assert "authoritative guide sufficiency report is required" in response.json()["detail"]


async def test_submission_artifact_policy_create_rejects_unacknowledged_warning_lineage(
    project_client: AsyncClient,
) -> None:
    """An authoritative warning result without exact 12E acknowledgement cannot create policy."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    diagnostic = await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        status="passed_with_warnings",
    )
    await create_compiled_report_fixture(diagnostic["id"], snapshot["id"])
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "manual-v1",
            "policy_body": project_submission_artifact_policy_body(),
        },
    )
    assert response.status_code == 422
    assert "authorized Project Manager acknowledgement" in response.json()["detail"]


async def test_submission_artifact_policy_create_exact_idempotency_replay_is_stable(
    project_client: AsyncClient,
) -> None:
    """Exact create replay returns the committed response and creates one row."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    diagnostic = await create_sufficiency_report(
        project_client, project["id"], guide["id"], snapshot["id"]
    )
    await create_compiled_report_fixture(diagnostic["id"], snapshot["id"])
    headers = auth_headers()
    payload = {
        "source_snapshot_id": snapshot["id"],
        "policy_version": "manual-v1",
        "policy_body": project_submission_artifact_policy_body(),
        "change_summary": "stable replay",
    }
    path = f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies"
    first = await project_client.post(path, headers=headers, json=payload)
    replay = await project_client.post(path, headers=headers, json=payload)
    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()
    async with db_session.get_session_factory()() as session:
        count = await session.scalar(
            select(func.count(SubmissionArtifactPolicy.id)).where(
                SubmissionArtifactPolicy.project_id == project["id"],
                SubmissionArtifactPolicy.guide_id == guide["id"],
            )
        )
    assert count == 1


@pytest.mark.parametrize(
    "fault_point",
    ["replay_reserved", "policy_staged", "evidence_staged", "replay_completed"],
)
async def test_submission_artifact_policy_create_fault_rolls_back_atomic_boundary(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    fault_point: str,
) -> None:
    """Every named post-authorization fault leaves no policy, replay, or allow evidence."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    diagnostic = await create_sufficiency_report(
        project_client, project["id"], guide["id"], snapshot["id"]
    )
    await create_compiled_report_fixture(diagnostic["id"], snapshot["id"])

    if fault_point == "replay_reserved":
        original = SubmissionPolicyMutationService.reserve_replay

        async def fail_after_reservation(self, facts):
            await original(self, facts)
            raise RuntimeError("fault after replay reservation")

        monkeypatch.setattr(
            SubmissionPolicyMutationService, "reserve_replay", fail_after_reservation
        )
    elif fault_point == "policy_staged":
        original_add = ProjectRepository.add_submission_artifact_policy

        async def fail_after_policy_staging(self, policy):
            await original_add(self, policy)
            raise RuntimeError("fault after policy staging")

        monkeypatch.setattr(
            ProjectRepository, "add_submission_artifact_policy", fail_after_policy_staging
        )
    elif fault_point == "evidence_staged":
        original_consume = PreparedAuthorizationService.consume
        consume_count = 0

        async def fail_after_final_evidence(self, *args, **kwargs):
            nonlocal consume_count
            decision = await original_consume(self, *args, **kwargs)
            consume_count += 1
            if consume_count == 1:
                raise RuntimeError("fault after authorization evidence staging")
            return decision

        monkeypatch.setattr(PreparedAuthorizationService, "consume", fail_after_final_evidence)
    else:
        original_complete = SubmissionPolicyMutationService.complete_replay

        async def fail_after_replay_completion(self, *args, **kwargs):
            await original_complete(self, *args, **kwargs)
            raise RuntimeError("fault after replay completion")

        monkeypatch.setattr(
            SubmissionPolicyMutationService, "complete_replay", fail_after_replay_completion
        )

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "manual-v1",
            "policy_body": project_submission_artifact_policy_body(),
        },
    )
    assert response.status_code == 500

    async with db_session.get_session_factory()() as session:
        policy_count = await session.scalar(
            select(func.count())
            .select_from(SubmissionArtifactPolicy)
            .where(
                SubmissionArtifactPolicy.project_id == project["id"],
                SubmissionArtifactPolicy.guide_id == guide["id"],
            )
        )
        replay_count = await session.scalar(
            select(func.count())
            .select_from(SubmissionPolicyMutationIdempotencyRecord)
            .where(
                SubmissionPolicyMutationIdempotencyRecord.project_id == project["id"],
                SubmissionPolicyMutationIdempotencyRecord.guide_id == guide["id"],
            )
        )
        allowed_count = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action_id == ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE.value,
                AuditEvent.event_type == "SensitiveAuthorizationAllowed",
                AuditEvent.target_ref_id == project["id"],
            )
        )

    assert policy_count == replay_count == allowed_count == 0


async def test_database_enforces_effective_policy_submission_policy_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(EffectiveProjectSubmissionArtifactPolicy, effective["id"])
        assert persisted is not None
        persisted.submission_artifact_policy_hash = sha256_hash("wrong-submission-policy")
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_database_enforces_pre_submit_checker_effective_policy_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    async with db_session.get_session_factory()() as session:
        persisted = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective["id"]
            )
        )
        assert persisted is not None
        persisted.effective_policy_hash = sha256_hash("wrong-effective-policy")
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_submission_artifact_policy_approval_merges_packaging_rules(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=project_submission_artifact_policy_body(
            packaging={
                "package_required": True,
                "allowed_package_formats": ["zip", "tar"],
            }
        ),
    )

    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    assert effective["effective_policy"]["packaging"] == {
        "package_required": True,
        "allowed_package_formats": ["tar", "zip"],
    }
    assert "workstream_default" not in effective["effective_policy"]["packaging"]
    assert "project" not in effective["effective_policy"]["packaging"]


async def test_approved_submission_artifact_policy_is_immutable(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    await approve_submission_artifact_policy(
        project_client, project["id"], guide["id"], policy["id"]
    )

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=auth_headers(),
        json={
            "expected_policy_hash": policy["policy_hash"],
            "successor_policy_version": "v2",
            "change_summary": "Try to mutate approved policy.",
        },
    )

    assert response.status_code == 409
    assert "immutable" in response.json()["detail"]


async def test_draft_submission_artifact_policy_can_be_updated(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )

    update_headers = auth_headers()
    update_payload = {
        "expected_policy_hash": policy["policy_hash"],
        "successor_policy_version": "v2",
        "policy_body": project_submission_artifact_policy_body(
            artifact_path="outputs/final-answer.md"
        ),
        "change_summary": "Use final answer artifact path.",
    }
    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=update_headers,
        json=update_payload,
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] != policy["id"]
    assert updated["supersedes_policy_id"] == policy["id"]
    assert updated["lifecycle_status"] == "draft"
    assert updated["policy_hash"] != policy["policy_hash"]
    assert updated["policy_body"]["required_artifacts"][0]["path"] == ("outputs/final-answer.md")
    assert updated["change_summary"] == "Use final answer artifact path."
    replay = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=update_headers,
        json=update_payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == updated
    async with db_session.get_session_factory()() as session:
        predecessor = await session.get(SubmissionArtifactPolicy, policy["id"])
        assert predecessor is not None
        assert predecessor.lifecycle_status == "superseded"
        assert predecessor.policy_hash == policy["policy_hash"]


async def test_submission_artifact_policy_update_rejects_stale_cas_without_successor(
    project_client: AsyncClient,
) -> None:
    """A stale predecessor digest creates no replacement or supersession."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client, project["id"], guide["id"], snapshot["id"]
    )
    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=auth_headers(),
        json={
            "expected_policy_hash": sha256_hash("stale"),
            "successor_policy_version": "v2",
            "change_summary": "must not commit",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "submission_policy_precondition_failed"
    async with db_session.get_session_factory()() as session:
        rows = list(
            (
                await session.scalars(
                    select(SubmissionArtifactPolicy).where(
                        SubmissionArtifactPolicy.project_id == project["id"],
                        SubmissionArtifactPolicy.guide_id == guide["id"],
                    )
                )
            ).all()
        )
    assert len(rows) == 1
    assert rows[0].lifecycle_status == "draft"


async def test_submission_artifact_policy_update_conceals_foreign_policy_id(
    project_client: AsyncClient,
) -> None:
    """A policy selected through another project or guide is indistinguishable from absent."""
    first_project = await create_project(project_client)
    first_guide = await create_guide(project_client, first_project["id"], complete_guide_payload())
    first_snapshot = await read_guide_source_snapshot(first_project["id"], first_guide["id"])
    await create_sufficiency_report(
        project_client, first_project["id"], first_guide["id"], first_snapshot["id"]
    )
    foreign_policy = await create_submission_artifact_policy(
        project_client, first_project["id"], first_guide["id"], first_snapshot["id"]
    )

    second_project = await create_project(project_client, name="Foreign Policy Target")
    second_guide = await create_guide(
        project_client, second_project["id"], complete_guide_payload()
    )
    response = await project_client.patch(
        f"/api/v1/projects/{second_project['id']}/guides/{second_guide['id']}/"
        f"submission-artifact-policies/{foreign_policy['id']}",
        headers=auth_headers(),
        json={
            "expected_policy_hash": foreign_policy["policy_hash"],
            "successor_policy_version": "foreign-v2",
            "change_summary": "must remain concealed",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "submission artifact policy not found"


async def test_submission_artifact_policy_update_fault_rolls_back_replacement(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-supersession fault restores the draft and all update boundary state."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client, project["id"], guide["id"], snapshot["id"]
    )
    original_complete = SubmissionPolicyMutationService.complete_replay

    async def fail_after_update_completion(self, *args, **kwargs):
        await original_complete(self, *args, **kwargs)
        raise RuntimeError("fault after update replay completion")

    monkeypatch.setattr(
        SubmissionPolicyMutationService, "complete_replay", fail_after_update_completion
    )
    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
        f"submission-artifact-policies/{policy['id']}",
        headers=auth_headers(),
        json={
            "expected_policy_hash": policy["policy_hash"],
            "successor_policy_version": "v2",
            "change_summary": "must roll back",
        },
    )
    assert response.status_code == 500

    async with db_session.get_session_factory()() as session:
        rows = list(
            (
                await session.scalars(
                    select(SubmissionArtifactPolicy).where(
                        SubmissionArtifactPolicy.project_id == project["id"],
                        SubmissionArtifactPolicy.guide_id == guide["id"],
                    )
                )
            ).all()
        )
        replay_count = await session.scalar(
            select(func.count())
            .select_from(SubmissionPolicyMutationIdempotencyRecord)
            .where(
                SubmissionPolicyMutationIdempotencyRecord.action_id
                == ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE.value,
                SubmissionPolicyMutationIdempotencyRecord.project_id == project["id"],
            )
        )
        allowed_count = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action_id == ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE.value,
                AuditEvent.event_type == "SensitiveAuthorizationAllowed",
                AuditEvent.target_ref_id == project["id"],
            )
        )
    assert len(rows) == 1
    assert rows[0].id == policy["id"]
    assert rows[0].lifecycle_status == "draft"
    assert replay_count == allowed_count == 0


async def test_submission_artifact_policy_update_concurrent_cas_creates_one_successor(
    project_client: AsyncClient,
) -> None:
    """Two replacement attempts against one draft converge on one append-only winner."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client, project["id"], guide["id"], snapshot["id"]
    )
    path = (
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
        f"submission-artifact-policies/{policy['id']}"
    )

    async def replace(version: str):
        return await project_client.patch(
            path,
            headers=auth_headers(),
            json={
                "expected_policy_hash": policy["policy_hash"],
                "successor_policy_version": version,
                "change_summary": version,
            },
        )

    first, second = await asyncio.gather(replace("concurrent-a"), replace("concurrent-b"))
    assert sorted((first.status_code, second.status_code)) == [200, 409]
    async with db_session.get_session_factory()() as session:
        rows = list(
            (
                await session.scalars(
                    select(SubmissionArtifactPolicy).where(
                        SubmissionArtifactPolicy.project_id == project["id"],
                        SubmissionArtifactPolicy.guide_id == guide["id"],
                    )
                )
            ).all()
        )
    assert len(rows) == 2
    assert sum(row.lifecycle_status == "draft" for row in rows) == 1
    assert sum(row.lifecycle_status == "superseded" for row in rows) == 1


async def test_approving_replacement_policy_supersedes_prior_rows(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    first_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v1",
    )
    first_effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        first_policy["id"],
    )
    second_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=project_submission_artifact_policy_body(
            artifact_path="outputs/final-answer.md"
        ),
        policy_version="v2",
    )

    second_effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        second_policy["id"],
    )

    async with db_session.get_session_factory()() as session:
        first_persisted = await session.get(SubmissionArtifactPolicy, first_policy["id"])
        second_persisted = await session.get(SubmissionArtifactPolicy, second_policy["id"])
        first_effective_persisted = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            first_effective["id"],
        )
        second_effective_persisted = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            second_effective["id"],
        )
        pre_submit_rows = (
            await session.scalars(
                select(PreSubmitCheckerPolicy).where(
                    PreSubmitCheckerPolicy.project_id == project["id"],
                    PreSubmitCheckerPolicy.guide_version == guide["version"],
                )
            )
        ).all()
        repo = ProjectRepository(session)
        current_policy = await repo.get_current_approved_submission_artifact_policy(
            project["id"],
            guide["version"],
        )
        current_effective = await repo.get_effective_submission_artifact_policy(
            project["id"],
            guide["version"],
            snapshot["id"],
        )
        current_pre_submit = await repo.get_current_pre_submit_checker_policy(
            project["id"],
            guide["version"],
        )

    assert len(pre_submit_rows) == 2
    assert first_persisted is not None
    assert second_persisted is not None
    assert first_effective_persisted is not None
    assert second_effective_persisted is not None
    assert current_policy is not None
    assert current_effective is not None
    assert current_pre_submit is not None

    assert first_persisted.lifecycle_status == "superseded"
    assert first_persisted.superseded_at is not None
    assert first_persisted.policy_body == first_policy["policy_body"]
    assert first_persisted.policy_hash == first_policy["policy_hash"]
    assert second_persisted.lifecycle_status == "approved"
    assert second_persisted.supersedes_policy_id == first_persisted.id
    assert first_effective_persisted.lifecycle_status == "superseded"
    assert first_effective_persisted.superseded_at is not None
    assert (
        first_effective_persisted.effective_policy_hash == first_effective["effective_policy_hash"]
    )
    assert second_effective_persisted.lifecycle_status == "approved"
    assert second_effective_persisted.supersedes_effective_policy_id == (
        first_effective_persisted.id
    )
    assert {row.lifecycle_status for row in pre_submit_rows} == {
        "compiled",
        "superseded",
    }
    old_pre_submit = next(
        row for row in pre_submit_rows if row.effective_policy_id == first_effective_persisted.id
    )
    assert old_pre_submit.superseded_at is not None
    assert current_pre_submit.effective_policy_id == second_effective_persisted.id
    assert current_pre_submit.supersedes_pre_submit_checker_policy_id == (old_pre_submit.id)
    assert current_policy.id == second_persisted.id
    assert current_effective.id == second_effective_persisted.id


async def test_approving_replacement_policy_with_same_effective_content_succeeds(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy_body = project_submission_artifact_policy_body()
    first_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=policy_body,
        policy_version="v1",
    )
    first_effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        first_policy["id"],
    )
    second_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=policy_body,
        policy_version="v2",
    )

    second_effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        second_policy["id"],
    )

    assert second_effective["effective_policy_hash"] == first_effective["effective_policy_hash"]


async def test_replacement_policy_requires_complete_prior_effective_context(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    first_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v1",
    )
    first_effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        first_policy["id"],
    )
    second_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=project_submission_artifact_policy_body(
            artifact_path="outputs/final-answer.md"
        ),
        policy_version="v2",
    )

    async with db_session.get_session_factory()() as session:
        effective = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            first_effective["id"],
        )
        assert effective is not None
        effective.lifecycle_status = "superseded"
        effective.superseded_at = datetime.now(UTC)
        await session.commit()

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{second_policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "Replacement should fail on incomplete chain."},
    )

    assert response.status_code == 409
    assert (
        "effective project submission artifact policy chain is incomplete"
        in (response.json()["detail"])
    )


async def test_concurrent_policy_approvals_do_not_fork_current_chain(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    first_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v1",
    )
    second_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=project_submission_artifact_policy_body(
            artifact_path="outputs/final-answer.md"
        ),
        policy_version="v2",
    )

    first_response, second_response = await asyncio.gather(
        project_client.post(
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
            f"submission-artifact-policies/{first_policy['id']}/approve",
            headers=auth_headers(),
            json={"approval_note": "Approved first policy."},
        ),
        project_client.post(
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
            f"submission-artifact-policies/{second_policy['id']}/approve",
            headers=auth_headers(),
            json={"approval_note": "Approved second policy."},
        ),
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    async with db_session.get_session_factory()() as session:
        policies = (
            await session.scalars(
                select(SubmissionArtifactPolicy).where(
                    SubmissionArtifactPolicy.project_id == project["id"],
                    SubmissionArtifactPolicy.guide_version == guide["version"],
                )
            )
        ).all()
        effective_policies = (
            await session.scalars(
                select(EffectiveProjectSubmissionArtifactPolicy).where(
                    EffectiveProjectSubmissionArtifactPolicy.project_id == project["id"],
                    EffectiveProjectSubmissionArtifactPolicy.guide_version == guide["version"],
                )
            )
        ).all()
        pre_submit_policies = (
            await session.scalars(
                select(PreSubmitCheckerPolicy).where(
                    PreSubmitCheckerPolicy.project_id == project["id"],
                    PreSubmitCheckerPolicy.guide_version == guide["version"],
                )
            )
        ).all()
        repo = ProjectRepository(session)
        current_policy = await repo.get_current_approved_submission_artifact_policy(
            project["id"],
            guide["version"],
        )
        current_pre_submit = await repo.get_current_pre_submit_checker_policy(
            project["id"],
            guide["version"],
        )

    assert len(policies) == 2
    assert len(effective_policies) == 2
    assert len(pre_submit_policies) == 2
    assert current_policy is not None
    assert current_pre_submit is not None
    assert {policy.lifecycle_status for policy in policies} == {"approved", "superseded"}
    assert {policy.lifecycle_status for policy in effective_policies} == {
        "approved",
        "superseded",
    }
    assert {policy.lifecycle_status for policy in pre_submit_policies} == {
        "compiled",
        "superseded",
    }
    assert (
        len({policy.supersedes_policy_id for policy in policies if policy.supersedes_policy_id})
        == 1
    )
    assert (
        len(
            {
                policy.supersedes_effective_policy_id
                for policy in effective_policies
                if policy.supersedes_effective_policy_id
            }
        )
        == 1
    )
    assert (
        len(
            {
                policy.supersedes_pre_submit_checker_policy_id
                for policy in pre_submit_policies
                if policy.supersedes_pre_submit_checker_policy_id
            }
        )
        == 1
    )


async def test_inline_guide_body_is_rejected_after_source_snapshot(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"content_markdown": "# Drift after snapshot"},
    )

    assert response.status_code == 422
    assert "content_markdown" in response.text


async def test_removed_payment_policy_edit_after_source_snapshot_is_rejected(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    await read_guide_source_snapshot(project["id"], guide["id"])
    payment_policy = {
        "base_amount": "25.00",
        "currency": "USD",
        "payout_type": "fixed",
        "revision_payment_rule": "none",
        "rejection_payment_rule": "none",
        "accepted_payment_rule": "pay base amount",
    }
    payment_policy["base_amount"] = "100.00"

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"payment_policy": payment_policy},
    )

    assert response.status_code == 422
    assert "payment_policy" in response.text


async def test_draft_policy_cannot_be_approved_after_guide_activation(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    report = await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    report = {
        **report,
        "id": await create_compiled_report_fixture(report["id"], snapshot["id"]),
    }
    first_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v1",
    )
    second_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v2",
    )
    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        first_policy["id"],
    )
    pre_submit_checker_policy = await load_pre_submit_checker_policy(effective)
    await seed_post_submit_policy_for_downstream_tests(
        project_id=project["id"],
        guide_id=guide["id"],
        source_snapshot=snapshot,
        pre_submit_checker_policy=pre_submit_checker_policy,
    )

    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{second_policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "late drift"},
    )

    assert response.status_code == 409
    assert "draft guides" in response.json()["detail"]


async def test_manual_submission_artifact_policy_create_rejects_default_weakening(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(
                manifest_required=False,
            ),
        },
    )

    assert response.status_code == 422
    assert "manifest" in response.json()["detail"]


async def test_submission_artifact_policy_rejects_default_artifact_key_conflict(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_policy = {
        **project_service_module.WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY,
        "required_artifacts": [
            {
                "key": "answer",
                "path": "platform/answer.md",
                "hash_required": True,
                "required": True,
                "description": "Platform answer artifact.",
            }
        ],
    }
    monkeypatch.setattr(
        project_service_module,
        "WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY",
        default_policy,
    )
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(
                artifact_path="project/answer.md",
            ),
            "change_summary": "Conflicting artifact key.",
        },
    )

    assert response.status_code == 422
    assert "conflicts with Workstream default rules" in response.json()["detail"]


async def test_submission_artifact_policy_dedupes_identical_default_artifact_key(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = project_submission_artifact_policy_body()["required_artifacts"][0]
    default_policy = {
        **project_service_module.WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY,
        "required_artifacts": [artifact],
    }
    monkeypatch.setattr(
        project_service_module,
        "WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY",
        default_policy,
    )
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )

    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    required_artifacts = effective["effective_policy"]["required_artifacts"]
    assert len(required_artifacts) == 1
    assert required_artifacts[0] == artifact


async def test_submission_artifact_policy_rejects_rule_hash_weakening(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(
                rule_hash_required=False,
            ),
        },
    )

    assert response.status_code == 422
    assert "hash_required" in response.text


async def test_submission_artifact_policy_rejects_arbitrary_packaging_refs(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(
                packaging={
                    "package_required": False,
                    "template_url": "https://storage.flow.test/pkg?token=secret",
                },
            ),
        },
    )

    assert response.status_code == 422
    assert "extra" in response.text


@pytest.mark.parametrize(
    "policy_body",
    [
        {**project_submission_artifact_policy_body(), "freeform": "not allowed"},
        {
            **project_submission_artifact_policy_body(),
            "required_artifacts": [
                {
                    **project_submission_artifact_policy_body()["required_artifacts"][0],
                    "checksum_hint": "not allowed",
                }
            ],
        },
        {
            **project_submission_artifact_policy_body(),
            "required_evidence": [
                {
                    **project_submission_artifact_policy_body()["required_evidence"][0],
                    "prompt": "not allowed",
                }
            ],
        },
        {
            **project_submission_artifact_policy_body(),
            "forbidden_artifacts": [
                {
                    **project_submission_artifact_policy_body()["forbidden_artifacts"][0],
                    "severity": "not allowed",
                }
            ],
        },
    ],
)
async def test_submission_artifact_policy_rejects_unknown_policy_keys(
    project_client: AsyncClient,
    policy_body: dict,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": policy_body,
        },
    )

    assert response.status_code == 422
    assert "extra" in response.text


async def test_submission_artifact_policy_rejects_unknown_wrapper_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )

    create_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v2",
            "policy_body": project_submission_artifact_policy_body(),
            "project_owner_approved": True,
        },
    )
    update_response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=auth_headers(),
        json={"change_summary": "valid", "approval_status": "not allowed"},
    )
    approve_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "valid", "project_owner_approved": True},
    )

    assert create_response.status_code == 422
    assert update_response.status_code == 422
    assert approve_response.status_code == 422
    assert "extra" in create_response.text
    assert "extra" in update_response.text
    assert "extra" in approve_response.text


@pytest.mark.parametrize(
    "artifact_path",
    [
        ".env",
        ".env.production",
        "config/.env.production",
        "private-key.txt",
        "keys/id_rsa.pub",
        "keys/id_ed25519",
        "keys/id_ecdsa",
        ".npmrc",
        ".pypirc",
        "api-key.txt",
        "api_key.txt",
        "outputs/aws access key.txt",
        "outputs/password dump.txt",
        "outputs/client secret.txt",
        "service-account.json",
        "secrets/api-token.txt",
        "config.env",
        "outputs/prod.env",
    ],
)
async def test_submission_artifact_policy_rejects_forbidden_required_artifacts(
    project_client: AsyncClient,
    artifact_path: str,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(artifact_path=artifact_path),
        },
    )

    assert response.status_code == 422
    assert "forbidden artifacts" in response.json()["detail"]


@pytest.mark.parametrize(
    "artifact_path",
    ["outputs/secretary.txt", "outputs/tokenizer.py", "outputs/credentialing.py"],
)
def test_submission_artifact_policy_allows_non_secret_keyword_prefixes(
    artifact_path: str,
) -> None:
    service = ProjectService(None)  # type: ignore[arg-type]

    assert not service._matches_forbidden_artifact(artifact_path, [])


@pytest.mark.parametrize(
    ("policy_body", "expected_detail"),
    [
        (
            {
                **project_submission_artifact_policy_body(),
                "required_artifacts": [
                    project_submission_artifact_policy_body()["required_artifacts"][0],
                    {
                        **project_submission_artifact_policy_body()["required_artifacts"][0],
                        "path": "outputs/alternate-answer.md",
                    },
                ],
            },
            "duplicate required artifact key",
        ),
        (
            {
                **project_submission_artifact_policy_body(),
                "required_evidence": [
                    project_submission_artifact_policy_body()["required_evidence"][0],
                    {
                        **project_submission_artifact_policy_body()["required_evidence"][0],
                        "label": "Alternate reasoning trace",
                    },
                ],
            },
            "duplicate required evidence key",
        ),
        (
            {
                **project_submission_artifact_policy_body(),
                "attestation_terms": ["a" * 101],
            },
            "attestation terms",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="outputs/%2E%2E/secret.txt"),
            "percent-encoded",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="outputs/100%complete.md"),
            "percent-encoded",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="outputs/final\nanswer.md"),
            "control characters",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="C:/Users/alice/output.md"),
            "safe relative paths",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="C:\\Users\\alice\\output.md"),
            "safe relative paths",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="outputs\\final-answer.md"),
            "local path separators",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="s3:bucket/key.md"),
            "storage refs or URLs",
        ),
        (
            project_submission_artifact_policy_body(artifact_path="file:output.md"),
            "storage refs or URLs",
        ),
        (
            {
                **project_submission_artifact_policy_body(),
                "required_artifacts": [
                    {
                        **project_submission_artifact_policy_body()["required_artifacts"][0],
                        "key": "aws_access_key",
                        "path": "outputs/safe.txt",
                    }
                ],
            },
            "required artifact conflicts with forbidden artifacts",
        ),
        (
            {
                **project_submission_artifact_policy_body(
                    artifact_path="steps/milestone_1/tests/test_m1.py"
                ),
                "forbidden_artifacts": [
                    {
                        "pattern": "steps/*/tests/*",
                        "reason": "Broad test-directory block conflicts with required tests.",
                        "worker_facing_fix": "Do not forbid required test files.",
                    }
                ],
            },
            "required artifact conflicts with forbidden artifacts",
        ),
        (
            {
                **project_submission_artifact_policy_body(),
                "required_artifacts": [
                    {
                        **project_submission_artifact_policy_body()["required_artifacts"][0],
                        "path": "outputs/safe.txt",
                        "description": "Upload the API token here.",
                    }
                ],
            },
            "required artifact conflicts with forbidden artifacts",
        ),
        (
            {
                **project_submission_artifact_policy_body(),
                "required_evidence": [
                    {
                        **project_submission_artifact_policy_body()["required_evidence"][0],
                        "description": "Include any private key used during the work.",
                    }
                ],
            },
            "required evidence conflicts with forbidden artifacts",
        ),
    ],
)
async def test_submission_artifact_policy_rejects_ambiguous_or_oversized_policy_terms(
    project_client: AsyncClient,
    policy_body: dict,
    expected_detail: str,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": policy_body,
        },
    )

    assert response.status_code == 422
    assert expected_detail in response.json()["detail"]


async def test_blocking_sufficiency_report_prevents_policy_creation(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        status="blocked",
    )
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(),
            "change_summary": "Blocked guide should not create policy.",
        },
    )

    assert response.status_code == 422
    assert "authoritative guide sufficiency report is required" in response.json()["detail"]


async def test_unified_warnings_do_not_use_the_manual_report_acknowledgement_path(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    diagnostic = await create_sufficiency_report(project_client, project["id"], guide["id"],
        snapshot["id"], status="passed_with_warnings")
    compiled_id = await create_compiled_report_fixture(diagnostic["id"], snapshot["id"])
    base = f"/api/v1/projects/{project['id']}/guides/{guide['id']}"
    blocked = await project_client.post(f"{base}/sufficiency-reports/{compiled_id}/acknowledge-warnings",
        headers=auth_headers(), json={"acknowledgement_note": "Requires complete proposal review."})
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "project_setup_run_context_mismatch"
    async with db_session.get_session_factory()() as session:
        compiled = await session.get(GuideSufficiencyReport, compiled_id)
        assert compiled.warnings_acknowledged_at is None
        assert compiled.warnings_acknowledged_by_actor_profile_id is None
        assert await session.scalar(select(SubmissionArtifactPolicy.id)) is None

    headers = auth_headers()
    route = f"{base}/sufficiency-reports/{diagnostic['id']}/acknowledge-warnings"
    payload = {"acknowledgement_note": "Human diagnostic acknowledged."}
    acknowledged = await project_client.post(route, headers=headers, json=payload)
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["warnings_acknowledged_by_role"] == "project_manager"
    replay = await project_client.post(route, headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json() == acknowledged.json()
    duplicate = await project_client.post(route, headers=auth_headers(), json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "sufficiency_warnings_already_acknowledged"
    policy = await project_client.post(f"{base}/submission-artifact-policies", headers=auth_headers(),
        json={"source_snapshot_id": snapshot["id"], "policy_version": "v1",
              "policy_body": project_submission_artifact_policy_body(), "change_summary": "Still blocked."})
    assert policy.status_code == 422
    assert "authorized Project Manager acknowledgement" in policy.json()["detail"]


async def test_sufficiency_warning_acknowledgement_requires_setup_role_for_policy_approval(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    report = await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        status="passed_with_warnings",
    )
    report = {
        **report,
        "id": await create_compiled_report_fixture(report["id"], snapshot["id"]),
    }

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(GuideSufficiencyReport, report["id"])
        assert persisted is not None
        persisted.warnings_acknowledged_by_actor = "worker-subject"
        persisted.warnings_acknowledged_by_role = "worker"
        persisted.warnings_acknowledged_at = datetime.now(UTC)
        await session.commit()

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(),
            "change_summary": "Invalid warning acknowledgement provenance.",
        },
    )

    assert response.status_code == 422
    assert "authorized Project Manager acknowledgement" in response.json()["detail"]


async def test_sufficiency_warning_acknowledgement_rejects_unknown_fields(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    report = await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        status="passed_with_warnings",
    )

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports/"
        f"{report['id']}/acknowledge-warnings",
        headers=auth_headers(),
        json={"acknowledgement_note": "valid", "approver_role": "project_owner"},
    )

    assert response.status_code == 422
    assert "extra" in response.text


async def test_worker_cannot_approve_submission_artifact_policy(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "worker")
    get_settings.cache_clear()

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "forged"},
    )

    assert response.status_code == 403


async def test_database_rejects_post_submit_checker_approved_by_non_setup_role(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(
        project_client,
        project["id"],
        guide["id"],
    )
    async with db_session.get_session_factory()() as session:
        policy = await session.get(
            PostSubmitCheckerPolicy, bundle["post_submit_checker_policy"]["id"]
        )
        assert policy is not None
        policy.approved_by_role = "worker"
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_database_rejects_superseded_post_submit_policy_without_correction_provenance(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(
        project_client,
        project["id"],
        guide["id"],
    )
    async with db_session.get_session_factory()() as session:
        policy = await session.get(
            PostSubmitCheckerPolicy,
            bundle["post_submit_checker_policy"]["id"],
        )
        assert policy is not None
        policy.lifecycle_status = "superseded"
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_guide_payload_rejects_manual_post_submit_checker_policy(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["post_submit_checker_policy"] = {
        "required_checkers": [],
        "warning_checkers": [],
    }

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "post_submit_checker_policy" in response.text


async def test_review_policy_rejects_invalid_decision_names(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["review_policy"] = {
        "requires_second_review": False,
        "allowed_decisions": ["accept", "hold"],
        "minimum_finding_fields": ["issue", "required_fix"],
        "review_preference_window_seconds": 3600,
        "review_lease_duration_seconds": 1800,
    }

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "review_policy" in detail["loc"]
    assert detail["input"] == "redacted"
    assert "hold" not in response.text


async def test_activation_requires_complete_payment_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["payment_policy"] = {
        "base_amount": "25.00",
        "currency": "USD",
        "payout_type": "fixed",
        "revision_payment_rule": "none",
        "rejection_payment_rule": "none",
        "accepted_payment_rule": None,
    }
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "payment_policy" in response.text


async def test_activation_requires_complete_revision_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"] = {
        "max_revision_rounds": 7,
        "revision_deadline_hours": 48,
        "allowed_resubmission_states": [],
        "reviewer_reassignment_rule": "same reviewer preferred",
    }
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "revision_policy" in response.text


async def test_revision_policy_requires_deadline(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"] = {
        "max_revision_rounds": 7,
        "allowed_resubmission_states": ["needs_revision"],
        "reviewer_reassignment_rule": "same reviewer preferred",
    }

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "revision_policy" in detail["loc"]


async def test_guide_update_rejects_manual_post_submit_checker_policy(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={
            "post_submit_checker_policy": {
                "required_checkers": ["check_policy_context_present"],
                "warning_checkers": [],
            }
        },
    )

    assert response.status_code == 422
    assert "post_submit_checker_policy" in response.text


async def test_activation_rejects_unsupported_revision_resubmission_states(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"] = {
        "max_revision_rounds": 7,
        "revision_deadline_hours": 48,
        "allowed_resubmission_states": ["random_state"],
        "reviewer_reassignment_rule": "same reviewer preferred",
    }
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "revision_policy" in response.text


async def test_database_enforces_compiled_pre_submit_checker_bundle_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == bundle["effective_policy"]["id"]
            )
        )
        assert pre_submit_checker_policy is not None
        pre_submit_checker_policy.compiled_bundle_hash = None
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_database_rejects_mismatched_post_submit_pre_submit_checker_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])
    async with db_session.get_session_factory()() as session:
        post_submit_checker_policy = await session.get(
            PostSubmitCheckerPolicy,
            bundle["post_submit_checker_policy"]["id"],
        )
        assert post_submit_checker_policy is not None
        post_submit_checker_policy.pre_submit_checker_bundle_hash = sha256_hash(
            "wrong-compiled-bundle"
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_active_guide_read_rejects_mismatched_effective_policy_body_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    await add_project_manager_admin_grant(project["id"])
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )
    async with db_session.get_session_factory()() as session:
        effective_policy = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            bundle["effective_policy"]["id"],
        )
        assert effective_policy is not None
        effective_policy.effective_policy = {
            **effective_policy.effective_policy,
            "allowed_storage_schemes": ["local"],
        }
        await session.commit()

    response = await project_client.get(
        f"/api/v1/projects/{project['id']}/active-guide",
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_authorization_resource_not_found"


async def test_active_guide_read_revalidates_policy_context(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    await add_project_manager_admin_grant(project["id"])
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )

    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == bundle["effective_policy"]["id"]
            )
        )
        assert pre_submit_checker_policy is not None
        pre_submit_checker_policy.lifecycle_status = "pending_compilation"
        await session.commit()

    response = await project_client.get(
        f"/api/v1/projects/{project['id']}/active-guide",
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_authorization_resource_not_found"


async def test_active_guide_retrieval_returns_exact_policy_bundle(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    await add_project_manager_admin_grant(project["id"])
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    activation = await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )
    active = await project_client.get(
        f"/api/v1/projects/{project['id']}/active-guide",
        headers=auth_headers(),
    )
    effective_read = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
        "effective-submission-artifact-policy",
        headers=auth_headers(),
    )
    checker_read = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/pre-submit-checker-policy",
        headers=auth_headers(),
    )

    assert active.status_code == 200, active.text
    assert effective_read.status_code == 200, effective_read.text
    assert checker_read.status_code == 200, checker_read.text
    assert set(effective_read.json()) == {
        "id",
        "project_id",
        "guide_id",
        "guide_version",
        "source_snapshot_id",
        "source_snapshot_hash",
        "submission_artifact_policy_id",
        "submission_artifact_policy_hash",
        "lifecycle_status",
        "merge_algorithm_version",
        "effective_policy",
        "effective_policy_hash",
        "created_by",
        "created_at",
        "supersedes_effective_policy_id",
        "superseded_at",
    }
    assert set(checker_read.json()) == {
        "id",
        "project_id",
        "guide_id",
        "guide_version",
        "source_snapshot_id",
        "source_snapshot_hash",
        "effective_policy_id",
        "effective_policy_hash",
        "lifecycle_status",
        "compiler_version",
        "compiled_bundle_hash",
        "checker_names",
        "created_by",
        "created_at",
        "supersedes_pre_submit_checker_policy_id",
        "superseded_at",
    }
    assert set(active.json()) == {
        "guide",
        "guide_source_snapshot",
        "guide_sufficiency_report",
        "submission_artifact_policy",
        "effective_submission_artifact_policy",
        "pre_submit_checker_policy",
        "post_submit_checker_policy",
        "review_policy",
        "revision_policy",
    }
    assert effective_read.json()["id"] == bundle["effective_policy"]["id"]
    assert checker_read.json()["effective_policy_id"] == bundle["effective_policy"]["id"]
    assert "compiled_bundle" not in checker_read.json()
    assert "checker_configs" not in checker_read.json()
    assert active.json()["guide"]["status"] == "active"
    assert active.json()["guide"]["version"] == "v1"
    assert active.json()["guide"]["approved_by"] == guide["created_by"]
    assert active.json()["guide"]["effective_at"] is not None
    assert activation["guide"]["approved_by"] == guide["created_by"]
    assert datetime.fromisoformat(activation["guide"]["effective_at"]) == datetime.fromisoformat(active.json()["guide"]["effective_at"])
    assert active.json()["post_submit_checker_policy"]["required_checkers"] == []
    assert (
        active.json()["guide_source_snapshot"]["bundle_hash"]
        == (bundle["source_snapshot"]["bundle_hash"])
    )
    assert active.json()["guide_sufficiency_report"]["status"] == "passed"
    assert active.json()["submission_artifact_policy"]["lifecycle_status"] == "approved"
    assert (
        active.json()["effective_submission_artifact_policy"]["effective_policy_hash"]
        == (bundle["effective_policy"]["effective_policy_hash"])
    )
    assert active.json()["pre_submit_checker_policy"]["lifecycle_status"] == "compiled"
    assert (
        active.json()["pre_submit_checker_policy"]["effective_policy_id"]
        == (bundle["effective_policy"]["id"])
    )
    assert (
        active.json()["pre_submit_checker_policy"]["compiled_bundle_hash"]
        == (bundle["pre_submit_checker_policy"]["compiled_bundle_hash"])
    )
    assert "compiled_bundle" not in active.json()["pre_submit_checker_policy"]
    assert "payment_policy" not in active.json()
    assert "review_policy" in active.json()
    assert (
        active.json()["pre_submit_checker_policy"]["checker_names"]
        == (bundle["pre_submit_checker_policy"]["checker_names"])
    )
    assert (
        active.json()["pre_submit_checker_policy"]["checker_configs"]
        == (bundle["pre_submit_checker_policy"]["checker_configs"])
    )
    assert active.json()["revision_policy"]["max_revision_rounds"] == 7
    assert "auto_reject_after_limit" not in active.json()["revision_policy"]


async def test_draft_guide_edit_and_active_guide_edit_block(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    draft_update = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"change_summary": "Updated draft"},
    )
    assert draft_update.status_code == 200, draft_update.text
    assert draft_update.json()["change_summary"] == "Updated draft"
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )

    active_update = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"change_summary": "Mutate active"},
    )
    assert active_update.status_code == 409


async def test_database_enforces_single_active_guide_per_project(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    first = await create_guide(project_client, project["id"], complete_guide_payload("v1"))
    second = await create_guide(project_client, project["id"], complete_guide_payload("v2"))

    async with db_session.get_session_factory()() as session:
        first_guide = await session.get(ProjectGuide, first["id"])
        second_guide = await session.get(ProjectGuide, second["id"])
        assert first_guide is not None
        assert second_guide is not None
        first_guide.status = "active"
        second_guide.status = "active"
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_active_guide_lookup_surfaces_duplicate_rows() -> None:
    guides = [
        ProjectGuide(id="guide-1", project_id="project-1", version="v1", status="active"),
        ProjectGuide(id="guide-2", project_id="project-1", version="v2", status="active"),
    ]

    class FakeScalars:
        def all(self) -> list[ProjectGuide]:
            return guides

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    class FakeSession:
        async def execute(self, statement) -> FakeResult:
            return FakeResult()

    with pytest.raises(ProjectRepositoryIntegrityError, match="multiple active guides"):
        await ProjectRepository(FakeSession()).get_active_guide("project-1")


async def test_worker_cannot_create_project_records(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "worker")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "ungranted-worker-subject")
    get_settings.cache_clear()

    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={"name": "Worker Project", "slug": "worker-project"},
    )

    assert response.status_code == 403


async def test_project_create_validation_errors_are_structured(project_client: AsyncClient) -> None:
    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={"slug": "missing-name"},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_project_create_requires_valid_idempotency_before_actor_provisioning(
    project_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = f"missing-idempotency-{uuid4()}"
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", subject)
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for headers in (
            {"Authorization": "Bearer project-token"},
            {"Authorization": "Bearer project-token", "Idempotency-Key": "invalid"},
        ):
            response = await client.post(
                "/api/v1/projects",
                headers=headers,
                json={"name": "Rejected", "slug": f"rejected-{uuid4()}"},
            )
            assert response.status_code == 422

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(ActorIdentityLink).where(ActorIdentityLink.subject == subject)
            )
            is None
        )


async def test_project_create_different_keys_same_slug_rolls_back_authority(
    project_client: AsyncClient,
) -> None:
    slug = f"same-slug-{uuid4()}"
    first = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={"name": "First", "slug": slug},
    )
    conflict = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={"name": "Second", "slug": slug},
    )
    assert first.status_code == 201, first.text
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "project_slug_conflict"

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Project).where(Project.slug == slug)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectCreateIdempotencyRecord)
                .where(ProjectCreateIdempotencyRecord.status == "pending")
            )
            == 0
        )


async def test_project_create_copied_key_cannot_cross_actor_namespace(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = str(uuid4())
    payload = {
        "name": "Actor-bound replay",
        "slug": f"actor-bound-replay-{uuid4()}",
    }
    first = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": key},
        json=payload,
    )
    assert first.status_code == 201

    second_subject = f"copied-key-actor-{uuid4()}"
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", second_subject)
    get_settings.cache_clear()
    admitted = await project_client.get("/api/v1/actors/me", headers=auth_headers())
    assert admitted.status_code == 200
    grantor_id, _, grantor_grant_id = await ensure_access_administrator_bootstrap()
    async with db_session.get_session_factory()() as session:
        second_link = await session.scalar(
            select(ActorIdentityLink).where(ActorIdentityLink.subject == second_subject)
        )
        assert second_link is not None
        session.add(
            AdminRoleGrant(
                id=uuid4(),
                target_actor_profile_id=second_link.actor_profile_id,
                role="project_manager",
                scope_type="system",
                scope_project_id=None,
                status="active",
                version=1,
                granted_by_actor_profile_id=grantor_id,
                granted_by_admin_role_grant_id=grantor_grant_id,
                grant_reason="AUTH-12C copied-key actor boundary proof",
            )
        )
        await session.commit()

    copied = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": key},
        json=payload,
    )
    assert copied.status_code == 409
    assert copied.json()["error"]["code"] == "project_slug_conflict"
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Project).where(Project.slug == payload["slug"])
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectCreateIdempotencyRecord)
                .where(
                    ProjectCreateIdempotencyRecord.idempotency_key == UUID(key),
                    ProjectCreateIdempotencyRecord.status == "pending",
                )
            )
            == 0
        )


async def test_project_create_denies_project_scoped_and_contributor_authority(
    project_client: AsyncClient,
) -> None:
    seed = await create_project(project_client, name="Scope boundary seed")
    async with db_session.get_session_factory()() as session:
        system_manager = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.role == "project_manager",
                AdminRoleGrant.scope_type == "system",
                AdminRoleGrant.status == "active",
            )
        )
        assert system_manager is not None
        system_manager_id = system_manager.id
    await revoke_local_admin_role(system_manager_id)
    await add_project_manager_admin_grant(seed["id"])
    await add_project_role_for_default_actor(seed["id"], "submitter")

    denied = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={"name": "Wrong scope", "slug": f"wrong-scope-{uuid4()}"},
    )
    assert denied.status_code == 403

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Project).where(Project.name == "Wrong scope")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectCreateIdempotencyRecord)
                .where(ProjectCreateIdempotencyRecord.status == "pending")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action_id == "project.create",
                    AuditEvent.event_type == "SensitiveAuthorizationAllowed",
                    AuditEvent.target_ref_id != seed["id"],
                )
            )
            == 0
        )
        denial_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action_id == "project.create",
                AuditEvent.event_type == "SensitiveAuthorizationDenied",
                AuditEvent.denial_code == "permission_not_granted",
            )
        )
        assert denial_event is not None
        assert denial_event.resource_type == "project_create_operation"
        assert denial_event.target_ref_kind == "project"
        assert denial_event.resource_id is not None
        assert denial_event.target_ref_id is not None
