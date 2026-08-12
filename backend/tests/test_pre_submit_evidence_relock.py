"""Focused proof for post-byte pre-submit evidence relocking."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.artifacts import pre_submit_evidence
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict,
    PreSubmitEvidenceService,
)
from app.modules.tasks.api import TaskSubmissionContextUnavailable


@pytest.mark.asyncio
async def test_stale_task_relock_denies_before_evidence_or_pass_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-byte TASK drift cannot persist evidence or mint continuation."""
    transaction = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: transaction),
        in_nested_transaction=lambda: False,
    )
    task_contexts = SimpleNamespace(
        lock_submission_context=AsyncMock(
            side_effect=TaskSubmissionContextUnavailable(
                "task_submission_context_invalid"
            )
        )
    )
    project_contexts = SimpleNamespace(lock_locked_policy_context=AsyncMock())
    service = PreSubmitEvidenceService(
        session,  # type: ignore[arg-type]
        task_contexts=task_contexts,
        project_contexts=project_contexts,
    )
    service._repository.persist = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(pre_submit_evidence, "_validate_execution", lambda *_: None)
    custody = SimpleNamespace(
        prepared_generation_id="generation",
        archive_sha256="archive",
        archive_byte_count=1,
        semantic_manifest_sha256="manifest",
    )
    request = SimpleNamespace(
        plan=object(),
        execution=SimpleNamespace(custody=custody),
        prepared_generation_id="generation",
        archive_sha256="archive",
        archive_byte_count=1,
        semantic_manifest_sha256="manifest",
        task_id="task",
        assignment_id="assignment",
        actor_profile_id="actor",
        predecessor_submission_id=None,
    )

    with pytest.raises(
        PreSubmitEvidenceConflict,
        match="pre_submit_locked_context_changed",
    ):
        await service.persist(request)  # type: ignore[arg-type]

    task_contexts.lock_submission_context.assert_awaited_once()
    project_contexts.lock_locked_policy_context.assert_not_awaited()
    service._repository.persist.assert_not_awaited()  # type: ignore[union-attr]
    assert service._live_pass_bindings == set()
