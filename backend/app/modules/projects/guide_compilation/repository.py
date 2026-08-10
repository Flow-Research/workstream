"""Short-transaction repository for hidden guide compilation custody."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.project_agents import (
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ProjectGuideCompilationExecutePersistFacts,
)

from .contracts import (
    CompilationAttemptIdentity,
    CompilationRecoveryClassification,
    accepted_compilation_result,
    validate_accepted_compilation_result,
)
from .models import ProjectGuideCompilation, ProjectGuideCompilationAttempt
from .validation import (
    accepted_from_attempt,
    identity_from_attempt,
    validate_persistence_authority,
    validate_terminal_failure_code,
)


class GuideCompilationIntegrityError(RuntimeError):
    """A durable compilation invariant was absent, stale, or mismatched."""


class GuideCompilationRepository:
    """Persist one hidden attempt and append-only compilation graph."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve_attempt(
        self, identity: CompilationAttemptIdentity
    ) -> tuple[Literal["claimed", "existing", "mismatch"], ProjectGuideCompilationAttempt]:
        """Claim or classify the sole attempt for one setup generation."""
        values = _identity_values(identity)
        values.update(
            id=uuid4(),
            provider_idempotency_key=identity.provider_idempotency_key(),
            status="reserved",
        )
        claimed = await self._session.scalar(
            insert(ProjectGuideCompilationAttempt)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["setup_run_id", "setup_generation"])
            .returning(ProjectGuideCompilationAttempt.id)
        )
        if claimed is not None:
            return "claimed", await self._required_attempt(claimed)
        attempt = await self._session.scalar(
            select(ProjectGuideCompilationAttempt).where(
                ProjectGuideCompilationAttempt.setup_run_id == str(identity.setup_run_id),
                ProjectGuideCompilationAttempt.setup_generation == identity.setup_generation,
            )
        )
        if attempt is None:
            raise GuideCompilationIntegrityError("compilation reservation disappeared")
        outcome = "existing" if _matches(attempt, identity) else "mismatch"
        return outcome, attempt

    async def mark_provider_uncertain(self, attempt_id: UUID) -> ProjectGuideCompilationAttempt:
        """Fence an unknown provider result under the original key."""
        attempt = await self._lock_attempt(attempt_id)
        if attempt.status == "provider_uncertain":
            return attempt
        if attempt.status != "reserved":
            raise GuideCompilationIntegrityError("invalid provider-uncertain transition")
        await self._transition(
            attempt_id,
            expected=("reserved",),
            status="provider_uncertain",
            provider_uncertain_at=datetime.now(UTC),
        )
        return await self._required_attempt(attempt_id)

    async def accept_result(
        self,
        *,
        attempt_id: UUID,
        context: ProjectGuideCompilationContext,
        result: ProjectGuideCompilationResult,
    ) -> ProjectGuideCompilationAttempt:
        """Store one revalidated canonical result before compilation insertion."""
        attempt = await self._lock_attempt(attempt_id)
        identity = identity_from_attempt(attempt)
        accepted = accepted_compilation_result(result)
        validate_accepted_compilation_result(
            identity=identity, context=context, accepted=accepted
        )
        if attempt.status in {"accepted", "persisted"}:
            if accepted_from_attempt(attempt) != accepted:
                raise GuideCompilationIntegrityError("accepted result mismatch")
            return attempt
        if attempt.status not in {"reserved", "provider_uncertain"}:
            raise GuideCompilationIntegrityError("invalid accepted transition")
        await self._transition(
            attempt_id,
            expected=("reserved", "provider_uncertain"),
            status="accepted",
            canonical_result=accepted.canonical_result,
            result_hash=accepted.result_hash,
            component_hashes=accepted.component_hashes.model_dump(mode="json"),
            accepted_at=datetime.now(UTC),
        )
        return await self._required_attempt(attempt_id)

    async def mark_invalid_terminal(
        self, *, attempt_id: UUID, failure_code: str
    ) -> ProjectGuideCompilationAttempt:
        """Terminally consume a generation after invalid or unsafe output."""
        failure_code = validate_terminal_failure_code(failure_code)
        attempt = await self._lock_attempt(attempt_id)
        if attempt.status == "invalid_terminal" and attempt.failure_code == failure_code:
            return attempt
        if attempt.status not in {"reserved", "provider_uncertain"}:
            raise GuideCompilationIntegrityError("invalid terminal transition")
        await self._transition(
            attempt_id,
            expected=("reserved", "provider_uncertain"),
            status="invalid_terminal",
            failure_code=failure_code,
            terminal_at=datetime.now(UTC),
        )
        return await self._required_attempt(attempt_id)

    async def recovery_classification(
        self, attempt_id: UUID
    ) -> CompilationRecoveryClassification:
        """Return one bounded hidden recovery classification."""
        attempt = await self._required_attempt(attempt_id)
        if attempt.status == "accepted":
            return CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED
        return CompilationRecoveryClassification(attempt.status)

    async def persist_accepted(
        self,
        *,
        attempt_id: UUID,
        context: ProjectGuideCompilationContext,
        expected_predecessor_id: UUID | None,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
        authorization_decision_event_id: UUID,
    ) -> ProjectGuideCompilation:
        """CAS-insert one immutable compilation and finish its attempt."""
        attempt = await self._lock_attempt(attempt_id)
        existing = await self._compilation_for_attempt(attempt_id)
        if attempt.status not in {"accepted", "persisted"}:
            raise GuideCompilationIntegrityError("attempt is not ready for persistence")
        try:
            accepted = accepted_from_attempt(attempt)
            identity = identity_from_attempt(attempt)
            validate_accepted_compilation_result(
                identity=identity, context=context, accepted=accepted
            )
            validate_persistence_authority(
                attempt=attempt,
                accepted=accepted,
                actor=actor,
                facts=facts,
                expected_predecessor_id=expected_predecessor_id,
            )
        except ValueError as exc:
            raise GuideCompilationIntegrityError(
                "accepted compilation custody is invalid"
            ) from exc
        if attempt.status == "persisted":
            if existing is None or attempt.persisted_compilation_id != existing.id:
                raise GuideCompilationIntegrityError("persisted compilation is missing")
            return existing
        if existing is not None:
            raise GuideCompilationIntegrityError("attempt is not ready for persistence")
        current = await self._current(identity.project_id, identity.guide_id, lock=True)
        if (current.id if current else None) != expected_predecessor_id:
            raise GuideCompilationIntegrityError("compilation predecessor is stale")
        if current and current.setup_generation >= identity.setup_generation:
            raise GuideCompilationIntegrityError("compilation generation did not advance")
        compilation_id = uuid4()
        compilation = ProjectGuideCompilation(
            id=compilation_id,
            attempt_id=attempt.id,
            **_compilation_identity_values(identity),
            canonical_result=accepted.canonical_result,
            result_hash=accepted.result_hash,
            component_hashes=accepted.component_hashes.model_dump(mode="json"),
            supersedes_compilation_id=expected_predecessor_id,
            created_by_actor_profile_id=str(actor.actor_profile_id),
            created_via_identity_link_id=str(actor.identity_link_id),
            created_by_service_identity=actor.service_identity or "",
            creation_action_id="project.guide_compilation.execute",
            authorization_decision_event_id=str(authorization_decision_event_id),
            authorization_resource_context_digest=facts.resource_context_digest,
        )
        self._session.add(compilation)
        await self._session.flush()
        await self._transition(
            attempt_id,
            expected=("accepted",),
            status="persisted",
            persisted_compilation_id=compilation_id,
            persisted_at=datetime.now(UTC),
        )
        await self._session.refresh(compilation)
        return compilation

    async def _transition(
        self, attempt_id: UUID, *, expected: tuple[str, ...], status: str, **values: object
    ) -> None:
        changed = await self._session.scalar(
            update(ProjectGuideCompilationAttempt)
            .where(
                ProjectGuideCompilationAttempt.id == attempt_id,
                ProjectGuideCompilationAttempt.status.in_(expected),
            )
            .values(status=status, **values)
            .returning(ProjectGuideCompilationAttempt.id)
        )
        if changed is None:
            raise GuideCompilationIntegrityError("compilation transition lost")

    async def _lock_attempt(self, attempt_id: UUID) -> ProjectGuideCompilationAttempt:
        attempt = await self._session.scalar(
            select(ProjectGuideCompilationAttempt)
            .where(ProjectGuideCompilationAttempt.id == attempt_id)
            .with_for_update()
        )
        if attempt is None:
            raise GuideCompilationIntegrityError("compilation attempt was not found")
        return attempt

    async def _required_attempt(self, attempt_id: UUID) -> ProjectGuideCompilationAttempt:
        attempt = await self._session.get(ProjectGuideCompilationAttempt, attempt_id)
        if attempt is None:
            raise GuideCompilationIntegrityError("compilation attempt disappeared")
        await self._session.refresh(attempt)
        return attempt

    async def _compilation_for_attempt(
        self, attempt_id: UUID
    ) -> ProjectGuideCompilation | None:
        return await self._session.scalar(
            select(ProjectGuideCompilation).where(
                ProjectGuideCompilation.attempt_id == attempt_id
            )
        )

    async def _current(
        self, project_id: UUID, guide_id: UUID, *, lock: bool
    ) -> ProjectGuideCompilation | None:
        child = ProjectGuideCompilation.__table__.alias("compilation_child")
        statement = select(ProjectGuideCompilation).where(
            ProjectGuideCompilation.project_id == str(project_id),
            ProjectGuideCompilation.guide_id == str(guide_id),
            ~exists(
                select(1).where(
                    child.c.supersedes_compilation_id == ProjectGuideCompilation.id
                )
            ),
        )
        if lock:
            statement = statement.with_for_update()
        rows = list((await self._session.scalars(statement)).all())
        if len(rows) > 1:
            raise GuideCompilationIntegrityError("multiple current compilations")
        return rows[0] if rows else None


