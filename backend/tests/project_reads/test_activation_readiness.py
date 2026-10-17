"""C3: readiness evaluates activation's own conditions, reports activation's refusal code, and writes nothing."""

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_activation import GuideActivationCondition, GuideActivationReadiness
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_activation.service import GuideActivationService
from tests.projects.guide_activation.pg_support import (
    activation_case, activation_command, activation_service, readiness_read as _readiness,
)

_PRODUCT_TABLES = (
    "project_guides", "projects", "guide_mutation_idempotency_records", "audit_events",
    "checker_policies", "review_policies", "revision_policies", "contribution_policies",
    "contribution_policy_versions",
)


async def _refusal(factory, actor, command, grant) -> str:
    """The refusal code a real activation raises for ``command``, with nothing committed."""
    with pytest.raises(GuideProposalError) as raised:
        async with factory() as session, session.begin():
            await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4(),
            )
    return raised.value.code


async def _state(factory):
    """Every row of the tables activation could write, for a before/after comparison."""
    async with factory() as session:
        return {
            table: (await session.execute(text(f"SELECT * FROM {table} ORDER BY 1"))).all()  # noqa: S608 - fixed names
            for table in _PRODUCT_TABLES
        }


def _ids(command):
    proposal = command.target.proposal
    return proposal.project_id, proposal.guide_id


@asynccontextmanager
async def _unbound_case(url, *, approve):
    """A complete draft whose post policy is derived (and optionally approved) but with no published CON policy."""
    from app.modules.projects.api.post_policy import PostPolicyApproval
    from tests.projects.guide_activation.source_fixtures import source_case
    from tests.projects.guide_compilation.helpers import service_actor
    from tests.projects.guide_compilation.proposals.pg_support import seed_selected_review_revision_inputs
    from tests.projects.post_policy.pg_support import operate, prepare_post_policy

    async with source_case(url) as (values, factory, finalization, actor, grant):
        await seed_selected_review_revision_inputs(factory, finalization, actor)
        _, derived = await prepare_post_policy(factory, finalization, actor, grant, service_actor(values))
        selected = derived
        if approve:
            selected = await operate(
                factory, actor, finalization.project_id, grant, "approve",
                PostPolicyApproval(target=derived.target, idempotency_key=uuid4()),
            )
        unpublished = SimpleNamespace(contribution_policy_id=uuid4(), contribution_policy_version_id=uuid4())
        yield factory, await activation_command(factory, selected, unpublished), actor, grant


@pytest.mark.parametrize("denial", ["no_root", "nested", "new", "dirty", "deleted"])
async def test_readiness_refuses_an_unclean_transaction_before_any_sql(denial):
    session = SimpleNamespace(
        in_transaction=lambda: denial != "no_root",
        in_nested_transaction=lambda: denial == "nested",
        new={object()} if denial == "new" else set(),
        dirty={object()} if denial == "dirty" else set(),
        deleted={object()} if denial == "deleted" else set(),
        execute=AsyncMock(side_effect=AssertionError("readiness reached SQL")),
        scalar=AsyncMock(side_effect=AssertionError("readiness reached SQL")),
    )
    service = GuideActivationService(session, contribution=None)
    with pytest.raises(GuideProposalError, match="storage_unavailable"):
        await service.readiness(uuid4(), uuid4(), contribution=SimpleNamespace())
    session.execute.assert_not_awaited()
    session.scalar.assert_not_awaited()


def test_readiness_is_ready_exactly_when_nothing_is_unmet():
    condition = GuideActivationCondition.of("proposal_stale", "contribution_policy_unpublished")
    assert condition.message
    for ready, unmet in ((True, (condition,)), (False, ())):
        with pytest.raises(ValueError):
            GuideActivationReadiness(project_id=uuid4(), guide_id=uuid4(), ready=ready, unmet=unmet)


async def test_ready_guide_reads_ready_without_effect_and_then_activates(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        before = await _state(factory)
        result = await _readiness(factory, *_ids(command))
        assert (result.ready, result.unmet) == (True, ())
        assert await _state(factory) == before
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4(),
            )
        assert receipt.command == command
        # The activated guide is no longer a draft; both paths refuse it with one code.
        again = await _readiness(factory, *_ids(command))
        fresh = command.model_copy(update={"idempotency_key": uuid4()})
        assert [item.reason for item in again.unmet] == ["guide_not_draft"]
        assert again.unmet[0].code == await _refusal(factory, actor, fresh, grant)


