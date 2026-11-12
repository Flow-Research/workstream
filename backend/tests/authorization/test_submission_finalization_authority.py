"""Real fixed-service finalization authority, exact handles and rollback."""
from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink
from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationAuthorityFacts
from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.tasks.models import AuditEvent
from tests.checkers.execution.support import provision_post_submit_service


def facts(phase="claim"):
    return SubmissionFinalizationAuthorityFacts(
        operation_id=new_record_id(), project_id=new_record_id(), task_id=new_record_id(),
        assignment_id=new_record_id(), contributor_id=new_record_id(), acceptance_decision_id=new_record_id(),
        accepted_context_sha256="sha256:"+"a"*64, acceptance_receipt_sha256="sha256:"+"b"*64,
        source_sha256="sha256:"+"c"*64, continuation_lease_id=new_record_id(), continuation_generation=1,
        phase=phase, submission_id=new_record_id() if phase=="commit" else None,
        submission_version=1 if phase=="commit" else None,
    )


@pytest.mark.parametrize("phase", ["claim", "commit"])
async def test_finalization_consumes_exact_service_authority(clean_postgres_database, phase):
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        actor = await provision_post_submit_service(factory, ServiceIdentity.ARTIFACT_BINDING)
        original = facts(phase)
        async with factory.begin() as session:
            authority = PreparedSubmissionFinalizationAuthorization(
                session, request_id=new_record_id(), correlation_id=original.operation_id)
            handle = await authority.prepare(facts=original, idempotency_key=original.continuation_lease_id)
            for changed in [replace(original, continuation_generation=2),
                            replace(original, acceptance_decision_id=new_record_id()),
                            replace(original, source_sha256="sha256:"+"d"*64)]:
                with pytest.raises(ArtifactAuthorityDeniedError):
                    await authority.consume(prepared_authorization=handle, facts=changed)
            decision = await authority.consume(prepared_authorization=handle, facts=original)
            assert isinstance(decision, UUID)
            with pytest.raises(ArtifactAuthorityDeniedError):
                await authority.consume(prepared_authorization=handle, facts=original)
        async with factory() as session:
            event = await session.get(AuditEvent, str(decision))
            assert event.actor_id == actor and event.matched_grant_id is None
            assert event.action_id == "artifact.submission.finalize"
            assert event.resource_type == "submission_operation" and event.resource_id == str(original.operation_id)
            assert event.target_ref_id == str(original.project_id)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("principal", ["missing", "wrong", "revoked"])
async def test_finalization_refuses_missing_wrong_or_revoked_service(clean_postgres_database, principal):
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if principal != "missing":
            identity = ServiceIdentity.ARTIFACT_MATERIALIZER if principal == "wrong" else ServiceIdentity.ARTIFACT_BINDING
            actor = await provision_post_submit_service(factory, identity)
            if principal == "revoked":
                async with factory.begin() as session:
                    from sqlalchemy import func
                    await session.execute(update(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id==actor)
                        .values(status="revoked", revoked_by="test", revoked_reason="test", revoked_at=func.now()))
        async with factory.begin() as session:
            authority = PreparedSubmissionFinalizationAuthorization(
                session, request_id=new_record_id(), correlation_id=new_record_id())
            with pytest.raises(ArtifactAuthorityDeniedError):
                await authority.prepare(facts=facts(), idempotency_key=new_record_id())
        async with factory() as session:
            assert not (await session.scalars(select(AuditEvent).where(
                AuditEvent.action_id=="artifact.submission.finalize",
                AuditEvent.event_type=="SensitiveAuthorizationAllowed"))).all()
    finally:
        await engine.dispose()
