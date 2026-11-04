"""Actual authorization decisions in atomic post-policy owner transactions."""

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import post_policy_derive_authorization_selector
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import (
    proposal_case,
    revoke_review_grant,
    seed_review_actor,
)
from tests.projects.post_policy.pg_support import prepare_upstream
from tests.projects.post_policy.test_authority import state, foreign_manager
from .pg_support import ready_case, operate, manager_command


async def test_setup_service_derives_with_exact_evidence(clean_postgres_database):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        payload = await prepare_upstream(factory, command, actor, grant, values)
        receipt = await operate(factory, service_actor(values), "derive", payload)
        async with factory() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT o.resource_context_digest,e.after_facts,e.actor_id,e.matched_grant_id,e.correlation_id "
                            "FROM project_post_policy_operations o JOIN audit_events e ON e.id=o.authorization_decision_event_id "
                            "WHERE o.operation_id=:id"
                        ),
                        dict(id=str(receipt.operation_id)),
                    )
                )
                .mappings()
                .one()
            )
            assert row["after_facts"] == dict(
                allowed=True, resource_context_digest=row["resource_context_digest"]
            )
            assert row["actor_id"] == str(service_actor(values).actor_profile_id)
            assert row["matched_grant_id"] is None and str(row["correlation_id"]) == str(
                post_policy_derive_authorization_selector(
                    payload.upstream_approval_operation_id
                )
            )
            assert (
                await session.scalar(text("SELECT count(*) FROM project_post_policy_operations"))
                == 1
            )


async def test_manager_reads_exact_post_policy(clean_postgres_database):
    async with ready_case(clean_postgres_database) as (factory, _, actor, _, _, payload, projected):
        package = await operate(
            factory,
            actor,
            "review_package",
            manager_command("review_package", payload, projected.target),
        )
        assert package.target == projected.target and package.current
        async with factory() as session:
            event = (
                (
                    await session.execute(
                        text(
                            "SELECT resource_type,resource_id,permission_id FROM audit_events WHERE action_id='project.guide_compilation.review_package.read'"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert event == dict(
                resource_type="project_guide_compilation_review_package",
                resource_id=str(projected.target.policy_id),
                permission_id="project.guide.manage",
            )


async def test_manager_approves_exact_post_policy(clean_postgres_database):
    async with ready_case(clean_postgres_database) as (
        factory,
        _,
        actor,
        grant,
        _,
        payload,
        projected,
    ):
        receipt = await operate(
            factory, actor, "approve", manager_command("approve", payload, projected.target)
        )
        async with factory() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT p.lifecycle_status,e.matched_grant_id,e.actor_id FROM checker_policies p JOIN project_post_policy_operations o ON o.operation_id=p.approval_operation_id JOIN audit_events e ON e.id=o.authorization_decision_event_id WHERE p.id=:id"
                        ),
                        dict(id=str(receipt.target.policy_id)),
                    )
                )
                .mappings()
                .one()
            )
            assert row == dict(
                lifecycle_status="approved",
                matched_grant_id=str(grant),
                actor_id=str(actor.actor_profile_id),
            )


