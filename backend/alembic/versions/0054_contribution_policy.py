"""add contribution-policy persistence

Revision ID: 0054_contribution_policy
Revises: 0053_compensation_bindings
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0054_contribution_policy"
down_revision = "0053_compensation_bindings"
branch_labels = depends_on = None

# SIX is the ISO 4217 Maintenance Agency. Snapshot: List One, 2026-08-04.
ISO_4217_CURRENCY_CODES = tuple(
    """AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV
    BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE
    CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
    HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW
    KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU
    MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR
    PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN
    SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU
    UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR
    XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG""".split()
)


def upgrade() -> None:
    op.create_table(
        "contribution_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("current_published_version_id", sa.Uuid()),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("retired_by", sa.String(36)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status in ('draft','active','retired')",
            name="ck_contribution_policies_status",
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) between 1 and 200",
            name="ck_contribution_policies_name",
        ),
        sa.CheckConstraint(
            "(status='draft' and current_published_version_id is null "
            "and retired_by is null and retired_at is null) or "
            "(status='active' and current_published_version_id is not null "
            "and retired_by is null and retired_at is null) or "
            "(status='retired' and current_published_version_id is not null "
            "and retired_by is not null and retired_at is not null)",
            name="ck_contribution_policies_lifecycle_shape",
        ),
        sa.CheckConstraint(
            "retired_at is null or retired_at >= created_at",
            name="ck_contribution_policies_retirement_timestamp",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_contribution_policy_project"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["actor_profiles.id"], name="fk_contribution_policy_created_by"
        ),
        sa.ForeignKeyConstraint(
            ["retired_by"], ["actor_profiles.id"], name="fk_contribution_policy_retired_by"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contribution_policies"),
        sa.UniqueConstraint("id", "project_id", name="uq_contribution_policy_ownership"),
    )
    op.create_index(
        "uq_contribution_policy_active_project",
        "contribution_policies",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status='active'"),
    )

    op.create_table(
        "contribution_policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contribution_policy_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("published_by", sa.String(36)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retired_by", sa.String(36)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_contribution_policy_versions_version_number_positive",
        ),
        sa.CheckConstraint(
            "status in ('draft','published','retired')",
            name="ck_contribution_policy_versions_status",
        ),
        sa.CheckConstraint(
            "(status='draft' and published_by is null and published_at is null "
            "and retired_by is null and retired_at is null) or "
            "(status='published' and published_by is not null and published_at is not null "
            "and retired_by is null and retired_at is null) or "
            "(status='retired' and published_by is not null and published_at is not null "
            "and retired_by is not null and retired_at is not null)",
            name="ck_contribution_policy_versions_lifecycle_shape",
        ),
        sa.CheckConstraint(
            "(published_at is null or published_at >= created_at) and "
            "(retired_at is null or retired_at >= published_at)",
            name="ck_contribution_policy_versions_lifecycle_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_policy_id", "project_id"],
            ["contribution_policies.id", "contribution_policies.project_id"],
            name="fk_contribution_policy_version_policy",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_contribution_policy_version_project"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["actor_profiles.id"],
            name="fk_contribution_policy_version_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["actor_profiles.id"],
            name="fk_contribution_policy_version_published_by",
        ),
        sa.ForeignKeyConstraint(
            ["retired_by"],
            ["actor_profiles.id"],
            name="fk_contribution_policy_version_retired_by",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contribution_policy_versions"),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_contribution_policy_version_project"
        ),
        sa.UniqueConstraint(
            "id",
            "contribution_policy_id",
            "project_id",
            name="uq_contribution_policy_version_ownership",
        ),
        sa.UniqueConstraint(
            "contribution_policy_id",
            "version_number",
            name="uq_contribution_policy_version_number",
        ),
    )
    op.create_foreign_key(
        "fk_contribution_policy_current_version",
        "contribution_policies",
        "contribution_policy_versions",
        ["current_published_version_id", "id", "project_id"],
        ["id", "contribution_policy_id", "project_id"],
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "contribution_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contribution_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("contribution_type", sa.String(32), nullable=False),
        sa.Column("compensation_mode", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "contribution_type in ('accepted_submission','completed_review')",
            name="ck_contribution_rules_contribution_type",
        ),
        sa.CheckConstraint(
            "compensation_mode in ('unpaid','compensated')",
            name="ck_contribution_rules_compensation_mode",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_contribution_rule_version",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_contribution_rule_project"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contribution_rules"),
        sa.UniqueConstraint(
            "id",
            "contribution_policy_version_id",
            "project_id",
            "contribution_type",
            name="uq_contribution_rule_ownership",
        ),
        sa.UniqueConstraint(
            "contribution_policy_version_id",
            "contribution_type",
            name="uq_contribution_rule_type",
        ),
    )

    iso_currency_codes = op.create_table(
        "iso_4217_currency_codes",
        sa.Column("code", sa.String(3), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[A-Z]{3}$'", name="ck_iso_4217_currency_codes_code"
        ),
        sa.PrimaryKeyConstraint("code", name="pk_iso_4217_currency_codes"),
    )
    op.bulk_insert(
        iso_currency_codes,
        [{"code": code} for code in ISO_4217_CURRENCY_CODES],
    )
    op.create_table(
        "project_compensation_units",
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("instrument_type", sa.String(32), nullable=False),
        sa.Column("unit_code", sa.String(32), nullable=False),
        sa.Column("iso_currency_code", sa.String(3)),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("retired_by", sa.String(36)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "instrument_type in ('money','project_points')",
            name="ck_project_compensation_units_instrument_type",
        ),
        sa.CheckConstraint(
            "status in ('active','retired')",
            name="ck_project_compensation_units_status",
        ),
        sa.CheckConstraint(
            "(instrument_type='money' and iso_currency_code is not null "
            "and unit_code=iso_currency_code) or "
            "(instrument_type='project_points' and iso_currency_code is null "
            "and unit_code ~ '^[A-Za-z][A-Za-z0-9._:-]{0,31}$')",
            name="ck_project_compensation_units_unit_identity",
        ),
        sa.CheckConstraint(
            "(status='active' and retired_by is null and retired_at is null) or "
            "(status='retired' and retired_by is not null and retired_at is not null)",
            name="ck_project_compensation_units_lifecycle_shape",
        ),
        sa.CheckConstraint(
            "retired_at is null or retired_at >= created_at",
            name="ck_project_compensation_units_retirement_time",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_project_compensation_unit_project"
        ),
        sa.ForeignKeyConstraint(
            ["iso_currency_code"],
            ["iso_4217_currency_codes.code"],
            name="fk_project_compensation_unit_iso_currency",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["actor_profiles.id"],
            name="fk_project_compensation_unit_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["retired_by"],
            ["actor_profiles.id"],
            name="fk_project_compensation_unit_retired_by",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "instrument_type",
            "unit_code",
            name="pk_project_compensation_units",
        ),
        sa.UniqueConstraint(
            "project_id",
            "instrument_type",
            "unit_code",
            name="uq_project_compensation_unit_identity",
        ),
    )

    op.create_table(
        "contribution_award_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contribution_rule_id", sa.Uuid(), nullable=False),
        sa.Column("contribution_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("contribution_type", sa.String(32), nullable=False),
        sa.Column("instrument_type", sa.String(32), nullable=False),
        sa.Column("unit_code", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("adapter_binding_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "contribution_type in ('accepted_submission','completed_review')",
            name="ck_contribution_award_definitions_contribution_type",
        ),
        sa.CheckConstraint(
            "instrument_type in ('money','project_points')",
            name="ck_contribution_award_definitions_instrument_type",
        ),
        sa.CheckConstraint(
            "quantity > 0 and quantity < 100000000000000000000 "
            "and scale(quantity) between 0 and 18",
            name="ck_contribution_award_definitions_quantity_exact_bounds",
        ),
        sa.CheckConstraint(
            "instrument_type <> 'project_points' or scale(quantity)=0",
            name="ck_contribution_award_definitions_project_points_whole",
        ),
        sa.ForeignKeyConstraint(
            [
                "contribution_rule_id",
                "contribution_policy_version_id",
                "project_id",
                "contribution_type",
            ],
            [
                "contribution_rules.id",
                "contribution_rules.contribution_policy_version_id",
                "contribution_rules.project_id",
                "contribution_rules.contribution_type",
            ],
            name="fk_contribution_award_definition_rule",
        ),
        sa.ForeignKeyConstraint(
            ["adapter_binding_id", "project_id", "instrument_type"],
            [
                "project_compensation_adapter_bindings.id",
                "project_compensation_adapter_bindings.project_id",
                "project_compensation_adapter_bindings.instrument_type",
            ],
            name="fk_contribution_award_definition_binding",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "instrument_type", "unit_code"],
            [
                "project_compensation_units.project_id",
                "project_compensation_units.instrument_type",
                "project_compensation_units.unit_code",
            ],
            name="fk_contribution_award_definition_unit",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_contribution_award_definition_project",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contribution_award_definitions"),
        sa.UniqueConstraint(
            "contribution_rule_id",
            "instrument_type",
            name="uq_contribution_award_definition_instrument",
        ),
    )

    op.execute(
        """
        create function guard_contribution_policy_version_content() returns trigger
        language plpgsql as $$
        begin
          if tg_op='DELETE' and old.status in ('published','retired') then
            raise exception 'published contribution policy versions are immutable'
              using errcode='55000';
          end if;
          if tg_op='UPDATE' and old.status='retired' then
            raise exception 'retired contribution policy versions are immutable'
              using errcode='55000';
          end if;
          if tg_op='UPDATE' and old.status='published' and not (
            new.status='retired'
            and new.id=old.id
            and new.contribution_policy_id=old.contribution_policy_id
            and new.project_id=old.project_id
            and new.version_number=old.version_number
            and new.created_by=old.created_by
            and new.created_at=old.created_at
            and new.published_by=old.published_by
            and new.published_at=old.published_at
            and new.retired_by is not null
            and new.retired_at is not null
          ) then
            raise exception 'published contribution policy version content is immutable'
              using errcode='55000';
          end if;
          return case when tg_op='DELETE' then old else new end;
        end;
        $$;
        """
    )
    op.execute(
        "create trigger contribution_policy_versions_content_guard "
        "before update or delete on contribution_policy_versions for each row "
        "execute function guard_contribution_policy_version_content()"
    )
    op.execute(
        """
        create function guard_iso_4217_currency_codes() returns trigger
        language plpgsql as $$
        begin
          raise exception 'ISO 4217 currency-code registry is migration-owned and immutable'
            using errcode='55000';
        end;
        $$;
        """
    )
    op.execute(
        "create trigger iso_4217_currency_codes_immutable "
        "before insert or update or delete on iso_4217_currency_codes for each row "
        "execute function guard_iso_4217_currency_codes()"
    )
    op.execute(
        """
        create function guard_project_compensation_units() returns trigger
        language plpgsql as $$
        begin
          if tg_op in ('UPDATE','DELETE') then
            raise exception 'project compensation-unit lifecycle behavior is deferred'
              using errcode='55000';
          end if;
          if new.status <> 'active' then
            raise exception 'project compensation units must begin active'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
        """
    )
    op.execute(
        "create trigger project_compensation_units_lifecycle_guard "
        "before insert or update or delete on project_compensation_units for each row "
        "execute function guard_project_compensation_units()"
    )
    op.execute(
        """
        create function guard_contribution_policy_children() returns trigger
        language plpgsql as $$
        declare old_parent_status text;
        declare new_parent_status text;
        begin
          if tg_op in ('UPDATE','DELETE') then
            select status into old_parent_status from contribution_policy_versions
            where id=old.contribution_policy_version_id for update;
          end if;
          if tg_op in ('INSERT','UPDATE') then
            select status into new_parent_status from contribution_policy_versions
            where id=new.contribution_policy_version_id for update;
          end if;
          if old_parent_status in ('published','retired')
             or new_parent_status in ('published','retired') then
            raise exception 'published contribution policy rules and definitions are immutable'
              using errcode='55000';
          end if;
          return case when tg_op='DELETE' then old else new end;
        end;
        $$;
        """
    )
    for table in ("contribution_rules", "contribution_award_definitions"):
        op.execute(
            f"create trigger {table}_content_guard before insert or update or delete on {table} "
            "for each row execute function guard_contribution_policy_children()"
        )

    op.execute(
        """
        create function validate_contribution_policy_graph() returns trigger
        language plpgsql as $$
        begin
          if exists (
            select 1 from contribution_policy_versions v
            where v.status in ('published','retired') and (
              (select count(*) from contribution_rules r
               where r.contribution_policy_version_id=v.id
                 and r.contribution_type='accepted_submission') <> 1
              or
              (select count(*) from contribution_rules r
               where r.contribution_policy_version_id=v.id
                 and r.contribution_type='completed_review') <> 1
              or exists (
                select 1 from contribution_rules r
                where r.contribution_policy_version_id=v.id and (
                  (r.compensation_mode='unpaid' and
                    (select count(*) from contribution_award_definitions d
                     where d.contribution_rule_id=r.id) <> 0)
                  or
                  (r.compensation_mode='compensated' and
                    (select count(*) from contribution_award_definitions d
                     where d.contribution_rule_id=r.id) not between 1 and 2)
                )
              )
            )
          ) then
            raise exception 'published contribution policy graph is incomplete'
              using errcode='23514';
          end if;

          if exists (
            select 1 from contribution_policies p
            left join contribution_policy_versions v
              on v.id=p.current_published_version_id
             and v.contribution_policy_id=p.id
             and v.project_id=p.project_id
            where p.status='active' and (v.id is null or v.status <> 'published')
          ) then
            raise exception 'active contribution policy selector is invalid'
              using errcode='23514';
          end if;
          return null;
        end;
        $$;
        """
    )
    for table in (
        "contribution_policies",
        "contribution_policy_versions",
        "contribution_rules",
        "contribution_award_definitions",
    ):
        op.execute(
            f"create constraint trigger {table}_graph_guard "
            f"after insert or update or delete on {table} deferrable initially deferred "
            "for each row execute function validate_contribution_policy_graph()"
        )
    op.execute(
        """
        create function reject_contribution_policy_truncate() returns trigger
        language plpgsql as $$
        begin
          raise exception 'contribution policy persistence cannot be truncated'
            using errcode='55000';
        end;
        $$;
        """
    )
    for table in (
        "contribution_policies",
        "contribution_policy_versions",
        "contribution_rules",
        "contribution_award_definitions",
        "project_compensation_units",
        "iso_4217_currency_codes",
    ):
        op.execute(
            f"create trigger {table}_reject_truncate before truncate on {table} "
            "execute function reject_contribution_policy_truncate()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    populated = sum(
        bind.execute(sa.text(f"select count(*) from {table}")).scalar_one()
        for table in (
            "contribution_policies",
            "contribution_policy_versions",
            "contribution_rules",
            "contribution_award_definitions",
            "project_compensation_units",
        )
    )
    if populated:
        raise RuntimeError("cannot downgrade populated contribution policy persistence")

    for table in (
        "contribution_policies",
        "contribution_policy_versions",
        "contribution_rules",
        "contribution_award_definitions",
        "project_compensation_units",
        "iso_4217_currency_codes",
    ):
        op.execute(f"drop trigger {table}_reject_truncate on {table}")
    op.execute("drop function reject_contribution_policy_truncate()")
    for table in (
        "contribution_policies",
        "contribution_policy_versions",
        "contribution_rules",
        "contribution_award_definitions",
    ):
        op.execute(f"drop trigger {table}_graph_guard on {table}")
    op.execute("drop function validate_contribution_policy_graph()")
    for table in ("contribution_award_definitions", "contribution_rules"):
        op.execute(f"drop trigger {table}_content_guard on {table}")
    op.execute("drop function guard_contribution_policy_children()")
    op.execute(
        "drop trigger project_compensation_units_lifecycle_guard "
        "on project_compensation_units"
    )
    op.execute("drop function guard_project_compensation_units()")
    op.execute(
        "drop trigger iso_4217_currency_codes_immutable on iso_4217_currency_codes"
    )
    op.execute("drop function guard_iso_4217_currency_codes()")
    op.execute(
        "drop trigger contribution_policy_versions_content_guard "
        "on contribution_policy_versions"
    )
    op.execute("drop function guard_contribution_policy_version_content()")
    op.drop_table("contribution_award_definitions")
    op.drop_table("project_compensation_units")
    op.drop_table("iso_4217_currency_codes")
    op.drop_table("contribution_rules")
    op.drop_constraint(
        "fk_contribution_policy_current_version",
        "contribution_policies",
        type_="foreignkey",
    )
    op.drop_table("contribution_policy_versions")
    op.drop_index(
        "uq_contribution_policy_active_project", table_name="contribution_policies"
    )
    op.drop_table("contribution_policies")
