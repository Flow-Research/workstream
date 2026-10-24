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
import time
from typing import Any
from uuid import UUID


COMPOSE_PATH = Path(__file__).with_name("compose.yml")
INFERENCE_COMPOSE_PATH = Path(__file__).with_name("compose.inference.yml")
SCRATCH_ROOT = Path("/var/lib/workstream/scratch")
SOCKET_ROOT = Path("/var/lib/workstream/checker-runtime")
SOCKET_PATH = SOCKET_ROOT / "checker.sock"
INTAKE_SOCKET_ROOT = Path("/var/lib/workstream/intake-runtime")
INTAKE_SOCKET_PATH = INTAKE_SOCKET_ROOT / "checker.sock"
INTAKE_DIGEST_KEYS = ("WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST", "WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST")
GUIDE_SOCKET_ROOT = Path("/var/lib/workstream/guide-runtime")
GUIDE_SOCKET_PATH = GUIDE_SOCKET_ROOT / "guide.sock"
GUIDE_PARSER_UID = 10002
GUIDE_PARSER_GID = 10001
DOCKER_SOCKET = Path("/var/run/docker.sock")
ROLES_ANYWHERE_CERTIFICATE_TARGET = Path(
    "/run/workstream-roles-anywhere/certificate.pem"
)
ROLES_ANYWHERE_PRIVATE_KEY_TARGET = Path(
    "/run/workstream-roles-anywhere/private-key.pem"
)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_REFERENCE = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}\Z")
ENVIRONMENT_KEY = re.compile(r"[A-Z][A-Z0-9_]*\Z")

