"""Arrange real unified projection, finalization and hidden manager approval."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.adapters.artifacts import guide_document_manifest_port
from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
from app.db import session as db_session
from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.models import AdminRoleGrant
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api import (
    ProjectGuideProjectionCommand,
    ProjectGuideSetupFinalizationCommand,
)
from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalSelection
from app.modules.projects.guide_compilation.models import ProjectGuideCompilation, ProjectGuideComponentProjectionOperation
from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.schemas import (
    EffectiveProjectSubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyResponse,
)
from tests.committed_guide_fixtures import create_compiled_report_fixture
from tests.projects.guide_compilation.finalization.pg_support import finalize
from tests.projects.guide_compilation.proposals.pg_support import ProposalAuthority


def downstream_artifact_proposal():
    return SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000_000,
        maximum_package_size_bytes=5_000_000,
        required_artifacts=("outputs/answer.md",),
        required_evidence=("reasoning_trace",),
        forbidden_artifacts=("*.tmp",),
        attestation_terms=("project_specific_originality",),
    )


async def create_unified_submission_policy(report_id, snapshot_id, *, proposal=None):
    """Project the actual scripted result, with no manual policy row replacement."""
    sessions = db_session.get_session_factory()
    proposal = proposal or downstream_artifact_proposal()
    await create_compiled_report_fixture(
        report_id,
        snapshot_id,
        artifact_proposal=proposal,
    )
    async with sessions() as session:
        compilation = (
            await session.scalars(
                select(ProjectGuideCompilation).where(
                    ProjectGuideCompilation.source_snapshot_id == snapshot_id,
                )
            )
        ).one()
        service_actor, service_link = (
            await session.execute(
                select(ActorProfile.id, ActorIdentityLink.id)
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(
                    ActorProfile.service_identity == "workstream.project.setup",
                    ActorIdentityLink.status == "active",
                ),
            )
        ).one()
        command = ProjectGuideSetupFinalizationCommand(
            project_id=UUID(compilation.project_id),
            guide_id=UUID(compilation.guide_id),
            setup_run_id=UUID(compilation.setup_run_id),
            setup_generation=compilation.setup_generation,
            compilation_id=compilation.id,
        )
        assert compilation.canonical_result["submission_artifact_policy"] == proposal.model_dump(
            mode="json"
        )
    projections = GuideCompilationProjectionService(
        sessions,
        material_factory=guide_document_manifest_port,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
    )
    projected = await projections.project_submission_artifact_policy(
        ProjectGuideProjectionCommand(attempt_id=compilation.attempt_id),
    )
    await finalize(sessions, {"actor": UUID(service_actor), "link": UUID(service_link)}, command)
    async with sessions() as session:
        policy = await session.get(SubmissionArtifactPolicy, str(projected.output_id))
        return SubmissionArtifactPolicyResponse.model_validate(policy).model_dump(mode="json")


async def approve_unified_submission_policy(project_id, guide_id, policy_id, *, sessions=None):
    """Use strict hidden test authority and the real approval owner; no live route exists."""
    sessions = sessions or db_session.get_session_factory()
    actor, grant_id, compilation = await _approval_context(sessions, project_id, guide_id, policy_id)
    async with sessions() as session, session.begin():
        service = GuideProposalService(
            session, ProposalAuthority(session, actor, UUID(project_id), grant_id)
        )
        package = await service.review_package(
            GuideProposalSelection(
                project_id=project_id,
                guide_id=guide_id,
                compilation_id=compilation.id,
            ),
            actor=actor,
            request_id=uuid4(),
        )
    assert str(package.target.artifact_policy_id) == policy_id
    planner = build_pre_submission_checker_catalogue()
    async with sessions() as session, session.begin():
        receipt = await GuideProposalService(
            session,
            ProposalAuthority(
                session,
                actor,
                UUID(project_id),
                grant_id,
            ),
        ).approve(
            GuideProposalApproval(
                target=package.target,
                idempotency_key=uuid4(),
                acknowledged_warning_hashes=package.warning_hashes,
                expected_previous_approval_operation_id=package.current_approval_operation_id,
                expected_previous_approval_output_digest=package.current_approval_output_digest,
            ),
            actor=actor,
            request_id=uuid4(),
            material=guide_document_manifest_port(session),
            pre_capabilities=project_guide_pre_submission_capabilities(planner),
            post_capabilities=current_post_submit_catalogue(),
            planner=planner,
        )
    async with sessions() as session:
        effective = await session.get(
            EffectiveProjectSubmissionArtifactPolicy, str(receipt.effective_policy_id)
        )
        return EffectiveProjectSubmissionArtifactPolicyResponse.model_validate(
            effective
        ).model_dump(mode="json")


async def create_standalone_unified_policy(sessions, namespace, *, guide_version="v1", artifact_proposal=None):
    """Arrange canonical setup before a lower-level artifact transaction starts."""
    from tests.projects.guide_compilation.helpers import context, seed_database
    from tests.projects.guide_compilation.finalization.pg_prerequisites import compilation_and_projections
    from app.modules.projects.api.guide_documents import GuideDocumentManifestRequest
    from app.modules.projects.models import PreSubmitCheckerPolicy

    url = sessions.kw["bind"].url.render_as_string(hide_password=False)
    values = await seed_database(url, namespace=namespace, guide_version=guide_version)
    async with sessions() as session:
        manifest = await guide_document_manifest_port(session).load(GuideDocumentManifestRequest(
            project_id=values["project"], guide_id=values["guide"],
            guide_source_snapshot_id=values["snapshot"],
            project_setup_run_id=values["setup_1"], setup_generation=1,
        ))
    compilation_context = context(values, guide_version=guide_version).model_copy(update={"material": manifest})
    from tests.projects.guide_compilation.helpers import result
    outcome = result()
    if artifact_proposal is not None:
        outcome = outcome.model_copy(update={"submission_artifact_policy": artifact_proposal})
    command = await compilation_and_projections(
        url, sessions, values, compilation_context=compilation_context, outcome=outcome,
    )
    await finalize(sessions, values, command)
    async with sessions() as session:
        policy = (await session.scalars(select(SubmissionArtifactPolicy).where(
            SubmissionArtifactPolicy.guide_id == str(values["guide"]),
        ))).one()
        policy_id = policy.id
    effective = await approve_unified_submission_policy(
        str(values["project"]), str(values["guide"]), policy_id, sessions=sessions,
    )
    async with sessions() as session:
        pre = (await session.scalars(select(PreSubmitCheckerPolicy).where(
            PreSubmitCheckerPolicy.effective_policy_id == effective["id"],
        ))).one()
        return values, effective, pre


async def _approval_context(sessions, project_id, guide_id, policy_id):
    async with sessions() as session:
        actor_id, link_id, grant_id = (
            await session.execute(
                select(ActorProfile.id, ActorIdentityLink.id, AdminRoleGrant.id)
                .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
                .join(AdminRoleGrant, AdminRoleGrant.target_actor_profile_id == ActorProfile.id)
                .where(
                    AdminRoleGrant.scope_project_id == project_id,
                    AdminRoleGrant.role == "project_manager",
                    AdminRoleGrant.status == "active",
                    ActorIdentityLink.status == "active",
                ),
            )
        ).one()
        compilation = (
            await session.scalars(
                select(ProjectGuideCompilation).join(
                    ProjectGuideComponentProjectionOperation,
                    ProjectGuideComponentProjectionOperation.compilation_id == ProjectGuideCompilation.id,
                ).where(
                    ProjectGuideCompilation.project_id == project_id,
                    ProjectGuideCompilation.guide_id == guide_id,
                    ProjectGuideComponentProjectionOperation.policy_id == policy_id,
                )
            )
        ).one()
    actor = ActorIdentityFacts(UUID(actor_id), UUID(link_id), ActorKind.HUMAN)
    return actor, grant_id, compilation


async def supersede_unified_submission_policy(project_id, guide_id, policy_id):
    """Create a real corrected-generation successor while the guide is still draft."""
    from app.modules.projects.api.guide_proposals import GuideProposalCorrection
    from tests.projects.guide_compilation.proposals.pg_support import finalize_corrected_attempt

    sessions = db_session.get_session_factory()
    actor, grant, compilation = await _approval_context(sessions, project_id, guide_id, policy_id)
    async with sessions() as session:
        service_actor, service_link = (await session.execute(
            select(ActorProfile.id, ActorIdentityLink.id)
            .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
            .where(ActorProfile.service_identity == "workstream.project.setup", ActorIdentityLink.status == "active")
        )).one()
    async with sessions() as session, session.begin():
        service = GuideProposalService(session, ProposalAuthority(session, actor, UUID(project_id), grant))
        package = await service.review_package(GuideProposalSelection(
            project_id=project_id, guide_id=guide_id, compilation_id=compilation.id,
        ), actor=actor, request_id=uuid4())
    async with sessions() as session, session.begin():
        correction = await GuideProposalService(session, ProposalAuthority(session, actor, UUID(project_id), grant)).request_correction(
            GuideProposalCorrection(target=package.target, idempotency_key=uuid4(), reason="Reconsider the proposal."),
            actor=actor, request_id=uuid4(),
        )
    values = {"project": UUID(project_id), "guide": UUID(guide_id), "actor": UUID(service_actor), "link": UUID(service_link)}
    next_command = await finalize_corrected_attempt(sessions, values, actor, correction)
    async with sessions() as session:
        next_policy_id = (await session.scalars(select(ProjectGuideComponentProjectionOperation.policy_id).where(
            ProjectGuideComponentProjectionOperation.compilation_id == next_command.compilation_id,
            ProjectGuideComponentProjectionOperation.component == "submission_artifact_policy",
        ))).one()
    return await approve_unified_submission_policy(project_id, guide_id, next_policy_id)
