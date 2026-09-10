"""Committed response recovery never repeats a command's product effect."""

from uuid import UUID

import pytest

from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations.commands import invoke, seed_replay
from projects.sufficiency_mutations.fixtures import case as case


@pytest.mark.parametrize("command", ["create", "ack"])
async def test_mutation_recovers_committed_response(case, command):
    record = await seed_replay(case, command)
    before = vars(case.report).copy()
    outcome = await invoke(case, command)
    assert outcome.replayed is True
    assert outcome.response.model_dump(mode="json") == record.response_json
    case.prepared.consume.assert_awaited_once()
    case.projects.add_guide_sufficiency_report.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert vars(case.report) == before


@pytest.mark.parametrize(
    "command,field",
    [
        *(
            (command, field)
            for command in ("create", "ack")
            for field in (
                "identity_link_id",
                "request_digest",
                "project_id",
                "guide_id",
            )
        ),
        ("create", "source_snapshot_id"),
        ("ack", "report_id"),
    ],
)
async def test_replay_rejects_changed_identity(case, command, field):
    record = await seed_replay(case, command)
    setattr(record, field, 2 if field == "setup_generation" else str(UUID(int=99)))
    with pytest.raises(module.GuideSufficiencyMutationConflict, match="idempotency_mismatch"):
        await invoke(case, command)
    case.prepared.prepare.assert_not_awaited()
    case.prepared.consume.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    case.projects.add_guide_sufficiency_report.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "ack"])
async def test_replay_rejects_pending_record(case, command):
    record = await seed_replay(case, command)
    record.status = "pending"
    record.response_json = None
    record.committed_at = None
    with pytest.raises(module.GuideSufficiencyMutationConflict, match="idempotency_pending"):
        await invoke(case, command)
    case.prepared.prepare.assert_not_awaited()
    case.prepared.consume.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "ack"])
async def test_replay_rejects_changed_resource_digest(case, command):
    record = await seed_replay(case, command)
    record.resource_context_digest = "sha256:" + "d" * 64
    before_report, before_setup = vars(case.report).copy(), vars(case.setup).copy()
    with pytest.raises(module.GuideSufficiencyMutationConflict, match="idempotency_mismatch"):
        await invoke(case, command)
    case.prepared.consume.assert_awaited_once()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    case.projects.add_guide_sufficiency_report.assert_not_awaited()
    assert vars(case.report) == before_report
    assert vars(case.setup) == before_setup
