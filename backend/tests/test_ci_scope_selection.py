"""Regression tests for conservative, event-independent PR impact selection."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from scripts.select_ci_scope import ALL_LANES, changed_paths, main, select_scope


def test_ready_mcp_pull_request_requires_its_contract_without_backend_execution() -> None:
    scope = select_scope(
        ["mcp_server/workstream_mcp/server.py"],
        event_name="pull_request",
        pull_request_draft=False,
    )

    assert scope.full_suite is False
    assert scope.preflight is False
    assert scope.external_checker is False
    assert scope.cli_contract is False
    assert scope.mcp_contract is True
    assert scope.lanes == ()


def test_main_push_always_selects_the_complete_suite() -> None:
    scope = select_scope(
        ["docs/operations_backend_testing.md"],
        event_name="push",
        pull_request_draft=False,
    )

    assert scope.full_suite is True
    assert scope.lanes == ALL_LANES
    assert scope.reason == "protected_push"


def test_empty_draft_diff_fails_closed_to_the_complete_suite() -> None:
    scope = select_scope(
        [],
        event_name="pull_request",
        pull_request_draft=True,
    )

    assert scope.full_suite is True
    assert scope.lanes == ALL_LANES
    assert scope.reason == "empty_diff_fails_closed"


def test_draft_mcp_and_documentation_changes_select_no_heavy_backend_work() -> None:
    scope = select_scope(
        [
            ".commitrail/changes/example.md",
            "docs/roadmap_status.md",
            "mcp_server/workstream_mcp/server.py",
        ],
        event_name="pull_request",
        pull_request_draft=True,
    )

    assert scope.full_suite is False
    assert scope.preflight is False
    assert scope.external_checker is False
    assert scope.cli_contract is False
    assert scope.minio_image is False
    assert scope.lanes == ()


def test_draft_cli_change_selects_only_the_cli_contract_and_minio() -> None:
    scope = select_scope(
        ["cli/internal/commands/task.go"],
        event_name="pull_request",
        pull_request_draft=True,
    )

    assert scope.full_suite is False
    assert scope.cli_contract is True
    assert scope.minio_image is True
    assert scope.preflight is False
    assert scope.external_checker is False
    assert scope.lanes == ()


def test_external_checker_change_requires_full_unmapped_consumer_proof() -> None:
    scope = select_scope(
        ["external_checkers/crates/workstream-checker-sdk/src/lib.rs"],
        event_name="pull_request",
        pull_request_draft=True,
    )

    assert scope.external_checker is True
    assert scope.full_suite is True
    assert scope.preflight is True
    assert scope.cli_contract is True
    assert scope.minio_image is True
    assert scope.lanes == ALL_LANES


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("backend/tests/test_observability.py", ("schema_contracts_a", "schema_contracts_b", "schema_contracts_c")),
        (
            "backend/tests/projects/guide_activation/test_contracts.py",
            (
                "project_lifecycle_a",
                "project_lifecycle_b",
                "project_lifecycle_c",
                "project_lifecycle_d",
            ),
        ),
        (
            "backend/tests/test_tasks.py",
            ("task_lifecycle_a", "task_lifecycle_b", "task_lifecycle_c"),
        ),
    ],
)
def test_known_test_module_retains_complete_backend_proof(
    path: str,
    expected: tuple[str, ...],
) -> None:
    scope = select_scope(
        [path],
        event_name="pull_request",
        pull_request_draft=True,
    )

    assert scope.full_suite is True
    assert scope.preflight is True
    assert set(expected) <= set(scope.lanes)
    assert scope.lanes == ALL_LANES
    assert scope.reason == "unknown_or_cross_cutting_path"


def test_unknown_or_support_test_module_fails_safe_to_every_lane() -> None:
    for path in (
        "backend/tests/test_new_unregistered_behavior.py",
        "backend/tests/projects/example_fixtures.py",
    ):
        scope = select_scope(
            [path],
            event_name="pull_request",
            pull_request_draft=True,
        )

        assert scope.full_suite is True
        assert scope.preflight is True
        assert scope.lanes == ALL_LANES


@pytest.mark.parametrize(
    "path",
    (
        "backend/app/modules/tasks/router.py",
        "backend/pyproject.toml",
        "backend/scripts/verify_auth_boundaries.py",
    ),
)
def test_backend_runtime_change_selects_all_lanes_and_public_cli_contract(
    path: str,
) -> None:
    scope = select_scope(
        [path], event_name="pull_request", pull_request_draft=True
    )

    assert scope.preflight is True
    assert scope.cli_contract is True
    assert scope.lanes == ALL_LANES


def test_backend_workflow_change_exercises_every_component_in_draft() -> None:
    scope = select_scope(
        [".github/workflows/backend.yml"],
        event_name="pull_request",
        pull_request_draft=True,
    )

    assert scope.full_suite is True
    assert scope.preflight is True
    assert scope.external_checker is True
    assert scope.cli_contract is True
    assert scope.lanes == ALL_LANES


def test_github_outputs_are_compact_and_parseable() -> None:
    scope = select_scope(
        ["backend/tests/test_observability.py"],
        event_name="pull_request",
        pull_request_draft=True,
    )
    outputs = scope.outputs()

    assert outputs["full_suite"] == "true"
    assert outputs["lanes_required"] == "true"
    assert outputs["minio_image"] == "true"
    matrix = json.loads(outputs["lane_matrix"])["include"]
    assert [entry["lane"] for entry in matrix] == list(ALL_LANES)
    assert {entry["sdk_environment"] for entry in matrix} == {"agents", "omnicore"}


def test_empty_scope_keeps_a_valid_but_skipped_fail_safe_matrix() -> None:
    scope = select_scope(
        ["docs/roadmap_status.md"],
        event_name="pull_request",
        pull_request_draft=True,
    )
    outputs = scope.outputs()

    assert outputs["lanes_required"] == "false"
    matrix = json.loads(outputs["lane_matrix"])["include"]
    assert [entry["lane"] for entry in matrix] == list(ALL_LANES)


def test_git_rename_out_of_backend_keeps_the_deleted_source_in_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("init", "--quiet")
    git("config", "user.email", "ci-scope@example.invalid")
    git("config", "user.name", "CI Scope Test")
    source = repo / "backend/app/runtime.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "--quiet", "-m", "base")
    base = git("rev-parse", "HEAD")

    destination = repo / "docs/runtime.py"
    destination.parent.mkdir(parents=True)
    source.rename(destination)
    git("add", "-A")
    git("commit", "--quiet", "-m", "rename")
    head = git("rev-parse", "HEAD")

    monkeypatch.chdir(repo)
    paths = changed_paths(base, head)
    scope = select_scope(
        paths,
        event_name="pull_request",
        pull_request_draft=True,
    )

    assert paths == ("backend/app/runtime.py", "docs/runtime.py")
    assert scope.preflight is True
    assert scope.cli_contract is True
    assert scope.lanes == ALL_LANES


@pytest.mark.parametrize(
    "path", ("/absolute.py", "../escape.py", "", "docs//a.md", "docs/./a.md", "docs\\a.md", "docs/a.md\n")
)
def test_invalid_changed_paths_are_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="invalid changed path"):
        select_scope(
            [path],
            event_name="pull_request",
            pull_request_draft=True,
        )


@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize(
    ("paths", "full", "cli", "mcp"),
    [
        (["docs/example.md"], False, False, False),
        (["cli/main.go", "docs/example.md"], False, True, False),
        (["mcp_server/server.py"], False, False, True),
        (["cli/main.go", "mcp_server/server.py"], False, True, True),
        (["cli/main.go", "backend/app/modules/tasks/service.py"], True, True, True),
        (["docs/example.md", "unknown/file.txt"], True, True, True),
        ([".github/workflows/backend.yml"], True, True, True),
        (["docs/tool.py"], True, True, True),
        (["AGENTS.md"], True, True, True),
    ],
)
def test_component_union_is_identical_for_draft_and_ready(paths, full, cli, mcp, draft):
    scope = select_scope(paths, event_name="pull_request", pull_request_draft=draft)
    assert scope.full_suite is full
    assert scope.cli_contract is cli
    assert scope.mcp_contract is mcp
    assert scope.lanes == (ALL_LANES if full else ())
    assert scope.preflight is full
    assert scope.external_checker is full
    assert scope.minio_image is (full or cli)


def test_main_skips_git_diff_on_push_even_with_null_or_unreachable_base(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "github_output.txt"
    exit_code = main(
        [
            "--event-name",
            "push",
            "--pull-request-draft",
            "false",
            "--base-ref",
            "0000000000000000000000000000000000000000",
            "--head-ref",
            "HEAD",
            "--github-output",
            str(output_file),
        ]
    )

    assert exit_code == 0
    contents = output_file.read_text(encoding="utf-8")
    assert "full_suite=true\n" in contents
    assert "scope_reason=protected_push\n" in contents
    assert "lanes_required=true\n" in contents


def test_main_falls_back_to_full_on_ready_pull_request_with_invalid_base(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "github_output.txt"
    exit_code = main(
        [
            "--event-name",
            "pull_request",
            "--pull-request-draft",
            "false",
            "--base-ref",
            "nonexistent-unreachable-sha",
            "--head-ref",
            "HEAD",
            "--github-output",
            str(output_file),
        ]
    )

    assert exit_code == 0
    contents = output_file.read_text(encoding="utf-8")
    assert "full_suite=true\n" in contents
    assert "scope_reason=unavailable_diff\n" in contents
    assert "lanes_required=true\n" in contents


def test_main_allows_omitting_base_and_head_refs_on_non_draft_events(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "github_output.txt"
    exit_code = main(
        [
            "--event-name",
            "push",
            "--pull-request-draft",
            "false",
            "--github-output",
            str(output_file),
        ]
    )

    assert exit_code == 0
    contents = output_file.read_text(encoding="utf-8")
    assert "full_suite=true\n" in contents


def test_main_draft_pull_request_requires_refs_when_no_paths_supplied(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "github_output.txt"
    with pytest.raises(SystemExit):
        main(
            [
                "--event-name",
                "pull_request",
                "--pull-request-draft",
                "true",
                "--github-output",
                str(output_file),
            ]
        )


def test_main_draft_pull_request_with_explicit_changed_paths(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "github_output.txt"
    exit_code = main(
        [
            "--event-name",
            "pull_request",
            "--pull-request-draft",
            "true",
            "--changed-path",
            "docs/roadmap_status.md",
            "--github-output",
            str(output_file),
        ]
    )

    assert exit_code == 0
    contents = output_file.read_text(encoding="utf-8")
    assert "full_suite=false\n" in contents
    assert "lanes_required=false\n" in contents
    assert "scope_reason=verified_changed_paths\n" in contents
