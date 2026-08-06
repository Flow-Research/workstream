"""Replay-only persistence for submission-policy mutations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.modules.projects.models import SubmissionPolicyMutationIdempotencyRecord
from app.modules.projects.repository import ProjectRepositoryIntegrityError


def _matches(
    column: InstrumentedAttribute, value: object
) -> ColumnElement[bool]:
    """Return exact null-safe equality for one nullable mapped column."""
    return column.is_(None) if value is None else column == value


class SubmissionPolicyMutationReplayRepository:
    """Own submission-policy replay rows in the caller transaction only."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind replay persistence to the caller-owned database session."""
        self._session = session

    async def find_by_operation(
        self, operation_id: UUID
    ) -> SubmissionPolicyMutationIdempotencyRecord | None:
        """Locate replay custody by its immutable public operation identity."""
        return await self._session.scalar(
            select(SubmissionPolicyMutationIdempotencyRecord).where(
                SubmissionPolicyMutationIdempotencyRecord.operation_id == operation_id
            )
        )

    async def _find_namespace(
        self,
        *,
        actor_profile_id: str,
        idempotency_key: UUID | None,
        service_identity: str | None,
        setup_run_id: str | None,
        setup_generation: int,
        setup_task_id: UUID | None,
        correlation_id: UUID | None,
        action_id: str,
    ) -> SubmissionPolicyMutationIdempotencyRecord | None:
        """Find the one human or fixed-service replay namespace."""
        namespace = (
            and_(
                SubmissionPolicyMutationIdempotencyRecord.service_identity.is_(None),
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.idempotency_key,
                    idempotency_key,
                ),
            )
            if service_identity is None
            else and_(
                SubmissionPolicyMutationIdempotencyRecord.service_identity == service_identity,
                SubmissionPolicyMutationIdempotencyRecord.setup_run_id == setup_run_id,
                SubmissionPolicyMutationIdempotencyRecord.setup_generation == setup_generation,
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.setup_task_id,
                    setup_task_id,
                ),
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.correlation_id,
                    correlation_id,
                ),
                SubmissionPolicyMutationIdempotencyRecord.action_id == action_id,
            )
        )
        return await self._session.scalar(
            select(SubmissionPolicyMutationIdempotencyRecord).where(
                SubmissionPolicyMutationIdempotencyRecord.actor_profile_id == actor_profile_id,
                namespace,
            )
        )

    async def reserve(
        self,
        *,
        actor_profile_id: str,
        identity_link_id: str,
        service_identity: str | None,
        action_id: str,
        idempotency_key: UUID | None,
        request_digest: str,
        resource_context_digest: str,
        resource_context_json: dict,
        operation_id: UUID,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        policy_id: str,
        setup_run_id: str | None,
        setup_generation: int,
        setup_task_id: UUID | None,
        correlation_id: UUID | None,
    ) -> tuple[
        Literal["claimed", "mismatch", "pending", "replayed"],
        SubmissionPolicyMutationIdempotencyRecord,
    ]:
        """Reserve or classify one exact immutable replay namespace."""
        values = {
            "id": uuid4(),
            "actor_profile_id": actor_profile_id,
            "identity_link_id": identity_link_id,
            "service_identity": service_identity,
            "action_id": action_id,
            "idempotency_key": idempotency_key,
            "request_digest": request_digest,
            "resource_context_digest": resource_context_digest,
            "resource_context_json": resource_context_json,
            "operation_id": operation_id,
            "project_id": project_id,
            "guide_id": guide_id,
            "source_snapshot_id": source_snapshot_id,
            "policy_id": policy_id,
            "setup_run_id": setup_run_id,
            "setup_generation": setup_generation,
            "setup_task_id": setup_task_id,
            "correlation_id": correlation_id,
            "status": "pending",
        }
        record_id = await self._session.scalar(
            insert(SubmissionPolicyMutationIdempotencyRecord)
            .values(**values)
            .on_conflict_do_nothing()
            .returning(SubmissionPolicyMutationIdempotencyRecord.id)
        )
        claimed = record_id is not None
        if record_id is None:
            record = await self.find_by_operation(operation_id)
            if record is None:
                record = await self._find_namespace(
                    actor_profile_id=actor_profile_id,
                    idempotency_key=idempotency_key,
                    service_identity=service_identity,
                    setup_run_id=setup_run_id,
                    setup_generation=setup_generation,
                    setup_task_id=setup_task_id,
                    correlation_id=correlation_id,
                    action_id=action_id,
                )
            if record is None:
                raise ProjectRepositoryIntegrityError(
                    "submission-policy replay reservation disappeared"
                )
        else:
            record = await self._session.get(
                SubmissionPolicyMutationIdempotencyRecord, record_id
            )
            if record is None:
                raise ProjectRepositoryIntegrityError(
                    "submission-policy replay reservation disappeared"
                )
        if claimed:
            return "claimed", record
        if any(
            (
                record.actor_profile_id != actor_profile_id,
                record.identity_link_id != identity_link_id,
                record.service_identity != service_identity,
                record.action_id != action_id,
                record.idempotency_key != idempotency_key,
                record.request_digest != request_digest,
                record.resource_context_digest != resource_context_digest,
                record.resource_context_json != resource_context_json,
                record.operation_id != operation_id,
                record.project_id != project_id,
                record.guide_id != guide_id,
                record.source_snapshot_id != source_snapshot_id,
                record.policy_id != policy_id,
                record.setup_run_id != setup_run_id,
                record.setup_generation != setup_generation,
                record.setup_task_id != setup_task_id,
                record.correlation_id != correlation_id,
            )
        ):
            return "mismatch", record
        return ("replayed" if record.status == "committed" else "pending"), record

    async def complete(
        self,
        operation_id: UUID,
        *,
        actor_profile_id: str,
        identity_link_id: str,
        service_identity: str | None,
        action_id: str,
        idempotency_key: UUID | None,
        request_digest: str,
        resource_context_digest: str,
        setup_run_id: str | None,
        setup_generation: int,
        setup_task_id: UUID | None,
        correlation_id: UUID | None,
        response_json: dict,
        committed_policy_id: str,
        committed_effective_policy_id: str | None = None,
        committed_pre_submit_policy_id: str | None = None,
    ) -> None:
        """Complete one pending operation exactly once."""
        completed = await self._session.scalar(
            update(SubmissionPolicyMutationIdempotencyRecord)
            .where(
                SubmissionPolicyMutationIdempotencyRecord.operation_id == operation_id,
                SubmissionPolicyMutationIdempotencyRecord.actor_profile_id == actor_profile_id,
                SubmissionPolicyMutationIdempotencyRecord.identity_link_id == identity_link_id,
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.service_identity,
                    service_identity,
                ),
                SubmissionPolicyMutationIdempotencyRecord.action_id == action_id,
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.idempotency_key,
                    idempotency_key,
                ),
                SubmissionPolicyMutationIdempotencyRecord.request_digest == request_digest,
                SubmissionPolicyMutationIdempotencyRecord.resource_context_digest
                == resource_context_digest,
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.setup_run_id,
                    setup_run_id,
                ),
                SubmissionPolicyMutationIdempotencyRecord.setup_generation == setup_generation,
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.setup_task_id,
                    setup_task_id,
                ),
                _matches(
                    SubmissionPolicyMutationIdempotencyRecord.correlation_id,
                    correlation_id,
                ),
                SubmissionPolicyMutationIdempotencyRecord.status == "pending",
            )
            .values(
                status="committed",
                response_json=response_json,
                committed_policy_id=committed_policy_id,
                committed_effective_policy_id=committed_effective_policy_id,
                committed_pre_submit_policy_id=committed_pre_submit_policy_id,
                committed_at=datetime.now(UTC),
            )
            .returning(SubmissionPolicyMutationIdempotencyRecord.id)
        )
        if completed is None:
            raise ProjectRepositoryIntegrityError("invalid submission-policy replay completion")
