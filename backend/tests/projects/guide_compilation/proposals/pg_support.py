"""Strict test-only request authority over actual PostgreSQL proposal custody."""

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy import text

from app.modules.authorization.api import ActorIdentityFacts, ActorKind, AuthorizationDenied
from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorityReceipt,
    PreparedGuideProposalOperation,
)
from app.modules.projects.api.guide_proposals import GuideProposalError, GuideProposalSelection
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.models import ProjectSetupRun
from tests.projects.guide_compilation.finalization.pg_support import database_case, finalize


class PreparedProposal(PreparedGuideProposalOperation):
    def __init__(self, port):
        self.port = port
        self.root = port.session.get_transaction()
        self.closed = False
        self.used = False

    def check(self, facts):
        if (
            self.closed
            or self.used
            or self.port.session.get_transaction() is not self.root
            or self.port.session.in_nested_transaction()
            or facts.locator != self.port.locator
        ):
            raise AuthorizationDenied("test proposal handle mismatch")
        self.used = True
        self.port.last_facts = facts

    async def authorize_read(self, facts):
        self.check(facts)
        assert facts.locator.action_id == "project.guide_compilation.review_package.read"

    async def consume_new(self, facts):
        self.check(facts)
        if self.port.on_consume:
            await self.port.on_consume()
        approval = facts.locator.action_id == "project.submission_artifact_policy.approve"
        permission = (
            "project.effective_policy.manage" if approval else "project.guide_compilation.request"
        )
        kind = (
            "project_submission_artifact_policy_mutation"
            if approval
            else "project_guide_compilation_correction"
        )
        resource = facts.artifact_policy_id if approval else facts.locator.operation_id
        decision = uuid4()
        await self.port.session.execute(
            text(
                "INSERT INTO audit_events(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                "auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,request_id,correlation_id,"
                "permission_id,action_id,reason,project_id,resource_type,resource_id,after_facts,matched_grant_id,"
                "target_ref_kind,target_ref_id) VALUES(:id,'authorization_decision',:id,'SensitiveAuthorizationAllowed',"
                ":actor,'[]'::json,'{}'::json,'local_authority',false,'{}'::json,'authority',1,'actor_profile',"
                ":request,:operation,:permission,:action,'authorization_evaluation',:project,:kind,:resource,"
                "jsonb_build_object('allowed',true,'resource_context_digest',cast(:digest as text))::json,"
                ":grant,'project',:project)"
            ),
            dict(
                id=str(decision),
                actor=str(self.port.actor.actor_profile_id),
                request=facts.locator.request_id,
                operation=facts.locator.operation_id,
                permission=permission,
                action=facts.locator.action_id,
                project=str(self.port.project_id),
                kind=kind,
                resource=str(resource),
                digest=facts.digest,
                grant=str(self.port.grant_id),
            ),
        )
        self.port.consumed += 1
        return GuideProposalAuthorityReceipt(
            actor_profile_id=self.port.actor.actor_profile_id,
            identity_link_id=self.port.actor.identity_link_id,
            admin_role_grant_id=self.port.grant_id,
            authorization_decision_event_id=decision,
            action_id=facts.locator.action_id,
            permission_id=permission,
            scope_project_id=self.port.project_id,
            resource_context_digest=facts.digest,
        )

    async def validate_replay(self, facts, decision_event_id):
        self.check(facts)
        row = (
            (
                await self.port.session.execute(
                    text(
                        "SELECT actor_id,action_id,project_id,after_facts FROM audit_events WHERE id=:id"
                    ),
                    {"id": str(decision_event_id)},
                )
            )
            .mappings()
            .one()
        )
        if (
            row["actor_id"] != str(self.port.actor.actor_profile_id)
            or row["action_id"] != facts.locator.action_id
            or row["project_id"] != str(self.port.project_id)
            or row["after_facts"] != {"allowed": True, "resource_context_digest": facts.digest}
        ):
            raise AuthorizationDenied("retained proposal evidence mismatch")


