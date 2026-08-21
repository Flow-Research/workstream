"""Authorized short-transaction coordinator for hidden guide compilation."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

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
    project_guide_compilation_execute_resource_digest,
)

from .contracts import (
    CompilationAttemptIdentity,
    CompilationDispatchReceipt,
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
)
from .validation import accepted_from_attempt, identity_from_attempt


class GuideCompilationService:
    """Own every privileged POL-03B mutation in one fresh root transaction."""

    def __init__(
        self,
        session: AsyncSession,
        authorization: ProjectGuideCompilationAuthorizationPort[Any],
    ) -> None:
        self._session = session
        self._authorization = authorization

    async def authorize_request(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
        identity: CompilationAttemptIdentity,
    ) -> CompilationRequestReceipt:
        """Atomically persist a PM-authorized request or recover its receipt."""
        self._require_fresh_session()
        _require_identity_matches(facts, identity)
        try:
            async with self._session.begin():
                repository = GuideCompilationRepository(self._session)
                existing = await repository.matching_request_operation(
                    actor=actor, facts=facts, lock=True
                )
                if existing is not None:
                    return await _request_receipt(repository, existing)
                handle = await self._authorization.prepare_request(
                    actor=actor, facts=facts
                )
                outcome, attempt = await repository.reserve_attempt(identity)
                if outcome == "mismatch":
                    raise GuideCompilationIntegrityError(
                        "compilation attempt identity mismatch"
                    )
                if outcome == "existing":
                    raise GuideCompilationConcurrencyError(
                        "existing attempt has no authorized request custody"
                    )
                event_id = await self._authorization.consume_request(
                    handle=handle, actor=actor, facts=facts
                )
                operation = await repository.insert_request_operation(
                    actor=actor,
                    facts=facts,
                    attempt=attempt,
                    authorization_decision_event_id=event_id,
                )
                receipt = await _request_receipt(repository, operation)
            return receipt
        except GuideCompilationConcurrencyError:
            return await self._recover_request(actor=actor, facts=facts)

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
                return _dispatch_receipt(
                    operation, attempt, dispatch_permitted=False
                )
            if attempt.status != "compilation_reserved":
                raise GuideCompilationIntegrityError("attempt cannot be dispatched")
            await self._authorization.authorize_execute_preflight(
                actor=actor, facts=facts
            )
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
            await self._authorization.authorize_execute_preflight(
                actor=actor, facts=facts
            )
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
            await self._authorization.authorize_execute_preflight(
                actor=actor, facts=facts
            )
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
    ) -> CompilationRequestReceipt:
        self._require_fresh_session()
        async with self._session.begin():
            repository = GuideCompilationRepository(self._session)
            operation = await repository.matching_request_operation(
                actor=actor, facts=facts, lock=False
            )
            if operation is None:
                raise GuideCompilationIntegrityError(
                    "concurrent request left no exact durable receipt"
                )
            return await _request_receipt(repository, operation)

    def _require_fresh_session(self) -> None:
        if self._session.in_transaction():
            raise GuideCompilationIntegrityError(
                "guide compilation requires a fresh root transaction"
            )


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
        resource_context_digest=project_guide_compilation_execute_resource_digest(
            actor, facts
        ),
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
    dispatch_permitted: bool,
) -> CompilationDispatchReceipt:
    return CompilationDispatchReceipt(
        operation_id=operation.operation_id,
        attempt_id=attempt.id,
        provider_idempotency_key=attempt.provider_idempotency_key,
        classification=CompilationRecoveryClassification.PROVIDER_UNCERTAIN,
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
