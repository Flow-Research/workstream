"""Complete approved guide and real CON publication, with controlled hidden authority."""

from app.modules.projects.api.guide_activation_context import GuidePolicySelection

from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import text

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.authorization.api import AuthorizationDenied
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.projects.api.guide_activation import (
    GuideActivationAuthorityReceipt,
    GuideActivationCommand,
    PreparedGuideActivation,
)
from app.modules.projects.api.post_policy import PostPolicyApproval
from tests.projects.post_policy.pg_support import PostAuthority, prepare_post_policy, operate
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import (
    seed_selected_review_revision_inputs,
    seed_review_actor,
)


class ActivationAuthority:
    """Test-only participant for isolated product-owner failure injection."""

    def __init__(self, session, actor, project_id, grant, *, close_error=False):
        self.session, self.actor, self.project_id, self.grant = session, actor, project_id, grant
        self.close_error = close_error

    @asynccontextmanager
    async def lock_activation_scope(self, locator):
        admin = AdminAuthorizationRepository(self.session)
        await admin.lock_control()
        await admin.lock_request_actor(self.actor.identity_link_id, self.actor.actor_profile_id)
        async with PostAuthority(
            self.session, self.actor, self.project_id, self.grant
        ).prepare_post_policy_operation(locator):
            prepared = ActivationHandle(self, locator)
            try:
                yield prepared
            finally:
                prepared.closed = True
                if self.close_error:
                    raise AuthorizationDenied("activation close rejected")


class ActivationHandle(PreparedGuideActivation):
    def __init__(self, port, locator):
        self.port, self.locator = port, locator
        self.root = port.session.get_transaction()
        self.used = self.closed = False

    def check(self, facts):
        if (
            self.used
            or self.closed
            or facts.locator != self.locator
            or self.port.session.get_transaction() is not self.root
            or self.port.session.in_nested_transaction()
        ):
            raise AuthorizationDenied("activation handle mismatch")
        self.used = True

    async def consume_new(self, facts):
        self.check(facts)
        decision = new_record_id()
        await self.port.session.execute(
            text(
                "INSERT INTO audit_events(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                "auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,request_id,correlation_id,"
                "permission_id,action_id,reason,project_id,resource_type,resource_id,after_facts,matched_grant_id,target_ref_kind,target_ref_id) "
                "VALUES(:id,'authorization_decision',:id,'SensitiveAuthorizationAllowed',:actor,'[]'::json,'{}'::json,"
                "'local_authority',false,'{}'::json,'authority',1,'actor_profile',:request,:operation,"
                "'project.guide.manage','project.guide.activate','authorization_evaluation',:project,"
                "'project_guide_activation',:guide,"
                "jsonb_build_object('allowed',true,'resource_context_digest',cast(:digest as text))::json,:grant,'project',:target_project)"
            ),
            dict(
                id=str(decision),
                actor=str(self.locator.actor_profile_id),
                request=self.locator.request_id,
                operation=self.locator.operation_id,
                project=str(self.locator.project_id),
                target_project=str(self.locator.project_id),
                guide=str(self.locator.guide_id),
                digest=facts.digest,
                grant=str(self.port.grant),
            ),
        )
        return GuideActivationAuthorityReceipt(
            actor_profile_id=self.locator.actor_profile_id,
            identity_link_id=self.locator.identity_link_id,
            admin_role_grant_id=self.port.grant,
            authorization_decision_event_id=decision,
            action_id="project.guide.activate",
            permission_id="project.guide.manage",
            scope_project_id=self.locator.project_id,
            resource_context_digest=facts.digest,
        )

    async def validate_replay(self, facts, decision_event_id):
        self.check(facts)
        row = (
            (
                await self.port.session.execute(
                    text(
                        "SELECT actor_id,action_id,project_id,resource_id,after_facts FROM audit_events WHERE id=:id"
                    ),
                    dict(id=str(decision_event_id)),
                )
            )
            .mappings()
            .one()
        )
        assert str(row["actor_id"]) == str(self.locator.actor_profile_id)
        assert row["action_id"] == "project.guide.activate"
        assert str(row["project_id"]) == str(self.locator.project_id)
        assert str(row["resource_id"]) == str(self.locator.guide_id)
        assert row["after_facts"] == dict(allowed=True, resource_context_digest=facts.digest)


