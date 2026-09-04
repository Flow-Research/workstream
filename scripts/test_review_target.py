"""Tests for the deterministic review-target sensor and receipt schema."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import jsonschema

from scripts.git_delta import (
    GitCommandError,
    resolve_commit,
    resolve_merge_base,
    run_checked,
)
from scripts.review_target import inspect_review_target, main


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / ".ci/reviewer-evidence/INTERNAL_REVIEW_RECEIPT.schema.json"


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repository, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


class ReviewTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name)
        git(self.repository, "init", "-q")
        git(self.repository, "config", "user.email", "review@example.test")
        git(self.repository, "config", "user.name", "Review Test")
        (self.repository / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(self.repository, "add", "tracked.txt")
        git(self.repository, "commit", "-qm", "base")
        self.base_sha = git(self.repository, "rev-parse", "HEAD")
        (self.repository / "tracked.txt").write_text("head\n", encoding="utf-8")
        git(self.repository, "commit", "-qam", "head")
        self.head_sha = git(self.repository, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inspect(self) -> dict[str, object]:
        return inspect_review_target(self.base_sha, "HEAD", self.repository)

    def test_clean_target_is_final_ready(self) -> None:
        payload = self.inspect()
        self.assertEqual(payload["base_sha"], self.base_sha)
        self.assertEqual(payload["head_sha"], self.head_sha)
        self.assertTrue(payload["worktree"]["clean"])
        self.assertTrue(payload["final_ready"])
        self.assertEqual(
            payload["changed_paths"], [{"path": "tracked.txt", "status": "M"}]
        )

    def test_staged_unstaged_and_untracked_are_dirty(self) -> None:
        (self.repository / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(self.repository, "add", "staged.txt")
        (self.repository / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
        (self.repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")
        worktree = self.inspect()["worktree"]
        self.assertFalse(worktree["clean"])
        self.assertEqual(worktree["staged"], ["staged.txt"])
        self.assertEqual(worktree["unstaged"], ["tracked.txt"])
        self.assertEqual(worktree["untracked"], ["untracked.txt"])
        self.assertFalse(self.inspect()["final_ready"])

    def test_local_change_after_start_invalidates_finality(self) -> None:
        start = self.inspect()
        (self.repository / "later.txt").write_text("later\n", encoding="utf-8")
        end = self.inspect()
        self.assertEqual(start["head_sha"], end["head_sha"])
        self.assertTrue(start["final_ready"])
        self.assertFalse(end["final_ready"])

    def test_rename_and_delete_are_reported(self) -> None:
        git(self.repository, "mv", "tracked.txt", "renamed.txt")
        git(self.repository, "commit", "-qm", "rename")
        renamed = inspect_review_target(self.head_sha, "HEAD", self.repository)[
            "changed_paths"
        ]
        self.assertEqual(
            renamed,
            [{"old_path": "tracked.txt", "path": "renamed.txt", "status": "R100"}],
        )
        (self.repository / "renamed.txt").unlink()
        git(self.repository, "commit", "-qam", "delete")
        deleted = inspect_review_target("HEAD^", "HEAD", self.repository)[
            "changed_paths"
        ]
        self.assertEqual(deleted, [{"path": "renamed.txt", "status": "D"}])

    def test_base_drift_changes_target(self) -> None:
        git(self.repository, "branch", "review-base", self.base_sha)
        first = inspect_review_target("review-base", self.head_sha, self.repository)
        git(self.repository, "branch", "-f", "review-base", self.head_sha)
        second = inspect_review_target("review-base", self.head_sha, self.repository)
        self.assertEqual(first["head_sha"], second["head_sha"])
        self.assertNotEqual(first["base_sha"], second["base_sha"])
        self.assertNotEqual(first["merge_base_sha"], second["merge_base_sha"])

    def test_invalid_refs_and_non_repository_fail_closed(self) -> None:
        with self.assertRaises(GitCommandError):
            inspect_review_target("missing-ref", "HEAD", self.repository)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GitCommandError):
                inspect_review_target("HEAD", "HEAD", Path(directory))

    def test_non_commit_ref_fails_closed(self) -> None:
        blob = git(self.repository, "hash-object", "tracked.txt")
        with self.assertRaises(GitCommandError):
            resolve_commit(blob, repository_root=self.repository)

    def test_unrelated_histories_fail_merge_base(self) -> None:
        git(self.repository, "checkout", "--orphan", "other")
        git(self.repository, "rm", "-q", "-rf", ".")
        (self.repository / "other.txt").write_text("other\n", encoding="utf-8")
        git(self.repository, "add", "other.txt")
        git(self.repository, "commit", "-qm", "other")
        other_sha = git(self.repository, "rev-parse", "HEAD")
        with self.assertRaises(GitCommandError):
            resolve_merge_base(
                self.base_sha, other_sha, repository_root=self.repository
            )

    def test_command_failure_timeout_and_empty_output_fail_closed(self) -> None:
        with self.assertRaises(GitCommandError):
            run_checked(
                ["git", "definitely-not-a-command"], repository_root=self.repository
            )
        with patch(
            "scripts.git_delta.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["git"], 1),
        ):
            with self.assertRaisesRegex(GitCommandError, "GIT_TIMEOUT"):
                run_checked(["git", "status"], repository_root=self.repository)
        with patch("scripts.git_delta.run_checked", return_value=""):
            with self.assertRaisesRegex(GitCommandError, "GIT_INVALID_COMMIT"):
                resolve_commit("HEAD", repository_root=self.repository)

    def test_cli_has_stable_error_shape_and_exit(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "--base",
                    "missing",
                    "--head",
                    "HEAD",
                    "--repository",
                    str(self.repository),
                ]
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stderr.getvalue()), {"error": "GIT_COMMAND_FAILED"})

    def test_cli_supports_direct_script_execution(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "review_target.py"),
                "--repository",
                str(self.repository),
                "--base",
                "HEAD",
                "--head",
                "HEAD",
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["final_ready"])


class ReceiptSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        sha = "a" * 40
        target = {"base_sha": sha, "merge_base_sha": sha, "head_sha": sha}
        cls.receipt = {
            "schema_version": 3,
            "custody": "advisory_session",
            "target": target,
            "reviewer": {"specialty": "security", "run_id": "run-1"},
            "inspections": {
                "start": {"cleanliness": "clean"},
                "end": {"cleanliness": "clean"},
            },
            "evidence": [{"kind": "executed", "source": "unit test", "result": "pass"}],
            "impact_cone": [
                {"source": "owner.py:Owner", "relevance": "owns the reviewed behavior"}
            ],
            "adversarial_probes": [
                {
                    "hypothesis": "invalid input bypasses denial",
                    "method": "negative test",
                    "defect": "remove the invalid-input denial",
                    "expected_observation": "negative test fails",
                    "actual_observation": "negative test failed",
                    "proof_survived": False,
                    "result": "pass",
                }
            ],
            "traceability": [
                {
                    "criterion": "deny invalid input",
                    "behavior": "invalid input cannot bypass denial",
                    "owner": "security",
                    "implementation_source": "owner.py:Owner",
                    "proof_source": "negative test",
                    "execution_custody": "unit test",
                    "claimed_boundary": "service",
                    "proof_strength": "service",
                    "proof_custody": {
                        "kind": "executed",
                        "observations": ["service_orchestration"],
                    },
                    "proof_compatibility": "compatible",
                    "result": "verified",
                }
            ],
            "residual_escape": {
                "hypothesis": "another invalid form bypasses denial",
                "method": "negative test inventory",
                "result": "falsified",
            },
            "findings": [],
            "uncertainty": [],
            "freshness": "current",
            "verdict": "PASS",
        }

    def assert_invalid(self, mutation) -> None:
        receipt = copy.deepcopy(self.receipt)
        mutation(receipt)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(receipt, self.schema)

    def test_minimal_receipt_is_valid(self) -> None:
        jsonschema.validate(self.receipt, self.schema)

    def test_malformed_json_is_rejected(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            json.loads("{")

    def test_required_identity_target_and_inspection_fields(self) -> None:
        for key in (
            "target",
            "reviewer",
            "uncertainty",
            "inspections",
            "impact_cone",
            "adversarial_probes",
            "traceability",
            "residual_escape",
        ):
            with self.subTest(key=key):
                self.assert_invalid(lambda receipt, key=key: receipt.pop(key))
        self.assert_invalid(
            lambda receipt: receipt["target"].__setitem__("head_sha", "bad")
        )
        self.assert_invalid(lambda receipt: receipt["reviewer"].pop("run_id"))
        self.assert_invalid(lambda receipt: receipt["inspections"].pop("end"))
        self.assert_invalid(lambda receipt: receipt.__setitem__("impact_cone", []))
        self.assert_invalid(
            lambda receipt: receipt.__setitem__("adversarial_probes", [])
        )
        self.assert_invalid(lambda receipt: receipt.__setitem__("traceability", []))

    def test_final_verdict_requires_verified_trace_and_closed_escape(self) -> None:
        for result in ("missing", "unavailable"):
            with self.subTest(trace_result=result):
                self.assert_invalid(
                    lambda receipt, result=result: receipt["traceability"][
                        0
                    ].__setitem__("result", result)
                )
        for result in ("survives", "unavailable"):
            with self.subTest(escape_result=result):
                self.assert_invalid(
                    lambda receipt, result=result: receipt[
                        "residual_escape"
                    ].__setitem__("result", result)
                )

        def append_unverified_row(receipt):
            row = copy.deepcopy(receipt["traceability"][0])
            row["behavior"] = "second independent behavior"
            row["result"] = "missing"
            receipt["traceability"].append(row)

        self.assert_invalid(append_unverified_row)
        receipt = copy.deepcopy(self.receipt)
        receipt["verdict"] = "PROVISIONAL"
        receipt["traceability"][0]["result"] = "unavailable"
        receipt["residual_escape"]["result"] = "unavailable"
        jsonschema.validate(receipt, self.schema)

    def test_closed_tokens_and_unknown_claims_are_rejected(self) -> None:
        self.assert_invalid(lambda receipt: receipt.__setitem__("verdict", "APPROVED"))
        self.assert_invalid(
            lambda receipt: receipt["evidence"][0].__setitem__("kind", "claimed")
        )
        self.assert_invalid(
            lambda receipt: receipt["evidence"][0].__setitem__("result", "unknown")
        )
        self.assert_invalid(
            lambda receipt: receipt["evidence"][0].__setitem__("command", "run me")
        )
        self.assert_invalid(
            lambda receipt: receipt.__setitem__("merge_authorized", True)
        )

    def test_final_verdict_requires_a_successful_adversarial_probe(self) -> None:
        for result in ("fail", "unavailable"):
            with self.subTest(result=result):
                self.assert_invalid(
                    lambda receipt, result=result: receipt.__setitem__(
                        "adversarial_probes",
                        [
                            {
                                "hypothesis": "authority bypass",
                                "method": "targeted inspection",
                                "defect": "remove the authority guard",
                                "expected_observation": "inspection finds the missing guard",
                                "actual_observation": "inspection found the missing guard",
                                "proof_survived": False,
                                "result": result,
                            }
                        ],
                    )
                )

        receipt = copy.deepcopy(self.receipt)
        receipt["verdict"] = "PROVISIONAL"
        receipt["adversarial_probes"][0]["result"] = "unavailable"
        jsonschema.validate(receipt, self.schema)

    def test_unresolved_blocker_and_dirty_pass_are_rejected(self) -> None:
        def add_blocker(receipt):
            receipt["findings"].append(
                {
                    "id": "SEC-1",
                    "severity": "High",
                    "location": "file:1",
                    "source_target": "a" * 40,
                    "blocks_pr": True,
                    "disposition": "unresolved",
                    "verification": "",
                    "failure_pattern_ids": [],
                }
            )

        self.assert_invalid(add_blocker)
        self.assert_invalid(
            lambda receipt: receipt["inspections"]["end"].__setitem__(
                "cleanliness", "dirty"
            )
        )

    def test_inspections_cannot_redefine_any_target_sha(self) -> None:
        for inspection in ("start", "end"):
            for field in ("base_sha", "merge_base_sha", "head_sha"):
                with self.subTest(inspection=inspection, field=field):
                    self.assert_invalid(
                        lambda receipt, inspection=inspection, field=field: receipt[
                            "inspections"
                        ][inspection].update(target={field: "b" * 40})
                    )


if __name__ == "__main__":
    unittest.main()
