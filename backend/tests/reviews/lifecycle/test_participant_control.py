"""Actual acceptance effects against authorized controller changes and shutdown."""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.db.session import get_session_factory
from app.modules.reviews.acceptance.repository import FinalAcceptanceRepository
from app.modules.reviews.api.acceptance import FinalAcceptanceConflict
from app.modules.reviews.api.lifecycle import (
    JointLifecycleControlFacts,
    JointLifecyclePhase,
    JointLifecycleUnavailable,
)
from app.modules.reviews.lifecycle.fence import (
    JOINT_LIFECYCLE_LOCK_KEY,
    PostgresJointLifecycleMutationFence,
)
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl
from app.modules.tasks.api.routing_outcome import TaskRoutingLifecycleDeferred
from tests.tasks.post_submit_routing.outcome_support import authorized_routing_source, apply_outcome
from tests.reviews.acceptance.participation_support import (
    stored_effects,
    denial_only_request,
)
from tests.reviews.lifecycle.test_fence import observe_advisory_wait
from tests.reviews.lifecycle.transition_support import (
    command_for,
    controller,
    snapshot,
    transition,
)


def _migration_config() -> Config:
    return Config(Path(__file__).resolve().parents[3] / "alembic.ini")


def _activation_migration():
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/0039_false_guide_activation.py"
    )
    spec = importlib.util.spec_from_file_location("activation_migration_0039", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _routing_acceptance_validity(session, manifest_id):
    return dict(
        (
            await session.execute(
                text(
                    "SELECT "
                    "public.task_routing_acceptance_matches("
                    "m.id,m.final_acceptance_id,m.authorization_decision_id,"
                    "m.router_actor_id,m.project_id,m.task_id,m.submission_id,"
                    "(m.authority_context#>>"
                    "'{source,locked_policy,locked_review_policy_id}')::uuid,"
                    "m.authorized_lifecycle_generation,true) AS new_valid,"
                    "public.task_routing_acceptance_matches("
                    "m.id,m.final_acceptance_id,m.authorization_decision_id,"
                    "m.router_actor_id,m.project_id,m.task_id,m.submission_id,"
                    "(m.authority_context#>>"
                    "'{source,locked_policy,locked_review_policy_id}')::uuid,"
                    "m.authorized_lifecycle_generation,false) AS replay_valid "
                    "FROM public.task_post_submit_routing_manifests m "
                    "WHERE m.id=:manifest"
                ),
                {"manifest": manifest_id},
            )
        ).mappings().one()
    )


async def _reset_to_0038(isolated_database_env, migration_lock) -> None:
    from tests.test_alembic import _execute

    await db_session.dispose_engine()
    with migration_lock():
        await _execute(
            isolated_database_env,
            "drop schema public cascade; create schema public",
        )
        await asyncio.to_thread(
            alembic_command.upgrade,
            _migration_config(),
            "0038_task_batch_transitions",
        )
    await db_session.dispose_engine()
    async with get_session_factory()() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0038_task_batch_transitions"
        )
        assert await session.scalar(
            text(
                "SELECT pg_catalog.to_regprocedure("
                "'public.joint_lifecycle_new_effects_enabled("
                "public.joint_lifecycle_release_control)') IS NULL"
            )
        ) is True


async def _provision_0038_operator(admin_access):
    from scripts.bootstrap_access_administrator import _run as run_bootstrap
    from tests.authorization.admin_access.support import AdminAccess

    admin = await admin_access.signed.actor("administrator", roles=("viewer",))
    target = await admin_access.signed.actor("target", roles=("admin",))
    code, bootstrap = await run_bootstrap(admin.id, execute=True)
    assert code == 0 and bootstrap["result_code"] == "bootstrapped"
    access = AdminAccess(
        admin_access.signed,
        admin,
        target,
        bootstrap["grant_id"],
    )
    await access.signed.grant(access.admin, access.target)
    return access


