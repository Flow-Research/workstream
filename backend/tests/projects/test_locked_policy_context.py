"""PROJECT public locked-policy context capability tests."""

# ruff: noqa: F401, F811 -- imported pytest fixtures must remain module globals.

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

from httpx import AsyncClient
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.hashing import canonical_json_hash
from app.db import session as db_session
from app.modules.projects.api import (
    CanonicalJsonObject,
    ProjectLockedPolicyContextFacts,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    PreSubmitCheckerPolicy,
)
from app.modules.projects.repository import ProjectRepository
from test_projects import (
    activate_guide_for_downstream_test,
    complete_guide_payload,
    create_approved_policy_bundle,
    create_guide,
    create_project,
    project_client,
    project_database_env,
)


def _project_locked_policy_rows(
    *,
    guide_status: str = "active",
    effective_status: str = "approved",
    pre_submit_status: str = "compiled",
) -> tuple[ProjectLockedPolicyContextRequest, tuple[SimpleNamespace, ...]]:
    """Build one internally consistent locked PROJECT lineage."""
    project_id, guide_id, snapshot_id, effective_id, pre_submit_id = (uuid4() for _ in range(5))
    manifest = {"items": [{"name": "guide.md"}], "schema_version": "v1"}
    effective_body = {"allowed": ["zip"], "limits": {"max_bytes": 1024}}
    compiled_bundle = {"rules": [{"primitive": "zip_safety"}]}
    snapshot_hash = canonical_json_hash(manifest)
    effective_hash = canonical_json_hash(effective_body)
    bundle_hash = canonical_json_hash(compiled_bundle)
    request = ProjectLockedPolicyContextRequest(
        project_id=project_id,
        guide_version="v1",
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        effective_policy_id=effective_id,
        effective_policy_hash=effective_hash,
        pre_submit_policy_id=pre_submit_id,
        pre_submit_policy_bundle_hash=bundle_hash,
    )
    rows = (
        SimpleNamespace(id=str(project_id), status="active"),
        SimpleNamespace(
            id=str(guide_id),
            project_id=str(project_id),
            version="v1",
            status=guide_status,
        ),
        SimpleNamespace(
            id=str(snapshot_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version="v1",
            manifest_json=manifest,
            bundle_hash=snapshot_hash,
        ),
        SimpleNamespace(
            id=str(effective_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version="v1",
            source_snapshot_id=str(snapshot_id),
            source_snapshot_hash=snapshot_hash,
            effective_policy=effective_body,
            effective_policy_hash=effective_hash,
            lifecycle_status=effective_status,
        ),
        SimpleNamespace(
            id=str(pre_submit_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version="v1",
            source_snapshot_id=str(snapshot_id),
            source_snapshot_hash=snapshot_hash,
            effective_policy_id=str(effective_id),
            effective_policy_hash=effective_hash,
            lifecycle_status=pre_submit_status,
            compiler_version="pre-submit-v1",
            compiled_bundle=compiled_bundle,
            compiled_bundle_hash=bundle_hash,
        ),
    )
    return request, rows


def test_project_locked_policy_public_facts_are_deeply_immutable() -> None:
    """Canonical public policy values copy inputs without a mutable projection."""
    source = {"nested": {"values": [1, 2]}}
    canonical = CanonicalJsonObject.from_mapping(source)
    cast(dict[str, Any], source["nested"])["values"] = [3]
    assert canonical.value == '{"nested":{"values":[1,2]}}'
    assert canonical.sha256 == canonical_json_hash({"nested": {"values": [1, 2]}})
    assert not hasattr(canonical, "as_dict")
    with pytest.raises(ValueError, match="canonical JSON object is invalid"):
        CanonicalJsonObject('{"z":1,"a":2}')
    with pytest.raises(ValueError, match="canonical JSON object is invalid"):
        CanonicalJsonObject("not-json")
    with pytest.raises(ValueError, match="canonical JSON object is invalid"):
        CanonicalJsonObject.from_mapping(cast(Any, []))
    with pytest.raises(ValueError, match="failure code is invalid"):
        ProjectLockedPolicyContextUnavailable(cast(Any, "unbounded"))
    unavailable = ProjectLockedPolicyContextUnavailable("project_locked_policy_context_changed")
    assert unavailable.code == "project_locked_policy_context_changed"
    assert str(unavailable) == "project_locked_policy_context_changed"
    request, rows = _project_locked_policy_rows()
    with pytest.raises(ValueError, match="guide version is empty"):
        replace(request, guide_version=" ")
    with pytest.raises(ValueError, match="hash is invalid"):
        replace(request, effective_policy_hash="sha256:invalid")
    valid_facts = ProjectLockedPolicyContextFacts(
        project_id=request.project_id,
        guide_id=UUID(rows[1].id),
        guide_version="v1",
        guide_status="active",
        source_snapshot_id=request.source_snapshot_id,
        source_snapshot_hash=request.source_snapshot_hash,
        effective_policy_id=request.effective_policy_id,
        effective_policy_hash=request.effective_policy_hash,
        effective_policy_status="approved",
        effective_policy=CanonicalJsonObject.from_mapping(rows[3].effective_policy),
        pre_submit_policy_id=request.pre_submit_policy_id,
        pre_submit_policy_bundle_hash=request.pre_submit_policy_bundle_hash,
        pre_submit_policy_status="compiled",
        pre_submit_compiler_version="pre-submit-v1",
        compiled_pre_submit_bundle=CanonicalJsonObject.from_mapping(rows[4].compiled_bundle),
    )
    with pytest.raises(ValueError, match="facts are invalid"):
        replace(valid_facts, guide_status=cast(Any, "draft"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guide_status", "effective_status", "pre_submit_status"),
    (("active", "approved", "compiled"), ("superseded", "superseded", "superseded")),
)
async def test_project_repository_resolves_exact_current_and_superseded_locked_policy(
    guide_status: str,
    effective_status: str,
    pre_submit_status: str,
) -> None:
    """Resolve exact valid historical lineage without selecting successors."""
    request, rows = _project_locked_policy_rows(
        guide_status=guide_status,
        effective_status=effective_status,
        pre_submit_status=pre_submit_status,
    )
    statements: list[Any] = []

    class Session:
        def __init__(self) -> None:
            self.rows = iter(rows)

        async def scalar(self, statement: Any) -> Any:
            statements.append(statement)
            return next(self.rows)

    facts = await ProjectRepository(cast(Any, Session())).lock_locked_policy_context(request)
    assert facts == ProjectLockedPolicyContextFacts(
        project_id=request.project_id,
        guide_id=UUID(rows[1].id),
        guide_version="v1",
        guide_status=cast(Any, guide_status),
        source_snapshot_id=request.source_snapshot_id,
        source_snapshot_hash=request.source_snapshot_hash,
        effective_policy_id=request.effective_policy_id,
        effective_policy_hash=request.effective_policy_hash,
        effective_policy_status=cast(Any, effective_status),
        effective_policy=CanonicalJsonObject.from_mapping(rows[3].effective_policy),
        pre_submit_policy_id=request.pre_submit_policy_id,
        pre_submit_policy_bundle_hash=request.pre_submit_policy_bundle_hash,
        pre_submit_policy_status=cast(Any, pre_submit_status),
        pre_submit_compiler_version="pre-submit-v1",
        compiled_pre_submit_bundle=CanonicalJsonObject.from_mapping(rows[4].compiled_bundle),
    )
    assert len(statements) == 5
    assert all("FOR UPDATE" in str(statement) for statement in statements)
    assert all(
        statement.get_execution_options().get("populate_existing") is True
        for statement in statements
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    (
        "draft",
        "pending",
        "hash",
        "cross_project",
        "effective_link",
        "snapshot_array",
        "effective_array",
        "bundle_array",
    ),
)
async def test_project_repository_rejects_invalid_locked_policy_lineage(
    failure: str,
) -> None:
    """Fail closed for draft, pending, drifted, or cross-project lineage."""
    request, rows = _project_locked_policy_rows()
    if failure == "draft":
        rows[1].status = "draft"
    elif failure == "pending":
        rows[4].lifecycle_status = "pending_compilation"
    elif failure == "hash":
        rows[3].effective_policy = {"allowed": ["tar"]}
    elif failure == "cross_project":
        rows[2].project_id = str(uuid4())
    elif failure == "effective_link":
        rows[4].effective_policy_id = str(uuid4())
    elif failure == "snapshot_array":
        drift_hash = canonical_json_hash(cast(Any, []))
        request = replace(request, source_snapshot_hash=drift_hash)
        rows[2].manifest_json = []
        rows[2].bundle_hash = drift_hash
        rows[3].source_snapshot_hash = drift_hash
        rows[4].source_snapshot_hash = drift_hash
    elif failure == "effective_array":
        drift_hash = canonical_json_hash(cast(Any, []))
        request = replace(request, effective_policy_hash=drift_hash)
        rows[3].effective_policy = []
        rows[3].effective_policy_hash = drift_hash
        rows[4].effective_policy_hash = drift_hash
    else:
        drift_hash = canonical_json_hash(cast(Any, []))
        request = replace(request, pre_submit_policy_bundle_hash=drift_hash)
        rows[4].compiled_bundle = []
        rows[4].compiled_bundle_hash = drift_hash

    class Session:
        def __init__(self) -> None:
            self.rows = iter(rows)

        async def scalar(self, _statement: Any) -> Any:
            return next(self.rows)

    with pytest.raises(
        ProjectLockedPolicyContextUnavailable,
        match="project_locked_policy_context_changed",
    ):
        await ProjectRepository(cast(Any, Session())).lock_locked_policy_context(request)


async def create_locked_policy_context_fixture(
    client: AsyncClient,
) -> ProjectLockedPolicyContextRequest:
    """Create and activate one complete PROJECT policy lineage."""
    project = await create_project(client, name=f"Locked Context {uuid4()}")
    guide = await create_guide(client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(client, project["id"], guide["id"])
    activation = await activate_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )
    assert activation.status_code == 200, activation.text
    snapshot = bundle["source_snapshot"]
    effective = bundle["effective_policy"]
    pre_submit = bundle["pre_submit_checker_policy"]
    assert pre_submit is not None
    return ProjectLockedPolicyContextRequest(
        project_id=UUID(project["id"]),
        guide_version=guide["version"],
        source_snapshot_id=UUID(snapshot["id"]),
        source_snapshot_hash=snapshot["bundle_hash"],
        effective_policy_id=UUID(effective["id"]),
        effective_policy_hash=effective["effective_policy_hash"],
        pre_submit_policy_id=UUID(pre_submit["id"]),
        pre_submit_policy_bundle_hash=pre_submit["compiled_bundle_hash"],
    )


async def _wait_for_project_database_lock(
    database_url: str,
    application_name: str,
) -> None:
    """Wait until one named PROJECT race participant blocks on PostgreSQL."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            for _ in range(5000):
                waiting = await connection.scalar(
                    text(
                        "select exists(select 1 from pg_stat_activity where "
                        "application_name = :application_name "
                        "and wait_event_type = 'Lock')"
                    ),
                    {"application_name": application_name},
                )
                if waiting:
                    return
                await asyncio.sleep(0)
    finally:
        await engine.dispose()
    raise AssertionError(f"{application_name} never reached the PostgreSQL lock")


async def _supersede_locked_policy_context(
    request: ProjectLockedPolicyContextRequest,
) -> None:
    """Move one exact PROJECT policy lineage to its historical states."""
    async with db_session.get_session_factory()() as session:
        superseded_at = datetime.now(UTC)
        for model, identifier in (
            (EffectiveProjectSubmissionArtifactPolicy, request.effective_policy_id),
            (PreSubmitCheckerPolicy, request.pre_submit_policy_id),
        ):
            await session.execute(
                update(model)
                .where(model.id == str(identifier))
                .values(lifecycle_status="superseded", superseded_at=superseded_at)
            )
        await session.commit()


@pytest.mark.asyncio
async def test_project_repository_postgresql_locked_policy_state_matrix(
    project_client: AsyncClient,
) -> None:
    """Prove exact and superseded lineage semantics against PostgreSQL."""
    request = await create_locked_policy_context_fixture(project_client)
    async with db_session.get_session_factory()() as session:
        current = await ProjectRepository(session).lock_locked_policy_context(request)
        assert current.guide_status == "active"
        assert current.effective_policy_status == "approved"
        assert current.pre_submit_policy_status == "compiled"

    await _supersede_locked_policy_context(request)
    async with db_session.get_session_factory()() as session:
        historical = await ProjectRepository(session).lock_locked_policy_context(request)
        assert historical.guide_status == "active"
        assert historical.effective_policy_status == "superseded"
        assert historical.pre_submit_policy_status == "superseded"

    wrong_successor = replace(request, effective_policy_id=uuid4())
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            ProjectLockedPolicyContextUnavailable,
            match="project_locked_policy_context_changed",
        ):
            await ProjectRepository(session).lock_locked_policy_context(wrong_successor)

    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(PreSubmitCheckerPolicy)
            .where(PreSubmitCheckerPolicy.id == str(request.pre_submit_policy_id))
            .values(lifecycle_status="pending_compilation", superseded_at=None)
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            ProjectLockedPolicyContextUnavailable,
            match="project_locked_policy_context_changed",
        ):
            await ProjectRepository(session).lock_locked_policy_context(request)

@pytest.mark.asyncio
async def test_project_repository_postgresql_does_not_substitute_successors(
    project_client: AsyncClient,
) -> None:
    """Keep resolving exact historical IDs after current successors exist."""
    request = await create_locked_policy_context_fixture(project_client)
    await _supersede_locked_policy_context(request)
    async with db_session.get_session_factory()() as session:
        original_effective = await session.get(
            EffectiveProjectSubmissionArtifactPolicy, str(request.effective_policy_id)
        )
        original_pre_submit = await session.get(
            PreSubmitCheckerPolicy, str(request.pre_submit_policy_id)
        )
        assert original_effective is not None
        assert original_pre_submit is not None
        successor_effective_id = str(uuid4())
        session.add(
            EffectiveProjectSubmissionArtifactPolicy(
                id=successor_effective_id,
                project_id=original_effective.project_id,
                guide_id=original_effective.guide_id,
                guide_version=original_effective.guide_version,
                source_snapshot_id=original_effective.source_snapshot_id,
                source_snapshot_hash=original_effective.source_snapshot_hash,
                submission_artifact_policy_id=original_effective.submission_artifact_policy_id,
                submission_artifact_policy_hash=original_effective.submission_artifact_policy_hash,
                lifecycle_status="approved",
                merge_algorithm_version=original_effective.merge_algorithm_version,
                effective_policy=original_effective.effective_policy,
                effective_policy_hash=original_effective.effective_policy_hash,
                created_by="locked-context-successor-test",
                supersedes_effective_policy_id=original_effective.id,
            )
        )
        session.add(
            PreSubmitCheckerPolicy(
                id=str(uuid4()),
                project_id=original_pre_submit.project_id,
                guide_id=original_pre_submit.guide_id,
                guide_version=original_pre_submit.guide_version,
                source_snapshot_id=original_pre_submit.source_snapshot_id,
                source_snapshot_hash=original_pre_submit.source_snapshot_hash,
                effective_policy_id=successor_effective_id,
                effective_policy_hash=original_pre_submit.effective_policy_hash,
                lifecycle_status="compiled",
                compiler_version=original_pre_submit.compiler_version,
                compiled_bundle=original_pre_submit.compiled_bundle,
                compiled_bundle_hash=original_pre_submit.compiled_bundle_hash,
                checker_names=original_pre_submit.checker_names,
                checker_configs=original_pre_submit.checker_configs,
                created_by="locked-context-successor-test",
                supersedes_pre_submit_checker_policy_id=original_pre_submit.id,
            )
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        historical = await ProjectRepository(session).lock_locked_policy_context(request)
        assert historical.effective_policy_id == request.effective_policy_id
        assert historical.pre_submit_policy_id == request.pre_submit_policy_id


@pytest.mark.asyncio
async def test_project_repository_postgresql_locked_policy_serializes_race(
    project_client: AsyncClient,
    project_database_env: str,
) -> None:
    """Prove exact PROJECT lineage observation holds its pre-submit row lock."""
    request = await create_locked_policy_context_fixture(project_client)
    contender_name = f"project-locked-policy-{uuid4()}"
    holder = db_session.get_session_factory()()
    contender = db_session.get_session_factory()()
    contender_call: asyncio.Task[Any] | None = None
    try:
        held = await ProjectRepository(holder).lock_locked_policy_context(request)
        await contender.execute(
            text("select set_config('application_name', :application_name, true)"),
            {"application_name": contender_name},
        )
        contender_call = asyncio.create_task(
            contender.scalar(
                select(PreSubmitCheckerPolicy)
                .where(PreSubmitCheckerPolicy.id == str(request.pre_submit_policy_id))
                .with_for_update()
            )
        )
        await _wait_for_project_database_lock(project_database_env, contender_name)
        assert not contender_call.done()
        await holder.rollback()
        assert await contender_call is not None
        assert held.pre_submit_policy_id == request.pre_submit_policy_id
    finally:
        if contender_call is not None:
            contender_call.cancel()
            await asyncio.gather(contender_call, return_exceptions=True)
        await holder.close()
        await contender.close()
