"""Invalid drafts are rejected; bounded corrections must pass source review."""

import copy
import json
from types import SimpleNamespace

import httpx2
import pytest

from app.adapters.project_agents.compilation_draft import (
    CompilationDraftParser,
    generated_compilation_schema,
)
from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    project_guide_compilation_prompt_bytes,
)
from tests.projects.guide_compilation.helpers import (
    context,
    generated_result,
    ids,
    runtime_configuration,
)
from tests.test_agent_runtime import (
    _compile,
    _open_prompt_documents,
    _provider_payload,
    _provider_specification,
    _chat_text,
    _chat_tool_call,
    _patch_openai_transport,
    _TestModelSession,
    model_credentials,  # noqa: F401
)


@pytest.fixture
def parser():
    """Use the exact strict schema the SDK exposes to both provider phases."""
    from agents import AgentOutputSchema

    return CompilationDraftParser(
        generated_compilation_schema(
            AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
        ),
        100_000,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "malformed",
        "duplicate",
        "nan",
        "infinity",
        "deep",
        "surrogate",
        "oversized",
        "missing",
        "extra",
        "wrong_type",
        "wrong_enum",
        "overlong",
    ],
)
def test_draft_structure_rejection_is_bounded_and_private(parser, fault):
    payload = _provider_payload()
    if fault == "missing":
        del payload["status"]
    elif fault == "extra":
        payload["untrusted-private-field"] = "private-value"
    elif fault == "wrong_type":
        payload["requirements"] = "not a list"
    elif fault == "wrong_enum":
        payload["status"] = "not a status"
    elif fault == "overlong":
        payload["findings"][0]["message"] = "x" * 1001
    elif fault == "surrogate":
        payload["findings"][0]["message"] = "\ud800"
    elif fault in {"nan", "infinity"}:
        payload["submission_artifact_policy"]["maximum_file_size_bytes"] = float(fault)
    raw = json.dumps(payload)
    if fault == "malformed":
        raw = '{"private-marker":'
    elif fault == "duplicate":
        raw = '{"status":"draft_ready",' + raw[1:]
    elif fault == "deep":
        raw = "[" * 1100 + "0" + "]" * 1100
    elif fault == "oversized":
        raw = " " * 100_001 + raw
    assert parser.parse(raw) is None
    if fault == "overlong":
        assert parser.issues == [
            {"path": ["findings", 0, "message"], "code": "schema_maxLength"}
        ]
    elif fault == "surrogate":
        assert parser.issues == [{"path": [], "code": "invalid_json"}]


@pytest.mark.parametrize(
    "patch",
    [
        {"$ref": "https://example.invalid/schema"},
        {"$dynamicRef": "file:///private/schema"},
        {"$id": "https://example.invalid/base"},
    ],
)
def test_draft_schema_never_resolves_external_resources(patch):
    with pytest.raises(ValueError, match="only local references"):
        CompilationDraftParser({"type": "object", "properties": {"field": patch}}, 1000)


def _invalid_canonical_payload(fault):
    """Reproduce live path/pairing defects and unsafe prose without invalid JSON shape."""
    payload = _provider_payload()
    if fault == "path":
        payload["submission_artifact_policy"]["required_artifacts"] = ["environment/"]
    elif fault == "material":
        specification = _provider_specification()
        specification["runtime_dependencies"] = [
            {
                "dependency_id": "prior_material",
                "kind": "task_context",
                "provisioning": "runtime_gap",
                "purpose": "Compare the prior task context.",
                "unavailable_code": "material_unavailable",
            }
        ]
        specification["infrastructure_failures"] = [
            {
                "code": "material_unavailable",
                "condition": "The prior context is unavailable.",
            }
        ]
        payload["requirements"][0]["check_specification"] = specification
    else:
        payload["findings"][0]["message"] = "token=private-draft-marker-7391"
    return payload


