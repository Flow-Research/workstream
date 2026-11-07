#!/usr/bin/env python3
"""Validate hosted-release topology without disclosing secret contents."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
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
from uuid import UUID, uuid4
from urllib.parse import urlsplit


COMPOSE_PATH = Path(__file__).with_name("compose.yml")
INFERENCE_COMPOSE_PATH = Path(__file__).with_name("compose.inference.yml")
TRIAL_COMPOSE_PATH = Path(__file__).with_name("compose.trials.yml")
TRIAL_MANIFEST_TARGET = Path("/etc/workstream/trial-authority.json")
TRIAL_KEYS = (
    "WORKSTREAM_CHECKER_TRIAL_AUTHORITY_MANIFEST_PATH",
    "WORKSTREAM_CHECKER_TRIAL_AUTHORITY_MANIFEST_DIGEST",
)
MODEL_OPENAI_COMPOSE_PATH = Path(__file__).with_name("compose.model-openai.yml")
MODEL_OPENROUTER_COMPOSE_PATH = Path(__file__).with_name("compose.model-openrouter.yml")
MCP_COMPOSE_PATH = Path(__file__).with_name("compose.mcp.yml")
DEMO_IDENTITY_COMPOSE_PATH = Path(__file__).with_name("compose.demo-identity.yml")
DEMO_IDENTITY_KEYS = (
    "DEMO_IDENTITY_IMAGE",
    "DEMO_IDENTITY_ISSUER",
    "DEMO_IDENTITY_AUDIENCE",
    "DEMO_IDENTITY_HOSTNAME",
    "DEMO_IDENTITY_DATA_DIR",
    "DEMO_IDENTITY_TLS_CERT_FILE",
    "DEMO_IDENTITY_TLS_KEY_FILE",
)
DEMO_IDENTITY_OPTIONAL_KEYS = (
    "DEMO_IDENTITY_PUBLISHED_BIND",
    "DEMO_IDENTITY_PUBLISHED_PORT",
)
GITHUB_COMPOSE_PATH = Path(__file__).with_name("compose.github.yml")
GITHUB_APP_KEYS = (
    "WORKSTREAM_GITHUB_APP_ID",
    "WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE",
    "WORKSTREAM_GITHUB_APP_INSTALLATION_ID",
)
DEFAULT_DEPLOYMENT_ROOT = Path("/var/lib/workstream")
DEFAULT_CHECKER_SERVICE_BINARY = Path("/opt/workstream/bin/workstream-checker-service")
INTAKE_DIGEST_KEYS = (
    "WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST",
    "WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST",
)


@dataclass(frozen=True)
class HostedPaths:
    root: Path

    @property
    def scratch(self) -> Path:
        return self.root / "scratch"

    @property
    def socket_root(self) -> Path:
        return self.root / "checker-runtime"

    @property
    def model_root(self) -> Path:
        return self.root / "model-runtime"

    @property
    def model_relays(self) -> Path:
        return self.root / "model-relays"

    @property
    def guide_root(self) -> Path:
        return self.root / "guide-runtime"

    @property
    def socket(self) -> Path:
        return self.socket_root / "checker.sock"

    @property
    def model_socket(self) -> Path:
        return self.model_root / "model.sock"

    @property
    def guide_socket(self) -> Path:
        return self.guide_root / "guide.sock"


def deployment_paths(values: dict[str, str]) -> HostedPaths:
    return HostedPaths(
        Path(values.get("WORKSTREAM_DEPLOYMENT_ROOT", str(DEFAULT_DEPLOYMENT_ROOT)))
    )


def checker_service_binary(values: dict[str, str]) -> Path:
    return Path(
        values.get(
            "WORKSTREAM_CHECKER_SERVICE_BINARY", str(DEFAULT_CHECKER_SERVICE_BINARY)
        )
    )


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
MODEL_PROXY_SECRET_FILE_KEYS = (
    "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE",
    "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE",
)
MODEL_PROVIDER_SECRET_FILE_KEYS = {
    "openai": "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE",
    "openrouter": "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE",
}
MODEL_PROVIDER_COMPOSE_PATHS = {
    "openai": MODEL_OPENAI_COMPOSE_PATH,
    "openrouter": MODEL_OPENROUTER_COMPOSE_PATH,
}
SECRET_FILE_KEYS = (
    *BASE_SECRET_FILE_KEYS,
    *MODEL_PROXY_SECRET_FILE_KEYS,
    GITHUB_APP_KEYS[1],
)
SECRET_FILE_TARGETS = {
    "WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE": (
        "github_app_private_key",
        "/run/secrets/github_app_private_key",
    ),
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
    "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE": (
        "model_proxy_openai_api_key",
        "/run/secrets/model_proxy_openai_api_key",
    ),
    "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE": (
        "model_proxy_openrouter_api_key",
        "/run/secrets/model_proxy_openrouter_api_key",
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
    "model-proxy": ("WORKSTREAM_DATABASE_URL_FILE",),
}
FORBIDDEN_RELEASE_KEYS = (
    "WORKSTREAM_GITHUB_APP_PRIVATE_KEY",
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
    "WORKSTREAM_MODEL_PROXY_ENABLED": {"true", "false"},
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
    "WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS",
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
    "WORKSTREAM_MODEL_PROXY_IMAGE",
    "WORKSTREAM_CHECKER_SERVICE_BINARY_SHA256",
    "WORKSTREAM_MODEL_PROXY_ENABLED",
    "WORKSTREAM_RUNTIME_UID",
    "WORKSTREAM_RUNTIME_GID",
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
    "WORKSTREAM_MCP_IMAGE",
    *DEMO_IDENTITY_KEYS,
    *DEMO_IDENTITY_OPTIONAL_KEYS,
    *GITHUB_APP_KEYS,
    "WORKSTREAM_DEPLOYMENT_ROOT",
    "WORKSTREAM_CHECKER_SERVICE_BINARY",
    *TRIAL_KEYS,
    "WORKSTREAM_API_HOST_PORT",
    "WORKSTREAM_CELERY_WORKER_CONCURRENCY",
    "WORKSTREAM_OBSERVABILITY_LOG_LEVEL",
    "WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT",
    "WORKSTREAM_OBSERVABILITY_TRACE_SAMPLE_RATIO",
    *MODEL_PROXY_SECRET_FILE_KEYS,
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


def validate_demo_identity_environment(values: dict[str, str]) -> None:
    selected = any(
        key in values for key in (*DEMO_IDENTITY_KEYS, *DEMO_IDENTITY_OPTIONAL_KEYS)
    )
    if not selected:
        return
    for key in DEMO_IDENTITY_KEYS:
        _required(values, key)
    if not IMAGE_REFERENCE.fullmatch(values["DEMO_IDENTITY_IMAGE"]):
        raise PreflightError("demo identity image must be digest-qualified")
    hostname = values["DEMO_IDENTITY_HOSTNAME"]
    if (
        len(hostname) > 253
        or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+",
            hostname,
        )
        or any(len(label) > 63 for label in hostname.split("."))
    ):
        raise PreflightError("demo identity hostname must be a canonical DNS name")
    try:
        origin = urlsplit(values["DEMO_IDENTITY_ISSUER"])
        port = origin.port
    except ValueError as exc:
        raise PreflightError("demo identity issuer origin is invalid") from exc
    expected = f"https://{hostname}" + (f":{port}" if port is not None else "")
    if values["DEMO_IDENTITY_ISSUER"] != expected or (
        port is not None and not 1 <= port <= 65535
    ):
        raise PreflightError("demo identity issuer must use its canonical HTTPS origin")
    if (
        values.get("WORKSTREAM_TOKEN_ISSUER") != values["DEMO_IDENTITY_ISSUER"]
        or values.get("WORKSTREAM_TOKEN_AUDIENCE") != values["DEMO_IDENTITY_AUDIENCE"]
        or values.get("WORKSTREAM_TOKEN_JWKS_URL")
        != values["DEMO_IDENTITY_ISSUER"] + "/jwks.json"
        or values.get("WORKSTREAM_TOKEN_ALGORITHMS") != "RS256"
    ):
        raise PreflightError("demo identity and Workstream verifier pins must match")
    if values.get("DEMO_IDENTITY_PUBLISHED_BIND", "127.0.0.1") != "127.0.0.1":
        raise PreflightError("demo identity publication must remain loopback")
    if values.get("DEMO_IDENTITY_PUBLISHED_PORT", "8443") != "8443":
        raise PreflightError("demo identity publication must use port 8443")
    paths = [values[key] for key in DEMO_IDENTITY_KEYS[-3:]]
    for raw in paths:
        path = Path(raw)
        if (
            not path.is_absolute()
            or path != path.resolve(strict=False)
            or any(c in raw for c in (",", "\n", "\r", "\0"))
        ):
            raise PreflightError("demo identity paths must be canonical absolute paths")
    if len(set(paths)) != 3 or any(
        Path(raw).is_relative_to(Path(paths[0])) for raw in paths[1:]
    ):
        raise PreflightError("demo identity state and TLS files must be separate")
    hosted = deployment_paths(values)
    shared_roots = (
        hosted.scratch,
        hosted.socket_root,
        hosted.guide_root,
        hosted.model_root,
        hosted.model_relays,
    )
    if any(
        Path(raw).is_relative_to(root) or root.is_relative_to(Path(raw))
        for raw in paths
        for root in shared_roots
    ):
        raise PreflightError(
            "demo identity custody must remain outside shared runtime roots"
        )


def validate_demo_identity_host_inputs(values: dict[str, str]) -> None:
    if not values.get("DEMO_IDENTITY_IMAGE"):
        return
    data = Path(values["DEMO_IDENTITY_DATA_DIR"])
    _private_metadata(data, kind="directory", uid=12001, gid=12001, mode=0o700)
    for name in ("accounts.db", "signer.pem"):
        _private_metadata(data / name, kind="file", uid=12001, gid=12001, mode=0o600)
    for key in ("DEMO_IDENTITY_TLS_CERT_FILE", "DEMO_IDENTITY_TLS_KEY_FILE"):
        _private_metadata(
            Path(values[key]), kind="file", uid=12001, gid=12001, mode=0o400
        )
    protected = [
        data / "signer.pem",
        data / "accounts.db",
        *(Path(values[key]) for key in DEMO_IDENTITY_KEYS[-2:]),
    ]
    if any(
        os.path.samestat(a.stat(), b.stat())
        for i, a in enumerate(protected)
        for b in protected[i + 1 :]
    ):
        raise PreflightError("demo identity private files must be distinct")
    backend_files = [
        Path(values[key])
        for key in (*BASE_SECRET_FILE_KEYS, *ROLES_ANYWHERE_HOST_FILE_KEYS)
        if values.get(key)
    ]
    try:
        if any(
            b.exists() and os.path.samestat(a.stat(), b.stat())
            for a in protected
            for b in backend_files
        ):
            raise PreflightError(
                "demo identity must not reuse Workstream private files"
            )
    except OSError as exc:
        raise PreflightError(
            "demo identity private file identity is unavailable"
        ) from exc


def validate_environment(values: dict[str, str]) -> None:
    """Validate only invariants introduced by the hosted release profile."""
    unknown = sorted(set(values) - RELEASE_KEYS)
    if unknown:
        raise PreflightError(
            f"release environment contains an unsupported key: {unknown[0]}"
        )
    if "WORKSTREAM_MCP_IMAGE" in values and not IMAGE_REFERENCE.fullmatch(values["WORKSTREAM_MCP_IMAGE"]):
        raise PreflightError("MCP image must be digest-qualified")
    validate_demo_identity_environment(values)
    github_app_id, github_key_file, github_installation_id = (
        values.get(key, "") for key in GITHUB_APP_KEYS
    )
    if bool(github_app_id) != bool(github_key_file) or (
        github_installation_id and not github_app_id
    ):
        raise PreflightError("GitHub App requires paired App ID and private key file")
    if github_app_id:
        _positive_id(values, GITHUB_APP_KEYS[0])
        if github_installation_id:
            _positive_id(values, GITHUB_APP_KEYS[2])
        path = Path(github_key_file)
        if (
            not path.is_absolute()
            or path != path.resolve(strict=False)
            or any(
                character in github_key_file for character in ("\n", "\r", "\0", ",")
            )
        ):
            raise PreflightError("GitHub App key file must use a canonical absolute path")
    root = deployment_paths(values).root
    binary = checker_service_binary(values)
    if values.get("WORKSTREAM_DEPLOYMENT_ROOT", str(root)) != str(root) or values.get(
        "WORKSTREAM_CHECKER_SERVICE_BINARY", str(binary)
    ) != str(binary):
        raise PreflightError("deployment paths must use canonical spelling")
    for path in (root, binary):
        if (
            not path.is_absolute()
            or path != path.resolve(strict=False)
            or any(character in str(path) for character in (",", "\n", "\r", "\0"))
            or len(path.parts) < 3
        ):
            raise PreflightError("deployment paths must be canonical absolute paths")
    if root == binary or binary.is_relative_to(root) or root.is_relative_to(binary):
        raise PreflightError("native service asset overlaps deployment data")
    for key in REQUIRED_RELEASE_KEYS:
        _required(values, key)
    for key in (
        "WORKSTREAM_BACKEND_IMAGE",
        "WORKSTREAM_MODEL_PROXY_IMAGE",
    ):
        if not IMAGE_REFERENCE.fullmatch(_required(values, key)):
            raise PreflightError(f"release image must use repository@sha256: {key}")
    for key in (
        "WORKSTREAM_RUNTIME_UID",
        "WORKSTREAM_RUNTIME_GID",
    ):
        _positive_id(values, key)
    for key in (*INTAKE_DIGEST_KEYS, "WORKSTREAM_CHECKER_SERVICE_BINARY_SHA256"):
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
    preparation_deadline = _positive_decimal(
        values, "WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS"
    )
    # The canonical Settings owner keeps ZIP inspection at 300s, cleanup at
    # 300s and scratch TTL at 3900s. No other scratch timing is configurable here.
    if not 300 < float(preparation_deadline) < 3600:
        raise PreflightError(
            "artifact preparation deadline must be greater than 300 and less than 3600 seconds"
        )
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
    else:
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
    model_proxy_enabled = values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true"
    if runtime != "manager_authored" and not model_proxy_enabled:
        raise PreflightError("inference setup requires the trusted model proxy")
    if model_proxy_enabled:
        configured_provider_keys = {
            key for key in MODEL_PROXY_SECRET_FILE_KEYS if values.get(key)
        }
        if runtime == "manager_authored":
            if not configured_provider_keys:
                raise PreflightError(
                    "enabled model proxy requires at least one provider credential"
                )
        else:
            selected_provider_key = MODEL_PROVIDER_SECRET_FILE_KEYS[provider]
            if selected_provider_key not in configured_provider_keys:
                raise PreflightError(
                    "inference setup requires its selected provider credential"
                )
    elif any(values.get(key) for key in MODEL_PROXY_SECRET_FILE_KEYS):
        raise PreflightError("disabled model proxy cannot select provider credentials")
    trial_path, trial_digest = (values.get(key, "") for key in TRIAL_KEYS)
    if bool(trial_path) != bool(trial_digest) or (
        trial_path
        and (
            not model_proxy_enabled
            or not Path(trial_path).is_absolute()
            or not DIGEST.fullmatch(trial_digest)
        )
    ):
        raise PreflightError(
            "trial authority requires the enabled proxy and one pinned manifest pair"
        )
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
    paths = deployment_paths(values)
    expected = {
        "socket_path": str(paths.socket),
        "material_root": str(paths.scratch),
        "runtime": "smolvm",
        "isolation_mode": "smol-microvm",
        "operating_system": "linux",
        "sandbox_uid": _positive_id(values, "WORKSTREAM_RUNTIME_UID"),
        "sandbox_gid": _positive_id(values, "WORKSTREAM_RUNTIME_GID"),
    }
    smol = config.get("smol")
    if not isinstance(smol, dict) or set(smol) != {
        "binary",
        "binary_sha256",
        "home",
        "guest_binary",
        "guest_sha256",
        "cgroup_root",
        "maximum_parallel",
        "maximum_storage_bytes",
    }:
        raise PreflightError("native Smol configuration is incomplete")
    for key in ("binary", "guest_binary", "home", "cgroup_root"):
        if not isinstance(smol[key], str) or not Path(smol[key]).is_absolute():
            raise PreflightError("native Smol path is invalid")
    if len(os.fsencode(smol["home"])) > 59:
        raise PreflightError("native Smol home exceeds the 59-byte socket path budget")
    for key in ("binary_sha256", "guest_sha256"):
        if not isinstance(smol[key], str) or not DIGEST.fullmatch(smol[key]):
            raise PreflightError("native Smol binary digest is invalid")
    for key in ("maximum_parallel", "maximum_storage_bytes"):
        if type(smol[key]) is not int or not 0 < smol[key] <= 2**64 - 1:
            raise PreflightError("native Smol capacity must be explicitly bounded")
    if Path(smol["home"]) == paths.scratch or Path(smol["home"]).is_relative_to(
        paths.scratch
    ):
        raise PreflightError("native Smol home must be separate from ART material")
    protected_inputs = [
        checker_service_binary(values),
        Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"]),
        Path(smol["binary"]),
        Path(smol["guest_binary"]),
        *(
            Path(values[key])
            for key in (*_secret_file_keys(values), *ROLES_ANYWHERE_HOST_FILE_KEYS)
        ),
    ]
    protected_inputs.extend(
        Path(image["smol"][key])
        for image in config.get("cache", [])
        if isinstance(image, dict) and isinstance(image.get("smol"), dict)
        for key in ("archive", "image_config")
        if isinstance(image["smol"].get(key), str)
    )
    if values.get(TRIAL_KEYS[0]):
        protected_inputs.append(Path(values[TRIAL_KEYS[0]]))
    if any(
        path.resolve(strict=False).is_relative_to(paths.root)
        for path in protected_inputs
    ):
        raise PreflightError(
            "private config, credentials and assets must remain outside deployment data"
        )
    model_proxy_enabled = values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true"
    expected.update(
        {
            "model_proxy_socket": str(paths.model_socket)
            if model_proxy_enabled
            else None,
            "model_relay_root": str(paths.model_relays)
            if model_proxy_enabled
            else None,
        }
    )
    for key, required in expected.items():
        if config.get(key) != required:
            raise PreflightError(
                f"checker configuration has an unsafe release value: {key}"
            )
    if config.get("architecture") != "amd64" or config.get("docker_binary") is not None:
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
        image = entry.get("smol")
        if not isinstance(image, dict) or set(image) != {
            "archive",
            "archive_sha256",
            "image_config",
        }:
            raise PreflightError("checker cache lacks native Smol assets")
        if not isinstance(image["archive_sha256"], str) or not DIGEST.fullmatch(
            image["archive_sha256"]
        ):
            raise PreflightError("checker cache archive digest is invalid")
        if any(
            not isinstance(image[key], str) or not Path(image[key]).is_absolute()
            for key in ("archive", "image_config")
        ):
            raise PreflightError("checker cache asset path is invalid")
        if digest in seen:
            raise PreflightError("checker cache manifest digest is duplicated")
        seen.add(digest)
        if entry.get("operating_system") != "linux":
            raise PreflightError("checker cache operating system must be linux")
        if entry.get("architecture") != config["architecture"]:
            raise PreflightError("checker cache architecture differs from the runner")

    intake = config.get("trusted_intake")
    if not isinstance(intake, dict) or set(intake) != {
        "platform_manifest_digest",
        "default_behavior_sha256",
        "storage_envelope",
    }:
        raise PreflightError("native node lacks the trusted intake purpose")
    selected = [
        entry
        for entry in cache
        if entry["platform_manifest_digest"] == values[INTAKE_DIGEST_KEYS[0]]
    ]
    if (
        len(selected) != 1
        or selected[0]["config_image_id"] != values[INTAKE_DIGEST_KEYS[1]]
        or intake["platform_manifest_digest"] != values[INTAKE_DIGEST_KEYS[0]]
        or not isinstance(intake["default_behavior_sha256"], str)
        or not DIGEST.fullmatch(intake["default_behavior_sha256"])
    ):
        raise PreflightError(
            "trusted intake cache identity differs from release configuration"
        )

    envelope = intake.get("storage_envelope")
    identities = {
        "archive_sha256": selected[0]["smol"]["archive_sha256"],
        "config_image_id": selected[0]["config_image_id"],
        "smol_binary_sha256": smol["binary_sha256"],
        "guest_sha256": smol["guest_sha256"],
    }
    bounds = {
        "maximum_entries",
        "maximum_path_bytes",
        "maximum_path_depth",
        "overhead_bytes",
        "maximum_storage_gib",
    }
    if (
        not isinstance(envelope, dict)
        or set(envelope) != set(identities) | bounds
        or any(envelope[key] != value for key, value in identities.items())
        or any(
            type(envelope[key]) is not int or not 0 < envelope[key] <= 2**64 - 1
            for key in bounds
        )
        or envelope["maximum_entries"] > 100_000
        or envelope["maximum_path_depth"] > 256
        or (envelope["maximum_storage_gib"] + 1) * 1024**3
        > smol["maximum_storage_bytes"]
    ):
        raise PreflightError(
            "trusted intake storage qualification is missing or differs"
        )

    for key, default in (("maximum_entries", 2000), ("maximum_path_bytes", 1024),
                         ("maximum_path_depth", 32)):
        setting = "WORKSTREAM_ARTIFACT_SUBMISSION_ZIP_" + key.upper()
        try:
            configured = int(values.get(setting, str(default)))
        except (TypeError, ValueError):
            raise PreflightError("trusted intake inspection limit is invalid") from None
        if not 0 < configured <= envelope[key]:
            raise PreflightError("trusted intake inspection limit exceeds storage qualification")

    # Qualification must cover supported inputs, independently of transient free space.
    internal_zip_bytes = 512 * 1024**2
    try:
        expanded = int(values.get("WORKSTREAM_ARTIFACT_SUBMISSION_ZIP_MAXIMUM_EXPANDED_BYTES",
                                  str(internal_zip_bytes)))
        ratio = int(values.get("WORKSTREAM_ARTIFACT_SUBMISSION_ZIP_MAXIMUM_COMPRESSION_RATIO", "100"))
    except (TypeError, ValueError):
        raise PreflightError("trusted intake expansion limits are invalid") from None
    if not 0 < expanded <= internal_zip_bytes or not 0 < ratio <= 2**64 - 1:
        raise PreflightError("trusted intake expansion limits are invalid")
    required_bytes = internal_zip_bytes + min(expanded, internal_zip_bytes * ratio) + envelope["overhead_bytes"]
    rounded_bytes = required_bytes + 1024**3 - 1
    if rounded_bytes > 2**64 - 1 or rounded_bytes // 1024**3 > envelope["maximum_storage_gib"]:
        raise PreflightError("trusted intake storage qualification cannot cover supported ZIPs")

    trial_path, trial_digest = (values.get(key) or None for key in TRIAL_KEYS)
    if (
        config.get("trial_authority_manifest_path"),
        config.get("trial_authority_manifest_digest"),
    ) != (trial_path, trial_digest):
        raise PreflightError("native trial authority differs from the model proxy")
    trial = config.get("trial_runtime")
    if trial_path:
        path_keys = (
            "relay_root",
            "scratch_root",
            "child_home_root",
            "offline_cache_root",
            "trusted_launcher_path",
            "filesystem_tool_path",
        )
        digest_keys = (
            "outer_runtime_config_digest",
            "builder_image_id",
            "trusted_launcher_digest",
            "filesystem_tool_digest",
        )
        if (
            not isinstance(trial, dict)
            or set(trial)
            != {
                *path_keys,
                *digest_keys,
                "deployment_owner",
                "maximum_candidate_archive_bytes",
            }
            or any(
                not isinstance(trial[key], str) or not Path(trial[key]).is_absolute()
                for key in path_keys
            )
            or any(
                not isinstance(trial[key], str) or not DIGEST.fullmatch(trial[key])
                for key in digest_keys
            )
            or not isinstance(trial["deployment_owner"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", trial["deployment_owner"])
            or type(trial["maximum_candidate_archive_bytes"]) is not int
            or not 0 < trial["maximum_candidate_archive_bytes"] <= 2**64 - 1
            or trial["builder_image_id"]
            not in {entry["config_image_id"] for entry in cache}
        ):
            raise PreflightError("native trial runtime configuration is incomplete")
        if len(os.fsencode(trial["child_home_root"])) > 18:
            raise PreflightError(
                "native trial child home root exceeds the 18-byte socket path budget"
            )
    elif trial is not None:
        raise PreflightError("native trial runtime lacks a pinned authority manifest")


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
    return (
        *BASE_SECRET_FILE_KEYS,
        *(
            key for key in MODEL_PROXY_SECRET_FILE_KEYS
            if values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true" and values.get(key)
        ),
        *((GITHUB_APP_KEYS[1],) if values.get(GITHUB_APP_KEYS[0]) else ()),
    )


def _role_secret_file_keys(role: str, values: dict[str, str]) -> tuple[str, ...]:
    keys = ROLE_SECRET_FILE_KEYS[role]
    if role == "worker" and values.get(GITHUB_APP_KEYS[0]):
        return (*keys, GITHUB_APP_KEYS[1])
    if role == "model-proxy" and values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true":
        return (
            *keys,
            *(key for key in MODEL_PROXY_SECRET_FILE_KEYS if values.get(key)),
        )
    return keys


def _validate_native_socket(path: Path, uid: int, gid: int) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PreflightError("native node socket is unavailable") from exc
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != uid
        or metadata.st_gid != gid
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        raise PreflightError("native node socket identity is unsafe")


def validate_private_host_inputs(
    values: dict[str, str], *, require_node: bool = True
) -> None:
    """Inspect metadata only; do not read application secret contents."""
    validate_demo_identity_host_inputs(values)
    paths = deployment_paths(values)
    uid = _positive_id(values, "WORKSTREAM_RUNTIME_UID")
    gid = _positive_id(values, "WORKSTREAM_RUNTIME_GID")
    _private_metadata(paths.root, kind="directory", uid=uid, gid=gid, mode=0o700)
    _private_metadata(paths.scratch, kind="directory", uid=uid, gid=gid, mode=0o700)
    _private_metadata(paths.socket_root, kind="directory", uid=uid, gid=gid, mode=0o700)
    if require_node:
        _validate_native_socket(paths.socket, uid, gid)
    model_proxy_enabled = values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true"
    if model_proxy_enabled:
        _private_metadata(
            paths.model_root, kind="directory", uid=uid, gid=gid, mode=0o700
        )
        _private_metadata(
            paths.model_relays, kind="directory", uid=uid, gid=gid, mode=0o700
        )
    _private_metadata(
        paths.guide_root,
        kind="directory",
        uid=GUIDE_PARSER_UID,
        gid=GUIDE_PARSER_GID,
        mode=0o750,
    )
    try:
        guide_socket = paths.guide_socket.lstat()
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
    if model_proxy_enabled:
        try:
            model_socket = paths.model_socket.lstat()
        except FileNotFoundError:
            model_socket = None
        except OSError as exc:
            raise PreflightError("model proxy socket identity is unavailable") from exc
        if model_socket is not None and (
            stat.S_ISLNK(model_socket.st_mode)
            or not stat.S_ISSOCK(model_socket.st_mode)
            or model_socket.st_uid != uid
            or model_socket.st_gid != gid
            or stat.S_IMODE(model_socket.st_mode) != 0o600
            or model_socket.st_nlink != 1
        ):
            raise PreflightError("model proxy socket has unsafe retained state")
    private_paths = [
        Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"]),
        *((Path(values[TRIAL_KEYS[0]]),) if values.get(TRIAL_KEYS[0]) else ()),
        *(Path(values[key]) for key in _secret_file_keys(values)),
        *(Path(values[key]) for key in ROLES_ANYWHERE_HOST_FILE_KEYS),
    ]
    for path in private_paths:
        _private_metadata(path, kind="file", uid=uid, gid=gid, mode=0o400)
    try:
        shared_roots = [
            paths.scratch.resolve(strict=True),
            paths.socket_root.resolve(strict=True),
            paths.guide_root.resolve(strict=True),
        ]
        if model_proxy_enabled:
            shared_roots.append(paths.model_root.resolve(strict=True))
            shared_roots.append(paths.model_relays.resolve(strict=True))
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
    if values.get("WORKSTREAM_MCP_IMAGE"):
        arguments.extend(("--file", str(MCP_COMPOSE_PATH)))
    if values.get("DEMO_IDENTITY_IMAGE"):
        arguments.extend(("--file", str(DEMO_IDENTITY_COMPOSE_PATH)))
    if values.get(GITHUB_APP_KEYS[0]):
        arguments.extend(("--file", str(GITHUB_COMPOSE_PATH)))
    if values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true":
        arguments.extend(("--file", str(INFERENCE_COMPOSE_PATH)))
        for provider, key in MODEL_PROVIDER_SECRET_FILE_KEYS.items():
            if values.get(key):
                arguments.extend(
                    ("--file", str(MODEL_PROVIDER_COMPOSE_PATHS[provider]))
                )
        arguments.extend(("--profile", "model-proxy"))
    if values.get(TRIAL_KEYS[0]):
        arguments.extend(["-f", str(TRIAL_COMPOSE_PATH)])
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
    if compose_arguments and compose_arguments[0] == "provision-project-points":
        return _run_points_operator(environment_path, values, compose_arguments)
    command_timeout = None
    if compose_arguments == ["start", "demo-identity"]:
        if not values.get("DEMO_IDENTITY_IMAGE"):
            raise PreflightError("demo identity bootstrap requires the issuer overlay")
        compose_arguments = [
            "up",
            "--detach",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "60",
            "demo-identity",
        ]
        command_timeout = 120
    elif compose_arguments == ["migrate"]:
        compose_arguments = [
            "run",
            "--rm",
            "--no-deps",
            "api",
            "python",
            "-m",
            "alembic",
            "upgrade",
            "head",
        ]
    elif compose_arguments == ["stop", "worker"]:
        # The fixed grace period matches validate_compose's worker contract.
        compose_arguments = ["stop", "--timeout", "7320", "worker"]
        command_timeout = 7380
    elif compose_arguments == ["start", "worker"]:
        compose_arguments = [
            "up",
            "--detach",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "60",
            "worker",
        ]
        command_timeout = 120
    elif not compose_arguments or compose_arguments[0] not in {
        "pull",
        "up",
        "ps",
    }:
        raise PreflightError("unsupported hosted Compose operation")
    # Sharing API's loopback namespace requires coupled replacement. Never leave
    # MCP attached to a retired API namespace after a Compose-managed update.
    selected_services = set(compose_arguments) & {
        "api", "mcp", "worker", "beat", "model-proxy", "demo-identity",
        "guide-document-parser", *PROOF_SERVICES,
    }
    targets_api = not selected_services or "api" in selected_services or (
        "--no-deps" not in compose_arguments
        and bool(selected_services & {"mcp", "worker", "beat"})
    )
    couple_mcp = bool(values.get("WORKSTREAM_MCP_IMAGE")) and (
        compose_arguments[0] == "up" and targets_api
    )
    prefix = ["docker", "compose", "--env-file", str(environment_path),
              *_compose_file_arguments(values)]
    try:
        if couple_mcp:
            stopped = subprocess.run(
                [*prefix, "stop", "mcp"], check=False,
                env=compose_environment(values), timeout=60,
            )
            if stopped.returncode:
                return stopped.returncode
        completed = subprocess.run(
            [*prefix, *compose_arguments],
            check=False,
            env=compose_environment(values),
            timeout=command_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PreflightError(
            "hosted Compose operation exceeded its management deadline"
        ) from exc
    except OSError as exc:
        raise PreflightError("hosted Compose operation could not start") from exc
    if completed.returncode == 0 and couple_mcp and "--no-start" not in compose_arguments:
        try:
            restarted = subprocess.run(
                [*prefix, "up", "--detach", "--no-deps", "--force-recreate",
                 "--wait", "--wait-timeout", "60", "mcp"],
                check=False, env=compose_environment(values), timeout=90,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PreflightError("MCP namespace replacement did not complete") from exc
        if restarted.returncode:
            return restarted.returncode
        validate_running_mcp_namespace(prefix, values)
    if (completed.returncode == 0 and values.get("WORKSTREAM_MCP_IMAGE")
            and not couple_mcp and compose_arguments[0] == "up"
            and "mcp" in compose_arguments and "--no-start" not in compose_arguments):
        validate_running_mcp_namespace(prefix, values)
    return completed.returncode


def validate_running_mcp_namespace(prefix: list[str], values: dict[str, str]) -> None:
    """Bind the running adapter to the current API, not a discarded namespace."""
    try:
        ids = []
        for name in ("api", "mcp"):
            result = subprocess.run(
                [*prefix, "ps", "--quiet", name], check=True, capture_output=True,
                text=True, env=compose_environment(values), timeout=15,
            )
            container_id = result.stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                raise PreflightError("MCP requires one running API and adapter")
            ids.append(container_id)
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.HostConfig.NetworkMode}}", ids[1]],
            check=True, capture_output=True, text=True,
            env=compose_environment(values), timeout=15,
        )
        if result.stdout.strip() != "container:" + ids[0]:
            raise PreflightError("MCP is attached to a different API namespace")
    except (OSError, subprocess.SubprocessError) as exc:
        raise PreflightError("MCP namespace verification failed") from exc


def _points_operator_arguments(arguments: list[str], values: dict[str, str]) -> list[str]:
    """Admit only fixed selectors and one private token-file mount source."""
    keys = {
        "--project-id", "--adapter-actor-id", "--unit-code", "--route-key",
        "--finance-token-file",
    }
    if len(arguments) != 11 or set(arguments[1::2]) != keys:
        raise PreflightError("points provisioning requires exactly five named inputs")
    inputs = dict(zip(arguments[1::2], arguments[2::2], strict=True))
    try:
        project = str(UUID(inputs["--project-id"]))
        adapter = str(UUID(inputs["--adapter-actor-id"]))
    except ValueError as exc:
        raise PreflightError("points provisioning selectors must be UUIDs") from exc
    unit, route = inputs["--unit-code"], inputs["--route-key"]
    if (
        re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]{0,31}", unit) is None
        or re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]{0,119}", route) is None
        or ".." in route
    ):
        raise PreflightError("points provisioning unit or route is invalid")
    path = Path(inputs["--finance-token-file"])
    try:
        metadata = path.lstat()
        if (
            not path.is_absolute() or path.resolve(strict=True) != path
            or any(character.isspace() or character in ":," for character in str(path))
            or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_uid != _positive_id(values, "WORKSTREAM_RUNTIME_UID")
            or metadata.st_gid != _positive_id(values, "WORKSTREAM_RUNTIME_GID")
            or stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}
            or not 0 < metadata.st_size <= 16_384
        ):
            raise ValueError
    except (OSError, ValueError):
        raise PreflightError("points Finance token file is unavailable or unsafe") from None
    return [
        "--volume", f"{path}:/run/secrets/points_finance_token:ro", "api",
        "/usr/bin/timeout", "--signal=TERM", "--kill-after=5s", "120s",
        "python", "scripts/provision_project_points.py",
        "--project-id", project, "--adapter-actor-id", adapter,
        "--unit-code", unit, "--route-key", route,
        "--finance-token-file", "/run/secrets/points_finance_token",
    ]


def _run_points_operator(
    environment_path: Path, values: dict[str, str], arguments: list[str],
) -> int:
    """Run only the image-owned provisioner; clean only this invocation on failure."""
    fixed_arguments = _points_operator_arguments(arguments, values)
    name = "workstream-points-" + uuid4().hex
    environment = compose_environment(values)
    try:
        return subprocess.run(
            [
                "docker", "compose", "--env-file", str(environment_path),
                *_compose_file_arguments(values), "run", "--rm", "--no-deps", "-T",
                "--pull", "never", "--name", name, *fixed_arguments,
            ],
            check=False, env=environment, timeout=150,
        ).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        try:
            cleanup = subprocess.run(
                ["docker", "rm", "--force", name], check=False, env=environment,
                capture_output=True, timeout=10,
            )
            removed = cleanup.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            removed = False
        if not removed:
            print(
                f"points operator cleanup uncertain; owned container: {name}",
                file=sys.stderr,
            )
        raise PreflightError(
            "points operator did not complete; no automatic retry"
        ) from exc


def run_shutdown(environment_path: Path, values: dict[str, str]) -> int:
    """Stop producers, drain the worker, then stop its isolated dependencies."""
    phases = [
        ["stop", "beat", "api"],
        ["stop", "--timeout", "7320", "worker"],
    ]
    if values.get("WORKSTREAM_MCP_IMAGE"):
        phases.insert(0, ["stop", "mcp"])
    if values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true":
        phases.append(["stop", "--timeout", "7320", "model-proxy"])
    phases.append(["stop", "guide-document-parser"])
    if values.get("DEMO_IDENTITY_IMAGE"):
        phases.append(["stop", "demo-identity"])
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


def demo_identity_healthcheck(values: dict[str, str]) -> list[str]:
    host = values["DEMO_IDENTITY_HOSTNAME"]
    return [
        "CMD",
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "5",
        "--cacert",
        "/run/tls/cert.pem",
        "--resolve",
        f"{host}:8443:127.0.0.1",
        f"https://{host}:8443/jwks.json",
    ]


def validate_demo_identity_compose(
    rendered: dict[str, Any], values: dict[str, str]
) -> None:
    services = rendered["services"]
    enabled = bool(values.get("DEMO_IDENTITY_IMAGE"))
    for name, service in services.items():
        expected_hosts = (
            [values["DEMO_IDENTITY_HOSTNAME"] + "=host-gateway"]
            if enabled and name == "api" else []
        )
        if (service.get("extra_hosts") or []) != expected_hosts:
            raise PreflightError("demo identity host mapping differs from its profile")
        networks = service.get("networks") or {}
        if "demo_identity" in networks and (
            not enabled or name != "demo-identity"
        ):
            raise PreflightError("demo identity network escaped its issuer boundary")
    if not enabled:
        return
    network = rendered.get("networks", {}).get("demo_identity", {})
    if (
        network.get("driver") != "bridge"
        or network.get("internal", False) is not False
        or network.get("ipam")
        or set(network) - {"name", "driver", "internal", "ipam"}
    ):
        raise PreflightError("demo identity network must use the dedicated publishing bridge")
    issuer = services["demo-identity"]
    expected_environment = {
        "DEMO_IDENTITY_ISSUER": values["DEMO_IDENTITY_ISSUER"],
        "DEMO_IDENTITY_AUDIENCE": values["DEMO_IDENTITY_AUDIENCE"],
        "DEMO_IDENTITY_TLS_CERT": "/run/tls/cert.pem",
        "DEMO_IDENTITY_TLS_KEY": "/run/tls/key.pem",
        "DEMO_IDENTITY_BIND": "0.0.0.0:8443",
    }
    if (
        issuer.get("image") != values["DEMO_IDENTITY_IMAGE"]
        or issuer.get("user") != "12001:12001"
        or issuer.get("environment") != expected_environment
        or issuer.get("command") != ["serve", "/data"]
        or issuer.get("entrypoint") is not None
        or issuer.get("secrets")
        or issuer.get("network_mode")
        or issuer.get("privileged")
        or issuer.get("devices")
        or issuer.get("tmpfs")
        or issuer.get("restart") != "on-failure:5"
        or str(issuer.get("mem_limit")) != "268435456"
        or issuer.get("cpus") != 1
        or issuer.get("pids_limit") != 64
        or issuer.get("init") is not True
        or issuer.get("pull_policy") != "always"
    ):
        raise PreflightError("demo identity process differs from its bounded profile")
    if issuer.get("healthcheck") != {
        "test": demo_identity_healthcheck(values),
        "interval": "10s",
        "timeout": "6s",
        "retries": 3,
        "start_period": "10s",
    }:
        raise PreflightError(
            "demo identity HTTPS readiness differs from its bounded profile"
        )
    ports = issuer.get("ports", [])
    if (
        len(ports) != 1
        or ports[0].get("host_ip") != "127.0.0.1"
        or str(ports[0].get("published")) != "8443"
        or ports[0].get("target") != 8443
        or ports[0].get("protocol") != "tcp"
    ):
        raise PreflightError("demo identity port must remain loopback")
    if (
        set(issuer.get("networks", {})) != {"demo_identity"}
        or issuer["networks"]["demo_identity"] is not None
    ):
        raise PreflightError(
            "demo identity network attachments differ from its profile"
        )
    _validate_exact_bind_mounts(
        "demo-identity",
        issuer,
        {
            "/data": (values["DEMO_IDENTITY_DATA_DIR"], False),
            "/run/tls/cert.pem": (values["DEMO_IDENTITY_TLS_CERT_FILE"], True),
            "/run/tls/key.pem": (values["DEMO_IDENTITY_TLS_KEY_FILE"], True),
        },
    )


def validate_mcp_compose(rendered: dict[str, Any], values: dict[str, str]) -> None:
    """Keep the private client beside API without handing it runtime secrets."""
    services = rendered["services"]
    mcp = services.get("mcp")
    api_ports = services["api"].get("ports", [])
    mcp_ports = [port for port in api_ports if port.get("target") == 8080]
    if not values.get("WORKSTREAM_MCP_IMAGE"):
        if mcp is not None or mcp_ports:
            raise PreflightError("MCP requires its explicit release image")
        return
    if (not isinstance(mcp, dict) or len(mcp_ports) != 1
            or mcp_ports[0].get("host_ip") != "127.0.0.1"
            or str(mcp_ports[0].get("published")) != "8080"
            or mcp_ports[0].get("protocol") != "tcp"):
        raise PreflightError("MCP requires one private API namespace publication")
    api = services["api"]
    bridge = rendered.get("networks", {}).get("default", {})
    if (api.get("network_mode") or api.get("networks") != {"default": None}
            or not isinstance(bridge, dict)
            or set(bridge) - {"name", "driver", "ipam"}
            or bridge.get("ipam")
            or bridge.get("driver", "bridge") != "bridge"):
        raise PreflightError("MCP parent API must use the private default bridge")
    if (mcp.get("image") != values["WORKSTREAM_MCP_IMAGE"]
            or mcp.get("network_mode") != "service:api"
            or mcp.get("user") != "1000:1000"
            or mcp.get("environment") != {
                "WORKSTREAM_API_URL": "http://127.0.0.1:8000",
                "WORKSTREAM_MCP_HOST": "0.0.0.0",
                "WORKSTREAM_MCP_PORT": "8080",
                "WORKSTREAM_MCP_MAX_IN_FLIGHT": "1",
                "WORKSTREAM_MCP_ALLOWED_HOSTS": "127.0.0.1:8080,localhost:8080",
            }
            or mcp.get("pull_policy") != "always"
            or mcp.get("init") is not True
            or mcp.get("restart") != "on-failure:5"
            or str(mcp.get("mem_limit")) != "536870912"
            or str(mcp.get("memswap_limit")) != "536870912"
            or str(mcp.get("cpus")) not in {"1", "1.0"}
            or mcp.get("pids_limit") != 64
            or mcp.get("stop_grace_period") not in {"30s", "30.0s"}
            or mcp.get("read_only") is not True
            or mcp.get("cap_drop") != ["ALL"]
            or mcp.get("security_opt") != ["no-new-privileges:true"]
            or mcp.get("healthcheck", {}).get("disable") is True
            or not mcp.get("healthcheck", {}).get("test")
            or any(mcp.get(key) for key in (
                "volumes", "secrets", "configs", "networks", "ports", "extra_hosts",
                "privileged", "devices", "device_cgroup_rules", "cap_add", "group_add",
                "pid", "ipc", "uts", "userns_mode", "cgroup", "use_api_socket",
                "credential_spec", "command", "entrypoint", "tmpfs",
            ))):
        raise PreflightError("MCP isolation or caller-token boundary is invalid")


def validate_compose(rendered: dict[str, Any], values: dict[str, str]) -> None:
    """Check the rendered release process and privilege topology."""
    paths = deployment_paths(values)
    services = rendered.get("services")
    expected_services = {
        "api",
        "worker",
        "beat",
        "guide-document-parser",
        *PROOF_SERVICES,
    }
    model_proxy_enabled = values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true"
    if model_proxy_enabled:
        expected_services.add("model-proxy")
    if values.get("DEMO_IDENTITY_IMAGE"):
        expected_services.add("demo-identity")
    if values.get("WORKSTREAM_MCP_IMAGE"):
        expected_services.add("mcp")
    if not isinstance(services, dict) or set(services) != expected_services:
        raise PreflightError(
            "release Compose services differ from the bounded topology"
        )
    validate_mcp_compose(rendered, values)
    validate_demo_identity_compose(rendered, values)
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
    backend_runtime_services = {
        "api",
        "worker",
        "beat",
        *PROOF_SERVICES,
    }
    if model_proxy_enabled:
        backend_runtime_services.add("model-proxy")
    for name in backend_runtime_services:
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
    if (
        model_proxy_enabled
        and services["model-proxy"]["image"] != values["WORKSTREAM_MODEL_PROXY_IMAGE"]
    ):
        raise PreflightError("model proxy must use the exact agents backend image")
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
        *({"model-proxy"} if model_proxy_enabled else set()),
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
        str(paths.scratch): (str(paths.scratch), False),
        str(paths.socket_root): (str(paths.socket_root), True),
    }
    expected_mounts = {
        "api": shared_backend_mounts | runtime_identity_mounts,
        "worker": shared_backend_mounts
        | {str(paths.guide_root): (str(paths.guide_root), True)}
        | (
            {str(paths.model_root): (str(paths.model_root), True)}
            if model_proxy_enabled
            else {}
        )
        | runtime_identity_mounts,
        "beat": {},
        "guide-document-parser": {
            str(paths.guide_root): (str(paths.guide_root), False),
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
    if model_proxy_enabled:
        expected_mounts["model-proxy"] = {
            str(paths.scratch): (str(paths.scratch), False),
            str(paths.model_root): (str(paths.model_root), False),
            **runtime_identity_mounts,
        }
    if values.get(TRIAL_KEYS[0]):
        expected_mounts["model-proxy"][str(TRIAL_MANIFEST_TARGET)] = (
            values[TRIAL_KEYS[0]],
            True,
        )
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
            "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET": str(paths.guide_socket),
        }
        or parser.get("command")
        != [
            "python",
            "-m",
            "app.adapters.guide_document_tools.service",
            "--socket",
            str(paths.guide_socket),
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
        str(paths.guide_socket),
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
    if model_proxy_enabled and worker_dependencies.get("model-proxy") != {
        "condition": "service_healthy",
        "required": True,
    }:
        raise PreflightError("worker must wait for a healthy model proxy")
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
    if model_proxy_enabled:
        proxy = services["model-proxy"]
        if (
            proxy.get("profiles") != ["model-proxy"]
            or proxy.get("ports")
            or proxy.get("command")
            != ["python", "-m", "app.workers.checker_model_proxy"]
            or proxy.get("stop_grace_period") not in {"7320s", "2h2m0s"}
            or proxy.get("healthcheck", {}).get("test")
            != [
                "CMD",
                "python",
                "-c",
                "import pathlib,sys; sys.exit(0 if pathlib.Path(sys.argv[1]).is_socket() else 1)",
                str(paths.model_socket),
            ]
        ):
            raise PreflightError("model proxy delivery profile is invalid")
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
    active_roles = ("api", "worker", "beat") + (
        ("model-proxy",) if model_proxy_enabled else ()
    )
    for role in active_roles:
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
                    "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET",
                    *TRIAL_KEYS,
                    *GITHUB_APP_KEYS,
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
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(paths.scratch),
        "WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT": str(paths.scratch),
        "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET": str(paths.socket),
        "WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET": str(paths.socket),
        **{key: values[key] for key in INTAKE_DIGEST_KEYS},
    }
    for key, value in exact.items():
        if str(environment.get(key, "")).lower() != value:
            raise PreflightError(f"rendered release environment is unsafe: {key}")
    for name in (
        "api",
        "worker",
        "beat",
        *PROOF_SERVICES,
        *(("model-proxy",) if model_proxy_enabled else ()),
    ):
        service_environment = services[name].get("environment")
        if not isinstance(service_environment, dict):
            raise PreflightError(f"{name} release environment is unavailable")
        deadline_key = "WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS"
        if str(service_environment.get(deadline_key, "")) != values[deadline_key]:
            raise PreflightError(
                f"rendered artifact preparation deadline differs from release: {name}.{deadline_key}"
            )
        for key in PROJECT_AGENT_CONFIGURATION_KEYS:
            if str(service_environment.get(key, "")) != values[key]:
                raise PreflightError(
                    "rendered project agent configuration differs from release: "
                    f"{name}.{key}"
                )
    for name, service in services.items():
        environment = service.get("environment") or {}
        expected_trial = (
            {
                TRIAL_KEYS[0]: str(TRIAL_MANIFEST_TARGET),
                TRIAL_KEYS[1]: values.get(TRIAL_KEYS[1]),
            }
            if name == "model-proxy" and values.get(TRIAL_KEYS[0])
            else {}
        )
        if {
            key: environment[key] for key in TRIAL_KEYS if key in environment
        } != expected_trial:
            raise PreflightError(
                "trial authority is exposed outside its model-proxy owner"
            )
    worker_environment = environments["worker"]
    if worker_environment.get("WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET") != str(
        paths.guide_socket
    ):
        raise PreflightError("worker lacks the fixed guide parser socket")
    if model_proxy_enabled and worker_environment.get(
        "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"
    ) != str(paths.model_socket):
        raise PreflightError("worker lacks the fixed model proxy socket")
    if model_proxy_enabled and environments["model-proxy"].get(
        "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"
    ) != str(paths.model_socket):
        raise PreflightError("model proxy lacks its fixed socket")
    for name in ("api", "beat", *PROOF_SERVICES):
        service_environment = services[name].get("environment") or {}
        if not isinstance(service_environment, dict):
            raise PreflightError(f"{name} release environment is invalid")
        if "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET" in service_environment:
            raise PreflightError(f"{name} must not receive the guide parser socket")
        if any(key in service_environment for key in MODEL_PROXY_SECRET_FILE_KEYS):
            raise PreflightError(
                f"{name} must not receive a model proxy credential selector"
            )
        if "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET" in service_environment:
            raise PreflightError(f"{name} must not receive the model proxy socket")
    if any(key in worker_environment for key in MODEL_PROXY_SECRET_FILE_KEYS):
        raise PreflightError(
            "worker must not receive a model proxy credential selector"
        )
    for name, service in services.items():
        service_environment = service.get("environment") or {}
        if not isinstance(service_environment, dict):
            raise PreflightError(f"{name} release environment is invalid")
        expected_github = (
            {
                GITHUB_APP_KEYS[0]: values[GITHUB_APP_KEYS[0]],
                GITHUB_APP_KEYS[1]: SECRET_FILE_TARGETS[GITHUB_APP_KEYS[1]][1],
                GITHUB_APP_KEYS[2]: values.get(GITHUB_APP_KEYS[2], ""),
            }
            if name == "worker" and values.get(GITHUB_APP_KEYS[0])
            else {}
        )
        actual_github = {
            key: service_environment[key]
            for key in GITHUB_APP_KEYS if key in service_environment
        }
        if actual_github != expected_github:
            raise PreflightError(f"{name} GitHub App settings differ from its release role")
        for key in (
            "WORKSTREAM_GITHUB_APP_PRIVATE_KEY",
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


def _verify_smol_asset(path: Path, expected: str, uid: int, deadline: float) -> None:
    """Hash pinned regular assets without symlinks or writable substitutions."""
    try:
        if path.resolve(strict=True) != path:
            raise PreflightError("native Smol asset path is not canonical")
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        )
        with os.fdopen(descriptor, "rb") as asset:
            metadata = os.fstat(asset.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid not in {0, uid}
                or metadata.st_mode & 0o022
            ):
                raise PreflightError("native Smol asset custody is unsafe")
            digest = hashlib.sha256()
            while True:
                if time.monotonic() >= deadline:
                    raise PreflightError(
                        "native Smol asset verification deadline exceeded"
                    )
                chunk = asset.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
            current = path.lstat()
            if (
                not os.path.samestat(metadata, current)
                or metadata.st_size != current.st_size
                or "sha256:" + digest.hexdigest() != expected
            ):
                raise PreflightError("native Smol asset digest or identity differs")
    except PreflightError:
        raise
    except (OSError, RuntimeError) as exc:
        raise PreflightError("native Smol asset is unavailable") from exc


def validate_smol_runtime(config: dict[str, Any], values: dict[str, str]) -> None:
    """Check pinned native inputs, delegation and the existing typed node health."""
    paths = deployment_paths(values)
    uid = _positive_id(values, "WORKSTREAM_RUNTIME_UID")
    gid = _positive_id(values, "WORKSTREAM_RUNTIME_GID")
    smol = config["smol"]
    _private_metadata(
        Path(smol["home"]), kind="directory", uid=uid, gid=gid, mode=0o700
    )
    group = Path(smol["cgroup_root"])
    try:
        if (
            group.resolve(strict=True) != group
            or group.stat().st_uid != uid
            or not group.joinpath("controller").is_dir()
        ):
            raise PreflightError("native Smol cgroup delegation identity differs")
        for name in ("cgroup.controllers", "cgroup.subtree_control"):
            with group.joinpath(name).open("r", encoding="ascii") as control:
                controllers = control.read(4097)
            if len(controllers) > 4096 or not {"cpu", "memory", "pids"} <= set(
                controllers.split()
            ):
                raise PreflightError("native Smol cgroup delegation is incomplete")
    except (OSError, UnicodeError) as exc:
        raise PreflightError("native Smol cgroup delegation is unavailable") from exc
    deadline = time.monotonic() + 30
    _verify_smol_asset(
        checker_service_binary(values),
        values["WORKSTREAM_CHECKER_SERVICE_BINARY_SHA256"],
        uid,
        deadline,
    )
    for path, digest in [
        (smol["binary"], smol["binary_sha256"]),
        (smol["guest_binary"], smol["guest_sha256"]),
    ]:
        _verify_smol_asset(Path(path), digest, uid, deadline)
    for entry in config["cache"]:
        _verify_smol_asset(
            Path(entry["smol"]["archive"]),
            entry["smol"]["archive_sha256"],
            uid,
            deadline,
        )
        _verify_smol_asset(
            Path(entry["smol"]["image_config"]), entry["config_image_id"], uid, deadline
        )
    if values.get(TRIAL_KEYS[0]):
        _verify_smol_asset(
            Path(values[TRIAL_KEYS[0]]), values[TRIAL_KEYS[1]], uid, deadline
        )
        trial = config["trial_runtime"]
        for key in (
            "relay_root",
            "scratch_root",
            "child_home_root",
            "offline_cache_root",
        ):
            _private_metadata(
                Path(trial[key]), kind="directory", uid=uid, gid=gid, mode=0o700
            )
        for path_key, digest_key in (
            ("trusted_launcher_path", "trusted_launcher_digest"),
            ("filesystem_tool_path", "filesystem_tool_digest"),
        ):
            _verify_smol_asset(Path(trial[path_key]), trial[digest_key], uid, deadline)
    script = (
        "import asyncio,json; from dataclasses import asdict; from pathlib import Path; "
        "from app.core.config import Settings; "
        "from app.adapters.checkers import configured_external_checker_execution; "
        "s=Settings(external_checker_service_socket=Path("
        + repr(str(paths.socket))
        + "),artifact_scratch_root=Path("
        + repr(str(paths.scratch))
        + "),external_checker_material_root=Path("
        + repr(str(paths.scratch))
        + "),external_checker_service_timeout_seconds=5.0); "
        "print(json.dumps(asdict(asyncio.run(configured_external_checker_execution(s).health()))))"
    )
    health = _run_json(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=512m",
            "--cpus=1",
            "--user",
            str(uid) + ":" + str(gid),
            "--mount",
            f"type=bind,src={paths.socket_root},dst={paths.socket_root},readonly",
            "--entrypoint",
            "python",
            values["WORKSTREAM_BACKEND_IMAGE"],
            "-c",
            script,
        ],
        failure="native Smol project readiness failed",
        environment=compose_environment(values),
    )
    if (
        not isinstance(health, dict)
        or health.get("runtime") != "smolvm"
        or health.get("isolation_mode") != "smol-microvm"
        or health.get("operating_system") != config["operating_system"]
        or health.get("architecture") != config["architecture"]
        or health.get("sandbox_uid") != uid
        or health.get("sandbox_gid") != gid
        or health.get("cached_platform_manifests") != len(config["cache"])
    ):
        raise PreflightError("native Smol project readiness identity differs")


def validate_trusted_intake(values: dict[str, str]) -> None:
    """Use the release image's typed ART adapter without mounting credentials."""
    paths = deployment_paths(values)
    script = (
        "import asyncio,json; from dataclasses import asdict; from pathlib import Path; "
        "from app.core.config import Settings; "
        "from app.adapters.artifacts import trusted_submission_intake; "
        "s=Settings(artifact_intake_service_socket=Path("
        + repr(str(paths.socket))
        + "),artifact_intake_image_digest="
        + repr(values[INTAKE_DIGEST_KEYS[0]])
        + ",artifact_intake_config_digest="
        + repr(values[INTAKE_DIGEST_KEYS[1]])
        + "); "
        "print(json.dumps(asdict(asyncio.run(trusted_submission_intake(s).health()))))"
    )
    health = _run_json(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=512m",
            "--cpus=1",
            "--user",
            values["WORKSTREAM_RUNTIME_UID"] + ":" + values["WORKSTREAM_RUNTIME_GID"],
            "--mount",
            f"type=bind,src={paths.socket_root},dst={paths.socket_root},readonly",
            "--entrypoint",
            "python",
            values["WORKSTREAM_BACKEND_IMAGE"],
            "-c",
            script,
        ],
        failure="trusted Smol intake readiness failed",
        environment=compose_environment(values),
    )
    if (
        not isinstance(health, dict)
        or (health.get("runtime"), health.get("isolation_mode"))
        != ("smolvm", "smol-microvm")
        or health.get("image_digest") != values[INTAKE_DIGEST_KEYS[0]]
        or health.get("config_digest") != values[INTAKE_DIGEST_KEYS[1]]
    ):
        raise PreflightError("trusted intake readiness identity differs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument(
        "--configuration-only",
        action="store_true",
        help="skip native host inputs, Smol readiness and image-cache checks",
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
                "configuration valid; host identity, Smol/cache, cloud, health and recovery checks skipped"
            )
            return 0
        validate_private_host_inputs(values)
        validate_smol_runtime(checker_config, values)
        validate_trusted_intake(values)
    except PreflightError as exc:
        print(f"hosted release preflight failed: {exc}", file=sys.stderr)
        return 1
    print("hosted release configuration and native Smol prerequisites are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
