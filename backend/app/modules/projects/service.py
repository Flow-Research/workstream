"""Service layer for project and project-guide lifecycle operations."""

from __future__ import annotations

import fnmatch
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.permissions import require_any_role


from app.modules.checkers.compiler import (
    PreSubmitCheckerCompilerError,
    compile_effective_project_submission_artifact_policy,
)
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
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.policy_lineage import require_complete_policy
from app.modules.projects.post_submit_policy import (
    parse_locked_post_submit_checker_policy_body,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.schemas import (
    ActiveGuideReadResponse,
    ActiveGuidePreSubmitCheckerPolicyResponse,
    EffectiveProjectSubmissionArtifactPolicyResponse,
    ProjectGuideCreate,
    GuideSourceSnapshotItemResponse,
    GuideSourceSnapshotResponse,
    GuideSufficiencyReportCreate,
    GuideSufficiencyReportResponse,
    PaymentPolicyInput,
    PostSubmitCheckerPolicyResponse,
    ContributorProjectResponse,
    ProjectGuideResponse,
    ProjectResponse,
    RevisionPolicyResponse,
    ReviewPolicyResponse,
    SubmissionArtifactPolicyApprove,
    SubmissionArtifactPolicyResponse,
)
from app.schemas.auth import ActorContext

logger = logging.getLogger(__name__)

PROJECT_SETUP_PUBLIC_ERROR_SUMMARY = (
    "project setup failed; inspect server logs with the setup run id"
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
GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION = "guide_source_snapshot.task_examples"
EFFECTIVE_POLICY_SCHEMA_VERSION = "effective_project_submission_artifact_policy.v1"
MERGE_ALGORITHM_VERSION = "workstream_default_merge.v1"
PLATFORM_HASH_ALGORITHM = "sha256"
MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE = "manual_admin_derivation"


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
    ) -> None:
        """Create a service instance bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current request.
        """
        self._session = session
        self._repo = ProjectRepository(session)

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
        if policy.derivation_source == "unified_compilation":
            raise PolicySetupBlocked("unified compilation policy approval is unavailable")
        if policy.derivation_source != MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
            raise PolicySetupBlocked("manual policy lineage is required for this approval")
        snapshot = await self._get_snapshot_for_guide(project_id, guide, policy.source_snapshot_id)
        await self._ensure_snapshot_is_latest(project_id, guide, snapshot)
        await self.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        if policy.source_snapshot_hash != snapshot.bundle_hash:
            raise PolicySetupBlocked(
                "submission artifact policy is bound to a stale source snapshot"
            )
        if self._hash_canonical_json(policy.policy_body) != policy.policy_hash:
            raise PolicySetupBlocked("submission artifact policy body hash mismatch")
        sufficiency_report = await self._repo.get_diagnostic_sufficiency_report_for_snapshot(
            snapshot.id
        )
        self._validate_sufficiency_report_allows_policy_approval(
            sufficiency_report,
            snapshot,
        )

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
        return EffectiveProjectSubmissionArtifactPolicyResponse.model_validate(effective)


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
        """Shape the validated active-guide administrative read fields."""
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


    def _safe_project_setup_error_summary(self, summary: str) -> str:
        """Return a bounded setup error summary safe for API responses."""
        return safe_project_setup_error_summary(summary)


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
        if set(manifest) != {
            "schema_version", "snapshot_id", "generation", "items",
            "task_examples_hash", "task_examples_count",
        }:
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

    def canonical_manual_submission_policy_body(
        self, policy_body: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        """Canonicalize a manual policy and enforce the Workstream default floor."""
        canonical = self._canonical_policy_body(policy_body)
        self._merge_effective_submission_artifact_policy(canonical)
        return canonical, self._hash_canonical_json(canonical)

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


    def canonical_agent_submission_policy_body(self, policy_body: dict[str, Any]) -> dict[str, Any]:
        """Canonicalize agent output and enforce platform policy defaults."""
        canonical = self._canonical_policy_body(policy_body)
        self._merge_effective_submission_artifact_policy(canonical)
        return canonical

    async def _verified_report_usages(self, sufficiency_report: GuideSufficiencyReport):
        """Require immutable document-access evidence from this report's exact compilation."""
        from app.modules.projects.guide_compilation.models import (
            ProjectGuideCompilationAttempt, ProjectGuideComponentProjectionOperation,
        )
        from app.modules.projects.guide_compilation.models import ProjectGuideDocumentAccess
        from app.modules.projects.guide_compilation.custody_payloads import report_digest

        projection = await self._session.scalar(select(ProjectGuideComponentProjectionOperation)
            .join(ProjectGuideCompilationAttempt,
                  ProjectGuideCompilationAttempt.id == ProjectGuideComponentProjectionOperation.attempt_id)
            .where(
                ProjectGuideComponentProjectionOperation.report_id == sufficiency_report.id,
                ProjectGuideComponentProjectionOperation.component == "guide_sufficiency",
                ProjectGuideComponentProjectionOperation.setup_run_id == sufficiency_report.project_setup_run_id,
                ProjectGuideComponentProjectionOperation.setup_generation == sufficiency_report.setup_generation,
                ProjectGuideCompilationAttempt.guide_material_hash == sufficiency_report.agent_material_sha256,
                ProjectGuideCompilationAttempt.status == "compilation_persisted",
            ))
        if projection is None or projection.output_digest != report_digest(sufficiency_report):
            raise PolicySetupBlocked("current guide document evidence is required")
        usages = list(await self._session.scalars(select(ProjectGuideDocumentAccess)
            .join(GuideSourceSnapshotItem,
                  GuideSourceSnapshotItem.id == ProjectGuideDocumentAccess.source_item_id)
            .where(
                ProjectGuideDocumentAccess.attempt_id == projection.attempt_id,
                ProjectGuideDocumentAccess.manifest_sha256 == sufficiency_report.agent_material_sha256,
                GuideSourceSnapshotItem.source_snapshot_id == sufficiency_report.source_snapshot_id,
            ).order_by(GuideSourceSnapshotItem.item_order)))
        expected = int(await self._session.scalar(select(func.count(GuideSourceSnapshotItem.id))
            .where(GuideSourceSnapshotItem.source_snapshot_id == sufficiency_report.source_snapshot_id)) or 0)
        if expected == 0 or len(usages) != expected or len({row.source_item_id for row in usages}) != expected:
            raise PolicySetupBlocked("complete guide document evidence is required")
        return usages

    async def _verified_source_material_refs(
        self,
        sufficiency_report: GuideSufficiencyReport | None,
    ) -> list[str]:
        """Project exact opened original-document versions into policy references."""
        if sufficiency_report is None:
            raise PolicySetupBlocked("verified guide source material is required")
        usages = await self._verified_report_usages(sufficiency_report)
        return [
            f"guide-document:{usage.document_version_id}#{usage.sha256}"
            for usage in usages
        ]

    async def verified_source_material_refs(
        self, sufficiency_report: GuideSufficiencyReport | None
    ) -> list[str]:
        """Return canonical verified source references for authorized policy writes."""
        return await self._verified_source_material_refs(sufficiency_report)


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
        if submission_artifact_policy.derivation_source != MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
            raise GuideActivationBlocked("current approved manual policy lineage is required")
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
        try:
            parsed_post_submit_policy.validate_sidecars(
                required_checkers=post_submit_checker_policy.required_checkers,
                warning_checkers=post_submit_checker_policy.warning_checkers,
                blocking_severities=post_submit_checker_policy.blocking_severities,
            )
        except ValueError as exc:
            raise GuideActivationBlocked("post-submit checker policy hash is invalid") from exc
        if review_policy is None or revision_policy is None:
            raise GuideActivationBlocked(
                "complete review and revision policy selections are required"
            )
        if not review_policy.allowed_decisions:
            raise GuideActivationBlocked("review policy with allowed decisions is required")
        try:
            require_complete_policy(
                kind="review",
                review_semantics_format=review_policy.semantics_format,
                status=review_policy.semantics_status,
                policy_hash=review_policy.policy_hash,
                semantic_values={
                    "human_review_required": review_policy.human_review_required,
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
        if not review_policy.human_review_required:
            raise GuideActivationBlocked("automated acceptance is unavailable")
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


def build_guide_source_snapshot_manifest(
    payload: ProjectGuideCreate,
    *,
    snapshot_id: str,
    generation: int,
    task_examples: object,
    expected_task_examples_hash: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Bind document declarations and the owning guide's immutable task examples."""
    from app.modules.projects.api.task_examples import (
        GuideTaskExampleInputError, task_examples_hash, require_task_example_commitment,
    )

    try:
        examples = require_task_example_commitment(task_examples, expected_task_examples_hash)
    except GuideTaskExampleInputError as exc:
        raise SourceSnapshotInvalid(exc.code) from None
    examples_hash = task_examples_hash(examples)
    declared_items: list[dict[str, Any]] = []
    seen_labels: set[tuple[str, str]] = set()
    for item in payload.documents:
        source_kind = "document"
        ingestion_adapter = "upload"
        source_label = _guide_source_label(item.label)
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
    ordered_items = [
        {"item_id": str(uuid4()), "item_order": index, **item}
        for index, item in enumerate(declared_items)
    ]
    return {
        "schema_version": GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "generation": generation,
        "task_examples_hash": examples_hash,
        "task_examples_count": len(examples),
        "items": ordered_items,
    }, ordered_items


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