async def _predecessor_lock_controller(owner):
    """Project only 0038's phase/generation fact while retaining its real locks."""
    transaction = owner._session.get_transaction()
    if (
        transaction is None
        or not transaction.is_active
        or owner._session.in_nested_transaction()
    ):
        raise JointLifecycleUnavailable(
            "lifecycle requires a root transaction and exact generation"
        )
    connection = await owner._session.connection()
    if connection.in_nested_transaction():
        raise JointLifecycleUnavailable("lifecycle requires a root database transaction")
    try:
        await owner._session.execute(text("SELECT pg_catalog.pg_export_snapshot()"))
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) != "25001":
            raise
        raise JointLifecycleUnavailable(
            "lifecycle requires a root database transaction"
        ) from exc
    await owner._session.execute(
        text("SELECT pg_catalog.pg_advisory_xact_lock(:key)"),
        {"key": JOINT_LIFECYCLE_LOCK_KEY},
    )
    row = (
        await owner._session.execute(
            select(
                JointLifecycleReleaseControl.id,
                JointLifecycleReleaseControl.phase,
                JointLifecycleReleaseControl.generation,
                JointLifecycleReleaseControl.created_at,
            )
            .where(JointLifecycleReleaseControl.singleton.is_(True))
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        raise JointLifecycleUnavailable(
            "lifecycle controller missing or generation changed"
        )
    try:
        return JointLifecycleControlFacts(
            singleton_id=row.id,
            phase=JointLifecyclePhase(row.phase),
            generation=row.generation,
            new_effects_enabled=row.phase == "live" and row.generation > 0,
            created_at=row.created_at,
        )
    except (ValueError, ValidationError) as exc:
        raise JointLifecycleUnavailable("lifecycle controller malformed") from exc


def _set_runtime_manifest(monkeypatch, digest) -> None:
    import app.modules.reviews.lifecycle.service as lifecycle_service
    import tests.reviews.lifecycle.transition_support as transition_support

    monkeypatch.setattr(
        lifecycle_service,
        "FIRST_CONTRIBUTION_MANIFEST_DIGEST",
        digest,
    )
    monkeypatch.setattr(
        transition_support,
        "FIRST_CONTRIBUTION_MANIFEST_DIGEST",
        digest,
    )


@pytest.mark.parametrize("instruments", [(), ("money",), ("money", "project_points")])
async def test_stopped_terminal_replay_is_select_only(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    instruments,
):
    access = live_acceptance_lifecycle
    async with authorized_routing_source(
        tmp_path,
        isolated_database_env,
        contribution_awards=instruments,
    ) as h:
        async with h.factory() as session, session.begin():
            original = await apply_outcome(session, h, 2)
        for phase in ("draining", "disabled"):
            receipt = await transition(await command_for(access.target.id, phase))
            engine = h.factory.kw["bind"].sync_engine
            writes = []

            def observe(_connection, _cursor, statement, _parameters, _context, _many):
                if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                    writes.append(statement)

            event.listen(engine, "before_cursor_execute", observe)
            try:
                async with h.factory() as session, session.begin():
                    replay = await apply_outcome(session, h, receipt.generation)
            finally:
                event.remove(engine, "before_cursor_execute", observe)
            assert replay == original.model_copy(update={"replayed": True})
            assert writes == []
        # Valid retained receipts remain evidence after a later lifecycle restart.
        await transition(await command_for(access.target.id, "shadow"))
        restarted = await transition(await command_for(access.target.id, "live"))
        assert restarted.phase == "live"
        async with h.factory() as session:
            facts = await stored_effects(session, h.request.task_id)
            assert facts["acceptances"] == facts["contributions"] == 1
            assert facts["awards"] == len(instruments)


@pytest.mark.postgres_schema_contract
async def test_0038_old_manifest_live_upgrade_denies_new_effects_until_renewed(
    tmp_path,
    isolated_database_env,
    admin_access,
    migration_lock,
    monkeypatch,
):
    """Upgrade retains old facts/replay but requires current Operator review for new effects."""
    migration = _activation_migration()
    await _reset_to_0038(isolated_database_env, migration_lock)
    # Current ACTORS reads need this nullable projection while seeding 0038.
    # Remove it before the real migration introduces the column.
    async with db_session.get_engine().begin() as connection:
        await connection.execute(text(
            "ALTER TABLE actor_identity_links ADD COLUMN email_observed_issued_at bigint"
        ))
    access = await _provision_0038_operator(admin_access)
    _set_runtime_manifest(monkeypatch, migration._OLD_MANIFEST)
    with monkeypatch.context() as predecessor:
        predecessor.setattr(
            PostgresJointLifecycleMutationFence,
            "lock_controller",
            _predecessor_lock_controller,
        )
        await transition(await command_for(access.target.id, "shadow"))
        old_live_command = await command_for(access.target.id, "live")
        old_live_receipt = await transition(old_live_command)
    assert old_live_receipt.generation == 2
    retained_lifecycle = await snapshot()

    _set_runtime_manifest(monkeypatch, migration._NEW_MANIFEST)
    await db_session.dispose_engine()
    with migration_lock():
        await asyncio.to_thread(
            alembic_command.upgrade,
            _migration_config(),
            "0039_false_guide_activation",
        )
    assert await transition(old_live_command) == old_live_receipt
    assert await snapshot() == retained_lifecycle

    async with db_session.get_engine().begin() as connection:
        await connection.execute(text(
            "ALTER TABLE actor_identity_links DROP COLUMN email_observed_issued_at"
        ))
    # The retained 0039 control is unchanged; current runtime owners require
    # their complete schema before exercising new submissions and acceptance.
    await db_session.dispose_engine()
    with migration_lock():
        await asyncio.to_thread(alembic_command.upgrade, _migration_config(), "head")
    assert await transition(old_live_command) == old_live_receipt
    assert await snapshot() == retained_lifecycle

    async with authorized_routing_source(
        tmp_path, isolated_database_env
    ) as pending:
        async with pending.factory() as session:
            pending_before = await stored_effects(session, pending.request.task_id)
        async with pending.factory() as session:
            with pytest.raises(
                TaskRoutingLifecycleDeferred,
                match="routing lifecycle is not live",
            ):
                async with session.begin():
                    await apply_outcome(session, pending, old_live_receipt.generation)
        async with pending.factory() as session:
            assert await stored_effects(session, pending.request.task_id) == pending_before

        original_lock = PostgresJointLifecycleMutationFence.lock_controller

        async def forge_python_fact(owner):
            facts = await original_lock(owner)
            return facts.model_copy(update={"new_effects_enabled": True})

        with monkeypatch.context() as bypass:
            bypass.setattr(
                PostgresJointLifecycleMutationFence,
                "lock_controller",
                forge_python_fact,
            )
            async with pending.factory() as session:
                with pytest.raises(
                    DBAPIError,
                    match="routing acceptance generation unavailable",
                ):
                    async with session.begin():
                        await apply_outcome(
                            session,
                            pending,
                            old_live_receipt.generation,
                        )
        async with pending.factory() as session:
            assert await stored_effects(session, pending.request.task_id) == pending_before

        for phase in ("draining", "disabled", "shadow"):
            await transition(await command_for(access.target.id, phase))
        renewed = await transition(await command_for(access.target.id, "live"))
        async with pending.factory() as session, session.begin():
            original = await apply_outcome(session, pending, renewed.generation)
        async with pending.factory() as session:
            await session.begin()
            await session.execute(
                text(
                    "CREATE OR REPLACE FUNCTION "
                    "public.joint_lifecycle_new_effects_enabled("
                    "c public.joint_lifecycle_release_control) RETURNS boolean "
                    "LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$ "
                    "SELECT false $$"
                )
            )
            assert await _routing_acceptance_validity(
                session,
                original.routing_manifest_id,
            ) == {"new_valid": False, "replay_valid": True}
            await session.rollback()
        stopped = await transition(await command_for(access.target.id, "draining"))
        async with pending.factory() as session, session.begin():
            replay = await apply_outcome(session, pending, stopped.generation)
        assert replay == original.model_copy(update={"replayed": True})


async def test_current_generation_cannot_admit_new_effects_when_stopped(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
):
    access = live_acceptance_lifecycle
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = await stored_effects(session, h.request.task_id)
        for phase in ("draining", "disabled", "shadow"):
            receipt = await transition(await command_for(access.target.id, phase))
            async with h.factory() as session:
                with pytest.raises(TaskRoutingLifecycleDeferred, match="routing lifecycle is not live"):
                    async with session.begin():
                        await apply_outcome(session, h, receipt.generation)
            async with h.factory() as session:
                assert await stored_effects(session, h.request.task_id) == before, phase


async def test_operator_who_is_submitter_does_not_deadlock_prior_acceptance(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
):
    access = live_acceptance_lifecycle
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        await access.signed.grant(
            access.admin,
            SimpleNamespace(id=h.actor_context.actor_profile_id),
        )
        command = await command_for(h.actor_context.actor_profile_id, "draining")
        reached, proceed = asyncio.Event(), asyncio.Event()
        original = FinalAcceptanceRepository.persist

        async def pause(owner, source, **kwargs):
            reached.set()
            await proceed.wait()
            return await original(owner, source, **kwargs)

        monkeypatch.setattr(FinalAcceptanceRepository, "persist", pause)

        async def accept():
            async with h.factory() as session, session.begin():
                return await apply_outcome(session, h, 2)

        pids = asyncio.Queue()

        async def stop():
            async with h.factory() as session, session.begin():
                await pids.put(await session.scalar(text("SELECT pg_catalog.pg_backend_pid()")))
                return await controller(session, command).transition(command)

        writer = asyncio.create_task(accept())
        stopper = None
        try:
            await asyncio.wait_for(reached.wait(), 10)
            stopper = asyncio.create_task(stop())
            pid = await asyncio.wait_for(pids.get(), 10)
            await observe_advisory_wait(h.factory, pid, stopper)
            proceed.set()
            accepted, stopped = await asyncio.wait_for(asyncio.gather(writer, stopper), 15)
            assert accepted.final_acceptance_id is not None
            assert stopped.phase == "draining"
        finally:
            proceed.set()
            pending = [task for task in (writer, stopper) if task is not None]
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        async with get_session_factory()() as session:
            control = await session.scalar(select(JointLifecycleReleaseControl))
            assert control.phase == "draining" and control.generation == 3
            facts = await stored_effects(session, h.request.task_id)
            assert facts["acceptances"] == facts["contributions"] == 1


async def test_committed_transition_fences_waiting_acceptance(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
):
    access = live_acceptance_lifecycle
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        command = await command_for(access.target.id, "draining")
        async with h.factory() as session:
            before = await stored_effects(session, h.request.task_id)
        async with h.factory() as stopper:
            await stopper.begin()
            stopped = await controller(stopper, command).transition(command)
            pids = asyncio.Queue()

            async def accept():
                async with h.factory() as session, session.begin():
                    await pids.put(await session.scalar(text("SELECT pg_catalog.pg_backend_pid()")))
                    return await apply_outcome(session, h, 2)

            writer = asyncio.create_task(accept())
            try:
                await observe_advisory_wait(h.factory, await pids.get(), writer)
                await stopper.commit()
                with pytest.raises(JointLifecycleUnavailable, match="generation changed"):
                    await asyncio.wait_for(writer, 10)
                # A fresh generation is still not permission for stopped effects.
                async with h.factory() as session, session.begin():
                    with pytest.raises(TaskRoutingLifecycleDeferred, match="routing lifecycle is not live"):
                        await apply_outcome(session, h, stopped.generation)
            finally:
                await stopper.rollback()
                if not writer.done():
                    writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)
        async with h.factory() as session:
            assert await stored_effects(session, h.request.task_id) == before


async def test_generation_zero_cannot_create_acceptance(tmp_path, isolated_database_env):
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = await stored_effects(session, h.request.task_id)
        async with h.factory() as session, session.begin():
            with pytest.raises(TaskRoutingLifecycleDeferred, match="routing lifecycle is not live"):
                await apply_outcome(session, h, 0)
        async with h.factory() as session:
            assert await stored_effects(session, h.request.task_id) == before


async def test_each_owner_rejects_manifest_disabled_live_facts(
    tmp_path,
    isolated_database_env,
):
    """Each new-effect owner consumes the strict manifest-bound fence fact."""
    from unittest.mock import AsyncMock

    from app.modules.contributions.api import (
        ContributionParticipationUnavailable,
        SubmitterParticipationRequest,
    )
    from app.modules.reviews.acceptance.participant import FinalAcceptanceParticipant
    from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant
    from app.modules.tasks.api.accepted_effects import (
        TaskAcceptedEffectsUnavailable,
        TaskAcceptedPreparation,
    )
    from tests.contributions.participation.support import (
        participant as contribution_participant,
    )

    lifecycle = SimpleNamespace(
        phase="live",
        generation=2,
        new_effects_enabled=False,
    )

    class ManifestDisabledFence:
        async def acquire(self, expected_generation):
            assert expected_generation == 2
            return lifecycle

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        request = await denial_only_request(h, 2)
        async with h.factory() as session:
            before = await stored_effects(session, h.request.task_id)
        async with h.factory() as session, session.begin():
            task = TaskAcceptedEffectsParticipant(
                session,
                fence=ManifestDisabledFence(),
            )
            with pytest.raises(
                TaskAcceptedEffectsUnavailable,
                match="lifecycle is not live",
            ):
                await task.lock_accepted_effects(
                    request.task_effects,
                    expected_generation=2,
                )
        async with h.factory() as session, session.begin():
            contribution = contribution_participant(session)
            contribution._fence = ManifestDisabledFence()
            contribution._repository.get_frozen_rule = AsyncMock(
                side_effect=AssertionError("CON reached repository")
            )
            with pytest.raises(
                ContributionParticipationUnavailable,
                match="lifecycle is not live",
            ):
                await contribution.participate_submitter(
                    SubmitterParticipationRequest(
                        acceptance_disposition="new",
                        project_id=request.acceptance.project_id,
                        task_id=request.acceptance.task_id,
                        submission_id=request.acceptance.submission_id,
                        final_acceptance_id=request.acceptance.id,
                        task_assignment_id=request.task_effects.assignment_id,
                        contributor_id=request.acceptance.accepted_submitter_id,
                        contribution_policy_version_id=(
                            request.task_effects.contribution_policy_version_id
                        ),
                        artifact_hash=request.task_effects.content_sha256,
                        correlation_id=request.correlation_id,
                        expected_generation=2,
                    )
                )
            contribution._repository.get_frozen_rule.assert_not_awaited()
        async with h.factory() as session, session.begin():
            tasks = SimpleNamespace(
                lock_accepted_effects=AsyncMock(
                    return_value=TaskAcceptedPreparation(
                        disposition="new",
                        locked_review_policy_id=(
                            request.acceptance.policy_context_ref
                        ),
                    )
                ),
                require_routing_source=AsyncMock(),
            )
            owner = FinalAcceptanceParticipant(
                session,
                tasks=lambda held: tasks,
                contributions=lambda held: AsyncMock(),
            )
            owner._repository.persist = AsyncMock(
                side_effect=AssertionError("REV reached persistence")
            )
            with pytest.raises(FinalAcceptanceConflict, match="lifecycle is not live"):
                await owner._participate(
                    request,
                    lifecycle,
                    tasks,
                    AsyncMock(),
                )
            owner._repository.persist.assert_not_awaited()
        async with h.factory() as session:
            assert await stored_effects(session, h.request.task_id) == before


@pytest.mark.parametrize("sequence", ["genesis", "stopped"])
async def test_each_owner_independently_rejects_new_effects(
    tmp_path,
    isolated_database_env,
    admin_access,
    sequence,
):
    from unittest.mock import AsyncMock

    from app.modules.contributions.api import ContributionParticipationUnavailable
    from app.modules.reviews.acceptance.participant import FinalAcceptanceParticipant
    from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
    from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant
    from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsUnavailable, TaskAcceptedPreparation
    from tests.contributions.participation.support import participant as contribution_participant
    from app.modules.contributions.api import SubmitterParticipationRequest

    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    generation = 0
    if sequence == "stopped":
        await transition(await command_for(admin_access.target.id, "shadow"))
        await transition(await command_for(admin_access.target.id, "live"))
    async with authorized_routing_source(
        tmp_path, isolated_database_env, contribution_awards=("money", "project_points")
    ) as h:
        phases = ("disabled", "shadow") if sequence == "genesis" else ("draining", "disabled", "shadow")
        for phase in phases:
            if not (sequence == "genesis" and phase == "disabled"):
                generation = (await transition(await command_for(admin_access.target.id, phase))).generation
            request = await denial_only_request(h, generation)
            async with h.factory() as session:
                before = await stored_effects(session, h.request.task_id)
            async with h.factory() as session, session.begin():
                task = TaskAcceptedEffectsParticipant(session, fence=PostgresJointLifecycleMutationFence(session))
                with pytest.raises(TaskAcceptedEffectsUnavailable, match="lifecycle is not live"):
                    await task.lock_accepted_effects(request.task_effects, expected_generation=generation)
            async with h.factory() as session, session.begin():
                contribution = contribution_participant(session)
                contribution._repository.get_frozen_rule = AsyncMock(
                    side_effect=AssertionError("CON reached repository")
                )
                with pytest.raises(
                    ContributionParticipationUnavailable, match="lifecycle is not live"
                ):
                    await contribution.participate_submitter(
                        SubmitterParticipationRequest(
                            acceptance_disposition="new",
                            project_id=request.acceptance.project_id,
                            task_id=request.acceptance.task_id,
                            submission_id=request.acceptance.submission_id,
                            final_acceptance_id=request.acceptance.id,
                            task_assignment_id=request.task_effects.assignment_id,
                            contributor_id=request.acceptance.accepted_submitter_id,
                            contribution_policy_version_id=request.task_effects.contribution_policy_version_id,
                            artifact_hash=request.task_effects.content_sha256,
                            correlation_id=request.correlation_id,
                            expected_generation=generation,
                        )
                    )
                contribution._repository.get_frozen_rule.assert_not_awaited()
            async with h.factory() as session, session.begin():
                # Isolate REV's own check: TASK supplies a correctly shaped new
                # preparation; neither TASK nor CON can mask a missing REV gate.
                tasks = SimpleNamespace(
                    lock_accepted_effects=AsyncMock(
                        return_value=TaskAcceptedPreparation(
                            disposition="new",
                            locked_review_policy_id=request.acceptance.policy_context_ref,
                        )
                    ),
                    require_routing_source=AsyncMock(),
                )
                owner = FinalAcceptanceParticipant(
                    session,
                    tasks=lambda held: tasks,
                    contributions=lambda held: AsyncMock(),
                )
                owner._repository.persist = AsyncMock(side_effect=AssertionError("REV reached persistence"))
                with pytest.raises(FinalAcceptanceConflict, match="lifecycle is not live"):
                    async with owner.prepare(generation) as prepared:
                        await prepared.participate(request)
                owner._repository.persist.assert_not_awaited()
            async with h.factory() as session:
                assert await stored_effects(session, h.request.task_id) == before


async def test_task_read_acceptance_and_transition_intermediate_waits(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
):
    from app.adapters.audit import task_transition_audit
    from app.adapters.tasks import task_commands
    from app.core.config import get_settings
    from app.modules.authorization.task_authorization import PreparedTaskAuthorization
    from tests.authorization.task_authority.test_concurrency import actor_context

    access = live_acceptance_lifecycle
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        actor_id = h.actor_context.actor_profile_id
        await access.signed.grant(access.admin, SimpleNamespace(id=actor_id))
        actor = await actor_context(str(actor_id))
        command = await command_for(actor_id, "draining")
        task_locked, proceed = asyncio.Event(), asyncio.Event()
        original = PreparedTaskAuthorization.prepare

        async def pause_after_task(owner, facts):
            task_locked.set()
            await proceed.wait()
            return await original(owner, facts)

        monkeypatch.setattr(PreparedTaskAuthorization, "prepare", pause_after_task)
        pids = {}

        async def identify(session, name):
            pids[name] = await session.scalar(text("SELECT pg_catalog.pg_backend_pid()"))

        async def read():
            async with h.factory() as session:
                await identify(session, "read")
                await session.commit()
                owner = task_commands(
                    session, settings=get_settings(), authorization=PreparedTaskAuthorization(session, actor),
                    audit=task_transition_audit(session), actor_profile_id=actor_id,
                )
                return await owner.management_detail(h.request.project_id, h.request.task_id)

        async def accept():
            async with h.factory() as session, session.begin():
                await identify(session, "accept")
                return await apply_outcome(session, h, 2)

        async def stop():
            async with h.factory() as session, session.begin():
                await identify(session, "stop")
                return await controller(session, command).transition(command)

        async def wait_for_blocker(waiter, blocker, pending):
            async with h.factory() as observer, asyncio.timeout(10):
                while True:
                    if pending.done():
                        await pending
                        raise AssertionError("expected intermediate database wait")
                    if waiter in pids and await observer.scalar(text(
                        "SELECT :blocker = ANY(pg_catalog.pg_blocking_pids(:waiter))"
                    ), {"blocker": pids[blocker], "waiter": pids[waiter]}):
                        return
                    await asyncio.sleep(0.01)

        jobs = [asyncio.create_task(read())]
        try:
            await asyncio.wait_for(task_locked.wait(), 10)
            jobs.append(asyncio.create_task(accept()))
            # Acceptance retains REV while the real task read retains TASK.
            await wait_for_blocker("accept", "read", jobs[1])
            jobs.append(asyncio.create_task(stop()))
            # Transition must wait for REV without retaining the reader's actor.
            await wait_for_blocker("stop", "accept", jobs[2])
            proceed.set()
            detail, accepted, stopped = await asyncio.wait_for(asyncio.gather(*jobs), 20)
            assert detail.task_id == h.request.task_id
            assert accepted.final_acceptance_id is not None
            assert stopped.phase == "draining" and stopped.generation == 3
        finally:
            proceed.set()
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
        async with h.factory() as session:
            facts = await stored_effects(session, h.request.task_id)
            assert facts["task_status"] == "accepted"
            assert facts["acceptances"] == facts["contributions"] == 1
