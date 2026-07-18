"""migrate classified actors to canonical profiles and identity links

Revision ID: 0020_canonical_actor_profile
Revises: 0019_authority_idempotency
Create Date: 2026-07-15
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from alembic import op
from pydantic import ValidationError
import sqlalchemy as sa

from app.modules.actors.legacy_classification import (
    LegacyClassificationError,
    LegacyActorRow,
    database_binding_identifier,
    load_migration_envelope_from_environment,
    source_row_set_sha256,
)

revision = "0020_canonical_actor_profile"
down_revision = "0019_authority_idempotency"
branch_labels = depends_on = None

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _legacy_rows(bind) -> tuple[LegacyActorRow, ...]:
    rows = bind.execute(
        sa.text(
            "select actor_id, external_issuer, external_subject "
            "from actor_identities order by actor_id"
        )
    ).all()
    try:
        return tuple(
            LegacyActorRow(actor_id=row[0], issuer=row[1], subject=row[2]) for row in rows
        )
    except ValidationError:
        raise LegacyClassificationError("invalid_source_rows") from None


def _classification(bind, rows: tuple[LegacyActorRow, ...]):
    if not rows:
        return None
    database_name, database_oid = bind.execute(
        sa.text(
            "select current_database(), oid from pg_database "
            "where datname = current_database()"
        )
    ).one()
    return load_migration_envelope_from_environment(
        rows,
        database_binding=database_binding_identifier(database_name, database_oid),
    )


def _rename_legacy_tables() -> None:
    op.rename_table("actor_profiles", "legacy_workflow_eligibility")
    op.rename_table("actor_identities", "legacy_actor_identities")
    statements = (
        "alter table legacy_actor_identities rename constraint pk_actor_identities to pk_legacy_actor_identities",
        "alter table legacy_actor_identities rename constraint uq_actor_identities_external_identity to uq_legacy_actor_identities_external_identity",
        "alter table legacy_workflow_eligibility rename constraint pk_actor_profiles to pk_legacy_workflow_eligibility",
        "alter table legacy_workflow_eligibility rename constraint ck_actor_profiles_ck_actor_profiles_profile_type to ck_legacy_workflow_eligibility_profile_type",
        "alter table legacy_workflow_eligibility rename constraint ck_actor_profiles_ck_actor_profiles_status to ck_legacy_workflow_eligibility_status",
        "alter table legacy_workflow_eligibility rename constraint uq_actor_profiles_actor_type_scope to uq_legacy_workflow_eligibility_actor_type_scope",
        "alter table legacy_workflow_eligibility rename constraint fk_actor_profiles_actor_id_actor_identities to fk_legacy_workflow_eligibility_actor_id_legacy_actor_identities",
        "alter index ix_actor_profiles_actor_id rename to ix_legacy_workflow_eligibility_actor_id",
        "alter index ix_actor_profiles_profile_type rename to ix_legacy_workflow_eligibility_profile_type",
        "alter index ix_actor_profiles_status rename to ix_legacy_workflow_eligibility_status",
    )
    for statement in statements:
        op.execute(statement)


def _create_canonical_tables() -> None:
    op.create_table(
        "actor_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("provisioning_method", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("contact_email", sa.String(320)),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("suspended_by", sa.String(120)),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("suspension_reason", sa.String(500)),
        sa.Column("deactivated_by", sa.String(120)),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)),
        sa.Column("deactivation_reason", sa.String(500)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actor_profiles")),
        sa.CheckConstraint(f"id ~ '{UUID_PATTERN}'", name=op.f("ck_actor_profiles_id_uuid")),
        sa.CheckConstraint("actor_kind in ('human','service')", name=op.f("ck_actor_profiles_actor_kind")),
        sa.CheckConstraint("status in ('active','suspended','deactivated')", name=op.f("ck_actor_profiles_status")),
        sa.CheckConstraint(
            "provisioning_method in ('automatic_first_access','manual_service_provisioning')",
            name=op.f("ck_actor_profiles_provisioning_method"),
        ),
        sa.CheckConstraint(
            "(actor_kind='human' and provisioning_method='automatic_first_access') or "
            "(actor_kind='service' and provisioning_method='manual_service_provisioning')",
            name=op.f("ck_actor_profiles_kind_provisioning"),
        ),
        sa.CheckConstraint(
            "(status='active' and suspended_by is null and suspended_at is null and "
            "suspension_reason is null and deactivated_by is null and deactivated_at is null "
            "and deactivation_reason is null) or "
            "(status='suspended' and suspended_by is not null and suspended_at is not null "
            "and suspension_reason is not null and deactivated_by is null and "
            "deactivated_at is null and deactivation_reason is null) or "
            "(status='deactivated' and deactivated_by is not null and deactivated_at is not null "
            "and deactivation_reason is not null)",
            name=op.f("ck_actor_profiles_lifecycle_fields"),
        ),
    )
    op.create_index(
        op.f("ix_actor_profiles_status_actor_kind"),
        "actor_profiles",
        ["status", "actor_kind"],
    )
    op.create_index(
        op.f("ix_actor_profiles_last_seen_at"),
        "actor_profiles",
        ["last_seen_at"],
    )

    op.create_table(
        "actor_identity_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("issuer", sa.String(200), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("subject_kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("linked_by", sa.String(120), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_by", sa.String(120)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.String(500)),
        sa.Column("reactivated_by", sa.String(120)),
        sa.Column("reactivated_at", sa.DateTime(timezone=True)),
        sa.Column("reactivation_reason", sa.String(500)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actor_identity_links")),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"], ["actor_profiles.id"], name=op.f("fk_actor_identity_links_actor_profile_id_actor_profiles")
        ),
        sa.UniqueConstraint("issuer", "subject", name=op.f("uq_actor_identity_links_external_identity")),
        sa.UniqueConstraint("actor_profile_id", name=op.f("uq_actor_identity_links_actor_profile")),
        sa.CheckConstraint(f"id ~ '{UUID_PATTERN}'", name=op.f("ck_actor_identity_links_id_uuid")),
        sa.CheckConstraint("length(btrim(issuer)) between 1 and 200", name=op.f("ck_actor_identity_links_issuer")),
        sa.CheckConstraint("length(btrim(subject)) between 1 and 200", name=op.f("ck_actor_identity_links_subject")),
        sa.CheckConstraint("subject_kind in ('human','service')", name=op.f("ck_actor_identity_links_subject_kind")),
        sa.CheckConstraint("status in ('active','revoked')", name=op.f("ck_actor_identity_links_status")),
        sa.CheckConstraint(
            "(status='active' and revoked_by is null and revoked_at is null and revoked_reason is null) or "
            "(status='revoked' and revoked_by is not null and revoked_at is not null and revoked_reason is not null)",
            name=op.f("ck_actor_identity_links_revocation_fields"),
        ),
    )
    op.create_index(
        op.f("ix_actor_identity_links_issuer_subject_status"),
        "actor_identity_links",
        ["issuer", "subject", "status"],
    )


def _install_guards() -> None:
    op.execute(
        """
        create function guard_actor_profile_history() returns trigger language plpgsql as $$
        begin
          if tg_op='DELETE' then raise exception 'actor profiles are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_kind,new.provisioning_method,new.created_by,new.created_at)
             is distinct from
             (old.id,old.actor_kind,old.provisioning_method,old.created_by,old.created_at) then
            raise exception 'actor profile identity is immutable' using errcode='55000';
          end if;
          if old.status='deactivated' and new.status <> 'deactivated' then
            raise exception 'deactivated actor is terminal' using errcode='23514';
          end if;
          new.updated_at = statement_timestamp(); return new;
        end $$
        """
    )
    op.execute(
        "create trigger actor_profile_history_guard before update or delete on actor_profiles "
        "for each row execute function guard_actor_profile_history()"
    )
    op.execute(
        """
        create function guard_actor_identity_link_history() returns trigger language plpgsql as $$
        begin
          if tg_op='DELETE' then raise exception 'actor identity links are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_profile_id,new.issuer,new.subject,new.subject_kind,new.linked_by,new.linked_at)
             is distinct from
             (old.id,old.actor_profile_id,old.issuer,old.subject,old.subject_kind,old.linked_by,old.linked_at) then
            raise exception 'actor identity link anchor is immutable' using errcode='55000';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger actor_identity_link_history_guard before update or delete on actor_identity_links "
        "for each row execute function guard_actor_identity_link_history()"
    )
    op.execute(
        """
        create function validate_canonical_actor_link() returns trigger language plpgsql as $$
        declare profile_row actor_profiles%rowtype; link_count integer;
        begin
          if tg_table_name='actor_profiles' then
            select count(*) into link_count from actor_identity_links where actor_profile_id=new.id;
            if link_count <> 1 then raise exception 'actor profile requires exactly one identity link' using errcode='23514'; end if;
            if not exists(select 1 from actor_identity_links where actor_profile_id=new.id and subject_kind=new.actor_kind) then
              raise exception 'actor and identity kind mismatch' using errcode='23514';
            end if;
          else
            select * into profile_row from actor_profiles where id=new.actor_profile_id;
            if not found or profile_row.actor_kind <> new.subject_kind then
              raise exception 'actor and identity kind mismatch' using errcode='23514';
            end if;
          end if; return new;
        end $$
        """
    )
    op.execute(
        "create constraint trigger actor_profile_link_guard after insert or update on actor_profiles "
        "deferrable initially deferred for each row execute function validate_canonical_actor_link()"
    )
    op.execute(
        "create constraint trigger actor_identity_link_profile_guard after insert or update on actor_identity_links "
        "deferrable initially deferred for each row execute function validate_canonical_actor_link()"
    )


