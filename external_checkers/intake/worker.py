"""Closed trusted-image composition: canonical ART ZIP and CHECKERS default code.

The Rust bootstrap stages the immutable archive and confines this process before
entry. This worker has no project command, artifact-store credential or host path.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import BinaryIO

from pydantic import TypeAdapter

from app.interfaces.trusted_submission_intake import (
    TrustedDefaultBinding,
    TrustedIntakePreparation,
)
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveEntryType,
    SubmissionArchiveRejectedError,
)
from app.modules.artifacts.submission_archive import (
    SealedSubmissionTree,
    SubmissionArchiveInspector,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    workstream_default_input_sha256,
)
from app.modules.checkers.api.material import SubmissionMaterialEntry
from app.modules.checkers.default_checker import evaluate_verified_archive

_PROTOCOL = "trusted_submission_intake.v1"
_MAX_COMMAND = 4 * 1024 * 1024
_MAX_FRAME = 64 * 1024 * 1024
_CHUNK = 64 * 1024


def _object(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("intake protocol invalid")
    return value


def _read_exact(reader: BinaryIO, count: int) -> bytes:
    output = bytearray()
    while len(output) < count:
        value = reader.read(count - len(output))
        if not value:
            raise EOFError("intake ended")
        output.extend(value)
    return bytes(output)


class _Material:
    def __init__(self, tree: SealedSubmissionTree) -> None:
        self._tree = tree
        self.entries = tuple(
            SubmissionMaterialEntry(**asdict(entry)) for entry in tree.entries
        )

    def read_file(self, normalized_path: str, *, maximum_bytes: int) -> bytes:
        return self._tree.read_file(normalized_path, maximum_bytes=maximum_bytes)


class IntakeWorker:
    """One archive and one default invocation inside one prepared VM lifetime."""

    def __init__(
        self,
        *,
        startup: dict,
        archive: Path,
        workspace: Path,
        reader: BinaryIO,
        writer: BinaryIO,
    ) -> None:
        _object(
            startup, {"lease", "preparation", "archive_sha256", "archive_byte_count"}
        )
        self._startup = startup
        self._preparation = TypeAdapter(TrustedIntakePreparation).validate_json(
            json.dumps(startup["preparation"]), strict=True
        )
        self._archive = archive
        self._workspace = workspace
        self._reader = reader
        self._writer = writer
        self._state = "new"

    def _reply(self, operation: str, payload: dict, *, status: str = "ok") -> None:
        raw = json.dumps(
            {
                "protocol_version": _PROTOCOL,
                "operation": operation,
                "lease": self._startup["lease"],
                "status": status,
                "payload": payload,
            },
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
        if len(raw) > _MAX_FRAME:
            raise ValueError("intake result exceeds limit")
        self._writer.write(struct.pack(">I", len(raw)))
        self._writer.write(raw)
        self._writer.flush()

    def _command(self) -> tuple[str, dict]:
        size = struct.unpack(">I", _read_exact(self._reader, 4))[0]
        if not 0 < size <= _MAX_COMMAND:
            raise ValueError("intake command exceeds limit")
        body = _object(
            json.loads(_read_exact(self._reader, size)),
            {"protocol_version", "operation", "lease", "payload"},
        )
        if (
            body["protocol_version"] != _PROTOCOL
            or body["lease"] != self._startup["lease"]
            or type(body["payload"]) is not dict
        ):
            raise ValueError("intake identity differs")
        return body["operation"], body["payload"]

    def run(self) -> None:
        self._reply(
            "ready", {"default_behavior_sha256": WORKSTREAM_DEFAULT_BEHAVIOR_SHA256}
        )
        with ExitStack() as stack:
            archive = stack.enter_context(self._archive.open("rb"))
            digest = hashlib.sha256()
            size = 0
            while chunk := archive.read(_CHUNK):
                digest.update(chunk)
                size += len(chunk)
            if (
                size != self._startup["archive_byte_count"]
                or "sha256:" + digest.hexdigest() != self._startup["archive_sha256"]
            ):
                raise ValueError("intake archive identity differs")
            inspector = SubmissionArchiveInspector(self._preparation.limits)
            try:
                inspection = inspector.inspect(archive)
                tree = stack.enter_context(
                    inspector._projected_tree(
                        archive,
                        self._workspace,
                        expected=inspection,
                    )
                )
            except SubmissionArchiveRejectedError as exc:
                self._reply("inspect", {"code": exc.code.value}, status="error")
                return
            manifest = build_submission_manifest(inspection)
            self._reply(
                "inspect",
                {
                    "archive_sha256": self._startup["archive_sha256"],
                    "archive_byte_count": size,
                    "inspection": asdict(inspection),
                },
            )
            self._state = "inspected"
            while True:
                operation, payload = self._command()
                if operation == "export" and self._state == "inspected":
                    _object(payload, set())
                    self._state = "exporting"
                    for entry in tree.entries:
                        if entry.entry_type is not SubmissionArchiveEntryType.FILE:
                            continue
                        self._reply("file", asdict(entry))
                        content = tree.read_file(
                            entry.normalized_path, maximum_bytes=entry.byte_count
                        )
                        for offset in range(0, len(content), _CHUNK):
                            self._writer.write(content[offset : offset + _CHUNK])
                        self._writer.flush()
                    self._reply("export", {})
                    self._state = "exported"
                elif (
                    operation == "default"
                    and self._state == "exported"
                    and self._preparation.phase == "pre_submit"
                ):
                    _object(payload, {"binding", "input"})
                    _object(
                        payload["binding"],
                        {field.name for field in fields(TrustedDefaultBinding)},
                    )
                    binding = TypeAdapter(TrustedDefaultBinding).validate_json(
                        json.dumps(payload["binding"]), strict=True
                    )
                    raw = _object(
                        payload["input"],
                        {field.name for field in fields(WorkstreamDefaultCheckerInput)},
                    )
                    _object(raw["packet"], {"summary", "contributor_attestation"})
                    for predecessor in (raw["predecessor"], raw["current_predecessor"]):
                        if predecessor is not None:
                            _object(
                                predecessor,
                                {
                                    "submission_id",
                                    "submission_version",
                                    "archive_sha256",
                                    "semantic_manifest_sha256",
                                },
                            )
                    if type(raw["entries"]) is not list:
                        raise ValueError("default entries invalid")
                    for entry in raw["entries"]:
                        _object(
                            entry,
                            {field.name for field in fields(SubmissionMaterialEntry)},
                        )
                    value = TypeAdapter(WorkstreamDefaultCheckerInput).validate_json(
                        json.dumps(raw), strict=True
                    )
                    if (
                        binding.policy_sha256 != self._preparation.policy_sha256
                        or binding.semantic_manifest_sha256 != manifest.sha256
                        or value.semantic_manifest_sha256 != manifest.sha256
                        or value.archive_sha256 != self._startup["archive_sha256"]
                        or value.archive_byte_count != size
                        or binding.default_input_sha256
                        != workstream_default_input_sha256(value)
                    ):
                        raise ValueError("default custody differs")
                    self._state = "evaluating"
                    result = evaluate_verified_archive(value, _Material(tree))
                    self._reply("default", result.model_dump(mode="json"))
                    self._state = "evaluated"
                else:
                    raise ValueError("intake operation out of sequence")


def main() -> None:
    # Paths are fixed image/bootstrap contracts, never provided by a contributor.
    startup = json.loads(Path("/work/request.json").read_bytes())
    IntakeWorker(
        startup=startup,
        archive=Path("/work/input/archive.zip"),
        workspace=Path("/work/scratch"),
        reader=sys.stdin.buffer,
        writer=sys.stdout.buffer,
    ).run()


if __name__ == "__main__":
    try:
        main()
    except EOFError:
        pass  # Controller closes the command pipe before exact VM destruction.
    except Exception:
        # Never emit inspected metadata, packet text, or filesystem paths on failure.
        print("trusted intake failed", file=sys.stderr)
        raise SystemExit(125) from None
