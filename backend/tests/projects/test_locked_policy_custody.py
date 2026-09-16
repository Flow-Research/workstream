"""Complete PROJECTS context uses actual activated guide custody."""

import json

from sqlalchemy import select

from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.models import SubmissionArtifactPolicy, PostSubmitCheckerPolicy
from tests.projects.locked_policy_fixtures import activated_context, frozen_request


async def test_active_and_frozen_context_are_complete(clean_postgres_database):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            owner = ProjectLockedPolicyRepository(session)
            active = await owner.lock_active_policy_context(receipt.contribution.project_id)
            frozen = await owner.lock_locked_policy_context(frozen_request(receipt))
            assert active == frozen
            assert active.activation_receipt == receipt
            artifact = await session.scalar(
                select(SubmissionArtifactPolicy).where(
                    SubmissionArtifactPolicy.id
                    == str(receipt.command.target.proposal.artifact_policy_id)
                )
            )
            post = await session.scalar(
                select(PostSubmitCheckerPolicy).where(
                    PostSubmitCheckerPolicy.id == str(receipt.command.target.policy_id)
                )
            )
            assert json.loads(active.artifact_policy.value) == artifact.policy_body
            assert json.loads(active.compiled_post_submit_policy.value) == post.policy_body
            assert json.loads(active.review_policy.value)["human_review_required"] is True
            assert json.loads(active.revision_policy.value)["max_revision_rounds"] > 0
            assert not session.new and not session.dirty and not session.deleted


async def test_frozen_context_survives_successor_and_retirement(clean_postgres_database):
    from tests.projects.guide_activation.test_successor import successor_command
    from tests.authorization.guide_activation.pg_support import activate

    async with activated_context(clean_postgres_database) as (
        factory,
        first,
        actor,
        grant,
        world,
        policy,
    ):
        async with factory() as session, session.begin():
            original = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(first)
            )
        successor = await successor_command(factory, first.command, actor, grant, policy)
        successor = successor.model_copy(
            update={
                "expected_previous_active_guide_id": first.command.target.proposal.guide_id,
                "expected_previous_active_guide_generation": first.activation_generation,
            }
        )
        next_receipt = await activate(factory, actor, successor)
        async with factory() as session, session.begin():
            await world.service(session).retire(world.request("retire", policy))
        async with factory() as session, session.begin():
            owner = ProjectLockedPolicyRepository(session)
            active = await owner.lock_active_policy_context(first.contribution.project_id)
            frozen = await owner.lock_locked_policy_context(frozen_request(first))
            assert active.activation_receipt == next_receipt
            from dataclasses import replace

            assert frozen == replace(original, guide_status="superseded")


async def test_new_publication_does_not_reselect_context(clean_postgres_database):
    from tests.projects.guide_activation.pg_support import publish_policy

    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        _, newer = await publish_policy(factory, receipt.contribution.project_id)
        assert (
            newer.contribution_policy_version_id
            != receipt.contribution.contribution_policy_version_id
        )
        async with factory() as session, session.begin():
            owner = ProjectLockedPolicyRepository(session)
            assert (
                await owner.lock_active_policy_context(receipt.contribution.project_id)
            ).activation_receipt == receipt
            assert (
                await owner.lock_locked_policy_context(frozen_request(receipt))
            ).activation_receipt == receipt


async def test_context_result_is_deeply_immutable(clean_postgres_database):
    from dataclasses import FrozenInstanceError
    from pydantic import ValidationError
    import pytest

    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            facts = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
        with pytest.raises(FrozenInstanceError):
            facts.review_policy.value = "{}"
        with pytest.raises(ValidationError):
            facts.activation_receipt.command.target.proposal.component_hashes.pre_submit_hash = (
                "sha256:" + "0" * 64
            )
        detached = facts.activation_receipt.model_dump(mode="json")
        detached["contribution"]["adapter_binding_ids"].append("not-a-binding")
        assert facts.activation_receipt == receipt
        assert not facts.activation_receipt.contribution.adapter_binding_ids


