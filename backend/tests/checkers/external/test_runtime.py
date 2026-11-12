"""External checker transport and ART grant remain strict and unselected."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import struct
from uuid import uuid4
import zipfile

import pytest

from tests.trusted_intake_fixtures import assert_sealed_export
from pydantic import ValidationError

from app.adapters.checkers import (
    configured_external_checker_execution,
    external_checker_execution_factory,
)
from app.adapters.checkers.external_service import (
    EXTERNAL_CHECKER_CAPABILITY_KEY,
    EXTERNAL_CHECKER_PROVIDER_KEY,
    UnixSocketExternalCheckerAdapter,
)
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.interfaces.external_checker_execution import (
    ExternalCheckerIsolationReceipt,
    ExternalCheckerMaterialGrant,
    ExternalCheckerServiceHealth,
)
from app.interfaces.external_services import (
    ExternalServiceUnavailableError,
    UnknownExternalServiceProviderError,
)
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchCapacityError,
    ArtifactScratchIntegrityError,
    ArtifactScratchManager,
    ExternalMaterialFile,
    ExternalMaterialGrantRequest,
    PostExternalMaterialGrantItem,
    PostExternalMaterialGrantRequest,
)
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveLimits,
    SubmissionArchiveEntryType,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.artifacts.submission_manifest import SUBMISSION_MANIFEST_SCHEMA_VERSION
from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
    PostSubmitExternalCheckerMaterial,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
)
from tests.checkers.external.support import SHA, execution_identity, registry_entry


FIXTURES = Path(__file__).parents[4] / "external_checkers" / "fixtures"


async def _stream(value: bytes):
    yield value


def _request(*, identity=None, archive_sha256=SHA, archive_byte_count=4):
    identity = identity or execution_identity()
    return make_external_checker_execution_request(
        registry=registry_entry(),
        identity=identity,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
        input={"task_version": "v3"},
        input_sha256=external_checker_json_hash({"task_version": "v3"}),
        materials=(
            PreSubmitExternalCheckerMaterial(
                role="submission_archive",
                operation_id=identity.operation_id, source_sha256=identity.source_sha256,
            lease_id=identity.lease_id, lease_generation=identity.lease_generation,
                attempt_id=identity.attempt_id,
                attempt_request_digest=identity.attempt_request_digest,
                archive_sha256=archive_sha256,
                archive_byte_count=archive_byte_count,
                semantic_manifest_sha256=SHA,
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
        "sha256:147cd4a72624caf97ec7ee167d00e1f76d2a9c89d0bda84134b6f1ac01a47a79"
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
    assert settings.external_checker_service_timeout_seconds == 3660.0
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
async def test_configured_execution_defers_absent_fixed_provider_until_invocation():
    adapter = configured_external_checker_execution(Settings())

    assert adapter.identity.capability_key == EXTERNAL_CHECKER_CAPABILITY_KEY
    assert adapter.identity.provider_key == EXTERNAL_CHECKER_PROVIDER_KEY
    with pytest.raises(ExternalServiceUnavailableError) as invocation:
        await adapter.execute(_request(), object())
    assert invocation.value.identity == adapter.identity
    with pytest.raises(ExternalServiceUnavailableError) as health:
        await adapter.health()
    assert health.value.identity == adapter.identity


def test_service_runtime_files_stay_outside_art_scratch_custody(tmp_path: Path):
    """A live or crashed service cannot poison ART's closed root layout."""
    scratch = tmp_path / "scratch"
    socket_root = tmp_path / "service"
    socket_root.mkdir(mode=0o700)
    stdout = socket_root / ".workstream-checker-runtime-owned.stdout"
    stderr = socket_root / ".workstream-checker-runtime-owned.stderr"
    with stdout.open("xb") as output, stderr.open("xb") as error:
        output.write(b"preserved stdout")
        error.write(b"preserved stderr")
        limits = ArtifactPreparationLimits(
            aggregate_reserved_bytes=2 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=1,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30.0,
            total_deadline_seconds=10.0,
            cleanup_margin_seconds=5.0,
            stream_buffer_bytes=2,
            maximum_source_bytes=64,
        )
        manager = ArtifactScratchManager(root=scratch, limits=limits)
        manager.close()
    assert stdout.read_bytes() == b"preserved stdout"
    assert stderr.read_bytes() == b"preserved stderr"
    reopened = ArtifactScratchManager(root=scratch, limits=limits)
    reopened.close()

    wrong_root = scratch / stdout.name
    wrong_root.write_bytes(b"must not share ART root")
    with pytest.raises(ValueError, match="dedicated directory"):
        ArtifactScratchManager(root=scratch, limits=limits)


