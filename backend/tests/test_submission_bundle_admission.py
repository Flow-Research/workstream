"""Focused custody and ordering proof for submission-bundle durable intent."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from app.core.identifiers import new_record_id

import pytest

import app.adapters.artifacts as artifact_adapters
from app.core.config import Settings
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRejected,
)
from app.interfaces.artifacts import (
    ArtifactConfigurationError,
)
from tests.artifact_store_helpers import artifact_admission_limit_settings
from app.main import create_app
from app.api.routes.artifact_submissions import router as submission_router
from app.modules.artifacts.submission_admission import validate_submission_packet_headers


@pytest.mark.asyncio
async def test_artifact_adapter_stale_scratch_cleanup_closes_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SimpleNamespace(cleanup_stale=AsyncMock(return_value=3), close=Mock())
    monkeypatch.setattr(
        artifact_adapters,
        "create_artifact_scratch_manager",
        lambda _settings: manager,
    )

    assert await artifact_adapters.cleanup_stale_artifact_scratch(Settings()) == 3
    manager.cleanup_stale.assert_awaited_once_with()
    manager.close.assert_called_once_with()


def test_artifact_adapter_maps_preparation_limits_from_settings() -> None:
    settings = Settings()

    preparation = artifact_adapters.artifact_preparation_limits(settings)
    archive = artifact_adapters.submission_archive_limits(settings)

    assert preparation.maximum_source_bytes == settings.artifact_maximum_bytes
    assert preparation.maximum_files == settings.artifact_scratch_maximum_files
    assert preparation.stream_buffer_bytes == settings.artifact_stream_buffer_bytes
    assert archive.maximum_entries == settings.artifact_submission_zip_maximum_entries
    assert archive.maximum_entry_bytes == settings.artifact_submission_zip_maximum_entry_bytes
    assert (
        archive.maximum_compression_ratio
        == settings.artifact_submission_zip_maximum_compression_ratio
    )


def test_artifact_adapter_requires_configured_scratch_root() -> None:
    settings = Settings()
    settings.artifact_scratch_root = None

    with pytest.raises(ArtifactConfigurationError):
        artifact_adapters.create_artifact_scratch_manager(settings)


def test_artifact_adapter_builds_configured_local_bootstrap(tmp_path) -> None:
    root = tmp_path / "objects"
    root.mkdir(mode=0o700)
    settings = Settings(
        _env_file=None,
        **artifact_admission_limit_settings(),
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=root,
        artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_minimum_free_bytes=0,
    )

    bootstrap = artifact_adapters.create_artifact_store_bootstrap(settings)

    try:
        assert bootstrap.identity.provider_key == "local"
        assert bootstrap.namespace_identity.provider_profile == "local-v2"
    finally:
        bootstrap.close()


def test_submission_is_public_binary_contract() -> None:
    from fastapi import FastAPI

    app = create_app()
    route = next(
        route
        for route in submission_router.routes
        if getattr(route, "name", None) == "submit_source"
    )
    assert route.include_in_schema is True
    mounted = app.url_path_for("submit_source", task_id=str(new_record_id()))
    assert str(mounted).startswith("/api/v1/tasks/")
    assert str(mounted).endswith("/submissions")
    assert route.methods == {"POST"}
    schema_app = FastAPI()
    schema_app.include_router(submission_router, prefix="/api/v1")
    operation = schema_app.openapi()["paths"]["/api/v1/tasks/{task_id}/submissions"]["post"]
    assert operation["requestBody"]["content"]["application/zip"]["schema"] == {
        "type": "string", "format": "binary",
    }
    required_headers = {parameter["name"] for parameter in operation["parameters"]
                        if parameter["in"] == "header" and parameter["required"]}
    assert {"X-Task-Assignment-Id", "Idempotency-Key"} <= required_headers
    assert operation["responses"]["202"] and operation["responses"]["422"]


def test_submission_packet_headers_reject_non_ascii() -> None:
    validate_submission_packet_headers("plain summary", "plain attestation")
    with pytest.raises(
        SubmissionBundlePreparationRejected,
        match="submission_bundle_packet_header_encoding_invalid",
    ):
        validate_submission_packet_headers("caf\N{LATIN SMALL LETTER E WITH ACUTE}", "ok")
