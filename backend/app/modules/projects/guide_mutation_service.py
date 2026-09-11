"""Authorized guide and source-metadata mutation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples
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
    GuideSourceSnapshotItemResponse,
    GuideSourceSnapshotResponse,
    ProjectGuideCreate,
    ProjectGuideCreateResponse,
    ProjectGuideDocumentResponse,
    ProjectGuideWaitingSetupResponse,
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
    build_guide_source_snapshot_manifest,
    build_guide_source_snapshot_items,
    ProjectService,
)


class GuideMutationIdempotencyConflict(ProjectServiceError):
    """One replay key was reused with incompatible guide-mutation state."""

    status_code = 409


@dataclass(frozen=True, slots=True)
class GuideMutationOutcome:
    """Route-owned transaction result and optional post-commit dispatch facts."""

    response: ProjectGuideResponse | ProjectGuideCreateResponse
    replayed: bool
    setup_run_id: str | None = None
    setup_generation: int | None = None


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
        body_value = body.model_dump(mode="json", exclude_unset=True)
        if action in {ActionId.PROJECT_GUIDE_CREATE, ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE}:
            examples = validate_task_examples(body.task_examples)
            body_value.pop("task_examples")
            body_value["task_examples_hash"] = task_examples_hash(examples)
            body_value["task_examples_count"] = len(examples)
        replay_request = {
            "action_id": action.value,
            "route": route,
            "actor_profile_id": resolved.profile.id,
            "identity_link_id": resolved.identity_link.id,
            "idempotency_key": str(key),
            "project_id": str(project_id),
            "guide_id": str(guide_id) if guide_id is not None else None,
            "body": body_value,
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
        if action is ActionId.PROJECT_GUIDE_CREATE:
            request.update(
                request_digest=digest,
                task_examples_hash=body_value["task_examples_hash"],
                task_examples_count=body_value["task_examples_count"],
            )
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
        examples = validate_task_examples(payload.task_examples)
        examples_hash = task_examples_hash(examples)
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
        existing = await self._replay_creation(resolved, prepared, key, project_id, payload, digest)
        if existing is not None:
            return existing
        snapshot_id, source_operation_id = uuid4(), uuid4()
        manifest, sanitized = build_guide_source_snapshot_manifest(
            payload, snapshot_id=str(snapshot_id), generation=1,
            task_examples=examples, expected_task_examples_hash=examples_hash,
        )
        source_action = ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE
        source_caller, source_digest = self._input(
            source_action, "POST /api/v1/projects/{project_id}/guides", resolved, key, payload,
            project_id=project_id, guide_id=guide_id,
            target_resource_id=snapshot_id, operation_id=source_operation_id,
        )
        handle = await self._prepare(
            prepared, action, caller, project_id, guide_id=None, target_kind="guide_create",
        )
        source_handle = await self._prepare(
            prepared, source_action, source_caller, project_id,
            guide_id=guide_id, target_kind="source_snapshot_create",
        )
        project = await self._repo.get_project(str(project_id), for_update=True)
        if project is None:
            raise ProjectNotFound("project not found")
        # A concurrent exact replay can miss the optimistic lookup and then wait
        # on this project lock. Re-read the ledger after the lock so the winner's
        # committed response takes precedence over the natural version conflict.
        existing = await self._replay_creation(resolved, prepared, key, project_id, payload, digest)
        if existing is not None:
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
            request_digest=digest,
            task_examples_hash=examples_hash,
            task_examples_count=len(examples),
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
        if disposition != "claimed":
            raise GuideMutationIdempotencyConflict("idempotency_pending")
        source_resource = self._source_resource(
            project_id, guide_id, payload.version, snapshot_id,
            canonical_json_hash(manifest), source_operation_id,
        )
        source_decision = await prepared.consume(
            source_handle, source_action, source_caller, source_resource,
        )
        self._prove(source_decision, project_id)
        source_disposition, source_replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=source_action.value, idempotency_key=key,
            request_digest=source_digest,
            resource_context_digest=source_decision.resource_context_digest,
            operation_id=source_operation_id, project_id=str(project_id),
            resource_id=str(snapshot_id), operation_generation=1,
        )
        if source_disposition != "claimed":
            raise GuideMutationIdempotencyConflict("idempotency_pending")
        guide = ProjectGuide(
            id=str(guide_id),
            project_id=str(project_id),
            version=payload.version,
            status="draft",
            task_examples=[item.model_dump(mode="json") for item in examples],
            task_examples_hash=examples_hash,
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
        items, setup = await self._initialize_documents(
            resolved, guide, snapshot_id, manifest, sanitized, source_decision, source_replay,
        )
        response = ProjectGuideCreateResponse(
            **ProjectGuideResponse.model_validate(guide).model_dump(),
            documents=[ProjectGuideDocumentResponse(
                document_id=UUID(item.id), label=item.source_label,
                media_type=item.media_type, order=item.item_order,
            ) for item in items],
            setup=ProjectGuideWaitingSetupResponse(id=UUID(setup.id)),
        )
        await self._replay.complete(replay, response_json=response.model_dump(mode="json"))
        return GuideMutationOutcome(response, False, setup.id, setup.setup_generation)

    @staticmethod
    def _source_resource(project_id, guide_id, version, snapshot_id, bundle_hash, operation_id):
        return ProjectGuideSourceSnapshotMutationResourceContext(
            resource_type="project_guide_source_snapshot_mutation",
            resource_id=snapshot_id, operation_id=operation_id,
            scope_project_id=project_id, guide_id=guide_id, guide_version=version,
            guide_status="draft", source_snapshot_id=snapshot_id,
            source_snapshot_hash=bundle_hash, predecessor_snapshot_id=None,
            predecessor_snapshot_hash=None, operation_generation=1,
        )

    async def _replay_creation(self, resolved, prepared, key, project_id, payload, digest):
        """Reauthorize both immutable original operations before returning a replay."""
        action = ActionId.PROJECT_GUIDE_CREATE
        source_action = ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE
        root = await self._replay.find(resolved.profile.id, action.value, key)
        source = await self._replay.find(resolved.profile.id, source_action.value, key)
        if root is None and source is None:
            return None
        if root is None or source is None:
            raise GuideMutationIdempotencyConflict("idempotency_pending")
        for record in (root, source):
            if (record.identity_link_id != resolved.identity_link.id
                    or record.project_id != str(project_id)):
                raise GuideMutationIdempotencyConflict("idempotency_mismatch")
            if record.status != "committed" or record.response_json is None:
                raise GuideMutationIdempotencyConflict("idempotency_pending")
        if root.request_digest != digest:
            raise GuideMutationIdempotencyConflict("idempotency_mismatch")
        guide = await self._repo.get_guide_by_version(str(project_id), payload.version)
        snapshot = await self._repo.get_guide_source_snapshot(source.resource_id)
        setup = await self._repo.get_project_setup_run(source.setup_run_id) if source.setup_run_id else None
        if (guide is None or guide.id != root.resource_id or snapshot is None
                or snapshot.guide_id != guide.id or snapshot.project_id != guide.project_id
                or snapshot.guide_version != guide.version or snapshot.creation_generation != 1
                or setup is None or setup.guide_id != guide.id
                or setup.source_snapshot_id != snapshot.id
                or setup.source_snapshot_hash != snapshot.bundle_hash):
            raise GuideMutationIdempotencyConflict("idempotency_mismatch")
        items = await self._repo.list_guide_source_snapshot_items(snapshot.id)
        await ProjectService(self._session).validate_source_snapshot_integrity(
            snapshot, GuideMutationIdempotencyConflict, persisted_items=items,
        )
        response = ProjectGuideCreateResponse.model_validate(root.response_json)
        if (str(response.setup.id) != setup.id
                or [str(item.document_id) for item in response.documents] != [item.id for item in items]):
            raise GuideMutationIdempotencyConflict("idempotency_mismatch")
        guide_id, snapshot_id = UUID(guide.id), UUID(snapshot.id)
        examples = validate_task_examples(payload.task_examples)
        resources = (
            ProjectGuideMutationResourceContext(
                resource_type="project_guide_mutation", resource_id=guide_id,
                operation_id=root.operation_id, scope_project_id=project_id,
                guide_id=guide_id, target_kind="create", guide_exists=False,
                operation_generation=1, request_digest=digest,
                task_examples_hash=task_examples_hash(examples), task_examples_count=len(examples),
            ),
            self._source_resource(project_id, guide_id, guide.version, snapshot_id,
                                  snapshot.bundle_hash, source.operation_id),
        )
        for record, resource, current_action, target in (
            (root, resources[0], action, "guide_create"),
            (source, resources[1], source_action, "source_snapshot_create"),
        ):
            caller, current_digest = self._input(
                current_action, "POST /api/v1/projects/{project_id}/guides", resolved, key, payload,
                project_id=project_id, guide_id=None if record is root else guide_id,
                target_resource_id=resource.resource_id, operation_id=record.operation_id,
            )
            if current_digest != record.request_digest:
                raise GuideMutationIdempotencyConflict("idempotency_mismatch")
            handle = await self._prepare(
                prepared, current_action, caller, project_id,
                guide_id=None if record is root else guide_id, target_kind=target,
            )
            decision = await prepared.consume(handle, current_action, caller, resource)
            self._prove(decision, project_id)
            if decision.resource_context_digest != record.resource_context_digest:
                raise GuideMutationIdempotencyConflict("idempotency_mismatch")
        return GuideMutationOutcome(response, True, setup.id, setup.setup_generation)

    async def _initialize_documents(
        self, resolved, guide, snapshot_id, manifest, sanitized, decision, replay,
    ):
        """Write the one document set inside its guide-create transaction."""
        action = ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE
        project_id = UUID(guide.project_id)
        generation = 1
        snapshot_hash = canonical_json_hash(manifest)
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
        setup_generation = await self._repo.next_project_setup_generation(guide.id)
        setup_run = ProjectSetupRun(
            id=str(uuid4()),
            project_id=guide.project_id,
            guide_id=guide.id,
            guide_version=guide.version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            setup_generation=setup_generation,
            status="awaiting_documents",
            current_step="awaiting_documents",
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
            setup_run_id=setup_run.id,
        )
        return items, setup_run

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