def upgrade() -> None:
    """Consume classified legacy evidence and install one canonical actor root."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table actor_profiles in access exclusive mode"))
    bind.execute(sa.text("lock table actor_identities in access exclusive mode"))
    rows = _legacy_rows(bind)
    envelope = _classification(bind, rows)
    kinds = {entry.actor_id: entry.subject_kind for entry in envelope.classifications} if envelope else {}

    _rename_legacy_tables()
    _create_canonical_tables()
    op.create_table(
        "actor_profile_migration_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("classified_count", sa.Integer(), nullable=False),
        sa.Column("source_row_set_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("envelope_sha256", sa.String(64)),
        sa.Column("migrated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actor_profile_migration_state")),
        sa.CheckConstraint("id=1 and schema_version=1 and classified_count >= 0", name=op.f("ck_actor_profile_migration_state_singleton")),
        sa.CheckConstraint(
            "(classified_count=0 and manifest_sha256 is null and envelope_sha256 is null) or "
            "(classified_count>0 and manifest_sha256 is not null and envelope_sha256 is not null)",
            name=op.f("ck_actor_profile_migration_state_evidence"),
        ),
    )
    bind.execute(
        sa.text(
            "insert into actor_profile_migration_state "
            "(id,schema_version,classified_count,source_row_set_sha256,manifest_sha256,envelope_sha256) "
            "values (1,1,:count,:source,:manifest,:envelope)"
        ),
        {
            "count": len(rows),
            "source": envelope.source_row_set_sha256 if envelope else source_row_set_sha256(()),
            "manifest": envelope.manifest_sha256 if envelope else None,
            "envelope": envelope.envelope_sha256 if envelope else None,
        },
    )
    legacy = bind.execute(
        sa.text(
            "select actor_id, external_subject, external_issuer, "
            "first_seen_at, last_seen_at, updated_at from legacy_actor_identities order by actor_id"
        )
    ).all()
    for row in legacy:
        kind = kinds[row.actor_id]
        profile_method = "automatic_first_access" if kind == "human" else "manual_service_provisioning"
        creator = row.actor_id if kind == "human" else "workstream:system:legacy-migration"
        link_id = str(uuid5(NAMESPACE_URL, f"workstream:identity-link:{row.actor_id}"))
        bind.execute(
            sa.text(
                "insert into actor_profiles "
                "(id,actor_kind,status,provisioning_method,display_name,contact_email,created_by,created_at,updated_at,last_seen_at) "
                "values (:id,:kind,'active',:method,null,null,:creator,:created,:updated,:last_seen)"
            ),
            {
                "id": row.actor_id,
                "kind": kind,
                "method": profile_method,
                "creator": creator,
                "created": row.first_seen_at,
                "updated": row.updated_at,
                "last_seen": row.last_seen_at,
            },
        )
        bind.execute(
            sa.text(
                "insert into actor_identity_links "
                "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,linked_at,last_verified_at) "
                "values (:id,:profile,:issuer,:subject,:kind,'active',:linked_by,:linked_at,:verified_at)"
            ),
            {
                "id": link_id,
                "profile": row.actor_id,
                "issuer": row.external_issuer,
                "subject": row.external_subject,
                "kind": kind,
                "linked_by": creator,
                "linked_at": row.first_seen_at,
                "verified_at": row.last_seen_at,
            },
        )
    _install_guards()


def downgrade() -> None:
    """Restore the legacy registry using only durable database state."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table actor_profiles in access exclusive mode"))
    bind.execute(sa.text("lock table actor_identity_links in access exclusive mode"))
    bind.execute(sa.text("lock table legacy_actor_identities in access exclusive mode"))
    unsafe_state = bind.execute(
        sa.text(
            "select exists("
            "select 1 from actor_profiles p join actor_identity_links l "
            "on l.actor_profile_id=p.id "
            "where p.status <> 'active' or l.status <> 'active'"
            ")"
        )
    ).scalar_one()
    if unsafe_state:
        raise RuntimeError("canonical actor downgrade refused: inactive authority state")
    bind.execute(
        sa.text(
            "insert into legacy_actor_identities "
            "(actor_id,external_subject,external_issuer,display_name,email,last_seen_roles,last_claim_snapshot,auth_source,is_dev_auth,first_seen_at,last_seen_at,updated_at) "
            "select p.id,l.subject,l.issuer,p.display_name,p.contact_email,'[]'::json,'{}'::json,'flow',false,p.created_at,coalesce(p.last_seen_at,p.created_at),p.updated_at "
            "from actor_profiles p join actor_identity_links l on l.actor_profile_id=p.id "
            "on conflict (actor_id) do update set "
            "display_name=excluded.display_name,email=excluded.email,"
            "last_seen_at=excluded.last_seen_at,updated_at=excluded.updated_at"
        )
    )
    op.execute("drop trigger actor_identity_link_profile_guard on actor_identity_links")
    op.execute("drop trigger actor_profile_link_guard on actor_profiles")
    op.execute("drop function validate_canonical_actor_link()")
    op.execute("drop trigger actor_identity_link_history_guard on actor_identity_links")
    op.execute("drop function guard_actor_identity_link_history()")
    op.execute("drop trigger actor_profile_history_guard on actor_profiles")
    op.execute("drop function guard_actor_profile_history()")
    op.drop_table("actor_identity_links")
    op.drop_table("actor_profiles")
    op.drop_table("actor_profile_migration_state")

    statements = (
        "alter table legacy_actor_identities rename constraint pk_legacy_actor_identities to pk_actor_identities",
        "alter table legacy_actor_identities rename constraint uq_legacy_actor_identities_external_identity to uq_actor_identities_external_identity",
        "alter table legacy_workflow_eligibility rename constraint pk_legacy_workflow_eligibility to pk_actor_profiles",
        "alter table legacy_workflow_eligibility rename constraint ck_legacy_workflow_eligibility_profile_type to ck_actor_profiles_ck_actor_profiles_profile_type",
        "alter table legacy_workflow_eligibility rename constraint ck_legacy_workflow_eligibility_status to ck_actor_profiles_ck_actor_profiles_status",
        "alter table legacy_workflow_eligibility rename constraint uq_legacy_workflow_eligibility_actor_type_scope to uq_actor_profiles_actor_type_scope",
        "alter table legacy_workflow_eligibility rename constraint fk_legacy_workflow_eligibility_actor_id_legacy_actor_identities to fk_actor_profiles_actor_id_actor_identities",
        "alter index ix_legacy_workflow_eligibility_actor_id rename to ix_actor_profiles_actor_id",
        "alter index ix_legacy_workflow_eligibility_profile_type rename to ix_actor_profiles_profile_type",
        "alter index ix_legacy_workflow_eligibility_status rename to ix_actor_profiles_status",
    )
    for statement in statements:
        op.execute(statement)
    op.rename_table("legacy_actor_identities", "actor_identities")
    op.rename_table("legacy_workflow_eligibility", "actor_profiles")
