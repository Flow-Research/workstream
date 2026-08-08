"""Install submission-bundle durable put intent.

Revision ID: 0060_submission_bundle_intent
Revises: 0059_policy_execution_claim
Create Date: 2026-08-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0060_submission_bundle_intent"
down_revision = "0059_policy_execution_claim"
branch_labels = depends_on = None

_UUID = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CURRENT_REQUEST_TYPES = "producer_request_type in ('guide', 'checker_output')"
_SUBMISSION_REQUEST_TYPES = (
    "producer_request_type in ('guide', 'checker_output', 'submission_bundle')"
)
_CURRENT_PRODUCER_IDENTITY = (
    "((producer_request_type = 'guide' and producer_type = 'actor_profile' "
    f"and producer_ref ~ '{_UUID}') or "
    "(producer_request_type = 'checker_output' and producer_type = 'service_identity' "
    "and producer_ref = 'workstream.artifact.checker_output'))"
)
_SUBMISSION_PRODUCER_IDENTITY = (
    "((producer_request_type = 'guide' and producer_type = 'actor_profile' "
    f"and producer_ref ~ '{_UUID}') or "
    "(producer_request_type = 'checker_output' and producer_type = 'service_identity' "
    "and producer_ref = 'workstream.artifact.checker_output') or "
    "(producer_request_type = 'submission_bundle' and producer_type = 'actor_profile' "
    f"and producer_ref ~ '{_UUID}'))"
)
_CURRENT_PRODUCER_REFERENCE = (
    "(producer_request_type = 'guide' and guide_source_item_id is not null "
    "and checker_run_id is null and task_id is null and logical_role is null) or "
    "(producer_request_type = 'checker_output' and guide_source_item_id is null "
    "and checker_run_id is not null and task_id is not null "
    "and octet_length(logical_role) between 1 and 100)"
)
_SUBMISSION_PRODUCER_REFERENCE = (
    f"{_CURRENT_PRODUCER_REFERENCE} or "
    "(producer_request_type = 'submission_bundle' and guide_source_item_id is null "
    "and checker_run_id is null and task_id is not null and logical_role is null)"
)
_CURRENT_RECEIPT_REFERENCE = (
    "contract_version = 2 and put_attempt_id is not null and "
    "((guide_source_item_id is not null)::int + "
    "(checker_run_id is not null)::int) = 1"
)
_SUBMISSION_RECEIPT_REFERENCE = (
    "contract_version = 2 and put_attempt_id is not null and "
    "((guide_source_item_id is not null and checker_run_id is null "
    "and logical_role is null) or "
    "(guide_source_item_id is null and checker_run_id is not null "
    "and octet_length(logical_role) between 1 and 100) or "
    "(guide_source_item_id is null and checker_run_id is null "
    "and logical_role is null))"
)


def _replace_put_constraint(name: str, expression: str) -> None:
    op.drop_constraint(name, "artifact_put_attempts", type_="check")
    op.create_check_constraint(name, "artifact_put_attempts", expression)


def upgrade() -> None:
    _replace_put_constraint("producer_request_type", _SUBMISSION_REQUEST_TYPES)
    _replace_put_constraint("producer_identity", _SUBMISSION_PRODUCER_IDENTITY)
    _replace_put_constraint("producer_reference", _SUBMISSION_PRODUCER_REFERENCE)
    op.drop_constraint(
        "contract_producer_reference",
        "artifact_operation_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "contract_producer_reference",
        "artifact_operation_receipts",
        _SUBMISSION_RECEIPT_REFERENCE,
    )
    op.execute(
        """
        create function guard_artifact_receipt_producer_reference()
        returns trigger language plpgsql as $$
        declare request_type text;
        begin
          select producer_request_type into request_type
          from artifact_put_attempts where id = new.put_attempt_id;
          if request_type is null
             or (request_type = 'guide' and not (
                 new.guide_source_item_id is not null and new.checker_run_id is null
                 and new.logical_role is null))
             or (request_type = 'checker_output' and not (
                 new.guide_source_item_id is null and new.checker_run_id is not null
                 and octet_length(new.logical_role) between 1 and 100))
             or (request_type = 'submission_bundle' and not (
                 new.guide_source_item_id is null and new.checker_run_id is null
                 and new.logical_role is null))
          then
            raise exception 'artifact receipt producer reference mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger artifact_receipt_producer_reference "
        "before insert or update of put_attempt_id, guide_source_item_id, "
        "checker_run_id, logical_role on artifact_operation_receipts "
        "for each row execute function guard_artifact_receipt_producer_reference()"
    )
    op.create_table(
        "submission_bundle_durable_intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pre_submit_evidence_set_id", sa.String(36), nullable=False),
        sa.Column("put_attempt_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "pre_submit_evidence_set_id",
            name="uq_submission_bundle_intent_evidence",
        ),
        sa.UniqueConstraint(
            "put_attempt_id",
            name="uq_submission_bundle_intent_put_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["pre_submit_evidence_set_id"],
            ["pre_submit_evidence_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["put_attempt_id"],
            ["artifact_put_attempts.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_submission_bundle_durable_intents_pre_submit_evidence_set_id",
        "submission_bundle_durable_intents",
        ["pre_submit_evidence_set_id"],
    )
    op.create_index(
        "ix_submission_bundle_durable_intents_put_attempt_id",
        "submission_bundle_durable_intents",
        ["put_attempt_id"],
    )
    op.execute(
        """
        create function guard_submission_bundle_durable_intent_put_attempt()
        returns trigger language plpgsql as $$
        declare request_type text;
        begin
          select producer_request_type into request_type
          from artifact_put_attempts
          where id = new.put_attempt_id
          for share;
          if request_type is distinct from 'submission_bundle' then
            raise exception 'submission bundle durable intent requires submission_bundle put attempt'
              using errcode='23514';
          end if;
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger submission_bundle_durable_intent_put_attempt "
        "before insert on submission_bundle_durable_intents "
        "for each row execute function "
        "guard_submission_bundle_durable_intent_put_attempt()"
    )
    op.execute(
        """
        create function guard_submission_bundle_durable_intents_immutable()
        returns trigger language plpgsql as $$
        begin
          raise exception 'submission_bundle_durable_intents rows are immutable'
            using errcode='55000';
        end;
        $$
        """
    )
    op.execute(
        "create trigger submission_bundle_durable_intents_immutable "
        "before update or delete on submission_bundle_durable_intents "
        "for each row execute function "
        "guard_submission_bundle_durable_intents_immutable()"
    )
    op.execute(
        "create trigger submission_bundle_durable_intents_no_truncate "
        "before truncate on submission_bundle_durable_intents "
        "for each statement execute function "
        "guard_submission_bundle_durable_intents_immutable()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("select count(*) from submission_bundle_durable_intents")).scalar_one():
        raise RuntimeError("cannot remove populated submission-bundle durable intents")
    op.execute("drop trigger artifact_receipt_producer_reference on artifact_operation_receipts")
    op.execute("drop function guard_artifact_receipt_producer_reference()")
    op.execute(
        "drop trigger submission_bundle_durable_intents_no_truncate "
        "on submission_bundle_durable_intents"
    )
    op.execute(
        "drop trigger submission_bundle_durable_intents_immutable "
        "on submission_bundle_durable_intents"
    )
    op.execute("drop function guard_submission_bundle_durable_intents_immutable()")
    op.execute(
        "drop trigger submission_bundle_durable_intent_put_attempt "
        "on submission_bundle_durable_intents"
    )
    op.execute("drop function guard_submission_bundle_durable_intent_put_attempt()")
    op.drop_index(
        "ix_submission_bundle_durable_intents_put_attempt_id",
        table_name="submission_bundle_durable_intents",
    )
    op.drop_index(
        "ix_submission_bundle_durable_intents_pre_submit_evidence_set_id",
        table_name="submission_bundle_durable_intents",
    )
    op.drop_table("submission_bundle_durable_intents")
    op.drop_constraint(
        "contract_producer_reference",
        "artifact_operation_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "contract_producer_reference",
        "artifact_operation_receipts",
        _CURRENT_RECEIPT_REFERENCE,
    )
    _replace_put_constraint("producer_reference", _CURRENT_PRODUCER_REFERENCE)
    _replace_put_constraint("producer_identity", _CURRENT_PRODUCER_IDENTITY)
    _replace_put_constraint("producer_request_type", _CURRENT_REQUEST_TYPES)
