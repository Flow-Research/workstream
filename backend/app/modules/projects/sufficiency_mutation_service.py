"""Authorized guide-sufficiency mutation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import AsyncIterator, Literal, cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy.exc import IntegrityError
from app.core.hashing import canonical_json_hash
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
)
from app.modules.projects.models import GuideSufficiencyReport
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.schemas import (
    GuideSufficiencyAcknowledgement,
    GuideSufficiencyReportCreate,
    GuideSufficiencyReportResponse,
)
from app.modules.projects.service import (
    GuideEditBlocked,
    GuideNotFound,
    PolicySetupBlocked,
    PolicySetupConflict,
    ProjectService,
    ProjectServiceError,
    SufficiencyReportNotFound,
    validate_sufficiency_report_payload,
)
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

    def __init__(self, session) -> None:
        self._session = session
        self._projects = ProjectRepository(session)
        self._replay = GuideSufficiencyMutationReplayRepository(session)
        self._validation = ProjectService(session)

    @staticmethod
    def _prove_human(decision, project_id: UUID) -> None:
        if (
            decision.matched_authority_kind is not MatchedAuthorityKind.ADMIN_ROLE_GRANT
            or decision.matched_grant_id is None
            or decision.matched_scope_project_id not in {None, project_id}
        ):
            raise RuntimeError("sufficiency mutation lacked Project Manager authority")

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
            "execution_kind": "human",
            "setup_service_custody": None,
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
            "execution_kind": "human",
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
            execution_kind="human",
            sufficiency_report_id=report_id,
            setup_generation=lineage.setup_generation,
            stale_output_digest=lineage.stale_output_digest,
            material_digest=material_digest,
            setup_service_custody=None,
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
        if report.project_setup_run_id is not None:
            setup_run = await self._projects.lock_project_setup_run(report.project_setup_run_id)
            if (
                setup_run is None
                or setup_run.id != str(final.setup_run_id)
                or setup_run.setup_generation != final.setup_generation
                or report.setup_generation != final.setup_generation
                or setup_run.output_sufficiency_report_id != report.id
                or setup_run.output_submission_artifact_policy_id is not None
            ):
                raise GuideSufficiencyMutationConflict("project_setup_run_context_mismatch")
        response = GuideSufficiencyReportResponse.model_validate(report)
        await self._replay.complete(
            replay, response_json=response.model_dump(mode="json"), report_id=report.id
        )
        return GuideSufficiencyMutationOutcome(response, False)
