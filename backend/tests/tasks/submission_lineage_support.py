"""Shared real ART preparation and verifier fixture for TASK integration proofs."""

from unittest.mock import patch
from tests.trusted_intake_fixtures import LocalIntakeAdapter

from types import SimpleNamespace
from uuid import UUID
from app.core.identifiers import new_record_id

from sqlalchemy import select
from starlette.requests import Request

from app.adapters.artifacts import get_submission_bundle_preparation_command
from app.adapters.tasks import task_submission_context_port
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.artifacts.authorization import (
    PreparedArtifactInternalAuthority,
    PreparedSubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.models import (
    ArtifactVerificationJob,
    SubmissionBundleAdmission,
)
from app.modules.artifacts.service import ArtifactStorageOrchestrator


async def _seed_services(factory):
    async with factory.begin() as session:
        for identity in (
            ServiceIdentity.ARTIFACT_MATERIALIZER,
            ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            ServiceIdentity.ARTIFACT_VERIFIER,
            ServiceIdentity.ARTIFACT_BINDING,
            ServiceIdentity.CHECKER_PRE_SUBMIT,
        ):
            actor_id, link_id = str(new_record_id()), str(new_record_id())
            session.add(
                ActorProfile(
                    id=actor_id,
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=identity.value,
                    created_by="cp08-test",
                )
            )
            session.add(
                ActorIdentityLink(
                    id=link_id,
                    actor_profile_id=actor_id,
                    issuer="flow-test",
                    subject=actor_id,
                    subject_kind="service",
                    status="active",
                    linked_by="cp08-test",
                )
            )


async def _verified_admission(factory, store, namespace, settings, context, request):
    """Run the real ART command and independent verifier, returning its ready admission."""
    put_attempt_id = await _prepare_put_attempt(factory, settings, context, request)
    return await _verify_put_attempt(
        factory, store, namespace, settings, put_attempt_id
    )


async def _prepare_put_attempt(factory, settings, context, request):
    """Run ART authority/storage with explicit in-process intake; leave verification pending."""
    http = Request(
        {
            "type": "http",
            "headers": [],
            "app": SimpleNamespace(state=SimpleNamespace(settings=settings)),
        }
    )
    async with factory() as session:
        put_authority = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        )
        with patch("app.adapters.artifacts.trusted_submission_intake", return_value=LocalIntakeAdapter()):
            result = await get_submission_bundle_preparation_command(
                http,
                session,
                put_authority,
                PreparedSubmissionBundlePreparationAuthorization(session, context),
            ).prepare(request)
        assert result.put_attempt_id is not None
    return result.put_attempt_id


async def _verify_put_attempt(factory, store, namespace, settings, put_attempt_id):
    """Publish a prepared put through the real independent ART verifier."""
    async with factory() as session:
        job_id = await session.scalar(
            select(ArtifactVerificationJob.id).where(
                ArtifactVerificationJob.originating_put_attempt_id == str(put_attempt_id)
            )
        )
        assert job_id is not None
        await session.rollback()
        verifier = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        )
        assert (
            await ArtifactStorageOrchestrator(
                session, store, namespace, settings, verifier
            ).verify_object(
                UUID(job_id),
                submission_task_contexts=task_submission_context_port(session),
            )
            == "verified"
        )
    async with factory() as session:
        admission = (await session.scalars(select(SubmissionBundleAdmission).where(
            SubmissionBundleAdmission.put_attempt_id == str(put_attempt_id),
        ))).one()
        assert admission.status == "ready"
        admission_id = UUID(admission.id)
    return admission_id