@pytest.mark.parametrize(
    "runtime,isolation_mode",
    [("runc", "gvisor"), ("smolvm", "docker-dev"), ("runsc", "smol-microvm")],
)
def test_receipts_cannot_misrepresent_an_engine_as_another_isolation(runtime, isolation_mode):
    shared = dict(
        operating_system="linux",
        architecture="amd64",
        runtime=runtime,
        isolation_mode=isolation_mode,
        sandbox_uid=1000,
        sandbox_gid=1000,
    )
    with pytest.raises(ValueError):
        ExternalCheckerServiceHealth(cached_platform_manifests=1, **shared)
    with pytest.raises(ValueError):
        ExternalCheckerIsolationReceipt(
            repository="registry.example/checker",
            platform_manifest_digest=SHA,
            platform_manifest_media_type="application/vnd.oci.image.manifest.v1+json",
            platform_manifest_byte_count=128,
            config_image_id=SHA,
            **shared,
        )


@pytest.mark.parametrize(
    "runtime,isolation_mode",
    [("runsc", "gvisor"), ("runc", "docker-dev"), ("smolvm", "smol-microvm")],
)
@pytest.mark.asyncio
async def test_unix_adapter_revalidates_exact_result_and_factory_is_closed(
    tmp_path: Path,
    runtime: str,
    isolation_mode: str,
):
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
                    "runtime": runtime,
                    "isolation_mode": isolation_mode,
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
        assert received["model_grant"] is None
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
                    "runtime": runtime,
                    "isolation_mode": isolation_mode,
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
        assert health.runtime == runtime
        assert health.isolation_mode == isolation_mode
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
        assert response.isolation.runtime == runtime
        assert response.isolation.isolation_mode == isolation_mode
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
                assert (
                    tree.read_file("src.txt", maximum_bytes=64) == b"root bytes sort before child"
                )
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


def _post_grant_item(
    *,
    role: str,
    submission_id,
    submission_version: int,
    source: bytes,
    projected_name: str,
    projected: bytes,
) -> PostExternalMaterialGrantItem:
    file = ExternalMaterialFile(
        normalized_path=projected_name,
        byte_count=len(projected),
        sha256=f"sha256:{hashlib.sha256(projected).hexdigest()}",
        executable=False,
    )
    semantic_manifest_sha256 = canonical_json_hash(
        {
            "schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION,
            "entries": [
                {
                    "normalized_path": file.normalized_path,
                    "entry_type": "file",
                    "byte_count": file.byte_count,
                    "sha256": file.sha256,
                    "executable": file.executable,
                }
            ],
        }
    )
    return PostExternalMaterialGrantItem(
        material=PostSubmitExternalCheckerMaterial(
            role=role,
            submission_id=submission_id,
            submission_version=submission_version,
            binding_id=uuid4(),
            content_id=uuid4(),
            replica_id=uuid4(),
            content_sha256=f"sha256:{hashlib.sha256(source).hexdigest()}",
            byte_count=len(source),
            media_type="application/zip",
            evidence_id=uuid4(),
            verification_receipt_id=uuid4(),
            verification_job_id=uuid4(),
            verification_generation=1,
            namespace_fingerprint=SHA,
            semantic_manifest_sha256=semantic_manifest_sha256,
        ),
        directories=(),
        files=(file,),
    )


