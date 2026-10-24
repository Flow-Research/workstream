"""Trial privileges require an exact declared POST policy capability."""

import pytest

from app.interfaces.project_agents import CapabilityParameter, CheckSpecification
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding, compile_external_checker_policies,
)
from tests.checkers.external.test_policy import _entry, _proposal, _Registry
from tests.checkers.external.test_trial_profiles import configuration
from tests.projects.guide_compilation.helpers import valid_specification


def _configuration():
    return {key: value for key, value in configuration().items() if key.startswith("trial_")}


def _binding(values, *, phase="post_submit", declared=True):
    document = {"type": "object"}
    if declared:
        document["properties"] = {key: {} for key in _configuration()}
    schema = ExternalCheckerSchema(
        schema_id="trial.configuration", schema_version="v1", document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    return LockedExternalCheckerBinding(
        requirement_id="runtime_evidence", stage=phase,
        registry=_entry("project.runtime_evidence", phase, schema),
        configuration=values, configuration_sha256=external_checker_json_hash(values),
    )


def test_complete_declared_trial_capability_is_locked_only_for_post():
    values = _configuration()
    assert _binding(values).configuration == values
    with pytest.raises(ValueError, match="post-submit"):
        _binding(values, phase="pre_submit")
    with pytest.raises(ValueError, match="does not declare trial"):
        _binding(values, declared=False)


@pytest.mark.parametrize("missing", sorted(_configuration()))
def test_partial_trial_selector_cannot_be_approved(missing):
    values = _configuration()
    values.pop(missing)
    with pytest.raises(ValueError, match="incomplete"):
        _binding(values)


@pytest.mark.parametrize("field,value", [
    ("trial_profile_id", "018F6F49-66B8-7D2A-BF4D-0E2EEAA00001"),
    ("trial_profile_version", True),
    ("trial_projection_digest", "sha256:" + "x" * 64),
    ("trial_unknown", "extra"),
])
def test_invalid_trial_selector_cannot_be_approved(field, value):
    values = _configuration() | {field: value}
    with pytest.raises(ValueError):
        _binding(values)


def test_ordinary_images_do_not_acquire_or_require_trial_privileges():
    assert _binding({}, phase="pre_submit", declared=False).configuration == {}
    assert _binding({}, declared=False).configuration == {}


def trial_specification():
    """Describe actual nested execution separately from the outer checker sandbox."""
    dependencies = [
        {"dependency_id": "checker", "kind": "isolated_execution",
         "provisioning": "current_runner", "purpose": "Isolate the checker image.",
         "unavailable_code": "implementation_unavailable"},
        {"dependency_id": "trial", "kind": "nested_sandbox",
         "provisioning": "trial_proxy", "purpose": "Build and run submitted code in isolation.",
         "unavailable_code": "implementation_unavailable"},
    ]
    return CheckSpecification.model_validate(valid_specification().model_dump(mode="json") | {
        "evaluation_method": "isolated_execution", "execution_mode": "background",
        "runtime_dependencies": dependencies,
        "infrastructure_failures": [{"code": "implementation_unavailable",
                                    "condition": "The approved trial runtime is unavailable."}],
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("declared,selected", [(True, True), (True, False), (False, True)])
async def test_approved_trial_dependency_and_configuration_must_match(declared, selected):
    proposal = _proposal()
    requirement = proposal.requirements[-1].model_copy(update={
        "check_specification": trial_specification() if declared else None,
    })
    values = _configuration() if selected else {}
    binding = proposal.post_submit_bindings[0].model_copy(update={
        "parameters": tuple(CapabilityParameter(name=key, value=value)
                            for key, value in values.items()),
    })
    proposal = proposal.model_copy(update={
        "requirements": (*proposal.requirements[:-1], requirement),
        "post_submit_bindings": (binding,),
    })
    registry = _Registry((
        _entry("acme.safe_archive", "pre_submit"),
        _entry("acme.quality_review", "post_submit", _binding({}).registry.configuration_schema),
    ))
    if declared and selected:
        _, post = await compile_external_checker_policies(proposal, registry)
        assert post.entries[0].configuration == values
    else:
        with pytest.raises(ValueError, match="trial dependency profile"):
            await compile_external_checker_policies(proposal, registry)
