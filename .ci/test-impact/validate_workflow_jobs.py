#!/usr/bin/env python3
"""Require the exact job inventory declared by the trusted selector."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

FULL = {
    "impact-selection",
    "auth-boundary-preflight",
    "minio-image",
    "lanes",
    "full-api-e2e",
}
S3 = {"impact-selection", "auth-boundary-preflight", "minio-image", "impact-s3"}
PURE = {"impact-selection", "auth-boundary-preflight", "impact-pure"}
KNOWN = FULL | S3 | PURE
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def validate(manifest: dict[str, Any], results: dict[str, str]) -> None:
    expected_by_mode = {
        ("full", "full"): FULL,
        ("impact", "minio"): S3,
        ("pure", "none"): PURE,
    }
    mode_profile = (manifest.get("mode"), manifest.get("infrastructure_profile"))
    expected = expected_by_mode.get(mode_profile)
    manifest_jobs = manifest.get("expected_jobs")
    if (
        manifest.get("schema_version") != 1
        or expected is None
        or not isinstance(manifest_jobs, list)
        or set(manifest_jobs) != expected
        or len(manifest_jobs) != len(expected)
        or set(results) != KNOWN
    ):
        raise ValueError("invalid_expected_job_inventory")
    for job, result in results.items():
        if job in expected and result != "success":
            raise ValueError(f"expected_job_not_success:{job}")
        if job not in expected and result != "skipped":
            raise ValueError(f"unexpected_job_ran:{job}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--results-json", required=True)
    args = parser.parse_args()
    try:
        if args.manifest.is_symlink() or not args.manifest.is_file():
            raise ValueError("missing_selection_manifest")
        if DIGEST_RE.fullmatch(args.manifest_sha256) is None:
            raise ValueError("invalid_selection_manifest_digest")
        raw = args.manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest() != args.manifest_sha256:
            raise ValueError("selection_manifest_digest_mismatch")
        manifest = json.loads(raw)
        results = json.loads(args.results_json)
        if not isinstance(manifest, dict) or not isinstance(results, dict) or any(
            not isinstance(job, str) or not isinstance(result, str)
            for job, result in results.items()
        ):
            raise ValueError("invalid_job_result_manifest")
        validate(manifest, results)
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"backend job fan-in rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
