"""Project intake rules over actual prepared ZIP bytes, not caller packet manifests.

AUTH is an explicit port double here; canonical authority has separate tests.
This module proves materialization outcomes, not durable admission or Submission creation.
"""

from dataclasses import replace

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.submission_materialization import PreparedBundleMaterializationService
from app.modules.checkers.compiler import compile_effective_project_submission_artifact_policy
from app.modules.checkers.effective_plan import compile_effective_pre_submission_execution_plan
from app.modules.checkers.pre_submit_execution import PreSubmissionResultStatus
from tests.test_default_pre_submit_execution import (
    _AllowAuthority, _CheckerExecution, _effective_policy, _request,
)


@pytest.mark.parametrize(("case", "failed_definition"), [
    ("complete", None),
    ("missing_file", "policy.file.require"),
    ("project_evidence", "policy.evidence.minimum"),
    ("project_attestation", "policy.attestation.require"),
    ("project_forbidden_file", "policy.artifact.forbid"),
])
async def test_effective_project_rules_control_exact_prepared_contents(
    tmp_path, case, failed_definition,
):
    request, inspector, manager, preparation, catalogue = await _request(
        tmp_path,
        path="unexpected.txt" if case == "missing_file" else "task.toml",
        extra_path="project-private.data" if case == "project_forbidden_file" else None,
    )
    try:
        policy = _effective_policy()
        if case == "project_evidence":
            addition = {"key": "build_log", "required": True}
            policy["project_policy"] = {"required_evidence": [addition]}
            policy["required_evidence"] = [*policy["required_evidence"], addition]
        elif case == "project_attestation":
            policy["project_policy"] = {"attestation_terms": ["project_confidentiality_confirmed"]}
            policy["attestation_terms"] = [*policy["attestation_terms"], "project_confidentiality_confirmed"]
        elif case == "project_forbidden_file":
            addition = {"pattern": "project-private.data"}
            policy["project_policy"] = {"forbidden_artifacts": [addition]}
            policy["forbidden_artifacts"] = [*policy["forbidden_artifacts"], addition]
        policy_hash = canonical_json_hash(policy)
        compiled = compile_effective_project_submission_artifact_policy(policy, policy_hash)
        plan = compile_effective_pre_submission_execution_plan(
            lineage=replace(
                request.effective_plan.lineage, effective_policy_hash=policy_hash,
                pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
            ),
            effective_policy=policy, compiled_bundle=compiled.compiled_bundle, catalogue=catalogue,
        )
        result = await PreparedBundleMaterializationService(
            authorization=_AllowAuthority(), preparation=preparation,
            checker_execution=_CheckerExecution(inspector, catalogue), storage_scheme="s3",
        ).materialize_prepared_bundle(replace(request, effective_plan=plan))
        assert result.eligible is (failed_definition is None)
        failed = [entry.definition_id for entry in result.entries
                  if entry.checker_execution_status == PreSubmissionResultStatus.FAILED.value]
        assert failed == ([] if failed_definition is None else [failed_definition])
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    finally:
        await request.prepared_artifact.close()
        manager.close()
