"""Hidden deterministic projections from one persisted unified compilation."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
import re
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import (
    GuideSufficiencyMaterialPort,
    GuideSufficiencyMaterialRequest,
    GuideSufficiencyMaterialResult,
    GuideSufficiencyMaterialUnavailable,
)
from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
    VerifiedGuideMaterialSnapshot,
)
from app.modules.authorization.api import (
    ArtifactPolicyProjectionAuthorizationPort,
    ArtifactPolicyProjectionFacts,
    AuthorizationDenied,
    AuthorizationUnavailable,
    GuideSufficiencyProjectionAuthorizationPort,
    GuideSufficiencyProjectionFacts,
    PreparedArtifactPolicyProjection,
    PreparedAuthorizationInvalid,
    PreparedGuideSufficiencyProjection,
    ProjectGuideProjectionAuthorityReceipt,
    ProjectGuideProjectionIdentity,
    ProjectGuideProjectionLocator,
    artifact_policy_projection_facts_digest,
    guide_sufficiency_projection_facts_digest,
    projection_authority_digest,
)
from app.modules.projects.api import (
    ProjectGuideProjectionCommand,
    ProjectGuideProjectionComponent,
    ProjectGuideProjectionError,
    ProjectGuideProjectionReceipt,
)
from app.modules.projects.models import (
    GuideSufficiencyReport,
    GuideSufficiencyReportSourceUsage,
    SubmissionArtifactPolicy,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import (
    GuideSufficiencyFindingInput,
    GuideSufficiencyReportCreate,
    SubmissionArtifactPolicyInput,
)
from app.modules.projects.service import (
    PolicySetupBlocked,
    ProjectService,
    build_verified_guide_sufficiency_material,
)
from app.modules.projects.setup_queue import pre_submit_setup_task_id

from .contracts import AcceptedCompilationResult
from .models import ProjectGuideComponentProjectionOperation
from .repository import GuideCompilationIntegrityError, GuideCompilationRepository

_PROJECTOR_NAME = "ProjectGuideCompilationProjection"
_PROJECTOR_VERSION = "v1"
_SERVICE_IDENTITY = "workstream.project.setup"
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


@dataclass(frozen=True, slots=True)
class _ProjectionSeed:
    """Immutable compilation lineage prepared before authorization."""

    attempt_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    request_operation_id: UUID
    provider_idempotency_key: UUID
    compilation_id: UUID
    result_hash: str
    component_hash: str
    sufficiency_component_hash: str
    result_schema_version: str
    compilation_agent_name: str
    compilation_agent_version: str
    result: ProjectGuideCompilationResult
    report_payload: GuideSufficiencyReportCreate | None = None
    policy_body: dict | None = None


@dataclass(frozen=True, slots=True)
class _LockedProjection:
    """Verified material and source state locked for one transaction."""

    material: GuideSufficiencyMaterialResult
    material_sha256: str
    material_byte_count: int
    celery_task_id: UUID
    source_state_digest: str


class _UnavailableSufficiencyAuthorization:
    """Deny sufficiency projection until AUTH explicitly activates it."""

    def prepare_sufficiency_projection(
        self, _locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedGuideSufficiencyProjection]:
        """Return a context that fails before any product access."""
        return _unavailable_sufficiency()


class _UnavailablePolicyAuthorization:
    """Deny policy projection until AUTH explicitly activates it."""

    def prepare_artifact_policy_projection(
        self, _locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedArtifactPolicyProjection]:
        """Return a context that fails before any product access."""
        return _unavailable_policy()


@asynccontextmanager
async def _unavailable_sufficiency():
    """Fail the deny-default sufficiency authorization context."""
    raise AuthorizationUnavailable("projection authority is unavailable")
    yield  # pragma: no cover


@asynccontextmanager
async def _unavailable_policy():
    """Fail the deny-default policy authorization context."""
    raise AuthorizationUnavailable("projection authority is unavailable")
    yield  # pragma: no cover


class GuideCompilationProjectionService:
    """Project exact compilation components without changing setup state."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        material_factory: Callable[[AsyncSession], GuideSufficiencyMaterialPort],
        sufficiency_authorization_factory: Callable[
            [AsyncSession], GuideSufficiencyProjectionAuthorizationPort
        ]
        | None = None,
        policy_authorization_factory: Callable[
            [AsyncSession], ArtifactPolicyProjectionAuthorizationPort
        ]
        | None = None,
    ) -> None:
        """Bind storage, material, and purpose-specific AUTH factories."""
        self._session_factory = session_factory
        self._material_factory = material_factory
        self._sufficiency_authorization_factory = (
            sufficiency_authorization_factory
            or (lambda _session: _UnavailableSufficiencyAuthorization())
        )
        self._policy_authorization_factory = policy_authorization_factory or (
            lambda _session: _UnavailablePolicyAuthorization()
        )

    async def project_guide_sufficiency(
        self, command: ProjectGuideProjectionCommand
    ) -> ProjectGuideProjectionReceipt:
        """Create or replay the exact canonical sufficiency report."""
        seed = await self._preflight(command.attempt_id, "guide_sufficiency")
        assert seed.report_payload is not None
        return await self._run_sufficiency(seed, retry_conflict=True)

    async def project_submission_artifact_policy(
        self, command: ProjectGuideProjectionCommand
    ) -> ProjectGuideProjectionReceipt:
        """Create or replay the exact canonical artifact-policy draft."""
        seed = await self._preflight(
            command.attempt_id, "submission_artifact_policy"
        )
        assert seed.policy_body is not None
        return await self._run_policy(seed, retry_conflict=True)

    async def _preflight(
        self,
        attempt_id: UUID,
        component: Literal["guide_sufficiency", "submission_artifact_policy"],
    ) -> _ProjectionSeed:
        """Load and validate immutable compilation input without row locks."""
        try:
            async with self._session_factory() as session:
                compilation_repo = GuideCompilationRepository(session)
                attempt = await compilation_repo.attempt(attempt_id, lock=False)
                if attempt.status in {
                    "compilation_invalid_terminal",
                    "compilation_provider_uncertain",
                }:
                    raise ProjectGuideProjectionError("component_forbidden")
                if attempt.status != "compilation_persisted":
                    raise ProjectGuideProjectionError("attempt_unavailable")
                compilation = await compilation_repo.persisted_compilation(attempt_id)
                accepted = AcceptedCompilationResult(
                    canonical_result=compilation.canonical_result,
                    result_hash=compilation.result_hash,
                    component_hashes=compilation.component_hashes,
                )
                result = ProjectGuideCompilationResult.model_validate(
                    accepted.canonical_result
                )
                if (
                    attempt.persisted_compilation_id != compilation.id
                    or compilation.attempt_id != attempt.id
                    or compilation.project_id != attempt.project_id
                    or compilation.guide_id != attempt.guide_id
                    or compilation.source_snapshot_id != attempt.source_snapshot_id
                    or compilation.setup_run_id != attempt.setup_run_id
                    or compilation.setup_generation != attempt.setup_generation
                ):
                    raise ProjectGuideProjectionError("attempt_unavailable")
                request = await compilation_repo.request_operation_for_attempt(
                    attempt_id, lock=False
                )
                report_payload = _report_payload(result, attempt.source_snapshot_id)
                policy_body = None
                if component == "submission_artifact_policy":
                    if result.status == "guide_blocked":
                        raise ProjectGuideProjectionError("component_forbidden")
                    policy_body = _policy_body(session, result.submission_artifact_policy)
                component_hash = (
                    accepted.component_hashes.sufficiency_hash
                    if component == "guide_sufficiency"
                    else accepted.component_hashes.artifact_policy_hash
                )
                return _ProjectionSeed(
                    attempt_id=attempt.id,
                    project_id=UUID(attempt.project_id),
                    guide_id=UUID(attempt.guide_id),
                    guide_version=attempt.guide_version,
                    source_snapshot_id=UUID(attempt.source_snapshot_id),
                    source_snapshot_hash=attempt.source_snapshot_hash,
                    setup_run_id=UUID(attempt.setup_run_id),
                    setup_generation=attempt.setup_generation,
                    request_operation_id=request.operation_id,
                    provider_idempotency_key=attempt.provider_idempotency_key,
                    compilation_id=compilation.id,
                    result_hash=compilation.result_hash,
                    component_hash=component_hash,
                    sufficiency_component_hash=(
                        accepted.component_hashes.sufficiency_hash
                    ),
                    result_schema_version=result.schema_version,
                    compilation_agent_name=result.agent_name,
                    compilation_agent_version=result.agent_version,
                    result=result,
                    report_payload=report_payload,
                    policy_body=policy_body,
                )
        except ProjectGuideProjectionError:
            raise
        except (ValidationError, ValueError, PolicySetupBlocked):
            raise ProjectGuideProjectionError("component_unprojectable") from None
        except GuideCompilationIntegrityError:
            raise ProjectGuideProjectionError("attempt_unavailable") from None
        except SQLAlchemyError:
            raise ProjectGuideProjectionError("storage_unavailable") from None

    async def _run_sufficiency(
        self, seed: _ProjectionSeed, *, retry_conflict: bool
    ) -> ProjectGuideProjectionReceipt:
        """Run one authorized sufficiency transaction with one conflict replay."""
        try:
            async with self._session_factory() as session:
                authorization = self._sufficiency_authorization_factory(session)
                async with session.begin():
                    locator = ProjectGuideProjectionLocator(
                        project_id=seed.project_id, attempt_id=seed.attempt_id
                    )
                    async with authorization.prepare_sufficiency_projection(
                        locator
                    ) as capability:
                        return await self._write_sufficiency(
                            session, seed, capability
                        )
        except IntegrityError:
            if retry_conflict:
                return await self._run_sufficiency(seed, retry_conflict=False)
            raise ProjectGuideProjectionError("source_state_unavailable") from None
        except ProjectGuideProjectionError:
            raise
        except (
            AuthorizationDenied,
            AuthorizationUnavailable,
            PreparedAuthorizationInvalid,
        ):
            raise ProjectGuideProjectionError("service_authority_denied") from None
        except GuideSufficiencyMaterialUnavailable:
            raise ProjectGuideProjectionError("source_state_unavailable") from None
        except GuideCompilationIntegrityError:
            raise ProjectGuideProjectionError("source_state_unavailable") from None
        except DBAPIError:
            raise ProjectGuideProjectionError("storage_unavailable") from None
        except SQLAlchemyError:
            raise ProjectGuideProjectionError("storage_unavailable") from None

    async def _run_policy(
        self, seed: _ProjectionSeed, *, retry_conflict: bool
    ) -> ProjectGuideProjectionReceipt:
        """Run one authorized policy transaction with one conflict replay."""
        try:
            async with self._session_factory() as session:
                authorization = self._policy_authorization_factory(session)
                async with session.begin():
                    locator = ProjectGuideProjectionLocator(
                        project_id=seed.project_id, attempt_id=seed.attempt_id
                    )
                    async with authorization.prepare_artifact_policy_projection(
                        locator
                    ) as capability:
                        return await self._write_policy(session, seed, capability)
        except IntegrityError:
            if retry_conflict:
                return await self._run_policy(seed, retry_conflict=False)
            raise ProjectGuideProjectionError("source_state_unavailable") from None
        except ProjectGuideProjectionError:
            raise
        except (
            AuthorizationDenied,
            AuthorizationUnavailable,
            PreparedAuthorizationInvalid,
        ):
            raise ProjectGuideProjectionError("service_authority_denied") from None
        except GuideSufficiencyMaterialUnavailable:
            raise ProjectGuideProjectionError("source_state_unavailable") from None
        except GuideCompilationIntegrityError:
            raise ProjectGuideProjectionError("source_state_unavailable") from None
        except DBAPIError:
            raise ProjectGuideProjectionError("storage_unavailable") from None
        except SQLAlchemyError:
            raise ProjectGuideProjectionError("storage_unavailable") from None

    async def _write_sufficiency(
        self,
        session: AsyncSession,
        seed: _ProjectionSeed,
        capability: PreparedGuideSufficiencyProjection,
    ) -> ProjectGuideProjectionReceipt:
        """Create or validate the exact sufficiency output and custody row."""
        locked = await self._lock_common(session, seed)
        identity = capability.identity
        _require_projection_identity(identity, seed, "guide_sufficiency")
        assert seed.report_payload is not None
        output = _report_output(seed, locked, identity, seed.report_payload)
        output_digest = canonical_json_hash(
            {
                "domain": "workstream.project_guide_sufficiency_projection.output.v1",
                "facts": output,
            }
        )
        facts = _sufficiency_facts(seed, locked, identity, output_digest)
        operation = await _projection_operation(session, identity.operation_id)
        if operation is not None:
            report = await ProjectRepository(session).lock_guide_sufficiency_report(
                str(identity.output_id),
                str(seed.project_id),
                str(seed.guide_id),
                seed.guide_version,
            )
            _require_replay(operation, seed, identity, facts, output_digest, report)
            await capability.validate_replay(
                facts, UUID(operation.authorization_decision_event_id)
            )
            return _receipt(seed, identity, output_digest, "guide_sufficiency", "replayed")

        if await _report_exists(session, seed, identity.output_id):
            raise ProjectGuideProjectionError("source_state_unavailable")
        authority = await capability.consume_new(facts)
        _require_authority(authority, seed, identity, facts, "guide_sufficiency")
        report = _new_report(seed, locked, identity, authority, seed.report_payload)
        session.add(report)
        _add_source_usages(session, report.id, seed, locked.material)
        await session.flush()
        session.add(
            _new_operation(
                seed,
                locked,
                identity,
                authority,
                component="guide_sufficiency",
                output_digest=output_digest,
                facts_digest=guide_sufficiency_projection_facts_digest(facts),
                report_id=report.id,
            )
        )
        await session.flush()
        return _receipt(seed, identity, output_digest, "guide_sufficiency", "projected")

    async def _write_policy(
        self,
        session: AsyncSession,
        seed: _ProjectionSeed,
        capability: PreparedArtifactPolicyProjection,
    ) -> ProjectGuideProjectionReceipt:
        """Create or validate the exact policy output and custody row."""
        locked = await self._lock_common(session, seed)
        identity = capability.identity
        _require_projection_identity(identity, seed, "submission_artifact_policy")
        prior = await _required_sufficiency_operation(session, seed, locked)
        report = await ProjectRepository(session).lock_guide_sufficiency_report(
            prior.report_id or "",
            str(seed.project_id),
            str(seed.guide_id),
            seed.guide_version,
        )
        if report is None or _report_digest(report) != prior.output_digest:
            raise ProjectGuideProjectionError("source_state_unavailable")
        assert seed.policy_body is not None
        output = _policy_output(seed, locked, identity, seed.policy_body)
        output_digest = canonical_json_hash(
            {
                "domain": (
                    "workstream.project_submission_artifact_policy_projection.output.v1"
                ),
                "facts": output,
            }
        )
        facts = _policy_facts(seed, locked, identity, prior, output_digest)
        operation = await _projection_operation(session, identity.operation_id)
        if operation is not None:
            policy = await ProjectRepository(session).lock_submission_artifact_policy(
                str(identity.output_id)
            )
            _require_replay(operation, seed, identity, facts, output_digest, policy)
            await capability.validate_replay(
                facts, UUID(operation.authorization_decision_event_id)
            )
            return _receipt(
                seed,
                identity,
                output_digest,
                "submission_artifact_policy",
                "replayed",
            )

        if await _policy_exists(session, seed, identity.output_id):
            raise ProjectGuideProjectionError("source_state_unavailable")
        authority = await capability.consume_new(facts)
        _require_authority(
            authority, seed, identity, facts, "submission_artifact_policy"
        )
        policy = _new_policy(seed, locked, identity, authority, seed.policy_body)
        session.add(policy)
        await session.flush()
        session.add(
            _new_operation(
                seed,
                locked,
                identity,
                authority,
                component="submission_artifact_policy",
                output_digest=output_digest,
                facts_digest=artifact_policy_projection_facts_digest(facts),
                policy_id=policy.id,
                prior=prior,
            )
        )
        await session.flush()
        return _receipt(
            seed,
            identity,
            output_digest,
            "submission_artifact_policy",
            "projected",
        )

    async def _lock_common(
        self, session: AsyncSession, seed: _ProjectionSeed
    ) -> _LockedProjection:
        """Lock and revalidate the compilation, material, guide, and setup."""
        compilation_repo = GuideCompilationRepository(session)
        attempt = await compilation_repo.attempt(seed.attempt_id, lock=True)
        request = await compilation_repo.request_operation_for_attempt(
            seed.attempt_id, lock=True
        )
        if not _seed_matches(attempt, request, seed):
            raise ProjectGuideProjectionError("source_state_unavailable")
        material = await self._material_factory(session).load(
            GuideSufficiencyMaterialRequest(
                project_id=seed.project_id,
                guide_id=seed.guide_id,
                guide_source_snapshot_id=seed.source_snapshot_id,
                project_setup_run_id=seed.setup_run_id,
                setup_generation=seed.setup_generation,
            )
        )
        projects = ProjectRepository(session)
        guide = await projects.lock_project_guide(str(seed.guide_id))
        setup = await projects.lock_project_setup_run(str(seed.setup_run_id))
        snapshot = await projects.get_guide_source_snapshot(str(seed.source_snapshot_id))
        latest_snapshot = await projects.get_latest_guide_source_snapshot(
            str(seed.project_id), str(seed.guide_id), seed.guide_version
        )
        latest_setup = await projects.lock_latest_project_setup_run(
            str(seed.project_id), str(seed.guide_id), seed.guide_version
        )
        if guide is None or setup is None or snapshot is None:
            raise ProjectGuideProjectionError("source_state_unavailable")
        expected_task = pre_submit_setup_task_id(setup.id, setup.setup_generation)
        if not _is_exact_projection_source_state(
            guide,
            snapshot,
            setup,
            latest_snapshot,
            latest_setup,
            seed,
            expected_task,
        ):
            raise ProjectGuideProjectionError("source_state_unavailable")
        verified = VerifiedGuideMaterialSnapshot.from_material(
            build_verified_guide_sufficiency_material(
                guide, snapshot, material.source_items
            )
        )
        if verified.canonical_payload_sha256 != attempt.guide_material_hash:
            raise ProjectGuideProjectionError("source_state_unavailable")
        state = _source_state(guide, snapshot, setup)
        return _LockedProjection(
            material=material,
            material_sha256=verified.canonical_payload_sha256,
            material_byte_count=len(verified.canonical_payload),
            celery_task_id=UUID(expected_task),
            source_state_digest=canonical_json_hash(
                {
                    "domain": "workstream.project_guide_projection.source_state.v1",
                    "facts": state,
                }
            ),
        )