def _rejected_semantic_payload(fault):
    """Synthetic versions of the live invariant failures, with no private fixture data."""
    if fault == "unsafe":
        return _invalid_canonical_payload("unsafe")
    payload = _provider_payload()
    if fault == "blocked":
        payload["status"] = "guide_blocked"
        payload["submission_artifact_policy"] = None
    elif fault == "duplicate":
        payload["requirements"].append(copy.deepcopy(payload["requirements"][0]))
    else:
        requirement = payload["requirements"][0]
        requirement["disposition"] = "supported_pre_submit"
        requirement["platform_coverage"] = None
        specification = _provider_specification()
        if fault == "isolated":
            specification.update(evaluation_method="isolated_execution", execution_mode="background")
        elif fault == "availability":
            specification["runtime_dependencies"] = [{
                "dependency_id": "file_inspection",
                "kind": "checker_tool",
                "provisioning": "current_runner",
                "purpose": "Inspect the required file.",
                "unavailable_code": "implementation_unavailable",
            }]
            specification["infrastructure_failures"] = [{
                "code": "implementation_unavailable",
                "condition": "The file checker is unavailable.",
            }]
        requirement["check_specification"] = specification
    return payload


def test_private_text_diagnostic_does_not_relabel_other_invalid_fields(parser):
    """A mixed rejection keeps useful closed causes without exposing either value."""
    payload = _rejected_semantic_payload("availability")
    payload["requirements"][0]["check_specification"]["check_steps"] = [
        "token=private-draft-marker-7391"
    ]
    assert parser.parse(json.dumps(payload)) == payload
    issues = parser.canonical_issues(payload)
    assert parser.unsafe_text is True
    assert issues == [
        {"path": ["requirements", 0, "check_specification", "check_steps"],
         "code": "unsafe_text"},
        {"path": ["requirements", 0, "check_specification", "runtime_dependencies", 0],
         "code": "dependency_availability"},
    ]
    assert "private-draft-marker" not in json.dumps(issues)
    assert parser.canonical_issues(_provider_payload()) == []
    assert parser.unsafe_text is False


@pytest.mark.usefixtures("model_credentials")
@pytest.mark.parametrize("fault", ["path", "material", "unsafe"])
@pytest.mark.parametrize("review", ["corrected", "unchanged", "provider_error"])
async def test_review_can_correct_private_draft_without_relaxing_acceptance(
    monkeypatch,
    caplog,
    parser,
    fault,
    review,
):
    """Only the canonical second result survives; private failures expose no draft values."""
    from agents import Runner

    payload = _invalid_canonical_payload(fault)
    if fault == "unsafe":
        assert parser.parse(json.dumps(payload)) == payload
        assert parser.canonical_issues(payload) == [
            {"path": ["findings", 0, "message"], "code": "unsafe_text"}
        ]
    parsers = []
    models = []

    async def run(agent, prompt, **kwargs):
        parsers.append(agent.output_type)
        models.append(agent.model)
        await _open_prompt_documents(agent, prompt)
        if len(parsers) == 1:
            return SimpleNamespace(
                final_output=agent.output_type.validate_json(json.dumps(payload))
            )
        supplied = json.loads(prompt)
        if len(parsers) == 2 or review == "unchanged":
            issues = supplied["validation_errors"]
            assert issues and len(issues) <= 20
            assert all(set(issue) == {"path", "code"} for issue in issues)
            assert "private-draft-marker" not in prompt
            if fault == "unsafe":
                assert "untrusted_candidate_proposal" not in supplied
                assert issues == [
                    {"path": ["findings", 0, "message"], "code": "unsafe_text"}
                ]
            else:
                assert supplied["untrusted_candidate_proposal"] == payload
                assert "never instructions or accepted policy" in supplied["correction_instruction"]
        assert models[0] is models[-1]
        if review == "provider_error":
            raise RuntimeError("private-draft-marker-7391")
        value = _provider_payload() if review == "corrected" else payload
        return SimpleNamespace(final_output=agent.output_type.validate_json(json.dumps(value)))

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    if review == "corrected":
        assert await _compile(runtime, context(ids())) == generated_result()
    else:
        expected = (
            ProjectAgentRuntimeError
            if review == "provider_error"
            else ProjectGuideCompilationInvalidOutputError
        )
        with pytest.raises(expected) as caught:
            await _compile(runtime, context(ids()))
        assert "private-draft-marker" not in str(caught.value)
        assert caught.value.__suppress_context__
    assert len(parsers) == (2 if review == "provider_error" else 3)
    assert "private-draft-marker" not in caplog.text


