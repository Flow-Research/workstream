"""ACTORS-owned composition for narrowly selected contribution display labels."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.api.contribution_labels import ContributionActorLabelPort
from app.modules.actors.contribution_labels import ContributionActorLabelRepository
from app.modules.actors.repository import ActorRepository


def contribution_actor_label_port(session: AsyncSession) -> ContributionActorLabelPort:
    """Read selected labels on the export's authorized caller-owned snapshot."""
    return ContributionActorLabelRepository(session)


async def verified_notification_email(
    session: AsyncSession, actor_id: UUID, issuer: str,
) -> str | None:
    """Expose private issuer-observed email only to the notification composition."""
    return await ActorRepository(session).verified_notification_email(actor_id, issuer)
