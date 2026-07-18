"""Temporary deterministic gateway for MCP conformance tests.

This gateway is intentionally non-authoritative and must be injected by a test.
It is not selected from runtime configuration and must never serve production
MCP traffic.
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
        self._submission_count = 0
        self._submissions: list[dict[str, Any]] = []
        self._replays: dict[tuple[str, str], tuple[tuple[Any, ...], dict[str, Any]]] = {}

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

    async def get_task_context(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return deterministic locked task context for the test Submitter journey."""
        _require_context(context)
        task = self._task(task_id, context)
        return {
            "source": "temporary_scenario_gateway",
            "task": deepcopy(task),
            "work_context": {
                "task": {"id": task_id, "instructions": "Scenario instructions."},
                "lifecycle": {"status": task["actor_facing_state"]},
            },
            "submission_requirements": {
                "task_id": task_id,
                "required_packet_fields": [
                    "summary",
                    "package_hash",
                    "artifact_hash_manifest",
                    "worker_attestation",
                ],
            },
            "submissions": [
                deepcopy(submission)
                for submission in self._submissions
                if submission["task_id"] == task_id
            ],
        }

    async def get_task_status(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return deterministic actor-facing state without a read side effect."""
        _require_context(context)
        task = self._task(task_id, context)
        task_submissions = [
            submission for submission in self._submissions if submission["task_id"] == task_id
        ]
        return {
            "source": "temporary_scenario_gateway",
            "task_id": task_id,
            "task": deepcopy(task),
            "latest_submission": deepcopy(task_submissions[-1]) if task_submissions else None,
            "checker_runs": [],
            "next_resource": (
                f"workstream://tasks/{task_id}/context"
                if task["actor_facing_state"] == "needs_revision"
                else None
            ),
        }

    async def claim_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Claim and begin the temporary task in one test-only operation."""
        _require_context(context)
        replay = self._replay("claim_task", request_id, (task_id,), context)
        if replay is not None:
            return replay
        task = self._task(task_id, context)
        if task["actor_facing_state"] != "available":
            raise WorkstreamMCPError(
                MCPErrorCode.TASK_NOT_CLAIMABLE,
                "The task is not currently claimable.",
                correlation_id=context.correlation_id,
            )
        task["actor_facing_state"] = "in_progress"
        task["may_claim"] = False
        return self._store_replay(
            "claim_task",
            request_id,
            (task_id,),
            {"task": deepcopy(task), "assignment": {"id": "scenario-assignment-1"}},
        )

    async def release_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        request_id: str,
        reason: str | None,
    ) -> dict[str, Any]:
        """Release an in-progress temporary task back to availability."""
        _require_context(context)
        replay = self._replay("release_task", request_id, (task_id, reason), context)
        if replay is not None:
            return replay
        task = self._task(task_id, context)
        if task["actor_facing_state"] != "in_progress":
            raise WorkstreamMCPError(
                MCPErrorCode.TASK_NOT_RELEASABLE,
                "The task is not currently releasable.",
                correlation_id=context.correlation_id,
            )
        task["actor_facing_state"] = "available"
        task["may_claim"] = True
        return self._store_replay(
            "release_task", request_id, (task_id, reason), {"task": deepcopy(task)}
        )

    async def run_pre_submit_check(
        self,
        context: RequestContext,
        *,
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        """Return a deterministic non-mutating checker outcome."""
        _require_context(context)
        self._task(task_id, context)
        return {
            "task_id": task_id,
            "authoritative": False,
            "status": "passed",
            "eligible_to_submit": True,
            "results": [],
            "request_id": request_id,
        }

    async def submit_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        """Record one temporary immutable submission for conformance testing."""
        _require_context(context)
        input_key = (task_id, repr(sorted(submission.items())))
        replay = self._replay("submit_task", request_id, input_key, context)
        if replay is not None:
            return replay
        task = self._task(task_id, context)
        if task["actor_facing_state"] not in {"in_progress", "needs_revision"}:
            raise WorkstreamMCPError(
                MCPErrorCode.SUBMISSION_NOT_ALLOWED,
                "The task is not ready for submission.",
                correlation_id=context.correlation_id,
            )
        self._submission_count += 1
        task["actor_facing_state"] = "review_pending"
        result = {
            "id": f"scenario-submission-{self._submission_count}",
            "task_id": task_id,
            "version": self._submission_count,
            "status": "submitted",
        }
        self._submissions.append(deepcopy(result))
        return self._store_replay(
            "submit_task",
            request_id,
            input_key,
            result,
        )

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
        replay = self._replay(
            "claim_review", request_id, (project_id, review_routing_ref), context
        )
        if replay is not None:
            return replay
        if self._review["state"] != "available_to_claim":
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
        return self._store_replay("claim_review", request_id, (project_id, review_routing_ref), {
            "operation": "claim_review",
            "outcome": "leased_to_actor",
            "review_ref": self._review["review_ref"],
            "request_id": request_id,
            "next_resource": self._review["context_resource"],
        })

    async def release_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Release the deterministic leased review."""
        _require_context(context)
        replay = self._replay("release_review", request_id, (review_ref,), context)
        if replay is not None:
            return replay
        if review_ref != self._review["review_ref"] or self._review["state"] != "leased_to_actor":
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "The review is not leased to the current actor.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "available_to_claim"
        self._review["actor_facing_state"] = "available_to_claim"
        self._review["context_resource"] = None
        return self._store_replay("release_review", request_id, (review_ref,), {
            "operation": "release_review",
            "outcome": "released",
            "review_ref": review_ref,
            "request_id": request_id,
        })

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
        input_key = (review_ref, decision, repr(findings))
        replay = self._replay("submit_review", request_id, input_key, context)
        if replay is not None:
            return replay
        if review_ref != self._review["review_ref"] or self._review["state"] != "leased_to_actor":
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "The review is not leased to the current actor.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "none_available"
        self._review["actor_facing_state"] = "completed"
        return self._store_replay("submit_review", request_id, input_key, {
            "operation": "submit_review",
            "outcome": decision,
            "review_ref": review_ref,
            "request_id": request_id,
            "findings_count": len(findings),
        })

    def _task(self, task_id: str, context: RequestContext) -> dict[str, Any]:
        """Return the one scenario task or fail without revealing other data."""
        for task in self._tasks:
            if task["task_id"] == task_id:
                return task
        raise WorkstreamMCPError(
            MCPErrorCode.RESOURCE_NOT_FOUND_OR_NOT_VISIBLE,
            "The requested Workstream resource was not found or is not visible.",
            correlation_id=context.correlation_id,
        )

    def _replay(
        self,
        operation: str,
        request_id: str,
        input_key: tuple[Any, ...],
        context: RequestContext,
    ) -> dict[str, Any] | None:
        """Return a prior temporary result or reject conflicting retry input."""
        existing = self._replays.get((operation, request_id))
        if existing is None:
            return None
        prior_input, result = existing
        if prior_input != input_key:
            raise WorkstreamMCPError(
                MCPErrorCode.IDEMPOTENCY_CONFLICT,
                "The request ID was already used for different input.",
                correlation_id=context.correlation_id,
            )
        return deepcopy(result)

    def _store_replay(
        self,
        operation: str,
        request_id: str,
        input_key: tuple[Any, ...],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Store a deterministic temporary result for a repeated test request."""
        self._replays[(operation, request_id)] = (input_key, deepcopy(result))
        return result


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
