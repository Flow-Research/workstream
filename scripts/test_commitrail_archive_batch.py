"""Focused regression proof for batched Commitrail archive validation."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_commitrail_records as gate


class CommitrailArchiveBatchTests(unittest.TestCase):
    SNAPSHOT_BASE = "0000000000000000000000000000000000000000"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, path: str, text: str) -> None:
        """Write text to a file relative to the test root directory."""
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_pre_cutover_object_checks_are_batched(self) -> None:
        """Verify that pre-cutover destination validation batches git hash-object calls."""
        self._write(
            ".commitrail/initiatives/WS-ENG-009/RELOCATION_INVENTORY.md",
            "# Inventory\n\nBase: `0000000000000000000000000000000000000000`.\n\n"
            "```text\nsource\\tdisposition\n"
            ".agent-loop/one.md\tLifted exactly\n"
            ".agent-loop/two.md\tLifted exactly\n```\n",
        )
        manifest_relative = (
            ".commitrail/initiatives/WS-ENG-009/PRE_CUTOVER_MANIFEST.tsv"
        )
        self._write(
            manifest_relative,
            "source\tdestination\tbase_blob_sha\n"
            ".agent-loop/one.md\t"
            ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md\t"
            "1111111111111111111111111111111111111111\n"
            ".agent-loop/two.md\t"
            ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/two.md\t"
            "2222222222222222222222222222222222222222\n",
        )
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md", "one\n"
        )
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/two.md", "two\n"
        )
        digest = hashlib.sha256(
            (self.root / manifest_relative).read_bytes()
        ).hexdigest()
        commands: list[list[str]] = []

        def batch_git(command: list[str], **_: object) -> str:
            commands.append(command)
            if "ls-tree" in command:
                return (
                    "100644 blob 1111111111111111111111111111111111111111\t"
                    ".agent-loop/one.md\n"
                    "100644 blob 2222222222222222222222222222222222222222\t"
                    ".agent-loop/two.md\n"
                )
            if "ls-files" in command:
                return (
                    "100644 1111111111111111111111111111111111111111 0\t"
                    ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md\n"
                    "100644 2222222222222222222222222222222222222222 0\t"
                    ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/two.md\n"
                )
            if "hash-object" in command:
                self.assertEqual(
                    command,
                    [
                        "git",
                        "hash-object",
                        "--",
                        ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md",
                        ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/two.md",
                    ],
                )
                return (
                    "1111111111111111111111111111111111111111\n"
                    "2222222222222222222222222222222222222222\n"
                )
            raise AssertionError(command)

        with (
            patch.object(gate, "run_checked", side_effect=batch_git),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: digest},
            ),
        ):
            gate._validate_relocation_inventory(self.root)

        self.assertEqual(sum("ls-tree" in command for command in commands), 1)
        self.assertEqual(sum("ls-files" in command for command in commands), 1)
        self.assertEqual(sum("hash-object" in command for command in commands), 1)
        self.assertFalse(any("rev-parse" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
