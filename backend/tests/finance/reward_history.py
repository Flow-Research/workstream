"""Checksum-bound genuine v1 reward and task/import history."""

import gzip
import asyncio
import hashlib
import json
from pathlib import Path

CHECKSUMS = {
    "dual": "19bd1ff5e7d09c47c6201cbbafac43e9a9bbccf8104e11f1ba8d352ba83a5f15",
    "task_replay": "577cd3c0d12815c53ccf32363d48ef711c7a8b53d6ba45d8f3bc1cfc01e33b44",
}


def reward_history(name: str) -> dict:
    """Read a fixed archived input, never infer or synthesize historical terms."""
    path = Path(__file__).parents[1] / "fixtures" / f"finance_reward_v1_{name}.json.gz"
    encoded = path.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == CHECKSUMS[name], (
        "reward archive checksum mismatch"
    )
    body = json.loads(gzip.decompress(encoded))
    assert body["schema_version"] == "workstream.reward_history.v1"
    assert body["source_revision"] == "0068_issuer_profile_email"
    assert body["writer_commit"] == "70a60846b6bb122a835f1a1d6928edf326cbfdef"
    return body


async def restore_reward_predecessor(database_url: str, snapshot: dict) -> None:
    """Restore genuine archived facts against their exact predecessor schema."""
    from alembic import command
    from app.db import session as db_session
    from tests.conftest import _drop_test_database_schema
    from tests.historical_submission_fixtures import _restore_validated_snapshot_rows
    from tests.migration_fixtures import _config

    await db_session.dispose_engine()
    await _drop_test_database_schema(database_url)
    await asyncio.to_thread(command.upgrade, _config(), snapshot["source_revision"])
    await _restore_validated_snapshot_rows(
        database_url,
        snapshot,
        expected_revision=snapshot["source_revision"],
    )
