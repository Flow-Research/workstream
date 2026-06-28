"""Service layer for project and project-guide lifecycle operations."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_any_role
from app.modules.checkers.runner import UnknownChecker, default_checker_registry
from app.modules.projects.models import (
    CheckerPolicy,
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSufficiencyReport,
    PaymentPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.schemas import (
    ActiveGuideResponse,
    CheckerPolicyInput,
    CheckerPolicyResponse,
    EffectiveProjectSubmissionArtifactPolicyResponse,
    GuideSourceSnapshotCreate,
    GuideSourceSnapshotItemResponse,
    GuideSourceSnapshotResponse,
    GuideSufficiencyAcknowledgement,
    GuideSufficiencyReportCreate,
    GuideSufficiencyReportResponse,
    PaymentPolicyInput,
    PaymentPolicyResponse,
    PreSubmitCheckerPolicySummaryResponse,
    ProjectCreate,
    ProjectGuideCreate,
    ProjectGuideResponse,
    ProjectGuideUpdate,
    ProjectResponse,
    RevisionPolicyInput,
    RevisionPolicyResponse,
    ReviewPolicyInput,
    ReviewPolicyResponse,
    SubmissionArtifactPolicyApprove,
    SubmissionArtifactPolicyCreate,
    SubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyUpdate,
)
from app.schemas.auth import ActorContext

PROJECT_SETUP_ROLES = {"admin", "project_manager"}
ALLOWED_REVIEW_DECISIONS = {"accept", "needs_revision", "reject"}
ALLOWED_REVISION_RESUBMISSION_STATES = {"needs_revision"}
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTENT_CID_PATTERN = re.compile(
    r"^(cid:[a-z0-9][a-z0-9._:-]{2,198}|ipfs://[A-Za-z0-9]{46,120}|bafy[a-z2-7]{20,120}|Qm[1-9A-HJ-NP-Za-km-z]{44})$"
)
SAFE_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
SECRET_REF_PATTERN = re.compile(
    r"(x-amz-|signature|credential|access[_-]?key|secret|token|password|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_ARTIFACT_NAME_PATTERN = re.compile(
    r"(^|[._/\-])("
    r"\.env[^/]*|"
    r"\.npmrc|\.pypirc|"
    r"id_(rsa|dsa|ecdsa|ed25519)(\.[^/]*)?|"
    r"private[_\-]?key[^/]*|"
    r"api[_\-]?key[^/]*|"
    r"access[_\-]?key[^/]*|"
    r"secret[^/]*|"
    r"credential[^/]*|"
    r"token[^/]*|"
    r"service[_\-]?account[^/]*"
    r")($|[._/\-])",
    re.IGNORECASE,
)
SECRET_ARTIFACT_TOKEN_SETS = [
    {"access", "key"},
    {"api", "key"},
    {"private", "key"},
    {"service", "account"},
    {"client", "secret"},
    {"aws", "access", "key"},
]
SECRET_ARTIFACT_SINGLE_TOKENS = {
    "credential",
    "credentials",
    "secret",
    "secrets",
    "password",
    "passwords",
    "token",
    "tokens",
}
ALLOWED_SOURCE_REF_SCHEMES = {"https", "http", "repo", "inline", "import", "s3", "r2"}
GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION = "guide_source_snapshot.v1"
EFFECTIVE_POLICY_SCHEMA_VERSION = "effective_project_submission_artifact_policy.v1"
MERGE_ALGORITHM_VERSION = "workstream_default_merge.v1"
PLATFORM_HASH_ALGORITHM = "sha256"
DEFAULT_ALLOWED_STORAGE_SCHEMES = ["local", "s3", "r2"]
DEFAULT_REQUIRED_PACKET_FIELDS = ["summary", "artifact_hash_manifest", "worker_attestation"]
DEFAULT_ATTESTATION_TERMS = [
    "original_work",
    "confidential_data_exclusion",
    "credentials_and_secret_exclusion",
    "human_accountability_for_agent_assisted_work",
]
DEFAULT_FORBIDDEN_ARTIFACT_PATTERNS = [
    ".env",
    ".env*",
    "*.env",
    "*.env.*",
    ".git",
    "credentials",
    "credential*",
    "secrets",
    "secret*",
    ".npmrc",
    ".pypirc",
    "api_key",
    "api-key",
    "api_key*",
    "api-key*",
    "access_key",
    "access-key",
    "access_key*",
    "access-key*",
    "private_key",
    "private-key",
    "private_key*",
    "private-key*",
    "id_rsa",
    "id_rsa*",
    "id_dsa",
    "id_dsa*",
    "id_ecdsa",
    "id_ecdsa*",
    "id_ed25519",
    "id_ed25519*",
    "service_account",
    "service-account",
    "service_account*",
    "service-account*",
    "token",
    "token*",
    "*.pem",
    "*.key",
    "node_modules",
]
OPAQUE_SOURCE_REF_SCHEMES = {"inline", "import", "repo"}
OPAQUE_SOURCE_REF_NAMESPACES = {
    "docs",
    "examples",
    "fixtures",
    "guides",
    "manual-imports",
    "project-docs",
    "rubrics",
    "source-material",
    "task-docs",
    "week1",
}
GUIDE_SOURCE_MATERIAL_FIELDS = {
    "content_markdown",
    "required_task_fields",
    "required_submission_fields",
    "task_instructions",
    "output_requirements",
    "acceptance_criteria",
    "rejection_criteria",
    "reviewer_rubric",
    "forbidden_actions",
    "required_skills",
    "difficulty_scale",
    "estimated_time_policy",
    "common_rejection_reasons",
    "evidence_policy",
    "unacceptable_work_policy",
}
WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY: dict[str, Any] = {
    "schema_version": "workstream_default_submission_artifact_policy.v1",
    "required_packet_fields": DEFAULT_REQUIRED_PACKET_FIELDS,
    "required_artifacts": [],
    "required_evidence": [],
    "forbidden_artifacts": [
        {"pattern": pattern, "source": "workstream_default", "severity": "blocking"}
        for pattern in DEFAULT_FORBIDDEN_ARTIFACT_PATTERNS
    ],
    "attestation_terms": DEFAULT_ATTESTATION_TERMS,
    "manifest_required": True,
    "artifact_hash_required": True,
    "artifact_hash_algorithm": PLATFORM_HASH_ALGORITHM,
    "allowed_storage_schemes": DEFAULT_ALLOWED_STORAGE_SCHEMES,
    "maximum_file_size_bytes": None,
    "maximum_package_size_bytes": None,
    "packaging": {},
}


class ProjectServiceError(Exception):
    """Base error for project service failures mapped to API responses."""

    status_code = 400


class ProjectNotFound(ProjectServiceError):
    """Raised when a project id does not match a stored project."""

    status_code = 404


class GuideNotFound(ProjectServiceError):
    """Raised when a project guide id is missing or outside the project."""

    status_code = 404


class GuideActivationBlocked(ProjectServiceError):
    """Raised when a guide is not ready to become active."""

    status_code = 422


class GuideEditBlocked(ProjectServiceError):
    """Raised when a non-draft guide is edited."""

    status_code = 409


class GuideActivationConflict(ProjectServiceError):
    """Raised when another transaction wins the guide activation race."""

    status_code = 409


class SourceSnapshotNotFound(ProjectServiceError):
    """Raised when a source snapshot cannot be found for a guide."""

    status_code = 404


class SourceSnapshotInvalid(ProjectServiceError):
    """Raised when guide-source snapshot input is unsafe or inconsistent."""

    status_code = 422


class SufficiencyReportNotFound(ProjectServiceError):
    """Raised when a guide sufficiency report cannot be found."""

    status_code = 404


class SubmissionArtifactPolicyNotFound(ProjectServiceError):
    """Raised when a submission artifact policy cannot be found."""

    status_code = 404


class PolicySetupBlocked(ProjectServiceError):
    """Raised when project submission artifact policy setup is invalid."""

    status_code = 422


class PolicySetupConflict(ProjectServiceError):
    """Raised when concurrent project policy setup wins a database race."""

    status_code = 409


class PolicyEditBlocked(ProjectServiceError):
    """Raised when immutable policy rows are edited."""

    status_code = 409


class ProjectService:
    """Coordinates project guide rules, persistence, and response shaping.

    The service owns business rules for project setup and guide activation. It
    keeps routers thin and repositories focused on database access.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Create a service instance bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current request.
        """
        self._session = session
        self._repo = ProjectRepository(session)

    async def create_project(self, actor: ActorContext, payload: ProjectCreate) -> ProjectResponse:
        """Create a draft project record after project setup authorization.

        Args:
            actor: Verified Flow actor context for the current request.
            payload: Validated project creation fields.

        Returns:
            Created project response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        project = Project(
            id=str(uuid4()),
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            status="draft",
            base_amount=payload.base_amount,
            currency=payload.currency,
        )
        project = await self._repo.add_project(project)
        await self._session.commit()
        await self._session.refresh(project)
        return ProjectResponse.model_validate(project)

    async def get_project(self, actor: ActorContext, project_id: str) -> ProjectResponse:
        """Return one project visible to project setup operators.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project identifier to load.

        Returns:
            Matching project response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            ProjectNotFound: If the project id is unknown.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        project = await self._repo.get_project(project_id)
        if project is None:
            raise ProjectNotFound("project not found")
        return ProjectResponse.model_validate(project)

    async def create_guide(
        self,
        actor: ActorContext,
        project_id: str,
        payload: ProjectGuideCreate,
    ) -> ProjectGuideResponse:
        """Create a draft guide and optional policy records for one project.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            payload: Guide content plus optional checker, review, revision, and payment policies.

        Returns:
            Created draft guide response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            ProjectNotFound: If the parent project is unknown.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        project = await self._repo.get_project(project_id)
        if project is None:
            raise ProjectNotFound("project not found")
        guide = ProjectGuide(
            id=str(uuid4()),
            project_id=project_id,
            version=payload.version,
            status="draft",
            content_markdown=payload.content_markdown,
            required_task_fields=payload.required_task_fields,
            required_submission_fields=payload.required_submission_fields,
            task_instructions=payload.task_instructions,
            output_requirements=payload.output_requirements,
            acceptance_criteria=payload.acceptance_criteria,
            rejection_criteria=payload.rejection_criteria,
            reviewer_rubric=payload.reviewer_rubric,
            forbidden_actions=payload.forbidden_actions,
            required_skills=payload.required_skills,
            difficulty_scale=payload.difficulty_scale,
            estimated_time_policy=payload.estimated_time_policy,
            common_rejection_reasons=payload.common_rejection_reasons,
            evidence_policy=payload.evidence_policy,
            unacceptable_work_policy=payload.unacceptable_work_policy,
            change_summary=payload.change_summary,
            created_by=actor.actor_id,
        )
        guide = await self._repo.add_guide(guide)
        await self._upsert_optional_policies(project_id, payload.version, payload)
        await self._session.commit()
        await self._session.refresh(guide)
        return ProjectGuideResponse.model_validate(guide)

    async def update_draft_guide(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        payload: ProjectGuideUpdate,
    ) -> ProjectGuideResponse:
        """Apply edits to a draft guide and its optional policy records.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Draft guide to update.
            payload: Partial guide and policy fields to apply.

        Returns:
            Updated draft guide response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            GuideNotFound: If the guide is missing or outside the project.
            GuideEditBlocked: If the guide is no longer a draft.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can be edited")

        changes = payload.model_dump(exclude_unset=True)
        if GUIDE_SOURCE_MATERIAL_FIELDS.intersection(changes):
            snapshots = await self._repo.list_guide_source_snapshots(
                project_id,
                guide.id,
                guide.version,
            )
            if snapshots:
                raise GuideEditBlocked(
                    "guide source material cannot change after a source snapshot exists"
                )
        for field, value in changes.items():
            if field in {"checker_policy", "review_policy", "revision_policy", "payment_policy"}:
                continue
            setattr(guide, field, value)
        await self._upsert_optional_policies(project_id, guide.version, payload)
        await self._session.commit()
        await self._session.refresh(guide)
        return ProjectGuideResponse.model_validate(guide)

    async def create_guide_source_snapshot(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        payload: GuideSourceSnapshotCreate,
    ) -> GuideSourceSnapshotResponse:
        """Create an immutable source-material snapshot for a draft guide.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Draft guide receiving the source snapshot.
            payload: Source items to sanitize, canonicalize, and hash.

        Returns:
            Created guide-source snapshot response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            GuideNotFound: If the guide is missing or outside the project.
            GuideEditBlocked: If the guide is not a draft.
            SourceSnapshotInvalid: If source refs or hashes are unsafe.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can receive source snapshots")

        manifest, sanitized_items = self._build_source_snapshot_manifest(payload, guide)
        bundle_hash = self._hash_canonical_json(manifest)
        snapshot = GuideSourceSnapshot(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            manifest_schema_version=GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            manifest_json=manifest,
            bundle_hash=bundle_hash,
            captured_by=actor.actor_id,
        )
        item_models = [
            GuideSourceSnapshotItem(
                id=str(uuid4()),
                source_snapshot_id=snapshot.id,
                item_order=index,
                source_kind=item["source_kind"],
                durable_ref=item["durable_ref"],
                ingestion_adapter=item["ingestion_adapter"],
                content_hash=item["content_hash"],
                content_cid=item.get("content_cid"),
                media_type=item.get("media_type"),
            )
            for index, item in enumerate(sanitized_items)
        ]
        try:
            snapshot = await self._repo.add_guide_source_snapshot(snapshot, item_models)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PolicySetupConflict(
                "guide source snapshot conflicted with concurrent setup; retry"
            ) from exc
        return await self._source_snapshot_response(snapshot)

    async def create_guide_sufficiency_report(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        payload: GuideSufficiencyReportCreate,
    ) -> GuideSufficiencyReportResponse:
        """Record Workstream's sufficiency assessment for a guide snapshot.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Guide whose source snapshot was assessed.
            payload: Sufficiency status and findings.

        Returns:
            Persisted sufficiency report response.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        snapshot = await self._get_snapshot_for_guide(project_id, guide, payload.source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self._validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        self._validate_sufficiency_report_payload(payload)
        report = GuideSufficiencyReport(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            status=payload.status,
            findings=[finding.model_dump(mode="json") for finding in payload.findings],
            summary=payload.summary,
            agent_name=payload.agent_name,
            agent_version=payload.agent_version,
            created_by=actor.actor_id,
        )
        try:
            report = await self._repo.add_guide_sufficiency_report(report)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PolicySetupConflict(
                "guide sufficiency report conflicted with concurrent setup; retry"
            ) from exc
        await self._session.refresh(report)
        return GuideSufficiencyReportResponse.model_validate(report)

    async def acknowledge_guide_sufficiency_warnings(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        report_id: str,
        payload: GuideSufficiencyAcknowledgement,
    ) -> GuideSufficiencyReportResponse:
        """Acknowledge non-blocking guide sufficiency warnings.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Guide whose report is being acknowledged.
            report_id: Sufficiency report id.
            payload: Optional acknowledgement note.

        Returns:
            Updated sufficiency report response.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can acknowledge sufficiency warnings")
        report = await self._repo.get_guide_sufficiency_report(report_id)
        if report is None or report.project_id != project_id or report.guide_id != guide.id:
            raise SufficiencyReportNotFound("guide sufficiency report not found")
        if report.status != "passed_with_warnings":
            raise PolicySetupBlocked("only sufficiency warnings can be acknowledged")
        report.warnings_acknowledged_by_role = self._approver_role(actor)
        report.warnings_acknowledged_by_actor = actor.actor_id
        report.warnings_acknowledged_at = datetime.now(UTC)
        report.acknowledgement_note = payload.acknowledgement_note
        await self._session.commit()
        await self._session.refresh(report)
        return GuideSufficiencyReportResponse.model_validate(report)

    async def create_submission_artifact_policy(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        payload: SubmissionArtifactPolicyCreate,
    ) -> SubmissionArtifactPolicyResponse:
        """Create a draft Workstream-derived submission artifact policy.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Draft guide receiving the policy.
            payload: Draft policy content and derivation metadata.

        Returns:
            Created draft policy response.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can receive submission artifact policies")
        snapshot = await self._get_snapshot_for_guide(project_id, guide, payload.source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self._validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        policy_body = self._canonical_policy_body(payload.policy_body.model_dump(mode="json"))
        self._merge_effective_submission_artifact_policy(policy_body)
        source_material_refs = await self._source_material_refs(snapshot.id)
        policy = SubmissionArtifactPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            policy_version=payload.policy_version,
            lifecycle_status="draft",
            policy_body=policy_body,
            policy_hash=self._hash_canonical_json(policy_body),
            derivation_source=payload.derivation_source,
            source_material_refs=source_material_refs,
            derivation_agent_name=payload.derivation_agent_name,
            derivation_agent_version=payload.derivation_agent_version,
            created_by=actor.actor_id,
            change_summary=payload.change_summary,
        )
        try:
            policy = await self._repo.add_submission_artifact_policy(policy)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PolicySetupConflict(
                "submission artifact policy conflicted with concurrent setup; retry"
            ) from exc
        await self._session.refresh(policy)
        return SubmissionArtifactPolicyResponse.model_validate(policy)

    async def update_submission_artifact_policy(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        policy_id: str,
        payload: SubmissionArtifactPolicyUpdate,
    ) -> SubmissionArtifactPolicyResponse:
        """Update mutable fields on a draft submission artifact policy.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the policy.
            guide_id: Guide that owns the policy.
            policy_id: Draft policy id to update.
            payload: Partial policy updates.

        Returns:
            Updated draft policy response.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can edit submission artifact policies")
        policy = await self._repo.lock_submission_artifact_policy(policy_id)
        if policy is None or policy.project_id != project_id or policy.guide_id != guide.id:
            raise SubmissionArtifactPolicyNotFound("submission artifact policy not found")
        if policy.lifecycle_status != "draft":
            raise PolicyEditBlocked("approved and superseded policies are immutable")
        if payload.policy_body is not None:
            policy_body = self._canonical_policy_body(payload.policy_body.model_dump(mode="json"))
            self._merge_effective_submission_artifact_policy(policy_body)
            policy.policy_body = policy_body
            policy.policy_hash = self._hash_canonical_json(policy_body)
        if payload.derivation_source is not None:
            policy.derivation_source = payload.derivation_source
        if payload.derivation_agent_name is not None:
            policy.derivation_agent_name = payload.derivation_agent_name
        if payload.derivation_agent_version is not None:
            policy.derivation_agent_version = payload.derivation_agent_version
        if payload.change_summary is not None:
            policy.change_summary = payload.change_summary
        await self._session.commit()
        await self._session.refresh(policy)
        return SubmissionArtifactPolicyResponse.model_validate(policy)

    async def approve_submission_artifact_policy(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        policy_id: str,
        payload: SubmissionArtifactPolicyApprove,
    ) -> EffectiveProjectSubmissionArtifactPolicyResponse:
        """Approve a draft policy and persist its effective project submission artifact policy.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the policy.
            guide_id: Guide that owns the policy.
            policy_id: Draft policy to approve.
            payload: Approval request body; provenance is server-derived.

        Returns:
            Effective project submission artifact policy response.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can approve submission artifact policies")
        policy = await self._repo.lock_submission_artifact_policy(policy_id)
        if policy is None or policy.project_id != project_id or policy.guide_id != guide.id:
            raise SubmissionArtifactPolicyNotFound("submission artifact policy not found")
        if policy.lifecycle_status != "draft":
            raise PolicyEditBlocked("only draft policies can be approved")
        snapshot = await self._get_snapshot_for_guide(project_id, guide, policy.source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self._validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        if policy.source_snapshot_hash != snapshot.bundle_hash:
            raise PolicySetupBlocked("submission artifact policy is bound to a stale source snapshot")
        sufficiency_report = await self._repo.get_sufficiency_report_for_snapshot(snapshot.id)
        self._validate_sufficiency_report_allows_policy_approval(
            sufficiency_report,
            snapshot,
        )

        effective_policy = self._merge_effective_submission_artifact_policy(policy.policy_body)
        effective_policy_hash = self._hash_canonical_json(effective_policy)
        now = datetime.now(UTC)
        try:
            previous_policy = await self._repo.get_current_approved_submission_artifact_policy(
                project_id,
                guide.version,
            )
        except ProjectRepositoryIntegrityError as exc:
            raise PolicySetupConflict(
                "submission artifact policy chain is ambiguous; create fresh policy records"
            ) from exc
        policy.supersedes_policy_id = previous_policy.id if previous_policy is not None else None

        previous_effective = None
        if previous_policy is not None:
            try:
                previous_effective = await self._repo.get_effective_submission_artifact_policy(
                    project_id,
                    guide.version,
                    previous_policy.source_snapshot_id,
                )
            except ProjectRepositoryIntegrityError as exc:
                raise PolicySetupConflict(
                    "effective project submission artifact policy chain is ambiguous; create fresh policy records"
                ) from exc
            if previous_effective is None:
                raise PolicySetupConflict(
                    "effective project submission artifact policy chain is incomplete; create fresh policy records"
                )
            if (
                previous_effective.submission_artifact_policy_id != previous_policy.id
                or previous_effective.submission_artifact_policy_hash != previous_policy.policy_hash
            ):
                raise PolicySetupConflict(
                    "effective project submission artifact policy chain is inconsistent; create fresh policy records"
                )
        try:
            previous_pre_submit_checker_policy = (
                await self._repo.get_current_pre_submit_checker_policy(
                    project_id,
                    guide.version,
                )
            )
        except ProjectRepositoryIntegrityError as exc:
            raise PolicySetupConflict(
                "pre-submit checker policy chain is ambiguous; create fresh policy records"
            ) from exc
        if previous_policy is not None:
            if previous_pre_submit_checker_policy is None:
                raise PolicySetupConflict(
                    "pre-submit checker policy chain is incomplete; create fresh policy records"
                )
            if (
                previous_pre_submit_checker_policy.effective_policy_id != previous_effective.id
                or previous_pre_submit_checker_policy.effective_policy_hash
                != previous_effective.effective_policy_hash
            ):
                raise PolicySetupConflict(
                    "pre-submit checker policy chain is inconsistent; create fresh policy records"
                )
        elif previous_pre_submit_checker_policy is not None:
            raise PolicySetupConflict(
                "pre-submit checker policy chain is inconsistent; create fresh policy records"
            )

        policy.lifecycle_status = "approved"
        policy.approved_by_role = self._approver_role(actor)
        policy.approved_by_actor = actor.actor_id
        policy.approved_at = now
        if payload.approval_note:
            policy.change_summary = payload.approval_note
        if previous_policy is not None:
            previous_policy.lifecycle_status = "superseded"
            previous_policy.superseded_at = now
            previous_effective.lifecycle_status = "superseded"
            previous_effective.superseded_at = now
            previous_pre_submit_checker_policy.lifecycle_status = "superseded"
            previous_pre_submit_checker_policy.superseded_at = now

        effective = EffectiveProjectSubmissionArtifactPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            submission_artifact_policy_id=policy.id,
            submission_artifact_policy_hash=policy.policy_hash,
            lifecycle_status="approved",
            merge_algorithm_version=MERGE_ALGORITHM_VERSION,
            effective_policy=effective_policy,
            effective_policy_hash=effective_policy_hash,
            created_by=actor.actor_id,
            supersedes_effective_policy_id=(
                previous_effective.id if previous_effective is not None else None
            ),
        )
        try:
            effective = await self._repo.add_effective_submission_artifact_policy(effective)
            pre_submit_checker_policy = PreSubmitCheckerPolicy(
                id=str(uuid4()),
                project_id=project_id,
                guide_id=guide.id,
                guide_version=guide.version,
                source_snapshot_id=snapshot.id,
                source_snapshot_hash=snapshot.bundle_hash,
                effective_policy_id=effective.id,
                effective_policy_hash=effective.effective_policy_hash,
                lifecycle_status="pending_compilation",
                compiler_version=None,
                compiled_bundle=None,
                compiled_bundle_hash=None,
                checker_names=[],
                checker_configs={},
                created_by=actor.actor_id,
                supersedes_pre_submit_checker_policy_id=(
                    previous_pre_submit_checker_policy.id
                    if previous_pre_submit_checker_policy is not None
                    else None
                ),
            )
            pre_submit_checker_policy = await self._repo.add_pre_submit_checker_policy(
                pre_submit_checker_policy
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PolicySetupConflict(
                "submission artifact policy approval conflicted with concurrent setup; retry"
            ) from exc
        await self._session.refresh(policy)
        await self._session.refresh(effective)
        await self._session.refresh(pre_submit_checker_policy)
        return EffectiveProjectSubmissionArtifactPolicyResponse.model_validate(effective)

    async def activate_guide(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
    ) -> ActiveGuideResponse:
        """Promote a complete draft guide and supersede any prior active guide.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Draft guide to activate.

        Returns:
            Active guide response with checker, review, revision, and payment policies.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            GuideNotFound: If the guide is missing or outside the project.
            GuideActivationBlocked: If the guide or its policy context is incomplete.
            GuideActivationConflict: If another activation wins the database race.
            ProjectNotFound: If the parent project disappears during activation.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideActivationBlocked("only draft guides can be activated")

        checker_policy = await self._repo.get_checker_policy(project_id, guide.version)
        review_policy = await self._repo.get_review_policy(project_id, guide.version)
        revision_policy = await self._repo.get_revision_policy(project_id, guide.version)
        payment_policy = await self._repo.get_payment_policy(project_id, guide.version)
        try:
            submission_artifact_policy = (
                await self._repo.get_current_approved_submission_artifact_policy(
                    project_id,
                    guide.version,
                )
            )
        except ProjectRepositoryIntegrityError as exc:
            raise GuideActivationBlocked("guide policy context is ambiguous") from exc
        if submission_artifact_policy is None:
            raise GuideActivationBlocked("approved submission artifact policy is required")
        source_snapshot = await self._get_snapshot_for_guide(
            project_id,
            guide,
            submission_artifact_policy.source_snapshot_id,
        )
        await self._ensure_snapshot_is_latest(project_id, guide, source_snapshot)
        await self._validate_source_snapshot_integrity(source_snapshot, GuideActivationBlocked)
        sufficiency_report = await self._repo.get_sufficiency_report_for_snapshot(
            source_snapshot.id
        )
        try:
            effective_policy = await self._repo.get_effective_submission_artifact_policy(
                project_id,
                guide.version,
                source_snapshot.id,
            )
            pre_submit_checker_policy = (
                await self._repo.get_pre_submit_checker_policy_for_effective_policy(
                    effective_policy.id if effective_policy is not None else ""
                )
            )
        except ProjectRepositoryIntegrityError as exc:
            raise GuideActivationBlocked("guide policy context is ambiguous") from exc
        self._validate_activation_ready(
            guide,
            source_snapshot,
            sufficiency_report,
            submission_artifact_policy,
            effective_policy,
            pre_submit_checker_policy,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )
        project = await self._repo.get_project(project_id)
        if project is None:
            raise ProjectNotFound("project not found")

        try:
            now = datetime.now(UTC)
            for active_guide in await self._repo.list_active_guides(project_id):
                active_guide.status = "superseded"
                active_guide.superseded_at = now
            await self._session.flush()

            guide.status = "active"
            guide.approved_by = actor.actor_id
            guide.effective_at = now

            project.status = "active"
            project.base_amount = payment_policy.base_amount
            project.currency = payment_policy.currency

            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise GuideActivationConflict(
                "guide activation conflicted with a concurrent update; retry"
            ) from exc
        await self._session.refresh(guide)
        await self._session.refresh(source_snapshot)
        await self._session.refresh(sufficiency_report)
        await self._session.refresh(submission_artifact_policy)
        await self._session.refresh(effective_policy)
        await self._session.refresh(pre_submit_checker_policy)
        await self._session.refresh(checker_policy)
        await self._session.refresh(review_policy)
        await self._session.refresh(revision_policy)
        await self._session.refresh(payment_policy)
        return await self._active_response(
            guide,
            source_snapshot,
            sufficiency_report,
            submission_artifact_policy,
            effective_policy,
            pre_submit_checker_policy,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )

    async def get_active_guide(self, actor: ActorContext, project_id: str) -> ActiveGuideResponse:
        """Return the active guide with checker, review, revision, and payment context.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project whose active guide should be loaded.

        Returns:
            Active guide response with all required policy records.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            GuideNotFound: If no active guide exists for the project.
            GuideActivationBlocked: If the active guide policy context is incomplete.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._repo.get_active_guide(project_id)
        if guide is None:
            raise GuideNotFound("active guide not found")
        checker_policy = await self._repo.get_checker_policy(project_id, guide.version)
        review_policy = await self._repo.get_review_policy(project_id, guide.version)
        revision_policy = await self._repo.get_revision_policy(project_id, guide.version)
        payment_policy = await self._repo.get_payment_policy(project_id, guide.version)
        try:
            submission_artifact_policy = (
                await self._repo.get_current_approved_submission_artifact_policy(
                    project_id,
                    guide.version,
                )
            )
        except ProjectRepositoryIntegrityError as exc:
            raise GuideActivationBlocked("active guide policy context is ambiguous") from exc
        if submission_artifact_policy is None:
            raise GuideActivationBlocked("active guide policy context is incomplete")
        source_snapshot = await self._get_snapshot_for_guide(
            project_id,
            guide,
            submission_artifact_policy.source_snapshot_id,
        )
        await self._ensure_snapshot_is_latest(project_id, guide, source_snapshot)
        await self._validate_source_snapshot_integrity(source_snapshot, GuideActivationBlocked)
        sufficiency_report = await self._repo.get_sufficiency_report_for_snapshot(
            source_snapshot.id
        )
        try:
            effective_policy = await self._repo.get_effective_submission_artifact_policy(
                project_id,
                guide.version,
                source_snapshot.id,
            )
            pre_submit_checker_policy = (
                await self._repo.get_pre_submit_checker_policy_for_effective_policy(
                    effective_policy.id if effective_policy is not None else ""
                )
            )
        except ProjectRepositoryIntegrityError as exc:
            raise GuideActivationBlocked("active guide policy context is ambiguous") from exc
        if (
            checker_policy is None
            or review_policy is None
            or revision_policy is None
            or payment_policy is None
            or sufficiency_report is None
            or effective_policy is None
            or pre_submit_checker_policy is None
        ):
            raise GuideActivationBlocked("active guide policy context is incomplete")
        self._validate_activation_ready(
            guide,
            source_snapshot,
            sufficiency_report,
            submission_artifact_policy,
            effective_policy,
            pre_submit_checker_policy,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )
        return await self._active_response(
            guide,
            source_snapshot,
            sufficiency_report,
            submission_artifact_policy,
            effective_policy,
            pre_submit_checker_policy,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )

    async def _get_project_guide(self, project_id: str, guide_id: str) -> ProjectGuide:
        """Load a guide and ensure it belongs to the requested project.

        Args:
            project_id: Project id expected to own the guide.
            guide_id: Guide id to load.

        Returns:
            Matching guide model.

        Raises:
            GuideNotFound: If the guide is missing or belongs to another project.
        """
        guide = await self._repo.get_guide(guide_id)
        if guide is None or guide.project_id != project_id:
            raise GuideNotFound("guide not found")
        return guide

    async def _lock_project_guide_for_setup(
        self,
        project_id: str,
        guide_id: str,
    ) -> ProjectGuide:
        """Load and lock a guide row before mutating setup records."""
        guide = await self._repo.lock_project_guide(guide_id)
        if guide is None or guide.project_id != project_id:
            raise GuideNotFound("guide not found")
        return guide

    async def _upsert_optional_policies(
        self,
        project_id: str,
        guide_version: str,
        payload: ProjectGuideCreate | ProjectGuideUpdate,
    ) -> None:
        """Create or replace policy records supplied with guide payloads.

        Args:
            project_id: Project that owns the policies.
            guide_version: Guide version the policies apply to.
            payload: Guide create or update payload carrying optional policies.
        """
        if payload.checker_policy is not None:
            await self._repo.upsert_checker_policy(
                self._checker_policy_model(project_id, guide_version, payload.checker_policy)
            )
        if payload.review_policy is not None:
            await self._repo.upsert_review_policy(
                self._review_policy_model(project_id, guide_version, payload.review_policy)
            )
        if payload.revision_policy is not None:
            await self._repo.upsert_revision_policy(
                self._revision_policy_model(project_id, guide_version, payload.revision_policy)
            )
        if payload.payment_policy is not None:
            await self._repo.upsert_payment_policy(
                self._payment_policy_model(project_id, guide_version, payload.payment_policy)
            )

    async def _get_snapshot_for_guide(
        self,
        project_id: str,
        guide: ProjectGuide,
        snapshot_id: str,
    ) -> GuideSourceSnapshot:
        """Load a guide-source snapshot and verify guide ownership.

        Args:
            project_id: Project id expected to own the snapshot.
            guide: Guide model expected to own the snapshot.
            snapshot_id: Snapshot id to load.

        Returns:
            Matching guide-source snapshot.

        Raises:
            SourceSnapshotNotFound: If the snapshot does not belong to the guide.
        """
        snapshot = await self._repo.get_guide_source_snapshot(snapshot_id)
        if (
            snapshot is None
            or snapshot.project_id != project_id
            or snapshot.guide_id != guide.id
            or snapshot.guide_version != guide.version
        ):
            raise SourceSnapshotNotFound("guide source snapshot not found")
        return snapshot

    async def _ensure_snapshot_is_latest(
        self,
        project_id: str,
        guide: ProjectGuide,
        snapshot: GuideSourceSnapshot,
    ) -> None:
        """Require policy setup to use the latest captured guide-source snapshot.

        Args:
            project_id: Project that owns the guide.
            guide: Guide whose source material is being evaluated.
            snapshot: Snapshot used by the downstream setup record.

        Raises:
            PolicySetupBlocked: If another snapshot was captured later.
        """
        try:
            latest_snapshot = await self._repo.get_latest_guide_source_snapshot(
                project_id,
                guide.id,
                guide.version,
            )
        except ProjectRepositoryIntegrityError as exc:
            raise PolicySetupBlocked(
                "latest guide source snapshot is ambiguous; create a fresh source snapshot"
            ) from exc
        if latest_snapshot is None or latest_snapshot.id != snapshot.id:
            raise PolicySetupBlocked(
                "guide source snapshot is stale; create fresh sufficiency and policy records"
            )

    async def _source_snapshot_response(
        self,
        snapshot: GuideSourceSnapshot,
    ) -> GuideSourceSnapshotResponse:
        """Build a snapshot response with ordered source items."""
        items = await self._repo.list_guide_source_snapshot_items(snapshot.id)
        response = GuideSourceSnapshotResponse.model_validate(snapshot)
        response.items = [
            GuideSourceSnapshotItemResponse.model_validate(item) for item in items
        ]
        return response

    async def _source_material_refs(self, snapshot_id: str) -> list[str]:
        """Return sanitized source refs included in a snapshot."""
        items = await self._repo.list_guide_source_snapshot_items(snapshot_id)
        return [item.durable_ref for item in items]

    async def _validate_source_snapshot_integrity(
        self,
        snapshot: GuideSourceSnapshot,
        exception_type: type[ProjectServiceError],
    ) -> None:
        """Recompute and verify an immutable guide-source snapshot bundle."""

        def fail() -> None:
            """Raise the caller-specific snapshot integrity error."""
            raise exception_type("guide source snapshot integrity check failed")

        manifest = snapshot.manifest_json
        if not isinstance(manifest, dict):
            fail()
        if snapshot.manifest_schema_version != GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION:
            fail()
        if manifest.get("schema_version") != GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION:
            fail()
        manifest_items = manifest.get("items")
        if not isinstance(manifest_items, list) or not manifest_items:
            fail()
        if self._hash_canonical_json(manifest) != snapshot.bundle_hash:
            fail()

        persisted_items = await self._repo.list_guide_source_snapshot_items(snapshot.id)
        if len(persisted_items) != len(manifest_items):
            fail()

        row_items: list[dict[str, Any]] = []
        seen_refs: set[tuple[str, str]] = set()
        required_fields = {
            "source_kind",
            "durable_ref",
            "ingestion_adapter",
            "content_hash",
            "content_cid",
            "media_type",
        }
        for index, item in enumerate(persisted_items):
            if item.item_order != index:
                fail()
            row_item = {
                "source_kind": item.source_kind,
                "durable_ref": item.durable_ref,
                "ingestion_adapter": item.ingestion_adapter,
                "content_hash": item.content_hash,
                "content_cid": item.content_cid,
                "media_type": item.media_type,
            }
            ref_key = (item.source_kind, item.durable_ref)
            if ref_key in seen_refs:
                fail()
            seen_refs.add(ref_key)
            row_items.append(row_item)

        for manifest_item in manifest_items:
            if not isinstance(manifest_item, dict):
                fail()
            if set(manifest_item) != required_fields:
                fail()
            if not isinstance(manifest_item["source_kind"], str):
                fail()
            if not isinstance(manifest_item["durable_ref"], str):
                fail()
            if not isinstance(manifest_item["ingestion_adapter"], str):
                fail()
            if not isinstance(manifest_item["content_hash"], str):
                fail()
            if not HASH_PATTERN.fullmatch(manifest_item["content_hash"]):
                fail()
            if manifest_item["content_cid"] is not None and not isinstance(
                manifest_item["content_cid"],
                str,
            ):
                fail()
            if manifest_item["media_type"] is not None and not isinstance(
                manifest_item["media_type"],
                str,
            ):
                fail()
            try:
                if (
                    self._safe_source_token(manifest_item["source_kind"], "source kind")
                    != manifest_item["source_kind"]
                ):
                    fail()
                if (
                    self._safe_source_token(
                        manifest_item["ingestion_adapter"],
                        "ingestion adapter",
                    )
                    != manifest_item["ingestion_adapter"]
                ):
                    fail()
                if (
                    self._sanitize_durable_source_ref(manifest_item["durable_ref"])
                    != manifest_item["durable_ref"]
                ):
                    fail()
                self._require_sha256_hash(
                    manifest_item["content_hash"],
                    "source item content hash",
                )
                if (
                    self._sanitize_content_cid(manifest_item["content_cid"])
                    != manifest_item["content_cid"]
                ):
                    fail()
            except ProjectServiceError:
                fail()

        if manifest_items != row_items:
            fail()

    def _build_source_snapshot_manifest(
        self,
        payload: GuideSourceSnapshotCreate,
        guide: ProjectGuide,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Sanitize source items and build a canonical manifest.

        Args:
            payload: Raw source snapshot request.
            guide: Current draft guide whose source material is included.

        Returns:
            Canonical manifest and deterministic source item dictionaries.

        Raises:
            SourceSnapshotInvalid: If any source item is unsafe or duplicated.
        """
        guide_item = self._guide_material_snapshot_item(guide)
        normalized_items = [guide_item]
        seen_refs: set[tuple[str, str]] = {
            (guide_item["source_kind"], guide_item["durable_ref"])
        }
        for item in payload.items:
            source_kind = self._safe_source_token(item.source_kind, "source kind")
            ingestion_adapter = self._safe_source_token(
                item.ingestion_adapter,
                "ingestion adapter",
            )
            durable_ref = self._sanitize_durable_source_ref(item.durable_ref)
            self._require_sha256_hash(item.content_hash, "source item content hash")
            content_cid = self._sanitize_content_cid(item.content_cid)
            duplicate_key = (source_kind, durable_ref)
            if duplicate_key in seen_refs:
                raise SourceSnapshotInvalid("duplicate source item durable reference")
            seen_refs.add(duplicate_key)
            normalized_items.append(
                {
                    "source_kind": source_kind,
                    "durable_ref": durable_ref,
                    "ingestion_adapter": ingestion_adapter,
                    "content_hash": item.content_hash,
                    "content_cid": content_cid,
                    "media_type": item.media_type,
                }
            )

        sorted_items = sorted(
            normalized_items,
            key=lambda item: (
                item["source_kind"],
                item["durable_ref"],
                item["content_hash"],
            ),
        )
        manifest = {
            "schema_version": GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            "items": sorted_items,
        }
        return manifest, sorted_items

    def _guide_material_snapshot_item(self, guide: ProjectGuide) -> dict[str, Any]:
        """Build the server-owned source item for the current guide body."""
        guide_material = {
            field: getattr(guide, field)
            for field in sorted(GUIDE_SOURCE_MATERIAL_FIELDS)
        }
        return {
            "source_kind": "project_guide",
            "durable_ref": f"inline:/guides/{guide.id}/{guide.version}",
            "ingestion_adapter": "workstream_project_guide",
            "content_hash": self._hash_canonical_json(guide_material),
            "content_cid": None,
            "media_type": "application/json",
        }

    def _safe_source_token(self, value: str, label: str) -> str:
        """Validate a source token field used in durable policy records."""
        normalized = value.strip().lower()
        if not SAFE_TOKEN_PATTERN.fullmatch(normalized):
            raise SourceSnapshotInvalid(f"invalid {label}")
        return normalized

    def _sanitize_durable_source_ref(self, durable_ref: str) -> str:
        """Reject unsafe durable source refs and return a canonical ref.

        Durable source refs are audit identity, not temporary fetch locators.
        Query strings, fragments, credentials, signed URL material, local paths,
        and token-bearing values are rejected before persistence.
        """
        raw_ref = durable_ref.strip()
        decoded_ref = self._decode_percent_encoded_ref(raw_ref)
        if "\\" in raw_ref or "\\" in decoded_ref:
            raise SourceSnapshotInvalid("durable source refs cannot contain local path separators")
        parsed = urlparse(raw_ref)
        decoded_parsed = urlparse(decoded_ref)
        if not parsed.scheme:
            raise SourceSnapshotInvalid("durable source refs must use an approved scheme")
        scheme = parsed.scheme.lower()
        if scheme not in ALLOWED_SOURCE_REF_SCHEMES:
            raise SourceSnapshotInvalid("durable source ref scheme is not approved")
        if decoded_parsed.scheme and decoded_parsed.scheme.lower() != scheme:
            raise SourceSnapshotInvalid("durable source refs cannot contain encoded locators")
        if decoded_parsed.netloc and decoded_parsed.netloc != parsed.netloc:
            raise SourceSnapshotInvalid("durable source refs cannot contain encoded locators")
        if scheme in OPAQUE_SOURCE_REF_SCHEMES and (parsed.netloc or parsed.path.startswith("//")):
            raise SourceSnapshotInvalid("durable source refs cannot contain network share authority")
        if scheme in OPAQUE_SOURCE_REF_SCHEMES and (
            decoded_parsed.netloc or decoded_parsed.path.startswith("//")
        ):
            raise SourceSnapshotInvalid("durable source refs cannot contain network share authority")
        if parsed.username or parsed.password or "@" in parsed.netloc:
            raise SourceSnapshotInvalid("durable source refs cannot contain credentials")
        if ";" in raw_ref or ";" in decoded_ref:
            raise SourceSnapshotInvalid(
                "durable source refs cannot contain query, fragment, or path parameters"
            )
        if (
            parsed.query
            or parsed.fragment
            or parsed.params
            or decoded_parsed.query
            or decoded_parsed.fragment
            or decoded_parsed.params
        ):
            raise SourceSnapshotInvalid(
                "durable source refs cannot contain query, fragment, or path parameters"
            )
        if SECRET_REF_PATTERN.search(raw_ref) or SECRET_REF_PATTERN.search(decoded_ref):
            raise SourceSnapshotInvalid("durable source refs cannot contain credential material")
        decoded_path = self._decode_percent_encoded_ref(parsed.path or "")
        if "?" in decoded_path or "#" in decoded_path or ";" in decoded_path:
            raise SourceSnapshotInvalid("durable source refs cannot contain encoded locators")
        path_segments = [segment for segment in decoded_path.split("/") if segment]
        if any(segment in {".", ".."} for segment in path_segments):
            raise SourceSnapshotInvalid("durable source refs cannot contain path traversal")
        if decoded_path.startswith(("~", "/tmp", "/home", "/Users", "/var", "/etc")) or re.match(
            r"^/?[A-Za-z]:/",
            decoded_path,
        ):
            raise SourceSnapshotInvalid("durable source refs cannot be local filesystem paths")
        if self._matches_forbidden_artifact(decoded_path, DEFAULT_FORBIDDEN_ARTIFACT_PATTERNS):
            raise SourceSnapshotInvalid("durable source refs cannot contain credential material")
        if scheme in OPAQUE_SOURCE_REF_SCHEMES:
            self._validate_opaque_source_ref_path(decoded_path)
        if scheme in {"http", "https"} and not parsed.netloc:
            raise SourceSnapshotInvalid("http source refs require a host")
        netloc = parsed.netloc.lower()
        path = parsed.path or ""
        return f"{scheme}://{netloc}{path}" if netloc else f"{scheme}:{path}"

    def _decode_percent_encoded_ref(self, value: str) -> str:
        """Decode percent-encoded source refs until stable or fail closed."""
        decoded = value
        for _ in range(5):
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                return decoded
            decoded = next_decoded
        raise SourceSnapshotInvalid("durable source refs cannot contain nested encoded locators")

    def _validate_opaque_source_ref_path(self, decoded_path: str) -> None:
        """Require opaque durable refs to use approved virtual namespaces."""
        segments = [segment for segment in decoded_path.split("/") if segment]
        if not decoded_path.startswith("/") or len(segments) < 2:
            raise SourceSnapshotInvalid(
                "opaque durable source refs must use an approved virtual namespace"
            )
        if segments[0] not in OPAQUE_SOURCE_REF_NAMESPACES:
            raise SourceSnapshotInvalid(
                "opaque durable source refs must use an approved virtual namespace"
            )

    def _sanitize_content_cid(self, content_cid: str | None) -> str | None:
        """Validate optional immutable content identifiers before persistence."""
        if content_cid is None:
            return None
        normalized = content_cid.strip()
        parsed = urlparse(normalized)
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise SourceSnapshotInvalid("content CID cannot contain credentials or locators")
        if SECRET_REF_PATTERN.search(normalized):
            raise SourceSnapshotInvalid("content CID cannot contain credential material")
        if normalized.startswith(("/", "\\", "~")) or parsed.scheme in {"file"}:
            raise SourceSnapshotInvalid("content CID cannot be a local filesystem path")
        if not CONTENT_CID_PATTERN.fullmatch(normalized):
            raise SourceSnapshotInvalid("content CID must be an approved opaque identifier")
        return normalized

    def _require_sha256_hash(self, value: str, label: str) -> None:
        """Validate platform hash shape."""
        if not HASH_PATTERN.fullmatch(value):
            raise PolicySetupBlocked(f"{label} must be sha256:<64 lowercase hex>")

    def _hash_canonical_json(self, value: dict[str, Any]) -> str:
        """Hash canonical JSON using the Workstream policy hash contract."""
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def _canonical_policy_body(self, policy_body: dict[str, Any]) -> dict[str, Any]:
        """Normalize project policy content before hashing or merging."""
        packaging = policy_body.get("packaging", {})
        self._validate_packaging_rules(packaging)
        self._validate_unique_policy_rule_keys(
            policy_body.get("required_artifacts", []),
            "required artifact",
        )
        self._validate_unique_policy_rule_keys(
            policy_body.get("required_evidence", []),
            "required evidence",
        )
        for term in policy_body.get("attestation_terms", []):
            if len(term) > 100:
                raise PolicySetupBlocked("attestation terms must be 100 characters or fewer")
        return {
            "schema_version": "project_submission_artifact_policy.v1",
            "required_artifacts": sorted(
                policy_body.get("required_artifacts", []),
                key=lambda item: item["key"],
            ),
            "required_evidence": sorted(
                policy_body.get("required_evidence", []),
                key=lambda item: item["key"],
            ),
            "forbidden_artifacts": sorted(
                policy_body.get("forbidden_artifacts", []),
                key=lambda item: item["pattern"],
            ),
            "attestation_terms": sorted(set(policy_body.get("attestation_terms", []))),
            "manifest_required": policy_body.get("manifest_required", True),
            "artifact_hash_required": policy_body.get("artifact_hash_required", True),
            "artifact_hash_algorithm": policy_body.get(
                "artifact_hash_algorithm",
                PLATFORM_HASH_ALGORITHM,
            ),
            "allowed_storage_schemes": sorted(
                set(policy_body.get("allowed_storage_schemes", DEFAULT_ALLOWED_STORAGE_SCHEMES))
            ),
            "maximum_file_size_bytes": policy_body.get("maximum_file_size_bytes"),
            "maximum_package_size_bytes": policy_body.get("maximum_package_size_bytes"),
            "packaging": packaging,
        }

    def _validate_unique_policy_rule_keys(
        self,
        rules: list[dict[str, Any]],
        label: str,
    ) -> None:
        """Reject duplicate policy rule keys before canonicalization."""
        seen: set[str] = set()
        for rule in rules:
            key = rule["key"]
            if key in seen:
                raise PolicySetupBlocked(f"duplicate {label} key")
            seen.add(key)

    def _validate_packaging_rules(self, packaging: dict[str, Any]) -> None:
        """Validate the constrained packaging rules accepted in v0.1."""
        allowed_keys = {"package_required", "allowed_package_formats"}
        unknown_keys = set(packaging).difference(allowed_keys)
        if unknown_keys:
            raise PolicySetupBlocked("packaging rules contain unsupported fields")
        allowed_formats = packaging.get("allowed_package_formats", [])
        if not isinstance(allowed_formats, list) or not all(
            package_format in {"zip", "tar", "tar.gz", "tar.zst"}
            for package_format in allowed_formats
        ):
            raise PolicySetupBlocked("packaging rules contain unsupported package formats")

    def _validate_sufficiency_report_payload(
        self,
        payload: GuideSufficiencyReportCreate,
    ) -> None:
        """Ensure sufficiency status and finding severities agree."""
        severities = {finding.severity for finding in payload.findings}
        if "blocking_gap" in severities and payload.status != "blocked":
            raise PolicySetupBlocked("blocking guide sufficiency findings require blocked status")
        if payload.status == "blocked" and "blocking_gap" not in severities:
            raise PolicySetupBlocked("blocked sufficiency reports require blocking gap findings")
        if payload.status == "passed" and severities.intersection({"blocking_gap", "warning"}):
            raise PolicySetupBlocked("passed sufficiency reports cannot contain gaps or warnings")
        if payload.status == "passed_with_warnings":
            if "blocking_gap" in severities:
                raise PolicySetupBlocked("warning sufficiency reports cannot contain blocking gaps")
            if "warning" not in severities:
                raise PolicySetupBlocked("warning sufficiency reports require warning findings")

    def _merge_effective_submission_artifact_policy(
        self,
        project_policy: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge Workstream defaults with project policy or raise on weakening.

        Args:
            project_policy: Canonical project submission artifact policy body.

        Returns:
            Effective project submission artifact policy.

        Raises:
            PolicySetupBlocked: If project policy conflicts with defaults.
        """
        self._validate_project_policy_against_defaults(project_policy)
        default_policy = WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY
        allowed_storage_schemes = sorted(
            set(default_policy["allowed_storage_schemes"]).intersection(
                project_policy["allowed_storage_schemes"]
            )
        )
        if not allowed_storage_schemes:
            raise PolicySetupBlocked("project policy leaves no allowed storage schemes")

        maximum_file_size_bytes = self._minimum_non_null(
            default_policy["maximum_file_size_bytes"],
            project_policy["maximum_file_size_bytes"],
        )
        maximum_package_size_bytes = self._minimum_non_null(
            default_policy["maximum_package_size_bytes"],
            project_policy["maximum_package_size_bytes"],
        )
        effective_packaging = self._merge_packaging_rules(
            default_policy["packaging"],
            project_policy["packaging"],
        )
        required_artifacts = self._merge_required_policy_rules(
            default_policy["required_artifacts"],
            project_policy["required_artifacts"],
            "key",
        )
        required_evidence = self._merge_required_policy_rules(
            default_policy["required_evidence"],
            project_policy["required_evidence"],
            "key",
        )
        effective = {
            "schema_version": EFFECTIVE_POLICY_SCHEMA_VERSION,
            "merge_algorithm_version": MERGE_ALGORITHM_VERSION,
            "workstream_default_policy": default_policy,
            "project_policy": project_policy,
            "required_packet_fields": sorted(default_policy["required_packet_fields"]),
            "required_artifacts": required_artifacts,
            "required_evidence": required_evidence,
            "forbidden_artifacts": sorted(
                [
                    *default_policy["forbidden_artifacts"],
                    *project_policy["forbidden_artifacts"],
                ],
                key=lambda item: item["pattern"],
            ),
            "attestation_terms": sorted(
                set(default_policy["attestation_terms"]).union(project_policy["attestation_terms"])
            ),
            "manifest_required": bool(
                default_policy["manifest_required"] or project_policy["manifest_required"]
            ),
            "artifact_hash_required": bool(
                default_policy["artifact_hash_required"]
                or project_policy["artifact_hash_required"]
            ),
            "artifact_hash_algorithm": PLATFORM_HASH_ALGORITHM,
            "allowed_storage_schemes": allowed_storage_schemes,
            "maximum_file_size_bytes": maximum_file_size_bytes,
            "maximum_package_size_bytes": maximum_package_size_bytes,
            "packaging": effective_packaging,
        }
        return effective

    def _merge_required_policy_rules(
        self,
        default_rules: list[dict[str, Any]],
        project_rules: list[dict[str, Any]],
        key: str,
    ) -> list[dict[str, Any]]:
        """Union default and project rules without allowing conflicting overrides."""
        merged: dict[str, dict[str, Any]] = {}
        for rule in default_rules:
            merged[rule[key]] = rule
        for rule in project_rules:
            existing = merged.get(rule[key])
            if existing is not None and existing != rule:
                raise PolicySetupBlocked("project policy conflicts with Workstream default rules")
            merged[rule[key]] = rule
        return [merged[rule_key] for rule_key in sorted(merged)]

    def _merge_packaging_rules(
        self,
        default_packaging: dict[str, Any],
        project_packaging: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge packaging rules without weakening platform defaults."""
        default_required = bool(default_packaging.get("package_required", False))
        project_required = bool(project_packaging.get("package_required", False))
        default_formats = set(default_packaging.get("allowed_package_formats") or [])
        project_formats = set(project_packaging.get("allowed_package_formats") or [])

        if default_formats and project_formats:
            allowed_formats = default_formats.intersection(project_formats)
            if not allowed_formats:
                raise PolicySetupBlocked("packaging rules leave no allowed package formats")
        else:
            allowed_formats = default_formats or project_formats

        effective = {"package_required": default_required or project_required}
        if allowed_formats:
            effective["allowed_package_formats"] = sorted(allowed_formats)
        return effective

    def _validate_project_policy_against_defaults(self, project_policy: dict[str, Any]) -> None:
        """Reject project policy that weakens Workstream default intake rules."""
        if project_policy["manifest_required"] is False:
            raise PolicySetupBlocked("project policy cannot disable manifest requirements")
        if project_policy["artifact_hash_required"] is False:
            raise PolicySetupBlocked("project policy cannot disable artifact hash requirements")
        if project_policy["artifact_hash_algorithm"] != PLATFORM_HASH_ALGORITHM:
            raise PolicySetupBlocked("project policy cannot change the platform hash algorithm")
        if not set(project_policy["allowed_storage_schemes"]).issubset(
            DEFAULT_ALLOWED_STORAGE_SCHEMES
        ):
            raise PolicySetupBlocked("project policy cannot add unsupported storage schemes")
        forbidden_patterns = [
            *DEFAULT_FORBIDDEN_ARTIFACT_PATTERNS,
            *[rule["pattern"] for rule in project_policy["forbidden_artifacts"]],
        ]
        for artifact in project_policy["required_artifacts"]:
            if artifact["required"] and artifact["hash_required"] is not True:
                raise PolicySetupBlocked("required artifacts must require sha256 hashes")
            self._validate_artifact_path(artifact["path"])
            if (
                self._matches_forbidden_artifact(artifact["key"], forbidden_patterns)
                or self._matches_forbidden_artifact(artifact["path"], forbidden_patterns)
                or self._matches_forbidden_artifact(
                    artifact.get("description") or "",
                    forbidden_patterns,
                )
            ):
                raise PolicySetupBlocked("required artifact conflicts with forbidden artifacts")
        for evidence in project_policy["required_evidence"]:
            if evidence["required"] and evidence["hash_required"] is not True:
                raise PolicySetupBlocked("required evidence must require sha256 hashes")
            if (
                self._matches_forbidden_artifact(evidence["key"], forbidden_patterns)
                or self._matches_forbidden_artifact(evidence["label"], forbidden_patterns)
                or self._matches_forbidden_artifact(
                    evidence.get("description") or "",
                    forbidden_patterns,
                )
            ):
                raise PolicySetupBlocked("required evidence conflicts with forbidden artifacts")

    def _validate_artifact_path(self, path: str) -> None:
        """Validate relative artifact paths used by project policy."""
        if any(ord(character) < 32 or ord(character) == 127 for character in path):
            raise PolicySetupBlocked("artifact paths cannot contain control characters")
        decoded_path = self._decode_percent_encoded_artifact_path(path)
        if "%" in path or decoded_path != path:
            raise PolicySetupBlocked("artifact paths cannot contain percent-encoded characters")
        if not path or path.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", path):
            raise PolicySetupBlocked("artifact paths must be safe relative paths")
        if "\\" in path:
            raise PolicySetupBlocked("artifact paths cannot contain local path separators")
        if ":" in path or "://" in path or "?" in path or "#" in path:
            raise PolicySetupBlocked("artifact paths cannot be storage refs or URLs")
        segments = path.replace("\\", "/").split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise PolicySetupBlocked("artifact paths cannot contain empty or traversal segments")

    def _decode_percent_encoded_artifact_path(self, path: str) -> str:
        """Decode artifact paths until stable without allowing nested encodings."""
        decoded = path
        for _ in range(5):
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                return decoded
            decoded = next_decoded
        raise PolicySetupBlocked("artifact paths cannot contain nested percent-encoding")

    def _matches_forbidden_artifact(self, value: str, patterns: list[str]) -> bool:
        """Return whether a value is blocked by default or project forbidden rules."""
        normalized = value.replace("\\", "/").lower()
        token_normalized = re.sub(r"[-\s]+", "_", normalized)
        segments = normalized.split("/")
        token_segments = token_normalized.split("/")
        if SECRET_ARTIFACT_NAME_PATTERN.search(normalized) or self._contains_secret_artifact_tokens(
            normalized
        ):
            return True
        for pattern in patterns:
            normalized_pattern = pattern.lower()
            token_pattern = re.sub(r"[-\s]+", "_", normalized_pattern)
            if (
                normalized_pattern in segments
                or token_pattern in token_segments
                or fnmatch.fnmatch(normalized, normalized_pattern)
                or fnmatch.fnmatch(token_normalized, token_pattern)
                or any(fnmatch.fnmatch(segment, normalized_pattern) for segment in segments)
                or any(fnmatch.fnmatch(segment, token_pattern) for segment in token_segments)
            ):
                return True
            if token_pattern in token_normalized and token_pattern in {
                "credentials",
                "credential",
                "secrets",
                "secret",
                "private_key",
                "id_rsa",
                "token",
            }:
                return True
        return False

    def _contains_secret_artifact_tokens(self, value: str) -> bool:
        """Return whether any path segment uses credential-like words."""
        all_tokens: set[str] = set()
        for segment in value.split("/"):
            tokens = {
                token
                for token in re.split(r"[^a-z0-9]+", segment.lower())
                if token
            }
            all_tokens.update(tokens)
            if tokens.intersection(SECRET_ARTIFACT_SINGLE_TOKENS):
                return True
            if any(secret_tokens.issubset(tokens) for secret_tokens in SECRET_ARTIFACT_TOKEN_SETS):
                return True
        if any(secret_tokens.issubset(all_tokens) for secret_tokens in SECRET_ARTIFACT_TOKEN_SETS):
            return True
        return False

    def _minimum_non_null(self, left: int | None, right: int | None) -> int | None:
        """Return the stricter non-null numeric limit."""
        if left is None:
            return right
        if right is None:
            return left
        return min(left, right)

    def _approver_role(self, actor: ActorContext) -> str:
        """Return the setup role used for server-derived approval provenance."""
        for role in ("admin", "project_manager"):
            if role in actor.roles:
                return role
        raise PolicySetupBlocked("actor lacks project setup approval role")

    def _validate_sufficiency_report_allows_policy_approval(
        self,
        sufficiency_report: GuideSufficiencyReport | None,
        source_snapshot: GuideSourceSnapshot,
    ) -> None:
        """Require sufficiency clearance before approving derived policy."""
        if sufficiency_report is None:
            raise PolicySetupBlocked("guide sufficiency report is required before policy approval")
        if sufficiency_report.source_snapshot_id != source_snapshot.id:
            raise PolicySetupBlocked("guide sufficiency report is bound to a stale snapshot")
        if sufficiency_report.source_snapshot_hash != source_snapshot.bundle_hash:
            raise PolicySetupBlocked("guide sufficiency report snapshot hash mismatch")
        if sufficiency_report.status == "blocked":
            raise PolicySetupBlocked("guide sufficiency has blocking gaps")
        if sufficiency_report.status == "passed_with_warnings":
            self._validate_sufficiency_warning_acknowledgement(
                sufficiency_report,
                PolicySetupBlocked,
                "before policy approval",
            )

    def _validate_activation_ready(
        self,
        guide: ProjectGuide,
        source_snapshot: GuideSourceSnapshot,
        sufficiency_report: GuideSufficiencyReport | None,
        submission_artifact_policy: SubmissionArtifactPolicy,
        effective_policy: EffectiveProjectSubmissionArtifactPolicy | None,
        pre_submit_checker_policy: PreSubmitCheckerPolicy | None,
        checker_policy: CheckerPolicy | None,
        review_policy: ReviewPolicy | None,
        revision_policy: RevisionPolicy | None,
        payment_policy: PaymentPolicy | None,
    ) -> None:
        """Enforce the minimum guide and policy contract required to activate.

        Args:
            guide: Draft guide being promoted.
            source_snapshot: Immutable source snapshot used for policy setup.
            sufficiency_report: Guide sufficiency report bound to the snapshot.
            submission_artifact_policy: Approved submission artifact policy.
            effective_policy: Effective policy produced from default + project policy.
            pre_submit_checker_policy: Project pre-submit checker bundle contract.
            checker_policy: Checker policy for the guide version.
            review_policy: Review policy for the guide version.
            revision_policy: Revision policy for the guide version.
            payment_policy: Payment policy for the guide version.

        Raises:
            GuideActivationBlocked: If a required field or policy is missing.
        """
        if source_snapshot.project_id != guide.project_id:
            raise GuideActivationBlocked("guide source snapshot project mismatch")
        if source_snapshot.guide_id != guide.id or source_snapshot.guide_version != guide.version:
            raise GuideActivationBlocked("guide source snapshot is not current for the guide")
        if sufficiency_report is None:
            raise GuideActivationBlocked("guide sufficiency report is required")
        if sufficiency_report.source_snapshot_id != source_snapshot.id:
            raise GuideActivationBlocked("guide sufficiency report is bound to a stale snapshot")
        if sufficiency_report.source_snapshot_hash != source_snapshot.bundle_hash:
            raise GuideActivationBlocked("guide sufficiency report snapshot hash mismatch")
        if sufficiency_report.status == "blocked":
            raise GuideActivationBlocked("guide sufficiency has blocking gaps")
        if sufficiency_report.status == "passed_with_warnings":
            self._validate_sufficiency_warning_acknowledgement(
                sufficiency_report,
                GuideActivationBlocked,
                "before guide activation",
            )
        if submission_artifact_policy.lifecycle_status != "approved":
            raise GuideActivationBlocked("approved submission artifact policy is required")
        if submission_artifact_policy.source_snapshot_id != source_snapshot.id:
            raise GuideActivationBlocked("submission artifact policy is bound to a stale snapshot")
        if submission_artifact_policy.source_snapshot_hash != source_snapshot.bundle_hash:
            raise GuideActivationBlocked("submission artifact policy snapshot hash mismatch")
        if (
            self._hash_canonical_json(submission_artifact_policy.policy_body)
            != submission_artifact_policy.policy_hash
        ):
            raise GuideActivationBlocked("submission artifact policy body hash mismatch")
        if not submission_artifact_policy.approved_by_actor or not submission_artifact_policy.approved_at:
            raise GuideActivationBlocked("submission artifact policy approval provenance is required")
        if submission_artifact_policy.approved_by_role not in PROJECT_SETUP_ROLES:
            raise GuideActivationBlocked("submission artifact policy approver role is invalid")
        if effective_policy is None:
            raise GuideActivationBlocked("effective project submission artifact policy is required")
        if effective_policy.lifecycle_status != "approved":
            raise GuideActivationBlocked("effective project submission artifact policy is not approved")
        if effective_policy.source_snapshot_id != source_snapshot.id:
            raise GuideActivationBlocked(
                "effective project submission artifact policy is bound to a stale snapshot"
            )
        if effective_policy.source_snapshot_hash != source_snapshot.bundle_hash:
            raise GuideActivationBlocked(
                "effective project submission artifact policy snapshot hash mismatch"
            )
        if (
            self._hash_canonical_json(effective_policy.effective_policy)
            != effective_policy.effective_policy_hash
        ):
            raise GuideActivationBlocked(
                "effective project submission artifact policy body hash mismatch"
            )
        expected_effective_policy = self._merge_effective_submission_artifact_policy(
            submission_artifact_policy.policy_body
        )
        if self._hash_canonical_json(expected_effective_policy) != effective_policy.effective_policy_hash:
            raise GuideActivationBlocked(
                "effective project submission artifact policy no longer matches submission policy"
            )
        if effective_policy.submission_artifact_policy_id != submission_artifact_policy.id:
            raise GuideActivationBlocked(
                "effective project submission artifact policy is bound to the wrong policy"
            )
        if effective_policy.submission_artifact_policy_hash != submission_artifact_policy.policy_hash:
            raise GuideActivationBlocked(
                "effective project submission artifact policy hash provenance mismatch"
            )
        if pre_submit_checker_policy is None:
            raise GuideActivationBlocked("project pre-submit checker policy contract is required")
        if pre_submit_checker_policy.source_snapshot_id != source_snapshot.id:
            raise GuideActivationBlocked("pre-submit checker policy is bound to a stale snapshot")
        if pre_submit_checker_policy.source_snapshot_hash != source_snapshot.bundle_hash:
            raise GuideActivationBlocked("pre-submit checker policy snapshot hash mismatch")
        if pre_submit_checker_policy.effective_policy_id != effective_policy.id:
            raise GuideActivationBlocked(
                "pre-submit checker policy is bound to the wrong effective policy"
            )
        if pre_submit_checker_policy.effective_policy_hash != effective_policy.effective_policy_hash:
            raise GuideActivationBlocked("pre-submit checker bundle provenance mismatch")
        if pre_submit_checker_policy.lifecycle_status != "compiled":
            raise GuideActivationBlocked("compiled project pre-submit checker policy is required")
        if not pre_submit_checker_policy.compiled_bundle_hash:
            raise GuideActivationBlocked("pre-submit checker compiled bundle hash is required")
        if not pre_submit_checker_policy.compiled_bundle:
            raise GuideActivationBlocked("pre-submit checker compiled bundle is required")
        self._require_sha256_hash(
            pre_submit_checker_policy.compiled_bundle_hash,
            "pre-submit checker compiled bundle hash",
        )
        if not isinstance(pre_submit_checker_policy.compiled_bundle, dict):
            raise GuideActivationBlocked("pre-submit checker compiled bundle must be an object")
        if (
            self._hash_canonical_json(pre_submit_checker_policy.compiled_bundle)
            != pre_submit_checker_policy.compiled_bundle_hash
        ):
            raise GuideActivationBlocked("pre-submit checker compiled bundle hash mismatch")
        if checker_policy is None or not checker_policy.required_checkers:
            raise GuideActivationBlocked("checker policy with required checkers is required")
        checker_names = set(checker_policy.required_checkers or []).union(
            checker_policy.warning_checkers or []
        )
        try:
            default_checker_registry().require_registered(checker_names)
        except UnknownChecker as exc:
            raise GuideActivationBlocked(str(exc)) from exc
        if review_policy is None or not review_policy.allowed_decisions:
            raise GuideActivationBlocked("review policy with allowed decisions is required")
        if not set(review_policy.allowed_decisions).issubset(ALLOWED_REVIEW_DECISIONS):
            raise GuideActivationBlocked("review policy contains invalid decisions")
        if revision_policy is None:
            raise GuideActivationBlocked("revision policy is required")
        if (
            revision_policy.max_revision_rounds < 1
            or revision_policy.revision_deadline_hours < 1
            or not revision_policy.allowed_resubmission_states
        ):
            raise GuideActivationBlocked("revision policy is incomplete")
        if not set(revision_policy.allowed_resubmission_states).issubset(
            ALLOWED_REVISION_RESUBMISSION_STATES
        ):
            raise GuideActivationBlocked("revision policy contains invalid resubmission states")
        if payment_policy is None:
            raise GuideActivationBlocked("payment policy is required")
        if (
            payment_policy.base_amount is None
            or payment_policy.base_amount < Decimal("0")
            or not payment_policy.currency
            or not payment_policy.payout_type
            or not payment_policy.accepted_payment_rule
        ):
            raise GuideActivationBlocked("payment policy is incomplete")

    def _validate_sufficiency_warning_acknowledgement(
        self,
        sufficiency_report: GuideSufficiencyReport,
        exception_type: type[ProjectServiceError],
        action: str,
    ) -> None:
        """Require trusted provenance for warning acknowledgements."""
        if (
            not sufficiency_report.warnings_acknowledged_by_actor
            or not sufficiency_report.warnings_acknowledged_at
            or sufficiency_report.warnings_acknowledged_by_role not in PROJECT_SETUP_ROLES
        ):
            raise exception_type(
                f"guide sufficiency warnings require admin/project_manager acknowledgement {action}"
            )

    def _checker_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: CheckerPolicyInput,
    ) -> CheckerPolicy:
        """Build a checker policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated checker policy input.

        Returns:
            Unsaved checker policy model.
        """
        return CheckerPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            required_checkers=payload.required_checkers,
            warning_checkers=payload.warning_checkers,
            blocking_severities=payload.blocking_severities,
        )

    def _review_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: ReviewPolicyInput,
    ) -> ReviewPolicy:
        """Build a review policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated review policy input.

        Returns:
            Unsaved review policy model.
        """
        return ReviewPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            requires_second_review=payload.requires_second_review,
            allowed_decisions=payload.allowed_decisions,
            minimum_finding_fields=payload.minimum_finding_fields,
            sla_hours=payload.sla_hours,
        )

    def _revision_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: RevisionPolicyInput,
    ) -> RevisionPolicy:
        """Build a revision policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated revision policy input.

        Returns:
            Unsaved revision policy model.
        """
        return RevisionPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            max_revision_rounds=payload.max_revision_rounds,
            revision_deadline_hours=payload.revision_deadline_hours,
            auto_reject_after_limit=payload.auto_reject_after_limit,
            allowed_resubmission_states=payload.allowed_resubmission_states,
            reviewer_reassignment_rule=payload.reviewer_reassignment_rule,
        )

    def _payment_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: PaymentPolicyInput,
    ) -> PaymentPolicy:
        """Build a payment policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated payment policy input.

        Returns:
            Unsaved payment policy model.
        """
        return PaymentPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            base_amount=payload.base_amount,
            currency=payload.currency,
            payout_type=payload.payout_type,
            revision_payment_rule=payload.revision_payment_rule,
            rejection_payment_rule=payload.rejection_payment_rule,
            accepted_payment_rule=payload.accepted_payment_rule,
        )

    async def _active_response(
        self,
        guide: ProjectGuide,
        source_snapshot: GuideSourceSnapshot,
        sufficiency_report: GuideSufficiencyReport,
        submission_artifact_policy: SubmissionArtifactPolicy,
        effective_policy: EffectiveProjectSubmissionArtifactPolicy,
        pre_submit_checker_policy: PreSubmitCheckerPolicy,
        checker_policy: CheckerPolicy,
        review_policy: ReviewPolicy,
        revision_policy: RevisionPolicy,
        payment_policy: PaymentPolicy,
    ) -> ActiveGuideResponse:
        """Shape the active guide payload returned by lifecycle endpoints.

        Args:
            guide: Active project guide model.
            source_snapshot: Source snapshot bound to the active policy bundle.
            sufficiency_report: Sufficiency report bound to the snapshot.
            submission_artifact_policy: Approved project submission artifact policy.
            effective_policy: Effective project policy bound to the snapshot.
            pre_submit_checker_policy: Project pre-submit checker bundle contract.
            checker_policy: Checker policy attached to the active guide version.
            review_policy: Review policy attached to the active guide version.
            revision_policy: Revision policy attached to the active guide version.
            payment_policy: Payment policy attached to the active guide version.

        Returns:
            API response containing the active guide and policy context.
        """
        source_snapshot_response = await self._source_snapshot_response(source_snapshot)
        return ActiveGuideResponse(
            guide=ProjectGuideResponse.model_validate(guide),
            guide_source_snapshot=source_snapshot_response,
            guide_sufficiency_report=GuideSufficiencyReportResponse.model_validate(
                sufficiency_report
            ),
            submission_artifact_policy=SubmissionArtifactPolicyResponse.model_validate(
                submission_artifact_policy
            ),
            effective_submission_artifact_policy=(
                EffectiveProjectSubmissionArtifactPolicyResponse.model_validate(effective_policy)
            ),
            pre_submit_checker_policy=PreSubmitCheckerPolicySummaryResponse.model_validate(
                pre_submit_checker_policy
            ),
            checker_policy=CheckerPolicyResponse.model_validate(checker_policy),
            review_policy=ReviewPolicyResponse.model_validate(review_policy),
            revision_policy=RevisionPolicyResponse.model_validate(revision_policy),
            payment_policy=PaymentPolicyResponse.model_validate(payment_policy),
        )
