"""Focused regression tests for the lightweight repository checks."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.check_markdown_links import local_target
from scripts.check_stale_artifact_contracts import phase_index
from scripts.check_stale_artifact_contracts import scan_text as scan_artifact_text
from scripts.check_stale_authorization_docs import scan_text as scan_authorization_text
from scripts.check_stale_workstream_wording import FORBIDDEN_PATTERNS
from scripts.check_stale_workstream_wording import forbidden_path_failures


class LightweightAgentGateTests(unittest.TestCase):
    """Keep the retained checks executable and cover their core parsing rules."""

    def test_markdown_link_target_classification(self) -> None:
        self.assertEqual(local_target("docs/guide.md#start"), "docs/guide.md")
        self.assertEqual(local_target("<docs/a file.md>"), "docs/a file.md")
        self.assertIsNone(local_target("https://example.com"))
        self.assertIsNone(local_target("#local-heading"))

    def test_tool_specific_agent_paths_are_rejected(self) -> None:
        failures = forbidden_path_failures(
            [Path(".claude/settings.json"), Path("docs/guide.md")]
        )
        self.assertEqual(len(failures), 1)
        self.assertIn(".claude/settings.json", failures[0])

    def test_stale_wording_pattern_rejects_legacy_name(self) -> None:
        self.assertTrue(
            any(
                pattern.search("task-production control " + "plane")
                for pattern in FORBIDDEN_PATTERNS
            )
        )

    def test_stale_authorization_rejects_noncanonical_api_prefix(self) -> None:
        failures = scan_authorization_text("docs/new-guide.md", "Call /v1/tasks.")
        self.assertIn("docs/new-guide.md:1: NON_CANONICAL_API_PREFIX", failures)

    def test_stale_artifact_rejects_reached_phase_term(self) -> None:
        failures = scan_artifact_text(
            "README.md", "Use S3" + "ArtifactStore.", "artifact_store_cutover"
        )
        self.assertIn("README.md:1: AMBIGUOUS_S3_ADAPTER_NAME", failures)

    def test_stale_artifact_rejects_unknown_phase(self) -> None:
        with self.assertRaises(ValueError):
            phase_index("unknown")

if __name__ == "__main__":
    unittest.main()
