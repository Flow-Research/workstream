"""Retained verifier input, restored before real upgrades and owner assertions."""
import asyncio
import base64
from contextlib import asynccontextmanager
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from alembic import command
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import session as db_session
from app.modules.artifacts.models import ArtifactStorageNamespace
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.authorization.runtime import HumanAuthorizationContext
from tests.conftest import _drop_test_database_schema
from tests.historical_submission_fixtures import _restore_validated_snapshot_rows
from tests.migration_fixtures import _config, current_schema_revision
from tests.retained_material_fixtures import MemoryStore
from tests.test_artifact_admission import _settings


@asynccontextmanager
async def retained_pending_verification(database_url, tmp_path, migration_lock):
    encoded = (Path(__file__).with_name('fixtures') / 'retained_pending_verification.json.gz').read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == '1305eaa9de3083d2ca4188f3cdba40a42fa912f211fc90c99ea36989d45e3e38'
    body = json.loads(gzip.decompress(encoded))
    assert body['schema_version'] == 'workstream.retained_pending_verification.v1'
    assert body['source_revision'] == 'e2b926288899bcd9b05e1a560ec19b6bca8cfcfc'
    snapshot = body['snapshot']
    assert snapshot['revision'] == '0065_claim_starts_work'
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(database_url)
        try:
            await asyncio.to_thread(command.upgrade, _config(), snapshot['revision'])
            seed = await _restore_validated_snapshot_rows(
                database_url, snapshot, expected_revision=snapshot['revision'],
            )
            await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
            engine = create_async_engine(database_url)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    row = await session.get(ArtifactStorageNamespace, 'primary')
                    assert row is not None
                    namespace = ArtifactStorageNamespaceSpec(
                        row.backend, row.adapter, row.provider_profile,
                        row.namespace_descriptor, row.namespace_fingerprint,
                    )
                store = MemoryStore(namespace)
                for ref, value in seed['objects'].items():
                    data = base64.b64decode(value, validate=True)
                    digest = hashlib.sha256(data).hexdigest()
                    assert ref == 'sha256/' + digest[:2] + '/' + digest[2:]
                    store.objects[ref] = data
                yield SimpleNamespace(
                    factory=factory, context=HumanAuthorizationContext.model_validate_json(json.dumps(seed['context'])),
                    task_id=UUID(seed['task_id']), assignment_id=UUID(seed['assignment_id']),
                    project_id=UUID(seed['project_id']), put_attempt_id=UUID(seed['put_attempt_id']),
                    settings=_settings(tmp_path, maximum_bytes=1024 * 1024),
                    namespace=namespace, store=store,
                )
            finally:
                await engine.dispose()
        finally:
            await db_session.dispose_engine()
            await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
