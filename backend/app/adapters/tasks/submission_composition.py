"""Hidden composition for the TASK-owned admission-backed Submission command."""

from __future__ import annotations

from app.modules.tasks.api import (
    SubmissionCreationAuthorityFacts,
    SubmissionCreationUnavailable,
)


class DenySubmissionCreationAuthorization:
    """Keep the hidden human action unavailable until AUTH activation."""

    async def authorize(self, facts: SubmissionCreationAuthorityFacts) -> None:
        del facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")

    async def consume(self, facts: SubmissionCreationAuthorityFacts) -> None:
        del facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")