def _is_exact_projection_source_state(
    guide,
    snapshot,
    setup,
    latest_snapshot,
    latest_setup,
    seed: _ProjectionSeed,
    expected_task: str,
) -> bool:
    """Return whether locked product rows match the sole source-state shape."""
    continuation_pair = (
        setup.continuation_verification_job_id,
        setup.continuation_started_at,
    )
    return not (
        guide.project_id != str(seed.project_id)
        or guide.version != seed.guide_version
        or guide.status != "draft"
        or snapshot.project_id != str(seed.project_id)
        or snapshot.guide_id != str(seed.guide_id)
        or snapshot.guide_version != seed.guide_version
        or snapshot.bundle_hash != seed.source_snapshot_hash
        or latest_snapshot is None
        or latest_snapshot.id != snapshot.id
        or latest_setup is None
        or latest_setup.id != setup.id
        or setup.source_snapshot_id != snapshot.id
        or setup.source_snapshot_hash != snapshot.bundle_hash
        or setup.setup_generation != seed.setup_generation
        or setup.status != "queued"
        or setup.current_step != "queued"
        or setup.celery_task_id != expected_task
        or (continuation_pair[0] is None) != (continuation_pair[1] is None)
        or setup.error_code is not None
        or setup.error_artifact_incident_id is not None
        or setup.error_summary is not None
        or setup.post_submit_derivation_summary is not None
        or setup.started_at is not None
        or setup.finished_at is not None
        or setup.output_sufficiency_report_id is not None
        or setup.output_submission_artifact_policy_id is not None
        or setup.output_post_submit_checker_policy_id is not None
    )


