"""Exact proposal reads over existing compilation and finalization custody."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import ProjectGuideCompilationResult
from app.modules.projects.api.guide_compilation import ProjectGuideSetupFinalizationCommand
from app.modules.projects.api.guide_proposals import (
    GuideProposalError,
    GuideProposalSelection,
    GuideProposalTarget,
)
from app.modules.projects.api.guide_proposal_package import (
    GuideProposalDisplayResult,
    GuideProposalReviewPackage,
)
from app.modules.projects.models import (
    GuideSourceArtifactIngest,
    GuideSourceSnapshotItem,
    ProjectSetupRun,
    SubmissionArtifactPolicy,
)

from .contracts import AcceptedCompilationResult
from .finalization_payloads import (
    LockedFinalization,
    compose_facts,
    require_lineage,
    require_replay,
)
from .models import ProjectGuideCompilation, ProjectGuideSetupFinalization
from .repository import GuideCompilationRepository
from .models import ProjectGuideProposalApproval


@dataclass(frozen=True)
class LockedGuideProposal:
    """Validated owner rows and the detached exact target shown to the manager."""

    view: LockedFinalization
    finalization: ProjectGuideSetupFinalization
    result: ProjectGuideCompilationResult
    target: GuideProposalTarget
    current: bool


class GuideProposalRepository:
    """Reuse the finalization lock order and validate every retained identity."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock(self, selection: GuideProposalSelection) -> LockedGuideProposal:
        """Resolve only the selected compilation, including retained predecessors."""
        compilation = await self.session.scalar(
            select(ProjectGuideCompilation).where(
                ProjectGuideCompilation.id == selection.compilation_id,
                ProjectGuideCompilation.project_id == str(selection.project_id),
                ProjectGuideCompilation.guide_id == str(selection.guide_id),
            )
        )
        if compilation is None:
            raise GuideProposalError("proposal_unavailable")
        command = ProjectGuideSetupFinalizationCommand(
            **selection.model_dump(include={"project_id", "guide_id", "compilation_id"}),
            setup_run_id=UUID(compilation.setup_run_id),
            setup_generation=compilation.setup_generation,
        )
        view = await GuideCompilationRepository(self.session).lock_finalization(
            command,
            compilation.attempt_id,
            exact_setup=True,
        )
        require_lineage(view, command, require_current=False)
        finalization = await self.session.scalar(
            select(ProjectGuideSetupFinalization)
            .where(
                ProjectGuideSetupFinalization.compilation_id == compilation.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if finalization is None:
            raise GuideProposalError("proposal_unavailable")
        facts = compose_facts(view, finalization.source_state_digest)
        require_replay(view, finalization, facts)
        accepted = AcceptedCompilationResult(
            canonical_result=view.compilation.canonical_result,
            result_hash=view.compilation.result_hash,
            component_hashes=view.compilation.component_hashes,
        )
        result = ProjectGuideCompilationResult.model_validate(accepted.canonical_result)
        attempt = view.attempt
        target = GuideProposalTarget(
            **selection.model_dump(include={"project_id", "guide_id", "compilation_id"}),
            guide_version=view.guide.version,
            source_snapshot_id=view.snapshot.id,
            source_snapshot_hash=view.snapshot.bundle_hash,
            setup_run_id=view.setup.id,
            setup_generation=view.setup.setup_generation,
            finalization_id=finalization.id,
            finalization_facts_digest=finalization.facts_digest,
            result_hash=accepted.result_hash,
            component_hashes=accepted.component_hashes,
            **{
                name: getattr(attempt, name)
                for name in (
                    "pre_catalogue_id",
                    "pre_catalogue_version",
                    "pre_catalogue_schema_version",
                    "pre_catalogue_manifest_hash",
                    "post_catalogue_id",
                    "post_catalogue_version",
                    "post_catalogue_schema_version",
                    "post_catalogue_manifest_hash",
                )
            },
            artifact_policy_id=finalization.artifact_policy_id,
            artifact_policy_hash=view.policy.policy_hash if view.policy is not None else None,
            artifact_projection_operation_id=finalization.artifact_policy_operation_id,
            artifact_projection_output_digest=finalization.artifact_policy_output_digest,
        )
        latest = await self.session.scalar(
            select(func.max(ProjectSetupRun.setup_generation)).where(
                ProjectSetupRun.guide_id == view.guide.id,
            )
        )
        return LockedGuideProposal(
            view,
            finalization,
            result,
            target,
            view.compilation_is_current and latest == view.setup.setup_generation,
        )

    async def current_approval(self, guide_id: UUID) -> ProjectGuideProposalApproval | None:
        """Read the exact approved tip while the guide serialization lock is held."""
        return (
            await self.session.scalars(
                select(ProjectGuideProposalApproval)
                .join(
                    SubmissionArtifactPolicy,
                    SubmissionArtifactPolicy.id == ProjectGuideProposalApproval.artifact_policy_id,
                )
                .where(
                    ProjectGuideProposalApproval.guide_id == str(guide_id),
                    SubmissionArtifactPolicy.lifecycle_status == "approved",
                )
                .with_for_update()
            )
        ).one_or_none()

    async def package(self, locked: LockedGuideProposal) -> GuideProposalReviewPackage:
        """Project safe content and page labels without exposing document handles."""
        sources = (
            await self.session.execute(
                select(GuideSourceSnapshotItem, GuideSourceArtifactIngest)
                .join(
                    GuideSourceArtifactIngest,
                    GuideSourceArtifactIngest.source_item_id == GuideSourceSnapshotItem.id,
                )
                .where(GuideSourceSnapshotItem.source_snapshot_id == locked.view.snapshot.id)
                .order_by(GuideSourceSnapshotItem.item_order, GuideSourceSnapshotItem.id)
            )
        ).all()
        locations = {
            (str(item.id), str(ingest.id), ingest.sha256): number
            for number, (item, ingest) in enumerate(sources, 1)
        }
        body = locked.result.model_dump(mode="json")
        for name in ("findings", "requirements", "capability_suggestions"):
            for item in body[name]:
                projected = []
                for ref in item["evidence_refs"]:
                    number = locations.get(
                        (
                            ref["source_item_id"],
                            ref["document_version_id"],
                            ref["sha256"],
                        )
                    )
                    if number is None:
                        raise GuideProposalError("proposal_unavailable")
                    projected.append(
                        {
                            "document_number": number,
                            "start_page": ref["start_page"],
                            "end_page": ref["end_page"],
                            "section": ref["section"],
                        }
                    )
                item["evidence_refs"] = projected
        display = GuideProposalDisplayResult.model_validate(body)
        approval = await self.current_approval(locked.target.guide_id)
        return GuideProposalReviewPackage(
            target=locked.target,
            target_digest=locked.target.digest,
            result=display,
            current=locked.current,
            artifact_policy_status=locked.view.policy.lifecycle_status
            if locked.view.policy is not None
            else None,
            warning_hashes=tuple(
                sorted(
                    canonical_json_hash(finding.model_dump(mode="json"))
                    for finding in locked.result.findings
                    if finding.severity == "warning"
                )
            ),
            current_approval_operation_id=approval.operation_id if approval else None,
            current_approval_output_digest=approval.output_digest if approval else None,
        )
