"""PROJECT public locked-policy context capability tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import session as db_session
from app.modules.projects.api import (
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    PreSubmitCheckerPolicy,
    Project,
)
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from test_projects import (
    complete_guide_payload,
    create_approved_policy_bundle,
    create_guide,
    create_project,
)
from project_create_fixtures import activate_guide_for_downstream_test
from projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)


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
            deadline = asyncio.get_running_loop().time() + 30.0
            while asyncio.get_running_loop().time() < deadline:
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
                await asyncio.sleep(0.01)
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
async def test_locked_policy_repository_postgresql_resolves_current(
    project_client: AsyncClient,
) -> None:
    request = await create_locked_policy_context_fixture(project_client)
    async with db_session.get_session_factory()() as session:
        current = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(request)
        assert current.guide_status == "active"
        assert current.effective_policy_status == "approved"
        assert current.pre_submit_policy_status == "compiled"


@pytest.mark.asyncio
async def test_locked_policy_repository_postgresql_resolves_superseded(
    project_client: AsyncClient,
) -> None:
    request = await create_locked_policy_context_fixture(project_client)
    await _supersede_locked_policy_context(request)
    async with db_session.get_session_factory()() as session:
        historical = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
            request
        )
        assert historical.guide_status == "active"
        assert historical.effective_policy_status == "superseded"
        assert historical.pre_submit_policy_status == "superseded"


@pytest.mark.asyncio
async def test_locked_policy_repository_postgresql_rejects_unknown_effective_policy(
    project_client: AsyncClient,
) -> None:
    request = await create_locked_policy_context_fixture(project_client)
    await _supersede_locked_policy_context(request)
    wrong_successor = replace(request, effective_policy_id=uuid4())
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            ProjectLockedPolicyContextUnavailable,
            match="project_locked_policy_context_changed",
        ):
            await ProjectLockedPolicyRepository(session).lock_locked_policy_context(wrong_successor)


@pytest.mark.asyncio
async def test_locked_policy_repository_postgresql_rejects_pending_pre_submit(
    project_client: AsyncClient,
) -> None:
    request = await create_locked_policy_context_fixture(project_client)
    await _supersede_locked_policy_context(request)
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
            await ProjectLockedPolicyRepository(session).lock_locked_policy_context(request)


@pytest.mark.asyncio
async def test_locked_policy_repository_postgresql_rejects_inactive_project(
    project_client: AsyncClient,
) -> None:
    """Writer commits first: refresh stale identity-map state before returning facts."""
    request = await create_locked_policy_context_fixture(project_client)
    factory = db_session.get_session_factory()
    async with factory() as observer:
        project = await observer.get(Project, str(request.project_id))
        assert project is not None and project.status == "active"
        current = await ProjectLockedPolicyRepository(observer).lock_locked_policy_context(request)
        assert current.project_id == request.project_id
        await observer.commit()

        async with factory() as writer:
            await writer.execute(
                update(Project).where(Project.id == str(request.project_id)).values(status="draft")
            )
            await writer.commit()

        assert project.status == "active"  # The observer still holds its cached object.
        with pytest.raises(ProjectLockedPolicyContextUnavailable) as denied:
            await ProjectLockedPolicyRepository(observer).lock_locked_policy_context(request)
        assert denied.value.code == "project_locked_policy_context_changed"
        assert project.status == "draft"
        assert not observer.new and not observer.dirty and not observer.deleted


@pytest.mark.asyncio
async def test_locked_policy_repository_postgresql_serializes_project_status_change(
    project_client: AsyncClient,
    project_database_env: str,
) -> None:
    """Reader locks first: inactivation waits for the exact owning transaction."""
    request = await create_locked_policy_context_fixture(project_client)
    contender_name = f"project-inactivation-{uuid4()}"
    factory = db_session.get_session_factory()
    holder, contender = factory(), factory()
    contender_call: asyncio.Task[Any] | None = None
    try:
        await ProjectLockedPolicyRepository(holder).lock_locked_policy_context(request)
        await contender.execute(
            text("select set_config('application_name', :application_name, true)"),
            {"application_name": contender_name},
        )
        contender_call = asyncio.create_task(
            contender.execute(
                update(Project).where(Project.id == str(request.project_id)).values(status="draft")
            )
        )
        await _wait_for_project_database_lock(project_database_env, contender_name)
        assert not contender_call.done()
        await holder.commit()
        await contender_call
        await contender.commit()
        async with factory() as observer:
            project = await observer.get(Project, str(request.project_id))
            assert project is not None and project.status == "draft"
    finally:
        if contender_call is not None:
            contender_call.cancel()
            await asyncio.gather(contender_call, return_exceptions=True)
        await holder.close()
        await contender.close()

@pytest.mark.asyncio
async def test_locked_policy_repository_postgresql_does_not_substitute_successors(
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
        historical = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
            request
        )
        assert historical.effective_policy_id == request.effective_policy_id
        assert historical.pre_submit_policy_id == request.pre_submit_policy_id


@pytest.mark.asyncio
async def test_locked_policy_repository_postgresql_serializes_race(
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
        held = await ProjectLockedPolicyRepository(holder).lock_locked_policy_context(request)
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
