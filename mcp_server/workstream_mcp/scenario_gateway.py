"""Temporary deterministic gateway for MCP surfaces without backend APIs.

This gateway is intentionally non-authoritative. It exists only to let the
WS-MCP-001 public MCP catalogue and conformance tests be built while backend
review, contribution, contributor-project-list, and contributor-task-list APIs
are unavailable.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from workstream_mcp.auth import RequestContext
from workstream_mcp.errors import MCPErrorCode, WorkstreamMCPError

SCENARIO_TIMESTAMP = "2026-07-10T00:00:00+00:00"


class ScenarioContributorGateway:
    """Deterministic temporary contributor gateway for unavailable APIs."""

    temporary = True

    def __init__(self) -> None:
        """Create a bounded in-memory scenario fixture."""
        self._projects = [
            {
                "project_id": "scenario-project-1",
                "name": "Scenario Project",
                "summary": "Temporary project fixture for MCP conformance.",
                "capability": "both",
                "availability_state": "approved",
            }
        ]
        self._tasks = [
            {
                "task_id": "scenario-task-1",
                "project_id": "scenario-project-1",
                "project_name": "Scenario Project",
                "title": "Scenario task",
                "summary": "Temporary task fixture for MCP conformance.",
                "actor_facing_state": "available",
                "may_claim": True,
                "context_resource": "workstream://tasks/scenario-task-1/context",
                "status_resource": "workstream://tasks/scenario-task-1/status",
            }
        ]
        self._contributions = [
            {
                "contribution_ref": "scenario-contribution-1",
                "project_id": "scenario-project-1",
                "project_name": "Scenario Project",
                "contribution_type": "submission_work",
                "source_ref": "scenario-task-1",
                "outcome": "accepted",
                "recorded_at": _now(),
                "compensation_status": "recorded",
            }
        ]
        self._review = {
            "state": "available_to_claim",
            "review_routing_ref": "scenario-review-route-1",
            "review_ref": "scenario-review-1",
            "project_id": "scenario-project-1",
            "task_summary": "Scenario review task",
            "actor_facing_state": "available_to_claim",
            "context_resource": None,
        }

    async def get_my_projects(self, context: RequestContext) -> dict[str, Any]:
        """Return deterministic project capabilities for tests and local demos."""
        _require_context(context)
        return {"source": "temporary_scenario_gateway", "projects": deepcopy(self._projects)}

    async def get_my_contributions(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return deterministic contribution records."""
        _require_context(context)
        records = deepcopy(self._contributions)
        if project_id is not None:
            records = [record for record in records if record["project_id"] == project_id]
        return {
            "source": "temporary_scenario_gateway",
            "project_id": project_id,
            "contributions": records,
        }

    async def list_tasks(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return deterministic task views."""
        _require_context(context)
        tasks = deepcopy(self._tasks)
        if project_id is not None:
            tasks = [task for task in tasks if task["project_id"] == project_id]
        return {"source": "temporary_scenario_gateway", "project_id": project_id, "tasks": tasks}

    async def get_current_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
    ) -> dict[str, Any]:
        """Return no more than one deterministic review view."""
        _require_context(context)
        if project_id != self._review["project_id"]:
            return {
                "source": "temporary_scenario_gateway",
                "project_id": project_id,
                "state": "none_available",
            }
        return {"source": "temporary_scenario_gateway", **deepcopy(self._review)}

    async def get_review_context(
        self,
        context: RequestContext,
        *,
        review_ref: str,
    ) -> dict[str, Any]:
        """Return deterministic review context only for the leased fixture."""
        _require_context(context)
        if review_ref != self._review["review_ref"] or self._review["state"] != "leased_to_actor":
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "Review context is available only for a review leased to the actor.",
                correlation_id=context.correlation_id,
            )
        return {
            "source": "temporary_scenario_gateway",
            "review_ref": review_ref,
            "project_id": self._review["project_id"],
            "task": {"title": "Scenario review task"},
            "submission": {"submission_id": "scenario-submission-1", "version": 1},
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "findings_required_for": ["needs_revision"],
        }

    async def claim_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
        review_routing_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Claim the deterministic current review."""
        _require_context(context)
        if (
            project_id != self._review["project_id"]
            or review_routing_ref != self._review["review_routing_ref"]
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_AVAILABLE,
                "No matching review is currently available.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "leased_to_actor"
        self._review["actor_facing_state"] = "leased_to_actor"
        self._review["context_resource"] = (
            f"workstream://reviews/{self._review['review_ref']}/context"
        )
        return {
            "operation": "claim_review",
            "outcome": "leased_to_actor",
            "review_ref": self._review["review_ref"],
            "request_id": request_id,
            "next_resource": self._review["context_resource"],
        }

    async def release_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Release the deterministic leased review."""
        _require_context(context)
        if review_ref != self._review["review_ref"] or self._review["state"] != "leased_to_actor":
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "The review is not leased to the current actor.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "available_to_claim"
        self._review["actor_facing_state"] = "available_to_claim"
        self._review["context_resource"] = None
        return {
            "operation": "release_review",
            "outcome": "released",
            "review_ref": review_ref,
            "request_id": request_id,
        }

    async def submit_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        decision: str,
        findings: list[dict[str, Any]],
        request_id: str,
    ) -> dict[str, Any]:
        """Record a deterministic review decision outcome."""
        _require_context(context)
        if decision == "needs_revision" and not findings:
            raise WorkstreamMCPError(
                MCPErrorCode.FINDINGS_REQUIRED,
                "needs_revision requires actionable findings.",
                correlation_id=context.correlation_id,
            )
        if review_ref != self._review["review_ref"] or self._review["state"] != "leased_to_actor":
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "The review is not leased to the current actor.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "none_available"
        self._review["actor_facing_state"] = "completed"
        return {
            "operation": "submit_review",
            "outcome": decision,
            "review_ref": review_ref,
            "request_id": request_id,
            "findings_count": len(findings),
        }


def _require_context(context: RequestContext) -> None:
    """Fail closed if a test/local caller omits identity context."""
    if not context.bearer_token:
        raise WorkstreamMCPError(
            MCPErrorCode.AUTHENTICATION_REQUIRED,
            "Contributor identity is required.",
            correlation_id=context.correlation_id,
        )


def _now() -> str:
    """Return a stable UTC timestamp string for scenario records."""
    return datetime.fromisoformat(SCENARIO_TIMESTAMP).astimezone(UTC).isoformat()
