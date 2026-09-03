"""Small fixtures for projection authorization behavior tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from app.modules.authorization.api import (
    ArtifactPolicyProjectionFacts,
    GuideSufficiencyProjectionFacts,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationService,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
)
from app.modules.actors.service_identities import ServiceIdentity

DIGEST = "sha256:" + "a" * 64


class Session:
    def __init__(self) -> None:
        self.root = SimpleNamespace(is_active=True)
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return False


class Repository:
    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        return (
            SimpleNamespace(
                id=str(identity_link_id),
                actor_profile_id=str(actor_profile_id),
                status="active",
            ),
            SimpleNamespace(
                id=str(actor_profile_id),
                actor_kind="service",
                status="active",
                service_identity=ServiceIdentity.PROJECT_SETUP.value,
            ),
        )


class Evidence:
    def __init__(self) -> None:
        self.events = []
        self._repository = self

    async def add_authority_event(self, event) -> None:
        self.events.append(event)

    async def get_authority_event(self, event_id: str):
        event = next((item for item in self.events if str(item.event_id) == str(event_id)), None)
        if event is None:
            return None
        return SimpleNamespace(
            event_type=event.event_type.value,
            actor_id=str(event.actor_ref),
            action_id=event.action_id.value,
            permission_id=event.permission_id.value,
            project_id=event.project_id,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            request_id=str(event.request_id),
            correlation_id=str(event.correlation_id),
            after_facts=event.after_facts,
        )


def custody() -> tuple[FixedServicePreparedAuthorization, Session, Evidence]:
    session, repository = Session(), Repository()
    context = ServiceAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=ServiceIdentity.PROJECT_SETUP,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    kernel = AuthorizationService(
        session,
        context,
        admin_repository=repository,  # type: ignore[arg-type]
    )
    evidence = Evidence()
    kernel._audit = evidence  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,
        context,
        kernel,
        repository,  # type: ignore[arg-type]
    )
    return (
        FixedServicePreparedAuthorization(
            actor_profile_id=context.actor_profile_id,
            identity_link_id=context.identity_link_id,
            service=prepared,
        ),
        session,
        evidence,
    )


def sufficiency_facts(project_id: UUID, attempt_id: UUID):
    return GuideSufficiencyProjectionFacts(
        project_id=project_id,
        attempt_id=attempt_id,
        request_operation_id=uuid4(),
        provider_idempotency_key=uuid4(),
        compilation_id=uuid4(),
        guide_id=uuid4(),
        guide_version="v1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash=DIGEST,
        setup_run_id=uuid4(),
        setup_generation=1,
        celery_task_id=uuid4(),
        source_state_digest=DIGEST,
        result_hash=DIGEST,
        component_hash=DIGEST,
        result_schema_version="v1",
        compilation_agent_name="compiler",
        compilation_agent_version="v1",
        material_sha256=DIGEST,
        material_byte_count=7,
        report_id=uuid4(),
        report_content_digest=DIGEST,
    )


def policy_facts(project_id: UUID, attempt_id: UUID):
    return ArtifactPolicyProjectionFacts(
        project_id=project_id,
        attempt_id=attempt_id,
        request_operation_id=uuid4(),
        provider_idempotency_key=uuid4(),
        compilation_id=uuid4(),
        guide_id=uuid4(),
        guide_version="v1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash=DIGEST,
        setup_run_id=uuid4(),
        setup_generation=1,
        celery_task_id=uuid4(),
        source_state_digest=DIGEST,
        result_hash=DIGEST,
        component_hash=DIGEST,
        result_schema_version="v1",
        compilation_agent_name="compiler",
        compilation_agent_version="v1",
        prior_operation_id=uuid4(),
        sufficiency_report_id=uuid4(),
        sufficiency_report_digest=DIGEST,
        policy_id=uuid4(),
        policy_content_digest=DIGEST,
    )


def action_for(component: str) -> ActionId:
    return (
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
        if component == "guide_sufficiency"
        else ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE
    )