BASE_SECRET_FILE_KEYS = (
    "WORKSTREAM_DATABASE_URL_FILE",
    "WORKSTREAM_CELERY_BROKER_URL_FILE",
    "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE",
    "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE",
)
PROJECT_AGENT_SECRET_FILE_KEY = "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE"
SECRET_FILE_KEYS = (*BASE_SECRET_FILE_KEYS, PROJECT_AGENT_SECRET_FILE_KEY)
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
    "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE": (
        "project_agent_api_key",
        "/run/secrets/project_agent_api_key",
    ),
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
    ),
    "beat": (
        "WORKSTREAM_DATABASE_URL_FILE",
        "WORKSTREAM_CELERY_BROKER_URL_FILE",
    ),
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
    "WORKSTREAM_PROJECT_AGENT_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_BASE_URL",
)
FORBIDDEN_RENDERED_KEYS = tuple(
    key for key in FORBIDDEN_RELEASE_KEYS if key != "WORKSTREAM_DEBUG"
)
EXACT_RELEASE_VALUES = {
    "WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD": {"roles-anywhere"},
    "WORKSTREAM_TOKEN_INTROSPECTION_MODE": {"disabled"},
    "WORKSTREAM_PROJECT_AGENT_RUNTIME": {
        "openai_agents_sdk",
        "omnicore_agent",
        "manager_authored",
    },
}
PROJECT_AGENT_LIMIT_KEYS = (
    "WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS",
    "WORKSTREAM_PROJECT_AGENT_MAX_MANIFEST_BYTES",
    "WORKSTREAM_PROJECT_AGENT_MAX_DOCUMENTS",
    "WORKSTREAM_PROJECT_AGENT_MAX_DOCUMENT_BYTES",
    "WORKSTREAM_PROJECT_AGENT_MAX_TOTAL_DOCUMENT_BYTES",
    "WORKSTREAM_PROJECT_AGENT_MAX_TURNS",
    "WORKSTREAM_PROJECT_AGENT_MAX_TOOL_CALLS",
    "WORKSTREAM_PROJECT_AGENT_MAX_TOOL_OUTPUT_CHARACTERS",
)
PROJECT_AGENT_CONFIGURATION_KEYS = (
    "WORKSTREAM_PROJECT_AGENT_RUNTIME",
    "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER",
    "WORKSTREAM_PROJECT_AGENT_MODEL",
    "WORKSTREAM_PROJECT_AGENT_MODEL_API",
    "WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS",
    *PROJECT_AGENT_LIMIT_KEYS,
)
PROJECT_AGENT_RUNTIME_OPTION_BOUNDS = {
    "request_timeout_seconds": (1, 1800),
    "maximum_retries": (0, 5),
    "retry_backoff_multiplier": (1, 4),
    "retry_initial_delay_seconds": (1, 30),
    "retry_max_delay_seconds": (1, 120),
    "circuit_failure_threshold": (1, 20),
    "circuit_cooldown_seconds": (1, 600),
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
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_TRUST_ANCHOR_ARN",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_TRUST_ANCHOR_SHA256",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PROFILE_ARN",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PROFILE_SHA256",
)
ROLES_ANYWHERE_HOST_FILE_KEYS = (
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_CERTIFICATE_HOST_FILE",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_PRIVATE_KEY_HOST_FILE",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_READINESS_CERTIFICATE_HOST_FILE",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_READINESS_PRIVATE_KEY_HOST_FILE",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_NEGATIVE_CERTIFICATE_HOST_FILE",
    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_NEGATIVE_PRIVATE_KEY_HOST_FILE",
)
PROOF_SERVICES = {
    "aws-proof-runtime": "runtime_immutability",
    "aws-proof-readiness": "readiness",
    "aws-proof-negative": "negative_access",
    "aws-proof-coordinate": "coordinate",
}
PROOF_GROUP_TIMEOUT_SECONDS = 120.0
PROOF_CLEANUP_RESERVE_SECONDS = 10.0
PROOF_INNER_KILL_AFTER_SECONDS = 5
PROOF_TIMEOUT_RETURN_CODE = 124
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
    *PROJECT_AGENT_CONFIGURATION_KEYS,
    *INTAKE_DIGEST_KEYS,
    *ROLES_ANYWHERE_HOST_FILE_KEYS,
    *AWS_S3_EVIDENCE_KEYS,
    *TIMEOUT_KEYS,
    *BASE_SECRET_FILE_KEYS,
)
OPTIONAL_RELEASE_KEYS = (
    "WORKSTREAM_API_HOST_PORT",
    "WORKSTREAM_CELERY_WORKER_CONCURRENCY",
    "WORKSTREAM_OBSERVABILITY_LOG_LEVEL",
    "WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT",
    "WORKSTREAM_OBSERVABILITY_TRACE_SAMPLE_RATIO",
    PROJECT_AGENT_SECRET_FILE_KEY,
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
            raise PreflightError(
                f"release environment line {number} has an invalid key"
            )
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
        raise PreflightError(
            f"release setting must be a finite positive number: {key}"
        ) from exc
    if not value.is_finite() or value <= 0:
        raise PreflightError(f"release setting must be a finite positive number: {key}")
    return value


def validate_environment(values: dict[str, str]) -> None:
    """Validate only invariants introduced by the hosted release profile."""
    unknown = sorted(set(values) - RELEASE_KEYS)
    if unknown:
        raise PreflightError(
            f"release environment contains an unsupported key: {unknown[0]}"
        )
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
    for key in INTAKE_DIGEST_KEYS:
        if not DIGEST.fullmatch(values[key]):
            raise PreflightError(f"trusted intake requires a pinned digest: {key}")
    for key in FORBIDDEN_RELEASE_KEYS:
        if values.get(key):
            raise PreflightError(
                f"development or static credential setting is forbidden: {key}"
            )
    for key, allowed in EXACT_RELEASE_VALUES.items():
        if _required(values, key) not in allowed:
            raise PreflightError(f"unsupported release setting: {key}")
    for key in TIMEOUT_KEYS:
        _positive_decimal(values, key)
    for key in PROJECT_AGENT_LIMIT_KEYS:
        _positive_id(values, key)
    if (
        _positive_id(values, "WORKSTREAM_RUNTIME_UID") != 10001
        or _positive_id(values, "WORKSTREAM_RUNTIME_GID") != GUIDE_PARSER_GID
    ):
        raise PreflightError("hosted backend runtime identity must be 10001:10001")
    runtime = values["WORKSTREAM_PROJECT_AGENT_RUNTIME"]
    provider = values["WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER"]
    model_api = values["WORKSTREAM_PROJECT_AGENT_MODEL_API"]
    model = values["WORKSTREAM_PROJECT_AGENT_MODEL"]
    if runtime == "manager_authored":
        if (provider, model_api, model) != ("none", "none", "none"):
            raise PreflightError(
                "manager-authored project agent configuration is invalid"
            )
        if values.get(PROJECT_AGENT_SECRET_FILE_KEY):
            raise PreflightError(
                "manager-authored releases cannot select a provider credential"
            )
    else:
        _required(values, PROJECT_AGENT_SECRET_FILE_KEY)
        if provider not in {"openai", "openrouter"}:
            raise PreflightError("unsupported project agent model provider")
        if model_api not in {"chat_completions", "responses"}:
            raise PreflightError("unsupported project agent model API")
        if provider == "openrouter" and model_api != "chat_completions":
            raise PreflightError("OpenRouter hosted releases require chat_completions")
        if runtime == "omnicore_agent" and (provider, model_api) != (
            "openrouter",
            "chat_completions",
        ):
            raise PreflightError("OmniCoreAgent requires OpenRouter chat completions")
        if provider == "openrouter" and (
            ":" in model or model.casefold().startswith("openrouter/")
        ):
            raise PreflightError("OpenRouter model routing variants are unsupported")
    try:
        runtime_options = json.loads(values["WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS"])
    except json.JSONDecodeError as exc:
        raise PreflightError(
            "project agent runtime options must be valid JSON"
        ) from exc
    if not isinstance(runtime_options, dict):
        raise PreflightError("project agent runtime options must be a JSON object")
    if len(values["WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS"].encode("utf-8")) > 8192:
        raise PreflightError("project agent runtime options are unbounded")
    allowed_runtime_options = {
        *PROJECT_AGENT_RUNTIME_OPTION_BOUNDS,
        "retry_jitter",
    }
    if any(
        type(key) is not str or key not in allowed_runtime_options
        for key in runtime_options
    ):
        raise PreflightError("project agent runtime options are unsupported")
    for key, (minimum, maximum) in PROJECT_AGENT_RUNTIME_OPTION_BOUNDS.items():
        if key not in runtime_options:
            continue
        value = runtime_options[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise PreflightError("project agent runtime options are invalid")
    if (
        "retry_jitter" in runtime_options
        and type(runtime_options["retry_jitter"]) is not bool
    ):
        raise PreflightError("project agent runtime options are invalid")
    if runtime_options.get("retry_initial_delay_seconds", 1) > runtime_options.get(
        "retry_max_delay_seconds", 30
    ):
        raise PreflightError("project agent runtime options are invalid")
    if runtime in {"manager_authored", "omnicore_agent"} and runtime_options:
        raise PreflightError(
            "selected project agent runtime accepts no runtime options"
        )
    if not values["WORKSTREAM_TOKEN_ISSUER"].startswith("https://"):
        raise PreflightError("Flow issuer must use HTTPS")
    if not values["WORKSTREAM_TOKEN_JWKS_URL"].startswith("https://"):
        raise PreflightError("Flow JWKS URL must use HTTPS")
    endpoint = values.get("WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT", "")
    if endpoint and not endpoint.startswith("https://"):
        raise PreflightError("production observability endpoint must use HTTPS")
    identities = [Path(values[key]) for key in ROLES_ANYWHERE_HOST_FILE_KEYS]
    if any(not path.is_absolute() for path in identities):
        raise PreflightError("Roles Anywhere host identity paths must be absolute")
    if len(set(identities)) != len(identities):
        raise PreflightError("Roles Anywhere host identity paths must be distinct")


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
            raise PreflightError(
                f"checker configuration has an unsafe release value: {key}"
            )
    if config.get("architecture") not in {"amd64", "arm64"}:
        raise PreflightError(
            "checker architecture is unsupported by this release profile"
        )
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


def _secret_file_keys(values: dict[str, str]) -> tuple[str, ...]:
    if values["WORKSTREAM_PROJECT_AGENT_RUNTIME"] == "manager_authored":
        return BASE_SECRET_FILE_KEYS
    return SECRET_FILE_KEYS


def _role_secret_file_keys(role: str, values: dict[str, str]) -> tuple[str, ...]:
    keys = ROLE_SECRET_FILE_KEYS[role]
    if (
        role == "worker"
        and values["WORKSTREAM_PROJECT_AGENT_RUNTIME"] != "manager_authored"
    ):
        return (*keys, PROJECT_AGENT_SECRET_FILE_KEY)
    return keys


def validate_private_host_inputs(values: dict[str, str]) -> None:
    """Inspect metadata only; do not read application secret contents."""
    uid = _positive_id(values, "WORKSTREAM_RUNTIME_UID")
    gid = _positive_id(values, "WORKSTREAM_RUNTIME_GID")
    _private_metadata(SCRATCH_ROOT, kind="directory", uid=uid, gid=gid, mode=0o700)
    _private_metadata(SOCKET_ROOT, kind="directory", uid=uid, gid=gid, mode=0o700)
    _private_metadata(INTAKE_SOCKET_ROOT, kind="directory", uid=uid, gid=gid, mode=0o700)
    try:
        intake_socket = INTAKE_SOCKET_PATH.lstat()
    except OSError as exc:
        raise PreflightError("trusted intake socket is unavailable") from exc
    if (not stat.S_ISSOCK(intake_socket.st_mode)
            or intake_socket.st_uid != uid or intake_socket.st_gid != gid
            or stat.S_IMODE(intake_socket.st_mode) != 0o600 or intake_socket.st_nlink != 1):
        raise PreflightError("trusted intake socket identity is unsafe")
    _private_metadata(
        GUIDE_SOCKET_ROOT,
        kind="directory",
        uid=GUIDE_PARSER_UID,
        gid=GUIDE_PARSER_GID,
        mode=0o750,
    )
    try:
        guide_socket = GUIDE_SOCKET_PATH.lstat()
    except FileNotFoundError:
        guide_socket = None
    except OSError as exc:
        raise PreflightError("guide parser socket identity is unavailable") from exc
    if guide_socket is not None and (
        stat.S_ISLNK(guide_socket.st_mode)
        or not stat.S_ISSOCK(guide_socket.st_mode)
        or guide_socket.st_uid != GUIDE_PARSER_UID
        or guide_socket.st_gid != GUIDE_PARSER_GID
        or stat.S_IMODE(guide_socket.st_mode) != 0o660
        or guide_socket.st_nlink != 1
    ):
        raise PreflightError("guide parser socket has unsafe retained state")
    private_paths = [
        Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"]),
        *(Path(values[key]) for key in _secret_file_keys(values)),
        *(Path(values[key]) for key in ROLES_ANYWHERE_HOST_FILE_KEYS),
    ]
    for path in private_paths:
        _private_metadata(path, kind="file", uid=uid, gid=gid, mode=0o400)
    try:
        shared_roots = (
            SCRATCH_ROOT.resolve(strict=True),
            SOCKET_ROOT.resolve(strict=True),
            INTAKE_SOCKET_ROOT.resolve(strict=True),
            GUIDE_SOCKET_ROOT.resolve(strict=True),
        )
        resolved_paths = [path.resolve(strict=True) for path in private_paths]
    except (OSError, RuntimeError) as exc:
        raise PreflightError("private host input identity is unavailable") from exc
    if any(
        path.is_relative_to(root) for path in resolved_paths for root in shared_roots
    ):
        raise PreflightError("private host inputs must remain outside shared roots")
    try:
        identities = [path.stat() for path in private_paths]
    except OSError as exc:
        raise PreflightError("private host input identity is unavailable") from exc
    if any(
        os.path.samestat(left, right)
        for index, left in enumerate(identities)
        for right in identities[index + 1 :]
    ):
        raise PreflightError("private host inputs must be distinct files")
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


def _compose_file_arguments(values: dict[str, str]) -> list[str]:
    arguments = ["--file", str(COMPOSE_PATH)]
    if values["WORKSTREAM_PROJECT_AGENT_RUNTIME"] != "manager_authored":
        arguments.extend(("--file", str(INFERENCE_COMPOSE_PATH)))
    return arguments


def render_compose(environment_path: Path, values: dict[str, str]) -> dict[str, Any]:
    """Render Compose from non-secret values without emitting the result."""
    rendered = _run_json(
        [
            "docker",
            "compose",
            "--env-file",
            str(environment_path),
            *_compose_file_arguments(values),
            "--profile",
            "aws-proof",
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
    if not compose_arguments or compose_arguments[0] not in {
        "pull",
        "up",
        "ps",
    }:
        raise PreflightError("unsupported hosted Compose operation")
    try:
        completed = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(environment_path),
                *_compose_file_arguments(values),
                *compose_arguments,
            ],
            check=False,
            env=compose_environment(values),
        )
    except OSError as exc:
        raise PreflightError("hosted Compose operation could not start") from exc
    return completed.returncode


def run_shutdown(environment_path: Path, values: dict[str, str]) -> int:
    """Stop producers, drain the worker, then stop its isolated dependencies."""
    phases = (
        ["stop", "beat", "api"],
        ["stop", "--timeout", "7320", "worker"],
        ["stop", "guide-document-parser", "checker-service"],
    )
    for arguments in phases:
        try:
            completed = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(environment_path),
                    *_compose_file_arguments(values),
                    *arguments,
                ],
                check=False,
                env=compose_environment(values),
            )
        except OSError as exc:
            raise PreflightError("hosted Compose shutdown could not start") from exc
        if completed.returncode != 0:
            return completed.returncode
    return 0


