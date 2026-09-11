"""Independent-session contributor lifecycle versus task-authority races."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from auth_concurrency_support import wait_for_named_database_lock
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine

from app.adapters.audit import task_transition_audit
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.submission_creation_authorization import (
    PreparedSubmissionCreationAuthorization,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api import (
    SubmissionCreationAuthorityFacts,
    SubmissionCreationUnavailable,
    TaskAuthorityDenied,
    TaskSubmissionContextRequest,
)
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.models import AuditEvent, TaskAssignment
from app.modules.tasks.repository import TaskRepository
from app.schemas.auth import ActorContext
from tests.test_tasks import (
    task_client as task_client,
    task_database_env as task_database_env,
    actor_id,
    admit_and_grant_project_submitter,
    create_active_project,
    create_ready_task,
    create_started_task,
)


async def _task_contributor_race_snapshot(
    connection: AsyncConnection,
    task_id: str,
) -> dict[str, object]:
    """Capture every task-owned write surface relevant to contributor races."""
    task = (
        await connection.execute(
            text("select status, assigned_to from workstream_tasks where id = :task_id"),
            {"task_id": task_id},
        )
    ).one()
    assignments = (
        await connection.execute(
            text(
                "select id, contributor_id, assigned_by, status, accepted_at, released_at "
                "from task_assignments where task_id = :task_id order by id"
            ),
            {"task_id": task_id},
        )
    ).all()
    submissions = (
        await connection.execute(
            text(
                "select id, contributor_id, version, status, locked_at "
                "from submissions where task_id = :task_id order by version"
            ),
            {"task_id": task_id},
        )
    ).all()
    evidence_count = await connection.scalar(
        text(
            "select count(*) from evidence_items evidence "
            "join submissions submission on submission.id = evidence.submission_id "
            "where submission.task_id = :task_id"
        ),
        {"task_id": task_id},
    )
    checker_run_count = await connection.scalar(
        text("select count(*) from checker_runs where task_id = :task_id"),
        {"task_id": task_id},
    )
    checker_result_count = await connection.scalar(
        text("select count(*) from checker_results where task_id = :task_id"),
        {"task_id": task_id},
    )
    audit_events = (
        await connection.execute(
            text(
                "select id, event_type, from_status, to_status, actor_id, event_payload "
                "from audit_events where entity_type = 'task' and entity_id = :task_id "
                "order by created_at, id"
            ),
            {"task_id": task_id},
        )
    ).all()
    idempotency_count = await connection.scalar(
        text("select count(*) from authority_idempotency_records")
    )
    return {
        "task": tuple(task),
        "assignments": [tuple(row) for row in assignments],
        "submissions": [tuple(row) for row in submissions],
        "evidence_count": evidence_count,
        "checker_run_count": checker_run_count,
        "checker_result_count": checker_result_count,
        "audit_events": [tuple(row) for row in audit_events],
        "idempotency_count": idempotency_count,
    }


async def _read_task_contributor_race_snapshot(
    database_url: str,
    task_id: str,
) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await _task_contributor_race_snapshot(connection, task_id)
    finally:
        await engine.dispose()


async def _run_contributor_lifecycle_write(
    database_url: str,
    *,
    actor_profile_id: str,
    identity_link_id: str,
    transition: str,
    task_id: str,
    application_name: str,
    entered: asyncio.Event,
    locked: asyncio.Event | None = None,
    release: asyncio.Event | None = None,
    observe_task_after_lock: bool = False,
) -> dict[str, object] | None:
    """Apply one canonical-order lifecycle write in an independent transaction."""
    engine = create_async_engine(database_url)
    observed: dict[str, object] | None = None
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("select set_config('application_name', :name, true)"),
                {"name": application_name},
            )
            entered.set()
            await connection.execute(
                text("select id from actor_profiles where id = :id for update"),
                {"id": actor_profile_id},
            )
            await connection.execute(
                text("select id from actor_identity_links where id = :id for update"),
                {"id": identity_link_id},
            )
            if locked is not None:
                locked.set()
            if release is not None:
                await release.wait()
            if observe_task_after_lock:
                observed = await _task_contributor_race_snapshot(connection, task_id)

            if transition == "suspend":
                await connection.execute(
                    text(
                        "update actor_profiles set status = 'suspended', "
                        "suspended_by = :actor_id, suspended_at = clock_timestamp(), "
                        "suspension_reason = 'contributor lock race' where id = :actor_id"
                    ),
                    {"actor_id": actor_profile_id},
                )
            elif transition == "deactivate":
                await connection.execute(
                    text(
                        "update actor_profiles set status = 'deactivated', "
                        "deactivated_by = :actor_id, deactivated_at = clock_timestamp(), "
                        "deactivation_reason = 'contributor lock race' where id = :actor_id"
                    ),
                    {"actor_id": actor_profile_id},
                )
            else:
                assert transition == "revoke_link"
                await connection.execute(
                    text(
                        "update actor_identity_links set status = 'revoked', "
                        "revoked_by = :actor_id, revoked_at = clock_timestamp(), "
                        "revoked_reason = 'contributor lock race' where id = :link_id"
                    ),
                    {"actor_id": actor_profile_id, "link_id": identity_link_id},
                )
        return observed
    finally:
        await engine.dispose()


async def _consume_submission_authority(session, context, task_id):
    """Prove AUTH commit under real TASK locks, not ART/Submission creation."""
    async with session.begin():
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_id, TaskAssignment.status == "active",
        ))
        assert assignment is not None
        task_context = await TaskRepository(session).lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=UUID(task_id), assignment_id=UUID(assignment.id),
                contributor_id=context.actor_profile_id, predecessor_submission_id=None,
            )
        )
        facts = SubmissionCreationAuthorityFacts(
            task_id=UUID(task_id), assignment_id=UUID(assignment.id),
            contributor_id=context.actor_profile_id, admission_id=uuid4(),
            predecessor_submission_id=None, submission_id=uuid4(),
            submission_version=1, task_context=task_context,
        )
        authority = PreparedSubmissionCreationAuthorization(session, context)
        await authority.authorize(facts)
        handle = await authority.prepare(facts)
        try:
            await authority.consume(handle, facts)
        finally:
            authority.close(handle)
    events = list(await session.scalars(select(AuditEvent).where(
        AuditEvent.request_id == context.request_id,
    )))
    assert len(events) == 1
    return events[0]


async def _run_task_contributor_write(
    database_url: str,
    *,
    actor: ActorContext,
    task_id: str,
    operation: str,
    application_name: str,
    entered: asyncio.Event,
) -> object:
    """Commit a claim or a submission AUTH decision in a named PostgreSQL session."""
    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"application_name": application_name}},
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            entered.set()
            link_id = await session.scalar(
                select(ActorIdentityLink.id).where(
                    ActorIdentityLink.actor_profile_id == actor.actor_id,
                )
            )
            assert link_id is not None
            await session.rollback()
            # Cached active facts must not overrule the concurrently locked rows.
            context = HumanAuthorizationContext(
                actor_profile_id=UUID(actor.actor_id),
                actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
                identity_link_id=UUID(link_id), identity_link_status=IdentityLinkStatus.ACTIVE,
                request_id=uuid4(), correlation_id=uuid4(),
            )
            if operation == "claim":
                return await AuthorizedTaskCommands(
                    session,
                    authorization=PreparedTaskAuthorization(session, context),
                    audit=task_transition_audit(session),
                    actor_profile_id=context.actor_profile_id,
                ).claim(UUID(task_id), "contributor lock race")
            assert operation == "submission_authority"
            return await _consume_submission_authority(session, context, task_id)
    finally:
        await engine.dispose()


async def _read_contributor_lifecycle_state(
    database_url: str,
    actor_profile_id: str,
    identity_link_id: str,
) -> tuple[str, str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            profile_status = await connection.scalar(
                text("select status from actor_profiles where id = :id"),
                {"id": actor_profile_id},
            )
            link_status = await connection.scalar(
                text("select status from actor_identity_links where id = :id"),
                {"id": identity_link_id},
            )
            assert isinstance(profile_status, str)
            assert isinstance(link_status, str)
            return profile_status, link_status
    finally:
        await engine.dispose()


async def _restore_contributor_after_lifecycle_race(
    database_url: str,
    actor_profile_id: str,
    identity_link_id: str,
) -> None:
    """Return a terminal test actor to active state under explicit test custody."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            reset = await connection.begin()
            try:
                await connection.execute(
                    text("alter table actor_profiles disable trigger actor_profile_history_guard")
                )
                await connection.execute(
                    text(
                        "alter table actor_identity_links disable trigger "
                        "actor_identity_link_history_guard"
                    )
                )
                await connection.execute(
                    text(
                        "update actor_profiles set status = 'active', "
                        "suspended_by = null, suspended_at = null, "
                        "suspension_reason = null, reactivated_by = null, "
                        "reactivated_at = null, reactivation_reason = null, "
                        "deactivated_by = null, deactivated_at = null, "
                        "deactivation_reason = null where id = :id"
                    ),
                    {"id": actor_profile_id},
                )
                await connection.execute(
                    text(
                        "update actor_identity_links set status = 'active', "
                        "revoked_by = null, revoked_at = null, revoked_reason = null, "
                        "reactivated_by = null, reactivated_at = null, "
                        "reactivation_reason = null where id = :id"
                    ),
                    {"id": identity_link_id},
                )
                await reset.commit()
            except BaseException:
                await reset.rollback()
                raise
            finally:
                enable = await connection.begin()
                try:
                    await connection.execute(
                        text(
                            "alter table actor_identity_links enable trigger "
                            "actor_identity_link_history_guard"
                        )
                    )
                    await connection.execute(
                        text(
                            "alter table actor_profiles enable trigger actor_profile_history_guard"
                        )
                    )
                    await enable.commit()
                except BaseException:
                    await enable.rollback()
                    raise
    finally:
        await engine.dispose()


