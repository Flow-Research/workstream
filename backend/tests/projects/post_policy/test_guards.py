"""Reachable downstream negatives with complete finalized and approved source custody."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.projects.api.guide_proposals import GuideProposalError, GuideProposalSelection
from app.modules.projects.api.post_policy import (
    PostPolicyApproval,
    PostPolicyDerive,
    post_policy_human_authorization_selector,
)
from app.modules.projects.post_policy.models import PostPolicyOperation
from app.modules.projects.post_policy.service import PostPolicyService
from tests.checkers.external.support import post_registry_spec
from tests.projects.guide_activation.source_fixtures import source_case
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import proposal_case, revoke_review_grant
from .pg_support import PostAuthority, operate, prepare_post_policy
from .test_authority import foreign_manager, state


async def test_valid_finalization_without_upstream_approval_cannot_project(clean_postgres_database):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        payload = PostPolicyDerive(selection=GuideProposalSelection(
            project_id=command.project_id, guide_id=command.guide_id, compilation_id=command.compilation_id),
            upstream_approval_operation_id=uuid4(), upstream_approval_output_digest='sha256:'+'a'*64)
        with pytest.raises(GuideProposalError, match='proposal_stale'):
            await operate(factory, service_actor(values), command.project_id, None, 'derive', payload)
        async with factory() as session:
            assert await session.scalar(text('SELECT count(*) FROM project_post_policy_operations')) == 0
            assert await session.scalar(text('SELECT count(*) FROM checker_policies')) == 0


async def test_missing_approval_receipt_hits_the_specific_deferred_guard(clean_postgres_database, monkeypatch):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        payload = PostPolicyApproval(target=projected.target, idempotency_key=uuid4())
        async with factory() as session:
            await session.begin()
            service = PostPolicyService(session, PostAuthority(session, actor, command.project_id, grant))

            async def omit_only_operation(*args):
                # Preserve actual policy outputs and the real prepared audit decision.
                await session.flush()

            monkeypatch.setattr(service, '_persist', omit_only_operation)
            try:
                receipt = await service.approve(payload, actor=actor, request_id=uuid4())
                assert receipt.kind == 'approve'
                assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE correlation_id=:id"),
                                            dict(id=post_policy_human_authorization_selector(
                                                actor.actor_profile_id,
                                                payload.idempotency_key,
                                                "approve",
                                            ))) == 1
                assert await session.scalar(text("SELECT approval_operation_id FROM checker_policies WHERE id=:id"),
                                            dict(id=str(projected.target.policy_id))) == receipt.operation_id
                # Run this exact deferred guard before unrelated deferred foreign keys.
                with pytest.raises(DBAPIError, match='post-policy approval receipt missing'):
                    await session.execute(text('SET CONSTRAINTS post_policy_output_custody IMMEDIATE'))
            finally:
                await session.rollback()
        async with factory() as session:
            assert await session.scalar(text("SELECT lifecycle_status FROM checker_policies WHERE id=:id"),
                                        dict(id=str(projected.target.policy_id))) == 'compiled'
        assert (await operate(factory, actor, command.project_id, grant, 'approve', payload)).kind == 'approve'


@pytest.mark.parametrize('change,error', [
    ('output_digest', 'post-policy operation lineage mismatch'),
    ('foreign_grant', 'guide proposal current authority missing'),
    ('wrong_action', 'post-policy authority evidence mismatch'),
])
async def test_direct_sql_rejects_one_substituted_external_policy_commitment(
    clean_postgres_database, monkeypatch, change, error,
):
    selected_spec = post_registry_spec()
    async with source_case(
        clean_postgres_database,
        post_submit_registry_spec=selected_spec,
    ) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        async with factory() as session:
            stored = (
                await session.execute(
                    text(
                        'SELECT policy.policy_body, registry.id AS registry_entry_id, '
                        'registry.entry_digest FROM checker_policies policy '
                        'JOIN external_checker_registry_entries registry '
                        'ON registry.capability_id=:capability_id '
                        'AND registry.capability_version=:capability_version '
                        "AND registry.phase='post_submit' WHERE policy.id=:policy_id"
                    ),
                    dict(
                        capability_id=selected_spec.capability_id,
                        capability_version=selected_spec.capability_version,
                        policy_id=str(projected.target.policy_id),
                    ),
                )
            ).mappings().one()
        policy_body = stored['policy_body']
        assert policy_body['schema_version'] == 'external_post_submit_policy.v1'
        assert len(policy_body['entries']) == 1
        locked_registry = policy_body['entries'][0]['registry']
        assert locked_registry['capability_id'] == selected_spec.capability_id
        assert locked_registry['registry_entry_id'] == str(stored['registry_entry_id'])
        assert locked_registry['entry_digest'] == stored['entry_digest']
        _, _, _, foreign_grant = await foreign_manager(factory, actor)
        payload = PostPolicyApproval(target=projected.target, idempotency_key=uuid4())
        before = await state(factory)
        async with factory() as session:
            await session.begin()
            captured = []
            original_add = session.add

            def capture_operation(row, **kwargs):
                if isinstance(row, PostPolicyOperation):
                    captured.append(row)
                else:
                    original_add(row, **kwargs)

            try:
                with monkeypatch.context() as patch:
                    patch.setattr(session, 'add', capture_operation)
                    service = PostPolicyService(
                        session,
                        PostAuthority(session, actor, command.project_id, grant),
                    )
                    receipt = await service.approve(payload, actor=actor, request_id=uuid4())
                assert len(captured) == 1
                row = {
                    column.name: getattr(captured[0], column.name)
                    for column in PostPolicyOperation.__table__.columns
                }
                row['created_at'] = datetime.now(UTC)
                assert row['operation_id'] == receipt.operation_id
                if change == 'output_digest':
                    row['output_digest'] = 'sha256:' + 'b' * 64
                elif change == 'foreign_grant':
                    row['admin_role_grant_id'] = foreign_grant
                else:
                    wrong_event = str(new_record_id())
                    await session.execute(
                        text(
                            'INSERT INTO audit_events SELECT '
                            '(jsonb_populate_record(NULL::audit_events, '
                            'to_jsonb(source)||CAST(:patch AS jsonb))).* '
                            'FROM audit_events source WHERE id=:id'
                        ),
                        dict(
                            id=row['authorization_decision_event_id'],
                            patch=json.dumps(dict(
                                id=wrong_event,
                                entity_id=wrong_event,
                                action_id='project.post_submit_checker_policy.correction.request',
                            )),
                        ),
                    )
                    row['authorization_decision_event_id'] = wrong_event
                await session.execute(
                    text(
                        'INSERT INTO project_post_policy_operations SELECT '
                        '(jsonb_populate_record('
                        'NULL::project_post_policy_operations, CAST(:row AS jsonb))).*'
                    ),
                    dict(row=json.dumps(row, default=str)),
                )
                with pytest.raises(DBAPIError, match=error) as refused:
                    await session.execute(
                        text('SET CONSTRAINTS post_policy_operation_custody IMMEDIATE')
                    )
                assert refused.value.orig.sqlstate == '23514'
            finally:
                await session.rollback()
        assert await state(factory) == before
        recovered = await operate(factory, actor, command.project_id, grant, 'approve', payload)
        assert recovered.kind == 'approve'
        assert recovered.operation_id != receipt.operation_id
        async with factory() as session:
            durable = (
                await session.execute(
                    text(
                        "SELECT operation_id,authorization_decision_event_id FROM "
                        "project_post_policy_operations WHERE kind='approve'"
                    )
                )
            ).mappings().one()
        assert durable['operation_id'] == recovered.operation_id
        assert durable['authorization_decision_event_id'] != row['authorization_decision_event_id']


async def test_revoked_manager_cannot_approve_or_replay(clean_postgres_database):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        payload = PostPolicyApproval(target=projected.target, idempotency_key=uuid4())
        approved = await operate(factory, actor, command.project_id, grant, 'approve', payload)
        await revoke_review_grant(factory, actor, grant)
        for candidate in (payload, PostPolicyApproval(target=projected.target, idempotency_key=uuid4())):
            with pytest.raises(GuideProposalError, match='authority_unavailable'):
                await operate(factory, actor, command.project_id, grant, 'approve', candidate)
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM project_post_policy_operations WHERE kind='approve'")) == 1
            assert await session.scalar(text("SELECT approval_operation_id FROM checker_policies WHERE id=:id"),
                                        dict(id=str(projected.target.policy_id))) == approved.operation_id


@pytest.mark.parametrize('statement', [
    "UPDATE project_post_policy_operations SET output_digest='sha256:'||repeat('a',64)",
    'DELETE FROM project_post_policy_operations',
    "UPDATE checker_policies SET policy_body='{}'::json",
    'DELETE FROM checker_policies',
])
async def test_retained_policy_and_operation_evidence_is_immutable(clean_postgres_database, statement):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        with pytest.raises(DBAPIError, match='immutable'):
            async with factory() as session, session.begin():
                await session.execute(text(statement))


@pytest.mark.parametrize('change', ['upstream', 'project', 'link', 'policy_hash'])
async def test_exact_source_and_authority_substitutions_reject_without_writes(clean_postgres_database, change):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        derive, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        payload = PostPolicyApproval(target=projected.target, idempotency_key=uuid4())
        if change == 'upstream':
            # A complete saved source with only its approved-output commitment substituted.
            bad = derive.model_copy(update={'upstream_approval_output_digest': 'sha256:'+'b'*64})
            with pytest.raises(GuideProposalError, match='operation_conflict'):
                await operate(factory, service_actor(values), command.project_id, None, 'derive', bad)
        else:
            async with factory() as session, session.begin():
                authority = PostAuthority(session, actor, uuid4() if change == 'project' else command.project_id, grant)
                caller = replace(actor, identity_link_id=uuid4()) if change == 'link' else actor
                if change == 'policy_hash':
                    payload = PostPolicyApproval(target=projected.target.model_copy(update={'policy_hash': 'sha256:'+'b'*64}),
                                                 idempotency_key=uuid4())
                service = PostPolicyService(session, authority)
                with pytest.raises(GuideProposalError, match='authority_unavailable' if change in {'project','link'} else 'proposal_stale'):
                    await service.approve(payload, actor=caller, request_id=uuid4())
        async with factory() as session:
            assert await session.scalar(text('SELECT count(*) FROM project_post_policy_operations')) == 1
            assert await session.scalar(text("SELECT count(*) FROM checker_policies WHERE lifecycle_status='compiled'")) == 1


async def test_changed_approval_key_and_correction_reason_do_not_repeat_effects(clean_postgres_database):
    from app.modules.projects.api.post_policy import PostPolicyCorrection

    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        approval = PostPolicyApproval(target=projected.target, idempotency_key=uuid4())
        await operate(factory, actor, command.project_id, grant, 'approve', approval)
        with pytest.raises(GuideProposalError, match='proposal_stale'):
            await operate(factory, actor, command.project_id, grant, 'approve', approval.model_copy(update={'idempotency_key': uuid4()}))
        correction = PostPolicyCorrection(target=projected.target, idempotency_key=uuid4(), reason='Reconsider the policy requirements')
        receipt = await operate(factory, actor, command.project_id, grant, 'request_correction', correction)
        with pytest.raises(GuideProposalError, match='operation_conflict'):
            await operate(factory, actor, command.project_id, grant, 'request_correction', correction.model_copy(update={'reason': 'A different request'}))
        assert await operate(factory, actor, command.project_id, grant, 'request_correction', correction) == receipt
