"""Database access methods for project and project-guide records."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSufficiencyReport,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
    ProjectSetupRun,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)


class ProjectRepositoryIntegrityError(RuntimeError):
    """Raised when persisted project data violates repository invariants."""


class ProjectRepository:
    """Wraps SQLAlchemy persistence for the project guide lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a repository bound to the current database session.

        Args:
            session: Async SQLAlchemy session for the current unit of work.
        """
        self._session = session

    def _resolve_current_append_only_row(
        self,
        rows: Sequence[Any],
        supersedes_field: str,
        description: str,
    ) -> Any | None:
        """Return the row not superseded by another row in an append-only chain."""
        superseded_ids = {
            getattr(row, supersedes_field)
            for row in rows
            if getattr(row, supersedes_field) is not None
        }
        current_rows = [row for row in rows if row.id not in superseded_ids]
        if len(current_rows) > 1:
            raise ProjectRepositoryIntegrityError(f"multiple current {description} found")
        if not current_rows:
            return None
        return current_rows[0]

    async def add_project(self, project: Project) -> Project:
        """Persist a new project and refresh generated database fields.

        Args:
            project: Project model to add to the session.

        Returns:
            Persisted project model.
        """
        self._session.add(project)
        await self._session.flush()
        await self._session.refresh(project)
        return project

    async def get_project(
        self,
        project_id: str,
        *,
        for_update: bool = False,
    ) -> Project | None:
        """Load one project by primary key.

        Args:
            project_id: Project id to load.
            for_update: Lock the canonical project row in the caller transaction.

        Returns:
            Project model when found; otherwise ``None``.
        """
        if not for_update:
            return await self._session.get(Project, project_id)
        return await self._session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )

    async def add_guide(self, guide: ProjectGuide) -> ProjectGuide:
        """Persist a new project guide and refresh generated database fields.

        Args:
            guide: Project guide model to add to the session.

        Returns:
            Persisted project guide model.
        """
        self._session.add(guide)
        await self._session.flush()
        await self._session.refresh(guide)
        return guide

    async def get_guide(self, guide_id: str) -> ProjectGuide | None:
        """Load one project guide by primary key.

        Args:
            guide_id: Guide id to load.

        Returns:
            Project guide model when found; otherwise ``None``.
        """
        return await self._session.get(ProjectGuide, guide_id)

    async def lock_project_guide(self, guide_id: str) -> ProjectGuide | None:
        """Load one project guide with a transactional row lock."""
        result = await self._session.execute(
            select(ProjectGuide)
            .where(ProjectGuide.id == guide_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_active_guide(self, project_id: str) -> ProjectGuide | None:
        """Load the active guide for a project.

        Args:
            project_id: Project id whose active guide should be loaded.

        Returns:
            Active guide when present; otherwise ``None``.

        Raises:
            ProjectRepositoryIntegrityError: If more than one active guide is
                found for the project.
        """
        result = await self._session.execute(
            select(ProjectGuide).where(
                ProjectGuide.project_id == project_id,
                ProjectGuide.status == "active",
            )
        )
        active_guides = list(result.scalars().all())
        if not active_guides:
            return None
        if len(active_guides) > 1:
            raise ProjectRepositoryIntegrityError("multiple active guides found for project")
        return active_guides[0]

    async def get_guide_by_version(self, project_id: str, version: str) -> ProjectGuide | None:
        """Load one project guide by project id and version.

        Args:
            project_id: Project that owns the guide.
            version: Guide version to load.

        Returns:
            Project guide when found; otherwise ``None``.
        """
        result = await self._session.execute(
            select(ProjectGuide).where(
                ProjectGuide.project_id == project_id,
                ProjectGuide.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def add_guide_source_snapshot(
        self,
        snapshot: GuideSourceSnapshot,
        items: Sequence[GuideSourceSnapshotItem],
    ) -> GuideSourceSnapshot:
        """Persist an immutable guide-source snapshot and its source items.

        Args:
            snapshot: Snapshot bundle model to persist.
            items: Sanitized source items included in the snapshot manifest.

        Returns:
            Persisted snapshot model.
        """
        self._session.add(snapshot)
        self._session.add_all(items)
        await self._session.flush()
        await self._session.refresh(snapshot)
        return snapshot

    async def get_guide_source_snapshot(
        self,
        snapshot_id: str,
    ) -> GuideSourceSnapshot | None:
        """Load one guide-source snapshot by primary key.

        Args:
            snapshot_id: Snapshot id to load.

        Returns:
            Snapshot when found; otherwise ``None``.
        """
        return await self._session.get(GuideSourceSnapshot, snapshot_id)

    async def list_guide_source_snapshots(
        self,
        project_id: str,
        guide_id: str,
        guide_version: str,
    ) -> Sequence[GuideSourceSnapshot]:
        """List snapshots created for a guide version.

        Args:
            project_id: Project that owns the guide.
            guide_id: Guide id whose snapshots should be loaded.
            guide_version: Guide version whose snapshots should be loaded.

        Returns:
            Snapshots ordered by creation time.
        """
        result = await self._session.execute(
            select(GuideSourceSnapshot)
            .where(
                GuideSourceSnapshot.project_id == project_id,
                GuideSourceSnapshot.guide_id == guide_id,
                GuideSourceSnapshot.guide_version == guide_version,
            )
            .order_by(GuideSourceSnapshot.captured_at)
        )
        return result.scalars().all()

    async def get_latest_guide_source_snapshot(
        self,
        project_id: str,
        guide_id: str,
        guide_version: str,
    ) -> GuideSourceSnapshot | None:
        """Load the latest source snapshot for a guide version."""
        result = await self._session.execute(
            select(GuideSourceSnapshot)
            .where(
                GuideSourceSnapshot.project_id == project_id,
                GuideSourceSnapshot.guide_id == guide_id,
                GuideSourceSnapshot.guide_version == guide_version,
            )
            .order_by(GuideSourceSnapshot.captured_at.desc())
            .limit(2)
        )
        snapshots = list(result.scalars().all())
        if not snapshots:
            return None
        if len(snapshots) > 1 and snapshots[0].captured_at == snapshots[1].captured_at:
            raise ProjectRepositoryIntegrityError(
                "latest guide source snapshot is ambiguous for guide version"
            )
        return snapshots[0]

    async def list_guide_source_snapshot_items(
        self,
        snapshot_id: str,
    ) -> Sequence[GuideSourceSnapshotItem]:
        """List sanitized source items for a snapshot in deterministic order.

        Args:
            snapshot_id: Snapshot id whose items should be loaded.

        Returns:
            Source items ordered by manifest item order.
        """
        result = await self._session.execute(
            select(GuideSourceSnapshotItem)
            .where(GuideSourceSnapshotItem.source_snapshot_id == snapshot_id)
            .order_by(GuideSourceSnapshotItem.item_order)
        )
        return result.scalars().all()

    async def add_project_setup_run(
        self,
        setup_run: ProjectSetupRun,
    ) -> ProjectSetupRun:
        """Persist a project setup run ledger row."""
        self._session.add(setup_run)
        await self._session.flush()
        await self._session.refresh(setup_run)
        return setup_run

    async def get_project_setup_run(self, setup_run_id: str) -> ProjectSetupRun | None:
        """Load one project setup run by primary key."""
        return await self._session.get(ProjectSetupRun, setup_run_id)

    async def lock_project_setup_run(self, setup_run_id: str) -> ProjectSetupRun | None:
        """Load one project setup run with a transactional row lock."""
        result = await self._session.execute(
            select(ProjectSetupRun)
            .where(ProjectSetupRun.id == setup_run_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_latest_project_setup_run(
        self,
        project_id: str,
        guide_id: str,
    ) -> ProjectSetupRun | None:
        """Load the latest setup run for one project guide."""
        result = await self._session.execute(
            select(ProjectSetupRun)
            .join(GuideSourceSnapshot, ProjectSetupRun.source_snapshot_id == GuideSourceSnapshot.id)
            .where(
                ProjectSetupRun.project_id == project_id,
                ProjectSetupRun.guide_id == guide_id,
            )
            .order_by(
                GuideSourceSnapshot.captured_at.desc(),
                ProjectSetupRun.created_at.desc(),
                ProjectSetupRun.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_guide_sufficiency_report(
        self,
        report: GuideSufficiencyReport,
    ) -> GuideSufficiencyReport:
        """Persist a guide sufficiency report.

        Args:
            report: Sufficiency report to persist.

        Returns:
            Persisted sufficiency report.
        """
        self._session.add(report)
        await self._session.flush()
        await self._session.refresh(report)
        return report

    async def get_guide_sufficiency_report(
        self,
        report_id: str,
    ) -> GuideSufficiencyReport | None:
        """Load one guide sufficiency report by primary key."""
        return await self._session.get(GuideSufficiencyReport, report_id)

    async def list_guide_sufficiency_reports(
        self,
        project_id: str,
        guide_id: str,
    ) -> Sequence[GuideSufficiencyReport]:
        """List sufficiency reports for one project guide."""
        result = await self._session.execute(
            select(GuideSufficiencyReport)
            .where(
                GuideSufficiencyReport.project_id == project_id,
                GuideSufficiencyReport.guide_id == guide_id,
            )
            .order_by(GuideSufficiencyReport.created_at.desc(), GuideSufficiencyReport.id.desc())
        )
        return result.scalars().all()

    async def get_sufficiency_report_for_snapshot(
        self,
        snapshot_id: str,
    ) -> GuideSufficiencyReport | None:
        """Load the sufficiency report bound to a guide-source snapshot."""
        result = await self._session.execute(
            select(GuideSufficiencyReport).where(
                GuideSufficiencyReport.source_snapshot_id == snapshot_id
            )
        )
        return result.scalar_one_or_none()

    async def add_submission_artifact_policy(
        self,
        policy: SubmissionArtifactPolicy,
    ) -> SubmissionArtifactPolicy:
        """Persist a draft submission artifact policy.

        Args:
            policy: Policy model to persist.

        Returns:
            Persisted policy model.
        """
        self._session.add(policy)
        await self._session.flush()
        await self._session.refresh(policy)
        return policy

    async def get_submission_artifact_policy(
        self,
        policy_id: str,
    ) -> SubmissionArtifactPolicy | None:
        """Load one submission artifact policy by primary key."""
        return await self._session.get(SubmissionArtifactPolicy, policy_id)

    async def list_submission_artifact_policies(
        self,
        project_id: str,
        guide_id: str,
    ) -> Sequence[SubmissionArtifactPolicy]:
        """List submission artifact policies for one project guide."""
        result = await self._session.execute(
            select(SubmissionArtifactPolicy)
            .where(
                SubmissionArtifactPolicy.project_id == project_id,
                SubmissionArtifactPolicy.guide_id == guide_id,
            )
            .order_by(
                SubmissionArtifactPolicy.created_at.desc(),
                SubmissionArtifactPolicy.id.desc(),
            )
        )
        return result.scalars().all()

    async def get_agent_derived_submission_artifact_policy_for_snapshot(
        self,
        project_id: str,
        guide_version: str,
        source_snapshot_id: str,
    ) -> SubmissionArtifactPolicy | None:
        """Load the current agent-derived policy for one guide source snapshot."""
        result = await self._session.execute(
            select(SubmissionArtifactPolicy).where(
                SubmissionArtifactPolicy.project_id == project_id,
                SubmissionArtifactPolicy.guide_version == guide_version,
                SubmissionArtifactPolicy.source_snapshot_id == source_snapshot_id,
                SubmissionArtifactPolicy.derivation_source == "agent_derivation",
                SubmissionArtifactPolicy.lifecycle_status.in_(["draft", "approved"]),
            )
        )
        rows = result.scalars().all()
        if len(rows) > 1:
            raise ProjectRepositoryIntegrityError(
                "multiple current agent-derived submission artifact policies found"
            )
        if not rows:
            return None
        return rows[0]

    async def lock_submission_artifact_policy(
        self,
        policy_id: str,
    ) -> SubmissionArtifactPolicy | None:
        """Load one submission artifact policy with a transactional row lock."""
        result = await self._session.execute(
            select(SubmissionArtifactPolicy)
            .where(SubmissionArtifactPolicy.id == policy_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_approved_submission_artifact_policy(
        self,
        project_id: str,
        guide_version: str,
        source_snapshot_id: str,
    ) -> SubmissionArtifactPolicy | None:
        """Load the approved policy for one guide source snapshot."""
        result = await self._session.execute(
            select(SubmissionArtifactPolicy).where(
                SubmissionArtifactPolicy.project_id == project_id,
                SubmissionArtifactPolicy.guide_version == guide_version,
                SubmissionArtifactPolicy.source_snapshot_id == source_snapshot_id,
                SubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        return self._resolve_current_append_only_row(
            result.scalars().all(),
            "supersedes_policy_id",
            "submission artifact policies",
        )

    async def get_current_approved_submission_artifact_policy(
        self,
        project_id: str,
        guide_version: str,
    ) -> SubmissionArtifactPolicy | None:
        """Load the current approved policy for one guide version."""
        result = await self._session.execute(
            select(SubmissionArtifactPolicy).where(
                SubmissionArtifactPolicy.project_id == project_id,
                SubmissionArtifactPolicy.guide_version == guide_version,
                SubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        return self._resolve_current_append_only_row(
            result.scalars().all(),
            "supersedes_policy_id",
            "submission artifact policies",
        )

    async def list_approved_submission_artifact_policies(
        self,
        project_id: str,
        guide_version: str,
    ) -> Sequence[SubmissionArtifactPolicy]:
        """List approved submission artifact policies for one guide version."""
        result = await self._session.execute(
            select(SubmissionArtifactPolicy).where(
                SubmissionArtifactPolicy.project_id == project_id,
                SubmissionArtifactPolicy.guide_version == guide_version,
                SubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        return result.scalars().all()

    async def add_effective_submission_artifact_policy(
        self,
        policy: EffectiveProjectSubmissionArtifactPolicy,
    ) -> EffectiveProjectSubmissionArtifactPolicy:
        """Persist an effective project submission artifact policy."""
        self._session.add(policy)
        await self._session.flush()
        await self._session.refresh(policy)
        return policy

    async def get_effective_submission_artifact_policy(
        self,
        project_id: str,
        guide_version: str,
        source_snapshot_id: str,
    ) -> EffectiveProjectSubmissionArtifactPolicy | None:
        """Load the active effective policy for one guide source snapshot."""
        result = await self._session.execute(
            select(EffectiveProjectSubmissionArtifactPolicy).where(
                EffectiveProjectSubmissionArtifactPolicy.project_id == project_id,
                EffectiveProjectSubmissionArtifactPolicy.guide_version == guide_version,
                EffectiveProjectSubmissionArtifactPolicy.source_snapshot_id == source_snapshot_id,
                EffectiveProjectSubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        return self._resolve_current_append_only_row(
            result.scalars().all(),
            "supersedes_effective_policy_id",
            "effective project submission artifact policies",
        )

    async def get_effective_submission_artifact_policy_by_id(
        self,
        policy_id: str,
    ) -> EffectiveProjectSubmissionArtifactPolicy | None:
        """Load one effective project submission artifact policy by primary key."""
        return await self._session.get(EffectiveProjectSubmissionArtifactPolicy, policy_id)

    async def add_pre_submit_checker_policy(
        self,
        policy: PreSubmitCheckerPolicy,
    ) -> PreSubmitCheckerPolicy:
        """Persist a project pre-submit checker policy contract."""
        self._session.add(policy)
        await self._session.flush()
        await self._session.refresh(policy)
        return policy

    async def get_pre_submit_checker_policy_for_effective_policy(
        self,
        effective_policy_id: str,
    ) -> PreSubmitCheckerPolicy | None:
        """Load the pre-submit checker policy bound to one effective policy."""
        result = await self._session.execute(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy_id,
                PreSubmitCheckerPolicy.lifecycle_status.in_(
                    ["pending_compilation", "compiled"]
                ),
            )
        )
        rows = result.scalars().all()
        if len(rows) > 1:
            raise ProjectRepositoryIntegrityError(
                "multiple pre-submit checker policies found for effective policy"
            )
        if not rows:
            return None
        return rows[0]

    async def get_pre_submit_checker_policy(
        self,
        policy_id: str,
    ) -> PreSubmitCheckerPolicy | None:
        """Load one project pre-submit checker policy by primary key."""
        return await self._session.get(PreSubmitCheckerPolicy, policy_id)

    async def get_current_pre_submit_checker_policy(
        self,
        project_id: str,
        guide_version: str,
    ) -> PreSubmitCheckerPolicy | None:
        """Load the current pre-submit checker policy for one guide version."""
        result = await self._session.execute(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.project_id == project_id,
                PreSubmitCheckerPolicy.guide_version == guide_version,
                PreSubmitCheckerPolicy.lifecycle_status.in_(
                    ["pending_compilation", "compiled"]
                ),
            )
        )
        return self._resolve_current_append_only_row(
            result.scalars().all(),
            "supersedes_pre_submit_checker_policy_id",
            "pre-submit checker policies",
        )

    async def list_active_guides(self, project_id: str) -> Sequence[ProjectGuide]:
        """List active guides for a project.

        Args:
            project_id: Project id whose active guides should be listed.

        Returns:
            Sequence of active guides, normally empty or one after DB constraints.
        """
        result = await self._session.execute(
            select(ProjectGuide).where(
                ProjectGuide.project_id == project_id,
                ProjectGuide.status == "active",
            )
        )
        return result.scalars().all()

    async def upsert_post_submit_checker_policy(
        self,
        policy: PostSubmitCheckerPolicy,
    ) -> PostSubmitCheckerPolicy:
        """Create or replace a post-submit checker policy for one guide version.

        Args:
            policy: Post-submit checker policy model carrying the desired values.

        Returns:
            Persisted post-submit checker policy model.
        """
        existing = await self.get_post_submit_checker_policy(
            policy.project_id,
            policy.guide_version,
        )
        if existing is None:
            self._session.add(policy)
            await self._session.flush()
            await self._session.refresh(policy)
            return policy
        if (
            existing.required_checkers != policy.required_checkers
            or existing.warning_checkers != policy.warning_checkers
            or existing.blocking_severities != policy.blocking_severities
            or existing.policy_hash != policy.policy_hash
            or existing.policy_body != policy.policy_body
            or existing.guide_id != policy.guide_id
            or existing.source_snapshot_id != policy.source_snapshot_id
            or existing.source_snapshot_hash != policy.source_snapshot_hash
            or existing.effective_policy_id != policy.effective_policy_id
            or existing.effective_policy_hash != policy.effective_policy_hash
            or existing.pre_submit_checker_policy_id != policy.pre_submit_checker_policy_id
            or existing.pre_submit_checker_bundle_hash != policy.pre_submit_checker_bundle_hash
        ):
            raise ProjectRepositoryIntegrityError(
                "post-submit checker policy already exists with different content"
            )
        return existing

    async def get_post_submit_checker_policy(
        self,
        project_id: str,
        guide_version: str,
    ) -> PostSubmitCheckerPolicy | None:
        """Load a post-submit checker policy by project and guide version.

        Args:
            project_id: Project id that owns the policy.
            guide_version: Guide version the policy applies to.

        Returns:
            Post-submit checker policy when found; otherwise ``None``.
        """
        result = await self._session.execute(
            select(PostSubmitCheckerPolicy).where(
                PostSubmitCheckerPolicy.project_id == project_id,
                PostSubmitCheckerPolicy.guide_version == guide_version,
                PostSubmitCheckerPolicy.lifecycle_status.in_(["compiled", "approved"]),
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_superseded_post_submit_checker_policy(
        self,
        project_id: str,
        guide_id: str,
        guide_version: str,
        source_snapshot_id: str,
        source_snapshot_hash: str,
        effective_policy_id: str,
        effective_policy_hash: str,
        pre_submit_checker_policy_id: str,
        pre_submit_checker_bundle_hash: str,
    ) -> PostSubmitCheckerPolicy | None:
        """Load the latest rejected policy retained for correction provenance."""
        result = await self._session.execute(
            select(PostSubmitCheckerPolicy)
            .where(
                PostSubmitCheckerPolicy.project_id == project_id,
                PostSubmitCheckerPolicy.guide_id == guide_id,
                PostSubmitCheckerPolicy.guide_version == guide_version,
                PostSubmitCheckerPolicy.source_snapshot_id == source_snapshot_id,
                PostSubmitCheckerPolicy.source_snapshot_hash == source_snapshot_hash,
                PostSubmitCheckerPolicy.effective_policy_id == effective_policy_id,
                PostSubmitCheckerPolicy.effective_policy_hash == effective_policy_hash,
                PostSubmitCheckerPolicy.pre_submit_checker_policy_id
                == pre_submit_checker_policy_id,
                PostSubmitCheckerPolicy.pre_submit_checker_bundle_hash
                == pre_submit_checker_bundle_hash,
                PostSubmitCheckerPolicy.lifecycle_status == "superseded",
            )
            .order_by(
                PostSubmitCheckerPolicy.superseded_at.desc(),
                PostSubmitCheckerPolicy.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_superseded_post_submit_checker_policies(
        self,
        project_id: str,
        guide_id: str,
        guide_version: str,
        source_snapshot_id: str,
        source_snapshot_hash: str,
        effective_policy_id: str,
        effective_policy_hash: str,
        pre_submit_checker_policy_id: str,
        pre_submit_checker_bundle_hash: str,
    ) -> Sequence[PostSubmitCheckerPolicy]:
        """List retained correction records newest first for operator visibility."""
        result = await self._session.execute(
            select(PostSubmitCheckerPolicy)
            .where(
                PostSubmitCheckerPolicy.project_id == project_id,
                PostSubmitCheckerPolicy.guide_id == guide_id,
                PostSubmitCheckerPolicy.guide_version == guide_version,
                PostSubmitCheckerPolicy.source_snapshot_id == source_snapshot_id,
                PostSubmitCheckerPolicy.source_snapshot_hash == source_snapshot_hash,
                PostSubmitCheckerPolicy.effective_policy_id == effective_policy_id,
                PostSubmitCheckerPolicy.effective_policy_hash == effective_policy_hash,
                PostSubmitCheckerPolicy.pre_submit_checker_policy_id
                == pre_submit_checker_policy_id,
                PostSubmitCheckerPolicy.pre_submit_checker_bundle_hash
                == pre_submit_checker_bundle_hash,
                PostSubmitCheckerPolicy.lifecycle_status == "superseded",
                PostSubmitCheckerPolicy.supersession_kind == "correction_requested",
            )
            .order_by(
                PostSubmitCheckerPolicy.superseded_at.desc(),
                PostSubmitCheckerPolicy.id.desc(),
            )
            .limit(100)
        )
        return result.scalars().all()

    async def get_post_submit_checker_policy_by_id(
        self,
        policy_id: str,
    ) -> PostSubmitCheckerPolicy | None:
        """Load a post-submit checker policy by id."""
        return await self._session.get(PostSubmitCheckerPolicy, policy_id)

    async def lock_post_submit_checker_policy(
        self,
        policy_id: str,
    ) -> PostSubmitCheckerPolicy | None:
        """Load one post-submit checker policy with a transactional row lock."""
        result = await self._session.execute(
            select(PostSubmitCheckerPolicy)
            .where(PostSubmitCheckerPolicy.id == policy_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def upsert_review_policy(self, policy: ReviewPolicy) -> ReviewPolicy:
        """Create or replace a review policy for one guide version.

        Args:
            policy: Review policy model carrying the desired values.

        Returns:
            Persisted review policy model.
        """
        existing = await self.get_review_policy(policy.project_id, policy.guide_version)
        if existing is None:
            self._session.add(policy)
            await self._session.flush()
            await self._session.refresh(policy)
            return policy
        existing.requires_second_review = policy.requires_second_review
        existing.allowed_decisions = policy.allowed_decisions
        existing.minimum_finding_fields = policy.minimum_finding_fields
        existing.sla_hours = policy.sla_hours
        await self._session.flush()
        await self._session.refresh(existing)
        return existing

    async def get_review_policy(self, project_id: str, guide_version: str) -> ReviewPolicy | None:
        """Load a review policy by project and guide version.

        Args:
            project_id: Project id that owns the policy.
            guide_version: Guide version the policy applies to.

        Returns:
            Review policy when found; otherwise ``None``.
        """
        result = await self._session.execute(
            select(ReviewPolicy).where(
                ReviewPolicy.project_id == project_id,
                ReviewPolicy.guide_version == guide_version,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_revision_policy(self, policy: RevisionPolicy) -> RevisionPolicy:
        """Create or replace a revision policy for one guide version.

        Args:
            policy: Revision policy model carrying the desired values.

        Returns:
            Persisted revision policy model.
        """
        existing = await self.get_revision_policy(policy.project_id, policy.guide_version)
        if existing is None:
            self._session.add(policy)
            await self._session.flush()
            await self._session.refresh(policy)
            return policy
        existing.max_revision_rounds = policy.max_revision_rounds
        existing.revision_deadline_hours = policy.revision_deadline_hours
        existing.auto_reject_after_limit = policy.auto_reject_after_limit
        existing.allowed_resubmission_states = policy.allowed_resubmission_states
        existing.reviewer_reassignment_rule = policy.reviewer_reassignment_rule
        await self._session.flush()
        await self._session.refresh(existing)
        return existing

    async def get_revision_policy(
        self,
        project_id: str,
        guide_version: str,
    ) -> RevisionPolicy | None:
        """Load a revision policy by project and guide version.

        Args:
            project_id: Project id that owns the policy.
            guide_version: Guide version the policy applies to.

        Returns:
            Revision policy when found; otherwise ``None``.
        """
        result = await self._session.execute(
            select(RevisionPolicy).where(
                RevisionPolicy.project_id == project_id,
                RevisionPolicy.guide_version == guide_version,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_payment_policy(self, policy: PaymentPolicy) -> PaymentPolicy:
        """Create or replace a payment policy for one guide version.

        Args:
            policy: Payment policy model carrying the desired values.

        Returns:
            Persisted payment policy model.
        """
        existing = await self.get_payment_policy(policy.project_id, policy.guide_version)
        if existing is None:
            self._session.add(policy)
            await self._session.flush()
            await self._session.refresh(policy)
            return policy
        existing.base_amount = policy.base_amount
        existing.currency = policy.currency
        existing.payout_type = policy.payout_type
        existing.revision_payment_rule = policy.revision_payment_rule
        existing.rejection_payment_rule = policy.rejection_payment_rule
        existing.accepted_payment_rule = policy.accepted_payment_rule
        await self._session.flush()
        await self._session.refresh(existing)
        return existing

    async def get_payment_policy(self, project_id: str, guide_version: str) -> PaymentPolicy | None:
        """Load a payment policy by project and guide version.

        Args:
            project_id: Project id that owns the policy.
            guide_version: Guide version the policy applies to.

        Returns:
            Payment policy when found; otherwise ``None``.
        """
        result = await self._session.execute(
            select(PaymentPolicy).where(
                PaymentPolicy.project_id == project_id,
                PaymentPolicy.guide_version == guide_version,
            )
        )
        return result.scalar_one_or_none()
