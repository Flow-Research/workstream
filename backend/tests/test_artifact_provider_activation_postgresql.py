"""PostgreSQL proof for immutable AWS artifact activation custody."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
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
from tests.trusted_intake_fixtures import LocalIntakeAdapter


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


def _roles_anywhere_settings(tmp_path: Path) -> Settings:
    """Select the exact mutable certificate resources for custody tests."""
    return _settings(tmp_path).model_copy(
        update={
            "artifact_s3_aws_workload_identity_method": "roles-anywhere",
            "artifact_s3_roles_anywhere_trust_anchor_arn": (
                "arn:aws:rolesanywhere:us-east-1:123456789012:trust-anchor/"
                "01234567-89ab-cdef-0123-456789abcdef"
            ),
            "artifact_s3_roles_anywhere_trust_anchor_sha256": "sha256:" + "6" * 64,
            "artifact_s3_roles_anywhere_profile_arn": (
                "arn:aws:rolesanywhere:us-east-1:123456789012:profile/"
                "11234567-89ab-cdef-0123-456789abcdef"
            ),
            "artifact_s3_roles_anywhere_profile_sha256": "sha256:" + "7" * 64,
            "artifact_s3_roles_anywhere_role_arn": (
                "arn:aws:iam::123456789012:role/workstream-runtime"
            ),
            "artifact_s3_roles_anywhere_certificate_file": tmp_path / "identity.crt",
            "artifact_s3_roles_anywhere_private_key_file": tmp_path / "identity.key",
        }
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


async def _insert_activation_direct(
    session,
    results: dict[str, UUID],
    *,
    backdate_activated_at: bool = False,
) -> UUID:
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
              negative_trust_policy_sha256,roles_anywhere_trust_anchor_arn,
              roles_anywhere_trust_anchor_sha256,roles_anywhere_profile_arn,
              roles_anywhere_profile_sha256,bootstrap_principal_arn,bucket_policy_sha256,
              group_nonce,activated_at,expires_at)
            SELECT :activation_id,readiness.id,runtime.id,negative.id,NULL,
              readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
              readiness.aws_partition,readiness.aws_account_id,readiness.region,
              readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
              readiness.runtime_policy_arn,readiness.readiness_role_arn,
              readiness.readiness_trust_policy_sha256,readiness.readiness_policy_arn,
              readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
              readiness.roles_anywhere_trust_anchor_arn,
              readiness.roles_anywhere_trust_anchor_sha256,
              readiness.roles_anywhere_profile_arn,
              readiness.roles_anywhere_profile_sha256,
              readiness.bootstrap_principal_arn,readiness.bucket_policy_sha256,
              readiness.group_nonce,
              CASE WHEN :backdate_activated_at
                THEN runtime.started_at ELSE clock_timestamp() END,
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
            "backdate_activated_at": backdate_activated_at,
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
async def test_direct_activation_rejects_one_mixed_roles_anywhere_profile_digest(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    """The database guard independently compares all four mutable custody fields."""
    settings = _roles_anywhere_settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    changed = settings.model_copy(
        update={"artifact_s3_roles_anywhere_profile_sha256": "sha256:" + "8" * 64}
    )
    try:
        results = await _insert_group(
            factory,
            settings,
            namespace,
            group_nonce,
            settings_by_type={"negative_access": changed},
        )
        with pytest.raises(DBAPIError, match="activation proof group is invalid"):
            async with factory() as session, session.begin():
                await _insert_activation_direct(session, results)
        # Test-of-test: the same otherwise-valid rows are admitted when the
        # activation comparison predicate is transactionally removed.
        async with factory() as session:
            transaction = await session.begin()
            try:
                await session.execute(
                    text(
                        """
                        CREATE OR REPLACE FUNCTION public.guard_artifact_provider_activation()
                        RETURNS trigger LANGUAGE plpgsql
                        SET search_path=pg_catalog,public,pg_temp AS $$
                        BEGIN
                          IF TG_OP<>'INSERT' THEN
                            RAISE EXCEPTION 'artifact provider activations are immutable'
                              USING ERRCODE='55000';
                          END IF;
                          RETURN NEW;
                        END $$
                        """
                    )
                )
                accepted_id = await _insert_activation_direct(session, results)
                assert await session.scalar(
                    text("select id from artifact_provider_activations where id=:id"),
                    {"id": str(accepted_id)},
                ) == accepted_id
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("custody_values", "constraint_name"),
    [
        (
            {
                "anchor_arn": None,
                "anchor_sha256": "sha256:" + "6" * 64,
                "profile_arn": (
                    "arn:aws:rolesanywhere:us-east-1:123456789012:profile/"
                    "11234567-89ab-cdef-0123-456789abcdef"
                ),
                "profile_sha256": "sha256:" + "7" * 64,
            },
            "ck_artifact_provider_probe_results_roles_anywhere_custody",
        ),
        (
            {
                "anchor_arn": (
                    "arn:aws:rolesanywhere:us-east-1:123456789012:trust-anchor/"
                    "01234567-89ab-cdef-0123-456789abcdef"
                ),
                "anchor_sha256": None,
                "profile_arn": (
                    "arn:aws:rolesanywhere:us-east-1:123456789012:profile/"
                    "11234567-89ab-cdef-0123-456789abcdef"
                ),
                "profile_sha256": "sha256:" + "7" * 64,
            },
            "ck_artifact_provider_probe_results_roles_anywhere_custody",
        ),
        (
            {
                "anchor_arn": (
                    "arn:aws:rolesanywhere:us-east-1:123456789012:trust-anchor/"
                    "01234567-89ab-cdef-0123-456789abcdef"
                ),
                "anchor_sha256": "sha256:" + "6" * 64,
                "profile_arn": None,
                "profile_sha256": "sha256:" + "7" * 64,
            },
            "ck_artifact_provider_probe_results_roles_anywhere_custody",
        ),
        (
            {
                "anchor_arn": (
                    "arn:aws:rolesanywhere:us-east-1:123456789012:trust-anchor/"
                    "01234567-89ab-cdef-0123-456789abcdef"
                ),
                "anchor_sha256": "sha256:" + "6" * 64,
                "profile_arn": (
                    "arn:aws:rolesanywhere:us-east-1:123456789012:profile/"
                    "11234567-89ab-cdef-0123-456789abcdef"
                ),
                "profile_sha256": None,
            },
            "ck_artifact_provider_probe_results_roles_anywhere_custody",
        ),
        (
            {
                "anchor_arn": (
                    "arn:aws:rolesanywhere:us-west-2:123456789012:trust-anchor/"
                    "01234567-89ab-cdef-0123-456789abcdef"
                ),
                "anchor_sha256": "sha256:" + "6" * 64,
                "profile_arn": (
                    "arn:aws:rolesanywhere:us-east-1:123456789012:profile/"
                    "11234567-89ab-cdef-0123-456789abcdef"
                ),
                "profile_sha256": "sha256:" + "7" * 64,
            },
            "ck_artifact_provider_probe_results_roles_anywhere_custody",
        ),
    ],
)
async def test_probe_database_requires_all_or_exact_scoped_roles_anywhere_custody(
    isolated_database_env: str,
    tmp_path: Path,
    custody_values: dict[str, str | None],
    constraint_name: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        rows = await _insert_group(factory, settings, namespace, uuid4())
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
                          negative_trust_policy_sha256,roles_anywhere_trust_anchor_arn,
                          roles_anywhere_trust_anchor_sha256,roles_anywhere_profile_arn,
                          roles_anywhere_profile_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at)
                        SELECT :id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,:anchor_arn,:anchor_sha256,
                          :profile_arn,:profile_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          :group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at
                        FROM artifact_provider_probe_results WHERE id=:source_id
                        """
                    ),
                    {
                        **custody_values,
                        "id": str(new_record_id()),
                        "group_nonce": str(uuid4()),
                        "source_id": str(rows["readiness"]),
                    },
                )
        assert integrity_constraint_name(failure.value) == constraint_name
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_activation_database_requires_each_roles_anywhere_custody_field(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    """Each nullable column is mandatory when an activation carries custody."""
    settings = _roles_anywhere_settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        results = await _insert_group(factory, settings, namespace, uuid4())
        async with factory() as session, session.begin():
            activation_id = await _insert_activation_direct(session, results)

        async with factory() as session:
            transaction = await session.begin()
            try:
                await session.execute(
                    text(
                        """
                        CREATE OR REPLACE FUNCTION public.guard_artifact_provider_activation()
                        RETURNS trigger LANGUAGE plpgsql
                        SET search_path=pg_catalog,public,pg_temp AS $$
                        BEGIN
                          RETURN NEW;
                        END $$
                        """
                    )
                )
                for field in (
                    "roles_anywhere_trust_anchor_arn",
                    "roles_anywhere_trust_anchor_sha256",
                    "roles_anywhere_profile_arn",
                    "roles_anywhere_profile_sha256",
                ):
                    with pytest.raises(IntegrityError) as failure:
                        async with session.begin_nested():
                            await session.execute(
                                text(
                                    f"UPDATE artifact_provider_activations SET {field}=NULL "
                                    "WHERE id=:id"
                                ),
                                {"id": str(activation_id)},
                            )
                    assert integrity_constraint_name(failure.value) == (
                        "ck_artifact_provider_activations_roles_anywhere_custody"
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_roles_anywhere_runtime_cannot_reuse_cross_method_activation(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    container_settings = _settings(tmp_path)
    roles_settings = _roles_anywhere_settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(container_settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        await _insert_group(factory, container_settings, namespace, group_nonce)
        async with factory() as session, session.begin():
            await coordinate_artifact_provider_activation(
                session,
                container_settings,
                namespace_fingerprint=namespace,
                group_nonce=group_nonce,
            )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="requires fresh exact live proof",
        ):
            await SqlAlchemyArtifactProviderActivationGuard(
                factory, roles_settings
            ).select_for_call(namespace_fingerprint=namespace)
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
async def test_activation_rejects_proof_sequence_beyond_fixed_allowance(
    isolated_database_env: str,
    tmp_path: Path,
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
            started_at_offsets={"runtime_immutability": timedelta(seconds=121)},
        )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="proof sequence exceeded its fixed allowance",
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
async def test_activation_trigger_rejects_proof_sequence_beyond_fixed_allowance(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        results = await _insert_group(
            factory,
            settings,
            namespace,
            uuid4(),
            started_at_offsets={"runtime_immutability": timedelta(seconds=121)},
        )
        with pytest.raises(DBAPIError) as failure:
            async with factory() as session, session.begin():
                await _insert_activation_direct(
                    session,
                    results,
                    backdate_activated_at=True,
                )
        assert failure.value.orig.sqlstate == "23514"  # type: ignore[attr-defined]
        assert "proof sequence exceeded fixed allowance" in str(failure.value.orig)
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


_WORKER_PROVIDER_REF = "sha256/00/" + "0" * 62


class _WorkerCompositionClient:
    """Observe the SDK boundary below the real PostgreSQL activation guard."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def head_object(self, **_kwargs: object) -> dict[str, int]:
        self._events.append("transport")
        return {"ContentLength": 1}


async def _cache_native_aws_worker_runtime(
    *,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> UUID:
    """Initialize once, then leave the process runtime cached outside its loop scope."""
    import app.core.config as config
    import app.adapters.artifacts as artifact_adapter
    from app.adapters.artifacts import internal_workers

    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(database_url)
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

    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(artifact_adapter, "trusted_submission_intake", lambda _settings: LocalIntakeAdapter())
    monkeypatch.setattr(internal_workers, "get_settings", lambda: settings)
    monkeypatch.setattr(internal_workers, "get_database_url", lambda: database_url)
    assert internal_workers._runtime is None
    await internal_workers.initialize_artifact_internal_runtime()
    assert internal_workers._runtime is not None
    assert internal_workers._loop_sessions.get() is None
    return activation_id


async def _change_cached_worker_activation(
    database_url: str,
    activation_id: UUID,
    state: str,
) -> None:
    """Model proof loss after startup without weakening the production guard."""
    if state == "valid":
        return
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("ALTER TABLE artifact_provider_activations DISABLE TRIGGER USER")
            )
            try:
                if state == "missing":
                    await connection.execute(
                        text("DELETE FROM artifact_provider_activations WHERE id=:id"),
                        {"id": str(activation_id)},
                    )
                else:
                    assert state == "expired"
                    await connection.execute(
                        text(
                            "UPDATE artifact_provider_activations "
                            "SET activated_at=clock_timestamp() - interval '2 seconds', "
                            "expires_at=clock_timestamp() - interval '1 second' "
                            "WHERE id=:id"
                        ),
                        {"id": str(activation_id)},
                    )
            finally:
                await connection.execute(
                    text("ALTER TABLE artifact_provider_activations ENABLE TRIGGER USER")
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer", ["guide", "post_submit"])
@pytest.mark.parametrize(
    "outcome",
    ["valid", "missing", "expired", "exception", "cancellation"],
)
async def test_cached_native_aws_worker_consumers_retain_activation_scope_through_cleanup(
    isolated_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    consumer: str,
    outcome: str,
) -> None:
    """Keep real activation custody live through I/O and all consumer cleanup."""
    import app.adapters.artifacts as artifact_adapter
    from app.adapters.artifacts import internal_workers
    from app.interfaces.artifacts import ArtifactProviderLiveProofRequiredError
    from app.modules.artifacts import guide_document_access
    from app.modules.checkers.api import external_policy

    settings = _settings(tmp_path)
    activation_id = await _cache_native_aws_worker_runtime(
        database_url=isolated_database_env,
        monkeypatch=monkeypatch,
        settings=settings,
    )
    try:
        await _change_cached_worker_activation(
            isolated_database_env,
            activation_id,
            outcome if outcome in {"missing", "expired"} else "valid",
        )
    except BaseException:
        internal_workers.shutdown_artifact_internal_runtime()
        raise

    events: list[str] = []
    operation_entered = asyncio.Event()
    business_sessions = object()
    runtime = internal_workers._runtime
    assert runtime is not None
    store = runtime[1]

    @asynccontextmanager
    async def client():
        yield _WorkerCompositionClient(events)

    monkeypatch.setattr(store, "_client", client)

    original_worker_database = internal_workers._artifact_worker_database

    @asynccontextmanager
    async def observed_worker_database():
        events.append("scope-enter")
        try:
            async with original_worker_database() as sessions:
                yield sessions
        finally:
            assert internal_workers._loop_sessions.get() is None
            events.append("scope-exit")

    monkeypatch.setattr(
        internal_workers,
        "_artifact_worker_database",
        observed_worker_database,
    )

    class Manager:
        def close(self) -> None:
            assert internal_workers._loop_sessions.get() is not None
            events.append("manager-close")

    monkeypatch.setattr(
        artifact_adapter,
        "create_artifact_scratch_manager",
        lambda _settings: Manager(),
    )

    async def complete_operation() -> None:
        if outcome == "exception":
            raise RuntimeError("controlled consumer failure")
        if outcome == "cancellation":
            operation_entered.set()
            await asyncio.Event().wait()

    class Grant:
        def __init__(self, sessions, selected_store, *_args, **_kwargs) -> None:
            assert sessions is business_sessions
            assert selected_store is store

        @asynccontextmanager
        async def open(self, _handle: str):
            try:
                await store.head(_WORKER_PROVIDER_REF)
                await complete_operation()
                yield SimpleNamespace()
            finally:
                assert internal_workers._loop_sessions.get() is not None
                events.append("prepared-close")

        async def close(self) -> None:
            assert internal_workers._loop_sessions.get() is not None
            events.append("grant-close")

    class Materialization:
        async def materialize(self, _facts, _consumer):
            try:
                await store.head(_WORKER_PROVIDER_REF)
                await complete_operation()
                return "materialized"
            finally:
                assert internal_workers._loop_sessions.get() is not None
                events.append("prepared-close")

    monkeypatch.setattr(guide_document_access, "ScopedGuideDocumentGrant", Grant)

    def compose_materialization(**kwargs):
        assert kwargs["sessions"] is business_sessions
        assert kwargs["store"] is store
        assert isinstance(kwargs["intake"], LocalIntakeAdapter)
        return Materialization()

    monkeypatch.setattr(
        artifact_adapter,
        "post_submission_materialization",
        compose_materialization,
    )
    monkeypatch.setattr(
        external_policy,
        "selected_post_submit_execution_budget_ms",
        lambda *_args, **_kwargs: 1,
    )

    async def invoke():
        if consumer == "guide":
            configuration = SimpleNamespace(
                timeout_seconds=30,
                maximum_document_bytes=1024,
            )
            async with artifact_adapter.guide_document_access_runtime(
                business_sessions,
                uuid4(),
                SimpleNamespace(),
                configuration,
            ) as grant:
                async with grant.open("assigned-handle"):
                    return "opened"
        facts = SimpleNamespace(request=SimpleNamespace(policy=object()))
        return await artifact_adapter.worker_post_submission_materialization(
            sessions=business_sessions
        ).materialize(facts, object())

    try:
        if outcome in {"missing", "expired"}:
            with pytest.raises(
                ArtifactProviderLiveProofRequiredError,
                match="requires fresh exact live proof",
            ):
                await invoke()
        elif outcome == "exception":
            with pytest.raises(RuntimeError, match="controlled consumer failure"):
                await invoke()
        elif outcome == "cancellation":
            task = asyncio.create_task(invoke())
            await asyncio.wait_for(operation_entered.wait(), timeout=10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await invoke() == ("opened" if consumer == "guide" else "materialized")

        assert internal_workers._runtime_active_operations == 0
        assert internal_workers._loop_sessions.get() is None
        assert events[0] == "scope-enter"
        assert events[-1] == "scope-exit"
        assert events.index("prepared-close") < events.index("manager-close")
        if consumer == "guide":
            assert events.index("grant-close") < events.index("manager-close")
        if outcome in {"missing", "expired"}:
            assert "transport" not in events
        else:
            assert events.count("transport") == 1
    finally:
        internal_workers.shutdown_artifact_internal_runtime()


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
