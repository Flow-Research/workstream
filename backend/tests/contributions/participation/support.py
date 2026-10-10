"""Real source-neutral composition for hidden submitter participation tests."""

from app.modules.compensation.awards.participant import CompensationAwardParticipant
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
        "artifact_hash": h.submitter_record.artifact_hash,
        "correlation_id": h.route_operation_id,
        "expected_generation": 2,
    }
    values.update(changes)
    return SubmitterParticipationRequest(**values)


def participant(session):
    return SubmitterContributionParticipant(
        session,
        fence=PostgresJointLifecycleMutationFence(session),
        awards=CompensationAwardParticipant(session),
    )
