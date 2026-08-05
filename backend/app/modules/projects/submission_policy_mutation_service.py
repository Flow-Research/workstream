"""Flush-only submission-policy authority foundation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.runtime import (
    PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION,
    ProjectSubmissionArtifactPolicyMutationResourceContext,
    authorization_resource_digest,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.projects.models import SubmissionPolicyMutationIdempotencyRecord
from app.modules.projects.submission_policy_mutation_repository import (
    SubmissionPolicyMutationReplayRepository,
)


@dataclass(frozen=True, slots=True)
class SubmissionPolicyReplayFacts:
    """Canonical replay facts supplied by later authorized mutation children."""

    actor_profile_id: str
    identity_link_id: str
    service_identity: str | None
    action_id: str
    idempotency_key: UUID | None
    request_digest: str
    resource_context: ProjectSubmissionArtifactPolicyMutationResourceContext
    operation_id: UUID
    project_id: str
    guide_id: str
    source_snapshot_id: str
    policy_id: str
    setup_run_id: str | None
    setup_generation: int
    setup_task_id: UUID | None
    correlation_id: UUID | None


class SubmissionPolicyMutationService:
    """Stage replay custody without owning commit, rollback, or product writes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._replay = SubmissionPolicyMutationReplayRepository(session)

    def _require_root_transaction(self) -> None:
        transaction = self._session.sync_session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise RuntimeError("submission-policy mutation requires one root transaction")

    @staticmethod
    def _replay_values(facts: SubmissionPolicyReplayFacts) -> dict[str, object]:
        resource = facts.resource_context
        try:
            action = ActionId(facts.action_id)
            target_kind = PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION[action]
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid submission-policy replay action") from exc
        if (
            resource.target_kind != target_kind
            or facts.request_digest != resource.request_digest
            or facts.operation_id != resource.operation_id
            or facts.project_id != str(resource.scope_project_id)
            or facts.guide_id != str(resource.guide_id)
            or facts.source_snapshot_id != str(resource.source_snapshot_id)
            or facts.policy_id != str(resource.policy_id)
            or facts.setup_generation != resource.setup_generation
        ):
            raise ValueError("submission-policy replay facts do not match resource context")
        custody = resource.setup_service_custody
        if resource.execution_kind == "setup_service":
            if (
                facts.service_identity != ServiceIdentity.PROJECT_SETUP.value
                or facts.idempotency_key is not None
                or custody is None
                or facts.setup_run_id != str(custody.setup_run_id)
                or facts.setup_task_id != custody.task_id
                or facts.correlation_id != custody.correlation_id
            ):
                raise ValueError("submission-policy service replay custody is invalid")
        elif facts.idempotency_key is None or any(
            value is not None
            for value in (
                facts.service_identity,
                facts.setup_run_id,
                facts.setup_task_id,
                facts.correlation_id,
            )
        ):
            raise ValueError("submission-policy human replay custody is invalid")
        return {
            "actor_profile_id": facts.actor_profile_id,
            "identity_link_id": facts.identity_link_id,
            "service_identity": facts.service_identity,
            "action_id": facts.action_id,
            "idempotency_key": facts.idempotency_key,
            "request_digest": facts.request_digest,
            "resource_context_digest": authorization_resource_digest(resource),
            "resource_context_json": resource.model_dump(mode="json"),
            "operation_id": facts.operation_id,
            "project_id": facts.project_id,
            "guide_id": facts.guide_id,
            "source_snapshot_id": facts.source_snapshot_id,
            "policy_id": facts.policy_id,
            "setup_run_id": facts.setup_run_id,
            "setup_generation": facts.setup_generation,
            "setup_task_id": facts.setup_task_id,
            "correlation_id": facts.correlation_id,
        }

    async def reserve_replay(
        self, facts: SubmissionPolicyReplayFacts
    ) -> tuple[
        Literal["claimed", "mismatch", "pending", "replayed"],
        SubmissionPolicyMutationIdempotencyRecord,
    ]:
        """Reserve replay custody while leaving transaction ownership to the caller."""
        self._require_root_transaction()
        return await self._replay.reserve(**self._replay_values(facts))

    async def complete_replay(
        self,
        facts: SubmissionPolicyReplayFacts,
        *,
        response_json: dict,
        committed_policy_id: str,
        committed_effective_policy_id: str | None = None,
        committed_pre_submit_policy_id: str | None = None,
    ) -> None:
        """Flush one replay completion without committing the caller transaction."""
        self._require_root_transaction()
        values = self._replay_values(facts)
        await self._replay.complete(
            facts.operation_id,
            actor_profile_id=facts.actor_profile_id,
            identity_link_id=facts.identity_link_id,
            service_identity=facts.service_identity,
            action_id=facts.action_id,
            idempotency_key=facts.idempotency_key,
            request_digest=facts.request_digest,
            resource_context_digest=str(values["resource_context_digest"]),
            setup_run_id=facts.setup_run_id,
            setup_generation=facts.setup_generation,
            setup_task_id=facts.setup_task_id,
            correlation_id=facts.correlation_id,
            response_json=response_json,
            committed_policy_id=committed_policy_id,
            committed_effective_policy_id=committed_effective_policy_id,
            committed_pre_submit_policy_id=committed_pre_submit_policy_id,
        )
