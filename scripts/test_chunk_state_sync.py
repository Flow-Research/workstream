"""Tests for atomic chunk state validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_chunk_state_sync as gate


class ChunkStateSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.initiative = ".agent-loop/initiatives/WS-EXAMPLE-001-example"
        self.chunk = f"{self.initiative}/chunks/WS-EXAMPLE-001-01-example.md"
        self.paths = [
            "backend/app/example.py",
            self.chunk,
            f"{self.initiative}/CHUNK_MAP.md",
            f"{self.initiative}/STATUS.md",
            ".agent-loop/CURRENT_STATE.md",
        ]
        self._write(self.chunk, "## Merge state\n\n- Outcome on merge: `complete`\n")
        self._write(
            f"{self.initiative}/CHUNK_MAP.md",
            "| `WS-EXAMPLE-001-01` | Example | L1 | Complete |\n",
        )
        self._write(
            f"{self.initiative}/STATUS.md",
            "WS-EXAMPLE-001-01 is complete.\n",
        )
        self._write(
            ".agent-loop/CURRENT_STATE.md",
            "WS-EXAMPLE-001-01 is complete.\n",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write(self, relative_path: str, text: str) -> None:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _validate(self, paths: list[str] | None = None) -> None:
        with patch.object(gate, "ROOT", self.root):
            gate.validate(self.paths if paths is None else paths)

    def test_complete_chunk_and_all_projections_pass(self) -> None:
        self._validate()

    def test_implementation_without_contract_fails(self) -> None:
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_CONTRACT_MISSING"):
            self._validate(["backend/app/example.py"])

    def test_multiple_chunk_contracts_fail(self) -> None:
        other = f"{self.initiative}/chunks/WS-EXAMPLE-001-02-other.md"
        self._write(other, "## Merge state\n\n- Outcome on merge: `complete`\n")
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_MULTIPLE_CONTRACTS"):
            self._validate([*self.paths, other])

    def test_planning_pr_may_define_multiple_planned_chunks(self) -> None:
        second = f"{self.initiative}/chunks/WS-EXAMPLE-001-02-other.md"
        self._write(self.chunk, "## Merge state\n\n- Outcome on merge: `planned`\n")
        self._write(second, "## Merge state\n\n- Outcome on merge: `planned`\n")
        self._write(
            f"{self.initiative}/CHUNK_MAP.md",
            "| `WS-EXAMPLE-001-01` | One | L1 | Planned |\n"
            "| `WS-EXAMPLE-001-02` | Two | L1 | Planned |\n",
        )
        self._write(
            f"{self.initiative}/STATUS.md",
            "WS-EXAMPLE-001-01 and WS-EXAMPLE-001-02 are planned.\n",
        )
        self._write(
            ".agent-loop/CURRENT_STATE.md",
            "WS-EXAMPLE-001-01 and WS-EXAMPLE-001-02 are planned.\n",
        )
        planning_paths = [path for path in self.paths if not path.startswith("backend/")]
        self._validate([*planning_paths, second])

    def test_missing_projection_fails(self) -> None:
        paths = [path for path in self.paths if not path.endswith("STATUS.md")]
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_PROJECTION_MISSING"):
            self._validate(paths)

    def test_missing_merge_outcome_fails(self) -> None:
        self._write(self.chunk, "# Chunk Contract\n")
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_OUTCOME_INVALID"):
            self._validate()

    def test_duplicate_merge_outcome_fails(self) -> None:
        self._write(
            self.chunk,
            "## Merge state\n\n"
            "- Outcome on merge: `complete`\n"
            "- Outcome on merge: `cancelled`\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_OUTCOME_INVALID"):
            self._validate()

    def test_outcome_outside_merge_state_fails(self) -> None:
        self._write(self.chunk, "## Notes\n\n- Outcome on merge: `complete`\n")
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_OUTCOME_INVALID"):
            self._validate()

    def test_outcome_must_share_projection_line_with_chunk(self) -> None:
        self._write(
            f"{self.initiative}/STATUS.md",
            "WS-EXAMPLE-001-01 remains active.\nAnother chunk is complete.\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_OUTCOME_MISMATCH"):
            self._validate()

    def test_outcome_substring_does_not_pass(self) -> None:
        self._write(
            f"{self.initiative}/CHUNK_MAP.md",
            "| `WS-EXAMPLE-001-01` | Example | L1 | Incomplete |\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_MAP_OUTCOME_MISMATCH"):
            self._validate()

    def test_negated_outcome_does_not_pass(self) -> None:
        self._write(
            f"{self.initiative}/STATUS.md",
            "WS-EXAMPLE-001-01 is not complete.\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_OUTCOME_MISMATCH"):
            self._validate()

    def test_longer_chunk_identifier_does_not_match(self) -> None:
        self._write(
            f"{self.initiative}/STATUS.md",
            "WS-EXAMPLE-001-010 is complete.\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_ID_MISSING"):
            self._validate()

    def test_complete_chunk_cannot_remain_in_review(self) -> None:
        self._write(
            f"{self.initiative}/CHUNK_MAP.md",
            "| `WS-EXAMPLE-001-01` | Example | L1 | Complete; in review |\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_REVIEW_WORDING"):
            self._validate()

    def test_chunk_map_cannot_land_temporal_merge_state(self) -> None:
        self._write(
            f"{self.initiative}/CHUNK_MAP.md",
            "| `WS-EXAMPLE-001-01` | Example | L1 | Complete on merge |\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_TEMPORAL_PROJECTION"):
            self._validate()

    def test_status_cannot_land_temporal_merge_state(self) -> None:
        self._write(
            f"{self.initiative}/STATUS.md",
            "WS-EXAMPLE-001-01 is complete on merge.\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_TEMPORAL_PROJECTION"):
            self._validate()

    def test_current_state_cannot_land_temporal_merge_state(self) -> None:
        self._write(
            ".agent-loop/CURRENT_STATE.md",
            "WS-EXAMPLE-001-01 is complete on merge.\n",
        )
        with self.assertRaisesRegex(gate.ChunkStateError, "CHUNK_STATE_TEMPORAL_PROJECTION"):
            self._validate()

    def test_planning_outcome_is_supported(self) -> None:
        self._write(self.chunk, "## Merge state\n\n- Outcome on merge: `planned`\n")
        self._write(
            f"{self.initiative}/CHUNK_MAP.md",
            "| `WS-EXAMPLE-001-01` | Example | L1 | Planned |\n",
        )
        self._write(f"{self.initiative}/STATUS.md", "WS-EXAMPLE-001-01 is planned.\n")
        self._write(".agent-loop/CURRENT_STATE.md", "WS-EXAMPLE-001-01 is planned.\n")
        self._validate()

    def test_documentation_only_change_needs_no_chunk_contract(self) -> None:
        self._validate(["README.md"])


if __name__ == "__main__":
    unittest.main()
