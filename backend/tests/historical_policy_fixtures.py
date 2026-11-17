"""Exact pre-cardinality TASK/PROJECT snapshots for isolated migration proofs."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from tests.historical_submission_fixtures import _restore_validated_snapshot_rows


ARCHIVE = Path(__file__).with_name("fixtures") / "policy_cardinality_history.json.gz"
ARCHIVE_SHA256 = "0b7cb10abc1c23864fac6c3be2b898caf297760192cc423e2f6f2c1e1862911c"
SOURCE_COMMIT = "fac8ea5110dfe3ac1d8fa90a5f0ff132c3811034"
PREDECESSOR = "0081_operation_read_authority"


async def restore_historical_policy(database_url: str, name: str) -> dict:
    """Restore synthetic captured rows with all guards reinstated before returning."""
    assert name in {"no_pre", "no_post"}
    encoded = ARCHIVE.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == ARCHIVE_SHA256
    body = json.loads(gzip.decompress(encoded))
    assert body["schema_version"] == "workstream.policy_cardinality_history.v1"
    snapshot = body["snapshots"][name]
    assert snapshot["source_commit"] == SOURCE_COMMIT
    assert snapshot["revision"] == PREDECESSOR
    [approval] = snapshot["tables"]["project_guide_proposal_approvals"]
    assert approval["request_json"] is not None
    plan = approval["effective_pre_submit_plan"]
    assert tuple(len(plan[phase]["entries"]) for phase in ("pre_submit", "post_submit")) == (
        (0, 1) if name == "no_pre" else (1, 0)
    )
    return await _restore_validated_snapshot_rows(
        database_url, snapshot, expected_revision=PREDECESSOR,
    )


@pytest.fixture
async def historical_policy_intake(postgres_database_url, migration_lock, monkeypatch, request):
    """Upgrade coherent captured custody before testing current intake refusal."""
    import asyncio
    from types import SimpleNamespace
    from uuid import UUID
    from alembic import command
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
    from app.modules.authorization.runtime import HumanAuthorizationContext
    from tests.conftest import _drop_test_database_schema
    from tests.migration_fixtures import _config

    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    get_settings.cache_clear()
    with migration_lock():
        await _drop_test_database_schema(postgres_database_url)
        await asyncio.to_thread(command.upgrade, _config(), PREDECESSOR)
        seed = await restore_historical_policy(postgres_database_url, request.param)
        await asyncio.to_thread(command.upgrade, _config(), "head")
        engine = create_async_engine(postgres_database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield SimpleNamespace(
                factory=factory,
                actor=HumanAuthorizationContext.model_validate_json(json.dumps(seed["actor"])),
                task=UUID(seed["task"]), assignment=UUID(seed["assignment"]), project=UUID(seed["project"]),
                namespace=ArtifactStorageNamespaceSpec(**seed["namespace"]),
            )
        finally:
            await engine.dispose()
            get_settings.cache_clear()