class ProposalAuthority:
    def __init__(self, session, actor, project_id, grant_id, *, on_consume=None, close_error=False):
        self.session, self.actor = session, actor
        self.project_id, self.grant_id = project_id, grant_id
        self.on_consume, self.close_error = on_consume, close_error
        self.consumed = 0
        self.last_facts = None

    @asynccontextmanager
    async def prepare_proposal_operation(self, locator):
        if (
            locator.actor_profile_id != self.actor.actor_profile_id
            or locator.identity_link_id != self.actor.identity_link_id
            or locator.project_id != self.project_id
        ):
            raise AuthorizationDenied("foreign proposal authority")
        current = await self.session.scalar(
            text(
                "SELECT a.id FROM actor_profiles a JOIN actor_identity_links l ON l.actor_profile_id=a.id "
                "JOIN admin_role_grants g ON g.target_actor_profile_id=a.id "
                "WHERE a.id=:actor AND a.actor_kind='human' AND a.status='active' "
                "AND l.id=:link AND l.status='active' AND l.subject_kind='human' "
                "AND g.id=:grant AND g.status='active' AND g.role='project_manager' "
                "AND g.scope_type='project' AND g.scope_project_id=:project FOR SHARE OF a,l,g"
            ),
            {
                "actor": str(self.actor.actor_profile_id),
                "link": str(self.actor.identity_link_id),
                "grant": self.grant_id,
                "project": str(self.project_id),
            },
        )
        if current is None:
            raise AuthorizationDenied("current proposal authority unavailable")
        self.locator = locator
        handle = PreparedProposal(self)
        try:
            yield handle
        finally:
            handle.closed = True
            if self.close_error:
                raise AuthorizationDenied("test close rejected")


@asynccontextmanager
async def proposal_case(url, *, classification="draft_ready", guide_version="v1", outcome=None):
    async with database_case(url, classification=classification, guide_version=guide_version, outcome=outcome) as (values, factory, command):
        await finalize(factory, values, command)
        async with factory() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT a.id,l.id AS link,g.id AS grant FROM actor_profiles a "
                            "JOIN actor_identity_links l ON l.actor_profile_id=a.id "
                            "JOIN admin_role_grants g ON g.target_actor_profile_id=a.id "
                            "WHERE g.role='project_manager' AND g.scope_project_id=:project AND g.status='active'"
                        ),
                        {"project": str(command.project_id)},
                    )
                )
                .mappings()
                .one()
            )
        actor = ActorIdentityFacts(UUID(row["id"]), UUID(row["link"]), ActorKind.HUMAN)
        yield values, factory, command, actor, row["grant"]


async def read_package(factory, command, actor, grant_id):
    try:
        async with factory() as session, session.begin():
            return await GuideProposalService(
                session,
                ProposalAuthority(
                    session,
                    actor,
                    command.project_id,
                    grant_id,
                ),
            ).review_package(
                GuideProposalSelection(
                    project_id=command.project_id,
                    guide_id=command.guide_id,
                    compilation_id=command.compilation_id,
                ),
                actor=actor,
                request_id=uuid4(),
            )
    except GuideProposalError as exc:
        raise exc from exc.__context__


