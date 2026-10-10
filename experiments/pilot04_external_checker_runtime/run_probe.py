"""Run the unselected Rust service against one real local digest-pinned image."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from uuid import uuid4
from urllib.request import Request, urlopen
import zipfile

from app.adapters.checkers import external_checker_execution_factory
from app.core.identifiers import new_record_id
from app.interfaces.external_checker_execution import ExternalCheckerMaterialGrant
from app.modules.artifacts.preparation import (
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
    ExternalMaterialFile,
    ExternalMaterialGrantRequest,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveEntryType,
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api.external import (
    ExternalCheckerMaterial,
    ExternalCheckerRegistryEntry,
    ExternalCheckerResourceLimits,
    ExternalCheckerSchema,
    ExternalCheckerRegistrySpec,
    PreSubmitExternalCheckerIdentity,
    external_checker_json_hash,
    make_external_checker_execution_request,
)
from tests.checkers.external.support import registry_spec


async def _stream(value: bytes):
    yield value


def _image_identity(reference: str) -> dict[str, str]:
    raw = subprocess.run(
        ["/usr/bin/docker", "image", "inspect", "--format", "{{json .}}", reference],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    value = json.loads(raw)
    repository, digest = reference.split("@", 1)
    if reference not in value["RepoDigests"]:
        raise RuntimeError("probe image lacks the requested repository digest")
    registry, image_name = repository.split("/", 1)
    if registry.split(":", 1)[0] not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("probe accepts only an isolated local registry")
    manifest_request = Request(
        f"http://{registry}/v2/{image_name}/manifests/{digest}",
        method="HEAD",
        headers={
            "Accept": (
                "application/vnd.oci.image.manifest.v1+json,"
                "application/vnd.docker.distribution.manifest.v2+json"
            )
        },
    )
    with urlopen(manifest_request, timeout=2) as response:
        media_type = response.headers["Content-Type"]
        byte_count = int(response.headers["Content-Length"])
        observed_digest = response.headers["Docker-Content-Digest"]
    if observed_digest != digest:
        raise RuntimeError("probe registry returned another manifest digest")
    return {
        "repository": repository,
        "platform_manifest_digest": digest,
        "platform_manifest_media_type": media_type,
        "platform_manifest_byte_count": byte_count,
        "operating_system": value["Os"],
        "architecture": value["Architecture"],
        "config_image_id": value["Id"],
    }


async def run(reference: str, service_binary: Path) -> dict[str, object]:
    image = _image_identity(reference)
    root = Path(tempfile.mkdtemp(prefix="ws-pilot-backend-p04-probe-"))
    scratch = root / "material"
    socket_root = root / "socket"
    scratch.mkdir(mode=0o700)
    socket_root.mkdir(mode=0o700)
    socket = socket_root / "checker.sock"
    config = {
        "socket_path": str(socket),
        "material_root": str(scratch),
        "docker_binary": "/usr/bin/docker",
        "runtime": "runc",
        "isolation_mode": "docker-dev",
        "operating_system": image["operating_system"],
        "architecture": image["architecture"],
        "sandbox_uid": os.getuid(),
        "sandbox_gid": os.getgid(),
        "cache": [image],
    }
    config_path = root / "service.json"
    config_path.write_text(json.dumps(config, separators=(",", ":")))
    service = subprocess.Popen(
        [str(service_binary), str(config_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    manager = None
    try:
        for _ in range(1_000):
            if socket.exists():
                break
            if service.poll() is not None:
                raise RuntimeError(service.stderr.read())
            await asyncio.sleep(0.02)
        else:
            raise RuntimeError("service socket did not become ready")

        adapter = external_checker_execution_factory(
            socket_path=socket, timeout_seconds=90.0
        ).create("unix_socket")
        health = await adapter.health()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("src/main.txt", b"verified bytes")
        archive_bytes = archive.getvalue()
        manager = ArtifactScratchManager(
            root=scratch,
            limits=ArtifactPreparationLimits(
                aggregate_reserved_bytes=2 * 512 * 1024 * 1024,
                maximum_files=2,
                maximum_concurrency=2,
                minimum_free_bytes=0,
                reservation_ttl_seconds=60.0,
                total_deadline_seconds=40.0,
                cleanup_margin_seconds=10.0,
                stream_buffer_bytes=1024,
                maximum_source_bytes=1024 * 1024,
                maximum_workspace_entries=20,
            ),
        )
        preparation = ArtifactPreparationService(manager)
        prepared = await preparation.prepare(
            _stream(archive_bytes), media_type="application/zip"
        )
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
        base = registry_spec()
        configuration_document = {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["pass", "deadline", "output_overflow"],
                }
            },
            "required": ["mode"],
            "additionalProperties": False,
        }
        configuration_schema = ExternalCheckerSchema(
            schema_id="acme.safe_archive.configuration",
            schema_version="v1",
            document=configuration_document,
            schema_sha256=external_checker_json_hash(configuration_document),
        )
        spec = ExternalCheckerRegistrySpec.model_validate(
            base.model_dump(mode="json")
            | {
                "image_digest": image["platform_manifest_digest"],
                "configuration_schema": configuration_schema.model_dump(mode="json"),
                "resources": ExternalCheckerResourceLimits(
                    cpu_millis=500,
                    memory_bytes=128 * 1024 * 1024,
                    deadline_ms=8_000,
                    maximum_output_bytes=2_048,
                ).model_dump(mode="json"),
            }
        )
        registry = ExternalCheckerRegistryEntry(
            **spec.model_dump(),
            registry_entry_id=new_record_id(),
            entry_digest=spec.spec_digest,
            registration_operation_id=uuid4(),
            registered_by_actor_profile_id=uuid4(),
            authorization_decision_event_id=uuid4(),
            created_at=datetime.now(timezone.utc),
        )
        input_value = {"task_version": "v3"}
        materials = (
            ExternalCheckerMaterial(
                role="submission_archive",
                content_id=uuid4(),
                replica_id=uuid4(),
                sha256=prepared.commitment.sha256,
                byte_count=prepared.commitment.byte_count,
                media_type="application/zip",
            ),
        )

        def request_for(mode: str):
            identity = PreSubmitExternalCheckerIdentity(
                project_id=uuid4(),
                task_id=uuid4(),
                assignment_id=uuid4(),
                prepared_generation_id=prepared.generation_id,
                attempt_id=uuid4(),
                attempt_request_digest="sha256:" + "2" * 64,
                effective_plan_sha256="sha256:" + "3" * 64,
            )
            configuration = {"mode": mode}
            return make_external_checker_execution_request(
                registry=registry,
                identity=identity,
                configuration=configuration,
                configuration_sha256=external_checker_json_hash(configuration),
                input=input_value,
                input_sha256=external_checker_json_hash(input_value),
                materials=materials,
            )

        async def execute_request(request, *, changed_control: bool = False):
            grant_request = ExternalMaterialGrantRequest(
                request_digest=request.request_digest,
                prepared_generation_id=str(prepared.generation_id),
                attempt_id=str(request.identity.attempt_id),
                attempt_request_digest=request.identity.attempt_request_digest,
                archive_sha256=prepared.commitment.sha256,
                archive_byte_count=prepared.commitment.byte_count,
                semantic_manifest_sha256=manifest.sha256,
                directories=tuple(
                    entry.normalized_path
                    for entry in inspection.entries
                    if entry.entry_type is SubmissionArchiveEntryType.DIRECTORY
                ),
                files=tuple(
                    ExternalMaterialFile(
                        normalized_path=entry.normalized_path,
                        byte_count=entry.byte_count,
                        sha256=entry.sha256,
                        executable=entry.executable,
                    )
                    for entry in inspection.entries
                    if entry.entry_type is SubmissionArchiveEntryType.FILE
                ),
            )
            retained: dict[str, object] = {}

            class Processor:
                def abort(self):
                    return None

                async def process(self, reader, workspace):
                    def project(_tree):
                        with preparation.external_material_grant(
                            prepared, workspace, grant_request
                        ) as grant:
                            exact = ExternalCheckerMaterialGrant(
                                grant_id=grant.grant_id,
                                binding_digest=grant.binding_digest,
                            )
                            if changed_control:
                                changed = ExternalCheckerMaterialGrant(
                                    grant_id=grant.grant_id,
                                    binding_digest="sha256:" + "f" * 64,
                                )
                                changed_result = asyncio.run(
                                    adapter.execute(request, changed)
                                )
                                retained["changed_failure"] = (
                                    changed_result.result.infrastructure_failure_code
                                )
                            response = asyncio.run(adapter.execute(request, exact))
                            retained["grant"] = exact
                            return response

                    return await asyncio.to_thread(
                        inspector.project_and_run,
                        reader,
                        workspace,
                        expected=inspection,
                        callback=project,
                    )

            response = await preparation._process_prepared_submission(
                prepared,
                Processor(),
                reserved_bytes=manifest.total_expanded_bytes,
                maximum_entries=manifest.entry_count + 2,
            )
            return response, retained

        request = request_for("pass")
        response, retained = await execute_request(request, changed_control=True)
        expired = await adapter.execute(request, retained["grant"])
        deadline, _ = await execute_request(request_for("deadline"))
        overflow, _ = await execute_request(request_for("output_overflow"))
        await prepared.close()
        return {
            "health": {
                "runtime": health.runtime,
                "isolation_mode": health.isolation_mode,
                "sandbox_uid": health.sandbox_uid,
                "sandbox_gid": health.sandbox_gid,
            },
            "image": image,
            "request_digest": request.request_digest,
            "result_digest": response.result.result_digest,
            "verdict": response.result.verdict,
            "changed_binding_failure": retained["changed_failure"],
            "expired_grant_failure": expired.result.infrastructure_failure_code,
            "deadline_failure": deadline.result.infrastructure_failure_code,
            "output_failure": overflow.result.infrastructure_failure_code,
            "isolation": asdict(response.isolation) if response.isolation else None,
            "workspace_cleanup": list((scratch / "workspaces").iterdir()) == [],
        }
    finally:
        try:
            if manager is not None:
                manager.close()
        finally:
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=5)
            shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-reference", required=True)
    parser.add_argument("--service-binary", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        run(args.image_reference, args.service_binary.resolve(strict=True))
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
