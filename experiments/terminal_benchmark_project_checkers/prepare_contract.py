#!/usr/bin/env python3
"""Create the exact service profile and immutable proof registration contract."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import UUID

from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
    ExternalCheckerResourceLimits,
    ExternalCheckerSchema,
    external_checker_json_hash,
)


REGISTRY_ENTRY_ID = UUID("01890f12-3456-789a-8bcd-ef0123456789")
REGISTRATION_OPERATION_ID = UUID("11111111-1111-4111-8111-111111111111")
REGISTERED_BY_ID = UUID("22222222-2222-4222-8222-222222222222")
AUTHORIZATION_EVENT_ID = UUID("33333333-3333-4333-8333-333333333333")


def _schema(schema_id: str, document: dict[str, object]) -> ExternalCheckerSchema:
    return ExternalCheckerSchema(
        schema_id=schema_id,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def _inventory(root: Path, expected_uid: int, expected_gid: int) -> dict[str, object]:
    if root.resolve(strict=True) != root or root.is_symlink():
        raise ValueError("sealed cache root is not canonical")
    root_metadata = root.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != expected_uid
        or root_metadata.st_gid != expected_gid
        or stat.S_IMODE(root_metadata.st_mode) != 0o555
    ):
        raise ValueError("sealed cache root identity differs")
    entries: list[dict[str, object]] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            metadata = path.stat(follow_symlinks=False)
            if (
                path.is_symlink()
                or metadata.st_uid != expected_uid
                or metadata.st_gid != expected_gid
            ):
                raise ValueError("sealed cache entry identity differs")
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISDIR(metadata.st_mode):
                if mode != 0o555:
                    raise ValueError("sealed cache directory mode differs")
                entries.append(
                    {
                        "path": relative,
                        "kind": "directory",
                        "mode": mode,
                        "byte_count": 0,
                        "sha256": None,
                    }
                )
            elif stat.S_ISREG(metadata.st_mode):
                if mode != 0o444:
                    raise ValueError("sealed cache file mode differs")
                before = (
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                )
                digest = hashlib.sha256()
                count = 0
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    while chunk := os.read(descriptor, 65_536):
                        count += len(chunk)
                        digest.update(chunk)
                    after_metadata = os.fstat(descriptor)
                finally:
                    os.close(descriptor)
                after = (
                    after_metadata.st_dev,
                    after_metadata.st_ino,
                    after_metadata.st_size,
                    after_metadata.st_mode,
                    after_metadata.st_uid,
                    after_metadata.st_gid,
                )
                if before != after or count != metadata.st_size:
                    raise ValueError("sealed cache entry changed")
                entries.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "mode": mode,
                        "byte_count": count,
                        "sha256": f"sha256:{digest.hexdigest()}",
                    }
                )
            else:
                raise ValueError("sealed cache special entry rejected")
    entries.sort(key=lambda item: str(item["path"]))
    return {
        "root": str(root),
        "uid": expected_uid,
        "gid": expected_gid,
        "mode": 0o555,
        "entries": entries,
        "total_count": len(entries),
        "total_bytes": sum(int(item["byte_count"]) for item in entries),
        "inventory_digest": external_checker_json_hash(entries),
    }


def _write(path: Path, value: object) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _registry_entry(image_digest: str) -> ExternalCheckerRegistryEntry:
    configuration_document = {
        "type": "object",
        "additionalProperties": False,
        "required": ["external_task_id", "schema_version"],
        "properties": {
            "external_task_id": {"const": "terminal-ledger-reconcile"},
            "schema_version": {"const": "terminal_benchmark_project.v1"},
        },
    }
    input_document = {
        "type": "object",
        "additionalProperties": False,
        "required": ["manifest"],
        "properties": {
            "manifest": {
                "type": "array",
                "minItems": 12,
                "maxItems": 12,
                "items": {"type": "object"},
            }
        },
    }
    output_document = {"type": "object"}
    spec = ExternalCheckerRegistrySpec(
        capability_id="workstream.terminal_benchmark_project",
        capability_version="v1",
        phase="post_submit",
        image_digest=image_digest,
        configuration_schema=_schema(
            "terminal_benchmark.configuration", configuration_document
        ),
        input_schema=_schema("external_checker_post_submit_input", input_document),
        output_schema=_schema("external_checker_result", output_document),
        resources=ExternalCheckerResourceLimits(
            cpu_millis=1_000,
            memory_bytes=512 * 1024 * 1024,
            deadline_ms=600_000,
            maximum_output_bytes=65_536,
        ),
    )
    return ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=REGISTRY_ENTRY_ID,
        entry_digest=spec.spec_digest,
        registration_operation_id=REGISTRATION_OPERATION_ID,
        registered_by_actor_profile_id=REGISTERED_BY_ID,
        authorization_decision_event_id=AUTHORIZATION_EVENT_ID,
        created_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--material-root", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--docker-wrapper", type=Path, required=True)
    parser.add_argument("--service-config", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--sandbox-uid", type=int, required=True)
    parser.add_argument("--sandbox-gid", type=int, required=True)
    arguments = parser.parse_args()

    facts = json.loads(arguments.facts.read_text(encoding="utf-8"))
    if set(facts) != {"approved_base", "builder", "checker"}:
        raise SystemExit("image facts inventory differs")
    for value in facts.values():
        if set(value) != {
            "architecture",
            "config_image_id",
            "operating_system",
            "platform_manifest_byte_count",
            "platform_manifest_digest",
            "platform_manifest_media_type",
            "repository",
        }:
            raise SystemExit("image facts shape differs")

    entry = _registry_entry(
        str(facts["checker"]["platform_manifest_digest"])
    )
    sealed_cache = _inventory(
        arguments.cache_root,
        arguments.sandbox_uid,
        arguments.sandbox_gid,
    )
    service = {
        "socket_path": str(arguments.socket),
        "material_root": str(arguments.material_root),
        "docker_binary": str(arguments.docker_wrapper),
        "runtime": "runsc",
        "isolation_mode": "gvisor",
        "operating_system": "linux",
        "architecture": "amd64",
        "sandbox_uid": arguments.sandbox_uid,
        "sandbox_gid": arguments.sandbox_gid,
        "cache": [facts["checker"], facts["builder"], facts["approved_base"]],
        "terminal_benchmark": {
            "profile_version": "terminal_benchmark_build_oracle.v1",
            "registry_entry_id": str(REGISTRY_ENTRY_ID),
            "registry_entry_digest": entry.entry_digest,
            "checker_image_digest": facts["checker"]["platform_manifest_digest"],
            "builder": facts["builder"],
            "approved_base": facts["approved_base"],
            "sealed_cache": sealed_cache,
            "temporary_repository": "workstream.local/terminal-benchmark-candidate",
        },
    }
    contract = {
        "schema_version": "workstream.terminal_benchmark_project_checker_contract.v1",
        "configuration": {
            "schema_version": "terminal_benchmark_project.v1",
            "external_task_id": "terminal-ledger-reconcile",
        },
        "registry": entry.model_dump(mode="json"),
    }
    _write(arguments.service_config, service)
    _write(arguments.contract, contract)
    _write(arguments.inventory, sealed_cache)


if __name__ == "__main__":
    main()
