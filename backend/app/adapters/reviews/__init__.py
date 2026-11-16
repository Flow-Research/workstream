"""REV-owned shared acceptance composition; no delivery or public entry."""

from app.modules.reviews.acceptance.participant import FinalAcceptanceParticipant
from app.modules.reviews.api.acceptance import FinalAcceptancePort


def fulfillment_current_custody(session):
    """Acquire current REV custody before request AUTH for factual evidence."""
    from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence

    return PostgresJointLifecycleMutationFence(session)


def final_acceptance_participant(session) -> FinalAcceptancePort:
    from app.adapters.tasks import task_accepted_effects_participant
    from app.adapters.contributions import submitter_contribution_participant

    return FinalAcceptanceParticipant(
        session,
        tasks=lambda held: task_accepted_effects_participant(session, held),
        contributions=lambda held: submitter_contribution_participant(session, held),
    )


def final_acceptance_read_port(session):
    """Compose actual source-time evidence without constructing acceptance authority."""
    from app.modules.reviews.acceptance.read_repository import FinalAcceptanceReadRepository
    from app.adapters.reviews.contribution_reads import ContributionAcceptanceSourceReadAdapter

    return ContributionAcceptanceSourceReadAdapter(FinalAcceptanceReadRepository(session))