def _report_payload(
    result: ProjectGuideCompilationResult, source_snapshot_id: str
) -> GuideSufficiencyReportCreate:
    """Map one validated compilation result to a canonical report payload."""
    status = {
        "guide_blocked": "blocked",
        "draft_ready": "passed",
        "draft_ready_with_warnings": "passed_with_warnings",
    }[result.status]
    return GuideSufficiencyReportCreate(
        source_snapshot_id=source_snapshot_id,
        status=cast(Literal["passed", "blocked", "passed_with_warnings"], status),
        findings=[
            GuideSufficiencyFindingInput(
                severity=item.severity,
                code=item.code,
                message=item.message,
                location=None,
            )
            for item in result.findings
        ],
        summary=None,
    )


def _policy_body(
    session: AsyncSession, proposal: SubmissionArtifactPolicyProposal | None
) -> dict:
    """Map a bounded proposal to the canonical platform policy body."""
    if proposal is None:
        raise ValueError("artifact policy proposal is absent")
    for value in (*proposal.required_evidence, *proposal.attestation_terms):
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("artifact policy identifier is not canonical")
    policy = SubmissionArtifactPolicyInput(
        required_artifacts=[
            {
                "key": f"required-artifact-{index:03d}",
                "path": value,
                "hash_required": True,
                "required": True,
                "description": None,
            }
            for index, value in enumerate(proposal.required_artifacts, 1)
        ],
        required_evidence=[
            {
                "key": f"required-evidence-{index:03d}",
                "label": value,
                "hash_required": True,
                "required": True,
                "description": None,
            }
            for index, value in enumerate(proposal.required_evidence, 1)
        ],
        forbidden_artifacts=[
            {"pattern": value, "reason": value, "worker_facing_fix": None}
            for value in proposal.forbidden_artifacts
        ],
        attestation_terms=list(proposal.attestation_terms),
        manifest_required=True,
        artifact_hash_required=True,
        artifact_hash_algorithm="sha256",
        allowed_storage_schemes=["local", "r2", "s3"],
        maximum_file_size_bytes=proposal.maximum_file_size_bytes,
        maximum_package_size_bytes=proposal.maximum_package_size_bytes,
        packaging={"package_required": True, "allowed_package_formats": ["zip"]},
    )
    return ProjectService(session).canonical_agent_submission_policy_body(
        policy.model_dump(mode="json")
    )


