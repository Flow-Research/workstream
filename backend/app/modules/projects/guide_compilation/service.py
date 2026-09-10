"""Authorized short-transaction coordinator for hidden guide compilation."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Literal
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.projects.models import ProjectSetupRun

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

from .automatic_request import AutomaticCompilationInputs, automatic_operation_id

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
        automatic_inputs: AutomaticCompilationInputs | None = None,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._automatic_inputs = automatic_inputs

    async def request_automatic(
        self, *, actor: ActorIdentityFacts, setup_run_id: UUID
    ) -> CompilationRequestReceipt:
        """Resolve a source-ready selector without calling or constructing a provider."""
        self._require_fresh_session()
        if self._automatic_inputs is None:
            raise GuideCompilationIntegrityError("automatic compilation inputs unavailable")
        async with self._session.begin():
            setup = await self._session.get(ProjectSetupRun, str(setup_run_id))
            if setup is None:
                raise GuideCompilationIntegrityError("automatic compilation setup unavailable")
            operation = await self._session.scalar(
                select(ProjectGuideCompilationRequestOperation).where(
                    ProjectGuideCompilationRequestOperation.operation_id
                    == automatic_operation_id(setup_run_id, setup.setup_generation)
                )
            )
            if operation is not None:
                repository = GuideCompilationRepository(self._session)
                attempt = await repository.attempt(operation.attempt_id, lock=False)
                facts = _request_facts(operation, attempt)
                identity = identity_from_attempt(attempt)
                origin = ProjectGuideCompilationRequestOrigin(
                    trigger=operation.request_trigger,
                    source_mutation_operation_id=operation.source_mutation_operation_id,
                    source_authorization_decision_event_id=UUID(
                        operation.source_authorization_decision_event_id
                    )
                    if operation.source_authorization_decision_event_id
                    else None,
                )
            else:
                facts, identity, origin = await self._automatic_inputs.resolve(
                    self._session, setup_run_id
                )
        return await self.authorize_request(
            actor=actor,
            facts=facts,
            identity=identity,
            origin=origin,
            runtime_configuration=self._automatic_inputs.runtime_configuration,
        )

    async def authorize_request(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
        identity: CompilationAttemptIdentity,
        origin: ProjectGuideCompilationRequestOrigin,
        runtime_configuration: ProjectGuideRuntimeConfiguration | None,
    ) -> CompilationRequestReceipt:
        """Atomically persist an authorized request or recover its receipt."""
        self._require_fresh_session()
        _require_identity_matches(facts, identity)
        try:
            async with self._session.begin():
                repository = GuideCompilationRepository(self._session)
                existing = await repository.matching_request_operation(
                    actor=actor, facts=facts, origin=origin, lock=True
                )
                if existing is not None:
                    await self._authorization.validate_request_replay(
                        actor=actor,
                        facts=facts,
                        origin=origin,
                    )
                    return await _request_receipt(repository, existing)
                handle = await self._authorization.prepare_request(
                    actor=actor,
                    facts=facts,
                    origin=origin,
                )
                if origin.trigger == "automatic_source_ready":
                    if self._automatic_inputs is None:
                        raise GuideCompilationIntegrityError(
                            "automatic compilation inputs unavailable"
                        )
                    resolved = await self._automatic_inputs.resolve(
                        self._session, facts.setup_run_id
                    )
                    if resolved != (facts, identity, origin):
                        raise GuideCompilationIntegrityError(
                            "automatic compilation request input mismatch"
                        )
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
                receipt = await _request_receipt(repository, operation)
            return receipt
        except GuideCompilationConcurrencyError:
            return await self._recover_request(actor=actor, facts=facts, origin=origin)

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
            operation, attempt = await _locked_exact(repository, facts)
            if attempt.status == "compilation_provider_uncertain":
                return _dispatch_receipt(operation, attempt, dispatch_permitted=False)
            if attempt.status != "compilation_reserved":
                return _dispatch_receipt(
                    operation,
                    attempt,
                    classification=await repository.recovery_classification(attempt.id),
                    dispatch_permitted=False,
                )
            await self._authorization.authorize_execute_preflight(actor=actor, facts=facts)
            attempt = await repository.mark_provider_uncertain(attempt.id)
            receipt = _dispatch_receipt(operation, attempt, dispatch_permitted=True)
        return receipt

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
            operation, attempt = await _locked_exact(repository, facts)
            if attempt.status != "compilation_provider_uncertain":
                raise GuideCompilationIntegrityError("provider outcome is not recordable")
            await self._authorization.authorize_execute_preflight(actor=actor, facts=facts)
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
            operation, attempt = await _locked_exact(repository, facts)
            if attempt.status != "compilation_provider_uncertain":
                raise GuideCompilationIntegrityError("provider outcome is not recordable")
            await self._authorization.authorize_execute_preflight(actor=actor, facts=facts)
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
            operation, attempt = await _locked_exact(repository, facts)
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
            operation = await repository.matching_request_operation(
                actor=actor, facts=facts, origin=origin, lock=False
            )
            if operation is None:
                raise GuideCompilationIntegrityError(
                    "concurrent request left no exact durable receipt"
                )
            await self._authorization.validate_request_replay(
                actor=actor,
                facts=facts,
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
        capability_suggestions_component_hash=hashes.capability_suggestions_hash,
        setup_notes_component_hash=hashes.setup_notes_hash,
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
