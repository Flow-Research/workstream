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


_BACKEND_ERROR_CODES: dict[str, MCPErrorCode] = {
    "idempotency_mismatch": MCPErrorCode.IDEMPOTENCY_CONFLICT,
    "pre_submission_checker_failed": MCPErrorCode.PRE_SUBMIT_CHECK_FAILED,
    "pre_submit_check_failed": MCPErrorCode.PRE_SUBMIT_CHECK_FAILED,
    "submission_version_unchanged": MCPErrorCode.SUBMISSION_UNCHANGED,
    "task_assignment_conflict": MCPErrorCode.TASK_NOT_CLAIMABLE,
    "task_not_claimable": MCPErrorCode.TASK_NOT_CLAIMABLE,
    "task_not_releasable": MCPErrorCode.TASK_NOT_RELEASABLE,
    "review_not_available": MCPErrorCode.REVIEW_NOT_AVAILABLE,
    "review_not_leased_to_actor": MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR,
    "review_lease_expired": MCPErrorCode.REVIEW_LEASE_EXPIRED,
    "findings_required": MCPErrorCode.FINDINGS_REQUIRED,
}


def map_http_error_response(
    status_code: int,
    payload: Any,
    *,
    correlation_id: str | None = None,
) -> WorkstreamMCPError:
    """Preserve safe Workstream domain classifications when the API provides one."""
    backend_code = _extract_error_code(payload)
    mcp_code = _BACKEND_ERROR_CODES.get(backend_code or "")
    if mcp_code is not None:
        return WorkstreamMCPError(
            mcp_code,
            "Workstream rejected the requested operation.",
            correlation_id=correlation_id,
        )
    return map_http_status(status_code, correlation_id=correlation_id)


def unexpected_server_error(*, correlation_id: str | None = None) -> WorkstreamMCPError:
    """Return a secret-safe envelope for an unexpected adapter failure."""
    return WorkstreamMCPError(
        MCPErrorCode.UNEXPECTED_SERVER_ERROR,
        "The MCP server could not complete the request.",
        retryable=False,
        correlation_id=correlation_id,
    )


def _extract_error_code(payload: Any) -> str | None:
    """Read a stable code from the canonical Workstream error envelope."""
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    if isinstance(payload.get("code"), str):
        return payload["code"]
    return None
