"""Same-session live AUTH composition over real finalized product fixtures."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.adapters.auth import post_policy_authorization, guide_proposal_authorization
from app.modules.authorization.runtime import (
    HumanAuthorizationContext,
    ServiceAuthorizationContext,
    ActorStatus,
    IdentityLinkStatus,
)
from app.modules.authorization.api import ActorKind
from app.modules.actors.api import ServiceIdentity
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.post_policy.service import PostPolicyService
from app.modules.projects.api.post_policy import (
    PostPolicyApproval,
    PostPolicyCorrection,
    PostPolicySelection,
)
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import proposal_case
from tests.projects.post_policy.pg_support import prepare_upstream


@pytest.fixture(autouse=True)
def forbid_runtime_calls(monkeypatch):
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
    from app.modules.artifacts.guide_document_access import ScopedGuideDocumentGrant

    async def forbidden(*args, **kwargs):
        raise AssertionError("post-policy authorization accessed inference, documents or evaluator")

    monkeypatch.setattr(OpenAIAgentSdkProjectGuideRuntime, "compile_project_guide", forbidden)
    monkeypatch.setattr(ScopedGuideDocumentGrant, "open", forbidden)


@asynccontextmanager
async def service(factory, actor):
    async with factory() as session, session.begin():
        request = uuid4()
        values = dict(
            actor_profile_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id,
            actor_kind=actor.actor_kind,
            actor_status=ActorStatus.ACTIVE,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=request,
            correlation_id=uuid4(),
        )
        context = (
            ServiceAuthorizationContext(
                **values, service_identity=ServiceIdentity(actor.service_identity)
            )
            if actor.actor_kind is ActorKind.SERVICE
            else HumanAuthorizationContext(**values)
        )
        yield (
            session,
            PostPolicyService(
                session,
                post_policy_authorization(session, context),
                current_post_submit_catalogue(),
            ),
            request,
            context,
        )


async def operate(factory, actor, operation, command):
    async with service(factory, actor) as (session, owner, request, context):
        kwargs = dict(actor=actor, request_id=request)
        if operation == "request_correction":
            kwargs["guide_authorization"] = guide_proposal_authorization(session, context)
        return await getattr(owner, operation)(command, **kwargs)


@asynccontextmanager
async def ready_case(url):
    async with proposal_case(url) as (values, factory, command, actor, grant):
        payload = await prepare_upstream(factory, command, actor, grant)
        setup_actor = service_actor(values)
        projected = await operate(factory, setup_actor, "derive", payload)
        yield factory, command, actor, grant, setup_actor, payload, projected


def manager_command(operation, payload, target):
    if operation == "review_package":
        return PostPolicySelection(**payload.selection.model_dump(), policy_id=target.policy_id)
    if operation == "approve":
        return PostPolicyApproval(target=target, idempotency_key=uuid4())
    return PostPolicyCorrection(
        target=target, idempotency_key=uuid4(), reason="Reconsider the evaluation requirements"
    )