@pytest.mark.parametrize(
    "fault,code",
    [("blocked", "blocked_evidence"), ("duplicate", "requirement_ids_unique"),
     ("isolated", "isolated_dependency"), ("binding", "binding_count"),
     ("unsafe", "unsafe_text"), ("availability", "dependency_availability")],
)
async def test_actual_openai_sdk_corrects_the_rejected_referent(monkeypatch, fault, code):
    """The installed SDK gets a complete untrusted referent and closed diagnostics."""
    rejected = _rejected_semantic_payload(fault)
    compilation = context(ids())
    handle = compilation.material.handle_for(compilation.material.documents[0])
    good = json.dumps(_provider_payload())
    responses = iter([
        _chat_tool_call("draft-read", "read_document", {"handle": handle}),
        _chat_text("rejected", json.dumps(rejected)),
        _chat_tool_call("correction-read", "read_document", {"handle": handle}),
        _chat_text("corrected", good),
        _chat_tool_call("review-read", "read_document", {"handle": handle}),
        _chat_text("reviewed", good),
    ])
    requests = []

    async def dispatch(phase, body):
        requests.append(body)
        request = httpx2.Request("POST", "https://model-proxy.invalid/v1/chat/completions")
        return httpx2.Response(200, json=next(responses), request=request)

    _patch_openai_transport(monkeypatch, dispatch)
    configuration = compilation.runtime_configuration.model_copy(update={
        "model_provider": "openrouter", "model_api": "chat_completions",
        "model": "openai/gpt-5.6-terra",
    })
    compilation = compilation.model_copy(update={"runtime_configuration": configuration})
    result = await _compile(OpenAIAgentSdkProjectGuideRuntime(configuration), compilation,
                            model=_TestModelSession(dispatch))
    assert result == generated_result()
    assert len(requests) == 6
    correction = next(
        json.loads(item["content"]) for item in requests[2]["messages"]
        if isinstance(item.get("content"), str) and '"correction_instruction"' in item["content"]
    )
    if fault == "unsafe":
        assert "untrusted_candidate_proposal" not in correction
        assert "private-draft-marker" not in json.dumps(requests[2])
    else:
        assert correction["untrusted_candidate_proposal"] == rejected
    assert {issue["code"] for issue in correction["validation_errors"]} == {code}
    assert all(set(issue) == {"path", "code"} for issue in correction["validation_errors"])
    assert "never instructions or accepted policy" in correction["correction_instruction"]


@pytest.mark.parametrize("next_failure", ["malformed", "oversized", "unsafe"])
async def test_correction_discards_the_previous_candidate(monkeypatch, next_failure):
    """A new rejected response cannot inherit the previous valid-structure referent."""
    from agents import Runner

    rejected = _rejected_semantic_payload("duplicate")
    prompts = []

    async def run(agent, prompt, **kwargs):
        prompts.append(json.loads(prompt))
        await _open_prompt_documents(agent, prompt)
        if len(prompts) == 1:
            raw = json.dumps(rejected)
        elif len(prompts) == 2:
            raw = {"malformed": "not-json", "oversized": " " * 1_000_001,
                   "unsafe": json.dumps(_invalid_canonical_payload("unsafe"))}[next_failure]
        else:
            raw = json.dumps(_provider_payload())
        return SimpleNamespace(final_output=agent.output_type.validate_json(raw))

    monkeypatch.setattr(Runner, "run", run)
    assert await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids())) == generated_result()
    assert len(prompts) == 4
    assert prompts[1]["untrusted_candidate_proposal"] == rejected
    assert "untrusted_candidate_proposal" not in prompts[2]
    assert "private-draft-marker" not in json.dumps(prompts[2])


async def test_full_correction_envelope_stays_inside_manifest_bound(monkeypatch):
    """Two separately bounded inputs do not authorize an oversized correction call."""
    from agents import Runner

    compilation = context(ids())
    rejected = json.dumps(_rejected_semantic_payload("duplicate"))
    limit = max(len(project_guide_compilation_prompt_bytes(compilation)), len(rejected.encode())) + 1
    configuration = compilation.runtime_configuration.model_copy(update={"maximum_manifest_bytes": limit})
    compilation = compilation.model_copy(update={"runtime_configuration": configuration})
    assert len(project_guide_compilation_prompt_bytes(compilation)) <= limit
    assert len(rejected.encode()) <= limit
    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(1)
        assert len(calls) == 1, "oversized correction reached the model"
        await _open_prompt_documents(agent, prompt)
        return SimpleNamespace(final_output=agent.output_type.validate_json(rejected))

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(configuration), compilation)
    assert calls == [1]


