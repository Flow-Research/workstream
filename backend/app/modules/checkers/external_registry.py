"""Hidden caller-transaction service for immutable external-checker registration."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.external import (
    ExternalCheckerRegistrationAuthorityFacts,
    ExternalCheckerRegistrationAuthorityPort,
    ExternalCheckerRegistrationRequest,
    ExternalCheckerRegistryConflict,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistryUnavailable,
    ExternalCheckerResourceLimits,
    ExternalCheckerSchema,
)
from app.modules.checkers.models import ExternalCheckerRegistryEntryRecord


def _schema_values(prefix: str, schema: ExternalCheckerSchema) -> dict[str, object]:
    return {
        f"{prefix}_schema_id": schema.schema_id,
        f"{prefix}_schema_version": schema.schema_version,
        f"{prefix}_schema_sha256": schema.schema_sha256,
        f"{prefix}_schema_document": schema.document,
    }


def _row_entry(row: ExternalCheckerRegistryEntryRecord) -> ExternalCheckerRegistryEntry:
    return ExternalCheckerRegistryEntry(
        registry_entry_id=row.id,
        registration_operation_id=row.registration_operation_id,
        registered_by_actor_profile_id=row.registered_by_actor_profile_id,
        authorization_decision_event_id=row.authorization_decision_event_id,
        created_at=row.created_at,
        capability_id=row.capability_id,
        capability_version=row.capability_version,
        phase=row.phase,
        image_digest=row.image_digest,
        configuration_schema=ExternalCheckerSchema(
            schema_id=row.configuration_schema_id,
            schema_version=row.configuration_schema_version,
            schema_sha256=row.configuration_schema_sha256,
            document=row.configuration_schema_document,
        ),
        input_schema=ExternalCheckerSchema(
            schema_id=row.input_schema_id,
            schema_version=row.input_schema_version,
            schema_sha256=row.input_schema_sha256,
            document=row.input_schema_document,
        ),
        output_schema=ExternalCheckerSchema(
            schema_id=row.output_schema_id,
            schema_version=row.output_schema_version,
            schema_sha256=row.output_schema_sha256,
            document=row.output_schema_document,
        ),
        resources=ExternalCheckerResourceLimits(
            cpu_millis=row.cpu_millis,
            memory_bytes=row.memory_bytes,
            deadline_ms=row.deadline_ms,
            maximum_output_bytes=row.maximum_output_bytes,
        ),
        entry_digest=row.entry_digest,
    )


class ExternalCheckerRegistryRepository:
    """Flush-only persistence for one caller-owned registration transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_registration_scopes(
        self, operation_id: UUID, *, capability_id: str, capability_version: str, phase: str
    ) -> None:
        """Serialize operation replay and immutable logical identity publication."""
        for value in (
            f"external-checker-operation:{operation_id}",
            f"external-checker-identity:{phase}:{capability_id}:{capability_version}",
        ):
            await self._session.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                {"scope": value},
            )

    async def by_operation(
        self, operation_id: UUID
    ) -> ExternalCheckerRegistryEntryRecord | None:
        return await self._session.scalar(
            select(ExternalCheckerRegistryEntryRecord).where(
                ExternalCheckerRegistryEntryRecord.registration_operation_id == operation_id
            )
        )

    async def by_identity(
        self, *, capability_id: str, capability_version: str, phase: str
    ) -> ExternalCheckerRegistryEntryRecord | None:
        return await self._session.scalar(
            select(ExternalCheckerRegistryEntryRecord).where(
                ExternalCheckerRegistryEntryRecord.capability_id == capability_id,
                ExternalCheckerRegistryEntryRecord.capability_version == capability_version,
                ExternalCheckerRegistryEntryRecord.phase == phase,
            )
        )

    async def by_exact_id(
        self, registry_entry_id: UUID
    ) -> ExternalCheckerRegistryEntryRecord | None:
        return await self._session.get(
            ExternalCheckerRegistryEntryRecord,
            registry_entry_id,
            populate_existing=True,
        )

    async def add(self, row: ExternalCheckerRegistryEntryRecord) -> None:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)


