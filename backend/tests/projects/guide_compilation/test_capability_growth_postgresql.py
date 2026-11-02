"""Persist external-capability gap handoffs and terminalize oversized output."""
import json

import pytest
from sqlalchemy import JSON, bindparam, text

from app.interfaces.project_agents import (
    ProjectGuideCompilationResult, project_guide_compilation_result_storage_bytes,
)
from tests.committed_guide_fixtures import create_committed_document_fixture
from tests.projects.client_fixtures import (
    project_client as project_client, project_database_env as project_database_env,
)
from .test_automatic_request import automatic_source as automatic_source
from .runtime_fixtures import (
    ScriptedGuideRuntime,
    scripted_model_profile,  # noqa: F401 - registered pytest fixture
    scripted_runtime_configuration,
)
from .test_live_cutover_postgresql import (
    _delivery,
    scripted_document_port as scripted_document_port,
)
from .test_capability_growth import growth_report
from .test_compilation_storage_limit import boundary_reports


@pytest.mark.parametrize("oversized", [False, True])
@pytest.mark.usefixtures("scripted_model_profile")
async def test_handoff_persistence_and_terminal_replay(automatic_source, monkeypatch, oversized):
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    from tests.checkers.external.support import registry_spec
    from tests.projects.guide_activation.source_fixtures import (
        _register_external_checker_fixture,
    )

    await _register_external_checker_fixture(factory, registry_spec("pre_submit"))
    await _register_external_checker_fixture(factory, registry_spec("post_submit"))
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    if oversized:
        # Runtime rewrites refs to actual originals; keep large sections after that step.
        from .runtime_fixtures import record_scripted_document_access
        from app.interfaces.project_agents import GuideEvidenceRef

        class OversizedRuntime(ScriptedGuideRuntime):
            async def compile_project_guide(self, context, capabilities):
                self.calls += 1
                await record_scripted_document_access(context, capabilities)
                document = context.material.documents[0]
                ref = GuideEvidenceRef(source_item_id=document.source_item_id,
                    document_version_id=document.ingest_id, sha256=document.sha256, section="文" * 200)
                report = boundary_reports()[1]
                return report.model_copy(update={
                    field: tuple(item.model_copy(update={"evidence_refs": (ref, ref)})
                                 for item in getattr(report, field))
                    for field in ("findings", "requirements", "capability_suggestions")
                })
        runtime = OversizedRuntime()
    else:
        runtime.outcome = growth_report()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", scripted_runtime_configuration)
    first = await (await worker._coordinator(factory)).run(delivery)
    assert first["status"] == (
        "compilation_invalid_terminal" if oversized else "policy_draft_ready"
    )
    if oversized:
        assert first["error_code"] == "schema_invalid"
    assert runtime.calls == 1
    async with factory() as session:
        before = await session.scalar(text("select count(*) from audit_events"))
        row = (await session.execute(text(
            "select canonical_result, octet_length(canonical_result::text) as stored_bytes "
            "from project_guide_compilation_attempts"
        ))).one()
        if oversized:
            assert row.canonical_result is None
        else:
            parsed = ProjectGuideCompilationResult.model_validate(row.canonical_result)
            assert row.stored_bytes == project_guide_compilation_result_storage_bytes(parsed)
            assert len(parsed.pre_submit_bindings) == len(parsed.post_submit_bindings) == 1
            assert {s.stage.value for s in parsed.capability_suggestions} == {"pre_submit", "post_submit"}
            assert {s.requirement_id for s in parsed.capability_suggestions} == {"gap_pre_submit", "gap_post_submit"}
        await _assert_projection_state(session, setup_id, oversized)
        expected_counts = {
            "project_guide_compilations": 1,
            "project_guide_component_projection_operations": 2,
            "project_guide_setup_finalizations": 1,
        }
        for table, expected in expected_counts.items():
            assert await session.scalar(text(f"select count(*) from {table}")) == (
                0 if oversized else expected
            )

    def forbidden_runtime(_configuration):
        pytest.fail("terminal replay constructed a provider runtime")

    def forbidden_configuration(_settings, *, adapter_profile_builder):
        pytest.fail("terminal replay constructed a provider runtime")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden_runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", forbidden_configuration
    )
    assert await (await worker._coordinator(factory)).run(delivery) == first
    assert runtime.calls == 1
    async with factory() as session:
        assert await session.scalar(text("select count(*) from audit_events")) == before
        await _assert_projection_state(session, setup_id, oversized)


