"""Process-only CLI test support; no Go function imports."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from collections.abc import Callable

import pytest


@pytest.fixture
def cli(tmp_path: Path) -> Callable[..., subprocess.CompletedProcess[str]]:
    executable = os.environ.get("WORKSTREAM_CLI_EXECUTABLE")
    assert executable and Path(executable).is_file(), (
        "build and set WORKSTREAM_CLI_EXECUTABLE"
    )

    def invoke(
        origin: str, token: str, *args: str, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL"}
        }
        env.update(WORKSTREAM_API_URL=origin, WORKSTREAM_TOKEN=token)
        env.update(extra_env or {})
        result = subprocess.run(  # noqa: S603 - built executable, bounded test inputs
            [executable, *args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        assert not token or token not in result.stdout + result.stderr, (
            "credential leaked"
        )
        return result

    return invoke
