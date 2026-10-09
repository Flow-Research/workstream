"""PILOT-13 assigned original isolation, custody, integrity and history proof."""

import asyncio
import hashlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactReplica
from app.modules.actors.models import ActorIdentityLink
from tests.tasks.guide_document_fixtures import (
    base_task_database_env as base_task_database_env,
    task_database_env as task_database_env,
    task_client as task_client,
    guide_world as guide_world,
    activate_uploaded_guide,
)
from tests.test_tasks import (
    auth_headers,
    set_dev_actor,
    admit_and_grant_project_submitter,
    create_active_project,
)
from app.adapters.tasks import task_commands
from app.adapters.audit import task_transition_audit
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from tests.authorization.task_authority.test_concurrency import actor_context


def content_path(world, document_id=None):
    return f"/api/v1/tasks/{world.task['id']}/guide/documents/{document_id or world.guide['documents'][0]['document_id']}/content"


async def test_assigned_originals_are_ordered_and_verified(task_client, guide_world):
    context = await task_client.get(
        f"/api/v1/tasks/{guide_world.task['id']}/work-context", headers=auth_headers()
    )
    assert context.status_code == 200, context.text
    documents = context.json()["guide_documents"]
    assert len(documents) == 2
    assert "PRIVATE SETUP EXAMPLE" not in context.text and "task_examples" not in context.text
    actor = await actor_context(guide_world.grant["actor_profile_id"])
    async with db_session.get_session_factory()() as session:
        commands = task_commands(
            session,
            authorization=PreparedTaskAuthorization(session, actor),
            audit=task_transition_audit(session),
            actor_profile_id=actor.actor_profile_id,
            settings=get_settings(),
        )
        async with commands.contributor_guide_document(
            UUID(guide_world.task["id"]), UUID(documents[0]["document_id"])
        ) as prepared:
            assert not session.in_transaction()
            assert b"".join([chunk async for chunk in prepared.stream]) == guide_world.originals[0]
    for index, (document, original) in enumerate(
        zip(documents, guide_world.originals, strict=True)
    ):
        assert set(document) == {
            "document_id",
            "order",
            "label",
            "media_type",
            "byte_count",
            "sha256",
            "read_reference",
        }
        assert document["document_id"] == guide_world.guide["documents"][index]["document_id"]
        assert document["order"] == index
        assert document["label"] == ("guide.md", "rubric.pdf")[index]
        assert document["media_type"] == ("text/markdown", "application/pdf")[index]
        assert (document["sha256"], document["byte_count"]) == (
            "sha256:" + hashlib.sha256(original).hexdigest(),
            len(original),
        )
        read = await task_client.get(document["read_reference"], headers=auth_headers())
        assert read.status_code == 200, read.text
        assert read.content == original and read.headers["cache-control"] == "private, no-store"
        assert int(read.headers["content-length"]) == len(original)
        assert read.headers["content-type"].partition(";")[0] == (
            "text/markdown",
            "application/pdf",
        )[index]


async def test_unassigned_and_foreign_actors_are_concealed(task_client, guide_world, monkeypatch):
    world = guide_world
    for subject in ("pilot13-bob", "pilot13-foreign"):
        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
        project_id = (
            world.project["id"]
            if subject == "pilot13-bob"
            else (await create_active_project(task_client, slug="pilot13-foreign"))["id"]
        )
        await admit_and_grant_project_submitter(task_client, monkeypatch, project_id, subject)
        denied = await task_client.get(content_path(world), headers=auth_headers())
        assert denied.status_code == 404, denied.text
        context = await task_client.get(
            f"/api/v1/tasks/{world.task['id']}/work-context", headers=auth_headers()
        )
        assert context.status_code == 404, context.text
    denied = await task_client.get(content_path(world))
    assert denied.status_code == 401
    set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
    wrong = await task_client.get(content_path(world, str(new_record_id())), headers=auth_headers())
    assert wrong.status_code == 404, wrong.text


