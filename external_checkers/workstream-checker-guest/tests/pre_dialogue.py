"""Portable live-worker protocol proof; no mount, VM or execution qualification."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import sys
from uuid import UUID
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.hashing import canonical_json_hash  # noqa: E402
from app.modules.checkers.api.selected_pre_submit import (  # noqa: E402
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)

CONTENT = b"finished work\n"
SECRET = b"-----BEGIN RSA PRIVATE KEY-----\nsecret"


def zip_bytes(case: str) -> bytes:
    """Create input bytes; only the actual worker inspects them in this proof."""
    if case == "unsafe":
        return b"not a ZIP"
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("nested/", b"")
        archive.writestr("nested/work.txt", SECRET if case == "secret" else CONTENT)
    return output.getvalue()


def incompatible_schema(reservation):
    """A default blocker must not enter this incompatible project contract."""
    from app.modules.checkers.api.external import external_checker_json_hash
    from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
    from tests.checkers.external.support import registry_entry
    binding = reservation.policy.entries[0].model_copy(update={"registry": registry_entry()})
    body = reservation.policy.model_dump(mode="json", exclude={"policy_sha256"})
    body["entries"] = [binding.model_dump(mode="json")]
    policy = LockedExternalPreSubmitPolicy.model_validate_json(json.dumps(
        body | {"policy_sha256": external_checker_json_hash(body)},
    ))
    return replace(reservation, policy=policy, admission_lineage=replace(
        reservation.admission_lineage, effective_plan_sha256=policy.policy_sha256,
    ))


def worker_process(case: str, directory: Path) -> None:
    """Use real stdin/stdout instead of the helper's simulated project reply."""
    from tests.test_trusted_intake import _pre_worker
    worker, _, unused_reply, lease = _pre_worker(
        directory, zip_bytes(case),
        reservation_change=incompatible_schema if case == "secret" else None,
    )
    assert unused_reply.calls == 0
    startup = {"operation": "execute_pre", "request": {
        "protocol_version": "external_checker_service.v1", "operation": "execute_pre",
        "reservation": lease.reservation.canonical_body(),
        "request_digest": lease.reservation.request_digest, "lease_id": str(lease.lease_id),
        "lease_generation": lease.lease_generation, "lease_expires_at": lease.lease_expires_at.isoformat(),
    }, "isolation": asdict(worker._isolation)}
    (directory / "startup.json").write_text(json.dumps(startup))
    # The prefix is test setup, consumed before production worker dialogue. Its
    # root descriptor is synthetic and must never be used as qualification.
    job = {
        "limits": json.loads(os.environ["WORKSTREAM_PRE_PROOF_LIMITS"]),
        "root": {
            "schema_version": "workstream.trusted_root.v1",
            "platform_manifest_digest": "sha256:" + "1" * 64,
            "config_image_id": "sha256:" + "2" * 64,
            "default_behavior_sha256": lease.reservation.default_behavior_sha256,
            "expanded_bytes": 3, "entries": 1, "bundle_byte_count": 128,
            "bundle_sha256": lease.reservation.runtime_profile.platform_root_sha256,
        },
        "root_limits": {"maximum_bundle_bytes": 128, "maximum_root_bytes": 3, "maximum_entries": 1},
        "selected": {"purpose": {"kind": "project", "capabilities": {"model": False, "execution": False}, "materials": []},
                     "request": None, "command": ["/protocol-result-sentinel"], "environment": [],
                     "working_directory": "/", "uid": 12346, "gid": 12346, "directories": [], "files": []},
        "startup": startup,
    }
    encoded = json.dumps(job).encode()
    sys.stdout.buffer.write(struct.pack(">I", len(encoded)) + encoded)
    sys.stdout.buffer.flush()
    worker._reader, worker._writer = sys.stdin.buffer, sys.stdout.buffer
    worker.run()
    assert unused_reply.calls == 0, "simulated helper reply escaped into live dialogue"


def validate_completion(case: str, directory: Path) -> None:
    """Validate exactly the frame Rust received, through the Python owner type."""
    startup = json.loads((directory / "startup.json").read_bytes())
    header = startup["request"]
    reservation = SelectedPreSubmitReservationFacts.from_canonical_body(header["reservation"])
    lease = SelectedPreSubmitLeaseFacts(reservation, UUID(header["lease_id"]),
                                       header["lease_generation"], datetime.fromisoformat(header["lease_expires_at"]))
    terminal = json.loads(sys.stdin.buffer.read())
    assert terminal["operation"] == "completed"
    execution = SelectedPreSubmitExecutionFacts.from_canonical_body(terminal["payload"])
    execution.validate_lease(lease)
    archive = (directory / "pre.zip").read_bytes()
    assert execution.observed_source.raw_sha256 == "sha256:" + hashlib.sha256(archive).hexdigest()
    assert execution.observed_source.raw_byte_count == len(archive)
    if case == "unsafe":
        assert execution.manifest_body is None
        assert execution.workstream_default.checks[0].status == "failed"
        assert all(check.status == "not_run" for check in execution.workstream_default.checks[1:])
    else:
        content = SECRET if case == "secret" else CONTENT
        expected = {"schema_version": "workstream.submission_bundle_manifest.v1", "entries": [
            {"normalized_path": "nested", "entry_type": "directory"},
            {"normalized_path": "nested/work.txt", "entry_type": "file", "byte_count": len(content),
             "sha256": "sha256:" + hashlib.sha256(content).hexdigest(), "executable": False},
        ]}
        assert execution.manifest_body == expected
        assert execution.manifest_sha256 == canonical_json_hash(expected)
        if case == "secret":
            assert execution.workstream_default.checks[2].status == "failed"
        else:
            assert all(check.status == "passed" for check in execution.workstream_default.checks)
    assert execution.eligible == (case == "passing")
    assert len(execution.external_members) == (1 if case == "passing" else 0)
    if case == "passing":
        assert execution.external_members[0].result.verdict == "passed"
    print(json.dumps({"eligible": execution.eligible, "result_digest": execution.result_digest}))


if __name__ == "__main__":
    mode, case, directory = sys.argv[1:]
    assert case in {"passing", "secret", "unsafe"}
    {"worker": worker_process, "validate": validate_completion}[mode](case, Path(directory))