def _source_state(guide, snapshot, setup) -> dict:
    """Build the complete source-state digest payload."""
    return {
        "celery_task_id": setup.celery_task_id,
        "continuation_started_at": (
            setup.continuation_started_at.isoformat()
            if setup.continuation_started_at is not None
            else None
        ),
        "continuation_verification_job_id": setup.continuation_verification_job_id,
        "current_step": setup.current_step,
        "error_artifact_incident_id": setup.error_artifact_incident_id,
        "error_code": setup.error_code,
        "error_summary": setup.error_summary,
        "finished_at": setup.finished_at.isoformat() if setup.finished_at else None,
        "guide_id": guide.id,
        "guide_status": guide.status,
        "guide_version": guide.version,
        "output_post_submit_checker_policy_id": setup.output_post_submit_checker_policy_id,
        "output_submission_artifact_policy_id": (
            setup.output_submission_artifact_policy_id
        ),
        "output_sufficiency_report_id": setup.output_sufficiency_report_id,
        "post_submit_derivation_summary": setup.post_submit_derivation_summary,
        "setup_generation": setup.setup_generation,
        "setup_run_id": setup.id,
        "source_snapshot_hash": snapshot.bundle_hash,
        "source_snapshot_id": snapshot.id,
        "started_at": setup.started_at.isoformat() if setup.started_at else None,
        "status": setup.status,
    }


