#!/usr/bin/env python3
"""Exercise the release parser's real Linux identity boundary in Docker."""

from __future__ import annotations

import argparse
import asyncio
import errno
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import resource
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile


SOCKET_PATH = Path("/var/lib/workstream/guide-runtime/guide.sock")
PROOF_PATH = Path("/workstream-guide-parser-proof.py")
PROOF_GO_PATH = Path("/tmp/workstream-guide-parser-proof-go")
OUTPUT_LIMIT = 128 * 1024
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
ATTACK_SOURCE = b"WORKSTREAM-ATTACK-PROBE\n"
HANG_SOURCE = b"WORKSTREAM-HANG-PROBE\n"
BROKER_PHASE_PREFIX = "guide parser isolation phase:"
BROKER_PHASES = (
    "formats",
    "attacks",
    "timeout",
    "timeout_reuse",
    "cancel",
    "cancel_reuse",
    "complete",
)
HOST_PHASES = (
    "preflight",
    "negative_controls",
    "broker_launch",
    "healthcheck",
    "worker_control",
    "broker_run",
    "sigterm_cleanup",
    "cleanup",
    "evidence",
)
_HOST_PHASE = "preflight"


class ProofFailure(ValueError):
    """One closed diagnostic code safe to expose from synthetic proof work."""

    def __init__(self, code: str) -> None:
        require(
            code
            in {
                "broker_startup",
                *(f"broker_{phase}" for phase in BROKER_PHASES),
                *(f"host_{phase}" for phase in HOST_PHASES),
            },
            "guide parser proof failure code differs",
        )
        self.code = code
        super().__init__(code)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run(command: list[str], *, timeout: float = 60) -> subprocess.CompletedProcess[bytes]:
    """Bound output without disclosing container diagnostics."""

    def limit_output() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_LIMIT, OUTPUT_LIMIT))

    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(
            command,
            stdout=stdout,
            stderr=stderr,
            timeout=timeout,
            check=False,
            preexec_fn=limit_output,
        )
        stdout.seek(0)
        stderr.seek(0)
        result.stdout = stdout.read(OUTPUT_LIMIT + 1)
        result.stderr = stderr.read(OUTPUT_LIMIT + 1)
        require(
            len(result.stdout) <= OUTPUT_LIMIT and len(result.stderr) <= OUTPUT_LIMIT,
            "guide parser proof output exceeded its limit",
        )
        return result


def checked(command: list[str], *, timeout: float = 60) -> bytes:
    result = run(command, timeout=timeout)
    require(result.returncode == 0, "guide parser Docker proof command failed")
    return result.stdout


