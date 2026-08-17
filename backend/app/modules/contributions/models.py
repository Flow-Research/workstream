"""SQLAlchemy persistence for contribution-policy economic truth."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ContributionPolicy(Base):
    """Stable project aggregate selecting one published policy version."""

    __tablename__ = "contribution_policies"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_contribution_policy_ownership"),
        ForeignKeyConstraint(
            ["current_published_version_id", "id", "project_id"],
            [
                "contribution_policy_versions.id",
                "contribution_policy_versions.contribution_policy_id",
                "contribution_policy_versions.project_id",
            ],
            name="fk_contribution_policy_current_version",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("status in ('draft','active','retired')", name="status"),
        CheckConstraint("char_length(btrim(name)) between 1 and 200", name="name"),
        CheckConstraint(
            "(status='draft' and current_published_version_id is null "
            "and retired_by is null and retired_at is null) or "
            "(status='active' and current_published_version_id is not null "
            "and retired_by is null and retired_at is null) or "
            "(status='retired' and current_published_version_id is not null "
            "and retired_by is not null and retired_at is not null)",
            name="lifecycle_shape",
        ),
        CheckConstraint(
            "retired_at is null or retired_at >= created_at",
            name="retirement_timestamp",
        ),
        Index(
            "uq_contribution_policy_active_project",
            "project_id",
            unique=True,
            postgresql_where=text("status='active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_contribution_policy_project"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    current_published_version_id: Mapped[UUID | None] = mapped_column(Uuid())
    last_transition_operation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "contribution_policy_transition_custody.operation_id",
            name="fk_contribution_policy_transition_custody",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        )
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_created_by"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    retired_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_retired_by")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    versions: Mapped[list["ContributionPolicyVersion"]] = relationship(
        back_populates="policy",
        foreign_keys="ContributionPolicyVersion.contribution_policy_id",
    )


class ContributionPolicyVersion(Base):
    """Versioned contribution rules; published economic content is immutable."""

    __tablename__ = "contribution_policy_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contribution_policy_id", "project_id"],
            ["contribution_policies.id", "contribution_policies.project_id"],
            name="fk_contribution_policy_version_policy",
        ),
        UniqueConstraint(
            "id", "project_id", name="uq_contribution_policy_version_project"
        ),
        UniqueConstraint(
            "id",
            "contribution_policy_id",
            "project_id",
            name="uq_contribution_policy_version_ownership",
        ),
        UniqueConstraint(
            "contribution_policy_id",
            "version_number",
            name="uq_contribution_policy_version_number",
        ),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint("status in ('draft','published','retired')", name="status"),
        CheckConstraint(
            "(status='draft' and published_by is null and published_at is null "
            "and retired_by is null and retired_at is null) or "
            "(status='published' and published_by is not null and published_at is not null "
            "and retired_by is null and retired_at is null) or "
            "(status='retired' and published_by is not null and published_at is not null "
            "and retired_by is not null and retired_at is not null)",
            name="lifecycle_shape",
        ),
        CheckConstraint(
            "(published_at is null or published_at >= created_at) and "
            "(retired_at is null or retired_at >= published_at)",
            name="lifecycle_timestamps",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    contribution_policy_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_contribution_policy_version_project"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    created_by: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_version_created_by"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    published_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_version_published_by")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_version_retired_by")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_version_updated_by")
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_transition_operation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "contribution_policy_transition_custody.operation_id",
            name="fk_contribution_policy_version_transition_custody",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        )
    )

    policy: Mapped[ContributionPolicy] = relationship(
        back_populates="versions",
        foreign_keys=[contribution_policy_id],
    )
    rules: Mapped[list["ContributionRule"]] = relationship(back_populates="version")


class ContributionRule(Base):
    """One explicit eligibility rule for a canonical contribution type."""

    __tablename__ = "contribution_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_contribution_rule_version",
        ),
        UniqueConstraint(
            "id",
            "contribution_policy_version_id",
            "project_id",
            "contribution_type",
            name="uq_contribution_rule_ownership",
        ),
        UniqueConstraint(
            "contribution_policy_version_id",
            "contribution_type",
            name="uq_contribution_rule_type",
        ),
        CheckConstraint(
            "contribution_type in ('accepted_submission','completed_review')",
            name="contribution_type",
        ),
        CheckConstraint(
            "compensation_mode in ('unpaid','compensated')",
            name="compensation_mode",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_contribution_rule_project"), nullable=False
    )
    contribution_type: Mapped[str] = mapped_column(String(32), nullable=False)
    compensation_mode: Mapped[str] = mapped_column(String(16), nullable=False)

    version: Mapped[ContributionPolicyVersion] = relationship(back_populates="rules")
    award_definitions: Mapped[list["ContributionAwardDefinition"]] = relationship(
        back_populates="rule"
    )


class Iso4217CurrencyCode(Base):
    """Migration-seeded immutable ISO 4217 List One alphabetic code."""

    __tablename__ = "iso_4217_currency_codes"
    __table_args__ = (
        CheckConstraint("code ~ '^[A-Z]{3}$'", name="code"),
    )

    code: Mapped[str] = mapped_column(String(3), primary_key=True)


class ProjectCompensationUnit(Base):
    """Project-enabled money or project-scoped points unit identity."""

    __tablename__ = "project_compensation_units"
    __table_args__ = (
        ForeignKeyConstraint(
            ["iso_currency_code"],
            ["iso_4217_currency_codes.code"],
            name="fk_project_compensation_unit_iso_currency",
        ),
        CheckConstraint(
            "instrument_type in ('money','project_points')", name="instrument_type"
        ),
        CheckConstraint("status in ('active','retired')", name="status"),
        CheckConstraint(
            "(instrument_type='money' and iso_currency_code is not null "
            "and unit_code=iso_currency_code) or "
            "(instrument_type='project_points' and iso_currency_code is null "
            "and unit_code ~ '^[A-Za-z][A-Za-z0-9._:-]{0,31}$')",
            name="unit_identity",
        ),
        CheckConstraint(
            "(status='active' and retired_by is null and retired_at is null) or "
            "(status='retired' and retired_by is not null and retired_at is not null)",
            name="lifecycle_shape",
        ),
        CheckConstraint("retired_at is null or retired_at >= created_at", name="retirement_time"),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_project_compensation_unit_project"),
        primary_key=True,
    )
    instrument_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    unit_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    iso_currency_code: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_by: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_project_compensation_unit_created_by"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    retired_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_project_compensation_unit_retired_by")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContributionAwardDefinition(Base):
    """Exact compensation fact attached to one compensated contribution rule."""

    __tablename__ = "contribution_award_definitions"
    __table_args__ = (
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
            ["adapter_binding_id", "project_id", "instrument_type"],
            [
                "project_compensation_adapter_bindings.id",
                "project_compensation_adapter_bindings.project_id",
                "project_compensation_adapter_bindings.instrument_type",
            ],
            name="fk_contribution_award_definition_binding",
        ),
        ForeignKeyConstraint(
            ["project_id", "instrument_type", "unit_code"],
            [
                "project_compensation_units.project_id",
                "project_compensation_units.instrument_type",
                "project_compensation_units.unit_code",
            ],
            name="fk_contribution_award_definition_unit",
        ),
        UniqueConstraint(
            "contribution_rule_id",
            "instrument_type",
            name="uq_contribution_award_definition_instrument",
        ),
        CheckConstraint(
            "contribution_type in ('accepted_submission','completed_review')",
            name="contribution_type",
        ),
        CheckConstraint(
            "instrument_type in ('money','project_points')",
            name="instrument_type",
        ),
        CheckConstraint(
            "quantity > 0 and quantity < 100000000000000000000 "
            "and scale(quantity) between 0 and 18",
            name="quantity_exact_bounds",
        ),
        CheckConstraint(
            "instrument_type <> 'project_points' or scale(quantity)=0",
            name="project_points_whole",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    contribution_rule_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_contribution_award_definition_project"),
        nullable=False,
    )
    contribution_type: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    adapter_binding_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)

    rule: Mapped[ContributionRule] = relationship(back_populates="award_definitions")

class ContributionPolicyTransitionCustody(Base):
    """Database-timestamped custody for one publish or retire transition."""

    __tablename__ = "contribution_policy_transition_custody"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contribution_policy_id", "project_id"],
            ["contribution_policies.id", "contribution_policies.project_id"],
            name="fk_contribution_policy_custody_policy",
        ),
        ForeignKeyConstraint(
            ["contribution_policy_version_id", "contribution_policy_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.contribution_policy_id", "contribution_policy_versions.project_id"],
            name="fk_contribution_policy_custody_version",
        ),
        ForeignKeyConstraint(
            ["prior_current_version_id", "contribution_policy_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.contribution_policy_id", "contribution_policy_versions.project_id"],
            name="fk_contribution_policy_custody_prior_version",
        ),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest"),
        CheckConstraint("event_type in ('published','retired')", name="event_type"),
    )

    operation_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_custody_actor"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_contribution_policy_custody_project"),
        nullable=False,
    )
    contribution_policy_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    prior_current_version_id: Mapped[UUID | None] = mapped_column(Uuid())
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))

class ContributionPolicyLifecycleEvent(Base):
    """Immutable recoverable truth for one policy-version mutation."""

    __tablename__ = "contribution_policy_lifecycle_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contribution_policy_id", "project_id"],
            ["contribution_policies.id", "contribution_policies.project_id"],
            name="fk_contribution_policy_event_policy_ownership",
        ),
        ForeignKeyConstraint(
            [
                "contribution_policy_version_id",
                "contribution_policy_id",
                "project_id",
            ],
            [
                "contribution_policy_versions.id",
                "contribution_policy_versions.contribution_policy_id",
                "contribution_policy_versions.project_id",
            ],
            name="fk_contribution_policy_event_version_ownership",
        ),
        UniqueConstraint("operation_id", name="uq_contribution_policy_event_operation"),
        UniqueConstraint(
            "publication_custody_operation_id",
            name="uq_contribution_policy_event_publication_custody",
        ),
        ForeignKeyConstraint(
            ["publication_custody_operation_id"],
            ["contribution_policy_transition_custody.operation_id"],
            name="fk_contribution_policy_event_publication_custody",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_contribution_policy_event_digest",
        ),
        CheckConstraint(
            "event_type in ('draft_created','draft_updated','published','retired')",
            name="ck_contribution_policy_event_type",
        ),
        CheckConstraint(
            "(event_type='draft_created' and from_version_status is null "
            "and to_version_status='draft') or "
            "(event_type='draft_updated' and from_version_status='draft' "
            "and to_version_status='draft') or "
            "(event_type='published' and from_version_status='draft' "
            "and to_version_status='published') or "
            "(event_type='retired' and from_version_status='published' "
            "and to_version_status='retired')",
            name="ck_contribution_policy_event_transition",
        ),
        CheckConstraint(
            "(event_type in ('draft_created','draft_updated') "
            "and publication_custody_operation_id is null) or "
            "(event_type in ('published','retired') "
            "and publication_custody_operation_id=operation_id)",
            name="ck_contribution_policy_event_custody_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    publication_custody_operation_id: Mapped[UUID | None] = mapped_column(Uuid())
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_contribution_policy_event_actor"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_contribution_policy_event_project"),
        nullable=False,
    )
    contribution_policy_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_current_version_id: Mapped[UUID | None] = mapped_column(Uuid())
    prior_current_version_number: Mapped[int | None] = mapped_column(Integer)
    from_policy_status: Mapped[str | None] = mapped_column(String(16))
    to_policy_status: Mapped[str] = mapped_column(String(16), nullable=False)
    from_version_status: Mapped[str | None] = mapped_column(String(16))
    to_version_status: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
