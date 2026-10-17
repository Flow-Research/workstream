"""C9: a Project Manager reads back each uploaded guide original, verified, through MinIO."""

import hashlib

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as db_session
from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactReplica
from tests.tasks.guide_document_fixtures import (
    base_task_database_env as base_task_database_env,
    guide_world as guide_world,
    task_client as task_client,
    task_database_env as task_database_env,
)
from tests.test_tasks import auth_headers
from .support import FINANCE, as_admin, as_manager, get_ok, project_path


def _content(world, index=0):
    document = world.guide["documents"][index]["document_id"]
    return project_path(world.project["id"], f"/guides/{world.guide['id']}/documents/{document}/content")


async def _replica(world, index=0):
    async with db_session.get_session_factory()() as session:
        attempt = (await session.scalars(select(ArtifactPutAttempt).where(
            ArtifactPutAttempt.guide_source_item_id == world.guide["documents"][index]["document_id"],
        ))).one()
        return await session.get(ArtifactReplica, attempt.replica_id)


async def test_manager_reads_back_each_uploaded_original_with_its_declared_commitment(task_client, guide_world, monkeypatch):
    world = guide_world
    as_manager(monkeypatch)
    detail = await get_ok(task_client, project_path(world.project["id"], f"/guides/{world.guide['id']}"))
    for index, original in enumerate(world.originals):
        declared = detail["documents"][index]
        assert declared["document_id"] == world.guide["documents"][index]["document_id"]
        assert (declared["ingest_state"], declared["sha256"], declared["byte_count"]) == (
            "uploaded", "sha256:" + hashlib.sha256(original).hexdigest(), len(original),
        )
        read = await task_client.get(_content(world, index), headers=auth_headers())
        assert read.status_code == 200, read.text
        assert read.content == original
        assert read.headers["content-type"].partition(";")[0] == declared["media_type"]
        assert int(read.headers["content-length"]) == len(original)
        assert read.headers["cache-control"] == "private, no-store"
        assert read.headers["x-content-type-options"] == "nosniff"
        assert read.headers["content-disposition"] == f'attachment; filename="{declared["document_id"]}"'


async def test_denied_caller_gets_the_concealed_answer_before_any_provider_io(task_client, guide_world, monkeypatch):
    world = guide_world
    opened = []

    def refuse(*_args, **_kwargs):
        opened.append(True)
        raise AssertionError("the provider opened for a denied read")

    await as_admin(task_client, monkeypatch, FINANCE, "finance_authority", project=world.project["id"])
    monkeypatch.setattr("app.adapters.artifacts.create_artifact_store_bootstrap", refuse)
    denied = await task_client.get(_content(world), headers=auth_headers())
    assert denied.status_code == 404 and denied.json()["error"]["code"] == "project_authorization_resource_not_found"
    assert world.originals[0] not in denied.content and opened == []


async def test_invalid_replica_custody_is_unavailable_without_bytes(task_client, guide_world, monkeypatch):
    world = guide_world
    replica = await _replica(world)
    async with db_session.get_session_factory()() as session, session.begin():
        (await session.get(ArtifactReplica, replica.id)).integrity_state = "invalid"
    as_manager(monkeypatch)
    response = await task_client.get(_content(world), headers=auth_headers())
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "guide_document_integrity_unavailable"
    assert world.originals[0] not in response.content and replica.provider_object_ref not in response.text


@pytest.mark.parametrize("damage", ("digest", "size"))
async def test_damaged_stored_original_never_serves_partial_bytes(task_client, guide_world, monkeypatch, damage):
    from app.adapters.artifacts.s3_compatible import S3CompatibleArtifactStore
    from tests.test_guide_document_intake import _open_store

    world = guide_world
    replica = await _replica(world)
    settings = get_settings()
    bootstrap, store = _open_store(settings)
    try:
        assert isinstance(store, S3CompatibleArtifactStore)
        original = world.originals[0]
        damaged = b"X" + original[1:] if damage == "digest" else original + b"EXTRA"
        async with store._client() as s3:
            await s3.put_object(
                Bucket=settings.artifact_s3_bucket, Key=store._object_key(replica.provider_object_ref), Body=damaged,
            )
    finally:
        store.close()
        bootstrap.close()
    as_manager(monkeypatch)
    response = await task_client.get(_content(world), headers=auth_headers())
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "guide_document_integrity_unavailable"
    assert world.originals[0] not in response.content
