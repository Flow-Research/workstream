"""register the fixed project-setup service identity

Revision ID: 0042_project_setup_service
Revises: 0041_project_mutation_evidence
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0042_project_setup_service"
down_revision = "0041_project_mutation_evidence"
branch_labels = depends_on = None

_HISTORICAL_IDENTITIES = (
    "workstream.artifact.verifier",
    "workstream.artifact.put_resolver",
    "workstream.artifact.scheduler",
    "workstream.artifact.binding",
    "workstream.artifact.guide_reader",
    "workstream.artifact.materializer",
    "workstream.artifact.checker_output",
)
_PROJECT_SETUP_IDENTITY = "workstream.project.setup"


def _tokens(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


def _replace_identity_constraint(values: tuple[str, ...]) -> None:
    op.drop_constraint("kind_service_identity", "actor_profiles", type_="check")
    op.create_check_constraint(
        "kind_service_identity",
        "actor_profiles",
        "(actor_kind='human' and service_identity is null) or "
        f"(actor_kind='service' and service_identity in ({_tokens(values)}))",
    )


def upgrade() -> None:
    """Admit the eighth closed identity without creating a service actor."""
    op.get_bind().execute(sa.text("lock table actor_profiles in access exclusive mode"))
    _replace_identity_constraint((*_HISTORICAL_IDENTITIES, _PROJECT_SETUP_IDENTITY))


def downgrade() -> None:
    """Restore the seven-identity constraint only when the new identity is unused."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table actor_profiles in access exclusive mode"))
    in_use = bind.execute(
        sa.text(
            "select exists(select 1 from actor_profiles where service_identity=:identity)"
        ),
        {"identity": _PROJECT_SETUP_IDENTITY},
    ).scalar_one()
    if in_use:
        raise RuntimeError("cannot downgrade project setup service identity")
    _replace_identity_constraint(_HISTORICAL_IDENTITIES)
