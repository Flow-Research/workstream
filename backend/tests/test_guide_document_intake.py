"""One public guide create owns its complete immutable document declaration."""

from uuid import uuid4
from types import SimpleNamespace
import os
import hashlib
import pytest

from sqlalchemy import select

from app.db import session as db_session
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    GuideSourceSnapshot,
    ProjectSetupRun,
)
from projects.client_fixtures import (
    auth_headers,
    project_client as project_client,
    project_database_env as _project_database_env,
)
from projects.guide_fixtures import create_project

base_project_database_env = _project_database_env


@pytest.fixture
def project_database_env(base_project_database_env, monkeypatch, tmp_path):
    from app.core.config import get_settings

    values = {
        "ARTIFACT_STORE_BACKEND": "s3_compatible",
        "ARTIFACT_S3_PROVIDER_PROFILE": "minio",
        "ARTIFACT_S3_REGION": "us-east-1",
        "ARTIFACT_S3_BUCKET": os.environ["WORKSTREAM_TEST_MINIO_BUCKET"],
        "ARTIFACT_S3_ENDPOINT_URL": os.environ["WORKSTREAM_TEST_MINIO_ENDPOINT"],
        "ARTIFACT_S3_PRIVATE_PREFIX": f"{os.environ['WORKSTREAM_TEST_MINIO_PREFIX']}/guide-intake/{uuid4().hex}",
        "ARTIFACT_S3_ADDRESSING_STYLE": "path",
        "ARTIFACT_S3_CREDENTIAL_MODE": "local_static",
        "ARTIFACT_S3_ACCESS_KEY_ID": "workstream-minio",
        "ARTIFACT_S3_SECRET_ACCESS_KEY": "workstream-minio-secret-key",
        "ARTIFACT_SCRATCH_ROOT": str(tmp_path / "scratch"),
        "CELERY_TASK_ALWAYS_EAGER": "false",
    }
    for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
        values[f"ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(1024 * 1024)
    for name, value in values.items():
        monkeypatch.setenv("WORKSTREAM_" + name, value)
    get_settings.cache_clear()
    yield base_project_database_env
    get_settings.cache_clear()


async def test_create_declares_document_set_and_replays_exact_ids(project_client):
    project = await create_project(project_client)
    path = f"/api/v1/projects/{project['id']}/guides"
    payload = {
        "version": "initial",
        "task_examples": [{"content": "Review a claim using the guide."}],
        "documents": [
            {"label": "z-guide.pdf", "media_type": "application/pdf"},
            {"label": "a-appendix.pdf", "media_type": "application/pdf"},
        ],
    }
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    created = await project_client.post(path, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert [item["label"] for item in body["documents"]] == ["z-guide.pdf", "a-appendix.pdf"]
    assert [item["order"] for item in body["documents"]] == [0, 1]
    assert body["setup"]["status"] == "awaiting_documents"
    assert "source_snapshot_id" not in body
    replay = await project_client.post(path, headers=headers, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json() == body
    conflict = await project_client.post(
        path, headers=headers, json=payload | {"documents": payload["documents"][::-1]}
    )
    assert conflict.status_code == 409, conflict.text
    async with db_session.get_session_factory()() as session:
        snapshots = (
            await session.scalars(
                select(GuideSourceSnapshot).where(GuideSourceSnapshot.guide_id == body["id"])
            )
        ).all()
        setups = (
            await session.scalars(
                select(ProjectSetupRun).where(ProjectSetupRun.guide_id == body["id"])
            )
        ).all()
        mutations = (
            await session.scalars(
                select(GuideMutationIdempotencyRecord).where(
                    GuideMutationIdempotencyRecord.project_id == project["id"]
                )
            )
        ).all()
        assert len(snapshots) == len(setups) == 1
        assert {row.action_id for row in mutations} == {
            "project.guide.create",
            "project.guide_source_snapshot.create",
        }
        assert len(mutations) == 2
        assert all(row.status == "committed" for row in mutations)
        assert len({row.idempotency_key for row in mutations}) == 1
        assert setups[0].source_snapshot_id == snapshots[0].id


@pytest.mark.parametrize(
    "invalid", ["content_type", "project", "guide", "document", "key", "declared_size", "setup_generation"]
)
async def test_upload_rejects_invalid_request_before_reading_body(project_client, invalid, monkeypatch):
    project = await create_project(project_client)
    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={
            "version": "initial",
            "task_examples": [{"content": "Review a claim."}],
            "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
        },
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    read = False

    async def body():
        nonlocal read
        read = True
        raise AssertionError("invalid upload must not read the request body")
        yield b""

    selectors = {
        "project": project["id"],
        "guide": guide["id"],
        "document": guide["documents"][0]["document_id"],
    }
    headers = auth_headers() | {"Content-Type": "application/pdf"}
    if invalid in selectors:
        selectors[invalid] = str(uuid4())
    elif invalid == "content_type":
        headers["Content-Type"] = "text/plain"
    elif invalid == "key":
        headers["Idempotency-Key"] = "invalid-key"
    elif invalid == "setup_generation":
        from dataclasses import replace
        from app.modules.projects.document_upload import ProjectGuideDocumentUploadTargets
        original_resolve = ProjectGuideDocumentUploadTargets.resolve
        async def drift(self, *args, for_update):
            target = await original_resolve(self, *args, for_update=for_update)
            return replace(target, setup_generation=target.setup_generation + 1) if for_update else target
        monkeypatch.setattr(ProjectGuideDocumentUploadTargets, "resolve", drift)
    else:
        headers["Content-Length"] = str(1024 * 1024 * 1024)
    response = await project_client.post(
        f"/api/v1/projects/{selectors['project']}/guides/{selectors['guide']}/documents/{selectors['document']}/content",
        headers=headers,
        content=body(),
    )
    assert response.status_code == {"key": 422, "content_type": 422, "declared_size": 413}.get(invalid, 404), (
        response.text
    )
    assert read is False
    await _assert_no_upload_effects()


@pytest.mark.parametrize("recover_callback", [False, True])
async def test_all_documents_stored_dispatches_once_through_minio(
    project_client, monkeypatch, recover_callback
):
    from app.core.config import get_settings
    from app.modules.actors.service_identities import ServiceIdentity
    from app.modules.artifacts.models import ArtifactReplica, ArtifactPutAttempt
    from app.workers.project_setup import run_project_guide_compilation
    from app.adapters.artifacts import internal_workers

    deliveries = []

    def publish(*, args, task_id):
        deliveries.append((args, task_id))
        return SimpleNamespace(id=task_id)

    monkeypatch.setattr(run_project_guide_compilation, "apply_async", publish)
    provision = await project_client.post(
        "/api/v1/service-actors",
        headers=auth_headers(),
        json={
            "service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
            "subject": "guide-intake-test-put-resolver",
            "reason": "Isolated guide upload proof.",
        },
    )
    assert provision.status_code == 201, provision.text
    project = await create_project(project_client)
    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={
            "version": "initial",
            "task_examples": [{"content": "Review a claim."}],
            "documents": [
                {"label": name, "media_type": "application/pdf"}
                for name in ("guide.pdf", "appendix.pdf")
            ],
        },
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    originals = [b"%PDF-1.7\nGuide fixture\n%%EOF", b"%PDF-1.7\nAppendix fixture\n%%EOF"]
    for index, (document, original) in enumerate(zip(guide["documents"], originals, strict=True)):
        path = f"/api/v1/projects/{project['id']}/guides/{guide['id']}/documents/{document['document_id']}/content"
        headers = auth_headers() | {"Content-Type": ("Application/PDF", "application/pdf; name=appendix.pdf")[index]}
        real_callback = internal_workers.continue_guide_setup_after_stored_document
        if index == 1 and recover_callback:

            async def unavailable_callback(_attempt_id):
                raise RuntimeError("injected callback failure")

            monkeypatch.setattr(
                internal_workers, "continue_guide_setup_after_stored_document", unavailable_callback
            )
        response = await project_client.post(path, headers=headers, content=original)
        if index == 1 and recover_callback:
            assert deliveries == []
            monkeypatch.setattr(
                internal_workers, "continue_guide_setup_after_stored_document", real_callback
            )

            async def recover(attempt_id):
                from uuid import UUID

                await real_callback(UUID(attempt_id))

            assert await internal_workers.scan_guide_setup_continuations(recover) == 1
            assert await internal_workers.scan_guide_setup_continuations(recover) == 0
        assert response.status_code == 202, response.text
        assert response.json()["sha256"] == "sha256:" + hashlib.sha256(original).hexdigest()
        assert set(response.json()) == {"document_id", "sha256", "byte_count", "status", "replayed"}
        assert len(deliveries) == index
        replay = await project_client.post(path, headers=headers, content=original)
        assert replay.status_code == 202, replay.text
        assert replay.json()["replayed"] is True
        assert len(deliveries) == index
        before_keys = await _stored_keys(get_settings())
        changed = await project_client.post(path, headers=headers, content=original + b"changed")
        assert changed.status_code == 409, changed.text
        another_key = await project_client.post(
            path, headers=auth_headers() | {"Content-Type": "application/pdf"}, content=original,
        )
        assert another_key.status_code == 409, another_key.text
        assert await _stored_keys(get_settings()) == before_keys
        assert len(deliveries) == index
        async with db_session.get_session_factory()() as session:
            run = await session.get(ProjectSetupRun, guide["setup"]["id"])
            assert run.status == ("awaiting_documents" if index == 0 else "queued")
    async with db_session.get_session_factory()() as session:
        attempts = (
            await session.scalars(
                select(ArtifactPutAttempt).where(ArtifactPutAttempt.project_id == project["id"])
            )
        ).all()
        replicas = (await session.scalars(select(ArtifactReplica))).all()
        assert len(attempts) == len(replicas) == 2
    bootstrap, store = _open_store(get_settings())
    try:
        stored = [
            b"".join([chunk async for chunk in store.open(row.provider_object_ref)])
            for row in replicas
        ]
        assert set(stored) == set(originals)
    finally:
        store.close()
        bootstrap.close()


async def test_create_replay_requires_current_manager_authority(project_client):
    from datetime import datetime, UTC
    from app.modules.authorization.models import AdminRoleGrant

    project = await create_project(project_client)
    path = f"/api/v1/projects/{project['id']}/guides"
    payload = {
        "version": "initial",
        "task_examples": [{"content": "Review a claim."}],
        "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
    }
    headers = auth_headers()
    first = await project_client.post(path, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    async with db_session.get_session_factory()() as session:
        grants = (
            await session.scalars(
                select(AdminRoleGrant).where(
                    AdminRoleGrant.role == "project_manager",
                    AdminRoleGrant.status == "active",
                )
            )
        ).all()
        assert grants
        for grant in grants:
            grant.status = "revoked"
            grant.version += 1
            grant.revoked_by_actor_profile_id = grant.target_actor_profile_id
            grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
            grant.revoked_reason = "Current-authority replay proof"
            grant.revoked_at = datetime.now(UTC)
        await session.commit()
    replay = await project_client.post(path, headers=headers, json=payload)
    assert replay.status_code == 403, replay.text
    assert "permission_not_granted" in replay.text
    async with db_session.get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(GuideMutationIdempotencyRecord).where(
                    GuideMutationIdempotencyRecord.project_id == project["id"],
                )
            )
        ).all()
        assert len(rows) == 2
        assert all(row.status == "committed" for row in rows)


async def test_late_create_failure_rolls_back_both_authorities_and_all_product_rows(
    project_client, monkeypatch
):
    from sqlalchemy import func
    from app.modules.projects.guide_mutation_repository import GuideMutationRepository
    from app.modules.projects.models import ProjectGuide, GuideSourceSnapshotItem
    from app.modules.tasks.models import AuditEvent

    project = await create_project(project_client)
    async with db_session.get_session_factory()() as session:
        before = await session.scalar(select(func.count()).select_from(AuditEvent))

    staged = []
    original_complete = GuideMutationRepository.complete

    async def fail_complete(self, record, **values):
        await original_complete(self, record, **values)
        if record.action_id != "project.guide.create":
            return
        await self._session.flush()
        for model, expected in ((ProjectGuide, 1), (GuideSourceSnapshot, 1),
                                (GuideSourceSnapshotItem, 1), (ProjectSetupRun, 1),
                                (GuideMutationIdempotencyRecord, 2)):
            count = await self._session.scalar(select(func.count()).select_from(model))
            assert count == expected
            staged.append(count)
        assert await self._session.scalar(select(func.count()).select_from(AuditEvent)) > before
        raise RuntimeError("injected complete-pair commit failure")

    monkeypatch.setattr(GuideMutationRepository, "complete", fail_complete)
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={
            "version": "initial",
            "task_examples": [{"content": "Review a claim."}],
            "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
        },
    )
    assert response.status_code == 500, response.text
    assert staged == [1, 1, 1, 1, 2]
    async with db_session.get_session_factory()() as session:
        for model in (
            ProjectGuide,
            GuideSourceSnapshot,
            GuideSourceSnapshotItem,
            ProjectSetupRun,
            GuideMutationIdempotencyRecord,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == before


async def test_concurrent_create_replays_one_paired_operation(project_client):
    import asyncio

    project = await create_project(project_client)
    payload = {
        "version": "initial",
        "task_examples": [{"content": "Review a claim."}],
        "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
    }
    path = f"/api/v1/projects/{project['id']}/guides"
    headers = auth_headers()
    results = await asyncio.gather(
        *(project_client.post(path, headers=headers, json=payload) for _ in range(2))
    )
    assert [result.status_code for result in results] == [201, 201], [
        result.text for result in results
    ]
    assert results[0].json() == results[1].json()
    from sqlalchemy import func
    from app.modules.projects.models import ProjectGuide, GuideSourceSnapshotItem
    async with db_session.get_session_factory()() as session:
        for model, expected in ((ProjectGuide, 1), (GuideSourceSnapshot, 1),
                                (GuideSourceSnapshotItem, 1), (ProjectSetupRun, 1),
                                (GuideMutationIdempotencyRecord, 2)):
            assert await session.scalar(select(func.count()).select_from(model)) == expected
        rows = (await session.scalars(select(GuideMutationIdempotencyRecord))).all()
        assert {row.action_id for row in rows} == {
            "project.guide.create", "project.guide_source_snapshot.create"}
        assert {str(row.idempotency_key) for row in rows} == {headers["Idempotency-Key"]}
        assert {row.status for row in rows} == {"committed"}


@pytest.mark.parametrize("guard_enabled", [True, False])
async def test_database_rejects_individually_valid_but_cross_key_creation_pair(
    project_client, monkeypatch, guard_enabled
):
    """Both decisions and rows are valid; only their shared replay key is wrong."""
    from app.modules.projects.guide_mutation_repository import GuideMutationRepository
    from sqlalchemy import func
    from app.modules.projects.models import ProjectGuide

    project = await create_project(project_client)
    original = GuideMutationRepository.reserve

    async def cross_key(self, **values):
        if values["action_id"] == "project.guide_source_snapshot.create":
            values["idempotency_key"] = uuid4()
        return await original(self, **values)

    monkeypatch.setattr(GuideMutationRepository, "reserve", cross_key)
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.exc import IntegrityError

    errors = []
    original_commit = AsyncSession.commit

    async def observe_commit(self):
        try:
            return await original_commit(self)
        except IntegrityError as error:
            errors.append(str(error.orig))
            raise

    monkeypatch.setattr(AsyncSession, "commit", observe_commit)
    guarded_tables = (
        "project_guides",
        "guide_source_snapshots",
        "guide_mutation_idempotency_records",
    )
    try:
        if not guard_enabled:
            async with db_session.get_session_factory()() as session, session.begin():
                for table in guarded_tables:
                    await session.execute(
                        text(f"alter table {table} disable trigger require_document_creation_pair")
                    )
        response = await project_client.post(
            f"/api/v1/projects/{project['id']}/guides",
            headers=auth_headers(),
            json={
                "version": "cross-key",
                "task_examples": [{"content": "Review a claim."}],
                "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
            },
        )
        if guard_enabled:
            assert response.status_code == 503, response.text
            assert len(errors) == 1
            assert "guide document creation pair is invalid" in errors[0]
        else:
            # Discriminating mutation: all unchanged authority/lineage guards pass.
            assert response.status_code == 201, response.text
            assert errors == []
        async with db_session.get_session_factory()() as session:
            for model, count in (
                (ProjectGuide, 1),
                (GuideSourceSnapshot, 1),
                (ProjectSetupRun, 1),
                (GuideMutationIdempotencyRecord, 2),
            ):
                assert await session.scalar(select(func.count()).select_from(model)) == (
                    0 if guard_enabled else count
                )
    finally:
        if not guard_enabled:
            async with db_session.get_session_factory()() as session, session.begin():
                for table in guarded_tables:
                    await session.execute(
                        text(f"alter table {table} enable trigger require_document_creation_pair")
                    )


def _open_store(settings):
    from app.adapters.artifacts import create_artifact_store_bootstrap
    from app.modules.artifacts.service import artifact_storage_namespace_spec
    from app.interfaces.artifacts import ArtifactStoreNamespaceClaim
    bootstrap = create_artifact_store_bootstrap(settings)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    store = bootstrap.initialize_after_namespace_claim(ArtifactStoreNamespaceClaim(
        adapter_identity=bootstrap.identity,
        namespace_identity=bootstrap.namespace_identity,
        namespace_fingerprint=namespace.namespace_fingerprint,
    ))
    return bootstrap, store


@pytest.mark.parametrize("missing", ["WORKSTREAM_TEST_MINIO_BUCKET", "WORKSTREAM_TEST_MINIO_PREFIX"])
def test_intake_fixture_requires_runner_owned_storage(monkeypatch, tmp_path, missing):
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_ENDPOINT", "http://127.0.0.1:9000")
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_BUCKET", "workstream-ci-proof")
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_PREFIX", "ci/isolated/proof")
    monkeypatch.delenv(missing)
    with pytest.raises(KeyError, match=missing):
        next(project_database_env.__wrapped__("unused-database", monkeypatch, tmp_path))


async def _stored_keys(settings):
    from scripts.run_isolated_tests import _minio_client
    async with _minio_client(settings.artifact_s3_endpoint_url) as client:
        result = await client.list_objects_v2(
            Bucket=settings.artifact_s3_bucket,
            Prefix=settings.artifact_s3_private_prefix + "/",
        )
    assert not result.get("IsTruncated", False)
    return {item["Key"] for item in result.get("Contents", [])}


@pytest.mark.parametrize("original", [b"", b"not a PDF", b"PK\x03\x04wrong container"])
async def test_invalid_bytes_are_correctable_and_leave_no_artifact(project_client, original):
    from sqlalchemy import func
    from app.core.config import get_settings
    from app.adapters.artifacts import create_artifact_scratch_manager
    from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactReplica, ArtifactAdmissionCharge
    project = await create_project(project_client)
    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides", headers=auth_headers(),
        json={"version": "initial", "task_examples": [{"content": "Review a claim."}],
              "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}]},
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/documents/{guide['documents'][0]['document_id']}/content",
        headers=auth_headers() | {"Content-Type": "application/pdf"}, content=original,
    )
    assert response.status_code == 422, response.text
    async with db_session.get_session_factory()() as session:
        for model in (ArtifactPutAttempt, ArtifactReplica, ArtifactAdmissionCharge):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        run = await session.get(ProjectSetupRun, guide["setup"]["id"])
        assert run.status == "awaiting_documents"
        assert run.celery_task_id is None
    settings = get_settings()
    assert await _stored_keys(settings) == set()
    manager = create_artifact_scratch_manager(settings)
    try:
        usage = await manager.usage()
        assert usage.reservation_count == usage.reserved_bytes == 0
    finally:
        manager.close()


@pytest.mark.parametrize("mode", ["distinct", "same_document", "aggregate_limit"])
async def test_concurrent_last_documents_dispatch_one_setup(project_client, monkeypatch, mode):
    import asyncio
    from sqlalchemy import func
    from app.core.config import get_settings
    from app.modules.actors.service_identities import ServiceIdentity
    from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactReplica
    from app.workers.project_setup import run_project_guide_compilation
    deliveries = []
    def publish(*, args, task_id):
        deliveries.append((args, task_id))
        return SimpleNamespace(id=task_id)
    monkeypatch.setattr(run_project_guide_compilation, "apply_async", publish)
    provision = await project_client.post("/api/v1/service-actors", headers=auth_headers(), json={
        "service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
        "subject": "guide-concurrent-put-resolver", "reason": "Isolated concurrent upload proof.",
    })
    assert provision.status_code == 201, provision.text
    project = await create_project(project_client)
    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides", headers=auth_headers(),
        json={"version": "initial", "task_examples": [{"content": "Review a claim."}],
              "documents": [{"label": label, "media_type": "application/pdf"} for label in ("guide.pdf", "appendix.pdf")]},
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    if mode == "aggregate_limit":
        app = project_client._transport.app
        app.state.settings = app.state.settings.model_copy(update={"project_agent_max_total_document_bytes": 40})
    same_headers = auth_headers() | {"Content-Type": "application/pdf"}
    async def upload(document):
        return await project_client.post(
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/documents/{document['document_id']}/content",
            headers=same_headers if mode == "same_document" else auth_headers() | {"Content-Type": "application/pdf"},
            content=b"%PDF-1.7\n" + document["label"].encode() + b"\n%%EOF",
        )
    documents = [guide["documents"][0]] * 2 if mode == "same_document" else guide["documents"]
    responses = await asyncio.gather(*(upload(document) for document in documents))
    assert sorted(response.status_code for response in responses) == (
        [202, 413] if mode == "aggregate_limit" else [202, 202]
    ), [response.text for response in responses]
    complete = mode == "distinct"
    assert len(deliveries) == int(complete)
    if complete:
        assert deliveries[0][0][-2:] == (guide["setup"]["id"], 1)
    async with db_session.get_session_factory()() as session:
        for model in (ArtifactPutAttempt, ArtifactReplica):
            assert await session.scalar(select(func.count()).select_from(model)) == (2 if complete else 1)
        run = await session.get(ProjectSetupRun, guide["setup"]["id"])
        assert run.status == ("queued" if complete else "awaiting_documents")
        assert run.celery_task_id == (deliveries[0][1] if complete else None)
    assert len(await _stored_keys(get_settings())) == (2 if complete else 1)


@pytest.mark.parametrize("source_mismatch", [False, True])
async def test_replay_reauthorizes_each_original_action(project_client, monkeypatch, source_mismatch):
    from app.modules.authorization.prepared import PreparedAuthorizationService
    project = await create_project(project_client)
    path = f"/api/v1/projects/{project['id']}/guides"
    payload = {"version": "initial", "task_examples": [{"content": "Review a claim."}],
               "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}]}
    headers = auth_headers()
    first = await project_client.post(path, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    calls = []
    prepare = PreparedAuthorizationService.prepare
    consume = PreparedAuthorizationService.consume
    async def observed_prepare(self, action, *args, **kwargs):
        calls.append(("prepare", action.value))
        return await prepare(self, action, *args, **kwargs)
    async def observed_consume(self, handle, action, *args, **kwargs):
        calls.append(("consume", action.value))
        decision = await consume(self, handle, action, *args, **kwargs)
        if source_mismatch and action.value == "project.guide_source_snapshot.create":
            return decision.model_copy(update={"resource_context_digest": "sha256:" + "0" * 64})
        return decision
    monkeypatch.setattr(PreparedAuthorizationService, "prepare", observed_prepare)
    monkeypatch.setattr(PreparedAuthorizationService, "consume", observed_consume)
    replay = await project_client.post(path, headers=headers, json=payload)
    assert replay.status_code == (409 if source_mismatch else 201), replay.text
    assert calls == [(phase, action) for action in (
        "project.guide.create", "project.guide_source_snapshot.create")
        for phase in ("prepare", "consume")]
    if source_mismatch:
        assert "idempotency_mismatch" in replay.text
    else:
        assert replay.json() == first.json()


async def _create_documents(client, project, labels=("guide.pdf",)):
    response = await client.post(
        f"/api/v1/projects/{project['id']}/guides", headers=auth_headers(),
        json={"version": "initial", "task_examples": [{"content": "Review a claim."}],
              "documents": [{"label": label, "media_type": "application/pdf"} for label in labels]},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _assert_no_upload_effects():
    from sqlalchemy import func
    from app.core.config import get_settings
    from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactReplica, ArtifactAdmissionCharge
    async with db_session.get_session_factory()() as session:
        for model in (ArtifactPutAttempt, ArtifactReplica, ArtifactAdmissionCharge):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        runs = (await session.scalars(select(ProjectSetupRun))).all()
        assert runs and all(run.status == "awaiting_documents" and run.celery_task_id is None for run in runs)
    assert await _stored_keys(get_settings()) == set()


@pytest.mark.parametrize("selector", ["project", "guide", "document"])
async def test_stored_foreign_document_selectors_are_concealed(project_client, selector):
    from sqlalchemy import func
    from app.modules.tasks.models import AuditEvent
    first = await create_project(project_client, name="First project")
    second = await create_project(project_client, name="Second project")
    guides = [await _create_documents(project_client, project) for project in (first, second)]
    selected = {"project": first["id"], "guide": guides[0]["id"],
                "document": guides[0]["documents"][0]["document_id"]}
    foreign = {"project": second["id"], "guide": guides[1]["id"],
               "document": guides[1]["documents"][0]["document_id"]}
    selected[selector] = foreign[selector]
    async with db_session.get_session_factory()() as session:
        before = await session.scalar(select(func.count()).select_from(AuditEvent))
    read = False
    async def body():
        nonlocal read
        read = True
        raise AssertionError("foreign selectors must be rejected before body consumption")
        yield b""
    response = await project_client.post(
        f"/api/v1/projects/{selected['project']}/guides/{selected['guide']}/documents/{selected['document']}/content",
        headers=auth_headers() | {"Content-Type": "application/pdf"}, content=body(),
    )
    assert response.status_code == 404, response.text
    assert not read
    await _assert_no_upload_effects()
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == before


@pytest.mark.parametrize("declared_length", [None, "1"])
async def test_actual_stream_limit_rejects_without_admission(project_client, declared_length):
    from app.adapters.artifacts import create_artifact_scratch_manager
    app = project_client._transport.app
    app.state.settings = app.state.settings.model_copy(update={"project_agent_max_document_bytes": 16})
    project = await create_project(project_client)
    guide = await _create_documents(project_client, project)
    consumed = []
    async def body():
        for chunk in (b"%PDF-1.7\n", b"a" * 16, b"must not be read"):
            consumed.append(chunk)
            yield chunk
    headers = auth_headers() | {"Content-Type": "application/pdf"}
    if declared_length is not None:
        headers["Content-Length"] = declared_length
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/documents/{guide['documents'][0]['document_id']}/content",
        headers=headers, content=body(),
    )
    assert response.status_code == 413, response.text
    assert consumed == [b"%PDF-1.7\n", b"a" * 16]
    await _assert_no_upload_effects()
    manager = create_artifact_scratch_manager(app.state.settings)
    try:
        usage = await manager.usage()
        assert usage.reservation_count == usage.reserved_bytes == 0
    finally:
        manager.close()


@pytest.mark.parametrize("remaining_scope", [None, "other_project"])
async def test_upload_rechecks_authority_before_body(project_client, remaining_scope):
    from datetime import datetime, UTC
    from app.modules.authorization.models import AdminRoleGrant
    first = await create_project(project_client, name="Target project")
    second = await create_project(project_client, name="Other project")
    guide = await _create_documents(project_client, first)
    await _create_documents(project_client, second)
    async with db_session.get_session_factory()() as session:
        grants = (await session.scalars(select(AdminRoleGrant).where(
            AdminRoleGrant.role == "project_manager", AdminRoleGrant.status == "active"))).all()
        assert len(grants) == 1
        grant = grants[0]
        if remaining_scope:
            session.add(AdminRoleGrant(
                id=uuid4(), target_actor_profile_id=grant.target_actor_profile_id,
                role="project_manager", scope_type="project", scope_project_id=second["id"],
                status="active", version=1,
                granted_by_actor_profile_id=grant.granted_by_actor_profile_id,
                granted_by_admin_role_grant_id=grant.granted_by_admin_role_grant_id,
                grant_reason="Authority only for the other persisted project",
            ))
        grant.status = "revoked"
        grant.version += 1
        grant.revoked_by_actor_profile_id = grant.target_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "Upload authority proof"
        grant.revoked_at = datetime.now(UTC)
        await session.commit()
    read = False
    async def body():
        nonlocal read
        read = True
        raise AssertionError("unauthorized upload must not read the body")
        yield b""
    response = await project_client.post(
        f"/api/v1/projects/{first['id']}/guides/{guide['id']}/documents/{guide['documents'][0]['document_id']}/content",
        headers=auth_headers() | {"Content-Type": "application/pdf"}, content=body(),
    )
    assert response.status_code == 404, response.text
    assert not read
    await _assert_no_upload_effects()


@pytest.mark.parametrize("fault,mutant", [
    (None, False), ("missing_source", False), ("missing_source", True),
    ("cross_key", False), ("cross_key", True), ("second_set", False), ("second_set", True),
    *[(fault, mutant) for fault in ("setup_status", "setup_step", "setup_ready_at", "setup_celery")
      for mutant in (False, True)],
])
async def test_raw_sql_creation_pair_custody(project_client, monkeypatch, fault, mutant):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from projects.guide_creation_sql import (
        capture_creation_graph, insert_graph, malformed_graph, second_source_graph,
        install_predicate_mutant,
    )
    project = await create_project(project_client)
    graph = await capture_creation_graph(project_client, project["id"], auth_headers(), monkeypatch)
    async with db_session.get_engine().connect() as connection:
        audit_before = await connection.scalar(text("select count(*) from audit_events"))
    async with db_session.get_engine().connect() as connection:
        transaction = await connection.begin()
        try:
            if mutant:
                await install_predicate_mutant(connection, fault)
            await insert_graph(connection, malformed_graph(graph, fault))
            if fault == "second_set":
                await insert_graph(connection, second_source_graph(graph))
            if fault and not mutant:
                with pytest.raises(IntegrityError, match="guide document creation pair is invalid") as error:
                    await connection.execute(text("set constraints require_document_creation_pair immediate"))
                assert error.value.orig.sqlstate == "23514"
            else:
                await connection.execute(text("set constraints all immediate"))
                expected_sets = 0 if fault == "missing_source" else 2 if fault == "second_set" else 1
                for table, expected in (("project_guides", 1), ("guide_source_snapshots", expected_sets),
                                        ("guide_source_snapshot_items", expected_sets),
                                        ("project_setup_runs", expected_sets),
                                        ("guide_mutation_idempotency_records", 1 + expected_sets)):
                    assert await connection.scalar(text(f"select count(*) from {table}")) == expected
                if fault == "cross_key":
                    assert await connection.scalar(text(
                        "select count(distinct idempotency_key) from guide_mutation_idempotency_records")) == 2
                if fault is None:
                    await transaction.commit()
        finally:
            if transaction.is_active:
                await transaction.rollback()
    async with db_session.get_engine().connect() as connection:
        for table in ("project_guides", "guide_source_snapshots", "guide_source_snapshot_items", "project_setup_runs"):
            assert await connection.scalar(text(f"select count(*) from {table}")) == (1 if fault is None else 0)
        assert await connection.scalar(text("select count(*) from guide_mutation_idempotency_records")) == (2 if fault is None else 0)
        assert await connection.scalar(text("select count(*) from audit_events")) == audit_before + (2 if fault is None else 0)


async def test_document_container_limit_rejects_before_admission(project_client):
    import io
    import zipfile
    from app.modules.artifacts.guide_formats import GuideFormatLimits
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in ("[Content_Types].xml", "_rels/.rels", "word/document.xml"):
            archive.writestr(name, "<document/>")
        for index in range(GuideFormatLimits().maximum_entries):
            archive.writestr(f"word/part-{index}.xml", "<part/>")
    project = await create_project(project_client)
    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides", headers=auth_headers(),
        json={"version": "initial", "task_examples": [{"content": "Review a claim."}],
              "documents": [{"label": "guide.docx", "media_type": media_type}]},
    )
    assert response.status_code == 201, response.text
    guide = response.json()
    upload = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/documents/{guide['documents'][0]['document_id']}/content",
        headers=auth_headers() | {"Content-Type": media_type}, content=content.getvalue(),
    )
    assert upload.status_code == 422, upload.text
    await _assert_no_upload_effects()