def _archive(entries: list[tuple[str, bytes]]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return output.getvalue()


def _docx() -> bytes:
    return _archive(
        [
            ("[Content_Types].xml", b"<Types/>"),
            ("_rels/.rels", b"<Relationships/>"),
            (
                "word/document.xml",
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
                b'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
                b"DOCX Guide</w:t></w:r></w:p></w:body></w:document>",
            ),
        ]
    )


def _pptx() -> bytes:
    return _archive(
        [
            ("[Content_Types].xml", b"<Types/>"),
            ("_rels/.rels", b"<Relationships/>"),
            (
                "ppt/presentation.xml",
                b'<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
                b'presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                b'officeDocument/2006/relationships"><p:sldIdLst>'
                b'<p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>',
            ),
            (
                "ppt/_rels/presentation.xml.rels",
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                b'2006/relationships"><Relationship Id="rId1" '
                b'Target="slides/slide1.xml"/></Relationships>',
            ),
            (
                "ppt/slides/slide1.xml",
                b'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/'
                b'2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/'
                b'2006/main"><p:cSld><a:t>PPTX Guide</a:t></p:cSld></p:sld>',
            ),
        ]
    )


def _pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length 42 >>\nstream\nBT /F1 12 Tf 20 100 Td (PDF Guide) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _request(source: bytes, media_type: str):
    from app.adapters.guide_document_tools.contracts import GuideDocumentParserRequest

    return GuideDocumentParserRequest(
        request_id=uuid.uuid4(),
        source_sha256=f"sha256:{sha256(source).hexdigest()}",
        source_byte_count=len(source),
        media_type=media_type,
        operation="read",
        offset=0,
        limit=65_536,
    )


async def _parse(source: bytes, media_type: str = "text/markdown"):
    from app.adapters.guide_document_tools.client import (
        UnixSocketGuideDocumentParserAdapter,
    )

    adapter = UnixSocketGuideDocumentParserAdapter(
        socket_path=SOCKET_PATH,
        timeout_seconds=10.0,
    )
    return await adapter.parse(_request(source, media_type), source)


def _read_exact(size: int) -> bytes:
    value = sys.stdin.buffer.read(size)
    if len(value) != size:
        raise EOFError
    return value


def _write_frame(value: object) -> None:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    sys.stdout.buffer.write(struct.pack(">I", len(raw)) + raw)
    sys.stdout.buffer.flush()


def _denied(operation, message: str) -> None:
    try:
        operation()
    except RuntimeError:
        return
    except OSError as exc:
        require(exc.errno in {errno.EACCES, errno.EPERM}, message)
        return
    raise ValueError(message)


def _sibling_pid(identity_uid: int) -> int:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit() or int(entry.name) in {os.getpid(), os.getppid()}:
                continue
            try:
                owner = entry.stat().st_uid
            except OSError:
                continue
            if owner in {10_003, 10_004} and owner != identity_uid:
                return int(entry.name)
        time.sleep(0.01)
    raise ValueError("guide parser sibling isolation was not exercised")


def _attack_from_child(identity_uid: int) -> None:
    from app.adapters.guide_document_tools import identity as identity_module

    sibling = _sibling_pid(identity_uid)
    time.sleep(0.15)
    _denied(
        lambda: os.kill(sibling, 0),
        "guide parser child can signal a sibling",
    )
    _denied(
        lambda: os.kill(os.getppid(), 0),
        "guide parser child can signal the broker",
    )
    _denied(
        lambda: Path(f"/proc/{os.getppid()}/environ").read_bytes(),
        "guide parser child can inspect the broker environment",
    )
    _denied(
        lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).connect(
            str(SOCKET_PATH)
        ),
        "guide parser child can connect to the broker socket",
    )
    _denied(
        SOCKET_PATH.unlink,
        "guide parser child can replace the broker socket",
    )
    _denied(
        lambda: os.setresuid(10_002, 10_002, 10_002),
        "guide parser child can regain broker identity",
    )
    _denied(
        lambda: identity_module._set_capability_masks(  # noqa: SLF001
            effective=identity_module.BROKER_CAPABILITY_MASK,
            permitted=identity_module.BROKER_CAPABILITY_MASK,
            inheritable=0,
        ),
        "guide parser child can regain capabilities",
    )
    try:
        forked = os.fork()
    except OSError as exc:
        require(exc.errno == errno.EAGAIN, "guide parser child fork denial changed")
    else:
        if forked == 0:
            os._exit(97)
        os.waitpid(forked, 0)
        raise ValueError("guide parser child can fork")
    time.sleep(0.15)


