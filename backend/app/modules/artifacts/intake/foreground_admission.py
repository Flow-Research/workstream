"""Authorized T1 reservation, T4 accepted handoff and exact replay.

Only a positively acknowledged reservation returns a foreground owner. A raced
key or uncertain commit resolves the stored operation through current read
authority and cannot acquire a replacement lease or start a second upload.
"""
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
from app.interfaces.artifacts import ArtifactLimitExceededError
from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
from app.modules.artifacts.api.submission_intake import SealedSubmissionSource, SubmissionIntakeFailure, SubmissionIntakeMetadata, SubmissionSourceCapacityLimits
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from app.modules.artifacts.intake.repository import (
    ForegroundDeadline, IntakeCustodyConflict, SubmissionIntakeRepository, clamped_foreground_deadline,
)
from app.modules.artifacts.intake.progress import finalization_progress
from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationProgress
from app.modules.artifacts.intake.streaming import hash_submission_replay
from app.modules.artifacts.models import ArtifactStorageNamespace, SubmissionBundleAdmission
from app.modules.artifacts.selected_pre_submit_admission import (
    bind_selected_pre_submit_admission, build_selected_pre_submit_reservation, project_submission_archive_limits,
)
from app.modules.artifacts.submission_manifest import SubmissionCanonicalPredecessor
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.authorization.api.submission_intake import (
    IntakeAuthorizationPort, IntakeAuthorityDenied, IntakeOperationReadFacts,
    IntakeReservationAuthorityFacts, IntakeReservationPreflightFacts,
)
from app.modules.checkers.api.external_policy import LockedExternalCheckerPolicies
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitCoordinationPort, SelectedPreSubmitReservationFacts, SelectedPreSubmitRuntimeProfile
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.outbox.api import OutboxAppendPort, FinalizedUnknownDeliveryPort
from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextPort, ProjectLockedPolicyContextRequest
from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
from app.modules.tasks.api.intake_custody import IntakeTaskCustodyPort
from app.modules.tasks.api.submission_context import (
    TaskSubmissionContextPort, TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable, require_revision_capacity,
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
    acceptance_receipt: dict | None


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
        deliveries: Callable[[AsyncSession], FinalizedUnknownDeliveryPort],
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
        self._events, self._deliveries = events, deliveries
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
            _, project = await self._validate_context(session, metadata, actor_id)
            caps = project_submission_archive_limits(project)
            maximum = self._maximum
            if caps is not None and caps.maximum_archive_size_bytes is not None:
                maximum = min(maximum, caps.maximum_archive_size_bytes)
            if declared is not None and declared > maximum:
                raise ArtifactLimitExceededError("submission exceeds the locked project raw ZIP limit")
            now = await session.scalar(select(func.clock_timestamp()))
            row = await repository.reserve(
                operation_id=selectors.operation_id, metadata=metadata, actor_id=actor_id,
                identity_link_id=identity_link_id, idempotency_key=key,
                maximum_raw_bytes=maximum, capacity_limits=self._capacity,
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
            metadata.task_id, metadata.assignment_id, actor_id, select_predecessor=True,
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
        policies = LockedExternalCheckerPolicies.model_validate_json(project.external_checker_policies.value)
        if len(policies.pre_submit.entries) != 1 or len(policies.post_submit.entries) != 1:
            raise IntakeCustodyConflict("intake_requires_one_pre_and_post_checker")
        namespace = await session.get(ArtifactStorageNamespace, "primary")
        if namespace is None or any(getattr(namespace, name) != value for name, value in asdict(self._namespace).items()):
            raise IntakeCustodyConflict("intake_namespace_unavailable")
        if namespace.provider_profile not in {"local-v2", "minio-v1", "aws-s3-v1"}:
            raise IntakeCustodyConflict("intake_source_provider_unqualified")
        return task, project

    @staticmethod
    async def _require_reserved_context(session, row, task):
        snapshot = await session.scalar(text(
            "SELECT public.submission_intake_task_snapshot(t) "
            "FROM public.workstream_tasks t WHERE id=:id"
        ), {"id": task.task_id})
        preparation = task.revision_context
        selection = row.command_metadata
        if (
            task.status != row.eligible_task_status
            or snapshot != row.locked_task_context
            or selection["predecessor_submission_id"] != (
                str(task.predecessor.submission_id) if task.predecessor else None
            )
            or selection["revision_preparation_id"] != (
                str(preparation.preparation_id) if preparation else None
            )
            or selection["revision_preparation_sha256"] != (
                preparation.preparation_sha256 if preparation else None
            )
        ):
            raise TaskSubmissionContextUnavailable("revision_context_changed")

    async def reserve_pre(
        self, owner: IntakeReservationOwner, source: SealedSubmissionSource, *,
        runtime_profile: SelectedPreSubmitRuntimeProfile,
        checkers: Callable[[AsyncSession], SelectedPreSubmitCoordinationPort],
    ) -> SelectedPreSubmitReservationFacts:
        """Commit one source-bound PRE reservation under fresh contributor authority.

        The original operation supplies every command selector. No body or provider
        I/O occurs under these locks; execution starts only after this commit.
        An uncertain commit never grants permission to start the guest.
        """
        async with self._root() as (session, authority):
            repository = SubmissionIntakeRepository(session, self._tasks(session))
            row = await repository._owned(owner.operation_id, owner.lease_id, owner.generation)
            if source.location.operation_id != owner.operation_id:
                raise IntakeCustodyConflict("intake_pre_source_mismatch")
            await authority.lock_actor(UUID(row.actor_profile_id), UUID(row.identity_link_id))
            await authority.preflight(IntakeReservationPreflightFacts(
                UUID(row.id), UUID(row.project_id), UUID(row.task_id), UUID(row.assignment_id),
                UUID(row.actor_profile_id), UUID(row.identity_link_id), UUID(row.idempotency_key),
                row.metadata_sha256,
            ))
            metadata = SubmissionIntakeMetadata(
                task_id=UUID(row.task_id), assignment_id=UUID(row.assignment_id),
                feedback=row.command_metadata["feedback"],
            )
            task, project = await self._validate_context(session, metadata, UUID(row.actor_profile_id))
            await self._require_reserved_context(session, row, task)
            custody = await repository.lock_pre_source(
                source=source, lease_id=owner.lease_id, generation=owner.generation)
            predecessor, predecessor_rules = None, None
            if task.predecessor is not None:
                admission = await session.scalar(select(SubmissionBundleAdmission).where(
                    SubmissionBundleAdmission.consumed_by_submission_id == str(task.predecessor.submission_id),
                    SubmissionBundleAdmission.status == "consumed",
                ))
                if (admission is None or admission.selected_pre_submit_run_id is None
                        or admission.pre_submit_evidence_set_id is not None
                        or admission.selected_rules_sha256 is None):
                    raise IntakeCustodyConflict("submission_canonical_predecessor_unavailable")
                predecessor = SubmissionCanonicalPredecessor(
                    submission_id=task.predecessor.submission_id,
                    submission_version=task.predecessor.version,
                    archive_sha256=admission.archive_sha256,
                    semantic_manifest_sha256=admission.semantic_manifest_sha256,
                )
                predecessor_rules = admission.selected_rules_sha256
            selected = bind_selected_pre_submit_admission(
                task=task, project=project, predecessor=predecessor,
                predecessor_rules_sha256=predecessor_rules,
                predecessor_exists=task.predecessor is not None,
                packet=SubmissionPacketView(),
            )
            reservation = build_selected_pre_submit_reservation(
                source=custody, metadata=metadata, task=task, project=project,
                attempt_id=new_record_id(), idempotency_key=UUID(row.idempotency_key),
                selected=selected, runtime_profile=runtime_profile,
            )
            await checkers(session).reserve(reservation)
        return reservation

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
            if integrity_constraint_name(exc) == "ck_submission_revision_acceptance_deadline":
                raise SubmissionIntakeFailure("revision_deadline_expired") from None
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

    async def finish(
        self, owner: IntakeReservationOwner, *, state: str, failure_code: str,
        deadline: ForegroundDeadline | None = None,
    ) -> str | None:
        """End drained foreground work, retaining all physical source obligations.

        A committed acceptance, another generation or an expired owner cannot be
        overwritten by a late request exception. Expiry remains the reaper's job.
        """
        try:
            async with self._root() as (session, _authority):
                repository = SubmissionIntakeRepository(session, self._tasks(session))
                return await repository.terminalize(
                    owner.operation_id, owner.lease_id, owner.generation,
                    state=state, failure_code=failure_code, deadline=deadline,
                )
        except IntakeCustodyConflict as exc:
            if str(exc) != "intake_owner_stale":
                raise
        except IntegrityError as exc:
            # The lease can expire after the locked read but before the SQL
            # trigger checks the update. The failed root is closed before recovery.
            error = getattr(exc.orig, "__cause__", None)
            if (getattr(exc.orig, "sqlstate", None) != "23514"
                    or getattr(error, "message", None) != "expired intake requires abandonment"):
                raise
        return None

    async def settle_expired_foreground(
        self, owner: IntakeReservationOwner, metadata: SubmissionIntakeMetadata, *,
        actor_id: UUID, idempotency_key: UUID,
    ) -> str | None:
        """Settle exact hard expiry or observe the original assignment release."""
        async with self._root() as (session, authority):
            repository = SubmissionIntakeRepository(session, self._tasks(session))
            row = await repository._lock(owner.operation_id)
            await authority.authorize_read(IntakeOperationReadFacts(
                UUID(row.id), UUID(row.project_id), UUID(row.task_id), UUID(row.actor_profile_id)))
            if (row.actor_profile_id != str(actor_id) or row.idempotency_key != str(idempotency_key)
                    or not self._matches_public_command(row, metadata)):
                raise IntakeCustodyConflict("submission_idempotency_conflict")
            released = (row.state in {"cancelled", "abandoned"}
                       and row.failure_code in {"revision_deadline_expired", "submission_unavailable"}
                       and row.lease_id == str(owner.lease_id)
                       and row.lease_generation == owner.generation + 1)
            code = row.failure_code if released else None
            deadline = clamped_foreground_deadline(row)
            if deadline is not None and await repository.abandon_expired(
                owner.operation_id, deadline_owner=(owner.lease_id, owner.generation),
            ):
                code = deadline.failure_code
        return code

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
        metadata = SubmissionIntakeMetadata(
            task_id=UUID(row.task_id), assignment_id=UUID(row.assignment_id),
            feedback=row.command_metadata["feedback"],
        )
        task, project = await self._validate_context(session, metadata, UUID(row.actor_profile_id))
        await self._require_reserved_context(session, row, task)
        lineage = request.admission_lineage
        predecessor = task.predecessor
        if (task.status != row.eligible_task_status
                or (predecessor.submission_id if predecessor else None) != lineage.predecessor_submission_id
                or (predecessor.version if predecessor else None) != lineage.predecessor_submission_version
                or task.checker_remediation_manifest_id != lineage.checker_remediation_manifest_id
                or request.default_context.project_archive_limits != project_submission_archive_limits(project)
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
        for name in (
            "accepted_at", "selected_pre_submit_run_id", "selected_pre_submit_request_sha256",
            "selected_pre_submit_terminal_sha256", "accepted_source_sha256", "accepted_manifest_sha256",
            "accepted_context", "accepted_context_sha256", "acceptance_receipt", "acceptance_receipt_sha256",
            "acceptance_decision_id", "finalization_event_id",
        ):
            setattr(row, name, getattr(draft, name))
        row.state = "finalization_pending"
        await self._tasks(session).accept(UUID(row.task_id), UUID(row.id), row.eligible_task_status)
        return dict(row.acceptance_receipt)

    @staticmethod
    def _matches_public_command(row, metadata):
        if (str(metadata.task_id), str(metadata.assignment_id)) != (row.task_id, row.assignment_id):
            return False
        if "feedback" in row.command_metadata:
            return row.metadata_sha256 == metadata.metadata_sha256()
        # Retired text cannot be presented on the public wire. Operation reads
        # still recover every historical command, even when it carried text.
        return (metadata.feedback is None and row.command_metadata["summary"] == ""
                and row.command_metadata["contributor_attestation"] == "")

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
            if not self._matches_public_command(row, metadata):
                raise IntakeCustodyConflict("submission_idempotency_conflict")
            if expected_operation_id is not None and UUID(row.id) != expected_operation_id:
                raise IntakeCustodyConflict("submission_idempotency_conflict")
            result = IntakeReplay(UUID(row.id), row.state, row.failure_code,
                                  row.maximum_raw_bytes, row.raw_sha256, row.raw_byte_count,
                                  await finalization_progress(row, self._events(session), self._deliveries(session)),
                                  await self._accepted_receipt(session, authority, row)
                                  if row.state in {"finalization_pending", "finalized"} else None)
        return result

    async def replay_failure(
        self, metadata: SubmissionIntakeMetadata, *, actor_id: UUID, idempotency_key: UUID,
        operation_id: UUID, checkers: Callable[[AsyncSession], SelectedPreSubmitCoordinationPort],
    ) -> dict:
        """Project retained failure under fresh read authority after replay/terminal observation."""
        async with self._root() as (session, authority):
            repository = SubmissionIntakeRepository(session, self._tasks(session))
            row = await repository._lock(operation_id)
            await authority.authorize_read(IntakeOperationReadFacts(
                UUID(row.id), UUID(row.project_id), UUID(row.task_id), UUID(row.actor_profile_id)))
            if (row.actor_profile_id != str(actor_id) or row.idempotency_key != str(idempotency_key)
                    or not self._matches_public_command(row, metadata)):
                raise IntakeCustodyConflict("submission_idempotency_conflict")
            if row.state in {"finalization_pending", "finalized"}:
                return await self._accepted_receipt(session, authority, row)
            if row.state in {"receiving", "pre_checking"}:
                raise IntakeCustodyConflict("submission_operation_in_progress")
            if (row.raw_sha256 is None or row.raw_byte_count is None) and row.failure_code not in {"revision_deadline_expired", "submission_unavailable"}:
                raise IntakeCustodyConflict("submission_operation_terminal")
            if row.state == "rejected" and row.failure_code == "pre_submission_checker_failed":
                terminal = await checkers(session).read_source_terminal(source_operation_id=operation_id)
                if (terminal is None or terminal.execution is None or terminal.execution.eligible
                        or terminal.lease.reservation.metadata_sha256 != row.metadata_sha256
                        or terminal.lease.reservation.actor_profile_id != actor_id
                        or terminal.lease.reservation.idempotency_key != idempotency_key
                        or terminal.lease.reservation.source != repository._sealed_source(row)):
                    raise IntakeCustodyConflict("intake_pre_result_mismatch")
                failure = SubmissionIntakeFailure(
                    "pre_submission_checker_failed",
                    pre_submission_results=public_pre_submission_results(terminal.execution),
                )
            else:
                code = row.failure_code if row.failure_code in {
                    "submission_packet_invalid", "submission_archive_limit_exceeded",
                    "submission_upload_timeout", "submission_pre_timeout",
                    "submission_infrastructure_unavailable", "revision_deadline_expired",
                    "submission_unavailable", "revision_limit_reached", "revision_context_changed",
                    "revision_context_blocked", "task_submission_predecessor_changed",
                } else "submission_operation_terminal"
                failure = SubmissionIntakeFailure(code)
        # Commit the current read authorization before returning QC feedback.
        raise failure

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
            if original.state in {"cancelled", "abandoned"} and original.failure_code in {"revision_deadline_expired", "submission_unavailable"}:
                return original
            code = "submission_operation_in_progress" if original.state in {"receiving", "pre_checking"} else "submission_operation_terminal"
            raise IntakeCustodyConflict(code)
        if declared_raw_bytes is not None and declared_raw_bytes > original.maximum_raw_bytes:
            raise IntakeCustodyConflict("submission_idempotency_conflict")
        raw = await hash_submission_replay(
            chunks, maximum_raw_bytes=original.maximum_raw_bytes, declared_raw_bytes=declared_raw_bytes,
            idle_timeout_seconds=idle_timeout_seconds, deadline_at=datetime.now(UTC) + replay_duration,
        )
        current = await self._read(metadata, actor_id, idempotency_key, expected_operation_id=original.operation_id)
        if (raw.raw_sha256, raw.raw_byte_count) != (current.raw_sha256, current.raw_byte_count):
            raise IntakeCustodyConflict("submission_idempotency_conflict")
        return current