@pytest.fixture
async def contributor_lifecycle_race_cleanup(
    task_database_env: str,
) -> AsyncIterator[list[tuple[str, str]]]:
    """Restore lifecycle race actors before the migration fixture downgrades."""
    actors: list[tuple[str, str]] = []
    yield actors
    for actor_profile_id, identity_link_id in actors:
        await _restore_contributor_after_lifecycle_race(
            task_database_env,
            actor_profile_id,
            identity_link_id,
        )


@dataclass
class ContributorRace:
    contributor_id: str
    identity_link_id: str
    actor: ActorContext
    task_id: str
    before: dict[str, object]
    task_application_name: str
    lifecycle_application_name: str


async def _prepare_contributor_race(
    task_client,
    task_database_env,
    contributor_lifecycle_race_cleanup,
    monkeypatch,
    operation,
    transition,
    ordering,
) -> ContributorRace:
    """Construct one race's prerequisites without performing the competing writes."""
    project = await create_active_project(task_client)
    subject = f"race-{operation}-{transition}-{ordering}"
    contributor_id = actor_id(subject)
    if operation == "claim":
        task = await create_ready_task(task_client, project["id"])
        await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], subject)
    else:
        assert operation == "submission_authority"
        task = await create_started_task(task_client, project["id"], monkeypatch, subject)
    async with db_session.get_session_factory()() as session:
        identity_link_id = await session.scalar(
            select(ActorIdentityLink.id).where(ActorIdentityLink.actor_profile_id == contributor_id)
        )
    assert identity_link_id is not None
    contributor_lifecycle_race_cleanup.append((contributor_id, identity_link_id))
    actor = ActorContext(
        actor_id=contributor_id,
        external_subject=subject,
        external_issuer="flow-test",
        roles=("worker",),
        claim_snapshot={"roles": ["worker"]},
        auth_source="dev_mock",
        is_dev_auth=True,
    )
    task_id = task["id"]
    before = await _read_task_contributor_race_snapshot(task_database_env, task_id)
    operation_label = "submit-auth" if operation == "submission_authority" else operation
    task_application_name = f"ws-race-{operation_label}-{transition}-{ordering}-task"
    lifecycle_application_name = f"ws-race-{operation_label}-{transition}-{ordering}-lifecycle"
    return ContributorRace(
        contributor_id,
        identity_link_id,
        actor,
        task_id,
        before,
        task_application_name,
        lifecycle_application_name,
    )


