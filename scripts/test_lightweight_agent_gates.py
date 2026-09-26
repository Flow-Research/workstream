"""Focused regression tests for the lightweight repository checks."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.check_markdown_links import local_target
from scripts.check_markdown_links import should_check_links
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

    def test_exact_pre_cutover_records_are_not_rewritten_for_old_links(self) -> None:
        self.assertFalse(
            should_check_links(Path(".commitrail/initiatives/WS-AUTH-001/pre-cutover/STATUS.md"))
        )
        self.assertTrue(should_check_links(Path(".commitrail/initiatives/WS-AUTH-001/OVERVIEW.md")))

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
        self.assertEqual(len(re.findall(r"(?m)^      matrix:$", workflow)), 1)
        matrix = re.search(r"(?m)^      matrix:\n((?: {8,}[^\n]*\n|\n)+)", workflow)
        self.assertIsNotNone(matrix)
        self.assertEqual(
            matrix[1].strip(),
            "lane:\n"
            "          - shared_foundations_a\n"
            "          - shared_foundations_b\n"
            "          - schema_contracts\n"
            "          - project_lifecycle_a\n"
            "          - project_lifecycle_b\n"
            "          - project_lifecycle_c\n"
            "          - task_lifecycle_a\n"
            "          - task_lifecycle_b\n"
            "          - task_lifecycle_c",
        )
        self.assertIn(
            "  test:\n    if: ${{ always() }}\n"
            "    needs: [auth-boundary-preflight, lanes, minio-image]", workflow
        )
        self.assertIn("Require preflight and every semantic lane", workflow)
        self.assertIn("python -m scripts.merge_test_lane_evidence", workflow)
        self.assertIn("scripts/validate_test_lane_evidence.py", workflow)
        self.assertIn(
            "WORKSTREAM_TEST_MINIO_ENDPOINT: http://127.0.0.1:9000",
            workflow,
        )
        self.assertIn("include-hidden-files: true", workflow)
        self.assertIn("coverage report --precision=2", workflow)
        self.assertNotIn("fail-under", workflow)
        self.assertNotIn("pull_request_review:", agent_gates)
        self.assertNotIn("--require-pr-approval", agent_gates)
        self.assertNotIn("pull-requests:", agent_gates)
        self.assertNotIn("types: [opened, synchronize, reopened, edited]", agent_gates)
        self.assertIn("types: [opened, synchronize, reopened]", agent_gates)
        self.assertIn("group: agent-gates-${{ github.event.pull_request.number }}", agent_gates)
        self.assertIn("cancel-in-progress: true", agent_gates)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha }}", agent_gates)
        self.assertNotIn("check_guide_extractor_dependencies.py", agent_gates)
        self.assertIn("python3 scripts/check_commitrail_records.py", agent_gates)
        self.assertNotIn("python3 scripts/check_chunk_state_sync.py", agent_gates)
        self.assertIn("scripts.test_commitrail_contracts", agent_gates)
        self.assertIn("scripts.test_commitrail_contribution_paths", agent_gates)
        self.assertIn('WORKSTREAM_BASE_SHA: ${{ github.event.pull_request.base.sha }}', agent_gates)
        self.assertNotIn("scripts.test_chunk_state_sync", agent_gates)
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

    def test_minio_source_image_is_built_once_and_shared_without_bypassing_lanes(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        image_job = workflow.split("\n  minio-image:\n", 1)[1].split("\n  auth-boundary-preflight:\n", 1)[0]
        self.assertEqual(workflow.count('docker build --tag "${MINIO_IMAGE}" docker/minio'), 1)
        self.assertNotIn("quay.io/minio", workflow)
        self.assertIn("hashFiles('docker/minio/**')", image_job)
        self.assertIn(
            "key: minio-source-v1-${{ github.sha }}-${{ runner.os }}-${{ runner.arch }}-",
            image_job,
        )
        self.assertNotIn("restore-keys:", image_job)
        self.assertIn("minio-source-${GITHUB_SHA}-${GITHUB_RUN_ATTEMPT}", image_job)
        self.assertIn("artifact: ${{ steps.identity.outputs.artifact }}", image_job)
        self.assertIn("sha256sum minio.tar > minio.tar.sha256", image_job)
        self.assertIn("/minio/health/live", image_job)
        self.assertIn("if-no-files-found: error", image_job)
        self.assertNotIn("continue-on-error", image_job)
        for name, end in (("lanes", "test"), ("test", None)):
            job = workflow.split(f"\n  {name}:\n", 1)[1]
            if end:
                job = job.split(f"\n  {end}:\n", 1)[0]
            self.assertIn("name: ${{ needs.minio-image.outputs.artifact }}", job)
            self.assertIn("sha256sum --check minio.tar.sha256", job)
            self.assertIn('docker load --input "${RUNNER_TEMP}/minio-image/minio.tar"', job)
            self.assertIn('"${MINIO_IMAGE}" server /data --address :9000', job)

    def test_parallel_preflight_and_lanes_fail_closed_at_fan_in(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        lanes = workflow.split("\n  lanes:\n", 1)[1].split("\n  test:\n", 1)[0]
        self.assertRegex(lanes, r"(?m)^    needs: minio-image$")
        self.assertNotIn("needs: auth-boundary-preflight", lanes)
        step = workflow.split(
            "      - name: Require preflight and every semantic lane\n", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("if: ${{ always() }}", step)
        self.assertIn("PREFLIGHT_RESULT: ${{ needs.auth-boundary-preflight.result }}", step)
        self.assertIn("LANES_RESULT: ${{ needs.lanes.result }}", step)
        guard = re.search(r"(?m)^        run: (.+)$", step)
        self.assertIsNotNone(guard)
        for preflight in ("success", "failure", "cancelled", "skipped", "", "unknown"):
            for lanes_result in ("success", "failure", "cancelled", "skipped", "", "unknown"):
                with self.subTest(preflight=preflight, lanes=lanes_result):
                    result = subprocess.run(
                        ["bash", "-e", "-c", guard[1]],
                        env={"PREFLIGHT_RESULT": preflight, "LANES_RESULT": lanes_result},
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode == 0,
                        preflight == lanes_result == "success",
                    )

    def test_postgres_storage_is_bounded_and_disk_contracts_remain(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        lane_service = workflow.split("\n  lanes:\n", 1)[1].split("\n    steps:", 1)[0]
        aggregate_service = workflow.split("\n  test:\n", 1)[1].split("\n    steps:", 1)[0]
        self.assertIn(
            "${{ matrix.lane != 'schema_contracts' && "
            "'--tmpfs /var/lib/postgresql/data:rw,nosuid,nodev,noexec,size=2147483648' || '' }}",
            lane_service,
        )
        self.assertNotIn("--tmpfs", aggregate_service)
        self.assertLess(
            workflow.index("- name: Verify PostgreSQL CI storage and write settings"),
            workflow.index("- name: Execute semantic lane"),
        )

    def test_postgres_storage_guard_rejects_wrong_mounts_and_write_settings(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        step = workflow.split(
            "      - name: Verify PostgreSQL CI storage and write settings\n", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("POSTGRES_CONTAINER: ${{ job.services.postgres.id }}", step)
        self.assertIn(
            "EXPECTED_PG_STORAGE: ${{ matrix.lane == 'schema_contracts' && 'disk' || 'tmpfs' }}",
            step,
        )
        guard = textwrap.dedent(step.split("        run: |\n", 1)[1])
        settings = "on|on|on|/var/lib/postgresql/data"
        memory = "tmpfs 524288 4096"
        disk = "ext2/ext3 524288 4096"
        cases = [
            ("tmpfs", memory, settings, "0", True),
            ("disk", disk, settings, "0", True),
            ("tmpfs", disk, settings, "0", False),
            ("disk", memory, settings, "0", False),
            ("tmpfs", "tmpfs 524287 4096", settings, "0", False),
            ("tmpfs", "tmpfs 524289 4096", settings, "0", False),
            ("tmpfs", "", settings, "0", False),
            ("tmpfs", memory, settings.replace("/data", "/elsewhere"), "0", False),
            ("unknown", memory, settings, "0", False),
            ("tmpfs", memory, settings, "1", False),
        ]
        for index in range(3):
            values = settings.split("|")
            values[index] = "off"
            cases.append(("tmpfs", memory, "|".join(values), "0", False))
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            docker.write_text(
                '#!/bin/sh\n[ "$TEST_DOCKER_STATUS" = 0 ] || exit 1\n'
                '[ "$1" = exec ] && [ "$2" = probe ] || exit 2\n'
                'case "$3" in\nstat) printf "%s\\n" "$TEST_STAT";;\n'
                'psql) printf "%s\\n" "$TEST_SETTINGS";;\n*) exit 2;;\nesac\n',
                encoding="utf-8",
            )
            docker.chmod(0o755)
            for mode, stat, configuration, status, allowed in cases:
                with self.subTest(mode=mode, stat=stat, configuration=configuration, status=status):
                    result = subprocess.run(
                        ["bash", "-e", "-c", guard],
                        env={
                            "PATH": directory + os.pathsep + os.defpath,
                            "POSTGRES_CONTAINER": "probe",
                            "EXPECTED_PG_STORAGE": mode,
                            "TEST_STAT": stat,
                            "TEST_SETTINGS": configuration,
                            "TEST_DOCKER_STATUS": status,
                        },
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode == 0, allowed, result.stderr.decode())

    def test_retired_behavior_mutation_gate_stays_out_of_required_ci(self) -> None:
        backend = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")

        self.assertFalse(Path(".github/workflows/mutation-pilot.yml").exists())
        self.assertNotIn("mutation-pilot", backend)

if __name__ == "__main__":
    unittest.main()
