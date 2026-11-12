"""Read-only retained-reward inventory; never a migration or payment operation."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC
import json
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db.session import dispose_engine, get_engine


SUPPORTED_REVISION = "0068_issuer_profile_email"

# Fixed offline inspection SQL. No caller input can select tables or predicates.
INVENTORIES = {
    **{
        f"v1_policy_{status}": (
            f"SELECT id FROM public.contribution_policy_versions WHERE status='{status}'"
        )
        for status in ("draft", "published", "retired")
    },
    "unscreened_draft_tasks": """
        SELECT id FROM public.workstream_tasks
        WHERE status='draft' AND locked_contribution_policy_version_id IS NULL
    """,
    "retained_contributions": "SELECT id FROM public.contribution_records",
    "retained_awards": "SELECT id FROM public.compensation_awards",
    "dual_award_contributions": """
        SELECT contribution_record_id AS id FROM public.compensation_awards
        GROUP BY contribution_record_id HAVING count(*) > 1
    """,
    "saved_task_commands": "SELECT id FROM public.task_command_receipts",
    "saved_import_batches": "SELECT id FROM public.task_import_batches",
    "saved_import_commands": "SELECT id FROM public.task_import_batch_command_receipts",
    "saved_import_members": "SELECT id FROM public.task_import_batch_members",
    "saved_policy_operations": "SELECT id FROM public.contribution_policy_lifecycle_events",
    "saved_policy_transition_custody": """
        SELECT operation_id AS id FROM public.contribution_policy_transition_custody
    """,
    "saved_revision_preparations": "SELECT id FROM public.task_revision_preparations",
}

LIVE_TASKS = """
    SELECT t.id FROM public.workstream_tasks t
    JOIN public.contribution_policy_versions p ON p.id=t.locked_contribution_policy_version_id
    WHERE t.status <> 'accepted'
