"""Canonical manual draft submission-policy preparation parsing."""

from uuid import UUID
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.runtime import (
    ProjectSubmissionArtifactPolicyMutationResourceContext,
    PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION,
    PreparedAuthorizationHandleInvalid,
    authorization_resource_digest,
)


def parse_submission_policy_prepare(action_id, request_value, projection):
    """Preserve exact create/update/derive bindings; unified approval has its own resource."""
    submission_policy_context = submission_policy_resource_digest = None
    if not projection and action_id in {
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE,
    }:
        try:
            value = dict(request_value)
            for field in (
                "resource_id",
                "operation_id",
                "scope_project_id",
                "guide_id",
                "source_snapshot_id",
                "policy_id",
                "sufficiency_report_id",
            ):
                value[field] = UUID(str(value[field]))
            raw_successor_policy_id = value.get("successor_policy_id")
            if raw_successor_policy_id is not None:
                value["successor_policy_id"] = UUID(str(raw_successor_policy_id))
            raw_custody = value.get("setup_service_custody")
            if raw_custody is not None:
                custody = dict(raw_custody)
                for field in (
                    "setup_run_id",
                    "scope_project_id",
                    "guide_id",
                    "source_snapshot_id",
                    "task_id",
                    "correlation_id",
                ):
                    custody[field] = UUID(str(custody[field]))
                value["setup_service_custody"] = custody
            resource = ProjectSubmissionArtifactPolicyMutationResourceContext.model_validate(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationHandleInvalid(
                "invalid prepared authorization handle"
            ) from exc
        expected_target = PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION[action_id]
        if resource.target_kind != expected_target:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        submission_policy_context = resource.model_dump(mode="json")
        submission_policy_resource_digest = authorization_resource_digest(resource)
    return submission_policy_context, submission_policy_resource_digest
