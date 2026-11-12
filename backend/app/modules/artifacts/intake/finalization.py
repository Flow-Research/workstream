"""Durable accepted continuation: observe the same source, then commit one T5."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.cancellation import await_completion_preserving_cancellation
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import SealedSourceObservation
from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationAuthorityFacts
from app.modules.artifacts.api.submission_intake import SealedSubmissionSource
from app.modules.artifacts.intake.foreground_admission import IntakeCommitUnknown
from app.modules.artifacts.intake.registration import register_accepted_source
from app.modules.artifacts.intake.repository import IntakeCustodyConflict, SubmissionIntakeRepository
from app.modules.tasks.api import SubmissionCreationRequest, SubmissionCreationResult


@dataclass(frozen=True, slots=True)
class AcceptedContinuation:
    source: SealedSubmissionSource
    lease_id: UUID
    generation: int


def continuation_facts(row, lease_id, generation):
    return SubmissionFinalizationAuthorityFacts(
        operation_id=UUID(row.id), project_id=UUID(row.project_id), task_id=UUID(row.task_id),
        assignment_id=UUID(row.assignment_id), contributor_id=UUID(row.actor_profile_id),
        acceptance_decision_id=UUID(row.acceptance_decision_id),
        accepted_context_sha256=row.accepted_context_sha256, acceptance_receipt_sha256=row.acceptance_receipt_sha256,
        source_sha256=row.accepted_source_sha256, continuation_lease_id=lease_id,
        continuation_generation=generation, phase="claim",
    )


class AcceptedSubmissionFinalization:
    """Keep provider I/O outside TASK locks; finalized replay precedes new claims."""

    def __init__(self, sessions, *, tasks, authorization, submissions, checkers, store, lease_duration):
        if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta(0):
            raise ValueError("finalization lease duration must be explicit and positive")
        self._sessions, self._tasks, self._authorization = sessions, tasks, authorization
        self._submissions, self._store, self._duration = submissions, store, lease_duration
        self._checkers = checkers

    @asynccontextmanager
    async def _root(self):
        session = self._sessions()
        authority = self._authorization(session)
        try:
            await session.begin()
            yield session, authority
            try:
                await await_completion_preserving_cancellation(session.commit())
            except DBAPIError as exc:
                if not exc.connection_invalidated:
                    raise
                raise IntakeCommitUnknown("finalization commit acknowledgement unavailable") from exc
            except Exception as exc:
                raise IntakeCommitUnknown("finalization commit acknowledgement unavailable") from exc
        finally:
            authority.close()
            await await_completion_preserving_cancellation(session.close())

    async def run(self, operation_id: UUID) -> SubmissionCreationResult:
        lease_id = new_record_id()
        try:
            claim = await self._claim(operation_id, lease_id)
        except IntakeCommitUnknown:
            claim = await self._recover_claim(operation_id, lease_id)
        if isinstance(claim, SubmissionCreationResult):
            return claim
        observation = await self._store.observe_sealed_source(claim.source)
        if observation is None:
            raise IntakeCustodyConflict("finalization_source_unavailable")
        try:
            return await self._finalize(operation_id, claim, observation)
        except IntakeCommitUnknown:
            async with self._root() as (session, authority):
                row = await SubmissionIntakeRepository(session, self._tasks(session))._lock(operation_id)
                await authority.authorize()
                return await self._finalized(session, row)

    async def _claim(self, operation_id, lease_id):
        async with self._root() as (session, authority):
            row = await SubmissionIntakeRepository(session, self._tasks(session))._lock(operation_id)
            await authority.authorize()
            if row.state == "finalized":
                return await self._finalized(session, row)
            if row.state != "finalization_pending":
                raise IntakeCustodyConflict("finalization_not_accepted")
            await session.execute(text("SELECT public.require_submission_acceptance(o) "
                "FROM public.submission_intake_operations o WHERE id=:id"), {"id": row.id})
            now = await session.scalar(select(func.clock_timestamp()))
            if row.continuation_expires_at is not None and row.continuation_expires_at > now:
                raise IntakeCustodyConflict("finalization_lease_busy")
            generation = (row.continuation_generation or 0) + 1
            facts = continuation_facts(row, lease_id, generation)
            handle = await authority.prepare(facts=facts, idempotency_key=lease_id)
            decision = await authority.consume(prepared_authorization=handle, facts=facts)
            if not isinstance(decision, UUID):
                raise IntakeCustodyConflict("finalization_authority_unavailable")
            row.continuation_lease_id, row.continuation_generation = str(lease_id), generation
            row.continuation_expires_at, row.continuation_decision_id = now + self._duration, str(decision)
            await session.flush()
            return AcceptedContinuation(SubmissionIntakeRepository._sealed_source(row), lease_id, generation)

    async def _recover_claim(self, operation_id, lease_id):
        async with self._root() as (session, authority):
            row = await SubmissionIntakeRepository(session, self._tasks(session))._lock(operation_id)
            await authority.authorize()
            if row.state == "finalized":
                return await self._finalized(session, row)
            now = await session.scalar(select(func.clock_timestamp()))
            if (row.state != "finalization_pending" or row.continuation_lease_id != str(lease_id)
                    or row.continuation_expires_at is None or row.continuation_expires_at <= now):
                raise IntakeCommitUnknown("finalization claim unavailable")
            await session.execute(text("SELECT public.require_submission_acceptance(o) "
                "FROM public.submission_intake_operations o WHERE id=:id"), {"id": row.id})
            valid = await session.scalar(text("SELECT public.submission_finalization_authority_valid(o,'claim') "
                "FROM public.submission_intake_operations o WHERE id=:id"), {"id": row.id})
            if valid is not True:
                raise IntakeCustodyConflict("finalization_authority_unavailable")
            return AcceptedContinuation(SubmissionIntakeRepository._sealed_source(row), lease_id, row.continuation_generation)

    async def _finalize(self, operation_id: UUID, claim: AcceptedContinuation, observation: SealedSourceObservation):
        async with self._root() as (session, authority):
            tasks = self._tasks(session)
            row = await SubmissionIntakeRepository(session, tasks)._lock(operation_id)
            await authority.authorize()
            if row.state == "finalized":
                return await self._finalized(session, row)
            now = await session.scalar(select(func.clock_timestamp()))
            if (row.state != "finalization_pending" or row.continuation_lease_id != str(claim.lease_id)
                    or row.continuation_generation != claim.generation or row.continuation_expires_at <= now
                    or SubmissionIntakeRepository._sealed_source(row) != claim.source):
                raise IntakeCustodyConflict("finalization_lease_stale")
            terminal = await self._checkers(session).read_accepted_terminal(
                run_id=UUID(row.selected_pre_submit_run_id), source_operation_id=operation_id,
                terminal_digest=row.selected_pre_submit_terminal_sha256,
            )
            admission_id = await register_accepted_source(session, row, observation, terminal)
            metadata = row.command_metadata
            result, decision = await self._submissions(session).create_accepted(
                SubmissionCreationRequest(
                    admission_id=admission_id, task_id=UUID(row.task_id), assignment_id=UUID(row.assignment_id),
                    contributor_id=UUID(row.actor_profile_id),
                    predecessor_submission_id=UUID(metadata["predecessor_submission_id"]) if metadata["predecessor_submission_id"] else None,
                    summary=metadata["summary"], contributor_attestation=metadata["contributor_attestation"],
                ), authority_facts=continuation_facts(row, claim.lease_id, claim.generation),
                finalization_authority=authority, snapshot_sha256=row.locked_context_sha256,
                eligible_status=row.eligible_task_status,
                remediation_id=UUID(row.accepted_context["checker_remediation_manifest_id"])
                if row.accepted_context["checker_remediation_manifest_id"] else None,
            )
            row.state = "finalized"
            row.finalized_at = row.terminal_at = await session.scalar(select(func.clock_timestamp()))
            row.finalized_submission_id, row.finalized_admission_id = str(result.submission_id), str(admission_id)
            row.finalization_decision_id = str(decision)
            await tasks.release(UUID(row.task_id), operation_id)
            await session.flush()
            return result

    async def _finalized(self, session, row):
        if row.state != "finalized":
            raise IntakeCommitUnknown("finalization result unavailable")
        await session.execute(text("SELECT public.require_submission_acceptance(o) "
            "FROM public.submission_intake_operations o WHERE id=:id"), {"id": row.id})
        valid = await session.scalar(text("SELECT public.submission_finalization_authority_valid(o,'claim') "
            "AND public.submission_finalization_authority_valid(o,'commit') "
            "FROM public.submission_intake_operations o WHERE id=:id"), {"id": row.id})
        await session.execute(text("SELECT public.require_source_submission_admission(a) "
            "FROM public.submission_bundle_admissions a WHERE id=:id"), {"id": row.finalized_admission_id})
        if valid is not True:
            raise IntakeCustodyConflict("finalization_result_mismatch")
        return await self._submissions(session).read_finalized(
            UUID(row.finalized_submission_id), UUID(row.finalized_admission_id), UUID(row.acceptance_decision_id),
        )
