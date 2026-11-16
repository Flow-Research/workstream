"""Exact HTTP command metadata for the single raw-ZIP submission mutation."""
from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.api_controls import StructuredHTTPException
from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata


@dataclass(frozen=True, slots=True)
class SubmissionIntakeHeaders:
    metadata: SubmissionIntakeMetadata
    idempotency_key: UUID
    declared_raw_bytes: int | None


_PACKET_HEADERS = (
    "x-task-assignment-id", "idempotency-key", "x-submission-summary",
    "x-contributor-attestation", "x-predecessor-submission-id",
    "x-revision-preparation-id", "x-revision-preparation-sha256",
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
        predecessor = headers.get("x-predecessor-submission-id")
        revision = headers.get("x-revision-preparation-id")
        metadata = SubmissionIntakeMetadata(
            task_id=task_id, assignment_id=UUID(headers["x-task-assignment-id"]),
            predecessor_submission_id=UUID(predecessor) if predecessor is not None else None,
            summary=headers.get("x-submission-summary", ""),
            contributor_attestation=headers.get("x-contributor-attestation", ""),
            revision_preparation_id=UUID(revision) if revision is not None else None,
            revision_preparation_sha256=headers.get("x-revision-preparation-sha256"),
        )
        key = UUID(headers["idempotency-key"])
    except ValueError:
        _reject("submission_packet_invalid", 422, "Submission packet is invalid")
    return SubmissionIntakeHeaders(metadata, key, declared)
