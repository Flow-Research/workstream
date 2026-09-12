"""Inject detached corrupt reads without rewriting immutable approval evidence."""

from copy import deepcopy
from types import SimpleNamespace

from sqlalchemy import inspect

from app.core.hashing import canonical_json_hash
from app.db import session as db_session
from app.modules.projects.models import EffectiveProjectSubmissionArtifactPolicy, PreSubmitCheckerPolicy
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService


def _detached(row):
    return SimpleNamespace(**{
        column.key: deepcopy(getattr(row, column.key))
        for column in inspect(type(row)).columns
    })


async def corrupt_locked_policy_reads(monkeypatch, task_id, mutation):
    """Exercise consumer validation after valid canonical setup; never persist faults.

    Hash-consistent faults update the detached task's matching pointers too, so
    digest checks cannot mask malformed-policy validation. Stale-bundle faults
    retain the locked hash and exercise that independent integrity boundary.
    """
    async with db_session.get_session_factory()() as session:
        stored_task = await session.get(WorkstreamTask, task_id)
        assert stored_task is not None
        await TaskService(session)._load_locked_task_context(stored_task)
        task = _detached(stored_task)
        effective = _detached(await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            task.locked_effective_project_submission_artifact_policy_id,
        ))
        pre = _detached(await session.get(
            PreSubmitCheckerPolicy, task.locked_pre_submit_checker_policy_id,
        ))
    if mutation == "schema":
        effective.effective_policy["schema_version"] = ["not", "a", "string"]
    elif mutation == "evidence":
        effective.effective_policy["required_evidence"] = ["bad-shape"]
    elif mutation == "packaging":
        effective.effective_policy["packaging"] = {
            "package_required": "yes", "allowed_package_formats": "zip",
        }
    elif mutation == "bundle":
        pre.compiled_bundle["rules"] = [
            rule for rule in pre.compiled_bundle["rules"] if rule["primitive"] != "require_file"
        ]
    elif mutation == "stale_effective":
        effective.effective_policy["required_evidence"] = []
    elif mutation == "checker_names":
        pre.checker_names = ["unknown_project_checker"]
    elif mutation == "stale_bundle":
        pre.compiled_bundle["tampered"] = True
    else:
        raise ValueError("unknown policy read fault")
    if mutation in {"schema", "evidence", "packaging", "bundle"}:
        effective.effective_policy_hash = canonical_json_hash(effective.effective_policy)
        pre.effective_policy_hash = effective.effective_policy_hash
        pre.compiled_bundle["effective_policy_hash"] = effective.effective_policy_hash
        pre.compiled_bundle_hash = canonical_json_hash(pre.compiled_bundle)
        task.locked_effective_project_submission_artifact_policy_hash = effective.effective_policy_hash
        task.locked_pre_submit_checker_bundle_hash = pre.compiled_bundle_hash

    def replace_read(owner, name, row):
        original = getattr(owner, name)

        async def read(repository, identifier, *args, **kwargs):
            if identifier == row.id:
                return row
            return await original(repository, identifier, *args, **kwargs)

        monkeypatch.setattr(owner, name, read)

    replace_read(ProjectRepository, "get_effective_submission_artifact_policy_by_id", effective)
    replace_read(ProjectRepository, "get_pre_submit_checker_policy", pre)
    if mutation in {"schema", "evidence", "packaging", "bundle"}:
        replace_read(TaskRepository, "get_task", task)
