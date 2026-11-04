"""Evidence admission regressions; these do not execute or qualify a microVM."""

from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import smol_recovery
import smol_runtime

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts/qualify_terminal_systems_smol.py"
)
spec = importlib.util.spec_from_file_location("smol_qualifier", SCRIPT)
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)


class QualificationEvidenceTests(unittest.TestCase):
    def test_source_guard_rejects_substitution_and_untracked_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", str(root), *args],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()

            git("init")
            (root / "source").write_text("reviewed")
            git("add", "source")
            git(
                "-c",
                "user.name=Qualification Test",
                "-c",
                "user.email=test@invalid.example",
                "commit",
                "-m",
                "fixture",
            )
            head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
            qualifier.verify_source(root, head, tree)
            with self.assertRaisesRegex(ValueError, "identity differs"):
                qualifier.verify_source(root, "0" * 40, tree)
            (root / "extra-code").write_text("unreviewed")
            with self.assertRaisesRegex(ValueError, "not clean"):
                qualifier.verify_source(root, head, tree)
            (root / "extra-code").unlink()
            (root / "source").write_text("changed")
            with self.assertRaisesRegex(ValueError, "not clean"):
                qualifier.verify_source(root, head, tree)

    def test_binary_provenance_rejects_mutation_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {
                name: root / name
                for name in ("service", "guest", "launcher", "filesystem_tool")
            }
            for name, path in paths.items():
                path.write_bytes(name.encode())
            binaries = {name: qualifier.digest(path) for name, path in paths.items()}
            manifest = {
                "source_head": "a" * 40,
                "source_tree": "b" * 40,
                "binaries": binaries,
            }
            config = {
                "smol": {
                    "guest_binary": str(paths["guest"]),
                    "guest_sha256": binaries["guest"],
                },
                "trial_runtime": {
                    "trusted_launcher_path": str(paths["launcher"]),
                    "trusted_launcher_digest": binaries["launcher"],
                    "filesystem_tool_path": str(paths["filesystem_tool"]),
                    "filesystem_tool_digest": binaries["filesystem_tool"],
                },
            }
            qualifier.verify_build(
                manifest, config, paths["service"], "a" * 40, "b" * 40
            )
            paths["service"].write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "binary differs"):
                qualifier.verify_build(
                    manifest, config, paths["service"], "a" * 40, "b" * 40
                )
            paths["service"].unlink()
            paths["service"].symlink_to(paths["guest"])
            with self.assertRaisesRegex(ValueError, "regular file"):
                qualifier.verify_build(
                    manifest, config, paths["service"], "a" * 40, "b" * 40
                )

    def check_result(
        self, *, children="", count=1, metadata_update=None, fixture_update=None
    ):
        with tempfile.TemporaryDirectory() as temporary:
            junit = Path(temporary) / "junit.xml"
            case = f'<testcase name="{qualifier.CASE}">{children}</testcase>'
            junit.write_text(
                f"<testsuites><testsuite>{case * count}</testsuite></testsuites>"
            )
            metadata = {
                "tree_sha": "a" * 40,
                "lane": "trial_composition",
                "database_cleanup_complete": True,
                "minio_cleanup_complete": True,
            }
            fixture = {
                "schema_version": "workstream.terminal_systems_composition_evidence.v1",
                "provider_mode": "controlled",
                "guide_to_contribution_proven": False,
                "replay_additional_provider_calls": 0,
                "owned_runtime_resources_removed": True,
                "model_effects": [{}, {}, {}, {}],
                "trials": [{}, {}],
            }
            metadata.update(metadata_update or {})
            fixture.update(fixture_update or {})
            qualifier.verify_results(junit, metadata, fixture, "a" * 40)

    def test_exact_completed_case_is_required(self):
        self.check_result()
        for count in (0, 2):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.check_result(count=count)
        for child in ("<skipped/>", "<failure/>", "<error/>"):
            with self.subTest(child=child), self.assertRaises(ValueError):
                self.check_result(children=child)

    def test_storage_cleanup_and_exact_source_are_required(self):
        for changed in (
            {"database_cleanup_complete": False},
            {"minio_cleanup_complete": False},
            {"tree_sha": "b" * 40},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.check_result(metadata_update=changed)

    def test_runtime_cleanup_and_replay_are_required(self):
        for changed in (
            {"owned_runtime_resources_removed": False},
            {"replay_additional_provider_calls": 1},
            {"trials": []},
            {"model_effects": []},
            {"provider_mode": "live"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.check_result(fixture_update=changed)

    def test_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            qualifier.write_new(path, {"status": "failed"})
            with self.assertRaises(FileExistsError):
                qualifier.write_new(path, {"status": "passed"})
            self.assertEqual(json.loads(path.read_text()), {"status": "failed"})


class SmolVMInventoryTests(unittest.TestCase):
    def lock(self, root):
        root.mkdir(parents=True, exist_ok=True)
        lock = root / ".artifact-cache.lock"
        with lock.open("x") as output:
            os.fchmod(output.fileno(), 0o600)
        return lock

    def test_fresh_home_permits_only_valid_engine_sentinel_then_tracks_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "vms"
            before = smol_runtime.smol_vm_inventory(root)
            self.assertEqual(before, (set(), None))
            lock = self.lock(root)
            observed = smol_runtime.assert_smol_vm_inventory(root, before)
            self.assertEqual(
                observed, (set(), (lock.stat().st_dev, lock.stat().st_ino))
            )
            self.assertEqual(
                smol_runtime.assert_smol_vm_inventory(root, observed), observed
            )
            lock.rename(Path(temporary) / "retained-original-lock")
            self.lock(root)
            with self.assertRaisesRegex(AssertionError, "identity changed"):
                smol_runtime.assert_smol_vm_inventory(root, observed)

    def test_unexpected_file_and_vm_directory_still_break_exact_inventory(self):
        for name, directory in ((".unexpected.lock", False), ("ws-owned-vm", True)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "vms"
                self.lock(root)
                before = smol_runtime.smol_vm_inventory(root)
                if directory:
                    (root / name).mkdir()
                else:
                    (root / name).write_bytes(b"")
                self.assertEqual(smol_runtime.smol_vm_inventory(root)[0], {name})
                with self.assertRaisesRegex(
                    AssertionError, "execution children changed"
                ):
                    smol_runtime.assert_smol_vm_inventory(root, before)

    def test_invalid_cache_sentinel_is_never_excluded(self):
        for kind in (
            "content",
            "mode",
            "symlink",
            "dangling_symlink",
            "directory",
            "hardlink",
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "vms"
                lock = self.lock(root)
                if kind == "content":
                    lock.write_bytes(b"not a coordination sentinel")
                elif kind == "mode":
                    lock.chmod(0o644)
                elif kind in {"symlink", "dangling_symlink"}:
                    lock.unlink()
                    target = Path(temporary) / "other"
                    if kind == "symlink":
                        target.write_bytes(b"")
                        target.chmod(0o600)
                    lock.symlink_to(target)
                elif kind == "directory":
                    lock.unlink()
                    lock.mkdir(mode=0o600)
                else:
                    os.link(lock, Path(temporary) / "extra-link")
                with self.assertRaises(AssertionError):
                    smol_runtime.smol_vm_inventory(root)

    def test_wrong_owner_and_disappearing_observed_lock_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "vms"
            lock = self.lock(root)
            before = smol_runtime.smol_vm_inventory(root)
            expected_uid, expected_gid = os.geteuid(), os.getegid()
            for attribute, other in (
                ("geteuid", expected_uid + 1),
                ("getegid", expected_gid + 1),
            ):
                with (
                    self.subTest(attribute=attribute),
                    patch.object(smol_runtime.os, attribute, return_value=other),
                ):
                    with self.assertRaisesRegex(AssertionError, "custody changed"):
                        smol_runtime.smol_vm_inventory(root)
            lock.unlink()
            with self.assertRaisesRegex(AssertionError, "identity changed"):
                smol_runtime.assert_smol_vm_inventory(root, before)

    def test_existing_recovery_owner_uses_same_inventory_and_stable_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recovery = smol_recovery.NestedTrialRecovery("caller_disconnect")
            recovery.config = {"smol": {"home": str(root / "home")}}
            recovery.leases, recovery.groups, recovery.child_root = (
                root / "leases",
                root / "groups",
                root / "children",
            )
            for directory in (recovery.leases, recovery.groups, recovery.child_root):
                directory.mkdir()
            self.assertTrue(recovery.physical_clean())
            vms = root / "home/.cache/smolvm/vms"
            lock = self.lock(vms)
            self.assertTrue(recovery.physical_clean())
            (vms / "ws-owned-vm").mkdir()
            self.assertFalse(recovery.physical_clean())
            (vms / "ws-owned-vm").rmdir()
            lock.rename(root / "retained-original-lock")
            self.lock(vms)
            with self.assertRaisesRegex(AssertionError, "identity changed"):
                recovery.physical_clean()


if __name__ == "__main__":
    unittest.main()
