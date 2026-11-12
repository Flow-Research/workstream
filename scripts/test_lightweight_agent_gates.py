"""Focused regression tests for the lightweight repository checks."""

from __future__ import annotations

import json
import os
import re
import shlex
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

    def test_cli_minio_retry_binds_successful_producer_not_consumer_attempt(self) -> None:
        workflow = Path(".github/workflows/cli.yml").read_text(encoding="utf-8")
        step = workflow.split("      - name: Bind checked-out source\n", 1)[1].split("\n      - ", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        guard = script[script.index('if ! [[ "${MINIO_PRODUCER_ATTEMPT}"'):]
        head = "a" * 40
        for producer, consumer, artifact, success in (
            ("1", "1", f"minio-source-{head}-1", True),
            ("1", "2", f"minio-source-{head}-1", True),
            ("2", "2", f"minio-source-{head}-2", True),
            ("3", "2", f"minio-source-{head}-3", False),
            ("1", "2", f"minio-source-{head}-2", False),
            ("1", "2", "minio-source-foreign-1", False),
            ("0", "2", f"minio-source-{head}-0", False),
            ("", "2", f"minio-source-{head}-1", False),
        ):
            with self.subTest(producer=producer, consumer=consumer, artifact=artifact):
                result = subprocess.run(
                    ["bash", "-eu", "-c", guard], capture_output=True, check=False,
                    env={"GITHUB_SHA": head, "GITHUB_RUN_ATTEMPT": consumer,
                         "MINIO_PRODUCER_ATTEMPT": producer, "MINIO_ARTIFACT": artifact},
                )
                self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_mcp_has_one_callable_owner_and_required_backend_fan_in(self) -> None:
        workflow = Path(".github/workflows/mcp.yml").read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_call:\n", workflow)
        self.assertNotIn("  pull_request:\n", workflow)
        self.assertNotIn("  push:\n", workflow)
        backend = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        self.assertEqual(backend.count("uses: ./.github/workflows/mcp.yml"), 1)
        self.assertIn('require_expected "${MCP_EXPECTED}" "${MCP_RESULT}"', backend)

    def test_mcp_backend_contract_uses_the_frozen_lock_and_propagates_failure(self) -> None:
        workflow = Path(".github/workflows/mcp.yml").read_text(encoding="utf-8")

        def step(name: str) -> str:
            body = workflow.split("      - name: " + name + "\n", 1)[1]
            return body.split("\n      - ", 1)[0]

        install = step("Install backend and adapter test environments")
        self.assertIn('python -m pip install "uv==0.10.7"', install)
        self.assertIn("uv lock --check --project backend", install)
        self.assertIn(
            "uv sync --frozen --extra agents --extra dev --project backend", install
        )
        self.assertNotIn('pip install -e "./backend', install)
        openapi = step("Compare selected OpenAPI contract")
        self.assertIn(
            'WORKSTREAM_MCP_OPENAPI_COMMAND="uv run --frozen python -c ', openapi,
        )
        runtime = step("Run real isolated API-to-MCP lifecycle parity")
        self.assertIn("working-directory: backend", runtime)
        script = textwrap.dedent(runtime.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            calls = scratch / "calls.jsonl"
            fake_uv = scratch / "uv"
            fake_uv.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['MCP_PROBE_CALLS'], 'a') as output:\n"
                "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "raise SystemExit(int(os.environ['MCP_PROBE_EXIT']))\n",
                encoding="utf-8",
            )
            fake_uv.chmod(0o700)
            for code in (0, 1, 124):
                with self.subTest(exit_code=code):
                    calls.unlink(missing_ok=True)
                    result = subprocess.run(
                        ["bash", "-eu", "-c", script],
                        cwd="backend", capture_output=True, text=True, check=False,
                        env=os.environ | {
                            "PATH": directory + os.pathsep + os.environ["PATH"],
                            "RUNNER_TEMP": directory,
                            "MCP_PROBE_CALLS": str(calls),
                            "MCP_PROBE_EXIT": str(code),
                        },
                    )
                    self.assertEqual(result.returncode, code, result.stderr)
                    actual = [json.loads(line) for line in calls.read_text().splitlines()]
                    suites = (
                        "test_profile_flow",
                        "test_access_reads",
                        "test_admin_grants",
                        "test_actor_lifecycle",
                        "test_projects",
                        "test_project_grants",
                        "test_guides",
                        "test_policies",
                    ) if code == 0 else ("test_profile_flow",)
                    expected = [
                        [
                            "run", "--frozen", "python", "scripts/run_isolated_tests.py",
                            "--metadata-json", str(scratch / f"workstream-mcp-{suite}-evidence.json"),
                            "--timeout-seconds", "240", "--",
                            "uv", "run", "--frozen", "--project", "../mcp_server",
                            "python", "-m", "pytest", "-q",
                            f"../mcp_server/tests/integration/{suite}.py",
                        ]
                        for suite in suites
                    ]
                    self.assertEqual(actual, expected)

    def test_cli_full_contract_preserves_failure_and_timeout_exits(self) -> None:
        workflow = Path(".github/workflows/cli.yml").read_text(encoding="utf-8")
        names = (
            "Exercise built CLI against task HTTP and local file boundaries",
            "Exercise native terminal HTTP and proof contracts",
            "Exercise existing guide HTTP contracts",
            "Exercise existing native guide API callers",
            "Exercise existing native CLI self-service caller",
            "Exercise complete native CLI batch journey",
        )
        scripts = []
        for name in names:
            step = workflow.split("      - name: " + name + "\n", 1)[1].split("\n      - ", 1)[0]
            script = textwrap.dedent(step.split("        run: |\n", 1)[1])
            self.assertIn("--timeout-seconds 300", script)
            self.assertIn(
                "uv run --frozen python scripts/run_isolated_tests.py",
                script,
            )
            self.assertNotIn("|| true", script)
            if name == "Exercise existing guide HTTP contracts":
                self.assertIn(
                    "guide_files+=(../cli/tests/integration/test_task_guide_http.py)",
                    script,
                )
            scripts.append(script)
            for exit_code in (0, 1, 124):
                with self.subTest(step=name, exit_code=exit_code):
                    result = subprocess.run(
                        [
                            "bash",
                            "-e",
                            "-c",
                            "uv() { shift 2; \"$@\"; }\n"
                            f"python() {{ return {exit_code}; }}\n"
                            + script,
                        ],
                        cwd="backend",
                        env=os.environ | {"RUNNER_TEMP": tempfile.gettempdir()},
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(result.returncode, exit_code, result.stderr)
        runner_prefix = [
            "uv", "run", "--frozen", "python", "scripts/run_isolated_tests.py",
        ]
        pytest_prefix = [
            "--timeout-seconds", "300", "--", "uv", "run", "--frozen", "python",
            "-m", "pytest", "-q",
        ]
        expected_runners = (
            [
                *runner_prefix,
                "--metadata-json", "${RUNNER_TEMP}/workstream-cli-isolation.json",
                *pytest_prefix,
                "../cli/tests/integration",
                "--ignore-glob=../cli/tests/integration/*_public_api.py",
                "--ignore-glob=../cli/tests/integration/test_guide*.py",
                "--ignore=../cli/tests/integration/test_public_self_service.py",
                "--ignore=../cli/tests/integration/test_task_guide_http.py",
                "--ignore=../cli/tests/integration/test_tui_http.py",
                "--ignore=../cli/tests/integration/test_tui_native_proof.py",
            ],
            [
                *runner_prefix,
                "--metadata-json", "${RUNNER_TEMP}/workstream-cli-tui-isolation.json",
                *pytest_prefix,
                "../cli/tests/integration/test_tui_http.py",
                "../cli/tests/integration/test_tui_native_proof.py",
            ],
            [
                *runner_prefix,
                "--metadata-json", "${RUNNER_TEMP}/workstream-cli-guide-isolation.json",
                *pytest_prefix, "${guide_files[@]}",
            ],
            [
                *runner_prefix,
                "--metadata-json", "${RUNNER_TEMP}/workstream-cli-native-isolation.json",
                *pytest_prefix, "${native_files[@]}",
            ],
            [
                *runner_prefix,
                "--metadata-json", "${RUNNER_TEMP}/workstream-cli-self-service-isolation.json",
                *pytest_prefix, "../cli/tests/integration/test_public_self_service.py",
            ],
            [
                *runner_prefix,
                "--metadata-json", "${RUNNER_TEMP}/workstream-cli-batch-isolation.json",
                *pytest_prefix, "../cli/tests/integration/test_task_batch_public_api.py",
            ],
        )
        for script, expected in zip(scripts, expected_runners, strict=True):
            runner = script[script.index("uv run --frozen python scripts/run_isolated_tests.py"):]
            self.assertEqual(
                shlex.split(runner.replace("\\\n", ""), comments=True),
                expected,
            )
        self.assertNotIn("continue-on-error", workflow)
        self.assertIn("timeout-minutes: 15", workflow)

    def test_cli_contract_partitions_assign_every_group_once(self) -> None:
        workflow = Path(".github/workflows/cli.yml").read_text(encoding="utf-8")
        job = workflow.split("\n  cli-public-contract:\n", 1)[1]
        self.assertEqual(
            job.split("    strategy:\n", 1)[1].split("    services:\n", 1)[0],
            "      fail-fast: false\n      matrix:\n"
            "        group: [http, api]\n",
        )
        self.assertEqual(job.count("    strategy:\n"), 1)
        self.assertEqual(job.count("        group:"), 1)
        self.assertNotIn("continue-on-error", job)
        self.assertNotIn("\n    if:", job)
        groups = {
            "Exercise built CLI against task HTTP and local file boundaries": "http",
            "Exercise native terminal HTTP and proof contracts": "http",
            "Exercise existing guide HTTP contracts": "http",
            "Exercise existing native guide API callers": "api",
            "Exercise existing native CLI self-service caller": "api",
            "Exercise complete native CLI batch journey": "api",
        }
        steps = job.split("\n      - ")[1:]
        assignments = {"http": [], "api": []}
        for step in steps:
            title = step.splitlines()[0]
            conditions = re.findall(r"^        if: (.+)$", step, re.MULTILINE)
            name = title.removeprefix("name: ")
            if name in groups:
                group = groups[name]
                self.assertEqual(conditions, ["${{ matrix.group == '" + group + "' }}"])
                assignments[group].append(name)
            elif name == "Stop owned CLI artifact provider":
                self.assertEqual(conditions, ["${{ always() }}"])
            else:
                # Checkout, source/build/lint and provider custody run in both jobs.
                self.assertEqual(conditions, [])
        for group in assignments:
            self.assertCountEqual(
                assignments[group], [name for name, owner in groups.items() if owner == group],
            )
        self.assertEqual(job.count("scripts/run_isolated_tests.py"), len(groups))
        self.assertIn("    timeout-minutes: 15\n", job)

    def test_cli_backend_groups_use_the_frozen_backend_lock_environment(self) -> None:
        workflow = Path(".github/workflows/cli.yml").read_text(encoding="utf-8")
        install = workflow.split("      - name: Install API integration tooling\n", 1)[1].split(
            "\n      - name:", 1
        )[0]
        source_check = workflow.split("      - name: Check integration test source\n", 1)[1].split(
            "\n      - name:", 1
        )[0]

        self.assertIn("        working-directory: backend", install)
        self.assertIn('python -m pip install "uv==0.10.7"', install)
        self.assertIn('test "$(uv --version)" = "uv 0.10.7"', install)
        self.assertIn("uv sync --frozen --extra agents --extra dev", install)
        self.assertIn(
            'test "$(uv run --frozen ruff --version)" = "ruff 0.15.22"',
            install,
        )
        self.assertNotIn("working-directory:", source_check)
        self.assertIn(
            "uv run --frozen --project backend ruff check cli/tests",
            source_check,
        )
        self.assertIn(
            "uv run --frozen --project backend ruff format --check cli/tests",
            source_check,
        )
        self.assertEqual(
            workflow.count("uv run --frozen python scripts/run_isolated_tests.py"),
            6,
        )
        self.assertEqual(
            workflow.count("-- uv run --frozen python -m pytest -q"),
            6,
        )
        self.assertNotIn('python -m pip install -e "./backend[dev,agents]"', workflow)
        self.assertNotIn("\n          ruff check cli/tests", workflow)
        self.assertNotIn("\n          ruff format --check cli/tests", workflow)
        for line in workflow.splitlines():
            if "uv run " in line:
                self.assertIn("uv run --frozen ", line)

    def test_backend_redis_services_use_the_exact_official_image(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        images = re.findall(r"(?m)^      redis:\n        image: (\S+)$", workflow)
        self.assertEqual(
            images,
            [
                "docker.io/library/redis:7-alpine@sha256:"
                "520775a41a63e77e06c73e35d2fd9cc15921a609516818796b4ecbb813078bc7"
            ]
            * 2,
        )

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

    def test_submission_storage_examples_do_not_exempt_public_routes_or_human_roles(self):
        path = "docs/spec_submission_execution.md"
        key = "submission-source/v1/<operation_uuid>/bundle.zip"
        for candidate_path, line, rejected in (
            (path, key, False), ("docs/other.md", key, True),
            (path, "POST /v1/tasks", True), (path, key + " POST /v1/tasks", True),
            (path, "/v1/submission-source", True),
            (path, "`backend/app/workers/artifacts.py`; task delivery", False),
            (path, "`backend/app/workers/artifacts.py`; the worker submits a task", True),
            (path, "A worker submits work", True),
        ):
            with self.subTest(path=candidate_path, line=line):
                self.assertEqual(bool(scan_authorization_text(candidate_path, line)), rejected)

    def test_stale_authorization_allows_exact_compose_worker_service(self) -> None:
        commands = (
            "docker compose --profile backend exec -T worker "
            "celery -A app.workers.celery_app inspect ping",
            "docker compose --profile backend logs -f backend worker beat",
            "Inspect `docker compose --profile backend logs --since 10m worker beat`.",
            "docker compose --profile backend run --rm --no-deps "
            "-e WORKSTREAM_ARTIFACT_STORE_BACKEND=disabled worker python -c 'pass'",
            "docker compose --profile backend kill -s KILL worker",
            "docker compose --profile backend up -d --wait worker",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(scan_authorization_text("docs/new-guide.md", command), [])

    def test_stale_authorization_rejects_human_worker_vocabulary(self) -> None:
        examples = (
            "The worker can approve project work.",
            "# docker compose --profile backend exec -T worker",
            "docker compose --profile backend exec -T backend echo worker",
            "docker compose --profile backend logs --since worker",
            "Use docker compose when the worker approves.",
            "docker compose --profile backend exec -T worker_id echo ok",
        )
        for example in examples:
            with self.subTest(example=example):
                failures = scan_authorization_text("docs/new-guide.md", example)
                self.assertTrue(
                    any(
                        code in failure
                        for failure in failures
                        for code in (
                            "HUMAN_WORKER_VOCABULARY",
                            "HUMAN_WORKER_IDENTIFIER",
                        )
                    )
                )

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
        self.assertIn(
            "types: [opened, synchronize, reopened, ready_for_review, converted_to_draft, edited]",
            workflow,
        )
        self.assertIn("cancel-in-progress: true", workflow)
        # Description-only edits must not cancel or repeat proof for the same head.
        self.assertIn(
            "format('-description-edit-{0}', github.run_id)",
            workflow,
        )
        self.assertIn("actions: read", workflow)
        self.assertIn(
            "if: ${{ !(github.event.action == 'edited' && !github.event.changes.base && github.event.pull_request.head.repo.full_name == github.repository) }}",
            workflow.split("\n  scope:\n", 1)[1].split("\n  minio-image:\n", 1)[0],
        )
        test_job = workflow.split("\n  test:\n", 1)[1]
        self.assertNotIn("Mirror the existing proof", test_job)
        self.assertNotIn("gh api", test_job)
        self.assertIn("timeout-minutes: 40", test_job.split("\n    steps:\n", 1)[0])
        scope_job = workflow.split("\n  scope:\n", 1)[1].split(
            "\n  minio-image:\n", 1
        )[0]
        self.assertIn("fetch-depth: 0", scope_job)
        self.assertIn("python backend/scripts/select_ci_scope.py", scope_job)
        self.assertIn("BASE_SHA: ${{ github.event.pull_request.base.sha || github.event.before }}", scope_job)
        self.assertIn("PR_DRAFT: ${{ github.event_name == 'pull_request' && github.event.pull_request.draft || false }}", scope_job)
        self.assertIn("lane_matrix: ${{ steps.select.outputs.lane_matrix }}", scope_job)
        self.assertEqual(
            workflow.count(
                "matrix: ${{ fromJSON(needs.scope.outputs.lane_matrix) }}"
            ),
            1,
        )
        self.assertIn(
            "  full-suite:\n    if: >-\n"
            "      ${{ always() && needs.scope.result == 'success' &&\n"
            "          needs.scope.outputs.full_suite == 'true' }}\n"
            "    needs: [scope, auth-boundary-preflight, external-checker-runtime, "
            "lanes, minio-image, cli-public-contract, mcp-contract]",
            workflow,
        )
        self.assertIn(
            "    needs: [scope, auth-boundary-preflight, external-checker-runtime, "
            "lanes, minio-image, cli-public-contract, mcp-contract, full-suite]",
            workflow,
        )
        self.assertIn("Require selected supporting checks and every expected lane", workflow)
        self.assertIn("Require the selected draft scope or complete merge proof", workflow)
        cli_job = workflow.split("\n  cli-public-contract:\n", 1)[1].split(
            "\n  full-suite:\n", 1
        )[0]
        self.assertIn("    uses: ./.github/workflows/cli.yml\n", cli_job)
        self.assertIn("    needs: [scope, minio-image]\n", cli_job)
        self.assertIn("      minio_artifact: ${{ needs.minio-image.outputs.artifact }}\n", cli_job)
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
        self.assertEqual(
            image_job.count("hashFiles('docker/minio/**', '.github/workflows/backend.yml')"),
            2,
        )
        self.assertIn(
            "key: minio-source-v2-${{ runner.os }}-${{ runner.arch }}-",
            image_job,
        )
        cache_step = image_job.split(
            "      - name: Restore exact source image from trusted cache\n", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn(
            "uses: actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830",
            cache_step,
        )
        self.assertNotIn("github.sha", cache_step)
        self.assertNotIn("restore-keys:", image_job)
        save_step = image_job.split(
            "      - name: Save verified source image to trusted cache\n", 1
        )[1].split("\n      - uses:", 1)[0]
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main' "
            "&& steps.cache.outputs.cache-hit != 'true'",
            save_step,
        )
        self.assertIn(
            "uses: actions/cache/save@0057852bfaa89a56745cba8c7296529d2fc39830",
            save_step,
        )
        self.assertLess(
            image_job.index("      - name: Verify the cached or freshly built provider"),
            image_job.index("      - name: Save verified source image to trusted cache"),
        )
        self.assertIn("minio-source-${GITHUB_SHA}-${GITHUB_RUN_ATTEMPT}", image_job)
        self.assertIn("artifact: ${{ steps.identity.outputs.artifact }}", image_job)
        self.assertIn("sha256sum minio.tar > minio.tar.sha256", image_job)
        self.assertIn("/minio/health/live", image_job)
        self.assertIn("if-no-files-found: error", image_job)
        self.assertNotIn("continue-on-error", image_job)
        for name, end in (("lanes", "cli-public-contract"), ("full-suite", "test")):
            job = workflow.split(f"\n  {name}:\n", 1)[1]
            if end:
                job = job.split(f"\n  {end}:\n", 1)[0]
            self.assertIn("name: ${{ needs.minio-image.outputs.artifact }}", job)
            self.assertIn("sha256sum --check minio.tar.sha256", job)
            self.assertIn('docker load --input "${RUNNER_TEMP}/minio-image/minio.tar"', job)
            self.assertIn('"${MINIO_IMAGE}" server /data --address :9000', job)

    def test_backend_uv_cache_keeps_fresh_frozen_installs_and_exact_inputs(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")

        key = (
            "backend-uv-v1-${{ runner.os }}-${{ runner.arch }}-py312-"
            "${{ hashFiles('backend/uv.lock', '.github/workflows/backend.yml') }}"
        )
        self.assertEqual(workflow.count("Restore exact backend uv downloads from trusted cache"), 3)
        self.assertEqual(workflow.count(f"key: {key}"), 3)
        self.assertEqual(workflow.count("py312-${{ matrix.sdk_environment }}-"), 1)
        self.assertEqual(
            workflow.count(
                "uses: actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830"
            ),
            4,
        )
        self.assertEqual(
            workflow.count("uses: actions/cache/save@0057852bfaa89a56745cba8c7296529d2fc39830"),
            2,
        )
        tool_install = 'python -m pip install "uv==0.10.7"'
        lock_check = "uv lock --check"
        cache_env = 'echo "UV_CACHE_DIR=${RUNNER_TEMP}/backend-uv-cache" >> "${GITHUB_ENV}"'
        job_blocks = (
            (
                workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split("\n  external-checker-runtime:\n", 1)[0],
                "uv sync --frozen --extra agents --extra dev",
            ),
            (
                workflow.split("\n  lanes:\n", 1)[1].split("\n  cli-public-contract:\n", 1)[0],
                'uv sync --frozen --extra "${{ matrix.sdk_environment }}" --extra dev',
            ),
            (
                workflow.split("\n  full-suite:\n", 1)[1].split("\n  test:\n", 1)[0],
                "uv sync --frozen --extra agents --extra dev",
            ),
        )
        for job, frozen_install in job_blocks:
            self.assertEqual(job.count("Restore exact backend uv downloads from trusted cache"), 1)
            self.assertEqual(job.count(tool_install), 1)
            self.assertEqual(job.count(lock_check), 1)
            self.assertEqual(job.count(frozen_install), 1)
            self.assertLess(job.index(tool_install), job.index(lock_check))
            self.assertLess(job.index(lock_check), job.index(frozen_install))
            self.assertEqual(job.count(cache_env), 1)
            self.assertLess(job.index("Restore exact backend uv downloads"), job.index(cache_env))
            self.assertLess(job.index(cache_env), job.index(tool_install))
            self.assertLess(job.index(tool_install), job.index(frozen_install))
        runtime_job = workflow.split("\n  external-checker-runtime:\n", 1)[1].split("\n  lanes:\n", 1)[0]
        self.assertEqual(runtime_job.count(tool_install), 1)
        self.assertEqual(runtime_job.count(lock_check), 1)
        self.assertEqual(runtime_job.count("uv sync --frozen --extra agents --extra dev"), 1)
        self.assertLess(runtime_job.index(tool_install), runtime_job.index(lock_check))
        self.assertLess(runtime_job.index(lock_check), runtime_job.index("uv sync --frozen"))
        self.assertEqual(workflow.count(tool_install), 4)
        self.assertEqual(workflow.count(lock_check), 4)
        self.assertEqual(
            workflow.count("uv sync --frozen --extra agents --extra dev"), 3
        )
        self.assertEqual(
            workflow.count(
                'uv sync --frozen --extra "${{ matrix.sdk_environment }}" --extra dev'
            ),
            1,
        )
        self.assertEqual(workflow.count(cache_env), 3)
        self.assertNotIn('python -m pip install -e ".[dev,agents]"', workflow)
        root_env = workflow.split("\nenv:\n", 1)[1].split("\njobs:\n", 1)[0]
        self.assertNotIn("runner.", root_env)
        uv_save = workflow.split(
            "      - name: Save verified backend uv downloads to trusted cache\n", 1
        )[1].split("\n  lanes:\n", 1)[0]
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main' "
            "&& steps.uv-cache.outputs.cache-hit != 'true'",
            uv_save,
        )
        preflight = workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split(
            "\n  lanes:\n", 1
        )[0]
        self.assertLess(
            preflight.index("      - name: Validate module, AUTH, and test boundaries"),
            preflight.index("      - name: Save verified backend uv downloads to trusted cache"),
        )
        self.assertNotIn("restore-keys:", workflow)
        self.assertNotIn(".venv", workflow)

    def test_backend_python_commands_stay_in_the_frozen_uv_environment(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        preflight = workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split(
            "\n  external-checker-runtime:\n", 1
        )[0]
        lanes = workflow.split("\n  lanes:\n", 1)[1].split(
            "\n  cli-public-contract:\n", 1
        )[0]
        full_suite = workflow.split("\n  full-suite:\n", 1)[1].split(
            "\n  test:\n", 1
        )[0]

        for command in (
            "uv run --frozen ruff check",
            "uv run --frozen python -m scripts.module_boundaries validate",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --frozen python -m pytest -q",
            "uv run --frozen python -m scripts.authorization_boundary validate",
            "uv run --frozen python -m scripts.test_structure_boundary validate",
            "uv run --frozen python -m scripts.behavior_ownership validate",
            "uv run --frozen docstr-coverage --config .docstr.yaml",
        ):
            self.assertIn(command, preflight)
        self.assertEqual(preflight.count("uv run --frozen ruff check"), 2)
        self.assertIn(
            'test "$(uv run --frozen ruff --version)" = "ruff 0.15.22"',
            preflight,
        )
        self.assertIn("uv run --frozen python scripts/run_test_lanes.py", lanes)
        for command in (
            "uv run --frozen python -m scripts.merge_test_lane_evidence",
            "uv run --frozen python scripts/validate_test_lane_evidence.py",
            "uv run --frozen coverage combine",
            "uv run --frozen python scripts/run_isolated_tests.py",
            "-- uv run --frozen python scripts/api_contract_e2e.py",
            "uv run --frozen coverage report --precision=2",
            "uv run --frozen coverage json",
            "uv run --frozen python - <<'PY'",
        ):
            self.assertIn(command, full_suite)

        for escaped in (
            "\n          ruff check ",
            "\n          python -m scripts.module_boundaries",
            "\n          PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest",
            "\n          python scripts/run_test_lanes.py",
            "\n          python -m scripts.merge_test_lane_evidence",
            "\n          python scripts/validate_test_lane_evidence.py",
            "\n          coverage combine",
            "\n          python scripts/run_isolated_tests.py",
            "\n          -- python scripts/api_contract_e2e.py",
            "\n        run: coverage report",
            "\n          coverage json",
            "\n          python - <<'PY'",
        ):
            self.assertNotIn(escaped, workflow)

        for line in workflow.splitlines():
            if "uv run " in line:
                self.assertIn("uv run --frozen ", line)

    def test_source_wide_static_checks_run_once_outside_semantic_lanes(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        preflight = workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split(
            "\n  external-checker-runtime:\n", 1
        )[0]
        lanes = workflow.split("\n  lanes:\n", 1)[1].split(
            "\n  cli-public-contract:\n", 1
        )[0]

        self.assertEqual(workflow.count("ruff check app tests scripts"), 1)
        self.assertEqual(workflow.count("docstr-coverage --config .docstr.yaml"), 1)
        self.assertIn("Lint and check docstring coverage once", preflight)
        self.assertNotIn("ruff check app tests scripts", lanes)
        self.assertNotIn("docstr-coverage", lanes)

    def test_parallel_preflight_and_lanes_fail_closed_at_fan_in(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        lanes = workflow.split("\n  lanes:\n", 1)[1].split(
            "\n  cli-public-contract:\n", 1
        )[0]
        self.assertRegex(lanes, r"(?m)^    needs: \[scope, minio-image\]$")
        self.assertNotIn("needs: auth-boundary-preflight", lanes)
        step = workflow.split(
            "      - name: Require selected supporting checks and every expected lane\n", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("if: ${{ always() }}", step)
        self.assertIn("PREFLIGHT_RESULT: ${{ needs.auth-boundary-preflight.result }}", step)
        self.assertIn(
            "EXTERNAL_CHECKER_RESULT: ${{ needs.external-checker-runtime.result }}",
            step,
        )
        self.assertIn("LANES_RESULT: ${{ needs.lanes.result }}", step)
        self.assertIn("CLI_RESULT: ${{ needs.cli-public-contract.result }}", step)
        guard = textwrap.dedent(step.split("        run: |\n", 1)[1])
        required = {"EXTERNAL_EXPECTED": "true", "CLI_EXPECTED": "true",
                    "MCP_EXPECTED": "true", "MCP_RESULT": "success"}
        for preflight in ("success", "failure", "cancelled", "skipped", "", "unknown"):
            for lanes_result in ("success", "failure", "cancelled", "skipped", "", "unknown"):
                with self.subTest(preflight=preflight, lanes=lanes_result):
                    result = subprocess.run(
                        ["bash", "-e", "-c", guard],
                        env=required | {
                            "PREFLIGHT_RESULT": preflight,
                            "EXTERNAL_CHECKER_RESULT": "success",
                            "LANES_RESULT": lanes_result,
                            "CLI_RESULT": "success",
                        },
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode == 0,
                        preflight == lanes_result == "success",
                    )
        for external_checker in (
            "failure",
            "cancelled",
            "skipped",
            "",
            "unknown",
        ):
            with self.subTest(external_checker=external_checker):
                result = subprocess.run(
                    ["bash", "-e", "-c", guard],
                    env=required | {
                        "PREFLIGHT_RESULT": "success",
                        "EXTERNAL_CHECKER_RESULT": external_checker,
                        "LANES_RESULT": "success",
                        "CLI_RESULT": "success",
                    },
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
        for cli_result in ("failure", "cancelled", "skipped", "", "unknown"):
            with self.subTest(cli=cli_result):
                result = subprocess.run(
                    ["bash", "-e", "-c", guard],
                    env=required | {
                        "PREFLIGHT_RESULT": "success",
                        "EXTERNAL_CHECKER_RESULT": "success",
                        "LANES_RESULT": "success",
                        "CLI_RESULT": cli_result,
                    },
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)

    def test_metadata_edits_cannot_publish_or_replace_required_proof(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        fan_in = workflow.split("\n  test:\n", 1)[1]
        metadata = (
            "github.event_name == 'pull_request' && github.event.action == 'edited' "
            "&& !github.event.changes.base "
            "&& github.event.pull_request.head.repo.full_name == github.repository"
        )
        expressions = {
            key: re.search(r"^    " + key + r": \$\{\{ (.+) \}\}$", fan_in, re.M).group(1)
            for key in ("name", "if")
        }
        self.assertEqual(
            expressions["name"], metadata + " && 'metadata-only' || "
            "github.event_name == 'pull_request' && github.event.pull_request.draft "
            "&& 'draft-test' || 'test'",
        )
        self.assertEqual(expressions["if"], "always() && !(" + metadata + ")")

        def evaluate(expression: str, event: dict[str, object]) -> object:
            # These two pinned expressions use only boolean operators, equality,
            # strings and event values. Model their extracted text if evaluated;
            # GitHub currently displays the literal name expression when skipped.
            rendered = re.sub(r"github[.\w]+", lambda match: repr(event[match[0]]), expression)
            rendered = rendered.replace("always()", "True").replace("&&", " and ")
            rendered = rendered.replace("||", " or ").replace("!", "not ")
            return eval(rendered, {"__builtins__": {}}, {})

        cases = [
            ("edited", False, True, "pull_request", "metadata-only", False),
            ("edited", True, True, "pull_request", None, True),
            ("edited", False, False, "pull_request", None, True),
            ("opened", False, True, "pull_request", None, True),
            ("reopened", False, True, "pull_request", None, True),
            ("synchronize", False, True, "pull_request", None, True),
            ("ready_for_review", False, True, "pull_request", None, True),
            ("converted_to_draft", False, True, "pull_request", None, True),
            ("", False, False, "push", "test", True),
            # A non-PR event must never enter the metadata path.
            ("edited", False, True, "push", "test", True),
        ]
        for action, base_changed, same_repo, event_name, name, runs in cases:
            for draft in (False, True):
                with self.subTest(action=action, base=base_changed, same_repo=same_repo,
                                  event=event_name, draft=draft):
                    event = {
                        "github.event_name": event_name,
                        "github.event.action": action,
                        "github.event.changes.base": base_changed,
                        "github.event.pull_request.head.repo.full_name": "owner/repo" if same_repo else "fork/repo",
                        "github.repository": "owner/repo",
                        "github.event.pull_request.draft": draft,
                    }
                    self.assertEqual(evaluate(expressions["name"], event), name or ("draft-test" if draft else "test"))
                    self.assertEqual(evaluate(expressions["if"], event), runs)

    def test_required_backend_status_accepts_only_the_exact_selected_scope(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        step = workflow.split(
            "      - name: Require the selected draft scope or complete merge proof\n", 1
        )[1]
        guard = textwrap.dedent(step.split("        run: |\n", 1)[1])

        def run_guard(**values: str) -> subprocess.CompletedProcess[bytes]:
            defaults = {
                "SCOPE_RESULT": "success",
                "FULL_SUITE": "false",
                "MCP_EXPECTED": "false",
                "MCP_RESULT": "skipped",
                "PREFLIGHT_EXPECTED": "false",
                "PREFLIGHT_RESULT": "skipped",
                "EXTERNAL_EXPECTED": "false",
                "EXTERNAL_RESULT": "skipped",
                "LANES_EXPECTED": "false",
                "LANES_RESULT": "skipped",
                "MINIO_EXPECTED": "false",
                "MINIO_RESULT": "skipped",
                "CLI_EXPECTED": "false",
                "CLI_RESULT": "skipped",
                "FULL_RESULT": "skipped",
            }
            return subprocess.run(
                ["bash", "-e", "-c", guard],
                env=defaults | values,
                capture_output=True,
                check=False,
            )

        self.assertEqual(run_guard().returncode, 0)
        self.assertEqual(
            run_guard(
                LANES_EXPECTED="true",
                LANES_RESULT="success",
                MINIO_EXPECTED="true",
                MINIO_RESULT="success",
            ).returncode,
            0,
        )
        self.assertEqual(
            run_guard(FULL_SUITE="true", FULL_RESULT="success", MCP_RESULT="success").returncode,
            0,
        )
        component_pairs = (
            ("PREFLIGHT_EXPECTED", "PREFLIGHT_RESULT"),
            ("EXTERNAL_EXPECTED", "EXTERNAL_RESULT"),
            ("LANES_EXPECTED", "LANES_RESULT"),
            ("MINIO_EXPECTED", "MINIO_RESULT"),
            ("CLI_EXPECTED", "CLI_RESULT"),
            ("MCP_EXPECTED", "MCP_RESULT"),
        )
        for expected_key, result_key in component_pairs:
            with self.subTest(component=result_key, outcome="success"):
                self.assertEqual(
                    run_guard(
                        **{expected_key: "true", result_key: "success"}
                    ).returncode,
                    0,
                )
            with self.subTest(component=result_key, outcome="unexpected_success"):
                self.assertNotEqual(
                    run_guard(**{result_key: "success"}).returncode,
                    0,
                )
            for bad_result in ("failure", "cancelled", "skipped", "", "unknown"):
                with self.subTest(component=result_key, outcome=bad_result):
                    self.assertNotEqual(
                        run_guard(
                            **{expected_key: "true", result_key: bad_result}
                        ).returncode,
                        0,
                    )
        for values in (
            {"SCOPE_RESULT": "failure"},
            {"LANES_EXPECTED": "true", "LANES_RESULT": "skipped"},
            {"LANES_EXPECTED": "false", "LANES_RESULT": "success"},
            {"MINIO_EXPECTED": "true", "MINIO_RESULT": "failure"},
            {"FULL_SUITE": "true", "FULL_RESULT": "failure"},
            {"FULL_RESULT": "success"},
        ):
            with self.subTest(values=values):
                self.assertNotEqual(run_guard(**values).returncode, 0)

    def test_postgres_storage_is_bounded_and_disk_contracts_remain(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        lane_service = workflow.split("\n  lanes:\n", 1)[1].split("\n    steps:", 1)[0]
        aggregate_service = workflow.split("\n  full-suite:\n", 1)[1].split(
            "\n    steps:", 1
        )[0]
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
