"""Real owner reads preserve the consumed revision and assignment boundary."""

from uuid import UUID

import pytest

from app.core.identifiers import new_record_id
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.tasks.api.evaluation_revision import TaskEvaluationRevisionRequest
from app.modules.tasks.api.submitted_bundle import SubmittedBundleUnavailable
from app.modules.tasks.evaluation_revision import TaskEvaluationRevisionReader
from app.modules.tasks.models import Submission
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import activate_successor_guide, revision_archive
from tests.tasks.submission_dispatch.test_replacement_creation import (
    _create,
    _creation_request,
    _creation_snapshot,
    _ready_replacement,
)
from tests.tasks.submission_dispatch.test_revision_exhaustion import (
    _apply,
    _other_eligible_actor,
    _submit_initial_after_reclaim,
)
from tests.tasks.test_public_submission_intake import _client
from tests.test_submission_predecessor_custody import _fixture_revision_context


async def revision_selector(h, submission_id):
    """Supply ART's consumed selector to TASK, as the later composition must do."""
    async with h.factory() as session:
        submission = await session.get(Submission, str(submission_id))
        admission = await session.get(
            SubmissionBundleAdmission, submission.submission_bundle_admission_id
        )
        return TaskEvaluationRevisionRequest(
            project_id=h.request.project_id,
            task_id=h.request.task_id,
            assignment_id=UUID(submission.task_assignment_id),
            submission_id=UUID(submission.id),
            submission_version=submission.version,
            admission_id=UUID(admission.id),
            preparation_id=admission.revision_preparation_id,
            preparation_sha256=admission.revision_preparation_sha256,
        )


async def _read(h, selector):
    async with h.factory() as session, session.begin():
        return await TaskEvaluationRevisionReader(session).read(selector)


@pytest.mark.parametrize("rebase", [False, True])
async def test_exact_consumed_preparation_and_source_are_read_without_mutation(
    tmp_path,
    isolated_database_env,
    rebase,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        first = await _read(h, await revision_selector(h, h.created.submission_id))
        assert first.kind == "initial" and first.predecessor is None and first.source is None
        if rebase:
            await activate_successor_guide(h)
        source_id = await _fixture_revision_context(h)
        prepared, admission_id = await _ready_replacement(h, revision_archive(h.data))
        created = await _create(h, _creation_request(h, prepared, admission_id))
        selector = await revision_selector(h, created.submission_id)
        before = await _creation_snapshot(h)
        context = await _read(h, selector)
        assert await _creation_snapshot(h) == before
        assert context.kind == "checker_remediation"
        assert context.predecessor == first.current
        assert context.current.submission_id == created.submission_id
        assert context.source.routing_manifest_id == source_id
        assert context.source.preparation_id == h.revision_preparation_id
        assert context.source.preparation_sha256 == h.revision_preparation_sha256
        assert context.source.revision_round == 1
        assert context.source.evaluation.result_id == h.result.result_id
        assert context.source.evaluation.result_digest == h.result.result_digest
        assert await _read(h, selector) == context
        for substitution in (
            {"project_id": new_record_id()},
            {"assignment_id": new_record_id()},
            {"submission_id": h.created.submission_id},
            {"preparation_id": new_record_id()},
            {"preparation_sha256": "sha256:" + "0" * 64},
            {"preparation_id": None, "preparation_sha256": None},
        ):
            with pytest.raises(SubmittedBundleUnavailable):
                await _read(h, selector.model_copy(update=substitution))


async def test_reclaimed_task_initial_never_includes_previous_contributors_work(
    tmp_path,
    isolated_database_env,
    monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env, max_revision_rounds=0) as h:
        old_contributor = h.actor_context.actor_profile_id
        old_submission = h.created.submission_id
        await _apply(h)
        h.actor_context = await _other_eligible_actor(h)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            created = await _submit_initial_after_reclaim(h, client)
        selector = await revision_selector(h, created.submission_id)
        context = await _read(h, selector)
        assert context.kind == "initial"
        assert context.current.submission_version == 2
        assert context.current.contributor_id != old_contributor
        assert context.current.submission_id != old_submission
        assert context.predecessor is None and context.source is None
        assert selector.preparation_id is None


async def test_task_revision_read_requires_caller_transaction(tmp_path, isolated_database_env):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        selector = await revision_selector(h, h.created.submission_id)
        async with h.factory() as session:
            with pytest.raises(SubmittedBundleUnavailable):
                await TaskEvaluationRevisionReader(session).read(selector)
