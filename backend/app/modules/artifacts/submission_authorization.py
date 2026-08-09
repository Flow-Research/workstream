"""Internal opaque authorization seam for submission-bundle durable intent."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    SubmissionBundleDurableIntentAuthorityFacts,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.runtime import AuthorizationContext


class SubmissionBundlePreparedAuthorization(Protocol):
    """Consume final contributor authority in the durable intent transaction."""

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: SubmissionBundleDurableIntentAuthorityFacts,
    ) -> None: ...


class SubmissionBundlePreparationAuthorization(SubmissionBundlePreparedAuthorization, Protocol):
    """Own preflight and final transaction-bound contributor preparation authority."""

    async def preflight(
        self,
        *,
        authorization_context: AuthorizationContext,
        task_id: UUID,
        assignment_id: UUID,
        predecessor_submission_id: UUID | None,
        idempotency_key: UUID,
    ) -> None: ...

    def transaction(self) -> AbstractAsyncContextManager[object]: ...

    async def prepare_final(
        self,
        *,
        authorization_context: AuthorizationContext,
        task_id: UUID,
        assignment_id: UUID,
        predecessor_submission_id: UUID | None,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle: ...

    def close(self) -> None: ...


class DenySubmissionBundlePreparedAuthorization:
    """Keep contributor durable preparation unavailable until XINT-05A."""

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: SubmissionBundleDurableIntentAuthorityFacts,
    ) -> None:
        del prepared_authorization, facts
        raise ArtifactAuthorityDeniedError("submission bundle durable preparation is unavailable")


class DenySubmissionBundlePreparationAuthorization(DenySubmissionBundlePreparedAuthorization):
    """Keep the complete contributor surface unavailable until XINT-05A."""

    async def preflight(self, **values: object) -> None:
        del values
        raise ArtifactAuthorityDeniedError("submission bundle preparation is unavailable")

    def transaction(self) -> AbstractAsyncContextManager[object]:
        raise ArtifactAuthorityDeniedError("submission bundle preparation is unavailable")

    async def prepare_final(self, **values: object) -> PreparedAuthorizationHandle:
        del values
        raise ArtifactAuthorityDeniedError("submission bundle preparation is unavailable")

    def close(self) -> None:
        return None
