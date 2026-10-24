"""Post-byte TASK drift refuses selected execution and durable admission."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.identifiers import new_record_id
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRejected, SubmissionBundlePreparationRequest,
)
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.submission_admission import PreparedSubmissionBundlePreparationCommand
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.tasks.api import TaskSubmissionContextUnavailable
from tests.checkers.external.test_selected_pre_submit import _policies
from tests.trusted_intake_fixtures import LocalIntakeAdapter


@pytest.mark.asyncio
async def test_stale_task_relock_denies_before_selected_execution_or_admission():
    actor = ActorIdentityFacts(new_record_id(), new_record_id(), ActorKind.HUMAN)
    references = SimpleNamespace(
        project_id=new_record_id(), guide_version="v1",
        source_snapshot_id=new_record_id(), source_snapshot_hash="sha256:" + "1" * 64,
        effective_policy_id=new_record_id(), effective_policy_hash="sha256:" + "2" * 64,
        pre_submit_policy_id=new_record_id(), pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
    )
    task = SimpleNamespace(locked_project_context=references, predecessor=None,
                           checker_remediation_manifest_id=None)
    tasks = SimpleNamespace(lock_submission_context=AsyncMock(side_effect=[
        task, TaskSubmissionContextUnavailable("task_submission_context_invalid"),
    ]))
    project = SimpleNamespace(external_checker_policies=SimpleNamespace(
        value=_policies().model_dump_json(),
    ))
    projects = SimpleNamespace(lock_locked_policy_context=AsyncMock(return_value=project))
    authority = SimpleNamespace(preflight=AsyncMock(), lock_actor=AsyncMock(),
                                revalidate=AsyncMock(), close=Mock())
    prepared = SimpleNamespace(close=AsyncMock())
    coordinator = SimpleNamespace(read_current=AsyncMock(), reserve=AsyncMock())
    executor = SimpleNamespace(execute=AsyncMock())
    durable = SimpleNamespace(admit_in_transaction=AsyncMock(), publish_after_commit=AsyncMock())
    runtime = SimpleNamespace(
        selected_coordinator=coordinator, selected_execution=executor, storage_scheme="s3",
        intake=LocalIntakeAdapter(), archive_limits=SubmissionArchiveLimits(),
        artifact_deadline_ms=60_000,
        preparation=SimpleNamespace(prepare=AsyncMock(return_value=prepared)), durable_put=durable,
    )

    @asynccontextmanager
    async def root():
        yield

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(begin=root), authority=authority,
        task_contexts=tasks, project_contexts=projects, runtime_factory=runtime_factory,
    )
    request = SubmissionBundlePreparationRequest(
        actor=actor, request_id=new_record_id(), correlation_id=new_record_id(),
        task_id=new_record_id(), assignment_id=new_record_id(), predecessor_submission_id=None,
        idempotency_key=new_record_id(), summary="", contributor_attestation="",
        media_type="application/zip", byte_source=object(),
    )
    with pytest.raises(SubmissionBundlePreparationRejected,
                       match="^submission_bundle_preparation_context_changed$"):
        await command.prepare(request)
    assert tasks.lock_submission_context.await_count == 2
    runtime.preparation.prepare.assert_awaited_once_with(request.byte_source, media_type="application/zip")
    projects.lock_locked_policy_context.assert_awaited_once()
    authority.lock_actor.assert_awaited_once()
    authority.revalidate.assert_awaited_once()
    coordinator.read_current.assert_not_awaited()
    coordinator.reserve.assert_not_awaited()
    executor.execute.assert_not_awaited()
    durable.admit_in_transaction.assert_not_awaited()
    durable.publish_after_commit.assert_not_awaited()
    prepared.close.assert_awaited_once()
    assert len(runtime.intake.sessions) == 1
    assert runtime.intake.sessions[0].events == ["close"]
    authority.close.assert_called_once_with()
