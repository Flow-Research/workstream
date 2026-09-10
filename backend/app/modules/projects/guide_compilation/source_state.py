"""The shared setup shape admitted before inference and deterministic projection."""

from app.modules.projects.models import ProjectSetupRun


def is_compilation_source_setup(setup: ProjectSetupRun, expected_task: str) -> bool:
    """Require untouched outputs and committed original-document readiness."""
    return (
        setup.status == "queued"
        and setup.current_step == "queued"
        and setup.celery_task_id == expected_task
        and setup.documents_ready_at is not None
        and all(
            getattr(setup, field) is None
            for field in (
                "error_code",
                "error_artifact_incident_id",
                "error_summary",
                "post_submit_derivation_summary",
                "started_at",
                "finished_at",
                "output_sufficiency_report_id",
                "output_submission_artifact_policy_id",
                "output_post_submit_checker_policy_id",
            )
        )
    )
