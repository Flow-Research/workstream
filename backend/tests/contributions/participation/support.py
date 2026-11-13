"""Real source-neutral composition for hidden submitter participation tests."""

from app.adapters.compensation import compensation_award_participant
from app.modules.compensation.api import AwardContributionFacts, AwardDefinitionFacts, CompleteAwardSetRequest
from app.modules.contributions.api import SubmitterParticipationRequest
from app.modules.contributions.records.participant import SubmitterContributionParticipant
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence


def request_for(h, *, acceptance_disposition, **changes):
    values = {
        "acceptance_disposition": acceptance_disposition,
        "project_id": h.submitter_record.project_id,
        "task_id": h.submitter_record.task_id,
        "submission_id": h.submitter_record.submission_id,
        "final_acceptance_id": h.submitter_record.source_final_acceptance_id,
        "task_assignment_id": h.submitter_record.source_task_assignment_id,
        "contributor_id": h.submitter_record.contributor_id,
        "contribution_policy_version_id": (h.submitter_record.contribution_policy_version_id),
        "task_size": h.source["task_size"],
        "contribution_award_definition_id": h.source["contribution_award_definition_id"],
        "artifact_hash": h.submitter_record.artifact_hash,
        "correlation_id": h.route_operation_id,
        "expected_generation": 2,
        "source_authorization_decision_id": h.acceptance.source_authorization_decision_id,
        "source_routing_manifest_id": h.acceptance.source_routing_manifest_id,
    }
    values.update(changes)
    return SubmitterParticipationRequest(**values)


def participant(session):
    fence = PostgresJointLifecycleMutationFence(session)
    return SubmitterContributionParticipant(
        session,
        fence=fence,
        awards=compensation_award_participant(session, fence),
    )


def complete_award_request_for(h, request):
    """Exact current input from the fixture's stored accepted contribution/awards."""
    record = h.submitter_record
    return CompleteAwardSetRequest(
        disposition=request.acceptance_disposition,
        compensation_mode="compensated" if h.participation.awards else "unpaid",
        contribution=AwardContributionFacts(
            id=record.id, project_id=record.project_id, contributor_id=record.contributor_id,
            contribution_policy_version_id=record.contribution_policy_version_id,
            contribution_type="accepted_submission", task_id=record.task_id,
            submission_id=record.submission_id, final_acceptance_id=record.source_final_acceptance_id,
            task_size=request.task_size,
        ),
        definitions=tuple(AwardDefinitionFacts(
            id=award.award_definition_id, project_id=award.project_id,
            contribution_policy_version_id=award.contribution_policy_version_id,
            contribution_type="accepted_submission", instrument_type=award.instrument_type,
            unit_code=award.unit_code, quantity=award.quantity, adapter_binding_id=award.adapter_binding_id,
        ) for award in h.participation.awards),
        correlation_id=request.correlation_id, expected_generation=request.expected_generation,
        source_authorization_decision_id=request.source_authorization_decision_id,
        source_routing_manifest_id=request.source_routing_manifest_id,
    )