async def test_corrected_candidate_still_requires_fresh_source_read(monkeypatch):
    """A prior phase's original read cannot authorize a corrected proposal."""
    from agents import Runner

    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            await _open_prompt_documents(agent, prompt)
            payload = _rejected_semantic_payload("duplicate")
        else:
            supplied = json.loads(prompt)
            assert "untrusted_candidate_proposal" in supplied
            payload = _provider_payload()
        return SimpleNamespace(final_output=agent.output_type.validate_json(json.dumps(payload)))

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))
    assert calls == [1, 1, 1]


@pytest.mark.parametrize("last_review_valid", [True, False])
async def test_actual_openai_sdk_corrections_are_bounded_per_phase(monkeypatch, last_review_valid):
    """The installed SDK allows two review repairs after one repaired draft."""
    compilation = context(ids())
    handle = compilation.material.handle_for(compilation.material.documents[0])
    good = json.dumps(_provider_payload())
    outputs = ["not-json", good, "not-json", "not-json", good if last_review_valid else "not-json"]
    responses = iter(
        response
        for index, output in enumerate(outputs)
        for response in (
            _chat_tool_call(f"source-read-{index}", "read_document", {"handle": handle}),
            _chat_text(f"completed-{index}", output),
        )
    )
    requests = []

    async def dispatch(phase, body):
        requests.append(body)
        request = httpx2.Request("POST", "https://model-proxy.invalid/v1/chat/completions")
        return httpx2.Response(200, json=next(responses), request=request)

    _patch_openai_transport(monkeypatch, dispatch)
    configuration = compilation.runtime_configuration.model_copy(update={
        "model_provider": "openrouter", "model_api": "chat_completions",
        "model": "openai/gpt-5.6-terra", "maximum_turns": 12,
    })
    compilation = compilation.model_copy(update={"runtime_configuration": configuration})
    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)
    if last_review_valid:
        assert await _compile(
            runtime, compilation, model=_TestModelSession(dispatch)
        ) == generated_result()
    else:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _compile(runtime, compilation, model=_TestModelSession(dispatch))
        assert caught.value.failure_code == "schema_invalid"
    assert len(requests) == 10
    for index in range(5):
        # Each completed output follows a successful new original read in that invocation.
        tool_result = requests[index * 2 + 1]["messages"][-1]
        assert tool_result["role"] == "tool"
        assert tool_result["tool_call_id"] == f"source-read-{index}"
        assert json.loads(tool_result["content"])["handle"] == handle
    for index, phase in ((2, "checker_specification"), (6, "coverage_review"), (8, "coverage_review")):
        correction = next(
            json.loads(item["content"]) for item in requests[index]["messages"]
            if isinstance(item.get("content"), str) and '"correction_instruction"' in item["content"]
        )
        assert correction["phase"] == phase