@pytest.mark.parametrize("approved", [False, True])
async def test_manager_correction_has_one_shared_successor(clean_postgres_database, approved):
    async with ready_case(clean_postgres_database) as (factory, _, actor, _, _, payload, projected):
        if approved:
            await operate(
                factory, actor, "approve", manager_command("approve", payload, projected.target)
            )
        receipt = await operate(
            factory,
            actor,
            "request_correction",
            manager_command("request_correction", payload, projected.target),
        )
        async with factory() as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM project_guide_proposal_corrections")
                )
                == 1
            )
            assert await session.scalar(text("SELECT count(*) FROM project_setup_runs")) == 2
            assert (
                await session.scalar(text("SELECT count(*) FROM project_guide_setup_finalizations"))
                == 1
            )
            actions = (
                (
                    await session.execute(
                        text(
                            "SELECT action_id FROM audit_events WHERE action_id LIKE '%.correction.request'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert set(actions) == {
                "project.post_submit_checker_policy.correction.request",
                "project.guide_compilation.correction.request",
            }
        assert receipt.correction.successor_setup_generation == 2


@pytest.mark.parametrize("operation", ["review_package", "approve", "request_correction"])
@pytest.mark.parametrize(
    "authority", ["operator", "audit_authority", "foreign", "system", "revoked"]
)
async def test_manager_operations_reject_wrong_authority(
    clean_postgres_database, operation, authority
):
    async with ready_case(clean_postgres_database) as (
        factory,
        _,
        actor,
        grant,
        _,
        payload,
        projected,
    ):
        command = manager_command(operation, payload, projected.target)
        if authority == "revoked":
            await revoke_review_grant(factory, actor, grant)
        elif authority == "foreign":
            _, actor, _, _ = await foreign_manager(factory, actor)
        else:
            actor, _ = await seed_review_actor(
                factory,
                None,
                role="project_manager" if authority == "system" else authority,
                scope="system",
            )
        before = await state(factory)
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            await operate(factory, actor, operation, command)
        assert await state(factory) == before


@pytest.mark.parametrize("operation", ["derive", "approve", "request_correction"])
async def test_exact_replay_adds_no_effects(clean_postgres_database, operation):
    async with ready_case(clean_postgres_database) as (
        factory,
        _,
        actor,
        grant,
        setup_actor,
        payload,
        projected,
    ):
        caller = setup_actor if operation == "derive" else actor
        command = (
            payload
            if operation == "derive"
            else manager_command(operation, payload, projected.target)
        )
        first = (
            projected
            if operation == "derive"
            else await operate(factory, caller, operation, command)
        )
        before = await state(factory)
        assert await operate(factory, caller, operation, command) == first
        assert await state(factory) == before
        if operation == "derive":
            async with factory() as session, session.begin():
                await session.execute(
                    text("UPDATE actor_identity_links SET status='revoked',revoked_at=now(),revoked_by=:by,revoked_reason='Service access revoked' WHERE id=:id"),
                    dict(id=str(caller.identity_link_id), by=str(actor.actor_profile_id)),
                )
        else:
            await revoke_review_grant(factory, actor, grant)
        before = await state(factory)
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            await operate(factory, caller, operation, command)
        assert await state(factory) == before


@pytest.mark.parametrize("which", ["post", "guide"])
@pytest.mark.parametrize("failure", ["consume", "close"])
async def test_correction_authority_failure_rolls_back(
    clean_postgres_database, monkeypatch, which, failure
):
    from app.modules.authorization.api import AuthorizationDenied
    from app.modules.authorization.post_policy_authorization import _PreparedPostPolicy
    from app.modules.authorization.guide_proposal_authorization import _PreparedProposal

    async with ready_case(clean_postgres_database) as (factory, _, actor, _, _, payload, projected):
        command = manager_command("request_correction", payload, projected.target)
        before = await state(factory)
        cls = _PreparedPostPolicy if which == "post" else _PreparedProposal
        original = cls.consume_new

        async def fail(prepared, facts):
            receipt = await original(prepared, facts)
            if failure == "close":
                close = prepared._service.close

                def reject_close():
                    close()
                    raise AuthorizationDenied("authority close failure")

                monkeypatch.setattr(prepared._service, "close", reject_close)
                return receipt
            raise AuthorizationDenied("authority consumption failure")

        with monkeypatch.context() as patch:
            patch.setattr(cls, "consume_new", fail)
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                await operate(factory, actor, "request_correction", command)
        assert await state(factory) == before
        assert (
            await operate(factory, actor, "request_correction", command)
        ).correction.successor_setup_generation == 2


async def test_stale_upstream_denies_through_live_authority(clean_postgres_database):
    from uuid import uuid4
    from tests.projects.guide_compilation.proposals.pg_support import (
        finalize_corrected_attempt,
        read_package,
    )
    from tests.projects.guide_compilation.proposals.test_postgresql import correct, approve
    from app.modules.projects.api.guide_proposals import (
        GuideProposalCorrection,
        GuideProposalApproval,
    )

    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        payload = await prepare_upstream(factory, command, actor, grant, values)
        first = await operate(factory, service_actor(values), "derive", payload)
        successor = await correct(
            factory,
            command,
            actor,
            grant,
            GuideProposalCorrection(
                target=first.target.proposal,
                idempotency_key=uuid4(),
                reason="Reconsider the complete guide proposal",
            ),
        )
        next_command = await finalize_corrected_attempt(factory, values, actor, successor)
        package = await read_package(factory, next_command, actor, grant)
        await approve(
            factory,
            next_command,
            actor,
            grant,
            GuideProposalApproval(
                target=package.target,
                pre_submit_attachments=values["pre_submit_attachments"],
                post_submit_attachments=values["post_submit_attachments"],
                idempotency_key=uuid4(),
                expected_previous_approval_operation_id=package.current_approval_operation_id,
                expected_previous_approval_output_digest=package.current_approval_output_digest,
            ),
        )
        before = await state(factory)
        for operation in ("approve", "request_correction"):
            with pytest.raises(GuideProposalError, match="proposal_stale"):
                await operate(
                    factory, actor, operation, manager_command(operation, payload, first.target)
                )
            assert await state(factory) == before
