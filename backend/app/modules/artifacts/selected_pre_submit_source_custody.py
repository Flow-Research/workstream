"""ART implementation of CHECKERS' exact live-source consumer boundary."""

from app.modules.artifacts.api.submission_intake import SubmissionIntakePreSourcePort
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitReservationFacts, SelectedPreSubmitUnavailable,
)


class SelectedPreSubmitSourceCustody:
    """Compare immutable request facts while holding ART's current source lease."""

    def __init__(self, sources: SubmissionIntakePreSourcePort) -> None:
        self._sources = sources

    async def lock_selected_pre_submit_source(
        self, facts: SelectedPreSubmitReservationFacts,
    ) -> None:
        """Caller already holds TASK; preserve exact ART checks before CHECKERS."""
        current = await self._sources.lock_pre_source(
            source=facts.source, lease_id=facts.foreground_lease_id,
            generation=facts.foreground_lease_generation,
        )
        if (
            current.source != facts.source
            or current.project_id != facts.project_id
            or current.task_id != facts.task_id
            or current.assignment_id != facts.assignment_id
            or current.actor_profile_id != facts.actor_profile_id
            or current.identity_link_id != facts.identity_link_id
            or current.metadata_sha256 != facts.metadata_sha256
            or current.locked_context_sha256 != facts.locked_context_sha256
            or current.lease_id != facts.foreground_lease_id
            or current.lease_generation != facts.foreground_lease_generation
            or current.pre_deadline_at != facts.pre_deadline_at
        ):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_source_changed")

