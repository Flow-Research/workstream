"""Hidden end-to-end proof for exact verified checker-output custody."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.adapters.artifacts import checker_output_binding, checker_output_storage
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactLimitExceededError
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactOperationReceipt,
    ArtifactPutObservationReceipt,
    ArtifactPutAttempt,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.service import ArtifactAdmissionConflictError
from app.modules.checkers.api.output_custody import (
    CheckerOutputArtifactRequest,
    CheckerOutputBindingRequest,
    CheckerOutputSelector,
    CheckerOutputUnavailable,
)
from app.modules.checkers.models import CheckerRun
from tests.checker_output_custody_helpers import (
    byte_stream,
    output_custody_harness,
    selector_for,
)
from tests.checkers.post_submit.support import request as post_submit_request


async def test_default_composition_denies_before_owner_source_or_storage() -> None:
    """Keep both production output capabilities unavailable before protected access."""

    class Forbidden:
        def __getattr__(self, name):
            pytest.fail(f"protected access: {name}")

    @asynccontextmanager
    async def session_scope():
        yield object()

    iterated = False

    async def source():
        nonlocal iterated
        iterated = True
        yield b"must-not-be-read"

    selector = CheckerOutputSelector(
        evaluation=post_submit_request(),
        checker_run_id=new_record_id(),
        worker_lease_id=new_record_id(),
        worker_lease_generation=1,
        slot_key="platform-review",
    )
    forbidden = Forbidden()
    storage = checker_output_storage(
        sessions=session_scope,
        store=forbidden,
        namespace=forbidden,
        preparation=forbidden,
        settings=forbidden,
    )
    with pytest.raises(CheckerOutputUnavailable, match="write_unavailable"):
        await storage.store(CheckerOutputArtifactRequest(selector, source()))
    assert not iterated

    class Transaction:
        def in_transaction(self):
            return True

        def in_nested_transaction(self):
            return False

    binding = checker_output_binding(
        Transaction(),
        namespace=SimpleNamespace(namespace_fingerprint="sha256:" + "0" * 64),
    )
    with pytest.raises(CheckerOutputUnavailable, match="binding_unavailable"):
        await binding.bind_checker_output(
            CheckerOutputBindingRequest(selector, new_record_id(), new_record_id())
        )


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_real_store_verification_and_binding(
    tmp_path,
    isolated_database_env,
    provider,
) -> None:
    """Store, independently verify and bind one exact output through real providers."""
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket

        await provision_minio_bucket.__wrapped__()
    async with output_custody_harness(
        tmp_path,
        isolated_database_env,
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
                "checker_run",
                str(harness.selector.checker_run_id),
                harness.selector.slot_key,
                ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
                "service_identity",
                str(result.put_attempt_id),
                str(result.verification_receipt_id),
            )
        assert harness.state.admissions
        assert harness.state.recoveries
        assert harness.state.bindings


async def test_identical_store_replay_reuses_verified_custody_without_provider_work(
    tmp_path,
    isolated_database_env,
) -> None:
    """Replay exact bytes through the stable attempt without another put or verify."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
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
                        ArtifactPutAttempt.checker_run_id == str(harness.selector.checker_run_id)
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
) -> None:
    """Reject coherent foreign ownership before bytes and immutable replay drift before put."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
        original_reservation = harness.state.reservation
        original_selector = harness.selector
        foreign = await harness.seed_reservation()
        foreign_selector = selector_for(foreign)

        original = await harness.service.store(
            harness.request(b"stable output", selector=original_selector)
        )
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
            original_selector.model_copy(update={"evaluation": foreign.evaluation}),
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

        with pytest.raises(ArtifactAdmissionConflictError):
            await harness.service.store(
                harness.request(b"changed output", selector=original_selector)
            )
        assert harness.store.puts == 2
        assert (await harness.manager.usage()).reservation_count == 0


async def test_binding_rejects_mixed_stored_lineage_before_consumption_or_mutation(
    tmp_path,
    isolated_database_env,
) -> None:
    """Bind two valid controls, then reject every original/foreign custody mix."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
        original_reservation = harness.state.reservation
        original_selector = harness.selector
        foreign_reservation = await harness.seed_reservation()
        foreign_selector = selector_for(foreign_reservation)

        original = await harness.service.store(harness.request(b"original binding control"))
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
) -> None:
    """Keep caller rollback empty and serialize concurrent binding to one row."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
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
                select(func.count()).select_from(ArtifactBinding).where(
                    ArtifactBinding.resource_type == "checker_run",
                    ArtifactBinding.resource_id == str(harness.selector.checker_run_id),
                )
            )
            assert count == 1


async def test_unknown_put_is_observed_recovered_and_bound_without_bytes(
    tmp_path,
    isolated_database_env,
) -> None:
    """Recover lost acknowledgement through typed observation evidence and bind it."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
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


