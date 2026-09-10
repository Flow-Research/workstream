"""Fresh, passive rows for sufficiency service composition (not database proof)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from app.modules.projects.models import GuideSufficiencyReport
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

PROJECT, GUIDE, SNAPSHOT, SETUP, REPORT, ACTOR, LINK, GRANT, KEY = (
    UUID(int=value) for value in range(1, 10)
)
NOW = datetime(2026, 1, 1, tzinfo=UTC)
SNAPSHOT_HASH = "sha256:" + "a" * 64
STALE_HASH = "sha256:" + "b" * 64
RESOURCE_HASH = "sha256:" + "c" * 64


def report_row():
    return GuideSufficiencyReport(
        id=str(REPORT),
        project_id=str(PROJECT),
        guide_id=str(GUIDE),
        guide_version="v1",
        source_snapshot_id=str(SNAPSHOT),
        source_snapshot_hash=SNAPSHOT_HASH,
        status="passed_with_warnings",
        findings=[{"severity": "warning", "code": "examples", "message": "Add examples."}],
        summary="Assessment",
        created_by=str(ACTOR),
        created_at=NOW,
    )


def setup_row():
    return SimpleNamespace(
        id=str(SETUP),
        project_id=str(PROJECT),
        guide_id=str(GUIDE),
        guide_version="v1",
        source_snapshot_id=str(SNAPSHOT),
        source_snapshot_hash=SNAPSHOT_HASH,
        setup_generation=1,
        celery_task_id=project_guide_compilation_task_id(str(SETUP), 1),
        continuation_verification_job_id=None,
        continuation_started_at=None,
        status="enqueue_failed",
        current_step="guide_sufficiency",
        output_sufficiency_report_id=None,
        output_submission_artifact_policy_id=None,
        output_post_submit_checker_policy_id=None,
        post_submit_derivation_summary=None,
        error_code="queue_error",
        error_artifact_incident_id=None,
        error_summary="Queue failed",
        created_by=str(ACTOR),
        created_at=NOW,
        updated_at=NOW,
        started_at=None,
        finished_at=None,
    )
