"""PostgreSQL proof for immutable AWS artifact activation custody."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts.s3_compatible import aws_s3_namespace_fingerprint
from app.core.config import Settings
from app.core.identifiers import new_record_id
from app.db.errors import integrity_constraint_name
from app.interfaces.artifacts import ArtifactProviderLiveProofRequiredError
from app.modules.artifacts.provider_activation import (
    SqlAlchemyArtifactProviderActivationGuard,
    artifact_provider_database_time,
    coordinate_artifact_provider_activation,
    record_artifact_provider_probe_result,
)
from app.modules.artifacts.models import ArtifactProviderProbeResult
from tests.artifact_store_helpers import artifact_admission_limit_settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        **artifact_admission_limit_settings(),
        environment="production",
        artifact_store_backend="s3_compatible",
        artifact_scratch_root=tmp_path / "scratch",
        artifact_s3_provider_profile="aws_s3",
        artifact_s3_region="us-east-1",
        artifact_s3_bucket="workstream-artifacts-prod",
        artifact_s3_private_prefix="workstream/artifacts",
        artifact_s3_credential_mode="aws_workload_identity",
        artifact_s3_aws_workload_identity_method="container-role",
        release_id="sha256:" + "1" * 64,
        artifact_s3_runtime_role_arn="arn:aws:iam::123456789012:role/workstream-runtime",
        artifact_s3_runtime_trust_policy_sha256="sha256:" + "3" * 64,
        artifact_s3_runtime_policy_arn="arn:aws:iam::123456789012:policy/workstream-runtime",
        artifact_s3_readiness_role_arn="arn:aws:iam::123456789012:role/workstream-readiness",
        artifact_s3_readiness_trust_policy_sha256="sha256:" + "4" * 64,
        artifact_s3_readiness_policy_arn="arn:aws:iam::123456789012:policy/workstream-readiness",
        artifact_s3_negative_role_arn="arn:aws:iam::123456789012:role/workstream-negative",
        artifact_s3_negative_trust_policy_sha256="sha256:" + "5" * 64,
        artifact_s3_bootstrap_principal_arn="arn:aws:iam::123456789012:role/workstream-bootstrap",
        artifact_s3_bucket_policy_sha256="sha256:" + "2" * 64,
        artifact_s3_operation_total_timeout_seconds=300,
        artifact_complete_read_deadline_seconds=300,
        artifact_terminal_persistence_margin_seconds=120,
    )


async def _insert_group(
    factory,
    settings: Settings,
    namespace_fingerprint: str,
    group_nonce: UUID,
    *,
    omit: str | None = None,
    fail: str | None = None,
    settings_by_type: dict[str, Settings] | None = None,
    started_at_offsets: dict[str, timedelta] | None = None,
) -> dict[str, UUID]:
    probe_types = ("runtime_immutability", "readiness", "negative_access")
    ids: dict[str, UUID] = {}
    async with factory() as session, session.begin():
        for probe_type in probe_types:
            if probe_type == omit:
                continue
            row_settings = (settings_by_type or {}).get(probe_type, settings)
            principal = {
                "readiness": row_settings.artifact_s3_readiness_role_arn,
                "runtime_immutability": row_settings.artifact_s3_runtime_role_arn,
                "negative_access": row_settings.artifact_s3_negative_role_arn,
            }[probe_type]
            assert principal is not None
            started_at = await artifact_provider_database_time(session)
            started_at -= (started_at_offsets or {}).get(probe_type, timedelta())
            ids[probe_type] = await record_artifact_provider_probe_result(
                session,
                row_settings,
                probe_type=probe_type,  # type: ignore[arg-type]
                namespace_fingerprint=namespace_fingerprint,
                group_nonce=group_nonce,
                expected_principal_arn=principal,
                observed_principal_arn=principal,
                passed=probe_type != fail,
                evidence={"mode": probe_type, "actual_calls": True},
                error_code="access_denied" if probe_type == fail else None,
                started_at=started_at,
            )
    return ids


async def _insert_activation_direct(session, results: dict[str, UUID]) -> UUID:
    """Insert an otherwise canonical activation without using the ART coordinator."""
    activation_id = new_record_id()
    await session.execute(
        text(
            """
            INSERT INTO artifact_provider_activations (
              id,readiness_result_id,runtime_result_id,negative_result_id,
              supersedes_activation_id,proof_version,release_id,namespace_fingerprint,
              aws_partition,aws_account_id,region,runtime_role_arn,
              runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
              readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
              negative_trust_policy_sha256,bootstrap_principal_arn,bucket_policy_sha256,
              group_nonce,activated_at,expires_at)
            SELECT :activation_id,readiness.id,runtime.id,negative.id,NULL,
              readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
              readiness.aws_partition,readiness.aws_account_id,readiness.region,
              readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
              readiness.runtime_policy_arn,readiness.readiness_role_arn,
              readiness.readiness_trust_policy_sha256,readiness.readiness_policy_arn,
              readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
              readiness.bootstrap_principal_arn,readiness.bucket_policy_sha256,
              readiness.group_nonce,clock_timestamp(),
              least(readiness.expires_at,runtime.expires_at,negative.expires_at)
            FROM artifact_provider_probe_results readiness,
                 artifact_provider_probe_results runtime,
                 artifact_provider_probe_results negative
            WHERE readiness.id=:readiness_id
              AND runtime.id=:runtime_id
              AND negative.id=:negative_id
            """
        ),
        {
            "activation_id": str(activation_id),
            "readiness_id": str(results["readiness"]),
            "runtime_id": str(results["runtime_immutability"]),
            "negative_id": str(results["negative_access"]),
        },
    )
    return activation_id


@pytest.mark.asyncio
async def test_overlapping_exact_groups_activate_and_latest_is_selected_deterministically(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        first_group, second_group = uuid4(), uuid4()
        await _insert_group(factory, settings, namespace, first_group)
        async with factory() as session, session.begin():
            first_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=first_group,
            )
        await _insert_group(factory, settings, namespace, second_group)
        async with factory() as session, session.begin():
            second_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=second_group,
            )

        lease = await SqlAlchemyArtifactProviderActivationGuard(
            factory,
            settings,
        ).select_for_call(namespace_fingerprint=namespace)
        assert first_id != second_id
        assert lease.activation_id == second_id
        async with factory() as session:
            predecessor = await session.scalar(
                text(
                    "select supersedes_activation_id from artifact_provider_activations "
                    "where id=:id"
                ),
                {"id": second_id},
            )
        assert str(predecessor) == str(first_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("started_before_runtime", ["readiness", "negative_access"])
async def test_activation_rejects_probes_started_before_runtime_completed(
    isolated_database_env: str,
    tmp_path: Path,
    started_before_runtime: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        await _insert_group(
            factory,
            settings,
            namespace,
            group_nonce,
            started_at_offsets={started_before_runtime: timedelta(minutes=1)},
        )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="runtime challenge was not established first",
        ):
            async with factory() as session, session.begin():
                await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace,
                    group_nonce=group_nonce,
                )
        async with factory() as session:
            assert (
                await session.scalar(text("select count(*) from artifact_provider_activations"))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("started_before_runtime", ["readiness", "negative_access"])
async def test_activation_trigger_rejects_probes_started_before_runtime_completed(
    isolated_database_env: str,
    tmp_path: Path,
    started_before_runtime: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        invalid_results = await _insert_group(
            factory,
            settings,
            namespace,
            uuid4(),
            started_at_offsets={started_before_runtime: timedelta(minutes=1)},
        )
        with pytest.raises(DBAPIError) as failure:
            async with factory() as session, session.begin():
                await _insert_activation_direct(session, invalid_results)
        assert failure.value.orig.sqlstate == "23514"  # type: ignore[attr-defined]

        valid_results = await _insert_group(factory, settings, namespace, uuid4())
        async with factory() as session, session.begin():
            activation_id = await _insert_activation_direct(session, valid_results)
        async with factory() as session:
            stored_id = await session.scalar(
                text("select id from artifact_provider_activations where id=:id"),
                {"id": str(activation_id)},
            )
        assert str(stored_id) == str(activation_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_activation_guard_uses_real_postgresql_across_two_sync_task_loops(
    isolated_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.adapters.artifacts import internal_workers
    from app.workers.async_runner import run_async_task

    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        await _insert_group(factory, settings, namespace, group_nonce)
        async with factory() as session, session.begin():
            activation_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=group_nonce,
            )
    finally:
        await engine.dispose()

    monkeypatch.setattr(internal_workers, "get_database_url", lambda: isolated_database_env)
    guard = internal_workers._LoopScopedArtifactProviderActivationGuard(settings)

    async def select_in_owned_loop() -> UUID:
        async with internal_workers._artifact_worker_database():
            lease = await guard.select_for_call(namespace_fingerprint=namespace)
            return lease.activation_id

    assert run_async_task(select_in_owned_loop) == activation_id
    assert run_async_task(select_in_owned_loop) == activation_id


@pytest.mark.asyncio
async def test_mixed_or_incomplete_nonce_group_cannot_activate(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_group, second_group = uuid4(), uuid4()
    try:
        await _insert_group(
            factory,
            settings,
            namespace,
            first_group,
            omit="negative_access",
        )
        await _insert_group(
            factory,
            settings,
            namespace,
            second_group,
            omit="readiness",
        )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="incomplete or mixed",
        ):
            async with factory() as session, session.begin():
                await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace,
                    group_nonce=first_group,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["failed", "binding_drift"])
async def test_failed_or_mixed_binding_group_cannot_activate(
    isolated_database_env: str,
    tmp_path: Path,
    case: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        if case == "failed":
            await _insert_group(
                factory,
                settings,
                namespace,
                group_nonce,
                fail="negative_access",
            )
        else:
            drifted = settings.model_copy(
                update={"artifact_s3_negative_trust_policy_sha256": "sha256:" + "6" * 64}
            )
            await _insert_group(
                factory,
                settings,
                namespace,
                group_nonce,
                settings_by_type={"negative_access": drifted},
            )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="incomplete or mixed",
        ):
            async with factory() as session, session.begin():
                await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace,
                    group_nonce=group_nonce,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overlap", "constraint_name"),
    [
        ("role", "ck_artifact_provider_probe_results_roles_distinct"),
        (
            "trust_digest",
            "ck_artifact_provider_probe_results_trust_digests_distinct",
        ),
    ],
)
async def test_direct_probe_insert_rejects_shared_executor_bindings(
    isolated_database_env: str,
    tmp_path: Path,
    overlap: str,
    constraint_name: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_group = uuid4()
    try:
        rows = await _insert_group(factory, settings, namespace, source_group)
        with pytest.raises(IntegrityError) as failure:
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO artifact_provider_probe_results (
                          id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at)
                        SELECT :id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,
                          CASE WHEN :overlap='role' THEN runtime_role_arn
                               ELSE readiness_role_arn END,
                          CASE WHEN :overlap='trust_digest' THEN runtime_trust_policy_sha256
                               ELSE readiness_trust_policy_sha256 END,
                          readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          CASE WHEN :overlap='role' THEN runtime_role_arn
                               ELSE expected_principal_arn END,
                          CASE WHEN :overlap='role' THEN runtime_role_arn
                               ELSE observed_principal_arn END,
                          bucket_policy_sha256,
                          :group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at
                        FROM artifact_provider_probe_results WHERE id=:source_id
                        """
                    ),
                    {
                        "id": str(new_record_id()),
                        "overlap": overlap,
                        "group_nonce": str(uuid4()),
                        "source_id": str(rows["readiness"]),
                    },
                )
        assert integrity_constraint_name(failure.value) == constraint_name

        async with factory() as session:
            constraint_names = set(
                (
                    await session.execute(
                        text(
                            """
                            SELECT conname FROM pg_catalog.pg_constraint
                            WHERE conrelid IN (
                              'public.artifact_provider_probe_results'::regclass,
                              'public.artifact_provider_activations'::regclass)
                            """
                        )
                    )
                ).scalars()
            )
        assert {
            "ck_artifact_provider_probe_results_roles_distinct",
            "ck_artifact_provider_probe_results_trust_digests_distinct",
            "ck_artifact_provider_activations_roles_distinct",
            "ck_artifact_provider_activations_trust_digests_distinct",
        } <= constraint_names
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expired_direct_probe_group_cannot_activate(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_group, expired_group = uuid4(), uuid4()
    try:
        rows = await _insert_group(factory, settings, namespace, source_group)
        async with factory() as session, session.begin():
            for source_id in rows.values():
                await session.execute(
                    text(
                        """
                        INSERT INTO artifact_provider_probe_results (
                          id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at)
                        SELECT :id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          :group_nonce,evidence_sha256,error_code,
                          statement_timestamp()-interval '16 minutes',
                          statement_timestamp()-interval '15 minutes 30 seconds',
                          statement_timestamp()-interval '1 minute'
                        FROM artifact_provider_probe_results WHERE id=:source_id
                        """
                    ),
                    {
                        "id": str(new_record_id()),
                        "group_nonce": str(expired_group),
                        "source_id": str(source_id),
                    },
                )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="incomplete or mixed",
        ):
            async with factory() as session, session.begin():
                await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace,
                    group_nonce=expired_group,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_probe_and_activation_rows_reject_mutation_and_deletion(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        results = await _insert_group(factory, settings, namespace, group_nonce)
        async with factory() as session, session.begin():
            activation_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=group_nonce,
            )
        for statement, identifier in (
            (
                "update artifact_provider_probe_results set result='fail' where id=:id",
                results["readiness"],
            ),
            ("delete from artifact_provider_activations where id=:id", activation_id),
        ):
            with pytest.raises(DBAPIError):
                async with factory() as session, session.begin():
                    await session.execute(text(statement), {"id": identifier})
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_probe_recorder_rejects_a_principal_from_another_proof_mode(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            started_at = await artifact_provider_database_time(session)
            with pytest.raises(
                ArtifactProviderLiveProofRequiredError,
                match="does not match its proof mode",
            ):
                await record_artifact_provider_probe_result(
                    session,
                    settings,
                    probe_type="readiness",
                    namespace_fingerprint=namespace,
                    group_nonce=uuid4(),
                    expected_principal_arn=settings.artifact_s3_runtime_role_arn,  # type: ignore[arg-type]
                    observed_principal_arn=settings.artifact_s3_runtime_role_arn,
                    passed=True,
                    evidence={"mode": "readiness", "actual_calls": True},
                    error_code=None,
                    started_at=started_at,
                )
            assert (
                await session.scalar(select(func.count()).select_from(ArtifactProviderProbeResult))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_direct_probe_insert_with_cross_mode_principal(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        rows = await _insert_group(factory, settings, namespace, group_nonce)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO artifact_provider_probe_results (
                          id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at)
                        SELECT :id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          runtime_role_arn,runtime_role_arn,bucket_policy_sha256,
                          :group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at
                        FROM artifact_provider_probe_results WHERE id=:source_id
                        """
                    ),
                    {
                        "id": str(new_record_id()),
                        "group_nonce": str(uuid4()),
                        "source_id": str(rows["readiness"]),
                    },
                )
        async with factory() as session, session.begin():
            activation_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=group_nonce,
            )
        assert type(activation_id) is UUID
    finally:
        await engine.dispose()
