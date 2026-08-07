"""Flush-only submission-policy authority foundation."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.project_agents import get_project_guide_agent_runtime
from app.interfaces.project_agents import (
    AgentFinding,
    GuideSufficiencyAgentResult,
    ProjectAgentRuntimeError,
)
from app.interfaces.artifact_operations import GuideSufficiencyMaterialPort
from app.modules.actors.service import ResolvedActor
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectSetupServiceCustodyContext,
    ProjectSubmissionArtifactPolicyMutationResourceContext,
    authorization_resource_digest,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.schemas import AdminRole
from app.modules.projects.models import (
    GuideSufficiencyReport,
    SubmissionArtifactPolicy,
    SubmissionPolicyMutationIdempotencyRecord,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.schemas import (
    SubmissionArtifactPolicyCreate,
    SubmissionArtifactPolicyInput,
    SubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyUpdate,
)
from app.modules.projects.service import (
    AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE,
    PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME,
    PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION,
    REPORT_STATUS_TO_AGENT_SUFFICIENCY_STATUS,
    SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_NAME,
    SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_VERSION,
    AgentRuntimeUnavailable,
    GuideEditBlocked,
    GuideNotFound,
    MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE,
    PolicyEditBlocked,
    PolicySetupBlocked,
    ProjectService,
    ProjectServiceError,
    SubmissionArtifactPolicyNotFound,
    agent_submission_artifact_policy_version,
)
from app.modules.projects.submission_policy_mutation_repository import (
    SubmissionPolicyMutationReplayRepository,
)


@dataclass(frozen=True, slots=True)
class SubmissionPolicyReplayFacts:
    """Canonical replay facts supplied by later authorized mutation children."""

    actor_profile_id: str
    identity_link_id: str
    service_identity: str | None
    action_id: str
    idempotency_key: UUID | None
    request_digest: str
    resource_context: ProjectSubmissionArtifactPolicyMutationResourceContext
    operation_id: UUID
    project_id: str
    guide_id: str
    source_snapshot_id: str
    policy_id: str
    setup_run_id: str | None
    setup_generation: int
    setup_task_id: UUID | None
    correlation_id: UUID | None


class SubmissionPolicyMutationConflict(ProjectServiceError):
    """A replay selector, CAS, or locked policy lineage no longer matches."""

    status_code = 409


@dataclass(frozen=True, slots=True)
class SubmissionPolicyMutationOutcome:
    """One route-owned manual policy transaction result."""

    response: SubmissionArtifactPolicyResponse
    replayed: bool


@dataclass(frozen=True, slots=True)
class _ManualPolicyLineage:
    """Exact server-owned facts locked around PREP consumption."""

    guide_version: str
    snapshot_id: UUID
    snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    report_id: UUID
    report_status: Literal["passed", "passed_with_warnings"]
    acknowledgement_digest: str | None
    source_material_refs: tuple[str, ...]
    predecessor_id: UUID | None = None
    predecessor_version: str | None = None
    predecessor_status: str | None = None
    predecessor_hash: str | None = None


class SubmissionPolicyMutationService:
    """Stage replay custody without owning commit, rollback, or product writes."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        material: GuideSufficiencyMaterialPort | None = None,
    ) -> None:
        self._session = session
        self._replay = SubmissionPolicyMutationReplayRepository(session)
        self._projects = ProjectRepository(session)
        self._admin = AdminAuthorizationRepository(session)
        self._validation = ProjectService(session, guide_sufficiency_material=material)

    @asynccontextmanager
    async def _execution_fence(self, actor_profile_id: str, action: ActionId, key: UUID):
        """Serialize one service-owned external derivation across processes."""
        engine = self._session.bind
        if not isinstance(engine, AsyncEngine):
            raise RuntimeError("submission-policy derivation requires an async database engine")
        digest = canonical_json_hash(
            {
                "domain": "workstream.submission_policy.execution_fence.v1",
                "actor_profile_id": actor_profile_id,
                "action_id": action.value,
                "key": str(key),
            }
        )
        lock_key = int(digest.removeprefix("sha256:")[:16], 16)
        if lock_key >= 2**63:
            lock_key -= 2**64
        async with engine.connect() as connection:
            acquired = await connection.scalar(
                text("select pg_try_advisory_lock(:lock_key)"), {"lock_key": lock_key}
            )
            if acquired is not True:
                raise SubmissionPolicyMutationConflict("idempotency_pending")
            try:
                yield
            finally:
                await connection.execute(
                    text("select pg_advisory_unlock(:lock_key)"), {"lock_key": lock_key}
                )

    @staticmethod
    def _stable_uuid(*parts: object) -> UUID:
        return uuid5(NAMESPACE_URL, "workstream:submission-policy:" + ":".join(map(str, parts)))

    def _operation_identity(
        self,
        *,
        action: ActionId,
        resolved: ResolvedActor,
        project_id: UUID,
        predecessor_id: UUID | None,
        key: UUID,
    ) -> tuple[UUID, UUID]:
        """Derive the stable operation and committed-policy identities once."""
        parts = (
            action.value,
            resolved.profile.id,
            resolved.identity_link.id,
            project_id,
            predecessor_id or "create",
            key,
        )
        return self._stable_uuid("operation", *parts), self._stable_uuid("policy", *parts)

    @staticmethod
    def _prove_human_authority(decision, project_id: UUID) -> None:
        if (
            decision.matched_authority_kind is not MatchedAuthorityKind.ADMIN_ROLE_GRANT
            or decision.matched_grant_id is None
            or decision.matched_scope_project_id not in {None, project_id}
        ):
            raise RuntimeError("manual policy mutation lacked covered Project Manager authority")

    @staticmethod
    def _acknowledgement_digest(
        report: GuideSufficiencyReport,
        project_id: UUID,
    ) -> str | None:
        if report.status != "passed_with_warnings":
            return None
        values = {
            "actor_profile_id": report.warnings_acknowledged_by_actor_profile_id,
            "identity_link_id": report.warnings_acknowledged_via_identity_link_id,
            "grant_id": (
                str(report.warnings_acknowledged_by_admin_role_grant_id)
                if report.warnings_acknowledged_by_admin_role_grant_id is not None
                else None
            ),
            "scope_type": report.warning_acknowledgement_scope_type,
            "scope_project_id": report.warning_acknowledgement_scope_project_id,
            "action_id": report.warning_acknowledgement_action_id,
            "decision_event_id": report.warning_acknowledgement_decision_event_id,
            "acknowledged_at": (
                report.warnings_acknowledged_at.isoformat()
                if report.warnings_acknowledged_at is not None
                else None
            ),
        }
        if (
            any(value is None for value in values.values())
            or values["scope_project_id"] != str(project_id)
            or values["scope_type"] not in {"system", "project"}
            or values["action_id"] != ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE.value
        ):
            raise PolicySetupBlocked(
                "guide sufficiency warnings require authorized Project Manager acknowledgement"
            )
        return canonical_json_hash(
            {
                "domain": "workstream.guide_sufficiency.warning_acknowledgement.v1",
                "report_id": report.id,
                **values,
            }
        )

    async def _lineage(
        self,
        project_id: UUID,
        guide_id: UUID,
        snapshot_id: UUID,
        *,
        lock: bool,
        predecessor_id: UUID | None = None,
    ) -> _ManualPolicyLineage:
        project = await self._projects.get_project(str(project_id), for_update=lock)
        if project is None:
            raise GuideNotFound("project not found")
        guide = (
            await self._projects.lock_project_guide(str(guide_id))
            if lock
            else await self._projects.get_guide(str(guide_id))
        )
        if guide is None or guide.project_id != str(project_id):
            raise GuideNotFound("guide not found")
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can receive submission artifact policies")
        try:
            snapshot = (
                await self._projects.lock_latest_guide_source_snapshot(
                    str(project_id), str(guide_id), guide.version
                )
                if lock
                else await self._projects.get_latest_guide_source_snapshot(
                    str(project_id), str(guide_id), guide.version
                )
            )
        except ProjectRepositoryIntegrityError as exc:
            raise PolicySetupBlocked("latest guide source snapshot is ambiguous") from exc
        if snapshot is None or snapshot.id != str(snapshot_id):
            raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
        await self._validation.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        setup = (
            await self._projects.lock_latest_project_setup_run(
                str(project_id), str(guide_id), guide.version
            )
            if lock
            else await self._projects.get_latest_project_setup_run(str(project_id), str(guide_id))
        )
        if setup is None:
            raise PolicySetupBlocked("authoritative guide sufficiency report is required")
        if (
            setup.guide_version != guide.version
            or setup.source_snapshot_id != snapshot.id
            or setup.source_snapshot_hash != snapshot.bundle_hash
        ):
            raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
        report = await self._projects.get_sufficiency_report_for_snapshot(snapshot.id)
        if report is None:
            raise PolicySetupBlocked("authoritative guide sufficiency report is required")
        if lock:
            report = await self._projects.lock_guide_sufficiency_report(
                report.id, str(project_id), str(guide_id), guide.version
            )
        if (
            report is None
            or report.project_setup_run_id != setup.id
            or report.setup_generation != setup.setup_generation
            or report.source_snapshot_hash != snapshot.bundle_hash
            or report.status not in {"passed", "passed_with_warnings"}
        ):
            raise PolicySetupBlocked("authoritative guide sufficiency report does not allow policy")
        acknowledgement_digest = self._acknowledgement_digest(report, project_id)
        source_refs = tuple(await self._validation.verified_source_material_refs(report))
        predecessor = None
        if predecessor_id is not None:
            predecessor = (
                await self._projects.lock_submission_artifact_policy(str(predecessor_id))
                if lock
                else await self._projects.get_submission_artifact_policy(str(predecessor_id))
            )
            if (
                predecessor is None
                or predecessor.project_id != str(project_id)
                or predecessor.guide_id != str(guide_id)
                or predecessor.source_snapshot_id != snapshot.id
            ):
                raise SubmissionArtifactPolicyNotFound("submission artifact policy not found")
            if predecessor.lifecycle_status != "draft":
                if predecessor.lifecycle_status == "approved":
                    raise PolicyEditBlocked("approved submission artifact policies are immutable")
                raise PolicyEditBlocked("only a current draft policy can be replaced")
            if predecessor.derivation_source != MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
                raise PolicyEditBlocked("agent-derived policy summaries are immutable")
        return _ManualPolicyLineage(
            guide_version=guide.version,
            snapshot_id=snapshot_id,
            snapshot_hash=snapshot.bundle_hash,
            setup_run_id=UUID(setup.id),
            setup_generation=setup.setup_generation,
            report_id=UUID(report.id),
            report_status=cast(Literal["passed", "passed_with_warnings"], report.status),
            acknowledgement_digest=acknowledgement_digest,
            source_material_refs=source_refs,
            predecessor_id=UUID(predecessor.id) if predecessor is not None else None,
            predecessor_version=predecessor.policy_version if predecessor is not None else None,
            predecessor_status=predecessor.lifecycle_status if predecessor is not None else None,
            predecessor_hash=predecessor.policy_hash if predecessor is not None else None,
        )

    @staticmethod
    def _request_digest(
        *,
        action: ActionId,
        route: str,
        resolved: ResolvedActor,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        policy_id: UUID,
        successor_id: UUID | None,
        successor_version: str,
        source_snapshot_id: UUID,
        body: dict,
    ) -> str:
        replay_value = {
            "action_id": action.value,
            "route": route,
            "actor_profile_id": resolved.profile.id,
            "identity_link_id": resolved.identity_link.id,
            "idempotency_key": str(key),
            "project_id": str(project_id),
            "guide_id": str(guide_id),
            "source_snapshot_id": str(source_snapshot_id),
            "policy_id": str(policy_id),
            "successor_policy_id": str(successor_id) if successor_id is not None else None,
            "successor_policy_version": successor_version,
            "body": body,
        }
        digest = canonical_json_hash(
            {"domain": "workstream.submission_policy.manual.idempotency.v1", **replay_value}
        )
        return digest

    @staticmethod
    def _resource(
        *,
        project_id: UUID,
        guide_id: UUID,
        policy_id: UUID,
        policy_version: str,
        successor_id: UUID | None,
        successor_version: str | None,
        operation_id: UUID,
        request_digest: str,
        lineage: _ManualPolicyLineage,
        target_kind: Literal["create", "update"],
    ) -> ProjectSubmissionArtifactPolicyMutationResourceContext:
        return ProjectSubmissionArtifactPolicyMutationResourceContext(
            resource_type="project_submission_artifact_policy_mutation",
            resource_id=successor_id or policy_id,
            operation_id=operation_id,
            request_digest=request_digest,
            scope_project_id=project_id,
            guide_id=guide_id,
            guide_version=lineage.guide_version,
            source_snapshot_id=lineage.snapshot_id,
            source_snapshot_hash=lineage.snapshot_hash,
            target_kind=target_kind,
            execution_kind="human",
            policy_id=policy_id,
            policy_version=policy_version,
            policy_generation=lineage.setup_generation,
            setup_generation=lineage.setup_generation,
            sufficiency_report_id=lineage.report_id,
            sufficiency_status=lineage.report_status,
            sufficiency_acknowledgement_digest=lineage.acknowledgement_digest,
            policy_status=lineage.predecessor_status,
            policy_digest=lineage.predecessor_hash,
            successor_policy_id=successor_id,
            successor_policy_version=successor_version,
        )

    async def _prepare(
        self,
        prepared: PreparedAuthorizationService,
        action: ActionId,
        caller: PreparedAuthorizationInput,
        project_id: UUID,
        resource: ProjectSubmissionArtifactPolicyMutationResourceContext,
    ):
        try:
            return await prepared.prepare(
                action,
                caller,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=project_id,
                ),
            )
        except PreparedAuthorizationUnsupported as exc:
            await prepared.deny_unsupported(action, caller, resource, exc)

    async def _require_pm_admission(
        self,
        *,
        resolved: ResolvedActor,
        project_id: UUID,
    ) -> None:
        """Conceal product lookups unless a covered PM grant exists.

        This guard never grants mutation authority. The sole durable decision
        is the later PREP consumption against exact locked product facts.
        """
        grant = await self._admin.find_effective_grant(
            UUID(resolved.profile.id),
            PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
            scope_project_id=project_id,
            allowed_roles=frozenset({AdminRole.PROJECT_MANAGER}),
        )
        if grant is None:
            raise SubmissionArtifactPolicyNotFound("submission artifact policy not found")

    async def _manual_mutation(
        self,
        *,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        predecessor_id: UUID | None,
        source_snapshot_id: UUID,
        policy_version: str,
        expected_policy_hash: str | None,
        policy_body: dict,
        change_summary: str | None,
    ) -> SubmissionPolicyMutationOutcome:
        action = (
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE
            if predecessor_id is not None
            else ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE
        )
        route = (
            "PATCH /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}"
            if predecessor_id is not None
            else "POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies"
        )
        operation_id, committed_policy_id = self._operation_identity(
            action=action,
            resolved=resolved,
            project_id=project_id,
            predecessor_id=predecessor_id,
            key=key,
        )
        canonical_body, policy_hash = self._validation.canonical_manual_submission_policy_body(
            policy_body
        )
        initial = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=False,
            predecessor_id=predecessor_id,
        )
        if predecessor_id is not None and initial.predecessor_hash != expected_policy_hash:
            raise SubmissionPolicyMutationConflict("submission_policy_precondition_failed")
        body = {
            "source_snapshot_id": str(source_snapshot_id),
            "policy_version": policy_version,
            "expected_policy_hash": expected_policy_hash,
            "policy_body": canonical_body,
            "change_summary": change_summary,
        }
        resource_policy_id = predecessor_id or committed_policy_id
        digest = self._request_digest(
            action=action,
            route=route,
            resolved=resolved,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            policy_id=resource_policy_id,
            successor_id=committed_policy_id if predecessor_id is not None else None,
            successor_version=policy_version,
            source_snapshot_id=initial.snapshot_id,
            body=body,
        )
        initial_resource = self._resource(
            project_id=project_id,
            guide_id=guide_id,
            policy_id=resource_policy_id,
            policy_version=initial.predecessor_version or policy_version,
            successor_id=committed_policy_id if predecessor_id is not None else None,
            successor_version=policy_version if predecessor_id is not None else None,
            operation_id=operation_id,
            request_digest=digest,
            lineage=initial,
            target_kind="update" if predecessor_id is not None else "create",
        )
        caller = PreparedAuthorizationInput(
            idempotency_key=key,
            request_value=cast(JsonValue, initial_resource.model_dump(mode="json")),
        )
        handle = await self._prepare(prepared, action, caller, project_id, initial_resource)
        final = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=True,
            predecessor_id=predecessor_id,
        )
        if final != initial or (
            predecessor_id is not None and final.predecessor_hash != expected_policy_hash
        ):
            raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
        final_resource = self._resource(
            project_id=project_id,
            guide_id=guide_id,
            policy_id=resource_policy_id,
            policy_version=final.predecessor_version or policy_version,
            successor_id=committed_policy_id if predecessor_id is not None else None,
            successor_version=policy_version if predecessor_id is not None else None,
            operation_id=operation_id,
            request_digest=digest,
            lineage=final,
            target_kind="update" if predecessor_id is not None else "create",
        )
        decision = await prepared.consume(handle, action, caller, final_resource)
        self._prove_human_authority(decision, project_id)
        facts = SubmissionPolicyReplayFacts(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            service_identity=None,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context=final_resource,
            operation_id=operation_id,
            project_id=str(project_id),
            guide_id=str(guide_id),
            source_snapshot_id=str(source_snapshot_id),
            policy_id=str(committed_policy_id),
            setup_run_id=None,
            setup_generation=final.setup_generation,
            setup_task_id=None,
            correlation_id=None,
        )
        disposition, replay = await self.reserve_replay(facts)
        if disposition == "replayed":
            if replay.response_json is None or replay.committed_policy_id != str(
                committed_policy_id
            ):
                raise SubmissionPolicyMutationConflict("idempotency_mismatch")
            return SubmissionPolicyMutationOutcome(
                SubmissionArtifactPolicyResponse.model_validate(replay.response_json), True
            )
        if disposition != "claimed":
            raise SubmissionPolicyMutationConflict(f"idempotency_{disposition}")
        policy = SubmissionArtifactPolicy(
            id=str(committed_policy_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version=final.guide_version,
            source_snapshot_id=str(source_snapshot_id),
            source_snapshot_hash=final.snapshot_hash,
            policy_version=policy_version,
            lifecycle_status="draft",
            policy_body=canonical_body,
            policy_hash=policy_hash,
            derivation_source=MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE,
            source_material_refs=list(final.source_material_refs),
            derivation_agent_name=None,
            derivation_agent_version=None,
            created_by=resolved.profile.id,
            created_by_actor_profile_id=resolved.profile.id,
            created_via_identity_link_id=resolved.identity_link.id,
            created_by_admin_role_grant_id=decision.matched_grant_id,
            created_by_service_identity=None,
            creation_scope_type=(
                "system" if decision.matched_scope_project_id is None else "project"
            ),
            creation_scope_project_id=str(project_id),
            creation_action_id=action.value,
            creation_decision_event_id=str(decision.decision_id),
            supersedes_policy_id=str(predecessor_id) if predecessor_id is not None else None,
            change_summary=change_summary,
        )
        try:
            await self._projects.add_submission_artifact_policy(policy)
        except IntegrityError as exc:
            raise SubmissionPolicyMutationConflict("submission_policy_version_conflict") from exc
        if predecessor_id is not None:
            superseded = await self._projects.supersede_draft_submission_artifact_policy(
                str(predecessor_id)
            )
            if not superseded:
                raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
            await self._session.flush()
        response = SubmissionArtifactPolicyResponse.model_validate(policy)
        await self.complete_replay(
            facts,
            response_json=response.model_dump(mode="json"),
            committed_policy_id=policy.id,
        )
        return SubmissionPolicyMutationOutcome(response, False)

    async def _existing_manual_replay(
        self,
        *,
        resolved: ResolvedActor,
        key: UUID,
        action: ActionId,
        project_id: UUID,
        guide_id: UUID,
        selected_policy_id: UUID,
        successor_policy_id: UUID | None,
        successor_policy_version: str,
        expected_policy_hash: str | None,
        source_snapshot_id: UUID | None,
        policy_body: dict | None,
        change_summary: str | None,
    ) -> SubmissionPolicyMutationOutcome | None:
        """Classify an existing operation without coupling replay to live lineage."""
        operation_id, derived_policy_id = self._operation_identity(
            action=action,
            resolved=resolved,
            project_id=project_id,
            predecessor_id=(
                selected_policy_id
                if action is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE
                else None
            ),
            key=key,
        )
        expected_committed_id = successor_policy_id or selected_policy_id
        if expected_committed_id != derived_policy_id:
            raise SubmissionPolicyMutationConflict("idempotency_mismatch")
        replay = await self._replay.find_by_operation(operation_id)
        if replay is None:
            return None
        if (
            replay.actor_profile_id != resolved.profile.id
            or replay.identity_link_id != resolved.identity_link.id
            or replay.action_id != action.value
            or replay.idempotency_key != key
            or replay.project_id != str(project_id)
            or replay.guide_id != str(guide_id)
        ):
            raise SubmissionPolicyMutationConflict("idempotency_mismatch")
        resource = ProjectSubmissionArtifactPolicyMutationResourceContext.model_validate_json(
            json.dumps(replay.resource_context_json)
        )
        response = (
            SubmissionArtifactPolicyResponse.model_validate(replay.response_json)
            if replay.status == "committed" and replay.response_json is not None
            else None
        )
        snapshot_id = source_snapshot_id or resource.source_snapshot_id
        predecessor = None
        if policy_body is None or (change_summary is None and response is None):
            predecessor = await self._projects.get_submission_artifact_policy(
                str(selected_policy_id)
            )
        effective_policy_body = policy_body or (
            response.policy_body
            if response is not None
            else predecessor.policy_body
            if predecessor is not None
            else None
        )
        if effective_policy_body is None:
            raise SubmissionPolicyMutationConflict("idempotency_mismatch")
        canonical_body, policy_hash = self._validation.canonical_manual_submission_policy_body(
            effective_policy_body
        )
        effective_change_summary = (
            change_summary
            if change_summary is not None
            else response.change_summary
            if response is not None
            else predecessor.change_summary
            if predecessor is not None
            else None
        )
        body = {
            "source_snapshot_id": str(snapshot_id),
            "policy_version": successor_policy_version,
            "expected_policy_hash": expected_policy_hash,
            "policy_body": canonical_body,
            "change_summary": effective_change_summary,
        }
        route = (
            "PATCH /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}"
            if action is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE
            else "POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies"
        )
        expected_digest = self._request_digest(
            action=action,
            route=route,
            resolved=resolved,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            policy_id=selected_policy_id,
            successor_id=successor_policy_id,
            successor_version=successor_policy_version,
            source_snapshot_id=snapshot_id,
            body=body,
        )
        expected_target = (
            "update" if action is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE else "create"
        )
        if (
            resource.target_kind != expected_target
            or resource.operation_id != operation_id
            or resource.request_digest != expected_digest
            or replay.request_digest != expected_digest
            or replay.resource_context_digest != authorization_resource_digest(resource)
            or resource.scope_project_id != project_id
            or resource.guide_id != guide_id
            or resource.source_snapshot_id != snapshot_id
            or resource.policy_id != selected_policy_id
            or resource.policy_digest != expected_policy_hash
            or resource.successor_policy_id != successor_policy_id
            or resource.successor_policy_version
            != (successor_policy_version if successor_policy_id is not None else None)
        ):
            raise SubmissionPolicyMutationConflict("idempotency_mismatch")
        if replay.status == "pending":
            raise SubmissionPolicyMutationConflict("idempotency_pending")
        if response is None or replay.committed_policy_id is None:
            raise SubmissionPolicyMutationConflict("idempotency_mismatch")
        committed = await self._projects.get_submission_artifact_policy(replay.committed_policy_id)
        if (
            response.policy_body != canonical_body
            or response.policy_hash != policy_hash
            or response.policy_version != successor_policy_version
            or response.change_summary != effective_change_summary
            or committed is None
            or committed.id != replay.committed_policy_id
            or committed.policy_hash != response.policy_hash
            or committed.creation_action_id != action.value
        ):
            raise SubmissionPolicyMutationConflict("idempotency_mismatch")
        return SubmissionPolicyMutationOutcome(response, True)

    async def create_manual(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        payload: SubmissionArtifactPolicyCreate,
    ) -> SubmissionPolicyMutationOutcome:
        """Create one manually authored policy draft under exact PM authority."""
        source_snapshot_id = payload.source_snapshot_id
        action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE
        _operation_id, policy_id = self._operation_identity(
            action=action,
            resolved=resolved,
            project_id=project_id,
            predecessor_id=None,
            key=key,
        )
        await self._require_pm_admission(resolved=resolved, project_id=project_id)
        replay = await self._existing_manual_replay(
            resolved=resolved,
            key=key,
            action=action,
            project_id=project_id,
            guide_id=guide_id,
            selected_policy_id=policy_id,
            successor_policy_id=None,
            successor_policy_version=payload.policy_version,
            expected_policy_hash=None,
            source_snapshot_id=source_snapshot_id,
            policy_body=payload.policy_body.model_dump(mode="json"),
            change_summary=payload.change_summary,
        )
        if replay is not None:
            return replay
        return await self._manual_mutation(
            resolved=resolved,
            prepared=prepared,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            predecessor_id=None,
            source_snapshot_id=source_snapshot_id,
            policy_version=payload.policy_version,
            expected_policy_hash=None,
            policy_body=payload.policy_body.model_dump(mode="json"),
            change_summary=payload.change_summary,
        )

    async def update_manual(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        policy_id: UUID,
        payload: SubmissionArtifactPolicyUpdate,
    ) -> SubmissionPolicyMutationOutcome:
        """Append one authorized replacement for a selected manual draft."""
        action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE
        _operation_id, successor_id = self._operation_identity(
            action=action,
            resolved=resolved,
            project_id=project_id,
            predecessor_id=policy_id,
            key=key,
        )
        await self._require_pm_admission(resolved=resolved, project_id=project_id)
        replay = await self._existing_manual_replay(
            resolved=resolved,
            key=key,
            action=action,
            project_id=project_id,
            guide_id=guide_id,
            selected_policy_id=policy_id,
            successor_policy_id=successor_id,
            successor_policy_version=payload.successor_policy_version,
            expected_policy_hash=payload.expected_policy_hash,
            source_snapshot_id=None,
            policy_body=(
                payload.policy_body.model_dump(mode="json")
                if payload.policy_body is not None
                else None
            ),
            change_summary=payload.change_summary,
        )
        if replay is not None:
            return replay
        predecessor = await self._projects.get_submission_artifact_policy(str(policy_id))
        if (
            predecessor is None
            or predecessor.project_id != str(project_id)
            or predecessor.guide_id != str(guide_id)
        ):
            raise SubmissionArtifactPolicyNotFound("submission artifact policy not found")
        policy_body = (
            payload.policy_body.model_dump(mode="json")
            if payload.policy_body is not None
            else predecessor.policy_body
        )
        return await self._manual_mutation(
            resolved=resolved,
            prepared=prepared,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            predecessor_id=policy_id,
            source_snapshot_id=UUID(predecessor.source_snapshot_id),
            policy_version=payload.successor_policy_version,
            expected_policy_hash=payload.expected_policy_hash,
            policy_body=policy_body,
            change_summary=(
                payload.change_summary
                if payload.change_summary is not None
                else predecessor.change_summary
            ),
        )

    @staticmethod
    def _prove_setup_service_authority(decision) -> None:
        if (
            decision.matched_authority_kind is not MatchedAuthorityKind.FIXED_SERVICE
            or decision.matched_grant_id is not None
        ):
            raise RuntimeError("policy derivation lacked fixed setup-service authority")

    @staticmethod
    def _service_identity(
        actor_profile_id: UUID,
        identity_link_id: UUID,
        custody,
    ) -> tuple[UUID, UUID, UUID]:
        operation_id = SubmissionPolicyMutationService._stable_uuid(
            "derive-operation", actor_profile_id, identity_link_id, custody.setup_run_id,
            custody.setup_generation,
        )
        policy_id = SubmissionPolicyMutationService._stable_uuid("derive-policy", operation_id)
        replay_key = SubmissionPolicyMutationService._stable_uuid("derive-replay", operation_id)
        return operation_id, policy_id, replay_key

    @staticmethod
    def _service_resource(
        *,
        project_id: UUID,
        guide_id: UUID,
        policy_id: UUID,
        operation_id: UUID,
        request_digest: str,
        lineage: _ManualPolicyLineage,
        custody,
    ) -> ProjectSubmissionArtifactPolicyMutationResourceContext:
        return ProjectSubmissionArtifactPolicyMutationResourceContext(
            resource_type="project_submission_artifact_policy_mutation",
            resource_id=policy_id,
            operation_id=operation_id,
            request_digest=request_digest,
            scope_project_id=project_id,
            guide_id=guide_id,
            guide_version=lineage.guide_version,
            source_snapshot_id=lineage.snapshot_id,
            source_snapshot_hash=lineage.snapshot_hash,
            target_kind="derive",
            execution_kind="setup_service",
            policy_id=policy_id,
            policy_version=agent_submission_artifact_policy_version(lineage.snapshot_hash),
            policy_generation=lineage.setup_generation,
            setup_generation=lineage.setup_generation,
            sufficiency_report_id=lineage.report_id,
            sufficiency_status=lineage.report_status,
            sufficiency_acknowledgement_digest=lineage.acknowledgement_digest,
            stale_output_digest=custody.stale_output_digest,
            setup_service_custody=custody,
        )

    async def resolve_setup_service_custody(
        self,
        *,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        setup_run_id: UUID,
        setup_generation: int,
        task_id: UUID,
        correlation_id: UUID,
    ):
        """Resolve the exact persisted derivation step to the closed AUTH selector."""
        lineage = await self._lineage(project_id, guide_id, source_snapshot_id, lock=False)
        setup = await self._projects.lock_project_setup_run(str(setup_run_id))
        running = (
            setup is not None
            and setup.status == "running_policy_derivation_agent"
            and setup.current_step == "submission_artifact_policy_derivation"
            and setup.output_submission_artifact_policy_id is None
        )
        completed = (
            setup is not None
            and setup.status == "policy_draft_ready"
            and setup.current_step == "submission_artifact_policy_derivation"
            and setup.output_submission_artifact_policy_id is not None
        )
        if (
            lineage.setup_run_id != setup_run_id
            or lineage.setup_generation != setup_generation
            or setup is None
            or not (running or completed)
            or setup.celery_task_id != str(task_id)
            or setup.output_sufficiency_report_id != str(lineage.report_id)
            or correlation_id != uuid5(NAMESPACE_URL, f"{task_id}:correlation")
        ):
            raise SubmissionPolicyMutationConflict("project_setup_run_context_mismatch")
        stale_output_digest = self._policy_derivation_stale_output_digest(setup)

        return ProjectSetupServiceCustodyContext(
            setup_run_id=setup_run_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=source_snapshot_id,
            setup_generation=setup_generation,
            expected_step="submission_artifact_policy",
            task_id=task_id,
            correlation_id=correlation_id,
            stale_output_digest=stale_output_digest,
        )

    @staticmethod
    def _policy_derivation_stale_output_digest(setup) -> str:
        return canonical_json_hash(
            {
                "domain": "workstream.project_setup.policy_derivation_stale_output.v1",
                "setup_run_id": setup.id,
                "setup_generation": setup.setup_generation,
                "current_step": setup.current_step,
                "sufficiency_report_id": setup.output_sufficiency_report_id,
                "submission_artifact_policy_id": None,
            }
        )

    async def _lock_complete_derivation_lineage(
        self,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        *,
        expected_policy_id: UUID | None = None,
    ) -> _ManualPolicyLineage:
        """Lock the shared 12F3/12F4/12G policy chain in its total order."""
        lineage = await self._lineage(
            project_id, guide_id, source_snapshot_id, lock=True
        )
        policies = await self._projects.lock_submission_artifact_policies(
            str(project_id), str(guide_id), lineage.guide_version
        )
        current = [
            policy
            for policy in policies
            if policy.lifecycle_status in {"draft", "approved"}
        ]
        if current and not (
            expected_policy_id is not None
            and len(current) == 1
            and current[0].id == str(expected_policy_id)
            and current[0].derivation_source
            == AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE
        ):
            raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
        effective = await self._projects.lock_effective_submission_artifact_policy(
            str(project_id), lineage.guide_version, str(source_snapshot_id)
        )
        if effective is not None:
            await self._projects.lock_compiled_pre_submit_checker_policy(effective.id)
        await self._projects.lock_post_submit_checker_policy_for_guide(
            str(project_id), lineage.guide_version
        )
        return lineage

    @staticmethod
    def _require_exact_running_custody(setup, lineage, custody) -> None:
        expected_stale = SubmissionPolicyMutationService._policy_derivation_stale_output_digest(
            setup
        )
        if (
            setup.id != str(custody.setup_run_id)
            or setup.project_id != str(custody.scope_project_id)
            or setup.guide_id != str(custody.guide_id)
            or setup.source_snapshot_id != str(custody.source_snapshot_id)
            or setup.setup_generation != custody.setup_generation
            or setup.status != "running_policy_derivation_agent"
            or setup.current_step != "submission_artifact_policy_derivation"
            or setup.celery_task_id != str(custody.task_id)
            or setup.output_sufficiency_report_id != str(lineage.report_id)
            or setup.output_submission_artifact_policy_id is not None
            or custody.correlation_id
            != uuid5(NAMESPACE_URL, f"{custody.task_id}:correlation")
            or custody.stale_output_digest != expected_stale
        ):
            raise SubmissionPolicyMutationConflict("project_setup_run_context_mismatch")

    @staticmethod
    def _require_exact_completed_custody(setup, lineage, custody, policy_id: UUID) -> None:
        if (
            setup.id != str(custody.setup_run_id)
            or setup.project_id != str(custody.scope_project_id)
            or setup.guide_id != str(custody.guide_id)
            or setup.source_snapshot_id != str(custody.source_snapshot_id)
            or setup.setup_generation != custody.setup_generation
            or setup.status != "policy_draft_ready"
            or setup.current_step != "submission_artifact_policy_derivation"
            or setup.celery_task_id != str(custody.task_id)
            or setup.output_sufficiency_report_id != str(lineage.report_id)
            or setup.output_submission_artifact_policy_id != str(policy_id)
            or custody.correlation_id
            != uuid5(NAMESPACE_URL, f"{custody.task_id}:correlation")
        ):
            raise SubmissionPolicyMutationConflict("project_setup_run_context_mismatch")

    @asynccontextmanager
    async def run_setup_service(
        self,
        *,
        actor_profile_id: UUID,
        identity_link_id: UUID,
        prepared: PreparedAuthorizationService,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        custody,
    ):
        """Derive one policy under fresh, single-use fixed-service authority."""
        operation_id, policy_id, replay_key = self._service_identity(
            actor_profile_id, identity_link_id, custody
        )
        async with self._execution_fence(
            str(actor_profile_id), ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE, replay_key
        ):
            yield await self._run_setup_derivation(
                actor_profile_id=actor_profile_id,
                identity_link_id=identity_link_id,
                prepared=prepared,
                project_id=project_id,
                guide_id=guide_id,
                source_snapshot_id=source_snapshot_id,
                custody=custody,
                operation_id=operation_id,
                policy_id=policy_id,
            )

    async def _run_setup_derivation(
        self,
        *,
        actor_profile_id: UUID,
        identity_link_id: UUID,
        prepared: PreparedAuthorizationService,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        custody,
        operation_id: UUID,
        policy_id: UUID,
    ) -> SubmissionPolicyMutationOutcome:
        action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE
        initial = await self._lineage(project_id, guide_id, source_snapshot_id, lock=False)
        preflight_digest = canonical_json_hash(
            {"domain": "workstream.submission_policy.derive.preflight.v1", "custody": custody.model_dump(mode="json")}
        )
        preflight_resource = self._service_resource(
            project_id=project_id, guide_id=guide_id, policy_id=policy_id,
            operation_id=operation_id, request_digest=preflight_digest,
            lineage=initial, custody=custody,
        )
        preflight_caller = PreparedAuthorizationInput(
            idempotency_key=operation_id,
            request_value=cast(JsonValue, preflight_resource.model_dump(mode="json")),
        )
        handle = await self._prepare(
            prepared, action, preflight_caller, project_id, preflight_resource
        )
        decision = await prepared.consume(handle, action, preflight_caller, preflight_resource)
        self._prove_setup_service_authority(decision)
        await self._session.rollback()

        existing_replay = await self._replay.find_by_operation(operation_id)
        if existing_replay is not None:
            if (
                existing_replay.actor_profile_id != str(actor_profile_id)
                or existing_replay.identity_link_id != str(identity_link_id)
                or existing_replay.service_identity != ServiceIdentity.PROJECT_SETUP.value
                or existing_replay.action_id != action.value
                or existing_replay.setup_run_id != str(custody.setup_run_id)
                or existing_replay.setup_generation != custody.setup_generation
                or existing_replay.setup_task_id != custody.task_id
                or existing_replay.correlation_id != custody.correlation_id
                or existing_replay.status != "committed"
                or existing_replay.response_json is None
                or existing_replay.committed_policy_id != str(policy_id)
            ):
                raise SubmissionPolicyMutationConflict("idempotency_mismatch")
            replay_resource = (
                ProjectSubmissionArtifactPolicyMutationResourceContext.model_validate_json(
                    json.dumps(existing_replay.resource_context_json)
                )
            )
            final = await self._lock_complete_derivation_lineage(
                project_id,
                guide_id,
                source_snapshot_id,
                expected_policy_id=policy_id,
            )
            if (
                final != initial
                or existing_replay.resource_context_digest
                != authorization_resource_digest(replay_resource)
                or replay_resource
                != self._service_resource(
                    project_id=project_id,
                    guide_id=guide_id,
                    policy_id=policy_id,
                    operation_id=operation_id,
                    request_digest=existing_replay.request_digest,
                    lineage=final,
                    custody=custody,
                )
            ):
                raise SubmissionPolicyMutationConflict("idempotency_mismatch")
            setup = await self._projects.lock_project_setup_run(str(custody.setup_run_id))
            if setup is None:
                raise SubmissionPolicyMutationConflict("project_setup_run_context_mismatch")
            self._require_exact_completed_custody(setup, final, custody, policy_id)
            persisted = await self._projects.get_submission_artifact_policy(str(policy_id))
            persisted_response = (
                SubmissionArtifactPolicyResponse.model_validate(persisted)
                if persisted is not None
                else None
            )
            replay_response = SubmissionArtifactPolicyResponse.model_validate(
                existing_replay.response_json
            )
            if persisted_response is None or replay_response != persisted_response:
                raise SubmissionPolicyMutationConflict("idempotency_mismatch")
            replay_caller = PreparedAuthorizationInput(
                idempotency_key=operation_id,
                request_value=cast(JsonValue, replay_resource.model_dump(mode="json")),
            )
            replay_handle = await self._prepare(
                prepared, action, replay_caller, project_id, replay_resource
            )
            replay_decision = await prepared.consume(
                replay_handle, action, replay_caller, replay_resource
            )
            self._prove_setup_service_authority(replay_decision)
            return SubmissionPolicyMutationOutcome(
                replay_response,
                True,
            )

        existing_policy = (
            await self._projects.get_agent_derived_submission_artifact_policy_for_snapshot(
                str(project_id), initial.guide_version, str(source_snapshot_id)
            )
        )
        if existing_policy is not None:
            raise SubmissionPolicyMutationConflict("submission_policy_replay_missing")

        preflight_facts = SubmissionPolicyReplayFacts(
            actor_profile_id=str(actor_profile_id),
            identity_link_id=str(identity_link_id),
            service_identity=ServiceIdentity.PROJECT_SETUP.value,
            action_id=action.value,
            idempotency_key=None,
            request_digest=preflight_digest,
            resource_context=preflight_resource,
            operation_id=operation_id,
            project_id=str(project_id),
            guide_id=str(guide_id),
            source_snapshot_id=str(source_snapshot_id),
            policy_id=str(policy_id),
            setup_run_id=str(custody.setup_run_id),
            setup_generation=custody.setup_generation,
            setup_task_id=custody.task_id,
            correlation_id=custody.correlation_id,
        )
        disposition, _ = await self.reserve_replay(preflight_facts, execution_claim=True)
        if disposition != "claimed":
            raise SubmissionPolicyMutationConflict(f"idempotency_{disposition}")
        # Persist the execution claim before external material or agent I/O. A
        # crashed delivery therefore remains pending and cannot repeat that I/O.
        await self._session.commit()

        guide = await self._projects.get_guide(str(guide_id))
        snapshot = await self._projects.get_guide_source_snapshot(str(source_snapshot_id))
        report = await self._projects.get_guide_sufficiency_report(str(initial.report_id))
        if guide is None or snapshot is None or report is None:
            raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
        await self._validation.validate_agent_sufficiency_report_for_derivation(report)
        material = await self._validation.verified_guide_source_material_for_agent(
            guide, snapshot, report
        )
        runtime_report = GuideSufficiencyAgentResult(
            status=REPORT_STATUS_TO_AGENT_SUFFICIENCY_STATUS[report.status],
            findings=[AgentFinding.model_validate(finding) for finding in report.findings],
            summary=report.summary,
            agent_name=PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME,
            agent_version=PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION,
        )
        try:
            result = await get_project_guide_agent_runtime().derive_submission_artifact_policy(
                material, runtime_report
            )
        except ProjectAgentRuntimeError:
            raise AgentRuntimeUnavailable(
                "submission artifact policy agent is unavailable"
            ) from None
        try:
            validated_policy = SubmissionArtifactPolicyInput.model_validate(result.policy_body)
        except ValueError as exc:
            raise PolicySetupBlocked("derived submission artifact policy is invalid") from exc
        policy_body = self._validation.canonical_agent_submission_policy_body(
            validated_policy.model_dump(mode="json")
        )
        policy_hash = canonical_json_hash(policy_body)
        final = await self._lock_complete_derivation_lineage(
            project_id, guide_id, source_snapshot_id
        )
        if final != initial:
            raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
        setup = await self._projects.lock_project_setup_run(str(custody.setup_run_id))
        if setup is None:
            raise SubmissionPolicyMutationConflict("project_setup_run_context_mismatch")
        self._require_exact_running_custody(setup, final, custody)
        request_digest = canonical_json_hash(
            {
                "domain": "workstream.submission_policy.derive.final.v1",
                "custody": custody.model_dump(mode="json"),
                "policy_hash": policy_hash,
                "change_summary": result.change_summary,
            }
        )
        resource = self._service_resource(
            project_id=project_id, guide_id=guide_id, policy_id=policy_id,
            operation_id=operation_id, request_digest=request_digest,
            lineage=final, custody=custody,
        )
        caller = PreparedAuthorizationInput(
            idempotency_key=operation_id,
            request_value=cast(JsonValue, resource.model_dump(mode="json")),
        )
        handle = await self._prepare(prepared, action, caller, project_id, resource)
        decision = await prepared.consume(handle, action, caller, resource)
        self._prove_setup_service_authority(decision)
        preflight_values = self._replay_values(preflight_facts)
        final_facts = SubmissionPolicyReplayFacts(
            actor_profile_id=str(actor_profile_id), identity_link_id=str(identity_link_id),
            service_identity=ServiceIdentity.PROJECT_SETUP.value, action_id=action.value,
            idempotency_key=None, request_digest=request_digest, resource_context=resource,
            operation_id=operation_id, project_id=str(project_id), guide_id=str(guide_id),
            source_snapshot_id=str(source_snapshot_id), policy_id=str(policy_id),
            setup_run_id=str(custody.setup_run_id), setup_generation=custody.setup_generation,
            setup_task_id=custody.task_id, correlation_id=custody.correlation_id,
        )
        final_values = self._replay_values(final_facts)
        rebound = await self._replay.bind_reserved_execution(
            operation_id,
            expected_request_digest=preflight_digest,
            expected_resource_context_digest=str(
                preflight_values["resource_context_digest"]
            ),
            request_digest=request_digest,
            resource_context_digest=str(final_values["resource_context_digest"]),
            resource_context_json=cast(dict, final_values["resource_context_json"]),
        )
        if rebound is None:
            raise SubmissionPolicyMutationConflict("idempotency_mismatch")
        policy = SubmissionArtifactPolicy(
            id=str(policy_id), project_id=str(project_id), guide_id=str(guide_id),
            guide_version=final.guide_version, source_snapshot_id=str(source_snapshot_id),
            source_snapshot_hash=final.snapshot_hash,
            policy_version=agent_submission_artifact_policy_version(final.snapshot_hash),
            lifecycle_status="draft", policy_body=policy_body, policy_hash=policy_hash,
            derivation_source=AGENT_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE,
            source_material_refs=list(final.source_material_refs),
            derivation_agent_name=SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_NAME,
            derivation_agent_version=SUBMISSION_ARTIFACT_POLICY_DERIVATION_AGENT_VERSION,
            created_by=str(actor_profile_id), created_by_actor_profile_id=str(actor_profile_id),
            created_via_identity_link_id=str(identity_link_id),
            created_by_admin_role_grant_id=None,
            created_by_service_identity=ServiceIdentity.PROJECT_SETUP.value,
            creation_scope_type="service", creation_scope_project_id=str(project_id),
            creation_action_id=action.value,
            creation_decision_event_id=str(decision.decision_id),
            change_summary=result.change_summary,
        )
        await self._projects.add_submission_artifact_policy(policy)
        setup.status = "policy_draft_ready"
        setup.current_step = "submission_artifact_policy_derivation"
        setup.output_submission_artifact_policy_id = policy.id
        response = SubmissionArtifactPolicyResponse.model_validate(policy)
        await self.complete_replay(
            final_facts,
            response_json=response.model_dump(mode="json"),
            committed_policy_id=policy.id,
        )
        return SubmissionPolicyMutationOutcome(response, False)

    def _require_root_transaction(self) -> None:
        transaction = self._session.sync_session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise RuntimeError("submission-policy mutation requires one root transaction")

    @staticmethod
    def _replay_values(facts: SubmissionPolicyReplayFacts) -> dict[str, object]:
        resource = facts.resource_context
        try:
            action = ActionId(facts.action_id)
            target_kind = PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION[action]
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid submission-policy replay action") from exc
        if (
            resource.target_kind != target_kind
            or facts.request_digest != resource.request_digest
            or facts.operation_id != resource.operation_id
            or facts.project_id != str(resource.scope_project_id)
            or facts.guide_id != str(resource.guide_id)
            or facts.source_snapshot_id != str(resource.source_snapshot_id)
            or facts.policy_id != str(resource.successor_policy_id or resource.policy_id)
            or facts.setup_generation != resource.setup_generation
        ):
            raise ValueError("submission-policy replay facts do not match resource context")
        custody = resource.setup_service_custody
        if resource.execution_kind == "setup_service":
            if (
                facts.service_identity != ServiceIdentity.PROJECT_SETUP.value
                or facts.idempotency_key is not None
                or custody is None
                or facts.setup_run_id != str(custody.setup_run_id)
                or facts.setup_task_id != custody.task_id
                or facts.correlation_id != custody.correlation_id
            ):
                raise ValueError("submission-policy service replay custody is invalid")
        elif facts.idempotency_key is None or any(
            value is not None
            for value in (
                facts.service_identity,
                facts.setup_run_id,
                facts.setup_task_id,
                facts.correlation_id,
            )
        ):
            raise ValueError("submission-policy human replay custody is invalid")
        return {
            "actor_profile_id": facts.actor_profile_id,
            "identity_link_id": facts.identity_link_id,
            "service_identity": facts.service_identity,
            "action_id": facts.action_id,
            "idempotency_key": facts.idempotency_key,
            "request_digest": facts.request_digest,
            "resource_context_digest": authorization_resource_digest(resource),
            "resource_context_json": resource.model_dump(mode="json"),
            "operation_id": facts.operation_id,
            "project_id": facts.project_id,
            "guide_id": facts.guide_id,
            "source_snapshot_id": facts.source_snapshot_id,
            "policy_id": facts.policy_id,
            "setup_run_id": facts.setup_run_id,
            "setup_generation": facts.setup_generation,
            "setup_task_id": facts.setup_task_id,
            "correlation_id": facts.correlation_id,
        }

    async def reserve_replay(
        self,
        facts: SubmissionPolicyReplayFacts,
        *,
        execution_claim: bool = False,
    ) -> tuple[
        Literal["claimed", "mismatch", "pending", "replayed"],
        SubmissionPolicyMutationIdempotencyRecord,
    ]:
        """Reserve replay custody while leaving transaction ownership to the caller."""
        self._require_root_transaction()
        status: Literal["reserved", "pending"] = "reserved" if execution_claim else "pending"
        return await self._replay.reserve(**self._replay_values(facts), status=status)

    async def complete_replay(
        self,
        facts: SubmissionPolicyReplayFacts,
        *,
        response_json: dict,
        committed_policy_id: str,
        committed_effective_policy_id: str | None = None,
        committed_pre_submit_policy_id: str | None = None,
    ) -> None:
        """Flush one replay completion without committing the caller transaction."""
        self._require_root_transaction()
        values = self._replay_values(facts)
        await self._replay.complete(
            facts.operation_id,
            actor_profile_id=facts.actor_profile_id,
            identity_link_id=facts.identity_link_id,
            service_identity=facts.service_identity,
            action_id=facts.action_id,
            idempotency_key=facts.idempotency_key,
            request_digest=facts.request_digest,
            resource_context_digest=str(values["resource_context_digest"]),
            setup_run_id=facts.setup_run_id,
            setup_generation=facts.setup_generation,
            setup_task_id=facts.setup_task_id,
            correlation_id=facts.correlation_id,
            response_json=response_json,
            committed_policy_id=committed_policy_id,
            committed_effective_policy_id=committed_effective_policy_id,
            committed_pre_submit_policy_id=committed_pre_submit_policy_id,
        )
