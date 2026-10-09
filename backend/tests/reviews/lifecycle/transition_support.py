"""Real AUTH/controller composition; no fake allow or SQL activation."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, text

from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.db.session import get_session_factory
from app.adapters.auth import lifecycle_transition_authorization
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.reviews.api.lifecycle import JointLifecyclePhase, LifecycleTransitionCommand
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl
from app.modules.reviews.lifecycle.service import JointLifecycleController, FIRST_CONTRIBUTION_MANIFEST_DIGEST


async def command_for(actor_id, phase, **changes):
    async with get_session_factory()() as session:
        control = await session.scalar(select(JointLifecycleReleaseControl))
        identity = await session.scalar(text(
            "SELECT id FROM public.actor_identity_links WHERE actor_profile_id=:actor"
        ), {"actor": actor_id})
        now = await session.scalar(text("SELECT pg_catalog.clock_timestamp()"))
        values = dict(
            operation_id=new_record_id(), singleton_id=control.id,
            actor_profile_id=actor_id, identity_link_id=UUID(str(identity)),
            expected_generation=control.generation, current_phase=JointLifecyclePhase(control.phase),
            target_phase=JointLifecyclePhase(phase), reviewed_manifest_digest=FIRST_CONTRIBUTION_MANIFEST_DIGEST,
            deadline=now + timedelta(minutes=5), reason="Exercise scoped contribution control",
        )
        values.update(changes)
        return LifecycleTransitionCommand(**values)


def controller(session, command):
    context = HumanAuthorizationContext(
        actor_profile_id=command.actor_profile_id, identity_link_id=command.identity_link_id,
        actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(), correlation_id=command.operation_id,
    )
    return JointLifecycleController(session, authorization=lifecycle_transition_authorization(session, context))


async def transition(command):
    async with get_session_factory()() as session, session.begin():
        return await controller(session, command).transition(command)


async def snapshot():
    async with get_session_factory()() as session:
        return {
            "control": (await session.execute(text("SELECT * FROM public.joint_lifecycle_release_control"))).all(),
            "history": (await session.execute(text("SELECT * FROM public.joint_lifecycle_transitions ORDER BY generation"))).all(),
            "events": (await session.execute(text(
                "SELECT * FROM public.audit_events WHERE action_id='review.lifecycle.activation.manage' ORDER BY id"
            ))).all(),
        }


def facts_for(command):
    """Complete canonical empty-store facts for direct-SQL substitution proofs."""
    from app.modules.reviews.api.lifecycle import LifecycleTransitionFacts

    return LifecycleTransitionFacts(command=command, observations_digest=canonical_json_hash({
        "singleton_id": str(command.singleton_id), "generation": command.expected_generation,
        "phase": command.current_phase.value, "retained_pre_authority_acceptance": False,
        "manifest": FIRST_CONTRIBUTION_MANIFEST_DIGEST,
    }))


async def issue_authority(session, command):
    """Real PREP and root locking; caller must attach the atomic transition."""
    owner = controller(session, command)
    await owner._fence.lock_controller()
    async with owner._authorization.lock_scope(command) as prepared:
        return await prepared.consume_new(facts_for(command))


def history_row(command, receipt, *, facts=None, digest=None):
    from app.modules.reviews.lifecycle.models import JointLifecycleTransition

    return JointLifecycleTransition(
        id=new_record_id(), operation_id=command.operation_id, singleton_id=command.singleton_id,
        generation=command.expected_generation + 1, previous_phase=command.current_phase.value,
        phase=command.target_phase.value, facts_json=(facts or facts_for(command)).model_dump(mode="json"),
        resource_context_digest=digest or receipt.resource_context_digest,
        authorization_decision_event_id=str(receipt.decision_event_id),
    )


async def publish_history(session, row):
    session.add(row)
    await session.flush()
    await session.execute(text(
        "UPDATE public.joint_lifecycle_release_control "
        "SET phase=:phase,generation=:generation,transition_id=:transition WHERE id=:id"
    ), {"phase": row.phase, "generation": row.generation, "transition": row.id, "id": row.singleton_id})
