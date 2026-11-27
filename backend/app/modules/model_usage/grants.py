"""Bounded private session grants; each paid effect remains in the call ledger."""

import hashlib
import json
import re
import secrets
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.interfaces.external_checker_execution import ExternalCheckerModelGrant
from app.modules.model_usage.api import (
    ModelCallCurrentExecutionPort,
    ModelCallExecutionFacts,
    ModelCallEffectAuthorityFacts,
    ModelCallUnavailable,
    ModelPaidSlotKey,
    model_action_digest,
)
from app.modules.model_usage.api import (
    ModelInvocationGrantAuthorityPort,
    ModelInvocationGrantFacts,
)
from app.modules.model_usage.repository import require_model_call_transaction
from app.modules.model_usage.models import (
    CheckerModelInvocationGrant,
    CheckerModelInvocationGrantCall,
)


def model_grant_token_hash(token: str) -> str:
    """Hash a closed short-lived capability with an explicit domain separator."""
    if type(token) is not str or re.fullmatch(r"model_[0-9a-f]{32}", token) is None:
        raise ModelCallUnavailable("model_grant_unavailable")
    return (
        "sha256:"
        + hashlib.sha256(b"workstream.checker.model-grant.v1\0" + token.encode("ascii")).hexdigest()
    )


class ModelInvocationGrants:
    """Issue invocation custody and bind each sequential call in caller transactions."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authority: ModelInvocationGrantAuthorityPort,
        current: ModelCallCurrentExecutionPort,
    ):
        self._session, self._authority, self._current = session, authority, current

    async def issue(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        external_request_digest: str,
        *,
        registry_entry_id: UUID,
    ) -> ExternalCheckerModelGrant:
        """Authorize current binding before creating one private random capability."""
        require_model_call_transaction(self._session)
        execution = ModelCallExecutionFacts.model_validate(execution)
        slot = ModelPaidSlotKey.model_validate(slot)
        token = "model_" + secrets.token_hex(16)
        grant = ExternalCheckerModelGrant(token, external_request_digest)
        token_hash = model_grant_token_hash(token)
        evidence = await self._authority.authorize_grant(
            execution,
            slot,
            external_request_digest,
            token_hash,
        )
        facts = {
            "execution": execution.model_dump(mode="json"),
            "slot": slot.model_dump(mode="json"),
            "external_request_digest": external_request_digest,
            "token_hash": token_hash,
        }
        if evidence.facts_digest != model_action_digest("grant", facts):
            raise ModelCallUnavailable("model_grant_authority_unavailable")
        live_until = await self._current.require_current(execution, slot)
        if live_until is None or live_until < execution.worker_lease_expires_at:
            raise ModelCallUnavailable("model_grant_unavailable")
        self._session.add(
            CheckerModelInvocationGrant(
                id=str(new_record_id()),
                token_hash=token_hash,
                project_id=str(execution.project_id),
                checker_run_id=str(execution.checker_run_id),
                registry_entry_id=registry_entry_id,
                execution_facts=execution.model_dump(mode="json"),
                paid_slot=slot.model_dump(mode="json"),
                external_request_digest=external_request_digest,
                expires_at=live_until,
                authorization_evidence_id=str(evidence.evidence_id),
            )
        )
        await self._session.flush()
        return grant

    async def resolve(self, token: str, request_digest: str) -> ModelInvocationGrantFacts:
        """Select concealed capability facts; this lookup does not grant model authority."""
        require_model_call_transaction(self._session)
        token_hash = model_grant_token_hash(token)
        row = await self._session.scalar(
            select(CheckerModelInvocationGrant).where(
                CheckerModelInvocationGrant.token_hash == token_hash,
                CheckerModelInvocationGrant.external_request_digest == request_digest,
                CheckerModelInvocationGrant.expires_at > func.clock_timestamp(),
            )
        )
        if row is None:
            raise ModelCallUnavailable("model_grant_unavailable")
        execution = ModelCallExecutionFacts.model_validate_json(json.dumps(row.execution_facts))
        slot = ModelPaidSlotKey.model_validate_json(json.dumps(row.paid_slot))
        if (
            str(execution.project_id) != row.project_id
            or str(execution.checker_run_id) != row.checker_run_id
            or execution.worker_lease_expires_at > row.expires_at
        ):
            raise ModelCallUnavailable("model_grant_unavailable")
        return ModelInvocationGrantFacts(
            token_hash=token_hash,
            external_request_digest=request_digest,
            execution=execution,
            slot=slot,
            registry_entry_id=UUID(str(row.registry_entry_id)),
        )

    async def consume_prepared(
        self,
        facts: ModelInvocationGrantFacts,
        *,
        call_index: int,
        request_sha256: str,
        prepared_attempt_id: UUID,
    ) -> None:
        """Bind one sequential call after preparation in the same owner transaction."""
        from app.modules.model_usage.repository import ModelCallRepository

        require_model_call_transaction(self._session)
        if re.fullmatch(r"sha256:[0-9a-f]{64}", request_sha256) is None:
            raise ModelCallUnavailable("model_grant_unavailable")
        if type(call_index) is not int or not 0 <= call_index <= 99:
            raise ModelCallUnavailable("model_grant_unavailable")
        selected_slot = facts.slot.model_copy(update={"slot_index": call_index})
        repo = ModelCallRepository(self._session)
        await repo.lock_envelope_scope(selected_slot)
        if await repo.envelope(selected_slot, lock=True) is None:
            raise ModelCallUnavailable("model_grant_unavailable")
        await repo.lock_slot_scope(selected_slot)
        slot = await repo.slot(selected_slot, lock=True)
        attempt = await repo.attempt(prepared_attempt_id, lock=True)
        if (
            slot is None
            or attempt is None
            or (attempt.checker_slot_id != slot.id or attempt.request_sha256 != request_sha256)
        ):
            raise ModelCallUnavailable("model_grant_unavailable")
        row = await self._session.scalar(
            select(CheckerModelInvocationGrant)
            .where(
                CheckerModelInvocationGrant.token_hash == facts.token_hash,
                CheckerModelInvocationGrant.external_request_digest
                == facts.external_request_digest,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = await self._session.scalar(select(func.clock_timestamp()))
        if (
            row is None
            or row.expires_at <= now
            or (
                row.execution_facts != facts.execution.model_dump(mode="json")
                or row.paid_slot != facts.slot.model_dump(mode="json")
            )
        ):
            raise ModelCallUnavailable("model_grant_unavailable")
        existing = await self._session.get(
            CheckerModelInvocationGrantCall,
            {"grant_id": row.id, "call_index": call_index},
        )
        if existing is not None:
            if (
                existing.attempt_id != str(prepared_attempt_id)
                or existing.request_sha256 != request_sha256
            ):
                raise ModelCallUnavailable("model_grant_unavailable")
            return
        self._session.add(
            CheckerModelInvocationGrantCall(
                grant_id=row.id,
                call_index=call_index,
                attempt_id=str(prepared_attempt_id),
                request_sha256=request_sha256,
            )
        )
        await self._session.flush()

    async def completed_effects(
        self,
        token: str,
        request_digest: str,
        execution: ModelCallExecutionFacts,
    ) -> tuple[ModelCallEffectAuthorityFacts, ...]:
        """Select all session effects; the ledger freshly authorizes each completed read."""
        from app.modules.model_usage.models import CheckerModelUsageSlot, ModelUsageEffect

        require_model_call_transaction(self._session)
        row = await self._session.scalar(
            select(CheckerModelInvocationGrant).where(
                CheckerModelInvocationGrant.token_hash == model_grant_token_hash(token),
                CheckerModelInvocationGrant.external_request_digest == request_digest,
                CheckerModelInvocationGrant.expires_at > func.clock_timestamp(),
            )
        )
        if row is None or row.execution_facts != execution.model_dump(mode="json"):
            raise ModelCallUnavailable("model_grant_completion_unavailable")
        calls = (
            await self._session.execute(
                select(CheckerModelInvocationGrantCall, ModelUsageEffect, CheckerModelUsageSlot)
                .join(
                    ModelUsageEffect,
                    ModelUsageEffect.id == CheckerModelInvocationGrantCall.attempt_id,
                )
                .join(
                    CheckerModelUsageSlot,
                    CheckerModelUsageSlot.id == ModelUsageEffect.checker_slot_id,
                )
                .where(CheckerModelInvocationGrantCall.grant_id == row.id)
                .order_by(CheckerModelInvocationGrantCall.call_index)
            )
        ).all()
        if any(
            call.call_index != index
            or attempt.request_sha256 != call.request_sha256
            or attempt.state != "completed"
            or slot.slot_index != index
            for index, (call, attempt, slot) in enumerate(calls)
        ):
            raise ModelCallUnavailable("model_grant_completion_unavailable")
        base_slot = ModelPaidSlotKey.model_validate_json(json.dumps(row.paid_slot))
        return tuple(
            ModelCallEffectAuthorityFacts(
                project_id=execution.project_id,
                task_id=execution.task_id,
                slot_id=UUID(attempt.checker_slot_id),
                slot_key=base_slot.model_copy(update={"slot_index": call.call_index}),
                attempt_id=UUID(attempt.id),
                internal_call_request_id=UUID(attempt.internal_call_request_id),
            )
            for call, attempt, _slot in calls
        )