class ExternalCheckerRegistryService:
    """Publish immutable registry metadata without granting execution authority."""

    def __init__(
        self,
        session: AsyncSession,
        authority: ExternalCheckerRegistrationAuthorityPort,
    ) -> None:
        self._session = session
        self._authority = authority
        self._repository = ExternalCheckerRegistryRepository(session)

    def _require_root_transaction(self) -> None:
        transaction = self._session.sync_session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            )

    async def register(
        self, request: ExternalCheckerRegistrationRequest
    ) -> ExternalCheckerRegistryEntry:
        """Authorize, publish or exactly replay one immutable registry entry."""
        self._require_root_transaction()
        request = ExternalCheckerRegistrationRequest.model_validate(request)
        facts = ExternalCheckerRegistrationAuthorityFacts(
            actor_profile_id=request.actor_profile_id,
            operation_id=request.operation_id,
            registry_entry_id=request.registry_entry_id,
            request_digest=request.request_digest,
            entry_digest=request.spec.spec_digest,
        )
        try:
            authority = await self._authority.authorize_registration(facts)
        except ExternalCheckerRegistryUnavailable:
            raise
        except Exception as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc
        if authority.actor_profile_id != request.actor_profile_id:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            )
        await self._repository.lock_registration_scopes(
            request.operation_id,
            capability_id=request.spec.capability_id,
            capability_version=request.spec.capability_version,
            phase=request.spec.phase,
        )
        replay = await self._repository.by_operation(request.operation_id)
        if replay is not None:
            if not self._matches_request(replay, request):
                raise ExternalCheckerRegistryConflict(
                    "external_checker_registry_conflict"
                )
            return _row_entry(replay)
        if await self._repository.by_identity(
            capability_id=request.spec.capability_id,
            capability_version=request.spec.capability_version,
            phase=request.spec.phase,
        ) is not None:
            raise ExternalCheckerRegistryConflict("external_checker_registry_conflict")
        spec = request.spec
        values = {
            "id": request.registry_entry_id,
            "registration_operation_id": request.operation_id,
            "request_digest": request.request_digest,
            "capability_id": spec.capability_id,
            "capability_version": spec.capability_version,
            "phase": spec.phase,
            "image_digest": spec.image_digest,
            **_schema_values("configuration", spec.configuration_schema),
            **_schema_values("input", spec.input_schema),
            **_schema_values("output", spec.output_schema),
            **spec.resources.model_dump(),
            "entry_digest": spec.spec_digest,
            "registered_by_actor_profile_id": request.actor_profile_id,
            "authorization_decision_event_id": authority.authorization_decision_event_id,
        }
        row = ExternalCheckerRegistryEntryRecord(**values)
        await self._repository.add(row)
        return _row_entry(row)

    async def read_exact(
        self, registry_entry_id: UUID, entry_digest: str
    ) -> ExternalCheckerRegistryEntry:
        """Read one exact row; never select a current/latest version."""
        self._require_root_transaction()
        if type(registry_entry_id) is not UUID or type(entry_digest) is not str:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            )
        row = await self._repository.by_exact_id(registry_entry_id)
        if row is None or row.entry_digest != entry_digest:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            )
        return _row_entry(row)

    @staticmethod
    def _matches_request(
        row: ExternalCheckerRegistryEntryRecord,
        request: ExternalCheckerRegistrationRequest,
    ) -> bool:
        try:
            entry = _row_entry(row)
        except (TypeError, ValueError):
            return False
        return (
            row.id == request.registry_entry_id
            and row.request_digest == request.request_digest
            and row.registered_by_actor_profile_id == request.actor_profile_id
            and entry.entry_digest == request.spec.spec_digest
            and ExternalCheckerRegistryEntry.model_validate(entry).model_dump(
                mode="json",
                exclude={
                    "registry_entry_id",
                    "entry_digest",
                    "registration_operation_id",
                    "registered_by_actor_profile_id",
                    "authorization_decision_event_id",
                    "created_at",
                },
            )
            == request.spec.model_dump(mode="json")
        )
