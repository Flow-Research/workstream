"""Contract tests for bounded changed-scope mutation selection and evidence."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from scripts.mutation_policy import MutationPolicyError
from scripts.mutation_policy import _eligible_target
from scripts.mutation_policy import _main
from scripts.mutation_policy import _mutant_filters
from scripts.mutation_policy import _parse_outcomes
from scripts.mutation_policy import _reject_disposable_special_files
from scripts.mutation_policy import _read_claim
from scripts.mutation_policy import _regular_repository_file
from scripts.mutation_policy import _safe_path
from scripts.mutation_policy import _strong_calibration
from scripts.mutation_policy import _weak_calibration
from scripts.mutation_policy import _verify_mutmut_config
from scripts.mutation_policy import build_selection
from scripts.mutation_policy import execute_pilot


class TestMutationPolicy:
    """Keep selection additive and evidence outcome parsing complete."""

    def test_changed_targets_are_mandatory_and_claims_are_additive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            changed = root / "backend/scripts/changed.py"
            changed.write_text("def changed():\n    return True\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "changed")
            head = self._git(root, "rev-parse", "HEAD")
            claim = root / ".ci/behavior-claims/WS-QUAL-001-04M.json"
            claim.parent.mkdir(parents=True)
            claim.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "chunk_id": "WS-QUAL-001-04M",
                        "claims": [
                            {
                                "target": "backend/scripts/changed.py",
                                "callables": ["scripts.changed.changed"],
                                "tests": [
                                    "backend/tests/test_claimed.py::test_claimed"
                                ],
                                "outcomes": ["return"],
                                "boundaries": [],
                            },
                            {
                                "target": "backend/scripts/claimed.py",
                                "callables": ["scripts.claimed.claimed"],
                                "tests": [
                                    "backend/tests/test_claimed.py::test_claimed"
                                ],
                                "outcomes": ["return"],
                                "boundaries": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = build_selection(
                root, self.base, head, "WS-QUAL-001-04M", claim
            )

            assert selection["changed_targets"] == ["backend/scripts/changed.py"]
            assert selection["targets"] == [
                "backend/scripts/changed.py",
                "backend/scripts/claimed.py",
            ]
            assert selection["tests"] == [
                "backend/tests/test_claimed.py::test_claimed"
            ]

    def test_claim_validation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            head = self._git(root, "rev-parse", "HEAD")
            claim = root / ".ci/behavior-claims/WS-QUAL-001-04M.json"
            claim.parent.mkdir(parents=True)
            claim.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "chunk_id": "WS-QUAL-001-OTHER",
                        "claims": [
                            {
                                "target": "../escape.py",
                                "callables": ["scripts.escape.escape"],
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                "outcomes": ["return"],
                                "boundaries": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with pytest.raises(MutationPolicyError, match="stale_behavior_claim_chunk"):
                build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)

    def test_outcomes_include_killed_survived_timeout_suspicious_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            meta = backend / "mutants/scripts/example.py.meta"
            meta.parent.mkdir(parents=True)
            meta.write_text(
                json.dumps(
                    {
                        "exit_code_by_key": {
                            "killed": 1,
                            "survived": 0,
                            "timeout": 36,
                            "suspicious": 35,
                            "excluded": 34,
                            "error": -11,
                        }
                    }
                ),
                encoding="utf-8",
            )

            outcomes, mutants = _parse_outcomes(backend)

            assert outcomes == {
                "generated": 6,
                "killed": 1,
                "survived": 1,
                "timeout": 1,
                "suspicious": 1,
                "excluded": 1,
                "error": 1,
            }
            assert len(mutants) == 6

    def test_strong_calibration_asserts_the_exact_boundary(self) -> None:
        assert _strong_calibration(1) is True
        assert _strong_calibration(0) is False
        assert _strong_calibration(-1) is False

    def test_weak_calibration_deliberately_asserts_only_the_result_type(self) -> None:
        assert isinstance(_weak_calibration(1), bool)

    @pytest.mark.parametrize(
        ("path", "eligible"),
        [
            ("backend/app/service.py", True),
            ("backend/scripts/tool.py", True),
            ("backend/app/__init__.py", False),
            ("backend/tests/test_service.py", False),
            ("docs/tool.py", False),
        ],
    )
    def test_target_eligibility_is_closed(self, path: str, eligible: bool) -> None:
        assert _eligible_target(path) is eligible

    @pytest.mark.parametrize("path", ["", "/absolute.py", "../escape.py", "a/../b.py", "a//b.py"])
    def test_unsafe_paths_fail_closed(self, path: str) -> None:
        with pytest.raises(MutationPolicyError, match="unsafe_path"):
            _safe_path(path)

    @pytest.mark.parametrize(
        ("claim", "error"),
        [
            ({"schema_version": 1, "chunk_id": "WS-QUAL-001-04M", "claims": [], "extra": True}, "invalid_behavior_claim_shape"),
            ({"schema_version": 1, "chunk_id": "WS-QUAL-001-04M", "claims": [42]}, "invalid_behavior_claim"),
            ({"schema_version": 2, "chunk_id": "WS-QUAL-001-04M", "claims": []}, "unsupported_behavior_claim_schema"),
            ({"schema_version": 1, "chunk_id": "WS-QUAL-001-04M", "claims": "bad"}, "invalid_behavior_claim_count"),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [{"target": "docs/no.py", "callables": ["docs.no.no"], "tests": ["backend/tests/test_claimed.py::test_claimed"], "outcomes": ["return"], "boundaries": []}],
                },
                "ineligible_claim_target",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [{"target": "backend/scripts/missing.py", "callables": ["scripts.missing.missing"], "tests": ["backend/tests/test_claimed.py::test_claimed"], "outcomes": ["return"], "boundaries": []}],
                },
                "missing_claim_target",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [{"target": "backend/scripts/claimed.py", "callables": ["scripts.claimed.claimed"], "tests": [], "outcomes": ["return"], "boundaries": []}],
                },
                "invalid_claim_tests",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [{"target": "backend/scripts/claimed.py", "callables": ["scripts.claimed.claimed"], "tests": ["not-a-node"], "outcomes": ["return"], "boundaries": []}],
                },
                "invalid_claim_test_node",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [{"target": "backend/scripts/claimed.py", "callables": ["scripts.claimed.claimed"], "tests": ["backend/tests/test_missing.py::test_missing"], "outcomes": ["return"], "boundaries": []}],
                },
                "missing_claim_test_module",
            ),
        ],
    )
    def test_claim_shapes_fail_closed(self, claim: dict[str, object], error: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            claim_path = root / ".ci/behavior-claims/WS-QUAL-001-04M.json"
            claim_path.parent.mkdir(parents=True)
            claim_path.write_text(json.dumps(claim), encoding="utf-8")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match=error):
                build_selection(root, self.base, head, "WS-QUAL-001-04M", claim_path)

    def test_claim_path_must_match_the_chunk_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            wrong = root / "claim.json"
            wrong.write_text(
                json.dumps({"schema_version": 1, "chunk_id": "WS-QUAL-001-04M", "claims": []}),
                encoding="utf-8",
            )
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="invalid_behavior_claim_path"):
                build_selection(root, self.base, head, "WS-QUAL-001-04M", wrong)

    @pytest.mark.parametrize(
        ("overrides", "error"),
        [
            ({"callables": []}, "invalid_claim_callables"),
            ({"tests": ["backend/tests/test_claimed.py::test_claimed"] * 2}, "duplicate_claim_test_node"),
            ({"outcomes": ["unknown"]}, "invalid_claim_outcomes"),
            ({"boundaries": ["unknown"]}, "invalid_claim_boundaries"),
        ],
    )
    def test_typed_claim_metadata_fails_closed(
        self, overrides: dict[str, object], error: str
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            item: dict[str, object] = {
                "target": "backend/scripts/claimed.py",
                "callables": ["scripts.claimed.claimed"],
                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                "outcomes": ["return"],
                "boundaries": [],
            }
            item.update(overrides)
            claim = root / ".ci/behavior-claims/WS-QUAL-001-04M.json"
            claim.parent.mkdir(parents=True)
            claim.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "chunk_id": "WS-QUAL-001-04M",
                        "claims": [item],
                    }
                ),
                encoding="utf-8",
            )
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match=error):
                build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)

    def test_malformed_and_duplicate_claims_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            head = self._git(root, "rev-parse", "HEAD")
            claim = root / ".ci/behavior-claims/WS-QUAL-001-04M.json"
            claim.parent.mkdir(parents=True)
            claim.write_text("not-json", encoding="utf-8")
            with pytest.raises(MutationPolicyError, match="invalid_behavior_claim_json"):
                build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)
            item = {
                "target": "backend/scripts/claimed.py",
                "callables": ["scripts.claimed.claimed"],
                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                "outcomes": ["return"],
                "boundaries": [],
            }
            claim.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "chunk_id": "WS-QUAL-001-04M",
                        "claims": [item, item],
                    }
                ),
                encoding="utf-8",
            )
            with pytest.raises(MutationPolicyError, match="duplicate_claim_target"):
                build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)

    def test_invalid_mutmut_metadata_and_zero_mutants_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            meta = backend / "mutants/scripts/example.py.meta"
            meta.parent.mkdir(parents=True)
            meta.write_text("not-json", encoding="utf-8")
            with pytest.raises(MutationPolicyError, match="invalid_mutmut_metadata"):
                _parse_outcomes(backend)
            meta.write_text(json.dumps({"exit_code_by_key": []}), encoding="utf-8")
            with pytest.raises(MutationPolicyError, match="invalid_mutmut_results"):
                _parse_outcomes(backend)
            meta.write_text(json.dumps({"exit_code_by_key": {}}), encoding="utf-8")
            with pytest.raises(MutationPolicyError, match="zero_generated_mutants"):
                _parse_outcomes(backend)

    def test_mutmut_configuration_parse_and_selection_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            pyproject = backend / "pyproject.toml"
            selection = {
                "targets": ["backend/scripts/example.py"],
                "tests": ["backend/tests/test_example.py::test_example"],
            }
            pyproject.write_text("not = [valid", encoding="utf-8")
            with pytest.raises(MutationPolicyError, match="invalid_mutation_config"):
                _verify_mutmut_config(backend, selection)
            pyproject.write_text(
                "[tool.mutmut]\nsource_paths = ['wrong']\n",
                encoding="utf-8",
            )
            with pytest.raises(MutationPolicyError, match="mutation_config_selection_mismatch"):
                _verify_mutmut_config(backend, selection)

    def test_disposable_symlinks_and_invalid_result_values_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            regular = root / "regular.py"
            regular.write_text("pass\n", encoding="utf-8")
            _reject_disposable_special_files(root)
            (root / "link.py").symlink_to(regular)
            with pytest.raises(MutationPolicyError, match="invalid_disposable_entry"):
                _reject_disposable_special_files(root)
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            meta = backend / "mutants/scripts/example.py.meta"
            meta.parent.mkdir(parents=True)
            meta.write_text(
                json.dumps({"exit_code_by_key": {"mutant": "invalid"}}),
                encoding="utf-8",
            )
            with pytest.raises(MutationPolicyError, match="invalid_mutmut_result"):
                _parse_outcomes(backend)

    def test_optional_claim_and_regular_file_custody(self) -> None:
        assert _read_claim(None, Path.cwd(), "WS-QUAL-001-04M") == []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "backend/scripts/target.py"
            target.parent.mkdir(parents=True)
            target.write_text("pass\n", encoding="utf-8")
            assert _regular_repository_file(root, "backend/scripts/target.py") is True
            link = root / "backend/scripts/link.py"
            link.symlink_to(target)
            assert _regular_repository_file(root, "backend/scripts/link.py") is False

    def test_callable_filters_are_exact_and_deterministic(self) -> None:
        selection = {
            "target_owners": [
                {
                    "callables": [
                        "scripts.example.public",
                        "scripts.example._private",
                        "scripts.example.public",
                    ]
                }
            ]
        }
        assert _mutant_filters(selection) == [
            "scripts.example.x__private__mutmut_*",
            "scripts.example.x_public__mutmut_*",
        ]

    def test_zero_targets_and_invalid_revisions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="invalid_revision"):
                build_selection(root, "bad", head, "WS-QUAL-001-04M", None)
            with pytest.raises(MutationPolicyError, match="zero_mutation_targets"):
                build_selection(root, self.base, head, "WS-QUAL-001-04M", None)
            changed = root / "backend/scripts/changed.py"
            changed.write_text("def changed():\n    return True\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "changed")
            changed_head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="changed_target_without_behavior_claim"):
                build_selection(root, self.base, changed_head, "WS-QUAL-001-04M", None)

    def test_execute_pilot_uses_disposable_tree_and_writes_reconciled_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            self._initialize_execution_repository(root)
            head = self._git(root, "rev-parse", "HEAD")
            claim = root / ".ci/behavior-claims/WS-QUAL-001-04M.json"
            selection = build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)
            manifest = root / "trusted.txt"
            manifest.write_text("trusted\n", encoding="utf-8")
            manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            executable = root / "fake-mutmut"
            executable.write_text(
                """#!/usr/bin/env python3
