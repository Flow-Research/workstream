"""Canonical fake owner boundaries for real MODEL-USAGE PostgreSQL tests."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.authorization.domain.model_usage import (
    BUDGET_CONFIGURE,
    COMPLETE,
    DISPATCH,
    OBSERVE,
    PREPARE,
    PROFILE_PROVISION,
    RECOVER,
    RECOVERY_CHILD_AUTHORIZE,
    SETUP_COMPLETE,
    SETUP_DISPATCH,
    SETUP_OBSERVE,
    SETUP_PREPARE,
    ModelCallCompleteAuthorityFacts,
    ModelCallDispatchAuthorityFacts,
    ModelCallObserveAuthorityFacts,
    ModelCallPrepareAuthorityFacts,
    ModelCallRecoverAuthorityFacts,
    ModelCallRecoveryChildAuthorityFacts,
    SetupModelCompleteAuthorityFacts,
    SetupModelDispatchAuthorityFacts,
    SetupModelObserveAuthorityFacts,
    SetupModelPrepareAuthorityFacts,
    checker_model_call_resource,
    project_model_admin_resource,
    setup_model_usage_resource,
)
from app.modules.authorization.domain.audit_targets import project_authority_audit_target
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.model_usage.api import (
    ModelActionEvidence,
    ModelCallUnavailable,
    ModelProfileSelector,
    SetupModelOwnerProfile,
    model_action_digest,
)


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


@dataclass
class BoundaryPorts:
    decisions: dict[str, UUID] = field(default_factory=dict)
    fresh_authority_evidence: bool = True
    request_checks: int = 0
    response_checks: int = 0
    current_checks: int = 0
    events: list[str] = field(default_factory=list)
    corrupt_admin_receipt: bool = False
    corrupt_runtime_receipt_action: str | None = None
    terminal_receipt_change: str | None = None

    def _decision(self, action: str, facts: object) -> ModelActionEvidence:
        self.events.append(action)
        digest = model_action_digest(action, facts)
        evidence_id = (
            new_record_id()
            if self.fresh_authority_evidence
            else self.decisions.setdefault(digest, new_record_id())
        )
        return ModelActionEvidence(evidence_id=evidence_id, facts_digest=digest)

    async def authorize_profile(self, facts):
        return self._decision("profile", facts)

    async def authorize_budget(self, facts):
        return self._decision("budget", facts)

    async def authorize_prepare(self, execution, slot, request_sha256):
        return self._decision(
            "prepare",
            {
                "execution": execution.model_dump(mode="json"),
                "slot": slot.model_dump(mode="json"),
                "request_sha256": request_sha256,
            },
        )

    async def authorize_dispatch(self, execution, attempt, request_evidence):
        return self._decision(
            "dispatch",
            {
                "execution": execution.model_dump(mode="json"),
                "attempt": attempt.model_dump(mode="json"),
                "request_evidence": request_evidence.model_dump(mode="json"),
            },
        )

    async def authorize_recover(self, execution, effect):
        return self._decision(
            "recover",
            {
                "execution": execution.model_dump(mode="json"),
                "effect": effect.model_dump(mode="json"),
            },
        )

    async def authorize_observe(self, effect, provider_response_id, observation_digest):
        return self._decision(
            "observe",
            {
                "effect": effect.model_dump(mode="json"),
                "provider_response_id": provider_response_id,
                "observation_digest": observation_digest,
            },
        )

    async def authorize_child(self, project_id, parent_attempt_id, terminal_digest):
        return self._decision(
            "child",
            {
                "project_id": str(project_id),
                "parent_attempt_id": str(parent_attempt_id),
                "terminal_digest": terminal_digest,
            },
        )

    async def authorize_complete(self, effect, response_evidence, terminal_digest):
        return self._decision(
            "complete",
            {
                "effect": effect.model_dump(mode="json"),
                "response_evidence": (
                    response_evidence.model_dump(mode="json")
                    if response_evidence is not None
                    else None
                ),
                "terminal_digest": terminal_digest,
            },
        )

    async def authorize_setup_prepare(self, slot, request_sha256):
        return self._decision(
            "setup_prepare",
            {"slot": slot.model_dump(mode="json"), "request_sha256": request_sha256},
        )

    async def authorize_setup_dispatch(self, prepared, request_evidence):
        return self._decision(
            "setup_dispatch",
            {
                "prepared": prepared.model_dump(mode="json"),
                "request_evidence": request_evidence.model_dump(mode="json"),
            },
        )

    async def authorize_setup_observe(self, effect, provider_response_id, observation_digest):
        return self._decision(
            "setup_observe",
            {
                "effect": effect.model_dump(mode="json"),
                "provider_response_id": provider_response_id,
                "observation_digest": observation_digest,
            },
        )

    async def authorize_setup_complete(self, effect, response_evidence, terminal_digest):
        return self._decision(
            "setup_complete",
            {
                "effect": effect.model_dump(mode="json"),
                "response_evidence": (
                    response_evidence.model_dump(mode="json")
                    if response_evidence is not None
                    else None
                ),
                "terminal_digest": terminal_digest,
            },
        )

    async def require_setup_request(self, prepared, evidence):
        self.request_checks += 1

    async def require_setup_response(self, effect_id, evidence):
        self.response_checks += 1

    async def require_current(self, facts, slot):
        self.current_checks += 1
        self.events.append("current")
        return facts.worker_lease_expires_at

    async def require_recovery_current(self, slot, parent_attempt_id):
        self.current_checks += 1
        self.events.append("recovery_current")

    async def require_request(self, attempt, evidence):
        self.request_checks += 1

    async def require_response(self, attempt_id, evidence):
        self.response_checks += 1


class DatabaseBoundaryPorts:
    """Persist fake boundary receipts so isolated PostgreSQL exercises real ancestry FKs."""

    def __init__(self, session: AsyncSession, ports: BoundaryPorts):
        self._session = session
        self._ports = ports

    async def _authority(
        self,
        evidence,
        *,
        action: str,
        permission: str,
        actor_id=None,
        resource=None,
        resource_digest=None,
        service_identity: str | None = None,
        matched_grant_id: UUID | None = None,
    ):
        actor = str(actor_id or new_record_id())
        if actor_id is not None or service_identity is not None:
            await self._session.execute(
                text(
                    "insert into actor_profiles(id,actor_kind,status,service_identity) "
                    "values (:id,:kind,'active',:identity) on conflict do nothing"
                ),
                {
                    "id": actor,
                    "kind": "service" if service_identity is not None else "human",
                    "identity": service_identity,
                },
            )
        project_id = None
        resource_type = None
        resource_id = None
        if resource is not None:
            resource_project_id = getattr(resource, "scope_project_id", None) or getattr(
                resource, "project_id", None
            )
            if resource_digest is None:
                resource_digest = authorization_resource_digest(resource)
            target = project_authority_audit_target(
                resource,
                resource.action_id,
                matched_scope_project_id=(
                    resource_project_id
                    if resource.resource_type == "project_model_administration"
                    else None
                ),
            )
            if target is not None:
                project_id, resource_type, resource_id, _, _ = target
        await self._session.execute(
            text(
                "insert into audit_events(id,event_domain,event_type,actor_ref_kind,actor_id,"
                "action_id,permission_id,project_id,resource_type,resource_id,matched_grant_id,"
                "denial_code,after_facts) values (:id,'authority',"
                "'SensitiveAuthorizationAllowed','actor_profile',:actor,:action,:permission,"
                ":project,:resource_type,:resource_id,:matched_grant,null,cast(:after as json))"
            ),
            {
                "id": evidence.evidence_id,
                "actor": actor,
                "action": action,
                "permission": permission,
                "project": project_id,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id is not None else None,
                "matched_grant": (str(matched_grant_id) if matched_grant_id is not None else None),
                "after": json.dumps(
                    {
                        "allowed": True,
                        "resource_context_digest": (
                            sha("substituted-authority")
                            if (
                                actor_id is not None and self._ports.corrupt_admin_receipt
                            )
                            or self._ports.corrupt_runtime_receipt_action == action
                            else resource_digest or sha("authority")
                        ),
                    }
                ),
            },
        )
        return evidence

    async def authorize_profile(self, facts):
        evidence = await self._ports.authorize_profile(facts)
        resource = project_model_admin_resource(
            PROFILE_PROVISION, facts, actor_profile_id=facts.actor_profile_id
        )
        return await self._authority(
            evidence,
            action="project.model_profile.provision",
            permission="project.model_profile.manage",
            actor_id=facts.actor_profile_id,
            resource=resource,
            resource_digest=authorization_resource_digest(resource),
        )

    async def authorize_budget(self, facts):
        evidence = await self._ports.authorize_budget(facts)
        resource = project_model_admin_resource(
            BUDGET_CONFIGURE, facts, actor_profile_id=facts.actor_profile_id
        )
        return await self._authority(
            evidence,
            action="project.model_budget.configure",
            permission="project.model_budget.manage",
            actor_id=facts.actor_profile_id,
            resource=resource,
            resource_digest=authorization_resource_digest(resource),
        )

    async def authorize_prepare(self, execution, slot, request_sha256):
        evidence = await self._ports.authorize_prepare(execution, slot, request_sha256)
        facts = ModelCallPrepareAuthorityFacts(
            execution=execution, slot=slot, request_sha256=request_sha256
        )
        return await self._authority(
            evidence,
            action="checker.model_call.prepare",
            permission="checker.model_call.prepare",
            resource=checker_model_call_resource(PREPARE, facts),
            service_identity="workstream.checker.post_submit",
        )

    async def authorize_dispatch(self, execution, attempt, request_evidence):
        evidence = await self._ports.authorize_dispatch(execution, attempt, request_evidence)
        facts = ModelCallDispatchAuthorityFacts(
            execution=execution, attempt=attempt, request_evidence=request_evidence
        )
        return await self._authority(
            evidence,
            action="checker.model_call.dispatch",
            permission="checker.model_call.dispatch",
            resource=checker_model_call_resource(DISPATCH, facts),
            service_identity="workstream.checker.post_submit",
        )

    async def authorize_recover(self, execution, effect):
        evidence = await self._ports.authorize_recover(execution, effect)
        actor_id = new_record_id()
        await self._session.execute(
            text(
                "insert into actor_profiles(id,actor_kind,status,service_identity) "
                "values (:id,'service','active','workstream.checker.post_submit')"
            ),
            {"id": actor_id},
        )
        facts = ModelCallRecoverAuthorityFacts(execution=execution, effect=effect)
        return await self._authority(
            evidence,
            action="checker.model_call.recover",
            permission="checker.model_call.recover",
            actor_id=actor_id,
            resource=checker_model_call_resource(RECOVER, facts),
            resource_digest=authorization_resource_digest(
                checker_model_call_resource(RECOVER, facts)
            ),
        )

    async def authorize_observe(self, effect, provider_response_id, observation_digest):
        evidence = await self._ports.authorize_observe(
            effect, provider_response_id, observation_digest
        )
        facts = ModelCallObserveAuthorityFacts(
            effect=effect,
            provider_response_id=provider_response_id,
            observation_digest=observation_digest,
        )
        return await self._authority(
            evidence,
            action="checker.model_call.observe",
            permission="checker.model_call.observe",
            resource=checker_model_call_resource(OBSERVE, facts),
            service_identity="workstream.checker.post_submit",
        )

    async def authorize_child(self, project_id, parent_attempt_id, terminal_digest):
        evidence = await self._ports.authorize_child(project_id, parent_attempt_id, terminal_digest)
        actor_id = new_record_id()
        facts = ModelCallRecoveryChildAuthorityFacts(
            project_id=project_id,
            parent_attempt_id=parent_attempt_id,
            terminal_digest=terminal_digest,
        )
        return await self._authority(
            evidence,
            action="project.model_call.recovery_child.authorize",
            permission="project.model_call.recovery_child.authorize",
            actor_id=actor_id,
            resource=project_model_admin_resource(
                RECOVERY_CHILD_AUTHORIZE, facts, actor_profile_id=actor_id
            ),
            matched_grant_id=new_record_id(),
        )

    async def authorize_complete(self, effect, response_evidence, terminal_digest):
        evidence = await self._ports.authorize_complete(effect, response_evidence, terminal_digest)
        actor_id = new_record_id()
        service_identity = (
            "workstream.project.setup"
            if self._ports.terminal_receipt_change == "actor"
            else "workstream.checker.post_submit"
        )
        await self._session.execute(
            text(
                "insert into actor_profiles(id,actor_kind,status,service_identity) "
                "values (:id,'service','active',:identity)"
            ),
            {"id": actor_id, "identity": service_identity},
        )
        authority_effect = effect
        if self._ports.terminal_receipt_change == "effect":
            authority_effect = effect.model_copy(update={"attempt_id": new_record_id()})
        elif self._ports.terminal_receipt_change == "project":
            foreign_project = new_record_id()
            authority_effect = effect.model_copy(
                update={
                    "project_id": foreign_project,
                    "slot_key": effect.slot_key.model_copy(update={"project_id": foreign_project}),
                }
            )
        facts = ModelCallCompleteAuthorityFacts(
            effect=authority_effect,
            response_evidence=response_evidence,
            terminal_digest=terminal_digest,
        )
        action = (
            "checker.model_call.observe"
            if self._ports.terminal_receipt_change == "action"
            else "checker.model_call.complete"
        )
        resource_digest = authorization_resource_digest(
            checker_model_call_resource(COMPLETE, facts)
        )
        if self._ports.terminal_receipt_change == "digest":
            resource_digest = sha("foreign terminal resource")
        return await self._authority(
            evidence,
            action=action,
            permission=action,
            actor_id=actor_id,
            resource=checker_model_call_resource(COMPLETE, facts),
            resource_digest=resource_digest,
        )

    async def authorize_setup_prepare(self, slot, request_sha256):
        evidence = await self._ports.authorize_setup_prepare(slot, request_sha256)
        facts = SetupModelPrepareAuthorityFacts(slot=slot, request_sha256=request_sha256)
        return await self._authority(
            evidence,
            action="project.guide_compilation.model.prepare",
            permission="project.guide_compilation.model.prepare",
            resource=setup_model_usage_resource(SETUP_PREPARE, facts),
            service_identity="workstream.project.setup",
        )

    async def authorize_setup_dispatch(self, prepared, request_evidence):
        evidence = await self._ports.authorize_setup_dispatch(prepared, request_evidence)
        facts = SetupModelDispatchAuthorityFacts(
            prepared=prepared, request_evidence=request_evidence
        )
        return await self._authority(
            evidence,
            action="project.guide_compilation.model.dispatch",
            permission="project.guide_compilation.model.dispatch",
            resource=setup_model_usage_resource(SETUP_DISPATCH, facts),
            service_identity="workstream.project.setup",
        )

    async def authorize_setup_observe(self, effect, provider_response_id, observation_digest):
        evidence = await self._ports.authorize_setup_observe(
            effect, provider_response_id, observation_digest
        )
        facts = SetupModelObserveAuthorityFacts(
            effect=effect,
            provider_response_id=provider_response_id,
            observation_digest=observation_digest,
        )
        return await self._authority(
            evidence,
            action="project.guide_compilation.model.observe",
            permission="project.guide_compilation.model.observe",
            resource=setup_model_usage_resource(SETUP_OBSERVE, facts),
            service_identity="workstream.project.setup",
        )

    async def authorize_setup_complete(self, effect, response_evidence, terminal_digest):
        evidence = await self._ports.authorize_setup_complete(
            effect, response_evidence, terminal_digest
        )
        actor_id = new_record_id()
        service_identity = (
            "workstream.checker.post_submit"
            if self._ports.terminal_receipt_change == "actor"
            else "workstream.project.setup"
        )
        await self._session.execute(
            text(
                "insert into actor_profiles(id,actor_kind,status,service_identity) "
                "values (:id,'service','active',:identity)"
            ),
            {"id": actor_id, "identity": service_identity},
        )
        authority_effect = effect
        if self._ports.terminal_receipt_change == "effect":
            authority_effect = effect.model_copy(update={"effect_id": new_record_id()})
        elif self._ports.terminal_receipt_change == "project":
            foreign_project = new_record_id()
            authority_effect = effect.model_copy(
                update={
                    "project_id": foreign_project,
                    "slot_key": effect.slot_key.model_copy(update={"project_id": foreign_project}),
                }
            )
        facts = SetupModelCompleteAuthorityFacts(
            effect=authority_effect,
            response_evidence=response_evidence,
            terminal_digest=terminal_digest,
        )
        action = (
            "project.guide_compilation.model.observe"
            if self._ports.terminal_receipt_change == "action"
            else "project.guide_compilation.model.complete"
        )
        resource_digest = authorization_resource_digest(
            setup_model_usage_resource(SETUP_COMPLETE, facts)
        )
        if self._ports.terminal_receipt_change == "digest":
            resource_digest = sha("foreign setup terminal resource")
        return await self._authority(
            evidence,
            action=action,
            permission=action,
            actor_id=actor_id,
            resource=setup_model_usage_resource(SETUP_COMPLETE, facts),
            resource_digest=resource_digest,
        )

    async def require_setup_request(self, prepared, evidence):
        await self._ports.require_setup_request(prepared, evidence)
        await self._artifact(evidence)

    async def require_setup_response(self, effect_id, evidence):
        await self._ports.require_setup_response(effect_id, evidence)
        await self._artifact(evidence)

    async def require_setup_current(self, slot):
        attempt_id = await self._session.scalar(
            text(
                "select id from project_guide_compilation_attempts where id=:id and project_id=:project and guide_id=:guide and source_snapshot_id=:snapshot and setup_run_id=:run and setup_generation=:generation and runtime_configuration_hash=:runtime and status='compilation_reserved' for update"
            ),
            {
                "id": slot.compilation_attempt_id,
                "project": slot.project_id,
                "guide": slot.guide_id,
                "snapshot": slot.source_snapshot_id,
                "run": slot.setup_run_id,
                "generation": slot.setup_generation,
                "runtime": slot.runtime_configuration_hash,
            },
        )
        if attempt_id is None:
            raise ModelCallUnavailable("setup_model_owner_unavailable")
        return SetupModelOwnerProfile(
            selector=ModelProfileSelector(
                profile_id=slot.profile_id,
                profile_version=slot.profile_version,
                profile_digest=slot.profile_digest,
            ),
            provider="openai_responses",
            api="responses.v1",
            model_snapshot="gpt-example-2026-10-01",
        )

    async def require_current(self, facts, slot):
        return await self._ports.require_current(facts, slot)

    async def require_recovery_current(self, slot, parent_attempt_id):
        await self._ports.require_recovery_current(slot, parent_attempt_id)

    async def _artifact(self, evidence):
        for table_name, value in (
            ("artifact_bindings", evidence.binding_id),
            ("artifact_contents", evidence.content_id),
            ("artifact_put_attempts", evidence.put_attempt_id),
            ("artifact_verification_receipts", evidence.verification_receipt_id),
        ):
            await self._session.execute(
                text(f"insert into {table_name}(id) values (:id) on conflict do nothing"),
                {"id": value},
            )

    async def require_request(self, attempt, evidence):
        await self._ports.require_request(attempt, evidence)
        await self._artifact(evidence)

    async def require_response(self, attempt_id, evidence):
        await self._ports.require_response(attempt_id, evidence)
        await self._artifact(evidence)