def _replace_configuration_schema(compilation, capability_id, document):
    from app.modules.checkers.api.external import (
        ExternalCheckerRegistryEntry,
        ExternalCheckerRegistrySpec,
        ExternalCheckerSchema,
        external_checker_json_hash,
    )
    from tests.checkers.external.support import capability_projection

    entries = [
        d.registry_entry for d in compilation.checker_capabilities.definitions if d.selectable
    ]
    selected = next(e for e in entries if e.capability_id == capability_id)
    schema = ExternalCheckerSchema(
        schema_id=selected.configuration_schema.schema_id,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    values = {key: selected.model_dump()[key] for key in ExternalCheckerRegistrySpec.model_fields}
    spec = ExternalCheckerRegistrySpec.model_validate(values | {"configuration_schema": schema})
    replacement = ExternalCheckerRegistryEntry.model_validate(
        selected.model_dump() | spec.model_dump() | {"entry_digest": spec.spec_digest}
    )
    return compilation.model_copy(
        update={
            "checker_capabilities": capability_projection(
                *(replacement if e.capability_id == capability_id else e for e in entries)
            )
        }
    )


def _configured_runtime_proposal(*, explicit=False):
    """Synthetic fixed registry metadata and a real explicit-choice schema share one wire."""
    from tests.test_guide_configuration_diagnostics import _configured_proposal

    body, projection = _configured_proposal()
    body.pop("setup_notes", None)
    for requirement in body["requirements"]:
        specification = _provider_specification()
        specification["execution_mode"] = "background"
        requirement["check_specification"] = specification
    compilation = context(ids(), checker_capabilities=projection)
    if explicit:
        binding = body["post_submit_bindings"][0]
        entry = next(
            d.registry_entry
            for d in projection.definitions
            if d.capability_id == binding["capability_id"]
        )
        schema = copy.deepcopy(entry.configuration_schema.document)
        schema["oneOf"][0]["properties"]["check"] = {"enum": ["brief", "alternate_brief"]}
        compilation = _replace_configuration_schema(compilation, binding["capability_id"], schema)
    wire = copy.deepcopy(body)
    for index, binding in enumerate(wire["post_submit_bindings"]):
        binding["configuration_source"] = "explicit" if explicit and index == 0 else "registry"
        if binding["configuration_source"] == "registry":
            binding["parameters"] = []
            body["post_submit_bindings"][index]["parameters"].sort(key=lambda p: p["name"])
    return compilation, wire, body


def _private_parser(limit=100_000):
    from agents import AgentOutputSchema

    return CompilationDraftParser(
        generated_compilation_schema(
            AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
        ),
        limit,
    )


def test_registry_wire_materializes_exact_metadata_without_mutating_or_echoing_wire():
    from app.adapters.project_agents.result_validation import validate_project_guide_runtime_result

    compilation, wire, expected = _configured_runtime_proposal()
    original = copy.deepcopy(wire)
    parser = _private_parser()
    assert parser.parse(json.dumps(wire)) == wire
    canonical = parser.canonical_candidate(compilation, wire)
    assert canonical is not None and wire == original
    opened = {compilation.material.handle_for(d) for d in compilation.material.documents}
    assert validate_project_guide_runtime_result(compilation, canonical, opened) == (
        ProjectGuideCompilationResult.model_validate(expected)
    )
    assert all("configuration_source" not in b for b in canonical["post_submit_bindings"])
    assert all(b["parameters"] == [] for b in wire["post_submit_bindings"])


@pytest.mark.parametrize(
    "mode,supplied,code",
    [
        ("explicit", False, "registry_configuration_required"),
        ("explicit", True, "registry_configuration_required"),
        ("registry", True, "registry_parameters_forbidden"),
    ],
)
def test_fixed_wire_rejects_contradictory_mode_even_with_correct_literals(mode, supplied, code):
    compilation, wire, canonical = _configured_runtime_proposal()
    wire["post_submit_bindings"][0]["configuration_source"] = mode
    if supplied:
        wire["post_submit_bindings"][0]["parameters"] = canonical["post_submit_bindings"][0][
            "parameters"
        ]
    parser = _private_parser()
    assert parser.parse(json.dumps(wire)) == wire
    assert parser.canonical_candidate(compilation, wire) is None
    assert parser.issues == [
        {
            "path": [
                "post_submit_bindings",
                0,
                "parameters" if supplied and mode == "registry" else "configuration_source",
            ],
            "code": code,
        }
    ]


@pytest.mark.parametrize("fault", ["missing", "unknown"])
def test_generation_wire_requires_new_mode_without_old_format_alias(fault):
    _, wire, _ = _configured_runtime_proposal()
    binding = wire["post_submit_bindings"][0]
    if fault == "missing":
        binding.pop("configuration_source")
    else:
        binding["configuration_source"] = "implicit"
    assert _private_parser().parse(json.dumps(wire)) is None


@pytest.mark.parametrize("fault", ["stage", "version", "capability", "foreign_entry"])
def test_registry_wire_cannot_substitute_selected_identity_or_stage(fault):
    compilation, wire, _ = _configured_runtime_proposal()
    if fault == "foreign_entry":
        definitions = list(compilation.checker_capabilities.definitions)
        chosen = next(
            d
            for d in definitions
            if d.capability_id == wire["post_submit_bindings"][0]["capability_id"]
        )
        other = next(d for d in definitions if d.selectable and d is not chosen)
        definitions[definitions.index(chosen)] = chosen.model_copy(
            update={"registry_entry": other.registry_entry}
        )
        compilation = compilation.model_copy(
            update={"checker_capabilities": SimpleNamespace(definitions=definitions)}
        )
    else:
        field = {"stage": "stage", "version": "capability_version", "capability": "capability_id"}[
            fault
        ]
        wire["post_submit_bindings"][0][field] = "pre_submit" if fault == "stage" else "unavailable"
    parser = _private_parser()
    assert parser.canonical_candidate(compilation, wire) is None
    assert parser.issues == [{"path": ["post_submit_bindings", 0], "code": "binding_reference"}]


@pytest.mark.parametrize("shape", ["variable", "branches", "default", "reference", "bad_parent"])
def test_non_singleton_or_invalid_parent_registry_contract_is_never_materialized(shape):
    compilation, wire, canonical = _configured_runtime_proposal()
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == wire["post_submit_bindings"][0]["capability_id"]
    )
    schema = copy.deepcopy(entry.configuration_schema.document)
    if shape == "variable":
        schema["oneOf"][0]["properties"]["check"] = {"enum": ["brief", "alternate_brief"]}
    elif shape == "branches":
        other = copy.deepcopy(schema["oneOf"][0])
        other["properties"]["model_profile_version"]["const"] = 2
        schema["oneOf"].append(other)
    elif shape == "default":
        schema["oneOf"][0]["properties"]["check"]["default"] = "brief"
    elif shape == "reference":
        schema["$defs"] = {"fixed": schema.pop("oneOf")[0]}
        schema["$ref"] = "#/$defs/fixed"
    else:
        schema["type"] = "array"
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    parser = _private_parser()
    assert parser.canonical_candidate(compilation, wire) is None
    assert parser.issues[0]["code"] == "registry_configuration_unavailable"
    if shape != "bad_parent":
        wire["post_submit_bindings"][0].update(
            configuration_source="explicit",
            parameters=canonical["post_submit_bindings"][0]["parameters"],
        )
        materialized = parser.canonical_candidate(compilation, wire)
        assert materialized is not None
        from app.adapters.project_agents.result_validation import (
            validate_project_guide_runtime_result,
        )

        opened = {compilation.material.handle_for(d) for d in compilation.material.documents}
        validate_project_guide_runtime_result(compilation, materialized, opened)


