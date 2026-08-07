"""add durable submission-policy derivation execution claims

Revision ID: 0059_policy_execution_claim
Revises: 0058_pre_submit_evidence
Create Date: 2026-08-07
"""

from __future__ import annotations

from alembic import op


revision = "0059_policy_execution_claim"
down_revision = "0058_pre_submit_evidence"
branch_labels = depends_on = None


def _install_guard(*, allow_reserved: bool) -> None:
    reserved_transition = """
          if old.status = 'reserved' and new.status = 'pending'
             and old.service_identity = 'workstream.project.setup'
             and old.action_id = 'project.submission_artifact_policy.derive'
             and (new.id,new.actor_profile_id,new.identity_link_id,new.service_identity,
                  new.action_id,new.idempotency_key,new.operation_id,new.project_id,
                  new.guide_id,new.source_snapshot_id,new.policy_id,new.setup_run_id,
                  new.setup_generation,new.setup_task_id,new.correlation_id,new.created_at,
                  new.response_json::text,new.committed_policy_id,new.committed_effective_policy_id,
                  new.committed_pre_submit_policy_id,new.committed_at)
                 is not distinct from
                 (old.id,old.actor_profile_id,old.identity_link_id,old.service_identity,
                  old.action_id,old.idempotency_key,old.operation_id,old.project_id,
                  old.guide_id,old.source_snapshot_id,old.policy_id,old.setup_run_id,
                  old.setup_generation,old.setup_task_id,old.correlation_id,old.created_at,
                  old.response_json::text,old.committed_policy_id,old.committed_effective_policy_id,
                  old.committed_pre_submit_policy_id,old.committed_at)
          then
            return new;
          end if;
    """ if allow_reserved else ""
    op.execute("drop function if exists reject_submission_policy_replay_mutation() cascade")
    op.execute(
        f"""
        create function reject_submission_policy_replay_mutation() returns trigger
        language plpgsql as $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'submission-policy replay rows cannot be deleted';
          end if;
{reserved_transition}
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.service_identity,
                 new.action_id,new.idempotency_key,new.request_digest,
                 new.resource_context_digest,new.resource_context_json::text,new.operation_id,
                 new.project_id,new.guide_id,new.source_snapshot_id,new.policy_id,
                 new.setup_run_id,new.setup_generation,new.setup_task_id,
                 new.correlation_id,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.service_identity,
                 old.action_id,old.idempotency_key,old.request_digest,
                 old.resource_context_digest,old.resource_context_json::text,old.operation_id,
                 old.project_id,old.guide_id,old.source_snapshot_id,old.policy_id,
                 old.setup_run_id,old.setup_generation,old.setup_task_id,
                 old.correlation_id,old.created_at)
          then
            raise exception 'invalid submission-policy replay mutation';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger trg_submission_policy_replay_immutable before update or delete "
        "on submission_policy_mutation_idempotency_records for each row "
        "execute function reject_submission_policy_replay_mutation()"
    )


def upgrade() -> None:
    op.execute(
        "drop trigger submission_policy_replay_custody "
        "on submission_policy_mutation_idempotency_records"
    )
    op.execute(
        "create constraint trigger submission_policy_replay_custody after insert or update "
        "on submission_policy_mutation_idempotency_records deferrable initially deferred "
        "for each row when (new.status='committed') "
        "execute function validate_submission_policy_authority_custody()"
    )
    op.drop_constraint(
        "ck_submission_policy_replay_status",
        "submission_policy_mutation_idempotency_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_submission_policy_replay_state_shape",
        "submission_policy_mutation_idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_submission_policy_replay_status",
        "submission_policy_mutation_idempotency_records",
        "status in ('reserved','pending','committed')",
    )
    op.create_check_constraint(
        "ck_submission_policy_replay_state_shape",
        "submission_policy_mutation_idempotency_records",
        "(status in ('reserved','pending') and response_json is null and committed_at is null "
        "and committed_policy_id is null and committed_effective_policy_id is null "
        "and committed_pre_submit_policy_id is null) or "
        "(status='committed' and response_json is not null and committed_at is not null "
        "and committed_policy_id is not null and "
        "((action_id='project.submission_artifact_policy.approve' "
        "and committed_effective_policy_id is not null "
        "and committed_pre_submit_policy_id is not null) or "
        "(action_id<>'project.submission_artifact_policy.approve' "
        "and committed_effective_policy_id is null "
        "and committed_pre_submit_policy_id is null)))",
    )
    _install_guard(allow_reserved=True)


def downgrade() -> None:
    op.execute("drop function reject_submission_policy_replay_mutation() cascade")
    op.execute(
        "do $$ begin if exists (select 1 from "
        "submission_policy_mutation_idempotency_records where status='reserved') then "
        "raise exception 'cannot downgrade submission-policy execution claims with reservations'; "
        "end if; end $$"
    )
    op.drop_constraint(
        "ck_submission_policy_replay_status",
        "submission_policy_mutation_idempotency_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_submission_policy_replay_state_shape",
        "submission_policy_mutation_idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_submission_policy_replay_status",
        "submission_policy_mutation_idempotency_records",
        "status in ('pending','committed')",
    )
    op.create_check_constraint(
        "ck_submission_policy_replay_state_shape",
        "submission_policy_mutation_idempotency_records",
        "(status='pending' and response_json is null and committed_at is null "
        "and committed_policy_id is null and committed_effective_policy_id is null "
        "and committed_pre_submit_policy_id is null) or "
        "(status='committed' and response_json is not null and committed_at is not null "
        "and committed_policy_id is not null and "
        "((action_id='project.submission_artifact_policy.approve' "
        "and committed_effective_policy_id is not null "
        "and committed_pre_submit_policy_id is not null) or "
        "(action_id<>'project.submission_artifact_policy.approve' "
        "and committed_effective_policy_id is null "
        "and committed_pre_submit_policy_id is null)))",
    )
    _install_guard(allow_reserved=False)
    op.execute(
        "drop trigger submission_policy_replay_custody "
        "on submission_policy_mutation_idempotency_records"
    )
    op.execute(
        "create constraint trigger submission_policy_replay_custody after insert or update "
        "on submission_policy_mutation_idempotency_records deferrable initially deferred "
        "for each row execute function validate_submission_policy_authority_custody()"
    )
