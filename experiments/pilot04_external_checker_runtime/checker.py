"""Small protocol fixture for the local selected external-checker probe."""

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
    if Path("/work/input/runtime-wait.txt").exists():
        time.sleep(30)
    failures: list[str] = []
    manifest = request["input"].get("manifest")
    if manifest is None:
        if Path("/work/input/src/main.txt").read_bytes() != b"verified bytes":
            failures.append("material")
    else:
        for entry in manifest:
            if entry["entry_type"] != "file":
                continue
            value = Path("/work/input", entry["normalized_path"]).read_bytes()
            digest = "sha256:" + hashlib.sha256(value).hexdigest()
            if len(value) != entry["byte_count"] or digest != entry["sha256"]:
                failures.append("material")
                break
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
    controls = Path("/sys/fs/cgroup")
    if controls.exists():
        if (controls / "memory.max").read_text().strip() != str(request["registry"]["resources"]["memory_bytes"]):
            failures.append("memory_limit")
        if (controls / "pids.max").read_text().strip() == "max":
            failures.append("pids_limit")
    elif list(Path("/sys").iterdir()):
        failures.append("management_filesystem")
    # Smol hides the management filesystem. Memory/PID enforcement is proved by
    # the runtime's adversarial allocation/fork trials, not by project testimony.
    findings = [
        {
            "check_id": "probe.isolation",
            "code": "probe.isolation_failed",
            "level": "error",
            "message": item,
            "path": None,
            "line": None,
        }
        for item in failures
    ]
    requirement = request["input"].get("requirement_id", "")
    pre_marker = "second-pre-rejected.txt" if requirement.endswith(".02") else "project-rejected.txt"
    if Path("/work/input", pre_marker).exists():
        findings.append({
            "check_id": "probe.project_rule",
            "code": "probe.project_rule_failed",
            "level": "error",
            "message": "The sample project rejects this fixture file.",
            "path": pre_marker,
            "line": None,
        })
    if (request["identity"]["phase"] == "post_submit"
            and Path("/work/input/post-rejected.txt").exists()):
        findings.append({
            "check_id": "probe.post_rule",
            "code": "probe.post_rule_failed",
            "level": "error",
            "message": "The sample project requests a replacement for this fixture file.",
            "path": "post-rejected.txt",
            "line": None,
        })
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
