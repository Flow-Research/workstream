"""Read one bounded A29 runner snapshot without invoking or changing the service."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


_VM_NAME = re.compile(r"ws-[0-9a-f]{32}")
_GRANT_NAME = re.compile(r"extract_[0-9a-f]{32}")
_PRE_FIELDS = ("run_id", "source_operation_id", "request_digest", "lease_id", "lease_generation")
_POST_FIELDS = ("project_id", "task_id", "submission_id", "evaluation_request_id", "attempt_id", "lease_id")


def _read(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("native observation exceeded its input bound")
    return payload


def _sha(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _lease_journal(path):
    # The owner creates each lease file before writing its fsynced contents.
    # A partial first read cannot count as an idle node or a completed admission.
    for attempt in range(3):
        journal = _read(path, 16_384)
        try:
            return journal, json.loads(journal)
        except json.JSONDecodeError:
            if attempt == 2:
                raise
            time.sleep(0.02)


def _controller_pid():
    value = subprocess.check_output(
        ["systemctl", "show", "workstream-checker.service", "-p", "MainPID", "--value"],
        timeout=3,
    )
    return int(value)


def observe(config_path, config_sha256, service_sha256):
    raw = _read(config_path, 65_536)
    if _sha(raw) != config_sha256:
        raise ValueError("active runner configuration differs from the reviewed copy")
    config = json.loads(raw)
    pid = _controller_pid()
    if pid <= 0:
        raise ValueError("native runner is not active")
    with Path(f"/proc/{pid}/exe").open("rb") as executable:
        if "sha256:" + hashlib.file_digest(executable, "sha256").hexdigest() != service_sha256:
            raise ValueError("active runner executable differs from the reviewed copy")
    lease_root = Path(config["socket_path"]).parent / "smol-leases"
    owner = _read(lease_root.parent / ".workstream-checker-owner", 128).decode().strip()
    groups = Path(config["smol"]["cgroup_root"])
    leases = []
    for path in sorted(lease_root.glob("ws-*.json")):
        if _VM_NAME.fullmatch(path.stem) is None or len(leases) == 2:
            raise ValueError("unexpected native lease inventory")
        try:
            journal, lease = _lease_journal(path)
        except FileNotFoundError:
            continue
        if lease["name"] != path.stem or lease["owner"] != owner:
            raise ValueError("native lease owner differs")
        try:
            events = _read(groups / path.stem / "cgroup.events", 1_024).splitlines()
        except FileNotFoundError:
            events = []
        if lease["pre"] is not None and lease["pre"]["operation"] != "execute_pre":
            raise ValueError("unknown native PRE lease operation")
        selected = None if lease["pre"] is None else {key: lease["pre"][key] for key in _PRE_FIELDS}
        leases.append({"name": path.stem, "epoch": lease["epoch"],
                       "journal_sha256": _sha(journal), "populated": b"populated 1" in events, "pre": selected})
    grants = []
    for path in sorted((Path(config["material_root"]) / "workspaces").glob("extract_*")):
        if _GRANT_NAME.fullmatch(path.name) is None or len(grants) == 1:
            raise ValueError("unexpected native material inventory")
        try:
            manifest = json.loads(_read(path / ".external-checker-grant.json", 2_097_152))
        except FileNotFoundError:
            continue
        binding = manifest.pop("binding_digest")
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode()
        if (manifest["protocol_version"] != "workstream.external_checker_material_grant.v2"
                or manifest["grant_id"] != path.name or manifest["phase"] != "post_submit"
                or manifest["identity"]["phase"] != "post_submit" or binding != _sha(canonical)):
            raise ValueError("native POST grant identity differs")
        grants.append({"grant_id": path.name, "request_digest": manifest["request_digest"],
                       **{key: manifest["identity"][key] for key in _POST_FIELDS}})
    if _controller_pid() != pid or _read(config_path, 65_536) != raw:
        raise ValueError("native runner changed during observation")
    return {"config_sha256": config_sha256, "service_sha256": service_sha256,
            "checker_pid": pid, "leases": leases, "post_grants": grants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("config_sha256")
    parser.add_argument("service_sha256")
    args = parser.parse_args()
    print(json.dumps(observe(args.config, args.config_sha256, args.service_sha256), sort_keys=True))


if __name__ == "__main__":
    main()
