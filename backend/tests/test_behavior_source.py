from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

import pytest

from scripts.behavior_source import (
    SourceAnalysisError,
    _eligible_target,
    _safe_path,
    _regular_repository_file,
    changed_callables,
)


class TestBehaviorSource:
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
        with pytest.raises(SourceAnalysisError, match="unsafe_path"):
            _safe_path(path)

    def test_regular_file_custody(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "backend/scripts/target.py"
            target.parent.mkdir(parents=True)
            target.write_text("pass\n", encoding="utf-8")
            assert _regular_repository_file(root, "backend/scripts/target.py") is True
            link = root / "backend/scripts/link.py"
            link.symlink_to(target)
            assert _regular_repository_file(root, "backend/scripts/link.py") is False

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
            with pytest.raises(SourceAnalysisError, match="unmappable_changed_logic"):
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

    def test_module_level_and_deleted_callable_changes_fail_closed(self) -> None:
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
            with pytest.raises(SourceAnalysisError, match="unmappable_changed_logic"):
                changed_callables(root, self.base, head, "backend/scripts/claimed.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._initialize(root)
            target = root / "backend/scripts/claimed.py"
            target.write_text("", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "remove callable")
            head = self._git(root, "rev-parse", "HEAD")
            with pytest.raises(SourceAnalysisError, match="unmappable_changed_logic"):
                changed_callables(root, self.base, head, "backend/scripts/claimed.py")

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

    def test_source_whitespace_preserves_exact_changed_owner(self, tmp_path: Path) -> None:
        from scripts.behavior_source import _source_at

        self._initialize(tmp_path)
        target = tmp_path / "backend/scripts/claimed.py"
        before = "\n\ndef first():\n    return True\n\ndef second():\n    return False\n\n"
        target.write_text(before)
        self._git(tmp_path, "add", ".")
        self._git(tmp_path, "commit", "-m", "leading whitespace")
        base = self._git(tmp_path, "rev-parse", "HEAD")
        after = before.replace("return True", "return 1")
        target.write_text(after)
        self._git(tmp_path, "add", ".")
        self._git(tmp_path, "commit", "-m", "first function only")
        head = self._git(tmp_path, "rev-parse", "HEAD")
        assert changed_callables(tmp_path, base, head, "backend/scripts/claimed.py") == [
            "scripts.claimed.first"
        ]
        assert _source_at(tmp_path, base, "backend/scripts/claimed.py") == before
        assert _source_at(tmp_path, head, "backend/scripts/claimed.py") == after

    @pytest.mark.parametrize("header", ["Base", "metaclass=Meta"])
    @pytest.mark.parametrize("change_header", [False, True])
    def test_multiline_class_header_and_method_edits(
        self, tmp_path: Path, header: str, change_header: bool
    ) -> None:
        self._initialize(tmp_path)
        target = tmp_path / "backend/scripts/claimed.py"
        before = (
            f"class Service(\n    {header},\n):\n"
            "    @staticmethod\n    def run():\n        return True\n"
        )
        target.write_text(before)
        self._git(tmp_path, "add", ".")
        self._git(tmp_path, "commit", "-m", "multiline header")
        base = self._git(tmp_path, "rev-parse", "HEAD")
        after = before.replace("return True", "return False")
        if change_header:
            after = after.replace(header, header + "Replacement")
        target.write_text(after)
        self._git(tmp_path, "add", ".")
        self._git(tmp_path, "commit", "-m", "method and optional header")
        head = self._git(tmp_path, "rev-parse", "HEAD")
        if change_header:
            with pytest.raises(SourceAnalysisError, match="unmappable_changed_logic"):
                changed_callables(tmp_path, base, head, "backend/scripts/claimed.py")
        else:
            assert changed_callables(tmp_path, base, head, "backend/scripts/claimed.py") == [
                "scripts.claimed.Service.run"
            ]

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
