"""Authorized guide-sufficiency mutation orchestration."""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import AsyncIterator, Literal, Sequence, cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.project_agents import get_project_guide_agent_runtime
from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import (
    GuideSufficiencyExtractionProvenance,
    GuideSufficiencyMaterialPort,
    GuideSufficiencyMaterialRequest,
    GuideSufficiencyMaterialUnavailable,
)
from app.interfaces.project_agents import ProjectAgentRuntimeError
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectGuideSufficiencyMutationResourceContext,
    ProjectSetupServiceCustodyContext,
)
from app.modules.projects.models import GuideSufficiencyReport
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.schemas import (
    GuideSufficiencyAcknowledgement,
    GuideSufficiencyFindingInput,
    GuideSufficiencyReportCreate,
    GuideSufficiencyReportResponse,
    ProjectSetupRunResponse,
)
from app.modules.projects.service import (
    GuideEditBlocked,
    GuideNotFound,
    AgentRuntimeUnavailable,
    AGENT_SUFFICIENCY_STATUS_TO_REPORT_STATUS,
    PolicySetupBlocked,
    PolicySetupConflict,
    ProjectService,
    ProjectServiceError,
    SufficiencyCreationAuthority,
    SufficiencyReportNotFound,
    bounded_canonical_guide_material,
    build_verified_guide_sufficiency_material,
    stage_verified_sufficiency_report,
    validate_sufficiency_report_payload,
    verified_guide_sufficiency_agent_item,
)
from app.modules.projects.setup_queue import pre_submit_setup_task_id
from app.modules.projects.sufficiency_mutation_repository import (
    GuideSufficiencyMutationReplayRepository,
)


class GuideSufficiencyMutationConflict(ProjectServiceError):
    """A replay selector or locked sufficiency lineage no longer matches."""

    status_code = 409


@dataclass(frozen=True, slots=True)
class GuideSufficiencyMutationOutcome:
    """One route-owned transaction result."""

    response: GuideSufficiencyReportResponse
    replayed: bool
    created: bool = False


@dataclass(frozen=True, slots=True)
class GuideSufficiencyDispatchOutcome:
    """Authorized custody for one asynchronous setup dispatch."""

    response: ProjectSetupRunResponse
    replayed: bool
    dispatch_claimed: bool = False


@dataclass(frozen=True, slots=True)
class _Lineage:
    """Server-owned guide setup facts used at prepare and final consumption."""

    guide_version: str
    snapshot_id: UUID
    snapshot_hash: str
    setup_generation: int
    setup_run_id: UUID | None
    stale_output_digest: str