"""

BLOCKERS = {
    "live_v1_tasks": LIVE_TASKS,
    "live_v1_assignments": """
        SELECT a.id FROM public.task_assignments a
        JOIN public.contribution_policy_versions p
          ON p.id=a.submitter_contribution_policy_version_id
        WHERE a.status='active'
    """,
    "live_v1_submissions": """
        SELECT s.id FROM public.submissions s
        JOIN public.contribution_policy_versions p ON p.id=s.contribution_policy_version_id
        WHERE s.attempt_status IN ('evaluation_pending','review_pending','needs_revision')
    """,
    "live_v1_revision_preparations": f"""
        SELECT r.id FROM public.task_revision_preparations r
        WHERE r.task_id IN ({LIVE_TASKS})
    """,
    "acceptance_source_anomalies": """
        SELECT f.id FROM public.final_acceptances f
        LEFT JOIN public.submissions s ON s.id=f.submission_id
        LEFT JOIN public.workstream_tasks t ON t.id=s.task_id
        LEFT JOIN public.artifact_contents content ON content.id=s.artifact_content_id
        LEFT JOIN public.audit_events audit ON audit.id=f.source_authorization_decision_id
        LEFT JOIN public.task_post_submit_routing_manifests m ON m.id=f.source_routing_manifest_id
        LEFT JOIN public.reviews r ON r.id=f.source_review_id
        LEFT JOIN public.review_leases lease ON lease.id=r.review_lease_id
        WHERE s.id IS NULL OR t.id IS NULL OR content.id IS NULL OR audit.id IS NULL
           OR ROW(f.project_id,f.task_id,f.accepted_submitter_id,f.policy_context_ref)
              IS DISTINCT FROM ROW(t.project_id,s.task_id,s.contributor_id,s.locked_review_policy_id)
           OR (f.acceptance_source='task_post_submit_route' AND (
                 m.id IS NULL OR m.human_review_required OR f.source_review_id IS NOT NULL
              OR ROW(m.project_id,m.task_id,m.submission_id,m.contributor_id,m.content_sha256,
                     m.router_actor_id,m.authorization_decision_id,m.final_acceptance_id)
                 IS DISTINCT FROM
                 ROW(f.project_id,f.task_id,f.submission_id,f.accepted_submitter_id,content.sha256,
                     f.recorded_by,f.source_authorization_decision_id,f.id)
              OR f.policy_context_ref::text IS DISTINCT FROM
                 m.authority_context#>>'{source,locked_policy,locked_review_policy_id}'
              OR NOT public.task_routing_receipt_valid(m)))
           OR (f.acceptance_source='human_review' AND (
                 r.id IS NULL OR lease.id IS NULL OR r.decision<>'accept'
              OR f.source_routing_manifest_id IS NOT NULL
              OR ROW(r.project_id,r.task_id,r.submission_id,r.task_assignment_id,
                     r.reviewer_id,r.locked_review_policy_id,r.artifact_hash)
                 IS DISTINCT FROM ROW(f.project_id,f.task_id,f.submission_id,s.task_assignment_id,
                     f.recorded_by,f.policy_context_ref,content.sha256)
              OR ROW(lease.project_id,lease.task_id,lease.submission_id,lease.reviewer_id,
                     lease.reviewer_contribution_policy_version_id)
                 IS DISTINCT FROM ROW(r.project_id,r.task_id,r.submission_id,r.reviewer_id,
                     r.reviewer_contribution_policy_version_id)
              OR audit.actor_id IS DISTINCT FROM f.recorded_by::text))
    """,
    "acceptance_contribution_gaps": """
        SELECT f.id FROM public.final_acceptances f
        WHERE NOT EXISTS (
            SELECT 1 FROM public.contribution_records c
            WHERE c.source_final_acceptance_id=f.id AND c.contribution_type='accepted_submission'
              AND ROW(c.project_id,c.task_id,c.submission_id,c.contributor_id)
                  IS NOT DISTINCT FROM
                  ROW(f.project_id,f.task_id,f.submission_id,f.accepted_submitter_id))
    """,
    "contribution_source_anomalies": """
        SELECT c.id FROM public.contribution_records c
        LEFT JOIN public.submissions s ON s.id=c.submission_id
        LEFT JOIN public.workstream_tasks t ON t.id=s.task_id
        LEFT JOIN public.task_assignments a ON a.id=s.task_assignment_id
        LEFT JOIN public.artifact_contents content ON content.id=s.artifact_content_id
        LEFT JOIN public.artifact_bindings binding ON binding.id=s.artifact_binding_id
        LEFT JOIN public.contribution_policy_versions p ON p.id=c.contribution_policy_version_id
        LEFT JOIN public.final_acceptances f ON f.id=c.source_final_acceptance_id
        LEFT JOIN public.reviews r ON r.id=c.source_review_id
        LEFT JOIN public.review_leases lease ON lease.id=c.source_review_lease_id
        WHERE s.id IS NULL OR t.id IS NULL OR a.id IS NULL OR content.id IS NULL
           OR binding.id IS NULL OR p.id IS NULL OR p.status NOT IN ('published','retired')
           OR ROW(c.project_id,c.task_id,c.artifact_hash)
              IS DISTINCT FROM ROW(t.project_id,s.task_id,content.sha256)
           OR ROW(a.project_id,a.task_id,a.contributor_id)
              IS DISTINCT FROM ROW(c.project_id,c.task_id,s.contributor_id)
           OR ROW(binding.content_id,binding.project_id,binding.resource_id,
                  binding.resource_type,binding.logical_role)
              IS DISTINCT FROM ROW(content.id,c.project_id,s.id::text,
                  'submission','submission_bundle_original')
           OR p.project_id IS DISTINCT FROM c.project_id
           OR NOT EXISTS (SELECT 1 FROM public.contribution_rules rule
                WHERE rule.contribution_policy_version_id=p.id AND rule.project_id=c.project_id
                  AND rule.contribution_type=c.contribution_type)
           OR (c.contribution_type='accepted_submission' AND (
                 f.id IS NULL OR c.source_review_id IS NOT NULL
              OR ROW(f.project_id,f.task_id,f.submission_id,f.accepted_submitter_id,
                     a.id,a.submitter_contribution_policy_version_id,s.contribution_policy_version_id)
                 IS DISTINCT FROM ROW(c.project_id,c.task_id,c.submission_id,c.contributor_id,
                     c.source_task_assignment_id,c.contribution_policy_version_id,
                     c.contribution_policy_version_id)))
           OR (c.contribution_type='completed_review' AND (
                 r.id IS NULL OR lease.id IS NULL OR c.source_final_acceptance_id IS NOT NULL
              OR ROW(r.project_id,r.task_id,r.submission_id,r.reviewer_id,r.review_lease_id,
                     r.reviewer_contribution_policy_version_id,r.artifact_hash)
                 IS DISTINCT FROM ROW(c.project_id,c.task_id,c.submission_id,c.contributor_id,
                     c.source_review_lease_id,c.contribution_policy_version_id,c.artifact_hash)
              OR ROW(lease.project_id,lease.task_id,lease.submission_id,lease.reviewer_id,
                     lease.reviewer_contribution_policy_version_id)
                 IS DISTINCT FROM ROW(c.project_id,c.task_id,c.submission_id,c.contributor_id,
                     c.contribution_policy_version_id)))
    """,
    "award_source_anomalies": """
        SELECT w.id FROM public.compensation_awards w
        LEFT JOIN public.contribution_records c ON c.id=w.contribution_record_id
        LEFT JOIN public.contribution_award_definitions d ON d.id=w.award_definition_id
        LEFT JOIN public.project_compensation_adapter_bindings b ON b.id=w.adapter_binding_id
        WHERE c.id IS NULL OR d.id IS NULL OR b.id IS NULL
           OR ROW(w.project_id,w.contributor_id,w.contribution_policy_version_id)
              IS DISTINCT FROM ROW(c.project_id,c.contributor_id,c.contribution_policy_version_id)
           OR ROW(w.project_id,w.contribution_policy_version_id,c.contribution_type,
                  w.instrument_type,w.unit_code,w.quantity,w.adapter_binding_id)
              IS DISTINCT FROM ROW(d.project_id,d.contribution_policy_version_id,d.contribution_type,
                  d.instrument_type,d.unit_code,d.quantity,d.adapter_binding_id)
           OR ROW(b.project_id,b.instrument_type) IS DISTINCT FROM ROW(w.project_id,w.instrument_type)
    """,
    "award_completeness_anomalies": """
        SELECT c.id FROM public.contribution_records c
        WHERE EXISTS (
            SELECT 1 FROM public.contribution_rules r
            JOIN public.contribution_award_definitions d ON d.contribution_rule_id=r.id
            WHERE r.contribution_policy_version_id=c.contribution_policy_version_id
              AND r.project_id=c.project_id AND r.contribution_type=c.contribution_type
              AND NOT EXISTS (SELECT 1 FROM public.compensation_awards w
                    WHERE w.contribution_record_id=c.id AND w.award_definition_id=d.id))
           OR EXISTS (
            SELECT 1 FROM public.compensation_awards w WHERE w.contribution_record_id=c.id
              AND NOT EXISTS (SELECT 1 FROM public.contribution_rules r
                JOIN public.contribution_award_definitions d ON d.contribution_rule_id=r.id
                WHERE r.contribution_policy_version_id=c.contribution_policy_version_id
                  AND r.project_id=c.project_id AND r.contribution_type=c.contribution_type
                  AND d.id=w.award_definition_id))
    """,
}


class PreflightUnavailable(RuntimeError):
    """A stable non-secret diagnostic failure; no safety conclusion is available."""


@asynccontextmanager
async def read_only_snapshot(engine: AsyncEngine):
    """Use one repeatable read, database-enforced read-only transaction."""
    async with engine.connect() as connection:
        await connection.execution_options(isolation_level="REPEATABLE READ")
        async with connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            yield connection


async def collect_snapshot(connection: AsyncConnection, *, sample_limit: int = 100) -> dict:
    """Inventory one caller-owned read-only snapshot without claiming cutover safety."""
    if type(sample_limit) is not int or not 1 <= sample_limit <= 100:
        raise ValueError("sample_limit must be an integer from 1 to 100")
    if await connection.scalar(text("SHOW transaction_read_only")) != "on":
        raise PreflightUnavailable("read_only_snapshot_required")
    if await connection.scalar(text("SHOW transaction_isolation")) != "repeatable read":
        raise PreflightUnavailable("repeatable_read_snapshot_required")
    versions = (
        await connection.scalars(text("SELECT version_num FROM public.alembic_version"))
    ).all()
    if versions != [SUPPORTED_REVISION]:
        raise PreflightUnavailable("unsupported_schema_revision")
    marker = await connection.scalar(
        text("""
        SELECT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='contribution_policy_versions'
              AND column_name='reward_model_version')
    """)
    )
    if marker:
        raise PreflightUnavailable("unexpected_reward_schema_at_baseline")
    categories = {}
    for name, query in {**INVENTORIES, **BLOCKERS}.items():
        row = (
            (
                await connection.execute(
                    text(f"""
            WITH facts AS MATERIALIZED ({query})
            SELECT (SELECT count(*) FROM facts) AS total_count,
              ARRAY(SELECT id::text FROM facts ORDER BY id LIMIT :sample_limit) AS sample_ids
        """),
                    {"sample_limit": sample_limit},
                )
            )
            .mappings()
            .one()
        )
        total = row["total_count"]
        categories[name] = {
            "total_count": total,
            "sample_ids": list(row["sample_ids"]),
            "truncated": total > sample_limit,
            "blocks_cutover": name in BLOCKERS and total > 0,
        }
    # These exact names are reserved for the forthcoming compensation owner.
    # Absence is explicit; it is not proof that a future financial store is empty.
    optional = {}
    for table in ("compensation_fulfillment_roots", "compensation_fulfillment_receipts"):
        present = await connection.scalar(
            text("SELECT to_regclass(:name) IS NOT NULL"), {"name": f"public.{table}"}
        )
        if present:
            raise PreflightUnavailable("unexpected_fulfillment_schema_at_baseline")
        optional[table] = {"present": False}
    observed = await connection.scalar(text("SELECT transaction_timestamp()"))
    return {
        "schema_version": "workstream.reward_preflight.v1",
        "database_revision": versions[0],
        "snapshot_at": observed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "categories": categories,
        "optional_inventory": optional,
        "cutover_blockers_present": any(item["blocks_cutover"] for item in categories.values()),
        "cutover_fence_held": False,
    }


async def reward_preflight(engine: AsyncEngine, *, sample_limit: int = 100) -> dict:
    """Collect a bounded diagnostic from the shared engine, never mutate data."""
    try:
        async with read_only_snapshot(engine) as connection:
            return await collect_snapshot(connection, sample_limit=sample_limit)
    except SQLAlchemyError as exc:
        raise PreflightUnavailable("reward_preflight_unavailable") from exc


async def _run(sample_limit: int) -> dict:
    try:
        return await reward_preflight(get_engine(), sample_limit=sample_limit)
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    """Print bounded JSON; nonzero signals blockers or unavailable evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-limit", type=int, choices=range(1, 101), default=100)
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(_run(args.sample_limit))
    except (PreflightUnavailable, RuntimeError):
        print("reward preflight unavailable; no cutover safety conclusion", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 2 if report["cutover_blockers_present"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
