"""AUTH commitment projection of the canonical TASK routing proposal."""

from uuid import UUID

from app.modules.authorization.api.acceptance_source import PostSubmitRoutingSourceCommitment
from app.modules.tasks.api.post_submit_routing import (
    TaskPostSubmitSourceProposal,
    task_post_submit_source_digest,
)


def routing_source_commitment(
    source: TaskPostSubmitSourceProposal,
    *,
    route_operation_id: UUID,
    route_request_digest: str,
) -> PostSubmitRoutingSourceCommitment:
    """Bind a distinct routing request without granting execution or acceptance."""
    digest = task_post_submit_source_digest(source)
    checked = TaskPostSubmitSourceProposal.model_validate(
        source.model_dump(mode="python", exclude={"created_at"})
    )
    if route_request_digest == checked.request_digest:
        raise ValueError("routing request digest must differ from checker request")
    return PostSubmitRoutingSourceCommitment(
        source="task_post_submit_route",
        routing_manifest_id=checked.id,
        project_id=checked.project_id,
        task_id=checked.task_id,
        assignment_id=checked.assignment_id,
        submission_id=checked.submission_id,
        submission_version=checked.submission_version,
        contributor_id=checked.contributor_id,
        contribution_policy_version_id=checked.contribution_policy_version_id,
        checker_run_id=checked.checker_run_id,
        evaluation_request_id=checked.evaluation_request_id,
        evaluation_generation=checked.evaluation_generation,
        result_id=checked.result_id,
        completion_event_id=checked.completion_event_id,
        human_review_required=checked.human_review_required,
        locked_review_policy_id=checked.locked_policy.locked_review_policy_id,
        locked_review_policy_generation=checked.locked_policy.locked_review_policy_generation,
        locked_review_policy_hash=checked.locked_policy.locked_review_policy_hash,
        content_id=checked.content_id,
        content_sha256=checked.content_sha256,
        semantic_manifest_sha256=checked.semantic_manifest_sha256,
        routing_source_digest=digest,
        route_operation_id=route_operation_id,
        route_request_digest=route_request_digest,
    )
