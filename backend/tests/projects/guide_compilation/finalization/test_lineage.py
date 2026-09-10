"""One-field malformed locked views reach each source and projection guard."""

from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.projects.api import ProjectGuideSetupFinalizationError
from .support import scenario


@pytest.mark.parametrize(
    ("owner", "field", "value"),
    [
        ("guide", "project_id", "foreign"),
        ("guide", "status", "active"),
        ("guide", "version", "v2"),
        ("snapshot", "id", "replaced"),
        ("snapshot", "bundle_hash", "sha256:" + "f" * 64),
        ("setup", "setup_generation", 2),
        ("setup", "source_snapshot_id", "replaced"),
        ("setup", "celery_task_id", str(uuid4())),
        ("setup", "current_step", "running"),
        ("setup", "status", "failed"),
        ("setup", "finished_at", "forged"),
        ("setup", "output_sufficiency_report_id", str(uuid4())),
        ("setup", "output_submission_artifact_policy_id", str(uuid4())),
        ("setup", "output_post_submit_checker_policy_id", str(uuid4())),
        ("setup", "error_code", "error"),
        ("setup", "error_summary", "error"),
        ("setup", "error_artifact_incident_id", str(uuid4())),
        ("setup", "started_at", "forged"),
        ("setup", "post_submit_derivation_summary", {}),
        ("setup", "documents_ready_at", None),
        ("attempt", "status", "compilation_reserved"),
        ("attempt", "persisted_compilation_id", uuid4()),
        ("compilation", "canonical_input_hash", "sha256:" + "f" * 64),
        ("request", "attempt_id", uuid4()),
        ("request", "setup_generation", 2),
        ("request", "project_id", str(uuid4())),
        ("request", "source_snapshot_id", str(uuid4())),
    ],
)
async def test_locked_source_field_drift_denies(owner, field, value):
    case = scenario()
    setattr(getattr(case.view, owner), field, value)
    with pytest.raises(ProjectGuideSetupFinalizationError, match="source_state_unavailable"):
        await case.service.finalize(case.command)
    assert case.auth.events == ["prepare", "close"]
    assert "persist" not in case.repo.calls


@pytest.mark.parametrize(
    "status", ["compilation_invalid_terminal", "compilation_provider_uncertain"]
)
async def test_invalid_terminal_attempt_denies_finalization_without_consumption(status):
    case = scenario()
    # Keep compilation and every projection valid so removing only this guard admits the call.
    case.view.attempt.status = status
    with pytest.raises(ProjectGuideSetupFinalizationError, match="source_state_unavailable"):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


async def test_stale_snapshot_denies_without_consumption():
    case = scenario()
    case.view.snapshot.id = str(uuid4())
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


async def test_stale_setup_generation_denies_without_consumption():
    case = scenario()
    case.view.setup.setup_generation = 2
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


async def test_replaced_compilation_denies_without_consumption():
    case = scenario()
    case.repo.view = replace(case.view, compilation_is_current=False)
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


async def test_unprojectable_result_denies_finalization_without_consumption():
    case = scenario()
    case.view.compilation.canonical_result = {"status": "unsafe"}
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


async def test_blocked_finalization_rejects_policy_projection():
    case = scenario("guide_blocked")
    forged = deepcopy(case.view.operations[0])
    forged.component = "submission_artifact_policy"
    case.repo.view = replace(case.view, operations=(*case.view.operations, forged))
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


async def test_ready_finalization_requires_exact_policy_projection():
    case = scenario()
    case.repo.view = replace(case.view, operations=case.view.operations[:1])
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


async def test_partial_projection_set_denies_finalization_without_consumption():
    case = scenario()
    case.repo.view = replace(case.view, operations=case.view.operations[1:])
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", str(uuid4())),
        ("guide_id", str(uuid4())),
        ("setup_generation", 2),
        ("attempt_id", uuid4()),
        ("compilation_id", uuid4()),
        ("request_operation_id", uuid4()),
        ("provider_idempotency_key", uuid4()),
        ("celery_task_id", str(uuid4())),
        ("source_state_digest", "sha256:" + "f" * 64),
        ("result_hash", "sha256:" + "f" * 64),
        ("component_hash", "sha256:" + "f" * 64),
        ("operation_id", uuid4()),
        ("correlation_id", uuid4()),
        ("result_schema_version", "v2"),
        ("compilation_agent_name", "other"),
        ("compilation_agent_version", "v2"),
    ],
)
async def test_projection_lineage_drift_denies(field, value):
    case = scenario()
    setattr(case.view.operations[1], field, value)
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


@pytest.mark.parametrize("field", ["prior_operation_id", "prior_output_id", "prior_output_digest"])
async def test_policy_projection_without_exact_sufficiency_predecessor_denies(field):
    case = scenario()
    setattr(
        case.view.operations[1],
        field,
        "sha256:" + "f" * 64 if field.endswith("digest") else uuid4(),
    )
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


@pytest.mark.parametrize("index", [0, 1])
async def test_projection_output_identity_mismatch_denies(index):
    case = scenario()
    case.view.operations[index].output_id = uuid4()
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events


@pytest.mark.parametrize("index", [0, 1])
async def test_projection_output_digest_mismatch_denies(index):
    case = scenario()
    case.view.operations[index].output_digest = "sha256:" + "f" * 64
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert "consume" not in case.auth.events