async def test_driver_json_byte_measure_matches_postgresql(automatic_source):
    factory, *_ = automatic_source
    below, above = boundary_reports()
    payloads = [below.model_dump(mode="json"), above.model_dump(mode="json"),
                {"parameters": [{"value": 1e-9}, {"value": 1000}, {"value": "文"}]}]
    async with factory() as session:
        statement = text("select octet_length(cast(:payload as json)::text)").bindparams(bindparam("payload", type_=JSON))
        for payload in payloads:
            actual = await session.scalar(statement, {"payload": payload})
            assert actual == len(json.dumps(payload, ensure_ascii=True, allow_nan=False).encode("utf-8"))


async def _assert_projection_state(session, setup_id, oversized):
    """Observe the current draft handoff or exact terminal absence before/after replay."""
    policy_ids = (
        await session.execute(text("select id from submission_artifact_policies order by id"))
    ).scalars().all()
    assert len(policy_ids) == (0 if oversized else 1)
    for table in (
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
        "checker_policies",
    ):
        assert await session.scalar(text(f"select count(*) from {table}")) == 0
    outputs = (await session.execute(text(
        "select status,current_step,output_sufficiency_report_id, "
        "output_submission_artifact_policy_id,output_post_submit_checker_policy_id "
        "from project_setup_runs where id=:id"
    ), {"id": str(setup_id)})).one()
    assert outputs.output_post_submit_checker_policy_id is None
    reports = (await session.execute(text("select id from guide_sufficiency_reports"))).scalars().all()
    projections = (await session.execute(text(
        "select operation_id,component,report_id,policy_id "
        "from project_guide_component_projection_operations order by component"
    ))).all()
    if oversized:
        assert (outputs.status, outputs.current_step) == ("queued", "queued")
        assert reports == [] and projections == []
        assert outputs.output_sufficiency_report_id is None
        assert outputs.output_submission_artifact_policy_id is None
    else:
        assert (outputs.status, outputs.current_step) == (
            "policy_draft_ready",
            "submission_artifact_policy_derivation",
        )
        assert reports == [outputs.output_sufficiency_report_id]
        assert policy_ids == [outputs.output_submission_artifact_policy_id]
        assert [tuple(row)[1:] for row in projections] == [
            ("guide_sufficiency", outputs.output_sufficiency_report_id, None),
            ("submission_artifact_policy", None, outputs.output_submission_artifact_policy_id),
        ]
        final = (await session.execute(text(
            "select sufficiency_report_id,artifact_policy_id,sufficiency_operation_id,"
            "artifact_policy_operation_id,sufficiency_output_digest,"
            "artifact_policy_output_digest from project_guide_setup_finalizations"
        ))).one()
        assert tuple(final[:4]) == (
            outputs.output_sufficiency_report_id,
            outputs.output_submission_artifact_policy_id,
            projections[0].operation_id,
            projections[1].operation_id,
        )
        assert final.sufficiency_output_digest.startswith("sha256:")
        assert final.artifact_policy_output_digest.startswith("sha256:")


@pytest.mark.usefixtures("scripted_model_profile")
async def test_inflight_metered_setup_read_is_unresolved_without_claiming_failure(
    automatic_source, monkeypatch, project_client
):
    """The committed dispatch fence alone does not establish a failed compilation."""
    import asyncio

    from app.core.config import get_settings
    from app.workers import project_setup as worker
    from tests.projects.client_fixtures import auth_headers

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    factory, _actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    entered, release = asyncio.Event(), asyncio.Event()
    compile_guide = runtime.compile_project_guide

    async def paused_compilation(context, capabilities):
        entered.set()
        await release.wait()
        return await compile_guide(context, capabilities)

    monkeypatch.setattr(runtime, "compile_project_guide", paused_compilation)
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", scripted_runtime_configuration
    )
    coordinator = await worker._coordinator(factory)
    task = asyncio.create_task(coordinator.run(delivery))
    path = (
        f"/api/v1/projects/{delivery.project_id}/guides/{delivery.guide_id}/setup-runs/latest"
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=20)
        async with factory() as session:
            before = await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(setup_id)},
            )
        assert before["status"] == "queued" and before["error_code"] is None
        first = await project_client.get(path, headers=auth_headers())
        replay = await project_client.get(path, headers=auth_headers())
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json()
        body = first.json()
        assert body["status"] == "provider_outcome_unresolved"
        assert body["current_step"] == "guide_compilation"
        assert body["started_at"] is not None and body["finished_at"] is None
        assert body["error_code"] is None and body["error_summary"] is None
        assert not task.done()
        async with factory() as session:
            assert await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(setup_id)},
            ) == before
        release.set()
        outcome = await asyncio.wait_for(task, timeout=30)
        assert outcome["status"] == "policy_draft_ready"
        assert runtime.calls == 1
        assert await coordinator.run(delivery) == outcome
        assert runtime.calls == 1
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
