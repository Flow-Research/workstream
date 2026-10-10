"""REV-owned shared acceptance composition; no delivery or public entry."""

from app.modules.reviews.acceptance.participant import FinalAcceptanceParticipant
from app.modules.reviews.api.acceptance import FinalAcceptancePort


def final_acceptance_participant(session) -> FinalAcceptancePort:
    from app.adapters.tasks import task_accepted_effects_participant
    from app.adapters.contributions import submitter_contribution_participant

    return FinalAcceptanceParticipant(
        session,
        tasks=lambda held: task_accepted_effects_participant(session, held),
        contributions=lambda held: submitter_contribution_participant(session, held),
    )