def _identity_values(identity: CompilationAttemptIdentity) -> dict[str, object]:
    values = identity.model_dump(mode="json")
    values.update(
        project_id=str(identity.project_id),
        guide_id=str(identity.guide_id),
        source_snapshot_id=str(identity.source_snapshot_id),
        setup_run_id=str(identity.setup_run_id),
    )
    return values


def _matches(
    attempt: ProjectGuideCompilationAttempt, identity: CompilationAttemptIdentity
) -> bool:
    return identity_from_attempt(attempt) == identity and (
        attempt.provider_idempotency_key == identity.provider_idempotency_key()
    )


def _compilation_identity_values(identity: CompilationAttemptIdentity) -> dict[str, object]:
    return {
        "project_id": str(identity.project_id),
        "guide_id": str(identity.guide_id),
        "guide_version": identity.guide_version,
        "source_snapshot_id": str(identity.source_snapshot_id),
        "source_snapshot_hash": identity.source_snapshot_hash,
        "setup_run_id": str(identity.setup_run_id),
        "setup_generation": identity.setup_generation,
        "canonical_input_hash": identity.canonical_input_hash,
        "guide_material_hash": identity.guide_material_hash,
        "pre_catalogue_manifest_hash": identity.pre_catalogue_manifest_hash,
        "post_catalogue_manifest_hash": identity.post_catalogue_manifest_hash,
        "agent_identity": identity.agent_identity,
        "agent_version": identity.agent_version,
        "instruction_version": identity.instruction_version,
    }
