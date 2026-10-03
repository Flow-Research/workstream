from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_installed_wheel_starts_without_backend_source(tmp_path: Path) -> None:
    adapter_python = os.environ.get("WORKSTREAM_MCP_WHEEL_PYTHON")
    if adapter_python is None:
        pytest.skip("set WORKSTREAM_MCP_WHEEL_PYTHON to run the clean-wheel proof")

    completed = subprocess.run(  # noqa: S603 - CI-provided interpreter from a fresh virtualenv
        [
            adapter_python,
            "-c",
            (
                "import importlib.util; import pathlib; import workstream_mcp; "
                "assert importlib.util.find_spec('app') is None; "
                "assert not pathlib.Path(workstream_mcp.__file__).resolve().is_relative_to("
                f"pathlib.Path({str(ROOT / 'mcp_server')!r}).resolve()); "
                "from workstream_mcp.config import Settings; "
                "from workstream_mcp.server import create_app; "
                "create_app(Settings(api_url='http://127.0.0.1:8000'))"
            ),
        ],
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": ""},
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
