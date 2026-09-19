from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mcp.types import CallToolResult, TextContent


@dataclass(frozen=True, slots=True)
class SafeFailure:
    error: str
    status: int | None = None
    code: str | None = None
    correlation_id: str | None = None
    retryable: bool = False

    def payload(self) -> dict[str, Any]:
        value: dict[str, Any] = {"error": self.error, "retryable": self.retryable}
        if self.status is not None:
            value["status"] = self.status
        if self.code is not None:
            value["code"] = self.code
        if self.correlation_id is not None:
            value["correlation_id"] = self.correlation_id
        return value

    def result(self) -> CallToolResult:
        payload = self.payload()
        return CallToolResult(
            is_error=True,
            content=[TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))],
            structured_content=payload,
        )


def adapter_failure(error: str, *, status: int | None = None) -> CallToolResult:
    return SafeFailure(error=error, status=status).result()
