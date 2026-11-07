"""Trusted-intake custody, canonical-rule and cancellation contracts."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import hashlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import struct
import threading
import zipfile

from pydantic import TypeAdapter
import pytest

from app.adapters.artifacts.trusted_intake import UnixSocketTrustedIntakeAdapter
from app.core.identifiers import new_record_id
from app.interfaces.external_services import ExternalServiceProtocolError
from app.interfaces.trusted_submission_intake import TrustedDefaultBinding, TrustedIntakePreparation
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    workstream_default_input_sha256,
)
from app.modules.checkers.api.material import SubmissionMaterialEntry
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView

_SPEC = importlib.util.spec_from_file_location(
    "trusted_intake_worker",
    Path(__file__).resolve().parents[2] / "external_checkers/intake/worker.py",
)
_WORKER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_WORKER)
_PROTOCOL = "trusted_submission_intake.v1"
_POLICY = "sha256:" + "a" * 64
_LEASE = "b" * 128
_IMAGE = "sha256:" + "c" * 64
_CONFIG = "sha256:" + "d" * 64


def _frame(value: dict) -> bytes:
    raw = json.dumps(value).encode()
    return struct.pack(">I", len(raw)) + raw


def _read(reader) -> dict:
    size = struct.unpack(">I", reader.read(4))[0]
    return json.loads(reader.read(size))


def _command(operation: str, payload: dict, lease: str = _LEASE) -> bytes:
    return _frame(
        {"protocol_version": _PROTOCOL, "operation": operation, "lease": lease, "payload": payload}
    )


def _archive(path: str = "work.txt", content: bytes = b"finished work") -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0)), content)
    return output.getvalue()


def _request(phase="pre_submit", archive_byte_count=None) -> TrustedIntakePreparation:
    return TrustedIntakePreparation(phase, _POLICY, SubmissionArchiveLimits(), 30_000,
                                    len(_archive()) if archive_byte_count is None else archive_byte_count)


def _default(data: bytes) -> WorkstreamDefaultCheckerInput:
    inspection = SubmissionArchiveInspector(SubmissionArchiveLimits()).inspect(BytesIO(data))
    return WorkstreamDefaultCheckerInput(
        archive_sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        archive_byte_count=len(data),
        archive_media_type="application/zip",
        semantic_manifest_sha256=build_submission_manifest(inspection).sha256,
        entries=tuple(SubmissionMaterialEntry(**asdict(item)) for item in inspection.entries),
        predecessor=None,
        predecessor_exists=False,
        current_predecessor=None,
        current_rules_sha256=_POLICY,
        predecessor_rules_sha256=None,
        packet=SubmissionPacketView("Complete", "Authorized"),
    )


def _binding(value: WorkstreamDefaultCheckerInput) -> TrustedDefaultBinding:
    return TrustedDefaultBinding(
        new_record_id(),
        _POLICY,
        _POLICY,
        value.semantic_manifest_sha256,
        workstream_default_input_sha256(value),
    )


def _default_command(value, binding=None):
    binding = binding or _binding(value)
    return _command(
        "default",
        {
            "binding": {**asdict(binding), "attempt_id": str(binding.attempt_id)},
            "input": TypeAdapter(WorkstreamDefaultCheckerInput).dump_python(value, mode="json"),
        },
    )


def _run(tmp_path, data, commands=b"", phase="pre_submit"):
    archive = tmp_path / "archive.zip"
    archive.write_bytes(data)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    output = BytesIO()
    worker = _WORKER.IntakeWorker(
        startup={
            "lease": _LEASE,
            "preparation": asdict(_request(phase, len(data))),
            "archive_sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            "archive_byte_count": len(data),
        },
        archive=archive,
        workspace=workspace,
        reader=BytesIO(commands),
        writer=output,
    )
    return worker, output


def _export_result(output, expected: bytes):
    output.seek(0)
    assert _read(output)["operation"] == "ready"
    assert _read(output)["operation"] == "inspect"
    assert _read(output)["operation"] == "file"
    assert output.read(len(expected)) == expected
    assert _read(output)["operation"] == "export"


def test_worker_inspects_exports_and_runs_canonical_default_once(tmp_path):
    data = _archive()
    value = _default(data)
    worker, output = _run(tmp_path, data, _command("export", {}) + _default_command(value) * 2)
    with pytest.raises(ValueError, match="out of sequence"):
        worker.run()
    _export_result(output, b"finished work")
    result = _read(output)
    assert result["operation"] == "default"
    assert all(check["status"] == "passed" for check in result["payload"]["checks"])
    assert output.read() == b""  # No second default response can be accepted.


@pytest.mark.parametrize(
    "data,code",
    [
        (b"not a zip", "submission_archive_malformed"),
        (_archive("../escape"), "submission_archive_unsafe_entry"),
    ],
    ids=("malformed", "traversal"),
)
def test_worker_preserves_canonical_zip_rejection_without_export(tmp_path, data, code):
    worker, output = _run(tmp_path, data)
    worker.run()
    output.seek(0)
    assert _read(output)["operation"] == "ready"
    assert _read(output)["payload"] == {"code": code}
    assert output.read() == b""
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "mutation", ["before_export", "post", "policy", "manifest", "packet", "lease"]
)
def test_default_requires_export_and_exact_pre_custody(tmp_path, mutation):
    data = _archive()
    value = _default(data)
    binding = _binding(value)
    prefix = _command("export", {})
    if mutation == "before_export":
        prefix = b""
    elif mutation == "policy":
        binding = replace(binding, policy_sha256=_IMAGE)
    elif mutation == "manifest":
        binding = replace(binding, semantic_manifest_sha256=_IMAGE)
    elif mutation == "packet":
        value = replace(value, packet=SubmissionPacketView("Substituted", "Authorized"))
    command = _default_command(value, binding)
    if mutation == "lease":
        command = command.replace(_LEASE.encode(), b"f" * 128)
    worker, output = _run(
        tmp_path,
        data,
        prefix + command,
        phase="post_submit" if mutation == "post" else "pre_submit",
    )
    with pytest.raises(ValueError):
        worker.run()
    assert b'"operation": "default"' not in output.getvalue()
    assert b'"operation":"default"' not in output.getvalue()


@pytest.mark.asyncio
async def test_cancelled_prepare_closes_connection_and_drains_blocking_io(tmp_path):
    path = tmp_path / "node.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen()
    entered, disconnected = threading.Event(), threading.Event()

    def node():
        with listener, listener.accept()[0] as connection:
            reader = connection.makefile("rb")
            assert _read(reader)["operation"] == "prepare"
            entered.set()
            assert reader.read() == b""
            disconnected.set()

    thread = threading.Thread(target=node)
    thread.start()
    adapter = UnixSocketTrustedIntakeAdapter(
        socket_path=path, image_digest=_IMAGE, config_digest=_CONFIG
    )
    pending = asyncio.create_task(adapter.prepare(_request()))
    assert await asyncio.to_thread(entered.wait, 3)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, 2)
    assert await asyncio.to_thread(disconnected.wait, 2)
    thread.join(2)
    assert not thread.is_alive()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime", "runsc"),
        ("image_digest", _POLICY),
        ("config_digest", _POLICY),
        ("default_behavior_sha256", _POLICY),
    ],
)
async def test_health_rejects_other_engine_or_trusted_identity(tmp_path, field, value):
    path = tmp_path / "node.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen()

    def node():
        with listener, listener.accept()[0] as connection:
            assert _read(connection.makefile("rb"))["operation"] == "health"
            identity = {
                "image_digest": _IMAGE,
                "config_digest": _CONFIG,
                "default_behavior_sha256": WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
                "runtime": "smolvm",
                "isolation_mode": "smol-microvm",
                "cpu_millis": 1000,
                "memory_bytes": 2 * 1024**3,
            }
            identity[field] = value
            connection.sendall(
                _frame(
                    {
                        "protocol_version": _PROTOCOL,
                        "operation": "health",
                        "lease": None,
                        "status": "ok",
                        "payload": identity,
                    }
                )
            )

    thread = threading.Thread(target=node)
    thread.start()
    adapter = UnixSocketTrustedIntakeAdapter(
        socket_path=path, image_digest=_IMAGE, config_digest=_CONFIG
    )
    with pytest.raises(ExternalServiceProtocolError):
        await adapter.health()
    thread.join(2)
    assert not thread.is_alive()


@pytest.mark.parametrize("failure", [None, "hash", "truncated", "extra", "path"])
def test_raw_guest_export_requires_exact_inventory_and_content(tmp_path, failure):
    from app.modules.artifacts.submission_archive import exported_submission_tree
    from app.modules.artifacts.api.submission_archive import SubmissionArchiveRejectedError

    data = _archive("folder/work.txt")
    inspection = SubmissionArchiveInspector(SubmissionArchiveLimits()).inspect(BytesIO(data))
    entry = next(item for item in inspection.entries if item.entry_type == "file")
    root = tmp_path / "scratch"
    root.mkdir(mode=0o700)

    def export(sink):
        if failure == "truncated":
            return
        actual = replace(entry, normalized_path="../escape") if failure == "path" else entry
        sink(actual, b"wrong content" if failure == "hash" else b"finished work")
        if failure == "extra":
            sink(entry, b"finished work")

    def consume():
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            projection = exported_submission_tree(
                export,
                Path(f"/proc/self/fd/{descriptor}"),
                expected=inspection,
                limits=SubmissionArchiveLimits(),
            )
            tree = projection.__enter__()
        finally:
            os.close(descriptor)
        try:
            assert tree.read_file("folder/work.txt", maximum_bytes=13) == b"finished work"
            assert (root / "folder/work.txt").stat().st_mode & 0o777 == 0o400
        finally:
            projection.__exit__(None, None, None)
        with pytest.raises(RuntimeError, match="closed"):
            tree.read_file("folder/work.txt", maximum_bytes=13)

    if failure is None:
        consume()
    else:
        with pytest.raises(SubmissionArchiveRejectedError):
            consume()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "missing",
    [
        "artifact_intake_service_socket",
        "artifact_intake_image_digest",
        "artifact_intake_config_digest",
    ],
)
def test_composition_requires_every_trusted_intake_identity(tmp_path, missing):
    from app.adapters.artifacts import trusted_submission_intake
    from app.core.config import Settings
    from app.interfaces.external_services import ExternalServiceConfigurationError

    settings = Settings(
        artifact_intake_service_socket=tmp_path / "intake.sock",
        artifact_intake_image_digest=_IMAGE,
        artifact_intake_config_digest=_CONFIG,
    )
    with pytest.raises(ExternalServiceConfigurationError):
        trusted_submission_intake(settings.model_copy(update={missing: None}))


def test_intake_factory_is_independent_of_project_engine(tmp_path):
    from app.adapters.artifacts import trusted_submission_intake
    from app.core.config import Settings

    adapter = trusted_submission_intake(
        Settings(
            artifact_intake_service_socket=tmp_path / "intake.sock",
            artifact_intake_image_digest=_IMAGE,
            artifact_intake_config_digest=_CONFIG,
            external_checker_service_socket=tmp_path / "project.sock",
            external_checker_material_root=tmp_path / "material",
            artifact_scratch_root=tmp_path / "material",
        )
    )
    assert adapter.identity.capability_key == "trusted_submission_intake"
    assert adapter.identity.provider_key == "unix_socket"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["entry", "sink", "digest"])
async def test_interrupted_export_disconnects_before_cleanup_can_read_raw_bytes(tmp_path, failure):
    import time
    from app.adapters.artifacts.trusted_intake import _Session, _CHUNK
    from app.interfaces.external_services import ExternalServiceUnavailableError

    content = b"x" * (_CHUNK + 64)
    inspection = SubmissionArchiveInspector(SubmissionArchiveLimits()).inspect(
        BytesIO(_archive(content=content)))
    entry = inspection.entries[0]
    adapter = UnixSocketTrustedIntakeAdapter(
        socket_path=tmp_path / "unused.sock", image_digest=_IMAGE, config_digest=_CONFIG)
    session = _Session(adapter, time.monotonic() + 60, _request())
    session._socket.close()
    session._socket, peer = socket.socketpair()
    session._state, session._lease, session._inspection = "inspected", _LEASE, inspection
    announced = replace(entry, normalized_path="different.txt") if failure == "entry" else entry
    payload = content[:-1] + b"y" if failure == "digest" else content
    peer.sendall(_frame({"protocol_version": _PROTOCOL, "operation": "file",
                        "lease": _LEASE, "status": "ok", "payload": asdict(announced)}) + payload)
    sink_error = OSError("scratch write unavailable")

    def sink(actual, chunk):
        assert actual == entry
        if failure == "sink":
            raise sink_error

    try:
        expected = OSError if failure == "sink" else ExternalServiceProtocolError
        with pytest.raises(expected) as raised:
            session.export(sink)
        if failure == "sink":
            assert raised.value is sink_error
        peer.settimeout(0.2)
        with peer.makefile("rb") as reader:
            assert _read(reader)["operation"] == "export"
            try:
                assert reader.read() == b""  # No close command or trailing-frame read.
            except ConnectionResetError:
                pass  # Closing with unread input may reset instead of sending EOF.
        with pytest.raises(ExternalServiceUnavailableError):
            await asyncio.wait_for(session.close(), 1)
    finally:
        session.abort()
        peer.close()


@pytest.mark.parametrize("byte_count", [None, True, 0, -1, 512 * 1024 * 1024 + 1])
def test_preparation_requires_positive_bounded_sealed_archive_count(byte_count):
    with pytest.raises(ValueError, match="trusted intake preparation is invalid"):
        replace(_request(), archive_byte_count=byte_count)
    assert replace(_request(), archive_byte_count=512 * 1024 * 1024).archive_byte_count == 512 * 1024 * 1024


def test_inspect_size_substitution_is_rejected_before_command_or_archive_bytes(tmp_path, monkeypatch):
    import time
    from app.adapters.artifacts.trusted_intake import _Session

    data = _archive()
    adapter = UnixSocketTrustedIntakeAdapter(socket_path=tmp_path / "unused.sock", image_digest=_IMAGE, config_digest=_CONFIG)
    session = _Session(adapter, time.monotonic() + 10, _request(archive_byte_count=len(data)))
    session._state = "prepared"
    commands = []

    def unexpected_command(*args, **kwargs):
        commands.append(args)
        raise AssertionError("size-substituted inspection reached transport")

    monkeypatch.setattr(session, "_command", unexpected_command)
    source = BytesIO(data)
    try:
        with pytest.raises(ExternalServiceProtocolError):
            session.inspect(source, archive_sha256="sha256:" + hashlib.sha256(data).hexdigest(), archive_byte_count=len(data) + 1)
        assert commands == [] and source.tell() == 0
    finally:
        session.abort()


def test_worker_rejects_preparation_size_substitution_before_inspection(tmp_path, monkeypatch):
    worker, output = _run(tmp_path, _archive())
    worker._preparation = replace(worker._preparation, archive_byte_count=worker._preparation.archive_byte_count + 1)

    def unexpected_inspector(*args, **kwargs):
        raise AssertionError("size-substituted archive reached inspector")

    monkeypatch.setattr(_WORKER, "SubmissionArchiveInspector", unexpected_inspector)
    with pytest.raises(ValueError, match="intake archive identity differs"):
        worker.run()
    output.seek(0)
    assert _read(output)["operation"] == "ready"
    assert output.read() == b""
