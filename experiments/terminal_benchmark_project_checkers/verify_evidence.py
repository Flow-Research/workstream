#!/usr/bin/env python3
"""Stage only the fixed, bounded, nonsecret WS493 runtime-proof evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


SCHEMA = "workstream.terminal_benchmark_project_checker_proof.v1"
HEAD = re.compile(r"[0-9a-f]{40}")
INITIAL_FILES = {
    "art-complete.json": 65_536,
    "art-interrupt.json": 65_536,
    "argv.ndjson": 262_144,
    "base-boundary.log": 8_192,
    "builder-boundary.log": 8_192,
    "cache-inventory.json": 2_097_152,
    "command-results.ndjson": 262_144,
    "complete-result.json": 65_536,
    "contract.json": 131_072,
    "docker-events.ndjson": 262_144,
    "harness.json": 65_536,
    "image-facts.json": 131_072,
    "interrupt.json": 65_536,
    "launches.ndjson": 262_144,
    "matrix.json": 65_536,
    "proof-head.txt": 64,
    "quota.json": 65_536,
    "restart-cleanup.json": 65_536,
    "service-complete.log": 131_072,
    "service-interrupt.log": 131_072,
    "tool-versions.json": 65_536,
    "verifier-tests.json": 8_192,
}
FINAL_ONLY = {"cleanup-receipt.json": 65_536}
MANIFEST = "manifest.json"
MAXIMUM_AGGREGATE_BYTES = 4 * 1024 * 1024


class EvidenceError(ValueError):
    """Reject evidence that is incomplete, unsafe, or outside the fixed matrix."""


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError("evidence directory is unavailable") from exc
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise EvidenceError("evidence directory is invalid")
    return descriptor


def _names(directory: int) -> set[str]:
    try:
        names = set(os.listdir(directory))
    except OSError as exc:
        raise EvidenceError("evidence inventory is unavailable") from exc
    if any(name in {"", ".", ".."} or "/" in name or "\x00" in name for name in names):
        raise EvidenceError("evidence name is unsafe")
    return names


def _read_regular(
    directory: int,
    name: str,
    maximum: int,
    *,
    expected_uid: int,
    expected_modes: set[int],
) -> bytes:
    if name in {"", ".", ".."} or "/" in name or "\x00" in name:
        raise EvidenceError("evidence file name is unsafe")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=directory)
    except OSError as exc:
        raise EvidenceError(f"evidence file unavailable: {name}") from exc
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != expected_uid
            or mode not in expected_modes
            or before.st_size <= 0
            or before.st_size > maximum
        ):
            raise EvidenceError(f"evidence file identity differs: {name}")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(data) > maximum or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mode,
            before.st_uid,
            before.st_gid,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mode,
            after.st_uid,
            after.st_gid,
        ):
            raise EvidenceError(f"evidence file changed while reading: {name}")
        return data
    finally:
        os.close(descriptor)


def _json_object(name: str, data: bytes) -> dict[str, object]:
    if b"\x00" in data:
        raise EvidenceError(f"evidence contains NUL: {name}")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"evidence JSON is invalid: {name}") from exc
    if type(value) is not dict:
        raise EvidenceError(f"evidence JSON is not an object: {name}")
    return value


def _validate_content(name: str, data: bytes, expected_head: str) -> None:
    if name.endswith(".json"):
        value = _json_object(name, data)
        if name == "matrix.json":
            interrupted = value.get("interrupted")
            complete = value.get("complete")
            if (
                value.get("schema_version") != SCHEMA
                or value.get("head_sha") != expected_head
                or type(interrupted) is not dict
                or type(complete) is not dict
                or interrupted
                != {
                    "adapter_failure": True,
                    "art_unwound": True,
                    "restart_swept_owned": True,
                    "unowned_control_preserved": True,
                }
                or complete
                != {
                    "builder_exit": 0,
                    "candidate_exit": 1,
                    "outcome": "completed",
                    "owned_resources_absent": True,
                    "reference_exits": [0, 0, 0],
                    "stable": True,
                    "verdict": "passed",
                }
            ):
                raise EvidenceError("matrix evidence is incomplete")
        elif name == "quota.json":
            required = {
                "backing_filesystem": "xfs",
                "d_type": True,
                "inner_driver": "overlay2",
                "project_quota": True,
                "storage_opt_bytes": 402_653_184,
                "below_limit_bytes": 335_544_320,
                "below_limit_succeeded": True,
                "above_limit_bytes": 419_430_400,
                "above_limit_failed": True,
            }
            if any(value.get(key) != expected for key, expected in required.items()):
                raise EvidenceError("quota evidence is incomplete")
        elif name == "harness.json":
            required = {
                "cpu_nanos": 2_000_000_000,
                "external_network": "none",
                "memory_bytes": 4_294_967_296,
                "pids_limit": 768,
                "privileged": True,
                "runtime_key": "runsc",
                "same_absolute_state_mount": True,
                "xfs_docker_state_mount": True,
            }
            if any(value.get(key) != expected for key, expected in required.items()):
                raise EvidenceError("harness boundary evidence is incomplete")
        elif name in {"art-interrupt.json", "art-complete.json"}:
            if (
                value.get("workspace_empty") is not True
                or value.get("ledger_empty") is not True
            ):
                raise EvidenceError("ART cleanup evidence is incomplete")
        elif name == "restart-cleanup.json":
            if value != {
                "owned_containers_absent": True,
                "owned_images_absent": True,
                "unowned_control_preserved": True,
            }:
                raise EvidenceError("restart cleanup evidence is incomplete")
        elif name == "cleanup-receipt.json":
            required = {
                "dind_absent": True,
                "loop_detached": True,
                "outer_owned_resources_absent": True,
                "raw_state_deleted": True,
                "registry_absent": True,
                "xfs_unmounted": True,
            }
            if (
                value.get("schema_version") != SCHEMA
                or value.get("head_sha") != expected_head
            ):
                raise EvidenceError("cleanup receipt head differs")
            if any(value.get(key) != expected for key, expected in required.items()):
                raise EvidenceError("cleanup receipt is incomplete")
    elif name.endswith(".ndjson"):
        if b"\x00" in data:
            raise EvidenceError(f"evidence contains NUL: {name}")
        lines = data.decode("utf-8").splitlines()
        if not lines or len(lines) > 1_024:
            raise EvidenceError(f"evidence NDJSON is empty or unbounded: {name}")
        for line in lines:
            if type(json.loads(line)) is not dict:
                raise EvidenceError(f"evidence NDJSON entry is invalid: {name}")
    else:
        if b"\x00" in data:
            raise EvidenceError(f"evidence contains NUL: {name}")
        try:
            text = data.decode("utf-8")
        except UnicodeError as exc:
            raise EvidenceError(f"evidence text is invalid: {name}") from exc
        if name == "proof-head.txt" and text.strip() != expected_head:
            raise EvidenceError("proof head differs")


def _read_inventory(
    directory: Path,
    allowlist: dict[str, int],
    *,
    expected_head: str,
    expected_uid: int,
    expected_modes: set[int],
) -> dict[str, bytes]:
    descriptor = _open_directory(directory)
    try:
        directory_metadata = os.fstat(descriptor)
        expected_directory_mode = 0o700 if expected_modes == {0o600} else 0o755
        if (
            directory_metadata.st_uid != expected_uid
            or stat.S_IMODE(directory_metadata.st_mode) != expected_directory_mode
        ):
            raise EvidenceError("evidence directory identity differs")
        if _names(descriptor) != set(allowlist):
            raise EvidenceError("evidence inventory differs")
        values: dict[str, bytes] = {}
        total = 0
        for name in sorted(allowlist):
            data = _read_regular(
                descriptor,
                name,
                allowlist[name],
                expected_uid=expected_uid,
                expected_modes=expected_modes,
            )
            _validate_content(name, data, expected_head)
            total += len(data)
            if total > MAXIMUM_AGGREGATE_BYTES:
                raise EvidenceError("evidence aggregate exceeds limit")
            values[name] = data
        return values
    finally:
        os.close(descriptor)


def _manifest(values: dict[str, bytes], expected_head: str) -> bytes:
    body = {
        "schema_version": SCHEMA,
        "head_sha": expected_head,
        "files": [
            {
                "name": name,
                "byte_count": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, data in sorted(values.items())
        ],
    }
    return (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _atomic_write(directory: Path, name: str, data: bytes, mode: int = 0o444) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
    temporary_path = Path(temporary)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise EvidenceError("staged evidence write failed")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, directory / name)
        parent = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def stage(raw: Path, destination: Path, expected_head: str, expected_uid: int) -> None:
    values = _read_inventory(
        raw,
        INITIAL_FILES,
        expected_head=expected_head,
        expected_uid=expected_uid,
        expected_modes={0o600},
    )
    try:
        destination.mkdir(mode=0o755)
    except OSError as exc:
        raise EvidenceError("staging directory must be new") from exc
    for name, data in values.items():
        _atomic_write(destination, name, data)
    _atomic_write(destination, MANIFEST, _manifest(values, expected_head))


def add_cleanup(
    destination: Path, receipt: Path, expected_head: str, expected_uid: int
) -> None:
    destination_name = "cleanup-receipt.json"
    destination_descriptor = _open_directory(destination)
    try:
        destination_metadata = os.fstat(destination_descriptor)
        if (
            destination_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(destination_metadata.st_mode) != 0o755
        ):
            raise EvidenceError("staging directory identity differs")
    finally:
        os.close(destination_descriptor)
    descriptor = _open_directory(receipt.parent)
    try:
        data = _read_regular(
            descriptor,
            receipt.name,
            FINAL_ONLY[destination_name],
            expected_uid=expected_uid,
            expected_modes={0o600},
        )
    finally:
        os.close(descriptor)
    _validate_content(destination_name, data, expected_head)
    _atomic_write(destination, destination_name, data)


def final(destination: Path, expected_head: str) -> None:
    uid = os.geteuid()
    allowlist = {**INITIAL_FILES, **FINAL_ONLY, MANIFEST: 262_144}
    values = _read_inventory(
        destination,
        allowlist,
        expected_head=expected_head,
        expected_uid=uid,
        expected_modes={0o444},
    )
    del values[MANIFEST]
    _atomic_write(destination, MANIFEST, _manifest(values, expected_head))
    checked = _read_inventory(
        destination,
        allowlist,
        expected_head=expected_head,
        expected_uid=uid,
        expected_modes={0o444},
    )
    manifest = _json_object(MANIFEST, checked[MANIFEST])
    expected = json.loads(
        _manifest(
            {key: value for key, value in checked.items() if key != MANIFEST},
            expected_head,
        )
    )
    if manifest != expected:
        raise EvidenceError("evidence manifest differs")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("raw", type=Path)
    stage_parser.add_argument("destination", type=Path)
    stage_parser.add_argument("expected_head")
    stage_parser.add_argument("expected_uid", type=int)
    cleanup_parser = subparsers.add_parser("add-cleanup")
    cleanup_parser.add_argument("destination", type=Path)
    cleanup_parser.add_argument("receipt", type=Path)
    cleanup_parser.add_argument("expected_head")
    cleanup_parser.add_argument("expected_uid", type=int)
    final_parser = subparsers.add_parser("final")
    final_parser.add_argument("destination", type=Path)
    final_parser.add_argument("expected_head")
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    if HEAD.fullmatch(arguments.expected_head) is None:
        raise SystemExit("expected head must be a full lowercase Git SHA")
    try:
        if arguments.operation == "stage":
            stage(
                arguments.raw,
                arguments.destination,
                arguments.expected_head,
                arguments.expected_uid,
            )
        elif arguments.operation == "add-cleanup":
            add_cleanup(
                arguments.destination,
                arguments.receipt,
                arguments.expected_head,
                arguments.expected_uid,
            )
        else:
            final(arguments.destination, arguments.expected_head)
    except EvidenceError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
