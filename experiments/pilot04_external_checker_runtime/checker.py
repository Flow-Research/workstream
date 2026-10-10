"""Small protocol fixture for the local unselected external-checker probe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import sys
import time


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def main() -> int:
    request = json.load(sys.stdin)
    mode = request["configuration"].get("mode", "pass")
    if mode == "deadline":
        time.sleep(10)
    if mode == "output_overflow":
        sys.stdout.write("x" * (request["registry"]["resources"]["maximum_output_bytes"] + 1))
        return 0
    failures: list[str] = []
    if Path("/work/input/src/main.txt").read_bytes() != b"verified bytes":
        failures.append("material")
    status = Path("/proc/self/status").read_text()
    if "CapEff:\t0000000000000000" not in status:
        failures.append("capabilities")
    if Path("/var/run/docker.sock").exists():
        failures.append("docker_socket")
    try:
        Path("/write-root").write_text("denied")
    except OSError:
        pass
    else:
        failures.append("read_only_root")
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=0.1)
    except OSError:
        pass
    else:
        failures.append("network")
    memory_max = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    if memory_max != str(request["registry"]["resources"]["memory_bytes"]):
        failures.append("memory_limit")
    if Path("/sys/fs/cgroup/pids.max").read_text().strip() == "max":
        failures.append("pids_limit")
    findings = [
        {
            "code": "probe.isolation_failed",
            "level": "error",
            "message": item,
            "path": None,
        }
        for item in failures
    ]
    body = {
        "schema_version": "external_checker_result.v1",
        "request_digest": request["request_digest"],
        "registry_entry_id": request["registry"]["registry_entry_id"],
        "registry_entry_digest": request["registry"]["entry_digest"],
        "phase": request["identity"]["phase"],
        "outcome": "completed",
        "verdict": "failed" if findings else "passed",
        "findings": findings,
        "infrastructure_failure_code": None,
    }
    json.dump(
        {**body, "result_digest": _digest(body)},
        sys.stdout,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
