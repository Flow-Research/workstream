"""Registry-constant corrections identify values without echoing private data."""

import copy
import json
from types import SimpleNamespace

import pytest

from app.adapters.project_agents.compilation_draft import contextual_output_issues
from app.core.identifiers import new_record_id
from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    validate_post_submission_bindings,
)
from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
    ExternalCheckerSchema,
    external_checker_json_hash,
)
from tests.checkers.external.support import capability_projection, registry_entry
from tests.projects.guide_compilation.helpers import generated_result


def _entry(check, profile_id, digest):
    base = registry_entry("post_submit")
    configuration = {
        "check": check,
        "model_profile_id": profile_id,
        "model_profile_version": 1,
        "model_profile_digest": digest,
    }
    branch = {
        "type": "object",
        "properties": {name: {"const": value} for name, value in configuration.items()},
        "required": list(configuration),
        "additionalProperties": False,
    }
    schema = ExternalCheckerSchema(
        schema_id="example.post.configuration",
        schema_version="v1",
        document={"oneOf": [branch]},
        schema_sha256=external_checker_json_hash({"oneOf": [branch]}),
    )
    values = {name: base.model_dump()[name] for name in ExternalCheckerRegistrySpec.model_fields}
    spec = ExternalCheckerRegistrySpec.model_validate(
        values | {"capability_id": f"example.{check}", "configuration_schema": schema}
    )
    entry = ExternalCheckerRegistryEntry.model_validate(
        base.model_dump() | spec.model_dump() | {"entry_digest": spec.spec_digest}
    )
    return entry, configuration


@pytest.fixture
def configured_proposal():
    entries, configurations = zip(
        _entry("brief", str(new_record_id()), "sha256:" + "a" * 64),
        _entry("accuracy", str(new_record_id()), "sha256:" + "b" * 64),
    )
    projection = capability_projection(*entries)
    body = generated_result().model_dump(mode="json")
    requirement = body["requirements"][0]
    body["requirements"] = [
        requirement
        | {
            "requirement_id": check,
            "disposition": "supported_post_submit",
            "platform_coverage": None,
        }
        for check in ("brief", "accuracy")
    ]
    body["post_submit_bindings"] = [
        {
            "requirement_id": check,
            "capability_id": entry.capability_id,
            "capability_version": entry.capability_version,
            "stage": "post_submit",
            "parameters": [{"name": name, "value": value} for name, value in configuration.items()],
        }
        for check, entry, configuration in zip(("brief", "accuracy"), entries, configurations)
    ]
    result = ProjectGuideCompilationResult.model_validate(body)
    assert validate_post_submission_bindings(result, projection) == {"brief", "accuracy"}
    return body, projection


@pytest.mark.parametrize("fault", ["profile_id", "profile_digest", "both"])
def test_registry_const_substitutions_report_parameter_value_paths(configured_proposal, fault):
    body, projection = configured_proposal
    changed = copy.deepcopy(body)
    expected = []
    if fault in {"profile_id", "both"}:
        changed["post_submit_bindings"][0]["parameters"][1]["value"] = body["post_submit_bindings"][
            1
        ]["parameters"][1]["value"]
        expected.append(
            {"path": ["post_submit_bindings", 0, "parameters", 1, "value"], "code": "schema_const"}
        )
    if fault in {"profile_digest", "both"}:
        changed["post_submit_bindings"][1]["parameters"][3]["value"] = (
            "sha256:" + "b" * 32 + "private-candidate-value"
        )
        expected.append(
            {"path": ["post_submit_bindings", 1, "parameters", 3, "value"], "code": "schema_const"}
        )
    result = ProjectGuideCompilationResult.model_validate(changed)
    with pytest.raises(ExternalCheckerContractError) as caught:
        validate_post_submission_bindings(result, projection)
    issues = contextual_output_issues(
        caught.value, context=SimpleNamespace(checker_capabilities=projection), result=result
    )
    assert issues == expected
    encoded = json.dumps(issues)
    for binding in changed["post_submit_bindings"]:
        for parameter in binding["parameters"]:
            if parameter["name"] in {"model_profile_id", "model_profile_digest"}:
                assert str(parameter["value"]) not in encoded
    assert "private-candidate-value" not in encoded


