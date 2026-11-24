"""Built-binary journey driver; never substitutes private product operations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4


class JourneyClient:
    def __init__(self, executable: Path, origin: str, directory: Path):
        self.executable = executable.resolve(strict=True)
        self.origin = origin
        self.directory = directory
        self.steps: list[dict[str, object]] = []
        self.completed_stages: list[str] = []
        self.evidence = None
        if location := os.environ.get("WORKSTREAM_CLI_JOURNEY_EVIDENCE"):
            self.evidence = Path(location) / "cli-receipts"
            self.evidence.mkdir(mode=0o700, parents=True)

    def complete_stage(self, stage: str):
        self.completed_stages.append(stage)
        print(json.dumps({"stage": stage, "result": "passed"}), flush=True)

    def call(self, token: str, *arguments: str, expected_exit: int = 0):
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL"}
        }
        environment.update(WORKSTREAM_API_URL=self.origin, WORKSTREAM_TOKEN=token)
        result = subprocess.run(
            [str(self.executable), *arguments, "--output", "json"],
            env=environment,
            cwd=self.directory,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if token and token in result.stdout + result.stderr:
            raise AssertionError("CLI credential disclosure; output withheld")
        # Never print input contents, credentials, or arbitrary server output.
        self.steps.append({"command": arguments[:3], "exit_code": result.returncode})
        if self.evidence is not None:
            path = self.evidence / f"{len(self.steps):04d}.json"
            with path.open("x", encoding="utf-8") as stream:
                path.chmod(0o600)
                json.dump(
                    {
                        "arguments": arguments,
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                    stream,
                )
        if result.returncode != expected_exit:
            evidence = Path(tempfile.mkdtemp(prefix="workstream-cli-failure-"))
            (evidence / "stdout.json").write_text(result.stdout)
            (evidence / "stderr.json").write_text(result.stderr)
            raise AssertionError(
                f"CLI stage {arguments[:3]!r}: exit {result.returncode}, "
                f"expected {expected_exit}; private local evidence: {evidence}"
            )
        document = json.loads(
            result.stdout if result.returncode == 0 else result.stderr
        )
        if result.returncode and result.stdout:
            raise AssertionError("failed CLI command emitted success output")
        return document

    def body(self, document: dict) -> str:
        path = self.directory / f"input-{uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            json.dump(document, stream)
        return str(path)

    def write(self, token: str, *arguments: str, body: dict, key: str):
        return self.call(
            token, *arguments, "--input", self.body(body), "--idempotency-key", key
        )

    def write_and_replay(self, token: str, *arguments: str, body: dict):
        key = str(uuid4())
        path = self.body(body)
        command = (*arguments, "--input", path, "--idempotency-key", key)
        first = self.call(token, *command)
        replay = self.call(token, *command)
        if replay != first:
            raise AssertionError(f"exact replay changed receipt at {arguments[:3]!r}")
        return first
