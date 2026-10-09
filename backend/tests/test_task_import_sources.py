"""Public declared JSON sources with real PostgreSQL, AUTH and MinIO custody."""

import asyncio
import hashlib
import json
import os
from uuid import UUID, uuid4
from datetime import UTC, datetime

from aiobotocore.session import AioSession
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.db import session as db_session
from app.main import create_app
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import ArtifactTaskImportSource, ArtifactPutAttempt, ArtifactAdmissionCharge
from app.modules.artifacts.models import ArtifactReplica
from app.adapters.artifacts.s3_compatible import S3CompatibleArtifactStore
from app.interfaces.artifacts import ArtifactStoreUnavailableError
from app.modules.authorization.models import AdminRoleGrant
from app.modules.authorization.task_import_sources import PreparedTaskImportSourceAuthorization
from app.modules.artifacts.api.task_import_source import TaskImportSourceAction
from app.modules.tasks.models import AuditEvent, WorkstreamTask
from tests.project_create_fixtures import grant_system_project_manager
from tests.test_artifact_internal_authorization import _service_principal
from tests.test_tasks import task_database_env as task_database_env, auth_headers, admit_and_grant_project_submitter
from tests.tasks.test_task_import_contract import document


@pytest.fixture
async def import_source_client(task_database_env, monkeypatch, tmp_path):
    """Use the runner's owned MinIO namespace and actual fixed-service authority."""
    endpoint = os.environ["WORKSTREAM_TEST_MINIO_ENDPOINT"]
    bucket = os.environ["WORKSTREAM_TEST_MINIO_BUCKET"]
    prefix = os.environ["WORKSTREAM_TEST_MINIO_PREFIX"]
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    values = {
        "WORKSTREAM_ARTIFACT_STORE_BACKEND": "s3_compatible", "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(scratch),
        "WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE": "minio", "WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL": endpoint,
        "WORKSTREAM_ARTIFACT_S3_REGION": "us-east-1", "WORKSTREAM_ARTIFACT_S3_BUCKET": bucket,
        "WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX": prefix, "WORKSTREAM_ARTIFACT_S3_ADDRESSING_STYLE": "path",
        "WORKSTREAM_ARTIFACT_S3_CREDENTIAL_MODE": "local_static", "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID": "workstream-minio",
        "WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY": "workstream-minio-secret-key",
    }
    for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
        values[f"WORKSTREAM_ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(64 * 1024 * 1024)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    s3 = AioSession()
    s3.set_credentials("workstream-minio", "workstream-minio-secret-key")
    async with s3.create_client("s3", endpoint_url=endpoint, region_name="us-east-1",
                                config=AioConfig(s3={"addressing_style": "path"})) as provider:
        try:
            await provider.create_bucket(Bucket=bucket)
        except ClientError as error:
            assert error.response["Error"]["Code"] in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://testserver") as client:
        admitted = await client.get("/api/v1/actors/me", headers=auth_headers())
        assert admitted.status_code == 200, admitted.text
        async with db_session.get_session_factory()() as session, session.begin():
            await grant_system_project_manager(session, issuer="flow-test", subject="project-manager-subject")
            for identity in (ServiceIdentity.ARTIFACT_PUT_RESOLVER, ServiceIdentity.ARTIFACT_VERIFIER, ServiceIdentity.ARTIFACT_SCHEDULER):
                profile, link = _service_principal(identity)
                session.add(profile)
                await session.flush()
                session.add(link)
        yield client


async def _project(client):
    response = await client.post("/api/v1/projects", headers=auth_headers(),
                                 json={"name": "Import source", "slug": "source-" + uuid4().hex})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _declare(client, project, raw, headers=None):
    response = await client.post(f"/api/v1/projects/{project}/task-import-sources", headers=headers or auth_headers(),
                                 json={"sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "byte_count": len(raw)})
    assert response.status_code == 201, response.text
    return response.json()


def _path(project, source):
    return f"/api/v1/projects/{project}/task-import-sources/{source['source_id']}"


async def _effects():
    async with db_session.get_session_factory()() as session:
        return tuple([await session.scalar(select(func.count()).select_from(owner)) for owner in (
            ArtifactTaskImportSource, ArtifactPutAttempt, ArtifactAdmissionCharge, WorkstreamTask,
        )])


async def test_200_row_public_source_round_trip_and_exact_replay(import_source_client):
    client = import_source_client
    project = await _project(client)
    raw = (json.dumps(document(200), ensure_ascii=False, indent=2) + "\n").encode()
    headers = auth_headers()
    declared = await _declare(client, project, raw, headers)
    assert declared["status"] == "declared"
    replay = await _declare(client, project, raw, headers)
    assert replay == declared
    path = _path(project, declared)
    upload_headers = auth_headers() | {"Content-Type": "application/json"}
    uploaded = await client.put(path + "/content", headers=upload_headers, content=raw)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "verified"
    again = await client.put(path + "/content", headers=upload_headers, content=raw)
    assert again.status_code == 200 and again.json() == uploaded.json(), again.text
    downloaded = await client.get(path + "/content", headers=auth_headers())
    assert downloaded.status_code == 200 and downloaded.content == raw, downloaded.text
    assert downloaded.headers["content-length"] == str(len(raw))
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert "sha256:" + hashlib.sha256(downloaded.content).hexdigest() == declared["sha256"]
    assert (await _effects()) == (1, 1, 3, 0)
    async with db_session.get_session_factory()() as session:
        source = await session.get(ArtifactTaskImportSource, declared["source_id"])
        audit = await session.get(AuditEvent, source.authorization_decision_id)
        assert audit.action_id == TaskImportSourceAction.DECLARE.value
        assert audit.permission_id == "project.task.manage" and audit.actor_id == source.actor_profile_id


@pytest.mark.parametrize("kind", ["invalid_row", "duplicate_id", "501_rows", "duplicate_member", "mismatched_bytes"])
async def test_invalid_uploads_leave_only_the_declared_parent(import_source_client, kind):
    client = import_source_client
    project = await _project(client)
    value = document(501 if kind == "501_rows" else 3)
    if kind == "invalid_row":
        value["tasks"][1]["title"] = " "
    elif kind == "duplicate_id":
        value["tasks"][1]["external_task_id"] = value["tasks"][0]["external_task_id"]
    raw = json.dumps(value).encode()
    if kind == "duplicate_member":
        raw = raw.replace(b'"schema_version":', b'"schema_version":"ambiguous","schema_version":', 1)
    source = await _declare(client, project, raw)
    body = raw + b" " if kind == "mismatched_bytes" else raw
    result = await client.put(_path(project, source) + "/content", headers=auth_headers() | {"Content-Type": "application/json"}, content=body)
    assert result.status_code in {413, 422}, result.text
    if kind in {"invalid_row", "duplicate_id"}:
        assert result.status_code == 422
        assert "tasks" in result.text and "1" in result.text
    assert (await _effects()) == (1, 0, 0, 0)
    status = await client.get(_path(project, source), headers=auth_headers())
    assert status.status_code == 200 and status.json()["status"] == "declared"


async def test_changed_declaration_conflicts_without_partial_effects(import_source_client):
    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document()).encode()
    headers = auth_headers()
    source = await _declare(client, project, raw, headers)
    changed = await client.post(f"/api/v1/projects/{project}/task-import-sources", headers=headers,
                                json={"sha256": "sha256:" + "a" * 64, "byte_count": len(raw)})
    assert changed.status_code == 409, changed.text
    assert (await _effects()) == (1, 0, 0, 0)
    status = await client.get(_path(project, source), headers=auth_headers())
    assert status.status_code == 200 and status.json()["sha256"] == source["sha256"]


async def test_revoked_authority_cannot_replay_or_read_a_verified_source(import_source_client):
    client = import_source_client
    project = await _project(client)
    raw, headers = json.dumps(document()).encode(), auth_headers()
    source = await _declare(client, project, raw, headers)
    uploaded = await client.put(_path(project, source) + "/content", headers=headers | {"Content-Type": "application/json"}, content=raw)
    assert uploaded.status_code == 200 and uploaded.json()["status"] == "verified", uploaded.text
    before = await _effects()
    async with db_session.get_session_factory()() as session, session.begin():
        grant = (await session.scalars(select(AdminRoleGrant).where(
            AdminRoleGrant.role == "project_manager", AdminRoleGrant.status == "active"))).one()
        grant.status = "revoked"
        grant.version += 1
        grant.revoked_by_actor_profile_id = grant.target_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "Source replay must require current authority"
        grant.revoked_at = datetime.now(UTC)
    replay = await client.post(f"/api/v1/projects/{project}/task-import-sources", headers=headers,
                               json={"sha256": source["sha256"], "byte_count": len(raw)})
    assert replay.status_code == 403, replay.text
    upload_replay = await client.put(_path(project, source) + "/content", headers=headers | {"Content-Type": "application/json"}, content=raw)
    download = await client.get(_path(project, source) + "/content", headers=auth_headers())
    status = await client.get(_path(project, source), headers=auth_headers())
    foreign = await client.get(f"/api/v1/projects/{uuid4()}/task-import-sources/{source['source_id']}", headers=auth_headers())
    assert status.status_code == foreign.status_code == upload_replay.status_code == download.status_code == 404
    assert (await _effects()) == before == (1, 1, 3, 0)


async def test_submitter_cannot_declare_or_upload_a_source(import_source_client, monkeypatch):
    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document()).encode()
    source = await _declare(client, project, raw)
    await admit_and_grant_project_submitter(client, monkeypatch, project, "source-denied-submitter")
    declared = await client.post(f"/api/v1/projects/{project}/task-import-sources", headers=auth_headers(),
                                 json={"sha256": source["sha256"], "byte_count": len(raw)})
    assert declared.status_code == 403, declared.text
    uploaded = await client.put(_path(project, source) + "/content", headers=auth_headers() | {"Content-Type": "application/json"}, content=raw)
    assert uploaded.status_code == 404, uploaded.text
    assert (await _effects()) == (1, 0, 0, 0)


async def test_concurrent_declarations_return_one_original_source(import_source_client):
    client = import_source_client
    project = await _project(client)
    raw, headers = json.dumps(document()).encode(), auth_headers()
    results = await asyncio.gather(*[_declare(client, project, raw, headers) for _ in range(4)])
    assert all(result == results[0] for result in results)
    assert (await _effects()) == (1, 0, 0, 0)


async def test_concurrent_uploads_share_one_attempt_and_complete_verification(import_source_client):
    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document(200)).encode()
    source = await _declare(client, project, raw)
    results = await asyncio.gather(*[client.put(_path(project, source) + "/content",
        headers=auth_headers() | {"Content-Type": "application/json"}, content=raw) for _ in range(2)])
    assert all(result.status_code == 200 for result in results), [result.text for result in results]
    assert all(result.json()["source_id"] == source["source_id"] for result in results)
    status = await client.get(_path(project, source), headers=auth_headers())
    assert status.json()["status"] == "verified", status.text
    assert (await _effects()) == (1, 1, 3, 0)


