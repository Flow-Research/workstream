#!/usr/bin/env python3
"""Validate hosted-release topology without disclosing secret contents."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
from typing import Any


COMPOSE_PATH = Path(__file__).with_name("compose.yml")
SCRATCH_ROOT = Path("/var/lib/workstream/scratch")
SOCKET_ROOT = Path("/run/workstream-checker")
SOCKET_PATH = SOCKET_ROOT / "checker.sock"
DOCKER_SOCKET = Path("/var/run/docker.sock")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_REFERENCE = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}\Z")
ENVIRONMENT_KEY = re.compile(r"[A-Z][A-Z0-9_]*\Z")

SECRET_FILE_KEYS = (
    "WORKSTREAM_DATABASE_URL_FILE",
    "WORKSTREAM_CELERY_BROKER_URL_FILE",
    "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE",
    "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE",
    "OPENAI_API_KEY_FILE",
)
SECRET_FILE_TARGETS = {
    "WORKSTREAM_DATABASE_URL_FILE": ("database_url", "/run/secrets/database_url"),
    "WORKSTREAM_CELERY_BROKER_URL_FILE": (
        "celery_broker_url",
        "/run/secrets/celery_broker_url",
    ),
    "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE": (
        "api_rate_limit_key",
        "/run/secrets/api_rate_limit_key",
    ),
    "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE": (
        "pagination_cursor_hmac",
        "/run/secrets/pagination_cursor_hmac",
    ),
    "OPENAI_API_KEY_FILE": ("openai_api_key", "/run/secrets/openai_api_key"),
}
ROLE_SECRET_FILE_KEYS = {
    "api": (
        "WORKSTREAM_DATABASE_URL_FILE",
        "WORKSTREAM_CELERY_BROKER_URL_FILE",
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE",
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE",
    ),
    "worker": (
        "WORKSTREAM_DATABASE_URL_FILE",
        "WORKSTREAM_CELERY_BROKER_URL_FILE",
        "OPENAI_API_KEY_FILE",
    ),
    "beat": ("WORKSTREAM_CELERY_BROKER_URL_FILE",),
}
FORBIDDEN_RELEASE_KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_CONFIG_FILE",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_ROLE_ARN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "WORKSTREAM_ARTIFACT_LOCAL_ROOT",
    "WORKSTREAM_DEV_AUTH_TOKEN",
    "WORKSTREAM_DEV_AUTH_SUBJECT",
    "WORKSTREAM_DEV_AUTH_ISSUER",
    "WORKSTREAM_DEBUG",
    "WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET",
    "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID",
    "WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY",
    "WORKSTREAM_ARTIFACT_S3_SESSION_TOKEN",
    "WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL",
)
FORBIDDEN_RENDERED_KEYS = tuple(
    key for key in FORBIDDEN_RELEASE_KEYS if key != "WORKSTREAM_DEBUG"
)
EXACT_RELEASE_VALUES = {
    "WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD": {"iam-role"},
    "WORKSTREAM_TOKEN_INTROSPECTION_MODE": {"disabled"},
}
TIMEOUT_KEYS = (
    "WORKSTREAM_ARTIFACT_S3_CONNECT_TIMEOUT_SECONDS",
    "WORKSTREAM_ARTIFACT_S3_READ_TIMEOUT_SECONDS",
    "WORKSTREAM_ARTIFACT_S3_WRITE_TIMEOUT_SECONDS",
    "WORKSTREAM_ARTIFACT_S3_POOL_TIMEOUT_SECONDS",
    "WORKSTREAM_ARTIFACT_S3_OPERATION_TOTAL_TIMEOUT_SECONDS",
    "WORKSTREAM_ARTIFACT_COMPLETE_READ_DEADLINE_SECONDS",
    "WORKSTREAM_ARTIFACT_TERMINAL_PERSISTENCE_MARGIN_SECONDS",
)
AWS_S3_EVIDENCE_KEYS = (
    "WORKSTREAM_RELEASE_ID",
    "WORKSTREAM_ARTIFACT_S3_RUNTIME_ROLE_ARN",
    "WORKSTREAM_ARTIFACT_S3_RUNTIME_TRUST_POLICY_SHA256",
    "WORKSTREAM_ARTIFACT_S3_RUNTIME_POLICY_ARN",
    "WORKSTREAM_ARTIFACT_S3_READINESS_ROLE_ARN",
    "WORKSTREAM_ARTIFACT_S3_READINESS_TRUST_POLICY_SHA256",
    "WORKSTREAM_ARTIFACT_S3_READINESS_POLICY_ARN",
    "WORKSTREAM_ARTIFACT_S3_NEGATIVE_ROLE_ARN",
    "WORKSTREAM_ARTIFACT_S3_NEGATIVE_TRUST_POLICY_SHA256",
    "WORKSTREAM_ARTIFACT_S3_BOOTSTRAP_PRINCIPAL_ARN",
    "WORKSTREAM_ARTIFACT_S3_BUCKET_POLICY_SHA256",
)
REQUIRED_RELEASE_KEYS = (
    "COMPOSE_PROJECT_NAME",
    "WORKSTREAM_BACKEND_IMAGE",
    "WORKSTREAM_CHECKER_SERVICE_IMAGE",
    "WORKSTREAM_RUNTIME_UID",
    "WORKSTREAM_RUNTIME_GID",
    "WORKSTREAM_DOCKER_SOCKET_GID",
    "WORKSTREAM_TOKEN_ISSUER",
    "WORKSTREAM_TOKEN_AUDIENCE",
    "WORKSTREAM_TOKEN_JWKS_URL",
    "WORKSTREAM_TOKEN_ALGORITHMS",
    "WORKSTREAM_TOKEN_INTROSPECTION_MODE",
    "WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON",
    "WORKSTREAM_REQUIRED_HUMAN_SCOPE",
    "WORKSTREAM_REQUIRED_SERVICE_SCOPE",
    "WORKSTREAM_ARTIFACT_S3_REGION",
    "WORKSTREAM_ARTIFACT_S3_BUCKET",
    "WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX",
    "WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD",
    "WORKSTREAM_CHECKER_CONFIG_FILE",
    *AWS_S3_EVIDENCE_KEYS,
    *TIMEOUT_KEYS,
    *SECRET_FILE_KEYS,
)
OPTIONAL_RELEASE_KEYS = (
    "WORKSTREAM_API_HOST_PORT",
    "WORKSTREAM_CELERY_WORKER_CONCURRENCY",
    "WORKSTREAM_OBSERVABILITY_LOG_LEVEL",
    "WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT",
    "WORKSTREAM_OBSERVABILITY_TRACE_SAMPLE_RATIO",
)
RELEASE_KEYS = frozenset((*REQUIRED_RELEASE_KEYS, *OPTIONAL_RELEASE_KEYS))


class PreflightError(RuntimeError):
    """One release-specific invariant is not satisfied."""


def parse_environment(path: Path) -> dict[str, str]:
    """Parse the non-secret release environment without shell evaluation."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PreflightError("release environment file is unavailable") from exc
    values: dict[str, str] = {}
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise PreflightError(f"release environment line {number} is invalid")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not ENVIRONMENT_KEY.fullmatch(key) or key in values:
            raise PreflightError(f"release environment line {number} has an invalid key")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _required(values: dict[str, str], key: str) -> str:
    value = values.get(key, "")
    if not value:
        raise PreflightError(f"required release setting is missing: {key}")
    return value


