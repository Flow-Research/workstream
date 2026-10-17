"""Exact revision custody races retain their public failure classification."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.adapters.tasks import TransactionalSubmissionCreationCommand
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from app.modules.tasks.api.submission_context import TaskSubmissionContextUnavailable
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands, TaskRevisionRepairError


def _constraint(name: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, SimpleNamespace(constraint_name=name))


@pytest.mark.parametrize(("name", "code"), [
    ("ck_revision_submission_deadline_expired", "revision_deadline_expired"),
    ("ck_revision_submission_context_changed", "revision_context_changed"),
])
async def test_submission_commit_maps_only_named_revision_races(monkeypatch, name, code):
    class Root:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            raise _constraint(name)

    session = SimpleNamespace(in_transaction=lambda: False, begin=Root)
    monkeypatch.setattr(
        "app.adapters.tasks.TaskSubmissionCreationService",
        lambda *_args, **_kwargs: SimpleNamespace(create=AsyncMock(return_value=object())),
    )
    command = TransactionalSubmissionCreationCommand(
        session, authorization=None, admissions=None, settings=None,
    )
    with pytest.raises(TaskSubmissionContextUnavailable) as caught:
        await command.create(None)
    assert caught.value.code == code


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
        claim, None, None, "verified", None, None, None,
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
            "verified", None, None, None,
        )
    service._complete_verification_transaction.assert_awaited_once()
