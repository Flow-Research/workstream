"""PostgreSQL terminal-custody proofs for native AWS artifact activation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.interfaces.artifacts import (
    ArtifactObjectMissingError,
    ArtifactProviderActivationLease,
    ArtifactProviderLiveProofRequiredError,
    ArtifactPutObservation,
    ArtifactPutResult,
    ArtifactStoreError,
)
from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
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

def _aws_activation_settings(settings: Settings) -> Settings:
    """Overlay the closed native-AWS activation tuple for terminal custody tests."""
    return settings.model_copy(
        update={
            "artifact_s3_provider_profile": "aws_s3",
            "artifact_s3_region": "us-east-1",
            "release_id": "sha256:" + "1" * 64,
            "artifact_s3_runtime_role_arn": "arn:aws:iam::123456789012:role/workstream-runtime",
            "artifact_s3_runtime_trust_policy_sha256": "sha256:" + "3" * 64,
            "artifact_s3_runtime_policy_arn": "arn:aws:iam::123456789012:policy/workstream-runtime",
            "artifact_s3_readiness_role_arn": "arn:aws:iam::123456789012:role/workstream-readiness",
            "artifact_s3_readiness_trust_policy_sha256": "sha256:" + "4" * 64,
            "artifact_s3_readiness_policy_arn": "arn:aws:iam::123456789012:policy/workstream-readiness",
            "artifact_s3_negative_role_arn": "arn:aws:iam::123456789012:role/workstream-negative",
            "artifact_s3_negative_trust_policy_sha256": "sha256:" + "5" * 64,
            "artifact_s3_bootstrap_principal_arn": "arn:aws:iam::123456789012:role/workstream-bootstrap",
            "artifact_s3_bucket_policy_sha256": "sha256:" + "2" * 64,
            "artifact_s3_operation_total_timeout_seconds": 0.1,
            "artifact_complete_read_deadline_seconds": 0.1,
            "artifact_terminal_persistence_margin_seconds": 0.1,
        }
    )

async def _insert_soon_expiring_activation(
    session,
    settings: Settings,
    namespace_fingerprint: str,
) -> UUID:
    from datetime import timedelta
    from uuid import uuid4

    from app.modules.artifacts.provider_activation import (
        artifact_provider_database_time,
        coordinate_artifact_provider_activation,
        record_artifact_provider_probe_result,
    )

    group_nonce = uuid4()
    principals = {
        "readiness": settings.artifact_s3_readiness_role_arn,
        "runtime_immutability": settings.artifact_s3_runtime_role_arn,
        "negative_access": settings.artifact_s3_negative_role_arn,
    }
    now = await artifact_provider_database_time(session)
    started_at = now - timedelta(minutes=14, seconds=55)
    for probe_type, principal in principals.items():
        assert principal is not None
        await record_artifact_provider_probe_result(
            session,
            settings,
            probe_type=probe_type,
            namespace_fingerprint=namespace_fingerprint,
            group_nonce=group_nonce,
            expected_principal_arn=principal,
            observed_principal_arn=principal,
            passed=True,
            evidence={"mode": probe_type, "actual_calls": True},
            error_code=None,
            started_at=started_at,
        )
    return await coordinate_artifact_provider_activation(
        session,
        settings,
        namespace_fingerprint=namespace_fingerprint,
        group_nonce=group_nonce,
    )

async def _assert_recoverable_verification_after_activation_expiry(
    session,
    *,
    job_id: UUID,
    replica_id: str,
    prior_replica_state: tuple[object, object, object, object],
    unrelated_receipt_count: int,
) -> None:
    job = await session.get(ArtifactVerificationJob, str(job_id))
    replica = await session.get(ArtifactReplica, replica_id)
    assert job is not None and replica is not None
    assert job.status == "provider_unavailable"
    assert job.next_run_at is not None
    assert job.terminal_at is None
    assert job.terminal_result_code is None
    assert (
        replica.verification_state,
        replica.availability_state,
        replica.integrity_state,
        replica.last_reconciled_at,
    ) == prior_replica_state
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ArtifactVerificationReceipt)
            .where(ArtifactVerificationReceipt.verification_job_id == str(job_id))
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ArtifactVerificationReceipt)
            .where(ArtifactVerificationReceipt.verification_job_id != str(job_id))
        )
        == unrelated_receipt_count
    )

async def test_activation_expiry_during_put_terminal_transaction_rolls_back_to_unknown(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    activation_id = UUID("0199e648-0b77-7000-8000-000000000001")

    class ActivatedPutStore:
        identity = SimpleNamespace(provider_key=namespace.adapter)

        async def put(self, source, *, operation_evidence):
            operation_evidence.bind(ArtifactProviderActivationLease(activation_id))
            return ArtifactPutResult(
                f"sha256/{source.commitment.sha256[7:9]}/{source.commitment.sha256[9:]}",
                replayed=False,
            )

    try:
        async with factory() as session:
            async with minted_source(tmp_path / "activation-expiry", b"provider wrote") as source:
                admission = await _admit_guide_source(
                    session,
                    settings,
                    namespace,
                    _context(),
                    source,
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    ActivatedPutStore(),
                    namespace,
                    settings,
                    _AllowArtifactAuthority(),
                )
                orchestrator._require_terminal_activation = AsyncMock(
                    side_effect=[
                        None,
                        ArtifactProviderLiveProofRequiredError("activation expired"),
                    ]
                )

                assert (
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    == "acknowledgement_unknown"
                )
                terminal_activation_args = [
                    call.args
                    for call in orchestrator._require_terminal_activation.await_args_list
                ]
                assert terminal_activation_args == [
                    (activation_id,),
                    (activation_id,),
                ]
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "acknowledgement_unknown"
                assert attempt.terminal_at is None
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert await _count(session, ArtifactPutObservationReceipt) == 0
                assert await _count(session, ArtifactReplica) == 0
                assert await _count(session, ArtifactVerificationJob) == 0
    finally:
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
                tmp_path / f"checker-{expected_outcome}", b"checker lifecycle"
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
                assert (attempt.project_id, attempt.task_id, attempt.checker_run_id) == (
                    project_id,
                    task_id,
                    checker_run_id,
                )
                assert receipt.checker_run_id == checker_run_id
                with pytest.raises(DBAPIError):
                    await session.execute(
                        text(
                            "update artifact_operation_receipts set contract_version=1 "
                            "where id=:receipt_id"
                        ),
                        {"receipt_id": receipt.id},
                    )
                await session.rollback()
                activation_id = UUID("0199e648-0b77-7000-8000-000000000003")

                async def read_complete(_provider_object_ref, *, operation_evidence):
                    operation_evidence.bind(ArtifactProviderActivationLease(activation_id))
                    if isinstance(read_result, Exception):
                        raise read_result
                    if read_result is not None:
                        return read_result
                    return source.commitment.sha256, source.commitment.byte_count

                orchestrator._read_complete = read_complete
                orchestrator._require_terminal_activation = AsyncMock()
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
                assert orchestrator._require_terminal_activation.await_count >= 2
                assert all(
                    call.args == (activation_id,)
                    for call in orchestrator._require_terminal_activation.await_args_list
                )
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
                tmp_path / f"checker-observation-{expected_outcome}", b"checker observation"
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
                activation_id = UUID("0199e648-0b77-7000-8000-000000000002")

                async def observe(_commitment, *, operation_evidence):
                    operation_evidence.bind(ArtifactProviderActivationLease(activation_id))
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
                orchestrator._require_terminal_activation = AsyncMock()

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
                assert checker_run_id == attempt.checker_run_id
                assert orchestrator._require_terminal_activation.await_count >= 2
                assert all(
                    call.args == (activation_id,)
                    for call in orchestrator._require_terminal_activation.await_args_list
                )
    finally:
        await engine.dispose()

@pytest.mark.parametrize("provider_outcome", ["missing", "integrity_mismatch"])
async def test_expired_activation_rolls_back_provider_verification_facts(
    admission_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider_outcome: str,
) -> None:
    """Real PostgreSQL expiry leaves missing and mismatch observations recoverable."""
    from app.modules.artifacts.provider_activation import (
        SqlAlchemyArtifactProviderActivationGuard,
    )

    local_settings = _settings(tmp_path)
    activation_settings = _aws_activation_settings(local_settings)
    namespace = _namespace(local_settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    monkeypatch.setattr(
        "app.modules.artifacts.provider_activation.ARTIFACT_AWS_CLOCK_SAFETY_MARGIN_SECONDS",
        0,
    )
    try:
        async with factory() as session:
            relationships = await seed_checker_output_relationships(
                session,
                namespace,
                policy_bundle=policy_bundle,
            )
            async with minted_source(
                tmp_path / f"expired-{provider_outcome}",
                b"provider terminal evidence",
            ) as source:
                _project_id, _task_id, _checker_run_id, admission = await _admit_checker_output(
                    session,
                    local_settings,
                    namespace,
                    source,
                    relationships=relationships,
                )

                class SeedPutStore:
                    identity = SimpleNamespace(provider_key=namespace.adapter)

                    async def put(self, put_source, *, operation_evidence):
                        return ArtifactPutResult(
                            "sha256/"
                            f"{put_source.commitment.sha256[7:9]}/"
                            f"{put_source.commitment.sha256[9:]}",
                            replayed=False,
                        )

                initial = ArtifactStorageOrchestrator(
                    session,
                    SeedPutStore(),
                    namespace,
                    local_settings,
                    _AllowArtifactAuthority(),
                )
                assert (
                    await initial.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    == "stored_pending_verification"
                )
                job = await session.scalar(
                    select(ArtifactVerificationJob).where(
                        ArtifactVerificationJob.originating_put_attempt_id
                        == str(admission.attempt_id)
                    )
                )
                assert job is not None
                replica = await session.get(ArtifactReplica, job.replica_id)
                assert replica is not None
                prior_replica_state = (
                    replica.verification_state,
                    replica.availability_state,
                    replica.integrity_state,
                    replica.last_reconciled_at,
                )
                job_id = UUID(job.id)
                replica_id = job.replica_id
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ArtifactVerificationReceipt)
                        .where(
                            ArtifactVerificationReceipt.verification_job_id
                            == str(job_id)
                        )
                    )
                    == 0
                )
                unrelated_receipt_count = await session.scalar(
                    select(func.count())
                    .select_from(ArtifactVerificationReceipt)
                    .where(
                        ArtifactVerificationReceipt.verification_job_id != str(job_id)
                    )
                )
                assert unrelated_receipt_count is not None
                assert unrelated_receipt_count > 0
                await session.rollback()
                async with session.begin():
                    activation_id = await _insert_soon_expiring_activation(
                        session,
                        activation_settings,
                        namespace.namespace_fingerprint,
                    )

                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    SimpleNamespace(identity=SimpleNamespace(provider_key=namespace.adapter)),
                    namespace,
                    activation_settings,
                    _AllowArtifactAuthority(),
                )

                async def read_after_expiry(_provider_object_ref, *, operation_evidence):
                    lease = await SqlAlchemyArtifactProviderActivationGuard(
                        factory,
                        activation_settings,
                    ).select_for_call(
                        namespace_fingerprint=namespace.namespace_fingerprint,
                    )
                    assert lease.activation_id == activation_id
                    operation_evidence.bind(lease)
                    await asyncio.sleep(5.1)
                    if provider_outcome == "missing":
                        raise ArtifactObjectMissingError("missing")
                    return "sha256:" + "0" * 64, 1

                orchestrator._read_complete = read_after_expiry
                assert await orchestrator.verify_object(job_id) == "provider_unavailable"
                await _assert_recoverable_verification_after_activation_expiry(
                    session,
                    job_id=job_id,
                    replica_id=replica_id,
                    prior_replica_state=prior_replica_state,
                    unrelated_receipt_count=unrelated_receipt_count,
                )
    finally:
        await engine.dispose()
