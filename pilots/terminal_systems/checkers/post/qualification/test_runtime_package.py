"""Static and local-semantic checks for the integration-only runtime package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).parent
PACKAGE = HERE / "runtime_package"
PRE_CHECKER = HERE.parents[1] / "pre" / "checker.py"


def _pre_module():
    spec = importlib.util.spec_from_file_location("terminal_systems_pre_checker", PRE_CHECKER)
    if spec is None or spec.loader is None:
        raise RuntimeError("PRE checker module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeQualificationPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "package"
        shutil.copytree(PACKAGE, self.root)

    def run_command(self, *command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    def test_package_passes_both_structural_pre_checks(self) -> None:
        checker = _pre_module()
        self.assertEqual(checker.layout(self.root), [])
        self.assertEqual(checker.metadata(self.root), [])
        self.assertFalse(any(path.is_symlink() for path in self.root.rglob("*")))

    def test_smoke_material_is_readable_by_the_image_user_under_private_umask(self) -> None:
        probe = """
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

spec = importlib.util.spec_from_file_location("post_qualifier", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(sys.argv[2])
os.umask(0o077)
module._write_material(root)
print(json.dumps({
    ".": stat.S_IMODE(root.stat().st_mode),
    **{str(path.relative_to(root)): stat.S_IMODE(path.stat().st_mode)
       for path in root.iterdir()},
}))
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", probe,
             str(HERE.parent / "qualify_image.py"),
             str(Path(self.temporary.name) / "smoke-input")],
            check=True, capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(json.loads(result.stdout), {
            ".": 0o755, "workspace": 0o755, "tests": 0o755,
            "instruction.md": 0o444, "task.toml": 0o444,
            "AUTHOR_NOTES.md": 0o444,
        })

    def test_expected_reference_and_negative_states_are_deterministic(self) -> None:
        self.assertNotEqual(self.run_command("sh", "tests/run.sh").returncode, 0)
        for _ in range(3):
            independent = Path(self.temporary.name) / f"reference-{_}"
            shutil.copytree(PACKAGE, independent)
            self.assertEqual(
                subprocess.run(
                    ("sh", "solution/apply.sh"), cwd=independent, timeout=5
                ).returncode,
                0,
            )
            self.assertEqual(
                subprocess.run(("sh", "tests/run.sh"), cwd=independent, timeout=5).returncode,
                0,
            )

        self.assertEqual(self.run_command("sh", "solution/incomplete.sh").returncode, 0)
        self.assertNotEqual(self.run_command("sh", "tests/run.sh").returncode, 0)
        self.assertEqual(self.run_command("sh", "solution/apply.sh").returncode, 0)
        self.assertEqual(self.run_command("sh", "tests/remove-output.sh").returncode, 0)
        self.assertNotEqual(self.run_command("sh", "tests/run.sh").returncode, 0)
        self.assertEqual(self.run_command("sh", "solution/apply.sh").returncode, 0)
        self.assertEqual(self.run_command("sh", "tests/fabricate-output.sh").returncode, 0)
        self.assertNotEqual(self.run_command("sh", "tests/run.sh").returncode, 0)

    def test_controlled_interruption_requires_restart_on_retained_state(self) -> None:
        interrupted = self.run_command("sh", "tests/interrupt.sh")
        self.assertEqual(interrupted.returncode, -15)
        self.assertTrue((self.root / "workspace/partial.txt").is_file())
        self.assertNotEqual(self.run_command("sh", "tests/run.sh").returncode, 0)
        self.assertEqual(self.run_command("sh", "tests/restart.sh").returncode, 0)
        self.assertEqual(self.run_command("sh", "tests/run.sh").returncode, 0)


if __name__ == "__main__":
    unittest.main()
