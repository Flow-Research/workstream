"""Bounded subprocess framework for canonical guide extraction."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from typing import BinaryIO


EXTRACTION_POLICY_VERSION = "guide-extraction-v1"
EXTRACTOR_VERSION = "1"
MAXIMUM_INPUT_BYTES = 32 * 1024 * 1024
MAXIMUM_OUTPUT_BYTES = 4 * 1024 * 1024
MAXIMUM_PROTOCOL_BYTES = (MAXIMUM_OUTPUT_BYTES * 6) + 1024
WALL_TIMEOUT_SECONDS = 60
_SUPPORTED = frozenset({"plain_text", "markdown", "json", "csv"})


@dataclass(frozen=True, slots=True)
class GuideExtractionResult:
    """One bounded child result without raw diagnostics."""

    status: str
    error_code: str | None
    canonical_output: str | None
    output_sha256: str | None
    extractor_name: str
    extractor_version: str = EXTRACTOR_VERSION
    policy_version: str = EXTRACTION_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class BoundGuideExtractor:
    """Typed prepared-artifact inspector for one classified format."""

    runner: GuideExtractionRunner
    detected_format: str

    def inspect(self, reader: BinaryIO, workspace: Path) -> GuideExtractionResult:
        return self.runner.extract(
            reader, detected_format=self.detected_format, workspace=workspace
        )


class GuideExtractionRegistry:
    """Fixed typed registry for the v0.1 standard-library extractors."""

    def __init__(self, runner: GuideExtractionRunner | None = None) -> None:
        self._runner = runner or GuideExtractionRunner()

    def resolve(self, detected_format: str) -> BoundGuideExtractor:
        """Return one policy-bound extractor; unsupported input stays bounded."""
        return BoundGuideExtractor(runner=self._runner, detected_format=detected_format)


class GuideExtractionRunner:
    """Supervise one fixed, secret-free, descriptor-only extraction child."""

    def __init__(self) -> None:
        self._worker_path = Path(__file__).with_name("guide_extraction_worker.py")

    def extract(
        self,
        reader: BinaryIO,
        *,
        detected_format: str,
        workspace: Path,
    ) -> GuideExtractionResult:
        if detected_format not in _SUPPORTED:
            return self._result(detected_format, "unsupported", "unsupported_format", None)
        payload = reader.read(MAXIMUM_INPUT_BYTES + 1)
        if len(payload) > MAXIMUM_INPUT_BYTES:
            return self._result(detected_format, "limit_exceeded", "input_limit", None)
        environment = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"}
        process = None
        try:
            process = subprocess.Popen(
                [sys.executable, "-I", str(self._worker_path), detected_format],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
                cwd=workspace,
                shell=False,
                close_fds=True,
                start_new_session=True,
            )
            stdout, _ = process.communicate(payload, timeout=WALL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            assert process is not None
            self._terminate(process)
            return self._result(detected_format, "limit_exceeded", "wall_time_limit", None)
        except (OSError, ValueError):
            if process is not None:
                self._terminate(process)
            return self._result(detected_format, "parser_failure", "executor_unavailable", None)
        if process.returncode == -signal.SIGXCPU:
            return self._result(detected_format, "limit_exceeded", "cpu_time_limit", None)
        if process.returncode != 0 or len(stdout) > MAXIMUM_PROTOCOL_BYTES:
            return self._result(detected_format, "parser_failure", "executor_lost", None)
        try:
            result = json.loads(stdout)
            status = result["status"]
            error_code = result["error_code"]
            output = result["output"]
        except (KeyError, TypeError, ValueError, UnicodeDecodeError):
            return self._result(detected_format, "parser_failure", "invalid_executor_output", None)
        if status not in {
            "extracted",
            "unsupported",
            "malformed",
            "limit_exceeded",
            "parser_failure",
        }:
            return self._result(detected_format, "parser_failure", "invalid_executor_output", None)
        if output is not None and (
            not isinstance(output, str) or len(output.encode("utf-8")) > MAXIMUM_OUTPUT_BYTES
        ):
            return self._result(detected_format, "limit_exceeded", "output_limit", None)
        return self._result(detected_format, status, error_code, output)

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        """Reap a started executor on every uncertain supervision path."""
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()

    @staticmethod
    def _result(
        detected_format: str,
        status: str,
        error_code: str | None,
        output: str | None,
    ) -> GuideExtractionResult:
        if status != "extracted":
            output = None
        digest = None if output is None else "sha256:" + hashlib.sha256(output.encode()).hexdigest()
        return GuideExtractionResult(
            status=status,
            error_code=error_code,
            canonical_output=output,
            output_sha256=digest,
            extractor_name=f"workstream.{detected_format}",
        )
