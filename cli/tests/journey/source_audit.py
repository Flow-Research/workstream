"""Read-only isolated-database postconditions for source custody hidden from public DTOs."""

import asyncio
from hashlib import sha256
import os
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.hashing import canonical_json_hash


_COUNTS = {
    "submissions": "SELECT count(*) FROM submissions WHERE task_id = CAST(:task_id AS uuid)",
    "dispatches": "SELECT count(*) FROM submission_dispatches WHERE task_id = CAST(:task_id AS uuid)",
    "checker_runs": "SELECT count(*) FROM checker_runs WHERE task_id = CAST(:task_id AS uuid)",
    "acceptances": "SELECT count(*) FROM final_acceptances WHERE task_id = CAST(:task_id AS uuid)",
    "reviews": "SELECT count(*) FROM reviews WHERE task_id = CAST(:task_id AS uuid)",
    "contributions": "SELECT count(*) FROM contribution_records WHERE task_id = CAST(:task_id AS uuid)",
    "awards": (
        "SELECT count(*) FROM compensation_awards AS award "
        "JOIN contribution_records AS contribution "
        "ON contribution.id = award.contribution_record_id "
        "WHERE contribution.task_id = CAST(:task_id AS uuid)"
    ),
}


async def _audit(
    operation_id: str,
    submission_id: str,
    task_id: str,
    digest: str,
    byte_count: int,
    *,
    accepted: bool,
) -> None:
    url = os.environ["WORKSTREAM_DATABASE_URL"]
    if not urlsplit(url).path.lstrip("/").startswith("workstream_test_"):
        raise RuntimeError("source audit requires the isolated test database")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            rows = (
                (
                    await connection.execute(
                        text("""
                SELECT o.id::text AS operation_id, o.task_id::text AS task_id,
                    o.state, o.finalized_submission_id::text AS submission_id,
                    o.raw_sha256, o.raw_byte_count, o.provider_generation,
                    o.sealed_upload_fence, o.namespace_id, o.namespace_fingerprint,
                    o.provider_profile, o.object_ref, o.accepted_source_sha256,
                    selected.request_json AS selected_request,
                    charge.state AS charge_state, charge.accounted_bytes,
                    admission.source_operation_id::text AS admission_source,
                    admission.consumed_by_submission_id::text AS admission_submission,
                    replica.source_operation_id::text AS replica_source,
                    replica.storage_namespace_id, replica.namespace_fingerprint AS replica_fingerprint,
                    replica.provider_profile AS replica_profile,
                    replica.provider_object_ref, content.sha256 AS content_sha256,
                    content.byte_count AS content_byte_count
                FROM submission_intake_operations AS o
                JOIN submission_source_charges AS charge ON charge.operation_id = o.id
                JOIN selected_pre_submit_runs AS selected ON selected.id = o.selected_pre_submit_run_id
                JOIN submission_bundle_admissions AS admission ON admission.id = o.finalized_admission_id
                JOIN artifact_replicas AS replica ON replica.source_operation_id = o.id
                JOIN artifact_contents AS content ON content.id = replica.content_id
                WHERE o.id = CAST(:operation_id AS uuid)
            """),
                        {"operation_id": operation_id},
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != 1:
                raise AssertionError(
                    "accepted source lacks one complete stored custody graph"
                )
            row = rows[0]
            expected = {
                "operation_id": operation_id,
                "task_id": task_id,
                "state": "finalized",
                "submission_id": submission_id,
                "raw_sha256": digest,
                "raw_byte_count": byte_count,
                "charge_state": "sealed",
                "accounted_bytes": byte_count,
                "admission_source": operation_id,
                "admission_submission": submission_id,
                "replica_source": operation_id,
                "storage_namespace_id": row["namespace_id"],
                "replica_fingerprint": row["namespace_fingerprint"],
                "replica_profile": row["provider_profile"],
                "provider_object_ref": row["object_ref"],
                "content_sha256": digest,
                "content_byte_count": byte_count,
            }
            for field, value in expected.items():
                if row[field] != value:
                    raise AssertionError(
                        f"accepted source stored {field} differs from public work"
                    )
            if not row["provider_generation"] or row["sealed_upload_fence"] <= 0:
                raise AssertionError(
                    "accepted source lacks an exact provider generation and fence"
                )
            source = row["selected_request"].get("source")
            if not isinstance(source, dict) or not isinstance(
                source.get("location"), dict
            ):
                raise AssertionError(
                    "selected PRE lacks the independently stored source"
                )
            if (
                {
                    "provider_generation": source.get("provider_generation"),
                    "sealed_upload_fence": source.get("sealed_upload_fence"),
                    "raw_sha256": source.get("raw_sha256"),
                    "raw_byte_count": source.get("raw_byte_count"),
                }
                != {
                    "provider_generation": row["provider_generation"],
                    "sealed_upload_fence": row["sealed_upload_fence"],
                    "raw_sha256": digest,
                    "raw_byte_count": byte_count,
                }
                or source["location"]
                != {
                    "operation_id": operation_id,
                    "namespace_id": row["namespace_id"],
                    "namespace_fingerprint": row["namespace_fingerprint"],
                    "provider_profile": row["provider_profile"],
                }
                or row["accepted_source_sha256"]
                != canonical_json_hash(
                    {
                        "schema_version": "workstream.sealed_submission_source.v1",
                        **source,
                    }
                )
            ):
                raise AssertionError(
                    "selected PRE source generation or fence differs from accepted custody"
                )
            counts = {
                name: await connection.scalar(text(query), {"task_id": task_id})
                for name, query in _COUNTS.items()
            }
            expected_counts = {
                "submissions": 1,
                "dispatches": 1,
                "checker_runs": 1,
                "acceptances": int(accepted),
                "reviews": 0,
                "contributions": int(accepted),
                "awards": 0,
            }
            if counts != expected_counts:
                raise AssertionError(
                    "isolated task effect counts differ from the governed outcome"
                )
    finally:
        await engine.dispose()


def audit_accepted_source(
    operation_id: str,
    submission_id: str,
    task_id: str,
    archive: Path,
    *,
    accepted: bool,
) -> None:
    """Observe exact source graph and downstream counts without changing state."""
    data = archive.read_bytes()
    asyncio.run(
        _audit(
            operation_id,
            submission_id,
            task_id,
            "sha256:" + sha256(data).hexdigest(),
            len(data),
            accepted=accepted,
        )
    )