class GuideSufficiencyMutationService:
    """Consume exact Project Manager authority before sufficiency writes."""

    def __init__(self, session, *, material: GuideSufficiencyMaterialPort | None = None) -> None:
        self._session = session
        self._projects = ProjectRepository(session)
        self._replay = GuideSufficiencyMutationReplayRepository(session)
        self._validation = ProjectService(session)
        self._material = material

    @asynccontextmanager
    async def _execution_fence(self, actor_profile_id: str, action: ActionId, key: UUID):
        """Hold one process-independent, crash-released external-work fence."""
        engine = self._session.bind
        if not isinstance(engine, AsyncEngine):
            raise RuntimeError("guide sufficiency execution requires an async database engine")
        digest = canonical_json_hash(
            {
                "domain": "workstream.guide_sufficiency.execution_fence.v1",
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
                raise GuideSufficiencyMutationConflict("idempotency_pending")
            try:
                yield
            finally:
                await connection.execute(
                    text("select pg_advisory_unlock(:lock_key)"), {"lock_key": lock_key}
                )

    @staticmethod
    def _prove_authority(decision, project_id: UUID, execution_kind: str) -> None:
        if execution_kind == "setup_service":
            if (
                decision.matched_authority_kind is not MatchedAuthorityKind.FIXED_SERVICE
                or decision.matched_grant_id is not None
            ):
                raise RuntimeError("sufficiency mutation lacked fixed setup-service authority")
            return
        if (
            decision.matched_authority_kind is not MatchedAuthorityKind.ADMIN_ROLE_GRANT
            or decision.matched_grant_id is None
            or decision.matched_scope_project_id not in {None, project_id}
        ):
            raise RuntimeError("sufficiency mutation lacked Project Manager authority")

    @staticmethod
    def _prove_human(decision, project_id: UUID) -> None:
        GuideSufficiencyMutationService._prove_authority(decision, project_id, "human")

    @staticmethod
    def _manual_dispatch_lineage(lineage: _Lineage, project_id: UUID, guide_id: UUID) -> _Lineage:
        """Bind manual replay to immutable setup custody, not queue progress."""
        return replace(
            lineage,
            stale_output_digest=canonical_json_hash(
                {
                    "domain": "workstream.project_setup.manual_dispatch.v1",
                    "project_id": str(project_id),
                    "guide_id": str(guide_id),
                    "source_snapshot_id": str(lineage.snapshot_id),
                    "setup_run_id": (
                        str(lineage.setup_run_id) if lineage.setup_run_id is not None else None
                    ),
                    "setup_generation": lineage.setup_generation,
                }
            ),
        )

    async def _lineage(
        self,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        *,
        lock: bool,
        require_setup_run: bool = False,
    ) -> _Lineage:
        guide = (
            await self._projects.lock_project_guide(str(guide_id))
            if lock
            else await self._projects.get_guide(str(guide_id))
        )
        if guide is None or guide.project_id != str(project_id):
            raise GuideNotFound("guide not found")
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can change sufficiency state")
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
            raise PolicySetupBlocked(
                "latest guide source snapshot is ambiguous; create a fresh source snapshot"
            ) from exc
        if snapshot is None or snapshot.id != str(source_snapshot_id):
            raise PolicySetupConflict("guide source snapshot is stale")
        await self._validation.validate_source_snapshot_integrity(snapshot, PolicySetupBlocked)
        setup = (
            await self._projects.lock_latest_project_setup_run(
                str(project_id), str(guide_id), guide.version
            )
            if lock
            else await self._projects.get_latest_project_setup_run(str(project_id), str(guide_id))
        )
        if setup is not None and (
            setup.guide_version != guide.version
            or setup.source_snapshot_id != snapshot.id
            or setup.source_snapshot_hash != snapshot.bundle_hash
        ):
            raise PolicySetupConflict("project setup run context mismatch")
        if setup is None and require_setup_run:
            raise PolicySetupConflict("project setup run context mismatch")
        setup_generation = (
            setup.setup_generation if setup is not None else snapshot.creation_generation
        )
        if setup_generation is None:
            raise PolicySetupConflict("project setup run context mismatch")
        return _Lineage(
            guide_version=guide.version,
            snapshot_id=UUID(snapshot.id),
            snapshot_hash=snapshot.bundle_hash,
            setup_generation=setup_generation,
            setup_run_id=UUID(setup.id) if setup is not None else None,
            stale_output_digest=canonical_json_hash(
                {
                    "domain": "workstream.project_setup.sufficiency_stale_output.v1",
                    "setup_run_id": setup.id if setup is not None else None,
                    "setup_generation": setup_generation,
                    "current_step": setup.current_step if setup is not None else "manual",
                    "output_sufficiency_report_id": None,
                }
            ),
        )

    @staticmethod
    def _caller(
        *,
        action: ActionId,
        route: str,
        actor_profile_id: str,
        identity_link_id: str,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        report_id: UUID | None,
        operation_id: UUID,
        lineage: _Lineage,
        target_kind: Literal["report", "run", "warning_acknowledgement"],
        body: dict,
        material_digest: str | None = None,
        execution_kind: Literal["human", "setup_service"] = "human",
        setup_service_custody: ProjectSetupServiceCustodyContext | None = None,
    ) -> tuple[PreparedAuthorizationInput, str]:
        replay_value = {
            "action_id": action.value,
            "route": route,
            "actor_profile_id": actor_profile_id,
            "identity_link_id": identity_link_id,
            "idempotency_key": str(key),
            "project_id": str(project_id),
            "guide_id": str(guide_id),
            "report_id": (str(report_id) if target_kind == "warning_acknowledgement" else None),
            "source_snapshot_id": str(lineage.snapshot_id),
            "body": body,
            "execution_kind": execution_kind,
            "setup_service_custody": (
                setup_service_custody.model_dump(mode="json")
                if setup_service_custody is not None
                else None
            ),
        }
        digest = canonical_json_hash(
            {"domain": "workstream.guide_sufficiency.idempotency.v1", **replay_value}
        )
        request_value = {
            **replay_value,
            "report_id": str(report_id) if report_id is not None else None,
            "guide_version": lineage.guide_version,
            "source_snapshot_hash": lineage.snapshot_hash,
            "operation_id": str(operation_id),
            "request_digest": digest,
            "target_kind": target_kind,
            "execution_kind": execution_kind,
            "setup_generation": lineage.setup_generation,
            "stale_output_digest": lineage.stale_output_digest,
            "material_digest": material_digest,
            "setup_service_custody": replay_value["setup_service_custody"],
        }
        return (
            PreparedAuthorizationInput(
                idempotency_key=key,
                request_value=cast(JsonValue, request_value),
            ),
            digest,
        )

    @staticmethod
    def _resource(
        *,
        project_id: UUID,
        guide_id: UUID,
        report_id: UUID | None,
        operation_id: UUID,
        request_digest: str,
        lineage: _Lineage,
        target_kind: Literal["report", "run", "warning_acknowledgement"],
        material_digest: str | None = None,
        execution_kind: Literal["human", "setup_service"] = "human",
        setup_service_custody: ProjectSetupServiceCustodyContext | None = None,
    ) -> ProjectGuideSufficiencyMutationResourceContext:
        return ProjectGuideSufficiencyMutationResourceContext(
            resource_type="project_guide_sufficiency_mutation",
            resource_id=report_id or lineage.snapshot_id,
            operation_id=operation_id,
            request_digest=request_digest,
            scope_project_id=project_id,
            guide_id=guide_id,
            guide_version=lineage.guide_version,
            source_snapshot_id=lineage.snapshot_id,
            source_snapshot_hash=lineage.snapshot_hash,
            target_kind=target_kind,
            execution_kind=execution_kind,
            sufficiency_report_id=report_id,
            setup_generation=lineage.setup_generation,
            stale_output_digest=lineage.stale_output_digest,
            material_digest=material_digest,
            setup_service_custody=setup_service_custody,
        )

    async def _prepare(
        self,
        prepared: PreparedAuthorizationService,
        action: ActionId,
        caller: PreparedAuthorizationInput,
        project_id: UUID,
        denial_resource: ProjectGuideSufficiencyMutationResourceContext,
    ):
        """Prepare authority or stage one exact bounded denial."""
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
            await prepared.deny_unsupported(action, caller, denial_resource, exc)

    async def create_report(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        payload: GuideSufficiencyReportCreate,
    ) -> AsyncIterator[GuideSufficiencyMutationOutcome]:
        """Create one explicitly human-authored sufficiency report."""
        action = ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE
        report_id, operation_id = uuid4(), uuid4()
        snapshot_id = UUID(payload.source_snapshot_id)
        initial = await self._lineage(project_id, guide_id, snapshot_id, lock=False)
        caller, digest = self._caller(
            action=action,
            route="POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            report_id=report_id,
            operation_id=operation_id,
            lineage=initial,
            target_kind="report",
            body=payload.model_dump(mode="json"),
        )
        existing = await self._replay.find(resolved.profile.id, action.value, key)
        if existing is not None:
            replay_mismatch = (
                existing.identity_link_id != resolved.identity_link.id
                or existing.request_digest != digest
                or existing.project_id != str(project_id)
                or existing.guide_id != str(guide_id)
                or existing.source_snapshot_id != str(snapshot_id)
            )
            if replay_mismatch:
                raise GuideSufficiencyMutationConflict("idempotency_mismatch")
            replay_pending = (
                existing.status != "committed"
                or existing.response_json is None
                or existing.report_id is None
            )
            if replay_pending:
                raise GuideSufficiencyMutationConflict("idempotency_pending")
            report_id = UUID(existing.report_id)
            operation_id = existing.operation_id
            caller, digest = self._caller(
                action=action,
                route="POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
                actor_profile_id=resolved.profile.id,
                identity_link_id=resolved.identity_link.id,
                key=key,
                project_id=project_id,
                guide_id=guide_id,
                report_id=report_id,
                operation_id=operation_id,
                lineage=initial,
                target_kind="report",
                body=payload.model_dump(mode="json"),
            )
        handle = await self._prepare(
            prepared,
            action,
            caller,
            project_id,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=report_id,
                operation_id=operation_id,
                request_digest=digest,
                lineage=initial,
                target_kind="report",
            ),
        )
        final = await self._lineage(project_id, guide_id, snapshot_id, lock=True)
        if final != initial:
            raise GuideSufficiencyMutationConflict("sufficiency_lineage_stale")
        decision = await prepared.consume(
            handle,
            action,
            caller,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=report_id,
                operation_id=operation_id,
                request_digest=digest,
                lineage=final,
                target_kind="report",
            ),
        )
        self._prove_human(decision, project_id)
        if existing is not None:
            if existing.resource_context_digest != decision.resource_context_digest:
                raise GuideSufficiencyMutationConflict("idempotency_mismatch")
            return GuideSufficiencyMutationOutcome(
                GuideSufficiencyReportResponse.model_validate(existing.response_json),
                True,
            )
        if await self._projects.get_sufficiency_report_for_snapshot(str(snapshot_id)) is not None:
            raise GuideSufficiencyMutationConflict("sufficiency_report_already_exists")
        validate_sufficiency_report_payload(payload)
        disposition, replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context_digest=decision.resource_context_digest,
            operation_id=operation_id,
            project_id=str(project_id),
            guide_id=str(guide_id),
            source_snapshot_id=str(snapshot_id),
            report_id=None,
            setup_run_id=None,
            setup_generation=final.setup_generation,
        )
        if disposition != "claimed":
            raise GuideSufficiencyMutationConflict(f"idempotency_{disposition}")
        report = GuideSufficiencyReport(
            id=str(report_id),
            project_id=str(project_id),
            guide_id=str(guide_id),
            guide_version=final.guide_version,
            source_snapshot_id=str(snapshot_id),
            source_snapshot_hash=final.snapshot_hash,
            status=payload.status,
            findings=[finding.model_dump(mode="json") for finding in payload.findings],
            summary=payload.summary,
            created_by=resolved.profile.id,
            created_by_actor_profile_id=resolved.profile.id,
            created_via_identity_link_id=resolved.identity_link.id,
            created_by_admin_role_grant_id=decision.matched_grant_id,
            creation_scope_type=(
                "system" if decision.matched_scope_project_id is None else "project"
            ),
            creation_scope_project_id=str(project_id),
            creation_action_id=action.value,
            authorization_decision_event_id=str(decision.decision_id),
        )
        try:
            report = await self._projects.add_guide_sufficiency_report(report)
        except IntegrityError:
            raise GuideSufficiencyMutationConflict("sufficiency_report_already_exists") from None
        response = GuideSufficiencyReportResponse.model_validate(report)
        await self._replay.complete(
            replay, response_json=response.model_dump(mode="json"), report_id=report.id
        )
        return GuideSufficiencyMutationOutcome(response, False, True)

    async def authorize_manual_dispatch(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
    ) -> GuideSufficiencyDispatchOutcome:
        """Authorize a human request to dispatch, never execute, sufficiency work."""
        action = ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
        operation_id = uuid4()
        initial = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=False,
            require_setup_run=True,
        )
        initial = self._manual_dispatch_lineage(initial, project_id, guide_id)
        if initial.setup_run_id is None:
            raise GuideSufficiencyMutationConflict("project_setup_run_context_mismatch")
        caller, digest = self._caller(
            action=action,
            route=(
                "POST /api/v1/projects/{project_id}/guides/{guide_id}/"
                "source-snapshots/{source_snapshot_id}/run-sufficiency-agent"
            ),
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            report_id=None,
            operation_id=operation_id,
            lineage=initial,
            target_kind="run",
            body={"source_snapshot_id": str(source_snapshot_id)},
        )
        existing = await self._replay.find(resolved.profile.id, action.value, key)
        if existing is not None:
            replay_mismatch = (
                existing.action_id != action.value
                or existing.identity_link_id != resolved.identity_link.id
                or existing.request_digest != digest
                or existing.project_id != str(project_id)
                or existing.guide_id != str(guide_id)
                or existing.source_snapshot_id != str(source_snapshot_id)
                or existing.setup_run_id != str(initial.setup_run_id)
                or existing.setup_generation != initial.setup_generation
            )
            if replay_mismatch:
                raise GuideSufficiencyMutationConflict("idempotency_mismatch")
            if existing.status != "committed" or existing.response_json is None:
                raise GuideSufficiencyMutationConflict("idempotency_pending")
            operation_id = existing.operation_id
            caller, digest = self._caller(
                action=action,
                route=(
                    "POST /api/v1/projects/{project_id}/guides/{guide_id}/"
                    "source-snapshots/{source_snapshot_id}/run-sufficiency-agent"
                ),
                actor_profile_id=resolved.profile.id,
                identity_link_id=resolved.identity_link.id,
                key=key,
                project_id=project_id,
                guide_id=guide_id,
                report_id=None,
                operation_id=operation_id,
                lineage=initial,
                target_kind="run",
                body={"source_snapshot_id": str(source_snapshot_id)},
            )
        resource = self._resource(
            project_id=project_id,
            guide_id=guide_id,
            report_id=None,
            operation_id=operation_id,
            request_digest=digest,
            lineage=initial,
            target_kind="run",
        )
        handle = await self._prepare(prepared, action, caller, project_id, resource)
        final = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=True,
            require_setup_run=True,
        )
        final = self._manual_dispatch_lineage(final, project_id, guide_id)
        if final != initial or final.setup_run_id is None:
            raise GuideSufficiencyMutationConflict("sufficiency_lineage_stale")
        setup_run = await self._projects.lock_project_setup_run(str(final.setup_run_id))
        if setup_run is None:
            raise GuideSufficiencyMutationConflict("project_setup_run_context_mismatch")
        authoritative_report = await self._projects.get_sufficiency_report_for_snapshot(
            str(source_snapshot_id)
        )
        if existing is not None:
            decision = await prepared.consume(handle, action, caller, resource)
            self._prove_human(decision, project_id)
            if existing.resource_context_digest != decision.resource_context_digest:
                raise GuideSufficiencyMutationConflict("idempotency_mismatch")
            return GuideSufficiencyDispatchOutcome(
                response=ProjectSetupRunResponse.model_validate(existing.response_json),
                replayed=True,
            )
        run_not_needed = (
            (
                authoritative_report is not None
                and authoritative_report.project_setup_run_id == setup_run.id
                and authoritative_report.setup_generation == setup_run.setup_generation
            )
            or setup_run.output_sufficiency_report_id is not None
            or setup_run.output_submission_artifact_policy_id is not None
            or setup_run.output_post_submit_checker_policy_id is not None
            or setup_run.status
            in {
                "sufficiency_blocked",
                "running_policy_derivation_agent",
                "policy_draft_ready",
                "running_post_submit_derivation_agent",
                "post_submit_setup_blocked",
                "post_submit_policy_compiled",
            }
        )
        if run_not_needed:
            raise GuideSufficiencyMutationConflict("guide_sufficiency_run_not_needed")
        if setup_run.celery_task_id is None and setup_run.continuation_verification_job_id is None:
            raise GuideSufficiencyMutationConflict("verified_guide_material_not_ready")
        expected_task_id = pre_submit_setup_task_id(setup_run.id, setup_run.setup_generation)
        if setup_run.celery_task_id is not None and setup_run.celery_task_id != expected_task_id:
            raise GuideSufficiencyMutationConflict("project_setup_task_identity_stale")
        decision = await prepared.consume(handle, action, caller, resource)
        self._prove_human(decision, project_id)
        disposition, replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context_digest=decision.resource_context_digest,
            operation_id=operation_id,
            project_id=str(project_id),
            guide_id=str(guide_id),
            source_snapshot_id=str(source_snapshot_id),
            report_id=None,
            setup_run_id=setup_run.id,
            setup_generation=setup_run.setup_generation,
        )
        if disposition != "claimed":
            raise GuideSufficiencyMutationConflict(f"idempotency_{disposition}")
        dispatch_claimed = setup_run.celery_task_id is None or setup_run.status in {
            "enqueue_failed",
            "setup_blocked",
            "failed",
        }
        if dispatch_claimed:
            setup_run.status = "dispatch_pending"
            setup_run.current_step = "dispatch"
            setup_run.celery_task_id = expected_task_id
            setup_run.error_code = None
            setup_run.error_summary = None
        response = ProjectSetupRunResponse.model_validate(setup_run)
        await self._replay.complete(
            replay,
            response_json=response.model_dump(mode="json"),
            report_id=None,
        )
        return GuideSufficiencyDispatchOutcome(
            response=response,
            replayed=False,
            dispatch_claimed=dispatch_claimed,
        )

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
        custody: ProjectSetupServiceCustodyContext,
    ) -> GuideSufficiencyMutationOutcome:
        """Run one exact setup-service command with server-derived replay custody."""
        replay_digest = canonical_json_hash(
            {
                "domain": "workstream.project_setup.sufficiency_replay.v1",
                "actor_profile_id": str(actor_profile_id),
                "identity_link_id": str(identity_link_id),
                "action_id": ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN.value,
                "custody": custody.model_dump(mode="json"),
            }
        )
        fence_key = UUID(hex=replay_digest.removeprefix("sha256:")[:32])
        async with self._execution_fence(
            str(actor_profile_id), ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN, fence_key
        ):
            yield await self._run_agent(
                actor_profile_id=str(actor_profile_id),
                identity_link_id=str(identity_link_id),
                prepared=prepared,
                key=fence_key,
                project_id=project_id,
                guide_id=guide_id,
                source_snapshot_id=source_snapshot_id,
                execution_kind="setup_service",
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
    ) -> ProjectSetupServiceCustodyContext:
        """Resolve server-owned setup facts before composing fixed-service PREP."""
        lineage = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=False,
            require_setup_run=True,
        )
        if lineage.setup_run_id != setup_run_id or lineage.setup_generation != setup_generation:
            raise GuideSufficiencyMutationConflict("project_setup_run_context_mismatch")
        setup_run = await self._projects.lock_project_setup_run(str(setup_run_id))
        if (
            setup_run is None
            or setup_run.status not in {"queued", "running_sufficiency_agent"}
            or setup_run.current_step != "guide_sufficiency"
            or setup_run.celery_task_id != str(task_id)
        ):
            raise GuideSufficiencyMutationConflict("project_setup_run_context_mismatch")
        stable_output_digest = canonical_json_hash(
            {
                "domain": "workstream.project_setup.sufficiency_stale_output.v1",
                "setup_run_id": setup_run.id,
                "setup_generation": setup_run.setup_generation,
                "current_step": setup_run.current_step,
                "output_sufficiency_report_id": None,
            }
        )
        return ProjectSetupServiceCustodyContext(
            setup_run_id=setup_run_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=source_snapshot_id,
            setup_generation=setup_generation,
            expected_step="guide_sufficiency",
            task_id=task_id,
            correlation_id=correlation_id,
            stale_output_digest=stable_output_digest,
        )

    @staticmethod
    def _setup_service_replay_key(
        actor_profile_id: str,
        identity_link_id: str,
        custody: ProjectSetupServiceCustodyContext,
        material_digest: str,
    ) -> UUID:
        """Derive durable service replay from identity, custody, and exact material."""
        digest = canonical_json_hash(
            {
                "domain": "workstream.project_setup.sufficiency_replay.v1",
                "actor_profile_id": actor_profile_id,
                "identity_link_id": identity_link_id,
                "action_id": ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN.value,
                "custody": custody.model_dump(mode="json"),
                "material_digest": material_digest,
            }
        )
        return UUID(hex=digest.removeprefix("sha256:")[:32])

    async def _validate_adoptable_verified_report(
        self,
        report: GuideSufficiencyReport,
        lineage: _Lineage,
        *,
        project_id: UUID,
        guide_id: UUID,
        material_digest: str,
        material_byte_count: int,
        source_provenance: Sequence[GuideSufficiencyExtractionProvenance],
    ) -> None:
        """Require an existing human agent report to match current ART custody exactly."""
        if (
            report.project_id != str(project_id)
            or report.guide_id != str(guide_id)
            or report.guide_version != lineage.guide_version
            or report.source_snapshot_id != str(lineage.snapshot_id)
            or report.source_snapshot_hash != lineage.snapshot_hash
            or report.project_setup_run_id != str(lineage.setup_run_id)
            or report.setup_generation != lineage.setup_generation
            or report.agent_material_sha256 != material_digest
            or report.agent_material_byte_count != material_byte_count
            or report.creation_action_id != ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN.value
            or report.created_by_admin_role_grant_id is None
            or report.created_by_service_identity is not None
        ):
            raise GuideSufficiencyMutationConflict("sufficiency_report_provenance_mismatch")
        usages = await self._validation._verified_report_usages(report)
        actual = [
            (
                usage.item_order,
                usage.source_item_id,
                usage.binding_id,
                usage.content_id,
                usage.extraction_usage_id,
                usage.extraction_attempt_id,
                usage.extracted_content_id,
                usage.canonical_output_sha256,
            )
            for usage in usages
        ]
        expected = [
            (
                item.item_order,
                str(item.source_item_id),
                str(item.binding_id),
                str(item.content_id),
                str(item.extraction_usage_id),
                str(item.extraction_attempt_id),
                str(item.extracted_content_id),
                item.canonical_output_sha256,
            )
            for item in source_provenance
        ]
        if actual != expected:
            raise GuideSufficiencyMutationConflict("sufficiency_report_provenance_mismatch")

    async def _run_agent(
        self,
        *,
        actor_profile_id: str,
        identity_link_id: str,
        prepared: PreparedAuthorizationService,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        execution_kind: Literal["setup_service"],
        setup_service_custody: ProjectSetupServiceCustodyContext,
    ) -> GuideSufficiencyMutationOutcome:
        """Run verified ART material through exact fixed setup-service authority."""
        if self._material is None:
            raise PolicySetupBlocked("verified guide sufficiency is unavailable")
        action = ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
        operation_id = uuid4()
        initial = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=False,
            require_setup_run=True,
        )
        if initial.setup_run_id is None:
            raise RuntimeError("required setup run was not resolved")
        initial = replace(
            initial,
            stale_output_digest=setup_service_custody.stale_output_digest,
        )
        body = {"source_snapshot_id": str(source_snapshot_id)}
        caller, digest = self._caller(
            action=action,
            route="internal:workstream.project.setup/guide-sufficiency",
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            report_id=None,
            operation_id=operation_id,
            lineage=initial,
            target_kind="run",
            body=body,
            execution_kind=execution_kind,
            setup_service_custody=setup_service_custody,
        )
        existing_report = await self._projects.get_sufficiency_report_for_snapshot(
            str(source_snapshot_id)
        )

        preflight = await self._prepare(
            prepared,
            action,
            caller,
            project_id,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=None,
                operation_id=operation_id,
                request_digest=digest,
                lineage=initial,
                target_kind="run",
                execution_kind=execution_kind,
                setup_service_custody=setup_service_custody,
            ),
        )
        preflight_decision = await prepared.consume(
            preflight,
            action,
            caller,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=None,
                operation_id=operation_id,
                request_digest=digest,
                lineage=initial,
                target_kind="run",
                execution_kind=execution_kind,
                setup_service_custody=setup_service_custody,
            ),
        )
        self._prove_authority(preflight_decision, project_id, execution_kind)
        await self._session.rollback()
        existing_report = await self._projects.get_sufficiency_report_for_snapshot(
            str(source_snapshot_id)
        )

        material_request = GuideSufficiencyMaterialRequest(
            project_id=project_id,
            guide_id=guide_id,
            guide_source_snapshot_id=source_snapshot_id,
            project_setup_run_id=initial.setup_run_id,
            setup_generation=initial.setup_generation,
        )
        material_error: GuideSufficiencyMaterialUnavailable | None = None
        service_created_report = (
            existing_report is not None
            and existing_report.created_by_service_identity == "workstream.project.setup"
            and existing_report.created_by_admin_role_grant_id is None
        )
        if service_created_report:
            first = None
        else:
            try:
                first = await self._material.load(material_request)
            except GuideSufficiencyMaterialUnavailable as exc:
                first = None
                material_error = exc
        agent_material = None
        first_prompt = None
        if first is not None:
            guide = await self._projects.get_guide(str(guide_id))
            snapshot = await self._projects.get_guide_source_snapshot(str(source_snapshot_id))
            if guide is None or snapshot is None:
                raise GuideSufficiencyMutationConflict("sufficiency_lineage_stale")
            agent_material = build_verified_guide_sufficiency_material(
                guide, snapshot, first.source_items
            )
            first_prompt = bounded_canonical_guide_material(agent_material)
            material_digest = f"sha256:{hashlib.sha256(first_prompt).hexdigest()}"
        elif service_created_report and existing_report.agent_material_sha256 is not None:
            material_digest = existing_report.agent_material_sha256
        elif material_error is not None:
            raise material_error
        else:
            raise RuntimeError("guide sufficiency material resolution failed")
        if execution_kind == "setup_service":
            adopted_report_id = (
                UUID(existing_report.id)
                if (
                    existing_report is not None
                    and existing_report.created_by_admin_role_grant_id is not None
                    and existing_report.created_by_service_identity is None
                )
                else None
            )
            key = self._setup_service_replay_key(
                actor_profile_id,
                identity_link_id,
                setup_service_custody,
                material_digest,
            )
            caller, digest = self._caller(
                action=action,
                route="internal:workstream.project.setup/guide-sufficiency",
                actor_profile_id=actor_profile_id,
                identity_link_id=identity_link_id,
                key=key,
                project_id=project_id,
                guide_id=guide_id,
                report_id=adopted_report_id,
                operation_id=operation_id,
                lineage=initial,
                target_kind="run",
                body=body,
                material_digest=material_digest,
                execution_kind=execution_kind,
                setup_service_custody=setup_service_custody,
            )
            existing_replay = await self._replay.find(actor_profile_id, action.value, key)
            if existing_replay is not None:
                if (
                    existing_replay.identity_link_id != identity_link_id
                    or existing_replay.request_digest != digest
                    or existing_replay.project_id != str(project_id)
                    or existing_replay.guide_id != str(guide_id)
                    or existing_replay.source_snapshot_id != str(source_snapshot_id)
                    or existing_replay.setup_run_id != str(initial.setup_run_id)
                    or existing_replay.setup_generation != initial.setup_generation
                    or existing_replay.status != "committed"
                    or existing_replay.response_json is None
                    or existing_replay.report_id is None
                ):
                    raise GuideSufficiencyMutationConflict("idempotency_mismatch")
                report = await self._projects.get_guide_sufficiency_report(
                    existing_replay.report_id
                )
                if (
                    report is None
                    or report.creation_action_id != action.value
                    or report.project_setup_run_id != str(initial.setup_run_id)
                    or report.setup_generation != initial.setup_generation
                    or report.agent_material_sha256 != material_digest
                ):
                    raise GuideSufficiencyMutationConflict("idempotency_mismatch")
                operation_id = existing_replay.operation_id
                caller, digest = self._caller(
                    action=action,
                    route="internal:workstream.project.setup/guide-sufficiency",
                    actor_profile_id=actor_profile_id,
                    identity_link_id=identity_link_id,
                    key=key,
                    project_id=project_id,
                    guide_id=guide_id,
                    report_id=adopted_report_id,
                    operation_id=operation_id,
                    lineage=initial,
                    target_kind="run",
                    body=body,
                    material_digest=material_digest,
                    execution_kind=execution_kind,
                    setup_service_custody=setup_service_custody,
                )
                handle = await self._prepare(
                    prepared,
                    action,
                    caller,
                    project_id,
                    self._resource(
                        project_id=project_id,
                        guide_id=guide_id,
                        report_id=adopted_report_id,
                        operation_id=operation_id,
                        request_digest=digest,
                        lineage=initial,
                        target_kind="run",
                        material_digest=material_digest,
                        execution_kind=execution_kind,
                        setup_service_custody=setup_service_custody,
                    ),
                )
                final = await self._lineage(
                    project_id,
                    guide_id,
                    source_snapshot_id,
                    lock=True,
                    require_setup_run=True,
                )
                final = replace(
                    final,
                    stale_output_digest=setup_service_custody.stale_output_digest,
                )
                if final != initial:
                    raise GuideSufficiencyMutationConflict("sufficiency_lineage_stale")
                decision = await prepared.consume(
                    handle,
                    action,
                    caller,
                    self._resource(
                        project_id=project_id,
                        guide_id=guide_id,
                        report_id=adopted_report_id,
                        operation_id=operation_id,
                        request_digest=digest,
                        lineage=final,
                        target_kind="run",
                        material_digest=material_digest,
                        execution_kind=execution_kind,
                        setup_service_custody=setup_service_custody,
                    ),
                )
                self._prove_authority(decision, project_id, execution_kind)
                if existing_replay.resource_context_digest != decision.resource_context_digest:
                    raise GuideSufficiencyMutationConflict("idempotency_mismatch")
                return GuideSufficiencyMutationOutcome(
                    GuideSufficiencyReportResponse.model_validate(existing_replay.response_json),
                    True,
                )
        if material_error is not None:
            raise material_error
        if service_created_report:
            raise GuideSufficiencyMutationConflict("sufficiency_report_provenance_mismatch")
        if first is None or agent_material is None or first_prompt is None:
            raise RuntimeError("guide sufficiency material resolution failed")
        adopting_existing = existing_report is not None
        if adopting_existing:
            assert existing_report is not None
            await self._validate_adoptable_verified_report(
                existing_report,
                initial,
                project_id=project_id,
                guide_id=guide_id,
                material_digest=material_digest,
                material_byte_count=len(first_prompt),
                source_provenance=first.provenance,
            )
            result = None
        else:
            await self._session.rollback()
            try:
                result = await get_project_guide_agent_runtime().analyze_guide_sufficiency(
                    agent_material
                )
            except ProjectAgentRuntimeError:
                raise AgentRuntimeUnavailable(
                    "project guide agent runtime is unavailable"
                ) from None

        try:
            second = await self._material.load(material_request)
        except GuideSufficiencyMaterialUnavailable:
            raise
        second_material = agent_material.model_copy(
            update={
                "source_items": [
                    verified_guide_sufficiency_agent_item(item) for item in second.source_items
                ]
            }
        )
        second_prompt = bounded_canonical_guide_material(second_material)
        second_digest = f"sha256:{hashlib.sha256(second_prompt).hexdigest()}"
        if second_digest != material_digest or second.provenance != first.provenance:
            raise GuideSufficiencyMutationConflict("verified_guide_material_changed")
        final = await self._lineage(
            project_id,
            guide_id,
            source_snapshot_id,
            lock=True,
            require_setup_run=True,
        )
        final = replace(
            final,
            stale_output_digest=setup_service_custody.stale_output_digest,
        )
        if final != initial:
            raise GuideSufficiencyMutationConflict("sufficiency_lineage_stale")
        payload = None
        if result is not None:
            payload = GuideSufficiencyReportCreate(
                source_snapshot_id=str(source_snapshot_id),
                status=cast(
                    Literal["passed", "blocked", "passed_with_warnings"],
                    AGENT_SUFFICIENCY_STATUS_TO_REPORT_STATUS[result.status],
                ),
                findings=[
                    GuideSufficiencyFindingInput.model_validate(finding.model_dump(mode="json"))
                    for finding in result.findings
                ],
                summary=result.summary,
            )
            validate_sufficiency_report_payload(payload)
        caller, digest = self._caller(
            action=action,
            route="internal:workstream.project.setup/guide-sufficiency",
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            report_id=(UUID(existing_report.id) if adopting_existing and existing_report else None),
            operation_id=operation_id,
            lineage=final,
            target_kind="run",
            body=body,
            material_digest=material_digest,
            execution_kind=execution_kind,
            setup_service_custody=setup_service_custody,
        )
        handle = await self._prepare(
            prepared,
            action,
            caller,
            project_id,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=(
                    UUID(existing_report.id) if adopting_existing and existing_report else None
                ),
                operation_id=operation_id,
                request_digest=digest,
                lineage=final,
                target_kind="run",
                material_digest=material_digest,
                execution_kind=execution_kind,
                setup_service_custody=setup_service_custody,
            ),
        )
        decision = await prepared.consume(
            handle,
            action,
            caller,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=(
                    UUID(existing_report.id) if adopting_existing and existing_report else None
                ),
                operation_id=operation_id,
                request_digest=digest,
                lineage=final,
                target_kind="run",
                material_digest=material_digest,
                execution_kind=execution_kind,
                setup_service_custody=setup_service_custody,
            ),
        )
        self._prove_authority(decision, project_id, execution_kind)
        disposition, replay = await self._replay.reserve(
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context_digest=decision.resource_context_digest,
            operation_id=operation_id,
            project_id=str(project_id),
            guide_id=str(guide_id),
            source_snapshot_id=str(source_snapshot_id),
            report_id=(existing_report.id if adopting_existing and existing_report else None),
            setup_run_id=str(final.setup_run_id),
            setup_generation=final.setup_generation,
        )
        if disposition != "claimed":
            raise GuideSufficiencyMutationConflict(f"idempotency_{disposition}")
        setup_run = await self._projects.lock_project_setup_run(str(final.setup_run_id))
        if (
            setup_run is None
            or setup_run.setup_generation != final.setup_generation
            or setup_run.output_sufficiency_report_id is not None
            or (
                setup_run.status not in {"queued", "running_sufficiency_agent"}
                or setup_run.current_step != setup_service_custody.expected_step
                or setup_run.celery_task_id != str(setup_service_custody.task_id)
            )
        ):
            raise GuideSufficiencyMutationConflict("project_setup_run_context_mismatch")
        if adopting_existing:
            assert existing_report is not None
            report = existing_report
            await self._validate_adoptable_verified_report(
                report,
                final,
                project_id=project_id,
                guide_id=guide_id,
                material_digest=material_digest,
                material_byte_count=len(second_prompt),
                source_provenance=second.provenance,
            )
        else:
            assert payload is not None
            report = stage_verified_sufficiency_report(
                self._session,
                report_id=str(uuid4()),
                project_id=str(project_id),
                guide_id=str(guide_id),
                guide_version=final.guide_version,
                source_snapshot_id=str(source_snapshot_id),
                source_snapshot_hash=final.snapshot_hash,
                payload=payload,
                setup_run_id=str(final.setup_run_id),
                setup_generation=final.setup_generation,
                material_sha256=material_digest,
                material_byte_count=len(second_prompt),
                source_provenance=second.provenance,
                created_by=actor_profile_id,
                authority=SufficiencyCreationAuthority(
                    actor_profile_id=actor_profile_id,
                    identity_link_id=identity_link_id,
                    admin_role_grant_id=None,
                    service_identity="workstream.project.setup",
                    scope_type="service",
                    scope_project_id=str(project_id),
                    action_id=action.value,
                    decision_event_id=str(decision.decision_id),
                ),
            )
        setup_run.output_sufficiency_report_id = report.id
        await self._session.flush()
        response = GuideSufficiencyReportResponse.model_validate(report)
        await self._replay.complete(
            replay,
            response_json=response.model_dump(mode="json"),
            report_id=report.id,
        )
        return GuideSufficiencyMutationOutcome(response, False, not adopting_existing)

    async def acknowledge_warnings(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        report_id: UUID,
        payload: GuideSufficiencyAcknowledgement,
    ) -> GuideSufficiencyMutationOutcome:
        """Record one authorized warning acknowledgement."""
        action = ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE
        report = await self._projects.get_guide_sufficiency_report(str(report_id))
        if (
            report is None
            or report.project_id != str(project_id)
            or report.guide_id != str(guide_id)
        ):
            raise SufficiencyReportNotFound("guide sufficiency report not found")
        snapshot_id, operation_id = UUID(report.source_snapshot_id), uuid4()
        initial = await self._lineage(project_id, guide_id, snapshot_id, lock=False)
        caller, digest = self._caller(
            action=action,
            route=(
                "POST /api/v1/projects/{project_id}/guides/{guide_id}/"
                "sufficiency-reports/{report_id}/acknowledge-warnings"
            ),
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            key=key,
            project_id=project_id,
            guide_id=guide_id,
            report_id=report_id,
            operation_id=operation_id,
            lineage=initial,
            target_kind="warning_acknowledgement",
            body=payload.model_dump(mode="json"),
        )
        existing = await self._replay.find(resolved.profile.id, action.value, key)
        if existing is not None:
            if (
                existing.identity_link_id != resolved.identity_link.id
                or existing.request_digest != digest
                or existing.project_id != str(project_id)
                or existing.guide_id != str(guide_id)
                or existing.report_id != str(report_id)
            ):
                raise GuideSufficiencyMutationConflict("idempotency_mismatch")
            if existing.status != "committed" or existing.response_json is None:
                raise GuideSufficiencyMutationConflict("idempotency_pending")
            operation_id = existing.operation_id
            caller, digest = self._caller(
                action=action,
                route=(
                    "POST /api/v1/projects/{project_id}/guides/{guide_id}/"
                    "sufficiency-reports/{report_id}/acknowledge-warnings"
                ),
                actor_profile_id=resolved.profile.id,
                identity_link_id=resolved.identity_link.id,
                key=key,
                project_id=project_id,
                guide_id=guide_id,
                report_id=report_id,
                operation_id=operation_id,
                lineage=initial,
                target_kind="warning_acknowledgement",
                body=payload.model_dump(mode="json"),
            )
        handle = await self._prepare(
            prepared,
            action,
            caller,
            project_id,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=report_id,
                operation_id=operation_id,
                request_digest=digest,
                lineage=initial,
                target_kind="warning_acknowledgement",
            ),
        )
        final = await self._lineage(project_id, guide_id, snapshot_id, lock=True)
        report = await self._projects.lock_guide_sufficiency_report(
            str(report_id), str(project_id), str(guide_id), final.guide_version
        )
        if report is None:
            raise SufficiencyReportNotFound("guide sufficiency report not found")
        if final != initial or report.source_snapshot_hash != final.snapshot_hash:
            raise GuideSufficiencyMutationConflict("sufficiency_lineage_stale")
        if report.status != "passed_with_warnings":
            raise PolicySetupBlocked("only sufficiency warnings can be acknowledged")
        decision = await prepared.consume(
            handle,
            action,
            caller,
            self._resource(
                project_id=project_id,
                guide_id=guide_id,
                report_id=report_id,
                operation_id=operation_id,
                request_digest=digest,
                lineage=final,
                target_kind="warning_acknowledgement",
            ),
        )
        self._prove_human(decision, project_id)
        if existing is not None:
            if existing.resource_context_digest != decision.resource_context_digest:
                raise GuideSufficiencyMutationConflict("idempotency_mismatch")
            return GuideSufficiencyMutationOutcome(
                GuideSufficiencyReportResponse.model_validate(existing.response_json), True
            )
        if report.warnings_acknowledged_at is not None:
            raise GuideSufficiencyMutationConflict("sufficiency_warnings_already_acknowledged")
        disposition, replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context_digest=decision.resource_context_digest,
            operation_id=operation_id,
            project_id=str(project_id),
            guide_id=str(guide_id),
            source_snapshot_id=str(snapshot_id),
            report_id=str(report_id),
            setup_run_id=None,
            setup_generation=final.setup_generation,
        )
        if disposition != "claimed":
            raise GuideSufficiencyMutationConflict(f"idempotency_{disposition}")
        report.warnings_acknowledged_by_role = "project_manager"
        report.warnings_acknowledged_by_actor = resolved.profile.id
        report.warnings_acknowledged_at = datetime.now(UTC)
        report.acknowledgement_note = payload.acknowledgement_note
        report.warnings_acknowledged_by_actor_profile_id = resolved.profile.id
        report.warnings_acknowledged_via_identity_link_id = resolved.identity_link.id
        report.warnings_acknowledged_by_admin_role_grant_id = decision.matched_grant_id
        report.warning_acknowledgement_scope_type = (
            "system" if decision.matched_scope_project_id is None else "project"
        )
        report.warning_acknowledgement_scope_project_id = str(project_id)
        report.warning_acknowledgement_action_id = action.value
        report.warning_acknowledgement_decision_event_id = str(decision.decision_id)
        response = GuideSufficiencyReportResponse.model_validate(report)
        await self._replay.complete(
            replay, response_json=response.model_dump(mode="json"), report_id=report.id
        )
        return GuideSufficiencyMutationOutcome(response, False)