@pytest.mark.parametrize("choice", ["brief", "alternate_brief"])
def test_explicit_variable_choices_and_fixed_fields_are_preserved(choice):
    compilation, wire, _ = _configured_runtime_proposal(explicit=True)
    wire["post_submit_bindings"][0]["parameters"][0]["value"] = choice
    parser = _private_parser()
    canonical = parser.canonical_candidate(compilation, wire)
    assert canonical is not None
    assert (
        canonical["post_submit_bindings"][0]["parameters"]
        == wire["post_submit_bindings"][0]["parameters"]
    )
    from app.adapters.project_agents.result_validation import validate_project_guide_runtime_result

    opened = {compilation.material.handle_for(d) for d in compilation.material.documents}
    validate_project_guide_runtime_result(compilation, canonical, opened)


def test_unsafe_text_is_suppressed_before_registry_mode_error():
    compilation, wire, canonical = _configured_runtime_proposal()
    wire["post_submit_bindings"][0]["parameters"] = canonical["post_submit_bindings"][0][
        "parameters"
    ]
    wire["requirements"][0]["statement"] = "token=private-mode-canary"
    parser = _private_parser()
    assert parser.parse(json.dumps(wire)) == wire
    assert parser.canonical_candidate(compilation, wire) is None and parser.unsafe_text
    assert any(i["code"] == "unsafe_text" for i in parser.issues)
    assert "private-mode-canary" not in json.dumps(parser.issues)


