#!/usr/bin/env python3
"""Move the joint review lifecycle to a target phase through its owner controller.

The system Operator named by ``--actor-profile-id`` must hold a current
``operator`` grant; the existing AUTH decision, not this script, grants the
transition. The script does not authenticate its caller: whoever can run it
already holds the database credentials, so it is a local operator tool only.
Each step is one ``JointLifecycleController.transition`` commit. Running the
script again at the target phase changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import json
from uuid import UUID

from sqlalchemy import func, select

from app.adapters.auth import lifecycle_transition_authorization
from app.core.identifiers import new_record_id
from app.db.session import dispose_engine, get_session_factory
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.reviews.api.lifecycle import (
    JointLifecyclePhase,
    JointLifecycleUnavailable,
    LifecycleTransitionCommand,
)
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl
from app.modules.reviews.lifecycle.service import (
    FIRST_CONTRIBUTION_MANIFEST_DIGEST,
    JointLifecycleController,
)
from app.adapters.compensation import compensation_fulfillment_readiness

ACTIVATION_ORDER = ("disabled", "shadow", "live")
TARGET_PHASES = (JointLifecyclePhase.SHADOW, JointLifecyclePhase.LIVE)


def phase_path(current: str, target: str) -> list[str]:
    """Return the forward activation steps after ``current`` up to ``target``.

    Only the activation direction (disabled -> shadow -> live) is supported here.
    Leaving live goes through the owner's draining path and is out of scope.
    """
    if current not in ACTIVATION_ORDER or ACTIVATION_ORDER.index(current) > ACTIVATION_ORDER.index(
        target
    ):
        raise JointLifecycleUnavailable(f"no forward activation path from {current} to {target}")
    return list(
        ACTIVATION_ORDER[ACTIVATION_ORDER.index(current) + 1 : ACTIVATION_ORDER.index(target) + 1]
    )


async def _transition_once(actor_profile_id: UUID, target: str, reason: str) -> dict:
    """Commit one owner transition from the current control row, or roll back."""
    async with get_session_factory()() as session, session.begin():
        control = await session.scalar(select(JointLifecycleReleaseControl))
        links = (
            await session.scalars(
                select(ActorIdentityLink.id).where(
                    ActorIdentityLink.actor_profile_id == str(actor_profile_id),
                    ActorIdentityLink.status == "active",
                )
            )
        ).all()
        if control is None or len(links) != 1:
            raise JointLifecycleUnavailable("lifecycle control or operator identity unavailable")
        now = await session.scalar(select(func.clock_timestamp()))
        command = LifecycleTransitionCommand(
            operation_id=new_record_id(),
            singleton_id=control.id,
            actor_profile_id=actor_profile_id,
            identity_link_id=UUID(str(links[0])),
            expected_generation=control.generation,
            current_phase=JointLifecyclePhase(control.phase),
            target_phase=JointLifecyclePhase(target),
            reviewed_manifest_digest=FIRST_CONTRIBUTION_MANIFEST_DIGEST,
            deadline=now + timedelta(minutes=5),
            reason=reason,
        )
        context = HumanAuthorizationContext(
            actor_profile_id=command.actor_profile_id,
            identity_link_id=command.identity_link_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=new_record_id(),
            correlation_id=command.operation_id,
        )
        controller = JointLifecycleController(
            session,
            authorization=lifecycle_transition_authorization(session, context),
            source_readiness=compensation_fulfillment_readiness(session),
        )
        receipt = await controller.transition(command)
        return {
            "phase": receipt.phase.value,
            "generation": receipt.generation,
            "operation_id": str(receipt.operation_id),
        }


async def _current_phase() -> str:
    async with get_session_factory()() as session:
        control = await session.scalar(select(JointLifecycleReleaseControl))
        if control is None:
            raise JointLifecycleUnavailable("lifecycle control unavailable")
        return control.phase


async def run(actor_profile_id: UUID, target: str, reason: str, steps: list[dict]) -> dict:
    """Walk forward to ``target``, appending each committed step; a reached target is a no-op."""
    try:
        start = await _current_phase()
        for phase in phase_path(start, target):
            steps.append(await _transition_once(actor_profile_id, phase, reason))
        return {
            "result_code": "changed" if steps else "unchanged",
            "previous_phase": start,
            "phase": target,
            "steps": steps,
        }
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--actor-profile-id", type=UUID, required=True)
    parser.add_argument("--phase", choices=[phase.value for phase in TARGET_PHASES], required=True)
    parser.add_argument("--reason", default="Local agent loop lifecycle activation")
    args = parser.parse_args(argv)
    steps: list[dict] = []
    try:
        output = asyncio.run(run(args.actor_profile_id, args.phase, args.reason, steps))
    except JointLifecycleUnavailable as error:
        print(json.dumps({"result_code": "unavailable", "detail": str(error), "steps": steps}))
        return 3
    except Exception as error:  # noqa: BLE001 - AUTH and database detail stay privacy-bounded.
        # Steps already listed were committed; the failed step was rolled back.
        print(
            json.dumps(
                {"result_code": "failed", "error_type": type(error).__name__, "steps": steps}
            )
        )
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
