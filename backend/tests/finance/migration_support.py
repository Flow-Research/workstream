"""Exact retained-reward cutover refusal shared by migration proof graphs."""

import ast
import asyncio
import json

from alembic import command
import pytest

from tests.finance.test_selected_reward_migration import _snapshot
from tests.migration_fixtures import _config, current_schema_revision


async def assert_reward_cutover_refusal(database_url):
    """Refuse incompatible0068 facts without changing any rows, schema or guards."""
    before = await _snapshot(database_url)
    rows = {table: [json.loads(value) for value in values] for table, values in before[0].items()}
    assert rows["alembic_version"] == [{"version_num": "0068_issuer_profile_email"}]
    assert len(rows["joint_lifecycle_release_control"]) == 1
    assert rows["joint_lifecycle_release_control"][0]["phase"] == "disabled"
    # Expected categories come from the retained facts, independently of the
    # migration implementation's own query/check map.
    candidates = {
        "published_policy_evidence": [row for row in rows["contribution_policy_versions"]
                                      if row["status"] != "draft"],
        "economic_definitions": rows["contribution_award_definitions"],
        "earned_awards": rows["compensation_awards"],
        "contribution_evidence": rows["contribution_records"],
        "command_evidence": rows["task_command_receipts"],
        "import_evidence": rows["task_import_batches"],
        "screened_work": [row for row in rows["workstream_tasks"]
                          if row["status"] != "draft" or row["locked_contribution_policy_version_id"] is not None],
    }
    expected = {name: {"sample_ids": sorted(row["id"] for row in values)[:20],
                       "truncated": len(values) > 20}
                for name, values in candidates.items() if values}
    assert expected, "this proof requires actual incompatible retained evidence"
    with pytest.raises(RuntimeError, match="reward transition requires explicit data resolution:") as failure:
        await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
    actual = ast.literal_eval(str(failure.value).split(": ", 1)[1])
    assert actual == expected
    assert await _snapshot(database_url) == before