@pytest.mark.parametrize("inactive", ("grant", "profile", "link"))
async def test_original_read_requires_current_authority(
    task_client, guide_world, inactive, monkeypatch
):
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == guide_world.grant["actor_profile_id"]
            )
        )
        paths = {
            "grant": f"/api/v1/projects/{guide_world.project['id']}/role-grants/{guide_world.grant['grant_id']}/revoke",
            "profile": f"/api/v1/actors/{guide_world.grant['actor_profile_id']}/suspend",
            "link": f"/api/v1/actor-identity-links/{link.id}/revoke",
        }
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    revoked = await task_client.post(
        paths[inactive],
        headers=auth_headers(),
        json={"reason": "Assigned document authority revocation proof"},
    )
    assert revoked.status_code == 200, revoked.text
    set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
    denied = await task_client.get(content_path(guide_world), headers=auth_headers())
    assert denied.status_code in (401, 404), denied.text
    assert b"%PDF" not in denied.content


async def test_successor_activation_keeps_task_originals(task_client, guide_world, monkeypatch):
    world = guide_world
    before = await task_client.get(
        f"/api/v1/tasks/{world.task['id']}/work-context", headers=auth_headers()
    )
    assert before.status_code == 200, before.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    newer, _ = await activate_uploaded_guide(
        task_client, world.project["id"], monkeypatch, version="v2"
    )
    set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
    after = await task_client.get(
        f"/api/v1/tasks/{world.task['id']}/work-context", headers=auth_headers()
    )
    assert after.status_code == 200, after.text
    assert after.json()["guide_documents"] == before.json()["guide_documents"]
    assert after.json()["guide"]["version"] == "v1"
    foreign = await task_client.get(
        content_path(world, newer["documents"][0]["document_id"]), headers=auth_headers()
    )
    assert foreign.status_code == 404, foreign.text
    retained = await task_client.get(content_path(world), headers=auth_headers())
    assert retained.status_code == 200 and retained.content == world.originals[0]
    # This is exact-selector port proof, not an implementation of TASK rebase.
    from app.adapters.projects import project_guide_document_scope_port
    from app.modules.projects.api.guide_documents import LockedGuideOriginalsRequest
    from app.modules.projects.models import GuideSourceSnapshot

    async with db_session.get_session_factory()() as session, session.begin():
        snapshot = await session.scalar(
            select(GuideSourceSnapshot).where(GuideSourceSnapshot.guide_id == newer["id"])
        )
        documents = await project_guide_document_scope_port(session).lock_task_originals(
            LockedGuideOriginalsRequest(
                UUID(world.project["id"]),
                UUID(newer["id"]),
                "v2",
                UUID(snapshot.id),
                snapshot.bundle_hash,
            )
        )
        assert [str(item.source.source_item_id) for item in documents] == [
            item["document_id"] for item in newer["documents"]
        ]


async def test_verified_read_serializes_revocation_then_serves_without_database_locks(
    task_client,
    guide_world,
    task_database_env,
    monkeypatch,
):
    """Observe a real PG waiter, not a timer-based claim that revocation waited."""
    from auth_concurrency_support import wait_for_named_database_lock
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.db.session import get_db_session
    from app.modules.artifacts.preparation import ArtifactPreparationService

    world = guide_world
    actor = await actor_context(world.grant["actor_profile_id"])
    locked, release, committed, revoked = (asyncio.Event() for _ in range(4))
    original = ArtifactPreparationService.prepare

    async def hold_verified_bytes(service, *args, **kwargs):
        prepared = await original(service, *args, **kwargs)
        locked.set()
        try:
            await release.wait()
        except BaseException:
            await prepared.close()
            raise
        return prepared

    monkeypatch.setattr(ArtifactPreparationService, "prepare", hold_verified_bytes)
    name = "pilot13-revoke-" + uuid4().hex
    engine = create_async_engine(
        task_database_env, connect_args={"server_settings": {"application_name": name}}
    )
    app = task_client._transport.app
    previous = app.dependency_overrides.get(get_db_session)

    async def revoke_session():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = revoke_session
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")

    async def read():
        async with db_session.get_session_factory()() as session:
            commands = task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, actor),
                audit=task_transition_audit(session),
                actor_profile_id=actor.actor_profile_id,
                settings=get_settings(),
            )
            async with commands.contributor_guide_document(
                UUID(world.task["id"]), UUID(world.guide["documents"][0]["document_id"])
            ) as prepared:
                assert not session.in_transaction()
                committed.set()
                await revoked.wait()
                return b"".join([chunk async for chunk in prepared.stream])

    async def revoke():
        response = await task_client.post(
            f"/api/v1/projects/{world.project['id']}/role-grants/{world.grant['grant_id']}/revoke",
            headers=auth_headers(),
            json={"reason": "Race exact original read"},
        )
        revoked.set()
        return response

    pending = []
    try:
        pending.append(asyncio.create_task(read()))
        await asyncio.wait_for(locked.wait(), 30)
        pending.append(asyncio.create_task(revoke()))
        await asyncio.wait_for(wait_for_named_database_lock(task_database_env, name), 30)
        release.set()
        await asyncio.wait_for(committed.wait(), 30)
        original_bytes, result = await asyncio.wait_for(asyncio.gather(*pending), 30)
        assert result.status_code == 200, result.text
        assert original_bytes == world.originals[0]
    finally:
        release.set()
        revoked.set()
        for running in pending:
            if not running.done():
                running.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        await engine.dispose()
    set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
    assert (await task_client.get(content_path(world), headers=auth_headers())).status_code == 404


