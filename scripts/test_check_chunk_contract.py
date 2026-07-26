#!/usr/bin/env python3
"""Dedicated mutation tests for check_chunk_contract.py."""

from __future__ import annotations

import json
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
            "loop-memory-state", "stale-artifact-contracts",
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
        with self.assertRaises(checker.ContractError):
            checker.parse_contract_bytes(contract() + b"x" * checker.MAX_CONTRACT_BYTES)
        block = b"```chunk-scope-json\n{}\n```\n"
        with self.assertRaises(checker.ContractError):
            checker.parse_contract_bytes(contract() + block)


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


if __name__ == "__main__":
    unittest.main()
