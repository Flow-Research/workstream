"""PostgreSQL artifact put, observation, and verification outcomes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.interfaces.artifacts import (
    ArtifactConfigurationError,
    ArtifactIntegrityError,
    ArtifactStoreUnavailableError,
    ArtifactObjectMissingError,
    ArtifactPutObservation,
    ArtifactStoreError,
)
from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactPutObservationReceipt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from projects.unified_policy_fixtures import create_standalone_unified_policy
from tests.artifact_store_helpers import minted_source
from tests.checker_output_admission_helpers import seed_checker_output_relationships
from tests.test_artifact_admission import (
    _AllowArtifactAuthority,
    _admit_checker_output,
    _admit_guide_source,
    _conflicting_checker_replica,
    _context,
    _count,
    _local_store,
    _namespace,
    _settings,
    admission_database_env as admission_database_env,
)


async def test_database_failure_at_put_commit_rolls_back_terminal_effects(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    try:
        async with factory() as session:
            relationships = await seed_checker_output_relationships(session, namespace, policy_bundle=policy_bundle)
            async with minted_source(
                tmp_path / "put-commit-failure", b'{"output":"put commit failure"}',
                media_type="application/json",
            ) as source:
                _, _, _, admission = await _admit_checker_output(
                    session, settings, namespace, source, relationships=relationships,
                )
                attempt_id = str(admission.attempt_id)
                attempt = await session.get(ArtifactPutAttempt, attempt_id)
                assert attempt is not None
                provider_object_ref = attempt.canonical_target
                persisted_models = (
                    ArtifactContent, ArtifactReplica, ArtifactOperationReceipt, ArtifactVerificationJob,
                )
                before = {model: await _count(session, model) for model in persisted_models}
                charge_state = (
                    select(ArtifactAdmissionCharge.state, ArtifactAdmissionCharge.completed_at)
                    .join(ArtifactPutAttemptCharge, ArtifactPutAttemptCharge.charge_id == ArtifactAdmissionCharge.id)
                    .where(ArtifactPutAttemptCharge.attempt_id == attempt_id)
                )
                provisional = (await session.execute(charge_state)).all()
                assert provisional and set(provisional) == {("provisional", None)}
                await session.rollback()

                @event.listens_for(session.sync_session, "before_commit")
                def fail_terminal_commit(transaction: Session) -> None:
                    transaction.flush()
                    if transaction.scalar(select(ArtifactPutAttempt.status).where(
                        ArtifactPutAttempt.id == attempt_id,
                    )) != "object_confirmed":
                        return
                    for model, count in before.items():
                        assert transaction.scalar(select(func.count()).select_from(model)) == count + 1
                    completed = transaction.execute(charge_state).all()
                    assert len(completed) == len(provisional)
                    assert all(state == "completed" and at is not None for state, at in completed)
                    transaction.execute(text("SELECT 1 / 0"))

                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority(),
                )
                with pytest.raises(DBAPIError, match="division by zero"):
                    await orchestrator.execute_committed_put(attempt_id=admission.attempt_id, source=source)

            assert (await store.head(provider_object_ref)).exists
        async with factory() as session:
            attempt = await session.get(ArtifactPutAttempt, attempt_id)
            assert attempt is not None
            assert attempt.status == "put_in_flight"
            assert attempt.executor_id is not None and attempt.lease_expires_at is not None
            assert attempt.terminal_at is None and attempt.terminal_result_code is None
            assert attempt.receipt_id is None and attempt.replica_id is None
            assert {model: await _count(session, model) for model in persisted_models} == before
            assert (await session.execute(charge_state)).all() == provisional
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize("provider_outcome", ["missing", "integrity_mismatch"])
async def test_database_failure_at_verification_commit_rolls_back_terminal_effects(
    admission_database_env: str,
    tmp_path: Path,
    provider_outcome: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    try:
        async with factory() as session:
            relationships = await seed_checker_output_relationships(session, namespace, policy_bundle=policy_bundle)
            async with minted_source(
                tmp_path / "verify-commit-failure", b'{"output":"verify commit failure"}',
                media_type="application/json",
            ) as source:
                _, _, _, admission = await _admit_checker_output(
                    session, settings, namespace, source, relationships=relationships,
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority(),
                )
                assert await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source,
                ) == "stored_pending_verification"

            job = await session.scalar(select(ArtifactVerificationJob).where(
                ArtifactVerificationJob.originating_put_attempt_id == str(admission.attempt_id),
            ))
            assert job is not None
            job_id = job.id
            replica_state = select(
                ArtifactReplica.verification_state, ArtifactReplica.availability_state,
                ArtifactReplica.integrity_state, ArtifactReplica.last_reconciled_at,
            ).where(ArtifactReplica.id == job.replica_id)
            prior_replica = (await session.execute(replica_state)).one()
            prior_receipt_count = await _count(session, ArtifactVerificationReceipt)
            own_receipt = select(ArtifactVerificationReceipt.outcome).where(
                ArtifactVerificationReceipt.verification_job_id == job_id,
            )
            assert await session.scalar(own_receipt) is None
            await session.rollback()

            @event.listens_for(session.sync_session, "before_commit")
            def fail_terminal_commit(transaction: Session) -> None:
                transaction.flush()
                if transaction.scalar(select(ArtifactVerificationJob.status).where(
                    ArtifactVerificationJob.id == job_id,
                )) != provider_outcome:
                    return
                assert transaction.execute(replica_state).one().verification_state == provider_outcome
                assert transaction.scalar(own_receipt) == provider_outcome
                transaction.execute(text("SELECT 1 / 0"))

            orchestrator._read_complete = (
                AsyncMock(side_effect=ArtifactObjectMissingError("missing"))
                if provider_outcome == "missing"
                else AsyncMock(return_value=("sha256:" + "0" * 64, 1))
            )
            with pytest.raises(DBAPIError, match="division by zero"):
                await orchestrator.verify_object(UUID(job_id))

        async with factory() as session:
            job = await session.get(ArtifactVerificationJob, job_id)
            assert job is not None
            assert job.status == "running" and job.attempt_count == 1
            assert job.executor_id is not None and job.lease_expires_at is not None
            assert job.terminal_at is None and job.terminal_result_code is None
            assert (await session.execute(replica_state)).one() == prior_replica
            assert await session.scalar(own_receipt) is None
            assert await _count(session, ArtifactVerificationReceipt) == prior_receipt_count
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize(
    ("read_result", "expected_outcome"),
    (
        (None, "verified"),
        (ArtifactObjectMissingError("missing"), "missing"),
        (("sha256:" + "0" * 64, 1), "integrity_mismatch"),
    ),
)
async def test_checker_output_shared_put_and_verification_lifecycle(
    admission_database_env: str,
    tmp_path: Path,
    read_result: object,
    expected_outcome: str,
) -> None:
    """Task-scoped checker output survives every shared terminal byte outcome."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    try:
        async with factory() as session:
            relationships = await seed_checker_output_relationships(session, namespace, policy_bundle=policy_bundle)
            async with minted_source(
                tmp_path / f"checker-{expected_outcome}", b'{"output":"checker lifecycle"}',
                media_type="application/json",
            ) as source:
                project_id, task_id, checker_run_id, admission = await _admit_checker_output(
                    session, settings, namespace, source, relationships=relationships)
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                assert (
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id, source=source
                    )
                    == "stored_pending_verification"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                receipt = await session.scalar(
                    select(ArtifactOperationReceipt).where(
                        ArtifactOperationReceipt.put_attempt_id == str(admission.attempt_id)
                    )
                )
                job = await session.scalar(
                    select(ArtifactVerificationJob).where(
                        ArtifactVerificationJob.originating_put_attempt_id
                        == str(admission.attempt_id)
                    )
                )
                assert attempt is not None and receipt is not None and job is not None
                job_id = UUID(job.id)
                assert attempt.producer_request_type == "checker_output"
                assert (attempt.project_id, attempt.task_id) == (
                    project_id,
                    task_id,
                )
                assert attempt.checker_run_id is None
                assert attempt.model_call_attempt_id is not None
                assert receipt.checker_run_id is None
                assert receipt.model_call_attempt_id == attempt.model_call_attempt_id
                with pytest.raises(DBAPIError):
                    await session.execute(
                        text(
                            "update artifact_operation_receipts set contract_version=1 "
                            "where id=:receipt_id"
                        ),
                        {"receipt_id": receipt.id},
                    )
                await session.rollback()

                async def read_complete(_provider_object_ref):
                    if isinstance(read_result, Exception):
                        raise read_result
                    if read_result is not None:
                        return read_result
                    return source.commitment.sha256, source.commitment.byte_count

                orchestrator._read_complete = read_complete
                assert await orchestrator.verify_object(job_id) == expected_outcome
                job = await session.get(ArtifactVerificationJob, str(job_id))
                assert job is not None
                assert job.status == expected_outcome
                verification = await session.scalar(
                    select(ArtifactVerificationReceipt).where(
                        ArtifactVerificationReceipt.verification_job_id == job.id
                    )
                )
                assert verification is not None
                assert verification.outcome == expected_outcome
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize(
    "expected_outcome", ["integrity_mismatch", "conflict", "existing_replica_conflict"]
)
async def test_checker_output_put_observation_terminal_outcomes(
    admission_database_env: str,
    tmp_path: Path,
    expected_outcome: str,
) -> None:
    """Current checker output preserves ambiguous-put mismatch and conflict evidence."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    try:
        async with factory() as session:
            relationships = await seed_checker_output_relationships(session, namespace, policy_bundle=policy_bundle)
            async with minted_source(
                tmp_path / f"checker-observation-{expected_outcome}", b'{"output":"checker observation"}',
                media_type="application/json",
            ) as source:
                _project_id, _task_id, checker_run_id, admission = await _admit_checker_output(
                    session, settings, namespace, source, relationships=relationships)
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                provider_object_ref = attempt.canonical_target
                if expected_outcome == "existing_replica_conflict":
                    await _conflicting_checker_replica(session, attempt, namespace, provider_object_ref)
                else:
                    await session.rollback()

                async def observe(_commitment):
                    if expected_outcome == "conflict":
                        raise ArtifactStoreError("provider conflict")
                    return ArtifactPutObservation(provider_object_ref, committed=True)

                provider = SimpleNamespace(
                    identity=SimpleNamespace(provider_key=namespace.adapter),
                    observe_put_result=observe,
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, provider, namespace, settings, _AllowArtifactAuthority()
                )
                orchestrator._read_complete = AsyncMock(
                    return_value=("sha256:" + "0" * 64, 1)
                )

                assert (
                    await orchestrator.resolve_put_attempt(admission.attempt_id)
                    == (
                        "conflict"
                        if expected_outcome == "existing_replica_conflict"
                        else expected_outcome
                    )
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                receipt = await session.scalar(
                    select(ArtifactPutObservationReceipt).where(
                        ArtifactPutObservationReceipt.put_attempt_id == attempt.id
                    )
                )
                charges = (
                    await session.execute(
                        select(ArtifactAdmissionCharge)
                        .join(
                            ArtifactPutAttemptCharge,
                            ArtifactPutAttemptCharge.charge_id == ArtifactAdmissionCharge.id,
                        )
                        .where(ArtifactPutAttemptCharge.attempt_id == attempt.id)
                    )
                ).scalars().all()
                assert receipt is not None
                assert receipt.outcome == (
                    "observed_integrity_mismatch"
                    if expected_outcome == "integrity_mismatch"
                    else "conflict"
                )
                terminal_outcome = (
                    "conflict"
                    if expected_outcome == "existing_replica_conflict"
                    else expected_outcome
                )
                assert attempt.status == attempt.terminal_result_code == terminal_outcome
                assert {charge.state for charge in charges} == {"completed"}
                if expected_outcome == "integrity_mismatch":
                    assert attempt.replica_id is not None
                    assert receipt.observed_sha256 == "sha256:" + "0" * 64
                    assert receipt.observed_byte_count == 1
                elif expected_outcome == "existing_replica_conflict":
                    assert attempt.replica_id is not None
                    assert receipt.observed_sha256 is None
                    assert receipt.observed_byte_count is None
                else:
                    assert attempt.replica_id is None
                    assert receipt.observed_sha256 is None
                    assert receipt.observed_byte_count is None
                assert receipt.execution_generation == attempt.execution_generation
                assert attempt.checker_run_id is None
                assert attempt.model_call_attempt_id is not None
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("observation_error", "fallback_error"),
    (
        (ArtifactStoreUnavailableError, None),
        (ArtifactConfigurationError, None),
        (ArtifactIntegrityError, ArtifactConfigurationError),
    ),
    ids=("provider-unavailable", "lazy-configuration", "integrity-fallback-configuration"),
)
async def test_put_observation_unavailable_retries_then_exhausts_without_facts(
    admission_database_env: str,
    tmp_path: Path,
    observation_error: type[ArtifactStoreError],
    fallback_error: type[ArtifactStoreError] | None,
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"artifact_provider_observation_maximum_attempts": 2}
    )
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    class UnavailableObservationStore:
        identity = SimpleNamespace(provider_key=namespace.adapter)

        async def observe_put_result(self, _commitment, **_kwargs):
            raise observation_error("provider unavailable")

        async def open(self, _provider_object_ref, **_kwargs):
            assert fallback_error is not None
            yield b"partial stream"
            raise fallback_error("provider unavailable")

    try:
        async with factory() as session:
            async with minted_source(tmp_path / "put-unavailable", b"observe") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    UnavailableObservationStore(),
                    namespace,
                    settings,
                    _AllowArtifactAuthority(),
                )
                assert (
                    await orchestrator.resolve_put_attempt(admission.attempt_id)
                    == "acknowledgement_unknown"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.observation_count == 1
                assert attempt.next_run_at is not None
                assert attempt.terminal_at is None
                assert attempt.executor_id is None
                charges = (await session.execute(select(ArtifactAdmissionCharge))).scalars().all()
                assert charges and {charge.state for charge in charges} == {"provisional"}
                await session.execute(
                    text(
                        "update artifact_put_attempts set next_run_at = "
                        "clock_timestamp() - interval '1 second' where id = :id"
                    ),
                    {"id": attempt.id},
                )
                await session.commit()
                assert (
                    await orchestrator.resolve_put_attempt(admission.attempt_id)
                    == "provider_unavailable"
                )
                await session.refresh(attempt)
                assert attempt.observation_count == 2
                assert attempt.next_run_at is None
                assert attempt.terminal_at is not None
                assert attempt.terminal_result_code == "provider_unavailable"
                assert attempt.executor_id is None
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert await _count(session, ArtifactPutObservationReceipt) == 0
                assert await _count(session, ArtifactReplica) == 0
                assert await _count(session, ArtifactVerificationJob) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "provider_error",
    (ArtifactStoreUnavailableError, ArtifactConfigurationError),
    ids=("provider-unavailable", "lazy-configuration"),
)
async def test_verification_unavailable_retries_then_exhausts(
    admission_database_env: str,
    tmp_path: Path,
    provider_error: type[ArtifactStoreError],
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"artifact_provider_observation_maximum_attempts": 2}
    )
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bootstrap, store = _local_store(settings, namespace)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    try:
        async with factory() as session:
            relationships = await seed_checker_output_relationships(session, namespace, policy_bundle=policy_bundle)
            async with minted_source(
                tmp_path / "unavailable", b'{"output":"retry"}', media_type="application/json"
            ) as source:
                _, _, _, admission = await _admit_checker_output(
                    session, settings, namespace, source, relationships=relationships)
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source
                )
                job = await session.scalar(select(ArtifactVerificationJob).where(ArtifactVerificationJob.originating_put_attempt_id == str(admission.attempt_id)))
                assert job is not None
                job_id = UUID(job.id)
                await session.rollback()
                async def unavailable_open(_provider_object_ref, **_kwargs):
                    yield b"partial stream"
                    raise provider_error("unavailable")

                orchestrator = ArtifactStorageOrchestrator(
                    session, SimpleNamespace(identity=store.identity, open=unavailable_open),
                    namespace, settings, _AllowArtifactAuthority(),
                )
                assert await orchestrator.verify_object(job_id) == "provider_unavailable"
                await session.refresh(job)
                assert job.attempt_count == 1
                assert job.next_run_at is not None
                assert job.terminal_at is None
                await session.execute(
                    text(
                        "update artifact_verification_jobs set next_run_at = "
                        "clock_timestamp() - interval '1 second' where id = :id"
                    ),
                    {"id": job.id},
                )
                await session.commit()
                assert await orchestrator.verify_object(job_id) == "provider_unavailable"
                await session.refresh(job)
                assert job.attempt_count == 2
                assert job.next_run_at is None
                assert job.terminal_at is not None
                assert job.terminal_result_code == "provider_unavailable"
                assert await session.scalar(select(func.count()).select_from(ArtifactVerificationReceipt).where(
                    ArtifactVerificationReceipt.verification_job_id == str(job_id))) == 0
    finally:
        bootstrap.close()
        await engine.dispose()
