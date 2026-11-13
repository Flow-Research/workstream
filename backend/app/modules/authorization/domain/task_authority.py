"""Exact resource and prepared rules for the bounded task-authority cutover."""

import json
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from app.modules.authorization.catalogue import ActionAvailability, ActionId, TASK_CONCEALED_READ_ACTIONS, TASK_LOCKED_CONTEXT_READ_ACTIONS
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind


TASK_CONTRIBUTOR_READ_ACTIONS = frozenset({
    ActionId.TASK_READ, ActionId.TASK_SUBMISSION_REQUIREMENTS_READ, ActionId.TASK_WORK_CONTEXT_READ,
})
TASK_PROJECT_ROLE_READ_ACTIONS = frozenset({ActionId.TASK_READ})
TASK_MANAGER_READ_ACTIONS = frozenset({
    ActionId.PROJECT_TASK_READ, ActionId.PROJECT_TASK_SUBMISSION_REQUIREMENTS_READ,
    ActionId.PROJECT_TASK_WORK_CONTEXT_READ,
})

TASK_SUBMITTER_ACTIONS = frozenset(
    {
        ActionId.TASK_CLAIM,
        ActionId.TASK_GUIDE_READ,
        ActionId.TASK_SUBMISSION_REQUIREMENTS_READ,
        ActionId.TASK_WORK_CONTEXT_READ,
    }
)
TASK_PROJECT_ROLE_ACTIONS = TASK_SUBMITTER_ACTIONS | TASK_PROJECT_ROLE_READ_ACTIONS
TASK_MANAGER_ACTIONS = frozenset({
    ActionId.PROJECT_TASK_CREATE, ActionId.PROJECT_TASK_SCREEN, ActionId.PROJECT_TASK_RELEASE,
    ActionId.PROJECT_TASK_REVISION_REPAIR,
})
TASK_IMPORT_BATCH_ACTIONS = frozenset({ActionId.PROJECT_TASK_IMPORT, ActionId.PROJECT_TASK_IMPORT_BATCH_READ})
TASK_ACTIONS = TASK_PROJECT_ROLE_ACTIONS | TASK_MANAGER_ACTIONS | TASK_MANAGER_READ_ACTIONS | TASK_LOCKED_CONTEXT_READ_ACTIONS | {
    ActionId.AUDIT_TASK_EVIDENCE_READ,
}


class TaskAuthorityResourceContext(BaseModel):
    """TASK-locked facts remain exact through AUTH preparation and consumption."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["task_authority"] = "task_authority"
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    task_status: str
    assigned_to: UUID | None
    assignment_id: UUID | None
    assignment_contributor_id: UUID | None
    locked_context_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str | None
    idempotency_key: UUID | None = None
    replay_assignment_id: UUID | None = None
    request_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    replay_command_id: UUID | None = None
    revision_preparation_id: UUID | None = None
    revision_preparation_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    revision_routing_manifest_id: UUID | None = None
    revision_replay_preparation_id: UUID | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        """Keep pre-existing TASK authority evidence exactly shaped on other actions."""
        values = handler(self)
        revision_keys = (
            "revision_preparation_id", "revision_preparation_sha256",
            "revision_routing_manifest_id", "revision_replay_preparation_id",
        )
        if all(values.get(key) is None for key in revision_keys):
            for key in revision_keys:
                values.pop(key, None)
        return values


class TaskImportBatchResourceContext(BaseModel):
    """Exact native batch, selected byte ancestry and original manifest under fresh PM authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    resource_type: Literal["task_import_batch"] = "task_import_batch"
    resource_id: UUID
    scope_project_id: UUID
    source_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)
    row_count: int = Field(ge=1, le=500)
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_binding_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def parse_task_authority_binding(
    action: ActionId, request: Mapping[str, object], invalid_error: type[Exception],
    idempotency_key: UUID,
) -> TaskAuthorityResourceContext | TaskImportBatchResourceContext | None:
    """Keep the complete task commitment typed and immutable through consumption."""
    if action not in TASK_ACTIONS | TASK_IMPORT_BATCH_ACTIONS:
        return None
    try:
        model = TaskImportBatchResourceContext if action in TASK_IMPORT_BATCH_ACTIONS else TaskAuthorityResourceContext
        resource = model.model_validate_json(json.dumps(dict(request)))
        if resource.idempotency_key is not None and resource.idempotency_key != idempotency_key:
            raise ValueError("task key differs from prepared binding")
        return resource
    except (TypeError, ValueError) as exc:
        raise invalid_error("invalid prepared authorization handle") from exc


