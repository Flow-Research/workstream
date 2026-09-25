"""Frozen, audience-specific locked-policy response contracts."""

from app.core.identifiers import new_record_id

import pytest
from pydantic import ValidationError

from app.modules.tasks.schemas import (
    AuditTaskLockedContext, ManagementTaskLockedContext,
    OperationalTaskLockedContext, PostSubmitPolicyBodySummary,
)
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
)

MODELS = (ManagementTaskLockedContext, OperationalTaskLockedContext, AuditTaskLockedContext)
REFERENCE_FIELDS = {
    "task_id", "project_id", "locked_guide_version", "locked_guide_source_snapshot_id",
    "locked_guide_source_snapshot_hash", "locked_effective_project_submission_artifact_policy_id",
    "locked_effective_project_submission_artifact_policy_hash", "locked_pre_submit_checker_policy_id",
    "locked_pre_submit_checker_bundle_hash", "locked_post_submit_checker_policy_id",
    "locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash",
    "locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
    "locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash",
    "locked_contribution_policy_version_id",
}
SUMMARY = "locked_post_submit_checker_policy_body_summary"
SUMMARY_FIELDS = {
    "schema_version", "default_checkers", "required_checkers", "warning_checkers",
    "execution_checkers", "blocking_severities",
}


def test_locked_context_contracts():
    values = {
        field: (new_record_id() if field.endswith("_id") else 1 if field.endswith("_generation")
                else "sha256:" + "1" * 64 if field.endswith("_hash") else "guide")
        for field in REFERENCE_FIELDS
    }
    summary = PostSubmitPolicyBodySummary(schema_version="1", default_checkers=(),
                                         required_checkers=("check_acceptance_criteria_present",),
                                         warning_checkers=(), execution_checkers=(), blocking_severities=("high",))
    for cls in MODELS:
        kwargs = {**values, **({SUMMARY: summary} if cls is ManagementTaskLockedContext else {})}
        result = cls(**kwargs)
        assert set(result.model_dump()) == REFERENCE_FIELDS | ({SUMMARY} if cls is ManagementTaskLockedContext else set())
        for field in REFERENCE_FIELDS:
            bad = " " if field.endswith("_version") else "bad" if field.endswith(("_id", "_hash")) else 0
            with pytest.raises(ValidationError):
                cls(**{**kwargs, field: bad})
        for extra in ({"source_ref": "private"}, {"base_amount": 99}, {"actor_id": new_record_id()}):
            with pytest.raises(ValidationError, match="extra_forbidden"):
                cls(**kwargs, **extra)
        with pytest.raises(ValidationError, match="frozen_instance"):
            result.task_id = new_record_id()
        if cls is not ManagementTaskLockedContext:
            with pytest.raises(ValidationError, match="extra_forbidden"):
                cls(**values, **{SUMMARY: summary})
    with pytest.raises(ValidationError, match="frozen_instance"):
        summary.required_checkers = ()
    with pytest.raises(ValidationError, match="tuple_type"):
        PostSubmitPolicyBodySummary(**{**summary.model_dump(), "required_checkers": ["mutable"]})
