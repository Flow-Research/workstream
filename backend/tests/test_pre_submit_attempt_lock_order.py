"""Real PostgreSQL proof of shared-project pre-submit AUTH/ART lock order."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from app.core.identifiers import new_record_id

import pytest

from app.adapters.artifacts import CheckerPhaseService
from tests.checkers.execution.support import forbidden_post_submission
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.artifacts.authorization import (
    PreparedPreSubmitMaterializationAuthorization,
    PreparedSubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.models import PreSubmitEvidenceSet, PreSubmitExecutionAttempt
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
    SubmissionBundlePreparationRuntime,
)
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
from tests.pre_submit_test_helpers import submission_preparation_request
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.test_default_pre_submit_execution import _archive, _bytes
from tests.test_pre_submit_attempt_authority_integration import _reserve_with_real_materializer
from tests.test_pre_submit_attempt_recovery import _harness


class _AfterEvidenceCommitted(Exception):
    """Stop before durable provider work after the real B evidence transaction."""


class _PauseAfterSpool:
    def __init__(self, preparation, spooled: asyncio.Event, resume: asyncio.Event):
        self._preparation = preparation
        self._spooled, self._resume = spooled, resume

    async def prepare(self, byte_source, *, media_type):
        prepared = await self._preparation.prepare(byte_source, media_type=media_type)
        self._spooled.set()
        try:
            await self._resume.wait()
        except BaseException:
            await prepared.close()
            raise
        return prepared


class _PauseAfterProjectLock:
    def __init__(self, repository, session, locked: asyncio.Event, resume: asyncio.Event):
        self._repository, self._session = repository, session
        self._locked, self._resume = locked, resume
        self.backend_pid: int | None = None
        self._paused = False

    async def lock_locked_policy_context(self, request):
        facts = await self._repository.lock_locked_policy_context(request)
        if not self._paused:
            self._paused = True
            self.backend_pid = int(await self._session.scalar(text("select pg_backend_pid()")))
            self._locked.set()
            await self._resume.wait()
        return facts


class _CompleteBeforeDurable:
    def __init__(self, workflow):
        self._workflow = workflow
        self.evidence = None

    async def reserve(self, request, *, preparation_request):
        return await self._workflow.reserve(request, preparation_request=preparation_request)

    async def execute_reserved(self, request, reservation, *, preparation_request):
        self.evidence = await self._workflow.execute_reserved(
            request, reservation, preparation_request=preparation_request,
        )
        raise _AfterEvidenceCommitted


async def _seed_second_contributor_task(harness):
    """Share PROJECT locks while avoiding actor, grant, task and assignment collisions."""
    actor_id, link_id, task_id, assignment_id = (new_record_id() for _ in range(4))
    project_id = harness.request.effective_plan.lineage.project_id
    async with harness.engine.begin() as connection:
        await connection.execute(text(
            "insert into actor_profiles "
            "(id,actor_kind,status,provisioning_method,created_by) values "
            "(:actor,'human','active','automatic_first_access','test')"
        ), {"actor": str(actor_id)})
        await connection.execute(text(
            "insert into actor_identity_links "
            "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,last_verified_at) "
            "values (:link,:actor,'flow-test',:subject,'human','active','test',now())"
        ), {"actor": str(actor_id), "subject": str(actor_id), "link": str(link_id)})
        await seed_started_task_for_artifact_test(connection, {
            "project": str(project_id), "task": str(task_id),
            "assignment": str(assignment_id), "actor": str(actor_id),
        })
        await install_submitter_grant(connection, {
            "project": str(project_id), "actor": str(actor_id),
        })
    return actor_id, link_id, task_id, assignment_id


def _contributor_authority(session, request):
    actor = request.actor
    return PreparedSubmissionBundlePreparationAuthorization(
        session,
        HumanAuthorizationContext(
            actor_profile_id=actor.actor_profile_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=actor.identity_link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
        ),
    )


def _second_preparation_request(harness, actor_id, link_id, task_id, assignment_id):
    template = replace(harness.request, task_id=task_id, assignment_id=assignment_id)
    return replace(
        submission_preparation_request(
            template, actor_profile_id=actor_id, identity_link_id=link_id,
        ),
        byte_source=_bytes(_archive(evidence_path=harness.evidence_path)),
    )


@dataclass(slots=True)
class _RaceParticipants:
    first_workflow: Any
    second_command: Any
    second_request: Any
    evidence_owner: _CompleteBeforeDurable
    pause_project: _PauseAfterProjectLock
    first_materializer: PreparedPreSubmitMaterializationAuthorization
    second_materializer: PreparedPreSubmitMaterializationAuthorization
    first_calls: list[int]
    second_calls: list[int]


async def _configure_participants(
    harness, first_session, second_session, second_request,
    spooled, resume_spool, project_locked, resume_project,
) -> _RaceParticipants:
    first_contributor = _contributor_authority(first_session, harness.preparation_request)
    await first_contributor.preflight(request=harness.preparation_request)
    async with first_session.begin():
        await first_contributor.revalidate(
            request=harness.preparation_request,
            project_id=harness.request.effective_plan.lineage.project_id,
        )
    first_materializer = PreparedPreSubmitMaterializationAuthorization(
        first_session,
        request_id=harness.preparation_request.request_id,
        correlation_id=harness.preparation_request.correlation_id,
    )
    first_calls: list[int] = []
    first_workflow = harness.workflow(
        first_session, first_calls, preparation_authorization=first_contributor,
    )
    first_workflow._materialization._authorization = first_materializer
    second_contributor = _contributor_authority(second_session, second_request)
    second_materializer = PreparedPreSubmitMaterializationAuthorization(
        second_session,
        request_id=second_request.request_id,
        correlation_id=second_request.correlation_id,
    )
    second_calls: list[int] = []
    second_workflow = harness.workflow(
        second_session, second_calls, preparation_authorization=second_contributor,
    )
    second_workflow._materialization._authorization = second_materializer
    evidence_owner = _CompleteBeforeDurable(second_workflow)
    runtime = SubmissionBundlePreparationRuntime(
        preparation=_PauseAfterSpool(harness.preparation, spooled, resume_spool),
        inspector=harness.inspector,
        catalogue=harness.catalogue,
        materialization=second_workflow._materialization,
        evidence=evidence_owner,
        checker_service=CheckerPhaseService(
            pre_submission=evidence_owner,
            post_submission=forbidden_post_submission(),
        ),
        durable_put=object(),
    )

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    second_command = PreparedSubmissionBundlePreparationCommand(
        session=second_session,
        authority=second_contributor,
        task_contexts=second_workflow._task_contexts,
        project_contexts=second_workflow._project_contexts,
        runtime_factory=runtime_factory,
    )
    pause_project = _PauseAfterProjectLock(
        first_workflow._project_contexts,
        first_session, project_locked, resume_project,
    )
    return _RaceParticipants(
        first_workflow, second_command, second_request, evidence_owner,
        pause_project, first_materializer, second_materializer,
        first_calls, second_calls,
    )


async def _wait_for_project_block(engine, *, application_name: str, blocker_pid: int):
    """Observe the competing command's actual PostgreSQL row-lock wait."""
    async with engine.connect() as observer:
        async with asyncio.timeout(8):
            while True:
                await observer.execute(text("select pg_stat_clear_snapshot()"))
                waits = (await observer.execute(text(
                    "select wait_event_type,pg_blocking_pids(pid) from pg_stat_activity "
                    "where application_name=:application and datname=current_database()"
                ), {"application": application_name})).all()
                if any(kind == "Lock" and blocker_pid in blocked_by
                       for kind, blocked_by in waits):
                    return
                await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_same_project_reservation_and_execution_complete_without_auth_project_deadlock(
    tmp_path: Path, isolated_database_env: str, monkeypatch,
) -> None:
    # The fixture's ordinary ten-second scratch deadline is too short for an
    # intentional database barrier; only this test extends the temporary lease.
    import tests.test_default_pre_submit_execution as default_tests

    original_limits = default_tests._limits
    monkeypatch.setattr(default_tests, "_limits", lambda: replace(
        original_limits(), total_deadline_seconds=90, reservation_ttl_seconds=120,
        aggregate_reserved_bytes=4 * default_tests.HARD_MAXIMUM_ARTIFACT_BYTES,
    ))
    harness = await _harness(tmp_path, isolated_database_env)
    second_engine = None
    first_task = second_task = None
    resume_spool, resume_project = asyncio.Event(), asyncio.Event()
    try:
        second_actor, second_link, second_task_id, second_assignment_id = (
            await _seed_second_contributor_task(harness)
        )
        await _seed_materializer(harness.factory)
        second_request = _second_preparation_request(
            harness, second_actor, second_link, second_task_id, second_assignment_id,
        )
        application_name = f"pol07a_lock_order_{new_record_id().hex[:12]}"
        second_engine = create_async_engine(
            isolated_database_env,
            connect_args={"server_settings": {"application_name": application_name}},
        )
        second_factory = async_sessionmaker(second_engine, expire_on_commit=False)
        spooled, project_locked = asyncio.Event(), asyncio.Event()
        async with harness.factory() as first_session, second_factory() as second_session:
            participants = await _configure_participants(
                harness, first_session, second_session, second_request,
                spooled, resume_spool, project_locked, resume_project,
            )
            try:
                first_reservation = await _reserve_with_real_materializer(
                    participants.first_workflow,
                    harness.request, harness.preparation_request,
                )
                participants.first_workflow._project_contexts = participants.pause_project
                second_task = asyncio.create_task(
                    participants.second_command.prepare(second_request)
                )
                await asyncio.wait_for(spooled.wait(), timeout=30)
                first_task = asyncio.create_task(participants.first_workflow.execute_reserved(
                    harness.request, first_reservation,
                    preparation_request=harness.preparation_request,
                ))
                await asyncio.wait_for(project_locked.wait(), timeout=30)
                assert participants.pause_project.backend_pid is not None
                resume_spool.set()
                await _wait_for_project_block(
                    harness.engine,
                    application_name=application_name,
                    blocker_pid=participants.pause_project.backend_pid,
                )
                resume_project.set()
                first_outcome, second_outcome = await asyncio.wait_for(
                    asyncio.gather(first_task, second_task, return_exceptions=True),
                    timeout=30,
                )
                assert not isinstance(first_outcome, BaseException), first_outcome
                assert isinstance(second_outcome, _AfterEvidenceCommitted), second_outcome
                assert participants.evidence_owner.evidence is not None
                assert first_outcome.pass_capability is not None
                assert participants.evidence_owner.evidence.pass_capability is not None
                assert participants.first_calls == [1]
                assert participants.second_calls == [1]
            finally:
                participants.first_materializer.close()
                participants.second_materializer.close()
        async with harness.factory() as session:
            attempts = (await session.scalars(select(PreSubmitExecutionAttempt))).all()
            assert len(attempts) == 2
            assert {attempt.actor_profile_id for attempt in attempts} == {
                str(harness.actor_id), str(second_actor),
            }
            assert all(attempt.status == "completed" for attempt in attempts)
            assert await session.scalar(select(func.count()).select_from(PreSubmitEvidenceSet)) == 2
    finally:
        resume_spool.set()
        resume_project.set()
        await asyncio.gather(
            *(task for task in (first_task, second_task) if task is not None),
            return_exceptions=True,
        )
        if second_engine is not None:
            await second_engine.dispose()
        await harness.close()
