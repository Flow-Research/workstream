"""Selected guide requirements must survive real policy compilation at approval."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.interfaces.project_agents import ProjectGuideCompilationResult
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalError
from app.modules.projects.guide_compilation.models import ProjectGuideProposalApproval
from app.modules.projects.guide_compilation.projection_payloads import policy_body
from app.modules.projects.guide_compilation.proposal_approval import _compile_approval
from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs
from tests.projects.guide_compilation.helpers import context, ids, result
from .pg_support import proposal_case, read_package
from .test_postgresql import approve


CASES = [
    ("required_evidence", "policy.evidence.minimum", "checker_log", "evidence_paths", "evidence/required-evidence-001"),
    ("required_artifacts", "policy.file.require", "answer.md", "artifact_paths", "answer.md"),
]


def selected_result(field, capability, value, configured):
    body = result().model_dump(mode="json")
    body["submission_artifact_policy"][field] = [value] if configured else []
    body["requirements"] = [dict(
        requirement_id="required-check", statement="Require the declared submission input.",
        disposition="supported_pre_submit", evidence_refs=body["findings"][0]["evidence_refs"],
    )]
    body["pre_submit_bindings"] = [dict(
        requirement_id="required-check", capability_id=capability,
        capability_version="v1", stage="pre_submit",
    )]
    return ProjectGuideCompilationResult.model_validate(body)


@pytest.mark.parametrize("field,capability,value,config_key,expected", CASES)
@pytest.mark.parametrize("configured", [False, True])
async def test_approval_reconciles_selection_with_real_compiled_configuration(
    monkeypatch, field, capability, value, config_key, expected, configured,
):
    compilation_context = context(ids())
    outcome = selected_result(field, capability, value, configured)

    async def loaded_context(self, session, setup):
        return compilation_context

    monkeypatch.setattr(CompilationRequestInputs, "context_for_setup", loaded_context)
    material = compilation_context.material
    target = SimpleNamespace(
        project_id=material.project_id, guide_id=material.guide_id,
        guide_version=material.guide_version, source_snapshot_id=material.source_snapshot_id,
        source_snapshot_hash=material.source_snapshot_hash, artifact_policy_id=uuid4(),
        digest="sha256:" + "a" * 64,
        pre_catalogue_manifest_hash=compilation_context.pre_submission_capabilities.manifest_sha256,
    )
    locked = SimpleNamespace(result=outcome, view=SimpleNamespace(
        attempt=SimpleNamespace(runtime_configuration=compilation_context.runtime_configuration.model_dump(mode="json")),
        setup=object(), policy=SimpleNamespace(policy_body=policy_body(None, outcome.submission_artifact_policy)),
    ))
    command = SimpleNamespace(target=target, acknowledged_warning_hashes=())
    args = (None, locked, command, uuid4(), None,
            compilation_context.pre_submission_capabilities,
            compilation_context.post_submission_capabilities,
            build_pre_submission_checker_catalogue())
    if not configured:
        with pytest.raises(GuideProposalError) as error:
            await _compile_approval(*args)
        assert error.value.code == "approval_blocked"
    else:
        outputs = await _compile_approval(*args)
        entries = [entry for entry in outputs.plan.entries if entry.definition_id == capability]
        assert len(entries) == 1
        assert entries[0].definition_version == "v1"
        assert entries[0].checker_definition_state == "enabled"
        assert entries[0].configuration.as_dict()[config_key] == [expected]
        assert any(entry.definition_id == "policy.hash.verify" for entry in outputs.plan.entries)


@pytest.mark.parametrize("field,capability,value,config_key,expected", CASES)
@pytest.mark.parametrize("configured", [False, True])
async def test_selected_requirement_is_persisted_or_approval_rejects_without_writes(
    clean_postgres_database, field, capability, value, config_key, expected, configured,
):
    outcome = selected_result(field, capability, value, configured)
    async with proposal_case(clean_postgres_database, outcome=outcome) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        async with factory() as session:
            before_audit = await session.scalar(text("SELECT count(*) FROM audit_events"))
        if not configured:
            with pytest.raises(GuideProposalError) as error:
                await approve(factory, command, actor, grant, payload)
            assert error.value.code == "approval_blocked"
            async with factory() as session:
                for table in ("project_guide_proposal_approvals", "effective_project_submission_artifact_policies",
                              "pre_submit_checker_policies", "submission_policy_mutation_idempotency_records"):
                    assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                assert await session.scalar(text("SELECT count(*) FROM audit_events")) == before_audit
            assert (await read_package(factory, command, actor, grant)).artifact_policy_status == "draft"
        else:
            receipt = await approve(factory, command, actor, grant, payload)
            async with factory() as session:
                operation = await session.scalar(select(ProjectGuideProposalApproval).where(
                    ProjectGuideProposalApproval.operation_id == receipt.operation_id))
                entries = [entry for entry in operation.effective_pre_submit_plan["entries"]
                           if entry["definition_id"] == capability]
                assert len(entries) == 1
                assert entries[0]["configuration"][config_key] == [expected]
                assert operation.receipt_json == receipt.model_dump(mode="json")
            assert await approve(factory, command, actor, grant, payload) == receipt
