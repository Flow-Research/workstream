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
    digest = hashlib.sha256()
    count = 0
    pending = bytearray()
    parts = []
    while True:
        try:
            async with asyncio.timeout(intent.idle_timeout_seconds):
                chunk = await anext(chunks)
        except StopAsyncIteration:
            break
        if type(chunk) is not bytes:
            raise ArtifactInputMismatchError("submission ingress returned invalid bytes")
        if len(chunk) > MAXIMUM_INGRESS_CHUNK_BYTES:
            raise ArtifactLimitExceededError("submission ingress chunk exceeds transport bound")
        count += len(chunk)
        if count > intent.maximum_raw_bytes:
            raise ArtifactLimitExceededError("submission ZIP exceeds raw byte limit")
        if intent.declared_raw_bytes is not None and count > intent.declared_raw_bytes:
            raise ArtifactInputMismatchError("submission exceeds declared byte count")
        digest.update(chunk)
        view = memoryview(chunk)
        while view:
            amount = min(intent.part_bytes - len(pending), len(view))
            pending.extend(view[:amount])
            view = view[amount:]
            if len(pending) == intent.part_bytes:
                parts.append(await store.upload_source_part(
                    upload, len(parts) + 1, bytes(pending), operation_evidence=evidence,
                ))
                pending.clear()
    if count == 0 or (intent.declared_raw_bytes is not None and count != intent.declared_raw_bytes):
        raise ArtifactInputMismatchError("submission EOF violates declared or nonempty size")
    if pending:
        parts.append(await store.upload_source_part(
            upload, len(parts) + 1, bytes(pending), operation_evidence=evidence,
        ))
    return SubmissionSourceCompletion(
        upload=upload, parts=tuple(parts), raw_sha256="sha256:" + digest.hexdigest(), raw_byte_count=count,
    )