def _report_output(
    seed: _ProjectionSeed,
    locked: _LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    payload: GuideSufficiencyReportCreate,
) -> dict:
    """Build the exact sufficiency output digest payload."""
    return {
        "id": str(identity.output_id),
        "project_id": str(seed.project_id),
        "guide_id": str(seed.guide_id),
        "guide_version": seed.guide_version,
        "source_snapshot_id": str(seed.source_snapshot_id),
        "source_snapshot_hash": seed.source_snapshot_hash,
        "status": payload.status,
        "findings": [item.model_dump(mode="json") for item in payload.findings],
        "summary": None,
        "agent_name": _PROJECTOR_NAME,
        "agent_version": _PROJECTOR_VERSION,
        "project_setup_run_id": str(seed.setup_run_id),
        "setup_generation": seed.setup_generation,
        "agent_material_sha256": locked.material_sha256,
        "agent_material_byte_count": locked.material_byte_count,
        "created_by": str(identity.actor_profile_id),
    }


def _policy_output(
    seed: _ProjectionSeed,
    locked: _LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    policy_body: dict,
) -> dict:
    """Build the exact draft-policy output digest payload."""
    policy_hash = canonical_json_hash(policy_body)
    return {
        "id": str(identity.output_id),
        "project_id": str(seed.project_id),
        "guide_id": str(seed.guide_id),
        "guide_version": seed.guide_version,
        "source_snapshot_id": str(seed.source_snapshot_id),
        "source_snapshot_hash": seed.source_snapshot_hash,
        "policy_version": (
            f"unified-{seed.source_snapshot_hash.removeprefix('sha256:')[:16]}"
            f"-g{seed.setup_generation}"
        ),
        "lifecycle_status": "draft",
        "policy_body": policy_body,
        "policy_hash": policy_hash,
        "derivation_source": "unified_compilation",
        "source_material_refs": [
            "artifact-content:"
            f"{item.content_id}#extraction-usage:{item.extraction_usage_id}"
            for item in locked.material.provenance
        ],
        "derivation_agent_name": _PROJECTOR_NAME,
        "derivation_agent_version": _PROJECTOR_VERSION,
        "created_by": str(identity.actor_profile_id),
        "change_summary": "Projected from unified project guide compilation.",
    }


def _sufficiency_facts(
    seed: _ProjectionSeed,
    locked: _LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    output_digest: str,
) -> GuideSufficiencyProjectionFacts:
    """Build the closed AUTH facts for sufficiency projection."""
    return GuideSufficiencyProjectionFacts(
        project_id=seed.project_id,
        attempt_id=seed.attempt_id,
        request_operation_id=seed.request_operation_id,
        provider_idempotency_key=seed.provider_idempotency_key,
        compilation_id=seed.compilation_id,
        guide_id=seed.guide_id,
        guide_version=seed.guide_version,
        source_snapshot_id=seed.source_snapshot_id,
        source_snapshot_hash=seed.source_snapshot_hash,
        setup_run_id=seed.setup_run_id,
        setup_generation=seed.setup_generation,
        celery_task_id=locked.celery_task_id,
        source_state_digest=locked.source_state_digest,
        result_hash=seed.result_hash,
        component_hash=seed.component_hash,
        result_schema_version=seed.result_schema_version,
        compilation_agent_name=seed.compilation_agent_name,
        compilation_agent_version=seed.compilation_agent_version,
        material_sha256=locked.material_sha256,
        material_byte_count=locked.material_byte_count,
        report_id=identity.output_id,
        report_content_digest=output_digest,
    )


def _policy_facts(
    seed: _ProjectionSeed,
    locked: _LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    prior: ProjectGuideComponentProjectionOperation,
    output_digest: str,
) -> ArtifactPolicyProjectionFacts:
    """Build the closed AUTH facts for artifact-policy projection."""
    return ArtifactPolicyProjectionFacts(
        project_id=seed.project_id,
        attempt_id=seed.attempt_id,
        request_operation_id=seed.request_operation_id,
        provider_idempotency_key=seed.provider_idempotency_key,
        compilation_id=seed.compilation_id,
        guide_id=seed.guide_id,
        guide_version=seed.guide_version,
        source_snapshot_id=seed.source_snapshot_id,
        source_snapshot_hash=seed.source_snapshot_hash,
        setup_run_id=seed.setup_run_id,
        setup_generation=seed.setup_generation,
        celery_task_id=locked.celery_task_id,
        source_state_digest=locked.source_state_digest,
        result_hash=seed.result_hash,
        component_hash=seed.component_hash,
        result_schema_version=seed.result_schema_version,
        compilation_agent_name=seed.compilation_agent_name,
        compilation_agent_version=seed.compilation_agent_version,
        prior_operation_id=prior.operation_id,
        sufficiency_report_id=UUID(cast(str, prior.report_id)),
        sufficiency_report_digest=prior.output_digest,
        policy_id=identity.output_id,
        policy_content_digest=output_digest,
    )


def _new_report(
    seed: _ProjectionSeed,
    locked: _LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    authority: ProjectGuideProjectionAuthorityReceipt,
    payload: GuideSufficiencyReportCreate,
) -> GuideSufficiencyReport:
    """Create a canonical report bound to the authority receipt."""
    return GuideSufficiencyReport(
        id=str(identity.output_id),
        project_id=str(seed.project_id),
        guide_id=str(seed.guide_id),
        guide_version=seed.guide_version,
        source_snapshot_id=str(seed.source_snapshot_id),
        source_snapshot_hash=seed.source_snapshot_hash,
        status=payload.status,
        findings=[item.model_dump(mode="json") for item in payload.findings],
        summary=None,
        agent_name=_PROJECTOR_NAME,
        agent_version=_PROJECTOR_VERSION,
        project_setup_run_id=str(seed.setup_run_id),
        setup_generation=seed.setup_generation,
        agent_material_sha256=locked.material_sha256,
        agent_material_byte_count=locked.material_byte_count,
        created_by=str(identity.actor_profile_id),
        created_by_actor_profile_id=str(authority.actor_profile_id),
        created_via_identity_link_id=str(authority.identity_link_id),
        created_by_service_identity=authority.service_identity,
        creation_scope_type="service",
        creation_scope_project_id=str(seed.project_id),
        creation_action_id="project.guide_sufficiency.run",
        authorization_decision_event_id=str(authority.decision_event_id),
    )