async def test_worker_takeover_recovers_same_attempt_without_bytes(
    tmp_path,
    isolated_database_env,
) -> None:
    """Fence the old lease and recover exact stored custody under its replacement."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
        old_selector = harness.selector
        stored = await harness.service.store(harness.request(b"takeover output"))
        puts = harness.store.puts
        harness.state.reservation = harness.state.reservation.model_copy(
            update={
                "worker_lease_id": new_record_id(),
                "worker_lease_generation": old_selector.worker_lease_generation + 1,
            }
        )

        with pytest.raises(CheckerOutputUnavailable, match="reservation_unavailable"):
            await harness.service.recover(old_selector)
        recovered = await harness.service.recover(harness.selector)
        assert recovered is not None
        assert recovered.put_attempt_id == stored.put_attempt_id
        assert recovered.verification_receipt_id == stored.verification_receipt_id
        assert recovered.replayed
        assert harness.store.puts == puts


async def test_authority_revocation_during_put_prevents_return_and_binding(
    tmp_path,
    isolated_database_env,
) -> None:
    """Recheck authority after provider I/O and deny publication after revocation."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
        harness.store.put_entered = asyncio.Event()
        harness.store.put_release = asyncio.Event()
        operation = asyncio.create_task(harness.service.store(harness.request(b"revoked output")))
        await asyncio.wait_for(harness.store.put_entered.wait(), timeout=10)
        async with harness.factory() as probe, probe.begin():
            locked_run = await probe.scalar(
                select(CheckerRun)
                .where(CheckerRun.id == str(harness.selector.checker_run_id))
                .with_for_update(nowait=True)
            )
            locked_attempt = await probe.scalar(
                select(ArtifactPutAttempt)
                .where(ArtifactPutAttempt.checker_run_id == str(harness.selector.checker_run_id))
                .with_for_update(nowait=True)
            )
            assert locked_run is not None and locked_attempt is not None
        harness.state.revoked = True
        harness.store.put_release.set()
        with pytest.raises(CheckerOutputUnavailable, match="authority_revoked"):
            await operation

        async with harness.factory() as session:
            attempt = (await session.scalars(
                select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.checker_run_id == str(harness.selector.checker_run_id)
                )
            )).one()
            receipt = (await session.scalars(
                select(ArtifactVerificationReceipt).join(ArtifactVerificationJob).where(
                    ArtifactVerificationJob.originating_put_attempt_id == attempt.id
                )
            )).one()
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
                select(func.count()).select_from(ArtifactBinding).where(
                    ArtifactBinding.resource_type == "checker_run",
                    ArtifactBinding.resource_id == str(harness.selector.checker_run_id),
                )
            )
            assert binding_count == 0


async def test_cancellation_during_provider_put_cleans_scratch_and_retains_uncertainty(
    tmp_path,
    isolated_database_env,
) -> None:
    """Preserve cancellation while retaining only the durable in-flight attempt."""
    async with output_custody_harness(tmp_path, isolated_database_env) as harness:
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
                    ArtifactPutAttempt.checker_run_id == str(harness.selector.checker_run_id)
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
                        ArtifactOperationReceipt.checker_run_id
                        == str(harness.selector.checker_run_id)
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
                        ArtifactBinding.resource_type == "checker_run",
                        ArtifactBinding.resource_id == str(harness.selector.checker_run_id),
                    )
                )
                == 0
            )


async def test_per_slot_cap_stops_source_and_cleans_scratch(
    tmp_path,
    isolated_database_env,
) -> None:
    """Apply the owner-issued cap before excess bytes reach durable intent or provider."""
    async with output_custody_harness(
        tmp_path,
        isolated_database_env,
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
                .where(ArtifactPutAttempt.producer_request_type == "checker_output")
            )
            assert attempts == 0