def test_untrusted_exception_text_cannot_manufacture_configuration_diagnostics(configured_proposal):
    from jsonschema.exceptions import ValidationError as SchemaValidationError

    body, projection = configured_proposal
    error = ExternalCheckerContractError("private-registry-message")
    error.__cause__ = SchemaValidationError("private-rejected-value", validator="const")
    assert contextual_output_issues(
        error,
        context=SimpleNamespace(checker_capabilities=projection),
        result=body,
    ) == [{"path": [], "code": "context_constraint"}]


def test_configuration_diagnostics_stop_at_twenty_positions(configured_proposal):
    body, projection = configured_proposal
    changed = copy.deepcopy(body)
    requirement = changed["requirements"][0]
    binding = changed["post_submit_bindings"][0]
    binding["parameters"][1]["value"] = str(new_record_id())
    changed["requirements"] = [requirement | {"requirement_id": f"check_{i}"} for i in range(25)]
    changed["post_submit_bindings"] = [
        binding | {"requirement_id": f"check_{i}"} for i in range(25)
    ]
    result = ProjectGuideCompilationResult.model_validate(changed)
    with pytest.raises(ExternalCheckerContractError) as caught:
        validate_post_submission_bindings(result, projection)
    assert contextual_output_issues(
        caught.value, context=SimpleNamespace(checker_capabilities=projection), result=result
    ) == [
        {"path": ["post_submit_bindings", i, "parameters", 1, "value"], "code": "schema_const"}
        for i in range(20)
    ]


