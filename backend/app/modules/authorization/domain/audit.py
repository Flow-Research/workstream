"""Privacy-bounded audit classification shared by AUTH capabilities."""

from __future__ import annotations

CONTEXT_DIGEST_RESOURCE_TYPES = (
    "artifact_put_attempt",
    "artifact_verification_job",
    "artifact_pending_work",
    "guide_source_binding",
    "guide_source_read",
    "pre_submit_checker_input",
    "project_diagnostic",
    "project_policy_read",
    "project_active_guide_read",
    "project_guide_compilation_request",
    "project_guide_compilation_attempt",
    "project_guide_sufficiency_projection",
    "project_submission_artifact_policy_projection",
)
