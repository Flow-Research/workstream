"""Authorized guide and source-metadata mutation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectGuideMutationResourceContext,
    ProjectGuideMutationPrepareDenialResourceContext,
    ProjectGuideSourceSnapshotMutationResourceContext,
)
from app.modules.projects.guide_mutation_repository import GuideMutationRepository
from app.modules.projects.models import (
    GuideSourceSnapshot,
    ProjectGuide,
    ProjectSetupRun,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import (
    GuideSourceSnapshotCreate,
    GuideSourceSnapshotItemResponse,
    GuideSourceSnapshotResponse,
    ProjectGuideCreate,
    ProjectGuideResponse,
    ProjectGuideUpdate,
)
from app.modules.projects.service import (
    GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION,
    GuideEditBlocked,
    GuideNotFound,
    GuideVersionConflict,
    ProjectNotFound,
    ProjectServiceError,
    PolicySetupBlocked,
    build_guide_source_snapshot_manifest,
    build_guide_source_snapshot_items,
)


class GuideMutationIdempotencyConflict(ProjectServiceError):
    """One replay key was reused with incompatible guide-mutation state."""

    status_code = 409


@dataclass(frozen=True, slots=True)
class GuideMutationOutcome:
    """Route-owned transaction result and optional post-commit dispatch facts."""

    response: ProjectGuideResponse | GuideSourceSnapshotResponse
    replayed: bool
    setup_run_id: str | None = None


class GuideMutationService:
    """Consume exact Project Manager authority before guide metadata writes."""

    def __init__(self, session) -> None:
        self._session = session
        self._repo = ProjectRepository(session)
        self._replay = GuideMutationRepository(session)

    @staticmethod
    def _input(
        action: ActionId,
        route: str,
        resolved: ResolvedActor,
        key: UUID,
        body,
        *,
        project_id: UUID,
        guide_id: UUID | None = None,
        target_resource_id: UUID,
        operation_id: UUID,
    ) -> tuple[PreparedAuthorizationInput, str]:
        replay_request = {
            "action_id": action.value,
            "route": route,
            "actor_profile_id": resolved.profile.id,
            "identity_link_id": resolved.identity_link.id,
            "idempotency_key": str(key),
            "project_id": str(project_id),
            "guide_id": str(guide_id) if guide_id is not None else None,
            "body": body.model_dump(mode="json", exclude_unset=True),
        }
        digest = canonical_json_hash(
            {"domain": "workstream.guide_mutation.idempotency.v1", **replay_request}
        )
        request = {
            **replay_request,
            "guide_id": str(guide_id or target_resource_id),
            "target_resource_id": str(target_resource_id),
            "operation_id": str(operation_id),
        }
        return PreparedAuthorizationInput(idempotency_key=key, request_value=request), digest

    async def _existing(self, resolved, action, key, digest, response_type):
        record = await self._replay.find(resolved.profile.id, action.value, key)
        if record is None:
            return None
        if record.identity_link_id != resolved.identity_link.id or record.request_digest != digest:
            raise GuideMutationIdempotencyConflict("idempotency_mismatch")
        if record.status != "committed" or record.response_json is None:
            raise GuideMutationIdempotencyConflict("idempotency_pending")
        return GuideMutationOutcome(response_type.model_validate(record.response_json), True)

    @staticmethod
    def _reservation_outcome(disposition, record, response_type):
        """Return an exact concurrent replay or raise the bounded conflict."""
        if disposition == "claimed":
            return None
        if disposition == "mismatch":
            raise GuideMutationIdempotencyConflict("idempotency_mismatch")
        if disposition == "pending" or record.response_json is None:
            raise GuideMutationIdempotencyConflict("idempotency_pending")
        return GuideMutationOutcome(
            response=response_type.model_validate(record.response_json),
            replayed=True,
        )

    @staticmethod
    def _prove(decision, project_id: UUID) -> None:
        if (
            decision.matched_authority_kind is not MatchedAuthorityKind.ADMIN_ROLE_GRANT
            or decision.matched_grant_id is None
            or decision.matched_scope_project_id not in {None, project_id}
        ):
            raise RuntimeError("guide mutation unexpectedly lacked Project Manager authority")

    async def _prepare(
        self,
        prepared,
        action: ActionId,
        caller: PreparedAuthorizationInput,
        project_id: UUID,
        *,
        guide_id: UUID | None,
        target_kind: str,
    ):
        """Prepare authority or persist one bounded denial without product locks."""
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
            denial_resource = ProjectGuideMutationPrepareDenialResourceContext(
                resource_type="project_guide_mutation_request",
                resource_id=guide_id or project_id,
                scope_project_id=project_id,
                requested_guide_id=guide_id,
                requested_target_kind=target_kind,
            )
            await prepared.deny_unsupported(action, caller, denial_resource, exc)

    async def create_guide(
        self, resolved, prepared, key: UUID, project_id: UUID, payload: ProjectGuideCreate
    ) -> GuideMutationOutcome:
        action = ActionId.PROJECT_GUIDE_CREATE
        guide_id, operation_id = uuid4(), uuid4()
        caller, digest = self._input(
            action,
            "POST /api/v1/projects/{project_id}/guides",
            resolved,
            key,
            payload,
            project_id=project_id,
            target_resource_id=guide_id,
            operation_id=operation_id,
        )
        existing = await self._existing(resolved, action, key, digest, ProjectGuideResponse)
        if existing:
            return existing
        handle = await self._prepare(
            prepared,
            action,
            caller,
            project_id,
            guide_id=None,
            target_kind="guide_create",
        )
        project = await self._repo.get_project(str(project_id), for_update=True)
        if project is None:
            raise ProjectNotFound("project not found")
        # A concurrent exact replay can miss the optimistic lookup and then wait
        # on this project lock. Re-read the ledger after the lock so the winner's
        # committed response takes precedence over the natural version conflict.
        existing = await self._existing(
            resolved, action, key, digest, ProjectGuideResponse
        )
        if existing:
            return existing
        if await self._repo.get_guide_by_version(str(project_id), payload.version):
            raise GuideVersionConflict("guide version already exists for project")
        resource = ProjectGuideMutationResourceContext(
            resource_type="project_guide_mutation",
            resource_id=guide_id,
            operation_id=operation_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            target_kind="create",
            guide_exists=False,
            operation_generation=1,
        )
        decision = await prepared.consume(handle, action, caller, resource)
        self._prove(decision, project_id)
        disposition, replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context_digest=decision.resource_context_digest,
            operation_id=operation_id,
            project_id=str(project_id),
            resource_id=str(guide_id),
            operation_generation=1,
        )
        concurrent = self._reservation_outcome(disposition, replay, ProjectGuideResponse)
        if concurrent is not None:
            return concurrent
        guide = ProjectGuide(
            id=str(guide_id),
            project_id=str(project_id),
            version=payload.version,
            status="draft",
            content_markdown=payload.content_markdown,
            change_summary=payload.change_summary,
            created_by=resolved.profile.id,
            mutation_generation=1,
            last_mutated_by_actor_profile_id=resolved.profile.id,
            last_mutated_via_identity_link_id=resolved.identity_link.id,
            last_mutated_by_admin_role_grant_id=decision.matched_grant_id,
            last_mutation_scope_type="system"
            if decision.matched_scope_project_id is None
            else "project",
            last_mutation_scope_project_id=str(decision.matched_scope_project_id)
            if decision.matched_scope_project_id
            else None,
            last_mutation_action_id=action.value,
            last_authorization_decision_event_id=str(decision.decision_id),
        )
        await self._repo.add_guide(guide)
        response = ProjectGuideResponse.model_validate(guide)
        await self._replay.complete(replay, response_json=response.model_dump(mode="json"))
        return GuideMutationOutcome(response, False)

    async def create_snapshot(
        self,
        resolved,
        prepared,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        payload: GuideSourceSnapshotCreate,
    ) -> GuideMutationOutcome:
        action = ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE
        snapshot_id, operation_id = uuid4(), uuid4()
        caller, digest = self._input(
            action,
            "POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots",
            resolved,
            key,
            payload,
            project_id=project_id,
            guide_id=guide_id,
            target_resource_id=snapshot_id,
            operation_id=operation_id,
        )
        existing = await self._existing(resolved, action, key, digest, GuideSourceSnapshotResponse)
        if existing:
            return existing
        handle = await self._prepare(
            prepared,
            action,
            caller,
            project_id,
            guide_id=guide_id,
            target_kind="source_snapshot_create",
        )
        project = await self._repo.get_project(str(project_id), for_update=True)
        guide = await self._repo.lock_project_guide(str(guide_id))
        if project is None:
            raise ProjectNotFound("project not found")
        if guide is None or guide.project_id != str(project_id):
            raise GuideNotFound("guide not found")
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can receive source snapshots")
        predecessor = await self._repo.lock_latest_guide_source_snapshot(
            str(project_id), guide.id, guide.version
        )
        manifest, sanitized = build_guide_source_snapshot_manifest(payload, guide)
        try:
            snapshot_hash = canonical_json_hash(manifest)
        except ValueError:
            raise PolicySetupBlocked(
                "canonical JSON cannot contain non-finite numbers"
            ) from None
        generation = (predecessor.creation_generation or 0) + 1 if predecessor else 1
        resource = ProjectGuideSourceSnapshotMutationResourceContext(
            resource_type="project_guide_source_snapshot_mutation",
            resource_id=snapshot_id,
            operation_id=operation_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            guide_version=guide.version,
            guide_status=guide.status,
            source_snapshot_id=snapshot_id,
            source_snapshot_hash=snapshot_hash,
            predecessor_snapshot_id=UUID(predecessor.id) if predecessor else None,
            predecessor_snapshot_hash=predecessor.bundle_hash if predecessor else None,
            operation_generation=generation,
        )
        decision = await prepared.consume(handle, action, caller, resource)
        self._prove(decision, project_id)
        disposition, replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context_digest=decision.resource_context_digest,
            operation_id=operation_id,
            project_id=str(project_id),
            resource_id=str(snapshot_id),
            operation_generation=generation,
        )
        concurrent = self._reservation_outcome(disposition, replay, GuideSourceSnapshotResponse)
        if concurrent is not None:
            return concurrent
        provenance = dict(
            created_by_actor_profile_id=resolved.profile.id,
            created_via_identity_link_id=resolved.identity_link.id,
            created_by_admin_role_grant_id=decision.matched_grant_id,
            creation_scope_type="system"
            if decision.matched_scope_project_id is None
            else "project",
            creation_scope_project_id=str(decision.matched_scope_project_id)
            if decision.matched_scope_project_id
            else None,
            creation_action_id=action.value,
            authorization_decision_event_id=str(decision.decision_id),
        )
        snapshot = GuideSourceSnapshot(
            id=str(snapshot_id),
            project_id=str(project_id),
            guide_id=guide.id,
            guide_version=guide.version,
            manifest_schema_version=GUIDE_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            manifest_json=manifest,
            bundle_hash=snapshot_hash,
            captured_by=resolved.profile.id,
            creation_generation=generation,
            **provenance,
        )
        items = build_guide_source_snapshot_items(snapshot.id, sanitized)
        await self._repo.add_guide_source_snapshot(snapshot, items)
        setup_run = None
        if get_settings().project_setup_pipeline_autostart:
            setup_generation = await self._repo.next_project_setup_generation(guide.id)
            setup_run = ProjectSetupRun(
                id=str(uuid4()),
                project_id=guide.project_id,
                guide_id=guide.id,
                guide_version=guide.version,
                source_snapshot_id=snapshot.id,
                source_snapshot_hash=snapshot.bundle_hash,
                setup_generation=setup_generation,
                status="queued",
                current_step="queued",
                created_by=resolved.profile.id,
                authorized_by_actor_profile_id=resolved.profile.id,
                authorized_via_identity_link_id=resolved.identity_link.id,
                authorized_by_admin_role_grant_id=decision.matched_grant_id,
                authorization_scope_type=provenance["creation_scope_type"],
                authorization_scope_project_id=provenance["creation_scope_project_id"],
                authorization_action_id=action.value,
                authorization_decision_event_id=str(decision.decision_id),
            )
            await self._repo.add_project_setup_run(setup_run)
        response = GuideSourceSnapshotResponse.model_validate(snapshot)
        response.items = [GuideSourceSnapshotItemResponse.model_validate(item) for item in items]
        await self._replay.complete(
            replay,
            response_json=response.model_dump(mode="json"),
            setup_run_id=setup_run.id if setup_run else None,
        )
        return GuideMutationOutcome(response, False, setup_run.id if setup_run else None)

    async def update_guide(
        self,
        resolved,
        prepared,
        key: UUID,
        project_id: UUID,
        guide_id: UUID,
        payload: ProjectGuideUpdate,
    ) -> GuideMutationOutcome:
        action = ActionId.PROJECT_GUIDE_UPDATE
        operation_id = uuid4()
        caller, digest = self._input(
            action,
            "PATCH /api/v1/projects/{project_id}/guides/{guide_id}",
            resolved,
            key,
            payload,
            project_id=project_id,
            guide_id=guide_id,
            target_resource_id=guide_id,
            operation_id=operation_id,
        )
        existing = await self._existing(resolved, action, key, digest, ProjectGuideResponse)
        if existing:
            return existing
        handle = await self._prepare(
            prepared,
            action,
            caller,
            project_id,
            guide_id=guide_id,
            target_kind="guide_update",
        )
        project = await self._repo.get_project(str(project_id), for_update=True)
        guide = await self._repo.lock_project_guide(str(guide_id))
        if project is None:
            raise ProjectNotFound("project not found")
        if guide is None or guide.project_id != str(project_id):
            raise GuideNotFound("guide not found")
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can be edited")
        predecessor = await self._repo.lock_latest_guide_source_snapshot(
            str(project_id), guide.id, guide.version
        )
        changes = payload.model_dump(exclude_unset=True)
        if predecessor is not None and "content_markdown" in changes:
            raise GuideEditBlocked(
                "guide source material cannot change after a source snapshot exists"
            )
        generation = (guide.mutation_generation or 0) + 1
        resource = ProjectGuideMutationResourceContext(
            resource_type="project_guide_mutation",
            resource_id=guide_id,
            operation_id=operation_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            target_kind="update",
            guide_exists=True,
            guide_status=guide.status,
            guide_version=guide.version,
            predecessor_snapshot_id=UUID(predecessor.id) if predecessor else None,
            predecessor_snapshot_hash=predecessor.bundle_hash if predecessor else None,
            operation_generation=generation,
        )
        decision = await prepared.consume(handle, action, caller, resource)
        self._prove(decision, project_id)
        disposition, replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=digest,
            resource_context_digest=decision.resource_context_digest,
            operation_id=operation_id,
            project_id=str(project_id),
            resource_id=guide.id,
            operation_generation=generation,
        )
        concurrent = self._reservation_outcome(disposition, replay, ProjectGuideResponse)
        if concurrent is not None:
            return concurrent
        for field, value in changes.items():
            setattr(guide, field, value)
        guide.mutation_generation = generation
        guide.last_mutated_by_actor_profile_id = resolved.profile.id
        guide.last_mutated_via_identity_link_id = resolved.identity_link.id
        guide.last_mutated_by_admin_role_grant_id = decision.matched_grant_id
        guide.last_mutation_scope_type = (
            "system" if decision.matched_scope_project_id is None else "project"
        )
        guide.last_mutation_scope_project_id = (
            str(decision.matched_scope_project_id) if decision.matched_scope_project_id else None
        )
        guide.last_mutation_action_id = action.value
        guide.last_authorization_decision_event_id = str(decision.decision_id)
        await self._session.flush()
        await self._session.refresh(guide)
        response = ProjectGuideResponse.model_validate(guide)
        await self._replay.complete(replay, response_json=response.model_dump(mode="json"))
        return GuideMutationOutcome(response, False)
