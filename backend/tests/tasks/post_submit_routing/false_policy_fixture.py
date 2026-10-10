"""Arrange an unavailable activation prestate; routing authority stays entirely real.

This is not a public false-policy activation proof. Only its availability gate is
suspended while the real activation owner binds complete policy and AUTH facts.
All triggers are restored before downstream execution, then custody is rechecked.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.modules.projects.service import (
    ALLOWED_REVIEW_DECISIONS,
    ALLOWED_REVISION_RESUBMISSION_STATES,
    GuideActivationBlocked,
    ProjectService,
)
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.api.guide_proposals import GuideProposalError
from tests.authorization.guide_activation.pg_support import service
from tests.projects.locked_policy_fixtures import frozen_request


_TRIGGERS = (
    ("project_guides", "guide_mutation_product_custody"),
    ("guide_mutation_idempotency_records", "guide_mutation_reservation_custody"),
    ("projects", "project_activation_custody"),
)


async def activate_false_prestate(factory, actor, command):
    # The real product path must still reject this otherwise well-formed guide.
    with pytest.raises(GuideProposalError, match="approval_blocked"):
        async with service(factory, actor) as (_, owner, request, _):
            await owner.activate(command, actor=actor, request_id=request)

    original = ProjectService.validate_activation_ready

    def readiness(self, *args, **kwargs):
        try:
            original(self, *args, **kwargs)
        except GuideActivationBlocked as exc:
            if str(exc) != "automated acceptance is unavailable":
                raise
            review, revision = args[7:9]
            assert review.human_review_required is False
            assert set(review.allowed_decisions).issubset(ALLOWED_REVIEW_DECISIONS)
            assert revision.max_revision_rounds >= 1 and revision.revision_deadline_hours >= 1
            assert revision.allowed_resubmission_states
            assert set(revision.allowed_resubmission_states).issubset(
                ALLOWED_REVISION_RESUBMISSION_STATES
            )
        else:
            pytest.fail("false-policy activation did not reach its availability gate")

    with patch.object(ProjectService, "validate_activation_ready", readiness):
        async with service(factory, actor) as (session, owner, request, _):
            for table, trigger in _TRIGGERS:
                await session.execute(text(f"ALTER TABLE public.{table} DISABLE TRIGGER {trigger}"))
            receipt = await owner.activate(command, actor=actor, request_id=request)
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            for table, trigger in _TRIGGERS:
                await session.execute(text(f"ALTER TABLE public.{table} ENABLE TRIGGER {trigger}"))

    async with factory() as session, session.begin():
        for table, trigger in _TRIGGERS:
            assert (
                await session.scalar(
                    text(
                        "SELECT tgenabled::text FROM pg_catalog.pg_trigger "
                        "WHERE tgrelid=CAST(:table AS regclass) AND tgname=:trigger"
                    ),
                    {"table": "public." + table, "trigger": trigger},
                )
                == "O"
            )
        await session.execute(
            text("SELECT public.require_guide_activation_custody(:id,false)"),
            {"id": receipt.operation_id},
        )
        context = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
            frozen_request(receipt)
        )
        assert json.loads(context.review_policy.value)["human_review_required"] is False
    return receipt
