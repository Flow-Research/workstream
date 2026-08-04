"""Service layer for project and project-guide lifecycle operations."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import unquote
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.permissions import require_any_role
from app.core.project_agents import get_project_guide_agent_runtime
from app.interfaces.project_agents import (
    AgentFinding,
    GuideSourceItemMaterial,
    GuideSourceMaterial,
    GuideSufficiencyAgentResult,
    PostSubmitCheckerCatalogEntry,
    PostSubmitCheckerPolicyCorrectionFeedback,
    PostSubmitCheckerPolicyDerivationContext,
    PostSubmitCheckerPolicyDerivationResult,
    ProjectAgentRuntimeError,
    ProjectGuideAgentRuntime,
    RepresentativeTaskMaterialContext,
    MAXIMUM_VERIFIED_GUIDE_AGENT_MATERIAL_BYTES,
    canonical_guide_source_material_bytes,
)
from app.interfaces.artifact_operations import (
    GuideSufficiencyMaterialPort,
    GuideSufficiencyMaterialRequest,
    GuideSufficiencyMaterialUnavailable,
)
from app.modules.checkers.compiler import (
    PreSubmitCheckerCompilerError,
    compile_effective_project_submission_artifact_policy,
)
from app.modules.checkers.runner import UnknownChecker, default_checker_registry
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSufficiencyReport,
    GuideSufficiencyReportSourceUsage,
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
from app.modules.projects.policy_lineage import require_complete_policy
from app.modules.projects.post_submit_policy import (
    DEFAULT_DURABLE_CHECKERS,
    PostSubmitCheckerCompilerError,
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
    parse_locked_post_submit_checker_policy_body,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.setup_queue import (
    ProjectSetupQueueError,
    enqueue_post_submit_setup_continuation,
)
from app.modules.projects.schemas import (
    ActiveGuideResponse,
    ActiveGuideReadResponse,
    ActiveGuidePreSubmitCheckerPolicyResponse,
    EffectiveProjectSubmissionArtifactPolicyResponse,
    GuideSourceSnapshotCreate,
    GuideSourceSnapshotItemResponse,
    GuideSourceSnapshotResponse,
    GuideSufficiencyAcknowledgement,
    GuideSufficiencyReportCreate,
    GuideSufficiencyReportResponse,
    PaymentPolicyInput,
    PaymentPolicyResponse,
    PostSubmitCheckerPolicyApproval,
    PostSubmitCheckerPolicyCorrectionSummaryResponse,
    PostSubmitCheckerPolicyCorrectionRequest,
    PostSubmitCheckerPolicyResponse,
    PostSubmitCheckerPolicySetupResponse,
    PostSubmitCheckerPolicySetupSummaryResponse,
    ContributorProjectResponse,
    ProjectGuideResponse,
    ProjectResponse,
    ProjectSetupRunResponse,
    RevisionPolicyResponse,
    ReviewPolicyResponse,
    SubmissionArtifactPolicyInput,
    SubmissionArtifactPolicyApprove,
    SubmissionArtifactPolicyCreate,
    SubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyUpdate,
)
from app.schemas.auth import ActorContext

logger = logging.getLogger(__name__)

PROJECT_SETUP_PUBLIC_ERROR_SUMMARY = (
    "project setup failed; inspect server logs with the setup run id"
)
MAXIMUM_GUIDE_AGENT_MATERIAL_BYTES = MAXIMUM_VERIFIED_GUIDE_AGENT_MATERIAL_BYTES


def bounded_canonical_guide_material(material: GuideSourceMaterial) -> bytes:
    """Return the exact agent payload when it fits the locked aggregate limit."""
    payload = canonical_guide_source_material_bytes(material)
    if len(payload) > MAXIMUM_GUIDE_AGENT_MATERIAL_BYTES:
        raise GuideSufficiencyMaterialUnavailable("guide_source_limit_exceeded")
    return payload


def verified_guide_sufficiency_agent_item(item: Any) -> GuideSourceItemMaterial:
    """Map one ART-verified extraction item into bounded agent material."""
    return GuideSourceItemMaterial(
        source_kind=item.source_kind,
        durable_ref="",
        ingestion_adapter=item.ingestion_adapter,
        content_hash=item.artifact_sha256,
        media_type=item.media_type,
        source_item_id=str(item.source_item_id),
        item_order=item.item_order,
        binding_id=str(item.binding_id),
        artifact_content_id=str(item.content_id),
        artifact_sha256=item.artifact_sha256,
        artifact_byte_count=item.artifact_byte_count,
        classification_id=str(item.classification_id),
        detected_format=item.detected_format,
        extraction_attempt_id=str(item.extraction_attempt_id),
        extraction_usage_id=str(item.extraction_usage_id),
        extracted_content_id=str(item.extracted_content_id),
        extractor_name=item.extractor_name,
        extractor_version=item.extractor_version,
        extraction_policy_version=item.extraction_policy_version,
        canonical_output_sha256=item.canonical_output_sha256,
        omission_facts=item.omission_facts,
        canonical_content=item.canonical_content,
        structural_metadata=item.structural_metadata,
        untrusted_data=True,
        untrusted_data_label="UNTRUSTED_GUIDE_SOURCE_DATA",
    )


def build_verified_guide_sufficiency_material(
    guide: ProjectGuide,
    snapshot: GuideSourceSnapshot,
    source_items: Sequence[Any],
) -> GuideSourceMaterial:
    """Compose canonical agent input solely from ART-verified extraction rows."""
    verified_items = [verified_guide_sufficiency_agent_item(item) for item in source_items]
    return GuideSourceMaterial(
        project_id=guide.project_id,
        guide_id=guide.id,
        guide_version=guide.version,
        source_snapshot_id=snapshot.id,
        source_snapshot_hash=snapshot.bundle_hash,
        guide_material={
            field: getattr(guide, field) for field in sorted(GUIDE_SOURCE_MATERIAL_FIELDS)
        },
        verified_artifact_material=True,
        source_items=verified_items,
        source_refs=[],
        representative_task_material=RepresentativeTaskMaterialContext(items=[]),
    )


PROJECT_SETUP_ROLES = {"admin", "project_manager"}
ALLOWED_REVIEW_DECISIONS = {"accept", "needs_revision", "reject"}
ALLOWED_REVISION_RESUBMISSION_STATES = {"needs_revision"}
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
HASH_TOKEN_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
SAFE_PUBLIC_SUMMARY_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,79}$")
SECRET_REF_PATTERN = re.compile(
    r"(x-amz-|access[_-]?key|private[_-]?key|"
    r"(?<![a-z0-9])(?:signature|credentials?|secrets?|tokens?|password)(?![a-z0-9]))",
    re.IGNORECASE,
)
CREDENTIAL_SHAPE_PATTERN = re.compile(
    r"("
    r"AKIA[0-9A-Z]{16}|"
    r"ASIA[0-9A-Z]{16}|"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"sk_live_[A-Za-z0-9]{20,}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"gho_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r")"
)
SECRET_ARTIFACT_NAME_PATTERN = re.compile(
    r"(^|/)("
    r"[^/]*\.env[^/]*|"
    r"\.npmrc[^/]*|\.pypirc[^/]*|"
    r"id_(rsa|dsa|ecdsa|ed25519)(\.[^/]*)?|"
    r"private[_\-]?key[^/]*|"
    r"api[_\-]?key[^/]*|"
    r"access[_\-]?key[^/]*|"
    r"secrets?(?=$|[_.\-])[^/]*|"
    r"credentials?(?=$|[_.\-])[^/]*|"
    r"tokens?(?=$|[_.\-])[^/]*|"
    r"service[_\-]?account[^/]*|"
    r"[^/]*\.pem"
    r")($|/)|"
    r"(^|/)(private|api|access)/key(\.[^/]*)?($|/)",
    re.IGNORECASE,
)


def safe_project_setup_error_summary(summary: str | None) -> str:
    """Return the only public setup-run error summary allowed by APIs/log results."""
    if summary is None or not " ".join(summary.split()):
        return "project setup failed"
    normalized = " ".join(summary.split())
    if normalized.startswith("unsupported post-submit checker requirements:"):
        unsupported_names = [
            name.strip()
            for name in normalized.removeprefix(
                "unsupported post-submit checker requirements:"
            ).split(",")
            if name.strip()
        ]
        if unsupported_names and all(
            SAFE_PUBLIC_SUMMARY_LABEL_PATTERN.fullmatch(name) for name in unsupported_names
        ):
            return f"unsupported post-submit checker requirements: {', '.join(unsupported_names)}"
    return PROJECT_SETUP_PUBLIC_ERROR_SUMMARY


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
GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION = "guide_source_snapshot.v2"
EFFECTIVE_POLICY_SCHEMA_VERSION = "effective_project_submission_artifact_policy.v1"
MERGE_ALGORITHM_VERSION = "workstream_default_merge.v1"
PLATFORM_HASH_ALGORITHM = "sha256"
MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE = "manual_admin_derivation"
AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE = "agent_derivation"
PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME = "ProjectGuideSufficiencyAgent"
PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION = "workstream-sufficiency-agent-v0.1"
SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_NAME = "SubmissionArtifactPolicyDerivationAgent"
SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_VERSION = "workstream-policy-derivation-agent-v0.1"
POST_SUBMIT_CHECKER_POLICY_DERIVATION_AGENT_NAME = "PostSubmitCheckerPolicyDerivationAgent"
POST_SUBMIT_CHECKER_POLICY_DERIVATION_AGENT_VERSION = (
    "workstream-post-submit-policy-derivation-agent-v0.1"
)
AGENT_SUFFICIENCY_STATUS_TO_REPORT_STATUS = {
    "guide_sufficient": "passed",
    "guide_blocked": "blocked",
    "guide_sufficient_with_warnings": "passed_with_warnings",
}
REPORT_STATUS_TO_AGENT_SUFFICIENCY_STATUS = {
    report_status: agent_status
    for agent_status, report_status in AGENT_SUFFICIENCY_STATUS_TO_REPORT_STATUS.items()
}


@dataclass(frozen=True, slots=True)
class SufficiencyCreationAuthority:
    """Optional exact authorization provenance for one staged agent report."""

    actor_profile_id: str
    identity_link_id: str
    admin_role_grant_id: UUID | None
    service_identity: str | None
    scope_type: str
    scope_project_id: str
    action_id: str
    decision_event_id: str


def validate_sufficiency_report_payload(payload: GuideSufficiencyReportCreate) -> None:
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


def stage_verified_sufficiency_report(
    session: AsyncSession,
    *,
    report_id: str,
    project_id: str,
    guide_id: str,
    guide_version: str,
    source_snapshot_id: str,
    source_snapshot_hash: str,
    payload: GuideSufficiencyReportCreate,
    setup_run_id: str,
    setup_generation: int,
    material_sha256: str,
    material_byte_count: int,
    source_provenance: Sequence[Any],
    created_by: str,
    authority: SufficiencyCreationAuthority | None = None,
) -> GuideSufficiencyReport:
    """Stage one canonical agent report and its exact ART source usages."""
    report = GuideSufficiencyReport(
        id=report_id,
        project_id=project_id,
        guide_id=guide_id,
        guide_version=guide_version,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_hash=source_snapshot_hash,
        status=payload.status,
        findings=[finding.model_dump(mode="json") for finding in payload.findings],
        summary=payload.summary,
        agent_name=PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME,
        agent_version=PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION,
        project_setup_run_id=setup_run_id,
        setup_generation=setup_generation,
        agent_material_sha256=material_sha256,
        agent_material_byte_count=material_byte_count,
        created_by=created_by,
        created_by_actor_profile_id=(authority.actor_profile_id if authority else None),
        created_via_identity_link_id=(authority.identity_link_id if authority else None),
        created_by_admin_role_grant_id=(authority.admin_role_grant_id if authority else None),
        created_by_service_identity=(authority.service_identity if authority else None),
        creation_scope_type=(authority.scope_type if authority else None),
        creation_scope_project_id=(authority.scope_project_id if authority else None),
        creation_action_id=(authority.action_id if authority else None),
        authorization_decision_event_id=(authority.decision_event_id if authority else None),
    )
    session.add(report)
    for item in source_provenance:
        session.add(
            GuideSufficiencyReportSourceUsage(
                id=str(uuid4()),
                report_id=report.id,
                item_order=item.item_order,
                source_item_id=str(item.source_item_id),
                binding_id=str(item.binding_id),
                content_id=str(item.content_id),
                extraction_usage_id=str(item.extraction_usage_id),
                extraction_attempt_id=str(item.extraction_attempt_id),
                extracted_content_id=str(item.extracted_content_id),
                canonical_output_sha256=item.canonical_output_sha256,
                project_setup_run_id=setup_run_id,
                setup_generation=setup_generation,
            )
        )
    return report
PROJECT_SETUP_TERMINAL_STATUSES = {
    "enqueue_failed",
    "sufficiency_blocked",
    "policy_draft_ready",
    "post_submit_setup_blocked",
    "post_submit_policy_compiled",
    "setup_blocked",
    "failed",
}
SAFE_POST_SUBMIT_EVIDENCE_REF_PATTERN = re.compile(
    r"^(project_guide|source_item:[0-9]{1,3}|sufficiency_report|effective_policy|pre_submit_checker)$"
)


def agent_submission_artifact_policy_version(source_snapshot_hash: str) -> str:
    """Return the server-owned policy version for agent-derived snapshot policy."""
    return f"agent-{source_snapshot_hash.removeprefix('sha256:')[:24]}"


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
GUIDE_SOURCE_MATERIAL_FIELDS = {
    "content_markdown",
}
REPRESENTATIVE_TASK_SOURCE_KINDS = {"example", "representative_task", "task_sample", "task_example"}
SOURCE_ITEM_SOURCE_LABEL_MAX_LENGTH = 500
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


class GuideVersionConflict(ProjectServiceError):
    """Raised when a guide version already exists for a project."""

    status_code = 409


class GuideActivationConflict(ProjectServiceError):
    """Raised when another transaction wins the guide activation race."""

    status_code = 409


class SourceSnapshotNotFound(ProjectServiceError):
    """Raised when a source snapshot cannot be found for a guide."""

    status_code = 404


class ProjectSetupRunNotFound(ProjectServiceError):
    """Raised when a project setup run cannot be found for a guide."""

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


class EffectiveProjectSubmissionArtifactPolicyNotFound(ProjectServiceError):
    """Raised when an effective project submission artifact policy cannot be found."""

    status_code = 404


class PreSubmitCheckerPolicyNotFound(ProjectServiceError):
    """Raised when a pre-submit checker policy cannot be found."""

    status_code = 404


class PolicySetupBlocked(ProjectServiceError):
    """Raised when project submission artifact policy setup is invalid."""

    status_code = 422

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """Initialize a setup-blocked error with optional safe details."""
        super().__init__(message)
        self.details = details or {}


class PolicySetupConflict(ProjectServiceError):
    """Raised when concurrent project policy setup wins a database race."""

    status_code = 409


class StaleProjectSetupContinuation(ProjectServiceError):
    """Raised when an old setup-continuation payload no longer matches the ledger."""

    status_code = 409


class PolicyEditBlocked(ProjectServiceError):
    """Raised when immutable policy rows are edited."""

    status_code = 409


class AgentRuntimeUnavailable(ProjectServiceError):
    """Raised when the configured project-agent runtime cannot run."""

    status_code = 503


class ProjectService:
    """Coordinates project guide rules, persistence, and response shaping.

    The service owns business rules for project setup and guide activation. It
    keeps routers thin and repositories focused on database access.
    """

    def __init__(
        self,
        session: AsyncSession,
        agent_runtime: ProjectGuideAgentRuntime | None = None,
        guide_sufficiency_material: GuideSufficiencyMaterialPort | None = None,
    ) -> None:
        """Create a service instance bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current request.
            agent_runtime: Optional project guide agent runtime override for tests.
        """
        self._session = session
        self._repo = ProjectRepository(session)
        self._agent_runtime = agent_runtime
        self._guide_sufficiency_material = guide_sufficiency_material

    def _project_agent_runtime(self) -> ProjectGuideAgentRuntime:
        """Return the configured project-agent runtime only for agent routes.

        Raises:
            AgentRuntimeUnavailable: If runtime configuration is incomplete or invalid.
        """
        if self._agent_runtime is not None:
            return self._agent_runtime
        try:
            return get_project_guide_agent_runtime()
        except ProjectAgentRuntimeError:
            raise AgentRuntimeUnavailable("project guide agent runtime is unavailable") from None

    async def resolve_project(self, project_id: str) -> Project:
        """Resolve one canonical project before authorization."""
        project = await self._repo.get_project(project_id)
        if project is None:
            raise ProjectNotFound("project not found")
        return project

    async def find_project(self, project_id: str) -> Project | None:
        """Return one canonical project without inventing an absence response."""
        return await self._repo.get_project(project_id)

    @staticmethod
    def project_identity_response(
        project: Project, *, contributor_only: bool
    ) -> ProjectResponse | ContributorProjectResponse:
        """Select the server-owned project identity disclosure shape."""
        if contributor_only:
            return ContributorProjectResponse.model_validate(project)
        return ProjectResponse.model_validate(project)

    async def approve_current_post_submit_checker_policy(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        payload: PostSubmitCheckerPolicyApproval,
    ) -> PostSubmitCheckerPolicySetupResponse:
        """Approve the current compiled project post-submit checker policy.

        Approval records are immutable. Retrying approval for an already
        approved policy returns the existing provenance without rewriting it.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can approve post-submit checker policies")
        setup_run = await self._repo.get_latest_project_setup_run(project_id, guide.id)
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        if (
            setup_run.status != "post_submit_policy_compiled"
            or setup_run.output_post_submit_checker_policy_id is None
        ):
            raise PolicySetupBlocked(
                "compiled post-submit checker policy setup output is required before approval"
            )
        policy = await self._repo.lock_post_submit_checker_policy(
            setup_run.output_post_submit_checker_policy_id
        )
        if policy is None:
            raise PolicySetupConflict("project setup run post-submit policy output mismatch")
        await self._validate_current_post_submit_policy_setup(guide, setup_run, policy)
        if policy.lifecycle_status == "superseded":
            raise PolicyEditBlocked("superseded post-submit checker policies are immutable")
        if policy.lifecycle_status == "approved":
            return await self._post_submit_policy_setup_response(setup_run, policy)
        if policy.lifecycle_status != "compiled":
            raise PolicySetupBlocked("compiled post-submit checker policy is required")
        now = datetime.now(UTC)
        policy.lifecycle_status = "approved"
        policy.approved_by_role = self._approver_role(actor)
        policy.approved_by_actor = actor.actor_id
        policy.approved_at = now
        await self._session.commit()
        await self._session.refresh(setup_run)
        await self._session.refresh(policy)
        return await self._post_submit_policy_setup_response(setup_run, policy)

    async def request_post_submit_checker_policy_correction(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        payload: PostSubmitCheckerPolicyCorrectionRequest,
    ) -> PostSubmitCheckerPolicySetupResponse:
        """Block the current compiled post-submit checker policy for correction."""
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can request post-submit policy correction")
        setup_run = await self._repo.get_latest_project_setup_run(project_id, guide.id)
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        if setup_run.output_post_submit_checker_policy_id is None:
            raise PolicySetupBlocked("compiled post-submit checker policy is required")
        policy = await self._repo.lock_post_submit_checker_policy(
            setup_run.output_post_submit_checker_policy_id
        )
        if policy is None:
            raise PolicySetupConflict("project setup run post-submit policy output mismatch")
        await self._validate_current_post_submit_policy_setup(guide, setup_run, policy)
        if policy.lifecycle_status == "approved":
            raise PolicyEditBlocked("approved post-submit checker policies are immutable")
        if policy.lifecycle_status != "compiled":
            raise PolicySetupBlocked("compiled post-submit checker policy is required")
        previous_policy_id = policy.id
        effective_policy_id = policy.effective_policy_id
        pre_submit_checker_policy_id = policy.pre_submit_checker_policy_id
        now = datetime.now(UTC)
        correction_reason = self._safe_bounded_summary_value(payload.correction_reason)
        self._supersede_post_submit_checker_policy(
            policy,
            actor,
            supersession_kind="correction_requested",
            supersession_reason=correction_reason,
            superseded_at=now,
        )
        setup_run.status = "post_submit_setup_blocked"
        setup_run.current_step = "post_submit_checker_policy_approval"
        setup_run.output_post_submit_checker_policy_id = None
        setup_run.post_submit_derivation_summary = self._safe_post_submit_derivation_summary(
            {
                "status": "correction_requested",
                "reason": correction_reason,
                "post_submit_checker_policy_id": previous_policy_id,
                "correction_requested_by_role": self._approver_role(actor),
                "correction_requested_by_actor": actor.actor_id,
                "correction_requested_at": now.isoformat(),
            }
        )
        setup_run.error_code = "post_submit_policy_correction_requested"
        setup_run.error_summary = "post-submit checker policy correction requested"
        setup_run.finished_at = now
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(setup_run)
        await self._enqueue_post_submit_setup_continuation_after_commit(
            project_id=project_id,
            guide_id=guide.id,
            source_snapshot_id=setup_run.source_snapshot_id,
            setup_run_id=setup_run.id,
            effective_policy_id=effective_policy_id,
            pre_submit_checker_policy_id=pre_submit_checker_policy_id,
        )
        refreshed_setup_run = await self._repo.get_project_setup_run(setup_run.id)
        if refreshed_setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        refreshed_policy = await self._post_submit_policy_from_setup_run(refreshed_setup_run)
        return await self._post_submit_policy_setup_response(
            refreshed_setup_run,
            refreshed_policy,
        )

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
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
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
            agent_name=None,
            agent_version=None,
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

    async def run_verified_guide_sufficiency_agent(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        setup_run_id: str,
        setup_generation: int,
    ) -> tuple[GuideSufficiencyReportResponse, bool]:
        """Run the hidden canonical ART-backed sufficiency continuation."""
        require_any_role(actor, PROJECT_SETUP_ROLES)
        if self._guide_sufficiency_material is None:
            raise PolicySetupBlocked("verified guide sufficiency is unavailable")
        request = GuideSufficiencyMaterialRequest(
            project_id=UUID(project_id),
            guide_id=UUID(guide_id),
            guide_source_snapshot_id=UUID(source_snapshot_id),
            project_setup_run_id=UUID(setup_run_id),
            setup_generation=setup_generation,
        )
        guide = await self._get_project_guide(project_id, guide_id)
        snapshot = await self._get_snapshot_for_guide(project_id, guide, source_snapshot_id)
        first = await self._guide_sufficiency_material.load(request)
        material = build_verified_guide_sufficiency_material(guide, snapshot, first.source_items)
        first_prompt = bounded_canonical_guide_material(material)
        first_prompt_sha256 = f"sha256:{hashlib.sha256(first_prompt).hexdigest()}"
        existing = await self._repo.get_sufficiency_report_for_snapshot(source_snapshot_id)
        if existing is not None:
            if (
                existing.project_setup_run_id == setup_run_id
                and existing.setup_generation == setup_generation
                and existing.agent_material_sha256 == first_prompt_sha256
            ):
                response = GuideSufficiencyReportResponse.model_validate(existing)
                await self._session.rollback()
                return response, False
            await self._session.rollback()
            raise PolicySetupConflict("guide sufficiency report provenance mismatch")
        await self._session.rollback()
        try:
            result = await self._project_agent_runtime().analyze_guide_sufficiency(material)
        except ProjectAgentRuntimeError:
            raise AgentRuntimeUnavailable(
                "project guide sufficiency agent is unavailable"
            ) from None
        payload = GuideSufficiencyReportCreate(
            source_snapshot_id=source_snapshot_id,
            status=AGENT_SUFFICIENCY_STATUS_TO_REPORT_STATUS[result.status],
            findings=[finding.model_dump(mode="json") for finding in result.findings],
            summary=result.summary,
        )
        self._validate_sufficiency_report_payload(payload)
        second = await self._guide_sufficiency_material.load(request)
        second_material = material.model_copy(
            update={
                "source_items": [
                    verified_guide_sufficiency_agent_item(item) for item in second.source_items
                ]
            }
        )
        second_prompt = bounded_canonical_guide_material(second_material)
        second_prompt_sha256 = f"sha256:{hashlib.sha256(second_prompt).hexdigest()}"
        if second_prompt_sha256 != first_prompt_sha256 or second.provenance != first.provenance:
            await self._session.rollback()
            raise PolicySetupConflict("verified guide material changed")
        existing = await self._repo.get_sufficiency_report_for_snapshot(source_snapshot_id)
        if existing is not None:
            if (
                existing.project_setup_run_id == setup_run_id
                and existing.setup_generation == setup_generation
                and existing.agent_material_sha256 == second_prompt_sha256
            ):
                response = GuideSufficiencyReportResponse.model_validate(existing)
                await self._session.rollback()
                return response, False
            await self._session.rollback()
            raise PolicySetupConflict("guide sufficiency report provenance mismatch")
        report = stage_verified_sufficiency_report(
            self._session,
            report_id=str(uuid4()),
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide.version,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=snapshot.bundle_hash,
            payload=payload,
            setup_run_id=setup_run_id,
            setup_generation=setup_generation,
            material_sha256=second_prompt_sha256,
            material_byte_count=len(second_prompt),
            source_provenance=second.provenance,
            created_by=actor.actor_id,
        )
        setup_run = await self._repo.lock_project_setup_run(setup_run_id)
        if setup_run is None or setup_run.setup_generation != setup_generation:
            await self._session.rollback()
            raise PolicySetupConflict("project setup run context mismatch")
        setup_run.output_sufficiency_report_id = report.id
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            concurrent = await self._repo.get_sufficiency_report_for_snapshot(source_snapshot_id)
            if (
                concurrent is not None
                and concurrent.project_setup_run_id == setup_run_id
                and concurrent.setup_generation == setup_generation
                and concurrent.agent_material_sha256 == second_prompt_sha256
            ):
                return GuideSufficiencyReportResponse.model_validate(concurrent), False
            raise PolicySetupConflict(
                "guide sufficiency report conflicted with concurrent setup; retry"
            ) from exc
        await self._session.refresh(report)
        return GuideSufficiencyReportResponse.model_validate(report), True

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
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        policy_body = self._canonical_policy_body(payload.policy_body.model_dump(mode="json"))
        self._merge_effective_submission_artifact_policy(policy_body)
        sufficiency_report = await self._repo.get_diagnostic_sufficiency_report_for_snapshot(
            snapshot.id
        )
        self._validate_sufficiency_report_allows_policy_approval(
            sufficiency_report,
            snapshot,
        )
        source_material_refs = await self._verified_source_material_refs(sufficiency_report)
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
            derivation_source=MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE,
            source_material_refs=source_material_refs,
            derivation_agent_name=None,
            derivation_agent_version=None,
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

    async def run_submission_artifact_policy_derivation_agent(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
    ) -> tuple[SubmissionArtifactPolicyResponse, bool]:
        """Run the configured policy derivation agent for a source snapshot.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Guide whose immutable source snapshot should be analyzed.
            source_snapshot_id: Source snapshot id to derive policy from.

        Returns:
            Existing or newly persisted policy plus whether it was created.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._get_project_guide(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can derive submission artifact policies")
        snapshot = await self._get_snapshot_for_guide(project_id, guide, source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        sufficiency_report = await self._repo.get_sufficiency_report_for_snapshot(snapshot.id)
        self._validate_sufficiency_report_allows_policy_derivation(
            sufficiency_report,
            snapshot,
        )
        await self._validate_agent_sufficiency_report_for_derivation(sufficiency_report)
        assert sufficiency_report is not None
        existing = await self._repo.get_agent_derived_submission_artifact_policy_for_snapshot(
            project_id,
            guide.version,
            snapshot.id,
        )
        if existing is not None:
            self._validate_agent_derived_submission_artifact_policy(existing, snapshot)
            return SubmissionArtifactPolicyResponse.model_validate(existing), False

        material = await self._verified_guide_source_material(
            guide,
            snapshot,
            sufficiency_report,
        )
        runtime_report = GuideSufficiencyAgentResult(
            status=REPORT_STATUS_TO_AGENT_SUFFICIENCY_STATUS[sufficiency_report.status],
            findings=[
                AgentFinding.model_validate(finding) for finding in sufficiency_report.findings
            ],
            summary=sufficiency_report.summary,
            agent_name=PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME,
            agent_version=PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION,
        )
        await self._session.rollback()
        try:
            result = await self._project_agent_runtime().derive_submission_artifact_policy(
                material,
                runtime_report,
            )
        except ProjectAgentRuntimeError:
            raise AgentRuntimeUnavailable(
                "submission artifact policy agent is unavailable"
            ) from None

        try:
            policy_input = SubmissionArtifactPolicyInput.model_validate(result.policy_body)
        except ValueError as exc:
            raise PolicySetupBlocked("derived submission artifact policy is invalid") from exc
        policy_body = self._canonical_policy_body(policy_input.model_dump(mode="json"))
        self._merge_effective_submission_artifact_policy(policy_body)
        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can derive submission artifact policies")
        snapshot = await self._get_snapshot_for_guide(project_id, guide, source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        sufficiency_report = await self._repo.get_sufficiency_report_for_snapshot(snapshot.id)
        self._validate_sufficiency_report_allows_policy_derivation(
            sufficiency_report,
            snapshot,
        )
        await self._validate_agent_sufficiency_report_for_derivation(sufficiency_report)
        existing = await self._repo.get_agent_derived_submission_artifact_policy_for_snapshot(
            project_id,
            guide.version,
            snapshot.id,
        )
        if existing is not None:
            self._validate_agent_derived_submission_artifact_policy(existing, snapshot)
            return SubmissionArtifactPolicyResponse.model_validate(existing), False
        source_material_refs = await self._verified_source_material_refs(sufficiency_report)
        policy = SubmissionArtifactPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            policy_version=agent_submission_artifact_policy_version(snapshot.bundle_hash),
            lifecycle_status="draft",
            policy_body=policy_body,
            policy_hash=self._hash_canonical_json(policy_body),
            derivation_source=AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE,
            source_material_refs=source_material_refs,
            derivation_agent_name=SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_NAME,
            derivation_agent_version=SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_VERSION,
            created_by=actor.actor_id,
            change_summary=result.change_summary,
        )
        try:
            policy = await self._repo.add_submission_artifact_policy(policy)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._repo.get_agent_derived_submission_artifact_policy_for_snapshot(
                project_id,
                guide.version,
                snapshot.id,
            )
            if existing is not None:
                self._validate_agent_derived_submission_artifact_policy(existing, snapshot)
                return SubmissionArtifactPolicyResponse.model_validate(existing), False
            raise PolicySetupConflict(
                "submission artifact policy conflicted with concurrent setup; retry"
            ) from exc
        await self._session.refresh(policy)
        return SubmissionArtifactPolicyResponse.model_validate(policy), True

    async def run_post_submit_checker_policy_derivation_agent(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        effective_policy_id: str,
        pre_submit_checker_policy_id: str,
        setup_run_id: str,
    ) -> tuple[PostSubmitCheckerPolicyResponse, bool, dict[str, Any]]:
        """Run post-submit checker derivation and trusted compilation for setup.

        Args:
            actor: Verified Flow actor context for the setup automation.
            project_id: Project that owns the guide.
            guide_id: Guide whose immutable source snapshot should be analyzed.
            source_snapshot_id: Source snapshot id to derive policy from.
            effective_policy_id: Approved effective project policy id.
            pre_submit_checker_policy_id: Compiled pre-submit checker policy id.
            setup_run_id: Setup-run ledger id that owns this continuation payload.

        Returns:
            Compiled post-submit policy, whether it was created, and a safe
            derivation summary for the setup ledger.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._get_project_guide(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can derive post-submit checker policies")
        guide_version = guide.version
        snapshot = await self._get_snapshot_for_guide(project_id, guide, source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        sufficiency_report = await self._repo.get_sufficiency_report_for_snapshot(snapshot.id)
        self._validate_sufficiency_report_allows_policy_derivation(
            sufficiency_report,
            snapshot,
        )
        await self._validate_agent_sufficiency_report_for_derivation(sufficiency_report)
        assert sufficiency_report is not None
        effective_policy = await self._repo.get_effective_submission_artifact_policy_by_id(
            effective_policy_id
        )
        if (
            effective_policy is None
            or effective_policy.project_id != project_id
            or effective_policy.guide_id != guide.id
            or effective_policy.guide_version != guide.version
            or effective_policy.source_snapshot_id != snapshot.id
            or effective_policy.source_snapshot_hash != snapshot.bundle_hash
            or effective_policy.lifecycle_status != "approved"
        ):
            raise PolicySetupBlocked(
                "effective project submission artifact policy is required before post-submit derivation"
            )
        pre_submit_checker_policy = await self._repo.get_pre_submit_checker_policy(
            pre_submit_checker_policy_id
        )
        if (
            pre_submit_checker_policy is None
            or pre_submit_checker_policy.project_id != project_id
            or pre_submit_checker_policy.guide_id != guide.id
            or pre_submit_checker_policy.guide_version != guide.version
            or pre_submit_checker_policy.source_snapshot_id != snapshot.id
            or pre_submit_checker_policy.source_snapshot_hash != snapshot.bundle_hash
            or pre_submit_checker_policy.effective_policy_id != effective_policy.id
            or pre_submit_checker_policy.effective_policy_hash
            != effective_policy.effective_policy_hash
            or pre_submit_checker_policy.lifecycle_status != "compiled"
            or not pre_submit_checker_policy.compiled_bundle_hash
        ):
            raise PolicySetupBlocked(
                "compiled project pre-submit checker policy is required before post-submit derivation"
            )
        superseded_policy = await self._repo.get_latest_superseded_post_submit_checker_policy(
            project_id,
            guide.id,
            guide.version,
            snapshot.id,
            snapshot.bundle_hash,
            effective_policy.id,
            effective_policy.effective_policy_hash,
            pre_submit_checker_policy.id,
            pre_submit_checker_policy.compiled_bundle_hash,
        )
        has_correction_feedback = (
            superseded_policy is not None
            and superseded_policy.supersession_kind == "correction_requested"
        )
        superseded_policy_id = superseded_policy.id if has_correction_feedback else None
        superseded_policy_hash = superseded_policy.policy_hash if has_correction_feedback else None

        material = await self._verified_guide_source_material(
            guide,
            snapshot,
            sufficiency_report,
        )
        context = self._post_submit_derivation_context(
            sufficiency_report,
            effective_policy,
            pre_submit_checker_policy,
            superseded_policy,
        )
        await self._session.rollback()
        try:
            result = await self._project_agent_runtime().derive_post_submit_checker_policy(
                material,
                context,
            )
        except ProjectAgentRuntimeError:
            raise AgentRuntimeUnavailable(
                "post-submit checker policy agent is unavailable"
            ) from None

        self._validate_post_submit_derivation_result(result)
        safe_reasons = [
            {
                "checker_name": reason.checker_name,
                "evidence_refs": [
                    self._safe_bounded_summary_value(ref.ref) for ref in reason.evidence_refs[:10]
                ],
            }
            for reason in result.reasons[:100]
        ]
        if result.unsupported_required_checks:
            unsupported_gaps = [
                {
                    "requested_checker": self._safe_public_unsupported_requirement(
                        gap.requested_checker
                    ),
                    "reason_code": "unsupported_required_checker",
                    "evidence_refs": [
                        self._safe_bounded_summary_value(ref.ref) for ref in gap.evidence_refs[:10]
                    ],
                }
                for gap in result.unsupported_required_checks[:50]
            ]
            unsupported_names = sorted({gap["requested_checker"] for gap in unsupported_gaps})
            raise PolicySetupBlocked(
                "unsupported post-submit checker requirements: " + ", ".join(unsupported_names),
                details={"unsupported_required_checks": unsupported_gaps},
            )
        self._raise_for_unknown_post_submit_checkers(result)
        try:
            spec = build_project_post_submit_checker_spec(
                project_id=project_id,
                guide_version=guide_version,
                required_checkers=result.required_checkers,
                warning_checkers=result.warning_checkers,
                blocking_severities=result.blocking_severities,
            )
            compiled_policy = compile_project_post_submit_checker_spec(
                project_id=project_id,
                guide_version=guide_version,
                spec=spec,
            )
        except PostSubmitCheckerCompilerError as exc:
            raise PolicySetupBlocked("post-submit checker policy compilation failed") from exc
        if (
            has_correction_feedback
            and superseded_policy_hash is not None
            and compiled_policy.policy_hash == superseded_policy_hash
        ):
            raise PolicySetupBlocked(
                "post-submit checker policy correction produced unchanged policy"
            )
        summary = self._safe_post_submit_derivation_summary(
            {
                "status": "compiled",
                "required_checkers": compiled_policy.required_checkers,
                "warning_checkers": compiled_policy.warning_checkers,
                "blocking_severities": compiled_policy.blocking_severities,
                "agent_name": POST_SUBMIT_CHECKER_POLICY_DERIVATION_AGENT_NAME,
                "agent_version": POST_SUBMIT_CHECKER_POLICY_DERIVATION_AGENT_VERSION,
                "reason_count": len(result.reasons),
                "reasons": safe_reasons,
                "setup_note_count": len(result.setup_notes),
            }
        )

        guide = await self._lock_project_guide_for_setup(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can derive post-submit checker policies")
        snapshot = await self._get_snapshot_for_guide(project_id, guide, source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        effective_policy = await self._repo.get_effective_submission_artifact_policy_by_id(
            effective_policy_id
        )
        if (
            effective_policy is None
            or effective_policy.project_id != project_id
            or effective_policy.guide_id != guide.id
            or effective_policy.guide_version != guide.version
            or effective_policy.source_snapshot_id != snapshot.id
            or effective_policy.source_snapshot_hash != snapshot.bundle_hash
            or effective_policy.lifecycle_status != "approved"
        ):
            raise StaleProjectSetupContinuation(
                "effective project submission artifact policy changed during post-submit derivation"
            )
        pre_submit_checker_policy = await self._repo.get_pre_submit_checker_policy(
            pre_submit_checker_policy_id
        )
        if (
            pre_submit_checker_policy is None
            or pre_submit_checker_policy.project_id != project_id
            or pre_submit_checker_policy.guide_id != guide.id
            or pre_submit_checker_policy.guide_version != guide.version
            or pre_submit_checker_policy.source_snapshot_id != snapshot.id
            or pre_submit_checker_policy.source_snapshot_hash != snapshot.bundle_hash
            or pre_submit_checker_policy.effective_policy_id != effective_policy.id
            or pre_submit_checker_policy.effective_policy_hash
            != effective_policy.effective_policy_hash
            or pre_submit_checker_policy.lifecycle_status != "compiled"
            or not pre_submit_checker_policy.compiled_bundle_hash
        ):
            raise StaleProjectSetupContinuation(
                "compiled project pre-submit checker policy changed during post-submit derivation"
            )
        setup_run = await self._repo.lock_project_setup_run(setup_run_id)
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        await self._validate_post_submit_continuation_payload(
            setup_run,
            project_id=project_id,
            guide_id=guide.id,
            source_snapshot_id=snapshot.id,
            effective_policy_id=effective_policy.id,
            pre_submit_checker_policy_id=pre_submit_checker_policy.id,
        )
        policy = PostSubmitCheckerPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            effective_policy_id=effective_policy.id,
            effective_policy_hash=effective_policy.effective_policy_hash,
            pre_submit_checker_policy_id=pre_submit_checker_policy.id,
            pre_submit_checker_bundle_hash=pre_submit_checker_policy.compiled_bundle_hash,
            required_checkers=compiled_policy.required_checkers,
            warning_checkers=compiled_policy.warning_checkers,
            blocking_severities=compiled_policy.blocking_severities,
            policy_hash=compiled_policy.policy_hash,
            policy_body=compiled_policy.policy_body,
            lifecycle_status="compiled",
            supersedes_policy_id=superseded_policy_id,
            created_by=actor.actor_id,
        )
        try:
            policy = await self._repo.upsert_post_submit_checker_policy(policy)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._repo.get_post_submit_checker_policy(project_id, guide.version)
            if (
                existing is not None
                and existing.required_checkers == compiled_policy.required_checkers
                and existing.warning_checkers == compiled_policy.warning_checkers
                and existing.blocking_severities == compiled_policy.blocking_severities
                and existing.policy_hash == compiled_policy.policy_hash
                and existing.policy_body == compiled_policy.policy_body
                and existing.guide_id == guide.id
                and existing.source_snapshot_id == snapshot.id
                and existing.source_snapshot_hash == snapshot.bundle_hash
                and existing.effective_policy_id == effective_policy.id
                and existing.effective_policy_hash == effective_policy.effective_policy_hash
                and existing.pre_submit_checker_policy_id == pre_submit_checker_policy.id
                and existing.pre_submit_checker_bundle_hash
                == pre_submit_checker_policy.compiled_bundle_hash
            ):
                return PostSubmitCheckerPolicyResponse.model_validate(existing), False, summary
            raise PolicySetupConflict(
                "post-submit checker policy conflicted with concurrent setup; retry"
            ) from exc
        except ProjectRepositoryIntegrityError as exc:
            await self._session.rollback()
            raise PolicySetupConflict(
                "post-submit checker policy content already exists for this guide version"
            ) from exc
        await self._session.refresh(policy)
        return PostSubmitCheckerPolicyResponse.model_validate(policy), True, summary

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
            if policy.derivation_source == AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
                raise PolicyEditBlocked(
                    "agent-derived policy bodies are immutable; create a manual policy to adjust"
                )
            policy_body = self._canonical_policy_body(payload.policy_body.model_dump(mode="json"))
            self._merge_effective_submission_artifact_policy(policy_body)
            policy.policy_body = policy_body
            policy.policy_hash = self._hash_canonical_json(policy_body)
        if payload.change_summary is not None:
            if policy.derivation_source == AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
                raise PolicyEditBlocked(
                    "agent-derived policy summaries are immutable; create a manual policy to adjust"
                )
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
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        if policy.source_snapshot_hash != snapshot.bundle_hash:
            raise PolicySetupBlocked(
                "submission artifact policy is bound to a stale source snapshot"
            )
        if self._hash_canonical_json(policy.policy_body) != policy.policy_hash:
            raise PolicySetupBlocked("submission artifact policy body hash mismatch")
        if policy.derivation_source == AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
            self._validate_agent_derived_submission_artifact_policy(policy, snapshot)
            sufficiency_report = await self._repo.get_sufficiency_report_for_snapshot(snapshot.id)
        else:
            sufficiency_report = await self._repo.get_diagnostic_sufficiency_report_for_snapshot(
                snapshot.id
            )
        self._validate_sufficiency_report_allows_policy_approval(
            sufficiency_report,
            snapshot,
        )
        if policy.derivation_source == AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
            await self._validate_agent_sufficiency_report_for_derivation(sufficiency_report)

        effective_policy = self._merge_effective_submission_artifact_policy(policy.policy_body)
        effective_policy_hash = self._hash_canonical_json(effective_policy)
        try:
            compiled_pre_submit_checker = compile_effective_project_submission_artifact_policy(
                effective_policy,
                effective_policy_hash,
            )
        except PreSubmitCheckerCompilerError as exc:
            raise PolicySetupBlocked("project pre-submit checker compilation failed") from exc
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
        if (
            payload.approval_note
            and policy.derivation_source != AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE
        ):
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
        existing_post_submit_policy = await self._repo.get_post_submit_checker_policy(
            project_id,
            guide.version,
        )
        if existing_post_submit_policy is not None:
            if existing_post_submit_policy.lifecycle_status == "approved":
                raise PolicySetupConflict(
                    "approved post-submit checker policy must be superseded through the approval workflow"
                )
            self._supersede_post_submit_checker_policy(
                existing_post_submit_policy,
                actor,
                supersession_kind="upstream_policy_changed",
                supersession_reason="effective project submission artifact policy changed",
                superseded_at=now,
            )
        setup_run_to_resume: ProjectSetupRun | None = None
        if get_settings().project_setup_pipeline_autostart:
            setup_run = await self._repo.get_latest_project_setup_run(project_id, guide.id)
            if setup_run is not None and setup_run.source_snapshot_id == snapshot.id:
                setup_run.output_submission_artifact_policy_id = policy.id
                setup_run.status = "policy_draft_ready"
                setup_run.current_step = "submission_artifact_policy_derivation"
                setup_run.output_post_submit_checker_policy_id = None
                setup_run.post_submit_derivation_summary = None
                setup_run.error_code = None
                setup_run.error_summary = None
                setup_run.finished_at = None
                setup_run_to_resume = setup_run

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
                lifecycle_status="compiled",
                compiler_version=compiled_pre_submit_checker.compiler_version,
                compiled_bundle=compiled_pre_submit_checker.compiled_bundle,
                compiled_bundle_hash=compiled_pre_submit_checker.compiled_bundle_hash,
                checker_names=compiled_pre_submit_checker.checker_names,
                checker_configs=compiled_pre_submit_checker.checker_configs,
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
        await self._session.refresh(effective)
        await self._session.refresh(pre_submit_checker_policy)
        if setup_run_to_resume is not None:
            await self._enqueue_post_submit_setup_continuation_after_commit(
                project_id=project_id,
                guide_id=guide.id,
                source_snapshot_id=snapshot.id,
                setup_run_id=setup_run_to_resume.id,
                effective_policy_id=effective.id,
                pre_submit_checker_policy_id=pre_submit_checker_policy.id,
            )
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

        post_submit_checker_policy = await self._repo.get_post_submit_checker_policy(
            project_id,
            guide.version,
        )
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
        await self.validate_source_snapshot_integrity(source_snapshot, GuideActivationBlocked)
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
        self.validate_activation_ready(
            guide,
            source_snapshot,
            sufficiency_report,
            submission_artifact_policy,
            effective_policy,
            pre_submit_checker_policy,
            post_submit_checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )
        try:
            await self._require_verified_report_sources(sufficiency_report)
        except PolicySetupBlocked as exc:
            raise GuideActivationBlocked(str(exc)) from exc
        setup_run = await self._repo.get_latest_project_setup_run(project_id, guide.id)
        if (
            setup_run is None
            or setup_run.source_snapshot_id != source_snapshot.id
            or setup_run.output_submission_artifact_policy_id != submission_artifact_policy.id
            or setup_run.status != "post_submit_policy_compiled"
            or setup_run.output_post_submit_checker_policy_id != post_submit_checker_policy.id
        ):
            raise GuideActivationBlocked(
                "compiled post-submit checker policy setup output is required"
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
        await self._session.refresh(post_submit_checker_policy)
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
            post_submit_checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )

    async def active_guide_read_response(
        self,
        guide: ProjectGuide,
        source_snapshot: GuideSourceSnapshot,
        source_items: tuple[GuideSourceSnapshotItem, ...],
        sufficiency_report: GuideSufficiencyReport,
        submission_artifact_policy: SubmissionArtifactPolicy,
        effective_policy: EffectiveProjectSubmissionArtifactPolicy,
        pre_submit_checker_policy: PreSubmitCheckerPolicy,
        post_submit_checker_policy: PostSubmitCheckerPolicy,
        review_policy: ReviewPolicy,
        revision_policy: RevisionPolicy,
    ) -> ActiveGuideReadResponse:
        """Shape the authorized active-guide projection without compensation data."""
        source_snapshot_response = GuideSourceSnapshotResponse.model_validate(source_snapshot)
        source_snapshot_response.items = [
            GuideSourceSnapshotItemResponse.model_validate(item) for item in source_items
        ]
        return ActiveGuideReadResponse(
            guide_source_snapshot=source_snapshot_response,
            **self._active_bundle_response_fields(
                guide,
                sufficiency_report,
                submission_artifact_policy,
                effective_policy,
                pre_submit_checker_policy,
                post_submit_checker_policy,
                review_policy,
                revision_policy,
            ),
        )

    def _active_bundle_response_fields(
        self,
        guide: ProjectGuide,
        sufficiency_report: GuideSufficiencyReport,
        submission_artifact_policy: SubmissionArtifactPolicy,
        effective_policy: EffectiveProjectSubmissionArtifactPolicy,
        pre_submit_checker_policy: PreSubmitCheckerPolicy,
        post_submit_checker_policy: PostSubmitCheckerPolicy,
        review_policy: ReviewPolicy,
        revision_policy: RevisionPolicy,
    ) -> dict[str, Any]:
        """Shape fields shared by activation and administrative read responses."""
        return {
            "guide": ProjectGuideResponse.model_validate(guide),
            "guide_sufficiency_report": GuideSufficiencyReportResponse.model_validate(
                sufficiency_report
            ),
            "submission_artifact_policy": SubmissionArtifactPolicyResponse.model_validate(
                submission_artifact_policy
            ),
            "effective_submission_artifact_policy": (
                EffectiveProjectSubmissionArtifactPolicyResponse.model_validate(effective_policy)
            ),
            "pre_submit_checker_policy": (
                ActiveGuidePreSubmitCheckerPolicyResponse.model_validate(pre_submit_checker_policy)
            ),
            "post_submit_checker_policy": PostSubmitCheckerPolicyResponse.model_validate(
                post_submit_checker_policy
            ),
            "review_policy": ReviewPolicyResponse.model_validate(review_policy),
            "revision_policy": RevisionPolicyResponse.model_validate(revision_policy),
        }

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

    async def _enqueue_post_submit_setup_continuation_after_commit(
        self,
        *,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        setup_run_id: str,
        effective_policy_id: str,
        pre_submit_checker_policy_id: str,
    ) -> str | None:
        """Enqueue post-submit setup continuation after pre-submit compile.

        The approval transaction has already committed when this runs. Broker
        failure must be represented on the setup run instead of undoing the
        approved policy bundle.
        """
        try:
            task_id = await asyncio.to_thread(
                enqueue_post_submit_setup_continuation,
                project_id=project_id,
                guide_id=guide_id,
                source_snapshot_id=source_snapshot_id,
                setup_run_id=setup_run_id,
                effective_policy_id=effective_policy_id,
                pre_submit_checker_policy_id=pre_submit_checker_policy_id,
            )
        except ProjectSetupQueueError as exc:
            safe_summary = self._safe_project_setup_error_summary(str(exc))
            logger.warning(
                "project setup post-submit continuation enqueue failed after commit",
                extra={
                    "project_id": project_id,
                    "guide_id": guide_id,
                    "source_snapshot_id": source_snapshot_id,
                    "setup_run_id": setup_run_id,
                    "error_code": exc.__class__.__name__,
                    "error_summary": safe_summary,
                },
            )
            await self.update_project_setup_run_status(
                setup_run_id,
                status="enqueue_failed",
                current_step="post_submit_checker_policy_enqueue",
                error_code=exc.__class__.__name__,
                error_summary=safe_summary,
                continuation_effective_policy_id=effective_policy_id,
                continuation_pre_submit_checker_policy_id=pre_submit_checker_policy_id,
            )
            return None
        await self.update_project_setup_run_task_id(
            setup_run_id,
            task_id=task_id,
            continuation_effective_policy_id=effective_policy_id,
            continuation_pre_submit_checker_policy_id=pre_submit_checker_policy_id,
        )
        return task_id

    async def update_project_setup_run_task_id(
        self,
        setup_run_id: str,
        *,
        task_id: str,
        continuation_effective_policy_id: str,
        continuation_pre_submit_checker_policy_id: str,
    ) -> ProjectSetupRunResponse:
        """Record a queued continuation task id only for the current payload."""
        setup_run = await self._repo.lock_project_setup_run(setup_run_id)
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        await self._validate_post_submit_continuation_payload(
            setup_run,
            project_id=setup_run.project_id,
            guide_id=setup_run.guide_id,
            source_snapshot_id=setup_run.source_snapshot_id,
            effective_policy_id=continuation_effective_policy_id,
            pre_submit_checker_policy_id=continuation_pre_submit_checker_policy_id,
        )
        if setup_run.status == "post_submit_policy_compiled":
            return ProjectSetupRunResponse.model_validate(setup_run)
        setup_run.celery_task_id = task_id
        await self._session.commit()
        await self._session.refresh(setup_run)
        return ProjectSetupRunResponse.model_validate(setup_run)

    async def update_project_setup_run_status(
        self,
        setup_run_id: str,
        *,
        status: str,
        current_step: str,
        output_sufficiency_report_id: str | None = None,
        output_submission_artifact_policy_id: str | None = None,
        output_post_submit_checker_policy_id: str | None = None,
        post_submit_derivation_summary: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_artifact_incident_id: str | None = None,
        error_summary: str | None = None,
        continuation_effective_policy_id: str | None = None,
        continuation_pre_submit_checker_policy_id: str | None = None,
    ) -> ProjectSetupRunResponse:
        """Update the setup-run ledger from the internal project setup worker."""
        uses_continuation_payload = (
            continuation_effective_policy_id is not None
            or continuation_pre_submit_checker_policy_id is not None
        )
        if uses_continuation_payload and (
            continuation_effective_policy_id is None
            or continuation_pre_submit_checker_policy_id is None
        ):
            raise PolicySetupConflict("incomplete post-submit continuation payload")
        setup_run = (
            await self._repo.lock_project_setup_run(setup_run_id)
            if uses_continuation_payload
            else await self._repo.get_project_setup_run(setup_run_id)
        )
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        if status == "running_sufficiency_agent" and setup_run.status not in {
            "queued",
            "dispatch_pending",
            "running_sufficiency_agent",
        }:
            return ProjectSetupRunResponse.model_validate(setup_run)
        if uses_continuation_payload:
            assert continuation_effective_policy_id is not None
            assert continuation_pre_submit_checker_policy_id is not None
            await self._validate_post_submit_continuation_payload(
                setup_run,
                project_id=setup_run.project_id,
                guide_id=setup_run.guide_id,
                source_snapshot_id=setup_run.source_snapshot_id,
                effective_policy_id=continuation_effective_policy_id,
                pre_submit_checker_policy_id=continuation_pre_submit_checker_policy_id,
            )
            if output_post_submit_checker_policy_id is not None:
                await self._validate_post_submit_policy_matches_continuation_payload(
                    setup_run,
                    output_post_submit_checker_policy_id=output_post_submit_checker_policy_id,
                    effective_policy_id=continuation_effective_policy_id,
                    pre_submit_checker_policy_id=continuation_pre_submit_checker_policy_id,
                )
            elif (
                setup_run.status == "post_submit_policy_compiled"
                and setup_run.output_post_submit_checker_policy_id is not None
                and status in {"post_submit_setup_blocked", "failed", "enqueue_failed"}
            ):
                return ProjectSetupRunResponse.model_validate(setup_run)
        await self._validate_project_setup_run_outputs(
            setup_run,
            output_sufficiency_report_id=output_sufficiency_report_id,
            output_submission_artifact_policy_id=output_submission_artifact_policy_id,
            output_post_submit_checker_policy_id=output_post_submit_checker_policy_id,
        )
        now = datetime.now(UTC)
        setup_run.status = status
        setup_run.current_step = current_step
        if setup_run.started_at is None and status != "queued":
            setup_run.started_at = now
        if status in PROJECT_SETUP_TERMINAL_STATUSES:
            setup_run.finished_at = now
        else:
            setup_run.finished_at = None
        if output_sufficiency_report_id is not None:
            setup_run.output_sufficiency_report_id = output_sufficiency_report_id
        if output_submission_artifact_policy_id is not None:
            setup_run.output_submission_artifact_policy_id = output_submission_artifact_policy_id
        if output_post_submit_checker_policy_id is not None:
            setup_run.output_post_submit_checker_policy_id = output_post_submit_checker_policy_id
        if post_submit_derivation_summary is not None:
            setup_run.post_submit_derivation_summary = self._safe_post_submit_derivation_summary(
                post_submit_derivation_summary
            )
        setup_run.error_code = error_code
        setup_run.error_artifact_incident_id = error_artifact_incident_id
        setup_run.error_summary = (
            self._safe_project_setup_error_summary(error_summary)
            if error_summary is not None
            else None
        )
        await self._session.commit()
        await self._session.refresh(setup_run)
        return ProjectSetupRunResponse.model_validate(setup_run)

    async def validate_project_setup_run_context(
        self,
        setup_run_id: str,
        *,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        setup_generation: int | None = None,
        celery_task_id: str | None = None,
    ) -> ProjectSetupRunResponse:
        """Validate that a worker payload matches the setup-run ledger row."""
        setup_run = await self._repo.get_project_setup_run(setup_run_id)
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        if (
            setup_run.project_id != project_id
            or setup_run.guide_id != guide_id
            or setup_run.source_snapshot_id != source_snapshot_id
            or (setup_generation is not None and setup_run.setup_generation != setup_generation)
            or setup_run.status not in {"queued", "running_sufficiency_agent"}
            or setup_run.current_step not in {"queued", "guide_sufficiency"}
            or (celery_task_id is not None and setup_run.celery_task_id != celery_task_id)
        ):
            raise PolicySetupConflict("project setup run context mismatch")
        return ProjectSetupRunResponse.model_validate(setup_run)

    async def validate_post_submit_continuation_payload(
        self,
        setup_run_id: str,
        *,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        effective_policy_id: str,
        pre_submit_checker_policy_id: str,
    ) -> None:
        """Validate a post-submit continuation payload against current setup state."""
        setup_run = await self._repo.get_project_setup_run(setup_run_id)
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        await self._validate_post_submit_continuation_payload(
            setup_run,
            project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=source_snapshot_id,
            effective_policy_id=effective_policy_id,
            pre_submit_checker_policy_id=pre_submit_checker_policy_id,
        )

    async def start_post_submit_setup_continuation(
        self,
        setup_run_id: str,
        *,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        effective_policy_id: str,
        pre_submit_checker_policy_id: str,
    ) -> str:
        """Move a setup run into post-submit derivation or return idempotent state."""
        setup_run = await self._repo.lock_project_setup_run(setup_run_id)
        if setup_run is None:
            raise ProjectSetupRunNotFound("project setup run not found")
        await self._validate_post_submit_continuation_payload(
            setup_run,
            project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=source_snapshot_id,
            effective_policy_id=effective_policy_id,
            pre_submit_checker_policy_id=pre_submit_checker_policy_id,
        )
        if setup_run.status == "post_submit_policy_compiled":
            return "already_compiled"
        if setup_run.status not in {
            "policy_draft_ready",
            "enqueue_failed",
            "running_post_submit_derivation_agent",
            "post_submit_setup_blocked",
        }:
            raise PolicySetupConflict("project setup run is not ready for post-submit derivation")
        now = datetime.now(UTC)
        setup_run.status = "running_post_submit_derivation_agent"
        setup_run.current_step = "post_submit_checker_policy_derivation"
        setup_run.started_at = setup_run.started_at or now
        setup_run.finished_at = None
        setup_run.error_code = None
        setup_run.error_summary = None
        await self._session.commit()
        return "started"

    async def _validate_post_submit_continuation_payload(
        self,
        setup_run: ProjectSetupRun,
        *,
        project_id: str,
        guide_id: str,
        source_snapshot_id: str,
        effective_policy_id: str,
        pre_submit_checker_policy_id: str,
    ) -> None:
        """Reject stale continuation payloads before they can update setup state."""
        if (
            setup_run.project_id != project_id
            or setup_run.guide_id != guide_id
            or setup_run.source_snapshot_id != source_snapshot_id
        ):
            raise PolicySetupConflict("project setup run context mismatch")
        if setup_run.output_submission_artifact_policy_id is None:
            raise PolicySetupConflict(
                "project setup run has no approved submission artifact policy"
            )

        effective_policy = await self._repo.get_effective_submission_artifact_policy_by_id(
            effective_policy_id
        )
        if (
            effective_policy is None
            or effective_policy.project_id != setup_run.project_id
            or effective_policy.guide_id != setup_run.guide_id
            or effective_policy.guide_version != setup_run.guide_version
            or effective_policy.source_snapshot_id != setup_run.source_snapshot_id
            or effective_policy.source_snapshot_hash != setup_run.source_snapshot_hash
            or effective_policy.submission_artifact_policy_id
            != setup_run.output_submission_artifact_policy_id
            or effective_policy.lifecycle_status != "approved"
        ):
            raise StaleProjectSetupContinuation(
                "post-submit continuation payload no longer matches setup state"
            )

        pre_submit_checker_policy = await self._repo.get_pre_submit_checker_policy(
            pre_submit_checker_policy_id
        )
        if (
            pre_submit_checker_policy is None
            or pre_submit_checker_policy.project_id != setup_run.project_id
            or pre_submit_checker_policy.guide_id != setup_run.guide_id
            or pre_submit_checker_policy.guide_version != setup_run.guide_version
            or pre_submit_checker_policy.source_snapshot_id != setup_run.source_snapshot_id
            or pre_submit_checker_policy.source_snapshot_hash != setup_run.source_snapshot_hash
            or pre_submit_checker_policy.effective_policy_id != effective_policy.id
            or pre_submit_checker_policy.effective_policy_hash
            != effective_policy.effective_policy_hash
            or pre_submit_checker_policy.lifecycle_status != "compiled"
            or not pre_submit_checker_policy.compiled_bundle_hash
        ):
            raise StaleProjectSetupContinuation(
                "post-submit continuation payload no longer matches setup state"
            )

        if setup_run.output_post_submit_checker_policy_id is None:
            return
        post_submit_checker_policy = await self._repo.get_post_submit_checker_policy_by_id(
            setup_run.output_post_submit_checker_policy_id
        )
        if (
            post_submit_checker_policy is None
            or post_submit_checker_policy.project_id != setup_run.project_id
            or post_submit_checker_policy.guide_id != setup_run.guide_id
            or post_submit_checker_policy.guide_version != setup_run.guide_version
            or post_submit_checker_policy.source_snapshot_id != setup_run.source_snapshot_id
            or post_submit_checker_policy.source_snapshot_hash != setup_run.source_snapshot_hash
            or post_submit_checker_policy.effective_policy_id != effective_policy.id
            or post_submit_checker_policy.effective_policy_hash
            != effective_policy.effective_policy_hash
            or post_submit_checker_policy.pre_submit_checker_policy_id
            != pre_submit_checker_policy.id
            or post_submit_checker_policy.pre_submit_checker_bundle_hash
            != pre_submit_checker_policy.compiled_bundle_hash
        ):
            raise StaleProjectSetupContinuation(
                "post-submit continuation payload no longer matches setup state"
            )

    async def _validate_post_submit_policy_matches_continuation_payload(
        self,
        setup_run: ProjectSetupRun,
        *,
        output_post_submit_checker_policy_id: str,
        effective_policy_id: str,
        pre_submit_checker_policy_id: str,
    ) -> None:
        """Require terminal post-submit output to match the worker payload exactly."""
        post_submit_checker_policy = await self._repo.get_post_submit_checker_policy_by_id(
            output_post_submit_checker_policy_id
        )
        if (
            post_submit_checker_policy is None
            or post_submit_checker_policy.project_id != setup_run.project_id
            or post_submit_checker_policy.guide_id != setup_run.guide_id
            or post_submit_checker_policy.guide_version != setup_run.guide_version
            or post_submit_checker_policy.source_snapshot_id != setup_run.source_snapshot_id
            or post_submit_checker_policy.source_snapshot_hash != setup_run.source_snapshot_hash
            or post_submit_checker_policy.effective_policy_id != effective_policy_id
            or post_submit_checker_policy.pre_submit_checker_policy_id
            != pre_submit_checker_policy_id
        ):
            raise StaleProjectSetupContinuation(
                "post-submit continuation payload no longer matches setup state"
            )

    async def _validate_project_setup_run_outputs(
        self,
        setup_run: ProjectSetupRun,
        *,
        output_sufficiency_report_id: str | None,
        output_submission_artifact_policy_id: str | None,
        output_post_submit_checker_policy_id: str | None,
    ) -> None:
        """Require setup-run output ids to belong to the same setup context."""
        if output_sufficiency_report_id is not None:
            report = await self._repo.get_guide_sufficiency_report(output_sufficiency_report_id)
            if report is None or not self._is_project_setup_run_output_match(setup_run, report):
                raise PolicySetupConflict("project setup run sufficiency output mismatch")
        if output_submission_artifact_policy_id is not None:
            policy = await self._repo.get_submission_artifact_policy(
                output_submission_artifact_policy_id
            )
            if policy is None or not self._is_project_setup_run_output_match(setup_run, policy):
                raise PolicySetupConflict("project setup run policy output mismatch")
        if output_post_submit_checker_policy_id is not None:
            post_submit_policy = await self._repo.get_post_submit_checker_policy_by_id(
                output_post_submit_checker_policy_id
            )
            if post_submit_policy is None or not self._is_project_setup_run_output_match(
                setup_run,
                post_submit_policy,
            ):
                raise PolicySetupConflict("project setup run post-submit policy output mismatch")

    async def _post_submit_policy_from_setup_run(
        self,
        setup_run: ProjectSetupRun,
    ) -> PostSubmitCheckerPolicy | None:
        """Load the generated post-submit policy referenced by a setup run."""
        if setup_run.output_post_submit_checker_policy_id is None:
            return None
        policy = await self._repo.get_post_submit_checker_policy_by_id(
            setup_run.output_post_submit_checker_policy_id
        )
        if policy is None or not self._is_project_setup_run_output_match(setup_run, policy):
            raise PolicySetupConflict("project setup run post-submit policy output mismatch")
        return policy

    async def _validate_current_post_submit_policy_setup(
        self,
        guide: ProjectGuide,
        setup_run: ProjectSetupRun,
        policy: PostSubmitCheckerPolicy,
    ) -> None:
        """Require a generated post-submit policy to match current guide setup."""
        if (
            setup_run.project_id != guide.project_id
            or setup_run.guide_id != guide.id
            or setup_run.guide_version != guide.version
            or setup_run.output_post_submit_checker_policy_id != policy.id
        ):
            raise PolicySetupConflict("project setup run context mismatch")
        snapshot = await self._get_snapshot_for_guide(
            setup_run.project_id,
            guide,
            setup_run.source_snapshot_id,
        )
        await self._ensure_snapshot_is_latest(setup_run.project_id, guide, snapshot)
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        if setup_run.source_snapshot_hash != snapshot.bundle_hash:
            raise PolicySetupBlocked("project setup run snapshot hash mismatch")
        await self._validate_post_submit_continuation_payload(
            setup_run,
            project_id=setup_run.project_id,
            guide_id=setup_run.guide_id,
            source_snapshot_id=setup_run.source_snapshot_id,
            effective_policy_id=policy.effective_policy_id,
            pre_submit_checker_policy_id=policy.pre_submit_checker_policy_id,
        )
        try:
            parsed_policy = parse_locked_post_submit_checker_policy_body(
                policy.policy_body,
                project_id=policy.project_id,
                guide_version=policy.guide_version,
                policy_hash=policy.policy_hash or "",
            )
        except ValueError as exc:
            raise PolicySetupBlocked("post-submit checker policy hash is invalid") from exc
        if (
            parsed_policy.required_checkers != policy.required_checkers
            or parsed_policy.warning_checkers != policy.warning_checkers
            or parsed_policy.blocking_severities != policy.blocking_severities
        ):
            raise PolicySetupBlocked("post-submit checker policy hash is invalid")

    async def _post_submit_policy_setup_response(
        self,
        setup_run: ProjectSetupRun,
        policy: PostSubmitCheckerPolicy | None,
    ) -> PostSubmitCheckerPolicySetupResponse:
        """Build an operator-visible setup response without source-hash leakage."""
        policy_summary = None
        if policy is not None:
            policy_summary = PostSubmitCheckerPolicySetupSummaryResponse(
                id=policy.id,
                project_id=policy.project_id,
                guide_id=policy.guide_id,
                guide_version=policy.guide_version,
                source_snapshot_id=policy.source_snapshot_id,
                effective_policy_id=policy.effective_policy_id,
                effective_policy_hash=policy.effective_policy_hash,
                pre_submit_checker_policy_id=policy.pre_submit_checker_policy_id,
                pre_submit_checker_bundle_hash=policy.pre_submit_checker_bundle_hash,
                required_checkers=policy.required_checkers,
                warning_checkers=policy.warning_checkers,
                blocking_severities=policy.blocking_severities,
                policy_hash=policy.policy_hash,
                lifecycle_status=policy.lifecycle_status,
                approved_by_role=policy.approved_by_role,
                approved_by_actor=policy.approved_by_actor,
                approved_at=policy.approved_at,
                created_by=policy.created_by,
                created_at=policy.created_at,
            )
        return PostSubmitCheckerPolicySetupResponse(
            project_id=setup_run.project_id,
            guide_id=setup_run.guide_id,
            guide_version=setup_run.guide_version,
            setup_run=ProjectSetupRunResponse.model_validate(setup_run),
            post_submit_checker_policy=policy_summary,
            derivation_input_summary=await self._post_submit_derivation_input_summary(
                setup_run, policy
            ),
            correction_history=await self._post_submit_policy_correction_history(setup_run),
        )

    async def post_submit_policy_setup_response(
        self,
        setup_run: ProjectSetupRun,
        policy: PostSubmitCheckerPolicy | None,
    ) -> PostSubmitCheckerPolicySetupResponse:
        """Project one already-authorized and transaction-locked setup result."""
        return await self._post_submit_policy_setup_response(setup_run, policy)

    async def _post_submit_policy_correction_history(
        self,
        setup_run: ProjectSetupRun,
    ) -> list[PostSubmitCheckerPolicyCorrectionSummaryResponse]:
        """Return bounded append-only correction provenance for setup operators."""
        effective_policy = await self._repo.get_effective_submission_artifact_policy(
            setup_run.project_id,
            setup_run.guide_version,
            setup_run.source_snapshot_id,
        )
        if effective_policy is None:
            return []
        pre_submit_policy = await self._repo.get_pre_submit_checker_policy_for_effective_policy(
            effective_policy.id
        )
        if (
            pre_submit_policy is None
            or pre_submit_policy.compiled_bundle_hash is None
            or effective_policy.source_snapshot_hash != setup_run.source_snapshot_hash
            or pre_submit_policy.source_snapshot_id != setup_run.source_snapshot_id
            or pre_submit_policy.source_snapshot_hash != setup_run.source_snapshot_hash
        ):
            return []
        policies = await self._repo.list_superseded_post_submit_checker_policies(
            setup_run.project_id,
            setup_run.guide_id,
            setup_run.guide_version,
            setup_run.source_snapshot_id,
            setup_run.source_snapshot_hash,
            effective_policy.id,
            effective_policy.effective_policy_hash,
            pre_submit_policy.id,
            pre_submit_policy.compiled_bundle_hash,
        )
        history: list[PostSubmitCheckerPolicyCorrectionSummaryResponse] = []
        for policy in policies[:100]:
            if (
                policy.supersession_reason is None
                or policy.superseded_by_role is None
                or policy.superseded_by_actor is None
                or policy.superseded_at is None
            ):
                raise PolicySetupConflict("post-submit policy correction provenance is incomplete")
            history.append(
                PostSubmitCheckerPolicyCorrectionSummaryResponse(
                    policy_id=policy.id,
                    policy_hash=policy.policy_hash,
                    required_checkers=policy.required_checkers,
                    warning_checkers=policy.warning_checkers,
                    blocking_severities=policy.blocking_severities,
                    correction_reason=policy.supersession_reason,
                    correction_requested_by_role=policy.superseded_by_role,
                    correction_requested_by_actor=policy.superseded_by_actor,
                    correction_requested_at=policy.superseded_at,
                )
            )
        return history

    async def _post_submit_derivation_input_summary(
        self,
        setup_run: ProjectSetupRun,
        policy: PostSubmitCheckerPolicy | None,
    ) -> dict[str, Any]:
        """Return bounded setup inputs used by post-submit policy derivation."""
        summary: dict[str, Any] = {
            "source_snapshot_id": setup_run.source_snapshot_id,
            "source_snapshot_hash_redacted": True,
            "sufficiency_status": None,
            "sufficiency_finding_count": None,
            "effective_policy_id": None,
            "effective_policy_hash": None,
            "effective_policy_required_artifact_count": None,
            "effective_policy_required_evidence_count": None,
            "effective_policy_forbidden_artifact_count": None,
            "pre_submit_checker_policy_id": None,
            "pre_submit_checker_bundle_hash": None,
            "pre_submit_checker_count": None,
            "pre_submit_checker_names": [],
            "registered_post_submit_checker_count": len(default_checker_registry().names()),
        }
        if setup_run.output_sufficiency_report_id is not None:
            report = await self._repo.get_guide_sufficiency_report(
                setup_run.output_sufficiency_report_id
            )
            if report is not None and self._is_project_setup_run_output_match(setup_run, report):
                summary["sufficiency_status"] = report.status
                summary["sufficiency_finding_count"] = len(report.findings or [])
        if setup_run.output_submission_artifact_policy_id is not None:
            effective_policy = await self._repo.get_effective_submission_artifact_policy(
                setup_run.project_id,
                setup_run.guide_version,
                setup_run.source_snapshot_id,
            )
            if effective_policy is not None and self._is_project_setup_run_output_match(
                setup_run,
                effective_policy,
            ):
                effective_body = effective_policy.effective_policy or {}
                summary["effective_policy_id"] = effective_policy.id
                summary["effective_policy_hash"] = effective_policy.effective_policy_hash
                summary["effective_policy_required_artifact_count"] = len(
                    effective_body.get("required_artifacts") or []
                )
                summary["effective_policy_required_evidence_count"] = len(
                    effective_body.get("required_evidence") or []
                )
                summary["effective_policy_forbidden_artifact_count"] = len(
                    effective_body.get("forbidden_artifacts") or []
                )
                pre_submit_policy = (
                    await self._repo.get_pre_submit_checker_policy_for_effective_policy(
                        effective_policy.id
                    )
                )
                if (
                    pre_submit_policy is not None
                    and pre_submit_policy.source_snapshot_id == setup_run.source_snapshot_id
                    and pre_submit_policy.source_snapshot_hash == setup_run.source_snapshot_hash
                ):
                    summary["pre_submit_checker_policy_id"] = pre_submit_policy.id
                    summary["pre_submit_checker_bundle_hash"] = (
                        pre_submit_policy.compiled_bundle_hash
                    )
                    summary["pre_submit_checker_names"] = pre_submit_policy.checker_names
                    summary["pre_submit_checker_count"] = len(pre_submit_policy.checker_names)
        if policy is not None:
            summary["effective_policy_id"] = policy.effective_policy_id
            summary["effective_policy_hash"] = policy.effective_policy_hash
            summary["pre_submit_checker_policy_id"] = policy.pre_submit_checker_policy_id
            summary["pre_submit_checker_bundle_hash"] = policy.pre_submit_checker_bundle_hash
        return summary

    def _is_project_setup_run_output_match(
        self,
        setup_run: ProjectSetupRun,
        output: GuideSufficiencyReport | SubmissionArtifactPolicy | PostSubmitCheckerPolicy,
    ) -> bool:
        """Return whether an output row belongs to the setup-run context."""
        if isinstance(output, PostSubmitCheckerPolicy):
            return (
                output.project_id == setup_run.project_id
                and output.guide_id == setup_run.guide_id
                and output.guide_version == setup_run.guide_version
                and output.source_snapshot_id == setup_run.source_snapshot_id
                and output.source_snapshot_hash == setup_run.source_snapshot_hash
            )
        return (
            output.project_id == setup_run.project_id
            and output.guide_id == setup_run.guide_id
            and output.guide_version == setup_run.guide_version
            and output.source_snapshot_id == setup_run.source_snapshot_id
            and output.source_snapshot_hash == setup_run.source_snapshot_hash
        )

    def _safe_project_setup_error_summary(self, summary: str) -> str:
        """Return a bounded setup error summary safe for API responses."""
        return safe_project_setup_error_summary(summary)

    def _safe_post_submit_derivation_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Return bounded post-submit derivation summary fields safe for APIs."""
        allowed_keys = {
            "status",
            "reason",
            "post_submit_checker_policy_id",
            "correction_requested_by_role",
            "correction_requested_by_actor",
            "correction_requested_at",
            "required_checkers",
            "warning_checkers",
            "blocking_severities",
            "unsupported_required_checks",
            "agent_name",
            "agent_version",
            "reason",
            "reason_count",
            "reasons",
            "setup_note_count",
        }
        safe_summary: dict[str, Any] = {}
        for key, value in summary.items():
            if key not in allowed_keys:
                continue
            safe_summary[key] = self._safe_summary_value(value)
        return safe_summary

    def _safe_summary_value(self, value: Any) -> Any:
        """Recursively redact API-visible setup summary values."""
        if isinstance(value, str):
            return self._safe_bounded_summary_value(value)
        if isinstance(value, list):
            return [self._safe_summary_value(item) for item in value[:100]]
        if isinstance(value, dict):
            safe_items: dict[str, Any] = {}
            for key, item in list(value.items())[:100]:
                safe_key = self._safe_bounded_summary_value(str(key))
                if safe_key == "redacted":
                    safe_key = "redacted_key"
                safe_items[safe_key[:100]] = self._safe_summary_value(item)
            return safe_items
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, int | float):
            return value
        return "redacted"

    def _safe_bounded_summary_value(self, value: str) -> str:
        """Redact unsafe summary values before storing API-visible setup summaries."""
        normalized = " ".join(value.split())[:500]
        if (
            SECRET_REF_PATTERN.search(normalized)
            or CREDENTIAL_SHAPE_PATTERN.search(normalized)
            or "/" in normalized
            or "\\" in normalized
            or HASH_TOKEN_PATTERN.search(normalized)
        ):
            return "redacted"
        return normalized

    def _safe_public_unsupported_requirement(self, value: str) -> str:
        """Return a safe operator-visible label for an unsupported requirement."""
        normalized = value.strip().lower()
        if not normalized.startswith("check_") or not SAFE_TOKEN_PATTERN.fullmatch(normalized):
            return "unsupported checker requirement"
        return normalized

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
        response.items = [GuideSourceSnapshotItemResponse.model_validate(item) for item in items]
        return response

    async def _verified_guide_source_material(
        self,
        guide: ProjectGuide,
        snapshot: GuideSourceSnapshot,
        report: GuideSufficiencyReport,
    ) -> GuideSourceMaterial:
        """Build agent material only from exact verified extraction provenance."""
        if (
            self._guide_sufficiency_material is None
            or report.project_setup_run_id is None
            or report.setup_generation is None
        ):
            raise PolicySetupBlocked("verified guide sufficiency is unavailable")
        loaded = await self._guide_sufficiency_material.load(
            GuideSufficiencyMaterialRequest(
                project_id=UUID(guide.project_id),
                guide_id=UUID(guide.id),
                guide_source_snapshot_id=UUID(snapshot.id),
                project_setup_run_id=UUID(report.project_setup_run_id),
                setup_generation=report.setup_generation,
            )
        )
        source_items = [self._verified_agent_item(item) for item in loaded.source_items]
        return GuideSourceMaterial(
            project_id=guide.project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            guide_material={
                field: getattr(guide, field) for field in sorted(GUIDE_SOURCE_MATERIAL_FIELDS)
            },
            verified_artifact_material=True,
            source_items=source_items,
            representative_task_material=RepresentativeTaskMaterialContext(items=[]),
        )

    @staticmethod
    def _verified_agent_item(item: Any) -> GuideSourceItemMaterial:
        """Project one canonical extraction row into bounded untrusted agent input."""
        return GuideSourceItemMaterial(
            source_kind=item.source_kind,
            ingestion_adapter=item.ingestion_adapter,
            media_type=item.media_type,
            source_item_id=str(item.source_item_id),
            item_order=item.item_order,
            binding_id=str(item.binding_id),
            artifact_content_id=str(item.content_id),
            artifact_sha256=item.artifact_sha256,
            artifact_byte_count=item.artifact_byte_count,
            classification_id=str(item.classification_id),
            detected_format=item.detected_format,
            extraction_attempt_id=str(item.extraction_attempt_id),
            extraction_usage_id=str(item.extraction_usage_id),
            extracted_content_id=str(item.extracted_content_id),
            extractor_name=item.extractor_name,
            extractor_version=item.extractor_version,
            extraction_policy_version=item.extraction_policy_version,
            canonical_output_sha256=item.canonical_output_sha256,
            omission_facts=item.omission_facts,
            canonical_content=item.canonical_content,
            structural_metadata=item.structural_metadata,
            untrusted_data=True,
            untrusted_data_label="UNTRUSTED_GUIDE_SOURCE_DATA",
        )

    async def validate_source_snapshot_integrity(
        self,
        snapshot: GuideSourceSnapshot,
        exception_type: type[ProjectServiceError],
        *,
        persisted_items: Sequence[GuideSourceSnapshotItem] | None = None,
    ) -> None:
        """Recompute and verify an immutable guide-source snapshot bundle.

        Args:
            snapshot: Snapshot whose manifest and bundle hash must match.
            exception_type: Domain error raised for invalid snapshot state.
            persisted_items: Already locked rows, or ``None`` to load canonical rows.

        Raises:
            ProjectServiceError: Through the caller-selected domain error type.
        """

        def fail() -> None:
            """Raise the caller-specific snapshot integrity error."""
            raise exception_type("guide source snapshot integrity check failed")

        manifest = snapshot.manifest_json
        if not isinstance(manifest, dict):
            fail()
        if snapshot.manifest_schema_version != GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION:
            fail()
        if set(manifest) != {"schema_version", "snapshot_id", "generation", "items"}:
            fail()
        if manifest.get("schema_version") != GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION:
            fail()
        if manifest.get("snapshot_id") != snapshot.id:
            fail()
        if manifest.get("generation") != snapshot.creation_generation:
            fail()
        manifest_items = manifest.get("items")
        if not isinstance(manifest_items, list) or not manifest_items:
            fail()
        if self._hash_canonical_json(manifest) != snapshot.bundle_hash:
            fail()

        if persisted_items is None:
            persisted_items = await self._repo.list_guide_source_snapshot_items(snapshot.id)
        if len(persisted_items) != len(manifest_items):
            fail()

        row_items: list[dict[str, Any]] = []
        seen_labels: set[tuple[str, str]] = set()
        required_fields = {
            "item_id",
            "item_order",
            "source_kind",
            "source_label",
            "ingestion_adapter",
            "media_type",
        }
        for index, item in enumerate(persisted_items):
            if item.item_order != index:
                fail()
            row_item = {
                "item_id": item.id,
                "item_order": item.item_order,
                "source_kind": item.source_kind,
                "source_label": item.source_label,
                "ingestion_adapter": item.ingestion_adapter,
                "media_type": item.media_type,
            }
            label_key = (item.source_kind, item.source_label)
            if label_key in seen_labels:
                fail()
            seen_labels.add(label_key)
            row_items.append(row_item)

        for manifest_item in manifest_items:
            if not isinstance(manifest_item, dict):
                fail()
            if set(manifest_item) != required_fields:
                fail()
            if not isinstance(manifest_item["item_id"], str):
                fail()
            if not isinstance(manifest_item["item_order"], int):
                fail()
            if not isinstance(manifest_item["source_kind"], str):
                fail()
            if not isinstance(manifest_item["source_label"], str):
                fail()
            if not isinstance(manifest_item["ingestion_adapter"], str):
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
                    _guide_source_label(manifest_item["source_label"])
                    != manifest_item["source_label"]
                ):
                    fail()
            except ProjectServiceError:
                fail()

        if manifest_items != row_items:
            fail()

    def _safe_source_token(self, value: str, label: str) -> str:
        """Validate a source token field used in durable policy records."""
        return _guide_source_token(value, label)

    def _require_sha256_hash(self, value: str, label: str) -> None:
        """Validate platform hash shape."""
        if not HASH_PATTERN.fullmatch(value):
            raise PolicySetupBlocked(f"{label} must be sha256:<64 lowercase hex>")

    def _hash_canonical_json(self, value: dict[str, Any]) -> str:
        """Hash canonical JSON using the Workstream policy hash contract."""
        try:
            return canonical_json_hash(value)
        except ValueError:
            raise PolicySetupBlocked("canonical JSON cannot contain non-finite numbers") from None

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
        validate_sufficiency_report_payload(payload)

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
                default_policy["artifact_hash_required"] or project_policy["artifact_hash_required"]
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
            tokens = {token for token in re.split(r"[^a-z0-9]+", segment.lower()) if token}
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
        """Require sufficiency clearance before creating or approving policy."""
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

    def _validate_sufficiency_report_allows_policy_derivation(
        self,
        sufficiency_report: GuideSufficiencyReport | None,
        source_snapshot: GuideSourceSnapshot,
    ) -> None:
        """Require report freshness and no blocking gaps before deriving policy."""
        if sufficiency_report is None:
            raise PolicySetupBlocked(
                "guide sufficiency report is required before policy derivation"
            )
        if sufficiency_report.source_snapshot_id != source_snapshot.id:
            raise PolicySetupBlocked("guide sufficiency report is bound to a stale snapshot")
        if sufficiency_report.source_snapshot_hash != source_snapshot.bundle_hash:
            raise PolicySetupBlocked("guide sufficiency report snapshot hash mismatch")
        if sufficiency_report.status == "blocked":
            raise PolicySetupBlocked("guide sufficiency has blocking gaps")

    async def _validate_agent_sufficiency_report_for_derivation(
        self,
        sufficiency_report: GuideSufficiencyReport | None,
    ) -> None:
        """Require server-owned sufficiency provenance before agent derivation."""
        if sufficiency_report is None:
            raise PolicySetupBlocked(
                "agent sufficiency report is required before policy derivation"
            )
        if (
            sufficiency_report.agent_name != PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME
            or sufficiency_report.agent_version != PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION
            or sufficiency_report.project_setup_run_id is None
            or sufficiency_report.setup_generation is None
            or sufficiency_report.agent_material_sha256 is None
            or sufficiency_report.agent_material_byte_count is None
        ):
            raise PolicySetupBlocked(
                "agent sufficiency report is required before policy derivation"
            )
        await self._verified_report_usages(sufficiency_report)

    async def _verified_report_usages(
        self,
        sufficiency_report: GuideSufficiencyReport,
    ) -> list[GuideSufficiencyReportSourceUsage]:
        """Load the complete exact-run usage set for one verified report."""
        if (
            sufficiency_report.project_setup_run_id is None
            or sufficiency_report.setup_generation is None
        ):
            raise PolicySetupBlocked("verified guide source material is required")
        usages = list(
            (
                await self._session.scalars(
                    select(GuideSufficiencyReportSourceUsage)
                    .join(
                        GuideSourceSnapshotItem,
                        GuideSourceSnapshotItem.id
                        == GuideSufficiencyReportSourceUsage.source_item_id,
                    )
                    .where(
                        GuideSufficiencyReportSourceUsage.report_id == sufficiency_report.id,
                        GuideSufficiencyReportSourceUsage.project_setup_run_id
                        == sufficiency_report.project_setup_run_id,
                        GuideSufficiencyReportSourceUsage.setup_generation
                        == sufficiency_report.setup_generation,
                        GuideSourceSnapshotItem.source_snapshot_id
                        == sufficiency_report.source_snapshot_id,
                    )
                    .order_by(GuideSufficiencyReportSourceUsage.item_order)
                )
            ).all()
        )
        expected_count = int(
            await self._session.scalar(
                select(func.count(GuideSourceSnapshotItem.id)).where(
                    GuideSourceSnapshotItem.source_snapshot_id
                    == sufficiency_report.source_snapshot_id
                )
            )
            or 0
        )
        if (
            expected_count == 0
            or len(usages) != expected_count
            or len({usage.source_item_id for usage in usages}) != expected_count
            or [usage.item_order for usage in usages] != list(range(expected_count))
        ):
            raise PolicySetupBlocked("verified guide source material is required")
        return usages

    async def _verified_source_material_refs(
        self,
        sufficiency_report: GuideSufficiencyReport | None,
    ) -> list[str]:
        """Project only verified extraction provenance into policy references."""
        if sufficiency_report is None:
            raise PolicySetupBlocked("verified guide source material is required")
        if sufficiency_report.agent_name is None:
            return []
        usages = await self._verified_report_usages(sufficiency_report)
        return [
            f"artifact-content:{usage.content_id}#extraction-usage:{usage.extraction_usage_id}"
            for usage in usages
        ]

    async def _require_verified_report_sources(
        self,
        sufficiency_report: GuideSufficiencyReport | None,
    ) -> None:
        """Require exact extraction usage before a guide can become active."""
        if sufficiency_report is None:
            raise PolicySetupBlocked("verified guide source material is required")
        await self._verified_report_usages(sufficiency_report)

    def _validate_agent_derived_submission_artifact_policy(
        self,
        policy: SubmissionArtifactPolicy,
        source_snapshot: GuideSourceSnapshot,
    ) -> None:
        """Require agent-derived policy rows to match server-owned provenance."""
        expected_policy_version = agent_submission_artifact_policy_version(
            source_snapshot.bundle_hash
        )
        if policy.source_snapshot_hash != source_snapshot.bundle_hash:
            raise PolicySetupConflict("agent-derived submission artifact policy snapshot mismatch")
        if policy.policy_version != expected_policy_version:
            raise PolicySetupConflict(
                "agent-derived submission artifact policy version is not server-owned"
            )
        if policy.derivation_source != AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
            raise PolicySetupConflict(
                "agent-derived submission artifact policy provenance is invalid"
            )
        if policy.derivation_agent_name is None or policy.derivation_agent_version is None:
            raise PolicySetupConflict(
                "agent-derived submission artifact policy runtime provenance is incomplete"
            )
        if (
            policy.derivation_agent_name != SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_NAME
            or policy.derivation_agent_version
            != SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_VERSION
        ):
            raise PolicySetupConflict(
                "agent-derived submission artifact policy runtime provenance is not server-owned"
            )
        if self._hash_canonical_json(policy.policy_body) != policy.policy_hash:
            raise PolicySetupConflict("agent-derived submission artifact policy body hash mismatch")

    def _post_submit_derivation_context(
        self,
        sufficiency_report: GuideSufficiencyReport,
        effective_policy: EffectiveProjectSubmissionArtifactPolicy,
        pre_submit_checker_policy: PreSubmitCheckerPolicy,
        superseded_policy: PostSubmitCheckerPolicy | None,
    ) -> PostSubmitCheckerPolicyDerivationContext:
        """Build bounded server-owned context for post-submit derivation."""
        registered_names = default_checker_registry().names()
        default_names = set(DEFAULT_DURABLE_CHECKERS)
        return PostSubmitCheckerPolicyDerivationContext(
            sufficiency_report_summary={
                "status": sufficiency_report.status,
                "finding_count": len(sufficiency_report.findings),
                "has_warnings_acknowledged": bool(
                    sufficiency_report.warnings_acknowledged_by_actor
                ),
            },
            effective_policy_summary={
                "required_artifact_count": len(
                    effective_policy.effective_policy.get("required_artifacts", [])
                ),
                "required_evidence_count": len(
                    effective_policy.effective_policy.get("required_evidence", [])
                ),
                "forbidden_artifact_count": len(
                    effective_policy.effective_policy.get("forbidden_artifacts", [])
                ),
                "manifest_required": bool(
                    effective_policy.effective_policy.get("manifest_required")
                ),
                "artifact_hash_required": bool(
                    effective_policy.effective_policy.get("artifact_hash_required")
                ),
                "artifact_hash_algorithm": effective_policy.effective_policy.get(
                    "artifact_hash_algorithm"
                ),
            },
            pre_submit_checker_summary={
                "compiler_version": pre_submit_checker_policy.compiler_version,
                "checker_names": pre_submit_checker_policy.checker_names,
                "compiled_bundle_present": pre_submit_checker_policy.compiled_bundle is not None,
            },
            registered_checker_catalog=[
                PostSubmitCheckerCatalogEntry(
                    name=name,
                    platform_default=name in default_names,
                )
                for name in sorted(registered_names)
            ],
            correction_feedback=(
                PostSubmitCheckerPolicyCorrectionFeedback(
                    superseded_policy_id=superseded_policy.id,
                    superseded_policy_hash=superseded_policy.policy_hash or "",
                    required_checkers=superseded_policy.required_checkers,
                    warning_checkers=superseded_policy.warning_checkers,
                    blocking_severities=superseded_policy.blocking_severities,
                    correction_reason=superseded_policy.supersession_reason or "",
                )
                if (
                    superseded_policy is not None
                    and superseded_policy.supersession_kind == "correction_requested"
                )
                else None
            ),
        )

    def _supersede_post_submit_checker_policy(
        self,
        policy: PostSubmitCheckerPolicy,
        actor: ActorContext,
        *,
        supersession_kind: str,
        supersession_reason: str,
        superseded_at: datetime,
    ) -> None:
        """Retire one compiled policy while preserving append-only provenance."""
        if policy.lifecycle_status != "compiled":
            raise PolicySetupConflict("only compiled post-submit policies can be superseded")
        if supersession_kind not in {"correction_requested", "upstream_policy_changed"}:
            raise PolicySetupConflict("post-submit policy supersession kind is invalid")
        policy.lifecycle_status = "superseded"
        policy.superseded_at = superseded_at
        policy.superseded_by_role = self._approver_role(actor)
        policy.superseded_by_actor = actor.actor_id
        policy.supersession_kind = supersession_kind
        policy.supersession_reason = supersession_reason

    def _validate_post_submit_derivation_result(
        self,
        result: PostSubmitCheckerPolicyDerivationResult,
    ) -> None:
        """Reject unsafe or underspecified post-submit derivation output."""
        requested_checker_names = set(result.required_checkers).union(result.warning_checkers)
        for checker_name in requested_checker_names:
            self._safe_checker_name(checker_name)
        for gap in result.unsupported_required_checks:
            self._safe_public_unsupported_requirement(gap.requested_checker)
            self._validate_post_submit_evidence_refs(gap.evidence_refs)
        reason_by_checker = {reason.checker_name: reason for reason in result.reasons}
        project_specific_names = requested_checker_names.difference(DEFAULT_DURABLE_CHECKERS)
        for checker_name in sorted(project_specific_names):
            reason = reason_by_checker.get(checker_name)
            if reason is None:
                raise PolicySetupBlocked(
                    "post-submit checker derivation reasons are required for project-specific checks"
                )
            self._validate_post_submit_evidence_refs(reason.evidence_refs)
        for reason in result.reasons:
            if reason.checker_name not in requested_checker_names:
                raise PolicySetupBlocked("post-submit checker derivation reason is unreferenced")
            self._safe_checker_name(reason.checker_name)
            self._validate_post_submit_evidence_refs(reason.evidence_refs)
        for note in result.setup_notes:
            self._safe_bounded_summary_value(note)

    def _raise_for_unknown_post_submit_checkers(
        self,
        result: PostSubmitCheckerPolicyDerivationResult,
    ) -> None:
        """Surface unregistered checker names as operator-visible setup blockers."""
        requested_checker_names = set(result.required_checkers).union(result.warning_checkers)
        registered_checker_names = default_checker_registry().names()
        unknown_checker_names = sorted(requested_checker_names.difference(registered_checker_names))
        if not unknown_checker_names:
            return
        reason_by_checker = {reason.checker_name: reason for reason in result.reasons}
        unsupported_gaps = []
        for checker_name in unknown_checker_names[:50]:
            reason = reason_by_checker.get(checker_name)
            unsupported_gaps.append(
                {
                    "requested_checker": self._safe_public_unsupported_requirement(checker_name),
                    "reason_code": "unsupported_required_checker",
                    "evidence_refs": [
                        self._safe_bounded_summary_value(ref.ref)
                        for ref in (reason.evidence_refs if reason is not None else [])[:10]
                    ],
                }
            )
        unsupported_names = sorted({gap["requested_checker"] for gap in unsupported_gaps})
        raise PolicySetupBlocked(
            "unsupported post-submit checker requirements: " + ", ".join(unsupported_names),
            details={"unsupported_required_checks": unsupported_gaps},
        )

    def _safe_checker_name(self, checker_name: str) -> str:
        """Validate checker names before exposing or compiling agent output."""
        normalized = checker_name.strip()
        if normalized != checker_name or not SAFE_TOKEN_PATTERN.fullmatch(normalized):
            raise PolicySetupBlocked("post-submit checker policy contains invalid checker name")
        return normalized

    def _validate_post_submit_evidence_refs(
        self,
        evidence_refs: list[Any],
    ) -> None:
        """Require bounded evidence refs that cannot smuggle source text or paths."""
        if not evidence_refs:
            raise PolicySetupBlocked("post-submit checker derivation reasons require evidence refs")
        for evidence_ref in evidence_refs:
            ref = getattr(evidence_ref, "ref", "")
            if not SAFE_POST_SUBMIT_EVIDENCE_REF_PATTERN.fullmatch(ref):
                raise PolicySetupBlocked("post-submit checker derivation evidence refs are invalid")

    def validate_activation_ready(
        self,
        guide: ProjectGuide,
        source_snapshot: GuideSourceSnapshot,
        sufficiency_report: GuideSufficiencyReport | None,
        submission_artifact_policy: SubmissionArtifactPolicy,
        effective_policy: EffectiveProjectSubmissionArtifactPolicy | None,
        pre_submit_checker_policy: PreSubmitCheckerPolicy | None,
        post_submit_checker_policy: PostSubmitCheckerPolicy | None,
        review_policy: ReviewPolicy | None,
        revision_policy: RevisionPolicy | None,
        payment_policy: PaymentPolicy | None,
        *,
        require_payment_policy: bool = True,
    ) -> None:
        """Enforce the minimum guide and policy contract required to activate.

        Args:
            guide: Draft guide being promoted.
            source_snapshot: Immutable source snapshot used for policy setup.
            sufficiency_report: Guide sufficiency report bound to the snapshot.
            submission_artifact_policy: Approved submission artifact policy.
            effective_policy: Effective policy produced from default + project policy.
            pre_submit_checker_policy: Project pre-submit checker bundle contract.
            post_submit_checker_policy: Post-submit checker policy for the guide version.
            review_policy: Review policy for the guide version.
            revision_policy: Revision policy for the guide version.
            payment_policy: Payment policy for the guide version.
            require_payment_policy: Whether payment completeness is part of readiness.

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
            submission_artifact_policy.derivation_source
            == AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE
        ):
            try:
                self._validate_agent_derived_submission_artifact_policy(
                    submission_artifact_policy,
                    source_snapshot,
                )
            except PolicySetupConflict as exc:
                raise GuideActivationBlocked(str(exc)) from exc
        if (
            self._hash_canonical_json(submission_artifact_policy.policy_body)
            != submission_artifact_policy.policy_hash
        ):
            raise GuideActivationBlocked("submission artifact policy body hash mismatch")
        if (
            not submission_artifact_policy.approved_by_actor
            or not submission_artifact_policy.approved_at
        ):
            raise GuideActivationBlocked(
                "submission artifact policy approval provenance is required"
            )
        if submission_artifact_policy.approved_by_role not in PROJECT_SETUP_ROLES:
            raise GuideActivationBlocked("submission artifact policy approver role is invalid")
        if effective_policy is None:
            raise GuideActivationBlocked("effective project submission artifact policy is required")
        if effective_policy.lifecycle_status != "approved":
            raise GuideActivationBlocked(
                "effective project submission artifact policy is not approved"
            )
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
        try:
            expected_effective_policy = self._merge_effective_submission_artifact_policy(
                submission_artifact_policy.policy_body
            )
        except (KeyError, TypeError, ValueError, ProjectServiceError) as exc:
            raise GuideActivationBlocked("submission artifact policy body is invalid") from exc
        if (
            self._hash_canonical_json(expected_effective_policy)
            != effective_policy.effective_policy_hash
        ):
            raise GuideActivationBlocked(
                "effective project submission artifact policy no longer matches submission policy"
            )
        if effective_policy.submission_artifact_policy_id != submission_artifact_policy.id:
            raise GuideActivationBlocked(
                "effective project submission artifact policy is bound to the wrong policy"
            )
        if (
            effective_policy.submission_artifact_policy_hash
            != submission_artifact_policy.policy_hash
        ):
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
        if (
            pre_submit_checker_policy.effective_policy_hash
            != effective_policy.effective_policy_hash
        ):
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
        if post_submit_checker_policy is None:
            raise GuideActivationBlocked("post-submit checker policy is required")
        if post_submit_checker_policy.guide_id != guide.id:
            raise GuideActivationBlocked("post-submit checker policy guide mismatch")
        if post_submit_checker_policy.source_snapshot_id != source_snapshot.id:
            raise GuideActivationBlocked("post-submit checker policy snapshot mismatch")
        if post_submit_checker_policy.source_snapshot_hash != source_snapshot.bundle_hash:
            raise GuideActivationBlocked("post-submit checker policy snapshot hash mismatch")
        if post_submit_checker_policy.effective_policy_id != effective_policy.id:
            raise GuideActivationBlocked(
                "post-submit checker policy is bound to the wrong effective policy"
            )
        if (
            post_submit_checker_policy.effective_policy_hash
            != effective_policy.effective_policy_hash
        ):
            raise GuideActivationBlocked("post-submit checker policy effective hash mismatch")
        if post_submit_checker_policy.pre_submit_checker_policy_id != pre_submit_checker_policy.id:
            raise GuideActivationBlocked(
                "post-submit checker policy is bound to the wrong pre-submit checker policy"
            )
        if (
            post_submit_checker_policy.pre_submit_checker_bundle_hash
            != pre_submit_checker_policy.compiled_bundle_hash
        ):
            raise GuideActivationBlocked("post-submit checker policy pre-submit hash mismatch")
        if post_submit_checker_policy.lifecycle_status != "approved":
            raise GuideActivationBlocked("approved post-submit checker policy is required")
        if (
            not post_submit_checker_policy.approved_by_role
            or not post_submit_checker_policy.approved_by_actor
            or post_submit_checker_policy.approved_at is None
        ):
            raise GuideActivationBlocked("post-submit checker approval provenance is required")
        if post_submit_checker_policy.approved_by_role not in PROJECT_SETUP_ROLES:
            raise GuideActivationBlocked("post-submit checker approval role is invalid")
        try:
            parsed_post_submit_policy = parse_locked_post_submit_checker_policy_body(
                post_submit_checker_policy.policy_body,
                project_id=post_submit_checker_policy.project_id,
                guide_version=post_submit_checker_policy.guide_version,
                policy_hash=post_submit_checker_policy.policy_hash or "",
            )
        except ValueError as exc:
            raise GuideActivationBlocked("post-submit checker policy hash is invalid") from exc
        if (
            parsed_post_submit_policy.required_checkers
            != post_submit_checker_policy.required_checkers
            or parsed_post_submit_policy.warning_checkers
            != post_submit_checker_policy.warning_checkers
            or parsed_post_submit_policy.blocking_severities
            != post_submit_checker_policy.blocking_severities
        ):
            raise GuideActivationBlocked("post-submit checker policy hash is invalid")
        checker_names = set(parsed_post_submit_policy.execution_checkers)
        try:
            default_checker_registry().require_registered(checker_names)
        except UnknownChecker as exc:
            raise GuideActivationBlocked(
                "post-submit checker policy references unregistered checker"
            ) from exc
        if review_policy is None or revision_policy is None:
            raise GuideActivationBlocked(
                "complete review and revision policy selections are required"
            )
        if not review_policy.allowed_decisions:
            raise GuideActivationBlocked("review policy with allowed decisions is required")
        try:
            require_complete_policy(
                kind="review",
                status=review_policy.semantics_status,
                policy_hash=review_policy.policy_hash,
                semantic_values={
                    "review_preference_window_seconds": (
                        review_policy.review_preference_window_seconds
                    ),
                    "review_lease_duration_seconds": review_policy.review_lease_duration_seconds,
                    "max_active_review_leases_per_reviewer": (
                        review_policy.max_active_review_leases_per_reviewer
                    ),
                    "self_review_allowed": review_policy.self_review_allowed,
                    "reject_policy": review_policy.reject_policy,
                    "finding_evidence_requirement": review_policy.finding_evidence_requirement,
                    "requires_second_review": review_policy.requires_second_review,
                    "allowed_decisions": review_policy.allowed_decisions,
                    "minimum_finding_fields": review_policy.minimum_finding_fields,
                },
            )
            require_complete_policy(
                kind="revision",
                status=revision_policy.semantics_status,
                policy_hash=revision_policy.policy_hash,
                semantic_values={
                    "max_revision_rounds": revision_policy.max_revision_rounds,
                    "revision_deadline_hours": revision_policy.revision_deadline_hours,
                    "allowed_resubmission_states": revision_policy.allowed_resubmission_states,
                    "reviewer_reassignment_rule": revision_policy.reviewer_reassignment_rule,
                },
            )
        except ValueError as exc:
            raise GuideActivationBlocked(
                "review and revision policy semantics are incomplete"
            ) from exc
        if not set(review_policy.allowed_decisions).issubset(ALLOWED_REVIEW_DECISIONS):
            raise GuideActivationBlocked("review policy contains invalid decisions")
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
        if not require_payment_policy:
            return
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
        post_submit_checker_policy: PostSubmitCheckerPolicy,
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
            post_submit_checker_policy: Post-submit checker policy attached to
                the active guide version.
            review_policy: Review policy attached to the active guide version.
            revision_policy: Revision policy attached to the active guide version.
            payment_policy: Payment policy attached to the active guide version.

        Returns:
            API response containing the active guide and policy context.
        """
        source_snapshot_response = await self._source_snapshot_response(source_snapshot)
        return ActiveGuideResponse(
            guide_source_snapshot=source_snapshot_response,
            payment_policy=PaymentPolicyResponse.model_validate(payment_policy),
            **self._active_bundle_response_fields(
                guide,
                sufficiency_report,
                submission_artifact_policy,
                effective_policy,
                pre_submit_checker_policy,
                post_submit_checker_policy,
                review_policy,
                revision_policy,
            ),
        )


def build_guide_source_snapshot_manifest(
    payload: GuideSourceSnapshotCreate,
    *,
    snapshot_id: str,
    generation: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compose a v2 declaration whose byte identity comes only from ART."""
    declared_items: list[dict[str, Any]] = []
    seen_labels: set[tuple[str, str]] = set()
    for item in payload.items:
        source_kind = _guide_source_token(item.source_kind, "source kind")
        ingestion_adapter = _guide_source_token(item.ingestion_adapter, "ingestion adapter")
        source_label = _guide_source_label(item.source_label)
        duplicate_key = (source_kind, source_label)
        if duplicate_key in seen_labels:
            raise SourceSnapshotInvalid("duplicate source item label")
        seen_labels.add(duplicate_key)
        declared_items.append(
            {
                "source_kind": source_kind,
                "source_label": source_label,
                "ingestion_adapter": ingestion_adapter,
                "media_type": item.media_type,
            }
        )
    sorted_declarations = sorted(
        declared_items,
        key=lambda item: (item["source_kind"], item["source_label"], item["ingestion_adapter"]),
    )
    sorted_items = [
        {"item_id": str(uuid4()), "item_order": index, **item}
        for index, item in enumerate(sorted_declarations)
    ]
    return {
        "schema_version": GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "generation": generation,
        "items": sorted_items,
    }, sorted_items


def _guide_source_token(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if not SAFE_TOKEN_PATTERN.fullmatch(normalized):
        raise SourceSnapshotInvalid(f"invalid {label}")
    return normalized


def _guide_source_label(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > SOURCE_ITEM_SOURCE_LABEL_MAX_LENGTH:
        raise SourceSnapshotInvalid("source label is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise SourceSnapshotInvalid("source label contains control characters")
    if any(character in normalized for character in (":", "/", "\\", "%", ";")) or (
        SECRET_REF_PATTERN.search(normalized)
    ):
        raise SourceSnapshotInvalid("source label cannot contain a locator or credential material")
    return normalized


def build_guide_source_snapshot_items(
    snapshot_id: str,
    items: list[dict[str, Any]],
) -> list[GuideSourceSnapshotItem]:
    """Build deterministic source-item rows shared by all snapshot writers."""
    return [
        GuideSourceSnapshotItem(
            id=item["item_id"],
            source_snapshot_id=snapshot_id,
            item_order=item["item_order"],
            source_kind=item["source_kind"],
            source_label=item["source_label"],
            ingestion_adapter=item["ingestion_adapter"],
            media_type=item.get("media_type"),
        )
        for index, item in enumerate(items)
    ]