async def test_unknown_acknowledgement_recovers_through_existing_scanner_and_workers(import_source_client, monkeypatch):
    from app.adapters.artifacts.internal_workers import (
        scan_artifact_pending_work, run_artifact_internal_operation, shutdown_artifact_internal_runtime,
    )

    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document()).encode()
    source = await _declare(client, project, raw)
    original = S3CompatibleArtifactStore.put
    writes = []

    async def lose_acknowledgement(self, prepared):
        result = await original(self, prepared)
        writes.append(result.provider_object_ref)
        raise ArtifactStoreUnavailableError("injected uncertainty after real MinIO put")

    monkeypatch.setattr(S3CompatibleArtifactStore, "put", lose_acknowledgement)
    result = await client.put(_path(project, source) + "/content", headers=auth_headers() | {"Content-Type": "application/json"}, content=raw)
    assert result.status_code == 200 and result.json()["status"] == "acknowledgement_unknown", result.text
    assert len(writes) == 1
    async with db_session.get_session_factory()() as session, session.begin():
        await session.execute(text("update artifact_put_attempts set next_run_at=clock_timestamp()-interval '1 second' "
                                   "where task_import_source_id=:id"), {"id": UUID(source["source_id"])})
    puts, jobs = [], []

    async def publish_put(value):
        puts.append(value)

    async def publish_job(value):
        jobs.append(value)

    try:
        assert await scan_artifact_pending_work(publish_put, publish_job) == 1
        assert len(puts) == 1 and jobs == []
        assert await run_artifact_internal_operation("put", UUID(puts[0])) == "observed_confirmed"
        puts.clear()
        assert await scan_artifact_pending_work(publish_put, publish_job) == 1
        assert puts == [] and len(jobs) == 1
        assert await run_artifact_internal_operation("verification", UUID(jobs[0])) == "verified"
    finally:
        await shutdown_artifact_internal_runtime()
    downloaded = await client.get(_path(project, source) + "/content", headers=auth_headers())
    assert downloaded.status_code == 200 and downloaded.content == raw, downloaded.text
    assert len(writes) == 1 and (await _effects()) == (1, 1, 3, 0)


