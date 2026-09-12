"""Actual kernel/PREP with explicit in-memory principal and evidence boundaries."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from app.modules.authorization import guide_proposal_authorization as adapters
from app.modules.authorization.api import ActorKind
from app.modules.authorization.runtime import (
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from tests.authorization.guide_compilation_projections.support import Session
from tests.projects.guide_compilation.proposals.contract_support import authority_case


class Case:
    def __init__(self, monkeypatch, action="project.submission_artifact_policy.approve"):
        actor, _, facts, _ = authority_case()
        self.facts = replace(facts, locator=replace(facts.locator, action_id=action))
        self.session = Session()
        self.context = HumanAuthorizationContext(
            actor_profile_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=facts.locator.request_id,
            correlation_id=uuid4(),
        )
        self.grant = SimpleNamespace(
            id=uuid4(),
            status="active",
            scope_type="project",
            scope_project_id=str(facts.locator.project_id),
            role="project_manager",
        )
        self.role, self.actor_status, self.link_status = "project_manager", "active", "active"
        self.events = []
        self.actor_kind = "human"
        self.last_filters = None
        monkeypatch.setattr(adapters, "AdminAuthorizationRepository", lambda session: self)
        original = adapters.AuthorizationService

        def kernel(session, context, **kwargs):
            result = original(session, context, **kwargs)
            result._audit = self
            return result

        monkeypatch.setattr(adapters, "AuthorizationService", kernel)

    async def lock_request_actor(self, link, actor):
        return (
            SimpleNamespace(id=str(link), actor_profile_id=str(actor), status=self.link_status),
            SimpleNamespace(id=str(actor), actor_kind=self.actor_kind, status=self.actor_status),
        )

    async def find_effective_grant(self, actor, permission, **filters):
        self.last_filters = filters
        if (
            self.role != "project_manager"
            or self.grant.status != "active"
            or self.grant.scope_type != "project"
            or self.grant.scope_project_id != str(filters["scope_project_id"])
        ):
            return None
        return self.grant

    async def add_authority_event(self, event):
        self.events.append(
            SimpleNamespace(
                id=str(event.event_id),
                event_domain="authority",
                event_type=event.event_type.value,
                actor_ref_kind=event.actor_ref_kind.value,
                actor_id=event.actor_ref,
                action_id=event.action_id.value,
                permission_id=event.permission_id.value,
                project_id=event.project_id,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                target_ref_kind=event.target_ref_kind,
                target_ref_id=event.target_ref_id,
                request_id=str(event.request_id),
                correlation_id=str(event.correlation_id),
                matched_grant_id=event.matched_grant_id,
                denial_code=event.denial_code,
                after_facts=event.after_facts,
            )
        )

    async def get_authority_event(self, decision):
        return next((e for e in self.events if e.id == str(decision)), None)

    def prepare(self, *, facts=None, context=None):
        return adapters.GuideProposalAuthorizationAdapter(
            self.session,
            context or self.context,
        ).prepare_proposal_operation((facts or self.facts).locator)

    async def consume(self, prepared, facts=None):
        facts = facts or self.facts
        if facts.locator.action_id == "project.guide_compilation.review_package.read":
            return await prepared.authorize_read(facts)
        return await prepared.consume_new(facts)