def run_proof_group(
    environment_path: Path, values: dict[str, str], group_nonce: UUID
) -> int:
    """Run the fixed proof sequence within one bounded, cleanup-reserved window."""
    deadline = time.monotonic() + PROOF_GROUP_TIMEOUT_SECONDS
    for service, mode in PROOF_SERVICES.items():
        container_name = f"workstream-proof-{group_nonce.hex}-{service}"
        try:
            command_timeout = (
                deadline - time.monotonic() - PROOF_CLEANUP_RESERVE_SECONDS
            )
            if command_timeout <= PROOF_INNER_KILL_AFTER_SECONDS + 1:
                return PROOF_TIMEOUT_RETURN_CODE
            inner_timeout = max(
                1,
                int(command_timeout - PROOF_INNER_KILL_AFTER_SECONDS - 1),
            )
            completed = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(environment_path),
                    *_compose_file_arguments(values),
                    "--profile",
                    "aws-proof",
                    "run",
                    "--rm",
                    "--no-deps",
                    "--name",
                    container_name,
                    service,
                    "/usr/bin/timeout",
                    "--signal=TERM",
                    f"--kill-after={PROOF_INNER_KILL_AFTER_SECONDS}s",
                    f"{inner_timeout}s",
                    "python",
                    "-m",
                    "scripts.aws_artifact_provider_proof",
                    mode,
                    "--group-nonce",
                    str(group_nonce),
                ],
                check=False,
                env=compose_environment(values),
                timeout=command_timeout,
            )
        except subprocess.TimeoutExpired:
            return PROOF_TIMEOUT_RETURN_CODE
        except OSError as exc:
            raise PreflightError("hosted AWS proof job could not start") from exc
        finally:
            cleanup_timeout = min(
                PROOF_CLEANUP_RESERVE_SECONDS,
                max(0.0, deadline - time.monotonic()),
            )
            if cleanup_timeout > 0:
                try:
                    subprocess.run(
                        ["docker", "rm", "--force", container_name],
                        check=False,
                        env=compose_environment(values),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=cleanup_timeout,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass
        if completed.returncode != 0:
            return completed.returncode
    return 0


def _service_mounts(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    volumes = service.get("volumes")
    if not isinstance(volumes, list):
        return {}
    return {
        volume.get("target"): volume
        for volume in volumes
        if isinstance(volume, dict) and isinstance(volume.get("target"), str)
    }


def _validate_exact_bind_mounts(
    service_name: str,
    service: dict[str, Any],
    expected: dict[str, tuple[str, bool]],
) -> None:
    raw_mounts = service.get("volumes")
    if raw_mounts is None:
        raw_mounts = []
    mounts = _service_mounts(service)
    if (
        not isinstance(raw_mounts, list)
        or len(raw_mounts) != len(expected)
        or len(mounts) != len(expected)
        or set(mounts) != set(expected)
    ):
        raise PreflightError(
            f"{service_name} bind mounts differ from the release profile"
        )
    for target, (source, read_only) in expected.items():
        mount = mounts[target]
        if (
            mount.get("type") != "bind"
            or mount.get("source") != source
            or mount.get("read_only", False) is not read_only
        ):
            raise PreflightError(
                f"{service_name} bind mount differs from the release profile: {target}"
            )


def validate_compose(rendered: dict[str, Any], values: dict[str, str]) -> None:
    """Check the rendered release process and privilege topology."""
    services = rendered.get("services")
    if not isinstance(services, dict) or set(services) != {
        "api",
        "worker",
        "beat",
        "guide-document-parser",
        "checker-service",
        *PROOF_SERVICES,
    }:
        raise PreflightError(
            "release Compose services differ from the bounded topology"
        )
    for name, service in services.items():
        if not isinstance(service, dict) or service.get("build") is not None:
            raise PreflightError(f"release service cannot build at runtime: {name}")
        if "volumes_from" in service:
            raise PreflightError(
                f"release service must not inherit another service's volumes: {name}"
            )
        if "configs" in service:
            raise PreflightError(
                f"release service must not receive Compose configs: {name}"
            )
        image = service.get("image")
        if not isinstance(image, str) or not IMAGE_REFERENCE.fullmatch(image):
            raise PreflightError(f"release service image is mutable: {name}")
        if service.get("read_only") is not True:
            raise PreflightError(f"release service root filesystem is writable: {name}")
        if "ALL" not in service.get("cap_drop", []):
            raise PreflightError(f"release service retains Linux capabilities: {name}")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            raise PreflightError(f"release service allows new privileges: {name}")
        if name != "guide-document-parser":
            if service.get("cap_add"):
                raise PreflightError(f"release service adds Linux capabilities: {name}")
            user = service.get("user")
            if not isinstance(user, str) or not re.fullmatch(
                r"[1-9][0-9]*:[1-9][0-9]*", user
            ):
                raise PreflightError(
                    f"release service must use a numeric non-root identity: {name}"
                )
    runtime_identity = (
        f"{values['WORKSTREAM_RUNTIME_UID']}:{values['WORKSTREAM_RUNTIME_GID']}"
    )
    for name in {"api", "worker", "beat", "checker-service", *PROOF_SERVICES}:
        if services[name]["user"] != runtime_identity:
            raise PreflightError(
                f"release service has the wrong runtime identity: {name}"
            )
    if services["guide-document-parser"]["user"] != "0:0":
        raise PreflightError("guide parser has the wrong bootstrap identity")
    backend_image = services["api"]["image"]
    if (
        services["worker"]["image"] != backend_image
        or services["beat"]["image"] != backend_image
        or services["guide-document-parser"]["image"] != backend_image
    ):
        raise PreflightError(
            "API, worker, Beat and guide parser must use one exact backend image"
        )
    if any(services[name]["image"] != backend_image for name in PROOF_SERVICES):
        raise PreflightError("AWS proof jobs must use the exact backend image")
    if any(services[name].get("pull_policy") != "never" for name in PROOF_SERVICES):
        raise PreflightError(
            "AWS proof jobs must use the cached release image without pulling"
        )
    for name in (
        "api",
        "worker",
        "beat",
        "guide-document-parser",
        *PROOF_SERVICES,
    ):
        if services[name].get("entrypoint") is not None:
            raise PreflightError(f"backend image entrypoint is overridden: {name}")
    runtime_identity_mounts = {
        str(ROLES_ANYWHERE_CERTIFICATE_TARGET): (
            values[
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_CERTIFICATE_HOST_FILE"
            ],
            True,
        ),
        str(ROLES_ANYWHERE_PRIVATE_KEY_TARGET): (
            values[
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_PRIVATE_KEY_HOST_FILE"
            ],
            True,
        ),
    }
    shared_backend_mounts = {
        str(SCRATCH_ROOT): (str(SCRATCH_ROOT), False),
        str(SOCKET_ROOT): (str(SOCKET_ROOT), True),
        str(INTAKE_SOCKET_ROOT): (str(INTAKE_SOCKET_ROOT), True),
    }
    expected_mounts = {
        "checker-service": {
            "/etc/workstream/checker-service.json": (
                values["WORKSTREAM_CHECKER_CONFIG_FILE"],
                True,
            ),
            str(SCRATCH_ROOT): (str(SCRATCH_ROOT), True),
            str(SOCKET_ROOT): (str(SOCKET_ROOT), False),
            str(DOCKER_SOCKET): (str(DOCKER_SOCKET), False),
        },
        "api": shared_backend_mounts | runtime_identity_mounts,
        "worker": shared_backend_mounts
        | {str(GUIDE_SOCKET_ROOT): (str(GUIDE_SOCKET_ROOT), True)}
        | runtime_identity_mounts,
        "beat": {},
        "guide-document-parser": {
            str(GUIDE_SOCKET_ROOT): (str(GUIDE_SOCKET_ROOT), False),
        },
        "aws-proof-runtime": runtime_identity_mounts,
        "aws-proof-readiness": {
            str(ROLES_ANYWHERE_CERTIFICATE_TARGET): (
                values[
                    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_READINESS_CERTIFICATE_HOST_FILE"
                ],
                True,
            ),
            str(ROLES_ANYWHERE_PRIVATE_KEY_TARGET): (
                values[
                    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_READINESS_PRIVATE_KEY_HOST_FILE"
                ],
                True,
            ),
        },
        "aws-proof-negative": {
            str(ROLES_ANYWHERE_CERTIFICATE_TARGET): (
                values[
                    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_NEGATIVE_CERTIFICATE_HOST_FILE"
                ],
                True,
            ),
            str(ROLES_ANYWHERE_PRIVATE_KEY_TARGET): (
                values[
                    "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_NEGATIVE_PRIVATE_KEY_HOST_FILE"
                ],
                True,
            ),
        },
        "aws-proof-coordinate": {},
    }
    for name, mounts in expected_mounts.items():
        _validate_exact_bind_mounts(name, services[name], mounts)
    expected_secret_files = {
        secret_name: values[key]
        for key, (secret_name, _target) in SECRET_FILE_TARGETS.items()
        if key in _secret_file_keys(values)
    }
    rendered_secrets = rendered.get("secrets")
    if not isinstance(rendered_secrets, dict) or set(rendered_secrets) != set(
        expected_secret_files
    ):
        raise PreflightError("release Compose secrets differ from the release profile")
    for name, expected_file in expected_secret_files.items():
        secret = rendered_secrets[name]
        if (
            not isinstance(secret, dict)
            or secret.get("file") != expected_file
            or set(secret) - {"name", "file"}
        ):
            raise PreflightError(
                f"release Compose secret file differs from configuration: {name}"
            )
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
    parser = services["guide-document-parser"]
    parser_environment = parser.get("environment")
    if (
        parser.get("network_mode") != "none"
        or parser.get("ports")
        or parser.get("secrets")
        or parser.get("group_add")
        or parser.get("privileged") is True
        or parser.get("cap_drop") != ["ALL"]
        or parser.get("cap_add") != ["KILL", "SETGID", "SETUID"]
        or parser.get("devices")
        or parser.get("device_cgroup_rules")
        or parser.get("credential_spec")
        or parser.get("pid")
        or parser.get("ipc")
        or parser.get("uts")
        or parser.get("userns_mode")
        or parser.get("cgroup")
        or parser.get("use_api_socket") is True
        or parser.get("oom_kill_disable") is True
        or parser.get("security_opt") != ["no-new-privileges:true"]
        or parser.get("pull_policy") != "always"
        or parser.get("init") is not True
        or parser.get("restart") != "on-failure:5"
        or str(parser.get("mem_limit")) != "536870912"
        or str(parser.get("memswap_limit")) != "536870912"
        or str(parser.get("cpus")) not in {"1", "1.0"}
        or parser.get("pids_limit") != 64
        or parser.get("stop_grace_period") not in {"30s", "30.0s"}
        or parser_environment
        != {
            "WORKSTREAM_RELEASE_ROLE": "parser",
            "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET": str(GUIDE_SOCKET_PATH),
        }
        or parser.get("command")
        != [
            "python",
            "-m",
            "app.adapters.guide_document_tools.service",
            "--socket",
            str(GUIDE_SOCKET_PATH),
        ]
    ):
        raise PreflightError("guide parser isolation profile is invalid")
    parser_health = parser.get("healthcheck", {}).get("test")
    if parser_health != [
        "CMD",
        "python",
        "-m",
        "app.adapters.guide_document_tools.service",
        "--healthcheck",
        "--socket",
        str(GUIDE_SOCKET_PATH),
    ]:
        raise PreflightError("guide parser healthcheck is invalid")
    parser_tmpfs = parser.get("tmpfs")
    if (
        not isinstance(parser_tmpfs, list)
        or len(parser_tmpfs) != 1
        or not isinstance(parser_tmpfs[0], str)
        or not parser_tmpfs[0].startswith("/tmp:")
        or {
            "mode=0700",
            "uid=10002",
            "gid=10001",
            "size=268435456",
            "noexec",
            "nosuid",
            "nodev",
        }
        != set(parser_tmpfs[0].split(":", 1)[1].split(","))
    ):
        raise PreflightError("guide parser tmpfs is unbounded or unsafe")
    worker_dependencies = services["worker"].get("depends_on")
    if not isinstance(worker_dependencies, dict) or worker_dependencies.get(
        "guide-document-parser"
    ) != {"condition": "service_healthy", "required": True}:
        raise PreflightError("worker must wait for a healthy guide parser")
    worker = services["worker"]
    worker_command = worker.get("command")
    if (
        worker.get("stop_grace_period") not in {"7320s", "2h2m0s"}
        or not isinstance(worker_command, list)
        or "--pool=prefork" not in worker_command
        or any(
            value == "-Q" or str(value).startswith("--queues")
            for value in worker_command
        )
    ):
        raise PreflightError("project guide worker delivery profile is invalid")
    for name in ("aws-proof-runtime", "aws-proof-readiness", "aws-proof-negative"):
        service = services[name]
        if service.get("profiles") != ["aws-proof"]:
            raise PreflightError(f"{name} is not isolated behind the proof profile")
    coordinator = services["aws-proof-coordinate"]
    if coordinator.get("profiles") != ["aws-proof"]:
        raise PreflightError("AWS proof coordinator must remain credential-free")
    expected_roles = {
        "aws-proof-runtime": "WORKSTREAM_ARTIFACT_S3_RUNTIME_ROLE_ARN",
        "aws-proof-readiness": "WORKSTREAM_ARTIFACT_S3_READINESS_ROLE_ARN",
        "aws-proof-negative": "WORKSTREAM_ARTIFACT_S3_NEGATIVE_ROLE_ARN",
    }
    for name, role_key in expected_roles.items():
        environment = services[name].get("environment")
        if (
            not isinstance(environment, dict)
            or environment.get("WORKSTREAM_RELEASE_ROLE") != "proof"
            or environment.get("WORKSTREAM_DATABASE_URL_FILE")
            != "/run/secrets/database_url"
            or environment.get("WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_ROLE_ARN")
            != environment.get(role_key)
        ):
            raise PreflightError(f"{name} selects the wrong proof identity")
    coordinator_environment = coordinator.get("environment")
    if (
        not isinstance(coordinator_environment, dict)
        or coordinator_environment.get("WORKSTREAM_RELEASE_ROLE") != "proof"
        or coordinator_environment.get("WORKSTREAM_DATABASE_URL_FILE")
        != "/run/secrets/database_url"
    ):
        raise PreflightError("AWS proof coordinator environment is invalid")
    for name in PROOF_SERVICES:
        mounted = services[name].get("secrets")
        service_uid, service_gid = services[name]["user"].split(":", maxsplit=1)
        if (
            not isinstance(mounted, list)
            or len(mounted) != 1
            or not isinstance(mounted[0], dict)
            or mounted[0].get("source") != "database_url"
            or mounted[0].get("target") != "database_url"
            or mounted[0].get("uid") != service_uid
            or mounted[0].get("gid") != service_gid
            or mounted[0].get("mode") not in (0o400, "0400")
        ):
            raise PreflightError(f"{name} must receive only the database secret")
    environments: dict[str, dict[str, Any]] = {}
    for role in ROLE_SECRET_FILE_KEYS:
        environment = services[role].get("environment")
        if not isinstance(environment, dict):
            raise PreflightError(f"{role} release environment is unavailable")
        if environment.get("WORKSTREAM_RELEASE_ROLE") != role:
            raise PreflightError(f"{role} has an unsafe release role")
        required_file_keys = set(_role_secret_file_keys(role, values))
        for key, (_, target) in SECRET_FILE_TARGETS.items():
            if key in required_file_keys:
                if environment.get(key) != target:
                    raise PreflightError(
                        f"{role} lacks a required secret selector: {key}"
                    )
            elif key in environment:
                raise PreflightError(
                    f"{role} contains an unrelated secret selector: {key}"
                )
        mounted = services[role].get("secrets")
        if not isinstance(mounted, list):
            raise PreflightError(f"{role} release secrets are unavailable")
        expected_sources = {
            SECRET_FILE_TARGETS[key][0] for key in _role_secret_file_keys(role, values)
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
                if key not in SECRET_FILE_KEYS
                and key
                not in {
                    "WORKSTREAM_RELEASE_ROLE",
                    "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET",
                }
            }
        )
    if any(
        environment != common_environments[0] for environment in common_environments[1:]
    ):
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
        "WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD": "roles-anywhere",
        "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_CERTIFICATE_FILE": str(
            ROLES_ANYWHERE_CERTIFICATE_TARGET
        ),
        "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PRIVATE_KEY_FILE": str(
            ROLES_ANYWHERE_PRIVATE_KEY_TARGET
        ),
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(SCRATCH_ROOT),
        "WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT": str(SCRATCH_ROOT),
        "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET": str(SOCKET_PATH),
        "WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET": str(INTAKE_SOCKET_PATH),
        **{key: values[key] for key in INTAKE_DIGEST_KEYS},
    }
    for key, value in exact.items():
        if str(environment.get(key, "")).lower() != value:
            raise PreflightError(f"rendered release environment is unsafe: {key}")
    for name in ("api", "worker", "beat", *PROOF_SERVICES):
        service_environment = services[name].get("environment")
        if not isinstance(service_environment, dict):
            raise PreflightError(f"{name} release environment is unavailable")
        for key in PROJECT_AGENT_CONFIGURATION_KEYS:
            if str(service_environment.get(key, "")) != values[key]:
                raise PreflightError(
                    "rendered project agent configuration differs from release: "
                    f"{name}.{key}"
                )
    worker_environment = environments["worker"]
    if worker_environment.get("WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET") != str(
        GUIDE_SOCKET_PATH
    ):
        raise PreflightError("worker lacks the fixed guide parser socket")
    for name in ("api", "beat", "checker-service", *PROOF_SERVICES):
        service_environment = services[name].get("environment") or {}
        if not isinstance(service_environment, dict):
            raise PreflightError(f"{name} release environment is invalid")
        if "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET" in service_environment:
            raise PreflightError(f"{name} must not receive the guide parser socket")
        if "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE" in service_environment:
            raise PreflightError(
                f"{name} must not receive the project agent credential selector"
            )
    for name, service in services.items():
        service_environment = service.get("environment") or {}
        if not isinstance(service_environment, dict):
            raise PreflightError(f"{name} release environment is invalid")
        for key in (
            "WORKSTREAM_PROJECT_AGENT_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
        ):
            if key in service_environment:
                raise PreflightError(
                    f"secret value was interpolated into Compose: {name}.{key}"
                )
    if environment.get(
        "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_ROLE_ARN"
    ) != environment.get("WORKSTREAM_ARTIFACT_S3_RUNTIME_ROLE_ARN"):
        raise PreflightError(
            "hosted Roles Anywhere identity must select the runtime role"
        )
    for key in FORBIDDEN_RENDERED_KEYS:
        if environment.get(key):
            raise PreflightError(
                f"rendered release contains a forbidden setting: {key}"
            )
    for key in (
        "WORKSTREAM_DATABASE_URL",
        "WORKSTREAM_CELERY_BROKER_URL",
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET",
        "WORKSTREAM_PROJECT_AGENT_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
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
            raise PreflightError(
                "preloaded checker image identity differs from configuration"
            )



def validate_trusted_intake(values: dict[str, str]) -> None:
    """Use the release image's typed ART adapter without mounting credentials."""
    script = (
        "import asyncio,json; from dataclasses import asdict; from pathlib import Path; "
        "from app.core.config import Settings; "
        "from app.adapters.artifacts import trusted_submission_intake; "
        "s=Settings(artifact_intake_service_socket=Path("
        + repr(str(INTAKE_SOCKET_PATH)) + "),artifact_intake_image_digest="
        + repr(values[INTAKE_DIGEST_KEYS[0]]) + ",artifact_intake_config_digest="
        + repr(values[INTAKE_DIGEST_KEYS[1]]) + "); "
        "print(json.dumps(asdict(asyncio.run(trusted_submission_intake(s).health()))))"
    )
    health = _run_json(
        ["docker", "run", "--rm", "--network", "none", "--read-only",
         "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
         "--memory=512m", "--cpus=1", "--user",
         values["WORKSTREAM_RUNTIME_UID"] + ":" + values["WORKSTREAM_RUNTIME_GID"],
         "--mount", f"type=bind,src={INTAKE_SOCKET_ROOT},dst={INTAKE_SOCKET_ROOT},readonly",
         "--entrypoint", "python", values["WORKSTREAM_BACKEND_IMAGE"], "-c", script],
        failure="trusted Smol intake readiness failed",
        environment=compose_environment(values),
    )
    if (not isinstance(health, dict)
            or (health.get("runtime"), health.get("isolation_mode")) != ("smolvm", "smol-microvm")
            or health.get("image_digest") != values[INTAKE_DIGEST_KEYS[0]]
            or health.get("config_digest") != values[INTAKE_DIGEST_KEYS[1]]):
        raise PreflightError("trusted intake readiness identity differs")


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
        checker_config = load_checker_config(
            Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"])
        )
        validate_checker_config(checker_config, values)
        validate_compose(render_compose(args.env_file, values), values)
        if args.configuration_only:
            print(
                "configuration valid; host identity, runsc/cache, cloud, health and recovery checks skipped"
            )
            return 0
        validate_private_host_inputs(values)
        validate_docker_runtime(checker_config, values)
        validate_trusted_intake(values)
    except PreflightError as exc:
        print(f"hosted release preflight failed: {exc}", file=sys.stderr)
        return 1
    print("hosted release configuration and local runsc/cache prerequisites are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
