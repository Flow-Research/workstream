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
import time
from typing import BinaryIO

from pydantic import TypeAdapter

from app.interfaces.trusted_submission_intake import (
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
    """POST-only archive inspection/export; no PRE default or project commands."""

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
        if self._preparation.phase != "post_submit":
            raise ValueError("prepared intake is POST-only")
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
                or size != self._preparation.archive_byte_count
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
                else:
                    raise ValueError("intake operation out of sequence")


class PreSubmitWorker:
    """Trusted source-derived PRE stages; the guest supervisor owns project exec."""

    def __init__(self, *, startup, archive, workspace, reader, writer):
        from datetime import UTC, datetime
        from uuid import UUID
        from app.modules.checkers.api.selected_pre_submit import (
            ExternalPreSubmitIsolationFacts, SelectedPreSubmitLeaseFacts,
            SelectedPreSubmitReservationFacts,
        )
        _object(startup, {"operation", "request", "isolation"})
        if startup["operation"] != "execute_pre":
            raise ValueError("PRE operation invalid")
        header = _object(startup["request"], {
            "protocol_version", "operation", "reservation", "request_digest",
            "lease_id", "lease_generation", "lease_expires_at",
        })
        if header["protocol_version"] != "external_checker_service.v1" or header["operation"] != "execute_pre":
            raise ValueError("PRE request invalid")
        reservation = SelectedPreSubmitReservationFacts.from_canonical_body(header["reservation"])
        if header["request_digest"] != reservation.request_digest:
            raise ValueError("PRE request digest differs")
        self._lease = SelectedPreSubmitLeaseFacts(
            reservation, UUID(header["lease_id"]), header["lease_generation"],
            datetime.fromisoformat(header["lease_expires_at"]),
        )
        self._isolation = ExternalPreSubmitIsolationFacts(**_object(
            startup["isolation"], {field.name for field in fields(ExternalPreSubmitIsolationFacts)},
        ))
        selected = reservation.policy.entries[0].registry
        if (self._isolation.platform_manifest_digest != selected.image_digest
                or reservation.default_behavior_sha256 != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256):
            raise ValueError("PRE selected identity differs")
        self._deadline = time.monotonic() + min(
            (self._lease.lease_expires_at - datetime.now(UTC)).total_seconds(),
            reservation.execution_budget_ms / 1000,
        )
        self._archive, self._workspace = archive, workspace
        self._reader, self._writer = reader, writer
        self._started = False

    def _check(self):
        from datetime import UTC, datetime
        if time.monotonic() >= self._deadline or datetime.now(UTC) >= self._lease.lease_expires_at:
            raise TimeoutError("PRE deadline exceeded")

    def _reply(self, operation, payload):
        self._check()
        raw = json.dumps({
            "protocol_version": "workstream.pre_submit_worker.v1",
            "operation": operation, "request_digest": self._lease.reservation.request_digest,
            "lease_id": str(self._lease.lease_id), "lease_generation": self._lease.lease_generation,
            "payload": payload,
        }, allow_nan=False, separators=(",", ":")).encode()
        if len(raw) > _MAX_FRAME:
            raise ValueError("PRE control frame exceeds limit")
        self._writer.write(struct.pack(">I", len(raw)))
        self._writer.write(raw)
        self._writer.flush()
        self._check()

    def _project_result(self, request):
        from app.modules.checkers.api.external import ExternalCheckerExecutionResult
        self._check()
        size = struct.unpack(">I", _read_exact(self._reader, 4))[0]
        if not 0 < size <= min(_MAX_FRAME, request.registry.resources.maximum_output_bytes + 1024):
            raise ValueError("PRE project output exceeds limit")
        body = _object(json.loads(_read_exact(self._reader, size)), {
            "request_digest", "lease_id", "lease_generation", "result",
        })
        if (body["request_digest"] != self._lease.reservation.request_digest
                or body["lease_id"] != str(self._lease.lease_id)
                or type(body["lease_generation"]) is not int
                or body["lease_generation"] != self._lease.lease_generation):
            raise ValueError("PRE project control binding differs")
        result = ExternalCheckerExecutionResult.model_validate_json(json.dumps(body["result"]))
        result.validate_request(request)
        result.validate_registry(self._lease.reservation.policy.entries[0].registry)
        self._check()
        return result

    def _finish(self, default, manifest=None, default_input=None, members=()):
        from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitExecutionFacts
        reservation = self._lease.reservation
        facts = SelectedPreSubmitExecutionFacts(
            request_digest=reservation.request_digest, lease_id=self._lease.lease_id,
            lease_generation=self._lease.lease_generation, observed_source=reservation.source,
            manifest_body=manifest.as_dict() if manifest else None,
            manifest_sha256=manifest.sha256 if manifest else None,
            default_input_sha256=workstream_default_input_sha256(default_input) if default_input else None,
            policy_sha256=reservation.policy_sha256, workstream_default=default,
            required_external_count=1, external_members=members,
            eligible=default.eligible and len(members) == 1 and members[0].result.verdict == "passed",
        )
        facts.validate_lease(self._lease)
        self._reply("completed", facts.canonical_body())

    def run(self):
        from app.modules.checkers.api.selected_pre_submit import (
            ExternalPreSubmitMemberFacts, derive_selected_pre_submit_default_input,
            derive_selected_pre_submit_input,
        )
        from app.modules.checkers.default_checker import evaluate_rejected_archive
        if self._started:
            raise ValueError("PRE worker already consumed")
        self._started = True
        self._check()
        reservation = self._lease.reservation
        source = reservation.source
        with self._archive.open("rb") as archive:
            digest, size = hashlib.sha256(), 0
            while chunk := archive.read(_CHUNK):
                self._check()
                size += len(chunk)
                if size > source.raw_byte_count:
                    raise ValueError("PRE source identity differs")
                digest.update(chunk)
            if size != source.raw_byte_count or "sha256:" + digest.hexdigest() != source.raw_sha256:
                raise ValueError("PRE source identity differs")
            inspector = SubmissionArchiveInspector(reservation.runtime_profile.archive_limits)
            try:
                inspection = inspector.inspect(archive)
                manifest = build_submission_manifest(inspection)
                value = derive_selected_pre_submit_default_input(
                    self._lease, manifest_body=manifest.as_dict(), manifest_sha256=manifest.sha256,
                )
                with inspector._projected_tree(archive, self._workspace, expected=inspection) as tree:
                    default = evaluate_verified_archive(value, _Material(tree))
            except SubmissionArchiveRejectedError as exc:
                self._finish(evaluate_rejected_archive(exc.code.value, packet=reservation.default_context.packet))
                return
        self._check()
        # Closing the canonical snapshot releases its byte cache; the verified
        # files remain for the supervisor's private read-only mount handoff.
        if not default.eligible:
            self._finish(default, manifest, value)
            return
        _, request = derive_selected_pre_submit_input(
            self._lease, manifest_body=manifest.as_dict(), manifest_sha256=manifest.sha256,
        )
        self._reply("project", {
            "request": request.model_dump(mode="json"), "manifest": manifest.as_dict(),
        })
        result = self._project_result(request)
        if result.outcome != "completed":
            self._reply("infrastructure_failed", {"code": result.infrastructure_failure_code})
            return
        selected = reservation.policy.entries[0]
        member = ExternalPreSubmitMemberFacts(
            order=0, requirement_id=selected.requirement_id,
            registry_entry_id=selected.registry.registry_entry_id,
            registry_entry_digest=selected.registry.entry_digest,
            request_digest=request.request_digest, result=result, isolation=self._isolation,
        )
        self._finish(default, manifest, value, (member,))


def main() -> None:
    # Paths are fixed image/bootstrap contracts, never provided by a contributor.
    startup = json.loads(Path("/work/request.json").read_bytes())
    worker = PreSubmitWorker if startup.get("operation") == "execute_pre" else IntakeWorker
    worker(
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
