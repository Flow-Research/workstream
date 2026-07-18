"""Privacy-keyed rate-control service with independent commit ownership."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import hashlib
import hmac
import math
from typing import TypeAlias

from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import decode_api_rate_limit_key_secret
from app.db.session import get_session_factory
from app.modules.api_controls.repository import ApiRateControlRepository

RATE_KEY_DOMAIN = b"workstream-api-rate/v1"
FIRST_ACCESS_SCOPE = "first_access"
ADMIN_MUTATION_SCOPE = "admin_mutation"
RATE_SCOPES = {FIRST_ACCESS_SCOPE, ADMIN_MUTATION_SCOPE}
MAX_IDENTITY_BYTES = 4_096
PRUNE_BATCH_SIZE = 100
MISSING_DATABASE_ERROR = "WORKSTREAM_DATABASE_URL must be set before database access"
SessionFactory: TypeAlias = async_sessionmaker[AsyncSession]


class RateControlUnavailableError(RuntimeError):
    """Raised when a rate decision cannot be made safely."""


@dataclass(frozen=True)
class RateControlDecision:
    """Committed fixed-window decision derived from database time."""

    allowed: bool
    request_count: int
    retry_after: int


def _frame(value: bytes) -> bytes:
    return len(value).to_bytes(4, "big") + value


def rate_key_digest(
    secret: SecretStr, control_scope: str, issuer: str, subject: str
) -> bytes:
    """Derive the exact privacy key for one verified external identity."""
    if control_scope not in RATE_SCOPES:
        raise ValueError("unsupported rate control scope")
    try:
        issuer_bytes = issuer.encode("utf-8")
        subject_bytes = subject.encode("utf-8")
    except UnicodeEncodeError:
        raise RateControlUnavailableError("rate control unavailable") from None
    if not 1 <= len(issuer_bytes) <= MAX_IDENTITY_BYTES or not 1 <= len(
        subject_bytes
    ) <= MAX_IDENTITY_BYTES:
        raise RateControlUnavailableError("rate control unavailable")
    preimage = b"".join(
        _frame(value)
        for value in (
            RATE_KEY_DOMAIN,
            control_scope.encode("ascii"),
            issuer_bytes,
            subject_bytes,
        )
    )
    return hmac.new(
        decode_api_rate_limit_key_secret(secret), preimage, hashlib.sha256
    ).digest()


class RateControlService:
    """Consume durable counters in a transaction independent of request work."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    def _factory(self) -> SessionFactory:
        if self._session_factory is not None:
            return self._session_factory
        try:
            return get_session_factory()
        except RuntimeError as exc:
            if str(exc) != MISSING_DATABASE_ERROR:
                raise
            raise RateControlUnavailableError("rate control unavailable") from exc

    async def consume(
        self,
        *,
        control_scope: str,
        issuer: str,
        subject: str,
        limit: int,
        window_seconds: int,
        secret: SecretStr | None,
    ) -> RateControlDecision:
        """Commit one counter use before returning its allow/deny decision."""
        if secret is None:
            raise RateControlUnavailableError("rate control unavailable")
        digest = rate_key_digest(secret, control_scope, issuer, subject)
        session: AsyncSession | None = None
        try:
            async with self._factory()() as session:
                repository = ApiRateControlRepository(session)
                consumed = await repository.consume(
                    control_scope, digest, window_seconds
                )
                await repository.prune_expired(
                    control_scope, digest, batch_size=PRUNE_BATCH_SIZE
                )
                await session.commit()
        except SQLAlchemyError as exc:
            if session is not None:
                with suppress(SQLAlchemyError):
                    await session.rollback()
            raise RateControlUnavailableError("rate control unavailable") from exc

        retry_after = max(
            1,
            min(
                window_seconds,
                math.ceil(
                    (consumed.window_expires_at - consumed.db_now).total_seconds()
                ),
            ),
        )
        return RateControlDecision(
            allowed=consumed.request_count <= limit,
            request_count=consumed.request_count,
            retry_after=retry_after,
        )
