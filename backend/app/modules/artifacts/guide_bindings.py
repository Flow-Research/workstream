"""Authoritative guide-source binding for one exact setup generation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifact_operations import (
    GuideSourceBindingRequest,
    GuideSourceBindingResult,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.models import (
    ArtifactContent,
    GuideSourceArtifactBinding,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    GuideSourceBindingAuthorityFacts,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.projects.models import (
    GuideSourceSnapshot,
    ProjectGuide,
    ProjectSetupRun,
)


class GuideSourceBindingError(RuntimeError):
    """Fail-closed guide binding rejection without leaking lineage details."""


def guide_source_binding_authority_facts(
    *,
    project_id: UUID,
    guide_id: UUID,
    source_snapshot_id: UUID,
    source_item_id: UUID,
    setup_run_id: UUID,
    setup_generation: int,
    content_id: UUID,
    replica_id: UUID,
    sha256: str,
    byte_count: int,
    logical_role: str = "guide_source_original",
) -> GuideSourceBindingAuthorityFacts:
    """Compose the one canonical AUTH fact set used to prepare and consume."""
    return GuideSourceBindingAuthorityFacts(
        project_id=project_id,
        guide_id=guide_id,
        guide_source_snapshot_id=source_snapshot_id,
        guide_source_item_id=source_item_id,
        project_setup_run_id=setup_run_id,
        setup_generation=setup_generation,
        content_id=content_id,
        verified_replica_id=replica_id,
        sha256=sha256,
        byte_count=byte_count,
        logical_role=logical_role,
    )


class GuideSourceBindingPreparedAuthorization(Protocol):
    """AUTH-04B seam for one transaction-bound fixed-service capability."""

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideSourceBindingAuthorityFacts,
    ) -> None: ...


class DenyGuideSourceBindingPreparedAuthorization:
    """Production default until AUTH-04B activates exact binding authority."""

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideSourceBindingAuthorityFacts,
    ) -> None:
        del prepared_authorization, facts
        raise ArtifactAuthorityDeniedError("guide source binding is unavailable")


class GuideSourceBindingService:
    """Implement ``ArtifactBindingPort.bind_guide_source`` without provider I/O."""

    def __init__(
        self,
        session: AsyncSession,
        authority: GuideSourceBindingPreparedAuthorization | None = None,
    ) -> None:
        self._session = session
        self._repository = ArtifactRepository(session)
        self._authority = authority or DenyGuideSourceBindingPreparedAuthorization()

    async def bind_guide_source(
        self,
        request: GuideSourceBindingRequest,
    ) -> GuideSourceBindingResult:
        """Bind the one verified item/content fact in the caller's root transaction."""
        if (
            not self._session.in_transaction()
            or self._session.in_nested_transaction()
            or type(request.prepared_authorization) is not PreparedAuthorizationHandle
            or request.logical_role != "guide_source_original"
            or request.setup_generation <= 0
        ):
            raise GuideSourceBindingError("guide source binding is unavailable")

        lineage = await self._repository.get_guide_lineage(str(request.source_item_id))
        admission = await self._repository.get_guide_admission_facts(str(request.source_item_id))
        if (
            lineage is None
            or admission is None
            or lineage.project_id != str(request.project_id)
            or lineage.guide_id != str(request.guide_id)
            or lineage.guide_source_snapshot_id != str(request.guide_source_snapshot_id)
            or admission.guide_source_item_id != lineage.guide_source_item_id
            or admission.guide_source_snapshot_id != lineage.guide_source_snapshot_id
            or admission.guide_id != lineage.guide_id
            or admission.project_id != lineage.project_id
        ):
            raise GuideSourceBindingError("guide source binding is unavailable")

        guide = await self._session.scalar(
            select(ProjectGuide).where(ProjectGuide.id == str(request.guide_id)).with_for_update()
        )
        snapshot = await self._session.scalar(
            select(GuideSourceSnapshot)
            .where(GuideSourceSnapshot.id == str(request.guide_source_snapshot_id))
            .with_for_update()
        )
        setup_run = await self._session.scalar(
            select(ProjectSetupRun)
            .where(ProjectSetupRun.id == str(request.project_setup_run_id))
            .with_for_update()
        )
        content = await self._session.scalar(
            select(ArtifactContent)
            .where(ArtifactContent.id == str(request.verified_content_id))
            .with_for_update()
        )
        latest_generation = await self._session.scalar(
            select(func.max(ProjectSetupRun.setup_generation)).where(
                ProjectSetupRun.guide_id == str(request.guide_id)
            )
        )
        if not self._lineage_matches(
            request,
            guide=guide,
            snapshot=snapshot,
            setup_run=setup_run,
            content=content,
            expected_sha256=admission.content_hash,
            expected_byte_count=admission.byte_count,
            latest_generation=latest_generation,
        ):
            raise GuideSourceBindingError("guide source binding is unavailable")
        assert content is not None

        candidate = await self._repository.get_verified_guide_content_candidate(
            admission.guide_source_item_id
        )
        if candidate is None or candidate.content_id != content.id:
            raise GuideSourceBindingError("guide source binding is unavailable")

        facts = guide_source_binding_authority_facts(
            project_id=request.project_id,
            guide_id=request.guide_id,
            source_snapshot_id=request.guide_source_snapshot_id,
            source_item_id=request.source_item_id,
            setup_run_id=request.project_setup_run_id,
            setup_generation=request.setup_generation,
            content_id=request.verified_content_id,
            replica_id=UUID(candidate.replica_id),
            sha256=candidate.sha256,
            byte_count=candidate.byte_count,
            logical_role=request.logical_role,
        )
        await self._authority.consume(
            prepared_authorization=request.prepared_authorization,
            facts=facts,
        )

        existing = await self._session.scalar(
            select(GuideSourceArtifactBinding)
            .where(
                GuideSourceArtifactBinding.source_item_id == str(request.source_item_id),
                GuideSourceArtifactBinding.setup_generation == request.setup_generation,
            )
            .with_for_update()
        )
        if existing is not None:
            if not self._binding_matches(existing, request, candidate.replica_id):
                raise GuideSourceBindingError("guide source binding conflicts")
            return GuideSourceBindingResult(
                binding_id=UUID(existing.id),
                content_id=UUID(existing.content_id),
                setup_generation=existing.setup_generation,
                replayed=True,
            )

        predecessor = await self._session.scalar(
            select(GuideSourceArtifactBinding)
            .where(
                GuideSourceArtifactBinding.source_item_id == str(request.source_item_id),
                GuideSourceArtifactBinding.setup_generation < request.setup_generation,
            )
            .order_by(GuideSourceArtifactBinding.setup_generation.desc())
            .limit(1)
            .with_for_update()
        )
        binding = GuideSourceArtifactBinding(
            id=str(uuid4()),
            project_id=str(request.project_id),
            guide_id=str(request.guide_id),
            source_snapshot_id=str(request.guide_source_snapshot_id),
            source_item_id=str(request.source_item_id),
            project_setup_run_id=str(request.project_setup_run_id),
            setup_generation=request.setup_generation,
            content_id=str(request.verified_content_id),
            verified_replica_id=candidate.replica_id,
            logical_role=request.logical_role,
            supersedes_binding_id=predecessor.id if predecessor is not None else None,
            created_by_service=ServiceIdentity.ARTIFACT_BINDING.value,
        )
        self._session.add(binding)
        await self._session.flush()
        return GuideSourceBindingResult(
            binding_id=UUID(binding.id),
            content_id=request.verified_content_id,
            setup_generation=request.setup_generation,
            replayed=False,
        )

    @staticmethod
    def _lineage_matches(
        request: GuideSourceBindingRequest,
        *,
        guide: ProjectGuide | None,
        snapshot: GuideSourceSnapshot | None,
        setup_run: ProjectSetupRun | None,
        content: ArtifactContent | None,
        expected_sha256: str,
        expected_byte_count: int,
        latest_generation: int | None,
    ) -> bool:
        project_id = str(request.project_id)
        guide_id = str(request.guide_id)
        snapshot_id = str(request.guide_source_snapshot_id)
        return bool(
            guide is not None
            and guide.project_id == project_id
            and guide.status == "draft"
            and snapshot is not None
            and snapshot.project_id == project_id
            and snapshot.guide_id == guide_id
            and snapshot.guide_version == guide.version
            and setup_run is not None
            and setup_run.project_id == project_id
            and setup_run.guide_id == guide_id
            and setup_run.guide_version == guide.version
            and setup_run.source_snapshot_id == snapshot_id
            and setup_run.source_snapshot_hash == snapshot.bundle_hash
            and setup_run.setup_generation == request.setup_generation
            and latest_generation == request.setup_generation
            and content is not None
            and content.sha256 == expected_sha256
            and content.byte_count == expected_byte_count
        )

    @staticmethod
    def _binding_matches(
        binding: GuideSourceArtifactBinding,
        request: GuideSourceBindingRequest,
        replica_id: str,
    ) -> bool:
        return (
            binding.project_id == str(request.project_id)
            and binding.guide_id == str(request.guide_id)
            and binding.source_snapshot_id == str(request.guide_source_snapshot_id)
            and binding.project_setup_run_id == str(request.project_setup_run_id)
            and binding.content_id == str(request.verified_content_id)
            and binding.verified_replica_id == replica_id
            and binding.logical_role == request.logical_role
        )