def _new_policy(
    seed: _ProjectionSeed,
    locked: _LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    authority: ProjectGuideProjectionAuthorityReceipt,
    policy_body: dict,
) -> SubmissionArtifactPolicy:
    """Create a canonical draft policy bound to the authority receipt."""
    output = _policy_output(seed, locked, identity, policy_body)
    return SubmissionArtifactPolicy(
        **output,
        created_by_actor_profile_id=str(authority.actor_profile_id),
        created_via_identity_link_id=str(authority.identity_link_id),
        created_by_service_identity=authority.service_identity,
        creation_scope_type="service",
        creation_scope_project_id=str(seed.project_id),
        creation_action_id="project.submission_artifact_policy.derive",
        creation_decision_event_id=str(authority.decision_event_id),
    )


def _add_source_usages(
    session: AsyncSession,
    report_id: str,
    seed: _ProjectionSeed,
    material: GuideSufficiencyMaterialResult,
) -> None:
    """Persist ordered ART provenance for the new report."""
    for item in material.provenance:
        session.add(
            GuideSufficiencyReportSourceUsage(
                id=str(uuid4()),
                report_id=report_id,
                item_order=item.item_order,
                source_item_id=str(item.source_item_id),
                binding_id=str(item.binding_id),
                content_id=str(item.content_id),
                extraction_usage_id=str(item.extraction_usage_id),
                extraction_attempt_id=str(item.extraction_attempt_id),
                extracted_content_id=str(item.extracted_content_id),
                project_setup_run_id=str(seed.setup_run_id),
                setup_generation=seed.setup_generation,
                canonical_output_sha256=item.canonical_output_sha256,
            )
        )


def _new_operation(
    seed: _ProjectionSeed,
    locked: _LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    authority: ProjectGuideProjectionAuthorityReceipt,
    *,
    component: Literal["guide_sufficiency", "submission_artifact_policy"],
    output_digest: str,
    facts_digest: str,
    report_id: str | None = None,
    policy_id: str | None = None,
    prior: ProjectGuideComponentProjectionOperation | None = None,
) -> ProjectGuideComponentProjectionOperation:
    """Create immutable projection custody from exact lineage and authority."""
    return ProjectGuideComponentProjectionOperation(
        operation_id=identity.operation_id,
        correlation_id=identity.correlation_id,
        component=component,
        project_id=str(seed.project_id),
        guide_id=str(seed.guide_id),
        guide_version=seed.guide_version,
        source_snapshot_id=str(seed.source_snapshot_id),
        source_snapshot_hash=seed.source_snapshot_hash,
        setup_run_id=str(seed.setup_run_id),
        setup_generation=seed.setup_generation,
        celery_task_id=str(locked.celery_task_id),
        source_state_digest=locked.source_state_digest,
        attempt_id=seed.attempt_id,
        request_operation_id=seed.request_operation_id,
        provider_idempotency_key=seed.provider_idempotency_key,
        compilation_id=seed.compilation_id,
        result_hash=seed.result_hash,
        component_hash=seed.component_hash,
        result_schema_version=seed.result_schema_version,
        compilation_agent_name=seed.compilation_agent_name,
        compilation_agent_version=seed.compilation_agent_version,
        material_sha256=(locked.material_sha256 if report_id else None),
        material_byte_count=(locked.material_byte_count if report_id else 0),
        prior_operation_id=(prior.operation_id if prior else None),
        prior_output_id=(prior.output_id if prior else None),
        prior_output_digest=(prior.output_digest if prior else None),
        output_id=identity.output_id,
        report_id=report_id,
        policy_id=policy_id,
        output_digest=output_digest,
        facts_digest=facts_digest,
        authority_resource_digest=authority.resource_context_digest,
        actor_profile_id=str(authority.actor_profile_id),
        identity_link_id=str(authority.identity_link_id),
        service_identity=authority.service_identity,
        action_id=(
            "project.guide_sufficiency.run"
            if component == "guide_sufficiency"
            else "project.submission_artifact_policy.derive"
        ),
        permission_id=(
            "project.guide.manage"
            if component == "guide_sufficiency"
            else "project.effective_policy.manage"
        ),
        authorization_decision_event_id=str(authority.decision_event_id),
    )


async def _projection_operation(
    session: AsyncSession, operation_id: UUID
) -> ProjectGuideComponentProjectionOperation | None:
    """Lock an existing operation for replay validation."""
    from sqlalchemy import select

    return await session.scalar(
        select(ProjectGuideComponentProjectionOperation)
        .where(ProjectGuideComponentProjectionOperation.operation_id == operation_id)
        .with_for_update()
    )


async def _required_sufficiency_operation(
    session: AsyncSession, seed: _ProjectionSeed, locked: _LockedProjection
) -> ProjectGuideComponentProjectionOperation:
    """Lock and validate the policy projection's sufficiency prerequisite."""
    from sqlalchemy import select

    operation = await session.scalar(
        select(ProjectGuideComponentProjectionOperation)
        .where(
            ProjectGuideComponentProjectionOperation.setup_run_id
            == str(seed.setup_run_id),
            ProjectGuideComponentProjectionOperation.setup_generation
            == seed.setup_generation,
            ProjectGuideComponentProjectionOperation.component
            == "guide_sufficiency",
        )
        .with_for_update()
    )
    if operation is None:
        raise ProjectGuideProjectionError("source_state_unavailable")
    expected_authority = projection_authority_digest(
        component="guide_sufficiency",
        identity=ProjectGuideProjectionIdentity(
            operation_id=operation.operation_id,
            correlation_id=operation.correlation_id,
            output_id=operation.output_id,
            actor_profile_id=UUID(operation.actor_profile_id),
            identity_link_id=UUID(operation.identity_link_id),
            service_identity=operation.service_identity,
        ),
        project_id=seed.project_id,
        facts_digest=operation.facts_digest,
    )
    if (
        operation.component != "guide_sufficiency"
        or operation.project_id != str(seed.project_id)
        or operation.guide_id != str(seed.guide_id)
        or operation.guide_version != seed.guide_version
        or operation.source_snapshot_id != str(seed.source_snapshot_id)
        or operation.source_snapshot_hash != seed.source_snapshot_hash
        or operation.setup_run_id != str(seed.setup_run_id)
        or operation.setup_generation != seed.setup_generation
        or operation.celery_task_id != str(locked.celery_task_id)
        or operation.source_state_digest != locked.source_state_digest
        or operation.attempt_id != seed.attempt_id
        or operation.request_operation_id != seed.request_operation_id
        or operation.provider_idempotency_key != seed.provider_idempotency_key
        or operation.compilation_id != seed.compilation_id
        or operation.result_hash != seed.result_hash
        or operation.component_hash != seed.sufficiency_component_hash
        or operation.result_schema_version != seed.result_schema_version
        or operation.compilation_agent_name != seed.compilation_agent_name
        or operation.compilation_agent_version != seed.compilation_agent_version
        or operation.material_sha256 != locked.material_sha256
        or operation.material_byte_count != locked.material_byte_count
        or operation.prior_operation_id is not None
        or operation.prior_output_id is not None
        or operation.prior_output_digest is not None
        or operation.output_id is None
        or operation.report_id != str(operation.output_id)
        or operation.policy_id is not None
        or operation.authority_resource_digest != expected_authority
        or operation.service_identity != _SERVICE_IDENTITY
        or operation.action_id != "project.guide_sufficiency.run"
        or operation.permission_id != "project.guide.manage"
    ):
        raise ProjectGuideProjectionError("source_state_unavailable")
    return operation