async def test_context_read_does_not_allow_activated_proposal_mutations(clean_postgres_database):
    import pytest
    from uuid import uuid4
    from app.modules.projects.api import ProjectGuideSetupFinalizationError
    from app.modules.projects.api.guide_proposals import (
        GuideProposalApproval,
        GuideProposalCorrection,
        GuideProposalError,
        GuideProposalSelection,
    )
    from app.modules.projects.guide_compilation.proposal_repository import GuideProposalRepository
    from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
    from tests.projects.guide_compilation.proposals.pg_support import ProposalAuthority
    from tests.projects.guide_compilation.proposals.test_postgresql import approve
    from tests.projects.guide_activation.test_successor import successor_command
    from tests.authorization.guide_activation.pg_support import activate

    async with activated_context(clean_postgres_database) as (
        factory,
        receipt,
        actor,
        grant,
        _,
        policy,
    ):
        target = receipt.command.target.proposal
        selected = GuideProposalSelection(
            project_id=target.project_id,
            guide_id=target.guide_id,
            compilation_id=target.compilation_id,
        )
        for status in ("active", "superseded"):
            async with factory() as session, session.begin():
                assert (
                    await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                        frozen_request(receipt)
                    )
                ).guide_status == status
            async with factory() as session, session.begin():
                with pytest.raises(ProjectGuideSetupFinalizationError):
                    await GuideProposalRepository(session).lock(selected)
            with pytest.raises(GuideProposalError):
                await approve(
                    factory,
                    selected,
                    actor,
                    grant,
                    GuideProposalApproval(
                        target=target,
                        idempotency_key=uuid4(),
                        acknowledged_warning_hashes=receipt.command.target.upstream.acknowledged_warning_hashes,
                    ),
                )
            async with factory() as session, session.begin():
                with pytest.raises(GuideProposalError):
                    await GuideProposalService(
                        session, ProposalAuthority(session, actor, target.project_id, grant)
                    ).request_correction(
                        GuideProposalCorrection(
                            target=target,
                            idempotency_key=uuid4(),
                            reason="Clarify the requirements.",
                        ),
                        actor=actor,
                        request_id=uuid4(),
                    )
            if status == "active":
                next_command = await successor_command(
                    factory, receipt.command, actor, grant, policy
                )
                next_target = next_command.target.proposal
                async with factory() as session, session.begin():
                    draft = await GuideProposalRepository(session).lock(
                        GuideProposalSelection(
                            project_id=next_target.project_id,
                            guide_id=next_target.guide_id,
                            compilation_id=next_target.compilation_id,
                        )
                    )
                    assert draft.view.guide.status == "draft"
                await activate(
                    factory,
                    actor,
                    next_command.model_copy(
                        update={
                            "expected_previous_active_guide_id": target.guide_id,
                            "expected_previous_active_guide_generation": receipt.activation_generation,
                        }
                    ),
                )


async def test_catalogue_rollout_preserves_context_but_blocks_new_activation(
    clean_postgres_database, monkeypatch,
):
    import pytest
    from app.modules.projects.api.guide_proposals import GuideProposalError
    from app.modules.projects import post_submit_policy
    from app.modules.projects.post_policy import custody
    from tests.checkers.post_submit.support import altered_catalogue
    from tests.projects.guide_activation.pg_support import activation_case
    from tests.authorization.guide_activation.pg_support import (
        activate, activation_state, service,
    )

    async with activation_case(clean_postgres_database) as (
        factory, command, actor, *_
    ):
        newer = altered_catalogue(index=8, state="disabled")
        assert newer.manifest_sha256 != command.target.proposal.post_catalogue_manifest_hash
        before = await activation_state(factory)
        with pytest.raises(GuideProposalError):
            async with service(factory, actor) as (_, owner, request_id, _):
                owner.post_catalogue = newer
                await owner.activate(command, actor=actor, request_id=request_id)
        assert await activation_state(factory) == before
        receipt = await activate(factory, actor, command)
        async with factory() as session, session.begin():
            original = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
        monkeypatch.setattr(post_submit_policy, "current_post_submit_catalogue", lambda: newer)
        monkeypatch.setattr(custody, "current_post_submit_catalogue", lambda: newer)
        async with factory() as session, session.begin():
            owner = ProjectLockedPolicyRepository(session)
            assert await owner.lock_locked_policy_context(frozen_request(receipt)) == original
            assert await owner.lock_active_policy_context(receipt.contribution.project_id) == original
            assert not session.new and not session.dirty and not session.deleted