async def test_changed_provider_bytes_are_rejected_before_download_headers(import_source_client):
    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document()).encode()
    source = await _declare(client, project, raw)
    upload = await client.put(_path(project, source) + "/content", headers=auth_headers() | {"Content-Type": "application/json"}, content=raw)
    assert upload.status_code == 200 and upload.json()["status"] == "verified", upload.text
    async with db_session.get_session_factory()() as session:
        replica = await session.scalar(select(ArtifactReplica).join(ArtifactPutAttempt, ArtifactPutAttempt.replica_id == ArtifactReplica.id)
                                       .where(ArtifactPutAttempt.task_import_source_id == source["source_id"]))
        provider_ref = replica.provider_object_ref
        before = await session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action_id == TaskImportSourceAction.READ.value))
    settings = get_settings()
    s3 = AioSession()
    s3.set_credentials("workstream-minio", "workstream-minio-secret-key")
    async with s3.create_client("s3", endpoint_url=settings.artifact_s3_endpoint_url, region_name="us-east-1",
                                config=AioConfig(s3={"addressing_style": "path"})) as provider:
        await provider.put_object(Bucket=settings.artifact_s3_bucket, Key=settings.artifact_s3_private_prefix + "/" + provider_ref,
                                  Body=b"x" * len(raw), ContentType="application/json")
    read = await client.get(_path(project, source) + "/content", headers=auth_headers())
    assert read.status_code == 503 and read.headers["content-type"] == "application/json", read.text
    assert read.content != raw and "attachment" not in read.headers.get("content-disposition", "")
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action_id == TaskImportSourceAction.READ.value)) == before