async def _assert_final_lifecycle(task_database_env, race, transition):
    profile_status, link_status = await _read_contributor_lifecycle_state(
        task_database_env, race.contributor_id, race.identity_link_id
    )
    if transition == "suspend":
        assert (profile_status, link_status) == ("suspended", "active")
    elif transition == "deactivate":
        assert (profile_status, link_status) == ("deactivated", "active")
    else:
        assert (profile_status, link_status) == ("active", "revoked")


@pytest.mark.parametrize(
    ("operation", "transition"),
    [
        (operation, transition)
        for operation in ("claim", "submission_authority")
        for transition in ("suspend", "deactivate", "revoke_link")
    ],
)
async def test_lifecycle_change_before_contributor_operation_denies_without_effects(
    task_client,
    task_database_env,
    contributor_lifecycle_race_cleanup,
    monkeypatch,
    operation,
    transition,
):
    race = await _prepare_contributor_race(
        task_client,
        task_database_env,
        contributor_lifecycle_race_cleanup,
        monkeypatch,
        operation,
        transition,
        "lifecycle_first",
    )
    lifecycle_entered = asyncio.Event()
    lifecycle_locked = asyncio.Event()
    release_lifecycle = asyncio.Event()
    lifecycle_call = asyncio.create_task(
        _run_contributor_lifecycle_write(
            task_database_env,
            actor_profile_id=race.contributor_id,
            identity_link_id=race.identity_link_id,
            transition=transition,
            task_id=race.task_id,
            application_name=race.lifecycle_application_name,
            entered=lifecycle_entered,
            locked=lifecycle_locked,
            release=release_lifecycle,
        ),
        name=race.lifecycle_application_name,
    )
    await lifecycle_entered.wait()
    await lifecycle_locked.wait()
    task_entered = asyncio.Event()
    task_call = asyncio.create_task(
        _run_task_contributor_write(
            task_database_env,
            actor=race.actor,
            task_id=race.task_id,
            operation=operation,
            application_name=race.task_application_name,
            entered=task_entered,
        ),
        name=race.task_application_name,
    )
    await task_entered.wait()
    lock_error: AssertionError | None = None
    try:
        await wait_for_named_database_lock(task_database_env, race.task_application_name)
    except AssertionError as exc:
        lock_error = exc
    finally:
        release_lifecycle.set()
    lifecycle_result, task_result = await asyncio.gather(
        lifecycle_call, task_call, return_exceptions=True
    )
    if lock_error is not None:
        raise lock_error
    assert lifecycle_result is None
    expected_denial = TaskAuthorityDenied if operation == "claim" else SubmissionCreationUnavailable
    assert isinstance(task_result, expected_denial), task_result
    assert (
        await _read_task_contributor_race_snapshot(task_database_env, race.task_id) == race.before
    )
    await _assert_final_lifecycle(task_database_env, race, transition)