async def test_archived_project_reports_activations_refusal_first(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        project_id, guide_id = _ids(command)
        async with factory() as session, session.begin():
            await session.execute(text("UPDATE projects SET status='archived' WHERE id=:id"), {"id": str(project_id)})
        before = await _state(factory)
        result = await _readiness(factory, project_id, guide_id)
        assert await _state(factory) == before
        assert (result.unmet[0].code, result.unmet[0].reason) == ("approval_blocked", "project_not_activatable")
        assert result.unmet[0].code == await _refusal(factory, actor, command, grant)
        assert await _state(factory) == before


async def test_human_requirement_under_disabled_review_reports_activations_refusal(clean_postgres_database):
    from app.interfaces.project_agents import AtomicGuideRequirement
    from tests.projects.guide_compilation.helpers import result as compiled

    outcome = compiled()
    requirement = AtomicGuideRequirement(
        requirement_id="human_quality", statement="An authorized reviewer must assess the final quality.",
        disposition="human_review", evidence_refs=outcome.findings[0].evidence_refs,
    )
    outcome = outcome.model_copy(update={"requirements": (requirement,)})
    async with activation_case(
        clean_postgres_database, human_review_required=False, compilation_outcome=outcome,
    ) as (factory, command, actor, grant, _, _):
        result = await _readiness(factory, *_ids(command))
        assert [item.reason for item in result.unmet] == ["human_review_required_by_guide"]
        assert result.unmet[0].code == "approval_blocked" == await _refusal(factory, actor, command, grant)


async def test_disposition_check_is_the_one_activation_runs(clean_postgres_database, monkeypatch):
    """Removing the shared check removes it from readiness too: one code path, not a copy."""
    from app.interfaces.project_agents import AtomicGuideRequirement
    from tests.projects.guide_compilation.helpers import result as compiled

    outcome = compiled()
    requirement = AtomicGuideRequirement(
        requirement_id="human_quality", statement="An authorized reviewer must assess the final quality.",
        disposition="human_review", evidence_refs=outcome.findings[0].evidence_refs,
    )
    outcome = outcome.model_copy(update={"requirements": (requirement,)})
    original = GuideActivationService._readiness

    async def omit_disposition(self, conditions, locked, *args):
        await original(self, conditions, replace(locked, result=locked.result.model_copy(update={"requirements": ()})), *args)

    async with activation_case(
        clean_postgres_database, human_review_required=False, compilation_outcome=outcome,
    ) as (factory, command, _, _, _, _):
        monkeypatch.setattr(GuideActivationService, "_readiness", omit_disposition)
        assert (await _readiness(factory, *_ids(command))).ready


async def test_unpublished_contribution_policy_is_unmet_with_activations_code(clean_postgres_database):
    async with _unbound_case(clean_postgres_database, approve=True) as (factory, command, actor, grant):
        before = await _state(factory)
        result = await _readiness(factory, *_ids(command))
        assert [item.reason for item in result.unmet] == ["contribution_policy_unpublished"]
        assert result.unmet[0].code == "proposal_stale" == await _refusal(factory, actor, command, grant)
        assert await _state(factory) == before


async def test_unapproved_post_policy_collects_every_unmet_condition_in_activation_order(clean_postgres_database):
    async with _unbound_case(clean_postgres_database, approve=False) as (factory, command, actor, grant):
        project_id, guide_id = _ids(command)
        async with factory() as session, session.begin():
            await session.execute(text("UPDATE projects SET status='archived' WHERE id=:id"), {"id": str(project_id)})
        result = await _readiness(factory, project_id, guide_id)
        reasons = [item.reason for item in result.unmet]
        # Later independent conditions are still reported after the first refusal.
        assert reasons[0] == "project_not_activatable" and "post_policy_not_approved" in reasons[1:]
        assert result.unmet[0].code == await _refusal(factory, actor, command, grant)
        async with factory() as session, session.begin():
            await session.execute(text("UPDATE projects SET status='draft' WHERE id=:id"), {"id": str(project_id)})
        result = await _readiness(factory, project_id, guide_id)
        assert (result.unmet[0].code, result.unmet[0].reason) == ("proposal_stale", "post_policy_not_approved")
        assert result.unmet[0].code == await _refusal(factory, actor, command, grant)


async def test_guide_without_a_derived_post_policy_is_unavailable(clean_postgres_database):
    from tests.projects.guide_activation.source_fixtures import source_case

    async with source_case(clean_postgres_database) as (_values, factory, finalization, _actor, _grant):
        result = await _readiness(factory, finalization.project_id, finalization.guide_id)
        assert (result.unmet[0].code, result.unmet[0].reason) == ("proposal_unavailable", "post_policy_unavailable")
