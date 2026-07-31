"""Test-only child for exercising production extraction sandbox limits."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.modules.artifacts.guide_extraction_worker import (  # noqa: E402
    ExtractionFailure,
    _install_limits,
    _install_seccomp,
)


def _denied(probe) -> bool:
    try:
        probe()
    except PermissionError:
        return True
    except OSError:
        return False
    return False


def main() -> int:
    probe = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        _install_limits(
            cpu_soft_seconds=1 if probe == "__cpu_probe__" else 29,
            cpu_hard_seconds=2 if probe == "__cpu_probe__" else 30,
        )
        _install_seccomp()
        if probe == "__isolation_probe__":
            output = json.dumps(
                {
                    "network": _denied(socket.socket),
                    "outside_read": _denied(lambda: os.open("/etc/passwd", os.O_RDONLY)),
                    "workspace_write": _denied(
                        lambda: os.open("probe", os.O_WRONLY | os.O_CREAT, 0o600)
                    ),
                    "outside_write": _denied(
                        lambda: os.open(
                            "/tmp/workstream-extraction-probe", os.O_WRONLY | os.O_CREAT, 0o600
                        )
                    ),
                    "process": _denied(os.fork),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        elif probe in {"__cpu_probe__", "__wall_probe__"}:
            while True:
                pass
        elif probe == "__memory_probe__":
            _ = bytearray(600 * 1024 * 1024)
            output = "unexpected"
        elif probe == "__abnormal_probe__":
            os._exit(3)
        else:
            raise ExtractionFailure("parser_failure", "invalid_test_probe")
        result = {
            "status": "extracted",
            "error_code": None,
            "output": output,
            "omission_facts": {"truncated": False, "omitted": False},
        }
    except ExtractionFailure as exc:
        result = {
            "status": exc.status,
            "error_code": exc.code,
            "output": None,
            "omission_facts": {"truncated": False, "omitted": False},
        }
    except MemoryError:
        result = {
            "status": "limit_exceeded",
            "error_code": "memory_limit",
            "output": None,
            "omission_facts": {"truncated": False, "omitted": False},
        }
    encoded = json.dumps(result, separators=(",", ":")).encode()
    os.write(1, encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