async def request_corrected_attempt(factory, actor, correction):
    """Enter the existing production human request port; no provider is invoked."""
    from app.adapters.artifacts import guide_document_manifest_port
    from app.modules.authorization.guide_compilation import (
        ProjectGuideCompilationAuthorizationAdapter,
    )
    from app.modules.authorization.kernel import AuthorizationService
    from app.modules.authorization.prepared import PreparedAuthorizationService
    from app.modules.authorization.repository import AdminAuthorizationRepository
    from app.modules.authorization.runtime import (
        ActorStatus,
        HumanAuthorizationContext,
        IdentityLinkStatus,
    )
    from app.modules.checkers.catalogue import (
        build_pre_submission_checker_catalogue,
        project_guide_pre_submission_capabilities,
    )
    from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
    from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs
    from app.modules.projects.guide_compilation.service import GuideCompilationService
    from tests.projects.guide_compilation.helpers import runtime_configuration

    ctx = HumanAuthorizationContext(
        actor_profile_id=actor.actor_profile_id,
        actor_kind=actor.actor_kind,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=actor.identity_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    async with factory() as session:
        repository = AdminAuthorizationRepository(session)
        kernel = AuthorizationService(session, ctx, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, ctx, kernel, repository)
        service = GuideCompilationService(
            session,
            ProjectGuideCompilationAuthorizationAdapter(kernel, prepared),
            request_inputs=CompilationRequestInputs(
                guide_document_manifest_port(session),
                project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue()),
                current_post_submit_catalogue(),
                runtime_configuration(),
            ),
        )
        return await service.request_correction(
            actor=actor, correction_operation_id=correction.operation_id
        )


async def finalize_corrected_attempt(factory, values, actor, correction):
    """Run a scripted result through actual execution, projections and finalization."""
    from app.adapters.artifacts import guide_document_manifest_port
    from app.adapters.auth import (
        artifact_policy_projection_authorization,
        guide_sufficiency_projection_authorization,
    )
    from app.modules.projects.api import (
        ProjectGuideCompilationExecutionCommand,
        ProjectGuideCompilationExecutionClassification,
        ProjectGuideProjectionCommand,
        ProjectGuideSetupFinalizationCommand,
    )
    from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
    from tests.projects.guide_compilation.test_hidden_orchestrator_postgresql import _Runtime, _port
    from tests.projects.guide_compilation.helpers import result

    requested = await request_corrected_attempt(factory, actor, correction)
    from app.modules.projects.api.guide_documents import GuideDocumentManifestRequest
    from app.interfaces.project_agents import GuideEvidenceRef
    async with factory() as session:
        setup = await session.get(ProjectSetupRun, str(correction.successor_setup_run_id))
        manifest = await guide_document_manifest_port(session).load(GuideDocumentManifestRequest(
            project_id=values["project"], guide_id=values["guide"],
            guide_source_snapshot_id=setup.source_snapshot_id,
            project_setup_run_id=correction.successor_setup_run_id,
            setup_generation=correction.successor_setup_generation,
        ))
    evidence_refs = tuple(GuideEvidenceRef(
        source_item_id=document.source_item_id, document_version_id=document.ingest_id,
        sha256=document.sha256,
    ) for document in manifest.documents)
    outcome = result()
    outcome = outcome.model_copy(update={"findings": tuple(
        finding.model_copy(update={"evidence_refs": evidence_refs}) for finding in outcome.findings
    )})
    runtime = _Runtime(outcome)
    execution = await _port(factory, runtime).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id),
    )
    assert execution.classification is ProjectGuideCompilationExecutionClassification.PERSISTED, execution
    assert runtime.calls == 1
    projections = GuideCompilationProjectionService(
        factory,
        material_factory=guide_document_manifest_port,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
    )
    project = ProjectGuideProjectionCommand(attempt_id=requested.attempt_id)
    await projections.project_guide_sufficiency(project)
    await projections.project_submission_artifact_policy(project)
    command = ProjectGuideSetupFinalizationCommand(
        project_id=values["project"],
        guide_id=values["guide"],
        setup_run_id=correction.successor_setup_run_id,
        setup_generation=correction.successor_setup_generation,
        compilation_id=execution.compilation_id,
    )
    await finalize(factory, values, command)
    return command


