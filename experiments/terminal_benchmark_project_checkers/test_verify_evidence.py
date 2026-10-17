#!/usr/bin/env python3
"""Focused rejection tests for the WS493 upload allowlist."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

import verify_evidence


HEAD = "a" * 40


class EvidenceVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.raw.mkdir(mode=0o700)
        self._write_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, name: str, value: bytes) -> None:
        path = self.raw / name
        path.write_bytes(value)
        path.chmod(0o600)

    def _write_fixture(self) -> None:
        generic = (
            json.dumps({"schema_version": verify_evidence.SCHEMA}).encode() + b"\n"
        )
        for name in verify_evidence.INITIAL_FILES:
            if name.endswith(".ndjson"):
                value = b"{}\n"
            elif name.endswith(".json"):
                value = generic
            else:
                value = b"bounded diagnostic\n"
            self._write(name, value)
        self._write("proof-head.txt", (HEAD + "\n").encode())
        self._write(
            "matrix.json",
            (
                json.dumps(
                    {
                        "schema_version": verify_evidence.SCHEMA,
                        "head_sha": HEAD,
                        "interrupted": {
                            "adapter_failure": True,
                            "art_unwound": True,
                            "restart_swept_owned": True,
                            "unowned_control_preserved": True,
                        },
                        "complete": {
                            "builder_exit": 0,
                            "candidate_exit": 1,
                            "outcome": "completed",
                            "owned_resources_absent": True,
                            "reference_exits": [0, 0, 0],
                            "stable": True,
                            "verdict": "passed",
                        },
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode(),
        )
        self._write(
            "quota.json",
            (
                json.dumps(
                    {
                        "backing_filesystem": "xfs",
                        "d_type": True,
                        "inner_driver": "overlay2",
                        "project_quota": True,
                        "storage_opt_bytes": 402_653_184,
                        "below_limit_bytes": 335_544_320,
                        "below_limit_succeeded": True,
                        "above_limit_bytes": 419_430_400,
                        "above_limit_failed": True,
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode(),
        )
        self._write(
            "harness.json",
            (
                json.dumps(
                    {
                        "cpu_nanos": 2_000_000_000,
                        "external_network": "none",
                        "memory_bytes": 4_294_967_296,
                        "pids_limit": 768,
                        "privileged": True,
                        "runtime_key": "runsc",
                        "same_absolute_state_mount": True,
                        "xfs_docker_state_mount": True,
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode(),
        )
        for name in ("art-interrupt.json", "art-complete.json"):
            self._write(name, b'{"ledger_empty":true,"workspace_empty":true}\n')
        self._write(
            "restart-cleanup.json",
            b'{"owned_containers_absent":true,"owned_images_absent":true,'
            b'"unowned_control_preserved":true}\n',
        )

    def _stage(self, name: str = "stage") -> Path:
        destination = self.root / name
        verify_evidence.stage(self.raw, destination, HEAD, os.geteuid())
        return destination

    def test_exact_inventory_stages_and_final_cleanup_verifies(self) -> None:
        stage = self._stage()
        receipt = self.root / "ws493-run-cleanup-receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": verify_evidence.SCHEMA,
                    "head_sha": HEAD,
                    "dind_absent": True,
                    "loop_detached": True,
                    "outer_owned_resources_absent": True,
                    "raw_state_deleted": True,
                    "registry_absent": True,
                    "xfs_unmounted": True,
                },
                sort_keys=True,
            )
            + "\n"
        )
        receipt.chmod(0o600)
        verify_evidence.add_cleanup(stage, receipt, HEAD, os.geteuid())
        self.assertTrue((stage / "cleanup-receipt.json").is_file())
        self.assertFalse((stage / receipt.name).exists())
        verify_evidence.final(stage, HEAD)

    def test_head_substitution_is_rejected(self) -> None:
        self._write("proof-head.txt", ("b" * 40 + "\n").encode())
        with self.assertRaisesRegex(verify_evidence.EvidenceError, "head differs"):
            self._stage()

    def test_missing_cleanup_is_rejected(self) -> None:
        stage = self._stage()
        with self.assertRaisesRegex(verify_evidence.EvidenceError, "inventory differs"):
            verify_evidence.final(stage, HEAD)

    def test_false_cleanup_is_rejected(self) -> None:
        stage = self._stage()
        receipt = self.root / "cleanup-receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": verify_evidence.SCHEMA,
                    "head_sha": HEAD,
                    "dind_absent": False,
                    "loop_detached": True,
                    "outer_owned_resources_absent": True,
                    "raw_state_deleted": True,
                    "registry_absent": True,
                    "xfs_unmounted": True,
                }
            )
        )
        receipt.chmod(0o600)
        with self.assertRaisesRegex(verify_evidence.EvidenceError, "cleanup receipt"):
            verify_evidence.add_cleanup(stage, receipt, HEAD, os.geteuid())

    def test_extra_entry_is_rejected(self) -> None:
        self._write("unexpected.json", b"{}\n")
        with self.assertRaisesRegex(verify_evidence.EvidenceError, "inventory differs"):
            self._stage()

    def test_symlink_and_fifo_are_rejected(self) -> None:
        target = self.raw / "tool-versions.json"
        target.unlink()
        target.symlink_to("matrix.json")
        with self.assertRaises(verify_evidence.EvidenceError):
            self._stage("symlink-stage")
        target.unlink()
        os.mkfifo(target, mode=0o600)
        with self.assertRaises(verify_evidence.EvidenceError):
            self._stage("fifo-stage")

    def test_path_escape_name_and_oversize_are_rejected(self) -> None:
        descriptor = os.open(self.raw, os.O_RDONLY)
        try:
            with self.assertRaisesRegex(
                verify_evidence.EvidenceError, "name is unsafe"
            ):
                verify_evidence._read_regular(
                    descriptor,
                    "../escape",
                    64,
                    expected_uid=os.geteuid(),
                    expected_modes={0o600},
                )
        finally:
            os.close(descriptor)
        self._write("verifier-tests.json", b"x" * (8_192 + 1))
        with self.assertRaisesRegex(verify_evidence.EvidenceError, "identity differs"):
            self._stage()


if __name__ == "__main__":
    unittest.main()
