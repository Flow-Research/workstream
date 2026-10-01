"""Real fixed-service execution fixtures and explicit forbidden phase participants."""

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorProfile, ActorIdentityLink


class ForbiddenPostSubmission:
    async def evaluate_post_submission(self, request):
        pytest.fail("pre-submit-only test entered post-submit execution")


def forbidden_post_submission():
    return ForbiddenPostSubmission()


async def provision_checker_service(factory):
    """Create fixture principal once without resetting an existing lifecycle decision."""
    async with factory() as session, session.begin():
        existing = await session.scalar(select(ActorProfile).where(
            ActorProfile.service_identity == ServiceIdentity.CHECKER_POST_SUBMIT.value,
        ))
        if existing is not None:
            return existing.id
        actor_id, link_id = str(new_record_id()), str(new_record_id())
        session.add(ActorProfile(
            id=actor_id, actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.CHECKER_POST_SUBMIT.value, created_by="checker-test",
        ))
        session.add(ActorIdentityLink(
            id=link_id, actor_profile_id=actor_id, issuer="flow-test", subject=actor_id,
            subject_kind="service", status="active", linked_by="checker-test",
        ))
        return actor_id


def live_executor(h, *, registry=None, outbox=None):
    from app.adapters.auth import post_submit_execution_authority
    from app.adapters.outbox import outbox_append
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.modules.checkers.runner import default_checker_registry

    return PostSubmissionExecutor(
        sessions=h.factory, materialization=h.service,
        execute_authority=post_submit_execution_authority,
        finalize_authority=post_submit_execution_authority,
        registry=registry if registry is not None else default_checker_registry(),
        outbox=outbox if outbox is not None else outbox_append,
    )


async def reserve(h, request=None):
    from app.modules.checkers.execution_coordination import EvaluationCoordinator

    async with h.factory() as session, session.begin():
        return await EvaluationCoordinator(session).reserve_current_evaluation(
            request if request is not None else h.request,
        )


async def material_execution(h):
    """Obtain one real committed execution lease for direct ART boundary tests."""
    from app.modules.checkers.api.execution import ExecuteFacts

    await reserve(h)
    lease, replay = await live_executor(h)._claim(h.request)
    assert replay is None
    return ExecuteFacts(request=h.request, lease=lease)


async def service_link_state(factory, identity, *, active):
    """Change real persisted service lifecycle in an independent transaction."""
    from sqlalchemy import text
    async with factory() as session, session.begin():
        if active:
            await session.execute(text(
                "update actor_identity_links set status='active', revoked_by=null, revoked_at=null, "
                "revoked_reason=null, reactivated_by='test', reactivated_at=clock_timestamp(), "
                "reactivation_reason='test' where actor_profile_id="
                "(select id from actor_profiles where service_identity=:identity)"
            ), {"identity": identity.value})
        else:
            await session.execute(text(
                "update actor_identity_links set status='revoked', revoked_by='test', "
                "revoked_at=clock_timestamp(), revoked_reason='test' where actor_profile_id="
                "(select id from actor_profiles where service_identity=:identity)"
            ), {"identity": identity.value})
