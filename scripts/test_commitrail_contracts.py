from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_commitrail_records as gate


class CommitrailContractTests(unittest.TestCase):
    SNAPSHOT_BASE = "0000000000000000000000000000000000000000"
    SNAPSHOT_DIGEST = "6c841f7ba7c4b67f9541110c402ee871d012d173e361bbf8071207e6137e13a7"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self._write(
            ".commitrail/INDEX.md",
            "| Initiative | Durable disposition | Next |\n"
            "|---|---|---|\n"
            "| [WS-EXAMPLE-001](initiatives/WS-EXAMPLE-001/OVERVIEW.md) | Planned | Next |\n",
        )
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n\n- Disposition: Planned\n",
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _record(self, disposition: str = "Complete") -> str:
        return (
            "# WS-EXAMPLE-001-01 — Example\n\n"
            f"- Durable disposition: {disposition}\n"
            "- Intended merge outcome: Example completes.\n\n"
            "## Intent\nX\n## Bounded change\nX\n## Acceptance criteria\nX\n"
            "## Risk and review routing\nX\n## Evidence\nX\n"
        )

    def _validate(
        self,
        paths: list[str],
        *,
        comparison_base_ref: str | None = None,
    ) -> None:
        with patch.object(gate, "tracked_legacy_paths", return_value=[]):
            gate.validate(
                self.root,
                paths,
                comparison_base_ref=comparison_base_ref,
            )

    def test_valid_single_record_change(self) -> None:
        path = ".commitrail/initiatives/WS-EXAMPLE-001/WS-EXAMPLE-001-01.md"
        self._write(path, self._record())
        self._validate(["backend/app/example.py", path])

    def test_valid_multi_pr_overview_and_all_dispositions(self) -> None:
        for disposition in sorted(gate.DISPOSITIONS):
            self._write(
                ".commitrail/INDEX.md",
                "| Initiative | Durable disposition | Next |\n|---|---|---|\n"
                f"| WS-EXAMPLE-001 | {disposition} | Next |\n",
            )
            self._write(
                ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
                f"# Example\n\n- Disposition: {disposition}\n",
            )
            self._validate([])

    def test_missing_field_fails(self) -> None:
        path = ".commitrail/initiatives/WS-EXAMPLE-001/WS-EXAMPLE-001-01.md"
        self._write(path, self._record().replace("## Evidence", "## Proof"))
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate(["backend/app/example.py", path])

    def test_invalid_disposition_fails(self) -> None:
        path = ".commitrail/initiatives/WS-EXAMPLE-001/WS-EXAMPLE-001-01.md"
        self._write(path, self._record("In review"))
        with self.assertRaisesRegex(gate.CommitrailError, "DISPOSITION_INVALID"):
            self._validate(["backend/app/example.py", path])

    def test_transient_state_fails(self) -> None:
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n\n- Disposition: Planned\n- CI: pending\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "TRANSIENT_STATE"):
            self._validate([])

    def test_index_overview_mismatch_fails(self) -> None:
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n\n- Disposition: Complete\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "MISMATCH"):
            self._validate([])

    def test_implementation_requires_exactly_one_record(self) -> None:
        with self.assertRaisesRegex(gate.CommitrailError, "RECORD_REQUIRED"):
            self._validate(["backend/app/example.py"])

    def test_process_control_requires_exactly_one_record(self) -> None:
        for path in (
            ".agents/skills/security-review/SKILL.md",
            ".codex/agents/security-reviewer.toml",
            ".commitrail/INDEX.md",
            "AGENTS.md",
            "docs/engineering/commitrail.md",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(gate.CommitrailError, "RECORD_REQUIRED"):
                    self._validate([path])

    def test_every_index_row_uses_a_closed_disposition(self) -> None:
        self._write(
            ".commitrail/INDEX.md",
            "| Initiative | Durable disposition | Next |\n|---|---|---|\n"
            "| WS-EXAMPLE-001 | Planned | Next |\n"
            "| WS-OLD-001 | Complete plus commentary | None |\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "INDEX_DISPOSITION_INVALID"):
            self._validate([])

    def test_record_id_must_match_parent_initiative(self) -> None:
        path = ".commitrail/initiatives/WS-EXAMPLE-001/WS-OTHER-001-01.md"
        self._write(path, self._record())
        with self.assertRaisesRegex(gate.CommitrailError, "RECORD_OWNER_MISMATCH"):
            self._validate(["backend/app/example.py", path])

    def test_relocation_inventory_must_cover_the_exact_base_tree(self) -> None:
        self._write_snapshot_contract()

        def incomplete_base_tree(command: list[str], **kwargs: object) -> str:
            if "ls-tree" in command:
                return ".agent-loop/one.md\n.agent-loop/two.md\n"
            return self._snapshot_git(command, **kwargs)

        with (
            patch.object(gate, "run_checked", side_effect=incomplete_base_tree),
            self.assertRaisesRegex(gate.CommitrailError, "INVENTORY_INCOMPLETE"),
        ):
            self._validate([])

    def test_relocation_inventory_rejects_rebased_source_tree_drift(self) -> None:
        self._write_snapshot_contract()

        def rebased_tree(command: list[str], **kwargs: object) -> str:
            if "ls-tree" in command and "--name-only" not in command:
                blob = "2" * 40 if command[3] == "rebased-main" else "1" * 40
                return f"100644 blob {blob}\t.agent-loop/one.md\n"
            return self._snapshot_git(command, **kwargs)

        with (
            patch.object(gate, "run_checked", side_effect=rebased_tree),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
            self.assertRaisesRegex(gate.CommitrailError, "RELOCATION_BASE_DRIFT"),
        ):
            self._validate([], comparison_base_ref="rebased-main")

    def test_relocation_inventory_allows_post_cutover_empty_base(self) -> None:
        self._write_snapshot_contract()

        def post_cutover_tree(command: list[str], **kwargs: object) -> str:
            if "ls-tree" in command and "--name-only" not in command:
                if command[3] == "post-cutover-main":
                    return ""
                return (
                    "100644 blob 1111111111111111111111111111111111111111\t"
                    ".agent-loop/one.md\n"
                )
            return self._snapshot_git(command, **kwargs)

        with (
            patch.object(gate, "run_checked", side_effect=post_cutover_tree),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
        ):
            self._validate([], comparison_base_ref="post-cutover-main")

    def test_commissioned_cutover_requires_relocation_inventory(self) -> None:
        self._write(
            ".commitrail/initiatives/WS-ENG-009/OVERVIEW.md",
            "# Cutover\n\n- Disposition: Complete\n",
        )
        self._write(
            ".commitrail/INDEX.md",
            "| Initiative | Durable disposition | Next |\n|---|---|---|\n"
            "| WS-EXAMPLE-001 | Planned | Next |\n"
            "| WS-ENG-009 | Complete | None |\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "INVENTORY_MISSING"):
            self._validate([])

    def _write_snapshot_contract(self) -> None:
        self._write(
            ".commitrail/initiatives/WS-ENG-009/RELOCATION_INVENTORY.md",
            "# Inventory\n\nBase: `0000000000000000000000000000000000000000`.\n\n"
            "```text\nsource\\tdisposition\n.agent-loop/one.md\tLifted exactly\n```\n",
        )
        self._write(
            ".commitrail/initiatives/WS-ENG-009/PRE_CUTOVER_MANIFEST.tsv",
            "source\tdestination\tbase_blob_sha\n"
            ".agent-loop/one.md\t"
            ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md\t"
            "1111111111111111111111111111111111111111\n",
        )
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md", "exact\n"
        )

    @staticmethod
    def _snapshot_git(command: list[str], **_: object) -> str:
        if "ls-tree" in command:
            return ".agent-loop/one.md\n"
        if "ls-files" in command:
            return (
                "100644 1111111111111111111111111111111111111111 0\t"
                ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md\n"
            )
        if "rev-parse" in command:
            return "1111111111111111111111111111111111111111"
        if "hash-object" in command:
            return "1111111111111111111111111111111111111111"
        raise AssertionError(command)

    def test_pre_cutover_manifest_accepts_exact_destination(self) -> None:
        self._write_snapshot_contract()
        with (
            patch.object(gate, "run_checked", side_effect=self._snapshot_git),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
        ):
            self._validate([])

    def test_pre_cutover_manifest_rejects_missing_destination(self) -> None:
        self._write_snapshot_contract()
        (self.root / ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md").unlink()
        with (
            patch.object(gate, "run_checked", side_effect=self._snapshot_git),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
            self.assertRaisesRegex(gate.CommitrailError, "DESTINATIONS_INVALID"),
        ):
            self._validate([])

    def test_pre_cutover_manifest_rejects_modified_destination(self) -> None:
        self._write_snapshot_contract()

        def changed_blob(command: list[str], **kwargs: object) -> str:
            if "hash-object" in command:
                return "2222222222222222222222222222222222222222"
            return self._snapshot_git(command, **kwargs)

        with (
            patch.object(gate, "run_checked", side_effect=changed_blob),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
            self.assertRaisesRegex(gate.CommitrailError, "CONTENT_MISMATCH"),
        ):
            self._validate([])

    def test_pre_cutover_manifest_rejects_symlink_destination(self) -> None:
        self._write_snapshot_contract()
        destination = (
            self.root
            / ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md"
        )
        payload = self.root / "identical.md"
        payload.write_text("exact\n", encoding="utf-8")
        destination.unlink()
        destination.symlink_to(payload)
        with (
            patch.object(gate, "run_checked", side_effect=self._snapshot_git),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
            self.assertRaisesRegex(gate.CommitrailError, "DESTINATION_NOT_REGULAR"),
        ):
            self._validate([])

    def test_pre_cutover_manifest_rejects_extra_destination(self) -> None:
        self._write_snapshot_contract()
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/extra.md", "extra\n"
        )
        with (
            patch.object(gate, "run_checked", side_effect=self._snapshot_git),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
            self.assertRaisesRegex(gate.CommitrailError, "DESTINATIONS_INVALID"),
        ):
            self._validate([])

    def test_pre_cutover_manifest_rejects_row_and_file_deletion(self) -> None:
        self._write_snapshot_contract()
        (self.root / ".commitrail/initiatives/WS-EXAMPLE-001/pre-cutover/one.md").unlink()
        self._write(
            ".commitrail/initiatives/WS-ENG-009/PRE_CUTOVER_MANIFEST.tsv",
            "source\tdestination\tbase_blob_sha\n",
        )
        with (
            patch.object(gate, "run_checked", side_effect=self._snapshot_git),
            patch.dict(
                gate.PRE_CUTOVER_MANIFEST_DIGESTS,
                {self.SNAPSHOT_BASE: self.SNAPSHOT_DIGEST},
            ),
            self.assertRaisesRegex(gate.CommitrailError, "MANIFEST_CHANGED"),
        ):
            self._validate([])

    def test_legacy_path_fails(self) -> None:
        with patch.object(gate, "tracked_legacy_paths", return_value=[".agent-loop/x"]):
            with self.assertRaisesRegex(gate.CommitrailError, "LEGACY_PATH"):
                gate.validate(self.root, [])


if __name__ == "__main__":
    unittest.main()
