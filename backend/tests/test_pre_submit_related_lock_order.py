"""Real PostgreSQL races between pre-submit, grant revocation, and TASK reads."""

from __future__ import annotations

from app.adapters.artifacts import task_guide_documents_port
from app.adapters.contributions import locked_compensation_terms_port
from app.core.config import get_settings

from app.adapters.tasks import task_service

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.audit import task_transition_audit
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
from app.modules.artifacts.models import PreSubmitEvidenceSet, PreSubmitExecutionAttempt
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.actors.service import ResolvedActor
from app.modules.authorization import router as authorization_router
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.models import ProjectRoleGrant
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.project_role_schemas import ProjectRoleGrantRevokeBody
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from project_create_fixtures import grant_fixture_admin_role
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
from tests.test_pre_submit_attempt_authority_integration import _reserve_with_real_materializer
from tests.test_pre_submit_attempt_lock_order import _wait_for_project_block
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.test_pre_submit_attempt_recovery import _harness


class _PauseBeforeProject:
    """Hold ART after its TASK and actor/link fence, before the PROJECT fence."""

    def __init__(self, repository, entered: asyncio.Event, release: asyncio.Event):
        self.repository, self.entered, self.release = repository, entered, release

    async def lock_locked_policy_context(self, request):
        self.entered.set()
        await self.release.wait()
        return await self.repository.lock_locked_policy_context(request)


async def _assert_row_locked(engine, table: str, row_id: UUID) -> None:
    """NOWAIT proves the first operation owns the contributor fence."""
    assert table in {"actor_profiles", "actor_identity_links"}
    async with engine.connect() as observer:
        try:
            await observer.execute(
                text(f"select id from {table} where id=:id for update nowait"),
                {"id": str(row_id)},
            )
        except DBAPIError as exc:
            assert getattr(exc.orig, "sqlstate", None) == "55P03", exc
        else:
            pytest.fail(f"First operation did not lock {table} before PROJECT")


async def _ready_workflow(harness, session, calls):
    contributor = harness.contributor_authority(session)
    await contributor.preflight(request=harness.preparation_request)
    async with session.begin():
        await contributor.revalidate(
            request=harness.preparation_request,
            project_id=harness.request.effective_plan.lineage.project_id,
        )
    materializer = PreparedPreSubmitMaterializationAuthorization(
        session,
        request_id=harness.preparation_request.request_id,
        correlation_id=harness.preparation_request.correlation_id,
    )
    workflow = harness.workflow(
        session, calls, preparation_authorization=contributor,
    )
    workflow._materialization._authorization = materializer
    return workflow, materializer


async def _manager_runtime(harness, session):
    """Use the canonical AUTH PREP service and a real project-manager grant."""
    manager_id, link_id = new_record_id(), new_record_id()
    session.add_all([
        ActorProfile(
            id=str(manager_id), actor_kind="human", status="active",
            provisioning_method="automatic_first_access", created_by="test",
        ),
        ActorIdentityLink(
            id=str(link_id), actor_profile_id=str(manager_id), issuer="flow-test",
            subject=f"revoke-lock-{manager_id}", subject_kind="human",
            status="active", linked_by="test", last_verified_at=datetime.now(UTC),
        ),
    ])
    await session.flush()
    await grant_fixture_admin_role(
        session, manager_id, scope="project",
        project_id=harness.request.effective_plan.lineage.project_id,
    )
    await session.commit()
    context = HumanAuthorizationContext(
        actor_profile_id=manager_id, actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE, identity_link_id=link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )
    repository = AdminAuthorizationRepository(session)
    authority = AuthorizationService(session, context, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context, authority, repository)
    profile = await session.get(ActorProfile, str(manager_id))
    link = await session.get(ActorIdentityLink, str(link_id))
    assert profile is not None and link is not None
    await session.commit()
    return prepared, ResolvedActor(profile, link)


async def _submitter_grant(harness):
    """Read the exact active grant whose revocation races with ART."""
    async with harness.factory() as session:
        grant_id = await session.scalar(select(ProjectRoleGrant.id).where(
            ProjectRoleGrant.project_id == str(harness.request.effective_plan.lineage.project_id),
            ProjectRoleGrant.actor_profile_id == str(harness.actor_id),
            ProjectRoleGrant.role == "submitter", ProjectRoleGrant.status == "active",
        ))
    assert grant_id is not None
    return grant_id


def _named_factory(database_url, name):
    """Give each competing owner an independently observable database session."""
    engine = create_async_engine(database_url, connect_args={"server_settings": {"application_name": name}})
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _wait_for_named_owner(harness, database_url, waiter, blocker):
    """Bind the actual waiter to the independently observed blocking backend."""
    async with harness.engine.connect() as observer:
        pid = await observer.scalar(text(
            "select pid from pg_stat_activity where application_name=:name"
        ), {"name": blocker})
    assert pid is not None
    await wait_for_named_database_lock(database_url, waiter, expected_blocker_pid=pid)