def child_main() -> int:
    """Verify post-exec state before imports or input, then run one test request."""
    from app.adapters.guide_document_tools.identity import (
        BROKER_CAPABILITY_MASK,
        child_identity_from_environment,
        security_state,
    )

    identity = child_identity_from_environment()
    state = security_state()
    require(
        state
        == {
            "uids": (identity.uid, identity.uid, identity.uid),
            "gids": (identity.gid, identity.gid, identity.gid),
            "groups": (),
            "cap_effective": 0,
            "cap_permitted": 0,
            "cap_inheritable": 0,
            "cap_ambient": 0,
            "cap_bounding": BROKER_CAPABILITY_MASK,
            "no_new_privileges": 1,
            "dumpable": 0,
        },
        "guide parser child kernel state differs",
    )

    from app.adapters.guide_document_tools.contracts import (
        GUIDE_DOCUMENT_PARSER_PROTOCOL,
        GuideDocumentParserRequest,
    )
    from app.adapters.guide_document_tools.parsing import parse_document

    metadata_size = struct.unpack(">I", _read_exact(4))[0]
    metadata = json.loads(_read_exact(metadata_size))
    request = GuideDocumentParserRequest.model_validate(metadata["request"])
    source = _read_exact(request.source_byte_count)
    require(
        metadata.get("protocol_version") == GUIDE_DOCUMENT_PARSER_PROTOCOL
        and metadata.get("operation") == "parse",
        "guide parser proof request differs",
    )
    if source == HANG_SOURCE:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            time.sleep(60)
    if source == ATTACK_SOURCE:
        _attack_from_child(identity.uid)
    result = parse_document(request, source)
    _write_frame(
        {
            "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
            "status": "ok",
            "result": result.model_dump(mode="json"),
        }
    )
    return 0


