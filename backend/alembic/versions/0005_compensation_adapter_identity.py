"""Add the target-only compensation adapter service identity."""

from alembic import op

revision = "0005_compensation_adapter_identity"
down_revision = "0004_compensation_adapter_binding_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_actor_profiles_kind_service_identity"),
        "actor_profiles",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_actor_profiles_kind_service_identity"),
        "actor_profiles",
        "(actor_kind = 'human' and service_identity is null) or "
        "(actor_kind = 'service' and service_identity in ("
        "'workstream.artifact.verifier',"
        "'workstream.artifact.put_resolver',"
        "'workstream.artifact.scheduler',"
        "'workstream.artifact.binding',"
        "'workstream.artifact.guide_reader',"
        "'workstream.artifact.materializer',"
        "'workstream.artifact.checker_output',"
        "'workstream.project.setup',"
        "'workstream.review.preference_expiry',"
        "'workstream.review.lease_expiry',"
        "'workstream.review.authority_invalidation_reconciliation',"
        "'workstream.review.reconciliation',"
        "'workstream.review.artifact_reference_reconciliation',"
        "'workstream.review.projection',"
        "'workstream.compensation.adapter'))",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Workstream v0.1 migrations cannot be downgraded; recreate the database"
    )