async def test_cancelled_original_read_releases_preparation(task_client, guide_world):
    from app.adapters.artifacts import create_artifact_scratch_manager

    actor = await actor_context(guide_world.grant["actor_profile_id"])
    ready = asyncio.Event()

    async def hold():
        async with db_session.get_session_factory()() as session:
            commands = task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, actor),
                audit=task_transition_audit(session),
                actor_profile_id=actor.actor_profile_id,
                settings=get_settings(),
            )
            async with commands.contributor_guide_document(
                UUID(guide_world.task["id"]), UUID(guide_world.guide["documents"][0]["document_id"])
            ):
                ready.set()
                await asyncio.Event().wait()

    pending = asyncio.create_task(hold())
    try:
        await asyncio.wait_for(ready.wait(), 30)
    finally:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    manager = create_artifact_scratch_manager(get_settings())
    try:
        assert (await manager.usage()).reservation_count == 0
    finally:
        manager.close()


async def test_original_port_readers_share_custody_but_fence_replica_writers(
    task_client, guide_world, task_database_env, monkeypatch
):
    """Exercise new PROJECTS/ART locks; existing TASK/AUTH fences remain unchanged."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from auth_concurrency_support import wait_for_named_database_lock
    from app.adapters.artifacts import task_guide_documents_port
    from app.modules.artifacts.preparation import ArtifactPreparationService
    from app.modules.projects.models import GuideSourceSnapshot
    from app.modules.tasks.api.guide_documents import TaskGuideSelection

    world = guide_world
    async with db_session.get_session_factory()() as session:
        snapshot = await session.scalar(select(GuideSourceSnapshot).where(
            GuideSourceSnapshot.guide_id == world.guide["id"],
        ))
        selection = TaskGuideSelection(
            UUID(world.project["id"]), UUID(world.guide["id"]), "v1",
            UUID(snapshot.id), snapshot.bundle_hash,
        )
        attempt = await session.scalar(select(ArtifactPutAttempt).where(
            ArtifactPutAttempt.guide_source_item_id == world.guide["documents"][0]["document_id"],
        ))
        replica_id = attempt.replica_id
    entered, release = asyncio.Event(), asyncio.Event()
    readers = 0
    original = ArtifactPreparationService.prepare

    async def hold(service, *args, **kwargs):
        nonlocal readers
        prepared = await original(service, *args, **kwargs)
        readers += 1
        if readers == 2:
            entered.set()
        try:
            await release.wait()
        except BaseException:
            await prepared.close()
            raise
        return prepared

    monkeypatch.setattr(ArtifactPreparationService, "prepare", hold)
    name = "pilot13-replica-writer-" + uuid4().hex
    engine = create_async_engine(
        task_database_env, connect_args={"server_settings": {"application_name": name}}
    )

    async def read():
        async with db_session.get_session_factory()() as session, session.begin():
            port = task_guide_documents_port(session, get_settings())
            async with port.open(
                UUID(world.task["id"]), UUID(world.guide["documents"][0]["document_id"]), selection,
            ) as prepared:
                return b"".join([chunk async for chunk in prepared.stream])

    async def invalidate():
        async with AsyncSession(engine) as session, session.begin():
            replica = await session.get(ArtifactReplica, replica_id, with_for_update=True)
            replica.integrity_state = "invalid"

    pending = [asyncio.create_task(read()), asyncio.create_task(read())]
    try:
        await asyncio.wait_for(entered.wait(), 30)
        pending.append(asyncio.create_task(invalidate()))
        await asyncio.wait_for(wait_for_named_database_lock(task_database_env, name), 30)
        release.set()
        first, second, _ = await asyncio.wait_for(asyncio.gather(*pending), 30)
        assert first == second == world.originals[0]
    finally:
        release.set()
        for running in pending:
            if not running.done():
                running.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()
    response = await task_client.get(content_path(world), headers=auth_headers())
    assert response.status_code == 503 and b"%PDF" not in response.content


async def test_replica_invalidation_before_shared_lock_is_not_hidden_by_identity_map(
    task_client, guide_world, monkeypatch
):
    from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest

    original = SqlAlchemyGuideDocumentManifest.versions

    async def invalidate_after_resolution(manifest, *args):
        versions = await original(manifest, *args)
        async with db_session.get_session_factory()() as session, session.begin():
            replica = await session.get(ArtifactReplica, str(versions[0].replica_id))
            replica.integrity_state = "invalid"
        return versions

    monkeypatch.setattr(SqlAlchemyGuideDocumentManifest, "versions", invalidate_after_resolution)
    response = await task_client.get(content_path(guide_world), headers=auth_headers())
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "guide_document_integrity_unavailable"
    assert b"%PDF" not in response.content


async def test_public_original_disconnect_closes_provider_and_scratch(
    task_client, guide_world, monkeypatch
):
    """Exercise native FastAPI yield cleanup after StreamingResponse starts."""
    from app.adapters.artifacts import create_artifact_scratch_manager
    from app.adapters.artifacts.s3_compatible import S3CompatibleArtifactStoreBootstrap

    body_started = asyncio.Event()
    provider_closed = []
    original_close = S3CompatibleArtifactStoreBootstrap.close

    def observe_close(bootstrap):
        original_close(bootstrap)
        provider_closed.append(bootstrap)

    monkeypatch.setattr(S3CompatibleArtifactStoreBootstrap, "close", observe_close)
    received_request = False
    statuses = []

    async def receive():
        nonlocal received_request
        if not received_request:
            received_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await body_started.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])
        elif message["type"] == "http.response.body" and message.get("body"):
            assert statuses == [200]
            assert guide_world.originals[0].startswith(message["body"])
            body_started.set()
            # Response producer is cancelled by the native disconnect listener.
            await asyncio.Event().wait()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": content_path(guide_world),
        "raw_path": content_path(guide_world).encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (name.lower().encode(), value.encode()) for name, value in auth_headers().items()
        ],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 4242),
    }
    await asyncio.wait_for(task_client._transport.app(scope, receive, send), timeout=30)
    assert body_started.is_set() and statuses == [200]
    assert len(provider_closed) == 1
    manager = create_artifact_scratch_manager(get_settings())
    try:
        assert (await manager.usage()).reservation_count == 0
    finally:
        manager.close()


@pytest.mark.parametrize("damage", ("missing", "digest", "size"))
async def test_damaged_stored_original_never_serves_partial_bytes(task_client, guide_world, damage):
    world = guide_world
    async with db_session.get_session_factory()() as session:
        attempt = (
            await session.scalars(
                select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.guide_source_item_id
                    == world.guide["documents"][0]["document_id"],
                )
            )
        ).one()
        replica = await session.get(ArtifactReplica, attempt.replica_id)
        key = replica.provider_object_ref
    settings = get_settings()
    from tests.test_guide_document_intake import _open_store

    bootstrap, store = _open_store(settings)
    try:
        # The canonical key builder belongs to the adapter, not product/API code.
        from app.adapters.artifacts.s3_compatible import S3CompatibleArtifactStore

        assert isinstance(store, S3CompatibleArtifactStore)
        object_key = store._object_key(key)
        async with store._client() as s3:
            if damage == "missing":
                await s3.delete_object(Bucket=settings.artifact_s3_bucket, Key=object_key)
            else:
                original = world.originals[0]
                damaged = b"X" + original[1:] if damage == "digest" else original + b"EXTRA"
                await s3.put_object(
                    Bucket=settings.artifact_s3_bucket, Key=object_key, Body=damaged
                )
        response = await task_client.get(content_path(world), headers=auth_headers())
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "guide_document_integrity_unavailable"
        assert world.originals[0] not in response.content and key not in response.text
    finally:
        store.close()
        bootstrap.close()
    from app.adapters.artifacts import create_artifact_scratch_manager

    manager = create_artifact_scratch_manager(settings)
    try:
        assert (await manager.usage()).reservation_count == 0
    finally:
        manager.close()
