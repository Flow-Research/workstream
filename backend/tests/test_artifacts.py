"""Focused tests for artifact namespace fencing after direct-write removal."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.core.config import Settings
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.models import (
    ArtifactOperationReceipt,
    ArtifactReplica,
    ArtifactStorageNamespace,
)
from app.modules.artifacts.service import (
    ArtifactStorageNamespaceError,
    artifact_storage_namespace_spec,
)
from tests.artifact_store_helpers import artifact_admission_limit_settings


def _settings(tmp_path: Path) -> Settings:
    root = tmp_path / "store"
    root.mkdir(mode=0o700, parents=True)
    return Settings(
        **artifact_admission_limit_settings(),
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=root,
        artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_minimum_free_bytes=0,
    )


def _bootstrap(settings: Settings) -> LocalStorageBootstrap:
    assert settings.artifact_local_root is not None
    return LocalStorageBootstrap(
        LocalStorageAdapter(
            root=settings.artifact_local_root,
            buffer_bytes=settings.artifact_stream_buffer_bytes,
            lock_timeout_seconds=settings.artifact_operation_lock_timeout_seconds,
        )
    )


def test_namespace_descriptor_is_canonical_and_excludes_local_path(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    bootstrap = _bootstrap(settings)
    try:
        spec = artifact_storage_namespace_spec(settings, bootstrap)
    finally:
        bootstrap.close()

    assert spec.backend == "local"
    assert spec.adapter == "local"
    assert spec.provider_profile == "local-v2"
    assert spec.namespace_descriptor["provider_profile"] == "local-v2"
    assert str(tmp_path) not in repr(spec.namespace_descriptor)
    assert spec.namespace_fingerprint.startswith("sha256:")


def test_namespace_fingerprint_changes_when_pinned_root_changes(tmp_path: Path) -> None:
    first = _settings(tmp_path / "first")
    second = _settings(tmp_path / "second")
    first_bootstrap = _bootstrap(first)
    second_bootstrap = _bootstrap(second)
    try:
        first_fingerprint = artifact_storage_namespace_spec(
            first,
            first_bootstrap,
        ).namespace_fingerprint
        second_fingerprint = artifact_storage_namespace_spec(
            second,
            second_bootstrap,
        ).namespace_fingerprint
    finally:
        first_bootstrap.close()
        second_bootstrap.close()

    assert first_fingerprint != second_fingerprint


def test_namespace_spec_rejects_adapter_identity_drift(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    class _DriftedBootstrap:
        identity = ExternalServiceAdapterIdentity(
            "artifact_store",
            "s3_compatible",
        )

    with pytest.raises(
        ArtifactStorageNamespaceError,
        match="does not match configuration",
    ):
        artifact_storage_namespace_spec(settings, _DriftedBootstrap())  # type: ignore[arg-type]


def test_models_retain_only_v2_provider_evidence_fields() -> None:
    assert "provider_manifest_id" not in ArtifactReplica.__table__.columns
    assert "retention_state" not in ArtifactReplica.__table__.columns
    assert "provider_receipt_id" not in ArtifactOperationReceipt.__table__.columns
    assert "retention_reference" not in ArtifactOperationReceipt.__table__.columns
    assert "namespace_fingerprint" in ArtifactStorageNamespace.__table__.columns
