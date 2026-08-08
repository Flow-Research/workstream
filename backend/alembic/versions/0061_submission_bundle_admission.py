"""Install verified submission-bundle ready admissions.

Revision ID: 0061_submission_admission
Revises: 0060_submission_bundle_intent
Create Date: 2026-08-08
"""

from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "0061_submission_admission"
down_revision = "0060_submission_bundle_intent"
branch_labels = depends_on = None


def upgrade() -> None:
    op.add_column(
        "pre_submit_evidence_sets",
        sa.Column("locked_policy_context_hash", sa.String(71), nullable=True),
    )
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                "select id,guide_id,guide_version,source_snapshot_id,source_snapshot_sha256,"
                "locked_guide_sha256,effective_policy_id,locked_artifact_policy_sha256,"
                "pre_submit_policy_id,locked_checker_policy_sha256,effective_plan_sha256 "
                "from pre_submit_evidence_sets"
            )
        ).mappings()
    )
    # 0058 made evidence rows immutable. This reviewed migration is the sole
    # bounded exception: add one deterministic derived column, then restore the
    # guard before installing any admission surface.
    op.execute(
        "alter table pre_submit_evidence_sets disable trigger pre_submit_evidence_sets_immutable"
    )
    for row in rows:
        value = {key: row[key] for key in row if key != "id"}
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        digest = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        bind.execute(
            sa.text(
                "update pre_submit_evidence_sets set locked_policy_context_hash=:digest "
                "where id=:id"
            ),
            {"id": row["id"], "digest": digest},
        )
    op.execute(
        "alter table pre_submit_evidence_sets enable trigger pre_submit_evidence_sets_immutable"
    )
    op.alter_column("pre_submit_evidence_sets", "locked_policy_context_hash", nullable=False)
    op.create_check_constraint(
        "ck_pre_submit_evidence_policy_context_sha256",
        "pre_submit_evidence_sets",
        "locked_policy_context_hash ~ '^sha256:[0-9a-f]{64}$'",
    )
    op.create_table(
        "submission_bundle_admissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("durable_intent_id", sa.String(36), nullable=False),
        sa.Column("pre_submit_evidence_set_id", sa.String(36), nullable=False),
        sa.Column("put_attempt_id", sa.String(36), nullable=False),
        sa.Column("artifact_content_id", sa.String(36), nullable=False),
        sa.Column("verified_replica_id", sa.String(36), nullable=False),
        sa.Column("verification_receipt_id", sa.String(36), nullable=False),
        sa.Column("put_operation_receipt_id", sa.String(36)),
        sa.Column("put_observation_receipt_id", sa.String(36)),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("identity_link_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("assignment_id", sa.String(36), nullable=False),
        sa.Column("predecessor_submission_id", sa.String(36)),
        sa.Column("predecessor_submission_version", sa.Integer()),
        sa.Column("locked_policy_context_hash", sa.String(71), nullable=False),
        sa.Column("semantic_manifest_id", sa.String(36), nullable=False),
        sa.Column("semantic_manifest_sha256", sa.String(71), nullable=False),
        sa.Column("archive_sha256", sa.String(71), nullable=False),
        sa.Column("archive_byte_count", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_by_submission_id", sa.String(36)),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.Column("stale_reason", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["durable_intent_id"], ["submission_bundle_durable_intents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pre_submit_evidence_set_id"], ["pre_submit_evidence_sets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["put_attempt_id"], ["artifact_put_attempts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_content_id"], ["artifact_contents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["verified_replica_id"], ["artifact_replicas.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["verification_receipt_id"], ["artifact_verification_receipts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["put_operation_receipt_id"], ["artifact_operation_receipts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["put_observation_receipt_id"],
            ["artifact_put_observation_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_profile_id"], ["actor_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["identity_link_id"], ["actor_identity_links.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["workstream_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignment_id"], ["task_assignments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["predecessor_submission_id"], ["submissions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["consumed_by_submission_id"], ["submissions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("durable_intent_id", name="uq_submission_bundle_admission_intent"),
        sa.UniqueConstraint(
            "pre_submit_evidence_set_id", name="uq_submission_bundle_admission_evidence"
        ),
        sa.UniqueConstraint(
            "verification_receipt_id", name="uq_submission_bundle_admission_verification"
        ),
        sa.CheckConstraint("status in ('ready','consumed','stale')", name="status"),
        sa.CheckConstraint(
            "locked_policy_context_hash ~ '^sha256:[0-9a-f]{64}$'", name="policy_context_hash"
        ),
        sa.CheckConstraint(
            "semantic_manifest_sha256 ~ '^sha256:[0-9a-f]{64}$'", name="manifest_sha256"
        ),
        sa.CheckConstraint("archive_sha256 ~ '^sha256:[0-9a-f]{64}$'", name="archive_sha256"),
        sa.CheckConstraint("archive_byte_count >= 0", name="archive_size"),
        sa.CheckConstraint(
            "((put_operation_receipt_id is not null)::int + (put_observation_receipt_id is not null)::int) = 1",
            name="write_receipt_shape",
        ),
        sa.CheckConstraint(
            "(predecessor_submission_id is null) = (predecessor_submission_version is null)",
            name="predecessor_shape",
        ),
        sa.CheckConstraint(
            "(status='ready' and consumed_at is null and consumed_by_submission_id is null and stale_at is null and stale_reason is null) or "
            "(status='consumed' and consumed_at is not null and consumed_by_submission_id is not null and stale_at is null and stale_reason is null) or "
            "(status='stale' and consumed_at is null and consumed_by_submission_id is null and stale_at is not null and octet_length(stale_reason) between 1 and 500)",
            name="terminal_shape",
        ),
    )
    for column in (
        "pre_submit_evidence_set_id",
        "artifact_content_id",
        "actor_profile_id",
        "project_id",
        "task_id",
        "status",
    ):
        op.create_index(
            f"ix_submission_bundle_admissions_{column}", "submission_bundle_admissions", [column]
        )
    op.execute(
        """
        create function guard_submission_bundle_admission_verified_lineage()
        returns trigger language plpgsql as $$
        declare matches integer;
        begin
          select count(*) into matches
          from submission_bundle_durable_intents intent
          join pre_submit_evidence_sets evidence
            on evidence.id=intent.pre_submit_evidence_set_id
          join artifact_put_attempts attempt on attempt.id=intent.put_attempt_id
          join artifact_replicas replica on replica.id=attempt.replica_id
          join artifact_contents content on content.id=replica.content_id
          join artifact_verification_jobs job
            on job.originating_put_attempt_id=attempt.id and job.replica_id=replica.id
          join artifact_verification_receipts verification
            on verification.verification_job_id=job.id
          where intent.id=new.durable_intent_id
            and evidence.id=new.pre_submit_evidence_set_id
            and attempt.id=new.put_attempt_id
            and content.id=new.artifact_content_id
            and replica.id=new.verified_replica_id
            and verification.id=new.verification_receipt_id
            and attempt.producer_request_type='submission_bundle'
            and attempt.producer_type='actor_profile'
            and attempt.producer_ref=evidence.actor_profile_id
            and attempt.project_id=evidence.project_id
            and attempt.task_id=evidence.task_id
            and attempt.media_type='application/zip'
            and content.media_type='application/zip'
            and attempt.status='object_confirmed'
            and evidence.terminal_status='passed' and evidence.eligible
            and replica.verification_state='verified'
            and replica.availability_state='available'
            and replica.integrity_state='valid'
            and verification.outcome='verified'
            and verification.execution_generation=job.execution_generation
            and verification.observed_sha256=attempt.sha256
            and verification.observed_sha256=content.sha256
            and verification.observed_sha256=evidence.archive_sha256
            and verification.observed_byte_count=attempt.byte_count
            and verification.observed_byte_count=content.byte_count
            and verification.observed_byte_count=evidence.archive_byte_count
            and new.actor_profile_id=evidence.actor_profile_id
            and new.identity_link_id=evidence.identity_link_id
            and new.project_id=evidence.project_id and new.task_id=evidence.task_id
            and new.assignment_id=evidence.assignment_id
            and new.predecessor_submission_id is not distinct from evidence.predecessor_submission_id
            and new.predecessor_submission_version is not distinct from evidence.predecessor_submission_version
            and new.locked_policy_context_hash=evidence.locked_policy_context_hash
            and new.semantic_manifest_id=evidence.semantic_manifest_id
            and new.semantic_manifest_sha256=evidence.semantic_manifest_sha256
            and new.archive_sha256=evidence.archive_sha256
            and new.archive_byte_count=evidence.archive_byte_count
            and ((new.put_operation_receipt_id is not null and exists (
                  select 1 from artifact_operation_receipts receipt
                  where receipt.id=new.put_operation_receipt_id
                    and receipt.put_attempt_id=attempt.id and receipt.replica_id=replica.id
                    and receipt.outcome='stored_pending_verification'))
              or (new.put_observation_receipt_id is not null and exists (
                  select 1 from artifact_put_observation_receipts observation
                  where observation.id=new.put_observation_receipt_id
                    and observation.put_attempt_id=attempt.id
                    and observation.outcome='observed_confirmed'
                    and observation.observed_sha256=attempt.sha256
                    and observation.observed_byte_count=attempt.byte_count)));
          if matches <> 1 then
            raise exception 'submission bundle admission verified lineage mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger submission_bundle_admission_verified_lineage before insert on submission_bundle_admissions for each row execute function guard_submission_bundle_admission_verified_lineage()"
    )
    op.execute(
        """
        create function guard_submission_bundle_admission_lineage()
        returns trigger language plpgsql as $$
        begin
          if row(old.durable_intent_id, old.pre_submit_evidence_set_id, old.put_attempt_id,
                 old.artifact_content_id, old.verified_replica_id, old.verification_receipt_id,
                 old.put_operation_receipt_id, old.put_observation_receipt_id,
                 old.actor_profile_id, old.identity_link_id, old.project_id, old.task_id,
                 old.assignment_id, old.predecessor_submission_id,
                 old.predecessor_submission_version,
                 old.locked_policy_context_hash,
                 old.semantic_manifest_id, old.semantic_manifest_sha256, old.archive_sha256,
                 old.archive_byte_count, old.ready_at, old.created_at)
             is distinct from
             row(new.durable_intent_id, new.pre_submit_evidence_set_id, new.put_attempt_id,
                 new.artifact_content_id, new.verified_replica_id, new.verification_receipt_id,
                 new.put_operation_receipt_id, new.put_observation_receipt_id,
                 new.actor_profile_id, new.identity_link_id, new.project_id, new.task_id,
                 new.assignment_id, new.predecessor_submission_id,
                 new.predecessor_submission_version,
                 new.locked_policy_context_hash,
                 new.semantic_manifest_id, new.semantic_manifest_sha256, new.archive_sha256,
                 new.archive_byte_count, new.ready_at, new.created_at)
          then
            raise exception 'submission bundle admission lineage is immutable' using errcode='55000';
          end if;
          if old.status <> 'ready' or new.status not in ('consumed','stale') then
            raise exception 'invalid submission bundle admission transition' using errcode='23514';
          end if;
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger submission_bundle_admission_lineage before update on submission_bundle_admissions for each row execute function guard_submission_bundle_admission_lineage()"
    )
    op.execute(
        "create function guard_submission_bundle_admission_delete() returns trigger language plpgsql as $$ begin raise exception 'submission bundle admissions cannot be removed' using errcode='55000'; end; $$"
    )
    op.execute(
        "create trigger submission_bundle_admission_delete before delete or truncate on submission_bundle_admissions for each statement execute function guard_submission_bundle_admission_delete()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("select count(*) from submission_bundle_admissions")).scalar_one():
        raise RuntimeError("cannot remove populated submission-bundle admissions")
    op.execute("drop trigger submission_bundle_admission_delete on submission_bundle_admissions")
    op.execute("drop function guard_submission_bundle_admission_delete()")
    op.execute("drop trigger submission_bundle_admission_lineage on submission_bundle_admissions")
    op.execute("drop function guard_submission_bundle_admission_lineage()")
    op.execute(
        "drop trigger submission_bundle_admission_verified_lineage on submission_bundle_admissions"
    )
    op.execute("drop function guard_submission_bundle_admission_verified_lineage()")
    op.drop_table("submission_bundle_admissions")
    op.drop_constraint(
        "ck_pre_submit_evidence_policy_context_sha256",
        "pre_submit_evidence_sets",
        type_="check",
    )
    op.drop_column("pre_submit_evidence_sets", "locked_policy_context_hash")
