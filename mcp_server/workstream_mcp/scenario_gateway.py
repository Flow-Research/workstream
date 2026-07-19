"""Temporary deterministic gateway for MCP conformance tests.

This gateway is intentionally non-authoritative and must be injected by a test.
It is not selected from runtime configuration and must never serve production
MCP traffic.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from workstream_mcp.auth import RequestContext
from workstream_mcp.errors import MCPErrorCode, WorkstreamMCPError

SCENARIO_TIMESTAMP = "2026-07-10T00:00:00+00:00"
SCENARIO_SUBMITTER_POLICY_REF = "scenario-submitter-policy-1:v1"
SCENARIO_REVIEWER_POLICY_REF = "scenario-reviewer-policy-1:v1"
SCENARIO_SUBMITTER_COMPENSATION_SUMMARY = (
    "The submitter contribution rule is explicitly unpaid."
)
SCENARIO_REVIEWER_COMPENSATION_SUMMARY = (
    "The reviewer contribution rule is explicitly unpaid."
)


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
                "granted_capabilities": ["submitter", "reviewer"],
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
                "available_from": SCENARIO_TIMESTAMP,
                "claim_by": "2026-07-17T00:00:00+00:00",
                "context_resource": "workstream://tasks/scenario-task-1/context",
                "status_resource": "workstream://tasks/scenario-task-1/status",
            }
        ]
        self._contributions: list[dict[str, Any]] = []
        self._contribution_owners: dict[str, str] = {}
        self._contribution_count = 0
        self._review = {
            "state": "none_available",
            "review_routing_ref": "scenario-review-route-1",
            "review_ref": "scenario-review-1",
            "project_id": "scenario-project-1",
            "task_summary": "Scenario review task",
            "actor_facing_state": "none_available",
            "context_resource": None,
            "lease_started_at": None,
            "lease_expires_at": None,
        }
        self._review_task_id = "scenario-task-1"
        self._revision_findings: dict[str, list[dict[str, Any]]] = {}
        self._revision_submissions: dict[str, dict[str, Any]] = {}
        self._latest_review_outcomes: dict[str, dict[str, Any]] = {}
        self._submission_count = 0
        self._submissions: list[dict[str, Any]] = []
        self._task_owner: str | None = None
        self._review_owner: str | None = None
        self._replays: dict[
            tuple[str, str, str], tuple[tuple[Any, ...], dict[str, Any]]
        ] = {}

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
        actor_key = _actor_key(context)
        records = [
            deepcopy(record)
            for record in self._contributions
            if self._contribution_owners[record["contribution_ref"]] == actor_key
        ]
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
        self._require_task_visibility(task, context)
        return {
            "source": "temporary_scenario_gateway",
            "task": deepcopy(task),
            "work_context": {
                "task": {"id": task_id, "instructions": "Scenario instructions."},
                "lifecycle": {"status": task["actor_facing_state"]},
            },
            "locked_context": {
                "guide_ref": "scenario-guide-1",
                "guide_version": 1,
                "policy_ref": "scenario-policy-1",
                "policy_version": 1,
                "locked_at": SCENARIO_TIMESTAMP,
            },
            "expected_output": "A complete scenario result package.",
            "acceptance_criteria": ["The package is complete and checker evidence passes."],
            "artifact_requirements": ["result.txt with a declared SHA-256 hash"],
            "evidence_requirements": ["pre-submit checker result"],
            "pre_submit_checks": ["scenario-checker-1"],
            "review_criteria": ["Correctness", "Evidence completeness"],
            "compensation": {
                "contribution_type": "accepted_submission",
                "compensation_mode": "unpaid",
                "policy_ref": SCENARIO_SUBMITTER_POLICY_REF,
                "summary": SCENARIO_SUBMITTER_COMPENSATION_SUMMARY,
            },
            "cycle": {"number": 1, "maximum_revisions": 2},
            "revision": {
                "required": task["actor_facing_state"] == "needs_revision",
                "findings": deepcopy(self._revision_findings.get(task_id, [])),
                **deepcopy(self._revision_submissions.get(task_id, {})),
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
        self._require_task_visibility(task, context)
        task_submissions = [
            submission for submission in self._submissions if submission["task_id"] == task_id
        ]
        return {
            "source": "temporary_scenario_gateway",
            "task_id": task_id,
            "task": deepcopy(task),
            "actor_facing_state": task["actor_facing_state"],
            "latest_submission": deepcopy(task_submissions[-1]) if task_submissions else None,
            "checker_runs": [],
            "latest_check_outcome": None,
            "latest_review_outcome": deepcopy(self._latest_review_outcomes.get(task_id)),
            "action_required": (
                "read_task_context"
                if task["actor_facing_state"] == "needs_revision"
                else None
            ),
            "final_outcome": (
                task["actor_facing_state"]
                if task["actor_facing_state"] in {"accepted", "rejected"}
                else None
            ),
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
        self._task_owner = _actor_key(context)
        return self._store_replay(
            "claim_task",
            request_id,
            (task_id,),
            {"task": deepcopy(task), "assignment": {"id": "scenario-assignment-1"}},
            context,
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
        if (
            task["actor_facing_state"] != "in_progress"
            or self._task_owner != _actor_key(context)
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.TASK_NOT_RELEASABLE,
                "The task is not currently releasable.",
                correlation_id=context.correlation_id,
            )
        task["actor_facing_state"] = "available"
        task["may_claim"] = True
        self._task_owner = None
        return self._store_replay(
            "release_task",
            request_id,
            (task_id, reason),
            {"task": deepcopy(task)},
            context,
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
        task = self._task(task_id, context)
        if self._task_owner != _actor_key(context) or task["actor_facing_state"] not in {
            "in_progress",
            "needs_revision",
        }:
            raise WorkstreamMCPError(
                MCPErrorCode.SUBMISSION_NOT_ALLOWED,
                "The task is not ready for submission.",
                correlation_id=context.correlation_id,
            )
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
        input_key = (task_id, _canonical_json(submission))
        replay = self._replay("submit_task", request_id, input_key, context)
        if replay is not None:
            return replay
        task = self._task(task_id, context)
        if (
            self._task_owner != _actor_key(context)
            or task["actor_facing_state"] not in {"in_progress", "needs_revision"}
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.SUBMISSION_NOT_ALLOWED,
                "The task is not ready for submission.",
                correlation_id=context.correlation_id,
            )
        self._submission_count += 1
        was_revision = task["actor_facing_state"] == "needs_revision"
        task["actor_facing_state"] = "review_pending"
        if was_revision:
            self._revision_findings.pop(task_id, None)
            self._revision_submissions.pop(task_id, None)
        next_review_number = self._submission_count
        self._review.update(
            {
                "state": "available_to_claim",
                "review_routing_ref": f"scenario-review-route-{next_review_number}",
                "review_ref": f"scenario-review-{next_review_number}",
                "actor_facing_state": "available_to_claim",
                "context_resource": None,
                "lease_started_at": None,
                "lease_expires_at": None,
            }
        )
        self._review_owner = None
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
            context,
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
        if self._task_owner == _actor_key(context):
            return {
                "source": "temporary_scenario_gateway",
                "project_id": project_id,
                "state": "none_available",
            }
        if self._review["state"] == "none_available":
            return {
                "source": "temporary_scenario_gateway",
                "project_id": project_id,
                "state": "none_available",
            }
        if self._review["state"] == "leased_to_actor" and self._review_owner != _actor_key(
            context
        ):
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
        if (
            review_ref != self._review["review_ref"]
            or self._review["state"] != "leased_to_actor"
            or self._review_owner != _actor_key(context)
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "Review context is available only for a review leased to the actor.",
                correlation_id=context.correlation_id,
            )
        task_submissions = [
            submission
            for submission in self._submissions
            if submission["task_id"] == self._review_task_id
        ]
        if not task_submissions:
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_AVAILABLE,
                "The submission for this review is not available.",
                correlation_id=context.correlation_id,
            )
        reviewed_submission = task_submissions[-1]
        return {
            "source": "temporary_scenario_gateway",
            "review_ref": review_ref,
            "project_id": self._review["project_id"],
            "task": {"title": "Scenario review task"},
            "task_context": {
                "task_id": "scenario-task-1",
                "guide_ref": "scenario-guide-1:v1",
                "policy_ref": "scenario-policy-1:v1",
                "expected_output": "A complete scenario result package.",
                "acceptance_criteria": ["The package is complete and evidence passes."],
            },
            "submission": {
                "submission_id": reviewed_submission["id"],
                "version": reviewed_submission["version"],
                "summary": "Scenario candidate submission.",
                "artifact_manifest": [
                    {"artifact": "result.txt", "hash": "sha256:def"}
                ],
                "evidence_items": [],
            },
            "checker_results": {"status": "passed", "results": []},
            "revision_chain": [],
            "review_criteria": ["Correctness", "Evidence completeness"],
            "compensation": {
                "contribution_type": "completed_review",
                "compensation_mode": "unpaid",
                "policy_ref": SCENARIO_REVIEWER_POLICY_REF,
                "summary": SCENARIO_REVIEWER_COMPENSATION_SUMMARY,
            },
            "lease": {
                "started_at": self._review["lease_started_at"],
                "expires_at": self._review["lease_expires_at"],
            },
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "findings_required_for": ["needs_revision"],
            "reason_required_for": ["reject"],
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
        input_key = (project_id, review_routing_ref)
        replay = self._replay("claim_review", request_id, input_key, context)
        if replay is not None:
            return replay
        if (
            project_id != self._review["project_id"]
            or review_routing_ref != self._review["review_routing_ref"]
            or self._task_owner == _actor_key(context)
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_AVAILABLE,
                "No matching review is currently available.",
                correlation_id=context.correlation_id,
            )
        if self._review["state"] != "available_to_claim":
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_AVAILABLE,
                "No matching review is currently available.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "leased_to_actor"
        self._review["actor_facing_state"] = "leased_to_actor"
        self._review_owner = _actor_key(context)
        self._review["lease_started_at"] = SCENARIO_TIMESTAMP
        self._review["lease_expires_at"] = "2026-07-10T00:30:00+00:00"
        self._review["context_resource"] = (
            f"workstream://reviews/{self._review['review_ref']}/context"
        )
        return self._store_replay(
            "claim_review",
            request_id,
            input_key,
            {
                "operation": "claim_review",
                "outcome": "leased_to_actor",
                "review_ref": self._review["review_ref"],
                "request_id": request_id,
                "next_resource": self._review["context_resource"],
                "lease_expires_at": self._review["lease_expires_at"],
            },
            context,
        )

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
        if (
            review_ref != self._review["review_ref"]
            or self._review["state"] != "leased_to_actor"
            or self._review_owner != _actor_key(context)
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "The review is not leased to the current actor.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "available_to_claim"
        self._review["actor_facing_state"] = "available_to_claim"
        self._review["context_resource"] = None
        self._review["lease_started_at"] = None
        self._review["lease_expires_at"] = None
        self._review_owner = None
        return self._store_replay(
            "release_review",
            request_id,
            (review_ref,),
            {
                "operation": "release_review",
                "outcome": "released",
                "review_ref": review_ref,
                "request_id": request_id,
            },
            context,
        )

    async def submit_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        decision: str,
        findings: list[dict[str, Any]],
        request_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a deterministic review decision outcome."""
        _require_context(context)
        if decision == "needs_revision" and not any(
            finding.get("finding_kind") == "blocking" for finding in findings
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.FINDINGS_REQUIRED,
                "needs_revision requires at least one blocking finding.",
                correlation_id=context.correlation_id,
            )
        if decision == "accept" and any(
            finding.get("finding_kind") == "blocking" for finding in findings
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.FINDINGS_REQUIRED,
                "accept permits advisory findings only.",
                correlation_id=context.correlation_id,
            )
        if decision == "reject" and not reason:
            raise WorkstreamMCPError(
                MCPErrorCode.FINDINGS_REQUIRED,
                "reject requires a bounded human reason.",
                correlation_id=context.correlation_id,
            )
        input_key = (review_ref, decision, _canonical_json(findings), reason)
        replay = self._replay("submit_review", request_id, input_key, context)
        if replay is not None:
            return replay
        if (
            review_ref != self._review["review_ref"]
            or self._review["state"] != "leased_to_actor"
            or self._review_owner != _actor_key(context)
            or self._task_owner is None
            or self._task_owner == _actor_key(context)
        ):
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
                "The review is not leased to the current actor.",
                correlation_id=context.correlation_id,
            )
        self._review["state"] = "none_available"
        self._review["actor_facing_state"] = "completed"
        task = self._task(self._review_task_id, context)
        task_submissions = [
            submission
            for submission in self._submissions
            if submission["task_id"] == self._review_task_id
        ]
        if not task_submissions:
            raise WorkstreamMCPError(
                MCPErrorCode.REVIEW_NOT_AVAILABLE,
                "The submission for this review is not available.",
                correlation_id=context.correlation_id,
            )
        reviewed_submission = task_submissions[-1]
        persisted_findings = deepcopy(findings)
        self._latest_review_outcomes[self._review_task_id] = {
            "decision": decision,
            "review_ref": review_ref,
            "submission_ref": reviewed_submission["id"],
            "submission_version": reviewed_submission["version"],
            "findings": persisted_findings,
            "reason": reason,
        }
        self._append_contribution(
            owner_key=_actor_key(context),
            contribution_type="completed_review",
            source_ref=review_ref,
            outcome=decision,
            policy_ref=SCENARIO_REVIEWER_POLICY_REF,
            summary=SCENARIO_REVIEWER_COMPENSATION_SUMMARY,
        )
        if decision == "needs_revision":
            task["actor_facing_state"] = "needs_revision"
            task["may_claim"] = False
            self._revision_findings[self._review_task_id] = persisted_findings
            self._revision_submissions[self._review_task_id] = {
                "submission_ref": reviewed_submission["id"],
                "submission_version": reviewed_submission["version"],
            }
        elif decision == "accept":
            task["actor_facing_state"] = "accepted"
            task["may_claim"] = False
            self._append_contribution(
                owner_key=self._task_owner,
                contribution_type="accepted_submission",
                source_ref=self._review_task_id,
                outcome="accepted",
                policy_ref=SCENARIO_SUBMITTER_POLICY_REF,
                summary=SCENARIO_SUBMITTER_COMPENSATION_SUMMARY,
            )
        else:
            task["actor_facing_state"] = "rejected"
            task["may_claim"] = False
        return self._store_replay(
            "submit_review",
            request_id,
            input_key,
            {
                "operation": "submit_review",
                "outcome": decision,
                "review_ref": review_ref,
                "request_id": request_id,
                "findings_count": len(findings),
            },
            context,
        )

    def _append_contribution(
        self,
        *,
        owner_key: str,
        contribution_type: str,
        source_ref: str,
        outcome: str,
        policy_ref: str,
        summary: str,
    ) -> None:
        """Append one actor-owned immutable contribution fixture record."""
        self._contribution_count += 1
        contribution_ref = f"scenario-contribution-{self._contribution_count}"
        self._contributions.append(
            {
                "contribution_ref": contribution_ref,
                "project_id": "scenario-project-1",
                "project_name": "Scenario Project",
                "contribution_type": contribution_type,
                "source_ref": source_ref,
                "outcome": outcome,
                "recorded_at": _now(),
                "compensation_status": "unpaid",
                "compensation_policy_ref": policy_ref,
                "compensation_summary": summary,
            }
        )
        self._contribution_owners[contribution_ref] = owner_key

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

    def _require_task_visibility(
        self,
        task: dict[str, Any],
        context: RequestContext,
    ) -> None:
        """Hide an actor-owned task context from every other test actor."""
        if (
            self._task_owner is not None
            and self._task_owner != _actor_key(context)
            and task["actor_facing_state"] != "available"
        ):
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
        existing = self._replays.get((_actor_key(context), operation, request_id))
        if existing is None:
            return None
        prior_input, result = existing
        if prior_input != input_key:
            raise WorkstreamMCPError(
                MCPErrorCode.IDEMPOTENCY_CONFLICT,
                "The request ID was already used for different input.",
                correlation_id=context.correlation_id,
            )
        replayed = deepcopy(result)
        replayed["idempotent_replay"] = True
        return replayed

    def _store_replay(
        self,
        operation: str,
        request_id: str,
        input_key: tuple[Any, ...],
        result: dict[str, Any],
        context: RequestContext,
    ) -> dict[str, Any]:
        """Store a deterministic temporary result for a repeated test request."""
        self._replays[(_actor_key(context), operation, request_id)] = (
            input_key,
            deepcopy(result),
        )
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


def _actor_key(context: RequestContext) -> str:
    """Return a process-local actor key without storing raw bearer material."""
    return hashlib.sha256(context.bearer_token.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    """Canonicalize temporary logical input for deterministic replay checks."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
