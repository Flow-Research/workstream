from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from workstream_mcp.http_gateway import GUIDE_LIFECYCLE_OPERATIONS
from workstream_mcp.schemas import GUIDE_LIFECYCLE_CONTRACT_NAMES

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "mcp_server" / "contracts"
BACKEND = ROOT / "backend"
OPERATIONS = {
    "profile_get": ("/api/v1/actors/me", "get"),
    "profile_update": ("/api/v1/actors/me", "patch"),
    "authorization_context_get": ("/api/v1/actors/me/authorization-context", "get"),
    "permissions_list": ("/api/v1/authorization/permissions", "get"),
    "admin_roles_list": ("/api/v1/authorization/admin-role-definitions", "get"),
    "admin_grants_list": ("/api/v1/admin-role-grants", "get"),
    "actor_admin_grants_list": ("/api/v1/actors/{actor_profile_id}/admin-role-grants", "get"),
    "actor_get": ("/api/v1/actors/{actor_profile_id}", "get"),
    "actor_identity_link_get": ("/api/v1/actors/{actor_profile_id}/identity-links", "get"),
    "admin_grants_issue": ("/api/v1/admin-role-grants", "post"),
    "admin_grants_revoke": ("/api/v1/admin-role-grants/{grant_id}/revoke", "post"),
    "actor_suspend": ("/api/v1/actors/{actor_profile_id}/suspend", "post"),
    "actor_reactivate": ("/api/v1/actors/{actor_profile_id}/reactivate", "post"),
    "actor_deactivate": ("/api/v1/actors/{actor_profile_id}/deactivate", "post"),
    "identity_link_revoke": (
        "/api/v1/actor-identity-links/{identity_link_id}/revoke",
        "post",
    ),
    "identity_link_reactivate": (
        "/api/v1/actor-identity-links/{identity_link_id}/reactivate",
        "post",
    ),
    "projects_create": ("/api/v1/projects", "post"),
    "projects_get": ("/api/v1/projects/{project_id}", "get"),
    "contributor_candidates_list": (
        "/api/v1/projects/{project_id}/contributor-candidates",
        "get",
    ),
    "project_grants_issue": ("/api/v1/projects/{project_id}/role-grants", "post"),
    "project_grants_list": ("/api/v1/projects/{project_id}/role-grants", "get"),
    "project_grants_get": (
        "/api/v1/projects/{project_id}/role-grants/{grant_id}",
        "get",
    ),
    "project_grants_revoke": (
        "/api/v1/projects/{project_id}/role-grants/{grant_id}/revoke",
        "post",
    ),
    "guides_create": ("/api/v1/projects/{project_id}/guides", "post"),
    "guides_update": (
        "/api/v1/projects/{project_id}/guides/{guide_id}",
        "patch",
    ),
    "review_policy_put": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/review-policy",
        "put",
    ),
    "revision_policy_put": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/revision-policy",
        "put",
    ),
    "actor_projects_list": ("/api/v1/actors/me/projects", "get"),
    "actor_assignments_list": ("/api/v1/actors/me/assignments", "get"),
    "actor_submissions_list": ("/api/v1/actors/me/submissions", "get"),
    "actor_summary_get": ("/api/v1/actors/me/summary", "get"),
    "contributions_list": ("/api/v1/actors/me/contributions", "get"),
    "project_contributions_export": (
        "/api/v1/projects/{project_id}/contributions/export",
        "get",
    ),
    "contribution_policies_list": (
        "/api/v1/projects/{project_id}/contribution-policies",
        "get",
    ),
    "contribution_policy_current_get": (
        "/api/v1/projects/{project_id}/contribution-policies/current",
        "get",
    ),
    "contribution_policy_get": (
        "/api/v1/projects/{project_id}/contribution-policies/{policy_id}",
        "get",
    ),
    "contribution_policy_create": (
        "/api/v1/projects/{project_id}/contribution-policies/drafts",
        "post",
    ),
    "contribution_policy_update": (
        "/api/v1/projects/{project_id}/contribution-policies/{policy_id}/versions/{version_id}",
        "put",
    ),
    "contribution_policy_publish": (
        "/api/v1/projects/{project_id}/contribution-policies/{policy_id}/versions/{version_id}/publication",
        "post",
    ),
    "contribution_policy_retire": (
        "/api/v1/projects/{project_id}/contribution-policies/{policy_id}/versions/{version_id}/retirement",
        "post",
    ),
    "project_submissions_list": ("/api/v1/projects/{project_id}/submissions", "get"),
    "project_assignments_list": ("/api/v1/projects/{project_id}/assignments", "get"),
    "project_summary_get": ("/api/v1/projects/{project_id}/summary", "get"),
    "project_task_import_batches_list": (
        "/api/v1/projects/{project_id}/task-import-batches",
        "get",
    ),
    "project_preparations_list": (
        "/api/v1/projects/{project_id}/submission-bundle-preparations",
        "get",
    ),
    "active_guide_get": ("/api/v1/projects/{project_id}/active-guide", "get"),
    "ready_tasks_list": ("/api/v1/projects/{project_id}/tasks/ready", "get"),
    "project_guides_list": ("/api/v1/projects/{project_id}/guides", "get"),
    "project_guide_get": ("/api/v1/projects/{project_id}/guides/{guide_id}", "get"),
    "guide_activate": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/activate",
        "post",
    ),
    "guide_activation_readiness_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/activation-readiness",
        "get",
    ),
    "guide_proposal_correct": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/"
        "{compilation_id}/corrections",
        "post",
    ),
    "guide_correction_dispatch": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/"
        "{compilation_id}/corrections/{correction_operation_id}/dispatch",
        "post",
    ),
    "guide_post_policy_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/"
        "{compilation_id}/post-submission-policies/{policy_id}",
        "get",
    ),
    "guide_post_policy_approve": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/"
        "{compilation_id}/post-submission-policies/{policy_id}/approval",
        "post",
    ),
    "guide_post_policy_correct": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/"
        "{compilation_id}/post-submission-policies/{policy_id}/corrections",
        "post",
    ),
    "guide_pre_submission_approve": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/"
        "{compilation_id}/pre-submission-approval",
        "post",
    ),
    "guide_proposal_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/"
        "{compilation_id}/proposal",
        "get",
    ),
    "guide_document_upload": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/documents/{document_id}/content",
        "post",
    ),
    "guide_document_content_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/documents/{document_id}/content",
        "get",
    ),
    "guide_effective_submission_artifact_policy_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/"
        "effective-submission-artifact-policy",
        "get",
    ),
    "guide_pre_submit_checker_policy_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy",
        "get",
    ),
    "guide_assistance_request": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/setup", "post",
    ),
    "guide_requirements_compile": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/requirements/compile", "post",
    ),
    "guide_setup_latest_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest",
        "get",
    ),
    "guide_submission_artifact_policies_list": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        "get",
    ),
    "guide_submission_artifact_policy_create": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        "post",
    ),
    "guide_submission_artifact_policy_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/"
        "submission-artifact-policies/{policy_id}",
        "get",
    ),
    "guide_submission_artifact_policy_update": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/"
        "submission-artifact-policies/{policy_id}",
        "patch",
    ),
    "guide_sufficiency_reports_list": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        "get",
    ),
    "guide_sufficiency_report_create": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        "post",
    ),
    "guide_sufficiency_report_get": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}",
        "get",
    ),
    "guide_sufficiency_warnings_acknowledge": (
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/"
        "{report_id}/acknowledge-warnings",
        "post",
    ),
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _without_schema_titles(value: Any, *, _in_properties: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_schema_titles(item, _in_properties=key == "properties")
            for key, item in value.items()
            if _in_properties or key != "title"
        }
    if isinstance(value, list):
        return [
            _without_schema_titles(item, _in_properties=_in_properties)
            for item in value
        ]
    return value


