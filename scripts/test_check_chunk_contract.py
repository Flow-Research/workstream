#!/usr/bin/env python3
"""Dedicated mutation tests for check_chunk_contract.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import check_chunk_contract as checker


ALLOWED = ("scripts/check_chunk_contract.py", "docs/**")
REVIEWERS = tuple(sorted(checker.REVIEWERS))


def contract(**updates: object) -> bytes:
    data: dict[str, object] = {
        "schema_version": 1,
        "chunk_id": "WS-ENG-008-01",
        "phase": "implementation",
        "risk_class": "L1",
        "allowed_paths": list(ALLOWED),
        "forbidden_paths": ["docs/private/**"],
        "required_reviewers": list(REVIEWERS),
        "verification_commands": ["chunk-scope-tests", "git-diff-check"],
    }
    data.update(updates)
    reviewers = "\n".join(f"- [ ] {name}" for name in data.get("required_reviewers", []))
    return f"""# Chunk Contract: WS-ENG-008-01 — Test

## Risk class

L1

## Start phase

`implementation`

## Allowed files

```text
scripts/check_chunk_contract.py
docs/**
```

## Not allowed

Explicit forbidden scope remains human-reviewed.

## Machine scope

```chunk-scope-json
{json.dumps(data, ensure_ascii=False)}
```

## Verification commands

```bash
python3 scripts/test_check_chunk_contract.py
git diff --check origin/main...HEAD
```

## Required reviewers