@pytest.mark.parametrize("corrected", [True, False])
@pytest.mark.parametrize("explicit", [True, False])
async def test_actual_openai_sdk_keeps_private_wire_and_strict_explicit_validation(
    monkeypatch, corrected, explicit
):
    compilation, wire, canonical = _configured_runtime_proposal(explicit=explicit)
    bad = copy.deepcopy(wire)
    if explicit:
        bad["post_submit_bindings"][0]["parameters"][1]["value"] = canonical[
            "post_submit_bindings"
        ][1]["parameters"][1]["value"]
    else:
        bad["post_submit_bindings"][0]["configuration_source"] = "explicit"
    handle = compilation.material.handle_for(compilation.material.documents[0])
    responses = iter(
        [
            _chat_tool_call("draft-read", "read_document", {"handle": handle}),
            _chat_text("invalid", json.dumps(bad)),
            _chat_tool_call("correction-read", "read_document", {"handle": handle}),
            _chat_text("next", json.dumps(wire if corrected else bad)),
            _chat_tool_call("last-read", "read_document", {"handle": handle}),
            _chat_text("last", json.dumps(wire if corrected else bad)),
        ]
    )
    requests = []

    async def dispatch(phase, body):
        requests.append(body)
        return httpx2.Response(
            200,
            json=next(responses),
            request=httpx2.Request("POST", "https://model-proxy.invalid/v1/chat/completions"),
        )

    _patch_openai_transport(monkeypatch, dispatch)
    configuration = compilation.runtime_configuration.model_copy(
        update={
            "maximum_turns": 12,
            "model_provider": "openrouter",
            "model_api": "chat_completions",
            "model": "openai/gpt-5.6-terra",
        }
    )
    compilation = compilation.model_copy(update={"runtime_configuration": configuration})
    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)
    if corrected:
        assert await _compile(
            runtime, compilation, model=_TestModelSession(dispatch)
        ) == ProjectGuideCompilationResult.model_validate(canonical)
    else:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _compile(runtime, compilation, model=_TestModelSession(dispatch))
        assert caught.value.failure_code == "schema_invalid"
    assert len(requests) == 6
    correction = next(
        json.loads(m["content"])
        for m in requests[2]["messages"]
        if isinstance(m.get("content"), str) and '"correction_instruction"' in m["content"]
    )
    assert correction["untrusted_candidate_proposal"] == bad
    assert {i["code"] for i in correction["validation_errors"]} == (
        {"schema_const"} if explicit else {"registry_configuration_required"}
    )
    if corrected:
        review = next(
            json.loads(m["content"])
            for m in requests[4]["messages"]
            if isinstance(m.get("content"), str) and '"candidate_proposal"' in m["content"]
        )
        assert review["candidate_proposal"] == wire


@pytest.mark.parametrize("value", [True, 7, 1.25, "literal", [True, 2, "literal"]])
def test_registry_materialization_preserves_existing_typed_flat_values(value):
    compilation, wire, _ = _configured_runtime_proposal()
    binding = wire["post_submit_bindings"][0]
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == binding["capability_id"]
    )
    schema = copy.deepcopy(entry.configuration_schema.document)
    branch = schema["oneOf"][0]
    branch["properties"]["machine_setting"] = {"const": value}
    branch["required"].append("machine_setting")
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    canonical = _private_parser().canonical_candidate(compilation, wire)
    assert canonical is not None
    actual = next(
        p["value"]
        for p in canonical["post_submit_bindings"][0]["parameters"]
        if p["name"] == "machine_setting"
    )
    assert actual == value and type(actual) is type(value)


@pytest.mark.parametrize(
    "value", [None, {}, [], [[1]], 10**12 + 1, "token=private-constant-canary"]
)
def test_registry_cannot_expand_values_outside_the_canonical_parameter_contract(value):
    compilation, wire, _ = _configured_runtime_proposal()
    binding = wire["post_submit_bindings"][0]
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == binding["capability_id"]
    )
    schema = copy.deepcopy(entry.configuration_schema.document)
    branch = schema["oneOf"][0]
    branch["properties"]["machine_setting"] = {"const": value}
    branch["required"].append("machine_setting")
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    parser = _private_parser()
    assert parser.canonical_candidate(compilation, wire) is None
    assert parser.issues == [
        {
            "path": ["post_submit_bindings", 0, "configuration_source"],
            "code": "registry_configuration_unavailable",
        }
    ]
    assert "private-constant-canary" not in json.dumps(parser.issues)


@pytest.mark.parametrize("count", [50, 51])
def test_registry_configuration_obeys_existing_fifty_parameter_limit(count):
    compilation, wire, _ = _configured_runtime_proposal()
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == wire["post_submit_bindings"][0]["capability_id"]
    )
    schema = {
        "type": "object",
        "properties": {f"field_{i}": {"const": i} for i in range(count)},
        "required": [f"field_{i}" for i in range(count)],
        "additionalProperties": False,
    }
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    parser = _private_parser()
    canonical = parser.canonical_candidate(compilation, wire)
    if count == 50:
        assert (
            canonical is not None and len(canonical["post_submit_bindings"][0]["parameters"]) == 50
        )
    else:
        assert (
            canonical is None and parser.issues[0]["code"] == "registry_configuration_unavailable"
        )


