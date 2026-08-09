"""Provider-neutral Operator reads for immutable artifact operations."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.interfaces.artifact_operations import (
    ArtifactAuditResourceType,
    ArtifactBindingResourceType,
)
from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
    ArtifactAdmissionScope,
    ArtifactBinding,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactPutObservationReceipt,
    ArtifactRecoveryAttempt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
    SubmissionBundleAdmission,
    SubmissionBundleDurableIntent,
)
from app.modules.artifacts.metrics import ArtifactAdmissionMetrics
from app.modules.artifacts.schemas import (
    ArtifactOperatorAuthority,
    ArtifactOperatorAuthorityFacts,
    ArtifactOperatorAuthorizationEvidence,
    ArtifactOperatorResourceType,
)
from app.modules.checkers.models import CheckerRun
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    Project,
    ProjectGuide,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.runtime import AuthorizationContext
from app.modules.tasks.models import AuditEvent, Submission, WorkstreamTask


@dataclass(frozen=True, slots=True)
class ArtifactPage:
    items: tuple[dict[str, object], ...]
    next_cursor: str | None


class ArtifactOperatorNotFound(RuntimeError):
    """Concealed missing or cross-project artifact resource."""


class ArtifactOperatorEvidenceError(RuntimeError):
    """Authority returned evidence for a different action or permission."""


class ArtifactOperatorInputError(ValueError):
    """Bounded invalid pagination or filter input."""


_PERMISSIONS = {
    ActionId.ARTIFACT_BINDING_READ: PermissionId.ARTIFACT_BINDING_READ,
    ActionId.ARTIFACT_REPLICA_READ: PermissionId.ARTIFACT_REPLICA_READ,
    ActionId.ARTIFACT_RECEIPT_READ: PermissionId.ARTIFACT_RECEIPT_READ,
    ActionId.ARTIFACT_VERIFICATION_JOB_READ: PermissionId.ARTIFACT_VERIFICATION_JOB_READ,
    ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ: PermissionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
    ActionId.ARTIFACT_AUDIT_READ: PermissionId.ARTIFACT_AUDIT_READ,
    ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ: PermissionId.OPERATIONS_STATUS_READ,
}


class ArtifactOperatorService:
    """Implement bounded reads after composing canonical artifact lineage."""

    def __init__(
        self,
        session: AsyncSession,
        authority: ArtifactOperatorAuthority,
        settings: Settings,
        metrics: ArtifactAdmissionMetrics,
    ) -> None:
        self._session = session
        self._authority = authority
        self._settings = settings
        self._metrics = metrics

    async def authorize_readiness(self, authorization_context: AuthorizationContext) -> None:
        """Authorize the static readiness view with the exact operations action."""
        await self._authorize(
            authorization_context,
            ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ,
            ArtifactOperatorResourceType.ADMISSION_SCOPE,
            "artifact-storage-readiness",
            (),
        )

    async def list_bindings(
        self,
        *,
        authorization_context: AuthorizationContext,
        resource_type: ArtifactBindingResourceType,
        resource_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ArtifactPage:
        canonical_project = await self._binding_resource_project(resource_type, str(resource_id))
        if canonical_project is None:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        project = (UUID(canonical_project),)
        await self._authorize(
            authorization_context,
            ActionId.ARTIFACT_BINDING_READ,
            ArtifactOperatorResourceType.BINDING_SCOPE,
            f"{resource_type}:{resource_id}",
            project,
        )
        base = (
            select(ArtifactBinding)
            .where(
                ArtifactBinding.project_id == canonical_project,
                ArtifactBinding.resource_type == resource_type,
                ArtifactBinding.resource_id == str(resource_id),
            )
            .with_for_update()
        )
        rows = await self._page(base, ArtifactBinding.id, cursor, limit)
        return self._result(
            rows,
            limit,
            lambda row: {
                "id": row.id,
                "content_id": row.content_id,
                "project_id": row.project_id,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "logical_role": row.logical_role,
                "scope_version": row.scope_version,
                "supersedes_binding_id": row.supersedes_binding_id,
                "created_at": row.created_at,
            },
        )

    async def list_replicas(
        self,
        *,
        authorization_context: AuthorizationContext,
        content_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ArtifactPage:
        projects = await self._content_projects(str(content_id))
        if not projects:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        await self._authorize(
            authorization_context,
            ActionId.ARTIFACT_REPLICA_READ,
            ArtifactOperatorResourceType.CONTENT,
            str(content_id),
            projects,
        )
        rows = await self._page(
            select(ArtifactReplica).where(ArtifactReplica.content_id == str(content_id)),
            ArtifactReplica.id,
            cursor,
            limit,
        )
        return self._result(
            rows,
            limit,
            lambda row: {
                "id": row.id,
                "content_id": row.content_id,
                "verification_state": row.verification_state,
                "availability_state": row.availability_state,
                "integrity_state": row.integrity_state,
                "last_reconciled_at": row.last_reconciled_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
        )

    async def list_receipts(
        self,
        *,
        authorization_context: AuthorizationContext,
        replica_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ArtifactPage:
        projects = await self._replica_projects(str(replica_id))
        if not projects:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        await self._authorize(
            authorization_context,
            ActionId.ARTIFACT_RECEIPT_READ,
            ArtifactOperatorResourceType.REPLICA,
            str(replica_id),
            projects,
        )

        receipt_order = {"put": 0, "put_observation": 1, "verification": 2}
        cursor_type: str | None = None
        cursor_id = ""
        if cursor:
            cursor_type, separator, cursor_id = cursor.partition(":")
            if not separator or cursor_type not in receipt_order:
                raise ArtifactOperatorInputError("artifact receipt cursor is invalid")

        def after_cursor(receipt_type: str, id_column):
            if cursor_type is None or receipt_order[receipt_type] > receipt_order[cursor_type]:
                return True
            if receipt_order[receipt_type] < receipt_order[cursor_type]:
                return False
            return id_column > cursor_id

        operations = (
            await self._session.scalars(
                select(ArtifactOperationReceipt)
                .where(
                    ArtifactOperationReceipt.replica_id == str(replica_id),
                    after_cursor("put", ArtifactOperationReceipt.id),
                )
                .order_by(ArtifactOperationReceipt.id)
                .limit(limit + 1)
            )
        ).all()
        observations = (
            await self._session.execute(
                select(ArtifactPutObservationReceipt, ArtifactPutAttempt.replica_id)
                .join(
                    ArtifactPutAttempt,
                    ArtifactPutAttempt.id == ArtifactPutObservationReceipt.put_attempt_id,
                )
                .where(
                    ArtifactPutAttempt.replica_id == str(replica_id),
                    after_cursor("put_observation", ArtifactPutObservationReceipt.id),
                )
                .order_by(ArtifactPutObservationReceipt.id)
                .limit(limit + 1)
            )
        ).all()
        verifications = (
            await self._session.execute(
                select(ArtifactVerificationReceipt, ArtifactVerificationJob.replica_id)
                .join(
                    ArtifactVerificationJob,
                    ArtifactVerificationJob.id == ArtifactVerificationReceipt.verification_job_id,
                )
                .where(
                    ArtifactVerificationJob.replica_id == str(replica_id),
                    after_cursor("verification", ArtifactVerificationReceipt.id),
                )
                .order_by(ArtifactVerificationReceipt.id)
                .limit(limit + 1)
            )
        ).all()
        encoded = (
            [
                {
                    "id": row.id,
                    "receipt_type": "put",
                    "replica_id": row.replica_id,
                    "outcome": row.outcome,
                    "replayed": row.replayed,
                    "attempt_number": row.attempt_number,
                    "created_at": row.created_at,
                }
                for row in operations
            ]
            + [
                {
                    "id": row.id,
                    "receipt_type": "put_observation",
                    "replica_id": bound_replica,
                    "outcome": row.outcome,
                    "execution_generation": row.execution_generation,
                    "created_at": row.created_at,
                }
                for row, bound_replica in observations
            ]
            + [
                {
                    "id": row.id,
                    "receipt_type": "verification",
                    "replica_id": bound_replica,
                    "verification_job_id": row.verification_job_id,
                    "outcome": row.outcome,
                    "execution_generation": row.execution_generation,
                    "created_at": row.created_at,
                }
                for row, bound_replica in verifications
            ]
        )
        encoded.sort(key=lambda item: (receipt_order[str(item["receipt_type"])], str(item["id"])))
        visible = encoded[:limit]
        return ArtifactPage(
            tuple(visible),
            (
                f"{visible[-1]['receipt_type']}:{visible[-1]['id']}"
                if len(encoded) > limit and visible
                else None
            ),
        )

    async def get_verification_job(
        self, *, authorization_context: AuthorizationContext, verification_job_id: UUID
    ) -> dict[str, object]:
        row = await self._session.scalar(
            select(ArtifactVerificationJob)
            .where(ArtifactVerificationJob.id == str(verification_job_id))
            .with_for_update()
        )
        if row is None:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        projects = await self._replica_projects(row.replica_id)
        await self._authorize(
            authorization_context,
            ActionId.ARTIFACT_VERIFICATION_JOB_READ,
            ArtifactOperatorResourceType.VERIFICATION_JOB,
            row.id,
            projects,
        )
        receipt = await self._session.scalar(
            select(ArtifactVerificationReceipt).where(
                ArtifactVerificationReceipt.verification_job_id == row.id
            )
        )
        return {
            "id": row.id,
            "replica_id": row.replica_id,
            "parent_verification_job_id": row.parent_verification_job_id,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "maximum_attempts": row.maximum_attempts,
            "next_run_at": row.next_run_at,
            "cas_version": row.cas_version,
            "terminal_result_code": row.terminal_result_code,
            "terminal_at": row.terminal_at,
            "receipt_id": receipt.id if receipt else None,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    async def get_recovery_attempt(
        self, *, authorization_context: AuthorizationContext, recovery_attempt_id: UUID
    ) -> dict[str, object]:
        row = await self._session.scalar(
            select(ArtifactRecoveryAttempt)
            .where(ArtifactRecoveryAttempt.id == str(recovery_attempt_id))
            .with_for_update()
        )
        if row is None:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        await self._authorize(
            authorization_context,
            ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
            ArtifactOperatorResourceType.RECOVERY_ATTEMPT,
            row.id,
            (UUID(row.project_id),),
        )
        source = await self._session.scalar(
            select(ArtifactVerificationJob).where(
                ArtifactVerificationJob.id == row.source_verification_job_id
            )
        )
        retry = await self._session.scalar(
            select(ArtifactVerificationJob).where(
                ArtifactVerificationJob.id == row.retry_verification_job_id
            )
        )
        if source is None or retry is None:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        return {
            "id": row.id,
            "project_id": row.project_id,
            "task_id": row.task_id,
            "submission_id": row.submission_id,
            "source_verification_job_id": source.id,
            "source_verification_job_status": source.status,
            "retry_verification_job_id": retry.id,
            "retry_verification_job_status": retry.status,
            "parent_recovery_attempt_id": row.parent_recovery_attempt_id,
            "status": row.status,
            "terminal_result_code": row.terminal_result_code,
            "initiation_audit_event_id": row.initiation_audit_event_id,
            "terminal_audit_event_id": row.terminal_audit_event_id,
            "cas_version": row.cas_version,
            "created_at": row.created_at,
            "terminal_at": row.terminal_at,
            "updated_at": row.updated_at,
        }

    async def list_audit_events(
        self,
        *,
        authorization_context: AuthorizationContext,
        resource_type: ArtifactAuditResourceType,
        resource_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ArtifactPage:
        projects = await self._audit_projects(resource_type, str(resource_id))
        if not projects:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        await self._authorize(
            authorization_context,
            ActionId.ARTIFACT_AUDIT_READ,
            ArtifactOperatorResourceType.AUDIT_RESOURCE,
            f"{resource_type}:{resource_id}",
            projects,
        )
        rows = await self._page(
            select(AuditEvent).where(
                AuditEvent.entity_type == resource_type, AuditEvent.entity_id == str(resource_id)
            ),
            AuditEvent.id,
            cursor,
            limit,
        )
        return self._result(
            rows,
            limit,
            lambda row: {
                "id": row.id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "event_type": row.event_type,
                "from_status": row.from_status,
                "to_status": row.to_status,
                "reason": row.reason,
                "occurred_at": row.occurred_at,
                "created_at": row.created_at,
                "request_id": row.request_id,
                "correlation_id": row.correlation_id,
            },
        )

    async def admission_usage(
        self,
        *,
        authorization_context: AuthorizationContext,
        project_id: UUID | None,
        task_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> ArtifactPage:
        if project_id is None:
            raise ArtifactOperatorInputError("artifact admission project scope is required")
        canonical_project = await self._session.scalar(
            select(Project.id).where(Project.id == str(project_id)).with_for_update()
        )
        if canonical_project is None:
            raise ArtifactOperatorNotFound("artifact resource was not found")
        filters = []
        if task_id is not None:
            task_project = await self._session.scalar(
                select(WorkstreamTask.project_id)
                .where(WorkstreamTask.id == str(task_id))
                .with_for_update()
            )
            if task_project is None or task_project != canonical_project:
                raise ArtifactOperatorNotFound("artifact resource was not found")
        filters.append(
            or_(
                and_(
                    ArtifactAdmissionScope.scope_type == "project",
                    ArtifactAdmissionScope.scope_id == str(project_id),
                ),
                ArtifactAdmissionScope.scope_type == "deployment",
            )
        )
        projects = (UUID(canonical_project),)
        if task_id is not None:
            filters.append(
                and_(
                    ArtifactAdmissionScope.scope_type == "task",
                    ArtifactAdmissionScope.scope_id == str(task_id),
                )
            )
        statement = select(ArtifactAdmissionScope)
        if filters:
            statement = statement.where(or_(*filters))
        await self._authorize(
            authorization_context,
            ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ,
            ArtifactOperatorResourceType.ADMISSION_SCOPE,
            f"project:{project_id or '*'}:task:{task_id or '*'}",
            projects,
        )
        if cursor:
            cursor_type, separator, cursor_id = cursor.partition(":")
            if not separator or cursor_type not in {"deployment", "project", "producer", "task"}:
                raise ArtifactOperatorInputError("artifact admission cursor is invalid")
            statement = statement.where(
                or_(
                    ArtifactAdmissionScope.scope_type > cursor_type,
                    and_(
                        ArtifactAdmissionScope.scope_type == cursor_type,
                        ArtifactAdmissionScope.scope_id > cursor_id,
                    ),
                )
            )
        rows = list(
            (
                await self._session.scalars(
                    statement.order_by(
                        ArtifactAdmissionScope.scope_type, ArtifactAdmissionScope.scope_id
                    ).limit(limit + 1)
                )
            ).all()
        )
        configured = self._configured_limits()
        scope_keys = [(row.scope_type, row.scope_id) for row in rows[:limit]]
        admission_usage: dict[tuple[str, str, str], tuple[int, int]] = {}
        if scope_keys:
            usage_rows = await self._session.execute(
                select(
                    ArtifactAdmissionCharge.scope_type,
                    ArtifactAdmissionCharge.scope_id,
                    SubmissionBundleAdmission.status,
                    func.count(SubmissionBundleAdmission.id),
                    func.coalesce(func.sum(ArtifactAdmissionCharge.byte_count), 0),
                )
                .join(
                    ArtifactPutAttemptCharge,
                    ArtifactPutAttemptCharge.charge_id == ArtifactAdmissionCharge.id,
                )
                .join(
                    SubmissionBundleDurableIntent,
                    SubmissionBundleDurableIntent.put_attempt_id
                    == ArtifactPutAttemptCharge.attempt_id,
                )
                .join(
                    SubmissionBundleAdmission,
                    SubmissionBundleAdmission.durable_intent_id
                    == SubmissionBundleDurableIntent.id,
                )
                .where(
                    tuple_(
                        ArtifactAdmissionCharge.scope_type,
                        ArtifactAdmissionCharge.scope_id,
                    ).in_(scope_keys),
                    SubmissionBundleAdmission.status.in_(("ready", "stale")),
                )
                .group_by(
                    ArtifactAdmissionCharge.scope_type,
                    ArtifactAdmissionCharge.scope_id,
                    SubmissionBundleAdmission.status,
                )
            )
            admission_usage = {
                (scope_type, scope_id, admission_status): (int(count), int(byte_count))
                for scope_type, scope_id, admission_status, count, byte_count in usage_rows
            }
        return self._result(
            rows,
            limit,
            lambda row: {
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "counted_bytes": row.counted_bytes,
                "limit_bytes": row.limit_bytes,
                "remaining_bytes": row.limit_bytes - row.counted_bytes,
                "configured_limit_bytes": configured[row.scope_type],
                "unbound_ready_count": admission_usage.get(
                    (row.scope_type, row.scope_id, "ready"), (0, 0)
                )[0],
                "unbound_ready_bytes": admission_usage.get(
                    (row.scope_type, row.scope_id, "ready"), (0, 0)
                )[1],
                "stale_count": admission_usage.get(
                    (row.scope_type, row.scope_id, "stale"), (0, 0)
                )[0],
                "stale_bytes": admission_usage.get(
                    (row.scope_type, row.scope_id, "stale"), (0, 0)
                )[1],
                "cas_version": row.cas_version,
                "updated_at": row.updated_at,
            },
            cursor_key=lambda row: f"{row.scope_type}:{row.scope_id}",
        )

    async def _authorize(
        self,
        context: AuthorizationContext,
        action: ActionId,
        resource_type: ArtifactOperatorResourceType,
        resource_id: str,
        projects: tuple[UUID, ...],
    ) -> ArtifactOperatorAuthorizationEvidence:
        evidence = await self._authority.authorize(
            authorization_context=context,
            facts=ArtifactOperatorAuthorityFacts(resource_type, resource_id, projects, action),
        )
        expected = _PERMISSIONS[action].value
        if evidence.action_id is not action or evidence.permission_id != expected:
            raise ArtifactOperatorEvidenceError(
                "artifact Operator authorization evidence is invalid"
            )
        return evidence

    async def _content_projects(self, content_id: str) -> tuple[UUID, ...]:
        binding_values = (
            await self._session.scalars(
                select(ArtifactBinding.project_id)
                .where(ArtifactBinding.content_id == content_id)
                .with_for_update()
            )
        ).all()
        attempt_values = (
            await self._session.scalars(
                select(ArtifactPutAttempt.project_id)
                .join(ArtifactReplica, ArtifactReplica.id == ArtifactPutAttempt.replica_id)
                .where(ArtifactReplica.content_id == content_id)
                .with_for_update(of=(ArtifactPutAttempt, ArtifactReplica))
            )
        ).all()
        return self._project_ids((*binding_values, *attempt_values))

    async def _replica_projects(self, replica_id: str) -> tuple[UUID, ...]:
        values = (
            await self._session.scalars(
                select(ArtifactPutAttempt.project_id)
                .where(ArtifactPutAttempt.replica_id == replica_id)
                .with_for_update()
            )
        ).all()
        if values:
            return self._project_ids(values)
        content_id = await self._session.scalar(
            select(ArtifactReplica.content_id)
            .where(ArtifactReplica.id == replica_id)
            .with_for_update()
        )
        return await self._content_projects(content_id) if content_id else ()

    async def _binding_resource_project(self, resource_type: str, resource_id: str) -> str | None:
        if resource_type == "project":
            return await self._session.scalar(
                select(Project.id).where(Project.id == resource_id).with_for_update()
            )
        if resource_type == "project_guide":
            return await self._session.scalar(
                select(ProjectGuide.project_id)
                .where(ProjectGuide.id == resource_id)
                .with_for_update()
            )
        if resource_type == "guide_source_snapshot":
            return await self._session.scalar(
                select(GuideSourceSnapshot.project_id)
                .where(GuideSourceSnapshot.id == resource_id)
                .with_for_update()
            )
        if resource_type == "guide_source_snapshot_item":
            return await self._session.scalar(
                select(GuideSourceSnapshot.project_id)
                .join(
                    GuideSourceSnapshotItem,
                    GuideSourceSnapshotItem.source_snapshot_id == GuideSourceSnapshot.id,
                )
                .where(GuideSourceSnapshotItem.id == resource_id)
                .with_for_update(of=(GuideSourceSnapshot, GuideSourceSnapshotItem))
            )
        if resource_type == "task":
            return await self._session.scalar(
                select(WorkstreamTask.project_id)
                .where(WorkstreamTask.id == resource_id)
                .with_for_update()
            )
        if resource_type == "submission":
            return await self._session.scalar(
                select(WorkstreamTask.project_id)
                .join(Submission, Submission.task_id == WorkstreamTask.id)
                .where(Submission.id == resource_id)
                .with_for_update(of=(Submission, WorkstreamTask))
            )
        if resource_type == "checker_run":
            return await self._session.scalar(
                select(WorkstreamTask.project_id)
                .join(CheckerRun, CheckerRun.task_id == WorkstreamTask.id)
                .where(CheckerRun.id == resource_id)
                .with_for_update(of=(CheckerRun, WorkstreamTask))
            )
        return None

    async def _audit_projects(self, resource_type: str, resource_id: str) -> tuple[UUID, ...]:
        if resource_type == "artifact_binding":
            value = await self._session.scalar(
                select(ArtifactBinding.project_id)
                .where(ArtifactBinding.id == resource_id)
                .with_for_update()
            )
            return self._project_ids((value,)) if value else ()
        if resource_type == "artifact_content":
            return await self._content_projects(resource_id)
        if resource_type in {"artifact_replica", "artifact_receipt"}:
            replica_id = resource_id
            if resource_type == "artifact_receipt":
                candidates: list[str] = []
                operation_replica = await self._session.scalar(
                    select(ArtifactOperationReceipt.replica_id)
                    .where(ArtifactOperationReceipt.id == resource_id)
                    .with_for_update()
                )
                if operation_replica:
                    candidates.append(operation_replica)
                observation_replica = await self._session.scalar(
                    select(ArtifactPutAttempt.replica_id)
                    .join(
                        ArtifactPutObservationReceipt,
                        ArtifactPutObservationReceipt.put_attempt_id == ArtifactPutAttempt.id,
                    )
                    .where(ArtifactPutObservationReceipt.id == resource_id)
                    .with_for_update(of=(ArtifactPutObservationReceipt, ArtifactPutAttempt))
                )
                if observation_replica:
                    candidates.append(observation_replica)
                verification_replica = await self._session.scalar(
                    select(ArtifactVerificationJob.replica_id)
                    .join(
                        ArtifactVerificationReceipt,
                        ArtifactVerificationReceipt.verification_job_id
                        == ArtifactVerificationJob.id,
                    )
                    .where(ArtifactVerificationReceipt.id == resource_id)
                    .with_for_update(of=(ArtifactVerificationReceipt, ArtifactVerificationJob))
                )
                if verification_replica:
                    candidates.append(verification_replica)
                if len(set(candidates)) != 1:
                    return ()
                replica_id = candidates[0]
            return await self._replica_projects(replica_id)
        if resource_type == "artifact_verification_job":
            replica_id = await self._session.scalar(
                select(ArtifactVerificationJob.replica_id)
                .where(ArtifactVerificationJob.id == resource_id)
                .with_for_update()
            )
            return await self._replica_projects(replica_id) if replica_id else ()
        if resource_type == "artifact_recovery_attempt":
            project_id = await self._session.scalar(
                select(ArtifactRecoveryAttempt.project_id)
                .where(ArtifactRecoveryAttempt.id == resource_id)
                .with_for_update()
            )
            return self._project_ids((project_id,)) if project_id else ()
        return ()

    async def _page(self, statement: Select, id_column, cursor: str | None, limit: int):
        if cursor:
            statement = statement.where(id_column > cursor)
        return list(
            (await self._session.scalars(statement.order_by(id_column).limit(limit + 1))).all()
        )

    @staticmethod
    def _result(rows, limit: int, encode, cursor_key=lambda row: row.id) -> ArtifactPage:
        visible = rows[:limit]
        return ArtifactPage(
            tuple(encode(row) for row in visible),
            cursor_key(visible[-1]) if len(rows) > limit and visible else None,
        )

    @staticmethod
    def _project_ids(values) -> tuple[UUID, ...]:
        return tuple(sorted({UUID(value) for value in values}, key=str))

    def _configured_limits(self) -> dict[str, int | None]:
        return {
            "task": self._settings.artifact_admission_task_maximum_bytes,
            "producer": self._settings.artifact_admission_producer_maximum_bytes,
            "project": self._settings.artifact_admission_project_maximum_bytes,
            "deployment": self._settings.artifact_admission_deployment_maximum_bytes,
        }


def artifact_provider_readiness(settings: Settings) -> dict[str, object]:
    """Return configuration-only readiness without constructing a provider adapter."""
    backend = settings.artifact_store_backend
    profile = settings.artifact_s3_provider_profile
    aws_requires_live_proof = backend == "s3_compatible" and profile == "aws_s3"
    return {
        "backend": backend,
        "provider_profile": profile,
        "configured": backend != "disabled",
        "active": False,
        "status": (
            "inactive_live_proof_required"
            if aws_requires_live_proof
            else "inactive_disabled"
            if backend == "disabled"
            else "configured_inactive"
        ),
        "prerequisites": {
            "durable_admission_limits_configured": all(
                value is not None
                for value in (
                    settings.artifact_admission_task_maximum_bytes,
                    settings.artifact_admission_producer_maximum_bytes,
                    settings.artifact_admission_project_maximum_bytes,
                    settings.artifact_admission_deployment_maximum_bytes,
                )
            ),
            "scratch_configured": settings.artifact_scratch_root is not None,
            "aws_live_proof_required": aws_requires_live_proof,
            "aws_live_proof_present": False,
        },
    }