@pytest.mark.parametrize(
    ("operation", "transition"),
    [
        (operation, transition)
        for operation in ("claim", "submission_authority")
        for transition in ("suspend", "deactivate", "revoke_link")
    ],
)
async def test_contributor_operation_commits_before_lifecycle_change(
    task_client,
    task_database_env,
    contributor_lifecycle_race_cleanup,
    monkeypatch,
    operation,
    transition,
):
    race = await _prepare_contributor_race(
        task_client,
        task_database_env,
        contributor_lifecycle_race_cleanup,
        monkeypatch,
        operation,
        transition,
        "task_write_first",
    )
    task_locked = asyncio.Event()
    release_task = asyncio.Event()
    if operation == "claim":
        original_prepare = PreparedTaskAuthorization.prepare

        async def hold_prepared_claim(authority, facts):
            handle = await original_prepare(authority, facts)
            task_locked.set()
            await release_task.wait()
            return handle

        monkeypatch.setattr(PreparedTaskAuthorization, "prepare", hold_prepared_claim)
    else:
        original_submission_prepare = PreparedSubmissionCreationAuthorization.prepare

        async def hold_prepared_submission_authority(authority, facts):
            handle = await original_submission_prepare(authority, facts)
            task_locked.set()
            await release_task.wait()
            return handle

        monkeypatch.setattr(
            PreparedSubmissionCreationAuthorization, "prepare", hold_prepared_submission_authority
        )
    task_entered = asyncio.Event()
    task_call = asyncio.create_task(
        _run_task_contributor_write(
            task_database_env,
            actor=race.actor,
            task_id=race.task_id,
            operation=operation,
            application_name=race.task_application_name,
            entered=task_entered,
        ),
        name=race.task_application_name,
    )
    await task_entered.wait()
    await task_locked.wait()
    lifecycle_entered = asyncio.Event()
    lifecycle_call = asyncio.create_task(
        _run_contributor_lifecycle_write(
            task_database_env,
            actor_profile_id=race.contributor_id,
            identity_link_id=race.identity_link_id,
            transition=transition,
            task_id=race.task_id,
            application_name=race.lifecycle_application_name,
            entered=lifecycle_entered,
            observe_task_after_lock=True,
        ),
        name=race.lifecycle_application_name,
    )
    await lifecycle_entered.wait()
    lock_error = None
    try:
        await wait_for_named_database_lock(task_database_env, race.lifecycle_application_name)
    except AssertionError as exc:
        lock_error = exc
    finally:
        release_task.set()
    task_result, observed_after_task_commit = await asyncio.gather(
        task_call, lifecycle_call, return_exceptions=True
    )
    if lock_error is not None:
        raise lock_error
    if isinstance(task_result, BaseException):
        raise task_result
    if isinstance(observed_after_task_commit, BaseException):
        raise observed_after_task_commit
    assert isinstance(observed_after_task_commit, dict)
    if operation == "claim":
        assert task_result.assignment.contributor_id == race.contributor_id
        assert observed_after_task_commit["task"] == ("claimed", race.contributor_id)
        assignments = observed_after_task_commit["assignments"]
        assert isinstance(assignments, list)
        assert len(assignments) == 1
        assert assignments[0][1] == race.contributor_id
    else:
        assert isinstance(task_result, AuditEvent)
        assert task_result.event_type == "SensitiveAuthorizationAllowed"
        assert task_result.action_id == "submission.create"
        assert task_result.actor_id == race.contributor_id
        assert task_result.matched_grant_id is not None
        # This branch commits AUTH evidence only. Artifact consumption,
        # Submission creation and checker dispatch are different owner proofs.
        assert observed_after_task_commit == race.before
    await _assert_final_lifecycle(task_database_env, race, transition)
