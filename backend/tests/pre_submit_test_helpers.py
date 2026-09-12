"""Shared dependency-safe construction for focused pre-submit tests."""

from uuid import UUID, uuid4

from app.adapters.checkers import PreSubmitCheckerExecutionAdapter
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationService,
    PreparedBundlePreSubmitEvidenceService,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.tasks.repository import TaskRepository


def checker_execution(inspector, catalogue) -> PreSubmitCheckerExecutionAdapter:
    """Build the owner adapter used by ART materialization tests."""
    return PreSubmitCheckerExecutionAdapter(
        archive_inspector=inspector,
        catalogue=catalogue,
    )


def submission_preparation_request(
    request,
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
) -> SubmissionBundlePreparationRequest:
    """Project one private materialization fixture into the public ART request."""
    return SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            actor_kind=ActorKind.HUMAN,
        ),
        request_id=uuid4(),
        correlation_id=uuid4(),
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        predecessor_submission_id=None,
        idempotency_key=uuid4(),
        summary=request.packet.summary,
        contributor_attestation=request.packet.contributor_attestation,
        media_type="application/zip",
        byte_source=_empty_bytes(),
    )


async def _empty_bytes():
    if False:  # pragma: no cover - preserve the async-iterable request shape
        yield b""


def evidence_workflow(
    *, session, preparation, inspector, catalogue, materialization_authorization,
    preparation_authorization,
) -> PreparedBundlePreSubmitEvidenceService:
    """Compose the exact public-port evidence workflow for database proof."""
    return PreparedBundlePreSubmitEvidenceService(
        session=session,
        materialization=PreparedBundleMaterializationService(
            authorization=materialization_authorization,
            preparation=preparation,
            checker_execution=checker_execution(inspector, catalogue),
            storage_scheme="s3",
        ),
        preparation_authorization=preparation_authorization,
        task_contexts=TaskRepository(session),
        project_contexts=ProjectLockedPolicyRepository(session),
    )


async def approved_pre_submit_fixture(factory, namespace, *, guide_version):
    """Build supported PROJECTS custody before the ART evidence transaction."""
    from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
    from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
    from app.modules.checkers.api import EffectivePreSubmissionPlanLineage
    from app.modules.projects.api.guide_proposals import GuideProposalSelection
    from app.modules.projects.models import ProjectGuide
    from tests.projects.unified_policy_fixtures import create_standalone_unified_policy, _approval_context
    from tests.projects.guide_compilation.proposals.pg_support import seed_selected_review_revision_inputs

    values, effective, pre = await create_standalone_unified_policy(
        factory, namespace, guide_version=guide_version,
        artifact_proposal=SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1_000_000, maximum_package_size_bytes=5_000_000,
            required_artifacts=("task.toml",), required_evidence=("results",),
            attestation_terms=("rights_confirmed",),
        ),
    )
    actor, _grant, compilation = await _approval_context(
        factory, str(values["project"]), str(values["guide"]), effective["submission_artifact_policy_id"],
    )
    await seed_selected_review_revision_inputs(factory, GuideProposalSelection(
        project_id=values["project"], guide_id=values["guide"], compilation_id=compilation.id,
    ), actor)
    lineage = EffectivePreSubmissionPlanLineage(
        project_id=values["project"], guide_id=values["guide"], guide_version=guide_version,
        source_snapshot_id=values["snapshot"], source_snapshot_hash=effective["source_snapshot_hash"],
        effective_policy_id=UUID(effective["id"]), effective_policy_hash=effective["effective_policy_hash"],
        pre_submit_policy_id=UUID(pre.id), pre_submit_policy_bundle_hash=pre.compiled_bundle_hash,
    )
    plan = build_pre_submission_checker_catalogue().compile_effective_plan(
        lineage=lineage, effective_policy=effective["effective_policy"], compiled_bundle=pre.compiled_bundle,
    )
    async with factory() as session:
        guide = await session.get(ProjectGuide, str(values["guide"]))
        return plan, {
            "submission_policy": effective["submission_artifact_policy_id"],
            "review_policy": guide.selected_review_policy_id,
            "review_policy_hash": guide.selected_review_policy_hash,
            "revision_policy": guide.selected_revision_policy_id,
            "revision_policy_hash": guide.selected_revision_policy_hash,
            "guide_version": guide_version,
            "attestation_terms": effective["effective_policy"]["attestation_terms"],
            "evidence_path": "evidence/" + effective["effective_policy"]["required_evidence"][0]["key"],
        }