async def _report_exists(
    session: AsyncSession, seed: _ProjectionSeed, report_id: UUID
) -> bool:
    """Detect a conflicting report before inserting custody."""
    from sqlalchemy import exists, select

    return bool(
        await session.scalar(
            select(
                exists().where(
                    (GuideSufficiencyReport.id == str(report_id))
                    | (
                        (GuideSufficiencyReport.source_snapshot_id == str(seed.source_snapshot_id))
                        & (GuideSufficiencyReport.setup_generation == seed.setup_generation)
                        & (GuideSufficiencyReport.project_setup_run_id.is_not(None))
                    )
                )
            )
        )
    )


async def _policy_exists(
    session: AsyncSession, seed: _ProjectionSeed, policy_id: UUID
) -> bool:
    """Detect a conflicting policy before inserting custody."""
    from sqlalchemy import exists, select

    return bool(
        await session.scalar(
            select(
                exists().where(
                    (SubmissionArtifactPolicy.id == str(policy_id))
                    | (
                        (SubmissionArtifactPolicy.project_id == str(seed.project_id))
                        & (SubmissionArtifactPolicy.guide_version == seed.guide_version)
                        & (
                            SubmissionArtifactPolicy.policy_version
                            == (
                                "unified-"
                                f"{seed.source_snapshot_hash.removeprefix('sha256:')[:16]}"
                                f"-g{seed.setup_generation}"
                            )
                        )
                    )
                )
            )
        )
    )


def _seed_matches(attempt, request, seed: _ProjectionSeed) -> bool:
    """Compare locked attempt and request custody with preflight lineage."""
    return (
        attempt.status == "compilation_persisted"
        and attempt.persisted_compilation_id == seed.compilation_id
        and attempt.project_id == str(seed.project_id)
        and attempt.guide_id == str(seed.guide_id)
        and attempt.guide_version == seed.guide_version
        and attempt.source_snapshot_id == str(seed.source_snapshot_id)
        and attempt.source_snapshot_hash == seed.source_snapshot_hash
        and attempt.setup_run_id == str(seed.setup_run_id)
        and attempt.setup_generation == seed.setup_generation
        and attempt.provider_idempotency_key == seed.provider_idempotency_key
        and attempt.result_hash == seed.result_hash
        and request.operation_id == seed.request_operation_id
        and request.attempt_id == seed.attempt_id
        and request.project_id == str(seed.project_id)
        and request.guide_id == str(seed.guide_id)
        and request.source_snapshot_id == str(seed.source_snapshot_id)
        and request.setup_run_id == str(seed.setup_run_id)
        and request.setup_generation == seed.setup_generation
    )


def _require_projection_identity(
    identity: ProjectGuideProjectionIdentity,
    seed: _ProjectionSeed,
    component: Literal["guide_sufficiency", "submission_artifact_policy"],
) -> None:
    """Reject an AUTH identity that does not match the component domain."""
    from app.modules.authorization.api import (
        artifact_policy_projection_identity,
        guide_sufficiency_projection_identity,
    )

    expected = (
        guide_sufficiency_projection_identity(
            attempt_id=seed.attempt_id,
            actor_profile_id=identity.actor_profile_id,
            identity_link_id=identity.identity_link_id,
        )
        if component == "guide_sufficiency"
        else artifact_policy_projection_identity(
            attempt_id=seed.attempt_id,
            actor_profile_id=identity.actor_profile_id,
            identity_link_id=identity.identity_link_id,
        )
    )
    if identity != expected:
        raise ProjectGuideProjectionError("service_authority_denied")


def _require_authority(
    authority: ProjectGuideProjectionAuthorityReceipt,
    seed: _ProjectionSeed,
    identity: ProjectGuideProjectionIdentity,
    facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts,
    component: Literal["guide_sufficiency", "submission_artifact_policy"],
) -> None:
    """Require an exact service authority receipt for new projection."""
    facts_digest = (
        guide_sufficiency_projection_facts_digest(facts)
        if component == "guide_sufficiency"
        else artifact_policy_projection_facts_digest(facts)
    )
    expected = projection_authority_digest(
        component=component,
        identity=identity,
        project_id=seed.project_id,
        facts_digest=facts_digest,
    )
    if (
        authority.actor_profile_id != identity.actor_profile_id
        or authority.identity_link_id != identity.identity_link_id
        or authority.service_identity != _SERVICE_IDENTITY
        or authority.resource_context_digest != expected
    ):
        raise ProjectGuideProjectionError("service_authority_denied")


