"""add fixed service identities and planned AUTH-09 actions

Revision ID: 0023_service_actor_identity
Revises: 0022_bootstrap_admin_grants
Create Date: 2026-07-16
"""

from __future__ import annotations

from alembic import op
from pathlib import Path
from pydantic import ValidationError
import sqlalchemy as sa

from migration_contracts.service_identity_0023 import (
    ExistingServiceActorRow,
    SERVICE_IDENTITY_VALUES,
    ServiceIdentityMappingError,
    database_binding_identifier,
    load_migration_mapping,
    source_row_set_sha256,
)

revision = "0023_service_actor_identity"
down_revision = "0022_bootstrap_admin_grants"
branch_labels = depends_on = None
MIGRATION_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

AUTH_09_ACTIONS = (
    "actor.profile.read",
    "actor.profile.suspend",
    "actor.profile.reactivate",
    "actor.profile.deactivate",
    "actor.identity_link.read",
    "actor.identity_link.revoke",
    "actor.identity_link.reactivate",
    "actor.service.provision",
)

ACTION_PERMISSION_PAIRS = (
    ("actor.profile.read_self", "actor.profile.read_self"),
    ("actor.profile.update_self", "actor.profile.update_self"),
    ("operations.task.start_override", "operations.task.start_override"),
    ("operations.submission_gate.repair", "operations.submission_gate.repair"),
    ("operations.checker.retry", "operations.checker.retry"),
    ("submission.create", "submission.create"),
    ("review.queue.read", "review.queue.read"),
    ("review.queue.inspect", "review.queue.inspect"),
    ("review.claim", "review.claim"),
    ("review.release", "review.release"),
    ("review.decline_preference", "review.decline_preference"),
    ("review.preference_expiry.run", "operations.timer.run"),
    ("review.lease_expiry.run", "operations.timer.run"),
    ("review.context.read", "submission.read_for_review"),
    ("review.chain.read", "review.chain.read"),
    ("review.finding_evidence.ingest", "review.decision"),
    ("review.decision", "review.decision"),
    ("review.finding_response_evidence.ingest", "submission.create"),
    ("review.lease.force_release", "review.lease.force_release"),
    ("review.queue.routing.override", "review.queue.override"),
    ("review.queue.routing.correct", "review.queue.override"),
    ("review.queue.close", "review.queue.override"),
    ("review.reconcile.run", "operations.reconcile.run"),
    ("review.artifact_reference.reconcile", "operations.reconcile.run"),
    ("review.projection.rebuild", "operations.projection.rebuild"),
    ("artifact.binding.read", "artifact.binding.read"),
    ("artifact.replica.read", "artifact.replica.read"),
    ("artifact.receipt.read", "artifact.receipt.read"),
    ("artifact.verification_job.read", "artifact.verification_job.read"),
    ("artifact.verification_job.retry", "artifact.verification_job.retry"),
    ("artifact.recovery_attempt.read", "artifact.recovery_attempt.read"),
    ("artifact.audit.read", "artifact.audit.read"),
    ("operations.artifact_storage_admission.read", "operations.status.read"),
    ("artifact.guide_source.ingest", "artifact.guide_source.ingest"),
    ("artifact.guide_source.read", "artifact.guide_source.read"),
    ("artifact.upload_session.create", "artifact.upload_session.create"),
    ("artifact.upload_session.read", "artifact.upload_session.read"),
    ("artifact.upload_item.write", "artifact.upload_item.write"),
    ("artifact.upload_session.seal", "artifact.upload_session.seal"),
    ("artifact.upload_session.cancel", "artifact.upload_session.cancel"),
    ("artifact.upload_session.expire", "artifact.upload_session.expire"),
    ("artifact.guide_source.binding.create", "artifact.binding.create"),
    ("artifact.submission.binding.create", "artifact.binding.create"),
    ("artifact.checker_output.binding.create", "artifact.binding.create"),
    ("artifact.verification.execute", "artifact.verification.execute"),
    ("artifact.pending_work.scan", "artifact.pending_work.scan"),
    ("artifact.put_attempt.resolve", "artifact.put_attempt.resolve"),
    ("artifact.pre_submit.checker_input.materialize", "artifact.checker_input.materialize"),
    ("artifact.post_submit.checker_input.materialize", "artifact.checker_input.materialize"),
    ("artifact.checker_output.write", "artifact.checker_output.write"),
    ("authorization.permission_catalogue.read", "admin_role.read"),
    ("authorization.admin_role_definitions.read", "admin_role.read"),
    ("admin_role_grant.list", "admin_role.read"),
    ("actor.admin_role_grant_history.read", "admin_role.read"),
    ("admin_role_grant.issue", "admin_role.grant"),
    ("admin_role_grant.revoke", "admin_role.revoke"),
    ("admin_role_grant.bootstrap", "admin_role.grant"),
    ("actor.profile.read", "actor.profile.read_any"),
    ("actor.profile.suspend", "actor.profile.suspend"),
    ("actor.profile.reactivate", "actor.profile.reactivate"),
    ("actor.profile.deactivate", "actor.profile.deactivate"),
    ("actor.identity_link.read", "actor.identity_link.read"),
    ("actor.identity_link.revoke", "actor.identity_link.revoke"),
    ("actor.identity_link.reactivate", "actor.identity_link.reactivate"),
    ("actor.service.provision", "actor.service.provision"),
)


