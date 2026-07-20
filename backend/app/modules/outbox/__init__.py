"""Shared transactional outbox persistence and caller-transaction append."""

from app.modules.outbox.schemas import (
    OutboxAppendDisposition,
    OutboxAppendInput,
    OutboxAppendResult,
    OutboxIdempotencyConflict,
    OutboxInputError,
    OutboxPersistenceError,
)
from app.modules.outbox.service import OutboxService

__all__ = [
    "OutboxAppendDisposition",
    "OutboxAppendInput",
    "OutboxAppendResult",
    "OutboxIdempotencyConflict",
    "OutboxInputError",
    "OutboxPersistenceError",
    "OutboxService",
]
