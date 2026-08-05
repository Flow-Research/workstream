#!/usr/bin/env python3
"""Select and execute bounded changed-scope mutation pilots fail closed."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any

def _repository_root() -> Path:
    """Locate the archive root from either original or mutmut-copied code."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "scripts/git_delta.py").is_file():
            return candidate
    raise RuntimeError("repository_root_not_found")


ROOT = _repository_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.git_delta import changed_files  # noqa: E402


SCHEMA_VERSION = 1
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
CHUNK_RE = re.compile(r"^WS-[A-Z]+-[0-9]{3}-[A-Z0-9]+$")
TEST_NODE_RE = re.compile(r"^backend/tests/test_[A-Za-z0-9_/]+\.py::[^\s]+$")
ELIGIBLE_PREFIXES = ("backend/app/", "backend/scripts/")
OUTCOMES = (
    "generated",
    "killed",
    "survived",
    "timeout",
    "suspicious",
    "excluded",
    "error",
)
STATUS_BY_EXIT_CODE: dict[int | None, str] = {
    0: "survived",
    1: "killed",
    3: "killed",
    -24: "timeout",
    24: "timeout",
    152: "timeout",
    255: "timeout",
    35: "suspicious",
    36: "timeout",
    5: "excluded",
    33: "excluded",
    34: "excluded",
    37: "killed",
    2: "error",
    -11: "error",
    -9: "error",
    None: "error",
}


class MutationPolicyError(RuntimeError):
    """The mutation pilot contract is unsafe, incomplete, or stale."""


def _strong_calibration(value: int) -> bool:
    """Provide a behavior whose boundary is asserted exactly by the pilot."""
    return value > 0


def _weak_calibration(value: int) -> bool:
    """Provide an intentionally under-asserted behavior for pilot calibration."""
    return value > 0


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        raise MutationPolicyError(f"git_command_failed:{arguments[0]}")
    return output


def _safe_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or value != path.as_posix()
    ):
        raise MutationPolicyError("unsafe_path")
    return path


def _eligible_target(path: str) -> bool:
    candidate = _safe_path(path)
    return (
        candidate.suffix == ".py"
        and candidate.name != "__init__.py"
        and any(path.startswith(prefix) for prefix in ELIGIBLE_PREFIXES)
        and "/tests/" not in f"/{path}"
    )


def _read_claim(path: Path | None, root: Path, expected_chunk: str) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MutationPolicyError("invalid_behavior_claim_json") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "chunk_id", "claims"}:
        raise MutationPolicyError("invalid_behavior_claim_shape")
    if value["schema_version"] != SCHEMA_VERSION:
        raise MutationPolicyError("unsupported_behavior_claim_schema")
    if value["chunk_id"] != expected_chunk or CHUNK_RE.fullmatch(expected_chunk) is None:
        raise MutationPolicyError("stale_behavior_claim_chunk")
    claims = value["claims"]
    if not isinstance(claims, list) or len(claims) > 8:
        raise MutationPolicyError("invalid_behavior_claim_count")
    normalized: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"target", "tests"}:
            raise MutationPolicyError("invalid_behavior_claim")
        target = claim["target"]
        tests = claim["tests"]
        if not isinstance(target, str) or not _eligible_target(target):
            raise MutationPolicyError("ineligible_claim_target")
        if target in seen_targets:
            raise MutationPolicyError("duplicate_claim_target")
        seen_targets.add(target)
        if not (root / target).is_file():
            raise MutationPolicyError("missing_claim_target")
        if not isinstance(tests, list) or not tests or len(tests) > 12:
            raise MutationPolicyError("invalid_claim_tests")
        normalized_tests: list[str] = []
        for node in tests:
            if not isinstance(node, str) or TEST_NODE_RE.fullmatch(node) is None:
                raise MutationPolicyError("invalid_claim_test_node")
            module = node.split("::", 1)[0]
            _safe_path(module)
            if not (root / module).is_file():
                raise MutationPolicyError("missing_claim_test_module")
            if node in normalized_tests:
                raise MutationPolicyError("duplicate_claim_test_node")
            normalized_tests.append(node)
        normalized.append({"target": target, "tests": sorted(normalized_tests)})
    return sorted(normalized, key=lambda item: item["target"])


