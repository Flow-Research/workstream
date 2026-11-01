"""Real TASK/AUTH/OUTBOX fixtures with traced canonical feature authority."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID
from app.core.identifiers import new_record_id

from sqlalchemy import select

from app.adapters.auth import assignment_invalidation_authorization
from app.adapters.tasks import TransactionalAssignmentInvalidationHandler
from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.api import OutboxAppendInput
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.service import OutboxService
from app.modules.outbox.registry import HandlerRegistry
from app.modules.tasks.api.assignment_invalidation import (
    ASSIGNMENT_INVALIDATION_EVENT,
    PreparedAssignmentInvalidation,
    AssignmentInvalidationTarget,
)
from app.modules.tasks.models import AuditEvent, TaskAssignment, WorkstreamTask
from tests.outbox.conftest import Harness
from tests.test_tasks import (
    admit_and_grant_project_submitter,
    auth_headers,
    create_active_project,
    create_ready_task,
    set_dev_actor,
)


class TracedFeatureAuthority:
    """Observe calls without replacing canonical service/PREP behavior."""

    def __init__(self, session, trace):
        self.owner, self.trace = assignment_invalidation_authorization(session), trace

    @asynccontextmanager
    async def prepare_assignment_invalidation(self, facts):
        self.trace.append(("prepare", facts))
        async with self.owner.prepare_assignment_invalidation(facts) as prepared:
            trace = self.trace

            class TracedPrepared(PreparedAssignmentInvalidation):
                async def consume(self, current):
                    trace.append(("consume", current))
                    return await prepared.consume(current)

            try:
                yield TracedPrepared()
            finally:
                self.trace.append(("close", facts))


async def provision_reconciler(sessions):
    actor_id, link_id = new_record_id(), new_record_id()
    async with sessions() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.TASK_ASSIGNMENT_RECONCILER.value,
            created_by=str(actor_id),
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(link_id), actor_profile_id=str(actor_id), issuer="workstream.internal",
            subject=ServiceIdentity.TASK_ASSIGNMENT_RECONCILER.value,
            subject_kind="service", status="active", linked_by="workstream:system:bootstrap",
        ))
    return actor_id, link_id


async def setup_assignment(client, monkeypatch, *, artifact_settings=None, reconciler=True):
    if artifact_settings is not None:
        from app.modules.artifacts.repository import ArtifactRepository
        from app.modules.artifacts.service import _claim_and_validate_storage_namespace
        from tests.test_artifact_admission import _namespace

        async with db_session.get_session_factory()() as session, session.begin():
            await _claim_and_validate_storage_namespace(
                ArtifactRepository(session), _namespace(artifact_settings)
            )
    project = await create_active_project(client)
    task = await create_ready_task(client, project["id"])
    grant = await admit_and_grant_project_submitter(
        client, monkeypatch, project["id"], "invalidation-submitter"
    )
    claimed = await client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["task"]["status"] == "in_progress"
    sessions = db_session.get_session_factory()
    h = Harness(sessions, UUID(project["id"]))
    h.options = DeliveryOptions(lease_seconds=300, handler_timeout_seconds=240)
    actor_id = new_record_id()
    async with sessions() as session, session.begin():
        session.add(
            ActorProfile(
                id=str(actor_id),
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=ServiceIdentity.OUTBOX_DISPATCHER.value,
                created_by=str(actor_id),
            )
        )
        await session.flush()
        session.add(
            ActorIdentityLink(
                id=str(new_record_id()),
                actor_profile_id=str(actor_id),
                issuer="workstream.internal",
                subject=ServiceIdentity.OUTBOX_DISPATCHER.value,
                subject_kind="service",
                status="active",
                linked_by="workstream:system:bootstrap",
            )
        )
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == grant["actor_profile_id"],
            )
        )
        link_id = link.id
        admin = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == "https://project-fixture-bootstrap.test",
            )
        )
        admin_identity = (admin.issuer, admin.subject)
    feature_actor, feature_link = await provision_reconciler(sessions) if reconciler else (None, None)
    trace = []
    h.delivery = h.build(HandlerRegistry([(ASSIGNMENT_INVALIDATION_EVENT, 1, h.handle)]))
    handler = TransactionalAssignmentInvalidationHandler(
        sessions,
        observer=h.delivery,
        authorization_factory=lambda session: TracedFeatureAuthority(session, trace),
    )
    return SimpleNamespace(
        client=client,
        monkeypatch=monkeypatch,
        project=project,
        task=task,
        grant=grant,
        assignment=claimed.json()["assignment"],
        link_id=link_id,
        sessions=sessions,
        h=h,
        handler=handler,
        trace=trace,
        admin_identity=admin_identity,
        feature_actor=feature_actor, feature_link=feature_link,
    )


async def revoke(s, kind="grant"):
    set_dev_actor(s.monkeypatch, roles="project_manager", subject="project-manager-subject")
    paths = {
        "grant": f"/api/v1/projects/{s.project['id']}/role-grants/{s.grant['grant_id']}/revoke",
        "suspend": f"/api/v1/actors/{s.grant['actor_profile_id']}/suspend",
        "deactivate": f"/api/v1/actors/{s.grant['actor_profile_id']}/deactivate",
        "link": f"/api/v1/actor-identity-links/{s.link_id}/revoke",
    }
    if kind != "grant":
        set_dev_actor(
            s.monkeypatch, roles="viewer", issuer=s.admin_identity[0], subject=s.admin_identity[1]
        )
    response = await s.client.post(
        paths[kind], headers=auth_headers(), json={"reason": "Assignment authority test"}
    )
    assert response.status_code == 200, response.text
    async with s.sessions() as session:
        invalidation = await session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == "AuthorityInvalidationRequested",
                AuditEvent.invalidation_target_ref.in_(
                    (s.grant["grant_id"], s.grant["actor_profile_id"])
                ),
            )
            .order_by(AuditEvent.occurred_at.desc())
        )
        assert invalidation is not None
        cause = await session.get(AuditEvent, invalidation.invalidation_cause_event_id)
        assert (
            cause.event_type
            == {
                "grant": "ProjectRoleGrantRevoked",
                "suspend": "ActorProfileSuspended",
                "deactivate": "ActorProfileDeactivated",
                "link": "ActorIdentityLinkRevoked",
            }[kind]
        )
        assert invalidation.after_facts["effective"] is False
        # The cause retains the transaction-start default; invalidation records
        # actual DB mutation time after authority locks, strictly later.
        assert invalidation.created_at > cause.created_at
        s.invalidation_id = UUID(invalidation.id)
    return s.invalidation_id


async def invoked(s, *, target=None, synthetic_transport=False):
    target = target or AssignmentInvalidationTarget(
        project_id=UUID(s.project["id"]),
        task_id=UUID(s.task["id"]),
        assignment_id=UUID(s.assignment["id"]),
        contributor_id=UUID(s.grant["actor_profile_id"]),
        authority_invalidation_event_id=s.invalidation_id,
    )
    canonical_key = (
        f"assignment-invalidation:{target.authority_invalidation_event_id}:"
        f"{target.assignment_id}"
    )
    payload = target.model_dump(mode="json")
    if not synthetic_transport:
        async with s.sessions() as session:
            published = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.idempotency_key == canonical_key)
            )
        assert published is not None, "canonical assignment invalidation publication is required"
        assert (
            published.event_type == ASSIGNMENT_INVALIDATION_EVENT
            and published.event_version == 1
            and published.aggregate_type == "task_assignment"
            and published.aggregate_id == target.assignment_id
            and published.project_id == str(target.project_id)
            and published.causation_event_id == target.authority_invalidation_event_id
            and published.payload == payload
        ), "canonical assignment invalidation publication does not match target"
        event_id = published.event_id
    else:
        value = OutboxAppendInput(
            event_type=ASSIGNMENT_INVALIDATION_EVENT,
            event_version=1,
            aggregate_type="task_assignment",
            aggregate_id=target.assignment_id,
            project_id=target.project_id,
            correlation_id=str(new_record_id()),
            causation_event_id=target.authority_invalidation_event_id,
            idempotency_key=f"assignment-invalidation-fixture:{new_record_id()}",
            payload=payload,
        )
        async with s.sessions() as session, session.begin():
            result = await OutboxService(session).append(value)
        event_id = result.event_id
    claim = await s.h.delivery.claim(event_id, target.project_id, "assignment-test")
    assert claim is not None
    envelope = await s.h.delivery._begin_invocation(claim)
    assert envelope is not None
    return target, envelope


async def snapshot(s):
    async with s.sessions() as session:
        task = (
            (
                await session.execute(
                    select(WorkstreamTask.__table__).where(WorkstreamTask.id == s.task["id"])
                )
            )
            .mappings()
            .one()
        )
        assignments = (
            (
                await session.execute(
                    select(TaskAssignment.__table__)
                    .where(TaskAssignment.task_id == s.task["id"])
                    .order_by(TaskAssignment.id)
                )
            )
            .mappings()
            .all()
        )
        events = (
            (
                await session.execute(
                    select(AuditEvent.__table__)
                    .where(AuditEvent.entity_type == "task", AuditEvent.entity_id == s.task["id"])
                    .order_by(AuditEvent.id)
                )
            )
            .mappings()
            .all()
        )
        return dict(task), [dict(row) for row in assignments], [dict(row) for row in events]


async def prepare_submission(s, settings):
    """Prepare real ZIP custody for the existing assignment before invalidation."""
    from app.modules.artifacts.api import SubmissionBundlePreparationRequest
    from app.modules.authorization.api import ActorIdentityFacts, ActorKind
    from app.modules.projects.models import EffectiveProjectSubmissionArtifactPolicy
    from app.modules.tasks.api import SubmissionCreationRequest
    from tests.tasks.submission_lineage_support import _seed_services, _verified_admission
    from tests.test_artifact_admission import _namespace, _local_store, _context
    from tests.archive_fixtures import byte_source as _bytes, submission_archive as _archive
    from tests.test_tasks import complete_submission_payload

    context = _context(
        actor_profile_id=UUID(s.grant["actor_profile_id"]), identity_link_id=UUID(s.link_id)
    )
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    try:
        async with s.sessions() as session:
            task = await session.get(WorkstreamTask, s.task["id"])
            policy = await session.get(
                EffectiveProjectSubmissionArtifactPolicy,
                task.locked_effective_project_submission_artifact_policy_id,
            )
            body = policy.effective_policy
            assert [item["path"] for item in body["required_artifacts"]] == ["answer.md"]
            assert [item["key"] for item in body["required_evidence"]] == ["required-evidence-001"]
        await _seed_services(s.sessions)
        request = SubmissionBundlePreparationRequest(
            actor=ActorIdentityFacts(
                context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN
            ),
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            task_id=UUID(s.task["id"]),
            assignment_id=UUID(s.assignment["id"]),
            predecessor_submission_id=None,
            idempotency_key=new_record_id(),
            summary="Completed the required project work and included evidence.",
            contributor_attestation=(
                complete_submission_payload()["worker_attestation"]
                + " "
                + " ".join(body["attestation_terms"])
            ),
            media_type="application/zip",
            byte_source=_bytes(
                _archive(path="answer.md", evidence_path="evidence/required-evidence-001")
            ),
        )
        admission_id = await _verified_admission(
            s.sessions, store, namespace, settings, context, request
        )
        return context, SubmissionCreationRequest(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            contributor_id=context.actor_profile_id,
            predecessor_submission_id=None,
            admission_id=admission_id,
            summary=request.summary,
            contributor_attestation=request.contributor_attestation,
        )
    finally:
        bootstrap.close()
