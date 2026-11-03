"""Trial privileges require an exact declared POST policy capability."""

import pytest

from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding, compile_external_checker_policies,
)
from tests.checkers.external.test_policy import _entry, _attachment, _request, _Registry
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


@pytest.mark.asyncio
async def test_human_post_attachment_locks_declared_trial_configuration():
    values = _configuration()
    entry = _entry(
        "project.runtime_evidence", "post_submit", _binding({}).registry.configuration_schema,
    )
    _, post = await compile_external_checker_policies(
        _request(post=(_attachment(entry, "runtime_evidence", values),)),
        _Registry((entry,)),
    )
    assert post.entries[0].configuration == values