def test_registry_expansion_and_raw_wire_have_exact_independent_utf8_byte_bounds():
    compilation, wire, _ = _configured_runtime_proposal()
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == wire["post_submit_bindings"][0]["capability_id"]
    )
    schema = copy.deepcopy(entry.configuration_schema.document)
    branch = schema["oneOf"][0]
    branch["properties"]["display_label"] = {"const": "é" * 80}
    branch["required"].append("display_label")
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    raw = json.dumps(wire, ensure_ascii=False, separators=(",", ":"))
    canonical = _private_parser().canonical_candidate(compilation, wire)
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(encoded) > len(raw.encode("utf-8")) and len(encoded) > len(encoded.decode("utf-8"))
    for bound, succeeds in ((len(encoded) - 1, False), (len(encoded), True)):
        parser = _private_parser(bound)
        assert parser.parse(raw) == wire  # Reaches expansion rather than failing raw setup.
        result = parser.canonical_candidate(compilation, wire)
        assert (result is not None) is succeeds
        if not succeeds:
            assert parser.issues == [{"path": [], "code": "expanded_output_too_large"}]
    assert _private_parser(len(raw.encode("utf-8")) - 1).parse(raw) is None
    assert _private_parser(len(raw.encode("utf-8"))).parse(raw) == wire


def test_constant_parameter_named_default_is_not_a_schema_default():
    compilation, wire, _ = _configured_runtime_proposal()
    entry = next(d.registry_entry for d in compilation.checker_capabilities.definitions
                 if d.capability_id == wire["post_submit_bindings"][0]["capability_id"])
    schema = copy.deepcopy(entry.configuration_schema.document)
    branch = schema["oneOf"][0]
    branch["properties"]["default"] = {"const": "literal"}
    branch["required"].append("default")
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    canonical = _private_parser().canonical_candidate(compilation, wire)
    assert canonical is not None
    assert {p["name"]: p["value"] for p in canonical["post_submit_bindings"][0]["parameters"]}["default"] == "literal"


@pytest.mark.parametrize("form", ["direct", "one_of"])
def test_pattern_properties_remain_explicit_typed_choices(form):
    from app.adapters.project_agents.result_validation import validate_project_guide_runtime_result

    compilation, wire, expected = _configured_runtime_proposal()
    binding = wire["post_submit_bindings"][0]
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == binding["capability_id"]
    )
    branch = copy.deepcopy(entry.configuration_schema.document["oneOf"][0])
    branch["patternProperties"] = {"^option_[a-z]+$": {"type": "integer"}}
    schema = branch if form == "direct" else {"oneOf": [branch]}
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    selected = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == binding["capability_id"]
    )
    configuration = {
        p["name"]: p["value"] for p in expected["post_submit_bindings"][0]["parameters"]
    }
    # Both are valid under this one exact registered schema: it is not singleton.
    selected.configuration_schema.validate_instance(configuration)
    selected.configuration_schema.validate_instance({**configuration, "option_retry": 7})
    parser = _private_parser()
    assert parser.parse(json.dumps(wire)) == wire
    assert parser.canonical_candidate(compilation, wire) is None, (
        "pattern_properties_must_not_be_registry_materialized"
    )
    assert parser.issues == [
        {
            "path": ["post_submit_bindings", 0, "configuration_source"],
            "code": "registry_configuration_unavailable",
        }
    ]
    binding.update(
        configuration_source="explicit",
        parameters=[
            *expected["post_submit_bindings"][0]["parameters"],
            {"name": "option_retry", "value": 7},
        ],
    )
    canonical = parser.canonical_candidate(compilation, wire)
    assert canonical is not None, "valid_pattern_choice_must_remain_explicit"
    assert canonical["post_submit_bindings"][0]["parameters"] == binding["parameters"]
    opened = {compilation.material.handle_for(d) for d in compilation.material.documents}
    validate_project_guide_runtime_result(compilation, canonical, opened)
    binding["parameters"][-1]["value"] = "wrong-type"
    canonical = parser.canonical_candidate(compilation, wire)
    assert canonical is not None
    with pytest.raises(ValueError, match="value is invalid"):
        validate_project_guide_runtime_result(compilation, canonical, opened)


def test_definition_named_pattern_properties_is_not_a_schema_keyword():
    compilation, wire, _ = _configured_runtime_proposal()
    binding = wire["post_submit_bindings"][0]
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == binding["capability_id"]
    )
    schema = copy.deepcopy(entry.configuration_schema.document)
    # Definition names may be camelCase; canonical parameter names may not.
    schema["$defs"] = {"patternProperties": {"type": "string"}}
    compilation = _replace_configuration_schema(compilation, entry.capability_id, schema)
    assert _private_parser().canonical_candidate(compilation, wire) is not None
