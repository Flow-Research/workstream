#!/usr/bin/env python3
"""Run the native Smol composition on an isolated, prepared Linux/KVM node.

Provisioning is separate: the caller supplies a delegated cgroup, sealed local
images/cache, PostgreSQL, MinIO and exact-source native binaries. This command
never alters an existing service, pulls images or calls a paid model provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
CASE = "test_production_service_executes_project_trial_under_smol_with_real_custody"
CASES = {"author": "author_evidence_accuracy", "runtime": "runtime_environment_and_verification_trials"}


def digest(path: Path) -> str:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"expected regular file: {path.name}")
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def read_json(path: Path, limit: int = 1024 * 1024):
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
        raise ValueError(f"invalid evidence file: {path.name}")
    return json.loads(path.read_bytes())


def verify_source(root: Path, head: str, tree: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not re.fullmatch(
        r"[0-9a-f]{40}", tree
    ):
        raise ValueError("source identities must be full commit/tree hashes")

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True
        ).strip()

    if git("rev-parse", "HEAD") != head or git("rev-parse", "HEAD^{tree}") != tree:
        raise ValueError("source identity differs")
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("source is not clean")


def verify_build(
    manifest: dict, config: dict, service: Path, head: str, tree: str
) -> None:
    if manifest.get("source_head") != head or manifest.get("source_tree") != tree:
        raise ValueError("build source identity differs")
    paths = {
        "service": service,
        "guest": Path(config["smol"]["guest_binary"]),
        "launcher": Path(config["trial_runtime"]["trusted_launcher_path"]),
        "filesystem_tool": Path(config["trial_runtime"]["filesystem_tool_path"]),
    }
    expected = manifest.get("binaries", {})
    if set(expected) != set(paths):
        raise ValueError("build binary inventory differs")
    for name, path in paths.items():
        if not path.is_absolute() or expected[name] != digest(path):
            raise ValueError(f"build binary differs: {name}")
    if (
        expected["guest"] != config["smol"]["guest_sha256"]
        or expected["launcher"] != config["trial_runtime"]["trusted_launcher_digest"]
        or expected["filesystem_tool"]
        != config["trial_runtime"]["filesystem_tool_digest"]
    ):
        raise ValueError("node binary pin differs")


def verify_results(junit: Path, metadata: dict, fixture: dict, head: str) -> None:
    document = ET.parse(junit).getroot()
    cases = document.findall(".//testcase")
    if (
        sorted(case.get("name", "") for case in cases) != sorted(
            f"{CASE}[{case}]" for case in CASES
        )
        or any(document.findall(f".//{tag}") for tag in ("failure", "error", "skipped"))
    ):
        raise ValueError("composition did not complete its exact required case")
    if (
        metadata.get("tree_sha") != head
        or metadata.get("lane") != "trial_composition"
        or metadata.get("database_cleanup_complete") is not True
        or metadata.get("minio_cleanup_complete") is not True
    ):
        raise ValueError("database/storage completion evidence is incomplete")
    selected_cases = fixture.get("cases", {})
    if type(selected_cases) is not dict or set(selected_cases) != set(CASES):
        raise ValueError("composition must retain both independent image cases")
    for case, value in selected_cases.items():
        if (value.get("case") != case or value.get("requirement_id") != CASES[case]
                or value.get("provider_mode") != "controlled"
                or value.get("guide_to_contribution_proven") is not False
                or value.get("replay_additional_provider_calls") != 0
                or value.get("owned_runtime_resources_removed") is not True
                or len(value.get("model_effects", [])) != 2
                or len(value.get("trials", [])) != 1):
            raise ValueError("one-image case custody is incomplete")
    if (fixture.get("model_effects") != [effect for case in CASES for effect in selected_cases[case]["model_effects"]]
            or fixture.get("trials") != [trial for case in CASES for trial in selected_cases[case]["trials"]]):
        raise ValueError("aggregate custody differs from independent cases")
    if (
        fixture.get("schema_version")
        != "workstream.terminal_systems_composition_evidence.v1"
        or fixture.get("provider_mode") != "controlled"
        or fixture.get("guide_to_contribution_proven") is not False
        or fixture.get("replay_additional_provider_calls") != 0
        or fixture.get("owned_runtime_resources_removed") is not True
        or len(fixture.get("model_effects", [])) != 4
        or len(fixture.get("trials", [])) != 2
    ):
        raise ValueError("runtime/custody completion evidence is incomplete")


def combine_case_results(path: Path) -> dict:
    """Retain both one-image receipts without pretending their authority is shared."""
    cases = {case: read_json(path.with_name(path.stem + "-" + case + path.suffix)) for case in CASES}
    common = ("schema_version", "provider_mode", "guide_to_contribution_proven", "image",
              "profile", "projection", "runtime", "predecessor_material_exercised")
    first = cases["author"]
    if any(value.get(field) != first.get(field) for value in cases.values() for field in common):
        raise ValueError("one-image runtime identities differ")
    result = {field: first[field] for field in common}
    result.update(
        cases=cases,
        authority_manifest_digests={case: value["authority_manifest_digest"] for case, value in cases.items()},
        model_effects=[effect for value in cases.values() for effect in value["model_effects"]],
        trials=[trial for value in cases.values() for trial in value["trials"]],
        replay_additional_provider_calls=sum(value["replay_additional_provider_calls"] for value in cases.values()),
        owned_runtime_resources_removed=all(value["owned_runtime_resources_removed"] for value in cases.values()),
    )
    return result


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, sort_keys=True, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def verify_runtime(
    fixture: dict, config: dict, platform: str, cache: str, checker: str
) -> None:
    expected = {
        "runtime": "smolvm",
        "isolation_mode": "smol-microvm",
        "platform_identity_digest": platform,
        "offline_cache_digest": cache,
        "engine_digest": config["smol"]["binary_sha256"],
        "guest_digest": config["smol"]["guest_sha256"],
        "filesystem_tool_digest": config["trial_runtime"]["filesystem_tool_digest"],
        "launcher_digest": config["trial_runtime"]["trusted_launcher_digest"],
        "builder_image_id": config["trial_runtime"]["builder_image_id"],
        "outer_configuration_digest": config["trial_runtime"][
            "outer_runtime_config_digest"
        ],
        "child_configuration_digest": config["trial_runtime"][
            "outer_runtime_config_digest"
        ],
    }
    if (
        any(
            fixture.get("runtime", {}).get(key) != value
            for key, value in expected.items()
        )
        or fixture.get("image", {}).get("digest") != checker
    ):
        raise ValueError("executed runtime identity differs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--node-config", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--platform-identity", required=True)
    parser.add_argument("--cache-digest", required=True)
    parser.add_argument("--checker-digest", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    for path in (args.root, args.evidence):
        if (
            not path.is_absolute()
            or path.resolve() != path
            or path.exists()
            or path.is_symlink()
        ):
            parser.error("root and evidence must be fresh canonical absolute paths")
    args.evidence.mkdir(mode=0o700)
    outcome = {
        "source_head": args.expected_head,
        "source_tree": args.expected_tree,
        "status": "failed",
        "provider_mode": "controlled",
    }
    try:
        verify_source(ROOT, args.expected_head, args.expected_tree)
        config = read_json(args.node_config)
        outcome["node_config_sha256"] = digest(args.node_config)
        manifest = read_json(args.build_manifest)
        verify_build(
            manifest, config, args.service, args.expected_head, args.expected_tree
        )
        if (config["runtime"], config["isolation_mode"]) != ("smolvm", "smol-microvm"):
            raise ValueError("qualification requires Smol")
        if not Path("/dev/kvm").exists():
            raise ValueError("KVM is unavailable")
        args.root.mkdir(mode=0o700)
        metadata = args.evidence / "metadata.json"
        junit = args.evidence / "junit.xml"
        fixture = args.evidence / "fixture-summary.json"
        environment = os.environ.copy()
        for key, value in {
            "NODE_CONFIG": args.node_config,
            "SERVICE": args.service,
            "ROOT": args.root,
            "SUMMARY_PATH": fixture,
            "PLATFORM_IDENTITY": args.platform_identity,
            "CACHE_DIGEST": args.cache_digest,
            "CHECKER_DIGEST": args.checker_digest,
        }.items():
            environment["WORKSTREAM_TS_SMOL_" + key] = str(value)
        environment["PYTHONPATH"] = ".:tests"
        command = [
            str(args.python),
            "scripts/run_isolated_tests.py",
            "--metadata-json",
            str(metadata),
            "--timeout-seconds",
            "1200",
            "--lane",
            "trial_composition",
            "--tree-sha",
            args.expected_head,
            "--",
            str(args.python),
            "-m",
            "pytest",
            "-c",
            "pyproject.toml",
            "-vv",
            "-x",
            "-p",
            "conftest",
            "-p",
            "tests.checkers.external.conftest",
            "-o",
            "faulthandler_timeout=120",
            "-o",
            "junit_family=xunit2",
            "--junitxml",
            str(junit),
            "../external_checkers/workstream-checker-service/tests/terminal_systems_smol_composition.py",
        ]
        with (args.evidence / "composition.log").open("x") as log:
            result = subprocess.run(
                command,
                cwd=ROOT / "backend",
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        outcome["test_exit_code"] = result.returncode
        if result.returncode:
            raise ValueError(
                "composition failed; retained composition.log contains the failure"
            )
        verify_source(ROOT, args.expected_head, args.expected_tree)
        verify_build(
            manifest, config, args.service, args.expected_head, args.expected_tree
        )
        if digest(args.node_config) != outcome["node_config_sha256"]:
            raise ValueError("node config changed")
        fixture_facts = combine_case_results(fixture)
        write_new(fixture, fixture_facts)
        verify_results(junit, read_json(metadata), fixture_facts, args.expected_head)
        verify_runtime(
            fixture_facts,
            config,
            args.platform_identity,
            args.cache_digest,
            args.checker_digest,
        )
        outcome.update(
            status="passed",
            artifacts={
                name: digest(args.evidence / name)
                for name in (
                    "composition.log",
                    "junit.xml",
                    "metadata.json",
                    "fixture-summary.json",
                    "fixture-summary-author.json",
                    "fixture-summary-runtime.json",
                )
            },
        )
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
        ET.ParseError,
    ) as error:
        outcome["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        write_new(args.evidence / "result.json", outcome)


if __name__ == "__main__":
    raise SystemExit(main())