async def test_failure_after_real_admission_authority_rolls_back_attempts_and_allow(import_source_client, monkeypatch):
    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document()).encode()
    source = await _declare(client, project, raw)
    original = PreparedTaskImportSourceAuthorization.authorize
    calls = 0

    async def fail_after_real_consume(self, action, facts):
        nonlocal calls
        decision = await original(self, action, facts)
        if action is TaskImportSourceAction.UPLOAD:
            calls += 1
            if calls == 2:
                raise RuntimeError("injected after real final authority")
        return decision

    monkeypatch.setattr(PreparedTaskImportSourceAuthorization, "authorize", fail_after_real_consume)
    failed = await client.put(_path(project, source) + "/content", headers=auth_headers() | {"Content-Type": "application/json"}, content=raw)
    assert failed.status_code == 500, failed.text
    assert calls == 2
    assert (await _effects()) == (1, 0, 0, 0)
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action_id == TaskImportSourceAction.UPLOAD.value)) == 0


async def test_postgres_rejects_source_mutation_and_foreign_attempt_custody(import_source_client):
    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document()).encode()
    source = await _declare(client, project, raw)
    uploaded = await client.put(_path(project, source) + "/content", headers=auth_headers() | {"Content-Type": "application/json"}, content=raw)
    assert uploaded.status_code == 200, uploaded.text
    foreign_project = await _project(client)
    foreign = await _declare(client, foreign_project, raw)
    forged_id = new_record_id()
    forged = json.dumps({"id": str(forged_id), "idempotency_key": str(uuid4()),
                         "operation_identity": canonical_json_hash({"request_type": "task_import_source", "source_id": str(forged_id)})})
    for statement, params in (
        ("update artifact_task_import_sources set byte_count=byte_count+1 where id=:id", {"id": UUID(source["source_id"])}),
        ("delete from artifact_task_import_sources where id=:id", {"id": UUID(source["source_id"])}),
        ("update artifact_put_attempts set task_import_source_id=:foreign where task_import_source_id=:id",
         {"id": UUID(source["source_id"]), "foreign": UUID(foreign["source_id"])}),
        ("insert into artifact_task_import_sources select "
         "(jsonb_populate_record(null::artifact_task_import_sources,to_jsonb(s)||cast(:forged as jsonb))).* "
         "from artifact_task_import_sources s where id=:id", {"id": UUID(source["source_id"]), "forged": forged}),
    ):
        async with db_session.get_session_factory()() as session:
            with pytest.raises(DBAPIError):
                async with session.begin():
                    await session.execute(text(statement), params)
    assert (await _effects()) == (2, 1, 3, 0)
