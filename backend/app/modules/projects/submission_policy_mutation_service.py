"""Flush-only submission-policy authority foundation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import JsonValue
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
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
    SubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyUpdate,
)
from app.modules.projects.service import (
    GuideEditBlocked,
    GuideNotFound,
    MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE,
    PolicyEditBlocked,
    PolicySetupBlocked,
    ProjectService,
    ProjectServiceError,
    SubmissionArtifactPolicyNotFound,
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

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._replay = SubmissionPolicyMutationReplayRepository(session)
        self._projects = ProjectRepository(session)
        self._admin = AdminAuthorizationRepository(session)
        self._validation = ProjectService(session)

    @staticmethod
    def _stable_uuid(*parts: object) -> UUID:
        return uuid5(NAMESPACE_URL, "workstream:submission-policy:" + ":".join(map(str, parts)))

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
        if (
            setup is None
            or setup.guide_version != guide.version
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
                raise PolicyEditBlocked("only a current draft policy can be replaced")
            if predecessor.derivation_source != MANUAL_SUBMISSION_ARTIFACT_POLICY_DERIVATION_SOURCE:
                raise PolicyEditBlocked("agent-derived policies are immutable through this path")
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
            resource_id=policy_id,
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
        policy_body: dict | None,
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
        stable_parts = (
            action.value,
            resolved.profile.id,
            resolved.identity_link.id,
            project_id,
            predecessor_id or "create",
            key,
        )
        operation_id = self._stable_uuid("operation", *stable_parts)
        committed_policy_id = self._stable_uuid("policy", *stable_parts)
        initial = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=False,
            predecessor_id=predecessor_id,
        )
        if predecessor_id is not None and initial.predecessor_hash != expected_policy_hash:
            raise SubmissionPolicyMutationConflict("submission_policy_precondition_failed")
        canonical_body, policy_hash = self._validation.canonical_manual_submission_policy_body(
            policy_body
        )
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
            predecessor = await self._projects.lock_submission_artifact_policy(str(predecessor_id))
            if predecessor is None or predecessor.lifecycle_status != "draft":
                raise SubmissionPolicyMutationConflict("submission_policy_lineage_stale")
            predecessor.lifecycle_status = "superseded"
            predecessor.superseded_at = datetime.now(UTC)
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
        prepared: PreparedAuthorizationService,
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
        operation_id = self._stable_uuid(
            "operation",
            action.value,
            resolved.profile.id,
            resolved.identity_link.id,
            project_id,
            selected_policy_id
            if action is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE
            else "create",
            key,
        )
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
            "policy_body": effective_policy_body,
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
        canonical_body, policy_hash = self._validation.canonical_manual_submission_policy_body(
            effective_policy_body
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
        caller = PreparedAuthorizationInput(
            idempotency_key=key,
            request_value=cast(JsonValue, resource.model_dump(mode="json")),
        )
        handle = await self._prepare(prepared, action, caller, project_id, resource)
        decision = await prepared.consume(handle, action, caller, resource)
        self._prove_human_authority(decision, project_id)
        if replay.resource_context_digest != decision.resource_context_digest:
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
        stable_parts = (
            action.value,
            resolved.profile.id,
            resolved.identity_link.id,
            project_id,
            "create",
            key,
        )
        policy_id = self._stable_uuid("policy", *stable_parts)
        await self._require_pm_admission(resolved=resolved, project_id=project_id)
        replay = await self._existing_manual_replay(
            resolved=resolved,
            prepared=prepared,
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
        stable_parts = (
            action.value,
            resolved.profile.id,
            resolved.identity_link.id,
            project_id,
            policy_id,
            key,
        )
        successor_id = self._stable_uuid("policy", *stable_parts)
        await self._require_pm_admission(resolved=resolved, project_id=project_id)
        replay = await self._existing_manual_replay(
            resolved=resolved,
            prepared=prepared,
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
        if predecessor is None:
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
        self, facts: SubmissionPolicyReplayFacts
    ) -> tuple[
        Literal["claimed", "mismatch", "pending", "replayed"],
        SubmissionPolicyMutationIdempotencyRecord,
    ]:
        """Reserve replay custody while leaving transaction ownership to the caller."""
        self._require_root_transaction()
        return await self._replay.reserve(**self._replay_values(facts))

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
