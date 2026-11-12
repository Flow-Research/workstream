"""Authorized T1 reservation, T4 accepted handoff and exact replay.

Only a positively acknowledged reservation returns a foreground owner. A raced
key or uncertain commit resolves the stored operation through current read
authority and cannot acquire a replacement lease or start a second upload.
"""
import json

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cancellation import await_completion_preserving_cancellation
from app.core.identifiers import new_record_id
from app.db.errors import integrity_constraint_name
from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata, SubmissionSourceCapacityLimits
from app.modules.artifacts.intake.repository import IntakeCustodyConflict, SubmissionIntakeRepository
from app.modules.artifacts.intake.progress import finalization_progress
from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationProgress
from app.modules.artifacts.intake.streaming import hash_submission_replay
from app.modules.artifacts.models import ArtifactStorageNamespace
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.authorization.api.submission_intake import (
    IntakeAuthorizationPort, IntakeAuthorityDenied, IntakeOperationReadFacts,
    IntakeReservationAuthorityFacts, IntakeReservationPreflightFacts,
)
from app.modules.checkers.api.external_policy import LockedExternalCheckerPolicies
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitCoordinationPort, SelectedPreSubmitReservationFacts
from app.modules.outbox.api import OutboxAppendPort
from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextPort, ProjectLockedPolicyContextRequest
from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
from app.modules.tasks.api.intake_custody import IntakeTaskCustodyPort
from app.modules.tasks.api.submission_context import (
    TaskSubmissionContextPort, TaskSubmissionContextRequest,
    require_revision_acknowledgement, require_revision_capacity,
)


@dataclass(frozen=True, slots=True)
class IntakeReservationOwner:
    operation_id: UUID
    lease_id: UUID
    generation: int


@dataclass(frozen=True, slots=True)
class IntakeReplay:
    """Detached operation state, never foreground write authority."""
    operation_id: UUID
    state: str
    failure_code: str | None
    maximum_raw_bytes: int
    raw_sha256: str | None
    raw_byte_count: int | None
    finalization: SubmissionFinalizationProgress | None


class IntakeCommitUnknown(RuntimeError):
    """Commit outcome cannot authorize new provider work."""


class _ExistingKey(RuntimeError):
    pass