import json
from pathlib import Path
path = Path('mutants/scripts/mutation_policy.py.meta')
path.parent.mkdir(parents=True)
path.write_text(json.dumps({'exit_code_by_key': {
    'scripts.mutation_policy.x__strong_calibration__mutmut_1': 1,
    'scripts.mutation_policy.x__weak_calibration__mutmut_1': 0,
    'scripts.mutation_policy.x_other__mutmut_1': 34,
}}))
""",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            output = root / "evidence.json"

            execute_pilot(
                root,
                selection,
                manifest,
                manifest_digest,
                executable,
                output,
                30,
            )

            evidence = json.loads(output.read_text(encoding="utf-8"))
            assert evidence["head_sha"] == head
            assert evidence["outcomes"] == {
                "generated": 3,
                "killed": 1,
                "survived": 1,
                "timeout": 0,
                "suspicious": 0,
                "excluded": 1,
                "error": 0,
            }
            assert evidence["calibration"] == {
                "strong": {"killed": 1},
                "weak": {"survived": 1},
            }
            assert self._git(root, "status", "--porcelain", "--untracked-files=no") == ""

    def test_execution_rejects_bad_digest_timeout_and_dirty_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            self._initialize_execution_repository(root)
            head = self._git(root, "rev-parse", "HEAD")
            selection = build_selection(
                root,
                self.base,
                head,
                "WS-QUAL-001-04M",
                root / ".ci/behavior-claims/WS-QUAL-001-04M.json",
            )
            manifest = root / "trusted.txt"
            manifest.write_text("trusted\n", encoding="utf-8")
            executable = root / "unused"
            output = root / "evidence.json"
            with pytest.raises(MutationPolicyError, match="untrusted_manifest_digest"):
                execute_pilot(root, selection, manifest, "0" * 64, executable, output, 30)
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with pytest.raises(MutationPolicyError, match="invalid_timeout"):
                execute_pilot(root, selection, manifest, digest, executable, output, 0)
            (root / "backend/scripts/mutation_policy.py").write_text("dirty\n", encoding="utf-8")
            with pytest.raises(MutationPolicyError, match="dirty_source_tree"):
                execute_pilot(root, selection, manifest, digest, executable, output, 30)

    def test_main_reports_policy_errors(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "mutation_policy.py",
                "--base-sha",
                "bad",
                "--head-sha",
                "bad",
                "--chunk-id",
                "WS-QUAL-001-04M",
            ],
        )
        assert _main() == 1
        assert "mutation_policy_error:invalid_revision" in capsys.readouterr().err

    def _initialize(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "test@example.com")
        self._git(root, "config", "user.name", "Test")
        for path, contents in {
            "backend/scripts/claimed.py": "def claimed():\n    return True\n",
            "backend/tests/test_claimed.py": "def test_claimed():\n    assert True\n",
        }.items():
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents, encoding="utf-8")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "base")
        self.base = self._git(root, "rev-parse", "HEAD")

    def _initialize_execution_repository(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "test@example.com")
        self._git(root, "config", "user.name", "Test")
        files = {
            "backend/scripts/mutation_policy.py": "def policy():\n    return True\n",
            "backend/tests/test_mutation_policy.py": (
                "def test_claim():\n    assert True\n"
                "def test_strong():\n    assert True\n"
                "def test_weak():\n    assert True\n"
            ),
            "backend/pyproject.toml": (
                "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
                "[tool.mutmut]\nsource_paths = ['scripts']\n"
                "only_mutate = ['scripts/mutation_policy.py']\n"
                "pytest_add_cli_args_test_selection = ['tests/test_mutation_policy.py::test_claim', "
                "'tests/test_mutation_policy.py::test_strong', 'tests/test_mutation_policy.py::test_weak']\n"
                "pytest_add_cli_args = ['-q', '--noconftest']\n"
                "use_git_change_detection = false\ndebug = true\n"
                "timeout_multiplier = 4.0\ntimeout_constant = 2.0\n"
            ),
            "scripts/git_delta.py": "# shared helper\n",
        }
        for path, contents in files.items():
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents, encoding="utf-8")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "base")
        self.base = self._git(root, "rev-parse", "HEAD")
        claim = root / ".ci/behavior-claims/WS-QUAL-001-04M.json"
        claim.parent.mkdir(parents=True)
        claim.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [
                        {
                            "target": "backend/scripts/mutation_policy.py",
                            "callables": ["scripts.mutation_policy.policy"],
                            "tests": [
                                "backend/tests/test_mutation_policy.py::test_claim",
                                "backend/tests/test_mutation_policy.py::test_strong",
                                "backend/tests/test_mutation_policy.py::test_weak",
                            ],
                            "outcomes": ["return"],
                            "boundaries": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", *arguments], cwd=root, text=True, stderr=subprocess.STDOUT
        ).strip()