@pytest.mark.asyncio
@pytest.mark.parametrize("ordering", ["materialization_first", "revoke_first"])
async def test_revocation_fences_art_materialization_and_evidence_persistence(
    tmp_path: Path, isolated_database_env: str, monkeypatch, ordering: str,
) -> None:
    """Revocation fences both checking and the later evidence-persistence transaction."""
    harness = await _harness(tmp_path, isolated_database_env)
    art_engine = revoke_engine = None
    art_task = revoke_task = None
    release_art, release_revoke = asyncio.Event(), asyncio.Event()
    try:
        await _seed_materializer(harness.factory)
        project_id = harness.request.effective_plan.lineage.project_id
        grant_id = await _submitter_grant(harness)
        revoke_name = f"pol07a_revoke_{new_record_id().hex[:12]}"
        art_name = f"pol07a_revoke_art_{new_record_id().hex[:12]}"
        art_engine, art_factory = _named_factory(isolated_database_env, art_name)
        revoke_engine, revoke_factory = _named_factory(isolated_database_env, revoke_name)
        art_before_project, revoke_has_project = asyncio.Event(), asyncio.Event()
        async with art_factory() as art_session, revoke_factory() as revoke_session:
            calls: list[int] = []
            workflow, materializer = await _ready_workflow(harness, art_session, calls)
            prepared_revoke, resolved_manager = await _manager_runtime(harness, revoke_session)
            reservation = await _reserve_with_real_materializer(
                workflow, harness.request, harness.preparation_request,
            )
            workflow._project_contexts = _PauseBeforeProject(
                workflow._project_contexts, art_before_project, release_art,
            )
            original_lock_project = AdminAuthorizationRepository.lock_project
            revoke_pid: int | None = None

            async def pause_revoke_project(repository, locked_project_id):
                nonlocal revoke_pid
                project = await original_lock_project(repository, locked_project_id)
                if repository._session is revoke_session:
                    revoke_pid = int(await revoke_session.scalar(text("select pg_backend_pid()")))
                    revoke_has_project.set()
                    await release_revoke.wait()
                return project

            monkeypatch.setattr(
                AdminAuthorizationRepository, "lock_project", pause_revoke_project,
            )
            try:
                async def execute_art():
                    return await workflow.execute_reserved(
                        harness.request, reservation,
                        preparation_request=harness.preparation_request,
                    )

                async def revoke():
                    return await authorization_router.revoke_project_role_grant(
                        project_id=project_id, grant_id=UUID(str(grant_id)),
                        payload=ProjectRoleGrantRevokeBody(reason="Concurrent pre-submit grant revocation"),
                        idempotency_key=new_record_id(), resolved=resolved_manager,
                        prepared=prepared_revoke, session=revoke_session,
                    )

                if ordering == "materialization_first":
                    art_task = asyncio.create_task(execute_art())
                    await asyncio.wait_for(art_before_project.wait(), timeout=30)
                    await _assert_row_locked(harness.engine, "actor_profiles", harness.actor_id)
                    await _assert_row_locked(harness.engine, "actor_identity_links", harness.identity_link_id)
                    revoke_task = asyncio.create_task(revoke())
                    await _wait_for_named_owner(harness, isolated_database_env, revoke_name, art_name)
                    assert not revoke_has_project.is_set()
                    release_art.set()
                    await asyncio.wait_for(revoke_has_project.wait(), timeout=30)
                    assert revoke_pid is not None
                    await wait_for_named_database_lock(
                        isolated_database_env, art_name, expected_blocker_pid=revoke_pid,
                    )
                else:
                    revoke_task = asyncio.create_task(revoke())
                    await asyncio.wait_for(revoke_has_project.wait(), timeout=30)
                    await _assert_row_locked(harness.engine, "actor_profiles", harness.actor_id)
                    await _assert_row_locked(harness.engine, "actor_identity_links", harness.identity_link_id)
                    release_art.set()
                    art_task = asyncio.create_task(execute_art())
                    assert revoke_pid is not None
                    await wait_for_named_database_lock(
                        isolated_database_env, art_name, expected_blocker_pid=revoke_pid,
                    )
                    assert not art_before_project.is_set()
                release_revoke.set()
                art_outcome, revoke_outcome = await asyncio.wait_for(
                    asyncio.gather(art_task, revoke_task, return_exceptions=True),
                    timeout=30,
                )
                # Materialization and evidence persistence reauthorize in separate
                # transactions. Revocation after checking still prevents evidence.
                assert isinstance(art_outcome, ArtifactAuthorityDeniedError), art_outcome
                assert calls == ([1] if ordering == "materialization_first" else [])
                assert not isinstance(revoke_outcome, BaseException), revoke_outcome
                assert revoke_outcome.status == "revoked"
            finally:
                release_art.set()
                release_revoke.set()
                for pending in (art_task, revoke_task):
                    if pending is not None and not pending.done():
                        pending.cancel()
                await asyncio.gather(
                    *(task for task in (art_task, revoke_task) if task is not None),
                    return_exceptions=True,
                )
                materializer.close()
                prepared_revoke.close()
        async with harness.factory() as session:
            grant = await session.get(ProjectRoleGrant, grant_id)
            assert grant is not None and grant.status == "revoked" and grant.version == 2
            assert await session.scalar(select(func.count()).select_from(PreSubmitEvidenceSet)) == 0
    finally:
        release_art.set()
        release_revoke.set()
        if art_engine is not None:
            await art_engine.dispose()
        if revoke_engine is not None:
            await revoke_engine.dispose()
        await harness.close()


