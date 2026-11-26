"""Exact HTTP command metadata for the single raw-ZIP submission mutation."""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.api_controls import StructuredHTTPException
from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
from app.modules.artifacts.api.submission_intake import (
    MAXIMUM_INGRESS_CHUNK_BYTES, MAXIMUM_SUBMISSION_FEEDBACK_BYTES, SubmissionIntakeMetadata,
)


@dataclass(frozen=True, slots=True)
class SubmissionIntakeHeaders:
    metadata: SubmissionIntakeMetadata
    idempotency_key: UUID
    declared_raw_bytes: int | None


_PACKET_HEADERS = (
    "x-task-assignment-id", "idempotency-key", "x-submission-feedback",
    "content-type", "content-encoding", "content-length", "transfer-encoding",
)


def _reject(code: str, status_code: int, message: str) -> NoReturn:
    raise StructuredHTTPException(status_code=status_code, detail=message,
                                  error_code=code, error_message=message)


def submission_intake_headers(request: Request, task_id: UUID) -> SubmissionIntakeHeaders:
    """Parse once without reading, trimming or otherwise rewriting packet bytes."""
    # Count and select from the same case-insensitive raw collection. ASGI
    # servers normally lowercase names, but an intermediary must not be able
    # to hide a second selector from the ambiguity check by preserving case.
    headers = Headers(raw=[(name.lower(), value) for name, value in request.scope["headers"]])
    for name in _PACKET_HEADERS:
        if len(headers.getlist(name)) > 1:
            _reject("submission_packet_invalid", 422, "Submission headers are ambiguous")
    if any(len(headers.getlist(name)) != 1 for name in ("idempotency-key", "x-task-assignment-id")):
        _reject("submission_packet_invalid", 422, "Submission selectors are required")
    if (headers.get("content-type", "").strip().lower() != "application/zip"
            or headers.get("content-encoding", "identity").strip().lower() != "identity"):
        _reject("submission_media_type_unsupported", 415, "Submission requires an unencoded ZIP body")
    length, transfer = headers.get("content-length"), headers.get("transfer-encoding")
    if transfer is not None and (length is not None or transfer.strip().lower() != "chunked"):
        _reject("submission_packet_invalid", 422, "Submission framing is invalid")
    declared = None
    if length is not None:
        if not length or len(length) > 20 or any(char not in "0123456789" for char in length):
            _reject("submission_packet_invalid", 422, "Submission length is invalid")
        declared = int(length)
        if declared > MAXIMUM_SUBMISSION_ZIP_BYTES:
            _reject("submission_archive_limit_exceeded", 413, "Submission ZIP exceeds the raw limit")
        if declared == 0:
            _reject("submission_packet_invalid", 422, "Submission ZIP must be nonempty")
    try:
        assignment_id = UUID(headers["x-task-assignment-id"])
        key = UUID(headers["idempotency-key"])
    except ValueError:
        _reject("submission_packet_invalid", 422, "Task assignment and idempotency key must be UUIDs")
    try:
        metadata = SubmissionIntakeMetadata(
            task_id=task_id, assignment_id=assignment_id, feedback=headers.get("x-submission-feedback"),
        )
    except ValueError:
        _reject("submission_packet_invalid", 422,
                f"Feedback accepts up to {MAXIMUM_SUBMISSION_FEEDBACK_BYTES} printable ASCII bytes "
                "without leading or trailing whitespace")
    return SubmissionIntakeHeaders(metadata, key, declared)


async def submission_intake_body(request: Request) -> AsyncIterator[bytes]:
    """Adapt arbitrary ASGI frames to bounded owner chunks without reading ahead."""
    async for frame in request.stream():
        for start in range(0, len(frame), MAXIMUM_INGRESS_CHUNK_BYTES):
            yield frame[start:start + MAXIMUM_INGRESS_CHUNK_BYTES]
