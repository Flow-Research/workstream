"""Observed PostgreSQL ordering of complete context reads and existing writers."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update

from app.modules.projects.api import (
    ProjectGuideSetupFinalizationCommand,
    ProjectGuideSetupFinalizationError,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
from app.modules.authorization.project_setup_finalization import SetupFinalizationAuthorization
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.models import Project, PreSubmitCheckerPolicy
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.projects.locked_policy_fixtures import activated_context, frozen_request


async def _name(session, label):
    await session.execute(
        text("select set_config('application_name', :label, true)"), {"label": label}
    )
    return await session.scalar(text("select pg_backend_pid()"))


@pytest.mark.parametrize("reader_first", (True, False))
async def test_context_serializes_project_archival(clean_postgres_database, reader_first):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        project_id = receipt.contribution.project_id
        task = None
        async with factory() as reader, factory() as writer:
            try:
                # Preserve a strong reference to an active cached row for writer-first proof.
                cached = await reader.get(Project, str(project_id))
                assert cached.status == "active"
                name = "arch03a-archive-" + uuid4().hex
                reader_pid = await _name(reader, name if not reader_first else name + "-reader")
                writer_pid = await _name(writer, name if reader_first else name + "-writer")
                owner = ProjectLockedPolicyRepository(reader)
                change = (
                    update(Project).where(Project.id == str(project_id)).values(status="archived")
                )
                if reader_first:
                    facts = await owner.lock_locked_policy_context(frozen_request(receipt))
                    task = asyncio.create_task(writer.execute(change))
                    await wait_for_named_database_lock(
                        clean_postgres_database,
                        name,
                        expected_waiter_pid=writer_pid,
                        expected_blocker_pid=reader_pid,
                    )
                    assert not task.done()
                    await reader.commit()
                    await asyncio.wait_for(task, 15)
                    await writer.commit()
                    assert facts.activation_receipt == receipt
                else:
                    await writer.execute(change)
                    task = asyncio.create_task(
                        owner.lock_locked_policy_context(frozen_request(receipt))
                    )
                    await wait_for_named_database_lock(
                        clean_postgres_database,
                        name,
                        expected_waiter_pid=reader_pid,
                        expected_blocker_pid=writer_pid,
                    )
                    await writer.commit()
                    with pytest.raises(ProjectLockedPolicyContextUnavailable):
                        await asyncio.wait_for(task, 15)
                    assert cached.status == "archived"
                await reader.rollback()
                async with factory() as observer, observer.begin():
                    with pytest.raises(ProjectLockedPolicyContextUnavailable):
                        await ProjectLockedPolicyRepository(observer).lock_active_policy_context(
                            project_id
                        )
            finally:
                if task is not None:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await reader.rollback()
                await writer.rollback()


@pytest.mark.parametrize("reader_first", (True, False))
async def test_context_and_finalization_share_lock_order(
    clean_postgres_database, monkeypatch, reader_first
):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        target = receipt.command.target.proposal
        command = ProjectGuideSetupFinalizationCommand(
            project_id=target.project_id,
            guide_id=target.guide_id,
            setup_run_id=target.setup_run_id,
            setup_generation=target.setup_generation,
            compilation_id=target.compilation_id,
        )
        locked, release = asyncio.Event(), asyncio.Event()
        tasks = []
        async with factory() as reader, factory() as finalizer:
            first, second = (reader, finalizer) if reader_first else (finalizer, reader)
            original = first.scalar

            async def pause_after_attempt(*args, **kwargs):
                row = await original(*args, **kwargs)
                if isinstance(row, ProjectGuideCompilationAttempt) and not locked.is_set():
                    locked.set()
                    await asyncio.wait_for(release.wait(), 20)
                return row

            monkeypatch.setattr(first, "scalar", pause_after_attempt)
            first_name, second_name = (
                "arch03a-first-" + uuid4().hex,
                "arch03a-waiter-" + uuid4().hex,
            )
            first_pid, second_pid = await _name(first, first_name), await _name(second, second_name)

            async def read():
                try:
                    facts = await ProjectLockedPolicyRepository(reader).lock_locked_policy_context(
                        frozen_request(receipt)
                    )
                    assert facts.activation_receipt == receipt
                    await reader.commit()
                    return "read"
                finally:
                    await reader.rollback()

            async def finalize():
                try:
                    with pytest.raises(ProjectGuideSetupFinalizationError) as denied:
                        await GuideCompilationFinalizationService(
                            finalizer,
                            SetupFinalizationAuthorization(finalizer),
                        ).finalize(command)
                    assert denied.value.code == "source_state_unavailable"
                    return "denied_active_finalization"
                finally:
                    await finalizer.rollback()

            try:
                tasks.append(asyncio.create_task(read() if reader_first else finalize()))
                await asyncio.wait_for(locked.wait(), 15)
                tasks.append(asyncio.create_task(finalize() if reader_first else read()))
                await wait_for_named_database_lock(
                    clean_postgres_database,
                    second_name,
                    expected_waiter_pid=second_pid,
                    expected_blocker_pid=first_pid,
                )
                release.set()
                outcomes = await asyncio.wait_for(asyncio.gather(*tasks), 20)
                assert set(outcomes) == {"read", "denied_active_finalization"}
            finally:
                release.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await reader.rollback()
                await finalizer.rollback()


async def test_context_retains_pre_policy_row_lock(clean_postgres_database):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        task = None
        async with factory() as reader, factory() as contender:
            try:
                pid = await _name(reader, "arch03a-pre-reader-" + uuid4().hex)
                name = "arch03a-pre-waiter-" + uuid4().hex
                waiter_pid = await _name(contender, name)
                request = frozen_request(receipt)
                await ProjectLockedPolicyRepository(reader).lock_locked_policy_context(request)
                task = asyncio.create_task(
                    contender.scalar(
                        select(PreSubmitCheckerPolicy)
                        .where(
                            PreSubmitCheckerPolicy.id == str(request.pre_submit_policy_id),
                        )
                        .with_for_update()
                    )
                )
                await wait_for_named_database_lock(
                    clean_postgres_database,
                    name,
                    expected_waiter_pid=waiter_pid,
                    expected_blocker_pid=pid,
                )
                await reader.rollback()
                assert (await asyncio.wait_for(task, 15)).id == str(request.pre_submit_policy_id)
            finally:
                if task is not None:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await reader.rollback()
                await contender.rollback()


@pytest.mark.parametrize("reader_first", (True, False))
async def test_context_serializes_guide_replacement(clean_postgres_database, reader_first):
    from tests.authorization.guide_activation.pg_support import service
    from tests.projects.guide_activation.test_successor import successor_command
    from app.modules.projects.models import ProjectGuide

    async with activated_context(clean_postgres_database) as (
        factory,
        first,
        actor,
        grant,
        _,
        policy,
    ):
        successor = await successor_command(factory, first.command, actor, grant, policy)
        successor = successor.model_copy(
            update={
                "expected_previous_active_guide_id": first.command.target.proposal.guide_id,
                "expected_previous_active_guide_generation": first.activation_generation,
            }
        )
        task = None
        async with (
            factory() as reader,
            service(factory, actor) as (writer, activation, request_id, _),
        ):
            try:
                cached = await reader.get(ProjectGuide, str(first.command.target.proposal.guide_id))
                assert cached.status == "active"
                name = "arch03a-replace-" + uuid4().hex
                reader_pid = await _name(reader, name if not reader_first else name + "-reader")
                writer_pid = await _name(writer, name if reader_first else name + "-writer")
                owner = ProjectLockedPolicyRepository(reader)
                if reader_first:
                    before = await owner.lock_active_policy_context(first.contribution.project_id)
                    assert before.activation_receipt == first
                    task = asyncio.create_task(
                        activation.activate(successor, actor=actor, request_id=request_id)
                    )
                    await wait_for_named_database_lock(
                        clean_postgres_database,
                        name,
                        expected_waiter_pid=writer_pid,
                        expected_blocker_pid=reader_pid,
                    )
                    await reader.commit()
                    next_receipt = await asyncio.wait_for(task, 20)
                    await writer.commit()
                else:
                    next_receipt = await activation.activate(
                        successor, actor=actor, request_id=request_id
                    )
                    task = asyncio.create_task(
                        owner.lock_active_policy_context(first.contribution.project_id)
                    )
                    await wait_for_named_database_lock(
                        clean_postgres_database,
                        name,
                        expected_waiter_pid=reader_pid,
                        expected_blocker_pid=writer_pid,
                    )
                    await writer.commit()
                    after = await asyncio.wait_for(task, 20)
                    assert after.activation_receipt == next_receipt
                await reader.rollback()
                async with reader.begin():
                    active = await owner.lock_active_policy_context(first.contribution.project_id)
                    historical = await owner.lock_locked_policy_context(frozen_request(first))
                    assert active.activation_receipt == next_receipt
                    assert historical.activation_receipt == first
                    assert historical.guide_status == cached.status == "superseded"
            finally:
                if task is not None:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await reader.rollback()
