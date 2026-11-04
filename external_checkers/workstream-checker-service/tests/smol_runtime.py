"""Opt-in Linux/KVM node contract proof using an isolated, already provisioned node.

This exercises synthetic ART grants, not public admission or durable job custody.
Use the separate public API drill for those claims. Run as the node/grant Unix
identity with --config and --fixtures (request.json and post_request.json).
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import struct
import time
import uuid


def smol_vm_inventory(path):
    """Separate execution children from Smol's validated persistent cache lock."""
    if not path.exists():
        return set(), None
    entries = {entry.name: entry for entry in path.iterdir()}
    lock = entries.pop(".artifact-cache.lock", None)
    identity = None
    if lock is not None:
        metadata = lock.lstat()
        assert stat.S_ISREG(metadata.st_mode), "engine cache lock is not regular"
        assert stat.S_IMODE(metadata.st_mode) == 0o600, "engine cache lock mode changed"
        assert (metadata.st_uid, metadata.st_gid, metadata.st_nlink, metadata.st_size) == (
            os.geteuid(), os.getegid(), 1, 0,
        ), "engine cache lock custody changed"
        identity = (metadata.st_dev, metadata.st_ino)
    return set(entries), identity


def assert_smol_vm_inventory(path, before):
    """Keep exact execution inventory and any already-observed lock identity."""
    observed = smol_vm_inventory(path)
    assert observed[0] == before[0], "Smol VM execution children changed"
    if before[1] is not None:
        assert observed[1] == before[1], "engine cache lock identity changed"
    return observed


def canonical(value):
    # Fixture rewrites use only strings, integers and booleans. Never use this
    # helper for arbitrary checker configuration's numeric canonicalization.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def receive(connection, size):
    value = b""
    while len(value) < size:
        chunk = connection.recv(size - len(value))
        if not chunk:
            raise EOFError("node closed connection")
        value += chunk
    return value


def exchange(address, envelope):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(90)
        connection.connect(str(address))
        raw = canonical(envelope)
        connection.sendall(struct.pack(">I", len(raw)) + raw)
        length = struct.unpack(">I", receive(connection, 4))[0]
        if not 0 < length <= 81920:
            raise ValueError("response exceeds contract bound")
        return json.loads(receive(connection, length))


