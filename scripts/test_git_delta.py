"""Tests for deterministic shared Git delta primitives."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.git_delta import changed_files
from scripts.git_delta import committed_changed_files
from scripts.git_delta import diff_text
from scripts.git_delta import numstat


class GitDeltaTests(unittest.TestCase):
    """Exercise committed and optional local delta discovery."""

    def test_committed_delta_is_sorted_and_local_changes_are_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git(root, "init")
            self._git(root, "config", "user.email", "test@example.com")
            self._git(root, "config", "user.name", "Test")
            (root / "b.txt").write_text("one\n", encoding="utf-8")
            self._git(root, "add", "b.txt")
            self._git(root, "commit", "-m", "base")
            base = self._git(root, "rev-parse", "HEAD")
            (root / "b.txt").write_text("one\ntwo\n", encoding="utf-8")
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "head")
            head = self._git(root, "rev-parse", "HEAD")
            (root / "local.txt").write_text("local\n", encoding="utf-8")

            self.assertEqual(
                changed_files(base, head, repository_root=root, include_local=False),
                ["a.txt", "b.txt"],
            )
            self.assertEqual(
                committed_changed_files(base, head, repository_root=root),
                ["a.txt", "b.txt"],
            )
            self.assertEqual(
                changed_files(base, head, repository_root=root),
                ["a.txt", "b.txt", "local.txt"],
            )
            self.assertEqual(numstat(base, head, repository_root=root, include_local=False)[:2], (2, 0))
            self.assertIn("+++ b/a.txt", diff_text(base, head, repository_root=root, include_local=False))

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", *arguments], cwd=root, text=True, stderr=subprocess.STDOUT
        ).strip()


if __name__ == "__main__":
    unittest.main()
