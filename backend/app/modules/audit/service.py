"""Application service for typed authority audit evidence."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repository import AuditRepository, LIFECYCLE_AUTH_SOURCE
from app.modules.audit.schemas import AuthorityAuditEventInput, LifecycleAuditEventInput
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
        if (
            cause_id is not None
            and await self._repository.get_authority_event(str(cause_id)) is None
        ):
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


class LifecycleAuditParticipant:
    """Stage privacy-bounded lifecycle evidence in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the participant to the caller-owned unit of work."""
        self._repository = AuditRepository(session)

    async def add_event(self, value: LifecycleAuditEventInput) -> AuditEvent:
        """Flush one lifecycle event without committing the caller transaction."""
        try:
            fields = dict(object.__getattribute__(value, "__dict__"))
        except Exception:  # noqa: BLE001 - caller diagnostics are never retained
            fields = None
        if fields is None:
            raise TypeError("invalid lifecycle audit input")
        try:
            value = LifecycleAuditEventInput.model_validate(fields)
        except Exception:
            raise TypeError("invalid lifecycle audit input") from None
        references = {
            key.value: str(reference)
            for key, reference in sorted(value.references.items(), key=lambda item: item[0].value)
        }
        event = AuditEvent(
            id=str(value.event_id),
            entity_type=value.entity_type.value,
            entity_id=str(value.entity_id),
            event_type=value.event_type.value,
            from_status=value.from_status,
            to_status=value.to_status,
            actor_id=str(value.actor_id),
            external_subject="workstream:lifecycle-participant",
            external_issuer="workstream:internal",
            actor_roles=[],
            claim_snapshot={},
            auth_source=LIFECYCLE_AUTH_SOURCE,
            is_dev_auth=False,
            reason=value.reason.value,
            event_payload={"references": references},
            event_domain="legacy_lifecycle",
            event_version=None,
            occurred_at=None,
        )
        return await self._repository._add_validated_lifecycle_event(event)