def _revision_repair_resource_guard(resource: TaskAuthorityResourceContext) -> bool:
    """Require the exact current or committed-child replay shape for PM repair."""
    return (
        resource.revision_routing_manifest_id is not None
        and ((resource.revision_preparation_id is None) ==
             (resource.revision_preparation_sha256 is None))
        and (
            resource.task_status == "needs_revision"
            or (
                resource.revision_replay_preparation_id is not None
                and resource.task_status in {
                    "submitted", "evaluation_pending", "review_pending", "accepted", "rejected",
                }
            )
        )
        and resource.assignment_id is not None
        and resource.assignment_contributor_id is not None
        and resource.assigned_to == resource.assignment_contributor_id
        and resource.reason is not None
        and bool(resource.reason.strip())
        and len(resource.reason) <= 1000
        and resource.idempotency_key is not None
        and resource.request_digest is not None
        and resource.replay_assignment_id is None
        and resource.replay_command_id is None
    )


def task_resource_guard(action: ActionId, resource: TaskAuthorityResourceContext) -> bool:
    """No authority allow may substitute for assignment and task currentness."""
    revision_fields = (
        resource.revision_preparation_id,
        resource.revision_preparation_sha256,
        resource.revision_routing_manifest_id,
        resource.revision_replay_preparation_id,
    )
    if action is ActionId.PROJECT_TASK_REVISION_REPAIR:
        return _revision_repair_resource_guard(resource)
    if any(value is not None for value in revision_fields):
        return False
    if action in TASK_MANAGER_ACTIONS:
        if (resource.idempotency_key is None or resource.request_digest is None
                or resource.replay_assignment_id is not None):
            return False
        if resource.replay_command_id is not None:
            # TASK supplies only a committed receipt from this actor/action/key.
            # Fresh authority precedes TASK replay currentness/conflict checks.
            return True
        if any(value is not None for value in (resource.assigned_to, resource.assignment_id,
                                               resource.assignment_contributor_id)):
            return False
        return resource.task_status == {
            ActionId.PROJECT_TASK_CREATE: "draft", ActionId.PROJECT_TASK_SCREEN: "draft",
            ActionId.PROJECT_TASK_RELEASE: "screening",
        }[action]
    if action in TASK_CONCEALED_READ_ACTIONS and any(value is not None for value in (
        resource.idempotency_key, resource.replay_assignment_id, resource.request_digest, resource.replay_command_id,
    )):
        return False
    if resource.request_digest is not None or resource.replay_command_id is not None:
        return False
    own_assignment = (
        resource.assignment_id is not None
        and resource.assignment_contributor_id == resource.actor_profile_id
        and resource.assigned_to == resource.actor_profile_id
    )
    unassigned_ready = (
        resource.task_status == "ready"
        and resource.assigned_to is None
        and resource.assignment_id is None
        and resource.assignment_contributor_id is None
    )
    if resource.replay_assignment_id is not None:
        if (
            resource.idempotency_key is None
            or resource.replay_assignment_id != resource.assignment_id
        ):
            return False
        if action is ActionId.TASK_CLAIM:
            return resource.task_status in {"in_progress", "needs_revision", "evaluation_pending", "review_pending"} and own_assignment
        return False
    if action is ActionId.TASK_CLAIM:
        return unassigned_ready
    if action in TASK_CONTRIBUTOR_READ_ACTIONS:
        return unassigned_ready or own_assignment
    if action is ActionId.TASK_GUIDE_READ:
        return own_assignment
    return action in TASK_MANAGER_READ_ACTIONS | TASK_LOCKED_CONTEXT_READ_ACTIONS | {ActionId.AUDIT_TASK_EVIDENCE_READ}


def evaluate_task_authority(action, context, authority, resource, lifecycle_denial):
    """Evaluate exact TASK facts against the authority already locked by AUTH."""
    denial = lifecycle_denial
    if denial is None and action.availability is not ActionAvailability.ACTIVE:
        denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
    if denial is None and (
        not isinstance(resource, TaskAuthorityResourceContext)
        or resource.scope_project_id != authority.scope_project_id
        or resource.actor_profile_id != context.actor_profile_id
        or resource.identity_link_id != context.identity_link_id
        or not task_resource_guard(action.action_id, resource)
    ):
        denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if denial is None and (
        authority.matched_grant_id is None or authority.matched_grant_status != "active"
    ):
        denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    if denial is not None:
        return denial, None, None, None
    matched_kind = (
        MatchedAuthorityKind.PROJECT_ROLE_GRANT if action.action_id in TASK_PROJECT_ROLE_ACTIONS
        else MatchedAuthorityKind.ADMIN_ROLE_GRANT
    )
    return None, matched_kind, authority.matched_grant_id, authority.scope_project_id
