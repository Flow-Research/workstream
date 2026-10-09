"""Admit Markdown to the persisted review-packet guide media invariant."""

from alembic import op
import sqlalchemy as sa

revision = "0027_markdown_guide_media"
down_revision = "0026_task_guide_read"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_review_packet_guide_items_guide_media"
_PREDECESSOR_DEFINITION = (
    "CHECK (((media_type)::text = ANY ((ARRAY['application/pdf'::character varying, "
    "'application/vnd.openxmlformats-officedocument.wordprocessingml.document'::character varying, "
    "'application/vnd.openxmlformats-officedocument.presentationml.presentation'::character varying])::text[])))"
)
_CURRENT_EXPRESSION = (
    "media_type in ('application/pdf',"
    "'application/vnd.openxmlformats-officedocument.wordprocessingml.document',"
    "'application/vnd.openxmlformats-officedocument.presentationml.presentation',"
    "'text/markdown')"
)


def upgrade():
    op.execute("set local search_path = pg_catalog, public, pg_temp")
    op.execute("lock table public.review_packet_guide_items in access exclusive mode")
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "select pg_get_constraintdef(oid), convalidated "
                "from pg_catalog.pg_constraint "
                "where conrelid='public.review_packet_guide_items'::regclass "
                "and conname=:name"
            ),
            {"name": _CONSTRAINT},
        )
        .one()
    )
    if row[0] != _PREDECESSOR_DEFINITION or row[1] is not True:
        raise RuntimeError("review packet guide media constraint shape changed")
    op.execute(f"alter table public.review_packet_guide_items drop constraint {_CONSTRAINT}")
    op.execute(
        f"alter table public.review_packet_guide_items add constraint {_CONSTRAINT} "
        f"check ({_CURRENT_EXPRESSION})"
    )


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
