"""PROJECT public locked-policy context capability tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
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
from projects.guide_fixtures import (
    complete_guide_payload,
    create_guide,
    create_project,
)
from projects.policy_bundle_fixtures import create_approved_policy_bundle
from project_create_fixtures import seed_active_guide_for_downstream_test
from projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)


async def create_locked_policy_context_fixture(
    client: AsyncClient, *, superseded=False,
) -> ProjectLockedPolicyContextRequest:
    """Create and activate one complete PROJECT policy lineage."""
    project = await create_project(client, name=f"Locked Context {uuid4()}")
    guide = await create_guide(client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(client, project["id"], guide["id"])
    if superseded:
        from projects.unified_policy_fixtures import supersede_unified_submission_policy
        await supersede_unified_submission_policy(project["id"], guide["id"], bundle["submission_artifact_policy"]["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )
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
    request = await create_locked_policy_context_fixture(project_client, superseded=True)
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
    request = await create_locked_policy_context_fixture(project_client, superseded=True)
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
    """Approved lineage cannot regress to pending before a locked reader observes it."""
    from sqlalchemy.exc import IntegrityError

    request = await create_locked_policy_context_fixture(project_client)
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(PreSubmitCheckerPolicy)
            .where(PreSubmitCheckerPolicy.id == str(request.pre_submit_policy_id))
            .values(lifecycle_status="pending_compilation", superseded_at=None)
        )
        with pytest.raises(IntegrityError, match="proposal approval lifecycle mismatch"):
            await session.commit()
        await session.rollback()
        current = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(request)
        assert current.pre_submit_policy_status == "compiled"


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
    """Keep resolving exact historical IDs after a real approved successor exists."""
    from sqlalchemy import select

    request = await create_locked_policy_context_fixture(project_client, superseded=True)
    async with db_session.get_session_factory()() as session:
        successor = (await session.scalars(select(EffectiveProjectSubmissionArtifactPolicy).where(
            EffectiveProjectSubmissionArtifactPolicy.project_id == str(request.project_id),
            EffectiveProjectSubmissionArtifactPolicy.lifecycle_status == "approved",
        ))).one()
        assert successor.id != str(request.effective_policy_id)
        assert successor.supersedes_effective_policy_id == str(request.effective_policy_id)
        historical = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(request)
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