async def _post_prepared_pair(tmp_path: Path):
    current_source = b"current archive bytes"
    prior_source = b"predecessor archive bytes"
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=2,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30.0,
            total_deadline_seconds=10.0,
            cleanup_margin_seconds=5.0,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024,
            maximum_workspace_entries=16,
        ),
    )
    service = ArtifactPreparationService(manager)
    current = await service.prepare(_stream(current_source), media_type="application/zip")
    prior = await service.prepare(_stream(prior_source), media_type="application/zip")
    identity = execution_identity("post_submit")
    current_item = _post_grant_item(
        role="submission_archive",
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        source=current_source,
        projected_name="current.txt",
        projected=b"projected current",
    )
    prior_item = _post_grant_item(
        role="predecessor_submission_archive",
        submission_id=uuid4(),
        submission_version=identity.submission_version - 1,
        source=prior_source,
        projected_name="prior.txt",
        projected=b"projected prior",
    )
    assert current.commitment.sha256 == current_item.material.content_sha256
    assert prior.commitment.sha256 == prior_item.material.content_sha256
    return manager, service, current, prior, identity, current_item, prior_item


@pytest.mark.asyncio
async def test_post_aggregate_reuses_materials_for_context_and_current_only_grants(
    tmp_path: Path,
) -> None:
    """Two selected bindings reuse one verified aggregate without exposing hidden prior."""
    (
        manager,
        service,
        current,
        prior,
        identity,
        current_item,
        prior_item,
    ) = await _post_prepared_pair(tmp_path)
    sources = (
        ("submission_archive", current),
        ("predecessor_submission_archive", prior),
    )
    context_request = PostExternalMaterialGrantRequest(
        request_digest="sha256:" + "b" * 64,
        identity=identity,
        evaluation_context_sha256="sha256:" + "c" * 64,
        materials=(current_item, prior_item),
        visible_roles=("submission_archive", "predecessor_submission_archive"),
    )
    current_only_request = PostExternalMaterialGrantRequest(
        request_digest="sha256:" + "d" * 64,
        identity=identity,
        evaluation_context_sha256=None,
        materials=(current_item, prior_item),
        visible_roles=("submission_archive",),
    )
    observed: list[tuple[object, dict[str, object]]] = []

    class Processor:
        def abort(self) -> None:
            raise AssertionError("aggregate grant processor must not be aborted")

        async def process(self, readers, workspace):
            assert set(readers) == {
                "submission_archive",
                "predecessor_submission_archive",
            }
            assert readers["submission_archive"].read() == b"current archive bytes"
            assert readers["predecessor_submission_archive"].read() == (
                b"predecessor archive bytes"
            )
            materials = workspace / "materials"
            materials.mkdir()
            for item, contents in (
                (current_item, b"projected current"),
                (prior_item, b"projected prior"),
            ):
                role_root = materials / item.material.role
                role_root.mkdir()
                (role_root / item.files[0].normalized_path).write_bytes(contents)
            [workspace_reservation] = json.loads(
                (tmp_path / "scratch" / ".ledger.json").read_text()
            )["workspaces"]
            assert workspace_reservation["reserved_bytes"] == (
                len(b"current archive bytes") + len(b"predecessor archive bytes")
            )
            assert workspace_reservation["maximum_entries"] == 6
            for request in (context_request, current_only_request):
                with service.post_external_material_grant(sources, workspace, request) as grant:
                    grant_root = tmp_path / "scratch" / "workspaces" / grant.grant_id
                    manifest_path = grant_root / ".external-checker-grant.json"
                    manifest = json.loads(manifest_path.read_text())
                    assert manifest["binding_digest"] == grant.binding_digest
                    assert [item["material"]["role"] for item in manifest["materials"]] == [
                        "submission_archive",
                        "predecessor_submission_archive",
                    ]
                    assert manifest["visible_roles"] == list(request.visible_roles)
                    assert not (grant_root / "workspace").exists()
                    assert (grant_root / "materials/submission_archive/current.txt").is_file()
                    assert (
                        grant_root / "materials/predecessor_submission_archive/prior.txt"
                    ).is_file()
                    observed.append((grant, manifest))
                assert not manifest_path.exists()

            current_file = materials / "submission_archive/current.txt"
            current_file.chmod(0o600)
            current_file.write_bytes(b"substituted")
            with pytest.raises(
                ArtifactScratchIntegrityError,
                match="inventory differs",
            ):
                with service.post_external_material_grant(sources, workspace, current_only_request):
                    pass
            return tuple(item[0] for item in observed)

    grants = await service._process_prepared_post_submission(
        sources,
        Processor(),
        reserved_bytes=len(b"current archive bytes") + len(b"predecessor archive bytes"),
        maximum_entries=6,
    )
    assert grants[0].grant_id == grants[1].grant_id
    assert grants[0].binding_digest != grants[1].binding_digest
    assert observed[0][1]["evaluation_context_sha256"] == "sha256:" + "c" * 64
    assert observed[1][1]["evaluation_context_sha256"] is None
    assert observed[1][1]["visible_roles"] == ["submission_archive"]
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    assert not service._external_grant_workspaces
    await current.close()
    await prior.close()
    assert (await manager.usage()).reservation_count == 0
    manager.close()


