#!/usr/bin/env python3
"""Smoke the built POST image against one controlled model-session exchange."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
from uuid import uuid4


MAXIMUM_FRAME_BYTES = 1_048_576
CHECK = "solver_brief_and_extension_disclosure"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _read_exact(stream: socket.socket, count: int) -> bytes:
    value = bytearray()
    while len(value) < count:
        chunk = stream.recv(count - len(value))
        if not chunk:
            raise RuntimeError("model session closed before the complete frame")
        value.extend(chunk)
    return bytes(value)


def _read_frame(stream: socket.socket) -> dict[str, object]:
    size = struct.unpack(">I", _read_exact(stream, 4))[0]
    if size < 1 or size > MAXIMUM_FRAME_BYTES:
        raise RuntimeError("model request frame is outside the protocol bound")
    value = json.loads(_read_exact(stream, size))
    if type(value) is not dict:
        raise RuntimeError("model request frame is not an object")
    return value


def _serve_model(socket_path: Path, ready: threading.Event, errors: list[BaseException]) -> None:
    try:
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(socket_path))
            socket_path.chmod(0o666)
            server.listen(1)
            server.settimeout(30)
            ready.set()
            connection, _ = server.accept()
            with connection:
                connection.settimeout(30)
                request = _read_frame(connection)
                if set(request) != {
                    "protocol_version",
                    "operation",
                    "call_index",
                    "prompt",
                    "required_receipt_handles",
                } or (
                    request["protocol_version"] != "workstream.model_session.v2"
                    or request["operation"] != "call"
                    or request["call_index"] != 0
                    or request["required_receipt_handles"] != []
                ):
                    raise RuntimeError("POST image emitted an invalid model-session request")
                prompt = json.loads(request["prompt"])
                evidence_id = prompt["untrusted_evidence_data"]["evidence"][0]["evidence_id"]
                assessment = {
                    "schema_version": "terminal_systems.model_assessment.v1",
                    "requirement_id": prompt["rubric"]["requirement_id"],
                    "material_digest": prompt["untrusted_evidence_data"]["material_digest"],
                    "conditions": [
                        {
                            "condition_number": item["condition_number"],
                            "status": "satisfied",
                            "evidence_ids": [evidence_id],
                            "finding_numbers": [],
                        }
                        for item in prompt["rubric"]["pass_conditions"]
                    ],
                    "findings": [],
                }
                response = _canonical(
                    {
                        "protocol_version": "workstream.model_session.v2",
                        "outcome": "completed",
                        "call_index": 0,
                        "output": _canonical(assessment).decode("utf-8"),
                        "receipt_digest": "sha256:"
                        + hashlib.sha256(_canonical(assessment)).hexdigest(),
                        "failure_code": None,
                        "session_exhausted": True,
                    }
                )
                connection.sendall(struct.pack(">I", len(response)) + response)
                if connection.recv(1):
                    raise RuntimeError("POST image sent an unexpected second model frame")
    except BaseException as exc:  # retain a bounded failure for the main thread
        errors.append(exc)
        ready.set()


def _request() -> bytes:
    return _canonical(
        {
            "request_digest": "sha256:" + "1" * 64,
            "registry": {
                "registry_entry_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
                "entry_digest": "sha256:" + "2" * 64,
                "resources": {"deadline_ms": 30_000},
            },
            "identity": {"phase": "post_submit"},
            "configuration": {"check": CHECK},
            "input": {"requirement_id": CHECK},
        }
    )


def _write_material(root: Path) -> None:
    root.mkdir(mode=0o755)
    (root / "instruction.md").write_text("Explain the solver approach.\n", encoding="utf-8")
    (root / "task.toml").write_text("format_version = 1\n", encoding="utf-8")
    (root / "AUTHOR_NOTES.md").write_text("No extensions are used.\n", encoding="utf-8")
    (root / "workspace").mkdir(mode=0o755)
    (root / "tests").mkdir(mode=0o755)
    for path in root.iterdir():
        if path.is_file():
            path.chmod(0o444)


def _owned_container_ids(name: str) -> str:
    completed = subprocess.run(
        [
            "docker",
            "container",
            "ls",
            "--all",
            "--quiet",
            "--filter",
            f"name=^/{name}$",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def qualify(image: str) -> None:
    name = "ws-terminal-systems-post-smoke-" + uuid4().hex
    with tempfile.TemporaryDirectory(prefix="ws-terminal-systems-post-") as temporary:
        work = Path(temporary)
        work.chmod(0o755)
        _write_material(work / "input")
        socket_path = work / "model.sock"
        ready = threading.Event()
        errors: list[BaseException] = []
        server = threading.Thread(
            target=_serve_model, args=(socket_path, ready, errors), daemon=True
        )
        server.start()
        if not ready.wait(10) or errors:
            raise RuntimeError("controlled model socket did not become ready") from (
                errors[0] if errors else None
            )
        create_attempted = False
        primary_error: BaseException | None = None
        cleanup_error: BaseException | None = None
        try:
            create_attempted = True
            subprocess.run(
                [
                    "docker",
                    "create",
                    "--name",
                    name,
                    "--label",
                    "workstream.terminal-systems-post-smoke=true",
                    "--network",
                    "none",
                    "--read-only",
                    "--user",
                    "65532:65532",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--pids-limit",
                    "64",
                    "--memory",
                    "268435456",
                    "--cpus",
                    "1.0",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,nodev,size=16777216",
                    "--mount",
                    f"type=bind,src={work},dst=/work,readonly",
                    "-i",
                    image,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            completed = subprocess.run(
                ["docker", "start", "--attach", "--interactive", name],
                input=_request(),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=40,
            )
            result = json.loads(completed.stdout)
            if (
                result.get("outcome") != "completed"
                or result.get("verdict") != "passed"
                or result.get("findings") != []
                or result.get("request_digest") != "sha256:" + "1" * 64
            ):
                raise RuntimeError("POST image did not return the controlled passing result")
            inspected = subprocess.run(
                ["docker", "inspect", "--format", "{{json .State}}", name],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            state = json.loads(inspected.stdout)
            if state.get("Running") or state.get("OOMKilled") or state.get("ExitCode") != 0:
                raise RuntimeError("POST image did not exit cleanly")
        except BaseException as exc:
            primary_error = exc
        finally:
            if create_attempted:
                try:
                    if _owned_container_ids(name):
                        removed = subprocess.run(
                            ["docker", "rm", "--force", name],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        if removed.stdout.strip() != name:
                            raise RuntimeError(
                                "Docker did not confirm the owned container removal"
                            )
                except BaseException as exc:
                    cleanup_error = RuntimeError(
                        "POST smoke container removal failed"
                    )
                    cleanup_error.__cause__ = exc
            server.join(10)
        if server.is_alive() and primary_error is None:
            primary_error = RuntimeError("controlled model server did not terminate")
        if errors and primary_error is None:
            primary_error = RuntimeError("controlled model exchange failed")
            primary_error.__cause__ = errors[0]
        try:
            if _owned_container_ids(name):
                raise RuntimeError("POST smoke container cleanup is incomplete")
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
        if primary_error is not None:
            if cleanup_error is not None:
                primary_error.add_note(f"cleanup also failed: {cleanup_error!r}")
            raise primary_error
        if cleanup_error is not None:
            raise cleanup_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    arguments = parser.parse_args()
    qualify(arguments.image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
