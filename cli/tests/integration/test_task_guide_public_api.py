"""Built CLI original upload/download through real API, AUTH, PostgreSQL and ART."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "tests"))
sys.path.insert(0, str(BACKEND / "scripts"))

from api_contract_e2e import find_free_port  # noqa: E402
from app.main import create_app  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.identifiers import new_record_id  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactReplica  # noqa: E402
from tests.test_guide_document_intake import _open_store  # noqa: E402
from tests.conftest import (  # noqa: E402
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.tasks.guide_document_fixtures import (  # noqa: E402
    base_task_database_env as base_task_database_env,
    task_client as _task_client,
    guide_world as _guide_world,
)
from tests.test_tasks import auth_headers, set_dev_actor  # noqa: E402


@pytest.fixture
def task_database_env(base_task_database_env, monkeypatch, tmp_path):
    endpoint = os.environ.get("WORKSTREAM_TEST_MINIO_ENDPOINT")
    if endpoint:
        bucket = os.environ.get("WORKSTREAM_TEST_MINIO_BUCKET")
        prefix = os.environ.get("WORKSTREAM_TEST_MINIO_PREFIX")
        if not bucket or not prefix:
            pytest.fail("MinIO CLI proof requires its owned bucket and prefix")
        values = {
            "ARTIFACT_STORE_BACKEND": "s3_compatible",
            "ARTIFACT_S3_PROVIDER_PROFILE": "minio",
            "ARTIFACT_S3_REGION": "us-east-1",
            "ARTIFACT_S3_BUCKET": bucket,
            "ARTIFACT_S3_ENDPOINT_URL": endpoint,
            "ARTIFACT_S3_PRIVATE_PREFIX": f"{prefix}/cli-guide-upload",
            "ARTIFACT_S3_ADDRESSING_STYLE": "path",
            "ARTIFACT_S3_CREDENTIAL_MODE": "local_static",
            "ARTIFACT_S3_ACCESS_KEY_ID": "workstream-minio",
            "ARTIFACT_S3_SECRET_ACCESS_KEY": "workstream-minio-secret-key",
            "ARTIFACT_SCRATCH_ROOT": str(tmp_path / "scratch"),
        }
    else:
        # The independent hosted CLI workflow owns PostgreSQL and uses local ART;
        # the backend lanes separately retain provider custody evidence.
        (tmp_path / "originals").mkdir(mode=0o700)
        values = {
            "ARTIFACT_STORE_BACKEND": "local",
            "ARTIFACT_LOCAL_ROOT": str(tmp_path / "originals"),
            "ARTIFACT_SCRATCH_ROOT": str(tmp_path / "scratch"),
        }
    values |= {
        "CELERY_BROKER_URL": "memory://",
        "CELERY_TASK_ALWAYS_EAGER": "false",
    }
    for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
        values[f"ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(1024 * 1024)
    for name, value in values.items():
        monkeypatch.setenv("WORKSTREAM_" + name, value)
    get_settings.cache_clear()
    yield base_task_database_env
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def task_client(task_database_env):
    async for client in _task_client.__wrapped__(task_database_env):
        yield client


@pytest_asyncio.fixture
async def guide_world(task_client, monkeypatch):
    return await _guide_world.__wrapped__(task_client, monkeypatch)


async def exercise_original_upload(cli, origin, world, tmp_path, monkeypatch):
    """Public creation/upload plus independent stored-original parity; no fake ART."""
    set_dev_actor(
        monkeypatch, roles="project_manager", subject="project-manager-subject"
    )
    declaration = tmp_path / "guide.json"
    declaration.write_text(
        json.dumps(
            {
                "version": "cli-original-upload",
                "task_examples": [
                    {"content": "Evaluate the evidence against the guide."}
                ],
                "documents": [
                    {"label": "Instructions.md", "media_type": "text/markdown"}
                ],
            }
        )
    )
    created = await asyncio.to_thread(
        cli,
        origin,
        "task-token",
        "project",
        "guide",
        "create",
        world.project["id"],
        "--input",
        str(declaration),
        "--idempotency-key",
        str(new_record_id()),
        "-o",
        "json",
    )
    assert created.returncode == 0, created.stderr
    guide = json.loads(created.stdout)
    assert (
        guide["status"] == "draft" and guide["setup"]["status"] == "awaiting_documents"
    )
    document = guide["documents"][0]["document_id"]
    original = world.originals[0]
    path = tmp_path / "original.md"
    path.write_bytes(original)
    key = str(new_record_id())

    async def upload(*, selectors=None, media="text/markdown", upload_key=key):
        return await asyncio.to_thread(
            cli,
            origin,
            "task-token",
            "project",
            "guide",
            "upload",
            *(selectors or (world.project["id"], guide["id"], document)),
            "--file",
            str(path),
            "--media-type",
            media,
            "--idempotency-key",
            upload_key,
            "-o",
            "json",
        )

    # Alternate supported UUID spelling reaches the real router unchanged.
    selectors = tuple(
        value.replace("-", "") for value in (world.project["id"], guide["id"], document)
    )
    wrong_media = await upload(
        selectors=selectors,
        media="application/pdf",
        upload_key=str(new_record_id()),
    )
    assert wrong_media.returncode == 1 and wrong_media.stdout == ""
    assert json.loads(wrong_media.stderr)["error"]["status"] == 422
    stored = await upload(selectors=selectors)
    assert stored.returncode == 0, stored.stderr
    receipt = json.loads(stored.stdout)
    assert receipt == {
        "document_id": document,
        "sha256": "sha256:" + hashlib.sha256(original).hexdigest(),
        "byte_count": len(original),
        "status": "document_stored",
        "replayed": False,
    }
    async with db_session.get_session_factory()() as session:
        put = (
            await session.scalars(
                select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.guide_source_item_id == document,
                )
            )
        ).one()
        replica = await session.get(ArtifactReplica, put.replica_id)
        assert put.status == "object_confirmed"
        assert (put.sha256, put.byte_count) == (
            receipt["sha256"],
            receipt["byte_count"],
        )
        object_ref = replica.provider_object_ref
        attempt_id = put.id
    bootstrap, store = _open_store(get_settings())
    try:
        assert b"".join([block async for block in store.open(object_ref)]) == original
    finally:
        store.close()
        bootstrap.close()
    replay = await upload()
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout) == receipt | {
        "status": "object_confirmed",
        "replayed": True,
    }
    path.write_bytes(original + b"changed")
    conflict = await upload()
    assert conflict.returncode == 1 and conflict.stdout == ""
    assert json.loads(conflict.stderr)["error"]["status"] == 409
    path.write_bytes(original)
    wrong = await upload(selectors=(world.project["id"], world.guide["id"], document))
    assert wrong.returncode == 1 and json.loads(wrong.stderr)["error"]["status"] == 404
    set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
    denied = await upload()
    assert denied.returncode == 1 and denied.stdout == ""
    assert json.loads(denied.stderr)["error"]["status"] == 404
    async with db_session.get_session_factory()() as session:
        current = (
            await session.scalars(
                select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.guide_source_item_id == document,
                )
            )
        ).one()
        assert current.id == attempt_id and current.replica_id == replica.id
        assert (current.sha256, current.byte_count) == (
            receipt["sha256"],
            len(original),
        )


@pytest.mark.asyncio
async def test_installed_cli_reads_and_downloads_real_assigned_originals(
    cli, guide_world, task_client, tmp_path, monkeypatch
):
    port = find_free_port()
    origin = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            host="127.0.0.1",
            port=port,
            log_level="error",
            access_log=False,
        )
    )
    serving = asyncio.create_task(server.serve())
    try:
        async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
            for _ in range(100):
                if serving.done():
                    await serving
                    raise AssertionError("API exited before readiness")
                try:
                    if (await client.get(origin + "/api/v1/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("API readiness timeout")
        await exercise_original_upload(cli, origin, guide_world, tmp_path, monkeypatch)
        directory = tmp_path / "downloaded"
        directory.mkdir()
        result = await asyncio.to_thread(
            cli,
            origin,
            "task-token",
            "task",
            "guide",
            guide_world.task["id"],
            "--download",
            str(directory),
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        documents = json.loads(result.stdout)
        assert len(documents) == len(guide_world.originals) == 2
        for document, original, extension in zip(
            documents, guide_world.originals, ("md", "pdf"), strict=True
        ):
            assert (
                directory / f"{document['document_id']}.{extension}"
            ).read_bytes() == original
        assert (
            "task_examples" not in result.stdout
            and "PRIVATE SETUP EXAMPLE" not in result.stdout
        )
        set_dev_actor(
            monkeypatch, roles="project_manager", subject="project-manager-subject"
        )
        revoke = await task_client.post(
            f"/api/v1/projects/{guide_world.project['id']}/role-grants/{guide_world.grant['grant_id']}/revoke",
            headers=auth_headers(),
            json={"reason": "Live CLI document revocation control"},
        )
        assert revoke.status_code == 200, revoke.text
        set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
        denied = await asyncio.to_thread(
            cli,
            origin,
            "task-token",
            "task",
            "guide",
            guide_world.task["id"],
            "-o",
            "json",
        )
        assert denied.returncode == 1 and denied.stdout == ""
        assert json.loads(denied.stderr)["error"]["status"] == 404
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=10)