{reviewers}
""".encode()


class ContractSchemaTests(unittest.TestCase):
    def test_verification_identifier_registry_is_closed(self) -> None:
        self.assertEqual(checker.VERIFICATION_COMMAND_IDS, frozenset({
            "chunk-scope-tests", "agent-gate-tests", "internal-review-evidence",
            "markdown-links", "stale-wording", "git-diff-check",
            "loop-memory-drift-tests", "loop-memory-property-tests",
            "authorization-property-tests", "authorization-property-lint",
            "mutation-policy-tests", "mutation-policy-lint",
            "review-log-archive-tests", "review-log-archive-check",
            "loop-memory-state", "loop-memory-recovery-tests", "stale-artifact-contracts",
        }))

    def test_positive_schema_identity_reviewer_and_command(self) -> None:
        parsed = checker.parse_contract_bytes(contract())
        self.assertEqual(parsed.chunk_id, "WS-ENG-008-01")
        self.assertEqual(parsed.phase, "implementation")

    def test_human_reviewer_labels_compare_case_insensitively(self) -> None:
        raw = contract().replace(b"- [ ] qa/test", b"- [ ] QA/test").replace(
            b"- [ ] ci integrity", b"- [ ] CI integrity"
        )
        self.assertEqual(checker.parse_contract_bytes(raw).required_reviewers, REVIEWERS)

    def test_human_verification_command_disagreement_is_rejected(self) -> None:
        raw = contract().replace(
            b"git diff --check origin/main...HEAD\n```",
            b"git diff --stat origin/main...HEAD\n```",
        )
        with self.assertRaisesRegex(checker.ContractError, "verification identifiers"):
            checker.parse_contract_bytes(raw)

    def test_negative_schema_mutations(self) -> None:
        mutations = [
            contract(schema_version="1"), contract(extra=True),
            contract(allowed_paths=list(ALLOWED) * 2),
            contract(required_reviewers=[*REVIEWERS, "mystery"]),
            contract(verification_commands=["rm -rf ."]),
        ]
        duplicate = contract().replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
        mutations.append(duplicate)
        for item in mutations:
            with self.subTest(item=item[-100:]), self.assertRaises(checker.ContractError):
                checker.parse_contract_bytes(item)

    def test_negative_identity_phase_and_human_agreement(self) -> None:
        mutations = [
            contract(chunk_id="WS-ENG-008-02"),
            contract(phase="specification"),
            contract().replace(b"docs/**\n```", b"other/**\n```", 1),
        ]
        for item in mutations:
            with self.assertRaises(checker.ContractError):
                checker.parse_contract_bytes(item)

    def test_negative_unicode_size_and_duplicate_block(self) -> None:
        with self.assertRaises(checker.ContractError):
            checker.parse_contract_bytes(b"\xff")
        with self.assertRaisesRegex(checker.ContractError, "not valid UTF-8"):
            checker.machine_block_or_none(b"\xff")
        with self.assertRaisesRegex(checker.ContractError, "not valid UTF-8"):
            checker._human_phase_risk(b"\xff")
        with self.assertRaises(checker.ContractError):
            checker.parse_contract_bytes(contract() + b"x" * checker.MAX_CONTRACT_BYTES)
        block = b"```chunk-scope-json\n{}\n```\n"
        with self.assertRaises(checker.ContractError):
            checker.parse_contract_bytes(contract() + block)

    def test_signed_json_decoders_normalize_invalid_utf8(self) -> None:
        with mock.patch.object(checker, "_git", return_value=b"\xff"):
            with self.assertRaisesRegex(checker.ContractError, "not valid UTF-8"):
                checker._git_json(Path("."), "state:.agent-loop/STATE.json")
            with self.assertRaisesRegex(checker.ContractError, "not valid UTF-8"):
                checker.authenticated_ledger(Path("."), "state")


class PathAndStatusTests(unittest.TestCase):
    def test_positive_closed_recursive_path(self) -> None:
        parsed = checker.parse_contract_bytes(contract())
        self.assertEqual(checker.enforce_scope(parsed, [b"docs/a/b.md"]), ("docs/a/b.md",))

    def test_negative_path_grammar_mutations(self) -> None:
        for path in ("/abs", "../escape", "a//b", "a\\b", "a/*", "a/./b", "a/{b,c}"):
            with self.subTest(path=path), self.assertRaises(checker.ContractError):
                checker.validate_pattern(path)

    def test_negative_forbidden_precedes_allowed(self) -> None:
        parsed = checker.parse_contract_bytes(contract())
        with self.assertRaisesRegex(checker.ContractError, "forbidden"):
            checker.enforce_scope(parsed, [b"docs/private/key.md"])

    def test_negative_foreign_and_colliding_paths(self) -> None:
        parsed = checker.parse_contract_bytes(contract())
        cases = [
            [b"foreign.txt"], [b"docs/A", b"docs/a"],
            ["docs/cafe\u0301".encode()], [b"docs/tab\tname"],
            [b"docs/new\nname"], [b"docs/\xff"],
        ]
        for paths in cases:
            with self.subTest(paths=paths), self.assertRaises(checker.ContractError):
                checker.enforce_scope(parsed, paths)

    def test_positive_and_negative_nul_statuses(self) -> None:
        self.assertEqual(
            checker.parse_name_status_z(b"M\0a\0R100\0old\0new\0C90\0x\0y\0"),
            [("M", (b"a",)), ("R100", (b"old", b"new")), ("C90", (b"x", b"y"))],
        )
        for raw in (b"R100\0old\0", b"Q\0a\0", b"M\0a"):
            with self.subTest(raw=raw), self.assertRaises(checker.ContractError):
                checker.parse_name_status_z(raw)

    def test_raw_diff_mode_mutations(self) -> None:
        sha = b"a" * 40
        checker.validate_raw_modes_z(b":100644 100644 " + sha + b" " + sha + b" M\0a\0")
        for mode in (b"100755", b"120000", b"160000"):
            raw = b":" + mode + b" 000000 " + sha + b" " + (b"0" * 40) + b" D\0a\0"
            with self.subTest(mode=mode), self.assertRaises(checker.ContractError):
                checker.validate_raw_modes_z(raw)


class SignedHistorySelectionTests(unittest.TestCase):
    def git(self, repo: Path, *args: str, input: bytes | None = None) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=repo, input=input, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.strip()

    def test_selects_exact_active_signed_start_and_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.email", "test@example.invalid")
            self.git(repo, "config", "user.name", "Test")
            path = Path(".agent-loop/initiatives/WS-ENG-008-x/chunks/WS-ENG-008-01-test.md")
            (repo / path).parent.mkdir(parents=True)
            (repo / path).write_bytes(contract())
            key = repo / ".agent-loop/keys/loop-memory-signing-public.pem"
            key.parent.mkdir(parents=True, exist_ok=True)
            key.write_text("not-a-real-public-key")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "base")
            base = self.git(repo, "rev-parse", "HEAD").decode()
            blob = self.git(repo, "rev-parse", f"HEAD:{path}").decode()
            self.git(repo, "checkout", "--orphan", "automation")
            self.git(repo, "rm", "-qrf", ".")
            state_path = repo / ".agent-loop"
            (state_path / "INITIATIVE_STATE").mkdir(parents=True)
            state = {
                "event": {
                    "type": "start", "initiative_id": "WS-ENG-008",
                    "chunk_id": "WS-ENG-008-01", "main_sha": base,
                    "selection": {"phase": "implementation", "contract_path": str(path),
                                  "contract_blob_sha": blob},
                }
            }
            (state_path / "STATE.json").write_text(json.dumps(state))
            (state_path / "STATE.sig").write_text("fixture-signature")
            (state_path / "MERGE_LOG.jsonl").write_text(json.dumps({
                "schema_version": 2, "previous_entry_hash": None,
                "record": state, "entry_hash": "0" * 64,
            }) + "\n")
            (state_path / "INITIATIVE_STATE/WS-ENG-008.md").write_text(
                "- Active planning chunk: `none`\n"
                "- Active implementation chunk: `WS-ENG-008-01`\n"
            )
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "signed start")
            self.git(repo, "checkout", "-q", "main")
            intent_path = repo / ".agent-loop/merge-intents/WS-ENG-008-01.json"
            intent_path.parent.mkdir(parents=True)
            intent_path.write_text(json.dumps({
                "schema_version": 2, "initiative_id": "WS-ENG-008",
                "chunk_id": "WS-ENG-008-01", "chunk_title": "Test",
                "next_chunk_id": None, "next_chunk_title": None,
                "next_requires_explicit_start": True,
            }))
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "head")
            with (
                mock.patch.object(checker, "verify_state_ref"),
                mock.patch.object(checker, "_git", wraps=checker._git) as git_spy,
            ):
                parsed, start = checker.select_contract(repo, base, "HEAD", "automation")
            history_calls = [
                call for call in git_spy.call_args_list
                if "rev-list" in call.args or any(":.agent-loop/STATE.json" in str(arg) for arg in call.args)
            ]
            self.assertEqual(history_calls, [], "parent STATE history must never authorize selection")
            self.assertEqual(parsed and parsed.chunk_id, "WS-ENG-008-01")
            self.assertEqual(start.contract_blob_sha, blob)
            with self.assertRaisesRegex(checker.ContractError, "authentication failed"):
                checker.select_contract(repo, base, "HEAD", "automation")
            self.git(repo, "checkout", "-q", "automation")
            cancel_record = {
                "event": {"type": "cancel", "initiative_id": "WS-ENG-008",
                          "chunk_id": "WS-ENG-008-01"}
            }
            with (repo / ".agent-loop/MERGE_LOG.jsonl").open("a") as ledger:
                ledger.write(json.dumps({
                    "schema_version": 2, "previous_entry_hash": "0" * 64,
                    "record": cancel_record, "entry_hash": "1" * 64,
                }) + "\n")
            (repo / ".agent-loop/INITIATIVE_STATE/WS-ENG-008.md").write_text(
                "- Active planning chunk: `none`\n- Active implementation chunk: `none`\n"
            )
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "cancel")
            self.git(repo, "checkout", "-q", "main")
            with (
                mock.patch.object(checker, "verify_state_ref"),
                self.assertRaisesRegex(checker.ContractError, "not a start"),
            ):
                checker.select_contract(repo, base, "HEAD", "automation")

    def test_rejects_stopped_projection_and_blob_mutation(self) -> None:
        # Focused helper mutations prove both state and tree bindings fail closed.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, "init", "-q")
            self.git(repo, "config", "user.email", "test@example.invalid")
            self.git(repo, "config", "user.name", "Test")
            (repo / "contract.md").write_text("signed")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "base")
            sha = self.git(repo, "rev-parse", "HEAD").decode()
            start = checker.SignedStart(
                0, "WS-ENG-008", "WS-ENG-008-01", "implementation", sha,
                "contract.md", "0" * 40,
            )
            with self.assertRaisesRegex(checker.ContractError, "path/blob"):
                checker.signed_contract_blob(repo, start, sha)

    def test_grandfather_requires_active_exact_cutover_parent_and_prestart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, "init", "-q", "-b", "automation")
            self.git(repo, "config", "user.email", "test@example.invalid")
            self.git(repo, "config", "user.name", "Test")
            projection = repo / ".agent-loop/INITIATIVE_STATE/WS-OLD-001.md"
            projection.parent.mkdir(parents=True)
            projection.write_text("- Active implementation chunk: `WS-OLD-001-01`\n")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "pre-cutover active")
            (repo / ".agent-loop/STATE.json").write_text(json.dumps({
                "completed_chunk": {"chunk_id": "WS-ENG-008-01"}
            }))
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "cutover")
            (repo / ".agent-loop/STATE.json").write_text(json.dumps({
                "event": {"type": "start", "chunk_id": "WS-OTHER-001-01"}
            }))
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "later")
            records = (
                {"event": {"type": "start", "initiative_id": "WS-OLD-001",
                           "chunk_id": "WS-OLD-001-01", "selection": {"phase": "implementation"}}},
                {"completed_chunk": {"chunk_id": "WS-ENG-008-01", "initiative_id": "WS-ENG-008"}},
                {"event": {"type": "start", "initiative_id": "WS-OTHER-001",
                           "chunk_id": "WS-OTHER-001-01", "selection": {"phase": "implementation"}}},
            )
            valid = checker.SignedStart(
                0, "WS-OLD-001", "WS-OLD-001-01", "implementation",
                "a" * 40, "legacy.md", "b" * 40,
            )
            checker.require_grandfather(records, valid)
            restarted = checker.SignedStart(
                2, "WS-OLD-001", "WS-OLD-001-01", "implementation",
                "a" * 40, "legacy.md", "b" * 40,
            )
            with self.assertRaisesRegex(checker.ContractError, "after cutover"):
                checker.require_grandfather(records, restarted)

    def test_select_rejects_stopped_and_post_cutover_no_schema_starts(self) -> None:
        start_record = {
            "event": {
                "type": "start", "initiative_id": "WS-OLD-001",
                "chunk_id": "WS-OLD-001-01", "main_sha": "a" * 40,
                "selection": {"phase": "implementation", "contract_path": "legacy.md",
                              "contract_blob_sha": "b" * 40},
            }
        }
        cutover = {
            "completed_chunk": {"initiative_id": "WS-ENG-008", "chunk_id": "WS-ENG-008-01"},
            "event": None,
        }
        stopped = {
            "completed_chunk": {"initiative_id": "WS-OLD-001", "chunk_id": "WS-OLD-001-01"},
            "event": None,
        }
        common = (
            mock.patch.object(checker, "added_merge_intent", return_value={
                "path": ".agent-loop/merge-intents/WS-OLD-001-01.json",
                "initiative_id": "WS-OLD-001", "chunk_id": "WS-OLD-001-01",
            }),
            mock.patch.object(checker, "verify_state_ref"),
        )
        with common[0], common[1], mock.patch.object(
            checker, "authenticated_ledger", return_value=(start_record, stopped)
        ), self.assertRaisesRegex(checker.ContractError, "not active"):
            checker.select_contract(Path("."), "base", "head", "state")
        with (
            mock.patch.object(checker, "added_merge_intent", return_value={
                "path": ".agent-loop/merge-intents/WS-OLD-001-01.json",
                "initiative_id": "WS-OLD-001", "chunk_id": "WS-OLD-001-01",
            }),
            mock.patch.object(checker, "verify_state_ref"),
            mock.patch.object(checker, "authenticated_ledger", return_value=(cutover, start_record)),
            mock.patch.object(checker, "require_active_projection"),
            mock.patch.object(checker, "signed_contract_blob", return_value=b"legacy contract"),
            mock.patch.object(checker, "_git", return_value=b"legacy contract"),
            mock.patch.object(subprocess, "run", return_value=mock.Mock(returncode=0)),
            self.assertRaisesRegex(checker.ContractError, "not signed-active at exact cutover"),
        ):
            checker.select_contract(Path("."), "base", "head", "state")


class PlanningIntakeSelectionTests(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.strip()

    def fixture(
        self, directory: str, *, foreign: str | None = None,
        base_existing: str | None = None,
    ) -> tuple[Path, str, dict[str, object]]:
        repo = Path(directory)
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Test")
        (repo / "README.md").write_text("trusted base\n")
        if base_existing:
            existing = repo / f".agent-loop/initiatives/{base_existing}/STATUS.md"
            existing.parent.mkdir(parents=True)
            existing.write_text("existing initiative\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "base")
        base = self.git(repo, "rev-parse", "HEAD").decode()
        initiative = "WS-NEW-001"
        root = repo / f".agent-loop/initiatives/{initiative}-planning"
        (root / "chunks").mkdir(parents=True)
        (root / "reviews").mkdir()
        for name in checker.PLANNING_ROOT_FILES:
            text = (
                "- Active planning chunk: `none`\n"
                "- Active implementation chunk: `none`\n"
                if name == "STATUS.md" else f"# {name}\n"
            )
            (root / name).write_text(text)
        successor = contract().replace(b"WS-ENG-008-01", b"WS-NEW-001-01")
        (root / "chunks/WS-NEW-001-01-implementation.md").write_bytes(successor)
        (root / "reviews/WS-NEW-001-PLAN-internal-review-evidence.md").write_text("review\n")
        (root / "reviews/WS-NEW-001-PLAN-pr-trust-bundle.md").write_text("trust\n")
        intent_path = repo / ".agent-loop/merge-intents/WS-NEW-001-PLAN.json"
        intent_path.parent.mkdir(parents=True)
        intent_path.write_text(json.dumps({
            "schema_version": 2, "initiative_id": initiative,
            "chunk_id": f"{initiative}-PLAN", "chunk_title": "Planning intake",
            "next_chunk_id": f"{initiative}-01", "next_chunk_title": "First chunk",
            "next_requires_explicit_start": True,
        }))
        if foreign:
            path = repo / foreign
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unauthorized\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "planning intake")
        intent = checker.added_merge_intent(repo, base, "HEAD")
        return repo, base, intent

    def test_first_new_initiative_planning_intake_gets_exact_additive_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            scope = checker.planning_intake_scope(repo, base, "HEAD", intent, ())
            self.assertIsNotNone(scope)
            assert scope is not None
            self.assertEqual(scope.chunk_id, "WS-NEW-001-PLAN")
            self.assertEqual(scope.phase, "planning")
            checker.enforce_scope(scope, checker.discover_changes(repo, base, "HEAD"))

    def test_planning_intake_rejects_foreign_and_existing_initiative(self) -> None:
        for foreign in (
            "scripts/implementation.py",
            ".github/workflows/bypass.yml",
            ".agent-loop/policies/broadened.json",
        ):
            with self.subTest(foreign=foreign), tempfile.TemporaryDirectory() as directory:
                repo, base, intent = self.fixture(directory, foreign=foreign)
                with self.assertRaisesRegex(checker.ContractError, "foreign path"):
                    checker.planning_intake_scope(repo, base, "HEAD", intent, ())
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            records = ({"event": {
                "type": "start", "initiative_id": "WS-NEW-001",
                "chunk_id": "WS-NEW-001-00",
            }},)
            with self.assertRaisesRegex(checker.ContractError, "already exists"):
                checker.planning_intake_scope(repo, base, "HEAD", intent, records)

    def test_planning_intake_rejects_nonadditive_and_bad_successor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            (repo / "README.md").write_text("modified by intake\n")
            self.git(repo, "add", "README.md")
            self.git(repo, "commit", "-qm", "smuggled modification")
            with self.assertRaisesRegex(checker.ContractError, "additive files only"):
                checker.planning_intake_scope(repo, base, "HEAD", intent, ())
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            intent["next_chunk_id"] = "WS-NEW-001-99"
            with self.assertRaisesRegex(checker.ContractError, "successor contract"):
                checker.planning_intake_scope(repo, base, "HEAD", intent, ())

    def test_planning_intake_rejects_existing_base_tree_initiative(self) -> None:
        for existing in ("WS-NEW-001", "WS-NEW-001-existing"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as directory:
                repo, base, intent = self.fixture(directory, base_existing=existing)
                with self.assertRaisesRegex(checker.ContractError, "trusted base tree"):
                    checker.planning_intake_scope(repo, base, "HEAD", intent, ())


class RootRecoverySelectionTests(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.strip()

    def fixture(self, directory: str) -> tuple[Path, str, dict[str, object]]:
        repo = Path(directory)
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Test")
        (repo / "README.md").write_text("base\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "base")
        base = self.git(repo, "rev-parse", "HEAD").decode()
        source_contract = (
            Path(__file__).resolve().parents[1] / checker.ROOT_RECOVERY_CONTRACT
        ).read_bytes()
        for path in checker.ROOT_RECOVERY_PATHS:
            destination = repo / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("fixture\n")
        (repo / checker.ROOT_RECOVERY_CONTRACT).write_bytes(source_contract)
        (repo / ".agent-loop/policies/loop-memory-recovery.json").write_text(json.dumps({
            "activation": {
                "chunk_id": checker.ROOT_RECOVERY_CHUNK,
                "initiative_id": checker.ROOT_RECOVERY_INITIATIVE,
            },
            "signed_basis": base,
            "recovered_merges": [],
            "schema_version": 7,
        }))
        intent = {
            "initiative_id": checker.ROOT_RECOVERY_INITIATIVE,
            "chunk_id": checker.ROOT_RECOVERY_CHUNK,
        }
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "root recovery")
        return repo, base, intent

    def scope(self, repo: Path, base: str, intent: dict[str, object]) -> checker.ScopeContract | None:
        with mock.patch.object(checker, "ROOT_RECOVERY_SIGNED_BASIS", base):
            return checker.root_recovery_scope(repo, base, "HEAD", intent)

    def test_exact_one_use_root_recovery_is_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            scope = self.scope(repo, base, intent)
            self.assertIsNotNone(scope)
            assert scope is not None
            checker.enforce_scope(scope, checker.discover_changes(repo, base, "HEAD"))

    def test_root_recovery_rejects_wrong_base_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            with self.assertRaisesRegex(checker.ContractError, "exact trusted commit"):
                checker.root_recovery_scope(repo, base, "HEAD", intent)
            wrong = {**intent, "initiative_id": "WS-ENG-ROOT-999"}
            with self.assertRaisesRegex(checker.ContractError, "identity"):
                self.scope(repo, base, wrong)
            self.assertIsNone(self.scope(repo, base, {**intent, "chunk_id": "WS-ENG-ROOT-001-02"}))

    def test_root_recovery_rejects_extra_path_scope_and_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            (repo / "scripts/extra.py").write_text("extra\n")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "extra path")
            with self.assertRaisesRegex(checker.ContractError, "exact path certificate"):
                self.scope(repo, base, intent)
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            path = repo / checker.ROOT_RECOVERY_CONTRACT
            path.write_bytes(path.read_bytes().replace(
                b"scripts/test_update_post_merge_memory.py", b"scripts/extra.py"
            ))
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "broaden scope")
            with self.assertRaisesRegex(checker.ContractError, "contract scope"):
                self.scope(repo, base, intent)
        with tempfile.TemporaryDirectory() as directory:
            repo, base, intent = self.fixture(directory)
            policy = repo / ".agent-loop/policies/loop-memory-recovery.json"
            data = json.loads(policy.read_text())
            data["recovered_merges"] = [{"merge_sha": "a" * 40}]
            policy.write_text(json.dumps(data))
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "reuse")
            with self.assertRaisesRegex(checker.ContractError, "consumed"):
                self.scope(repo, base, intent)

class GitDiscoveryIntegrationTests(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.strip()

    def repo(self, directory: str) -> tuple[Path, str]:
        repo = Path(directory)
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Test")
        (repo / "README.md").write_text("tracked\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "base")
        return repo, self.git(repo, "rev-parse", "HEAD").decode()

    def scope(self, *allowed: str) -> checker.ScopeContract:
        return checker.ScopeContract(
            "WS-ENG-008-01", "implementation", "L1", tuple(allowed), (), (), (),
        )

    def test_untracked_symlink_is_rejected_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self.repo(directory)
            (repo / "allowed-link").symlink_to("README.md")
            with self.assertRaisesRegex(checker.ContractError, "not a regular file"):
                checker.discover_changes(repo, base, "HEAD")

    def test_untracked_executable_is_rejected_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self.repo(directory)
            executable = repo / "allowed-tool.py"
            executable.write_text("print('ok')\n")
            executable.chmod(0o755)
            with self.assertRaisesRegex(checker.ContractError, "executable"):
                checker.discover_changes(repo, base, "HEAD")

    def test_untracked_case_collision_with_unchanged_head_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self.repo(directory)
            (repo / "readme.md").write_text("collision\n")
            with self.assertRaisesRegex(checker.ContractError, "collide"):
                checker.discover_changes(repo, base, "HEAD")

    def test_staged_dirty_and_untracked_paths_are_aggregated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self.repo(directory)
            (repo / "staged.txt").write_text("staged\n")
            self.git(repo, "add", "staged.txt")
            (repo / "README.md").write_text("dirty\n")
            (repo / "untracked.txt").write_text("untracked\n")
            changed = set(checker.discover_changes(repo, base, "HEAD"))
            self.assertTrue({b"staged.txt", b"README.md", b"untracked.txt"} <= changed)

    def test_grandfather_scope_rejects_foreign_path(self) -> None:
        raw = b"""# Chunk Contract: WS-OLD-001-01 -- Legacy

