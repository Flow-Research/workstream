"""Authorized short-transaction coordinator for hidden guide compilation."""

from __future__ import annotations

from datetime import datetime

from dataclasses import asdict, replace
from typing import Any, Literal
from uuid import UUID, uuid5
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.repository import ProjectRepository

from app.interfaces.project_agents import (
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ProjectGuideCompilationAuthorizationPort,
    ProjectGuideCompilationExecutePersistFacts,
    ProjectGuideCompilationExecutePreflightFacts,
    ProjectGuideCompilationRequestFacts,
    ProjectGuideCompilationRequestOrigin,
    project_guide_compilation_execute_resource_digest,
)

from .request_inputs import (
    CompilationRequestInputs,
    new_compilation_request_operation_id,
)

from .contracts import (
    CompilationAttemptIdentity,
    CompilationDispatchReceipt,
    CompilationExecutionState,
    CompilationOutcomeReceipt,
    CompilationPersistenceReceipt,
    CompilationRecoveryClassification,
    CompilationRequestReceipt,
)
from .models import (
    ProjectGuideCompilationAttempt,
    ProjectGuideCompilationRequestOperation,
)
from .repository import (
    GuideCompilationConcurrencyError,
    GuideCompilationIntegrityError,
    GuideCompilationRepository,
    GuideCompilationStorageError,
)
from .validation import accepted_from_attempt, identity_from_attempt
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.core.hashing import canonical_json_hash


