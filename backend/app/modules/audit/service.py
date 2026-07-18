"""Application service for typed authority audit evidence."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuthorityAuditEventInput
from app.modules.tasks.models import AuditEvent


class AuditService:
    """Build and persist privacy-safe authority events in the caller unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the shared audit repository to the caller's session."""
        self._repository = AuditRepository(session)

    async def add_authority_event(self, value: AuthorityAuditEventInput) -> AuditEvent:
        """Persist one validated authority event without committing its transaction."""
        try:
            fields = dict(object.__getattribute__(value, "__dict__"))
        except Exception:  # noqa: BLE001 - the service boundary accepts no caller diagnostics
            fields = None
        if fields is None:
            raise TypeError("invalid authority audit input")
        value = AuthorityAuditEventInput.model_validate(fields)
        cause_id = value.invalidation_cause_event_id
        if cause_id is not None and await self._repository.get_authority_event(str(cause_id)) is None:
            raise ValueError("invalidation cause must be an existing authority event")
        fields = value.model_dump(mode="json")
        fields["id"] = fields.pop("event_id")
        fields["actor_id"] = fields.pop("actor_ref")
        event = AuditEvent(
            **fields,
            from_status=None,
            to_status=None,
            external_subject=None,
            external_issuer=None,
            actor_roles=[],
            claim_snapshot={},
            auth_source="local_authority",
            is_dev_auth=False,
            event_payload={},
            event_domain="authority",
            event_version=1,
        )
        return await self._repository._add_validated_authority_event(event)
