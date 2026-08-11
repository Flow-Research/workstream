"""PROJECT persistence for exact task-locked policy lineage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api import (
    CanonicalJsonObject,
    ProjectLockedPolicyContextFacts,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
)


class ProjectLockedPolicyRepository:
    """Resolve one exact historical locked-policy context under PROJECT locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_locked_policy_context(
        self, request: ProjectLockedPolicyContextRequest
    ) -> ProjectLockedPolicyContextFacts:
        """Lock, validate, and return the exact selected policy lineage."""

        async def lock_by_id(model: Any, identifier: UUID) -> Any:
            return await self._session.scalar(
                select(model)
                .where(model.id == str(identifier))
                .with_for_update()
                .execution_options(populate_existing=True)
            )

        project = await lock_by_id(Project, request.project_id)
        guide = await self._session.scalar(
            select(ProjectGuide)
            .where(
                ProjectGuide.project_id == str(request.project_id),
                ProjectGuide.version == request.guide_version,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        snapshot = await lock_by_id(GuideSourceSnapshot, request.source_snapshot_id)
        effective_policy = await lock_by_id(
            EffectiveProjectSubmissionArtifactPolicy, request.effective_policy_id
        )
        pre_submit_policy = await lock_by_id(PreSubmitCheckerPolicy, request.pre_submit_policy_id)
        if (
            project is None
            or project.status != "active"
            or guide is None
            or guide.status not in {"active", "superseded"}
            or snapshot is None
            or effective_policy is None
            or effective_policy.lifecycle_status not in {"approved", "superseded"}
            or pre_submit_policy is None
            or pre_submit_policy.lifecycle_status not in {"compiled", "superseded"}
            or pre_submit_policy.compiler_version is None
            or pre_submit_policy.compiled_bundle is None
            or pre_submit_policy.compiled_bundle_hash is None
        ):
            raise ProjectLockedPolicyContextUnavailable("project_locked_policy_context_changed")
        values = (
            snapshot.manifest_json,
            effective_policy.effective_policy,
            pre_submit_policy.compiled_bundle,
        )
        if not all(isinstance(value, Mapping) for value in values):
            raise ProjectLockedPolicyContextUnavailable("project_locked_policy_context_changed")
        try:
            canonical_snapshot = CanonicalJsonObject.from_mapping(snapshot.manifest_json)
            canonical_effective = CanonicalJsonObject.from_mapping(
                effective_policy.effective_policy
            )
            canonical_pre_submit = CanonicalJsonObject.from_mapping(
                pre_submit_policy.compiled_bundle
            )
        except (TypeError, ValueError) as exc:
            raise ProjectLockedPolicyContextUnavailable(
                "project_locked_policy_context_changed"
            ) from exc
        expected = (
            guide.project_id == str(request.project_id),
            guide.version == request.guide_version,
            snapshot.project_id == str(request.project_id),
            snapshot.guide_id == guide.id,
            snapshot.guide_version == request.guide_version,
            snapshot.bundle_hash == request.source_snapshot_hash,
            effective_policy.project_id == str(request.project_id),
            effective_policy.guide_id == guide.id,
            effective_policy.guide_version == request.guide_version,
            effective_policy.source_snapshot_id == str(request.source_snapshot_id),
            effective_policy.source_snapshot_hash == request.source_snapshot_hash,
            effective_policy.effective_policy_hash == request.effective_policy_hash,
            pre_submit_policy.project_id == str(request.project_id),
            pre_submit_policy.guide_id == guide.id,
            pre_submit_policy.guide_version == request.guide_version,
            pre_submit_policy.source_snapshot_id == str(request.source_snapshot_id),
            pre_submit_policy.source_snapshot_hash == request.source_snapshot_hash,
            pre_submit_policy.effective_policy_id == str(request.effective_policy_id),
            pre_submit_policy.effective_policy_hash == request.effective_policy_hash,
            pre_submit_policy.compiled_bundle_hash == request.pre_submit_policy_bundle_hash,
            canonical_snapshot.sha256 == request.source_snapshot_hash,
            canonical_effective.sha256 == request.effective_policy_hash,
            canonical_pre_submit.sha256 == request.pre_submit_policy_bundle_hash,
        )
        if not all(expected):
            raise ProjectLockedPolicyContextUnavailable("project_locked_policy_context_changed")
        try:
            return ProjectLockedPolicyContextFacts(
                project_id=request.project_id,
                guide_id=UUID(guide.id),
                guide_version=guide.version,
                guide_status=guide.status,
                source_snapshot_id=request.source_snapshot_id,
                source_snapshot_hash=snapshot.bundle_hash,
                effective_policy_id=request.effective_policy_id,
                effective_policy_hash=effective_policy.effective_policy_hash,
                effective_policy_status=effective_policy.lifecycle_status,
                effective_policy=canonical_effective,
                pre_submit_policy_id=request.pre_submit_policy_id,
                pre_submit_policy_bundle_hash=pre_submit_policy.compiled_bundle_hash,
                pre_submit_policy_status=pre_submit_policy.lifecycle_status,
                pre_submit_compiler_version=pre_submit_policy.compiler_version,
                compiled_pre_submit_bundle=canonical_pre_submit,
            )
        except (TypeError, ValueError) as exc:
            raise ProjectLockedPolicyContextUnavailable(
                "project_locked_policy_context_changed"
            ) from exc
