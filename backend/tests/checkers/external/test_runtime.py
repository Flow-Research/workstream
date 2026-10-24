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

from app.adapters.checkers import (
    configured_external_checker_execution,
    external_checker_execution_factory,
)
from app.adapters.checkers.external_service import (
    EXTERNAL_CHECKER_CAPABILITY_KEY,
    EXTERNAL_CHECKER_PROVIDER_KEY,
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
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
    SubmissionArchiveEntryType,
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
                prepared_generation_id=identity.prepared_generation_id,
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
        "sha256:a06707b14348ffe5ef22a55de8d4ec4845c9029da7180d5731fb2c120b5591f3"
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
        operating_system="linux", architecture="amd64", runtime=runtime,
        isolation_mode=isolation_mode, sandbox_uid=1000, sandbox_gid=1000,
    )
    with pytest.raises(ValueError):
        ExternalCheckerServiceHealth(cached_platform_manifests=1, **shared)
    with pytest.raises(ValueError):
        ExternalCheckerIsolationReceipt(
            repository="registry.example/checker", platform_manifest_digest=SHA,
            platform_manifest_media_type="application/vnd.oci.image.manifest.v1+json",
            platform_manifest_byte_count=128, config_image_id=SHA, **shared,
        )


@pytest.mark.parametrize(
    "runtime,isolation_mode",
    [("runsc", "gvisor"), ("runc", "docker-dev"), ("smolvm", "smol-microvm")],
)
@pytest.mark.asyncio
async def test_unix_adapter_revalidates_exact_result_and_factory_is_closed(
    tmp_path: Path, runtime: str, isolation_mode: str,
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