def _selected(openapi: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    operation = openapi["paths"][path][method]
    names: set[str] = set()
    pending: list[Any] = [operation]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
                name = reference.rsplit("/", 1)[-1]
                if name not in names:
                    names.add(name)
                    pending.append(openapi["components"]["schemas"][name])
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return {
        "operation": operation,
        "components": {
            "schemas": {name: openapi["components"]["schemas"][name] for name in sorted(names)}
        },
    }


def _running_openapi() -> dict[str, Any]:
    command = os.environ.get("WORKSTREAM_MCP_OPENAPI_COMMAND")
    argv = (
        shlex.split(command)
        if command
        else [
            sys.executable,
            "-c",
            "import json; from app.main import app; print(json.dumps(app.openapi()))",
        ]
    )
    completed = subprocess.run(  # noqa: S603 - fixed local/configured contract probe
        argv,
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize("name", OPERATIONS)
def test_contract_has_a_tamper_evident_selected_fragment(name: str) -> None:
    snapshot = json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
    captured = {"operation": snapshot["operation"], "components": snapshot["components"]}
    assert hashlib.sha256(_canonical(captured)).hexdigest() == snapshot["canonical_sha256"]


def test_contracts_match_current_backend_openapi_when_command_is_provided() -> None:
    if "WORKSTREAM_MCP_OPENAPI_COMMAND" not in os.environ:
        pytest.skip("backend OpenAPI comparison is run in the isolated backend environment")
    openapi = _running_openapi()
    for name, (path, method) in OPERATIONS.items():
        snapshot = json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
        captured = {"operation": snapshot["operation"], "components": snapshot["components"]}
        assert snapshot["source"]["openapi_version"] == openapi["openapi"]
        assert _without_schema_titles(captured) == _without_schema_titles(
            _selected(openapi, path, method)
        )


def test_selected_fragment_follows_transitive_schema_references() -> None:
    openapi = {
        "paths": {
            "/selected": {"get": {"responses": {"200": {"$ref": "#/components/schemas/Outer"}}}}
        },
        "components": {
            "schemas": {
                "Outer": {"properties": {"child": {"$ref": "#/components/schemas/Inner"}}},
                "Inner": {"type": "string"},
            }
        },
    }
    selected = _selected(openapi, "/selected", "get")
    assert set(selected["components"]["schemas"]) == {"Inner", "Outer"}


def test_guide_gateway_bindings_match_reviewed_contract_snapshots() -> None:
    assert set(GUIDE_LIFECYCLE_OPERATIONS) == set(GUIDE_LIFECYCLE_CONTRACT_NAMES)
    for name in GUIDE_LIFECYCLE_CONTRACT_NAMES:
        method, path, status = GUIDE_LIFECYCLE_OPERATIONS[name]
        assert OPERATIONS[name] == (path, method.lower())
        snapshot = json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
        success_codes = {
            int(code)
            for code in snapshot["operation"]["responses"]
            if str(code).startswith("2")
        }
        assert success_codes == {status}


def test_contract_comparison_ignores_only_schema_titles() -> None:
    stored = {"schema": {"title": "Old display label", "type": "string"}}
    current = {"schema": {"title": "New display label", "type": "string"}}
    changed = {"schema": {"title": "New display label", "type": "integer"}}

    assert _without_schema_titles(stored) == _without_schema_titles(current)
    assert _without_schema_titles(stored) != _without_schema_titles(changed)


def test_contract_comparison_preserves_property_named_title() -> None:
    stored = {
        "schema": {
            "properties": {
                "title": {"title": "Old display label", "type": "string"}
            }
        }
    }
    current = {
        "schema": {
            "properties": {
                "title": {"title": "New display label", "type": "string"}
            }
        }
    }
    changed = {
        "schema": {
            "properties": {
                "title": {"title": "New display label", "type": "integer"}
            }
        }
    }

    assert _without_schema_titles(stored) == _without_schema_titles(current)
    assert _without_schema_titles(stored) != _without_schema_titles(changed)
