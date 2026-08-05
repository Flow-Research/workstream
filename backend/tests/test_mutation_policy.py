"""Contract tests for bounded changed-scope mutation selection and evidence."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from scripts.mutation_policy import MutationPolicyError
from scripts.mutation_policy import _parse_outcomes
from scripts.mutation_policy import _strong_calibration
from scripts.mutation_policy import _weak_calibration
from scripts.mutation_policy import build_selection


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
                                "target": "backend/scripts/claimed.py",
                                "tests": [
                                    "backend/tests/test_claimed.py::test_claimed"
                                ],
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
            claim = root / "claim.json"
            claim.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "chunk_id": "WS-QUAL-001-OTHER",
                        "claims": [
                            {
                                "target": "../escape.py",
                                "tests": ["backend/tests/test_claimed.py::test_claimed"],
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

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", *arguments], cwd=root, text=True, stderr=subprocess.STDOUT
        ).strip()
