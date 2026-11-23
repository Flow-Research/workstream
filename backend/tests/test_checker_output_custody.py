"""Hidden end-to-end proof for exact verified checker-output custody."""

from __future__ import annotations

import asyncio
import hashlib
from uuid import UUID

import pytest
from sqlalchemy import func, select

from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)

from app.interfaces.artifacts import ArtifactLimitExceededError
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactOperationReceipt,
    ArtifactPutObservationReceipt,
    ArtifactPutAttempt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.checkers.api.output_custody import (
    CheckerOutputArtifactRequest,
    CheckerOutputBindingRequest,
    CheckerOutputUnavailable,
)
from app.modules.model_usage.models import ModelUsageEffect
from tests.checker_output_custody_helpers import (
    byte_stream,
    output_custody_harness,
    selector_for,
)


def content_sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_canonical_public_provisioning_enables_exact_model_request_custody(
    tmp_path, isolated_database_env, admin_access, provider,
) -> None:
    """The journey bootstrap must provision the writer before any model request I/O."""
    from scripts.provision_local_service_actors import (
        JOURNEY_SERVICE_IDENTITIES,
        idempotency_key,
        subject_for,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.adapters.artifacts import create_artifact_store_bootstrap
    from app.interfaces.artifacts import ArtifactStoreNamespaceClaim
    from app.modules.actors.models import ActorProfile
    from app.modules.artifacts.preparation import (
        ArtifactPreparationService,
        ArtifactScratchManager,
    )
    from app.modules.artifacts.service import artifact_storage_namespace_spec
    from app.modules.checkers.api.output_custody import (
        CheckerOutputReservation,
        CheckerOutputSelector,
        CheckerOutputSlot,
    )
    from tests.artifact_store_helpers import artifact_preparation_limits
    from tests.checker_output_admission_helpers import seed_checker_output_relationships
    from tests.checker_output_custody_helpers import (
        ObservedStore,
        _output_storage_settings,
        _prepare_model_attempt,
        _provision_model_policy,
        _store_model_request_evidence,
    )
    from tests.checkers_model_calls.model_usage_boundary_support import BoundaryPorts

    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket

        await provision_minio_bucket.__wrapped__()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _output_storage_settings(tmp_path, provider, None)
    bootstrap = create_artifact_store_bootstrap(settings)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    store = ObservedStore(bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            bootstrap.identity, bootstrap.namespace_identity, namespace.namespace_fingerprint,
        )
    ))
    manager = ArtifactScratchManager(
        root=tmp_path / "request-scratch", limits=artifact_preparation_limits(),
    )
    try:
        policy, profile = await _provision_model_policy(factory, namespace, admin_access)
        data = b'{"prompt":"publicly provisioned request custody"}'
        async with factory() as session:
            _, _, run_id = await seed_checker_output_relationships(
                session, namespace, policy_bundle=policy,
            )
            execution, attempt, _ = await _prepare_model_attempt(
                session, run_id, content_sha256(data), model_profile=profile,
                model_ports=BoundaryPorts(),
            )
            await session.commit()
        selector = CheckerOutputSelector(
            paid_slot=attempt.slot_key, task_id=execution.task_id,
            model_call_slot_id=attempt.slot_id, model_call_attempt_id=attempt.attempt_id,
            slot_key="model_request", content_sha256=content_sha256(data), execution=execution,
        )
        reservation = CheckerOutputReservation(
            selector=selector,
            slot=CheckerOutputSlot(key="model_request", maximum_bytes=profile.spec.maximum_request_bytes),
        )
        identity = ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
        async with factory() as session:
            assert await session.scalar(select(ActorProfile.id).where(
                ActorProfile.service_identity == identity,
            )) is None
        arguments = dict(
            factory=factory, preparation=ArtifactPreparationService(manager), store=store,
            namespace=namespace, settings=settings, reservation=reservation, request_bytes=data,
        )
        with pytest.raises(CheckerOutputUnavailable, match="authority_unavailable"):
            await _store_model_request_evidence(**arguments)
        assert (store.puts, store.opens) == (0, 0)
        async with factory() as session:
            for table in (ArtifactPutAttempt, ArtifactOperationReceipt):
                assert await session.scalar(select(func.count()).select_from(table).where(
                    table.model_call_attempt_id == str(attempt.attempt_id),
                )) == 0
            assert await session.scalar(select(func.count()).select_from(ArtifactBinding).where(
                ArtifactBinding.resource_type == "checker_model_call",
                ArtifactBinding.resource_id == str(attempt.attempt_id),
            )) == 0
            effect = await session.get(ModelUsageEffect, str(attempt.attempt_id))
            assert effect.state == "prepared" and effect.request_binding_id is None
            assert effect.reserved_nanodollars is None

        # Select through the actual canonical bootstrap list; removing the identity
        # must leave this real storage call refused, rather than pass a constant test.
        responses = []
        for service_identity in JOURNEY_SERVICE_IDENTITIES:
            if service_identity == identity:
                subject = subject_for(service_identity, "public-request-custody")
                for _ in range(2):
                    response = await admin_access.signed.client.post(
                        "/api/v1/service-actors",
                        headers=admin_access.admin.headers | {
                            "Idempotency-Key": idempotency_key(service_identity, subject),
                        },
                        json={"service_identity": service_identity, "subject": subject,
                              "reason": "Provision canonical model evidence writer"},
                    )
                    assert response.status_code == 201, response.text
                    responses.append(response.json())
        evidence = await _store_model_request_evidence(**arguments)
        assert len(responses) == 2 and responses[0] == responses[1]
        assert (store.puts, store.opens) == (1, 1)
        assert evidence.content_sha256 == selector.content_sha256
        async with factory() as session:
            binding = await session.get(ArtifactBinding, str(evidence.binding_id))
            assert (binding.resource_type, binding.resource_id, binding.logical_role) == (
                "checker_model_call", str(attempt.attempt_id), "model_request",
            )
            assert binding.put_attempt_id == str(evidence.put_attempt_id)
            assert binding.verification_receipt_id == str(evidence.verification_receipt_id)
    finally:
        manager.close()
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_real_store_verification_and_binding(
    tmp_path,
    isolated_database_env,
    admin_access,
    provider,
) -> None:
    """Store, independently verify and bind one exact output through real providers."""
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket

        await provision_minio_bucket.__wrapped__()
    async with output_custody_harness(
        tmp_path,
        isolated_database_env,
        admin_access=admin_access,
        provider=provider,
    ) as harness:
        result = await harness.service.store(harness.request(b"verified checker output"))
        assert result.status == "verified"
        assert result.content_id is not None
        assert result.verification_receipt_id is not None
        assert not result.replayed
        assert harness.store.puts == 1
        assert harness.store.opens == 1

        async with harness.factory() as session:
            async with session.begin():
                bound = await harness.binding_service(session).bind_checker_output(
                    CheckerOutputBindingRequest(
                        harness.selector,
                        result.put_attempt_id,
                        result.verification_receipt_id,
                    )
                )
            row = await session.get(ArtifactBinding, str(bound.binding_id))
            assert row is not None
            assert (
                row.resource_type,
                row.resource_id,
                row.logical_role,
                row.actor_id,
                row.attribution_type,
                row.put_attempt_id,
                row.verification_receipt_id,
            ) == (
                "checker_model_call",
                str(harness.selector.model_call_attempt_id),
                harness.selector.slot_key,
                ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
                "service_identity",
                str(result.put_attempt_id),
                str(result.verification_receipt_id),
            )
            attempt = await session.get(ArtifactPutAttempt, str(result.put_attempt_id))
            receipt = await session.scalar(
                select(ArtifactOperationReceipt).where(
                    ArtifactOperationReceipt.put_attempt_id == str(result.put_attempt_id)
                )
            )
            job = await session.scalar(
                select(ArtifactVerificationJob).where(
                    ArtifactVerificationJob.originating_put_attempt_id == str(result.put_attempt_id)
                )
            )
            assert attempt is not None and receipt is not None and job is not None
            replica = await session.get(ArtifactReplica, job.replica_id)
            assert replica is not None
            assert (
                receipt.model_call_attempt_id,
                receipt.logical_role,
                attempt.checker_output_custody_sealed,
                job.checker_output_custody_sealed,
                replica.checker_output_custody_sealed,
            ) == (
                str(harness.selector.model_call_attempt_id),
                harness.selector.slot_key,
                True,
                True,
                True,
            )
        assert harness.state.admissions
        assert harness.state.recoveries
        assert harness.state.bindings


