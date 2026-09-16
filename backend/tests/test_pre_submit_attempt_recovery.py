"""Real PostgreSQL and scratch proof for ART pre-submit invocation custody."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.models import (
    PreSubmitEvidenceResult, PreSubmitEvidenceSet, PreSubmitExecutionAttempt,
)
from app.modules.artifacts.authorization import PreparedSubmissionBundlePreparationAuthorization
from app.modules.artifacts.pre_submit_attempts import PreSubmitAttemptClaim
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict,
    PreSubmitEvidencePersistenceResult,
    PreSubmitEvidenceService,
)
from app.modules.artifacts.submission_manifest import (
    build_submission_manifest,
    evaluate_submission_change,
)
from tests.pre_submit_test_helpers import (
    approved_pre_submit_fixture,
    evidence_workflow,
    submission_preparation_request,
)
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.test_default_pre_submit_execution import _AllowAuthority, _archive, _bytes, _request
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)


class _CountedProcessor:
    def __init__(self, wrapped, calls: list[int], entered=None, release=None):
        self._wrapped, self._calls = wrapped, calls
        self._entered, self._release = entered, release

    def abort(self):
        return self._wrapped.abort()

    async def process(self, reader, workspace):
        self._calls.append(1)
        if self._entered is not None:
            self._entered.set()
            await self._release.wait()
        return await self._wrapped.process(reader, workspace)


class _CountedExecution:
    def __init__(self, wrapped, calls, entered=None, release=None):
        self._wrapped, self._calls = wrapped, calls
        self._entered, self._release = entered, release

    @property
    def catalogue_manifest_sha256(self):
        return self._wrapped.catalogue_manifest_sha256

    def build(self, request):
        return _CountedProcessor(
            self._wrapped.build(request), self._calls, self._entered, self._release,
        )


@dataclass
class _Harness:
    engine: object
    factory: object
    request: object
    preparation_request: object
    preparation: object
    inspector: object
    catalogue: object
    manager: object
    evidence_path: str
    actor_id: UUID
    identity_link_id: UUID

    def workflow(self, session, calls, *, entered=None, release=None,
                 preparation_authorization=None):
        workflow = evidence_workflow(
            session=session,
            preparation=self.preparation,
            inspector=self.inspector,
            catalogue=self.catalogue,
            materialization_authorization=_AllowAuthority(),
            preparation_authorization=(
                preparation_authorization
                if preparation_authorization is not None
                else SimpleNamespace(lock_actor=AsyncMock(), revalidate=AsyncMock())
            ),
        )
        materialization = workflow._materialization
        materialization._checker_execution = _CountedExecution(
            materialization._checker_execution, calls, entered, release,
        )
        return workflow

    async def fresh_request(self, data=None):
        prepared = await self.preparation.prepare(
            _bytes(data if data is not None else _archive(evidence_path=self.evidence_path)),
            media_type="application/zip",
        )
        inspection = await prepared.inspect(self.inspector)
        manifest = build_submission_manifest(inspection)
        request = replace(
            self.request,
            prepared_artifact=prepared,
            inspection=inspection,
            manifest=manifest,
            change_gate=evaluate_submission_change(
                commitment=prepared.commitment,
                manifest=manifest,
                predecessor=None,
                predecessor_exists=False,
            ),
        )
        return request

    async def close(self):
        await self.request.prepared_artifact.close()
        self.manager.close()
        await self.engine.dispose()

    def contributor_authority(self, session):
        return PreparedSubmissionBundlePreparationAuthorization(
            session,
            HumanAuthorizationContext(
                actor_profile_id=self.actor_id,
                actor_kind=ActorKind.HUMAN,
                actor_status=ActorStatus.ACTIVE,
                identity_link_id=self.identity_link_id,
                identity_link_status=IdentityLinkStatus.ACTIVE,
                request_id=self.preparation_request.request_id,
                correlation_id=self.preparation_request.correlation_id,
            ),
        )


async def _harness(tmp_path: Path, database_url: str) -> _Harness:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    namespace = ArtifactStorageNamespaceSpec(
        backend="local", adapter="local", provider_profile="test",
        namespace_descriptor={"test": "submission-bundle"},
        namespace_fingerprint=canonical_json_hash({"test": "submission-bundle"}),
    )
    plan, policy = await approved_pre_submit_fixture(factory, namespace, guide_version="v0.1")
    evidence_path = policy.pop("evidence_path")
    request, inspector, manager, preparation, catalogue = await _request(
        tmp_path, plan=plan, evidence_path=evidence_path,
    )
    request = replace(request, packet=replace(
        request.packet,
        contributor_attestation=(
            request.packet.contributor_attestation + " " + " ".join(policy.pop("attestation_terms"))
        ),
    ))
    actor_id, identity_link_id = uuid4(), uuid4()
    lineage = request.effective_plan.lineage
    params = {
        "actor": str(actor_id), "link": str(identity_link_id),
        "project": str(lineage.project_id), "guide": str(lineage.guide_id),
        "snapshot": str(lineage.source_snapshot_id),
        "snapshot_hash": lineage.source_snapshot_hash, **policy,
        "effective_policy": str(lineage.effective_policy_id),
        "effective_hash": lineage.effective_policy_hash,
        "checker_policy": str(lineage.pre_submit_policy_id),
        "checker_hash": lineage.pre_submit_policy_bundle_hash,
        "task": str(request.task_id), "assignment": str(request.assignment_id),
    }
    async with engine.begin() as connection:
        await connection.execute(text(
            "insert into actor_profiles "
            "(id,actor_kind,status,provisioning_method,created_by) values "
            "(:actor,'human','active','automatic_first_access','test')"
        ), params)
        await connection.execute(text(
            "insert into actor_identity_links "
            "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,last_verified_at) "
            "values (:link,:actor,'flow-test',:actor,'human','active','test',now())"
        ), params)
        await connection.execute(text(
            "insert into workstream_tasks "
            "(id,project_id,locked_guide_version,locked_guide_source_snapshot_id,"
            "locked_guide_source_snapshot_hash,"
            "locked_effective_project_submission_artifact_policy_id,"
            "locked_effective_project_submission_artifact_policy_hash,"
            "locked_pre_submit_checker_policy_id,locked_pre_submit_checker_bundle_hash,"
            "locked_post_submit_checker_policy_id,locked_post_submit_checker_policy_version,"
            "locked_post_submit_checker_policy_hash,locked_post_submit_checker_policy_body,"
            "locked_review_policy_id,locked_review_policy_generation,locked_review_policy_hash,"
            "locked_revision_policy_id,locked_revision_policy_generation,locked_revision_policy_hash,"
            "source_type,title,description,skill_tags,status,assigned_to,created_by) values "
            "(:task,:project,:guide_version,:snapshot,:snapshot_hash,:effective_policy,"
            ":effective_hash,:checker_policy,:checker_hash,:post_policy,:guide_version,"
            ":post_policy_hash,CAST(:post_policy_body AS json),:review_policy,1,:review_policy_hash,"
            ":revision_policy,1,:revision_policy_hash,'manual','Evidence task',"
            "'Evidence test task','[]'::json,'in_progress',:actor,'test')"
        ), params)
        await connection.execute(text(
            "insert into task_assignments "
            "(id,task_id,contributor_id,assigned_by,status) values "
            "(:assignment,:task,:actor,'test','active')"
        ), params)
        await install_submitter_grant(connection, params)
    preparation_request = submission_preparation_request(
        request, actor_profile_id=actor_id, identity_link_id=identity_link_id,
    )
    return _Harness(
        engine, factory, request, preparation_request, preparation, inspector,
        catalogue, manager, evidence_path, actor_id, identity_link_id,
    )


async def _reserve(workflow, request, preparation_request):
    async with workflow._session.begin():
        return await workflow.reserve(request, preparation_request=preparation_request)


@pytest.mark.asyncio
async def test_completed_replay_after_original_scratch_closes(
    tmp_path: Path, isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    retry = None
    try:
        async with harness.factory() as session:
            workflow = harness.workflow(session, calls)
            reservation = await _reserve(workflow, harness.request, harness.preparation_request)
            first = await workflow.execute_reserved(
                harness.request, reservation, preparation_request=harness.preparation_request,
            )
            assert len(calls) == 1
            assert first.pass_capability is not None
            original_generation = first.execution.custody.prepared_generation_id
            await harness.request.prepared_artifact.close()
            retry = await harness.fresh_request()
            assert retry.prepared_artifact.generation_id != original_generation
            replay = await _reserve(workflow, retry, harness.preparation_request)
            assert isinstance(replay, PreSubmitEvidencePersistenceResult)
            assert replay.evidence.evidence_set_id == first.evidence.evidence_set_id
            assert replay.execution == first.execution
            assert replay.execution.custody.prepared_generation_id == original_generation
            assert replay.pass_capability is None
            assert len(calls) == 1
            changed_packet = replace(retry, packet=replace(
                retry.packet, summary="Different work was completed.",
            ))
            changed_preparation = replace(
                harness.preparation_request, summary=changed_packet.packet.summary,
            )
            with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_attempt_request_conflict"):
                await _reserve(workflow, changed_packet, changed_preparation)
            assert len(calls) == 1
            await retry.prepared_artifact.close()
            retry = await harness.fresh_request(
                _archive(extra_path="different.txt", evidence_path=harness.evidence_path)
            )
            with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_attempt_request_conflict"):
                await _reserve(workflow, retry, harness.preparation_request)
            assert len(calls) == 1
    finally:
        if retry is not None:
            await retry.prepared_artifact.close()
        await harness.close()


@pytest.mark.asyncio
async def test_crash_after_member_before_evidence_commit_cannot_rerun(
    tmp_path: Path, isolated_database_env: str, monkeypatch,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    original_persist = PreSubmitEvidenceService.persist

    async def crash_after_member(self, request):
        raise RuntimeError("simulated crash before evidence commit")

    try:
        async with harness.factory() as session:
            workflow = harness.workflow(session, calls)
            reservation = await _reserve(workflow, harness.request, harness.preparation_request)
            monkeypatch.setattr(PreSubmitEvidenceService, "persist", crash_after_member)
            with pytest.raises(RuntimeError, match="simulated crash"):
                await workflow.execute_reserved(
                    harness.request, reservation, preparation_request=harness.preparation_request,
                )
            monkeypatch.setattr(PreSubmitEvidenceService, "persist", original_persist)
            assert len(calls) == 1
            async with harness.factory() as retry_session:
                retry_workflow = harness.workflow(retry_session, calls)
                with pytest.raises(
                    PreSubmitEvidenceConflict, match="pre_submit_attempt_outcome_unresolved"
                ):
                    await _reserve(
                        retry_workflow, harness.request, harness.preparation_request,
                    )
            assert len(calls) == 1
            attempt = await session.scalar(select(PreSubmitExecutionAttempt))
            assert attempt is not None and attempt.status == "reserved"
            assert await session.scalar(select(func.count()).select_from(PreSubmitEvidenceSet)) == 0
            await session.rollback()
    finally:
        monkeypatch.setattr(PreSubmitEvidenceService, "persist", original_persist)
        await harness.close()


@pytest.mark.asyncio
async def test_completion_failure_rolls_back_evidence_and_keeps_attempt_reserved(
    tmp_path: Path, isolated_database_env: str, monkeypatch,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    original_complete = PreSubmitAttemptClaim.complete

    async def fail_completion(self, session, evidence_id):
        # The repository has already inserted the evidence and all result rows.
        assert await session.get(PreSubmitEvidenceSet, str(evidence_id)) is not None
        raise RuntimeError("simulated completion failure")

    try:
        async with harness.factory() as session:
            workflow = harness.workflow(session, calls)
            reservation = await _reserve(workflow, harness.request, harness.preparation_request)
            monkeypatch.setattr(PreSubmitAttemptClaim, "complete", fail_completion)
            with pytest.raises(RuntimeError, match="simulated completion failure"):
                await workflow.execute_reserved(
                    harness.request, reservation, preparation_request=harness.preparation_request,
                )
            monkeypatch.setattr(PreSubmitAttemptClaim, "complete", original_complete)
            assert len(calls) == 1
            attempt = await session.scalar(select(PreSubmitExecutionAttempt))
            assert attempt is not None and attempt.status == "reserved"
            assert await session.scalar(select(func.count()).select_from(PreSubmitEvidenceSet)) == 0
            await session.rollback()
            with pytest.raises(
                PreSubmitEvidenceConflict, match="pre_submit_attempt_outcome_unresolved"
            ):
                await _reserve(workflow, harness.request, harness.preparation_request)
    finally:
        monkeypatch.setattr(PreSubmitAttemptClaim, "complete", original_complete)
        await harness.close()


@pytest.mark.asyncio
async def test_independent_sessions_same_key_invoke_members_once(
    tmp_path: Path, isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    entered, release = asyncio.Event(), asyncio.Event()
    executing = competing = None
    try:
        async with harness.factory() as first_session, harness.factory() as second_session:
            first_workflow = harness.workflow(first_session, calls, entered=entered, release=release)
            second_workflow = harness.workflow(second_session, calls)
            competing_pid = asyncio.get_running_loop().create_future()
            task_contexts = second_workflow._task_contexts

            class _ObservedTaskContexts:
                async def lock_submission_context(self, request):
                    pid = await second_session.scalar(text("select pg_backend_pid()"))
                    competing_pid.set_result(pid)
                    return await task_contexts.lock_submission_context(request)

            second_workflow._task_contexts = _ObservedTaskContexts()
            reservation = await _reserve(
                first_workflow, harness.request, harness.preparation_request,
            )
            executing = asyncio.create_task(first_workflow.execute_reserved(
                harness.request, reservation, preparation_request=harness.preparation_request,
            ))
            await asyncio.wait_for(entered.wait(), timeout=10)
            competing = asyncio.create_task(_reserve(
                second_workflow, harness.request, harness.preparation_request,
            ))
            pid = await asyncio.wait_for(competing_pid, timeout=3)
            async with harness.engine.connect() as observer:
                wait_type = None
                async with asyncio.timeout(3):
                    while not competing.done():
                        await observer.execute(text("select pg_stat_clear_snapshot()"))
                        wait_type = await observer.scalar(text(
                            "select wait_event_type from pg_stat_activity where pid=:pid"
                        ), {"pid": pid})
                        if wait_type == "Lock":
                            break
                        await asyncio.sleep(0.02)
            assert competing.done() or wait_type == "Lock"
            release.set()
            result = await executing
            recovered = (await asyncio.gather(competing, return_exceptions=True))[0]
            assert result.pass_capability is not None
            if isinstance(recovered, PreSubmitEvidencePersistenceResult):
                assert recovered.pass_capability is None
                assert recovered.evidence.evidence_set_id == result.evidence.evidence_set_id
            else:
                assert isinstance(recovered, PreSubmitEvidenceConflict)
                assert str(recovered) == "pre_submit_attempt_outcome_unresolved"
            assert len(calls) == 1
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (executing, competing) if task is not None),
            return_exceptions=True,
        )
        await harness.close()


@pytest.mark.asyncio
async def test_uncommitted_reservation_never_issues_a_claim(
    tmp_path: Path, isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    try:
        async with harness.factory() as session:
            workflow = harness.workflow(session, calls)
            async with session.begin():
                reservation = await workflow.reserve(
                    harness.request, preparation_request=harness.preparation_request,
                )
                with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_attempt_not_committed"):
                    await workflow._attempts.committed_claim(reservation)
                await session.rollback()
            assert await session.scalar(select(func.count()).select_from(PreSubmitExecutionAttempt)) == 0
            await session.rollback()
            with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_attempt_not_committed"):
                await workflow._attempts.committed_claim(reservation)
            assert calls == []
    finally:
        await harness.close()


@pytest.mark.asyncio
async def test_attempt_database_guards_reject_rewrite_delete_and_orphan_completion(
    tmp_path: Path, isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    try:
        async with harness.factory() as session:
            workflow = harness.workflow(session, [])
            reservation = await _reserve(workflow, harness.request, harness.preparation_request)
            attempt_id = str(reservation.attempt_id)
        statements = (
            ("update pre_submit_execution_attempts set request_digest=:digest where id=:id",
             {"digest": "sha256:" + "0" * 64}),
            ("update pre_submit_execution_attempts set status='completed',evidence_set_id=:evidence "
             "where id=:id", {"evidence": str(uuid4())}),
            ("delete from pre_submit_execution_attempts where id=:id", {}),
        )
        for sql, values in statements:
            with pytest.raises(DBAPIError):
                async with harness.engine.begin() as connection:
                    await connection.execute(text(sql), {"id": attempt_id, **values})
        async with harness.factory() as session:
            attempt = await session.get(PreSubmitExecutionAttempt, attempt_id)
            assert attempt is not None and attempt.status == "reserved"
            assert attempt.evidence_set_id is None
    finally:
        await harness.close()


@pytest.mark.asyncio
async def test_database_rejects_same_resource_different_packet_evidence_completion(
    tmp_path: Path, isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    try:
        async with harness.factory() as first_session:
            first_workflow = harness.workflow(first_session, [])
            first_reservation = await _reserve(
                first_workflow, harness.request, harness.preparation_request,
            )
            first = await first_workflow.execute_reserved(
                harness.request, first_reservation,
                preparation_request=harness.preparation_request,
            )
        changed_request = replace(harness.request, packet=replace(
            harness.request.packet, summary="A different packet for the same work artifact.",
        ))
        changed_preparation = replace(
            harness.preparation_request,
            idempotency_key=uuid4(),
            summary=changed_request.packet.summary,
        )
        async with harness.factory() as second_session:
            second_workflow = harness.workflow(second_session, [])
            second_reservation = await _reserve(
                second_workflow, changed_request, changed_preparation,
            )
        assert first_reservation.request_digest != second_reservation.request_digest
        new_evidence = str(uuid4())
        source_evidence = str(first.evidence.evidence_set_id)
        async with harness.factory() as session:
            original_evidence = await session.get(PreSubmitEvidenceSet, source_evidence)
            second_attempt = await session.get(
                PreSubmitExecutionAttempt, str(second_reservation.attempt_id),
            )
            assert original_evidence is not None and second_attempt is not None
            assert original_evidence.packet_sha256 == canonical_json_hash(
                asdict(harness.request.packet)
            )
            assert original_evidence.packet_sha256 != second_attempt.request_json["packet_sha256"]
        columns = tuple(column.name for column in PreSubmitEvidenceSet.__table__.columns)
        replacements = {
            "id": ":new_evidence",
            "operation_identity": ":new_operation",
            "attempt_id": ":new_attempt",
            "created_at": "transaction_timestamp()",
            # The request digest is valid for the second attempt. Only the
            # evidence's independently captured packet hash remains original.
            "attempt_request_digest": ":correct_request_digest",
        }
        copy_sql = (
            f"insert into pre_submit_evidence_sets ({', '.join(columns)}) "
            f"select {', '.join(replacements.get(column, column) for column in columns)} "
            "from pre_submit_evidence_sets where id=:source_evidence"
        )
        result_columns = tuple(column.name for column in PreSubmitEvidenceResult.__table__.columns)
        result_replacements = {
            "id": "gen_random_uuid()::text",
            "evidence_set_id": ":new_evidence",
            "created_at": "transaction_timestamp()",
        }
        copy_results_sql = (
            f"insert into pre_submit_evidence_results ({', '.join(result_columns)}) "
            f"select {', '.join(result_replacements.get(column, column) for column in result_columns)} "
            "from pre_submit_evidence_results where evidence_set_id=:source_evidence "
            "order by result_order"
        )
        with pytest.raises(DBAPIError, match="pre-submit evidence packet mismatch"):
            async with harness.engine.begin() as connection:
                await connection.execute(text(copy_sql), {
                    "new_evidence": new_evidence,
                    "new_operation": canonical_json_hash({"counterexample": new_evidence}),
                    "new_attempt": str(second_reservation.attempt_id),
                    "correct_request_digest": second_reservation.request_digest,
                    "source_evidence": source_evidence,
                })
                copied = await connection.execute(text(copy_results_sql), {
                    "new_evidence": new_evidence,
                    "source_evidence": source_evidence,
                })
                assert copied.rowcount == len(first.execution.entries)
                await connection.execute(text(
                    "update pre_submit_execution_attempts set status='completed',"
                    "evidence_set_id=:evidence where id=:attempt"
                ), {"evidence": new_evidence, "attempt": str(second_reservation.attempt_id)})
        async with harness.factory() as session:
            attempt = await session.get(
                PreSubmitExecutionAttempt, str(second_reservation.attempt_id),
            )
            assert attempt is not None and attempt.status == "reserved"
            assert await session.get(PreSubmitEvidenceSet, new_evidence) is None
            assert await session.get(PreSubmitEvidenceSet, source_evidence) is not None
    finally:
        await harness.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("before_execution", "completed_replay"))
async def test_revoked_contributor_cannot_execute_or_replay_after_reservation(
    tmp_path: Path, isolated_database_env: str, phase: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    retry = None
    try:
        async with harness.factory() as session:
            authority = harness.contributor_authority(session)
            await authority.preflight(request=harness.preparation_request)
            async with session.begin():
                await authority.revalidate(
                    request=harness.preparation_request,
                    project_id=harness.request.effective_plan.lineage.project_id,
                )
            workflow = harness.workflow(
                session, calls, preparation_authorization=authority,
            )
            reservation = await _reserve(
                workflow, harness.request, harness.preparation_request,
            )
            if phase == "completed_replay":
                completed = await workflow.execute_reserved(
                    harness.request, reservation,
                    preparation_request=harness.preparation_request,
                )
                assert completed.pass_capability is not None
                assert len(calls) == 1
                await harness.request.prepared_artifact.close()
                retry = await harness.fresh_request()
            else:
                assert calls == []
            async with harness.engine.begin() as connection:
                await connection.execute(text(
                    "update actor_identity_links set status='revoked',"
                    "revoked_by='test',revoked_at=now(),revoked_reason='test revocation' "
                    "where id=:link"
                ), {"link": str(harness.identity_link_id)})
            with pytest.raises(ArtifactAuthorityDeniedError):
                if phase == "before_execution":
                    await workflow.execute_reserved(
                        harness.request, reservation,
                        preparation_request=harness.preparation_request,
                    )
                else:
                    await _reserve(workflow, retry, harness.preparation_request)
            assert len(calls) == (0 if phase == "before_execution" else 1)
    finally:
        if retry is not None:
            await retry.prepared_artifact.close()
        await harness.close()