def _positive_id(values: dict[str, str], key: str) -> int:
    raw = _required(values, key)
    if not raw.isascii() or not raw.isdecimal() or int(raw) <= 0:
        raise PreflightError(f"release identity must be a positive integer: {key}")
    return int(raw)


def _positive_decimal(values: dict[str, str], key: str) -> Decimal:
    raw = _required(values, key)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise PreflightError(f"release setting must be a finite positive number: {key}") from exc
    if not value.is_finite() or value <= 0:
        raise PreflightError(f"release setting must be a finite positive number: {key}")
    return value


def validate_environment(values: dict[str, str]) -> None:
    """Validate only invariants introduced by the hosted release profile."""
    unknown = sorted(set(values) - RELEASE_KEYS)
    if unknown:
        raise PreflightError(f"release environment contains an unsupported key: {unknown[0]}")
    for key in REQUIRED_RELEASE_KEYS:
        _required(values, key)
    for key in ("WORKSTREAM_BACKEND_IMAGE", "WORKSTREAM_CHECKER_SERVICE_IMAGE"):
        if not IMAGE_REFERENCE.fullmatch(_required(values, key)):
            raise PreflightError(f"release image must use repository@sha256: {key}")
    for key in (
        "WORKSTREAM_RUNTIME_UID",
        "WORKSTREAM_RUNTIME_GID",
        "WORKSTREAM_DOCKER_SOCKET_GID",
    ):
        _positive_id(values, key)
    for key in FORBIDDEN_RELEASE_KEYS:
        if values.get(key):
            raise PreflightError(f"development or static credential setting is forbidden: {key}")
    for key, allowed in EXACT_RELEASE_VALUES.items():
        if _required(values, key) not in allowed:
            raise PreflightError(f"unsupported release setting: {key}")
    for key in TIMEOUT_KEYS:
        _positive_decimal(values, key)
    if not values["WORKSTREAM_TOKEN_ISSUER"].startswith("https://"):
        raise PreflightError("Flow issuer must use HTTPS")
    if not values["WORKSTREAM_TOKEN_JWKS_URL"].startswith("https://"):
        raise PreflightError("Flow JWKS URL must use HTTPS")
    endpoint = values.get("WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT", "")
    if endpoint and not endpoint.startswith("https://"):
        raise PreflightError("production observability endpoint must use HTTPS")


