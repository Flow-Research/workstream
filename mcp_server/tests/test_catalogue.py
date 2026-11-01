from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from workstream_mcp.schemas import (
    ACCESS_READ_INPUT_SCHEMAS,
    ACTOR_LIFECYCLE_INPUT_SCHEMAS,
    ADMIN_GRANT_INPUT_SCHEMAS,
    AUTHORIZATION_CONTEXT_INPUT_SCHEMA,
    CHECKER_ARTIFACT_CONTRACT_NAMES,
    CONTRIBUTION_POLICY_INPUT_SCHEMAS,
    EMPTY_INPUT_SCHEMA,
    GUIDE_INPUT_SCHEMAS,
    GUIDE_LIFECYCLE_CONTRACT_NAMES,
    POLICY_INPUT_SCHEMAS,
    PROFILE_UPDATE_INPUT_SCHEMA,
    PROJECT_GRANT_INPUT_SCHEMAS,
    PROJECT_INPUT_SCHEMAS,
    TASK_EXECUTION_CONTRACT_NAMES,
    TASK_EXECUTION_INPUT_SCHEMAS,
    TASK_OPERATION_CONTRACT_NAMES,
    WORKSPACE_READ_INPUT_SCHEMAS,
    authorization_context_output_schema,
    checker_artifact_input_schema,
    guide_lifecycle_input_schema,
    profile_output_schema,
    profile_update_output_schema,
    task_operation_input_schema,
    task_operation_output_schema,
)
from workstream_mcp.tools.checker_artifacts import TOOL_NAMES as CHECKER_ARTIFACT_TOOL_NAMES
from workstream_mcp.tools.context import TOOL_NAME as CONTEXT_TOOL_NAME
from workstream_mcp.tools.context import definition as context_definition
from workstream_mcp.tools.profile import (
    PROFILE_GET_TOOL_NAME,
    PROFILE_UPDATE_TOOL_NAME,
    get_definition,
    update_definition,
)
from workstream_mcp.tools.task_execution import TOOL_NAMES as TASK_EXECUTION_TOOL_NAMES
from workstream_mcp.tools.task_operations import TOOL_NAMES as TASK_OPERATION_TOOL_NAMES


def test_tool_definitions_are_closed_and_use_selected_outputs() -> None:
    profile_get = get_definition()
    profile_update = update_definition()
    context_get = context_definition()

    assert profile_get.input_schema == EMPTY_INPUT_SCHEMA
    assert profile_get.output_schema == profile_output_schema()
    assert profile_update.input_schema == PROFILE_UPDATE_INPUT_SCHEMA
    assert profile_update.output_schema == profile_update_output_schema()
    assert context_get.input_schema == AUTHORIZATION_CONTEXT_INPUT_SCHEMA
    assert context_get.output_schema == authorization_context_output_schema()
    # All three calls can write admission/audit state in Workstream.
    assert all(
        tool.annotations is not None and tool.annotations.read_only_hint is False
        for tool in (profile_get, profile_update, context_get)
    )
    assert profile_update.annotations is not None
    assert profile_update.annotations.destructive_hint is True
    assert profile_update.annotations.idempotent_hint is False