class Proof:
    def __init__(self, config, fixtures):
        self.config = config
        self.fixtures = fixtures
        self.created = []

    def request(self, image, phase, case, *, deadline_ms=30000):
        filename = "request.json" if phase == "pre_submit" else "post_request.json"
        request = json.loads((self.fixtures / filename).read_text())
        registry = request["registry"]
        registry["image_digest"] = image["platform_manifest_digest"]
        registry["capability_id"] = "workstream.runtime_fixture"
        registry["configuration_schema"]["document"] = {"type": "object"}
        registry["configuration_schema"]["schema_sha256"] = digest({"type": "object"})
        registry["resources"].update(cpu_millis=500, memory_bytes=134217728,
                                     deadline_ms=deadline_ms, maximum_output_bytes=32768)
        record_fields = {"registry_entry_id", "entry_digest", "registration_operation_id",
                         "registered_by_actor_profile_id", "authorization_decision_event_id", "created_at"}
        registry["entry_digest"] = digest({k: v for k, v in registry.items() if k not in record_fields})
        request["configuration"] = {"case": case}
        request["configuration_sha256"] = digest(request["configuration"])
        content = b"verified material"
        entry = {"normalized_path": "material.txt", "byte_count": len(content),
                 "sha256": "sha256:" + hashlib.sha256(content).hexdigest(), "executable": False}
        semantic = digest({"schema_version": "workstream.submission_bundle_manifest.v1",
                           "entries": [{**entry, "entry_type": "file"}]})
        request["materials"][0]["semantic_manifest_sha256"] = semantic
        request["request_digest"] = digest({k: v for k, v in request.items() if k != "request_digest"})
        identity = {k: v for k, v in request["identity"].items()
                    if k not in {"project_id", "task_id", "assignment_id", "effective_plan_sha256"}}
        identity.update({k: v for k, v in request["materials"][0].items() if k not in {"role", "media_type"}})
        grant_id = "extract_" + uuid.uuid4().hex
        manifest = {"protocol_version": "workstream.external_checker_material_grant.v1",
                    "grant_id": grant_id, "request_digest": request["request_digest"],
                    **identity, "directories": [], "files": [entry]}
        manifest["binding_digest"] = digest(manifest)
        root = Path(self.config["material_root"]) / "workspaces" / grant_id
        root.mkdir(parents=True, mode=0o700)
        self.created.append(root)
        workspace = root / "workspace"
        workspace.mkdir(mode=0o700)
        (workspace / "material.txt").write_bytes(content)
        (workspace / "material.txt").chmod(0o400)
        workspace.chmod(0o500)
        (root / ".external-checker-grant.json").write_bytes(canonical(manifest))
        (root / ".external-checker-grant.json").chmod(0o400)
        return {"protocol_version": "external_checker_service.v1", "operation": "execute",
                "model_grant": None, "request": request, "grant": {"grant_id": grant_id, "binding_digest": manifest["binding_digest"]}}

    def execute(self, image, phase, case, *, expected="passed", deadline_ms=30000):
        envelope = self.request(image, phase, case, deadline_ms=deadline_ms)
        started = time.monotonic()
        response = exchange(self.config["socket_path"], envelope)
        result = response["result"]
        assert result["request_digest"] == envelope["request"]["request_digest"], response
        assert result["result_digest"] == digest({k: v for k, v in result.items() if k != "result_digest"}), response
        observed = result["verdict"] or result["infrastructure_failure_code"]
        row = {"phase": phase, "case": case, "image": image["repository"],
               "observed": observed, "seconds": time.monotonic() - started}
        print(json.dumps(row), flush=True)
        assert observed == expected, response
        # Every matrix case deliberately reaches guest execution, including
        # negative workload cases. A pre-launch failure must not count as proof.
        assert response["isolation"] is not None, response
        assert response["isolation"]["runtime"] == "smolvm", response
        assert response["isolation"]["platform_manifest_digest"] == image["platform_manifest_digest"], response
        return row

    def close(self):
        for root in self.created:
            (root / "workspace").chmod(0o700)
            shutil.rmtree(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    assert config["sandbox_uid"] == os.geteuid() and config["sandbox_gid"] == os.getegid()
    python = next(c for c in config["cache"] if c["repository"] == "workstream-test/smol-python")
    native = next(c for c in config["cache"] if c["repository"] == "workstream-test/smol-native")
    proof = Proof(config, args.fixtures)
    try:
        for image in (python, native):
            for phase in ("pre_submit", "post_submit"):
                proof.execute(image, phase, "pass")
        for case in ("isolation", "cpu", "pids", "disk"):
            proof.execute(python, "pre_submit", case)
        proof.execute(native, "pre_submit", "io_uring")
        for case, expected, deadline in (("memory", "capacity_exceeded", 30000),
                                          ("output", "invalid_output", 30000),
                                          ("sleep", "deadline_exceeded", 2500)):
            proof.execute(python, "pre_submit", case, expected=expected, deadline_ms=deadline)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(proof.execute, python, "post_submit", "cpu") for _ in range(2)]
            for future in futures:
                future.result()
        leases = Path(config["socket_path"]).parent / "smol-leases"
        assert not list(leases.iterdir()), "owned leases remain after returned results"
        cgroups = Path(config["smol"]["cgroup_root"])
        assert not [p for p in cgroups.iterdir() if p.is_dir() and p.name.startswith("ws-")]
        print(json.dumps({"cleanup": "confirmed"}), flush=True)
    finally:
        proof.close()


if __name__ == "__main__":
    main()
