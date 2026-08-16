"""Tests for repository-wide active-state projection validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_active_state_projections import temporal_projection_failures


class ActiveStateProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_final_durable_values_pass(self) -> None:
        self._write(".agent-loop/CURRENT_STATE.md", "WS-EXAMPLE-001-01 is complete.\n")
        self._write(
            ".agent-loop/initiatives/WS-EXAMPLE-001-example/STATUS.md",
            "WS-EXAMPLE-001-01 is merged.\n",
        )
        self._write(
            ".agent-loop/initiatives/WS-EXAMPLE-001-example/CHUNK_MAP.md",
            "| `WS-EXAMPLE-001-02` | Later | Planned |\n",
        )
        self.assertEqual(temporal_projection_failures(self.root), [])

    def test_each_active_projection_type_is_scanned_case_insensitively(self) -> None:
        self._write(".agent-loop/CURRENT_STATE.md", "One is complete on merge.\n")
        self._write(
            ".agent-loop/initiatives/WS-ONE-001-one/STATUS.md",
            "Two is Planned on merge.\n",
        )
        self._write(
            ".agent-loop/initiatives/WS-TWO-001-two/CHUNK_MAP.md",
            "| Three | CANCELLED ON MERGE |\n",
        )
        failures = temporal_projection_failures(self.root)
        self.assertEqual(len(failures), 3)
        self.assertTrue(all(item.startswith("ACTIVE_STATE_TEMPORAL_PROJECTION:") for item in failures))

    def test_contracts_and_historical_reviews_are_not_active_projections(self) -> None:
        self._write(".agent-loop/CURRENT_STATE.md", "Current state is complete.\n")
        self._write(
            ".agent-loop/initiatives/WS-ONE-001-one/chunks/WS-ONE-001-01.md",
            "- Outcome on merge: `complete`\n",
        )
        self._write(
            ".agent-loop/initiatives/WS-ONE-001-one/reviews/review.md",
            "The change was complete on merge.\n",
        )
        self.assertEqual(temporal_projection_failures(self.root), [])


if __name__ == "__main__":
    unittest.main()