def _empty_post_grant_request() -> PostExternalMaterialGrantRequest:
    identity = execution_identity("post_submit")
    semantic_manifest_sha256 = canonical_json_hash(
        {"schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION, "entries": []}
    )
    item = PostExternalMaterialGrantItem(
        material=PostSubmitExternalCheckerMaterial(
            role="submission_archive",
            submission_id=identity.submission_id,
            submission_version=identity.submission_version,
            binding_id=uuid4(),
            content_id=uuid4(),
            replica_id=uuid4(),
            content_sha256=SHA,
            byte_count=0,
            media_type="application/zip",
            evidence_id=uuid4(),
            verification_receipt_id=uuid4(),
            verification_job_id=uuid4(),
            verification_generation=1,
            namespace_fingerprint=SHA,
            semantic_manifest_sha256=semantic_manifest_sha256,
        ),
        directories=(),
        files=(),
    )
    return PostExternalMaterialGrantRequest(
        request_digest=SHA,
        identity=identity,
        evaluation_context_sha256=None,
        materials=(item,),
        visible_roles=("submission_archive",),
    )


def test_post_grants_keep_small_concurrent_reservations(
    tmp_path: Path,
) -> None:
    """Preserve simultaneous POST grants without expanding their reserved capacity."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            minimum_free_bytes=0,
            maximum_workspace_entries=6,
        ),
    )
    request = _empty_post_grant_request()

    with manager.extraction_workspace(reserved_bytes=1, maximum_entries=4) as first:
        with manager.extraction_workspace(reserved_bytes=1, maximum_entries=4) as second:
            for workspace in (first, second):
                materials = workspace / "materials"
                materials.mkdir()
                (materials / "submission_archive").mkdir()
            with manager._external_material_grant(first, request) as first_grant:
                with manager._external_material_grant(second, request) as second_grant:
                    roots = [
                        tmp_path / "scratch" / "workspaces" / item.grant_id
                        for item in (first_grant, second_grant)
                    ]
                    assert all(not (root / "runtime").exists() for root in roots)
                    ledger = json.loads((tmp_path / "scratch" / ".ledger.json").read_text())
                    assert [item["reserved_bytes"] for item in ledger["workspaces"]] == [
                        1,
                        1,
                    ]
                    assert [item["maximum_entries"] for item in ledger["workspaces"]] == [
                        4,
                        4,
                    ]
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()


def test_post_external_grant_preserves_submitted_reserved_names(
    tmp_path: Path,
) -> None:
    """Move submitted reserved names below ART's distinct grant control paths."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            minimum_free_bytes=0,
            maximum_workspace_entries=16,
        ),
    )
    payload = b"print('starter')\n"
    submitted_manifest = b"submitted project file\n"
    files = tuple(
        sorted(
            (
                ExternalMaterialFile(
                    normalized_path=".external-checker-grant.json",
                    byte_count=len(submitted_manifest),
                    sha256=f"sha256:{hashlib.sha256(submitted_manifest).hexdigest()}",
                    executable=False,
                ),
                ExternalMaterialFile(
                    normalized_path="workspace/program.py",
                    byte_count=len(payload),
                    sha256=f"sha256:{hashlib.sha256(payload).hexdigest()}",
                    executable=False,
                ),
            ),
            key=lambda item: item.normalized_path,
        )
    )
    manifest_entries = sorted(
        [
            {"normalized_path": "runtime", "entry_type": "directory"},
            {"normalized_path": "workspace", "entry_type": "directory"},
            *(
                {
                    "normalized_path": file.normalized_path,
                    "entry_type": "file",
                    "byte_count": file.byte_count,
                    "sha256": file.sha256,
                    "executable": file.executable,
                }
                for file in files
            ),
        ],
        key=lambda item: item["normalized_path"],
    )
    semantic_manifest_sha256 = canonical_json_hash(
        {
            "schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION,
            "entries": manifest_entries,
        }
    )
    identity = execution_identity("post_submit")
    material = PostSubmitExternalCheckerMaterial(
        role="submission_archive",
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        binding_id=uuid4(),
        content_id=uuid4(),
        replica_id=uuid4(),
        content_sha256=SHA,
        byte_count=len(payload) + len(submitted_manifest),
        media_type="application/zip",
        evidence_id=uuid4(),
        verification_receipt_id=uuid4(),
        verification_job_id=uuid4(),
        verification_generation=1,
        namespace_fingerprint=SHA,
        semantic_manifest_sha256=semantic_manifest_sha256,
    )
    request = PostExternalMaterialGrantRequest(
        request_digest=SHA,
        identity=identity,
        evaluation_context_sha256=None,
        materials=(
            PostExternalMaterialGrantItem(
                material=material,
                directories=("runtime", "workspace"),
                files=files,
            ),
        ),
        visible_roles=("submission_archive",),
    )

    with manager.extraction_workspace(
        reserved_bytes=len(payload) + len(submitted_manifest), maximum_entries=6
    ) as extraction:
        materials = extraction / "materials"
        materials.mkdir()
        submitted = materials / "submission_archive"
        submitted.mkdir()
        (submitted / ".external-checker-grant.json").write_bytes(submitted_manifest)
        (submitted / "runtime").mkdir()
        submitted_workspace = submitted / "workspace"
        submitted_workspace.mkdir()
        (submitted_workspace / "program.py").write_bytes(payload)
        for digest in (SHA, "sha256:" + "9" * 64):
            with manager._external_material_grant(
                extraction, replace(request, request_digest=digest)
            ) as grant:
                grant_root = tmp_path / "scratch" / "workspaces" / grant.grant_id
                assert (
                    grant_root / "materials/submission_archive/workspace/program.py"
                ).read_bytes() == payload
                assert (grant_root / "materials/submission_archive/runtime").is_dir()
                assert (
                    grant_root / "materials/submission_archive/.external-checker-grant.json"
                ).read_bytes() == submitted_manifest
                manifest = json.loads((grant_root / ".external-checker-grant.json").read_text())
                assert (
                    manifest["grant_id"] == grant.grant_id and manifest["request_digest"] == digest
                )
                assert "runtime_scratch" not in manifest
                assert not (grant_root / "runtime").exists()
                [reservation] = json.loads((tmp_path / "scratch" / ".ledger.json").read_text())[
                    "workspaces"
                ]
                assert reservation["reserved_bytes"] == len(payload) + len(submitted_manifest)
                assert reservation["maximum_entries"] == 6
                assert not any(
                    item.name.startswith(".external-material-") for item in grant_root.iterdir()
                )
            assert_sealed_export(materials)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()