@pytest.mark.asyncio
async def test_work_context_task_lock_precedes_art_actor_lock(
    tmp_path: Path, isolated_database_env: str,
) -> None:
    """TASK T then AUTH C and ART T then C complete without a cycle."""
    harness = await _harness(tmp_path, isolated_database_env)
    art_engine = None
    art_task = task_command = None
    release_task = asyncio.Event()
    try:
        await _seed_materializer(harness.factory)
        art_name = f"pol07a_task_art_{new_record_id().hex[:12]}"
        art_engine = create_async_engine(
            isolated_database_env,
            connect_args={"server_settings": {"application_name": art_name}},
        )
        art_factory = async_sessionmaker(art_engine, expire_on_commit=False)
        task_locked = asyncio.Event()
        async with harness.factory() as task_session, art_factory() as art_session:
            calls: list[int] = []
            workflow, materializer = await _ready_workflow(harness, art_session, calls)
            reservation = await _reserve_with_real_materializer(
                workflow, harness.request, harness.preparation_request,
            )
            context = HumanAuthorizationContext(
                actor_profile_id=harness.actor_id, actor_kind=ActorKind.HUMAN,
                actor_status=ActorStatus.ACTIVE,
                identity_link_id=harness.identity_link_id,
                identity_link_status=IdentityLinkStatus.ACTIVE,
                request_id=new_record_id(), correlation_id=new_record_id(),
            )
            task_authority = PreparedTaskAuthorization(task_session, context)
            real_prepare = task_authority.prepare
            task_pid: int | None = None

            async def pause_before_auth(facts):
                nonlocal task_pid
                task_pid = int(await task_session.scalar(text("select pg_backend_pid()")))
                task_locked.set()
                await release_task.wait()
                return await real_prepare(facts)

            task_authority.prepare = pause_before_auth
            commands = AuthorizedTaskCommands(
                task_session,
                authorization=task_authority,
                audit=task_transition_audit(task_session),
                actor_profile_id=harness.actor_id,
                contexts=task_service(task_session, settings=get_settings()),
                guide_documents=task_guide_documents_port(task_session, get_settings()),
                compensation_terms=locked_compensation_terms_port(task_session),
            )
            try:
                task_command = asyncio.create_task(commands.contributor_work_context(harness.request.task_id))
                await asyncio.wait_for(task_locked.wait(), timeout=30)
                assert task_pid is not None
                art_task = asyncio.create_task(workflow.execute_reserved(
                    harness.request, reservation,
                    preparation_request=harness.preparation_request,
                ))
                await _wait_for_project_block(
                    harness.engine, application_name=art_name, blocker_pid=task_pid,
                )
                release_task.set()
                task_result, art_result = await asyncio.wait_for(
                    asyncio.gather(task_command, art_task, return_exceptions=True),
                    timeout=30,
                )
                assert not isinstance(task_result, BaseException), task_result
                assert task_result.task.status == "in_progress"
                assert task_result.lifecycle.assigned_to_current_actor is True
                assert not isinstance(art_result, BaseException), art_result
                assert art_result.pass_capability is not None
                assert calls == [1]
            finally:
                release_task.set()
                await asyncio.gather(
                    *(task for task in (art_task, task_command) if task is not None),
                    return_exceptions=True,
                )
                materializer.close()
        async with harness.factory() as session:
            attempts = (await session.scalars(select(PreSubmitExecutionAttempt))).all()
            assert len(attempts) == 1 and attempts[0].status == "completed"
            assert await session.scalar(select(func.count()).select_from(PreSubmitEvidenceSet)) == 1
    finally:
        release_task.set()
        if art_engine is not None:
            await art_engine.dispose()
        await harness.close()
