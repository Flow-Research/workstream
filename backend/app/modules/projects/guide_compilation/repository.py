"""Short-transaction repository for hidden guide compilation custody."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import integrity_constraint_name
from app.interfaces.project_agents import (
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ProjectGuideCompilationExecutePersistFacts,
    ProjectGuideCompilationRequestFacts,
    project_guide_compilation_facts_digest,
)
from app.modules.projects.models import GuideSourceSnapshot, ProjectGuide, ProjectSetupRun

from .contracts import (
    CompilationAttemptIdentity,
    CompilationRecoveryClassification,
    accepted_compilation_result,
    validate_accepted_compilation_result,
)
from .models import (
    ProjectGuideCompilation,
    ProjectGuideCompilationAttempt,
    ProjectGuideCompilationRequestOperation,
)
from .validation import (
    accepted_from_attempt,
    identity_from_attempt,
    validate_persistence_authority,
    validate_terminal_failure_code,
)


class GuideCompilationIntegrityError(RuntimeError):
    """A durable compilation invariant was absent, stale, or mismatched."""


class GuideCompilationConcurrencyError(GuideCompilationIntegrityError):
    """A concurrent lineage append won; callers must reload the tip and retry."""


class GuideCompilationStorageError(GuideCompilationIntegrityError):
    """An unexpected database failure prevented a custody write."""


_LINEAGE_CONSTRAINTS = frozenset(
    {
        "uq_project_guide_compilation_predecessor",
        "uq_project_guide_compilation_root",
    }
)
_REQUEST_CONSTRAINTS = frozenset(
    {
        "pk_project_guide_compilation_request_operations",
        "uq_compilation_request_actor_request",
        "uq_compilation_request_actor_key",
        "uq_compilation_request_attempt",
        "uq_compilation_request_authorization_event",
    }
)
_BLOCKED_SETUP_STATUSES = frozenset(
    {
        "enqueue_failed",
        "enqueue_identity_mismatch",
        "sufficiency_blocked",
        "post_submit_setup_blocked",
        "setup_blocked",
        "failed",
    }
)


def _persistence_error(exc: DBAPIError) -> GuideCompilationIntegrityError:
    """Classify a database write failure without leaking driver exceptions."""
    if integrity_constraint_name(exc) in _LINEAGE_CONSTRAINTS:  # type: ignore[arg-type]
        return GuideCompilationConcurrencyError(
            "concurrent compilation append won; reload the lineage tip and retry"
        )
    return GuideCompilationStorageError(
        "compilation persistence failed before durable custody"
    )


class GuideCompilationRepository:
    """Persist one hidden attempt and append-only compilation graph."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind repository operations to the caller-owned transaction."""
        self._session = session

    async def matching_request_operation(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
        lock: bool = False,
    ) -> ProjectGuideCompilationRequestOperation | None:
        """Load one operation touching any replay identity and require exactness."""
        statement = select(ProjectGuideCompilationRequestOperation).where(
            or_(
                ProjectGuideCompilationRequestOperation.operation_id == facts.operation_id,
                (
                    ProjectGuideCompilationRequestOperation.actor_profile_id
                    == str(actor.actor_profile_id)
                )
                & (ProjectGuideCompilationRequestOperation.request_id == facts.request_id),
                (
                    ProjectGuideCompilationRequestOperation.actor_profile_id
                    == str(actor.actor_profile_id)
                )
                & (
                    ProjectGuideCompilationRequestOperation.idempotency_key
                    == facts.idempotency_key
                ),
            )
        )
        if lock:
            statement = statement.with_for_update()
        rows = list((await self._session.scalars(statement)).all())
        if not rows:
            return None
        if len(rows) != 1 or not _request_matches(rows[0], actor, facts):
            raise GuideCompilationIntegrityError("compilation request replay mismatch")
        return rows[0]

    async def request_operation_for_attempt(
        self, attempt_id: UUID, *, lock: bool
    ) -> ProjectGuideCompilationRequestOperation:
        """Load the exact immutable request custody for an attempt."""
        statement = select(ProjectGuideCompilationRequestOperation).where(
            ProjectGuideCompilationRequestOperation.attempt_id == attempt_id
        )
        if lock:
            statement = statement.with_for_update()
        operation = await self._session.scalar(statement)
        if operation is None:
            raise GuideCompilationIntegrityError("compilation request custody is missing")
        return operation

    async def insert_request_operation(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
        attempt: ProjectGuideCompilationAttempt,
        authorization_decision_event_id: UUID,
    ) -> ProjectGuideCompilationRequestOperation:
        """Insert one authorized operation receipt bound to exact custody."""
        operation = ProjectGuideCompilationRequestOperation(
            operation_id=facts.operation_id,
            request_id=facts.request_id,
            idempotency_key=facts.idempotency_key,
            actor_profile_id=str(actor.actor_profile_id),
            identity_link_id=str(actor.identity_link_id),
            project_id=str(facts.project_id),
            guide_id=str(facts.guide_id),
            source_snapshot_id=str(facts.source_snapshot_id),
            setup_run_id=str(facts.setup_run_id),
            setup_generation=facts.setup_generation,
            expected_predecessor_compilation_id=facts.expected_predecessor_compilation_id,
            request_facts_digest=project_guide_compilation_facts_digest(facts),
            attempt_id=attempt.id,
            authorization_decision_event_id=str(authorization_decision_event_id),
        )
        self._session.add(operation)
        try:
            await self._session.flush()
        except DBAPIError as exc:
            if integrity_constraint_name(exc) in _REQUEST_CONSTRAINTS:  # type: ignore[arg-type]
                raise GuideCompilationConcurrencyError(
                    "concurrent compilation request won; reload its exact receipt"
                ) from exc
            raise GuideCompilationStorageError(
                "compilation request custody failed before commit"
            ) from exc
        return operation

    async def attempt(
        self, attempt_id: UUID, *, lock: bool
    ) -> ProjectGuideCompilationAttempt:
        """Load an attempt, optionally holding its row for a root transaction."""
        return (
            await self._lock_attempt(attempt_id)
            if lock
            else await self._required_attempt(attempt_id)
        )

    async def require_current_setup_lineage(
        self, attempt: ProjectGuideCompilationAttempt
    ) -> None:
        """Lock and require the attempt's exact active, latest setup lineage."""
        guide = await self._session.scalar(
            select(ProjectGuide)
            .where(
                ProjectGuide.id == attempt.guide_id,
                ProjectGuide.project_id == attempt.project_id,
            )
            .with_for_update()
        )
        if guide is None or guide.version != attempt.guide_version or guide.status != "draft":
            raise GuideCompilationIntegrityError("compilation guide lineage is stale")

        setup = await self._session.scalar(
            select(ProjectSetupRun)
            .where(ProjectSetupRun.id == attempt.setup_run_id)
            .with_for_update()
        )
        snapshot = await self._session.scalar(
            select(GuideSourceSnapshot).where(
                GuideSourceSnapshot.id == attempt.source_snapshot_id
            )
        )
        if (
            setup is None
            or snapshot is None
            or setup.project_id != attempt.project_id
            or setup.guide_id != attempt.guide_id
            or setup.guide_version != attempt.guide_version
            or setup.source_snapshot_id != attempt.source_snapshot_id
            or setup.source_snapshot_hash != attempt.source_snapshot_hash
            or setup.setup_generation != attempt.setup_generation
            or snapshot.project_id != attempt.project_id
            or snapshot.guide_id != attempt.guide_id
            or snapshot.guide_version != attempt.guide_version
            or snapshot.bundle_hash != attempt.source_snapshot_hash
            or setup.status in _BLOCKED_SETUP_STATUSES
        ):
            raise GuideCompilationIntegrityError("compilation setup lineage is stale")

        latest_generation = await self._session.scalar(
            select(ProjectSetupRun.setup_generation)
            .where(
                ProjectSetupRun.project_id == attempt.project_id,
                ProjectSetupRun.guide_id == attempt.guide_id,
            )
            .order_by(ProjectSetupRun.setup_generation.desc())
            .limit(1)
        )
        if latest_generation != attempt.setup_generation:
            raise GuideCompilationIntegrityError("compilation setup generation is stale")

    async def current_compilation(
        self, project_id: UUID, guide_id: UUID, *, lock: bool
    ) -> ProjectGuideCompilation | None:
        """Return the exact current lineage tip."""
        return await self._current(project_id, guide_id, lock=lock)

    async def persisted_compilation(
        self, attempt_id: UUID
    ) -> ProjectGuideCompilation:
        """Return an attempt's required immutable compilation."""
        compilation = await self._compilation_for_attempt(attempt_id)
        if compilation is None:
            raise GuideCompilationIntegrityError("persisted compilation is missing")
        return compilation

    async def reserve_attempt(
        self, identity: CompilationAttemptIdentity
    ) -> tuple[Literal["claimed", "existing", "mismatch"], ProjectGuideCompilationAttempt]:
        """Claim or classify the sole attempt for one setup generation."""
        values = _identity_values(identity)
        values.update(
            id=uuid4(),
            provider_idempotency_key=identity.provider_idempotency_key(),
            status="compilation_reserved",
        )
        claimed = await self._session.scalar(
            insert(ProjectGuideCompilationAttempt)
            .values(**values)
            .on_conflict_do_nothing()
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
        if attempt.status == "compilation_provider_uncertain":
            return attempt
        if attempt.status != "compilation_reserved":
            raise GuideCompilationIntegrityError("invalid provider-uncertain transition")
        await self._transition(
            attempt_id,
            expected=("compilation_reserved",),
            status="compilation_provider_uncertain",
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
        try:
            identity = identity_from_attempt(attempt)
            accepted = accepted_compilation_result(result)
            validate_accepted_compilation_result(
                identity=identity, context=context, accepted=accepted
            )
        except ValueError as exc:
            raise GuideCompilationIntegrityError(
                "accepted compilation result is invalid"
            ) from exc
        if attempt.status in {"provider_result_accepted", "compilation_persisted"}:
            if accepted_from_attempt(attempt) != accepted:
                raise GuideCompilationIntegrityError("accepted result mismatch")
            return attempt
        if attempt.status not in {
            "compilation_reserved",
            "compilation_provider_uncertain",
        }:
            raise GuideCompilationIntegrityError("invalid accepted transition")
        await self._transition(
            attempt_id,
            expected=("compilation_reserved", "compilation_provider_uncertain"),
            status="provider_result_accepted",
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
        try:
            failure_code = validate_terminal_failure_code(failure_code)
        except ValueError as exc:
            raise GuideCompilationIntegrityError(
                "terminal compilation failure code is invalid"
            ) from exc
        attempt = await self._lock_attempt(attempt_id)
        if (
            attempt.status == "compilation_invalid_terminal"
            and attempt.failure_code == failure_code
        ):
            return attempt
        if attempt.status not in {
            "compilation_reserved",
            "compilation_provider_uncertain",
        }:
            raise GuideCompilationIntegrityError("invalid terminal transition")
        await self._transition(
            attempt_id,
            expected=("compilation_reserved", "compilation_provider_uncertain"),
            status="compilation_invalid_terminal",
            failure_code=failure_code,
            terminal_at=datetime.now(UTC),
        )
        return await self._required_attempt(attempt_id)

    async def recovery_classification(
        self, attempt_id: UUID
    ) -> CompilationRecoveryClassification:
        """Return one bounded hidden recovery classification."""
        attempt = await self._required_attempt(attempt_id)
        if attempt.status == "provider_result_accepted":
            return CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED
        if attempt.status == "compilation_provider_uncertain":
            return CompilationRecoveryClassification.PROVIDER_UNCERTAIN
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
        if attempt.status not in {"provider_result_accepted", "compilation_persisted"}:
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
            assert actor.service_identity is not None
        except ValueError as exc:
            raise GuideCompilationIntegrityError(
                "accepted compilation custody is invalid"
            ) from exc
        if attempt.status == "compilation_persisted":
            if existing is None or attempt.persisted_compilation_id != existing.id:
                raise GuideCompilationIntegrityError("persisted compilation is missing")
            return existing
        if existing is not None:
            raise GuideCompilationIntegrityError("attempt is not ready for persistence")
        current = await self._current(identity.project_id, identity.guide_id, lock=True)
        if (current.id if current else None) != expected_predecessor_id:
            raise GuideCompilationConcurrencyError(
                "compilation predecessor is stale; reload the lineage tip and retry"
            )
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
            created_by_service_identity=actor.service_identity,
            creation_action_id="project.guide_compilation.execute",
            authorization_decision_event_id=str(authorization_decision_event_id),
            authorization_resource_context_digest=facts.resource_context_digest,
        )
        self._session.add(compilation)
        try:
            await self._session.flush()
        except DBAPIError as exc:
            raise _persistence_error(exc) from exc
        await self._transition(
            attempt_id,
            expected=("provider_result_accepted",),
            status="compilation_persisted",
            persisted_compilation_id=compilation_id,
            persisted_at=datetime.now(UTC),
        )
        await self._session.refresh(compilation)
        return compilation

    async def _transition(
        self, attempt_id: UUID, *, expected: tuple[str, ...], status: str, **values: object
    ) -> None:
        """Apply one compare-and-set attempt transition or fail closed."""
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
        """Lock and return the exact durable attempt."""
        attempt = await self._session.scalar(
            select(ProjectGuideCompilationAttempt)
            .where(ProjectGuideCompilationAttempt.id == attempt_id)
            .with_for_update()
        )
        if attempt is None:
            raise GuideCompilationIntegrityError("compilation attempt was not found")
        return attempt

    async def _required_attempt(self, attempt_id: UUID) -> ProjectGuideCompilationAttempt:
        """Load one required attempt and refresh its database-owned state."""
        attempt = await self._session.get(
            ProjectGuideCompilationAttempt,
            attempt_id,
            populate_existing=True,
        )
        if attempt is None:
            raise GuideCompilationIntegrityError("compilation attempt disappeared")
        return attempt

    async def _compilation_for_attempt(
        self, attempt_id: UUID
    ) -> ProjectGuideCompilation | None:
        """Return the immutable compilation already owned by an attempt."""
        return await self._session.scalar(
            select(ProjectGuideCompilation).where(
                ProjectGuideCompilation.attempt_id == attempt_id
            )
        )

    async def _current(
        self, project_id: UUID, guide_id: UUID, *, lock: bool
    ) -> ProjectGuideCompilation | None:
        """Return the sole unsuperseded compilation, optionally locked."""
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
    """Map validated attempt identity into explicit database values."""
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
    """Return whether a row retains the exact identity and provider key."""
    return identity_from_attempt(attempt) == identity and (
        attempt.provider_idempotency_key == identity.provider_idempotency_key()
    )


def _request_matches(
    operation: ProjectGuideCompilationRequestOperation,
    actor: ActorIdentityFacts,
    facts: ProjectGuideCompilationRequestFacts,
) -> bool:
    """Require every immutable replay selector and the complete facts digest."""
    return (
        operation.operation_id == facts.operation_id
        and operation.request_id == facts.request_id
        and operation.idempotency_key == facts.idempotency_key
        and operation.actor_profile_id == str(actor.actor_profile_id)
        and operation.identity_link_id == str(actor.identity_link_id)
        and operation.project_id == str(facts.project_id)
        and operation.guide_id == str(facts.guide_id)
        and operation.source_snapshot_id == str(facts.source_snapshot_id)
        and operation.setup_run_id == str(facts.setup_run_id)
        and operation.setup_generation == facts.setup_generation
        and operation.expected_predecessor_compilation_id
        == facts.expected_predecessor_compilation_id
        and operation.request_facts_digest
        == project_guide_compilation_facts_digest(facts)
    )


def _compilation_identity_values(identity: CompilationAttemptIdentity) -> dict[str, object]:
    """Map immutable compilation lineage fields from the attempt identity."""
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
