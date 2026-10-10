"""External checker transport and ART grant remain strict and unselected."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import struct
from uuid import uuid4
import zipfile

import pytest
from pydantic import ValidationError

from app.adapters.checkers.external_service import external_checker_execution_factory
from app.core.config import Settings
from app.interfaces.external_checker_execution import (
    ExternalCheckerIsolationReceipt,
    ExternalCheckerMaterialGrant,
)
from app.interfaces.external_services import (
    ExternalServiceUnavailableError,
    UnknownExternalServiceProviderError,
)
from app.modules.artifacts.preparation import (
    ArtifactScratchIntegrityError,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
    ExternalMaterialFile,
    ExternalMaterialGrantRequest,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
    SubmissionArchiveEntryType,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
    ExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
)
from tests.checkers.external.support import SHA, execution_identity, registry_entry


FIXTURES = Path(__file__).parents[4] / "external_checkers" / "fixtures"


async def _stream(value: bytes):
    yield value


def _request(*, identity=None, archive_sha256=SHA, archive_byte_count=4):
    return make_external_checker_execution_request(
        registry=registry_entry(),
        identity=identity or execution_identity(),
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
        input={"task_version": "v3"},
        input_sha256=external_checker_json_hash({"task_version": "v3"}),
        materials=(
            ExternalCheckerMaterial(
                role="submission_archive",
                content_id=uuid4(),
                replica_id=uuid4(),
                sha256=archive_sha256,
                byte_count=archive_byte_count,
                media_type="application/zip",
            ),
        ),
    )


def test_shared_rust_fixtures_preserve_python_contract_and_derived_digests():
    request = ExternalCheckerExecutionRequest.model_validate_json(
        (FIXTURES / "request.json").read_bytes()
    )
    result = ExternalCheckerExecutionResult.model_validate_json(
        (FIXTURES / "result.json").read_bytes()
    )
    result.validate_request(request)
    assert request.configuration == {"threshold": 1e-6}
    assert request.request_digest == (
        "sha256:81adbc8a7cc0e13b4221ac06ecdd2f95850d6215c3a336d932ad14f8988a70b7"
    )
    changed = request.model_dump(mode="json")
    changed["configuration"]["threshold"] = 2e-6
    with pytest.raises((ExternalCheckerContractError, ValidationError), match="digest mismatch"):
        ExternalCheckerExecutionRequest.model_validate_json(json.dumps(changed))

    for case in json.loads((FIXTURES / "canonical_numbers.json").read_text()):
        assert external_checker_json_hash(json.loads(case["json"])) == (
            "sha256:" + hashlib.sha256(case["canonical"].encode()).hexdigest()
        )


def test_external_service_settings_share_the_art_scratch_root(tmp_path: Path):
    scratch = tmp_path / "scratch"
    settings = Settings(
        artifact_scratch_root=scratch,
        external_checker_service_socket=tmp_path / "service" / "checker.sock",
        external_checker_material_root=scratch,
    )
    assert settings.external_checker_material_root == scratch
    with pytest.raises(ValidationError, match="must be complete"):
        Settings(external_checker_service_socket=tmp_path / "checker.sock")
    with pytest.raises(ValidationError, match="must equal"):
        Settings(
            artifact_scratch_root=scratch,
            external_checker_service_socket=tmp_path / "service" / "checker.sock",
            external_checker_material_root=tmp_path / "other",
        )
    with pytest.raises(ValueError, match="isolation receipt"):
        ExternalCheckerIsolationReceipt(
            repository="--network/host",
            platform_manifest_digest=SHA,
            platform_manifest_media_type="application/vnd.oci.image.manifest.v1+json",
            platform_manifest_byte_count=128,
            operating_system="linux",
            architecture="amd64",
            config_image_id=SHA,
            runtime="runc",
            isolation_mode="docker-dev",
            sandbox_uid=1000,
            sandbox_gid=1000,
        )


@pytest.mark.asyncio
async def test_unix_adapter_revalidates_exact_result_and_factory_is_closed(tmp_path: Path):
    request = _request()
    result = make_external_checker_execution_result(
        request_digest=request.request_digest,
        registry_entry_id=request.registry.registry_entry_id,
        registry_entry_digest=request.registry.entry_digest,
        phase="pre_submit",
        outcome="completed",
        verdict="passed",
        findings=(),
        infrastructure_failure_code=None,
    )
    socket = tmp_path / "checker.sock"

    async def handle(reader, writer):
        size = struct.unpack(">I", await reader.readexactly(4))[0]
        received = json.loads(await reader.readexactly(size))
        if received["operation"] == "health":
            body = json.dumps(
                {
                    "protocol_version": "external_checker_service.v1",
                    "operation": "health",
                    "status": "ready",
                    "operating_system": "linux",
                    "architecture": "amd64",
                    "runtime": "runsc",
                    "isolation_mode": "gvisor",
                    "cached_platform_manifests": 1,
                    "sandbox_uid": 65532,
                    "sandbox_gid": 65532,
                },
                separators=(",", ":"),
            ).encode()
            writer.write(struct.pack(">I", len(body)) + body)
            await writer.drain()
            writer.close()
            return
        assert received["request"]["request_digest"] == request.request_digest
        body = json.dumps(
            {
                "protocol_version": "external_checker_service.v1",
                "result": result.model_dump(mode="json"),
                "isolation": {
                    "repository": "registry.example/workstream/checker",
                    "platform_manifest_digest": request.registry.image_digest,
                    "platform_manifest_media_type": ("application/vnd.oci.image.manifest.v1+json"),
                    "platform_manifest_byte_count": 1367,
                    "operating_system": "linux",
                    "architecture": "amd64",
                    "config_image_id": "sha256:" + "b" * 64,
                    "runtime": "runsc",
                    "isolation_mode": "gvisor",
                    "sandbox_uid": 65532,
                    "sandbox_gid": 65532,
                },
            },
            separators=(",", ":"),
        ).encode()
        writer.write(struct.pack(">I", len(body)) + body)
        await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(handle, socket)
    try:
        factory = external_checker_execution_factory(socket_path=socket, timeout_seconds=90.0)
        adapter = factory.create("unix_socket")
        health = await adapter.health()
        assert health.runtime == "runsc"
        assert health.cached_platform_manifests == 1
        response = await adapter.execute(
            request,
            ExternalCheckerMaterialGrant(
                grant_id="extract_" + "a" * 32,
                binding_digest="sha256:" + "c" * 64,
            ),
        )
        assert response.result == result
        assert response.isolation is not None
        with pytest.raises(UnknownExternalServiceProviderError):
            factory.create("docker")
        short = external_checker_execution_factory(socket_path=socket, timeout_seconds=2.0).create(
            "unix_socket"
        )
        with pytest.raises(ExternalServiceUnavailableError):
            await short.execute(
                request,
                ExternalCheckerMaterialGrant(
                    grant_id="extract_" + "a" * 32,
                    binding_digest="sha256:" + "c" * 64,
                ),
            )
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_unix_adapter_cancellation_closes_the_service_connection(tmp_path: Path):
    socket = tmp_path / "checker.sock"
    received = asyncio.Event()
    disconnected = asyncio.Event()

    async def handle(reader, writer):
        try:
            size = struct.unpack(">I", await reader.readexactly(4))[0]
            await reader.readexactly(size)
            received.set()
            assert await reader.read() == b""
        finally:
            disconnected.set()
            writer.close()

    server = await asyncio.start_unix_server(handle, socket)
    try:
        adapter = external_checker_execution_factory(
            socket_path=socket, timeout_seconds=90.0
        ).create("unix_socket")
        task = asyncio.create_task(
            adapter.execute(
                _request(),
                ExternalCheckerMaterialGrant(
                    grant_id="extract_" + "a" * 32,
                    binding_digest="sha256:" + "c" * 64,
                ),
            )
        )
        await asyncio.wait_for(received.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(disconnected.wait(), 2)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_prepared_zip_issues_request_bound_grant_only_inside_callback(tmp_path: Path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("src/main.txt", b"verified bytes")
        output.writestr("src.txt", b"root bytes sort before child")
    archive_bytes = archive.getvalue()
    root = tmp_path / "scratch"
    manager = ArtifactScratchManager(
        root=root,
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=2 * 512 * 1024 * 1024,
            maximum_files=2,
            maximum_concurrency=2,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30.0,
            total_deadline_seconds=10.0,
            cleanup_margin_seconds=5.0,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024 * 1024,
            maximum_workspace_entries=20,
        ),
    )
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(_stream(archive_bytes), media_type="application/zip")
    inspector = SubmissionArchiveInspector(
        SubmissionArchiveLimits(
            maximum_entries=20,
            maximum_path_bytes=256,
            maximum_path_depth=8,
            maximum_central_directory_bytes=4096,
            maximum_entry_bytes=4096,
            maximum_expanded_bytes=8192,
            maximum_compression_ratio=100,
            maximum_inspection_seconds=5,
        )
    )
    inspection = await prepared.inspect(inspector)
    manifest = build_submission_manifest(inspection)
    identity = execution_identity().model_copy(
        update={"prepared_generation_id": prepared.generation_id}
    )
    request = _request(
        identity=identity,
        archive_sha256=prepared.commitment.sha256,
        archive_byte_count=prepared.commitment.byte_count,
    )
    expected_files = tuple(
        ExternalMaterialFile(
            normalized_path=item.normalized_path,
            byte_count=item.byte_count,
            sha256=item.sha256,
            executable=item.executable,
        )
        for item in inspection.entries
        if item.entry_type is SubmissionArchiveEntryType.FILE
    )
    expected_directories = tuple(
        item.normalized_path
        for item in inspection.entries
        if item.entry_type is SubmissionArchiveEntryType.DIRECTORY
    )
    grant_request = ExternalMaterialGrantRequest(
        request_digest=request.request_digest,
        prepared_generation_id=str(prepared.generation_id),
        attempt_id=str(request.identity.attempt_id),
        attempt_request_digest=request.identity.attempt_request_digest,
        archive_sha256=prepared.commitment.sha256,
        archive_byte_count=prepared.commitment.byte_count,
        semantic_manifest_sha256=manifest.sha256,
        directories=expected_directories,
        files=expected_files,
    )
    observed = {}

    class Processor:
        def abort(self):
            raise AssertionError("grant processor must not be aborted")

        async def process(self, reader, workspace):
            def project(tree):
                assert tree.read_file("src/main.txt", maximum_bytes=64) == b"verified bytes"
                assert tree.read_file("src.txt", maximum_bytes=64) == b"root bytes sort before child"
                with service.external_material_grant(prepared, workspace, grant_request) as grant:
                    grant_root = root / "workspaces" / grant.grant_id
                    body = json.loads((grant_root / ".external-checker-grant.json").read_text())
                    assert body["binding_digest"] == grant.binding_digest
                    assert (
                        grant_root / "workspace" / "src" / "main.txt"
                    ).read_bytes() == b"verified bytes"
                    assert oct((grant_root / "workspace").stat().st_mode & 0o777) == "0o500"
                    observed.update(grant=grant, manifest=body)
                    return grant

            return await asyncio.to_thread(
                inspector.project_and_run,
                reader,
                workspace,
                expected=inspection,
                callback=project,
            )

    grant = await service._process_prepared_submission(
        prepared,
        Processor(),
        reserved_bytes=manifest.total_expanded_bytes,
        maximum_entries=manifest.entry_count + 2,
    )
    assert grant == observed["grant"]
    assert observed["manifest"]["request_digest"] == request.request_digest
    assert list((root / "workspaces").iterdir()) == []
    await prepared.close()
    manager.close()


def test_external_grant_rejects_symlinked_projected_material(tmp_path: Path):
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(minimum_free_bytes=0),
    )
    request = ExternalMaterialGrantRequest(
        request_digest=SHA,
        prepared_generation_id=str(uuid4()),
        attempt_id=str(uuid4()),
        attempt_request_digest=SHA,
        archive_sha256=SHA,
        archive_byte_count=0,
        semantic_manifest_sha256=SHA,
        directories=(),
        files=(),
    )
    with manager.extraction_workspace(reserved_bytes=0, maximum_entries=4) as workspace:
        os.symlink("/etc/passwd", workspace / "escape")
        with pytest.raises(ArtifactScratchIntegrityError, match="not regular"):
            with manager._external_material_grant(workspace, request):
                pass
    manager.close()


def test_external_grant_requires_a_live_prepared_callback(tmp_path: Path):
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(minimum_free_bytes=0),
    )
    service = ArtifactPreparationService(manager)
    request = ExternalMaterialGrantRequest(
        request_digest=SHA,
        prepared_generation_id=str(uuid4()),
        attempt_id=str(uuid4()),
        attempt_request_digest=SHA,
        archive_sha256=SHA,
        archive_byte_count=0,
        semantic_manifest_sha256=SHA,
        directories=(),
        files=(),
    )
    with manager.extraction_workspace(reserved_bytes=0, maximum_entries=4) as workspace:
        with pytest.raises(ArtifactScratchIntegrityError, match="source is unavailable"):
            with service.external_material_grant(object(), workspace, request):
                pass
    manager.close()


def test_external_grant_recomputes_the_semantic_manifest(tmp_path: Path):
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(minimum_free_bytes=0),
    )
    request = ExternalMaterialGrantRequest(
        request_digest=SHA,
        prepared_generation_id=str(uuid4()),
        attempt_id=str(uuid4()),
        attempt_request_digest=SHA,
        archive_sha256=SHA,
        archive_byte_count=0,
        semantic_manifest_sha256=SHA,
        directories=(),
        files=(),
    )
    with manager.extraction_workspace(reserved_bytes=0, maximum_entries=4) as workspace:
        with pytest.raises(ArtifactScratchIntegrityError, match="semantic manifest differs"):
            with manager._external_material_grant(workspace, request):
                pass
    manager.close()
