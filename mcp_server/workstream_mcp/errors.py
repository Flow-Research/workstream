"""Safe MCP error contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class MCPErrorCode(StrEnum):
    """Stable WS-MCP-001 error categories."""

    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_TOKEN = "invalid_token"
    PROJECT_ACCESS_DENIED = "project_access_denied"
    CAPABILITY_NOT_GRANTED = "capability_not_granted"
    RESOURCE_NOT_FOUND_OR_NOT_VISIBLE = "resource_not_found_or_not_visible"
    TASK_NOT_CLAIMABLE = "task_not_claimable"
    TASK_NOT_RELEASABLE = "task_not_releasable"
    PRE_SUBMIT_CHECK_FAILED = "pre_submit_check_failed"
    SUBMISSION_NOT_ALLOWED = "submission_not_allowed"
    SUBMISSION_UNCHANGED = "submission_unchanged"
    REVIEW_NOT_AVAILABLE = "review_not_available"
    REVIEW_NOT_LEASED_TO_ACTOR = "review_not_leased_to_actor"
    REVIEW_LEASE_EXPIRED = "review_lease_expired"
    FINDINGS_REQUIRED = "findings_required"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    WORKSTREAM_TEMPORARILY_UNAVAILABLE = "workstream_temporarily_unavailable"
    UNEXPECTED_SERVER_ERROR = "unexpected_server_error"


class WorkstreamMCPError(Exception):
    """Contributor-safe MCP error with no secret-bearing fields."""

    def __init__(
        self,
        code: MCPErrorCode,
        message: str,
        *,
        retryable: bool = False,
        correlation_id: str | None = None,
        next_resource: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Create one safe MCP error."""
        self.code = code
        self.message = message
        self.retryable = retryable
        self.correlation_id = correlation_id
        self.next_resource = next_resource
        self.details = details or {}
        super().__init__(code.value)

    def to_result(self) -> dict[str, Any]:
        """Return a structured error result suitable for MCP responses."""
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "retryable": self.retryable,
                "correlation_id": self.correlation_id,
                "next_resource": self.next_resource,
                "details": self.details,
            }
        }


def map_http_status(status_code: int, *, correlation_id: str | None = None) -> WorkstreamMCPError:
    """Map a Workstream HTTP status to a safe MCP error."""
    if status_code == 401:
        return WorkstreamMCPError(
            MCPErrorCode.INVALID_TOKEN,
            "Authentication failed.",
            correlation_id=correlation_id,
        )
    if status_code == 403:
        return WorkstreamMCPError(
            MCPErrorCode.CAPABILITY_NOT_GRANTED,
            "The actor is not authorized for this Workstream operation.",
            correlation_id=correlation_id,
        )
    if status_code == 404:
        return WorkstreamMCPError(
            MCPErrorCode.RESOURCE_NOT_FOUND_OR_NOT_VISIBLE,
            "The requested Workstream resource was not found or is not visible.",
            correlation_id=correlation_id,
        )
    if status_code in {409, 412}:
        return WorkstreamMCPError(
            MCPErrorCode.IDEMPOTENCY_CONFLICT,
            "The request conflicts with current Workstream state.",
            correlation_id=correlation_id,
        )
    if status_code in {422, 400}:
        return WorkstreamMCPError(
            MCPErrorCode.SUBMISSION_NOT_ALLOWED,
            "Workstream rejected the submitted payload.",
            correlation_id=correlation_id,
        )
    if status_code in {429, 500, 502, 503, 504}:
        return WorkstreamMCPError(
            MCPErrorCode.WORKSTREAM_TEMPORARILY_UNAVAILABLE,
            "Workstream is temporarily unavailable.",
            retryable=True,
            correlation_id=correlation_id,
        )
    return WorkstreamMCPError(
        MCPErrorCode.UNEXPECTED_SERVER_ERROR,
        "Unexpected Workstream response.",
        correlation_id=correlation_id,
    )
