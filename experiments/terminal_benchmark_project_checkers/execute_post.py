#!/usr/bin/env python3
"""Drive one real POST request through ART custody and the Unix adapter."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import UUID

from app.adapters.checkers import external_checker_execution_factory
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionResponse,
    ExternalCheckerMaterialGrant,
)
from app.interfaces.external_services import ExternalServiceUnavailableError
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactScratchManager,
    ExternalMaterialFile,
    PostExternalMaterialGrantRequest,
)
from app.modules.artifacts.submission_manifest import SUBMISSION_MANIFEST_SCHEMA_VERSION
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    PostSubmitExternalCheckerIdentity,
    PostSubmitExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_request,
)


_UNEXPECTED_RESPONSE_PREFIX = "ws493_unexpected_complete="
_MAX_DIAGNOSTIC_LINE_BYTES = 65_536


def _inventory(
    package: Path,
) -> tuple[
    tuple[str, ...],
    tuple[ExternalMaterialFile, ...],
    list[dict[str, object]],
]:
    directories: list[str] = []
    files: list[ExternalMaterialFile] = []
    entries: list[dict[str, object]] = []
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            raise ValueError("package link rejected")
        relative = path.relative_to(package).as_posix()
        if path.is_dir():
            directories.append(relative)
            entries.append({"normalized_path": relative, "entry_type": "directory"})
        elif path.is_file():
            data = path.read_bytes()
            item = ExternalMaterialFile(
                normalized_path=relative,
                byte_count=len(data),
                sha256=f"sha256:{hashlib.sha256(data).hexdigest()}",
                executable=False,
            )
            files.append(item)
            entries.append(
                {
                    "normalized_path": relative,
                    "entry_type": "file",
                    "byte_count": item.byte_count,
                    "sha256": item.sha256,
                    "executable": False,
                }
            )
        else:
            raise ValueError("package special entry rejected")
    return (
        tuple(directories),
        tuple(files),
        sorted(entries, key=lambda item: str(item["normalized_path"])),
    )


def _copy_package(package: Path, workspace: Path) -> None:
    for path in sorted(package.rglob("*")):
        relative = path.relative_to(package)
        target = workspace / relative
        if path.is_dir():
            target.mkdir(mode=0o700)
        else:
            shutil.copyfile(path, target, follow_symlinks=False)
            target.chmod(0o600)


def _write(path: Path, value: object) -> None:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OSError("short write")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _registry_entry_from_json(value: object) -> ExternalCheckerRegistryEntry:
    """Restore the strict registry value through its actual JSON boundary."""
    return ExternalCheckerRegistryEntry.model_validate_json(
        json.dumps(value, sort_keys=True, separators=(",", ":"))
    )


def _post_material(
    identity: PostSubmitExternalCheckerIdentity,
    identifiers: list[UUID],
    files: tuple[ExternalMaterialFile, ...],
    semantic_digest: str,
) -> PostSubmitExternalCheckerMaterial:
    """Build the proof material with the production POST archive role."""
    return PostSubmitExternalCheckerMaterial(
        role="submission_archive",
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        binding_id=identifiers[8],
        content_id=identifiers[9],
        replica_id=identifiers[10],
        content_sha256=external_checker_json_hash(
            [{"path": item.normalized_path, "sha256": item.sha256} for item in files]
        ),
        byte_count=sum(item.byte_count for item in files),
        media_type="application/vnd.workstream.submission-bundle",
        evidence_id=identifiers[11],
        verification_receipt_id=identifiers[12],
        verification_job_id=identifiers[13],
        verification_generation=1,
        namespace_fingerprint="sha256:" + "2" * 64,
        semantic_manifest_sha256=semantic_digest,
    )


def _report_unexpected_response(response: ExternalCheckerExecutionResponse) -> None:
    try:
        result = response.result
        isolation = response.isolation
        payload = json.dumps(
            {
                "isolation": asdict(isolation) if isolation is not None else None,
                "result": result.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        payload_bytes = payload.encode()
        maximum_payload_bytes = (
            _MAX_DIAGNOSTIC_LINE_BYTES
            - len(_UNEXPECTED_RESPONSE_PREFIX.encode())
            - 1
        )
        if len(payload_bytes) > maximum_payload_bytes:
            payload = json.dumps(
                {
                    "byte_count": len(payload_bytes),
                    "sha256": hashlib.sha256(payload_bytes).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        print(
            f"{_UNEXPECTED_RESPONSE_PREFIX}{payload}",
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        try:
            print(
                f"{_UNEXPECTED_RESPONSE_PREFIX}diagnostic_failed",
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass


async def _execute(arguments: argparse.Namespace) -> None:
    contract = json.loads(arguments.contract.read_text(encoding="utf-8"))
    registry = _registry_entry_from_json(contract["registry"])
    directories, files, manifest_entries = _inventory(arguments.package)
    semantic_body = {
        "schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION,
        "entries": manifest_entries,
    }
    semantic_digest = canonical_json_hash(semantic_body)
    identifiers = [new_record_id() for _ in range(14)]
    identity = PostSubmitExternalCheckerIdentity(
        project_id=identifiers[0],
        task_id=identifiers[1],
        assignment_id=identifiers[2],
        submission_id=identifiers[3],
        submission_version=1,
        evaluation_request_id=identifiers[4],
        evaluation_request_digest="sha256:" + "1" * 64,
        evaluation_generation=1,
        attempt_id=identifiers[5],
        result_id=identifiers[6],
        lease_id=identifiers[7],
        lease_generation=1,
        lease_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    material = _post_material(identity, identifiers, files, semantic_digest)
    configuration = contract["configuration"]
    request = make_external_checker_execution_request(
        registry=registry,
        identity=identity,
        configuration=configuration,
        configuration_sha256=external_checker_json_hash(configuration),
        input={"manifest": manifest_entries},
        input_sha256=external_checker_json_hash({"manifest": manifest_entries}),
        materials=(material,),
    )
    grant_request = PostExternalMaterialGrantRequest(
        request_digest=request.request_digest,
        submission_id=str(identity.submission_id),
        submission_version=identity.submission_version,
        evaluation_request_id=str(identity.evaluation_request_id),
        evaluation_request_digest=identity.evaluation_request_digest,
        evaluation_generation=identity.evaluation_generation,
        attempt_id=str(identity.attempt_id),
        result_id=str(identity.result_id),
        lease_id=str(identity.lease_id),
        lease_generation=identity.lease_generation,
        lease_expires_at=identity.lease_expires_at.isoformat().replace("+00:00", "Z"),
        binding_id=str(material.binding_id),
        content_id=str(material.content_id),
        replica_id=str(material.replica_id),
        content_sha256=material.content_sha256,
        byte_count=material.byte_count,
        evidence_id=str(material.evidence_id),
        verification_receipt_id=str(material.verification_receipt_id),
        verification_job_id=str(material.verification_job_id),
        verification_generation=material.verification_generation,
        namespace_fingerprint=material.namespace_fingerprint,
        semantic_manifest_sha256=material.semantic_manifest_sha256,
        registry_capability_id=registry.capability_id,
        registry_capability_version=registry.capability_version,
        directories=directories,
        files=files,
    )
    manager = ArtifactScratchManager(
        root=arguments.scratch,
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=1,
            minimum_free_bytes=0,
            reservation_ttl_seconds=900.0,
            total_deadline_seconds=30.0,
            cleanup_margin_seconds=10.0,
            stream_buffer_bytes=65_536,
            maximum_source_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_workspace_entries=64,
        ),
    )
    outcome: dict[str, object]
    try:
        with manager.extraction_workspace(
            reserved_bytes=material.byte_count,
            maximum_entries=len(directories) + len(files) + 1,
        ) as workspace:
            _copy_package(arguments.package, workspace)
            with manager._external_material_grant(workspace, grant_request) as grant:
                adapter = external_checker_execution_factory(
                    socket_path=arguments.socket,
                    timeout_seconds=700.0,
                ).create("unix_socket")
                try:
                    response = await adapter.execute(
                        request,
                        ExternalCheckerMaterialGrant(
                            grant_id=grant.grant_id,
                            binding_digest=grant.binding_digest,
                        ),
                    )
                except ExternalServiceUnavailableError:
                    if arguments.expect != "interrupted":
                        raise
                    outcome = {
                        "schema_version": "workstream.terminal_benchmark_interruption.v1",
                        "adapter_failure": True,
                        "request_digest": request.request_digest,
                    }
                else:
                    if arguments.expect != "complete":
                        _report_unexpected_response(response)
                        raise RuntimeError("interrupted request unexpectedly completed")
                    if (
                        response.result.outcome != "completed"
                        or response.result.verdict != "passed"
                        or response.result.findings
                        or response.isolation is None
                        or response.isolation.runtime != "runsc"
                    ):
                        raise RuntimeError("complete POST result differs")
                    outcome = {
                        "schema_version": "workstream.terminal_benchmark_complete.v1",
                        "result": response.result.model_dump(mode="json"),
                        "isolation": asdict(response.isolation),
                    }
    finally:
        manager.close()

    ledger = json.loads(
        (arguments.scratch / ".ledger.json").read_text(encoding="utf-8")
    )
    workspace_entries = list((arguments.scratch / "workspaces").iterdir())
    cleanup = {
        "ledger_empty": ledger["workspaces"] == [],
        "workspace_empty": workspace_entries == [],
    }
    if cleanup != {"ledger_empty": True, "workspace_empty": True}:
        raise RuntimeError("ART workspace cleanup differs")
    _write(arguments.output, outcome)
    _write(arguments.art_output, cleanup)


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--expect", choices=("interrupted", "complete"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--art-output", type=Path, required=True)
    arguments = parser.parse_args()
    asyncio.run(_execute(arguments))


if __name__ == "__main__":
    main()