def activation_service(session, actor, command, grant, *, authority=True, close_error=False):
    from app.adapters.checkers import project_guide_approval_compiler
    from app.adapters.contributions import contribution_policy_validation_port
    from app.adapters.projects.contribution_validation import GuideContributionPolicyValidation
    from app.modules.projects.guide_activation.service import GuideActivationService

    planner, pre, post = project_guide_approval_compiler()
    return GuideActivationService(
        session,
        contribution=GuideContributionPolicyValidation(
            contribution_policy_validation_port(session)
        ),
        planner=planner,
        pre_catalogue=pre,
        post_catalogue=post,
        authorization=ActivationAuthority(
            session, actor, command.target.proposal.project_id, grant, close_error=close_error
        )
        if authority
        else None,
    )


@asynccontextmanager
async def activation_case(
    url, *, human_review_required=True, compensated=False, contribution_awards=()
):
    from .source_fixtures import source_case

    async with source_case(url) as (values, factory, finalization, actor, grant):
        await seed_selected_review_revision_inputs(
            factory, finalization, actor, human_review_required=human_review_required
        )
        _, derived = await prepare_post_policy(
            factory, finalization, actor, grant, service_actor(values)
        )
        approved = await operate(
            factory,
            actor,
            finalization.project_id,
            grant,
            "approve",
            PostPolicyApproval(target=derived.target, idempotency_key=uuid4()),
        )
        world, policy = await publish_policy(
            factory,
            finalization.project_id,
            compensated=compensated,
            contribution_awards=contribution_awards,
        )
        command = await activation_command(factory, approved, policy)
        yield factory, command, actor, grant, world, policy


async def activation_command(factory, approved, policy):
    """Select exactly the separately approved policies for a guide."""
    async with factory() as session:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM project_guides WHERE id=:id"),
                    dict(id=str(approved.target.proposal.guide_id)),
                )
            )
            .mappings()
            .one()
        )
    return GuideActivationCommand(
        target=approved.target,
        post_approval_operation_id=approved.operation_id,
        post_approval_output_digest=canonical_json_hash(approved.model_dump(mode="json")),
        guide_mutation_generation=row["mutation_generation"],
        review=GuidePolicySelection(
            policy_id=row["selected_review_policy_id"],
            generation=row["selected_review_policy_generation"],
            policy_hash=row["selected_review_policy_hash"],
        ),
        revision=GuidePolicySelection(
            policy_id=row["selected_revision_policy_id"],
            generation=row["selected_revision_policy_generation"],
            policy_hash=row["selected_revision_policy_hash"],
        ),
        contribution_policy_id=policy.contribution_policy_id,
        contribution_policy_version_id=policy.contribution_policy_version_id,
        expected_previous_active_guide_id=None,
        expected_previous_active_guide_generation=None,
        idempotency_key=uuid4(),
    )


async def publish_policy(factory, project_id, *, compensated=False, contribution_awards=()):
    """Publish complete rules with real scoped Finance authority."""
    from app.modules.authorization.runtime import (
        HumanAuthorizationContext,
        ActorKind,
        ActorStatus,
        IdentityLinkStatus,
    )
    from tests.authorization.contribution_policies.postgresql_support import PolicyWorld

    finance, finance_grant = await seed_review_actor(factory, project_id, role="finance_authority")
    context = HumanAuthorizationContext(
        actor_profile_id=finance.actor_profile_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=finance.identity_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    world = PolicyWorld(None, project_id, uuid4(), context, str(finance_grant))
    if compensated:
        from .compensation_fixtures import create_binding

        world.binding = await create_binding(factory, world)
    award_bindings = ()
    if contribution_awards:
        from .compensation_fixtures import create_binding
        award_bindings = tuple([
            (instrument, await create_binding(factory, world, instrument_type=instrument))
            for instrument in contribution_awards
        ])
    policy = None
    for operation in ("create_draft", "update_draft", "publish"):
        async with factory() as session, session.begin():
            policy = await getattr(world.service(session), operation)(
                world.request(operation, policy, compensated=compensated, award_bindings=award_bindings)
            )
    return world, policy
