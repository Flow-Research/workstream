"""Public upload through MinIO, real activation/claim, then exact original reads."""

import hashlib
import os
from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as db_session
from app.modules.artifacts.models import (
    ArtifactPutAttempt,
    ArtifactOperationReceipt,
    ArtifactReplica,
)
from app.modules.projects.models import ProjectGuide
from app.modules.actors.models import ActorIdentityLink
from tests.project_create_fixtures import (
    seed_active_guide_for_downstream_test,
    grant_fixture_admin_role,
)
from tests.test_tasks import (
    task_database_env as _base_task_database_env,
    task_client as task_client,
    auth_headers,
    create_policy_bundle_for_guide,
    create_ready_task,
    admit_and_grant_project_submitter,
    set_dev_actor,
)

base_task_database_env = _base_task_database_env


@pytest.fixture
def task_database_env(base_task_database_env, monkeypatch, tmp_path):
    values = {
        "ARTIFACT_STORE_BACKEND": "s3_compatible",
        "ARTIFACT_S3_PROVIDER_PROFILE": "minio",
        "ARTIFACT_S3_REGION": "us-east-1",
        "ARTIFACT_S3_ADDRESSING_STYLE": "path",
        "ARTIFACT_S3_BUCKET": os.environ["WORKSTREAM_TEST_MINIO_BUCKET"],
        "ARTIFACT_S3_ENDPOINT_URL": os.environ["WORKSTREAM_TEST_MINIO_ENDPOINT"],
        "ARTIFACT_S3_PRIVATE_PREFIX": f"{os.environ['WORKSTREAM_TEST_MINIO_PREFIX']}/pilot13/{uuid4().hex}",
        "ARTIFACT_S3_CREDENTIAL_MODE": "local_static",
        "ARTIFACT_S3_ACCESS_KEY_ID": "workstream-minio",
        "ARTIFACT_S3_SECRET_ACCESS_KEY": "workstream-minio-secret-key",
        "ARTIFACT_SCRATCH_ROOT": str(tmp_path / "scratch"),
        "CELERY_TASK_ALWAYS_EAGER": "false",
        "CELERY_BROKER_URL": "memory://",
    }
    for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
        values[f"ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(1024 * 1024)
    for name, value in values.items():
        monkeypatch.setenv("WORKSTREAM_" + name, value)
    get_settings.cache_clear()
    yield base_task_database_env
    get_settings.cache_clear()


@dataclass
class GuideWorld:
    project: dict
    guide: dict
    task: dict
    grant: dict
    originals: tuple[bytes, ...]


async def activate_uploaded_guide(client, project_id, monkeypatch, *, version="v1"):
    """Agent findings are scripted; original upload, custody and activation are real."""
    from app.workers.project_setup import run_project_guide_compilation
    from types import SimpleNamespace

    monkeypatch.setattr(
        run_project_guide_compilation,
        "apply_async",
        lambda **kwargs: SimpleNamespace(id=kwargs["task_id"]),
    )
    created = await client.post(
        f"/api/v1/projects/{project_id}/guides",
        headers=auth_headers(),
        json={
            "version": version,
            "task_examples": [{"content": "PRIVATE SETUP EXAMPLE"}],
            "documents": [
                {"label": "guide.md", "media_type": "text/markdown"},
                {"label": "rubric.pdf", "media_type": "application/pdf"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    originals = (
        f"# {version} guide\n\nFollow the locked original. 雪\n".encode(),
        f"%PDF-1.7\n{version} rubric original\n%%EOF".encode(),
    )
    for document, original, media_type in zip(
        guide["documents"], originals, ("text/markdown", "application/pdf"), strict=True
    ):
        stored = await client.post(
            f"/api/v1/projects/{project_id}/guides/{guide['id']}/documents/{document['document_id']}/content",
            headers=auth_headers() | {"Content-Type": media_type},
            content=original,
        )
        assert stored.status_code == 202, stored.text
        assert stored.json()["sha256"] == "sha256:" + hashlib.sha256(original).hexdigest()
        assert stored.json()["byte_count"] == len(original)
    await create_policy_bundle_for_guide(client, project_id, guide["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(), project_id=project_id, guide_id=guide["id"]
    )
    async with db_session.get_session_factory()() as session:
        assert (await session.get(ProjectGuide, guide["id"])).status == "active"
        for document, original, media_type in zip(
            guide["documents"], originals, ("text/markdown", "application/pdf"), strict=True
        ):
            put = (
                await session.scalars(
                    select(ArtifactPutAttempt).where(
                        ArtifactPutAttempt.guide_source_item_id == document["document_id"],
                    )
                )
            ).one()
            receipt = await session.get(ArtifactOperationReceipt, put.receipt_id)
            replica = await session.get(ArtifactReplica, put.replica_id)
            assert put.status == "object_confirmed" and receipt.outcome == "document_stored"
            assert (
                receipt.replica_id == replica.id
                and receipt.provider_object_ref == replica.provider_object_ref
            )
            assert (put.sha256, put.byte_count, put.media_type) == (
                "sha256:" + hashlib.sha256(original).hexdigest(),
                len(original),
                media_type,
            )
            from tests.test_guide_document_intake import _open_store

            bootstrap, store = _open_store(get_settings())
            try:
                assert (
                    b"".join([block async for block in store.open(replica.provider_object_ref)])
                    == original
                )
            finally:
                store.close()
                bootstrap.close()
    return guide, originals


@pytest.fixture
async def guide_world(task_client, monkeypatch):
    async with db_session.get_session_factory()() as session, session.begin():
        manager = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == "flow-test",
                ActorIdentityLink.subject == "project-manager-subject",
            )
        )
        await grant_fixture_admin_role(
            session, manager.actor_profile_id, role="access_administrator", scope="system"
        )
    provision = await task_client.post(
        "/api/v1/service-actors",
        headers=auth_headers(),
        json={
            "service_identity": "workstream.artifact.put_resolver",
            "subject": "pilot13-put-resolver",
            "reason": "Real original read integration proof",
        },
    )
    assert provision.status_code == 201, provision.text
    project = await task_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Assigned guide original",
            "slug": "pilot13-" + uuid4().hex,
        },
    )
    assert project.status_code == 201, project.text
    project = project.json()
    guide, originals = await activate_uploaded_guide(task_client, project["id"], monkeypatch)
    task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "pilot13-alice"
    )
    claim = await task_client.post(
        f"/api/v1/tasks/{task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "Read assigned instructions"},
    )
    assert claim.status_code == 200, claim.text
    start = await task_client.post(
        f"/api/v1/tasks/{task['id']}/start",
        headers=auth_headers(),
        json={"reason": "Work from exact guide"},
    )
    assert start.status_code == 200, start.text
    set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
    return GuideWorld(project, guide, task, grant, originals)