def test_mcp_tool_listing_exposes_exactly_the_chunk_catalogue(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, _, _ = adapter
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    listed = response.json()["result"]["tools"]
    assert [item["name"] for item in listed] == [
        PROFILE_GET_TOOL_NAME,
        PROFILE_UPDATE_TOOL_NAME,
        CONTEXT_TOOL_NAME,
        "workstream_permissions_list",
        "workstream_admin_roles_list",
        "workstream_admin_grants_list",
        "workstream_admin_grants_issue",
        "workstream_admin_grants_revoke",
        "workstream_actor_suspend",
        "workstream_actor_reactivate",
        "workstream_actor_deactivate",
        "workstream_identity_link_revoke",
        "workstream_identity_link_reactivate",
        "workstream_actor_admin_grants_list",
        "workstream_actor_get",
        "workstream_actor_identity_link_get",
        "workstream_projects_create",
        "workstream_projects_get",
        "workstream_contributor_candidates_list",
        "workstream_project_grants_issue",
        "workstream_project_grants_list",
        "workstream_project_grants_get",
        "workstream_project_grants_revoke",
        "workstream_guides_create",
        "workstream_guides_update",
        "workstream_review_policy_put",
        "workstream_revision_policy_put",
        "workstream_actor_projects_list",
        "workstream_actor_assignments_list",
        "workstream_actor_submissions_list",
        "workstream_actor_summary_get",
        "workstream_contributions_list",
        "workstream_project_contributions_export",
        "workstream_project_submissions_list",
        "workstream_project_assignments_list",
        "workstream_project_summary_get",
        "workstream_project_task_import_batches_list",
        "workstream_project_preparations_list",
        "workstream_active_guide_get",
        "workstream_ready_tasks_list",
        "workstream_contribution_policies_list",
        "workstream_contribution_policy_current_get",
        "workstream_contribution_policy_get",
        "workstream_contribution_policy_create",
        "workstream_contribution_policy_update",
        "workstream_contribution_policy_publish",
        "workstream_contribution_policy_retire",
        "workstream_project_guides_list",
        "workstream_project_guide_get",
        "workstream_guide_activate",
        "workstream_guide_activation_readiness_get",
        "workstream_guide_proposal_correct",
        "workstream_guide_correction_dispatch",
        "workstream_guide_post_policy_get",
        "workstream_guide_post_policy_approve",
        "workstream_guide_post_policy_correct",
        "workstream_guide_pre_submission_approve",
        "workstream_guide_proposal_get",
        "workstream_guide_document_upload",
        "workstream_guide_document_content_get",
        "workstream_guide_effective_submission_artifact_policy_get",
        "workstream_guide_pre_submit_checker_policy_get",
        "workstream_guide_setup_latest_get",
        "workstream_guide_submission_artifact_policies_list",
        "workstream_guide_submission_artifact_policy_create",
        "workstream_guide_submission_artifact_policy_get",
        "workstream_guide_submission_artifact_policy_update",
        "workstream_guide_sufficiency_reports_list",
        "workstream_guide_sufficiency_report_create",
        "workstream_guide_sufficiency_report_get",
        "workstream_guide_sufficiency_warnings_acknowledge",
        *CHECKER_ARTIFACT_TOOL_NAMES,
        *TASK_EXECUTION_TOOL_NAMES,
        *TASK_OPERATION_TOOL_NAMES,
    ]
    assert [item["inputSchema"] for item in listed] == [
        EMPTY_INPUT_SCHEMA,
        PROFILE_UPDATE_INPUT_SCHEMA,
        AUTHORIZATION_CONTEXT_INPUT_SCHEMA,
        *list(ACCESS_READ_INPUT_SCHEMAS.values())[:3],
        *ADMIN_GRANT_INPUT_SCHEMAS.values(),
        *ACTOR_LIFECYCLE_INPUT_SCHEMAS.values(),
        *list(ACCESS_READ_INPUT_SCHEMAS.values())[3:],
        *PROJECT_INPUT_SCHEMAS.values(),
        *PROJECT_GRANT_INPUT_SCHEMAS.values(),
        *GUIDE_INPUT_SCHEMAS.values(),
        *POLICY_INPUT_SCHEMAS.values(),
        *WORKSPACE_READ_INPUT_SCHEMAS.values(),
        *CONTRIBUTION_POLICY_INPUT_SCHEMAS.values(),
        *(guide_lifecycle_input_schema(name) for name in GUIDE_LIFECYCLE_CONTRACT_NAMES),
        *(
            checker_artifact_input_schema(name)
            for name in CHECKER_ARTIFACT_CONTRACT_NAMES
        ),
        *(TASK_EXECUTION_INPUT_SCHEMAS[name] for name in TASK_EXECUTION_CONTRACT_NAMES),
        *(task_operation_input_schema(name) for name in TASK_OPERATION_CONTRACT_NAMES),
    ]
    assert [item["outputSchema"] for item in listed[-24:]] == [
        task_operation_output_schema(name) for name in TASK_OPERATION_CONTRACT_NAMES
    ]


def test_discover_exposes_tools_without_resources_or_prompts(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, _, _ = adapter
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2026-07-28",
            "mcp-method": "server/discover",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "server/discover",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientInfo": {
                        "name": "catalogue-test",
                        "version": "0",
                    },
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert "2026-07-28" in result["supportedVersions"]
    assert "tools" in result["capabilities"]
    assert "resources" not in result["capabilities"]
    assert "prompts" not in result["capabilities"]
