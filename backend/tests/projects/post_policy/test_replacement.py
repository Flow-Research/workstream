"""A corrected unified generation replaces one policy chain without rewriting evidence."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.core.config import get_settings
from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalSelection
from app.modules.projects.api.post_policy import PostPolicyApproval, PostPolicyCorrection, PostPolicyDerive
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import (
    finalize_corrected_attempt,
    proposal_case,
    read_package,
    seed_review_actor,
)
from tests.projects.guide_compilation.runtime_fixtures import (
    publish_scripted_model_profile,
    scripted_runtime_configuration,
)
from tests.projects.guide_compilation.proposals.test_postgresql import approve
from tests.projects.guide_compilation.proposals.public_support import proposal_client, proposal_path
from .pg_support import prepare_post_policy, operate


@pytest.mark.parametrize('origin', ['post_policy', 'unified'])
async def test_corrected_generation_replaces_policy_and_retains_original_receipts(
    clean_postgres_database, monkeypatch, origin
):
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    get_settings.cache_clear()
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        operator, _ = await seed_review_actor(factory, None, role="operator", scope="system")
        configuration = scripted_runtime_configuration(
            get_settings(), adapter_profile_builder=lambda value: value
        )
        async with proposal_client(factory, operator) as operator_client:
            profile = await publish_scripted_model_profile(
                operator_client, command.project_id, configuration
            )
        configuration = configuration.model_copy(
            update={
                "model_profile_id": UUID(profile["profile_id"]),
                "model_profile_version": profile["spec"]["profile_version"],
                "model_profile_digest": profile["profile_digest"],
            }
        )
        setup = service_actor(values)
        derive, first = await prepare_post_policy(factory, command, actor, grant, setup, values)
        approval = PostPolicyApproval(target=first.target, idempotency_key=uuid4())
        approved = await operate(factory, actor, command.project_id, grant, 'approve', approval)
        if origin == 'post_policy':
            correction = await operate(factory, actor, command.project_id, grant, 'request_correction',
                PostPolicyCorrection(target=first.target, idempotency_key=uuid4(), reason='Reconsider these evaluation requirements'))
            successor = correction.correction
        else:
            from app.modules.projects.api.guide_proposals import GuideProposalCorrection
            from tests.projects.guide_compilation.proposals.test_postgresql import correct
            successor = await correct(factory, command, actor, grant, GuideProposalCorrection(
                target=first.target.proposal, idempotency_key=uuid4(), reason='Reconsider the complete guide proposal'))
        next_command = await finalize_corrected_attempt(
            factory, values, actor, successor, configuration=configuration
        )
        package = await read_package(factory, next_command, actor, grant)
        upstream = await approve(factory, next_command, actor, grant, GuideProposalApproval(
            target=package.target, idempotency_key=uuid4(),
            pre_submit_attachments=values["pre_submit_attachments"],
            post_submit_attachments=values["post_submit_attachments"],
            expected_previous_approval_operation_id=package.current_approval_operation_id,
            expected_previous_approval_output_digest=package.current_approval_output_digest))
        next_derive = PostPolicyDerive(selection=GuideProposalSelection(
            project_id=command.project_id, guide_id=command.guide_id, compilation_id=next_command.compilation_id),
            upstream_approval_operation_id=upstream.operation_id,
            upstream_approval_output_digest=canonical_json_hash(upstream.model_dump(mode='json')))
        second = await operate(factory, setup, command.project_id, None, 'derive', next_derive)
        assert second.target.predecessor_policy_id == first.target.policy_id
        assert second.target.policy_hash == first.target.policy_hash
        assert second.target.proposal.setup_generation == first.target.proposal.setup_generation + 1
        # Both reads see the newer guide-wide approval tip. Each requested
        # compilation must still identify its own separately derived policy.
        async with proposal_client(factory, actor) as client:
            old_package = await client.get(proposal_path(command) + '/proposal')
            new_package = await client.get(proposal_path(next_command) + '/proposal')
            assert old_package.status_code == new_package.status_code == 200
            assert old_package.json()['current_approval_operation_id'] == str(upstream.operation_id)
            assert new_package.json()['current_approval_operation_id'] == str(upstream.operation_id)
            assert old_package.json()['post_submit_policy_id'] == str(first.target.policy_id)
            assert new_package.json()['post_submit_policy_id'] == str(second.target.policy_id)
            assert first.target.policy_id != second.target.policy_id
        assert await operate(factory, setup, command.project_id, None, 'derive', derive) == first
        assert await operate(factory, actor, command.project_id, grant, 'approve', approval) == approved
        async with factory() as session:
            rows = (await session.execute(text(
                'SELECT id,lifecycle_status,approval_operation_id,supersession_operation_id FROM checker_policies ORDER BY lifecycle_status'
            ))).all()
            assert rows == [
                (second.target.policy_id, 'compiled', None, None),
                (first.target.policy_id, 'superseded', approved.operation_id,
                 correction.operation_id if origin == 'post_policy' else second.operation_id)]
        await operate(factory, actor, command.project_id, grant, 'request_correction',
            PostPolicyCorrection(target=second.target, idempotency_key=uuid4(), reason='Reconsider the next evaluation requirements'))
        # Both source rows are valid superseded history, so the earlier current-policy
        # uniqueness guard cannot mask the independent root/successor protections.
        # Direct SQL cannot fork either the root or a successor, independent of application locks.
        for policy, constraint in ((first, 'uq_post_policy_chain_root'), (second, 'uq_post_policy_chain_successor')):
            with pytest.raises(DBAPIError, match=constraint):
                async with factory() as session, session.begin():
                    await session.execute(text(
                        "INSERT INTO checker_policies SELECT (jsonb_populate_record(NULL::checker_policies, "
                        "to_jsonb(source)||jsonb_build_object('id',cast(:id as text)))).* "
                        "FROM checker_policies source WHERE id=:source"),
                        dict(id=str(new_record_id()), source=str(policy.target.policy_id)))


async def test_fresh_predecessor_decisions_reject_after_successor_upstream_approval(clean_postgres_database):
    from app.modules.projects.api.guide_proposals import GuideProposalCorrection, GuideProposalError
    from tests.projects.guide_compilation.proposals.test_postgresql import correct
    from .test_authority import state

    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        setup = service_actor(values)
        _, first = await prepare_post_policy(factory, command, actor, grant, setup, values)
        successor = await correct(factory, command, actor, grant, GuideProposalCorrection(
            target=first.target.proposal, idempotency_key=uuid4(), reason='Reconsider the complete guide proposal'))
        next_command = await finalize_corrected_attempt(factory, values, actor, successor)
        package = await read_package(factory, next_command, actor, grant)
        upstream = await approve(factory, next_command, actor, grant, GuideProposalApproval(
            target=package.target, idempotency_key=uuid4(),
            pre_submit_attachments=values["pre_submit_attachments"],
            post_submit_attachments=values["post_submit_attachments"],
            expected_previous_approval_operation_id=package.current_approval_operation_id,
            expected_previous_approval_output_digest=package.current_approval_output_digest))
        before = await state(factory)
        async with factory() as session:
            assert await session.scalar(text('SELECT lifecycle_status FROM checker_policies WHERE id=:id'),
                dict(id=str(first.target.policy_id))) == 'compiled'
        for operation, payload in (
            ('approve', PostPolicyApproval(target=first.target, idempotency_key=uuid4())),
            ('request_correction', PostPolicyCorrection(target=first.target,
                idempotency_key=uuid4(), reason='Fresh attempt against the predecessor')),
        ):
            with pytest.raises(GuideProposalError, match='proposal_stale'):
                await operate(factory, actor, command.project_id, grant, operation, payload)
            assert await state(factory) == before
        current = await operate(factory, setup, command.project_id, None, 'derive', PostPolicyDerive(
            selection=GuideProposalSelection(project_id=command.project_id, guide_id=command.guide_id,
                compilation_id=next_command.compilation_id), upstream_approval_operation_id=upstream.operation_id,
            upstream_approval_output_digest=canonical_json_hash(upstream.model_dump(mode='json'))))
        assert current.target.predecessor_policy_id == first.target.policy_id
        assert (await operate(factory, actor, command.project_id, grant, 'approve', PostPolicyApproval(
            target=current.target, idempotency_key=uuid4()))).kind == 'approve'