async def test_identical_store_replay_reuses_verified_custody_without_provider_work(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Replay exact bytes through the stable attempt without another put or verify."""
    async with output_custody_harness(
        tmp_path, isolated_database_env, admin_access=admin_access
    ) as harness:
        first = await harness.service.store(harness.request(b"stable replay output"))
        assert first.status == "verified"
        assert first.content_id is not None
        assert first.verification_receipt_id is not None
        assert first.replayed is False
        provider_counts = (harness.store.puts, harness.store.opens)
        assert provider_counts == (1, 1)
        bound = await harness.bind(harness.selector, first)
        assert (
            bound.content_id,
            bound.put_attempt_id,
            bound.verification_receipt_id,
            bound.replayed,
        ) == (
            first.content_id,
            first.put_attempt_id,
            first.verification_receipt_id,
            False,
        )

        replay = await harness.service.store(harness.request(b"stable replay output"))

        assert (
            replay.put_attempt_id,
            replay.content_id,
            replay.verification_receipt_id,
            replay.status,
            replay.replayed,
        ) == (
            first.put_attempt_id,
            first.content_id,
            first.verification_receipt_id,
            "verified",
            True,
        )
        assert (harness.store.puts, harness.store.opens) == provider_counts
        assert (await harness.manager.usage()).reservation_count == 0
        assert list((tmp_path / "output-scratch" / "files").iterdir()) == []
        async with harness.factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactPutAttempt)
                    .where(
                        ArtifactPutAttempt.model_call_attempt_id
                        == str(harness.selector.model_call_attempt_id),
                        ArtifactPutAttempt.logical_role == harness.selector.slot_key,
                    )
                )
                == 1
            )
            assert (
                await session.get(
                    ArtifactVerificationReceipt,
                    str(first.verification_receipt_id),
                )
                is not None
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactVerificationJob)
                    .where(
                        ArtifactVerificationJob.originating_put_attempt_id
                        == str(first.put_attempt_id)
                    )
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactOperationReceipt)
                    .where(ArtifactOperationReceipt.put_attempt_id == str(first.put_attempt_id))
                )
                == 1
            )


async def test_foreign_lineage_and_changed_bytes_fail_before_provider(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Reject coherent foreign ownership before bytes and immutable replay drift before put."""
    async with output_custody_harness(
        tmp_path, isolated_database_env, admin_access=admin_access
    ) as harness:
        original_reservation = harness.state.reservation
        foreign = await harness.seed_reservation(content_sha256=content_sha256(b"foreign control"))
        foreign_selector = selector_for(foreign)

        original = await harness.service.store(harness.request(b"stable output"))
        original_reservation = harness.state.reservation
        original_selector = harness.selector
        assert original.status == "verified"
        harness.state.reservation = foreign
        foreign_result = await harness.service.store(
            harness.request(b"foreign control", selector=foreign_selector)
        )
        assert foreign_result.status == "verified"
        assert foreign_result.verification_receipt_id is not None
        assert harness.store.puts == 2

        harness.state.reservation = original_reservation
        for wrong_selector in (
            foreign_selector,
            original_selector.model_copy(
                update={"model_call_attempt_id": foreign_selector.model_call_attempt_id}
            ),
        ):
            observed: list[bytes] = []
            with pytest.raises(CheckerOutputUnavailable, match="reservation_unavailable"):
                await harness.service.store(
                    harness.request(
                        b"mismatched bytes",
                        selector=wrong_selector,
                        observed=observed,
                    )
                )
            assert observed == []
            assert harness.store.puts == 2
            assert (await harness.manager.usage()).reservation_count == 0

        with pytest.raises(CheckerOutputUnavailable, match="authority_unavailable"):
            await harness.service.store(
                harness.request(b"changed output", selector=original_selector)
            )
        assert harness.store.puts == 2
        assert (await harness.manager.usage()).reservation_count == 0


async def test_binding_rejects_mixed_stored_lineage_before_consumption_or_mutation(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Bind two valid controls, then reject every original/foreign custody mix."""
    async with output_custody_harness(
        tmp_path, isolated_database_env, admin_access=admin_access
    ) as harness:
        original_reservation = harness.state.reservation
        foreign_reservation = await harness.seed_reservation(
            content_sha256=content_sha256(b"foreign binding control")
        )
        foreign_selector = selector_for(foreign_reservation)

        original = await harness.service.store(harness.request(b"original binding control"))
        original_reservation = harness.state.reservation
        original_selector = harness.selector
        harness.state.reservation = foreign_reservation
        foreign = await harness.service.store(
            harness.request(b"foreign binding control", selector=foreign_selector)
        )
        assert original.content_id is not None and original.verification_receipt_id is not None
        assert foreign.content_id is not None and foreign.verification_receipt_id is not None

        harness.state.reservation = original_reservation
        original_bound = await harness.bind(original_selector, original)
        harness.state.reservation = foreign_reservation
        foreign_bound = await harness.bind(foreign_selector, foreign)
        assert (
            original_bound.content_id,
            original_bound.put_attempt_id,
            original_bound.verification_receipt_id,
            original_bound.replayed,
        ) == (
            original.content_id,
            original.put_attempt_id,
            original.verification_receipt_id,
            False,
        )
        assert (
            foreign_bound.content_id,
            foreign_bound.put_attempt_id,
            foreign_bound.verification_receipt_id,
            foreign_bound.replayed,
        ) == (
            foreign.content_id,
            foreign.put_attempt_id,
            foreign.verification_receipt_id,
            False,
        )

        binding_baseline = await harness.binding_rows()
        assert {UUID(row[0]) for row in binding_baseline} == {
            original_bound.binding_id,
            foreign_bound.binding_id,
        }
        consumed_baseline = len(harness.state.bindings)
        assert consumed_baseline == 2

        harness.state.reservation = original_reservation
        for put_attempt_id, receipt_id, failure in (
            (foreign.put_attempt_id, original.verification_receipt_id, "identity_mismatch"),
            (original.put_attempt_id, foreign.verification_receipt_id, "verification_unavailable"),
            (foreign.put_attempt_id, foreign.verification_receipt_id, "identity_mismatch"),
        ):
            async with harness.factory() as session:
                with pytest.raises(CheckerOutputUnavailable, match=failure):
                    async with session.begin():
                        await harness.binding_service(session).bind_checker_output(
                            CheckerOutputBindingRequest(
                                original_selector,
                                put_attempt_id,
                                receipt_id,
                            )
                        )
            assert len(harness.state.bindings) == consumed_baseline
            assert await harness.binding_rows() == binding_baseline


async def test_binding_rollback_and_concurrent_replay_are_atomic(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Keep caller rollback empty and serialize concurrent binding to one row."""
    async with output_custody_harness(
        tmp_path, isolated_database_env, admin_access=admin_access
    ) as harness:
        stored = await harness.service.store(harness.request(b"binding output"))
        assert stored.verification_receipt_id is not None
        request = CheckerOutputBindingRequest(
            harness.selector,
            stored.put_attempt_id,
            stored.verification_receipt_id,
        )

        async with harness.factory() as session:
            transaction = await session.begin()
            rolled_back = await harness.binding_service(session).bind_checker_output(request)
            await transaction.rollback()
        async with harness.factory() as session:
            assert await session.get(ArtifactBinding, str(rolled_back.binding_id)) is None

        async def bind_once():
            async with harness.factory() as session:
                async with session.begin():
                    return await harness.binding_service(session).bind_checker_output(request)

        first, second = await asyncio.gather(bind_once(), bind_once())
        assert first.binding_id == second.binding_id
        assert sorted((first.replayed, second.replayed)) == [False, True]
        async with harness.factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(ArtifactBinding)
                .where(
                    ArtifactBinding.resource_type == "checker_model_call",
                    ArtifactBinding.resource_id == str(harness.selector.model_call_attempt_id),
                    ArtifactBinding.logical_role == harness.selector.slot_key,
                )
            )
            assert count == 1


async def test_unknown_put_is_observed_recovered_and_bound_without_bytes(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Recover lost acknowledgement through typed observation evidence and bind it."""
    async with output_custody_harness(
        tmp_path, isolated_database_env, admin_access=admin_access
    ) as harness:
        harness.store.lose_put_acknowledgement = True
        unknown = await harness.service.store(harness.request(b"observed output"))
        assert unknown.status == "acknowledgement_unknown"
        assert unknown.content_id is None
        assert unknown.verification_receipt_id is None
        assert harness.store.puts == 1

        recovered = await harness.service.recover(harness.selector)
        assert recovered is not None
        assert recovered.put_attempt_id == unknown.put_attempt_id
        assert recovered.status == "verified"
        assert recovered.content_id is not None
        assert recovered.verification_receipt_id is not None
        assert recovered.replayed
        assert harness.store.puts == 1

        async with harness.factory() as session:
            attempt = await session.get(ArtifactPutAttempt, str(recovered.put_attempt_id))
            observation = await session.scalar(
                select(ArtifactPutObservationReceipt).where(
                    ArtifactPutObservationReceipt.put_attempt_id == str(recovered.put_attempt_id)
                )
            )
            direct_receipt = await session.scalar(
                select(ArtifactOperationReceipt).where(
                    ArtifactOperationReceipt.put_attempt_id == str(recovered.put_attempt_id)
                )
            )
            assert attempt is not None and attempt.receipt_id is None
            assert observation is not None and observation.outcome == "observed_confirmed"
            assert direct_receipt is None
            await session.rollback()
            async with session.begin():
                bound = await harness.binding_service(session).bind_checker_output(
                    CheckerOutputBindingRequest(
                        harness.selector,
                        recovered.put_attempt_id,
                        recovered.verification_receipt_id,
                    )
                )
            assert bound.content_id == recovered.content_id


async def test_authority_revocation_during_put_prevents_return_and_binding(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Recheck authority after provider I/O and deny publication after revocation."""
    async with output_custody_harness(
        tmp_path, isolated_database_env, admin_access=admin_access
    ) as harness:
        harness.store.put_entered = asyncio.Event()
        harness.store.put_release = asyncio.Event()
        operation = asyncio.create_task(harness.service.store(harness.request(b"revoked output")))
        await asyncio.wait_for(harness.store.put_entered.wait(), timeout=10)
        async with harness.factory() as probe, probe.begin():
            locked_effect = await probe.scalar(
                select(ModelUsageEffect)
                .where(ModelUsageEffect.id == str(harness.selector.model_call_attempt_id))
                .with_for_update(nowait=True)
            )
            locked_attempt = await probe.scalar(
                select(ArtifactPutAttempt)
                .where(
                    ArtifactPutAttempt.model_call_attempt_id
                    == str(harness.selector.model_call_attempt_id),
                    ArtifactPutAttempt.logical_role == harness.selector.slot_key,
                )
                .with_for_update(nowait=True)
            )
            assert locked_effect is not None and locked_attempt is not None
        harness.state.revoked = True
        harness.store.put_release.set()
        with pytest.raises(CheckerOutputUnavailable, match="authority_revoked"):
            await operation

        async with harness.factory() as session:
            attempt = (
                await session.scalars(
                    select(ArtifactPutAttempt).where(
                        ArtifactPutAttempt.model_call_attempt_id
                        == str(harness.selector.model_call_attempt_id),
                        ArtifactPutAttempt.logical_role == harness.selector.slot_key,
                    )
                )
            ).one()
            receipt = (
                await session.scalars(
                    select(ArtifactVerificationReceipt)
                    .join(ArtifactVerificationJob)
                    .where(ArtifactVerificationJob.originating_put_attempt_id == attempt.id)
                )
            ).one()
            assert attempt is not None and receipt is not None
            attempt_id, receipt_id = UUID(attempt.id), UUID(receipt.id)
            await session.rollback()
            with pytest.raises(CheckerOutputUnavailable, match="authority_revoked"):
                async with session.begin():
                    await harness.binding_service(session).bind_checker_output(
                        CheckerOutputBindingRequest(
                            harness.selector,
                            attempt_id,
                            receipt_id,
                        )
                    )
            binding_count = await session.scalar(
                select(func.count())
                .select_from(ArtifactBinding)
                .where(
                    ArtifactBinding.resource_type == "checker_model_call",
                    ArtifactBinding.resource_id == str(harness.selector.model_call_attempt_id),
                    ArtifactBinding.logical_role == harness.selector.slot_key,
                )
            )
            assert binding_count == 0


async def test_cancellation_during_provider_put_cleans_scratch_and_retains_uncertainty(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Preserve cancellation while retaining only the durable in-flight attempt."""
    async with output_custody_harness(
        tmp_path, isolated_database_env, admin_access=admin_access
    ) as harness:
        harness.store.put_entered = asyncio.Event()
        harness.store.put_release = asyncio.Event()
        operation = asyncio.create_task(harness.service.store(harness.request(b"cancelled output")))
        try:
            await asyncio.wait_for(harness.store.put_entered.wait(), timeout=10)
            assert harness.store.puts == 1
            live_usage = await harness.manager.usage()
            assert live_usage.reservation_count == 1
            assert live_usage.reserved_bytes > 0

            operation.cancel("cancelled checker output provider put")
            with pytest.raises(
                asyncio.CancelledError,
                match="cancelled checker output provider put",
            ):
                await operation
        finally:
            harness.store.put_release.set()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)

        assert harness.store.puts == 1
        assert harness.store.opens == 0
        assert (await harness.manager.usage()).reservation_count == 0
        assert list((tmp_path / "output-scratch" / "files").iterdir()) == []
        async with harness.factory() as session:
            attempt = await session.scalar(
                select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.model_call_attempt_id
                    == str(harness.selector.model_call_attempt_id),
                    ArtifactPutAttempt.logical_role == harness.selector.slot_key,
                )
            )
            assert attempt is not None
            assert attempt.status == "put_in_flight"
            assert attempt.execution_mode == "caller_put"
            assert attempt.executor_id is not None
            assert attempt.lease_expires_at is not None
            assert attempt.replica_id is None
            assert attempt.receipt_id is None
            assert attempt.terminal_result_code is None
            assert attempt.terminal_at is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactOperationReceipt)
                    .where(
                        ArtifactOperationReceipt.model_call_attempt_id
                        == str(harness.selector.model_call_attempt_id),
                        ArtifactOperationReceipt.logical_role == harness.selector.slot_key,
                    )
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactPutObservationReceipt)
                    .where(ArtifactPutObservationReceipt.put_attempt_id == attempt.id)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactVerificationJob)
                    .where(ArtifactVerificationJob.originating_put_attempt_id == attempt.id)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactBinding)
                    .where(
                        ArtifactBinding.resource_type == "checker_model_call",
                        ArtifactBinding.resource_id == str(harness.selector.model_call_attempt_id),
                        ArtifactBinding.logical_role == harness.selector.slot_key,
                    )
                )
                == 0
            )


async def test_per_slot_cap_stops_source_and_cleans_scratch(
    tmp_path,
    isolated_database_env,
    admin_access,
) -> None:
    """Apply the owner-issued cap before excess bytes reach durable intent or provider."""
    async with output_custody_harness(
        tmp_path,
        isolated_database_env,
        admin_access=admin_access,
        maximum_bytes=4,
    ) as harness:
        observed: list[bytes] = []
        request = CheckerOutputArtifactRequest(
            harness.selector,
            byte_stream(b"abcd", b"e", b"must-not-be-read", observed=observed),
        )
        with pytest.raises(ArtifactLimitExceededError):
            await harness.service.store(request)
        assert observed == [b"abcd", b"e"]
        assert harness.store.puts == 0
        assert (await harness.manager.usage()).reservation_count == 0
        assert list((tmp_path / "output-scratch" / "files").iterdir()) == []
        async with harness.factory() as session:
            attempts = await session.scalar(
                select(func.count())
                .select_from(ArtifactPutAttempt)
                .where(
                    ArtifactPutAttempt.model_call_attempt_id
                    == str(harness.selector.model_call_attempt_id),
                    ArtifactPutAttempt.logical_role == harness.selector.slot_key,
                )
            )
            assert attempts == 0
