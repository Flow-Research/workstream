"""Tests for repository-wide active-state projection validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_active_state_projections import temporal_projection_failures


class ActiveStateProjectionTests(unittest.TestCase):
    """Verify temporal wording cannot survive in active state projections."""

    def setUp(self) -> None:
        """Create an isolated repository-shaped test root."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        """Remove the isolated test root."""
        self.temporary_directory.cleanup()

    def _write(self, relative: str, text: str) -> None:
        """Write one fixture file beneath the isolated root."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_final_durable_values_pass(self) -> None:
        """Accept durable final values in every active projection type."""
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
        """Reject temporal wording regardless of projection type or case."""
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

    def test_equivalent_temporal_merge_phrases_are_rejected(self) -> None:
        """Reject temporal labels and prose beyond a fixed status vocabulary."""
        self._write(".agent-loop/CURRENT_STATE.md", "Outcome on merge: complete.\n")
        self._write(
            ".agent-loop/initiatives/WS-ONE-001-one/CHUNK_MAP.md",
            "| Plan | Planning contract lands on merge |\n",
        )
        failures = temporal_projection_failures(self.root)
        self.assertEqual(len(failures), 2)

    def test_contracts_and_historical_reviews_are_not_active_projections(self) -> None:
        """Exclude contracts and historical evidence from active-state scans."""
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