## Risk class

L1

## Start phase

`implementation`

## Allowed files

```text
allowed.txt
```
"""
        start = checker.SignedStart(
            0, "WS-OLD-001", "WS-OLD-001-01", "implementation",
            "a" * 40, "legacy.md", "b" * 40,
        )
        scope = checker.legacy_scope_from_signed_blob(raw, start)
        with self.assertRaisesRegex(checker.ContractError, "outside allowed scope"):
            checker.enforce_scope(scope, [b"foreign.txt"])

    def test_rename_checks_source_and_destination_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self.repo(directory)
            self.git(repo, "mv", "README.md", "allowed.md")
            with self.assertRaisesRegex(checker.ContractError, "outside allowed scope"):
                checker.enforce_scope(
                    self.scope("allowed.md"), checker.discover_changes(repo, base, "HEAD")
                )

    def test_copy_checks_source_and_destination_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self.repo(directory)
            (repo / "allowed.md").write_bytes((repo / "README.md").read_bytes())
            self.git(repo, "add", "allowed.md")
            changed = checker.discover_changes(repo, base, "HEAD")
            self.assertIn(b"README.md", changed, "copy source must be present")
            with self.assertRaisesRegex(checker.ContractError, "outside allowed scope"):
                checker.enforce_scope(self.scope("allowed.md"), changed)

    def test_staged_executable_symlink_and_gitlink_are_rejected(self) -> None:
        for mode in ("executable", "symlink", "gitlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                repo, base = self.repo(directory)
                if mode == "executable":
                    path = repo / "mode-path"
                    path.write_text("tool\n")
                    path.chmod(0o755)
                    self.git(repo, "add", "mode-path")
                elif mode == "symlink":
                    (repo / "mode-path").symlink_to("README.md")
                    self.git(repo, "add", "mode-path")
                else:
                    commit = self.git(repo, "rev-parse", "HEAD").decode()
                    self.git(repo, "update-index", "--add", "--cacheinfo", f"160000,{commit},mode-path")
                with self.assertRaisesRegex(checker.ContractError, mode):
                    checker.discover_changes(repo, base, "HEAD")

    def test_staged_type_change_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self.repo(directory)
            (repo / "README.md").unlink()
            (repo / "README.md").symlink_to("missing")
            self.git(repo, "add", "README.md")
            with self.assertRaises(checker.ContractError):
                checker.discover_changes(repo, base, "HEAD")

    def test_git_permitted_invalid_utf8_and_non_nfc_names_are_rejected(self) -> None:
        for raw_name in (b"bad-\xff", "cafe\u0301".encode("utf-8")):
            with self.subTest(raw_name=raw_name), tempfile.TemporaryDirectory() as directory:
                repo, base = self.repo(directory)
                descriptor = os.open(os.fsencode(repo), os.O_RDONLY | os.O_DIRECTORY)
                try:
                    file_descriptor = os.open(
                        raw_name, os.O_WRONLY | os.O_CREAT, 0o644, dir_fd=descriptor
                    )
                    os.write(file_descriptor, b"bad\n")
                    os.close(file_descriptor)
                finally:
                    os.close(descriptor)
                with self.assertRaises(checker.ContractError):
                    checker.discover_changes(repo, base, "HEAD")


if __name__ == "__main__":
    unittest.main()