def build_selection(
    root: Path,
    base_sha: str,
    head_sha: str,
    chunk_id: str,
    claim_path: Path | None,
) -> dict[str, Any]:
    """Build deterministic mandatory changed targets plus additive claims."""
    if SHA_RE.fullmatch(base_sha) is None or SHA_RE.fullmatch(head_sha) is None:
        raise MutationPolicyError("invalid_revision")
    resolved_head = _git(root, "rev-parse", head_sha)
    resolved_base = _git(root, "rev-parse", base_sha)
    if resolved_head != head_sha or resolved_base != base_sha:
        raise MutationPolicyError("non_exact_revision")
    changed = changed_files(
        base_sha,
        head_sha,
        repository_root=root,
        include_local=False,
    )
    changed_targets = sorted(path for path in changed if _eligible_target(path))
    claims = _read_claim(claim_path, root, chunk_id)
    targets = sorted(set(changed_targets) | {claim["target"] for claim in claims})
    tests = sorted({node for claim in claims for node in claim["tests"]})
    if not targets:
        raise MutationPolicyError("zero_mutation_targets")
    if not tests:
        raise MutationPolicyError("zero_owning_tests")
    return {
        "schema_version": SCHEMA_VERSION,
        "chunk_id": chunk_id,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "head_tree": _git(root, "rev-parse", f"{head_sha}^{{tree}}"),
        "changed_paths": changed,
        "changed_targets": changed_targets,
        "claims": claims,
        "targets": targets,
        "tests": tests,
    }


def _verify_mutmut_config(backend: Path, selection: dict[str, Any]) -> None:
    pyproject = backend / "pyproject.toml"
    try:
        config = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["mutmut"]
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError) as exc:
        raise MutationPolicyError("invalid_mutation_config") from exc
    relative_targets = [target.removeprefix("backend/") for target in selection["targets"]]
    source_paths = sorted({target.split("/", 1)[0] for target in relative_targets})
    test_nodes = [node.removeprefix("backend/") for node in selection["tests"]]
    expected = {
        "source_paths": source_paths,
        "only_mutate": relative_targets,
        "pytest_add_cli_args_test_selection": test_nodes,
        "pytest_add_cli_args": ["-q"],
        "use_git_change_detection": False,
        "debug": True,
        "timeout_multiplier": 4.0,
        "timeout_constant": 2.0,
    }
    if config != expected:
        raise MutationPolicyError("mutation_config_selection_mismatch")


