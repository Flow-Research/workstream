"""Owned Redis and dedicated workers for the remote-runner CLI drill."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time


SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
PILOT_CHECKS = {
    "pre": ("pre_submit", "incident_summary_layout"),
    "post": ("post_submit", "incident_summary_counts"),
}


def _required_file(environment: dict[str, str], name: str, *, limit: int) -> Path:
    raw = environment.get(name)
    if not raw:
        raise RuntimeError(f"journey requires {name}")
    path = Path(raw)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"journey requires a regular {name}")
    size = path.stat().st_size
    if size <= 0 or size > limit:
        raise RuntimeError(f"journey {name} has an invalid size")
    return path.resolve(strict=True)


def _required_json(environment: dict[str, str], name: str) -> tuple[Path, dict]:
    path = _required_file(environment, name, limit=1_048_576)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError(f"journey {name} is not JSON") from exc
    if type(value) is not dict:
        raise RuntimeError(f"journey {name} must be an object")
    return path, value


def load_journey_configuration(environment: dict[str, str]) -> dict[str, Path]:
    """Validate every external pin before API, worker or provider startup."""
    from jsonschema import Draft202012Validator

    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.modules.artifacts.api.submission_cleanup import (
        SubmissionSourceCleanupProfile,
    )
    from app.modules.artifacts.api.submission_command import SubmissionExecutionProfile
    from app.modules.checkers.api.external import ExternalCheckerRegistrySpec
    from app.modules.checkers.api.source_contracts import source_contracts_context
    from public_setup import validate_authored_rules_template

    host = environment.get("WORKSTREAM_EXTERNAL_RUNNER_HOST")
    port = environment.get("WORKSTREAM_EXTERNAL_RUNNER_PORT")
    server_name = environment.get("WORKSTREAM_EXTERNAL_RUNNER_SERVER_NAME")
    if (
        host != "127.0.0.1"
        or not port
        or not port.isdecimal()
        or not 1 <= int(port) <= 65_535
        or not server_name
    ):
        raise RuntimeError("journey requires an explicit loopback TLS runner tunnel")
    for name in (
        "WORKSTREAM_EXTERNAL_RUNNER_CA_PATH",
        "WORKSTREAM_EXTERNAL_RUNNER_CERTIFICATE_PATH",
        "WORKSTREAM_EXTERNAL_RUNNER_PRIVATE_KEY_PATH",
    ):
        environment[name] = str(_required_file(environment, name, limit=1_048_576))
    for name in (
        "WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST",
        "WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST",
        "WORKSTREAM_CLI_JOURNEY_CHECKER_IMAGE_DIGEST",
    ):
        if SHA256.fullmatch(environment.get(name, "")) is None:
            raise RuntimeError(f"journey requires exact {name}")

    _, selected_runtime = _required_json(
        environment, "WORKSTREAM_CLI_JOURNEY_PRE_RUNTIME_PROFILE_FILE"
    )
    _, execution = _required_json(
        environment, "WORKSTREAM_CLI_JOURNEY_EXECUTION_PROFILE_FILE"
    )
    _, cleanup = _required_json(
        environment, "WORKSTREAM_CLI_JOURNEY_CLEANUP_PROFILE_FILE"
    )
    profile = SubmissionExecutionProfile.model_validate(
        execution,
        context=source_contracts_context(selected_pre_submit_source_contracts()),
    )
    cleanup_profile = SubmissionSourceCleanupProfile.model_validate(cleanup)
    if cleanup_profile.upload_principal != "workstream-minio":
        raise RuntimeError("journey cleanup profile must identify the upload principal")
    cleanup_key = environment.get("WORKSTREAM_CLI_JOURNEY_CLEANUP_ACCESS_KEY_ID")
    if not cleanup_key or cleanup_key == cleanup_profile.upload_principal:
        raise RuntimeError("journey requires a distinct cleanup access key")
    secret_path = _required_file(
        environment, "WORKSTREAM_CLI_JOURNEY_CLEANUP_SECRET_FILE", limit=4096
    )
    if stat.S_IMODE(secret_path.stat().st_mode) != 0o600:
        raise RuntimeError("journey cleanup secret file must be private")
    parser_path = Path(environment.get("WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET", ""))
    if not parser_path.is_absolute() or not parser_path.is_socket():
        raise RuntimeError("journey requires the real guide parser socket")
    parser_stat = parser_path.stat()
    parent_stat = parser_path.parent.stat()
    if (parser_stat.st_uid, parser_stat.st_gid, stat.S_IMODE(parser_stat.st_mode)) != (
        10_002,
        10_001,
        0o660,
    ) or (
        parent_stat.st_uid,
        parent_stat.st_gid,
        stat.S_IMODE(parent_stat.st_mode),
    ) != (10_002, 10_001, 0o750):
        raise RuntimeError(
            "journey guide parser custody differs from the fixed service"
        )
    if profile.runtime.model_dump(mode="json") != selected_runtime:
        raise RuntimeError("journey PRE runtime differs from qualified profile")

    registry_files = {}
    for name, (phase, check) in PILOT_CHECKS.items():
        path, body = _required_json(
            environment, f"WORKSTREAM_CLI_JOURNEY_REGISTRY_{name.upper()}_FILE"
        )
        spec = ExternalCheckerRegistrySpec.model_validate(body)
        if (
            spec.phase != phase
            or spec.image_digest
            != environment["WORKSTREAM_CLI_JOURNEY_CHECKER_IMAGE_DIGEST"]
        ):
            raise RuntimeError("journey checker phase or pinned image differs")
        if (
            spec.resources.cpu_millis > profile.runtime.cpu_millis
            or spec.resources.memory_bytes > profile.runtime.memory_bytes
            or spec.resources.maximum_output_bytes
            > profile.runtime.maximum_output_bytes
            or spec.resources.deadline_ms > profile.runtime.aggregate_deadline_ms
        ):
            raise RuntimeError("journey checker exceeds qualified PRE resources")
        if not Draft202012Validator(spec.configuration_schema.document).is_valid(
            {"check": check}
        ):
            raise RuntimeError("journey registry rejects its selected check")
        registry_files[name] = path

    environment.update(
        WORKSTREAM_SUBMISSION_EXECUTION_PROFILE=json.dumps(execution, sort_keys=True),
        WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE=json.dumps(
            cleanup, sort_keys=True
        ),
        WORKSTREAM_EXTERNAL_CHECKER_SERVICE_TIMEOUT_SECONDS=str(
            profile.runtime.aggregate_deadline_ms / 1000
        ),
    )
    environment.pop("WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET", None)
    validate_authored_rules_template()
    return registry_files


@contextmanager
def durable_runtime(root: Path, directory: Path, environment: dict[str, str]):
    """Start only owned local broker/worker groups; runner lives outside this host."""
    processes, logs = [], []

    def start(arguments: list[str], label: str, *, extra_environment=None):
        log = (directory / (label + ".log")).open("wb")
        logs.append(log)
        process = subprocess.Popen(
            arguments,
            cwd=root / "backend",
            env=environment | (extra_environment or {}),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(process)
        return process

    scratch = directory / "scratch"
    scratch.mkdir(mode=0o700)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        redis_port = sock.getsockname()[1]
    environment.update(
        WORKSTREAM_CELERY_BROKER_URL=f"redis://127.0.0.1:{redis_port}/0",
        WORKSTREAM_CELERY_RESULT_BACKEND_URL=f"redis://127.0.0.1:{redis_port}/1",
        WORKSTREAM_CELERY_TASK_ALWAYS_EAGER="false",
        WORKSTREAM_ARTIFACT_STORE_BACKEND="s3_compatible",
        WORKSTREAM_ARTIFACT_SCRATCH_ROOT=str(scratch),
        WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT=str(scratch),
        WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE="minio",
        WORKSTREAM_ARTIFACT_S3_REGION="us-east-1",
        WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL=environment[
            "WORKSTREAM_TEST_MINIO_ENDPOINT"
        ],
        WORKSTREAM_ARTIFACT_S3_BUCKET=environment["WORKSTREAM_TEST_MINIO_BUCKET"],
        WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX=environment[
            "WORKSTREAM_TEST_MINIO_PREFIX"
        ],
        WORKSTREAM_ARTIFACT_S3_ADDRESSING_STYLE="path",
        WORKSTREAM_ARTIFACT_S3_CREDENTIAL_MODE="local_static",
        WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID="workstream-minio",
        WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY="workstream-minio-secret-key",
        WORKSTREAM_ARTIFACT_ADMISSION_DEPLOYMENT_MAXIMUM_BYTES="268435456",
        WORKSTREAM_ARTIFACT_ADMISSION_PROJECT_MAXIMUM_BYTES="134217728",
        WORKSTREAM_ARTIFACT_ADMISSION_PRODUCER_MAXIMUM_BYTES="67108864",
        WORKSTREAM_ARTIFACT_ADMISSION_TASK_MAXIMUM_BYTES="67108864",
        WORKSTREAM_ARTIFACT_PENDING_WORK_SCAN_INTERVAL_SECONDS="2",
    )
    redis_binary = shutil.which("redis-server")
    if redis_binary is None:
        raise RuntimeError("journey requires redis-server")
    try:
        redis = start(
            [
                redis_binary,
                "--bind",
                "127.0.0.1",
                "--port",
                str(redis_port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                str(directory),
            ],
            "redis",
        )
        deadline = time.monotonic() + 30
        while True:
            if redis.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("owned Redis startup failed")
            try:
                with socket.create_connection(("127.0.0.1", redis_port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)

        def start_workers():
            required = []

            def worker(
                label: str, queues: str, concurrency: int, *, extra_environment=None
            ):
                required.append(
                    start(
                        [
                            sys.executable,
                            "-m",
                            "celery",
                            "-A",
                            "app.workers.celery_app",
                            "worker",
                            "--pool=prefork",
                            f"--concurrency={concurrency}",
                            "--queues",
                            queues,
                            f"--hostname={label}@localhost",
                            "--loglevel=WARNING",
                        ],
                        label,
                        extra_environment=extra_environment,
                    )
                )

            worker("worker", "celery,workstream.outbox", 2)
            worker("finalizer", "workstream.submission_finalization", 1)
            worker(
                "source-cleanup",
                "workstream.source_cleanup",
                1,
                extra_environment={
                    "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID": environment[
                        "WORKSTREAM_CLI_JOURNEY_CLEANUP_ACCESS_KEY_ID"
                    ],
                    "WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY": Path(
                        environment["WORKSTREAM_CLI_JOURNEY_CLEANUP_SECRET_FILE"]
                    ).read_text(encoding="ascii"),
                },
            )
            required.append(
                start(
                    [
                        sys.executable,
                        "-m",
                        "celery",
                        "-A",
                        "app.workers.celery_app",
                        "beat",
                        "--schedule",
                        str(directory / "beat-schedule"),
                        "--loglevel=WARNING",
                    ],
                    "beat",
                )
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if any(process.poll() is not None for process in required):
                    raise RuntimeError("required journey worker exited during startup")
                time.sleep(0.2)

        yield start_workers
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
        for log in logs:
            log.close()
        if location := os.environ.get("WORKSTREAM_CLI_JOURNEY_EVIDENCE"):
            retained = Path(location) / "runtime-logs"
            retained.mkdir(mode=0o700, parents=True)
            for source in directory.glob("*.log"):
                target = retained / source.name
                with target.open("xb") as destination:
                    target.chmod(0o600)
                    with source.open("rb") as incoming:
                        shutil.copyfileobj(incoming, destination)
