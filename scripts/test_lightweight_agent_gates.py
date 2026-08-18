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
        failures = forbidden_path_failures([Path(".claude/settings.json"), Path("docs/guide.md")])
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

    def test_stale_artifact_rejects_legacy_guide_content_identity(self) -> None:
        failures = scan_artifact_text(
            "backend/app/modules/projects/example.py",
            "Caller supplied content_" + "cid.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/modules/projects/example.py:1: LEGACY_GUIDE_CONTENT_CID",
            failures,
        )

    def test_stale_artifact_rejects_legacy_guide_durable_ref(self) -> None:
        failures = scan_artifact_text(
            "backend/app/modules/projects/example.py",
            "Caller supplied durable_" + "ref.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/modules/projects/example.py:1: LEGACY_GUIDE_DURABLE_REF",
            failures,
        )
        interface_failures = scan_artifact_text(
            "backend/app/interfaces/project_agents.py",
            "Caller supplied durable_" + "ref.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/interfaces/project_agents.py:1: LEGACY_GUIDE_DURABLE_REF",
            interface_failures,
        )

    def test_stale_artifact_rejects_legacy_guide_content_hash(self) -> None:
        failures = scan_artifact_text(
            "backend/app/modules/projects/example.py",
            "Caller supplied content_" + "hash.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/modules/projects/example.py:1: LEGACY_GUIDE_CONTENT_HASH",
            failures,
        )
        interface_failures = scan_artifact_text(
            "backend/app/interfaces/project_agents.py",
            "Caller supplied content_" + "hash.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/interfaces/project_agents.py:1: LEGACY_GUIDE_CONTENT_HASH",
            interface_failures,
        )

    def test_stale_artifact_rejects_unknown_phase(self) -> None:
        with self.assertRaises(ValueError):
            phase_index("unknown")

    def test_backend_uses_distributed_semantic_lanes_and_stable_fan_in(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        agent_gates = Path(".github/workflows/agent-gates.yml").read_text(encoding="utf-8")
        gate_requirements = Path(".github/requirements/agent-gates.txt").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("pull_request_review:", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertIn("matrix:\n        lane:", workflow)
        self.assertNotIn("          - shared_foundations\n", workflow)
        self.assertEqual(workflow.count("          - shared_foundations_a\n"), 1)
        self.assertEqual(workflow.count("          - shared_foundations_b\n"), 1)
        self.assertEqual(workflow.count("          - schema_contracts_a"), 1)
        self.assertEqual(workflow.count("          - schema_contracts_b"), 1)
        self.assertEqual(workflow.count("          - schema_contracts_c"), 1)
        self.assertIn("  test:\n    if: ${{ always() }}\n    needs: lanes", workflow)
        self.assertIn("Require every semantic lane", workflow)
        self.assertIn("python -m scripts.merge_test_lane_evidence", workflow)
        self.assertIn("scripts/validate_test_lane_evidence.py", workflow)
        self.assertIn(
            "WORKSTREAM_TEST_MINIO_ENDPOINT: http://127.0.0.1:9000",
            workflow,
        )
        self.assertIn("include-hidden-files: true", workflow)
        self.assertIn("coverage report --precision=2 --fail-under=78", workflow)
        self.assertGreaterEqual(workflow.count("--fail-under=90"), 10)
        self.assertNotIn("pull_request_review:", agent_gates)
        self.assertNotIn("--require-pr-approval", agent_gates)
        self.assertNotIn("pull-requests:", agent_gates)
        self.assertNotIn("types: [opened, synchronize, reopened, edited]", agent_gates)
        self.assertIn("types: [opened, synchronize, reopened]", agent_gates)
        self.assertIn("group: agent-gates-${{ github.event.pull_request.number }}", agent_gates)
        self.assertIn("cancel-in-progress: true", agent_gates)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha }}", agent_gates)
        self.assertIn(
            "run: python3 backend/scripts/check_guide_extractor_dependencies.py",
            agent_gates,
        )
        self.assertIn("python3 scripts/check_chunk_state_sync.py", agent_gates)
        self.assertIn('WORKSTREAM_BASE_SHA: ${{ github.event.pull_request.base.sha }}', agent_gates)
        self.assertIn("scripts.test_chunk_state_sync", agent_gates)
        self.assertIn("--require-hashes", agent_gates)
        self.assertIn("-r .github/requirements/agent-gates.txt", agent_gates)
        for package in (
            "attrs",
            "jsonschema",
            "jsonschema-specifications",
            "referencing",
            "rpds-py",
            "typing-extensions",
        ):
            with self.subTest(package=package):
                self.assertRegex(
                    gate_requirements,
                    rf"(?m)^{package}==[^ ]+ \\\n    --hash=sha256:[0-9a-f]{{64}}$",
                )

    def test_retired_behavior_mutation_gate_stays_out_of_required_ci(self) -> None:
        backend = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")

        self.assertFalse(Path(".github/workflows/mutation-pilot.yml").exists())
        self.assertNotIn("mutation-pilot", backend)

if __name__ == "__main__":
    unittest.main()
