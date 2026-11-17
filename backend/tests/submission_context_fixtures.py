"""Complete locked TASK facts for focused lifecycle tests without storage."""

from app.core.identifiers import new_record_id
from app.modules.tasks.api import TaskSubmissionContextFacts
from app.modules.tasks.api.transition_audit import TaskPolicyLineage


def submission_context_facts(**fields) -> TaskSubmissionContextFacts:
    """Keep lifecycle fixtures explicit while supplying unrelated complete policy stamps."""
    refs = fields["locked_project_context"]
    fields.setdefault("task_size", "small")
    fields.setdefault("contribution_award_definition_id", None)
    fields.setdefault("acceptance_criteria", "Meet the project requirements")
    fields.setdefault("locked_policy", TaskPolicyLineage(
        locked_guide_version=refs.guide_version,
        locked_guide_source_snapshot_id=refs.source_snapshot_id,
        locked_guide_source_snapshot_hash=refs.source_snapshot_hash,
        locked_effective_project_submission_artifact_policy_id=refs.effective_policy_id,
        locked_effective_project_submission_artifact_policy_hash=refs.effective_policy_hash,
        locked_pre_submit_checker_policy_id=refs.pre_submit_policy_id,
        locked_pre_submit_checker_bundle_hash=refs.pre_submit_policy_bundle_hash,
        locked_post_submit_checker_policy_id=new_record_id(),
        locked_post_submit_checker_policy_version=refs.guide_version,
        locked_post_submit_checker_policy_hash="sha256:" + "4" * 64,
        locked_review_policy_id=new_record_id(), locked_review_policy_generation=1,
        locked_review_policy_hash="sha256:" + "5" * 64,
        locked_revision_policy_id=new_record_id(), locked_revision_policy_generation=1,
        locked_revision_policy_hash="sha256:" + "6" * 64,
        locked_contribution_policy_version_id=refs.locked_contribution_policy_version_id,
    ))
    return TaskSubmissionContextFacts(**fields)
