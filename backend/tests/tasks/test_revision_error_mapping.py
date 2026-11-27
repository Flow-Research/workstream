"""Exact revision custody races retain their public failure classification."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.artifacts.service import ArtifactStorageOrchestrator
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands, TaskRevisionRepairError


def _constraint(name: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, SimpleNamespace(constraint_name=name))


async def test_repair_commit_maps_named_deadline_race():
    command = AuthorizedTaskCommands.__new__(AuthorizedTaskCommands)
    command._repair_revision_context_root = AsyncMock(
        side_effect=_constraint("ck_revision_preparation_deadline_expired")
    )
    with pytest.raises(TaskRevisionRepairError) as caught:
        await command.repair_revision_context(None, None, None, idempotency_key=None)
    assert caught.value.code == "revision_deadline_expired"


async def test_art_deadline_race_reenters_terminal_conflict_path():
    service = ArtifactStorageOrchestrator.__new__(ArtifactStorageOrchestrator)
    service._complete_verification_transaction = AsyncMock(side_effect=[
        _constraint("ck_revision_admission_deadline_expired"), "conflict",
    ])
    claim = SimpleNamespace(id="job", execution_generation=2)
    assert await service._complete_verification(
        claim, None, None, "verified", None, None,
    ) == "conflict"
    assert service._complete_verification_transaction.await_count == 2
    assert service._complete_verification_transaction.await_args.kwargs["publication_conflict"] is True


async def test_art_other_integrity_failure_does_not_retry():
    service = ArtifactStorageOrchestrator.__new__(ArtifactStorageOrchestrator)
    service._complete_verification_transaction = AsyncMock(
        side_effect=_constraint("ck_unrelated"),
    )
    with pytest.raises(IntegrityError):
        await service._complete_verification(
            SimpleNamespace(id="job", execution_generation=2), None, None,
            "verified", None, None,
        )
    service._complete_verification_transaction.assert_awaited_once()
