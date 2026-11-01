from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx2 as httpx
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from workstream_mcp.config import Settings
from workstream_mcp.errors import SafeFailure
from workstream_mcp.limits import GUIDE_DOCUMENT_MEDIA_TYPES, TASK_IMPORT_SOURCE_MAX_BYTES
from workstream_mcp.schemas import (
    access_read_output_validator,
    actor_lifecycle_output_validator,
    admin_grant_output_validator,
    authorization_context_output_validator,
    checker_artifact_output_validator,
    contribution_policy_output_validator,
    guide_lifecycle_output_validator,
    guide_output_validator,
    policy_output_validator,
    profile_output_validator,
    profile_update_output_validator,
    project_grant_output_validator,
    project_output_validator,
    task_execution_output_validator,
    task_operation_output_validator,
    workspace_read_output_validator,
)

_SAFE_VALUE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    re.ASCII,
)
_CORRELATION_HEADERS = ("x-request-id", "x-correlation-id")
_PUBLIC_ERROR_CODES = frozenset(
    {
        "actor_deactivated",
        "actor_deactivated_terminal",
        "actor_already_suspended",
        "actor_not_suspended",
        "actor_not_found",
        "actor_suspended",
        "actor_resource_not_found",
        "identity_link_revoked",
        "identity_link_already_revoked",
        "identity_link_not_revoked",
        "identity_verification_unavailable",
        "admin_role_grant_exists",
        "grant_not_found",
        "idempotency_mismatch",
        "internal_error",
        "invalid_request",
        "invalid_token",
        "missing_token",
        "permission_not_granted",
        "pre_submission_checker_failed",
        "project_authorization_resource_not_found",
        "project_slug_conflict",
        "idempotency_pending",
        "invalid_cursor",
        "project_role_grant_already_revoked",
        "project_role_grant_exists",
        "project_role_grant_replay_state_changed",
        "policy_precondition_failed",
        "policy_precondition_invalid",
        "authorization_handle_invalid",
        "contribution_export_invalid",
        "contribution_policy_conflict",
        "contribution_policy_not_found",
        "contribution_policy_storage_unavailable",
        "resource_guard_denied",
        "resource_not_found",
        "rate_limit_exceeded",
        "scope_not_authorized",
        "self_grant_forbidden",
        "self_role_revoke_forbidden",
        "last_access_administrator",
        "invalid_role_scope",
        "service_unavailable",
        "submission_preparation_headers_invalid",
        "submission_unavailable",
        "submission_packet_invalid",
        "submission_infrastructure_unavailable",
        "unsupported_subject_kind",
        "validation_error",
    }
)

ACCESS_READ_PATHS = {
    "permissions_list": "/api/v1/authorization/permissions",
    "admin_roles_list": "/api/v1/authorization/admin-role-definitions",
    "admin_grants_list": "/api/v1/admin-role-grants",
    "actor_admin_grants_list": "/api/v1/actors/{actor_profile_id}/admin-role-grants",
    "actor_get": "/api/v1/actors/{actor_profile_id}",
    "actor_identity_link_get": "/api/v1/actors/{actor_profile_id}/identity-links",
}
ACTOR_LIFECYCLE_MUTATIONS = {
    "actor_suspend": (
        "/api/v1/actors/{resource_id}/suspend",
        "actor_profile_id",
        "actor_profile",
    ),
    "actor_reactivate": (
        "/api/v1/actors/{resource_id}/reactivate",
        "actor_profile_id",
        "actor_profile",
    ),
    "actor_deactivate": (
        "/api/v1/actors/{resource_id}/deactivate",
        "actor_profile_id",
        "actor_profile",
    ),
    "identity_link_revoke": (
        "/api/v1/actor-identity-links/{resource_id}/revoke",
        "identity_link_id",
        "actor_identity_link",
    ),
    "identity_link_reactivate": (
        "/api/v1/actor-identity-links/{resource_id}/reactivate",
        "identity_link_id",
        "actor_identity_link",
    ),
}
WORKSPACE_READ_PATHS = {
    "actor_projects_list": "/api/v1/actors/me/projects",
    "actor_assignments_list": "/api/v1/actors/me/assignments",
    "actor_submissions_list": "/api/v1/actors/me/submissions",
    "actor_summary_get": "/api/v1/actors/me/summary",
    "contributions_list": "/api/v1/actors/me/contributions",
    "project_contributions_export": "/api/v1/projects/{project_id}/contributions/export",
    "project_submissions_list": "/api/v1/projects/{project_id}/submissions",
    "project_assignments_list": "/api/v1/projects/{project_id}/assignments",
    "project_summary_get": "/api/v1/projects/{project_id}/summary",
    "project_task_import_batches_list": "/api/v1/projects/{project_id}/task-import-batches",
    "project_preparations_list": "/api/v1/projects/{project_id}/submission-bundle-preparations",
    "active_guide_get": "/api/v1/projects/{project_id}/active-guide",
    "ready_tasks_list": "/api/v1/projects/{project_id}/tasks/ready",
}
GUIDE_LIFECYCLE_OPERATIONS = {
    "project_guides_list": ("GET", "/api/v1/projects/{project_id}/guides", 200),
    "project_guide_get": ("GET", "/api/v1/projects/{project_id}/guides/{guide_id}", 200),
    "guide_activate": ("POST", "/api/v1/projects/{project_id}/guides/{guide_id}/activate", 200),
    "guide_activation_readiness_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/activation-readiness",
        200,
    ),
    "guide_proposal_correct": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/corrections",
        201,
    ),
    "guide_correction_dispatch": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/corrections/{correction_operation_id}/dispatch",
        202,
    ),
    "guide_post_policy_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/post-submission-policies/{policy_id}",
        200,
    ),
    "guide_post_policy_approve": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/post-submission-policies/{policy_id}/approval",
        200,
    ),
    "guide_post_policy_correct": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/post-submission-policies/{policy_id}/corrections",
        201,
    ),
    "guide_pre_submission_approve": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/pre-submission-approval",
        200,
    ),
    "guide_proposal_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/proposal",
        200,
    ),
    "guide_document_upload": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/documents/{document_id}/content",
        202,
    ),
    "guide_document_content_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/documents/{document_id}/content",
        200,
    ),
    "guide_effective_submission_artifact_policy_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy",
        200,
    ),
    "guide_pre_submit_checker_policy_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy",
        200,
    ),
    "guide_setup_latest_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest",
        200,
    ),
    "guide_submission_artifact_policies_list": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        200,
    ),
    "guide_submission_artifact_policy_create": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        201,
    ),
    "guide_submission_artifact_policy_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}",
        200,
    ),
    "guide_submission_artifact_policy_update": (
        "PATCH",
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}",
        200,
    ),
    "guide_sufficiency_reports_list": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        200,
    ),
    "guide_sufficiency_report_create": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        201,
    ),
    "guide_sufficiency_report_get": (
        "GET",
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}",
        200,
    ),
    "guide_sufficiency_warnings_acknowledge": (
        "POST",
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}/acknowledge-warnings",
        200,
    ),
}
CHECKER_ARTIFACT_OPERATIONS = {
    "submission_checker_runs_list": (
        "GET",
        "/api/v1/submissions/{submission_id}/checker-runs",
        200,
    ),
    "submission_checker_runs_get": (
        "GET",
        "/api/v1/submissions/{submission_id}/checker-runs/{checker_run_id}",
        200,
    ),
    "project_checker_runs_list": (
        "GET",
        "/api/v1/projects/{project_id}/submissions/{submission_id}/checker-runs",
        200,
    ),
    "project_checker_runs_get": (
        "GET",
        "/api/v1/projects/{project_id}/submissions/{submission_id}/checker-runs/{checker_run_id}",
        200,
    ),
    "checker_retry_sources_list": (
        "GET",
        "/api/v1/operations/projects/{project_id}/checker-retry-sources",
        200,
    ),
    "checker_runs_retry": (
        "POST",
        "/api/v1/operations/projects/{project_id}/checker-runs/{source_run_id}/retry",
        201,
    ),
    "post_submit_deliveries_list": (
        "GET",
        "/api/v1/operations/projects/{project_id}/post-submit-deliveries",
        200,
    ),
    "post_submit_deliveries_reconcile": (
        "POST",
        "/api/v1/operations/projects/{project_id}/post-submit-deliveries/{event_id}/reconcile",
        201,
    ),
    "checker_registry_read": (
        "GET",
        "/api/v1/operations/external-checker-registry/{registry_entry_id}",
        200,
    ),
    "checker_registry_register": (
        "POST",
        "/api/v1/operations/external-checker-registry",
        201,
    ),
    "artifact_readiness_get": ("GET", "/api/v1/operator/artifacts/readiness", 200),
    "artifact_bindings_list": ("GET", "/api/v1/operator/artifacts/bindings", 200),
    "artifact_replicas_list": (
        "GET",
        "/api/v1/operator/artifacts/contents/{content_id}/replicas",
        200,
    ),
    "artifact_receipts_list": (
        "GET",
        "/api/v1/operator/artifacts/replicas/{replica_id}/receipts",
        200,
    ),
    "artifact_verification_job_get": (
        "GET",
        "/api/v1/operator/artifacts/verification-jobs/{verification_job_id}",
        200,
    ),
    "artifact_verification_job_retry": (
        "POST",
        "/api/v1/operator/artifacts/verification-jobs/{verification_job_id}/retry",
        202,
    ),
    "artifact_recovery_attempt_get": (
        "GET",
        "/api/v1/operator/artifacts/recovery-attempts/{recovery_attempt_id}",
        200,
    ),
    "artifact_admission_usage_get": (
        "GET",
        "/api/v1/operator/artifacts/admission-usage",
        200,
    ),
    "artifact_audit_events_list": (
        "GET",
        "/api/v1/operator/artifacts/audit-events",
        200,
    ),
}
_CHECKER_ARTIFACT_MUTATIONS = frozenset(
    {
        "checker_runs_retry",
        "post_submit_deliveries_reconcile",
        "checker_registry_register",
        "artifact_verification_job_retry",
    }
)

