"""Persist blocked catalogue handoffs and terminalize oversized output without inference replay."""
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
from .test_live_cutover_postgresql import (
    Runtime, _delivery, scripted_document_port as scripted_document_port,
)
from .helpers import runtime_configuration
from .test_capability_growth import growth_report
from .test_compilation_storage_limit import boundary_reports


@pytest.mark.parametrize("oversized", [False, True])
async def test_handoff_persistence_and_terminal_replay(automatic_source, monkeypatch, oversized):
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    if oversized:
        # Runtime rewrites refs to actual originals; keep large sections after that step.
        from .runtime_fixtures import record_scripted_document_access
        from app.interfaces.project_agents import GuideEvidenceRef

        class OversizedRuntime(Runtime):
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
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration())
    first = await worker._coordinator(factory).run(delivery)
    assert first["status"] == ("compilation_invalid_terminal" if oversized else "sufficiency_blocked")
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
            final = (await session.execute(text(
                "select artifact_policy_id, artifact_policy_operation_id, artifact_policy_output_digest "
                "from project_guide_setup_finalizations"
            ))).one()
            assert tuple(final) == (None, None, None)
        await _assert_projection_state(session, setup_id, oversized)
        for table in ("project_guide_compilations", "project_guide_component_projection_operations",
                      "project_guide_setup_finalizations"):
            assert await session.scalar(text(f"select count(*) from {table}")) == (0 if oversized else 1)

    def forbidden(*args):
        pytest.fail("terminal replay constructed a provider runtime")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", forbidden)
    assert await worker._coordinator(factory).run(delivery) == first
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
    """Observe both checker stages and the exact sole sufficiency output before/after replay."""
    for table in ("submission_artifact_policies", "effective_project_submission_artifact_policies",
                  "pre_submit_checker_policies", "checker_policies"):
        assert await session.scalar(text(f"select count(*) from {table}")) == 0
    outputs = (await session.execute(text(
        "select output_sufficiency_report_id, output_submission_artifact_policy_id, "
        "output_post_submit_checker_policy_id from project_setup_runs where id=:id"
    ), {"id": str(setup_id)})).one()
    assert outputs.output_submission_artifact_policy_id is None
    assert outputs.output_post_submit_checker_policy_id is None
    reports = (await session.execute(text("select id from guide_sufficiency_reports"))).scalars().all()
    projections = (await session.execute(text(
        "select component,report_id,policy_id from project_guide_component_projection_operations"
    ))).all()
    if oversized:
        assert reports == [] and projections == []
        assert outputs.output_sufficiency_report_id is None
    else:
        assert reports == [outputs.output_sufficiency_report_id]
        assert projections == [("guide_sufficiency", outputs.output_sufficiency_report_id, None)]