def _require_replay(
    operation: ProjectGuideComponentProjectionOperation,
    seed: _ProjectionSeed,
    identity: ProjectGuideProjectionIdentity,
    facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts,
    output_digest: str,
    output: GuideSufficiencyReport | SubmissionArtifactPolicy | None,
) -> None:
    """Compare every stored custody and output field before replay."""
    component = (
        "guide_sufficiency"
        if isinstance(facts, GuideSufficiencyProjectionFacts)
        else "submission_artifact_policy"
    )
    facts_digest = (
        guide_sufficiency_projection_facts_digest(facts)
        if component == "guide_sufficiency"
        else artifact_policy_projection_facts_digest(facts)
    )
    expected_output_digest = (
        _report_digest(output)
        if isinstance(output, GuideSufficiencyReport)
        else _policy_digest(output)
        if isinstance(output, SubmissionArtifactPolicy)
        else None
    )
    expected_authority_digest = projection_authority_digest(
        component=component,
        identity=identity,
        project_id=seed.project_id,
        facts_digest=facts_digest,
    )
    if isinstance(facts, GuideSufficiencyProjectionFacts):
        material_sha256 = facts.material_sha256
        material_byte_count = facts.material_byte_count
        prior_operation_id = None
        prior_output_id = None
        prior_output_digest = None
        report_id = str(facts.report_id)
        policy_id = None
    else:
        material_sha256 = None
        material_byte_count = 0
        prior_operation_id = facts.prior_operation_id
        prior_output_id = facts.sufficiency_report_id
        prior_output_digest = facts.sufficiency_report_digest
        report_id = None
        policy_id = str(facts.policy_id)
    if (
        operation.operation_id != identity.operation_id
        or operation.correlation_id != identity.correlation_id
        or operation.output_id != identity.output_id
        or operation.component != component
        or operation.project_id != str(seed.project_id)
        or operation.guide_id != str(seed.guide_id)
        or operation.guide_version != seed.guide_version
        or operation.source_snapshot_id != str(seed.source_snapshot_id)
        or operation.source_snapshot_hash != seed.source_snapshot_hash
        or operation.setup_run_id != str(seed.setup_run_id)
        or operation.setup_generation != seed.setup_generation
        or operation.celery_task_id != str(facts.celery_task_id)
        or operation.source_state_digest != facts.source_state_digest
        or operation.attempt_id != seed.attempt_id
        or operation.request_operation_id != seed.request_operation_id
        or operation.provider_idempotency_key != seed.provider_idempotency_key
        or operation.compilation_id != seed.compilation_id
        or operation.result_hash != seed.result_hash
        or operation.component_hash != seed.component_hash
        or operation.result_schema_version != seed.result_schema_version
        or operation.compilation_agent_name != seed.compilation_agent_name
        or operation.compilation_agent_version != seed.compilation_agent_version
        or operation.material_sha256 != material_sha256
        or operation.material_byte_count != material_byte_count
        or operation.prior_operation_id != prior_operation_id
        or operation.prior_output_id != prior_output_id
        or operation.prior_output_digest != prior_output_digest
        or operation.report_id != report_id
        or operation.policy_id != policy_id
        or operation.output_digest != output_digest
        or operation.facts_digest != facts_digest
        or operation.authority_resource_digest != expected_authority_digest
        or operation.actor_profile_id != str(identity.actor_profile_id)
        or operation.identity_link_id != str(identity.identity_link_id)
        or operation.service_identity != _SERVICE_IDENTITY
        or operation.action_id
        != (
            "project.guide_sufficiency.run"
            if component == "guide_sufficiency"
            else "project.submission_artifact_policy.derive"
        )
        or operation.permission_id
        != (
            "project.guide.manage"
            if component == "guide_sufficiency"
            else "project.effective_policy.manage"
        )
        or expected_output_digest != output_digest
    ):
        raise ProjectGuideProjectionError("source_state_unavailable")


def _report_digest(report: GuideSufficiencyReport | None) -> str | None:
    """Recompute the canonical report output digest."""
    if report is None:
        return None
    return canonical_json_hash(
        {
            "domain": "workstream.project_guide_sufficiency_projection.output.v1",
            "facts": {
                "id": report.id,
                "project_id": report.project_id,
                "guide_id": report.guide_id,
                "guide_version": report.guide_version,
                "source_snapshot_id": report.source_snapshot_id,
                "source_snapshot_hash": report.source_snapshot_hash,
                "status": report.status,
                "findings": report.findings,
                "summary": report.summary,
                "agent_name": report.agent_name,
                "agent_version": report.agent_version,
                "project_setup_run_id": report.project_setup_run_id,
                "setup_generation": report.setup_generation,
                "agent_material_sha256": report.agent_material_sha256,
                "agent_material_byte_count": report.agent_material_byte_count,
                "created_by": report.created_by,
            },
        }
    )


def _policy_digest(policy: SubmissionArtifactPolicy | None) -> str | None:
    """Recompute the canonical policy output digest."""
    if policy is None:
        return None
    return canonical_json_hash(
        {
            "domain": (
                "workstream.project_submission_artifact_policy_projection.output.v1"
            ),
            "facts": {
                "id": policy.id,
                "project_id": policy.project_id,
                "guide_id": policy.guide_id,
                "guide_version": policy.guide_version,
                "source_snapshot_id": policy.source_snapshot_id,
                "source_snapshot_hash": policy.source_snapshot_hash,
                "policy_version": policy.policy_version,
                "lifecycle_status": policy.lifecycle_status,
                "policy_body": policy.policy_body,
                "policy_hash": policy.policy_hash,
                "derivation_source": policy.derivation_source,
                "source_material_refs": policy.source_material_refs,
                "derivation_agent_name": policy.derivation_agent_name,
                "derivation_agent_version": policy.derivation_agent_version,
                "created_by": policy.created_by,
                "change_summary": policy.change_summary,
            },
        }
    )


def _receipt(
    seed: _ProjectionSeed,
    identity: ProjectGuideProjectionIdentity,
    output_digest: str,
    component: Literal["guide_sufficiency", "submission_artifact_policy"],
    disposition: Literal["projected", "replayed"],
) -> ProjectGuideProjectionReceipt:
    """Return the bounded receipt shared by create and replay."""
    return ProjectGuideProjectionReceipt(
        operation_id=identity.operation_id,
        attempt_id=seed.attempt_id,
        component=ProjectGuideProjectionComponent(component),
        output_id=identity.output_id,
        output_digest=output_digest,
        disposition=disposition,
    )


__all__ = ("GuideCompilationProjectionService",)
