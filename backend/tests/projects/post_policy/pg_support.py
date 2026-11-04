"""Strict test-only post-policy authority over real actors, decisions and transactions."""

from app.adapters.contributions import published_contribution_policy_port
from app.adapters.projects.contribution_validation import GuideContributionPolicyDiscovery

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.authorization.api import ActorKind, AuthorizationDenied
from app.modules.authorization.api.post_policy import PreparedPostPolicyOperation, PostPolicyAuthorityReceipt


class PreparedPostPolicy(PreparedPostPolicyOperation):
    def __init__(self, port, locator):
        self.port, self.locator = port, locator
        self.root = port.session.get_transaction()
        self.closed, self.used = False, False

    def check(self, facts):
        if (self.closed or self.used or facts.locator != self.locator
                or self.port.session.get_transaction() is not self.root
                or self.port.session.in_nested_transaction()):
            raise AuthorizationDenied('post-policy handle mismatch')
        self.used = True

    async def authorize_read(self, facts):
        self.check(facts)
        assert self.locator.action_id == 'project.guide_compilation.review_package.read'
        assert self.port.actor.actor_kind is ActorKind.HUMAN

    async def consume_new(self, facts):
        self.check(facts)
        decision = new_record_id()
        derive = self.locator.action_id.endswith('.derive')
        if derive != (self.port.actor.actor_kind is ActorKind.SERVICE):
            raise AuthorizationDenied('wrong post-policy actor kind')
        await self.port.session.execute(text(
            "INSERT INTO audit_events(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
            "auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,request_id,correlation_id,"
            "permission_id,action_id,reason,project_id,resource_type,resource_id,after_facts,matched_grant_id,target_ref_kind,target_ref_id) "
            "VALUES(:id,'authorization_decision',:id,'SensitiveAuthorizationAllowed',:actor,'[]'::json,'{}'::json,"
            "'local_authority',false,'{}'::json,'authority',1,'actor_profile',:request,:operation,"
            "'project.effective_policy.manage',:action,'authorization_evaluation',:project,"
            "'project_post_submit_checker_policy_mutation',:policy,"
            "jsonb_build_object('allowed',true,'resource_context_digest',cast(:digest as text))::json,:grant,'project',:target_project)"
        ), dict(id=str(decision), actor=str(self.port.actor.actor_profile_id), request=self.locator.request_id,
                operation=self.locator.operation_id, action=self.locator.action_id, project=str(self.port.project_id),
                target_project=str(self.port.project_id),
                policy=str(facts.policy_id), digest=facts.digest, grant=str(self.port.grant) if self.port.grant else None))
        return PostPolicyAuthorityReceipt(
            actor_profile_id=self.port.actor.actor_profile_id, identity_link_id=self.port.actor.identity_link_id,
            authorization_decision_event_id=decision, action_id=self.locator.action_id,
            permission_id='project.effective_policy.manage', scope_project_id=self.port.project_id,
            resource_context_digest=facts.digest, admin_role_grant_id=UUID(str(self.port.grant)) if self.port.grant else None,
            service_identity=self.port.actor.service_identity,
        )

    async def validate_replay(self, facts, decision_event_id):
        self.check(facts)
        row = (await self.port.session.execute(text(
            'SELECT actor_id,action_id,project_id,after_facts FROM audit_events WHERE id=:id'
        ), dict(id=str(decision_event_id)))).mappings().one()
        if (row['actor_id'] != str(self.port.actor.actor_profile_id) or row['action_id'] != self.locator.action_id
                or row['project_id'] != self.port.project_id
                or row['after_facts'] != dict(allowed=True, resource_context_digest=facts.digest)):
            raise AuthorizationDenied('post-policy replay evidence mismatch')


class PostAuthority:
    def __init__(self, session, actor, project_id, grant=None, *, close_error=False):
        self.session, self.actor, self.project_id, self.grant = session, actor, project_id, grant
        self.close_error = close_error

    @asynccontextmanager
    async def prepare_post_policy_operation(self, locator):
        if (locator.project_id != self.project_id or locator.actor_profile_id != self.actor.actor_profile_id
                or locator.identity_link_id != self.actor.identity_link_id):
            raise AuthorizationDenied('foreign post-policy authority')
        row = await self.session.scalar(text(
            "SELECT a.id FROM actor_profiles a JOIN actor_identity_links l ON l.actor_profile_id=a.id "
            "WHERE a.id=:actor AND l.id=:link AND a.status='active' AND l.status='active' "
            "AND a.actor_kind=:kind AND l.subject_kind=:kind "
            "AND (:kind='human' OR a.service_identity='workstream.project.setup') FOR SHARE OF a,l"
        ), dict(actor=str(self.actor.actor_profile_id), link=str(self.actor.identity_link_id), kind=self.actor.actor_kind.value))
        if row is None:
            raise AuthorizationDenied('inactive post-policy identity')
        if self.actor.actor_kind is ActorKind.HUMAN:
            grant = await self.session.scalar(text(
                "SELECT id FROM admin_role_grants WHERE id=:id AND target_actor_profile_id=:actor "
                "AND role='project_manager' AND status='active' AND scope_type='project' "
                "AND scope_project_id=:project FOR SHARE"
            ), dict(id=self.grant, actor=str(self.actor.actor_profile_id), project=str(self.project_id)))
            if grant is None:
                raise AuthorizationDenied('current project grant missing')
        prepared = PreparedPostPolicy(self, locator)
        try:
            yield prepared
        finally:
            prepared.closed = True
            if self.close_error:
                raise AuthorizationDenied('post-policy close rejected')


async def prepare_upstream(factory, command, actor, grant, values):
    from app.core.hashing import canonical_json_hash
    from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalSelection
    from app.modules.projects.api.post_policy import PostPolicyDerive
    from tests.projects.guide_compilation.proposals.pg_support import read_package
    from tests.projects.guide_compilation.proposals.test_postgresql import approve

    package = await read_package(factory, command, actor, grant)
    upstream = await approve(factory, command, actor, grant, GuideProposalApproval(
        target=package.target,
        pre_submit_attachments=values["pre_submit_attachments"],
        post_submit_attachments=values["post_submit_attachments"],
        idempotency_key=uuid4(),
    ))
    payload = PostPolicyDerive(selection=GuideProposalSelection(
        project_id=command.project_id, guide_id=command.guide_id, compilation_id=command.compilation_id),
        upstream_approval_operation_id=upstream.operation_id,
        upstream_approval_output_digest=canonical_json_hash(upstream.model_dump(mode='json')))
    return payload


async def prepare_post_policy(factory, command, actor, grant, setup_actor, values):
    payload = await prepare_upstream(factory, command, actor, grant, values)
    receipt = await operate(factory, setup_actor, command.project_id, None, 'derive', payload)
    return payload, receipt


async def operate(factory, actor, project_id, grant, operation, command, *, close_error=False, guide_close_error=False):
    from app.modules.projects.post_policy.service import PostPolicyService
    from tests.projects.guide_compilation.proposals.pg_support import ProposalAuthority

    async with factory() as session, session.begin():
        service = PostPolicyService(
            session,
            PostAuthority(session, actor, project_id, grant, close_error=close_error),
        )
        kwargs = dict(actor=actor, request_id=uuid4())
        if operation == "review_package":
            kwargs["contribution"] = GuideContributionPolicyDiscovery(published_contribution_policy_port(session))
        if operation == 'request_correction':
            kwargs['guide_authorization'] = ProposalAuthority(session, actor, project_id, grant, close_error=guide_close_error)
        return await getattr(service, operation)(command, **kwargs)
