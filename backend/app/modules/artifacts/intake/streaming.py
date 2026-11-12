"""Bounded foreground ZIP receipt without an API scratch file.

The owner persists operation/intent before initiation and the returned upload
handle before calling this function. The result is EOF/completion intent: it
must be committed under the live fence before calling complete_source_upload.
Errors leave physical ownership with that operation; this helper neither frees
capacity nor invents a successful abort after cancellation.
"""

from collections.abc import AsyncIterator
import asyncio
from datetime import UTC, datetime
from dataclasses import dataclass
import math
import hashlib

from app.interfaces.artifacts import (
    ArtifactInputMismatchError,
    ArtifactLimitExceededError,
    ArtifactProviderOperationEvidence,
    ArtifactStore,
    ArtifactStoreUnavailableError,
)
from app.modules.artifacts.api.submission_intake import (
    SubmissionSourceCompletion,
    SubmissionSourceUpload,
)


MAXIMUM_INGRESS_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class RawSubmissionIdentity:
    raw_sha256: str
    raw_byte_count: int


class _IngressReceipt:
    def __init__(self) -> None:
        self.digest = hashlib.sha256()
        self.count = 0

    def identity(self) -> RawSubmissionIdentity:
        return RawSubmissionIdentity("sha256:" + self.digest.hexdigest(), self.count)


def _require_deadline(deadline_at: datetime) -> None:
    if datetime.now(UTC) >= deadline_at:
        raise TimeoutError("submission total deadline expired")


async def _bounded_chunks(
    chunks: AsyncIterator[bytes], receipt: _IngressReceipt, *, maximum_raw_bytes: int,
    declared_raw_bytes: int | None, idle_timeout_seconds: float, deadline_at: datetime,
) -> AsyncIterator[bytes]:
    """The same framing, size and EOF rules govern upload and discard replay."""
    loop = asyncio.get_running_loop()
    while True:
        _require_deadline(deadline_at)
        started = loop.time()
        ended = False
        try:
            async with asyncio.timeout(idle_timeout_seconds):
                chunk = await anext(chunks)
        except StopAsyncIteration:
            ended = True
        # A buffered or blocking iterator may never yield control to the timeout
        # callback. Check elapsed time even when the read reports EOF.
        if loop.time() - started >= idle_timeout_seconds:
            raise TimeoutError("submission ingress idle deadline expired")
        _require_deadline(deadline_at)
        if ended:
            break
        if type(chunk) is not bytes:
            raise ArtifactInputMismatchError("submission ingress returned invalid bytes")
        if len(chunk) > MAXIMUM_INGRESS_CHUNK_BYTES:
            raise ArtifactLimitExceededError("submission ingress chunk exceeds transport bound")
        receipt.count += len(chunk)
        if receipt.count > maximum_raw_bytes:
            raise ArtifactLimitExceededError("submission ZIP exceeds raw byte limit")
        if declared_raw_bytes is not None and receipt.count > declared_raw_bytes:
            raise ArtifactInputMismatchError("submission exceeds declared byte count")
        receipt.digest.update(chunk)
        yield chunk
    if receipt.count == 0 or (declared_raw_bytes is not None and receipt.count != declared_raw_bytes):
        raise ArtifactInputMismatchError("submission EOF violates declared or nonempty size")


async def hash_submission_replay(
    chunks: AsyncIterator[bytes], *, maximum_raw_bytes: int, declared_raw_bytes: int | None,
    idle_timeout_seconds: float, deadline_at: datetime,
) -> RawSubmissionIdentity:
    """Hash/count a retry into a discard sink with no source/provider capability."""
    from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
    if (type(maximum_raw_bytes) is not int or not 1 <= maximum_raw_bytes <= MAXIMUM_SUBMISSION_ZIP_BYTES
            or (declared_raw_bytes is not None and (type(declared_raw_bytes) is not int
                or not 1 <= declared_raw_bytes <= maximum_raw_bytes))
            or isinstance(idle_timeout_seconds, bool) or not isinstance(idle_timeout_seconds, (int, float))
            or not math.isfinite(idle_timeout_seconds) or idle_timeout_seconds <= 0
            or not isinstance(deadline_at, datetime) or deadline_at.utcoffset() is None):
        raise ValueError("submission replay limits are invalid")
    remaining = (deadline_at - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise ArtifactStoreUnavailableError("submission replay deadline expired")
    receipt = _IngressReceipt()
    try:
        async with asyncio.timeout(remaining):
            async for _chunk in _bounded_chunks(chunks, receipt, maximum_raw_bytes=maximum_raw_bytes,
                    declared_raw_bytes=declared_raw_bytes, idle_timeout_seconds=idle_timeout_seconds,
                    deadline_at=deadline_at):
                pass
            _require_deadline(deadline_at)
    except TimeoutError:
        raise ArtifactStoreUnavailableError("submission replay deadline expired") from None
    return receipt.identity()


async def receive_submission_source(
    store: ArtifactStore, upload: SubmissionSourceUpload, chunks: AsyncIterator[bytes], *,
    operation_evidence: ArtifactProviderOperationEvidence | None = None,
) -> SubmissionSourceCompletion:
    """Count/hash raw bytes and await every part before reading more input.

    Application-owned memory is at most two configured parts (assembly plus
    immutable in-flight bytes) and one ingress chunk. SDK/TLS overhead is separate.
    Parts are sequential, with no application retry queue or whole-file spool.
    The transport must provide chunks within its own published 1 MiB bound.
    """
    upload = SubmissionSourceUpload.model_validate(upload)
    remaining = (upload.intent.upload_deadline_at - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise ArtifactStoreUnavailableError("submission upload deadline expired")
    try:
        async with asyncio.timeout(remaining):
            return await _receive_parts(store, upload, chunks, operation_evidence)
    except TimeoutError:
        raise ArtifactStoreUnavailableError("submission upload deadline expired") from None


async def _receive_parts(
    store: ArtifactStore, upload: SubmissionSourceUpload, chunks: AsyncIterator[bytes],
    operation_evidence: ArtifactProviderOperationEvidence | None,
) -> SubmissionSourceCompletion:
    """Receive sequential parts inside the caller's immutable total deadline."""
    intent = upload.intent
    evidence = operation_evidence or ArtifactProviderOperationEvidence()
    receipt = _IngressReceipt()
    pending = bytearray()
    parts = []
    async for chunk in _bounded_chunks(chunks, receipt, maximum_raw_bytes=intent.maximum_raw_bytes,
            declared_raw_bytes=intent.declared_raw_bytes, idle_timeout_seconds=intent.idle_timeout_seconds,
            deadline_at=intent.upload_deadline_at):
        view = memoryview(chunk)
        while view:
            amount = min(intent.part_bytes - len(pending), len(view))
            pending.extend(view[:amount])
            view = view[amount:]
            if len(pending) == intent.part_bytes:
                _require_deadline(intent.upload_deadline_at)
                parts.append(await store.upload_source_part(
                    upload, len(parts) + 1, bytes(pending), operation_evidence=evidence,
                ))
                pending.clear()
    if pending:
        _require_deadline(intent.upload_deadline_at)
        parts.append(await store.upload_source_part(
            upload, len(parts) + 1, bytes(pending), operation_evidence=evidence,
        ))
    _require_deadline(intent.upload_deadline_at)
    return SubmissionSourceCompletion(
        upload=upload, parts=tuple(parts), raw_sha256=receipt.identity().raw_sha256, raw_byte_count=receipt.count,
    )
