"""Opt-in public A19 resource drill through Caddy, API, PostgreSQL and MinIO.

Run only with the isolated database/bucket runner and a pinned Caddy binary.
The body is generated incrementally; neither the test nor the API stores it.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import zipfile

import httpx
import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from tests.artifacts.test_submission_intake_admission import admission_intake as admission_intake
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access,
    admin_access as admin_access,
)
from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation
from tests.test_s3_artifact_store import minio_settings


MIB = 1024 * 1024
REPOSITORY = Path(__file__).resolve().parents[3]
BACKEND = REPOSITORY / "backend"


def _free_port() -> int:
    with socket.socket() as value:
        value.bind(("127.0.0.1", 0))
        return int(value.getsockname()[1])


def _rss(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except FileNotFoundError:
        pass
    return 0


def _disk_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _stop(process: subprocess.Popen, output) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    output.close()


async def _listen(port: int, process: subprocess.Popen, log: Path) -> None:
    async with asyncio.timeout(180):
        while True:
            if process.poll() is not None:
                raise AssertionError(f"socket owner exited: {log.read_text()[-3000:]}")
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                await asyncio.sleep(0.05)
            else:
                writer.close()
                await writer.wait_closed()
                return


def _caddy_config(binary: Path, directory: Path, api_port: int, caddy_port: int) -> Path:
    certificate, key = directory / "identity.crt", directory / "identity.key"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-days", "1", "-subj", "/CN=identity.example.test",
        "-addext", "subjectAltName=DNS:identity.example.test",
        "-keyout", str(key), "-out", str(certificate),
    ], check=True, capture_output=True, timeout=15)
    environment = os.environ | {
        "FLOW_IDENTITY_HOSTNAME": "identity.example.test",
        "FLOW_IDENTITY_UPSTREAM_CERT": str(certificate),
        "WORKSTREAM_PUBLIC_HOSTNAME": "workstream.example.test",
        "WORKSTREAM_API_HOST_PORT": str(api_port),
    }
    adapted = subprocess.run([
        str(binary), "adapt", "--config", str(REPOSITORY / "deploy/hosted/public.Caddyfile"),
        "--adapter", "caddyfile",
    ], check=True, capture_output=True, text=True, env=environment, timeout=15)
    configuration = json.loads(adapted.stdout)
    servers = list(configuration["apps"]["http"]["servers"].values())
    server = next(item for item in servers if item["listen"] == [":443"])
    server["listen"] = [f"127.0.0.1:{caddy_port}"]
    server["automatic_https"] = {"disable": True}
    server.pop("tls_connection_policies", None)
    configuration["apps"].pop("tls", None)
    routes = []

    def relocate(value):
        if isinstance(value, dict):
            if value.get("handler") == "reverse_proxy":
                for upstream in value["upstreams"]:
                    if upstream["dial"] == f"127.0.0.1:{api_port}":
                        routes.append(upstream)
            for item in value.values():
                relocate(item)
        elif isinstance(value, list):
            for item in value:
                relocate(item)

    relocate(configuration)
    assert len(routes) == 1  # The product API route is the only measured upstream.
    target = directory / "caddy.json"
    target.write_text(json.dumps(configuration))
    return target


class _QueueSink:
    """Non-seekable ZIP output with one queued chunk, never a body-sized file."""

    def __init__(self, chunks: queue.Queue, stopped: threading.Event):
        self.chunks, self.stopped, self.position = chunks, stopped, 0

    def write(self, data) -> int:
        value = bytes(data)
        while not self.stopped.is_set():
            try:
                self.chunks.put(value, timeout=0.1)
                self.position += len(value)
                return len(value)
            except queue.Full:
                continue
        raise OSError("A19 HTTP reader stopped")

    def tell(self) -> int:
        return self.position

    def flush(self) -> None:
        pass


async def _zip_body(content_mib: int, emitted: list[int]):
    chunks: queue.Queue = queue.Queue(maxsize=1)
    stopped = threading.Event()
    errors = []
    block = b"A" * MIB

    def produce() -> None:
        try:
            with zipfile.ZipFile(_QueueSink(chunks, stopped), "w", compression=zipfile.ZIP_STORED) as archive:
                sizes = (content_mib,) if content_mib < 128 else (124, 124, 124, content_mib - 372)
                for number, size in enumerate(sizes):
                    with archive.open(f"work-{number}.bin", "w", force_zip64=True) as entry:
                        for _ in range(size):
                            entry.write(block)
        except BaseException as error:
            errors.append(error)
        finally:
            while not stopped.is_set():
                try:
                    chunks.put(None, timeout=0.1)
                    break
                except queue.Full:
                    continue

    producer = threading.Thread(target=produce, daemon=True)
    producer.start()
    emitted.append(0)
    try:
        while True:
            chunk = await asyncio.to_thread(chunks.get)
            if chunk is None:
                break
            emitted[0] += len(chunk)
            yield chunk
            if content_mib == 496:
                await asyncio.sleep(0.03)  # Finite slow client, still below idle timeout.
        assert not errors, errors
    finally:
        stopped.set()
        await asyncio.to_thread(producer.join, 2)
        assert not producer.is_alive(), "ZIP generator survived the request"


API_CODE = """
import asyncio
import os
from pathlib import Path
from app.adapters.artifacts.s3_compatible import S3CompatibleArtifactStore
from app.interfaces.artifacts import ArtifactStoreUnavailableError

