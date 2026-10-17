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


def _empty_post_grant_request(*, terminal: bool) -> PostExternalMaterialGrantRequest:
    identifiers = [str(uuid4()) for _ in range(11)]
    return PostExternalMaterialGrantRequest(
        request_digest=SHA,
        submission_id=identifiers[0],
        submission_version=1,
        evaluation_request_id=identifiers[1],
        evaluation_request_digest=SHA,
        evaluation_generation=1,
        attempt_id=identifiers[2],
        result_id=identifiers[3],
        lease_id=identifiers[4],
        lease_generation=1,
        lease_expires_at="2026-10-16T00:00:00Z",
        binding_id=identifiers[5],
        content_id=identifiers[6],
        replica_id=identifiers[7],
        content_sha256=SHA,
        byte_count=0,
        evidence_id=identifiers[8],
        verification_receipt_id=identifiers[9],
        verification_job_id=identifiers[10],
        verification_generation=1,
        namespace_fingerprint=SHA,
        semantic_manifest_sha256=canonical_json_hash(
            {"schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION, "entries": []}
        ),
        registry_capability_id=(
            "workstream.terminal_benchmark_project" if terminal else "acme.safe_archive"
        ),
        registry_capability_version="v1" if terminal else "v1.2.3",
        directories=(),
        files=(),
    )


def test_post_external_grant_uses_existing_workspace_byte_and_entry_ownership(
    tmp_path: Path,
) -> None:
    """Bind runtime scratch to the existing ledger and admit its exact entry limit."""
    maximum_entries = 6
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            minimum_free_bytes=0,
            maximum_workspace_entries=maximum_entries,
        ),
    )
    semantic_manifest_sha256 = canonical_json_hash(
        {"schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION, "entries": []}
    )
    identifiers = [str(uuid4()) for _ in range(11)]
    request = PostExternalMaterialGrantRequest(
        request_digest=SHA,
        submission_id=identifiers[0],
        submission_version=1,
        evaluation_request_id=identifiers[1],
        evaluation_request_digest=SHA,
        evaluation_generation=1,
        attempt_id=identifiers[2],
        result_id=identifiers[3],
        lease_id=identifiers[4],
        lease_generation=1,
        lease_expires_at="2026-10-16T00:00:00Z",
        binding_id=identifiers[5],
        content_id=identifiers[6],
        replica_id=identifiers[7],
        content_sha256=SHA,
        byte_count=0,
        evidence_id=identifiers[8],
        verification_receipt_id=identifiers[9],
        verification_job_id=identifiers[10],
        verification_generation=1,
        namespace_fingerprint=SHA,
        semantic_manifest_sha256=semantic_manifest_sha256,
        registry_capability_id="workstream.terminal_benchmark_project",
        registry_capability_version="v1",
        directories=(),
        files=(),
    )

    with manager.extraction_workspace(reserved_bytes=0, maximum_entries=1) as workspace:
        with manager._external_material_grant(workspace, request) as grant:
            grant_root = tmp_path / "scratch" / "workspaces" / grant.grant_id
            manifest = json.loads(
                (grant_root / ".external-checker-grant.json").read_text()
            )
            assert manifest["runtime_scratch"] == {
                "byte_allowance": HARD_MAXIMUM_ARTIFACT_BYTES,
                "entry_allowance": maximum_entries - 3,
                "gid": os.getgid(),
                "mode": 0o700,
                "uid": os.getuid(),
            }
            ledger = json.loads((tmp_path / "scratch" / ".ledger.json").read_text())
            [reservation] = ledger["workspaces"]
            assert reservation["reserved_bytes"] == HARD_MAXIMUM_ARTIFACT_BYTES
            assert reservation["maximum_entries"] == maximum_entries
            runtime = grant_root / "runtime"
            for index in range(manifest["runtime_scratch"]["entry_allowance"]):
                (runtime / f"entry-{index}").write_bytes(b"")

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()


def test_terminal_grant_holds_aggregate_capacity_until_workspace_release(
    tmp_path: Path,
) -> None:
    """Reject a second expansion without residue, then admit it after release."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            minimum_free_bytes=0,
            maximum_workspace_entries=6,
        ),
    )
    request = _empty_post_grant_request(terminal=True)

    with manager.extraction_workspace(reserved_bytes=0, maximum_entries=4) as first:
        with manager.extraction_workspace(reserved_bytes=0, maximum_entries=4) as second:
            with manager._external_material_grant(first, request):
                with pytest.raises(
                    ArtifactScratchCapacityError,
                    match="artifact scratch byte limit reached",
                ):
                    with manager._external_material_grant(second, request):
                        pytest.fail("second terminal grant exceeded aggregate capacity")
                assert list(second.iterdir()) == []

    with manager.extraction_workspace(reserved_bytes=0, maximum_entries=4) as retry:
        with manager._external_material_grant(retry, request) as grant:
            grant_root = tmp_path / "scratch" / "workspaces" / grant.grant_id
            assert (grant_root / "runtime").is_dir()
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()


def test_conventional_post_grants_keep_small_concurrent_reservations(
    tmp_path: Path,
) -> None:
    """Keep ordinary POST concurrency outside the terminal scratch reservation."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            minimum_free_bytes=0,
            maximum_workspace_entries=6,
        ),
    )
    request = _empty_post_grant_request(terminal=False)

    with manager.extraction_workspace(reserved_bytes=1, maximum_entries=4) as first:
        with manager.extraction_workspace(reserved_bytes=1, maximum_entries=4) as second:
            with manager._external_material_grant(first, request) as first_grant:
                with manager._external_material_grant(second, request) as second_grant:
                    roots = [
                        tmp_path / "scratch" / "workspaces" / item.grant_id
                        for item in (first_grant, second_grant)
                    ]
                    assert all(not (root / "runtime").exists() for root in roots)
                    ledger = json.loads(
                        (tmp_path / "scratch" / ".ledger.json").read_text()
                    )
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
                    sha256=(
                        f"sha256:{hashlib.sha256(submitted_manifest).hexdigest()}"
                    ),
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
    identifiers = [str(uuid4()) for _ in range(11)]
    request = PostExternalMaterialGrantRequest(
        request_digest=SHA,
        submission_id=identifiers[0],
        submission_version=1,
        evaluation_request_id=identifiers[1],
        evaluation_request_digest=SHA,
        evaluation_generation=1,
        attempt_id=identifiers[2],
        result_id=identifiers[3],
        lease_id=identifiers[4],
        lease_generation=1,
        lease_expires_at="2026-10-16T00:00:00Z",
        binding_id=identifiers[5],
        content_id=identifiers[6],
        replica_id=identifiers[7],
        content_sha256=SHA,
        byte_count=len(payload) + len(submitted_manifest),
        evidence_id=identifiers[8],
        verification_receipt_id=identifiers[9],
        verification_job_id=identifiers[10],
        verification_generation=1,
        namespace_fingerprint=SHA,
        semantic_manifest_sha256=semantic_manifest_sha256,
        registry_capability_id="acme.safe_archive",
        registry_capability_version="v1.2.3",
        directories=("runtime", "workspace"),
        files=files,
    )

    with manager.extraction_workspace(
        reserved_bytes=len(payload) + len(submitted_manifest), maximum_entries=5
    ) as extraction:
        (extraction / ".external-checker-grant.json").write_bytes(submitted_manifest)
        (extraction / "runtime").mkdir()
        submitted_workspace = extraction / "workspace"
        submitted_workspace.mkdir()
        (submitted_workspace / "program.py").write_bytes(payload)
        with manager._external_material_grant(extraction, request) as grant:
            grant_root = tmp_path / "scratch" / "workspaces" / grant.grant_id
            assert (grant_root / "workspace/workspace/program.py").read_bytes() == payload
            assert (grant_root / "workspace/runtime").is_dir()
            assert (
                grant_root / "workspace/.external-checker-grant.json"
            ).read_bytes() == submitted_manifest
            assert json.loads((grant_root / ".external-checker-grant.json").read_text())[
                "grant_id"
            ] == grant.grant_id
            manifest = json.loads(
                (grant_root / ".external-checker-grant.json").read_text()
            )
            assert "runtime_scratch" not in manifest
            assert not (grant_root / "runtime").exists()
            [reservation] = json.loads(
                (tmp_path / "scratch" / ".ledger.json").read_text()
            )["workspaces"]
            assert reservation["reserved_bytes"] == len(payload) + len(submitted_manifest)
            assert reservation["maximum_entries"] == 5
            assert not any(
                item.name.startswith(".external-material-")
                for item in grant_root.iterdir()
            )

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()
