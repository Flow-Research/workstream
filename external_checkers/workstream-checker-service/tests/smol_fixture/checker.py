"""Adversarial runtime fixture. Never registered as a project evaluator."""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import stat
import sys
import time


PRE_SOURCE_SCHEMA = "workstream.external_checker_pre_submit_input.v1"
TIMEOUT_MARKER = "pre-qualification-timeout.txt"
MEMORY_MARKER = "pre-qualification-memory.txt"
CRASH_MARKER = "pre-qualification-crash.txt"
OUTPUT_MARKER = "pre-qualification-output.txt"


def denied(operation, *, expected_errno=None):
    try:
        value = operation()
    except OSError as error:
        if expected_errno is not None:
            assert error.errno == expected_errno, error
        return
    if hasattr(value, "close"):
        value.close()
    raise AssertionError("operation was allowed")


def evaluate_source_first(request):
    """Pass only after the selected PRE safety observations complete."""
    assert request["identity"]["phase"] == "pre_submit"
    assert request["input"]["schema_version"] == PRE_SOURCE_SCHEMA
    assert os.getuid() != 0 and os.getgid() != 0
    input_root = Path("/work/input")
    manifest = request["input"]["manifest"]
    assert all(entry["entry_type"] == "file" for entry in manifest)
    assert {path.name for path in input_root.iterdir()} == {
        entry["normalized_path"] for entry in manifest
    }
    assert os.statvfs(input_root).f_flag & os.ST_RDONLY
    for entry in manifest:
        path = input_root / entry["normalized_path"]
        data = path.read_bytes()
        assert len(data) == entry["byte_count"]
        assert "sha256:" + hashlib.sha256(data).hexdigest() == entry["sha256"]
        denied(lambda: path.open("ab"))
        assert path.read_bytes() == data

    assert fcntl.fcntl(0, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
    for descriptor in Path("/proc/self/fd").iterdir():
        if int(descriptor.name) > 2:
            denied(lambda: os.fstat(int(descriptor.name)), expected_errno=errno.EBADF)
    (private,) = Path("/").glob(".workstream-pre-*")
    denied(lambda: list(private.iterdir()), expected_errno=errno.EACCES)
    worker_control = private / "worker-view/request.json"
    denied(lambda: worker_control.open("rb"), expected_errno=errno.EACCES)
    denied(lambda: worker_control.open("ab"), expected_errno=errno.EACCES)
    assert not list(Path("/run").iterdir())
    assert not list(Path("/sys").iterdir())
    assert "WORKSTREAM_PRE_QUALIFICATION_PRIVATE_CANARY" not in os.environ
    denied(lambda: socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM))

    if (input_root / TIMEOUT_MARKER).is_file():
        assert (input_root / TIMEOUT_MARKER).read_bytes() == b"selected PRE deadline fixture\n"
        time.sleep(30)
    if (input_root / MEMORY_MARKER).is_file():
        assert (input_root / MEMORY_MARKER).read_bytes() == b"selected PRE memory fixture\n"
        # Commit more than the selected 128 MiB guest ceiling in bounded pages.
        allocated = []
        for _ in range(128):
            allocated.append(bytearray(4 * 1024 * 1024))
        raise AssertionError("guest memory ceiling was not enforced")
    if (input_root / CRASH_MARKER).is_file():
        assert (input_root / CRASH_MARKER).read_bytes() == b"selected PRE crash fixture\n"
        os._exit(37)
    if (input_root / OUTPUT_MARKER).is_file():
        assert (input_root / OUTPUT_MARKER).read_bytes() == b"selected PRE output fixture\n"
        sys.stdout.write("x" * 1024 * 1024)
        sys.stdout.flush()
        raise AssertionError("guest output ceiling was not enforced")


def evaluate(request):
    if request["configuration"] == {"check": "incident_summary_layout"}:
        evaluate_source_first(request)
        return
    case = request["configuration"]["case"]
    if case == "sleep":
        time.sleep(30)
    elif case == "output":
        sys.stdout.write("x" * 1024 * 1024)
        sys.stdout.flush()
        time.sleep(30)
    elif case == "memory":
        # Incremental committed pages reach the cgroup ceiling. One huge mmap
        # can instead be refused by kernel overcommit before that boundary.
        allocated = []
        for _ in range(128):
            allocated.append(bytearray(4 * 1024 * 1024))
    elif case == "pids":
        children = []
        try:
            for _ in range(512):
                try:
                    pid = os.fork()
                except OSError as error:
                    assert error.errno == errno.EAGAIN
                    limit = max(16, min(256, request["registry"]["resources"]["memory_bytes"] // (16 * 1024 * 1024)))
                    assert len(children) == limit - 1
                    break
                if pid == 0:
                    time.sleep(30)
                    os._exit(0)
                children.append(pid)
            else:
                raise AssertionError("PID ceiling not enforced")
        finally:
            for pid in children:
                os.kill(pid, signal.SIGKILL)
            for pid in children:
                os.waitpid(pid, 0)
    elif case == "cpu":
        start = time.monotonic()
        cpu = time.process_time()
        while time.monotonic() - start < 3:
            pass
        ratio = (time.process_time() - cpu) / (time.monotonic() - start)
        assert ratio <= request["registry"]["resources"]["cpu_millis"] / 1000 + 0.15
    elif case == "disk":
        try:
            with open("/tmp/fill", "wb") as output:
                for _ in range(32):
                    output.write(b"x" * 1024 * 1024)
        except OSError as error:
            assert error.errno == errno.ENOSPC
        else:
            raise AssertionError("scratch disk ceiling not enforced")
        finally:
            Path("/tmp/fill").unlink(missing_ok=True)
    elif case == "isolation":
        assert os.getuid() != 0 and os.getgid() != 0
        assert all(int(line.split()[1], 16) == 0 for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("Cap"))
        assert os.statvfs("/").f_flag & os.ST_RDONLY
        assert os.statvfs("/work/input").f_flag & os.ST_RDONLY
        assert not list(Path("/sys").iterdir())
        assert not list(Path("/run").iterdir())
        assert Path("/work/input/material.txt").read_bytes() == b"verified material"
        denied(lambda: open("/work/input/material.txt", "wb"))
        denied(lambda: open("/etc/passwd", "ab"))
        device = Path("/image-owned-device").lstat()
        assert stat.S_ISCHR(device.st_mode)
        assert os.major(device.st_rdev) == 1 and os.minor(device.st_rdev) == 3
        denied(lambda: open("/image-owned-device", "rb"), expected_errno=errno.EACCES)
        denied(lambda: socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM))
        denied(lambda: socket.create_connection(("1.1.1.1", 443), timeout=0.3))
        with open("/tmp/private", "wb") as temporary:
            temporary.write(b"scratch")
    elif case != "pass":
        raise AssertionError("unknown fixture case")


def main():
    request = json.load(sys.stdin)
    evaluate(request)
    body = {"schema_version": "external_checker_result.v1",
            "request_digest": request["request_digest"],
            "registry_entry_id": request["registry"]["registry_entry_id"],
            "registry_entry_digest": request["registry"]["entry_digest"],
            "phase": request["identity"]["phase"], "outcome": "completed", "verdict": "passed",
            "findings": [], "infrastructure_failure_code": None}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    body["result_digest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    print(json.dumps(body, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
