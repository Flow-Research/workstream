"""Contract tests for bounded changed-scope mutation selection and evidence."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

import pytest

from scripts.mutation_policy import MutationPolicyError
from scripts.mutation_policy import _eligible_target
from scripts.mutation_policy import _main
from scripts.mutation_policy import _minimal_runtime_environment
from scripts.mutation_policy import _mutant_filters
from scripts.mutation_policy import _parse_outcomes
from scripts.mutation_policy import _reject_disposable_special_files
from scripts.mutation_policy import _read_claim
from scripts.mutation_policy import _regular_repository_file
from scripts.mutation_policy import _safe_path
from scripts.mutation_policy import _strong_calibration
from scripts.mutation_policy import _weak_calibration
from scripts.mutation_policy import _validate_calibration
from scripts.mutation_policy import _write_mutmut_config
from scripts.mutation_policy import build_selection
from scripts.mutation_policy import changed_callables
from scripts.mutation_policy import changed_target_ownership
from scripts.mutation_policy import classify_outcomes
from scripts.mutation_policy import discover_claim_path
from scripts.mutation_policy import discover_selection
from scripts.mutation_policy import execute_pilot
from scripts.mutation_policy import policy_self_test


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
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                "outcomes": ["return"],
                                "boundaries": [],
                            },
                            {
                                "target": "backend/scripts/claimed.py",
                                "callables": ["scripts.claimed.claimed"],
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                "outcomes": ["return"],
                                "boundaries": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)

            assert selection["changed_targets"] == ["backend/scripts/changed.py"]
            assert selection["targets"] == [
                "backend/scripts/changed.py",
                "backend/scripts/claimed.py",
            ]
            assert selection["mutation_targets"] == [
                "backend/scripts/changed.py",
                "backend/scripts/claimed.py",
            ]
            assert selection["tests"] == ["backend/tests/test_claimed.py::test_claimed"]

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

    def test_declaration_only_target_requires_tests_but_is_not_mutated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text(
                '"""Declaration-owned module."""\n\n'
                "from dataclasses import dataclass\n"
                "from typing import Final\n\n"
                "SETTING: Final = True\n\n"
                '@dataclass(frozen=True)\nclass Contract:\n    """Declaration-owned class."""\n\n'
                "    value: bool = True\n\n"
                "def claimed():\n    return True\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "declaration")
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
                                "target": "backend/scripts/claimed.py",
                                "callables": [],
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                "outcomes": ["return"],
                                "boundaries": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)

            assert selection["changed_callables"] == {"backend/scripts/claimed.py": []}
            assert selection["declaration_targets"] == ["backend/scripts/claimed.py"]
            assert selection["mutation_targets"] == []
            assert selection["tests"] == ["backend/tests/test_claimed.py::test_claimed"]

    def test_empty_callables_cannot_hide_changed_or_claim_only_behavior(self) -> None:
        for change_target in (True, False):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._initialize(root)
                if change_target:
                    (root / "backend/scripts/claimed.py").write_text(
                        "def claimed():\n    return False\n", encoding="utf-8"
                    )
                else:
                    (root / "README.md").write_text("claim only\n", encoding="utf-8")
                self._git(root, "add", ".")
                self._git(root, "commit", "-m", "empty callable claim")
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
                                    "target": "backend/scripts/claimed.py",
                                    "callables": [],
                                    "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                    "outcomes": ["return"],
                                    "boundaries": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                expected = (
                    "unowned_changed_callable" if change_target else "empty_claim_only_callables"
                )
                with pytest.raises(MutationPolicyError, match=expected):
                    build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)

    def test_mixed_declaration_and_callable_change_remains_mutated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            (root / "backend/scripts/claimed.py").write_text(
                "SETTING = True\n\ndef claimed():\n    return False\n", encoding="utf-8"
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "mixed behavior")
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
                                "target": "backend/scripts/claimed.py",
                                "callables": ["scripts.claimed.claimed"],
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                "outcomes": ["return"],
                                "boundaries": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = build_selection(root, self.base, head, "WS-QUAL-001-04M", claim)

            assert selection["declaration_targets"] == ["backend/scripts/claimed.py"]
            assert selection["mutation_targets"] == ["backend/scripts/claimed.py"]
            assert selection["changed_callables"] == {
                "backend/scripts/claimed.py": ["scripts.claimed.claimed"]
            }

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
            (
                {"schema_version": 1, "chunk_id": "WS-QUAL-001-04M", "claims": [], "extra": True},
                "invalid_behavior_claim_shape",
            ),
            (
                {"schema_version": 1, "chunk_id": "WS-QUAL-001-04M", "claims": [42]},
                "invalid_behavior_claim",
            ),
            (
                {"schema_version": 2, "chunk_id": "WS-QUAL-001-04M", "claims": []},
                "unsupported_behavior_claim_schema",
            ),
            (
                {"schema_version": 1, "chunk_id": "WS-QUAL-001-04M", "claims": "bad"},
                "invalid_behavior_claim_count",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [
                        {
                            "target": "docs/no.py",
                            "callables": ["docs.no.no"],
                            "tests": ["backend/tests/test_claimed.py::test_claimed"],
                            "outcomes": ["return"],
                            "boundaries": [],
                        }
                    ],
                },
                "ineligible_claim_target",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [
                        {
                            "target": "backend/scripts/missing.py",
                            "callables": ["scripts.missing.missing"],
                            "tests": ["backend/tests/test_claimed.py::test_claimed"],
                            "outcomes": ["return"],
                            "boundaries": [],
                        }
                    ],
                },
                "missing_claim_target",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [
                        {
                            "target": "backend/scripts/claimed.py",
                            "callables": ["scripts.claimed.claimed"],
                            "tests": [],
                            "outcomes": ["return"],
                            "boundaries": [],
                        }
                    ],
                },
                "invalid_claim_tests",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [
                        {
                            "target": "backend/scripts/claimed.py",
                            "callables": ["scripts.claimed.claimed"],
                            "tests": ["not-a-node"],
                            "outcomes": ["return"],
                            "boundaries": [],
                        }
                    ],
                },
                "invalid_claim_test_node",
            ),
            (
                {
                    "schema_version": 1,
                    "chunk_id": "WS-QUAL-001-04M",
                    "claims": [
                        {
                            "target": "backend/scripts/claimed.py",
                            "callables": ["scripts.claimed.claimed"],
                            "tests": ["backend/tests/test_missing.py::test_missing"],
                            "outcomes": ["return"],
                            "boundaries": [],
                        }
                    ],
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
            (
                {"tests": ["backend/tests/test_claimed.py::test_claimed"] * 2},
                "duplicate_claim_test_node",
            ),
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

    def test_mutmut_configuration_is_generated_from_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            pyproject = backend / "pyproject.toml"
            selection = {
                "targets": [
                    "backend/scripts/declaration.py",
                    "backend/scripts/example.py",
                ],
                "mutation_targets": ["backend/scripts/example.py"],
                "tests": ["backend/tests/test_example.py::test_example"],
            }
            pyproject.write_text("not = [valid", encoding="utf-8")
            with pytest.raises(MutationPolicyError, match="invalid_mutation_config"):
                _write_mutmut_config(backend, selection)
            pyproject.write_text(
                "[project]\nname = 'example'\nversion = '0.1.0'\n"
                "[tool.mutmut]\nsource_paths = ['wrong']\n",
                encoding="utf-8",
            )
            digest = _write_mutmut_config(backend, selection)
            document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            assert document["project"] == {"name": "example", "version": "0.1.0"}
            rendered = document["tool"]["mutmut"]
            assert rendered == {
                "source_paths": ["scripts"],
                "only_mutate": ["scripts/example.py"],
                "pytest_add_cli_args_test_selection": ["tests/test_example.py::test_example"],
                "pytest_add_cli_args": ["-q", "--noconftest"],
                "use_git_change_detection": False,
                "debug": True,
                "timeout_multiplier": 4.0,
                "timeout_constant": 2.0,
            }
            assert len(digest) == 64

    def test_generated_mutmut_parse_failure_is_typed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            (backend / "pyproject.toml").write_text(
                "[project]\nname = 'example'\nversion = '0.1.0'\n",
                encoding="utf-8",
            )
            selection = {
                "targets": ["backend/scripts/example.py"],
                "tests": ["backend/tests/test_example.py::test_example"],
            }
            real_loads = tomllib.loads
            calls = 0

            def fail_second_parse(value: str) -> dict[str, object]:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise tomllib.TOMLDecodeError("generated failure", value, 0)
                return real_loads(value)

            monkeypatch.setattr(tomllib, "loads", fail_second_parse)
            with pytest.raises(MutationPolicyError, match="invalid_generated_mutation_config"):
                _write_mutmut_config(backend, selection)

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
                    "target": "backend/scripts/example.py",
                    "callables": [
                        "scripts.example.public",
                        "scripts.example._private",
                        "scripts.example.public",
                    ],
                }
            ]
        }
        assert _mutant_filters(selection) == [
            "scripts.example.x__private__mutmut_*",
            "scripts.example.x_public__mutmut_*",
        ]
        with pytest.raises(MutationPolicyError, match="missing_owner_target"):
            _mutant_filters({"target_owners": [{"callables": ["scripts.example.public"]}]})

    def test_no_target_no_claim_is_typed_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            (root / "README.md").write_text("docs\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "docs")
            head = self._git(root, "rev-parse", "HEAD")
            selection = discover_selection(root, self.base, head)
            assert selection["applicability"] == "not_applicable"
            assert "targets" not in selection

    def test_deleted_target_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            (root / "backend/scripts/claimed.py").unlink()
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "delete target")
            head = self._git(root, "rev-parse", "HEAD")

            with pytest.raises(MutationPolicyError, match="deleted_eligible_target"):
                discover_selection(root, self.base, head)

    def test_applicable_delta_requires_one_changed_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            changed = root / "backend/scripts/claimed.py"
            changed.write_text("def claimed():\n    return False\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "behavior")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="missing_behavior_claim"):
                discover_selection(root, self.base, head)

    def test_multiple_changed_claims_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            claims = root / ".ci/behavior-claims"
            claims.mkdir(parents=True)
            for name in ("WS-QUAL-001-A.json", "WS-QUAL-001-B.json"):
                (claims / name).write_text("{}", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "claims")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="multiple_behavior_claims"):
                discover_claim_path(root, self.base, head)

    def test_changed_callable_mapping_covers_decorated_async_and_nested_methods(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text(
                "class Service:\n"
                "    @staticmethod\n"
                "    async def claimed():\n"
                "        return True\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "nested base")
            self.base = self._git(root, "rev-parse", "HEAD")
            target.write_text(
                "class Service:\n"
                "    @staticmethod\n"
                "    async def claimed():\n"
                "        return False\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "nested")
            head = self._git(root, "rev-parse", "HEAD")
            assert changed_callables(root, self.base, head, "backend/scripts/claimed.py") == [
                "scripts.claimed.Service.claimed"
            ]

    def test_plain_class_header_change_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text(
                "class Service:\n    def claimed(self):\n        return True\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "class base")
            self.base = self._git(root, "rev-parse", "HEAD")
            target.write_text(
                "class RenamedService:\n    def claimed(self):\n        return True\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "rename class")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="unmappable_changed_logic"):
                changed_callables(root, self.base, head, "backend/scripts/claimed.py")

    def test_function_nested_in_function_maps_to_inner_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            body = "def outer():\n    def inner():\n        return {value}\n    return inner\n"
            target.write_text(body.format(value="True"), encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "nested function base")
            self.base = self._git(root, "rev-parse", "HEAD")
            target.write_text(body.format(value="False"), encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "nested function change")
            head = self._git(root, "rev-parse", "HEAD")
            assert changed_callables(root, self.base, head, "backend/scripts/claimed.py") == [
                "scripts.claimed.outer.inner"
            ]

    def test_declaration_only_changes_are_owned_without_inventing_a_callable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text(
                "def claimed():\n    return True\n\nSETTING = True\n", encoding="utf-8"
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "module")
            head = self._git(root, "rev-parse", "HEAD")
            assert changed_target_ownership(
                root, self.base, head, "backend/scripts/claimed.py"
            ) == ([], True)

    def test_deleted_callable_changes_still_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text("", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "remove callable")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="unmappable_changed_logic"):
                changed_callables(root, self.base, head, "backend/scripts/claimed.py")

    def test_module_control_flow_changes_still_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text(
                "def claimed():\n    return True\n\nif True:\n    SETTING = True\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "module control flow")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="unmappable_changed_logic"):
                changed_target_ownership(root, self.base, head, "backend/scripts/claimed.py")

    @pytest.mark.parametrize(
        "body",
        (
            "def claimed():\n    return True\n\nSETTING = compute_policy()\n",
            "class Contract:\n    value = side_effect()\n\ndef claimed():\n    return True\n",
            "@decorate()\nclass Contract:\n    pass\n\ndef claimed():\n    return True\n",
            "@decorate\nclass Contract:\n    pass\n\ndef claimed():\n    return True\n",
            (
                "from local import relationship\n\n"
                "class Contract:\n    value = relationship()\n\n"
                "def claimed():\n    return True\n"
            ),
            (
                "from sqlalchemy.orm import relationship\n\n"
                "def relationship():\n    return object()\n\n"
                "class Contract:\n    value = relationship()\n\n"
                "def claimed():\n    return True\n"
            ),
            (
                "from sqlalchemy.orm import relationship\n\n"
                "@relationship\nclass Contract:\n    value = True\n\n"
                "def claimed():\n    return True\n"
            ),
            (
                "from sqlalchemy.orm import relationship\n\n"
                "@relationship()\nclass Contract:\n    value = True\n\n"
                "def claimed():\n    return True\n"
            ),
            (
                "from pydantic import Field\n\n"
                "@Field()\nclass Contract:\n    value = True\n\n"
                "def claimed():\n    return True\n"
            ),
            (
                "from dataclasses import dataclass\n\n"
                "@dataclass(Evil)\nclass Contract:\n    value = True\n\n"
                "def claimed():\n    return True\n"
            ),
            (
                "from dataclasses import dataclass\n\n"
                "@dataclass(*ARGS)\nclass Contract:\n    value = True\n\n"
                "def claimed():\n    return True\n"
            ),
            (
                "from dataclasses import dataclass\n\n"
                "@dataclass(**OPTIONS)\nclass Contract:\n    value = True\n\n"
                "def claimed():\n    return True\n"
            ),
        ),
    )
    def test_executable_declaration_expressions_fail_closed(self, body: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            (root / "backend/scripts/claimed.py").write_text(body, encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "executable declaration")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(MutationPolicyError, match="unmappable_changed_logic"):
                changed_target_ownership(root, self.base, head, "backend/scripts/claimed.py")

    def test_callable_mapping_uses_merge_base_not_advanced_main(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            self._git(root, "branch", "feature")
            target = root / "backend/scripts/claimed.py"
            target.write_text(
                "def claimed():\n    return True\n\ndef main_only():\n    return True\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "main moved")
            advanced_main = self._git(root, "rev-parse", "HEAD")
            self._git(root, "switch", "feature")
            target.write_text("def claimed():\n    return False\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "feature behavior")
            feature = self._git(root, "rev-parse", "HEAD")
            assert changed_callables(
                root, advanced_main, feature, "backend/scripts/claimed.py"
            ) == ["scripts.claimed.claimed"]

    def test_claim_only_callable_must_exist_in_target_ast(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            head = self._git(root, "rev-parse", "HEAD")
            claim = root / ".ci/behavior-claims/WS-TEST-001-01.json"
            claim.parent.mkdir(parents=True)
            claim.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "chunk_id": "WS-TEST-001-01",
                        "claims": [
                            {
                                "target": "backend/scripts/claimed.py",
                                "callables": ["scripts.claimed.missing"],
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                "outcomes": ["return"],
                                "boundaries": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with pytest.raises(MutationPolicyError, match="missing_claim_callable"):
                build_selection(root, self.base, head, "WS-TEST-001-01", claim)

    def test_blocking_verdict_allows_only_weak_control_and_unselected_exclusions(self) -> None:
        filters = ["scripts.example.x_public__mutmut_*"]
        pass_mutants = [
            {"name": "scripts.example.x_public__mutmut_1", "outcome": "killed"},
            {
                "name": "scripts.mutation_policy.x__weak_calibration__mutmut_1",
                "outcome": "survived",
            },
            {"name": "scripts.example.x_other__mutmut_1", "outcome": "excluded"},
        ]
        pass_filters = [*filters, "scripts.mutation_policy.x__weak_calibration__mutmut_*"]
        counts = {
            name: 0
            for name in (
                "generated",
                "killed",
                "survived",
                "timeout",
                "suspicious",
                "excluded",
                "error",
            )
        }
        counts.update({"generated": 3, "killed": 1, "survived": 1, "excluded": 1})
        assert classify_outcomes(counts, pass_mutants, pass_filters)["status"] == "pass"

        impostor = [{"name": "app.example.x__weak_calibration__mutmut_1", "outcome": "survived"}]
        impostor_filters = ["app.example.x__weak_calibration__mutmut_*"]
        impostor_counts = {name: 0 for name in counts}
        impostor_counts.update({"generated": 1, "survived": 1})
        assert classify_outcomes(impostor_counts, impostor, impostor_filters)["status"] == "block"

        for outcome in ("survived", "timeout", "suspicious", "error", "excluded"):
            mutants = [{"name": "scripts.example.x_public__mutmut_1", "outcome": outcome}]
            blocked = {name: 0 for name in counts}
            blocked.update({"generated": 1, outcome: 1})
            assert classify_outcomes(blocked, mutants, filters)["status"] == "block"

    def test_incomplete_and_unknown_outcomes_fail_closed(self) -> None:
        with pytest.raises(MutationPolicyError, match="incomplete_mutation_outcomes"):
            classify_outcomes({"generated": 0}, [], [])
        counts = {
            name: 0
            for name in (
                "generated",
                "killed",
                "survived",
                "timeout",
                "suspicious",
                "excluded",
                "error",
            )
        }
        counts["generated"] = 1
        with pytest.raises(MutationPolicyError, match="unknown_mutation_outcome"):
            classify_outcomes(counts, [{"name": "mutant", "outcome": "unknown"}], [])
        counts["generated"] = 0
        counts["killed"] = -1
        with pytest.raises(MutationPolicyError, match="invalid_mutation_outcomes"):
            classify_outcomes(counts, [], [])

    def test_policy_self_test_proves_control_and_blocker(self) -> None:
        policy_self_test()

    def test_calibration_rejects_contributor_named_impostors(self) -> None:
        impostors = [
            {"name": "app.example.x__strong_calibration__mutmut_1", "outcome": "killed"},
            {"name": "app.example.x__weak_calibration__mutmut_1", "outcome": "survived"},
        ]
        with pytest.raises(MutationPolicyError, match="strong_calibration_not_killed"):
            _validate_calibration(impostors)
        assert _validate_calibration(
            [
                {
                    "name": "scripts.mutation_policy.x__strong_calibration__mutmut_1",
                    "outcome": "killed",
                },
                {
                    "name": "scripts.mutation_policy.x__weak_calibration__mutmut_1",
                    "outcome": "survived",
                },
            ]
        ) == {"strong": {"killed": 1}, "weak": {"survived": 1}}

    def test_candidate_runtime_environment_excludes_ci_authority(self) -> None:
        environment = _minimal_runtime_environment(
            {
                "PATH": "/bin",
                "HOME": "/tmp/home",
                "GITHUB_ENV": "/tmp/commands",
                "GITHUB_TOKEN": "secret",
                "SERVICE_PASSWORD": "secret",
                "SIGNING_KEY": "secret",
            }
        )
        assert environment == {
            "PATH": "/bin",
            "HOME": "/tmp/home",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONHASHSEED": "0",
        }

    def test_discovery_builds_applicable_exact_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text("def claimed():\n    return False\n", encoding="utf-8")
            claim = root / ".ci/behavior-claims/WS-TEST-001-01.json"
            claim.parent.mkdir(parents=True)
            claim.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "chunk_id": "WS-TEST-001-01",
                        "claims": [
                            {
                                "target": "backend/scripts/claimed.py",
                                "callables": ["scripts.claimed.claimed"],
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
                                "outcomes": ["return"],
                                "boundaries": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "claimed behavior")
            head = self._git(root, "rev-parse", "HEAD")
            selection = discover_selection(root, self.base, head)
            assert selection["applicability"] == "applicable"
            assert selection["claim_path"] == ".ci/behavior-claims/WS-TEST-001-01.json"
            assert selection["changed_callables"] == {
                "backend/scripts/claimed.py": ["scripts.claimed.claimed"]
            }

    def test_main_supports_self_test_and_not_applicable_discovery(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["mutation_policy.py", "--self-test"])
        assert _main() == 0
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            (root / "README.md").write_text("docs\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "docs")
            head = self._git(root, "rev-parse", "HEAD")
            output = root / "selection.json"
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "mutation_policy.py",
                    "--repository-root",
                    str(root),
                    "--base-sha",
                    self.base,
                    "--head-sha",
                    head,
                    "--discover",
                    "--selection-output",
                    str(output),
                ],
            )
            assert _main() == 0
            assert (
                json.loads(output.read_text(encoding="utf-8"))["applicability"] == "not_applicable"
            )

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

    def test_execute_pilot_enforcement_blocks_selected_survivor(self) -> None:
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
    'scripts.mutation_policy.x_policy__mutmut_1': 0,
}}))
""",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            output = root / "evidence.json"

            with pytest.raises(MutationPolicyError, match="blocking_mutation_outcome"):
                execute_pilot(
                    root,
                    selection,
                    manifest,
                    hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    executable,
                    output,
                    30,
                    enforce=True,
                )

            assert json.loads(output.read_text(encoding="utf-8"))["verdict"]["status"] == "block"

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

    def test_main_reports_policy_errors(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
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

    def test_changed_policy_behavior_contract(self) -> None:
        """Exercise the complete non-parameterized contract owned by this correction."""
        scenarios = (
            self.test_changed_targets_are_mandatory_and_claims_are_additive,
            self.test_claim_validation_fails_closed,
            self.test_declaration_only_target_requires_tests_but_is_not_mutated,
            self.test_empty_callables_cannot_hide_changed_or_claim_only_behavior,
            self.test_mixed_declaration_and_callable_change_remains_mutated,
            self.test_claim_path_must_match_the_chunk_contract,
            self.test_malformed_and_duplicate_claims_fail_closed,
            self.test_mutmut_configuration_is_generated_from_selection,
            self.test_callable_filters_are_exact_and_deterministic,
            self.test_no_target_no_claim_is_typed_not_applicable,
            self.test_deleted_target_fails_closed,
            self.test_applicable_delta_requires_one_changed_claim,
            self.test_multiple_changed_claims_fail_closed,
            self.test_changed_callable_mapping_covers_decorated_async_and_nested_methods,
            self.test_plain_class_header_change_fails_closed,
            self.test_function_nested_in_function_maps_to_inner_owner,
            self.test_declaration_only_changes_are_owned_without_inventing_a_callable,
            self.test_deleted_callable_changes_still_fail_closed,
            self.test_module_control_flow_changes_still_fail_closed,
            self.test_callable_mapping_uses_merge_base_not_advanced_main,
            self.test_claim_only_callable_must_exist_in_target_ast,
        )
        for scenario in scenarios:
            scenario()

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
