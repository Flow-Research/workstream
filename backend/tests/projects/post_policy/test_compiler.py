"""Exact typed array parameters survive approved POST projection without coercion."""

import pytest

from app.interfaces.project_agents import CapabilityParameter
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.external_policy import compile_external_checker_policy_bundle
from app.modules.projects.post_policy.compiler import compile_saved_post_policy
from tests.checkers.external.test_policy import _entry, _proposal, _Registry


async def test_saved_post_policy_matches_json_arrays_and_still_rejects_changed_values():
    """Approval's JSON representation and proposal tuples denote the same exact list."""
    document = {"type": "object", "properties": {"groups": {"type": "array", "items": {"type": "string"}}}}
    schema = ExternalCheckerSchema(
        schema_id="project.groups", schema_version="v1", document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    registry = _Registry((
        _entry("acme.safe_archive", "pre_submit"),
        _entry("acme.quality_review", "post_submit", configuration_schema=schema),
    ))
    proposal = _proposal()
    binding = proposal.post_submit_bindings[0].model_copy(update={
        "parameters": (CapabilityParameter(name="groups", value=("first", "second")),),
    })
    proposal = proposal.model_copy(update={"post_submit_bindings": (binding,)})
    locked = await compile_external_checker_policy_bundle(proposal, registry)
    assert binding.parameters[0].value == ("first", "second")
    assert locked.post_submit.entries[0].configuration == {"groups": ["first", "second"]}
    assert compile_saved_post_policy(result=proposal, policies=locked) == locked.post_submit
    changed = proposal.model_copy(update={"post_submit_bindings": (binding.model_copy(update={
        "parameters": (CapabilityParameter(name="groups", value=("second", "first")),),
    }),)})
    with pytest.raises(ValueError, match="changes a required binding"):
        compile_saved_post_policy(result=changed, policies=locked)
