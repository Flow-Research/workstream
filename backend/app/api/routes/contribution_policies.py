"""Public Finance-authorized ContributionPolicy administration."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.contribution_policies import (
    IDEMPOTENCY_PARAMETER, PolicyRequest, commit_policy_response, get_policy_request,
    require_policy_key,
)
from app.core.api_controls import ApiErrorResponse
from app.modules.contributions.api import (
    ContributionPolicyCreateDraftRequest, ContributionPolicyMutationResult,
    ContributionPolicyProjectReadRequest, ContributionPolicyProjectSelection,
    ContributionPolicyPublishRequest, ContributionPolicyReadRequest,
    ContributionPolicyRetireRequest, ContributionPolicyUpdateDraftRequest, ContributionPolicyView,
)
from app.modules.contributions.api.policy_http import PolicyCreateInput, PolicyDecisionInput, PolicyUpdateInput

router = APIRouter(
    prefix="/projects/{project_id}/contribution-policies", tags=["contribution-policies"],
    dependencies=[Depends(enforce_human_authorization_read)],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
)
RequestOwner = Annotated[PolicyRequest, Depends(get_policy_request)]
ReplayKey = Annotated[UUID, Depends(require_policy_key)]


@router.get("/current", response_model=ContributionPolicyProjectSelection,
            openapi_extra={"x-workstream-action-id": "contribution.policy.read"})
async def discover_policy(project_id: UUID, request: RequestOwner) -> ContributionPolicyProjectSelection:
    """Recover exact draft and published selectors under current Finance authority."""
    response = await request.service.read_current(ContributionPolicyProjectReadRequest(
        project_id=project_id, actor_profile_id=request.actor_profile_id,
    ))
    return await commit_policy_response(request, response, ContributionPolicyProjectSelection)


@router.get("/{policy_id}", response_model=ContributionPolicyView,
            openapi_extra={"x-workstream-action-id": "contribution.policy.read"})
async def read_policy(
    project_id: UUID, policy_id: UUID, request: RequestOwner, version_id: UUID | None = None,
) -> ContributionPolicyView:
    """Inspect one exact version, or the owner's selected current version."""
    response = await request.service.read(ContributionPolicyReadRequest(
        project_id=project_id, actor_profile_id=request.actor_profile_id,
        contribution_policy_id=policy_id, contribution_policy_version_id=version_id,
    ))
    return await commit_policy_response(request, response, ContributionPolicyView)


@router.post("/drafts", response_model=ContributionPolicyMutationResult, status_code=201,
             dependencies=[Depends(require_policy_key)],
             openapi_extra={"x-workstream-action-id": "contribution.policy.create_draft",
                            "parameters": [IDEMPOTENCY_PARAMETER]})
async def create_draft(
    project_id: UUID, payload: PolicyCreateInput, key: ReplayKey, request: RequestOwner,
) -> ContributionPolicyMutationResult:
    """Create a draft without fabricating default contribution rules."""
    response = await request.service.create_draft(ContributionPolicyCreateDraftRequest(
        project_id=project_id, actor_profile_id=request.actor_profile_id,
        operation_id=key, name=payload.name,
    ))
    return await commit_policy_response(request, response, ContributionPolicyMutationResult)


@router.put("/{policy_id}/versions/{version_id}", response_model=ContributionPolicyMutationResult,
            dependencies=[Depends(require_policy_key)],
            openapi_extra={"x-workstream-action-id": "contribution.policy.update_draft",
                           "parameters": [IDEMPOTENCY_PARAMETER]})
async def update_draft(
    project_id: UUID, policy_id: UUID, version_id: UUID, payload: PolicyUpdateInput,
    key: ReplayKey, request: RequestOwner,
) -> ContributionPolicyMutationResult:
    """Replace the selected draft graph through the existing unit/binding validation."""
    response = await request.service.update_draft(ContributionPolicyUpdateDraftRequest(
        project_id=project_id, actor_profile_id=request.actor_profile_id, operation_id=key,
        contribution_policy_id=policy_id, contribution_policy_version_id=version_id, rules=payload.rules,
    ))
    return await commit_policy_response(request, response, ContributionPolicyMutationResult)


@router.post("/{policy_id}/versions/{version_id}/publication", response_model=ContributionPolicyMutationResult,
             dependencies=[Depends(require_policy_key)],
             openapi_extra={"x-workstream-action-id": "contribution.policy.publish",
                            "parameters": [IDEMPOTENCY_PARAMETER]})
async def publish_policy(
    project_id: UUID, policy_id: UUID, version_id: UUID, payload: PolicyDecisionInput,
    key: ReplayKey, request: RequestOwner,
) -> ContributionPolicyMutationResult:
    """Publish the selected complete draft under exact Finance authority."""
    response = await request.service.publish(ContributionPolicyPublishRequest(
        project_id=project_id, actor_profile_id=request.actor_profile_id, operation_id=key,
        contribution_policy_id=policy_id, contribution_policy_version_id=version_id,
    ))
    return await commit_policy_response(request, response, ContributionPolicyMutationResult)


@router.post("/{policy_id}/versions/{version_id}/retirement", response_model=ContributionPolicyMutationResult,
             dependencies=[Depends(require_policy_key)],
             openapi_extra={"x-workstream-action-id": "contribution.policy.retire",
                            "parameters": [IDEMPOTENCY_PARAMETER]})
async def retire_policy(
    project_id: UUID, policy_id: UUID, version_id: UUID, payload: PolicyDecisionInput,
    key: ReplayKey, request: RequestOwner,
) -> ContributionPolicyMutationResult:
    """Retire a published aggregate while preserving historical exact reads."""
    response = await request.service.retire(ContributionPolicyRetireRequest(
        project_id=project_id, actor_profile_id=request.actor_profile_id, operation_id=key,
        contribution_policy_id=policy_id, contribution_policy_version_id=version_id,
    ))
    return await commit_policy_response(request, response, ContributionPolicyMutationResult)