class GuideCompilationService:
    """Own every privileged POL-03B mutation in one fresh root transaction."""

    def __init__(
        self,
        session: AsyncSession,
        authorization: ProjectGuideCompilationAuthorizationPort[Any],
        *,
        request_inputs: CompilationRequestInputs | None = None,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._request_inputs = request_inputs

    async def request_initial(
        self, *, actor: ActorIdentityFacts, setup_run_id: UUID,
        idempotency_key: UUID, inference_required: bool,
    ) -> CompilationRequestReceipt:
        """Request one initial generation using exact saved inputs on replay."""
        self._require_fresh_session()
        if self._request_inputs is None:
            raise GuideCompilationIntegrityError("compilation inputs unavailable")
        async with self._session.begin():
            setup = await self._session.get(ProjectSetupRun, str(setup_run_id))
            if setup is None:
                raise GuideCompilationIntegrityError("compilation setup unavailable")
            await self._authorization.lock_request_scope(actor=actor, project_id=UUID(setup.project_id))
            repository = GuideCompilationRepository(self._session)
            operation = await repository.request_operation_for_setup(
                setup_run_id, setup.setup_generation, "project_manager", lock=False,
            )
            if operation is not None:
                attempt = await repository.attempt(operation.attempt_id, lock=False)
                retained = _request_facts(operation, attempt)
                facts = replace(retained, idempotency_key=idempotency_key,
                                request_id=uuid5(idempotency_key, "guide-compilation-request"))
                identity = identity_from_attempt(attempt)
                configuration = ProjectGuideRuntimeConfiguration.model_validate(attempt.runtime_configuration)
            else:
                context = await self._request_inputs.context_for_setup(self._session, setup)
                identity = CompilationAttemptIdentity.from_context(context)
                configuration = self._request_inputs.runtime_configuration
                facts = ProjectGuideCompilationRequestFacts(
                    **identity.model_dump(), operation_id=uuid5(idempotency_key, "guide-compilation-operation"),
                    request_id=uuid5(idempotency_key, "guide-compilation-request"),
                    idempotency_key=idempotency_key, expected_predecessor_compilation_id=None,
                )
        inputs = replace(self._request_inputs, runtime_configuration=configuration)
        return await GuideCompilationService(self._session, self._authorization, request_inputs=inputs).authorize_request(
            actor=actor, facts=facts, identity=identity,
            origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
            runtime_configuration=configuration, inference_required=inference_required,
        )

    async def request_correction(
        self,
        *,
        actor: ActorIdentityFacts,
        correction_operation_id: UUID,
    ) -> CompilationRequestReceipt:
        """Reuse canonical human request/replay for a committed correction successor."""
        from .correction_request import correction_request_inputs

        self._require_fresh_session()
        if self._request_inputs is None:
            raise GuideCompilationIntegrityError("compilation request inputs unavailable")
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            from .models import ProjectGuideProposalCorrection

            correction = await self._session.get(
                ProjectGuideProposalCorrection, correction_operation_id
            )
            operation = (
                await repository.request_operation_for_setup(
                    UUID(correction.successor_setup_run_id),
                    correction.successor_setup_generation,
                    "project_manager",
                    lock=False,
                )
                if correction is not None
                else None
            )
            if operation is None:
                facts, identity = await correction_request_inputs(
                    self._session,
                    self._request_inputs,
                    correction_operation_id,
                )
            else:
                attempt = await repository.attempt(operation.attempt_id, lock=False)
                facts, identity = _request_facts(operation, attempt), identity_from_attempt(attempt)
        return await self.authorize_request(
            actor=actor,
            facts=facts,
            identity=identity,
            origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
            runtime_configuration=self._request_inputs.runtime_configuration,
        )

    async def authorize_request(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
        identity: CompilationAttemptIdentity,
        origin: ProjectGuideCompilationRequestOrigin,
        runtime_configuration: ProjectGuideRuntimeConfiguration | None,
        inference_required: bool | None = None,
    ) -> CompilationRequestReceipt:
        """Atomically persist an authorized request or recover its receipt."""
        self._require_fresh_session()
        _require_identity_matches(facts, identity)
        try:
            async with self._session.begin():
                repository = GuideCompilationRepository(self._session)
                await self._authorization.validate_request_replay(actor=actor, facts=facts, origin=origin)
                if origin.trigger != "project_manager":
                    raise GuideCompilationIntegrityError("explicit Project Manager request required")
                if (inference_required is not None and
                        (runtime_configuration is None or runtime_configuration.uses_inference != inference_required)):
                    raise GuideCompilationIntegrityError("compilation request mode mismatch")
                existing = await self._existing_request(repository, actor, facts, origin)
                if existing is not None:
                    observed_operation_id = existing.operation_id
                    await self._authorization.validate_request_replay(
                        actor=actor, facts=facts, origin=origin
                    )
                    locked = await repository.matching_request_operation(
                        actor=actor, facts=facts, origin=origin, lock=True
                    )
                    if locked is None or locked.operation_id != observed_operation_id:
                        raise GuideCompilationIntegrityError(
                            "compilation request custody is missing"
                        )
                    return await _request_receipt(repository, locked)
                handle = await self._authorization.prepare_request(
                    actor=actor, facts=facts, origin=origin
                )
                # Match manager mutations and diagnostic reads: AUTH, then
                # Project, then Guide/Setup and the attempt's parent FK locks.
                project = await ProjectRepository(self._session).get_project(
                    str(facts.project_id), for_update=True
                )
                if project is None:
                    raise GuideCompilationIntegrityError("compilation project unavailable")
                prepared_facts = facts
                facts, correction_setup, replay = await self._admit_request(
                    repository, actor, prepared_facts, identity, origin
                )
                if replay is not None:
                    return replay
                receipt = await self._persist_request(
                    repository=repository,
                    handle=handle,
                    actor=actor,
                    prepared_facts=prepared_facts,
                    facts=facts,
                    identity=identity,
                    origin=origin,
                    runtime_configuration=runtime_configuration,
                    correction_setup=correction_setup,
                )
            return receipt
        except GuideCompilationConcurrencyError:
            return await self._recover_request(actor=actor, facts=facts, origin=origin)

    async def _existing_request(self, repository, actor, facts, origin):
        """Discover a direct replay before acquiring AUTH and its operation lock."""
        if facts.operation_id.version != 7:
            return None
        return await repository.matching_request_operation(
            actor=actor, facts=facts, origin=origin, lock=False
        )

    async def _admit_request(self, repository, actor, prepared_facts, identity, origin):
        """Resolve owner-locked inputs or return one exact natural replay receipt."""
        from .correction_request import admit_correction_request

        setup, facts, natural = await admit_correction_request(
            self._session,
            self._request_inputs,
            actor=actor,
            facts=prepared_facts,
            identity=identity,
            operation_id=new_compilation_request_operation_id(),
        )
        if natural is not None:
            receipt = await self._natural_request_replay(
                repository, actor, prepared_facts, origin, natural
            )
            return prepared_facts, None, receipt
        if facts is None:
            raise GuideCompilationIntegrityError("correction compilation request input mismatch")
        return facts, setup, None

    async def _natural_request_replay(
        self, repository, actor, prepared_facts, origin, natural
    ) -> CompilationRequestReceipt:
        """Require exact current caller selectors before returning a natural owner row."""
        exact_facts = replace(prepared_facts, operation_id=natural.operation_id)
        matched = await repository.matching_request_operation(
            actor=actor, facts=exact_facts, origin=origin, lock=True
        )
        if matched is None:
            raise GuideCompilationIntegrityError("compilation request custody is missing")
        await self._authorization.validate_request_replay(
            actor=actor, facts=exact_facts, origin=origin
        )
        return await _request_receipt(repository, matched)

    async def _persist_request(
        self,
        *,
        repository,
        handle,
        actor,
        prepared_facts,
        facts,
        identity,
        origin,
        runtime_configuration,
        correction_setup,
    ) -> CompilationRequestReceipt:
        """Reserve the attempt, consume exact authority, and persist one request operation."""
        if (
            runtime_configuration is None
            or runtime_configuration.instruction_version != identity.instruction_version
        ):
            raise GuideCompilationIntegrityError("compilation instruction version mismatch")
        outcome, attempt = await repository.reserve_attempt(identity, runtime_configuration)
        if outcome == "mismatch":
            raise GuideCompilationIntegrityError("compilation attempt identity mismatch")
        if outcome == "existing":
            raise GuideCompilationConcurrencyError(
                "existing attempt has no authorized request custody"
            )
        event_id = await self._authorization.consume_request(
            handle=handle,
            actor=actor,
            prepared_facts=prepared_facts,
            facts=facts,
            origin=origin,
        )
        operation = await repository.insert_request_operation(
            actor=actor,
            facts=facts,
            origin=origin,
            attempt=attempt,
            authorization_decision_event_id=event_id,
        )
        if correction_setup is not None:
            correction_setup.status = "dispatch_pending"
            correction_setup.current_step = "dispatch"
            await self._session.flush()
        return await _request_receipt(repository, operation)

    async def _lock_execution(
        self,
        repository: GuideCompilationRepository,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
    ) -> tuple[ProjectGuideCompilationRequestOperation, ProjectGuideCompilationAttempt]:
        """Retain service authority and parent custody before compilation children."""
        await self._authorization.authorize_execute_preflight(actor=actor, facts=facts)
        project = await ProjectRepository(self._session).get_project(
            str(facts.project_id), for_update=True
        )
        if project is None:
            raise GuideCompilationIntegrityError("compilation project unavailable")
        return await _locked_exact(repository, facts)

    async def fence_dispatch(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
    ) -> CompilationDispatchReceipt:
        """Commit the conservative may-have-dispatched fence after AUTH preflight."""
        self._require_fresh_session()
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            operation, attempt = await self._lock_execution(repository, actor, facts)
            if attempt.status == "compilation_provider_uncertain":
                return _dispatch_receipt(operation, attempt, dispatch_permitted=False)
            if attempt.status != "compilation_reserved":
                return _dispatch_receipt(
                    operation,
                    attempt,
                    classification=await repository.recovery_classification(attempt.id),
                    dispatch_permitted=False,
                )
            attempt = await repository.mark_provider_uncertain(attempt.id)
            receipt = _dispatch_receipt(operation, attempt, dispatch_permitted=True)
        return receipt

    async def release_no_inference_dispatch(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
        stale_before: datetime | None = None,
    ) -> bool:
        """Reopen a no-inference fence so delivery can retry; report whether it is open."""
        self._require_fresh_session()
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            _operation, attempt = await self._lock_execution(repository, actor, facts)
            attempt = await repository.release_no_inference_fence(
                attempt.id, stale_before=stale_before
            )
            return attempt.status == "compilation_reserved"

    async def record_accepted_result(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
        context: ProjectGuideCompilationContext,
        result: ProjectGuideCompilationResult,
    ) -> CompilationOutcomeReceipt:
        """Record one known, strictly validated provider result."""
        self._require_fresh_session()
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            operation, attempt = await self._lock_execution(repository, actor, facts)
            if attempt.status != "compilation_provider_uncertain":
                raise GuideCompilationIntegrityError("provider outcome is not recordable")
            attempt = await repository.accept_result(
                attempt_id=attempt.id, context=context, result=result
            )
            receipt = _outcome_receipt(operation, attempt)
        return receipt

    async def record_invalid_result(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
        failure_code: str,
    ) -> CompilationOutcomeReceipt:
        """Record one allowlisted terminal invalid-result code."""
        self._require_fresh_session()
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            operation, attempt = await self._lock_execution(repository, actor, facts)
            if attempt.status != "compilation_provider_uncertain":
                raise GuideCompilationIntegrityError("provider outcome is not recordable")
            attempt = await repository.mark_invalid_terminal(
                attempt_id=attempt.id, failure_code=failure_code
            )
            receipt = _outcome_receipt(operation, attempt)
        return receipt

    async def persist_accepted(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
        context: ProjectGuideCompilationContext,
    ) -> CompilationPersistenceReceipt:
        """Consume fresh result-bound authority with immutable persistence."""
        self._require_fresh_session()
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            operation, attempt = await self._lock_execution(repository, actor, facts)
            if attempt.status == "compilation_persisted":
                return await _persisted_receipt(repository, operation, attempt)
            if attempt.status != "provider_result_accepted":
                raise GuideCompilationIntegrityError("attempt is not ready to persist")
            persist_facts = _persist_facts(actor, facts, attempt)
            handle = await self._authorization.prepare_execute_persist(
                actor=actor, facts=persist_facts
            )
            event_id = await self._authorization.consume_execute_persist(
                handle=handle, actor=actor, facts=persist_facts
            )
            compilation = await repository.persist_accepted(
                attempt_id=attempt.id,
                context=context,
                expected_predecessor_id=operation.expected_predecessor_compilation_id,
                actor=actor,
                facts=persist_facts,
                authorization_decision_event_id=event_id,
            )
            receipt = CompilationPersistenceReceipt(
                operation_id=operation.operation_id,
                attempt_id=attempt.id,
                provider_idempotency_key=attempt.provider_idempotency_key,
                classification=CompilationRecoveryClassification.PERSISTED,
                compilation_id=compilation.id,
            )
        return receipt

    async def _recover_request(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
        origin: ProjectGuideCompilationRequestOrigin,
    ) -> CompilationRequestReceipt:
        self._require_fresh_session()
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            natural = await repository.request_operation_for_setup(
                facts.setup_run_id,
                facts.setup_generation,
                origin.trigger,
                lock=False,
            )
            if natural is None:
                raise GuideCompilationIntegrityError(
                    "concurrent request left no durable natural owner"
                )
            exact_facts = replace(facts, operation_id=natural.operation_id)
            operation = await repository.matching_request_operation(
                actor=actor, facts=exact_facts, origin=origin, lock=False
            )
            if operation is None:
                raise GuideCompilationIntegrityError(
                    "concurrent request left no exact durable receipt"
                )
            await self._authorization.validate_request_replay(
                actor=actor,
                facts=exact_facts,
                origin=origin,
            )
            return await _request_receipt(repository, operation)

    def _require_fresh_session(self) -> None:
        if self._session.in_transaction():
            raise GuideCompilationIntegrityError(
                "guide compilation requires a fresh root transaction"
            )


class CompilationExecutionStateUnavailable(RuntimeError):
    """Bounded internal classification for hidden state loading."""

    def __init__(
        self, code: Literal["attempt_unavailable", "context_unavailable", "storage_unavailable"]
    ) -> None:
        super().__init__(code)
        self.code = code


async def load_compilation_execution_state(
    session: AsyncSession, attempt_id: UUID
) -> CompilationExecutionState:
    """Load exact current custody without exposing ORM or accepted output."""
    if session.in_transaction():
        raise GuideCompilationIntegrityError("guide compilation requires a fresh root transaction")
    async with session.begin():
        repository = GuideCompilationRepository(session)
        try:
            attempt = await repository.attempt(attempt_id, lock=True)
            operation = await repository.request_operation_for_attempt(attempt.id, lock=True)
        except GuideCompilationStorageError as exc:
            raise CompilationExecutionStateUnavailable("storage_unavailable") from exc
        except GuideCompilationIntegrityError as exc:
            raise CompilationExecutionStateUnavailable("attempt_unavailable") from exc
        try:
            if operation.request_trigger != "project_manager":
                raise GuideCompilationIntegrityError("explicit Project Manager request required")
            await repository.require_current_setup_lineage(attempt)
            classification = await repository.recovery_classification(attempt.id)
            compilation_id = None
            if classification is CompilationRecoveryClassification.PERSISTED:
                compilation_id = (await repository.persisted_compilation(attempt.id)).id
            configuration = None
            if attempt.runtime_configuration is not None:
                configuration = ProjectGuideRuntimeConfiguration.model_validate(
                    attempt.runtime_configuration
                )
                if (
                    canonical_json_hash(attempt.runtime_configuration)
                    != attempt.runtime_configuration_hash
                ):
                    raise GuideCompilationIntegrityError(
                        "compilation runtime configuration hash mismatch"
                    )
            return CompilationExecutionState(
                identity=identity_from_attempt(attempt),
                preflight_facts=_preflight_facts(operation, attempt),
                classification=classification,
                compilation_id=compilation_id,
                runtime_configuration=configuration,
            )
        except GuideCompilationStorageError as exc:
            raise CompilationExecutionStateUnavailable("storage_unavailable") from exc
        except (GuideCompilationIntegrityError, TypeError, ValueError) as exc:
            raise CompilationExecutionStateUnavailable("context_unavailable") from exc


async def _locked_exact(
    repository: GuideCompilationRepository,
    facts: ProjectGuideCompilationExecutePreflightFacts,
) -> tuple[ProjectGuideCompilationRequestOperation, ProjectGuideCompilationAttempt]:
    attempt = await repository.attempt(facts.attempt_id, lock=True)
    operation = await repository.request_operation_for_attempt(attempt.id, lock=True)
    if operation.request_trigger != "project_manager":
        raise GuideCompilationIntegrityError("explicit Project Manager request required")
    if _preflight_facts(operation, attempt) != facts:
        raise GuideCompilationIntegrityError("compilation execute facts mismatch")
    await repository.require_current_setup_lineage(attempt)
    return operation, attempt


def _request_facts(
    operation: ProjectGuideCompilationRequestOperation,
    attempt: ProjectGuideCompilationAttempt,
) -> ProjectGuideCompilationRequestFacts:
    identity = identity_from_attempt(attempt)
    values = identity.model_dump()
    return ProjectGuideCompilationRequestFacts(
        **values,
        operation_id=operation.operation_id,
        request_id=operation.request_id,
        idempotency_key=operation.idempotency_key,
        expected_predecessor_compilation_id=operation.expected_predecessor_compilation_id,
    )


def _preflight_facts(
    operation: ProjectGuideCompilationRequestOperation,
    attempt: ProjectGuideCompilationAttempt,
) -> ProjectGuideCompilationExecutePreflightFacts:
    request = _request_facts(operation, attempt)
    return ProjectGuideCompilationExecutePreflightFacts(
        **asdict(request),
        attempt_id=attempt.id,
        provider_idempotency_key=attempt.provider_idempotency_key,
    )


def _persist_facts(
    actor: ActorIdentityFacts,
    preflight: ProjectGuideCompilationExecutePreflightFacts,
    attempt: ProjectGuideCompilationAttempt,
) -> ProjectGuideCompilationExecutePersistFacts:
    accepted = accepted_from_attempt(attempt)
    hashes = accepted.component_hashes
    facts = ProjectGuideCompilationExecutePersistFacts(
        **asdict(preflight),
        result_hash=accepted.result_hash,
        sufficiency_component_hash=hashes.sufficiency_hash,
        artifact_policy_component_hash=hashes.artifact_policy_hash,
        requirement_inventory_component_hash=hashes.requirement_inventory_hash,
        pre_submit_policy_component_hash=hashes.pre_submit_hash,
        post_submit_policy_component_hash=hashes.post_submit_hash,
        resource_context_digest="sha256:" + "0" * 64,
    )
    return replace(
        facts,
        resource_context_digest=project_guide_compilation_execute_resource_digest(actor, facts),
    )


def _require_identity_matches(
    facts: ProjectGuideCompilationRequestFacts,
    identity: CompilationAttemptIdentity,
) -> None:
    identity_values = identity.model_dump()
    fact_values = {name: getattr(facts, name) for name in identity_values}
    if fact_values != identity_values:
        raise GuideCompilationIntegrityError("request facts do not match attempt identity")


async def _request_receipt(
    repository: GuideCompilationRepository,
    operation: ProjectGuideCompilationRequestOperation,
) -> CompilationRequestReceipt:
    attempt = await repository.attempt(operation.attempt_id, lock=False)
    return CompilationRequestReceipt(
        operation_id=operation.operation_id,
        attempt_id=attempt.id,
        provider_idempotency_key=attempt.provider_idempotency_key,
        classification=await repository.recovery_classification(attempt.id),
    )


def _dispatch_receipt(
    operation: ProjectGuideCompilationRequestOperation,
    attempt: ProjectGuideCompilationAttempt,
    *,
    classification: CompilationRecoveryClassification = (
        CompilationRecoveryClassification.PROVIDER_UNCERTAIN
    ),
    dispatch_permitted: bool,
) -> CompilationDispatchReceipt:
    return CompilationDispatchReceipt(
        operation_id=operation.operation_id,
        attempt_id=attempt.id,
        provider_idempotency_key=attempt.provider_idempotency_key,
        classification=classification,
        dispatch_permitted=dispatch_permitted,
    )


def _outcome_receipt(
    operation: ProjectGuideCompilationRequestOperation,
    attempt: ProjectGuideCompilationAttempt,
) -> CompilationOutcomeReceipt:
    classification = (
        CompilationRecoveryClassification.ACCEPTED_NOT_PERSISTED
        if attempt.status == "provider_result_accepted"
        else CompilationRecoveryClassification.INVALID_TERMINAL
    )
    return CompilationOutcomeReceipt(
        operation_id=operation.operation_id,
        attempt_id=attempt.id,
        provider_idempotency_key=attempt.provider_idempotency_key,
        classification=classification,
    )


async def _persisted_receipt(
    repository: GuideCompilationRepository,
    operation: ProjectGuideCompilationRequestOperation,
    attempt: ProjectGuideCompilationAttempt,
) -> CompilationPersistenceReceipt:
    compilation = await repository.persisted_compilation(attempt.id)
    return CompilationPersistenceReceipt(
        operation_id=operation.operation_id,
        attempt_id=attempt.id,
        provider_idempotency_key=attempt.provider_idempotency_key,
        classification=CompilationRecoveryClassification.PERSISTED,
        compilation_id=compilation.id,
    )