def _parse_outcomes(backend: Path) -> tuple[dict[str, int], list[dict[str, str]]]:
    counts = Counter({outcome: 0 for outcome in OUTCOMES})
    mutants: list[dict[str, str]] = []
    for meta_path in sorted((backend / "mutants").rglob("*.meta")):
        try:
            value = json.loads(meta_path.read_text(encoding="utf-8"))
            results = value["exit_code_by_key"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            raise MutationPolicyError("invalid_mutmut_metadata") from exc
        if not isinstance(results, dict):
            raise MutationPolicyError("invalid_mutmut_results")
        for name, exit_code in sorted(results.items()):
            if not isinstance(name, str) or not (isinstance(exit_code, int) or exit_code is None):
                raise MutationPolicyError("invalid_mutmut_result")
            status = STATUS_BY_EXIT_CODE.get(exit_code, "suspicious")
            counts[status] += 1
            mutants.append({"name": name, "outcome": status})
    counts["generated"] = len(mutants)
    if not mutants:
        raise MutationPolicyError("zero_generated_mutants")
    return dict(counts), mutants


def execute_pilot(
    root: Path,
    selection: dict[str, Any],
    manifest: Path,
    manifest_digest: str,
    mutmut_executable: Path,
    output: Path,
    timeout_seconds: int,
) -> None:
    """Run mutation testing in an archived disposable tree and emit evidence."""
    if timeout_seconds < 1 or timeout_seconds > 720:
        raise MutationPolicyError("invalid_timeout")
    manifest_bytes = manifest.read_bytes()
    if DIGEST_RE.fullmatch(manifest_digest) is None or _sha256(manifest_bytes) != manifest_digest:
        raise MutationPolicyError("untrusted_manifest_digest")
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise MutationPolicyError("dirty_source_tree")
    before_tree = _git(root, "rev-parse", "HEAD^{tree}")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="workstream-mutation-") as temporary:
        disposable = Path(temporary) / "repository"
        disposable.mkdir()
        archive = subprocess.run(
            ["git", "archive", selection["head_sha"]],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if archive.returncode != 0:
            raise MutationPolicyError("archive_failed")
        extract = subprocess.run(
            ["tar", "-x", "-C", str(disposable)],
            input=archive.stdout,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if extract.returncode != 0:
            raise MutationPolicyError("archive_extract_failed")
        backend = disposable / "backend"
        _verify_mutmut_config(backend, selection)
        environment = os.environ.copy()
        environment.pop("GITHUB_TOKEN", None)
        environment.pop("GH_TOKEN", None)
        environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        baseline = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *[node.removeprefix("backend/") for node in selection["tests"]]],
            cwd=backend,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=min(timeout_seconds, 180),
        )
        if baseline.returncode != 0:
            raise MutationPolicyError("baseline_test_failure")
        try:
            result = subprocess.run(
                [str(mutmut_executable), "run", "--max-children", "2"],
                cwd=backend,
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise MutationPolicyError("mutation_timeout") from exc
        if result.returncode != 0:
            raise MutationPolicyError("mutation_engine_error")
        counts, mutants = _parse_outcomes(backend)
        strong = [
            mutant
            for mutant in mutants
            if ".x__strong_calibration__mutmut_" in mutant["name"]
        ]
        weak = [
            mutant
            for mutant in mutants
            if ".x__weak_calibration__mutmut_" in mutant["name"]
        ]
        if not any(mutant["outcome"] == "killed" for mutant in strong):
            raise MutationPolicyError("strong_calibration_not_killed")
        if not any(mutant["outcome"] == "survived" for mutant in weak):
            raise MutationPolicyError("weak_calibration_not_survived")
        calibration = {
            "strong": dict(Counter(mutant["outcome"] for mutant in strong)),
            "weak": dict(Counter(mutant["outcome"] for mutant in weak)),
        }
        elapsed = round(time.monotonic() - started, 3)
    if (
        _git(root, "status", "--porcelain", "--untracked-files=no")
        or _git(root, "rev-parse", "HEAD^{tree}") != before_tree
    ):
        raise MutationPolicyError("source_tree_changed")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "chunk_id": selection["chunk_id"],
        "base_sha": selection["base_sha"],
        "head_sha": selection["head_sha"],
        "head_tree": selection["head_tree"],
        "tool": {"name": "mutmut", "version": "3.7.0"},
        "manifest": {"sha256": manifest_digest},
        "config": {
            "timeout_seconds": timeout_seconds,
            "targets": selection["targets"],
            "tests": selection["tests"],
        },
        "selection_sha256": _sha256(_json_bytes(selection)),
        "elapsed_seconds": elapsed,
        "outcomes": counts,
        "calibration": calibration,
        "mutants": mutants,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(_json_bytes(evidence))


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--chunk-id", required=True)
    parser.add_argument("--claim-file", type=Path)
    parser.add_argument("--selection-output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-digest")
    parser.add_argument("--mutmut-executable", type=Path)
    parser.add_argument("--evidence-output", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=720)
    args = parser.parse_args()
    try:
        root = args.repository_root.resolve(strict=True)
        selection = build_selection(
            root,
            args.base_sha,
            args.head_sha,
            args.chunk_id,
            args.claim_file,
        )
        if args.selection_output:
            args.selection_output.write_bytes(_json_bytes(selection))
        if args.execute:
            if not all((args.manifest, args.manifest_digest, args.mutmut_executable, args.evidence_output)):
                raise MutationPolicyError("missing_execution_argument")
            execute_pilot(
                root,
                selection,
                args.manifest,
                args.manifest_digest,
                args.mutmut_executable,
                args.evidence_output,
                args.timeout_seconds,
            )
    except (MutationPolicyError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"mutation_policy_error:{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