original = S3CompatibleArtifactStore.upload_source_part
markers = Path(os.environ['WORKSTREAM_A19_MARKERS'])
last = int(os.environ['WORKSTREAM_A19_LAST_PART'])

async def measured_part(self, upload, number, data):
    if number == 1:
        (markers / 'first').write_text(str(len(data)))
        while not (markers / 'release-first').exists():
            await asyncio.sleep(0.02)
    if number == last:
        (markers / 'last').write_text(str(len(data)))
        await asyncio.sleep(8)  # Finite stalled provider; owner can terminalize before hard expiry.
        raise ArtifactStoreUnavailableError('measured provider stall')
    receipt = await original(self, upload, number, data)
    (markers / 'completed').write_text(str(number))
    return receipt

S3CompatibleArtifactStore.upload_source_part = measured_part
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=int(os.environ['WORKSTREAM_A19_API_PORT']),
            log_level='warning', lifespan='on')
"""


def _api_environment(fixture, prefix: str, directory: Path, part_bytes: int, markers: Path, last: int):
    settings = minio_settings(private_prefix=prefix, buffer_bytes=65536)
    settings = settings.model_copy(update={
        "artifact_admission_task_maximum_bytes": 1024**3,
        "artifact_admission_producer_maximum_bytes": 1024**3,
        "artifact_admission_project_maximum_bytes": 1024**3,
        "artifact_admission_deployment_maximum_bytes": 1024**3,
    })
    profile = {
        "capacity": {"maximum_total_bytes": 1024**3},
        "runtime": _source_reservation().runtime_profile.model_dump(mode="json"),
        "upload_total_seconds": 120.0 if last == 2 else 300.0,
        "upload_idle_seconds": 30.0,
        "foreground_lease_seconds": 60.0, "heartbeat_seconds": 10.0,
        "replay_total_seconds": 30.0, "part_bytes": part_bytes,
    }
    values = {
        "WORKSTREAM_ENVIRONMENT": "test",
        "WORKSTREAM_AUTH_PROVIDER": "dev",
        "WORKSTREAM_DATABASE_URL": os.environ["WORKSTREAM_TEST_DATABASE_URL"],
        "WORKSTREAM_DEV_AUTH_TOKEN": "a19-measurement-token",
        "WORKSTREAM_DEV_AUTH_SUBJECT": fixture.access.target.subject,
        "WORKSTREAM_DEV_AUTH_ISSUER": fixture.access.signed.issuer,
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET": "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=",
        "WORKSTREAM_SUBMISSION_EXECUTION_PROFILE": json.dumps(profile),
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(directory / "scratch"),
        "WORKSTREAM_A19_MARKERS": str(markers),
        "WORKSTREAM_A19_LAST_PART": str(last),
    }
    for key in (
        "artifact_store_backend", "artifact_s3_provider_profile", "artifact_s3_region",
        "artifact_s3_endpoint_url", "artifact_s3_bucket", "artifact_s3_private_prefix",
        "artifact_s3_addressing_style", "artifact_s3_credential_mode",
        "artifact_s3_operation_total_timeout_seconds", "artifact_s3_write_timeout_seconds",
        "artifact_stream_buffer_bytes", "artifact_admission_task_maximum_bytes",
        "artifact_admission_producer_maximum_bytes", "artifact_admission_project_maximum_bytes",
        "artifact_admission_deployment_maximum_bytes",
    ):
        values["WORKSTREAM_" + key.upper()] = str(getattr(settings, key))
    values["WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID"] = settings.artifact_s3_access_key_id.get_secret_value()
    values["WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY"] = settings.artifact_s3_secret_access_key.get_secret_value()
    return os.environ | values, profile


async def _wait_file(path: Path, *, timeout: float) -> None:
    async with asyncio.timeout(timeout):
        while not path.exists():
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
@pytest.mark.parametrize("admission_intake", ["minio"], indirect=True)
async def test_public_a19_near_limit_upload_stays_bounded(admission_intake, tmp_path):
    """A real public request holds a provider part and expires with charged custody."""
    content_mib = int(os.environ.get("WORKSTREAM_A19_BODY_MIB", "6"))
    assert content_mib in {6, 496}
    binary = Path(os.environ["WORKSTREAM_TEST_CADDY"])
    assert binary.is_file()
    fixture = admission_intake
    source = fixture.source_store_factory()
    try:
        prefix = source._private_prefix
    finally:
        source.close()
    markers = tmp_path / "markers"
    markers.mkdir()
    (tmp_path / "scratch").mkdir(mode=0o700)
    part_bytes = (5 if content_mib == 6 else 16) * MIB
    last_part = 2 if content_mib == 6 else 32
    api_port, caddy_port = _free_port(), _free_port()
    environment, profile = _api_environment(fixture, prefix, tmp_path, part_bytes, markers, last_part)
    environment["WORKSTREAM_A19_API_PORT"] = str(api_port)
    for name, key in (("xdg-config", "XDG_CONFIG_HOME"), ("xdg-data", "XDG_DATA_HOME")):
        private = tmp_path / name
        private.mkdir(mode=0o700)
        environment[key] = str(private)
    environment["PYTHONPATH"] = os.pathsep.join((str(BACKEND), str(BACKEND / "tests"), str(REPOSITORY)))
    api_log, caddy_log = tmp_path / "api.log", tmp_path / "caddy.log"
    api_output = api_log.open("wb")
    api = subprocess.Popen([sys.executable, "-c", API_CODE], cwd=BACKEND,
                           env=environment, stdout=api_output, stderr=api_output)
    caddy = None
    caddy_output = None
    request = None
    try:
        await _listen(api_port, api, api_log)
        config = _caddy_config(binary, tmp_path, api_port, caddy_port)
        caddy_output = caddy_log.open("wb")
        caddy = subprocess.Popen([str(binary), "run", "--config", str(config)],
                                 env=environment, stdout=caddy_output, stderr=caddy_output)
        await _listen(caddy_port, caddy, caddy_log)
        emitted = []
        samples = []

        async def sample() -> None:
            while request is not None and not request.done():
                samples.append({"at": time.monotonic(), "api_rss": _rss(api.pid),
                                "caddy_rss": _rss(caddy.pid), "client_rss": _rss(os.getpid()),
                                "scratch_bytes": _disk_bytes(tmp_path / "scratch"),
                                "emitted_bytes": emitted[0] if emitted else 0})
                await asyncio.sleep(0.2)

        async with httpx.AsyncClient(timeout=None) as client:
            headers = {
                "Host": "workstream.example.test", "Authorization": "Bearer a19-measurement-token",
                "Content-Type": "application/zip", "X-Task-Assignment-Id": str(fixture.assignment),
                "X-Submission-Summary": "Measured bounded source upload",
                "X-Contributor-Attestation": "I completed the measured work",
                "Idempotency-Key": str(new_record_id()),
            }
            request = asyncio.create_task(client.post(
                f"http://127.0.0.1:{caddy_port}/api/v1/tasks/{fixture.task}/submissions",
                headers=headers, content=_zip_body(content_mib, emitted)))
            sampler = asyncio.create_task(sample())
            await _wait_file(markers / "first", timeout=90)
            blocked_at = emitted[0]
            await asyncio.sleep(2)
            blocked_growth = emitted[0] - blocked_at
            assert content_mib == 6 or blocked_growth < content_mib * MIB // 4
            (markers / "release-first").touch()
            await _wait_file(markers / "last", timeout=240)
            response = await asyncio.wait_for(request, timeout=125)
            await sampler
        timeline = tmp_path / "a19-timeline.json"
        timeline.write_text(json.dumps(samples, separators=(",", ":")))
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "submission_infrastructure_unavailable"
        assert int((markers / "completed").read_text()) == last_part - 1
        assert emitted[0] > content_mib * MIB and emitted[0] < 500 * MIB
        assert samples
        assert max(row["scratch_bytes"] for row in samples) < 2 * MIB
        async with fixture.factory() as session:
            state = (await session.execute(text(
                "SELECT o.id,o.state AS operation_state,o.failure_code,o.accepted_at,"
                "c.accounted_bytes,c.state AS charge_state "
                "FROM submission_intake_operations o JOIN submission_source_charges c "
                "ON c.operation_id=o.id WHERE o.task_id=:task"
            ), {"task": fixture.task})).one()
            assert state.operation_state == "failed" and state.failure_code == "submission_infrastructure_unavailable"
            assert state.accepted_at is None and state.accounted_bytes == 500 * MIB
            assert state.charge_state == "reserved"
        result = {
            "content_mib": content_mib, "raw_bytes_emitted": emitted[0],
            "provider_part_bytes": part_bytes, "held_part_number": last_part,
            "provider_completed_parts": last_part - 1,
            "blocked_client_growth_bytes": blocked_growth,
            "peak_api_rss_bytes": max(row["api_rss"] for row in samples),
            "peak_caddy_rss_bytes": max(row["caddy_rss"] for row in samples),
            "peak_client_rss_bytes": max(row["client_rss"] for row in samples),
            "peak_api_scratch_bytes": max(row["scratch_bytes"] for row in samples),
            "timeline": str(timeline),
            "upload_total_seconds": profile["upload_total_seconds"],
            "result": "503_provider_stall_retained_charge",
        }
        print("A19_MEASUREMENT=" + json.dumps(result, sort_keys=True), flush=True)
    finally:
        if request is not None and not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
        if caddy is not None:
            _stop(caddy, caddy_output)
        _stop(api, api_output)