class ForegroundIntakeAdmission:
    """Own reservation and acceptance roots without body or provider I/O."""
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], *,
        tasks: Callable[[AsyncSession], IntakeTaskCustodyPort],
        task_contexts: Callable[[AsyncSession], TaskSubmissionContextPort],
        projects: Callable[[AsyncSession], ProjectLockedPolicyContextPort],
        authorization: Callable[[AsyncSession], IntakeAuthorizationPort],
        events: Callable[[AsyncSession], OutboxAppendPort],
        namespace: ArtifactStorageNamespaceSpec, capacity_limits: SubmissionSourceCapacityLimits,
        maximum_raw_bytes: int, upload_duration: timedelta, lease_duration: timedelta,
    ) -> None:
        """Bind explicit limits and transaction-local owner ports without provider I/O."""
        if (type(maximum_raw_bytes) is not int or not 1 <= maximum_raw_bytes <= MAXIMUM_SUBMISSION_ZIP_BYTES
                or not isinstance(upload_duration, timedelta) or not isinstance(lease_duration, timedelta)
                or not timedelta(0) < lease_duration <= upload_duration):
            raise ValueError("intake reservation limits are invalid")
        self._sessions, self._tasks, self._contexts = sessions, tasks, task_contexts
        self._projects, self._authorization = projects, authorization
        self._events = events
        self._namespace = namespace
        self._capacity = SubmissionSourceCapacityLimits.model_validate(capacity_limits)
        self._maximum, self._upload_duration, self._lease_duration = maximum_raw_bytes, upload_duration, lease_duration

    @asynccontextmanager
    async def _root(self):
        """Own commit/cleanup and restage only this request's canonical AUTH denial."""
        session = self._sessions()
        authority = self._authorization(session)
        try:
            await session.begin()
            try:
                yield session, authority
            except IntakeAuthorityDenied as exc:
                await await_completion_preserving_cancellation(session.rollback())
                if await authority.restage_denial(exc):
                    await await_completion_preserving_cancellation(session.commit())
                raise
            else:
                try:
                    await await_completion_preserving_cancellation(session.commit())
                except IntegrityError:
                    # PostgreSQL rejected this transaction; unlike transport loss,
                    # a constraint failure positively proves no acceptance commit.
                    raise
                except Exception as exc:
                    raise IntakeCommitUnknown("intake commit acknowledgement unavailable") from exc
        finally:
            authority.close()
            await await_completion_preserving_cancellation(session.close())

    async def admit(
        self, metadata: SubmissionIntakeMetadata, *, actor_id: UUID, identity_link_id: UUID,
        idempotency_key: UUID, declared_raw_bytes: int | None,
    ) -> IntakeReservationOwner | IntakeReplay:
        """Return upload ownership only after commit, otherwise resolve current read authority."""
        metadata = SubmissionIntakeMetadata.model_validate(metadata)
        if declared_raw_bytes is not None and (
            type(declared_raw_bytes) is not int or not 1 <= declared_raw_bytes <= self._maximum
        ):
            raise ValueError("intake declared byte count is invalid")
        try:
            return await self._reserve(metadata, actor_id, identity_link_id, idempotency_key, declared_raw_bytes)
        except IntegrityError as exc:
            if integrity_constraint_name(exc) != "uq_submission_intake_actor_key":
                raise
        except (_ExistingKey, IntakeCommitUnknown):
            pass
        # The old root has been closed. Never acquire a second TASK in that root.
        return await self._read(metadata, actor_id, idempotency_key)

    async def _reserve(self, metadata, actor_id, identity_link_id, key, declared):
        """Serialize TASK then actor/grant before committing pointer, charge and allow."""
        async with self._root() as (session, authority):
            tasks = self._tasks(session)
            repository = SubmissionIntakeRepository(session, tasks)
            if await repository.find_actor_key(actor_id, key) is not None:
                raise _ExistingKey()
            project_id = await tasks.lock(metadata.task_id)
            await authority.lock_actor(actor_id, identity_link_id)
            selectors = IntakeReservationPreflightFacts(
                new_record_id(), project_id, metadata.task_id, metadata.assignment_id,
                actor_id, identity_link_id, key, metadata.metadata_sha256(),
            )
            await authority.preflight(selectors)
            if await repository.find_actor_key(actor_id, key) is not None:
                raise _ExistingKey()
            await self._validate_context(session, metadata, actor_id)
            now = await session.scalar(select(func.clock_timestamp()))
            row = await repository.reserve(
                operation_id=selectors.operation_id, metadata=metadata, actor_id=actor_id,
                identity_link_id=identity_link_id, idempotency_key=key,
                maximum_raw_bytes=self._maximum, capacity_limits=self._capacity,
                declared_raw_bytes=declared, upload_deadline_at=now + self._upload_duration,
                lease_expires_at=now + self._lease_duration,
            )
            facts = IntakeReservationAuthorityFacts(
                **asdict(selectors), locked_context_sha256=row.locked_context_sha256,
                task_status=row.eligible_task_status,
            )
            await authority.consume(await authority.prepare(facts), facts)
            owner = IntakeReservationOwner(UUID(row.id), UUID(row.lease_id), row.lease_generation)
        return owner

    async def _validate_context(self, session, metadata, actor_id):
        """Require canonical lineage, selected phases and the exact qualified namespace."""
        task = await self._contexts(session).lock_submission_context(TaskSubmissionContextRequest(
            metadata.task_id, metadata.assignment_id, actor_id, metadata.predecessor_submission_id,
        ))
        references = asdict(task.locked_project_context)
        references.pop("locked_contribution_policy_version_id")
        project = await self._projects(session).lock_locked_policy_context(ProjectLockedPolicyContextRequest(**references))
        if task.predecessor is not None:
            revision = project.activation_receipt.command.revision
            require_revision_capacity(
                task, project_id=project.project_id, policy_id=revision.policy_id,
                policy_generation=revision.generation, policy_hash=revision.policy_hash,
                max_revision_rounds=RevisionPolicySemantics.model_validate_json(project.revision_policy.value).max_revision_rounds,
            )
        require_revision_acknowledgement(task, metadata.revision_preparation_id, metadata.revision_preparation_sha256)
        policies = LockedExternalCheckerPolicies.model_validate_json(project.external_checker_policies.value)
        if len(policies.pre_submit.entries) != 1 or len(policies.post_submit.entries) != 1:
            raise IntakeCustodyConflict("intake_requires_one_pre_and_post_checker")
        namespace = await session.get(ArtifactStorageNamespace, "primary")
        if namespace is None or any(getattr(namespace, name) != value for name, value in asdict(self._namespace).items()):
            raise IntakeCustodyConflict("intake_namespace_unavailable")
        if namespace.provider_profile not in {"local-v2", "minio-v1"}:
            raise IntakeCustodyConflict("intake_source_provider_unqualified")
        return task, project

    async def accept(
        self, owner: IntakeReservationOwner, request: SelectedPreSubmitReservationFacts, terminal_digest: str, *,
        checkers: Callable[[AsyncSession], SelectedPreSubmitCoordinationPort],
        outbox: Callable[[AsyncSession], OutboxAppendPort],
    ) -> dict:
        """Commit T4 or resolve an uncertain acknowledgement by the same operation.

        checkers/outbox are transaction-local owner ports supplied by composition.
        The surrounding foreground lease must continue heartbeating through here.
        """
        try:
            async with self._root() as (session, authority):
                repository = SubmissionIntakeRepository(session, self._tasks(session))
                row = await repository._lock(owner.operation_id)
                await authority.authorize_read(IntakeOperationReadFacts(
                    UUID(row.id), UUID(row.project_id), UUID(row.task_id), UUID(row.actor_profile_id)))
                self._match_acceptance_command(row, request, terminal_digest, accepted=row.state in {"finalization_pending", "finalized"})
                if row.state in {"finalization_pending", "finalized"}:
                    return await self._accepted_receipt(session, authority, row)
                receipt = await self._accept_new(session, authority, repository, row, owner,
                                                 request, terminal_digest, checkers, outbox)
            return receipt
        except IntegrityError as exc:
            raise IntakeCustodyConflict("intake_acceptance_conflict") from exc
        except IntakeCommitUnknown:
            async with self._root() as (session, authority):
                row = await SubmissionIntakeRepository(session, self._tasks(session))._lock(owner.operation_id)
                await authority.authorize_read(IntakeOperationReadFacts(
                    UUID(row.id), UUID(row.project_id), UUID(row.task_id), UUID(row.actor_profile_id)))
                if row.state not in {"finalization_pending", "finalized"}:
                    raise IntakeCommitUnknown("submission acceptance outcome is unresolved")
                self._match_acceptance_command(row, request, terminal_digest, accepted=True)
                return await self._accepted_receipt(session, authority, row)

    @staticmethod
    def _match_acceptance_command(row, request, terminal_digest, *, accepted):
        if (row.id != str(request.source.location.operation_id)
                or row.actor_profile_id != str(request.actor_profile_id)
                or row.idempotency_key != str(request.idempotency_key)
                or row.metadata_sha256 != request.metadata_sha256
                or row.locked_context_sha256 != request.locked_context_sha256
                or (accepted and (row.selected_pre_submit_run_id != str(request.attempt_id)
                    or row.selected_pre_submit_request_sha256 != request.request_digest
                    or row.selected_pre_submit_terminal_sha256 != terminal_digest))):
            raise IntakeCustodyConflict("intake_acceptance_conflict")

    async def _accepted_receipt(self, session, authority, row):
        from app.modules.artifacts.intake.acceptance import authority_facts
        await authority.validate_acceptance_receipt(authority_facts(row), UUID(row.acceptance_decision_id))
        await session.execute(text("SELECT public.require_submission_acceptance(o) "
                                   "FROM public.submission_intake_operations o WHERE id=:id"), {"id": UUID(row.id)})
        return dict(row.acceptance_receipt, replayed=True)

    async def _accept_new(self, session, authority, repository, row, owner,
                          request, terminal_digest, checkers, outbox):
        from types import SimpleNamespace
        from app.modules.artifacts.intake.acceptance import authority_facts, finalization_event, stage_acceptance
        row = await repository._owned(owner.operation_id, owner.lease_id, owner.generation)
        if row.state != "pre_checking":
            raise IntakeCustodyConflict("intake_acceptance_conflict")
        await authority.lock_actor(UUID(row.actor_profile_id), UUID(row.identity_link_id))
        await authority.preflight(IntakeReservationPreflightFacts(
            UUID(row.id), UUID(row.project_id), UUID(row.task_id), UUID(row.assignment_id),
            UUID(row.actor_profile_id), UUID(row.identity_link_id), UUID(row.idempotency_key), row.metadata_sha256))
        metadata = SubmissionIntakeMetadata.model_validate_json(json.dumps(row.command_metadata))
        task, project = await self._validate_context(session, metadata, UUID(row.actor_profile_id))
        lineage = request.admission_lineage
        predecessor = task.predecessor
        if (task.status != row.eligible_task_status
                or (predecessor.submission_id if predecessor else None) != lineage.predecessor_submission_id
                or (predecessor.version if predecessor else None) != lineage.predecessor_submission_version
                or task.checker_remediation_manifest_id != lineage.checker_remediation_manifest_id
                or LockedExternalCheckerPolicies.model_validate_json(project.external_checker_policies.value).pre_submit != request.policy):
            raise IntakeCustodyConflict("intake_acceptance_context_changed")
        terminal = await checkers(session).lock_acceptance(
            run_id=request.attempt_id, facts=request, terminal_digest=terminal_digest)
        draft = SimpleNamespace(**{name: getattr(row, name) for name in (
            "id", "project_id", "task_id", "assignment_id", "actor_profile_id", "identity_link_id",
            "idempotency_key", "metadata_sha256", "locked_context_sha256", "eligible_task_status",
            "lease_id", "lease_generation")})
        stage_acceptance(draft, terminal, await session.scalar(select(func.clock_timestamp())))
        facts = authority_facts(draft)
        draft.acceptance_decision_id = str(await authority.consume_acceptance(
            await authority.prepare_acceptance(facts), facts))
        draft.finalization_event_id = str((await outbox(session).append(finalization_event(draft))).event_id)
        for name, value in vars(draft).items():
            setattr(row, name, value)
        row.state = "finalization_pending"
        await self._tasks(session).accept(UUID(row.task_id), UUID(row.id), row.eligible_task_status)
        return dict(row.acceptance_receipt)

    async def _read(self, metadata, actor_id, key, *, expected_operation_id=None):
        """Authorize the stored operation before comparing metadata or returning its state."""
        async with self._root() as (session, authority):
            repository = SubmissionIntakeRepository(session, self._tasks(session))
            found = await repository.find_actor_key(actor_id, key)
            if found is None:
                raise IntakeCommitUnknown("intake reservation could not be resolved")
            row = await repository._lock(UUID(found.id))
            await authority.authorize_read(IntakeOperationReadFacts(
                UUID(row.id), UUID(row.project_id), UUID(row.task_id), UUID(row.actor_profile_id),
            ))
            if row.metadata_sha256 != metadata.metadata_sha256():
                raise IntakeCustodyConflict("submission_idempotency_conflict")
            if expected_operation_id is not None and UUID(row.id) != expected_operation_id:
                raise IntakeCustodyConflict("submission_idempotency_conflict")
            result = IntakeReplay(UUID(row.id), row.state, row.failure_code,
                                  row.maximum_raw_bytes, row.raw_sha256, row.raw_byte_count,
                                  await finalization_progress(row, self._events(session)))
        return result

    async def replay(
        self, metadata: SubmissionIntakeMetadata, chunks: AsyncIterator[bytes], *,
        actor_id: UUID, idempotency_key: UUID, declared_raw_bytes: int | None,
        idle_timeout_seconds: float, replay_duration: timedelta,
    ) -> IntakeReplay:
        """Authorize before reading bytes and again before revealing current state."""
        if not isinstance(replay_duration, timedelta) or replay_duration <= timedelta(0):
            raise ValueError("intake replay duration must be positive")
        metadata = SubmissionIntakeMetadata.model_validate(metadata)
        original = await self._read(metadata, actor_id, idempotency_key)
        if original.raw_sha256 is None or original.raw_byte_count is None:
            code = "submission_operation_in_progress" if original.state in {"receiving", "pre_checking"} else "submission_operation_terminal"
            raise IntakeCustodyConflict(code)
        raw = await hash_submission_replay(
            chunks, maximum_raw_bytes=original.maximum_raw_bytes, declared_raw_bytes=declared_raw_bytes,
            idle_timeout_seconds=idle_timeout_seconds, deadline_at=datetime.now(UTC) + replay_duration,
        )
        current = await self._read(metadata, actor_id, idempotency_key, expected_operation_id=original.operation_id)
        if (raw.raw_sha256, raw.raw_byte_count) != (current.raw_sha256, current.raw_byte_count):
            raise IntakeCustodyConflict("submission_idempotency_conflict")
        return current