def _tokens(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _pair_tokens(pairs: tuple[tuple[str, str], ...]) -> str:
    return ", ".join(f"('{action}', '{permission}')" for action, permission in pairs)


def _create_action_constraint(pairs: tuple[tuple[str, str], ...]) -> None:
    new_permissions = tuple(
        "operations.task.start_override operations.submission_gate.repair operations.checker.retry "
        "artifact.binding.read artifact.replica.read artifact.receipt.read "
        "artifact.verification_job.read artifact.verification_job.retry "
        "artifact.recovery_attempt.read artifact.audit.read artifact.guide_source.ingest "
        "artifact.upload_session.create artifact.upload_session.read artifact.upload_item.write "
        "artifact.upload_session.seal artifact.upload_session.cancel artifact.upload_session.expire "
        "artifact.binding.create artifact.verification.execute artifact.pending_work.scan "
        "artifact.put_attempt.resolve artifact.guide_source.read "
        "artifact.checker_input.materialize artifact.checker_output.write review.queue.override".split()
    )
    pair_tokens = _pair_tokens(pairs)
    op.create_check_constraint(
        "authorization_action_evidence",
        "audit_events",
        f"""
        (event_domain = 'legacy_lifecycle' and action_id is null) or (
          event_domain = 'authority'
          and (
            action_id is null or (
              event_type in ('SensitiveAuthorizationAllowed', 'SensitiveAuthorizationDenied')
              and permission_id is not null
              and (action_id, permission_id) in ({pair_tokens})
            )
          )
          and (
            permission_id is null or permission_id not in ({_tokens(new_permissions)})
            or (action_id is not null and (action_id, permission_id) in ({pair_tokens}))
          )
        )
        """,
    )


def _existing_service_rows(bind) -> tuple[ExistingServiceActorRow, ...]:
    raw_rows = bind.execute(
        sa.text(
            "select p.id,l.issuer,l.subject from actor_profiles p "
            "join actor_identity_links l on l.actor_profile_id=p.id "
            "where p.actor_kind='service' order by p.id"
        )
    ).all()
    try:
        return tuple(
            ExistingServiceActorRow(
                actor_profile_id=row[0],
                issuer=row[1],
                subject=row[2],
            )
            for row in raw_rows
        )
    except ValidationError:
        raise ServiceIdentityMappingError("service_mapping_source_invalid") from None


def _database_binding(bind) -> str:
    database_name, database_oid = bind.execute(
        sa.text(
            "select current_database(),oid from pg_database where datname=current_database()"
        )
    ).one()
    return database_binding_identifier(database_name, database_oid)


def _replace_actor_history_guard(*, with_service_identity: bool) -> None:
    immutable = "new.id,new.actor_kind,new.provisioning_method,new.created_by,new.created_at"
    if with_service_identity:
        immutable = (
            "new.id,new.actor_kind,new.provisioning_method,new.service_identity,"
            "new.created_by,new.created_at"
        )
    old_immutable = immutable.replace("new.", "old.")
    op.execute(
        f"""
        create or replace function guard_actor_profile_history() returns trigger language plpgsql as $$
        begin
          if tg_op='DELETE' then raise exception 'actor profiles are immutable history' using errcode='55000'; end if;
          if ({immutable}) is distinct from ({old_immutable}) then
            raise exception 'actor profile identity is immutable' using errcode='55000';
          end if;
          if old.status='deactivated' and new.status <> 'deactivated' then
            raise exception 'deactivated actor is terminal' using errcode='23514';
          end if;
          new.updated_at = statement_timestamp(); return new;
        end $$
        """
    )


def _add_mapping_state(
    *,
    mapped_count: int,
    source_digest: str,
    manifest_digest: str | None,
    envelope_digest: str | None,
    database_binding: str,
) -> None:
    columns = (
        sa.Column("service_identity_mapped_count", sa.Integer()),
        sa.Column("service_identity_source_row_set_sha256", sa.String(64)),
        sa.Column("service_identity_manifest_sha256", sa.String(64)),
        sa.Column("service_identity_envelope_sha256", sa.String(64)),
        sa.Column("service_identity_database_binding", sa.String(76)),
    )
    for column in columns:
        op.add_column("actor_profile_migration_state", column)
    op.execute(
        sa.text(
            "update actor_profile_migration_state set "
            "service_identity_mapped_count=:count,"
            "service_identity_source_row_set_sha256=:source,"
            "service_identity_manifest_sha256=:manifest,"
            "service_identity_envelope_sha256=:envelope,"
            "service_identity_database_binding=:binding where id=1"
        ).bindparams(
            count=mapped_count,
            source=source_digest,
            manifest=manifest_digest,
            envelope=envelope_digest,
            binding=database_binding,
        )
    )
    for name in (
        "service_identity_mapped_count",
        "service_identity_source_row_set_sha256",
        "service_identity_database_binding",
    ):
        op.alter_column("actor_profile_migration_state", name, nullable=False)
    op.create_check_constraint(
        "service_identity_evidence",
        "actor_profile_migration_state",
        "service_identity_mapped_count between 0 and 7 "
        "and service_identity_source_row_set_sha256 ~ '^[0-9a-f]{64}$' "
        "and service_identity_database_binding ~ '^postgres-v1:[0-9a-f]{64}$' "
        "and ((service_identity_mapped_count=0 "
        "and service_identity_manifest_sha256 is null "
        "and service_identity_envelope_sha256 is null) or "
        "(service_identity_mapped_count between 1 and 7 "
        "and service_identity_manifest_sha256 ~ '^[0-9a-f]{64}$' "
        "and service_identity_envelope_sha256 ~ '^[0-9a-f]{64}$'))",
    )
    op.execute(
        """
        create function guard_service_identity_migration_evidence() returns trigger
        language plpgsql as $$ begin
          raise exception 'service identity migration evidence is immutable' using errcode='55000';
        end $$
        """
    )
    op.execute(
        "create trigger service_identity_migration_evidence_row_guard "
        "before update or delete on actor_profile_migration_state for each row "
        "execute function guard_service_identity_migration_evidence()"
    )
    op.execute(
        "create trigger service_identity_migration_evidence_truncate_guard "
        "before truncate on actor_profile_migration_state for each statement "
        "execute function guard_service_identity_migration_evidence()"
    )


def upgrade() -> None:
    """Add fixed service identities without activating any AUTH-09 action."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table actor_profiles,actor_identity_links,actor_profile_migration_state,"
            "audit_events in access exclusive mode"
        )
    )
    rows = _existing_service_rows(bind)
    binding = _database_binding(bind)
    envelope = load_migration_mapping(
        rows,
        database_binding=binding,
        repository_root=MIGRATION_REPOSITORY_ROOT,
    )
    mapping = {row.actor_profile_id: row.service_identity.value for row in envelope.mappings} if envelope else {}

    op.add_column("actor_profiles", sa.Column("service_identity", sa.String(80)))
    op.create_unique_constraint("service_identity", "actor_profiles", ["service_identity"])
    for actor_profile_id, service_identity in mapping.items():
        bind.execute(
            sa.text(
                "update actor_profiles set service_identity=:identity where id=:actor_id"
            ),
            {"identity": service_identity, "actor_id": actor_profile_id},
        )
    bind.execute(sa.text("set constraints all immediate"))
    op.create_check_constraint(
        "kind_service_identity",
        "actor_profiles",
        "(actor_kind='human' and service_identity is null) or "
        f"(actor_kind='service' and service_identity in ({_tokens(SERVICE_IDENTITY_VALUES)}))",
    )
    _replace_actor_history_guard(with_service_identity=True)
    _add_mapping_state(
        mapped_count=len(rows),
        source_digest=source_row_set_sha256(rows),
        manifest_digest=envelope.manifest_sha256 if envelope else None,
        envelope_digest=envelope.envelope_sha256 if envelope else None,
        database_binding=binding,
    )
    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    _create_action_constraint(ACTION_PERMISSION_PAIRS)


def downgrade() -> None:
    """Restore 0022 only when no fixed service identity or new action evidence exists."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table actor_profiles,actor_identity_links,actor_profile_migration_state,"
            "audit_events in access exclusive mode"
        )
    )
    blocked = bind.execute(
        sa.text(
            "select exists(select 1 from actor_profiles where service_identity is not null) "
            f"or exists(select 1 from audit_events where action_id in ({_tokens(AUTH_09_ACTIONS)}))"
        )
    ).scalar_one()
    if blocked:
        raise RuntimeError("cannot downgrade fixed service identity authority")

    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    _create_action_constraint(ACTION_PERMISSION_PAIRS[:-8])
    op.execute(
        "drop trigger service_identity_migration_evidence_truncate_guard "
        "on actor_profile_migration_state"
    )
    op.execute(
        "drop trigger service_identity_migration_evidence_row_guard "
        "on actor_profile_migration_state"
    )
    op.execute("drop function guard_service_identity_migration_evidence()")
    op.drop_constraint("service_identity_evidence", "actor_profile_migration_state", type_="check")
    for name in (
        "service_identity_database_binding",
        "service_identity_envelope_sha256",
        "service_identity_manifest_sha256",
        "service_identity_source_row_set_sha256",
        "service_identity_mapped_count",
    ):
        op.drop_column("actor_profile_migration_state", name)
    _replace_actor_history_guard(with_service_identity=False)
    op.drop_constraint("kind_service_identity", "actor_profiles", type_="check")
    op.drop_constraint("service_identity", "actor_profiles", type_="unique")
    op.drop_column("actor_profiles", "service_identity")
