"""Inspect disposable release images; never provision or contact a deployment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import resource
import stat
import subprocess
import sys
import tempfile
import tomllib
import uuid


SOURCE_PATHS = (
    "app",
    "alembic",
    "scripts/schema_baseline_sql.py",
    "uv.lock",
    "pyproject.toml",
    "alembic.ini",
)
MAX_FILES = 4096
MAX_BYTES = 64 * 1024 * 1024
OUTPUT_LIMIT = 2 * 1024 * 1024
LOADER = "/usr/local/bin/workstream-release-entrypoint"
SDK_ENVIRONMENT_MARKER = "/etc/workstream/project-agent-sdk-environment"
ROLES_ANYWHERE_HELPER = "/usr/local/bin/aws_signing_helper"
PROOF_COMMAND_TIMEOUT = "/usr/bin/timeout"
ROLES_ANYWHERE_HELPER_SHA256 = {
    "x86_64": "beec9ed1c492d93db809890f16713e3556353294b823c2184ad4e891f1b2b54d",
    "aarch64": "3d131aa888cd56da446f9c6bb460b1f0569f6c7edc74eae6193a2fe3928883ba",
}
CHECKER = "/usr/local/bin/workstream-checker-service"
CHECKER_ERROR = "external checker service unavailable: configuration unavailable\n"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def file_hash(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "proof input is not a regular file")
        require(info.st_size <= MAX_BYTES, "proof input exceeds byte limit")
        content = stream.read(MAX_BYTES + 1)
        require(
            len(content) == info.st_size, "proof input changed or exceeds byte limit"
        )
        return hashlib.sha256(content).hexdigest()


def source_inventory(root: Path, shared_root: Path | None = None) -> dict[str, str]:
    found: dict[str, str] = {}
    total = 0

    def visit(path: Path, base: Path, prefix: str = "") -> None:
        nonlocal total
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode), "source symlink refused")
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir()):
                visit(child, base, prefix)
            return
        require(stat.S_ISREG(info.st_mode), "source special file refused")
        total += info.st_size
        require(len(found) < MAX_FILES and total <= MAX_BYTES, "source inventory limit")
        found[prefix + str(path.relative_to(base))] = file_hash(path)

    for relative in SOURCE_PATHS:
        visit(root / relative, root)
    if shared_root is not None:
        visit(shared_root, shared_root, "shared-adapter/")
    return found


def run(
    command: list[str], *, data: bytes | None = None
) -> subprocess.CompletedProcess:
    """Bound client time and captured output, including noisy failing images."""

    def output_limit() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_LIMIT, OUTPUT_LIMIT))

    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(
            command,
            input=data,
            stdout=stdout,
            stderr=stderr,
            timeout=60,
            preexec_fn=output_limit,
            check=False,
        )
        stdout.seek(0)
        stderr.seek(0)
        result.stdout = stdout.read(OUTPUT_LIMIT + 1)
        result.stderr = stderr.read(OUTPUT_LIMIT + 1)
        require(len(result.stdout) < OUTPUT_LIMIT, "proof stdout exceeded limit")
        require(len(result.stderr) < OUTPUT_LIMIT, "proof stderr exceeded limit")
        return result


def checked(command: list[str]) -> bytes:
    result = run(command)
    require(result.returncode == 0, "proof command failed")
    return result.stdout


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def expected_packages(root: Path, sdk_environment: str) -> dict[str, str]:
    # uv owns dependency resolution. This only evaluates its exported markers.
    from packaging.requirements import Requirement

    exported = checked(
        [
            "uv",
            "export",
            "--project",
            str(root / "backend"),
            "--frozen",
            "--offline",
            "--extra",
            sdk_environment,
            "--no-dev",
            "--no-hashes",
            "--no-header",
            "--no-annotate",
            "--no-emit-project",
        ]
    ).decode()
    lock = tomllib.loads((root / "backend/uv.lock").read_text())
    project = tomllib.loads((root / "backend/pyproject.toml").read_text())["project"]
    expected = {canonical_name(project["name"]): project["version"]}
    for line in exported.splitlines():
        path, separator, marker = line.partition(";")
        if path.strip() == "../packages/external-services":
            shared = tomllib.loads((root / "packages/external-services/pyproject.toml").read_text())["project"]
            name, version = canonical_name(shared["name"]), shared["version"]
            require(name == "workstream-external-services", "shared adapter package identity differs")
            require(any(entry["name"] == name and entry["version"] == version
                        and entry.get("source") == {"directory": "../packages/external-services"}
                        for entry in lock["package"]), "shared adapter lock differs")
            line = f"{name}=={version}" + (";" + marker if separator else "")
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        name = canonical_name(requirement.name)
        versions = {
            entry["version"]
            for entry in lock["package"]
            if canonical_name(entry["name"]) == name
            and (not requirement.specifier or entry["version"] in requirement.specifier)
        }
        require(len(versions) == 1, "ambiguous locked package version")
        expected[name] = versions.pop()
    return expected


def installed_packages() -> dict[str, str]:
    packages = {}
    for dist in importlib.metadata.distributions():
        name = canonical_name(dist.metadata["Name"])
        require(name not in packages, "duplicate canonical distribution")
        packages[name] = dist.version
    return packages


def read_sdk_environment_marker() -> str:
    """Read the immutable root-owned SDK environment marker."""
    marker = Path(SDK_ENVIRONMENT_MARKER)
    marker_info = marker.lstat()
    require(
        stat.S_ISREG(marker_info.st_mode)
        and marker_info.st_uid == 0
        and marker_info.st_gid == 0
        and stat.S_IMODE(marker_info.st_mode) == 0o444,
        "SDK environment marker differs",
    )
    value = marker.read_text(encoding="utf-8").strip()
    require(value in {"agents", "omnicore"}, "SDK environment marker differs")
    return value


def inside_backend() -> dict:
    require(os.getuid() == 10001, "backend runtime user changed")
    require(stat.S_IMODE(Path(LOADER).lstat().st_mode) == 0o555, "loader mode changed")
    helper = Path(ROLES_ANYWHERE_HELPER)
    machine = platform.machine()
    require(machine in ROLES_ANYWHERE_HELPER_SHA256, "helper architecture unsupported")
    require(stat.S_IMODE(helper.lstat().st_mode) == 0o555, "helper mode changed")
    timeout = Path(PROOF_COMMAND_TIMEOUT)
    try:
        timeout_info = timeout.lstat()
    except OSError as exc:
        raise ValueError("proof timeout command unavailable") from exc
    require(
        stat.S_ISREG(timeout_info.st_mode) and os.access(timeout, os.X_OK),
        "proof timeout command unavailable",
    )
    helper_hash = file_hash(helper)
    require(
        helper_hash == ROLES_ANYWHERE_HELPER_SHA256[machine],
        "helper identity changed",
    )
    checked(["/bin/uv", "--no-cache", "pip", "check", "--python", sys.executable])
    sdk_environment = read_sdk_environment_marker()
    return {
        "source": source_inventory(
            Path("/workspace/backend"),
            Path(importlib.metadata.distribution("workstream-external-services").locate_file(
                "workstream_external_services")),
        ),
        "loader": file_hash(Path(LOADER)),
        "roles_anywhere_helper": helper_hash,
        "proof_command_timeout": True,
        "packages": installed_packages(),
        "sdk_environment": sdk_environment,
    }


def inside_checker() -> dict:
    require(os.getuid() == 10001, "checker runtime user changed")
    result = run([CHECKER, "/workstream-release-proof-absent.json"])
    return {
        "binary": file_hash(Path(CHECKER)),
        "docker": checked(["/usr/local/bin/docker", "--version"]).decode(),
        "status": result.returncode,
        "stdout": result.stdout.decode(),
        "stderr": result.stderr.decode(),
    }


def verify_backend(
    actual: dict,
    inventory: dict,
    packages: dict,
    loader: str,
    sdk_environment: str,
) -> None:
    require(actual["source"] == inventory, "backend source inventory differs")
    require(
        actual["packages"] == packages, "backend production package closure differs"
    )
    require(actual["loader"] == loader, "backend secret loader differs")
    require(
        actual["sdk_environment"] == sdk_environment,
        "backend SDK environment marker differs",
    )
    require(
        actual["roles_anywhere_helper"] in ROLES_ANYWHERE_HELPER_SHA256.values(),
        "Roles Anywhere helper differs",
    )
    require(
        actual["proof_command_timeout"] is True, "proof timeout command unavailable"
    )


def verify_checker(actual: dict) -> None:
    require(actual["status"] == 1, "checker startup status differs")
    require(
        actual["stdout"] == "" and actual["stderr"] == CHECKER_ERROR,
        "checker startup failure differs",
    )
    require(actual["docker"].startswith("Docker version 29.1.3,"), "Docker CLI differs")
    require(
        re.fullmatch(r"[a-f0-9]{64}", actual["binary"]) is not None,
        "checker binary identity missing",
    )


def image_metadata(image: str, role: str) -> str:
    actual = json.loads(checked(["docker", "image", "inspect", image]))
    require(len(actual) == 1, "image lookup is ambiguous")
    info = actual[0]
    config = info["Config"]
    require(
        info["Os"] == "linux" and info["Architecture"] in {"amd64", "arm64"},
        "image platform differs",
    )
    require(config["User"] == "workstream", "image default user differs")
    expected = (
        (
            [LOADER],
            [
                "python",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ],
        )
        if role == "backend"
        else ([CHECKER], ["/etc/workstream/checker-service.json"])
    )
    require(
        (config["Entrypoint"], config["Cmd"]) == expected,
        "image default command differs",
    )
    require(
        re.fullmatch(r"sha256:[a-f0-9]{64}", info["Id"]) is not None, "image ID invalid"
    )
    return info["Id"]


def owner_label(owner: str) -> str:
    require(re.fullmatch(r"[0-9]+-[0-9]+", owner) is not None, "invalid proof owner")
    return "workstream.release-proof=" + owner


def cleanup_containers(owner: str) -> None:
    command = [
        "docker",
        "ps",
        "--all",
        "--quiet",
        "--no-trunc",
        "--filter",
        "label=" + owner_label(owner),
    ]
    containers = checked(command).decode().splitlines()
    for container in containers:
        require(
            re.fullmatch(r"[a-f0-9]{64}", container) is not None,
            "invalid container identity",
        )
        checked(["docker", "rm", "--force", container])
    require(not checked(command).strip(), "proof containers remain after cleanup")


def inspect_image(image: str, role: str, owner: str) -> dict:
    name = "workstream-release-proof-" + uuid.uuid4().hex
    command = [
        "docker",
        "run",
        "--name",
        name,
        "--label",
        owner_label(owner),
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "1g",
        "--cpus",
        "2",
        "--pids-limit",
        "128",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m",
        "-i",
        "--entrypoint",
        "python",
        image,
        "-B",
        "-",
        "--inside",
        role,
    ]
    try:
        result = run(command, data=Path(__file__).read_bytes())
        if result.returncode != 0:
            # Only fixed verifier failures may cross the image boundary. Never
            # print arbitrary image stdout/stderr, paths or exception values.
            failures = {
                b"ValueError: proof command failed": "dependency check failed",
                b"ValueError: duplicate canonical distribution": "duplicate package metadata",
                b"ValueError: source symlink refused": "source symlink refused",
                b"ValueError: source special file refused": "source special file refused",
                b"ValueError: loader mode changed": "loader mode changed",
                b"ValueError: proof timeout command unavailable": (
                    "proof timeout command unavailable"
                ),
                b"ValueError: backend runtime user changed": "runtime user changed",
                b"ValueError: checker runtime user changed": "runtime user changed",
            }
            lines = result.stderr.splitlines()
            failure = failures.get(lines[-1] if lines else b"", "unclassified failure")
            raise ValueError(f"{role} release image inspection failed: {failure}")
        return json.loads(result.stdout)
    finally:
        # No --rm: successful and failed runs retain one exact owned cleanup target.
        checked(["docker", "rm", "--force", name])


def verify_backend_entrypoint(image: str, sdk_environment: str, owner: str) -> None:
    """Exercise neutral parser startup and fail-closed inference SDK binding."""
    require(sdk_environment in {"agents", "omnicore"}, "SDK environment differs")
    wrong_runtime = (
        "omnicore_agent" if sdk_environment == "agents" else "openai_agents_sdk"
    )
    cases = (
        (
            "parser",
            ["WORKSTREAM_RELEASE_ROLE=parser"],
            0,
            b"",
        ),
        (
            "mismatched-worker",
            [
                "WORKSTREAM_RELEASE_ROLE=worker",
                f"WORKSTREAM_PROJECT_AGENT_RUNTIME={wrong_runtime}",
            ],
            1,
            b"project agent runtime does not match the installed SDK environment\n",
        ),
    )
    for case, environment, expected_status, expected_stderr in cases:
        name = "workstream-release-proof-" + uuid.uuid4().hex
        command = [
            "docker",
            "run",
            "--name",
            name,
            "--label",
            owner_label(owner),
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--pids-limit",
            "32",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=1m",
        ]
        for setting in environment:
            command.extend(("--env", setting))
        command.extend((image, "/bin/true"))
        try:
            result = run(command)
            require(
                result.returncode == expected_status
                and result.stdout == b""
                and result.stderr == expected_stderr,
                f"backend {case} entrypoint behavior differs",
            )
        finally:
            checked(["docker", "rm", "--force", name])


def write_evidence(path: Path, evidence: dict) -> None:
    scope = evidence.get("proof_scope")
    require(scope in {"all-release-images", "native-hosted"}, "evidence scope differs")
    keys = {
        "proof_scope",
        "source_sha",
        "tree_sha",
        "backend_agents_image_id",
        "backend_omnicore_image_id",
        "backend_source_sha256",
        "backend_lock_sha256",
        "loader_sha256",
        "roles_anywhere_helper_sha256",
    }
    if scope == "all-release-images":
        keys.update(
            {"checker_image_id", "checker_lock_sha256", "checker_binary_sha256"}
        )
    require(
        set(evidence) == keys,
        "evidence shape differs",
    )
    for key, value in evidence.items():
        if key == "proof_scope":
            continue
        pattern = (
            r"sha256:[a-f0-9]{64}"
            if key.endswith("_image_id")
            else (
                r"[a-f0-9]{40}"
                if key in {"source_sha", "tree_sha"}
                else r"[a-f0-9]{64}"
            )
        )
        require(
            isinstance(value, str) and re.fullmatch(pattern, value) is not None,
            "evidence identity invalid",
        )
    payload = json.dumps(evidence, sort_keys=True).encode() + b"\n"
    require(len(payload) <= 65536, "evidence exceeds limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", choices=("backend", "checker"))
    parser.add_argument("--expected-head")
    parser.add_argument("--container-owner")
    parser.add_argument("--cleanup-owner")
    parser.add_argument("--backend-agents-image")
    parser.add_argument("--backend-omnicore-image")
    parser.add_argument("--checker-image")
    parser.add_argument(
        "--scope",
        choices=("all-release-images", "native-hosted"),
        default="all-release-images",
    )
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.cleanup_owner:
        cleanup_containers(args.cleanup_owner)
        return
    if args.inside:
        print(
            json.dumps(
                inside_backend() if args.inside == "backend" else inside_checker()
            )
        )
        return
    require(
        bool(args.backend_agents_image) and bool(args.backend_omnicore_image),
        "both backend SDK images are required",
    )
    require(
        bool(args.checker_image) == (args.scope == "all-release-images"),
        "checker image is required only for all-release-images scope",
    )
    owner_label(args.container_owner or "")
    root = Path(__file__).resolve().parents[1]
    head = checked(["git", "rev-parse", "HEAD"]).decode().strip()
    require(head == args.expected_head, "proof checkout differs from requested head")
    require(not checked(["git", "status", "--porcelain"]), "proof checkout is dirty")
    inventory = source_inventory(root / "backend", root / "packages/external-services/workstream_external_services")
    agents_packages = expected_packages(root, "agents")
    omnicore_packages = expected_packages(root, "omnicore")
    loader = file_hash(root / "docker/backend/release-entrypoint.sh")
    backend_agents_id = image_metadata(args.backend_agents_image, "backend")
    backend_omnicore_id = image_metadata(args.backend_omnicore_image, "backend")
    backend_agents = inspect_image(backend_agents_id, "backend", args.container_owner)
    verify_backend(backend_agents, inventory, agents_packages, loader, "agents")
    verify_backend_entrypoint(backend_agents_id, "agents", args.container_owner)
    backend_omnicore = inspect_image(
        backend_omnicore_id, "backend", args.container_owner
    )
    verify_backend(backend_omnicore, inventory, omnicore_packages, loader, "omnicore")
    verify_backend_entrypoint(backend_omnicore_id, "omnicore", args.container_owner)
    evidence = {
        "proof_scope": args.scope,
        "source_sha": head,
        "tree_sha": checked(["git", "rev-parse", "HEAD^{tree}"]).decode().strip(),
        "backend_agents_image_id": backend_agents_id,
        "backend_omnicore_image_id": backend_omnicore_id,
        "backend_source_sha256": hashlib.sha256(
            json.dumps(inventory, sort_keys=True).encode()
        ).hexdigest(),
        "backend_lock_sha256": inventory["uv.lock"],
        "loader_sha256": loader,
        "roles_anywhere_helper_sha256": backend_agents["roles_anywhere_helper"],
    }
    if args.scope == "all-release-images":
        checker_id = image_metadata(args.checker_image, "checker")
        checker = inspect_image(checker_id, "checker", args.container_owner)
        verify_checker(checker)
        evidence.update(
            checker_image_id=checker_id,
            checker_lock_sha256=file_hash(root / "external_checkers/Cargo.lock"),
            checker_binary_sha256=checker["binary"],
        )
    require(
        checked(["git", "rev-parse", "HEAD"]).decode().strip() == head,
        "proof checkout changed during inspection",
    )
    require(
        not checked(["git", "status", "--porcelain"]), "proof checkout became dirty"
    )
    write_evidence(args.evidence, evidence)
    print(
        f"{args.scope} image source, packages, metadata and bounded smoke checks passed."
    )


if __name__ == "__main__":
    main()