def test_ambiguous_schema_branches_keep_generic_closed_diagnostics(configured_proposal):
    body, projection = configured_proposal
    entries = [d.registry_entry for d in projection.definitions if d.selectable]
    entry = next(e for e in entries if e.capability_id == "example.brief")
    document = copy.deepcopy(entry.configuration_schema.document)
    other = copy.deepcopy(document["oneOf"][0])
    other["properties"]["model_profile_version"]["const"] = 2
    document["oneOf"].append(other)
    schema = ExternalCheckerSchema(
        schema_id=entry.configuration_schema.schema_id,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    values = {name: entry.model_dump()[name] for name in ExternalCheckerRegistrySpec.model_fields}
    spec = ExternalCheckerRegistrySpec.model_validate(values | {"configuration_schema": schema})
    replacement = ExternalCheckerRegistryEntry.model_validate(
        entry.model_dump() | spec.model_dump() | {"entry_digest": spec.spec_digest}
    )
    projection = capability_projection(
        *(replacement if e.capability_id == entry.capability_id else e for e in entries)
    )
    changed = copy.deepcopy(body)
    changed["post_submit_bindings"][0]["parameters"][3]["value"] = "private-candidate-value"
    result = ProjectGuideCompilationResult.model_validate(changed)
    with pytest.raises(ExternalCheckerContractError) as caught:
        validate_post_submission_bindings(result, projection)
    assert contextual_output_issues(
        caught.value, context=SimpleNamespace(checker_capabilities=projection), result=result
    ) == [{"path": [], "code": "context_constraint"}]


def _deadline_proposal(configured_proposal, *, duration=31, deadline_ms=30_000):
    from tests.projects.guide_compilation.helpers import valid_specification

    original, projection = configured_proposal
    body = copy.deepcopy(original)
    body.pop("setup_notes", None)
    for index, requirement in enumerate(body["requirements"]):
        specification = valid_specification().model_dump(mode="json")
        specification.update(
            execution_mode="background", maximum_duration_seconds=duration if index == 0 else 10
        )
        requirement["check_specification"] = specification
    entries = [d.registry_entry for d in projection.definitions if d.selectable]
    entry = next(e for e in entries if e.capability_id == "example.brief")
    values = {name: entry.model_dump()[name] for name in ExternalCheckerRegistrySpec.model_fields}
    values["resources"] = entry.resources.model_dump() | {"deadline_ms": deadline_ms}
    spec = ExternalCheckerRegistrySpec.model_validate(values)
    replacement = ExternalCheckerRegistryEntry.model_validate(
        entry.model_dump() | spec.model_dump() | {"entry_digest": spec.spec_digest}
    )
    projection = capability_projection(
        *(replacement if e.capability_id == entry.capability_id else e for e in entries)
    )
    return body, SimpleNamespace(
        checker_capabilities=projection, runtime_configuration=SimpleNamespace(uses_inference=True)
    )


def _deadline_issue(index=0, deadline_ms=30_000):
    return {
        "path": ["requirements", index, "check_specification", "maximum_duration_seconds"],
        "code": "checker_deadline",
        "checker_deadline_ms": deadline_ms,
    }


def test_configuration_failure_also_reports_independent_selected_deadline(configured_proposal):
    body, context = _deadline_proposal(configured_proposal)
    body["post_submit_bindings"][0]["parameters"][1]["value"] = "private-candidate-value"
    result = ProjectGuideCompilationResult.model_validate(body)
    with pytest.raises(ExternalCheckerContractError) as caught:
        validate_post_submission_bindings(result, context.checker_capabilities)
    issues = contextual_output_issues(caught.value, context=context, result=result)
    assert issues == [
        {"path": ["post_submit_bindings", 0, "parameters", 1, "value"], "code": "schema_const"},
        _deadline_issue(),
    ]
    encoded = json.dumps(issues)
    assert "private-candidate-value" not in encoded
    for binding in body["post_submit_bindings"]:
        for parameter in binding["parameters"]:
            if parameter["name"] in {"model_profile_id", "model_profile_digest"}:
                assert str(parameter["value"]) not in encoded


@pytest.mark.parametrize(
    ("duration", "deadline_ms", "exceeds"),
    [(30, 30_000, False), (30, 30_001, False), (31, 30_999, True), (31, 31_000, False)],
)
def test_deadline_diagnostic_matches_exact_owner_millisecond_boundary(
    configured_proposal, duration, deadline_ms, exceeds
):
    from app.interfaces.project_agents import require_complete_generated_specifications

    body, context = _deadline_proposal(
        configured_proposal, duration=duration, deadline_ms=deadline_ms
    )
    result = ProjectGuideCompilationResult.model_validate(body)
    assert validate_post_submission_bindings(result, context.checker_capabilities) == {
        "brief", "accuracy"
    }
    if exceeds:
        with pytest.raises(ValueError, match="exceeds the checker deadline") as caught:
            require_complete_generated_specifications(context, result)
        error = caught.value
    else:
        require_complete_generated_specifications(context, result)
        error = ValueError("check specification exceeds the checker deadline")
    assert contextual_output_issues(error, context=context, result=result) == (
        [_deadline_issue(deadline_ms=deadline_ms)]
        if exceeds else [{"path": [], "code": "context_constraint"}]
    )


@pytest.mark.parametrize("fault", ["unknown_version", "missing_requirement", "missing_specification", "missing_binding"])
def test_deadline_diagnostic_requires_known_bound_requirement(configured_proposal, fault):
    body, context = _deadline_proposal(configured_proposal)
    if fault == "unknown_version":
        body["post_submit_bindings"][0]["capability_version"] = "unknown"
    elif fault == "missing_requirement":
        body["post_submit_bindings"][0]["requirement_id"] = "unknown"
    elif fault == "missing_specification":
        body["requirements"][0]["check_specification"] = None
    else:
        body["post_submit_bindings"].pop(0)
    result = ProjectGuideCompilationResult.model_validate(body)
    assert contextual_output_issues(
        ValueError("check specification exceeds the checker deadline"), context=context, result=result
    ) == [{"path": [], "code": "context_constraint"}]


def test_independent_configuration_and_deadline_diagnostics_share_twenty_limit(configured_proposal):
    body, context = _deadline_proposal(configured_proposal)
    requirement, binding = body["requirements"][0], body["post_submit_bindings"][0]
    binding["parameters"][1]["value"] = "private-candidate-value"
    body["requirements"] = [requirement | {"requirement_id": f"check_{i}"} for i in range(25)]
    body["post_submit_bindings"] = [
        binding | {"requirement_id": f"check_{i}"} for i in range(25)
    ]
    result = ProjectGuideCompilationResult.model_validate(body)
    with pytest.raises(ExternalCheckerContractError) as caught:
        validate_post_submission_bindings(result, context.checker_capabilities)
    issues = contextual_output_issues(caught.value, context=context, result=result)
    assert issues == [
        issue for index in range(10) for issue in (
            {"path": ["post_submit_bindings", index, "parameters", 1, "value"], "code": "schema_const"},
            _deadline_issue(index),
        )
    ]
    assert "private-candidate-value" not in json.dumps(issues)


def test_arbitrary_exception_does_not_trigger_deadline_metadata(configured_proposal):
    body, context = _deadline_proposal(configured_proposal)
    assert contextual_output_issues(
        ValueError("private-error-text"), context=context, result=body
    ) == [{"path": [], "code": "context_constraint"}]
