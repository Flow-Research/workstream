"""Drain captured multi-image POST custody; byte transport is a bounded test port."""
import asyncio
import base64
import gzip
import hashlib
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import post_submission_materialization
from app.adapters.checkers import evaluation_coordinator
from app.core.config import get_settings
from app.interfaces.artifacts import ArtifactObjectMissingError
from workstream_external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager, HARD_MAXIMUM_ARTIFACT_BYTES
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.checkers.api.evaluation_contract import PostSubmissionExecutionRequest, PostSubmissionExecutionResult
from tests.conftest import _drop_test_database_schema
from tests.historical_submission_fixtures import _restore_validated_snapshot_rows
from tests.migration_fixtures import _config
from tests.test_checker_materialization import _limits
from tests.trusted_intake_fixtures import LocalIntakeAdapter

ARCHIVE = Path(__file__).with_name("fixtures") / "multi_post_history.json.gz"
ARCHIVE_SHA256 = "acde3375a3e96603868480fff9ffbb4492fe62ef3a89f9348e2ac9caddaae552"
PREDECESSOR = "0068_issuer_profile_email"
SOURCE_COMMIT = "94334ccf4085c26c7bfaa054465fc05cfbdad1fc"


class CapturedArchiveStore:
    """Only exact captured references can be read; no provider qualification claim."""
    def __init__(self, namespace, seed):
        self.identity = ExternalServiceAdapterIdentity("artifact_store", namespace.adapter)
        prefix = seed["private_prefix"] + "/"
        objects = {}
        for item in seed["objects"]:
            assert item["key"].startswith(prefix)
            ref = item["key"][len(prefix):]
            assert ref and ref not in objects
            data = base64.b64decode(item["body"], validate=True)
            assert len(data) <= 1024 * 1024
            objects[ref] = data
        assert len(objects) == 2
        self.objects, self.opens = MappingProxyType(objects), []

    async def put(self, *_args, **_kwargs):
        raise AssertionError("captured historical store is read-only")

    def open_source(self, *_args, **_kwargs):
        raise AssertionError("historical material must use its exact retained replica reference")

    async def open(self, reference, byte_range=None):
        assert byte_range is None
        self.opens.append(reference)
        if reference not in self.objects:
            raise ArtifactObjectMissingError()
        data = self.objects[reference]
        for offset in range(0, len(data), 65536):
            yield data[offset:offset + 65536]


def snapshot_for(roles):
    encoded = ARCHIVE.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == ARCHIVE_SHA256
    body = json.loads(gzip.decompress(encoded))
    assert body["schema_version"] == "workstream.multi_post_history.v1"
    snapshot = body["snapshots"]["-".join(roles)]
    assert snapshot["revision"] == PREDECESSOR and snapshot["source_commit"] == SOURCE_COMMIT
    assert tuple(snapshot["seed"]["roles"]) == roles
    entries = snapshot["seed"]["request"]["policy"]["entries"]
    assert len(entries) == 2
    assert tuple(entries[0]["configuration"]["workstream_evaluation_context_roles"]) == roles
    assert entries[1]["configuration"] == {}
    contents = {row["id"]: row for row in snapshot["tables"]["artifact_contents"]}
    replicas = snapshot["tables"]["artifact_replicas"]
    for item in snapshot["seed"]["objects"]:
        prefix = snapshot["seed"]["private_prefix"] + "/"
        assert item["key"].startswith(prefix)
        ref = item["key"][len(prefix):]
        data = base64.b64decode(item["body"], validate=True)
        expected = [(contents[row["content_id"]]["sha256"], contents[row["content_id"]]["byte_count"])
                    for row in replicas if row["provider_object_ref"] == ref]
        assert expected and set(expected) == {("sha256:" + hashlib.sha256(data).hexdigest(), len(data))}
    return snapshot


@pytest.fixture
async def historical_revision_material(tmp_path, postgres_database_url, migration_lock, monkeypatch, request):
    snapshot = snapshot_for(request.node.callspec.params["roles"])
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    get_settings.cache_clear()
    with migration_lock():
        await _drop_test_database_schema(postgres_database_url)
        await asyncio.to_thread(command.upgrade, _config(), PREDECESSOR)
        seed = await _restore_validated_snapshot_rows(postgres_database_url, snapshot, expected_revision=PREDECESSOR)
        await asyncio.to_thread(command.upgrade, _config(), "head")
        engine = create_async_engine(postgres_database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        namespace = ArtifactStorageNamespaceSpec(**seed["namespace"])
        store = CapturedArchiveStore(namespace, seed)
        scratch = tmp_path / "historical-post-scratch"
        manager = ArtifactScratchManager(root=scratch, limits=_limits(
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=8, maximum_concurrency=4,
            total_deadline_seconds=60.0, reservation_ttl_seconds=120.0,
        ))
        preparation = ArtifactPreparationService(manager)
        captured_request = PostSubmissionExecutionRequest.model_validate_json(json.dumps(seed["request"]))
        try:
            service = post_submission_materialization(
                sessions=factory, store=store, namespace=namespace, preparation=preparation,
                intake=LocalIntakeAdapter(), archive_limits=SubmissionArchiveLimits(), artifact_deadline_ms=120_000,
            )
            async with factory() as session, session.begin():
                envelope = await evaluation_coordinator(session).read_reserved_evaluation(
                    project_id=captured_request.project_id, task_id=captured_request.task_id,
                    submission_id=captured_request.submission_id, request_id=captured_request.evaluation_request_id,
                )
            assert envelope.request == captured_request
            yield SimpleNamespace(
                factory=factory, namespace=namespace, store=store, scratch=scratch,
                preparation=preparation, service=service,
                request=envelope.request,
                first_result=PostSubmissionExecutionResult.model_validate_json(json.dumps(seed["first_result"])),
                first_submission=SimpleNamespace(submission_id=UUID(seed["first_submission_id"])),
                revision_preparation_id=UUID(seed["revision_preparation_id"]),
            )
        finally:
            manager.close()
            await engine.dispose()
            get_settings.cache_clear()