def test_post_aggregate_workspace_enforces_combined_quota_and_cleanup(
    tmp_path: Path,
) -> None:
    """One aggregate workspace may exceed one archive but never the root quota."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=2 * HARD_MAXIMUM_ARTIFACT_BYTES,
            minimum_free_bytes=0,
            maximum_workspace_entries=4,
        ),
    )
    combined = HARD_MAXIMUM_ARTIFACT_BYTES + 1
    with manager.extraction_workspace(reserved_bytes=combined, maximum_entries=0):
        [reservation] = json.loads((tmp_path / "scratch" / ".ledger.json").read_text())[
            "workspaces"
        ]
        assert reservation["reserved_bytes"] == combined
        with pytest.raises(ArtifactScratchCapacityError, match="byte limit"):
            with manager.extraction_workspace(
                reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
                maximum_entries=0,
            ):
                pass
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_post_aggregate_rejects_duplicate_sources_and_drains_cancellation(
    tmp_path: Path,
) -> None:
    """Duplicate custody is rejected before scratch; cancellation drains both readers."""
    (
        manager,
        service,
        current,
        prior,
        _identity,
        _current_item,
        _prior_item,
    ) = await _post_prepared_pair(tmp_path)

    class Uncalled:
        def abort(self) -> None:
            raise AssertionError("duplicate source processor must not be aborted")

        async def process(self, readers, workspace):
            raise AssertionError("duplicate source processor must not run")

    with pytest.raises(ArtifactScratchIntegrityError, match="duplicated"):
        await service._process_prepared_post_submission(
            (
                ("submission_archive", current),
                ("predecessor_submission_archive", current),
            ),
            Uncalled(),
            reserved_bytes=1,
            maximum_entries=1,
        )
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []

    entered = asyncio.Event()
    aborted = asyncio.Event()

    class Blocking:
        def abort(self) -> None:
            aborted.set()

        async def process(self, readers, workspace):
            assert set(readers) == {
                "submission_archive",
                "predecessor_submission_archive",
            }
            entered.set()
            await aborted.wait()
            raise RuntimeError("aborted callback result must not replace cancellation")

    task = asyncio.create_task(
        service._process_prepared_post_submission(
            (
                ("submission_archive", current),
                ("predecessor_submission_archive", prior),
            ),
            Blocking(),
            reserved_bytes=1,
            maximum_entries=1,
        )
    )
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert aborted.is_set()
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    assert not service._external_grant_workspaces
    await current.close()
    await prior.close()
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.parametrize("with_model_grant", [False, True])
async def test_public_trace_preserves_execution_arguments(monkeypatch, tmp_path, with_model_grant):
    """The opt-in observer must remain transparent to the current adapter port."""
    import runpy
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.adapters.artifacts.trusted_intake import UnixSocketTrustedIntakeAdapter
    from app.adapters.checkers.external_service import UnixSocketExternalCheckerAdapter

    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("WORKSTREAM_PROBE_INTAKE_TRACE", str(trace))
    original_prepare = UnixSocketTrustedIntakeAdapter.prepare
    monkeypatch.setattr(UnixSocketTrustedIntakeAdapter, "prepare", original_prepare)
    expected = object()
    execute = AsyncMock(return_value=expected)
    monkeypatch.setattr(UnixSocketExternalCheckerAdapter, "execute", execute)
    probe = Path(__file__).resolve().parents[4] / "experiments/pilot04_external_checker_runtime/public_intake_observer.py"
    runpy.run_path(str(probe))
    adapter, grant = object(), object()
    model_grant = object() if with_model_grant else None
    request = SimpleNamespace(request_digest="sha256:" + "a" * 64)
    actual = await UnixSocketExternalCheckerAdapter.execute(
        adapter, request, grant, model_grant=model_grant,
    )
    assert actual is expected
    execute.assert_awaited_once_with(adapter, request, grant, model_grant=model_grant)
    assert [json.loads(line)["event"] for line in trace.read_text().splitlines()] == [
        "project_started", "project_completed",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [None, "source_hash", "source_short", "source_long", "result_fence", "trailing", "chunk_oversized", "slow_decode"])
async def test_single_pre_transport_streams_source_and_validates_combined_result(tmp_path, monkeypatch, changed):
    from dataclasses import replace
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitLeaseFacts
    from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitInfrastructureUnavailable
    from tests.checkers.external.test_selected_pre_submit_coordination import (
        _source_reservation, _source_completed_execution,
    )

    payload = b"controlled transport bytes" * 4000
    reservation = _source_reservation()
    reservation = replace(reservation, source=reservation.source.model_copy(update={
        "raw_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "raw_byte_count": len(payload),
    }))
    execution = _source_completed_execution(reservation)
    lease = SelectedPreSubmitLeaseFacts(
        reservation, execution.lease_id, execution.lease_generation, reservation.pre_deadline_at,
    )
    body = execution.canonical_body()
    if changed == "result_fence":
        body["lease_generation"] += 1
    received = bytearray()
    sizes = []
    finished = asyncio.Event()
    requests = []

    async def handle(reader, writer):
        try:
            size = struct.unpack(">I", await reader.readexactly(4))[0]
            requests.append(json.loads(await reader.readexactly(size)))
            while True:
                size = struct.unpack(">I", await reader.readexactly(4))[0]
                if size == 0:
                    break
                sizes.append(size)
                received.extend(await reader.readexactly(size))
            response = json.dumps(body).encode()
            writer.write(struct.pack(">I", len(response)) + response)
            if changed == "trailing":
                writer.write(b"extra")
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass  # A refused source must close transport before the EOF marker.
        finally:
            writer.close()
            await writer.wait_closed()
            finished.set()

    class Grant:
        closed = False
        calls = 0

        async def open_source(self, *, lease):
            assert lease == expected_lease
            self.calls += 1
            try:
                data = (payload[:-1] if changed == "source_short" else
                        payload + b"!" if changed == "source_long" else
                        b"x" * len(payload) if changed == "source_hash" else payload)
                if changed == "chunk_oversized":
                    yield data
                else:
                    for offset in range(0, len(data), 16 * 1024):
                        yield data[offset:offset + 16 * 1024]
            finally:
                self.closed = True

    decode_called = []
    if changed == "slow_decode":
        import time
        from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitExecutionFacts
        decode = SelectedPreSubmitExecutionFacts.from_canonical_body
        def delayed_decode(cls, value):
            decode_called.append(True)
            time.sleep(0.3)
            return decode(value)
        monkeypatch.setattr(SelectedPreSubmitExecutionFacts, "from_canonical_body", classmethod(delayed_decode))
    expected_lease = lease
    grant = Grant()
    socket = tmp_path / "pre.sock"
    server = await asyncio.start_unix_server(handle, socket)
    adapter = UnixSocketExternalCheckerAdapter(
        socket_path=socket, timeout_seconds=0.2 if changed == "slow_decode" else 5.0,
    )
    processor = SelectedPreSubmitProcessor(lease=lease, execution=adapter)
    try:
        if changed is None:
            assert await processor.process(grant) == execution
            assert bytes(received) == payload
            assert sizes and max(sizes) <= 64 * 1024
            with pytest.raises(SelectedPreSubmitInfrastructureUnavailable, match="material_unavailable"):
                await processor.process(grant)
        else:
            code = "deadline_exceeded" if changed == "slow_decode" else "invalid_output"
            with pytest.raises(SelectedPreSubmitInfrastructureUnavailable, match=code):
                await processor.process(grant)
        if changed == "slow_decode":
            assert decode_called == [True]
        if changed == "chunk_oversized":
            assert not sizes
        await asyncio.wait_for(finished.wait(), 2)
        assert grant.closed and grant.calls == 1
        assert len(requests) == 1 and requests[0]["operation"] == "execute_pre"
        assert requests[0]["reservation"] == reservation.canonical_body()
        assert "grant" not in requests[0] and "prepared_generation_id" not in requests[0]
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_single_pre_expired_lease_does_not_open_source_or_runtime(tmp_path):
    from datetime import datetime, timedelta, timezone
    from app.modules.checkers.api.selected_pre_submit import (
        SelectedPreSubmitLeaseFacts, SelectedPreSubmitInfrastructureUnavailable,
    )
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    lease = SelectedPreSubmitLeaseFacts(
        _source_reservation(), uuid4(), 1, datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    class NoSource:
        def open_source(self, **kwargs):
            raise AssertionError("expired execution opened source")

    adapter = UnixSocketExternalCheckerAdapter(socket_path=tmp_path / "absent.sock", timeout_seconds=5.0)
    with pytest.raises(SelectedPreSubmitInfrastructureUnavailable, match="deadline_exceeded"):
        await adapter.execute_pre(lease, NoSource())


@pytest.mark.asyncio
async def test_single_pre_cancellation_closes_source_and_transport(tmp_path):
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitLeaseFacts
    from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    entered, source_closed, connection_closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    reservation = _source_reservation()
    lease = SelectedPreSubmitLeaseFacts(reservation, uuid4(), 1, reservation.pre_deadline_at)
    class Grant:
        async def open_source(self, *, lease):
            try:
                entered.set()
                await asyncio.Event().wait()
                yield b"unreachable"
            finally:
                source_closed.set()

    async def handle(reader, writer):
        try:
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            connection_closed.set()

    socket = tmp_path / "cancel.sock"
    server = await asyncio.start_unix_server(handle, socket)
    adapter = UnixSocketExternalCheckerAdapter(socket_path=socket, timeout_seconds=5.0)
    processor = SelectedPreSubmitProcessor(lease=lease, execution=adapter)
    task = asyncio.create_task(processor.process(Grant()))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        processor.abort()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(connection_closed.wait(), 2)
        assert source_closed.is_set()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        server.close()
        await server.wait_closed()