def load_checker_config(path: Path) -> dict[str, Any]:
    """Load the non-secret runner configuration as one bounded JSON object."""
    try:
        if path.stat().st_size > 1024 * 1024:
            raise PreflightError("checker configuration is unbounded")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError("checker configuration is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise PreflightError("checker configuration must be an object")
    return value


def validate_checker_config(config: dict[str, Any], values: dict[str, str]) -> None:
    """Bind release selectors and cache identities to the existing runner."""
    expected = {
        "socket_path": str(SOCKET_PATH),
        "material_root": str(SCRATCH_ROOT),
        "docker_binary": "/usr/local/bin/docker",
        "runtime": "runsc",
        "isolation_mode": "gvisor",
        "operating_system": "linux",
        "sandbox_uid": _positive_id(values, "WORKSTREAM_RUNTIME_UID"),
        "sandbox_gid": _positive_id(values, "WORKSTREAM_RUNTIME_GID"),
    }
    for key, required in expected.items():
        if config.get(key) != required:
            raise PreflightError(f"checker configuration has an unsafe release value: {key}")
    if config.get("architecture") not in {"amd64", "arm64"}:
        raise PreflightError("checker architecture is unsupported by this release profile")
    cache = config.get("cache")
    if not isinstance(cache, list) or not cache:
        raise PreflightError("checker cache must contain at least one approved image")
    seen: set[str] = set()
    for entry in cache:
        if not isinstance(entry, dict):
            raise PreflightError("checker cache entry must be an object")
        digest = entry.get("platform_manifest_digest")
        image_id = entry.get("config_image_id")
        repository = entry.get("repository")
        if not isinstance(repository, str) or not repository or "@" in repository:
            raise PreflightError("checker cache repository is invalid")
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise PreflightError("checker cache manifest digest is invalid")
        if not isinstance(image_id, str) or not DIGEST.fullmatch(image_id):
            raise PreflightError("checker cache image ID is invalid")
        if digest in seen:
            raise PreflightError("checker cache manifest digest is duplicated")
        seen.add(digest)
        if entry.get("operating_system") != "linux":
            raise PreflightError("checker cache operating system must be linux")
        if entry.get("architecture") != config["architecture"]:
            raise PreflightError("checker cache architecture differs from the runner")


def _private_metadata(path: Path, *, kind: str, uid: int, gid: int, mode: int) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PreflightError(f"private {kind} is unavailable: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise PreflightError(f"private {kind} cannot be a symbolic link: {path}")
    expected_kind = stat.S_ISDIR if kind == "directory" else stat.S_ISREG
    if not expected_kind(metadata.st_mode):
        raise PreflightError(f"private {kind} has the wrong type: {path}")
    if metadata.st_uid != uid or metadata.st_gid != gid:
        raise PreflightError(f"private {kind} has the wrong owner: {path}")
    if stat.S_IMODE(metadata.st_mode) != mode:
        raise PreflightError(f"private {kind} has the wrong mode: {path}")
    if kind == "file" and metadata.st_size == 0:
        raise PreflightError(f"private file is empty: {path}")


def validate_private_host_inputs(values: dict[str, str]) -> None:
    """Inspect metadata only; do not read application secret contents."""
    uid = _positive_id(values, "WORKSTREAM_RUNTIME_UID")
    gid = _positive_id(values, "WORKSTREAM_RUNTIME_GID")
    _private_metadata(SCRATCH_ROOT, kind="directory", uid=uid, gid=gid, mode=0o700)
    _private_metadata(SOCKET_ROOT, kind="directory", uid=uid, gid=gid, mode=0o700)
    _private_metadata(
        Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"]),
        kind="file",
        uid=uid,
        gid=gid,
        mode=0o400,
    )
    for key in SECRET_FILE_KEYS:
        _private_metadata(Path(values[key]), kind="file", uid=uid, gid=gid, mode=0o400)
    try:
        docker_socket = DOCKER_SOCKET.stat()
    except OSError as exc:
        raise PreflightError("Docker socket is unavailable") from exc
    if not stat.S_ISSOCK(docker_socket.st_mode):
        raise PreflightError("Docker control path is not a socket")
    if docker_socket.st_gid != _positive_id(values, "WORKSTREAM_DOCKER_SOCKET_GID"):
        raise PreflightError("Docker socket group differs from release configuration")


def compose_environment(values: dict[str, str]) -> dict[str, str]:
    """Return the sole environment used for release Compose interpolation."""
    environment = {key: value for key, value in values.items() if key in RELEASE_KEYS}
    environment["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    environment["HOME"] = pwd.getpwuid(os.getuid()).pw_dir
    environment["DOCKER_HOST"] = f"unix://{DOCKER_SOCKET}"
    return environment


def _run_json(
    command: list[str], *, failure: str, environment: dict[str, str] | None = None
) -> Any:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise PreflightError(failure) from exc


def render_compose(environment_path: Path, values: dict[str, str]) -> dict[str, Any]:
    """Render Compose from non-secret values without emitting the result."""
    rendered = _run_json(
        [
            "docker",
            "compose",
            "--env-file",
            str(environment_path),
            "-f",
            str(COMPOSE_PATH),
            "config",
            "--format",
            "json",
        ],
        failure="release Compose configuration did not render",
        environment=compose_environment(values),
    )
    if not isinstance(rendered, dict):
        raise PreflightError("release Compose output is invalid")
    return rendered


def run_compose(
    environment_path: Path, values: dict[str, str], compose_arguments: list[str]
) -> int:
    """Run one documented Compose operation with no ambient interpolation."""
    if not compose_arguments or compose_arguments[0] not in {"pull", "up", "ps", "stop"}:
        raise PreflightError("unsupported hosted Compose operation")
    try:
        completed = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(environment_path),
                "--file",
                str(COMPOSE_PATH),
                *compose_arguments,
            ],
            check=False,
            env=compose_environment(values),
        )
    except OSError as exc:
        raise PreflightError("hosted Compose operation could not start") from exc
    return completed.returncode


def _service_mounts(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    volumes = service.get("volumes")
    if not isinstance(volumes, list):
        return {}
    return {
        volume.get("target"): volume
        for volume in volumes
        if isinstance(volume, dict) and isinstance(volume.get("target"), str)
    }


def validate_compose(rendered: dict[str, Any]) -> None:
    """Check the rendered release process and privilege topology."""
    services = rendered.get("services")
    if not isinstance(services, dict) or set(services) != {
        "api",
        "worker",
        "beat",
        "checker-service",
    }:
        raise PreflightError("release Compose services differ from the bounded topology")
    for name, service in services.items():
        if not isinstance(service, dict) or service.get("build") is not None:
            raise PreflightError(f"release service cannot build at runtime: {name}")
        image = service.get("image")
        if not isinstance(image, str) or not IMAGE_REFERENCE.fullmatch(image):
            raise PreflightError(f"release service image is mutable: {name}")
        if service.get("read_only") is not True:
            raise PreflightError(f"release service root filesystem is writable: {name}")
        if "ALL" not in service.get("cap_drop", []):
            raise PreflightError(f"release service retains Linux capabilities: {name}")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            raise PreflightError(f"release service allows new privileges: {name}")
        user = service.get("user")
        if (
            not isinstance(user, str)
            or not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", user)
        ):
            raise PreflightError(f"release service must use a numeric non-root identity: {name}")
    if len({service["user"] for service in services.values()}) != 1:
        raise PreflightError("release services must share the configured runtime identity")
    backend_image = services["api"]["image"]
    if services["worker"]["image"] != backend_image or services["beat"]["image"] != backend_image:
        raise PreflightError("API, worker and Beat must use one exact backend image")
    checker = services["checker-service"]
    if checker.get("network_mode") != "none" or checker.get("ports"):
        raise PreflightError("checker controller must be networkless and unpublished")
    checker_groups = checker.get("group_add")
    if (
        not isinstance(checker_groups, list)
        or len(checker_groups) != 1
        or not isinstance(checker_groups[0], str)
        or not re.fullmatch(r"[1-9][0-9]*", checker_groups[0])
    ):
        raise PreflightError("checker controller must use only the Docker socket group")
    checker_mounts = _service_mounts(checker)
    docker_mount = checker_mounts.get(str(DOCKER_SOCKET))
    material_mount = checker_mounts.get(str(SCRATCH_ROOT))
    socket_mount = checker_mounts.get(str(SOCKET_ROOT))
    config_mount = checker_mounts.get("/etc/workstream/checker-service.json")
    if docker_mount is None or docker_mount.get("source") != str(DOCKER_SOCKET):
        raise PreflightError("checker controller lacks the exact Docker socket")
    if material_mount is None or material_mount.get("source") != str(SCRATCH_ROOT):
        raise PreflightError("checker material path differs between host and controller")
    if material_mount.get("read_only") is not True:
        raise PreflightError("checker controller material view must be read-only")
    if socket_mount is None or socket_mount.get("source") != str(SOCKET_ROOT):
        raise PreflightError("checker controller lacks the exact private socket path")
    if socket_mount.get("read_only") is True:
        raise PreflightError("checker controller socket path must be writable")
    if config_mount is None or config_mount.get("read_only") is not True:
        raise PreflightError("checker controller config must be mounted read-only")
    for name in ("api", "worker"):
        mounts = _service_mounts(services[name])
        for path in (SCRATCH_ROOT, SOCKET_ROOT):
            mount = mounts.get(str(path))
            if mount is None or mount.get("source") != str(path):
                raise PreflightError(f"{name} does not preserve exact host path {path}")
            if mount.get("read_only") is True:
                raise PreflightError(f"{name} requires a writable private path {path}")
    environments: dict[str, dict[str, Any]] = {}
    for role in ROLE_SECRET_FILE_KEYS:
        environment = services[role].get("environment")
        if not isinstance(environment, dict):
            raise PreflightError(f"{role} release environment is unavailable")
        if environment.get("WORKSTREAM_RELEASE_ROLE") != role:
            raise PreflightError(f"{role} has an unsafe release role")
        required_file_keys = set(ROLE_SECRET_FILE_KEYS[role])
        for key, (_, target) in SECRET_FILE_TARGETS.items():
            if key in required_file_keys:
                if environment.get(key) != target:
                    raise PreflightError(f"{role} lacks a required secret selector: {key}")
            elif key in environment:
                raise PreflightError(f"{role} contains an unrelated secret selector: {key}")
        mounted = services[role].get("secrets")
        if not isinstance(mounted, list):
            raise PreflightError(f"{role} release secrets are unavailable")
        expected_sources = {
            SECRET_FILE_TARGETS[key][0] for key in ROLE_SECRET_FILE_KEYS[role]
        }
        service_uid, service_gid = services[role]["user"].split(":", maxsplit=1)
        if len(mounted) != len(expected_sources) or any(
            not isinstance(item, dict)
            or item.get("source") not in expected_sources
            or item.get("target") != item.get("source")
            or item.get("uid") != service_uid
            or item.get("gid") != service_gid
            or type(item.get("mode")) not in (int, str)
            or item.get("mode") not in (0o400, "0400")
            for item in mounted
        ):
            raise PreflightError(f"{role} mounted secrets differ from its release role")
        environments[role] = environment
    common_environments = []
    for environment in environments.values():
        common_environments.append(
            {
                key: value
                for key, value in environment.items()
                if key not in SECRET_FILE_KEYS and key != "WORKSTREAM_RELEASE_ROLE"
            }
        )
    if any(environment != common_environments[0] for environment in common_environments[1:]):
        raise PreflightError("backend roles must share the same non-secret environment")
    environment = environments["api"]
    exact = {
        "WORKSTREAM_AUTH_PROVIDER": "flow",
        "WORKSTREAM_DEBUG": "false",
        "WORKSTREAM_ENVIRONMENT": "production",
        "WORKSTREAM_ARTIFACT_STORE_BACKEND": "s3_compatible",
        "WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE": "aws_s3",
        "WORKSTREAM_ARTIFACT_S3_CREDENTIAL_MODE": "aws_workload_identity",
        "WORKSTREAM_ARTIFACT_S3_ADDRESSING_STYLE": "virtual",
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(SCRATCH_ROOT),
        "WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT": str(SCRATCH_ROOT),
        "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET": str(SOCKET_PATH),
    }
    for key, value in exact.items():
        if str(environment.get(key, "")).lower() != value:
            raise PreflightError(f"rendered release environment is unsafe: {key}")
    for key in FORBIDDEN_RENDERED_KEYS:
        if environment.get(key):
            raise PreflightError(f"rendered release contains a forbidden setting: {key}")
    for key in (
        "WORKSTREAM_DATABASE_URL",
        "WORKSTREAM_CELERY_BROKER_URL",
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET",
        "OPENAI_API_KEY",
    ):
        if key in environment:
            raise PreflightError(f"secret value was interpolated into Compose: {key}")


def validate_docker_runtime(config: dict[str, Any], values: dict[str, str]) -> None:
    """Check local runsc registration and exact preloaded image identities."""
    runtimes = _run_json(
        ["docker", "info", "--format", "{{json .Runtimes}}"],
        failure="Docker runtime inventory is unavailable",
        environment=compose_environment(values),
    )
    if not isinstance(runtimes, dict) or "runsc" not in runtimes:
        raise PreflightError("Docker does not report the required runsc runtime")
    for entry in config["cache"]:
        reference = f"{entry['repository']}@{entry['platform_manifest_digest']}"
        inspected = _run_json(
            ["docker", "image", "inspect", reference],
            failure="one configured checker image is not preloaded",
            environment=compose_environment(values),
        )
        if not isinstance(inspected, list) or len(inspected) != 1:
            raise PreflightError("checker image inspection is ambiguous")
        image = inspected[0]
        if (
            image.get("Id") != entry["config_image_id"]
            or image.get("Os") != entry["operating_system"]
            or image.get("Architecture") != entry["architecture"]
            or reference not in image.get("RepoDigests", [])
        ):
            raise PreflightError("preloaded checker image identity differs from configuration")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument(
        "--configuration-only",
        action="store_true",
        help="skip host files, Docker runsc and image-cache checks",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        values = parse_environment(args.env_file)
        validate_environment(values)
        checker_config = load_checker_config(Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"]))
        validate_checker_config(checker_config, values)
        validate_compose(render_compose(args.env_file, values))
        if args.configuration_only:
            print(
                "configuration valid; host identity, runsc/cache, cloud, health and recovery checks skipped"
            )
            return 0
        validate_private_host_inputs(values)
        validate_docker_runtime(checker_config, values)
    except PreflightError as exc:
        print(f"hosted release preflight failed: {exc}", file=sys.stderr)
        return 1
    print("hosted release configuration and local runsc/cache prerequisites are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
