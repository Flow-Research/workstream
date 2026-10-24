"""Retained revision findings keep exact source and complete bounded evidence."""

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.api.revision_feedback import (
    RevisionFeedback,
    RevisionFeedbackRequest,
)
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmitCurrentResultReference
from app.modules.checkers.revision_feedback import RevisionFeedbackReader
from tests.checkers.execution.completion_fixture import completed_evidence, evidence_snapshot


def feedback_selector(h):
    """Project the exact completion selectors rather than looking up latest results."""
    result = h.result
    return RevisionFeedbackRequest(
        project_id=h.request.project_id,
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        submission_id=h.request.submission_id,
        submission_version=h.request.submission_version,
        completion_event_id=h.run.completion_event_id,
        result=SelectedPostSubmitCurrentResultReference(
            request_id=result.request_id,
            request_digest=result.request_digest,
            attempt_id=result.attempt_id,
            evaluation_generation=result.evaluation_generation,
            result_id=result.result_id,
            result_digest=result.result_digest,
        ),
    )


@pytest.mark.parametrize(
    "findings",
    [
        None,
        (
            {
                "check_id": "coverage.files",
                "code": "coverage.unreadable",
                "level": "coverage_incomplete",
                "message": "Required material could not be evaluated.",
                "path": "src/vendor.bin",
                "line": None,
            },
        ),
    ],
)
async def test_retained_feedback_matches_exact_completed_members_without_writes(
    tmp_path,
    isolated_database_env,
    findings,
):
    async with completed_evidence(
        tmp_path,
        isolated_database_env,
        findings=findings,
        human_review_required=False,
    ) as h:
        selector = feedback_selector(h)
        async with h.factory() as session, session.begin():
            before = await evidence_snapshot(session)
            feedback = await RevisionFeedbackReader(session).read(selector)
            assert await evidence_snapshot(session) == before
        assert feedback.source == selector
        assert feedback.policy_sha256 == h.request.policy.policy_sha256
        assert len(feedback.members) == len(h.result.execution.external_members)
        for projected, retained, binding in zip(
            feedback.members,
            h.result.execution.external_members,
            h.request.policy.entries,
            strict=True,
        ):
            assert projected.findings == retained.result.findings
            assert projected.result_digest == retained.result.result_digest
            assert projected.configuration_sha256 == binding.configuration_sha256
            assert projected.registry_entry_id == binding.registry.registry_entry_id
        for substitution in (
            {"project_id": new_record_id()},
            {"assignment_id": new_record_id()},
            {"submission_id": new_record_id()},
            {"completion_event_id": new_record_id()},
            {"result": selector.result.model_copy(update={"result_digest": "sha256:" + "0" * 64})},
        ):
            async with h.factory() as session, session.begin():
                with pytest.raises(CheckerExecutionUnavailable):
                    await RevisionFeedbackReader(session).read(
                        selector.model_copy(update=substitution)
                    )
        # An excess result is unavailable, never a seemingly complete truncated list.
        member = feedback.members[0]
        expanded = tuple(
            member.model_copy(
                update={
                    "order": index,
                    "requirement_id": f"requirement-{index}",
                }
            )
            for index in range(1000)
        )
        with pytest.raises(ValidationError):
            RevisionFeedback(
                source=selector, policy_sha256=feedback.policy_sha256, members=expanded
            )


async def test_passing_completion_is_not_revision_feedback(tmp_path, isolated_database_env):
    async with completed_evidence(
        tmp_path, isolated_database_env, recommendation="allow_review"
    ) as h:
        async with h.factory() as session, session.begin():
            with pytest.raises(CheckerExecutionUnavailable):
                await RevisionFeedbackReader(session).read(feedback_selector(h))