async def seed_review_actor(factory, project_id, *, actor=None, role="project_manager", scope="project"):
    """Seed stored grant variants; request/approval authority guards remain enabled."""
    from datetime import UTC, datetime
    from app.modules.actors.models import ActorProfile, ActorIdentityLink
    from project_create_fixtures import grant_fixture_admin_role

    async with factory() as session, session.begin():
        if actor is None:
            actor = ActorIdentityFacts(uuid4(), uuid4(), ActorKind.HUMAN)
            session.add(ActorProfile(id=str(actor.actor_profile_id), actor_kind="human", status="active",
                                    provisioning_method="automatic_first_access", created_by="proposal-fixture"))
            await session.flush()
            session.add(ActorIdentityLink(id=str(actor.identity_link_id), actor_profile_id=str(actor.actor_profile_id),
                                         issuer="https://identity.flowresearch.tech", subject=str(actor.actor_profile_id),
                                         subject_kind="human", status="active", linked_by="proposal-fixture",
                                         last_verified_at=datetime.now(UTC)))
            await session.flush()
        grant = await grant_fixture_admin_role(session, actor.actor_profile_id, role=role, scope=scope,
                                               project_id=project_id if scope == "project" else None)
        return actor, grant.id


async def revoke_review_grant(factory, actor, grant):
    """Use the database's real revoke transition with an attributed administrator."""
    administrator, admin_grant = await seed_review_actor(factory, None, role="access_administrator", scope="system")
    async with factory() as session, session.begin():
        result = await session.execute(text(
            "UPDATE admin_role_grants SET status='revoked',version=2,revoked_by_actor_profile_id=:actor,"
            "revoked_by_admin_role_grant_id=:authorizer,revoked_at=now(),revoked_reason='Manager turnover' WHERE id=:id AND target_actor_profile_id=:target"
        ), {"actor": str(administrator.actor_profile_id), "authorizer": admin_grant, "id": grant, "target": str(actor.actor_profile_id)})
        assert result.rowcount == 1


async def seed_selected_review_revision_inputs(factory, command, actor):
    """Select valid review/revision inputs through their authorized mutation owner."""
    from app.modules.actors.models import ActorProfile, ActorIdentityLink
    from app.modules.actors.service import ResolvedActor
    from app.modules.authorization.kernel import AuthorizationService
    from app.modules.authorization.prepared import PreparedAuthorizationService
    from app.modules.authorization.repository import AdminAuthorizationRepository
    from app.modules.authorization.runtime import ActorStatus, HumanAuthorizationContext, IdentityLinkStatus
    from app.modules.projects.policy_mutation_service import ProjectPolicyMutationService, NO_CURRENT_POLICY_ETAG
    from app.modules.projects.schemas import ReviewPolicyInput, RevisionPolicyInput

    for kind, payload in (
        ("review", ReviewPolicyInput(review_preference_window_seconds=3600, review_lease_duration_seconds=1800,
                                   allowed_decisions=["accept", "needs_revision", "reject"])),
        ("revision", RevisionPolicyInput(max_revision_rounds=2, revision_deadline_hours=48,
                                       allowed_resubmission_states=["needs_revision"])),
    ):
        async with factory() as session:
            resolved = ResolvedActor(
                await session.get(ActorProfile, str(actor.actor_profile_id)),
                await session.get(ActorIdentityLink, str(actor.identity_link_id)),
            )
            ctx = HumanAuthorizationContext(
                actor_profile_id=actor.actor_profile_id, actor_kind=ActorKind.HUMAN,
                actor_status=ActorStatus.ACTIVE, identity_link_id=actor.identity_link_id,
                identity_link_status=IdentityLinkStatus.ACTIVE, request_id=uuid4(), correlation_id=uuid4(),
            )
            repository = AdminAuthorizationRepository(session)
            kernel = AuthorizationService(session, ctx, admin_repository=repository)
            prepared = PreparedAuthorizationService(session, ctx, kernel, repository)
            service = ProjectPolicyMutationService(session)
            mutate = service.replace_review_policy if kind == "review" else service.replace_revision_policy
            await mutate(resolved, prepared, uuid4(), NO_CURRENT_POLICY_ETAG, command.project_id, command.guide_id, payload)
            await session.commit()
