"""Internal opaque authorization seam for submission-bundle durable intent."""

from __future__ import annotations

from typing import Protocol

from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    SubmissionBundleDurableIntentAuthorityFacts,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle


class SubmissionBundlePreparedAuthorization(Protocol):
    """Consume final contributor authority in the durable intent transaction."""

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: SubmissionBundleDurableIntentAuthorityFacts,
    ) -> None: ...


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