TASK_EXECUTION_OPERATIONS = {
    "preparation_create": (
        "POST",
        "/api/v1/tasks/{task_id}/submission-bundle-preparations",
        202,
    ),
    "preparations_list": (
        "GET",
        "/api/v1/tasks/{task_id}/submission-bundle-preparations",
        200,
    ),
    "preparation_get": (
        "GET",
        "/api/v1/tasks/{task_id}/submission-bundle-preparations/{preparation_id}",
        200,
    ),
    "task_get": ("GET", "/api/v1/tasks/{task_id}", 200),
    "task_submission_requirements_get": (
        "GET",
        "/api/v1/tasks/{task_id}/submission-requirements",
        200,
    ),
    "task_screen": ("POST", "/api/v1/tasks/{task_id}/screen", 200),
    "task_release": ("POST", "/api/v1/tasks/{task_id}/release", 200),
    "task_claim": ("POST", "/api/v1/tasks/{task_id}/claim", 200),
    "task_start": ("POST", "/api/v1/tasks/{task_id}/start", 200),
    "task_work_context_get": ("GET", "/api/v1/tasks/{task_id}/work-context", 200),
    "task_guide_document_content_get": (
        "GET",
        "/api/v1/tasks/{task_id}/guide/documents/{document_id}/content",
        200,
    ),
    "submission_create": ("POST", "/api/v1/tasks/{task_id}/submissions", 201),
    "task_submissions_list": ("GET", "/api/v1/tasks/{task_id}/submissions", 200),
    "submission_get": ("GET", "/api/v1/submissions/{submission_id}", 200),
    "management_task_submissions_list": (
        "GET",
        "/api/v1/projects/{project_id}/tasks/{task_id}/submissions",
        200,
    ),
    "management_submission_get": (
        "GET",
        "/api/v1/projects/{project_id}/submissions/{submission_id}",
        200,
    ),
    "management_task_work_context_get": (
        "GET",
        "/api/v1/projects/{project_id}/tasks/{task_id}/work-context",
        200,
    ),
    "management_task_submission_requirements_get": (
        "GET",
        "/api/v1/projects/{project_id}/tasks/{task_id}/submission-requirements",
        200,
    ),
}
_TASK_EXECUTION_MUTATIONS = frozenset(
    {
        "preparation_create",
        "task_screen",
        "task_release",
        "task_claim",
        "task_start",
        "submission_create",
    }
)

TASK_OPERATIONS = {
    "projects_list": ("GET", "/api/v1/projects", 200),
    "service_actor_create": ("POST", "/api/v1/service-actors", 201),
    "task_import_batch_create": (
        "POST",
        "/api/v1/projects/{project_id}/task-import-batches",
        201,
    ),
    "management_tasks_list": ("GET", "/api/v1/projects/{project_id}/tasks", 200),
    "management_task_create": ("POST", "/api/v1/projects/{project_id}/tasks", 201),
    "operational_tasks_list": (
        "GET",
        "/api/v1/operations/projects/{project_id}/tasks",
        200,
    ),
    "task_import_batch_screen": (
        "POST",
        "/api/v1/projects/{project_id}/task-import-batches/{batch_id}/screen",
        200,
    ),
    "task_import_batch_release": (
        "POST",
        "/api/v1/projects/{project_id}/task-import-batches/{batch_id}/release",
        200,
    ),
    "task_import_batch_get": (
        "GET",
        "/api/v1/projects/{project_id}/task-import-batches/{batch_id}",
        200,
    ),
    "management_task_get": (
        "GET",
        "/api/v1/projects/{project_id}/tasks/{task_id}",
        200,
    ),
    "management_task_locked_context_get": (
        "GET",
        "/api/v1/projects/{project_id}/tasks/{task_id}/locked-context",
        200,
    ),
    "operational_task_locked_context_get": (
        "GET",
        "/api/v1/operations/projects/{project_id}/tasks/{task_id}/locked-context",
        200,
    ),
    "audit_task_locked_context_get": (
        "GET",
        "/api/v1/audit/projects/{project_id}/tasks/{task_id}/locked-context",
        200,
    ),
    "task_revision_context_repair": (
        "POST",
        "/api/v1/projects/{project_id}/tasks/{task_id}/revision-context/repair",
        200,
    ),
    "audit_task_evidence_get": (
        "GET",
        "/api/v1/audit/projects/{project_id}/tasks/{task_id}/evidence",
        200,
    ),
    "operational_task_start_override": (
        "POST",
        "/api/v1/operations/tasks/{task_id}/start",
        200,
    ),
    "project_model_profile_provision": (
        "POST",
        "/api/v1/operations/projects/{project_id}/model-profiles",
        201,
    ),
    "project_model_budget_configure": (
        "POST",
        "/api/v1/operations/projects/{project_id}/model-budget-configurations",
        201,
    ),
    "project_model_usage_effect_get": (
        "GET",
        "/api/v1/operations/projects/{project_id}/model-usage/effects/{effect_id}",
        200,
    ),
    "project_model_recovery_child_create": (
        "POST",
        "/api/v1/operations/projects/{project_id}/model-call-attempts/"
        "{parent_attempt_id}/recovery-children",
        201,
    ),
    "task_import_source_declare": (
        "POST",
        "/api/v1/projects/{project_id}/task-import-sources",
        201,
    ),
    "task_import_source_content_upload": (
        "PUT",
        "/api/v1/projects/{project_id}/task-import-sources/{source_id}/content",
        200,
    ),
    "task_import_source_content_get": (
        "GET",
        "/api/v1/projects/{project_id}/task-import-sources/{source_id}/content",
        200,
    ),
    "task_import_source_get": (
        "GET",
        "/api/v1/projects/{project_id}/task-import-sources/{source_id}",
        200,
    ),
}
_TASK_OPERATION_MUTATIONS = frozenset(
    name for name, (method, _, _) in TASK_OPERATIONS.items() if method != "GET"
)


@dataclass(frozen=True, slots=True)
class GatewayResult:
    data: dict[str, Any] | None = None
    failure: SafeFailure | None = None
    correlation_id: str | None = None


class ResponseTooLarge(Exception):
    """The upstream response exceeded the configured byte bound."""


class WorkstreamGateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client
        self._slots = asyncio.Semaphore(settings.max_in_flight)

    async def profile_get(self, bearer: str, correlation_id: str | None = None) -> GatewayResult:
        return await self._request(
            "GET",
            "/api/v1/actors/me",
            bearer,
            profile_output_validator(),
            correlation_id,
        )

    async def profile_update(
        self,
        bearer: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        return await self._request(
            "PATCH",
            "/api/v1/actors/me",
            bearer,
            profile_update_output_validator(),
            correlation_id,
            json_body=payload,
            mutation=True,
        )

    async def authorization_context_get(
        self,
        bearer: str,
        project_id: str,
        correlation_id: str | None = None,
    ) -> GatewayResult:
        return await self._request(
            "GET",
            "/api/v1/actors/me/authorization-context",
            bearer,
            authorization_context_output_validator(),
            correlation_id,
            params={"project_id": project_id},
        )

    async def access_read(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch a registered read; callers cannot supply an HTTP route."""
        path = ACCESS_READ_PATHS[name]
        if "{actor_profile_id}" in path:
            path = path.format(actor_profile_id=quote(arguments["actor_profile_id"], safe=""))
        params = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None and key != "actor_profile_id"
        }
        return await self._request(
            "GET",
            path,
            bearer,
            access_read_output_validator(name),
            correlation_id,
            params=params or None,
        )

    async def admin_grant_mutation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed administrative grant mutation."""
        if name == "admin_grants_issue":
            path = "/api/v1/admin-role-grants"
            expected_status = 201
            expected_version = 1
        else:
            path = "/api/v1/admin-role-grants/{grant_id}/revoke".format(
                grant_id=quote(arguments["grant_id"], safe="")
            )
            expected_status = 200
            expected_version = 2
        return await self._request(
            "POST",
            path,
            bearer,
            admin_grant_output_validator(name),
            correlation_id,
            json_body=arguments["body"],
            idempotency_key=arguments["idempotency_key"],
            expected_status=expected_status,
            expected_payload={"http_status": expected_status, "version": expected_version},
            expected_resource_id=(arguments["grant_id"] if name == "admin_grants_revoke" else None),
            mutation=True,
        )

    async def actor_lifecycle_mutation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed actor-profile or identity-link lifecycle mutation."""
        path, resource_key, resource_type = ACTOR_LIFECYCLE_MUTATIONS[name]
        resource_id = arguments[resource_key]
        return await self._request(
            "POST",
            path.format(resource_id=quote(resource_id, safe="")),
            bearer,
            actor_lifecycle_output_validator(name),
            correlation_id,
            json_body=arguments["body"],
            idempotency_key=arguments["idempotency_key"],
            expected_status=200,
            expected_payload={
                "resource_type": resource_type,
                "http_status": 200,
                "version": None,
            },
            expected_resource_id=resource_id,
            mutation=True,
        )

    async def project_create(
        self,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Create one project shell through the fixed public API route."""
        return await self._request(
            "POST",
            "/api/v1/projects",
            bearer,
            project_output_validator("projects_create"),
            correlation_id,
            json_body=arguments["body"],
            idempotency_key=arguments["idempotency_key"],
            expected_status=201,
            mutation=True,
        )

    async def project_get(
        self,
        bearer: str,
        project_id: str,
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Read one project and bind the response to the requested UUID."""
        outcome = await self._request(
            "GET",
            f"/api/v1/projects/{quote(project_id, safe='')}",
            bearer,
            project_output_validator("projects_get"),
            correlation_id,
        )
        if outcome.failure is not None:
            return outcome
        try:
            matches = UUID((outcome.data or {})["id"]) == UUID(project_id)
        except (KeyError, TypeError, ValueError):
            matches = False
        if not matches:
            return GatewayResult(
                failure=SafeFailure(
                    "invalid_api_response",
                    status=502,
                    correlation_id=correlation_id,
                )
            )
        return outcome

    async def project_grant_read(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed project-participation read and bind its selectors."""
        project_id = arguments["project_id"]
        base = f"/api/v1/projects/{quote(project_id, safe='')}"
        if name == "contributor_candidates_list":
            path = f"{base}/contributor-candidates"
        elif name == "project_grants_list":
            path = f"{base}/role-grants"
        else:
            path = f"{base}/role-grants/{quote(arguments['grant_id'], safe='')}"
        params = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None and key not in {"project_id", "grant_id"}
        }
        outcome = await self._request(
            "GET",
            path,
            bearer,
            project_grant_output_validator(name),
            correlation_id,
            params=params or None,
        )
        if outcome.failure is not None:
            return outcome
        data = outcome.data or {}
        if name == "contributor_candidates_list":
            items = data.get("items")
            if not self._unique_uuid_field(items, "actor_profile_id"):
                return self._invalid_read_response(correlation_id)
            return outcome
        grants = data.get("items") if name == "project_grants_list" else [data]
        if not isinstance(grants, list) or any(
            not isinstance(grant, dict)
            or not self._same_uuid(grant.get("project_id"), project_id)
            or not self._valid_grant_observation(grant)
            or (
                name == "project_grants_get"
                and not self._same_uuid(grant.get("id"), arguments["grant_id"])
            )
            for grant in grants
        ) or not self._unique_uuid_field(grants, "id"):
            return self._invalid_read_response(correlation_id)
        return outcome

    async def project_grant_mutation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed project-role mutation; Workstream owns replay state."""
        project_id = arguments["project_id"]
        base = f"/api/v1/projects/{quote(project_id, safe='')}/role-grants"
        issue = name == "project_grants_issue"
        path = base if issue else f"{base}/{quote(arguments['grant_id'], safe='')}/revoke"
        expected_status = 201 if issue else 200
        outcome = await self._request(
            "POST",
            path,
            bearer,
            project_grant_output_validator(name),
            correlation_id,
            json_body=arguments["body"],
            idempotency_key=arguments["idempotency_key"],
            expected_status=expected_status,
            mutation=True,
        )
        if outcome.failure is not None:
            return outcome
        data = outcome.data or {}
        expected = {
            "status": "active" if issue else "revoked",
            "version": 1 if issue else 2,
        }
        matches = self._same_uuid(data.get("project_id"), project_id) and all(
            data.get(key) == value for key, value in expected.items()
        )
        if issue:
            matches = (
                matches
                and self._same_uuid(
                    data.get("actor_profile_id"),
                    arguments["body"]["target_actor_profile_id"],
                )
                and data.get("role") == arguments["body"]["role"]
            )
        else:
            matches = matches and self._same_uuid(data.get("id"), arguments["grant_id"])
        if not matches:
            return GatewayResult(
                failure=SafeFailure(
                    "workstream_execution_uncertain",
                    status=502,
                    correlation_id=correlation_id,
                )
            )
        return outcome

    async def guide_mutation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed guide metadata mutation and bind its selectors."""
        project_id = arguments["project_id"]
        base = f"/api/v1/projects/{quote(project_id, safe='')}/guides"
        create = name == "guides_create"
        path = (
            base
            if create
            else f"{base}/{quote(arguments['guide_id'], safe='')}"
        )
        outcome = await self._request(
            "POST" if create else "PATCH",
            path,
            bearer,
            guide_output_validator(name),
            correlation_id,
            json_body=arguments["body"],
            idempotency_key=arguments["idempotency_key"],
            expected_status=201 if create else 200,
            mutation=True,
        )
        if outcome.failure is not None:
            return outcome
        data = outcome.data or {}
        matches = self._same_uuid(data.get("project_id"), project_id)
        if create:
            body = arguments["body"]
            requested_examples = [
                {
                    "content": item["content"],
                    "title": item.get("title"),
                    "labels": item.get("labels", []),
                }
                for item in body["task_examples"]
            ]
            returned_documents = data.get("documents")
            requested_documents = body["documents"]
            matches = (
                matches
                and data.get("version") == body["version"]
                and data.get("status") == "draft"
                and data.get("change_summary") == body.get("change_summary")
                and data.get("task_examples") == requested_examples
                and isinstance(returned_documents, list)
                and len(returned_documents) == len(requested_documents)
                and self._unique_uuid_field(returned_documents, "document_id")
                and all(
                    isinstance(returned, dict)
                    and returned.get("label") == " ".join(requested["label"].split())
                    and returned.get("media_type") == requested.get("media_type")
                    and returned.get("order") == index
                    for index, (returned, requested) in enumerate(
                        zip(returned_documents, requested_documents, strict=True)
                    )
                )
                and isinstance(data.get("setup"), dict)
                and data["setup"].get("status") == "awaiting_documents"
            )
        else:
            matches = matches and self._same_uuid(data.get("id"), arguments["guide_id"])
            if "change_summary" in arguments["body"]:
                matches = (
                    matches
                    and data.get("change_summary") == arguments["body"]["change_summary"]
                )
        if not matches:
            return GatewayResult(
                failure=SafeFailure(
                    "workstream_execution_uncertain",
                    status=502,
                    correlation_id=correlation_id,
                )
            )
        return outcome

    async def policy_mutation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed policy mutation and bind its returned lineage."""
        project_id = arguments["project_id"]
        guide_id = arguments["guide_id"]
        policy_kind = "review" if name == "review_policy_put" else "revision"
        path = (
            f"/api/v1/projects/{quote(project_id, safe='')}/guides/"
            f"{quote(guide_id, safe='')}/{policy_kind}-policy"
        )
        outcome = await self._request(
            "PUT",
            path,
            bearer,
            policy_output_validator(name),
            correlation_id,
            json_body=arguments["body"],
            idempotency_key=arguments["idempotency_key"],
            if_match=arguments["if_match"],
            expected_status=200,
            mutation=True,
        )
        if outcome.failure is not None:
            return outcome
        data = outcome.data or {}
        lineage_matches = self._policy_lineage_matches(data, arguments["if_match"])
        matches = (
            self._same_uuid(data.get("project_id"), project_id)
            and lineage_matches
            and data.get("semantics_status") == "complete"
            and isinstance(data.get("policy_generation"), int)
            and data["policy_generation"] >= 1
            and isinstance(data.get("policy_hash"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", data["policy_hash"]) is not None
        )
        body = arguments["body"]
        matches = matches and all(data.get(key) == value for key, value in body.items())
        if not matches:
            return GatewayResult(
                failure=SafeFailure(
                    "workstream_execution_uncertain",
                    status=502,
                    correlation_id=correlation_id,
                )
            )
        return outcome

    async def workspace_read(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed contributor/project read with JSON-only exports."""
        path = WORKSPACE_READ_PATHS[name]
        project_id_value = arguments.get("project_id")
        project_id = project_id_value if isinstance(project_id_value, str) else None
        if "{project_id}" in path:
            if project_id is None:  # guarded by the tool schema
                return self._invalid_read_response(correlation_id)
            path = path.format(project_id=quote(project_id, safe=""))
        params = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None and key != "project_id"
        }
        if name in {"contributions_list", "project_contributions_export"}:
            params["format"] = "json"
            if name == "contributions_list" and project_id is not None:
                params["project_id"] = project_id
        elif name.startswith("actor_") and project_id is not None:
            params["project_id"] = project_id
        outcome = await self._request(
            "GET",
            path,
            bearer,
            workspace_read_output_validator(name),
            correlation_id,
            params=params or None,
        )
        if outcome.failure is not None or project_id is None:
            return outcome
        data = outcome.data or {}
        if not self._workspace_project_matches(name, data, project_id):
            return self._invalid_read_response(correlation_id)
        return outcome

    @classmethod
    def _workspace_project_matches(
        cls, name: str, data: dict[str, Any], project_id: str
    ) -> bool:
        candidates: list[dict[str, Any]] = [data]
        items = data.get("items")
        if isinstance(items, list):
            candidates.extend(item for item in items if isinstance(item, dict))
        if name == "active_guide_get":
            candidates.extend(item for item in data.values() if isinstance(item, dict))
        return all(
            "project_id" not in item
            or cls._same_uuid(item["project_id"], project_id)
            for item in candidates
        )

    async def contribution_policy_read(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Read one fixed contribution-policy projection and bind selectors."""
        project_id = arguments["project_id"]
        base = f"/api/v1/projects/{quote(project_id, safe='')}/contribution-policies"
        if name == "contribution_policies_list":
            path = base
        elif name == "contribution_policy_current_get":
            path = f"{base}/current"
        else:
            path = f"{base}/{quote(arguments['policy_id'], safe='')}"
        params = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None and key not in {"project_id", "policy_id"}
        }
        outcome = await self._request(
            "GET",
            path,
            bearer,
            contribution_policy_output_validator(name),
            correlation_id,
            params=params or None,
        )
        if outcome.failure is not None:
            return outcome
        data = outcome.data or {}
        items = data.get("items") if name == "contribution_policies_list" else [data]
        if not isinstance(items, list) or any(
            not isinstance(item, dict)
            or not self._same_uuid(item.get("project_id"), project_id)
            or (
                "policy_id" in arguments
                and not self._same_uuid(
                    item.get("contribution_policy_id"), arguments["policy_id"]
                )
            )
            or (
                "version_id" in arguments
                and not self._same_uuid(
                    item.get("contribution_policy_version_id"), arguments["version_id"]
                )
            )
            for item in items
        ):
            return self._invalid_read_response(correlation_id)
        if name == "contribution_policies_list" and not self._unique_uuid_field(
            items, "contribution_policy_version_id"
        ):
            return self._invalid_read_response(correlation_id)
        if name == "contribution_policy_current_get":
            published = data.get("current_published_version_id")
            draft = data.get("open_draft_version_id")
            if (published is None and draft is None) or (
                published is not None
                and draft is not None
                and self._same_uuid(published, str(draft))
            ):
                return self._invalid_read_response(correlation_id)
        return outcome

    async def contribution_policy_mutation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Mutate one contribution policy and bind its immutable receipt."""
        project_id = arguments["project_id"]
        base = f"/api/v1/projects/{quote(project_id, safe='')}/contribution-policies"
        if name == "contribution_policy_create":
            method, path, expected_status = "POST", f"{base}/drafts", 201
        else:
            policy_id = arguments["policy_id"]
            version_id = arguments["version_id"]
            path = (
                f"{base}/{quote(policy_id, safe='')}/versions/"
                f"{quote(version_id, safe='')}"
            )
            method, expected_status = "PUT", 200
            if name == "contribution_policy_publish":
                method, path = "POST", f"{path}/publication"
            elif name == "contribution_policy_retire":
                method, path = "POST", f"{path}/retirement"
        outcome = await self._request(
            method,
            path,
            bearer,
            contribution_policy_output_validator(name),
            correlation_id,
            json_body=arguments["body"],
            idempotency_key=arguments["idempotency_key"],
            expected_status=expected_status,
            mutation=True,
        )
        if outcome.failure is not None:
            return outcome
        data = outcome.data or {}
        matches = (
            self._same_uuid(data.get("operation_id"), arguments["idempotency_key"])
            and self._same_uuid(data.get("project_id"), project_id)
        )
        if name != "contribution_policy_create":
            matches = (
                matches
                and self._same_uuid(data.get("contribution_policy_id"), arguments["policy_id"])
                and self._same_uuid(
                    data.get("contribution_policy_version_id"), arguments["version_id"]
                )
            )
        matches = matches and self._contribution_policy_transition_matches(name, data)
        if not matches:
            return GatewayResult(
                failure=SafeFailure(
                    "workstream_execution_uncertain",
                    status=502,
                    correlation_id=correlation_id,
                )
            )
        return outcome

    @classmethod
    def _contribution_policy_transition_matches(
        cls, name: str, data: dict[str, Any]
    ) -> bool:
        version_number = data.get("version_number")
        digest = data.get("request_digest")
        prior_id = data.get("prior_current_version_id")
        prior_number = data.get("prior_current_version_number")
        if (
            not isinstance(version_number, int)
            or isinstance(version_number, bool)
            or version_number < 1
            or not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or (prior_id is None) != (prior_number is None)
            or (
                prior_id is not None
                and (
                    not cls._same_uuid(prior_id, str(prior_id))
                    or not isinstance(prior_number, int)
                    or isinstance(prior_number, bool)
                    or prior_number < 1
                )
            )
        ):
            return False
        from_policy = data.get("from_policy_status")
        from_version = data.get("from_version_status")
        to_policy = data.get("to_policy_status")
        to_version = data.get("to_version_status")
        event = data.get("event_type")
        if name == "contribution_policy_create":
            return event == "draft_created" and from_version is None and to_version == "draft" and (
                (from_policy is None and to_policy == "draft" and prior_id is None)
                or (from_policy == "active" and to_policy == "active" and prior_id is not None)
            )
        consistent_prior = (from_policy == "draft" and prior_id is None) or (
            from_policy == "active" and prior_id is not None
        )
        if name == "contribution_policy_update":
            return (
                event == "draft_updated"
                and consistent_prior
                and from_version == "draft"
                and to_version == "draft"
                and to_policy == from_policy
            )
        if name == "contribution_policy_publish":
            return (
                event == "published"
                and consistent_prior
                and from_version == "draft"
                and to_version == "published"
                and to_policy == "active"
            )
        return (
            event == "retired"
            and from_policy == "active"
            and to_policy == "retired"
            and from_version == "published"
            and to_version == "retired"
            and prior_id is not None
            and cls._same_uuid(prior_id, str(data.get("contribution_policy_version_id")))
            and prior_number == version_number
        )

    async def guide_lifecycle(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
        *,
        upload: bytes | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed guide route and bind returned selectors."""
        method, path_template, expected_status = GUIDE_LIFECYCLE_OPERATIONS[name]
        selectors = set(re.findall(r"{([a-z_]+)}", path_template))
        path = path_template
        for selector in selectors:
            value = arguments.get(selector)
            if not isinstance(value, str):  # guarded by the tool schema
                return self._invalid_read_response(correlation_id)
            path = path.replace(f"{{{selector}}}", quote(value, safe=""))
        if name == "guide_document_content_get":
            return await self._request_binary(
                path,
                bearer,
                correlation_id,
            )
        query = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None
            and key not in selectors
            and key
            not in {
                "body",
                "content_base64",
                "media_type",
                "idempotency_key",
            }
        }
        mutation = method != "GET"
        outcome = await self._request(
            method,
            path,
            bearer,
            guide_lifecycle_output_validator(name),
            correlation_id,
            json_body=arguments.get("body"),
            params=query or None,
            idempotency_key=arguments.get("idempotency_key"),
            expected_status=expected_status,
            mutation=mutation,
            raw_body=upload,
            content_type=arguments.get("media_type"),
            array_envelope=name
            in {
                "guide_submission_artifact_policies_list",
                "guide_sufficiency_reports_list",
            },
            operation_timeout_seconds=(
                self._settings.document_timeout_seconds
                if name == "guide_document_upload"
                else None
            ),
        )
        if outcome.failure is not None:
            return outcome
        data = outcome.data or {}
        if name == "guide_document_upload":
            digest = f"sha256:{hashlib.sha256(upload or b'').hexdigest()}"
            matches = (
                upload is not None
                and self._same_uuid(data.get("document_id"), arguments["document_id"])
                and data.get("sha256") == digest
                and data.get("byte_count") == len(upload)
                and data.get("status") in {"document_stored", "object_confirmed"}
            )
        else:
            matches = self._guide_lifecycle_response_matches(name, data, arguments)
        if matches:
            return outcome
        return GatewayResult(
            failure=SafeFailure(
                "workstream_execution_uncertain" if mutation else "invalid_api_response",
                status=502,
                correlation_id=outcome.correlation_id or correlation_id,
            )
        )

    async def _request_binary(
        self,
        path: str,
        bearer: str,
        correlation_id: str | None,
    ) -> GatewayResult:
        request_id = correlation_id or str(uuid4())
        try:
            async with asyncio.timeout(self._settings.document_timeout_seconds):
                async with self._slots:
                    async with self._client.stream(
                        "GET",
                        path,
                        headers={
                            "Authorization": bearer,
                            "Accept": ", ".join(GUIDE_DOCUMENT_MEDIA_TYPES),
                            "Accept-Encoding": "identity",
                            "X-Request-ID": request_id,
                        },
                        timeout=self._settings.document_timeout_seconds,
                    ) as response:
                        body = await self._bounded_body(
                            response, max_bytes=self._settings.max_document_bytes
                        )
                        response_id = self._correlation_id(response, request_id)
                        if response.status_code != 200:
                            return GatewayResult(
                                failure=self._api_failure(
                                    response.status_code,
                                    body,
                                    response_id,
                                )
                            )
                        media_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        if media_type not in GUIDE_DOCUMENT_MEDIA_TYPES or not body:
                            return self._invalid_read_response(response_id)
                        return GatewayResult(
                            data={
                                "media_type": media_type,
                                "content_base64": base64.b64encode(body).decode("ascii"),
                                "byte_count": len(body),
                                "sha256": f"sha256:{hashlib.sha256(body).hexdigest()}",
                            },
                            correlation_id=response_id,
                        )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return GatewayResult(
                failure=SafeFailure("workstream_timeout", status=504, retryable=True)
            )
        except ResponseTooLarge:
            return GatewayResult(
                failure=SafeFailure("workstream_response_too_large", status=502)
            )
        except httpx.HTTPError:
            return GatewayResult(
                failure=SafeFailure("workstream_unavailable", status=502, retryable=True)
            )
        except Exception:  # pragma: no cover
            return GatewayResult(failure=SafeFailure("adapter_internal_error", status=500))

    @classmethod
    def _guide_lifecycle_response_matches(
        cls,
        name: str,
        data: dict[str, Any],
        arguments: dict[str, Any],
    ) -> bool:
        """Bind only authoritative response fields for one fixed guide route."""

        def matches(
            record: object, field: str, argument: str | None = None
        ) -> bool:
            argument = argument or field
            return (
                isinstance(record, dict)
                and argument in arguments
                and cls._same_uuid(record.get(field), arguments[argument])
            )

        if name == "project_guides_list":
            return True
        if name == "project_guide_get":
            guide = data.get("guide")
            return matches(guide, "project_id") and matches(guide, "guide_id")
        if name == "guide_activate":
            command = data.get("command")
            target = command.get("target") if isinstance(command, dict) else None
            proposal = target.get("proposal") if isinstance(target, dict) else None
            return (
                matches(proposal, "project_id")
                and matches(proposal, "guide_id")
            )
        if name in {
            "guide_activation_readiness_get",
            "guide_effective_submission_artifact_policy_get",
            "guide_pre_submit_checker_policy_get",
            "guide_setup_latest_get",
        }:
            return matches(data, "project_id") and matches(data, "guide_id")
        if name in {"guide_proposal_correct", "guide_pre_submission_approve"}:
            return True
        if name == "guide_correction_dispatch":
            return matches(data, "correction_operation_id")
        if name == "guide_proposal_get":
            target = data.get("target")
            return (
                matches(target, "project_id")
                and matches(target, "guide_id")
                and matches(target, "compilation_id")
            )
        if name in {
            "guide_post_policy_get",
            "guide_post_policy_approve",
            "guide_post_policy_correct",
        }:
            target = data.get("target")
            proposal = target.get("proposal") if isinstance(target, dict) else None
            return (
                matches(target, "policy_id")
                and matches(proposal, "project_id")
                and matches(proposal, "guide_id")
                and matches(proposal, "compilation_id")
            )
        if name in {
            "guide_submission_artifact_policies_list",
            "guide_submission_artifact_policy_create",
            "guide_submission_artifact_policy_get",
            "guide_submission_artifact_policy_update",
        }:
            records = data.get("items") if name.endswith("policies_list") else [data]
            if not isinstance(records, list):
                return False
            return all(
                matches(record, "project_id")
                and matches(record, "guide_id")
                and (
                    "policy_id" not in arguments
                    or (
                        matches(record, "supersedes_policy_id", "policy_id")
                        if name == "guide_submission_artifact_policy_update"
                        else matches(record, "id", "policy_id")
                    )
                )
                for record in records
            )
        if name.startswith("guide_sufficiency"):
            records = data.get("items") if name.endswith("reports_list") else [data]
            if not isinstance(records, list):
                return False
            return all(
                matches(record, "project_id")
                and matches(record, "guide_id")
                and (
                    "report_id" not in arguments
                    or matches(record, "id", "report_id")
                )
                for record in records
            )
        return False

    async def task_execution_operation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
        *,
        upload: bytes | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed task, preparation or submission operation."""
        method, path_template, expected_status = TASK_EXECUTION_OPERATIONS[name]
        selectors = set(re.findall(r"{([a-z_]+)}", path_template))
        path = path_template
        for selector in selectors:
            value = arguments.get(selector)
            if not isinstance(value, str):  # guarded by the tool schema
                return self._invalid_read_response(correlation_id)
            path = path.replace(f"{{{selector}}}", quote(value, safe=""))
        if name == "task_guide_document_content_get":
            return await self._request_binary(path, bearer, correlation_id)

        excluded = {
            *selectors,
            "body",
            "zip_base64",
            "assignment_id",
            "idempotency_key",
            "summary",
            "contributor_attestation",
            "predecessor_submission_id",
            "revision_preparation_id",
            "revision_preparation_sha256",
        }
        params = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None and key not in excluded
        }
        extra_headers: dict[str, str] | None = None
        if name == "preparation_create":
            if upload is None:
                return GatewayResult(failure=SafeFailure("invalid_tool_input", status=400))
            extra_headers = {"X-Task-Assignment-Id": arguments["assignment_id"]}
            for argument, header in (
                ("summary", "X-Submission-Summary"),
                ("contributor_attestation", "X-Contributor-Attestation"),
                ("predecessor_submission_id", "X-Predecessor-Submission-Id"),
                ("revision_preparation_id", "X-Revision-Preparation-Id"),
                ("revision_preparation_sha256", "X-Revision-Preparation-Sha256"),
            ):
                value = arguments.get(argument)
                if isinstance(value, str):
                    extra_headers[header] = value

        mutation = name in _TASK_EXECUTION_MUTATIONS
        outcome = await self._request(
            method,
            path,
            bearer,
            task_execution_output_validator(name),
            correlation_id,
            json_body=arguments.get("body"),
            params=params or None,
            idempotency_key=arguments.get("idempotency_key"),
            expected_status=expected_status,
            mutation=mutation,
            raw_body=upload,
            content_type="application/zip" if name == "preparation_create" else None,
            operation_timeout_seconds=(
                self._settings.document_timeout_seconds
                if name == "preparation_create"
                else None
            ),
            extra_headers=extra_headers,
        )
        if outcome.failure is not None:
            return outcome
        if self._task_execution_response_matches(name, outcome.data or {}, arguments):
            return outcome
        return GatewayResult(
            failure=SafeFailure(
                "workstream_execution_uncertain" if mutation else "invalid_api_response",
                status=502,
                correlation_id=outcome.correlation_id or correlation_id,
            )
        )

    @classmethod
    def _task_execution_response_matches(
        cls, name: str, data: dict[str, Any], arguments: dict[str, Any]
    ) -> bool:
        task_id = arguments.get("task_id")
        project_id = arguments.get("project_id")
        if name == "preparation_create":
            put_attempt_id = data.get("put_attempt_id")
            if not isinstance(put_attempt_id, str):
                return False
            try:
                UUID(put_attempt_id)
            except ValueError:
                return False
            return True
        if name in {"submission_get", "management_submission_get"}:
            return cls._same_uuid(data.get("id"), arguments["submission_id"])
        if not isinstance(task_id, str):
            return False
        if project_id is not None and not isinstance(project_id, str):
            return False
        if name == "preparations_list":
            return cls._items_match(data, {"task_id": task_id}, unique="preparation_id")
        if name == "preparation_get":
            return cls._fields_match(
                data,
                {"task_id": task_id, "preparation_id": arguments["preparation_id"]},
            )
        if name in {"task_get", "task_submission_requirements_get"}:
            return cls._same_uuid(data.get("task_id"), task_id)
        if name in {"task_screen", "task_release", "task_start"}:
            return cls._same_uuid(data.get("id"), task_id)
        if name == "task_claim":
            task = data.get("task")
            assignment = data.get("assignment")
            return (
                isinstance(task, dict)
                and isinstance(assignment, dict)
                and cls._same_uuid(task.get("id"), task_id)
                and cls._same_uuid(assignment.get("task_id"), task_id)
            )
        if name in {"task_work_context_get", "management_task_work_context_get"}:
            task = data.get("task")
            project = data.get("project")
            return (
                isinstance(task, dict)
                and cls._same_uuid(task.get("task_id"), task_id)
                and (
                    project_id is None
                    or (
                        isinstance(project, dict)
                        and cls._same_uuid(project.get("id"), project_id)
                        and cls._same_uuid(task.get("project_id"), project_id)
                    )
                )
            )
        if name == "submission_create":
            body = arguments["body"]
            return cls._same_uuid(data.get("admission_id"), body["admission_id"])
        if name in {"task_submissions_list", "management_task_submissions_list"}:
            return cls._items_match(data, {"task_id": task_id}, unique="id")
        if name == "management_task_submission_requirements_get":
            if not isinstance(project_id, str):
                return False
            return cls._fields_match(
                data,
                {"task_id": task_id, "project_id": project_id},
            )
        return False

    async def task_operation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
        *,
        upload: bytes | None = None,
    ) -> GatewayResult:
        """Dispatch one fixed management, import, audit or model operation."""
        method, path_template, expected_status = TASK_OPERATIONS[name]
        selectors = set(re.findall(r"{([a-z_]+)}", path_template))
        path = path_template
        for selector in selectors:
            value = arguments.get(selector)
            if not isinstance(value, str):
                return self._invalid_read_response(correlation_id)
            path = path.replace(f"{{{selector}}}", quote(value, safe=""))

        if name == "task_import_source_content_get":
            return await self._request_import_source_content(path, bearer, correlation_id)
        if name == "task_import_source_content_upload" and upload is None:
            return GatewayResult(failure=SafeFailure("invalid_tool_input", status=400))

        params = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None
            and key not in selectors
            and key not in {"body", "content_base64", "idempotency_key"}
        }
        mutation = name in _TASK_OPERATION_MUTATIONS
        outcome = await self._request(
            method,
            path,
            bearer,
            task_operation_output_validator(name),
            correlation_id,
            json_body=arguments.get("body"),
            params=params or None,
            idempotency_key=arguments.get("idempotency_key"),
            expected_status=expected_status,
            mutation=mutation,
            raw_body=upload,
            content_type=(
                "application/json" if name == "task_import_source_content_upload" else None
            ),
        )
        if outcome.failure is not None:
            return outcome
        if self._task_operation_response_matches(name, outcome.data or {}, arguments, upload):
            return outcome
        return GatewayResult(
            failure=SafeFailure(
                "workstream_execution_uncertain" if mutation else "invalid_api_response",
                status=502,
                correlation_id=outcome.correlation_id or correlation_id,
            )
        )

    async def _request_import_source_content(
        self,
        path: str,
        bearer: str,
        correlation_id: str | None,
    ) -> GatewayResult:
        request_id = correlation_id or str(uuid4())
        try:
            async with asyncio.timeout(self._settings.total_timeout_seconds):
                async with self._slots:
                    async with self._client.stream(
                        "GET",
                        path,
                        headers={
                            "Authorization": bearer,
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                            "X-Request-ID": request_id,
                        },
                    ) as response:
                        body = await self._bounded_body(
                            response,
                            max_bytes=TASK_IMPORT_SOURCE_MAX_BYTES,
                        )
                        response_id = self._correlation_id(response, request_id)
                        if response.status_code != 200:
                            return GatewayResult(
                                failure=self._api_failure(
                                    response.status_code,
                                    body,
                                    response_id,
                                )
                            )
                        media_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        if media_type != "application/json" or not body:
                            return self._invalid_read_response(response_id)
                        data = {
                            "media_type": media_type,
                            "content_base64": base64.b64encode(body).decode("ascii"),
                            "byte_count": len(body),
                            "sha256": f"sha256:{hashlib.sha256(body).hexdigest()}",
                        }
                        task_operation_output_validator(
                            "task_import_source_content_get"
                        ).validate(data)
                        return GatewayResult(data=data, correlation_id=response_id)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return GatewayResult(
                failure=SafeFailure("workstream_timeout", status=504, retryable=True)
            )
        except ResponseTooLarge:
            return GatewayResult(
                failure=SafeFailure("workstream_response_too_large", status=502)
            )
        except httpx.HTTPError:
            return GatewayResult(
                failure=SafeFailure("workstream_unavailable", status=502, retryable=True)
            )
        except ValidationError:  # pragma: no cover - static schema is checked at startup
            return GatewayResult(failure=SafeFailure("adapter_internal_error", status=500))
        except Exception:  # pragma: no cover - defensive transport boundary
            return GatewayResult(failure=SafeFailure("adapter_internal_error", status=500))

    @classmethod
    def _task_operation_response_matches(
        cls,
        name: str,
        data: dict[str, Any],
        arguments: dict[str, Any],
        upload: bytes | None,
    ) -> bool:
        project_id = cast(str, arguments.get("project_id"))
        task_id = cast(str, arguments.get("task_id"))
        batch_id = cast(str, arguments.get("batch_id"))
        source_id = cast(str | None, arguments.get("source_id"))
        if name == "projects_list":
            return cls._unique_uuid_field(data.get("items"), "project_id")
        if name == "service_actor_create":
            return cls._payload_contains(
                data.get("service_identity"),
                arguments["body"]["service_identity"],
            )
        if name == "task_import_batch_create":
            return cls._fields_match(
                data,
                {"project_id": project_id, "source_id": arguments["body"]["source_id"]},
            )
        if name in {"management_tasks_list", "operational_tasks_list"}:
            return cls._same_uuid(data.get("project_id"), project_id) and cls._items_match(
                data, {"project_id": project_id}, unique="task_id"
            )
        if name == "management_task_create":
            return cls._same_uuid(data.get("project_id"), project_id)
        if name in {"task_import_batch_screen", "task_import_batch_release"}:
            return cls._fields_match(
                data, {"project_id": project_id, "batch_id": batch_id}
            )
        if name == "task_import_batch_get":
            creation = data.get("creation")
            return isinstance(creation, dict) and cls._fields_match(
                creation, {"project_id": project_id, "batch_id": batch_id}
            )
        if name == "management_task_get":
            return cls._fields_match(data, {"project_id": project_id, "task_id": task_id})
        if name in {
            "management_task_locked_context_get",
            "operational_task_locked_context_get",
            "audit_task_locked_context_get",
        }:
            return cls._fields_match(data, {"project_id": project_id, "task_id": task_id})
        if name == "task_revision_context_repair":
            body = arguments["body"]
            predecessor_id = body.get("parent_preparation_id")
            return (
                predecessor_id is None
                or cls._same_uuid(data.get("predecessor_preparation_id"), predecessor_id)
            )
        if name == "audit_task_evidence_get":
            return cls._fields_match(data, {"project_id": project_id, "task_id": task_id})
        if name == "operational_task_start_override":
            return cls._same_uuid(data.get("id"), task_id)
        if name in {
            "project_model_profile_provision",
            "project_model_budget_configure",
        }:
            spec = data.get("spec")
            return isinstance(spec, dict) and cls._same_uuid(spec.get("project_id"), project_id)
        if name == "project_model_usage_effect_get":
            return cls._fields_match(
                data, {"project_id": project_id, "effect_id": arguments["effect_id"]}
            )
        if name == "project_model_recovery_child_create":
            body = arguments["body"]
            slot_matches = cls._payload_contains(data.get("slot_key"), body.get("slot"))
            digest_matches = data.get("request_sha256") == body.get("request_sha256")
            return bool(slot_matches and digest_matches)
        if name in {"task_import_source_declare", "task_import_source_get"}:
            expected: dict[str, str] = {"project_id": project_id}
            if source_id is not None:
                expected["source_id"] = source_id
            matches = cls._fields_match(data, expected)
            if name == "task_import_source_declare":
                body = arguments["body"]
                matches = (
                    matches
                    and data.get("sha256") == body.get("sha256")
                    and data.get("byte_count") == body.get("byte_count")
                )
            return matches
        if name == "task_import_source_content_upload":
            return (
                upload is not None
                and source_id is not None
                and cls._fields_match(
                    data, {"project_id": project_id, "source_id": source_id}
                )
                and data.get("byte_count") == len(upload)
                and data.get("sha256") == f"sha256:{hashlib.sha256(upload).hexdigest()}"
            )
        return False

    async def checker_artifact_operation(
        self,
        name: str,
        bearer: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        """Dispatch one reviewed checker or artifact operation."""
        method, path_template, expected_status = CHECKER_ARTIFACT_OPERATIONS[name]
        path = path_template
        consumed: set[str] = set()
        for key in (
            "project_id",
            "submission_id",
            "checker_run_id",
            "source_run_id",
            "event_id",
            "registry_entry_id",
            "content_id",
            "replica_id",
            "verification_job_id",
            "recovery_attempt_id",
        ):
            marker = "{" + key + "}"
            if marker in path:
                path = path.replace(marker, quote(arguments[key], safe=""))
                consumed.add(key)
        params = {
            key: str(value)
            for key, value in arguments.items()
            if value is not None
            and key not in consumed
            and key not in {"body", "idempotency_key"}
        }
        mutation = name in _CHECKER_ARTIFACT_MUTATIONS
        outcome = await self._request(
            method,
            path,
            bearer,
            checker_artifact_output_validator(name),
            correlation_id,
            json_body=arguments.get("body"),
            params=params or None,
            idempotency_key=arguments.get("idempotency_key"),
            expected_status=expected_status,
            mutation=mutation,
        )
        if outcome.failure is not None:
            return outcome
        if not self._checker_artifact_response_matches(name, outcome.data or {}, arguments):
            return GatewayResult(
                failure=SafeFailure(
                    "workstream_execution_uncertain" if mutation else "invalid_api_response",
                    status=502,
                    correlation_id=outcome.correlation_id or correlation_id,
                )
            )
        return outcome

    @classmethod
    def _checker_artifact_response_matches(
        cls, name: str, data: dict[str, Any], arguments: dict[str, Any]
    ) -> bool:
        if name == "artifact_readiness_get":
            return True
        if name in {"submission_checker_runs_list", "project_checker_runs_list"}:
            return cls._items_match(
                data, {"submission_id": arguments["submission_id"]}, unique="id"
            )
        if name in {"submission_checker_runs_get", "project_checker_runs_get"}:
            return cls._fields_match(
                data,
                {
                    "id": arguments["checker_run_id"],
                    "submission_id": arguments["submission_id"],
                },
            )
        if name == "checker_retry_sources_list":
            return cls._same_uuid(
                data.get("project_id"), arguments["project_id"]
            ) and cls._items_match(
                data,
                {"project_id": arguments["project_id"]},
                unique="source_run_id",
                nested="source",
            )
        if name == "checker_runs_retry":
            source = data.get("source")
            return isinstance(source, dict) and cls._fields_match(
                source,
                {
                    "project_id": arguments["project_id"],
                    "source_run_id": arguments["source_run_id"],
                },
            )
        if name == "post_submit_deliveries_list":
            return cls._same_uuid(
                data.get("project_id"), arguments["project_id"]
            ) and cls._items_match(
                data, {"project_id": arguments["project_id"]}, unique="event_id"
            )
        if name == "post_submit_deliveries_reconcile":
            source = data.get("source")
            return isinstance(source, dict) and cls._fields_match(
                source,
                {
                    "project_id": arguments["project_id"],
                    "event_id": arguments["event_id"],
                },
            )
        if name == "checker_registry_read":
            return cls._same_uuid(data.get("registry_entry_id"), arguments["registry_entry_id"])
        if name == "checker_registry_register":
            body = arguments["body"]
            return cls._same_uuid(
                data.get("registration_operation_id"), arguments["idempotency_key"]
            ) and cls._payload_contains(data, body)
        if name == "artifact_bindings_list":
            return cls._items_match(
                data,
                {
                    "resource_type": arguments["resource_type"],
                    "resource_id": arguments["resource_id"],
                },
                unique="id",
            )
        if name == "artifact_replicas_list":
            return cls._items_match(data, {"content_id": arguments["content_id"]}, unique="id")
        if name == "artifact_receipts_list":
            return cls._items_match(data, {"replica_id": arguments["replica_id"]}, unique="id")
        if name == "artifact_verification_job_get":
            return cls._same_uuid(data.get("id"), arguments["verification_job_id"])
        if name == "artifact_verification_job_retry":
            return cls._same_uuid(
                data.get("source_verification_job_id"), arguments["verification_job_id"]
            )
        if name == "artifact_recovery_attempt_get":
            return cls._same_uuid(data.get("id"), arguments["recovery_attempt_id"])
        if name == "artifact_admission_usage_get":
            return cls._admission_items_match(data, arguments)
        if name == "artifact_audit_events_list":
            return cls._items_match(
                data,
                {
                    "entity_type": arguments["resource_type"],
                    "entity_id": arguments["resource_id"],
                },
                unique="id",
            )
        return False

    @classmethod
    def _payload_contains(cls, actual: object, expected: object) -> bool:
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(
                key in actual and cls._payload_contains(actual[key], value)
                for key, value in expected.items()
            )
        return actual == expected

    @classmethod
    def _fields_match(cls, item: dict[str, Any], expected: dict[str, str]) -> bool:
        return all(
            item.get(key) == value
            if key in {"resource_type", "entity_type"}
            else cls._same_uuid(item.get(key), value)
            for key, value in expected.items()
        )

    @classmethod
    def _items_match(
        cls,
        data: dict[str, Any],
        expected: dict[str, str],
        *,
        unique: str,
        nested: str | None = None,
    ) -> bool:
        items = data.get("items")
        if not isinstance(items, list):
            return False
        selected: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                return False
            candidate = item.get(nested) if nested is not None else item
            if not isinstance(candidate, dict) or not cls._fields_match(candidate, expected):
                return False
            selected.append(candidate)
        return cls._unique_uuid_field(selected, unique)

    @classmethod
    def _admission_items_match(
        cls, data: dict[str, Any], arguments: dict[str, Any]
    ) -> bool:
        items = data.get("items")
        if not isinstance(items, list):
            return False
        expected = {
            "project": arguments["project_id"],
            **({"task": arguments["task_id"]} if "task_id" in arguments else {}),
        }
        seen: set[tuple[str, str]] = set()
        for item in items:
            if not isinstance(item, dict):
                return False
            scope_type = item.get("scope_type")
            scope_id = item.get("scope_id")
            if not isinstance(scope_type, str) or not isinstance(scope_id, str):
                return False
            if scope_type in expected and not cls._same_uuid(scope_id, expected[scope_type]):
                return False
            if scope_type not in {"deployment", *expected}:
                return False
            selector = (scope_type, scope_id)
            if selector in seen:
                return False
            seen.add(selector)
        return True

    @classmethod
    def _policy_lineage_matches(cls, data: dict[str, Any], selector: str) -> bool:
        """Bind a successful immutable policy response to its requested predecessor."""
        if selector == '"no-current-policy"':
            return data.get("policy_generation") == 1 and data.get(
                "supersedes_policy_id"
            ) is None
        match = re.fullmatch(
            r'"([0-9a-fA-F-]{36})\.([1-9][0-9]*)\.([0-9a-f]{64})"', selector
        )
        if match is None:
            return False
        predecessor_id, generation, _ = match.groups()
        return cls._same_uuid(data.get("supersedes_policy_id"), predecessor_id) and data.get(
            "policy_generation"
        ) == int(generation) + 1

    @staticmethod
    def _same_uuid(candidate: object, expected: str) -> bool:
        try:
            return UUID(str(candidate)) == UUID(expected)
        except (TypeError, ValueError):
            return False

    @classmethod
    def _unique_uuid_field(cls, items: object, field: str) -> bool:
        if not isinstance(items, list):
            return False
        identifiers: set[UUID] = set()
        for item in items:
            if not isinstance(item, dict):
                return False
            try:
                identifier = UUID(str(item[field]))
            except (KeyError, TypeError, ValueError):
                return False
            if identifier in identifiers:
                return False
            identifiers.add(identifier)
        return True

    @staticmethod
    def _valid_grant_observation(grant: dict[str, Any]) -> bool:
        snapshot = grant.get("qualification_snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("requested_role") != grant.get("role"):
            return False
        if any(
            "://" in reference
            for key in ("external_expertise_refs",)
            for reference in snapshot.get(key, [])
            if isinstance(reference, str)
        ):
            return False
        for key in ("skills_snapshot", "reputation_snapshot"):
            evidence = snapshot.get(key)
            if not isinstance(evidence, dict):
                return False
            availability = evidence.get("availability")
            references = evidence.get("reference_ids")
            reason = evidence.get("unavailable_reason")
            if not isinstance(references, list) or any(
                not isinstance(reference, str) or "://" in reference
                for reference in references
            ):
                return False
            if availability == "available":
                if not references or reason is not None:
                    return False
            elif availability == "unavailable":
                if references or reason not in {
                    "not_collected",
                    "source_unavailable",
                    "no_record",
                }:
                    return False
            else:
                return False
        return True

    @staticmethod
    def _invalid_read_response(correlation_id: str | None) -> GatewayResult:
        return GatewayResult(
            failure=SafeFailure(
                "invalid_api_response",
                status=502,
                correlation_id=correlation_id,
            )
        )

    async def _request(
        self,
        method: str,
        path: str,
        bearer: str,
        output_validator: Draft202012Validator,
        correlation_id: str | None,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        if_match: str | None = None,
        expected_status: int = 200,
        expected_payload: dict[str, Any] | None = None,
        expected_resource_id: str | None = None,
        mutation: bool = False,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        array_envelope: bool = False,
        operation_timeout_seconds: float | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GatewayResult:
        request_id = correlation_id or str(uuid4())
        operation_timeout = operation_timeout_seconds or self._settings.total_timeout_seconds
        try:
            async with asyncio.timeout(operation_timeout):
                async with self._slots:
                    headers = {
                        "Authorization": bearer,
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "X-Request-ID": request_id,
                    }
                    if idempotency_key is not None:
                        headers["Idempotency-Key"] = idempotency_key
                    if if_match is not None:
                        headers["If-Match"] = if_match
                    if content_type is not None:
                        headers["Content-Type"] = content_type
                    if extra_headers is not None:
                        headers.update(extra_headers)
                    async with self._client.stream(
                        method,
                        path,
                        headers=headers,
                        json=json_body if raw_body is None else None,
                        content=raw_body,
                        params=params,
                        timeout=(
                            operation_timeout_seconds
                            if operation_timeout_seconds is not None
                            else httpx.USE_CLIENT_DEFAULT
                        ),
                    ) as response:
                        body = await self._bounded_body(response)
                        correlation_id = self._correlation_id(response, request_id)
                        if response.status_code != expected_status:
                            failure = self._api_failure(response.status_code, body, correlation_id)
                            # Proxy errors and unexpected successes cannot prove rollback.
                            if mutation and (
                                response.status_code < 400 or response.status_code >= 500
                            ):
                                failure = SafeFailure(
                                    "workstream_execution_uncertain",
                                    status=response.status_code,
                                    code=failure.code,
                                    correlation_id=correlation_id,
                                )
                            return GatewayResult(failure=failure)
                        media_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        if media_type != "application/json":
                            return GatewayResult(
                                failure=SafeFailure(
                                    (
                                        "workstream_execution_uncertain"
                                        if mutation
                                        else "invalid_api_response"
                                    ),
                                    status=502,
                                    correlation_id=correlation_id,
                                )
                            )
                        try:
                            decoded = json.loads(body)
                            payload: dict[str, Any]
                            if array_envelope and isinstance(decoded, list):
                                payload = {"items": decoded}
                            elif isinstance(decoded, dict):
                                payload = decoded
                            else:
                                raise ValueError
                            output_validator.validate(payload)
                        except (ValueError, RecursionError, ValidationError):
                            return GatewayResult(
                                failure=SafeFailure(
                                    (
                                        "workstream_execution_uncertain"
                                        if mutation
                                        else "invalid_api_response"
                                    ),
                                    status=502,
                                    correlation_id=correlation_id,
                                )
                            )
                        if expected_payload is not None and any(
                            payload.get(key) != value for key, value in expected_payload.items()
                        ):
                            return GatewayResult(
                                failure=SafeFailure(
                                    "workstream_execution_uncertain",
                                    status=502,
                                    correlation_id=correlation_id,
                                )
                            )
                        if expected_resource_id is not None:
                            try:
                                resource_matches = UUID(payload["resource_id"]) == UUID(
                                    expected_resource_id
                                )
                            except (KeyError, TypeError, ValueError):
                                resource_matches = False
                            if not resource_matches:
                                return GatewayResult(
                                    failure=SafeFailure(
                                        "workstream_execution_uncertain",
                                        status=502,
                                        correlation_id=correlation_id,
                                    )
                                )
                        return GatewayResult(data=payload, correlation_id=correlation_id)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=504,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(
                failure=SafeFailure("workstream_timeout", status=504, retryable=True)
            )
        except httpx.TimeoutException:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=504,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(
                failure=SafeFailure("workstream_timeout", status=504, retryable=True)
            )
        except ResponseTooLarge:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=502,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(failure=SafeFailure("workstream_response_too_large", status=502))
        except httpx.HTTPError:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=502,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(
                failure=SafeFailure("workstream_unavailable", status=502, retryable=True)
            )
        except Exception:  # pragma: no cover
            return GatewayResult(failure=SafeFailure("adapter_internal_error", status=500))

    async def _bounded_body(
        self, response: httpx.Response, *, max_bytes: int | None = None
    ) -> bytes:
        byte_limit = max_bytes or self._settings.max_response_bytes
        content_encoding = response.headers.get("content-encoding", "identity").lower()
        if content_encoding != "identity":
            raise ResponseTooLarge
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > byte_limit:
                    raise ResponseTooLarge
            except ValueError:
                pass
        if response.is_stream_consumed:
            if len(response.content) > byte_limit:
                raise ResponseTooLarge
            return response.content
        body = bytearray()
        async for chunk in response.aiter_raw():
            body.extend(chunk)
            if len(body) > byte_limit:
                raise ResponseTooLarge
        return bytes(body)

    @staticmethod
    def _correlation_id(response: httpx.Response, fallback: str) -> str:
        for name in _CORRELATION_HEADERS:
            value = response.headers.get(name)
            if value and _SAFE_VALUE.fullmatch(value):
                return str(value)
        return fallback

    @staticmethod
    def _api_failure(status: int, body: bytes, correlation_id: str) -> SafeFailure:
        code = None
        if len(body) <= 8_192:
            try:
                payload = json.loads(body)
                error = payload.get("error") if isinstance(payload, dict) else None
                candidate = error.get("code") if isinstance(error, dict) else None
                if isinstance(candidate, str) and candidate in _PUBLIC_ERROR_CODES:
                    code = candidate
            except (ValueError, RecursionError):
                pass
        return SafeFailure(
            "workstream_request_failed",
            status=status,
            code=code,
            correlation_id=correlation_id,
            retryable=status in {429, 502, 503, 504} or code == "idempotency_pending",
        )


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.api_url,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.connect_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=settings.max_in_flight,
            max_keepalive_connections=settings.max_in_flight,
        ),
    )