async def _cancel_in_flight_request() -> None:
    from app.adapters.guide_document_tools.contracts import (
        GUIDE_DOCUMENT_PARSER_PROTOCOL,
    )

    request = _request(HANG_SOURCE, "text/markdown")
    metadata = json.dumps(
        {
            "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
            "operation": "parse",
            "request": request.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    _reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
    writer.write(struct.pack(">I", len(metadata)) + metadata + HANG_SOURCE)
    await writer.drain()
    await asyncio.sleep(0.1)
    writer.close()
    await writer.wait_closed()
    await asyncio.sleep(0.5)


async def broker_main() -> int:
    from app.adapters.guide_document_tools.identity import (
        BROKER_CAPABILITY_MASK,
        BROKER_GID,
        BROKER_UID,
        bootstrap_broker_identity,
        security_state,
    )
    import app.adapters.guide_document_tools.service as service_module
    from workstream_external_services import ExternalServiceUnavailableError

    bootstrap_broker_identity()
    state = security_state()
    require(
        state
        == {
            "uids": (BROKER_UID, BROKER_UID, BROKER_UID),
            "gids": (BROKER_GID, BROKER_GID, BROKER_GID),
            "groups": (),
            "cap_effective": BROKER_CAPABILITY_MASK,
            "cap_permitted": BROKER_CAPABILITY_MASK,
            "cap_inheritable": 0,
            "cap_ambient": 0,
            "cap_bounding": BROKER_CAPABILITY_MASK,
            "no_new_privileges": 1,
            "dumpable": 0,
        },
        "guide parser broker kernel state differs",
    )
    service_module._FIXED_CHILD_COMMAND = (  # noqa: SLF001
        sys.executable,
        "-B",
        str(PROOF_PATH),
        "--child",
    )
    service = service_module.GuideDocumentParserService(
        socket_path=SOCKET_PATH,
        maximum_concurrency=2,
        child_timeout_seconds=8.0,
    )
    await service.start()
    print("guide parser isolation proof ready", flush=True)
    try:
        # Wait for the host to exercise the real healthcheck drop and worker UID.
        deadline = time.monotonic() + 300
        while not PROOF_GO_PATH.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        require(PROOF_GO_PATH.is_file(), "guide parser host controls did not run")
        info = PROOF_GO_PATH.stat()
        require(
            info.st_uid == BROKER_UID and info.st_gid == BROKER_GID,
            "guide parser host control marker identity differs",
        )
        PROOF_GO_PATH.unlink()
        print(f"{BROKER_PHASE_PREFIX}formats", flush=True)
        formats = (
            (b"# Markdown Guide\n", "text/markdown", "Markdown Guide"),
            (_docx(), DOCX, "DOCX Guide"),
            (_pptx(), PPTX, "PPTX Guide"),
            (_pdf(), "application/pdf", "PDF Guide"),
        )
        results = await asyncio.gather(
            *(_parse(source, media_type) for source, media_type, _text in formats)
        )
        for result, (_source, _media_type, expected) in zip(results, formats, strict=True):
            require(expected in result.text, "guide parser format proof differs")
        print(f"{BROKER_PHASE_PREFIX}attacks", flush=True)
        attacks = await asyncio.gather(_parse(ATTACK_SOURCE), _parse(ATTACK_SOURCE))
        require(
            all(result.text == ATTACK_SOURCE.decode() for result in attacks),
            "guide parser concurrent isolation proof differs",
        )
    finally:
        await service.close()

    # One closed slot makes reap-before-reuse observable for timeout and disconnect.
    service = service_module.GuideDocumentParserService(
        socket_path=SOCKET_PATH,
        maximum_concurrency=1,
        child_timeout_seconds=2.0,
    )
    await service.start()
    try:
        print(f"{BROKER_PHASE_PREFIX}timeout", flush=True)
        try:
            await _parse(HANG_SOURCE)
        except ExternalServiceUnavailableError:
            pass
        else:
            raise ValueError("guide parser timeout proof did not fail closed")
        print(f"{BROKER_PHASE_PREFIX}timeout_reuse", flush=True)
        require(
            (await _parse(b"timeout slot reused\n")).text == "timeout slot reused\n",
            "guide parser timeout slot was not safely reused",
        )
        print(f"{BROKER_PHASE_PREFIX}cancel", flush=True)
        await _cancel_in_flight_request()
        print(f"{BROKER_PHASE_PREFIX}cancel_reuse", flush=True)
        require(
            (await _parse(b"cancel slot reused\n")).text == "cancel slot reused\n",
            "guide parser cancelled slot was not safely reused",
        )
    finally:
        await service.close()
    print(f"{BROKER_PHASE_PREFIX}complete", flush=True)
    print("guide parser isolation proof passed", flush=True)
    return 0


async def worker_client_main() -> int:
    from app.adapters.guide_document_tools.identity import security_state

    state = security_state()
    require(
        state["uids"] == (10_001, 10_001, 10_001)
        and state["gids"] == (10_001, 10_001, 10_001)
        and state["cap_effective"] == 0
        and state["cap_permitted"] == 0
        and state["cap_inheritable"] == 0
        and state["cap_ambient"] == 0
        and state["no_new_privileges"] == 1,
        "guide parser worker-client identity differs",
    )
    result = await _parse(b"worker socket control\n")
    require(result.text == "worker socket control\n", "worker parser control failed")
    return 0


def bootstrap_only_main() -> int:
    from app.adapters.guide_document_tools.identity import bootstrap_broker_identity

    bootstrap_broker_identity()
    return 0


def child_check_only_main() -> int:
    from app.adapters.guide_document_tools.identity import (
        child_identity_from_environment,
    )

    child_identity_from_environment()
    return 0


def _container_base(image: str, owner: str) -> list[str]:
    return [
        "docker",
        "run",
        "--label",
        f"workstream.guide-parser-proof={owner}",
        "--network",
        "none",
        "--read-only",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--pids-limit",
        "64",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "--cpus",
        "1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,mode=0700,uid=10002,gid=10001,size=64m",
        "--volume",
        f"{Path(__file__).resolve()}:{PROOF_PATH}:ro",
        "--entrypoint",
        "python",
        image,
        "-B",
        str(PROOF_PATH),
    ]


def _with_container_options(base: list[str], options: list[str]) -> list[str]:
    """Insert Docker options immediately before the image reference."""
    return base[:-3] + options + base[-3:]


def _cleanup(owner: str) -> None:
    command = [
        "docker",
        "ps",
        "--all",
        "--quiet",
        "--no-trunc",
        "--filter",
        f"label=workstream.guide-parser-proof={owner}",
    ]
    containers = checked(command).decode().splitlines()
    for container in containers:
        require(
            len(container) == 64 and all(character in "0123456789abcdef" for character in container),
            "guide parser proof container identity differs",
        )
        checked(["docker", "rm", "--force", container])
    require(not checked(command).strip(), "guide parser proof containers remain")
    volume_command = [
        "docker",
        "volume",
        "ls",
        "--quiet",
        "--filter",
        f"label=workstream.guide-parser-proof={owner}",
    ]
    volumes = checked(volume_command).decode().splitlines()
    for volume in volumes:
        require(
            volume.startswith("workstream-guide-parser-proof-")
            and all(character.isalnum() or character in "-_" for character in volume),
            "guide parser proof volume identity differs",
        )
        checked(["docker", "volume", "rm", volume])
    require(not checked(volume_command).strip(), "guide parser proof volumes remain")


def _prove_sigterm_socket_cleanup(image: str, owner: str) -> None:
    """Stop the production parser container and require its socket to be gone."""

    label = f"workstream.guide-parser-proof={owner}"
    suffix = uuid.uuid4().hex
    volume = f"workstream-guide-parser-proof-{suffix}"
    name = f"workstream-guide-parser-sigterm-{suffix}"
    created = checked(
        ["docker", "volume", "create", "--label", label, volume]
    ).decode().strip()
    require(created == volume, "guide parser proof volume creation differs")
    directory = str(SOCKET_PATH.parent)
    container = checked(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            label,
            "--init",
            "--user",
            "0:0",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "KILL",
            "--cap-add",
            "SETGID",
            "--cap-add",
            "SETUID",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "512m",
            "--memory-swap",
            "512m",
            "--cpus",
            "1",
            "--stop-timeout",
            "30",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,mode=0700,uid=10002,gid=10001,size=64m",
            "--mount",
            f"type=volume,source={volume},target={directory}",
            "--env",
            "WORKSTREAM_RELEASE_ROLE=parser",
            "--env",
            f"WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET={SOCKET_PATH}",
            image,
            "python",
            "-m",
            "app.adapters.guide_document_tools.service",
            "--socket",
            str(SOCKET_PATH),
        ]
    ).decode().strip()
    require(
        len(container) == 64
        and all(character in "0123456789abcdef" for character in container),
        "guide parser SIGTERM container identity differs",
    )
    health = [
        "docker",
        "exec",
        container,
        "python",
        "-m",
        "app.adapters.guide_document_tools.service",
        "--healthcheck",
        "--socket",
        str(SOCKET_PATH),
    ]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if run(health, timeout=30).returncode == 0:
            break
        time.sleep(0.1)
    else:
        raise ValueError("guide parser SIGTERM service did not become healthy")
    stopped = checked(["docker", "stop", "--timeout", "30", container], timeout=60)
    require(stopped.decode().strip() == container, "guide parser SIGTERM stop differs")
    exit_code = checked(
        ["docker", "inspect", "--format", "{{.State.ExitCode}}", container]
    ).decode().strip()
    require(exit_code == "0", "guide parser SIGTERM exit code differs")
    absent = run(
        [
            "docker",
            "run",
            "--rm",
            "--label",
            label,
            "--user",
            "10001:10001",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=volume,source={volume},target={directory},readonly",
            "--entrypoint",
            "python",
            image,
            "-B",
            "-c",
            (
                "import os; path='/var/lib/workstream/guide-runtime/guide.sock'; "
                "raise SystemExit(1 if os.path.lexists(path) else 0)"
            ),
        ]
    )
    require(absent.returncode == 0, "guide parser SIGTERM left its socket")
    checked(["docker", "rm", container])


def _validate_owner(owner: str) -> None:
    require(
        bool(owner)
        and all(character.isalnum() or character in "-_" for character in owner),
        "guide parser proof owner is invalid",
    )


def _set_host_phase(phase: str) -> None:
    global _HOST_PHASE
    require(phase in HOST_PHASES, "guide parser host phase differs")
    _HOST_PHASE = phase


def _write_evidence(path: Path, evidence: dict[str, object]) -> None:
    payload = json.dumps(evidence, sort_keys=True).encode() + b"\n"
    require(len(payload) <= 4096, "guide parser proof evidence exceeds its limit")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def _broker_failure(logs: bytes) -> ProofFailure:
    phase = "startup"
    for raw_line in logs.decode("ascii", errors="ignore").splitlines():
        if raw_line.startswith(BROKER_PHASE_PREFIX):
            candidate = raw_line.removeprefix(BROKER_PHASE_PREFIX)
            if candidate in BROKER_PHASES:
                phase = candidate
    return ProofFailure(f"broker_{phase}")


def _source_checkout(expected_head: str | None) -> str:
    # run() bounds all child file writes, including Git's optional index refresh.
    # Evidence inspection must be read-only even when a large index is stale.
    git = ["git", "--no-optional-locks"]
    source_sha = checked([*git, "rev-parse", "HEAD"]).decode().strip()
    if expected_head is not None:
        require(source_sha == expected_head, "guide parser proof checkout differs")
        require(
            not checked([*git, "status", "--porcelain"]),
            "guide parser proof checkout is dirty",
        )
    return source_sha


def host_main(
    image: str,
    owner: str,
    *,
    expected_head: str | None = None,
    evidence_path: Path | None = None,
) -> int:
    _set_host_phase("preflight")
    _validate_owner(owner)
    source_sha = _source_checkout(expected_head)
    image_id = checked(["docker", "image", "inspect", image, "--format", "{{.Id}}"]).decode().strip()
    require(
        len(image_id) == 71
        and image_id.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in image_id[7:]),
        "guide parser proof image identity differs",
    )
    base = _container_base(image, owner)
    try:
        _set_host_phase("negative_controls")
        # The test must discriminate exact capabilities, an omitted transition,
        # and the rejected former shared-UID design.
        missing = run(
            _with_container_options(
                base,
                ["--user", "0:0", "--cap-add", "SETGID", "--cap-add", "SETUID"],
            )
            + ["--bootstrap-only"]
        )
        require(missing.returncode != 0, "missing broker capability was accepted")
        extra = run(
            _with_container_options(
                base,
                [
                    "--user",
                    "0:0",
                    "--cap-add",
                    "KILL",
                    "--cap-add",
                    "SETGID",
                    "--cap-add",
                    "SETUID",
                    "--cap-add",
                    "CHOWN",
                ],
            )
            + ["--bootstrap-only"]
        )
        require(extra.returncode != 0, "extra broker capability was accepted")
        omitted = run(
            _with_container_options(
                base,
                [
                    "--user",
                    "10002:10001",
                    "--env",
                    "WORKSTREAM_GUIDE_PARSER_CHILD_UID=10003",
                    "--env",
                    "WORKSTREAM_GUIDE_PARSER_CHILD_GID=10003",
                ],
            )
            + ["--child-check-only"]
        )
        require(omitted.returncode != 0, "omitted child transition was accepted")
        shared = run(
            _with_container_options(
                base,
                [
                    "--user",
                    "10002:10001",
                    "--env",
                    "WORKSTREAM_GUIDE_PARSER_CHILD_UID=10002",
                    "--env",
                    "WORKSTREAM_GUIDE_PARSER_CHILD_GID=10001",
                ],
            )
            + ["--child-check-only"]
        )
        require(shared.returncode != 0, "shared broker-child identity was accepted")

        name = "workstream-guide-parser-proof-" + uuid.uuid4().hex
        _set_host_phase("broker_launch")
        broker = _with_container_options(
            base,
            [
                "--detach",
                "--init",
                "--name",
                name,
                "--user",
                "0:0",
                "--cap-add",
                "KILL",
                "--cap-add",
                "SETGID",
                "--cap-add",
                "SETUID",
                "--tmpfs",
                "/var/lib/workstream/guide-runtime:rw,nosuid,nodev,mode=0750,uid=10002,gid=10001,size=1m",
            ]
        ) + ["--broker"]
        container = checked(broker).decode().strip()
        require(len(container) == 64, "guide parser broker container identity differs")

        health = [
            "docker",
            "exec",
            container,
            "python",
            "-m",
            "app.adapters.guide_document_tools.service",
            "--healthcheck",
            "--socket",
            str(SOCKET_PATH),
        ]
        _set_host_phase("healthcheck")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if run(health, timeout=30).returncode == 0:
                    break
            except subprocess.TimeoutExpired:
                pass
            time.sleep(0.1)
        else:
            raise ValueError("guide parser healthcheck identity proof failed")
        _set_host_phase("worker_control")
        worker = run(
            [
                "docker",
                "exec",
                "--user",
                "10001:10001",
                container,
                "python",
                "-B",
                str(PROOF_PATH),
                "--worker-client",
            ],
            timeout=120,
        )
        require(worker.returncode == 0, "guide parser worker control failed")
        _set_host_phase("broker_run")
        checked(
            [
                "docker",
                "exec",
                "--user",
                "10002:10001",
                container,
                "touch",
                str(PROOF_GO_PATH),
            ]
        )
        status = checked(["docker", "wait", container], timeout=120).decode().strip()
        logs_result = run(["docker", "logs", container])
        require(logs_result.returncode == 0, "guide parser broker logs unavailable")
        if status != "0":
            raise _broker_failure(logs_result.stdout)
        logs = logs_result.stdout.decode()
        require(
            logs
            == "guide parser isolation proof ready\n"
            "guide parser isolation phase:formats\n"
            "guide parser isolation phase:attacks\n"
            "guide parser isolation phase:timeout\n"
            "guide parser isolation phase:timeout_reuse\n"
            "guide parser isolation phase:cancel\n"
            "guide parser isolation phase:cancel_reuse\n"
            "guide parser isolation phase:complete\n"
            "guide parser isolation proof passed\n",
            "guide parser broker proof output differs",
        )
        _set_host_phase("sigterm_cleanup")
        _prove_sigterm_socket_cleanup(image, owner)
    finally:
        try:
            _cleanup(owner)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise ProofFailure("host_cleanup") from exc
    _set_host_phase("evidence")
    evidence = {
        "backend_image_id": image_id,
        "cases": [
            "exact_broker_capabilities",
            "broker_and_child_kernel_state",
            "healthcheck_identity_drop",
            "worker_socket_control",
            "four_formats_two_slots",
            "child_socket_broker_sibling_isolation",
            "child_no_regain_or_fork",
            "timeout_cancel_reap_slot_reuse",
            "missing_extra_caps_and_wrong_child_state_denied",
            "omitted_transition_and_shared_uid_detected",
            "sigterm_removes_owned_socket",
        ],
        "container_owner": owner,
        "proof": "guide_parser_identity_isolation_v1",
        "source_sha": source_sha,
    }
    if evidence_path is not None:
        _write_evidence(evidence_path, evidence)
    print(json.dumps(evidence, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image")
    parser.add_argument("--container-owner")
    parser.add_argument("--cleanup-owner")
    parser.add_argument("--expected-head")
    parser.add_argument("--evidence", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--broker", action="store_true")
    modes.add_argument("--child", action="store_true")
    modes.add_argument("--worker-client", action="store_true")
    modes.add_argument("--bootstrap-only", action="store_true")
    modes.add_argument("--child-check-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.cleanup_owner:
        _validate_owner(arguments.cleanup_owner)
        _cleanup(arguments.cleanup_owner)
        print("Guide parser proof cleanup passed.")
        return 0
    if arguments.broker:
        return asyncio.run(broker_main())
    if arguments.child:
        return child_main()
    if arguments.worker_client:
        return asyncio.run(worker_client_main())
    if arguments.bootstrap_only:
        return bootstrap_only_main()
    if arguments.child_check_only:
        return child_check_only_main()
    require(
        bool(arguments.backend_image) and bool(arguments.container_owner),
        "guide parser proof image and owner are required",
    )
    try:
        return host_main(
            arguments.backend_image,
            arguments.container_owner,
            expected_head=arguments.expected_head,
            evidence_path=arguments.evidence,
        )
    except ProofFailure:
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ProofFailure(f"host_{_HOST_PHASE}") from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProofFailure as exc:
        print(f"guide parser isolation proof failed: {exc.code}", file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, subprocess.SubprocessError, ValueError):
        print("guide parser isolation proof failed", file=sys.stderr)
        raise SystemExit(1) from None
