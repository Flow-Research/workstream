"""Outcome observations and explicitly untrusted lifecycle-denial candidates."""

from sqlalchemy import text
from app.core.identifiers import new_record_id
from app.modules.reviews.api.acceptance import FinalAcceptanceRequest
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest


async def stored_effects(session, task_id) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                "SELECT task.status AS task_status, assignment.status AS assignment_status, "
                "(SELECT count(*) FROM public.final_acceptances) AS acceptances, "
                "(SELECT count(*) FROM public.contribution_records "
                " WHERE contribution_type='accepted_submission') AS contributions, "
                "(SELECT count(*) FROM public.contribution_records "
                " WHERE contribution_type='completed_review') AS reviewer_contributions, "
                "(SELECT count(*) FROM public.compensation_awards) AS awards "
                "FROM public.workstream_tasks task "
                "JOIN public.task_assignments assignment ON assignment.task_id=task.id "
                "WHERE task.id=:task_id"
            ),
            {"task_id": task_id},
        )
    ).mappings().one()
    return dict(row)


async def denial_only_request(h, generation: int) -> FinalAcceptanceRequest:
    """Untrusted candidate for lifecycle denial; never valid source authority.

    These allocated receipt/source IDs deliberately have no stored AUTH event or
    manifest. Tests using this value must stop at the lifecycle gate, before any
    source lookup or write. Successful acceptance uses apply_outcome instead.
    """
    from app.adapters.tasks import routing_source_preparer
    from app.modules.checkers.api.execution import EvaluationCompletion
    from app.modules.reviews.api.acceptance import FinalAcceptanceInput

    async with h.factory() as session, session.begin():
        prepared = await routing_source_preparer(session).prepare(
            h.envelope.claim.event_id,
            EvaluationCompletion.model_validate_json(h.envelope.payload_json),
        )
        source = prepared.source
        await session.rollback()
    acceptance_id = new_record_id()
    return FinalAcceptanceRequest(
        acceptance=FinalAcceptanceInput(
            id=acceptance_id,
            project_id=source.project_id,
            task_id=source.task_id,
            submission_id=source.submission_id,
            acceptance_source="task_post_submit_route",
            source_review_id=None,
            source_routing_manifest_id=source.id,
            accepted_submitter_id=source.contributor_id,
            recorded_by=new_record_id(),
            policy_context_ref=source.locked_policy.locked_review_policy_id,
            source_authorization_decision_id=new_record_id(),
        ),
        task_effects=TaskAcceptedEffectsRequest(
            project_id=source.project_id,
            task_id=source.task_id,
            assignment_id=source.assignment_id,
            submission_id=source.submission_id,
            submission_version=source.submission_version,
            contributor_id=source.contributor_id,
            contribution_policy_version_id=source.contribution_policy_version_id,
            content_id=source.content_id,
            content_sha256=source.content_sha256,
            final_acceptance_id=acceptance_id,
            expected_task_status="evaluation_pending",
        ),
        correlation_id=new_record_id(),
        expected_generation=generation,
    )
