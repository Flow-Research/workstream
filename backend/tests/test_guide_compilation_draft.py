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


def _configured_runtime_proposal():
    """Two synthetic locked tuples expose cross-profile mixing without private fixtures."""
    from app.adapters.project_agents.result_validation import validate_project_guide_runtime_result
    from app.interfaces.project_agents import validate_post_submission_bindings
    from app.modules.checkers.api.external import ExternalCheckerContractError
    from tests.test_guide_configuration_diagnostics import _configured_proposal

    body, projection = _configured_proposal()
    body.pop("setup_notes", None)
    for requirement in body["requirements"]:
        specification = _provider_specification()
        specification["execution_mode"] = "background"
        requirement["check_specification"] = specification
    compilation = context(ids(), checker_capabilities=projection)
    good = _provider_payload(ProjectGuideCompilationResult.model_validate(body))
    opened = {compilation.material.handle_for(d) for d in compilation.material.documents}
    validate_project_guide_runtime_result(compilation, good, opened)
    bad = copy.deepcopy(good)
    bad["post_submit_bindings"][0]["parameters"][1]["value"] = good["post_submit_bindings"][1][
        "parameters"
    ][1]["value"]
    with pytest.raises(ExternalCheckerContractError):
        validate_post_submission_bindings(
            ProjectGuideCompilationResult.model_validate(bad), projection
        )
    return compilation, bad, good


def test_correction_contracts_repeat_only_the_selected_trusted_schema():
    from app.adapters.project_agents.compilation_draft import (
        selected_configuration_correction_context,
    )

    compilation, bad, good = _configured_runtime_proposal()
    before = copy.deepcopy(bad)
    issues = [
        {"path": ["post_submit_bindings", 0, "parameters", 1, "value"], "code": "schema_const"}
    ]
    selected = selected_configuration_correction_context(compilation, bad, issues)
    entry = next(
        d.registry_entry
        for d in compilation.checker_capabilities.definitions
        if d.capability_id == good["post_submit_bindings"][0]["capability_id"]
    )
    assert selected == [
        {
            "binding_paths": [["post_submit_bindings", 0]],
            "capability_id": entry.capability_id,
            "capability_version": entry.capability_version,
            "registry_entry_id": str(entry.registry_entry_id),
            "registry_entry_digest": entry.entry_digest,
            "configuration_schema": entry.configuration_schema.model_dump(mode="json"),
        }
    ]
    assert bad == before
    bad["post_submit_bindings"][0]["parameters"][1]["value"] = "private-candidate-guidance-canary"
    assert selected_configuration_correction_context(compilation, bad, issues) == selected
    assert "private-candidate-guidance-canary" not in json.dumps(selected)
    unrelated_id = good["post_submit_bindings"][1]["parameters"][1]["value"]
    assert unrelated_id not in json.dumps(selected)


@pytest.mark.parametrize(
    "fault", ["absent", "invalid", "version", "stage", "default", "unselectable", "nonconst"]
)
def test_correction_contracts_cannot_select_unrelated_or_unavailable_registry(fault):
    from app.adapters.project_agents.compilation_draft import (
        selected_configuration_correction_context,
    )

    compilation, bad, _ = _configured_runtime_proposal()
    issues = [
        {"path": ["post_submit_bindings", 0, "parameters", 1, "value"], "code": "schema_const"}
    ]
    if fault == "absent":
        bad = None
    elif fault == "invalid":
        bad = {"private-candidate-guidance-canary": "not a proposal"}
    elif fault == "version":
        bad["post_submit_bindings"][0]["capability_version"] = "unavailable"
    elif fault == "stage":
        bad["post_submit_bindings"][0]["stage"] = "pre_submit"
    elif fault == "default":
        bad["post_submit_bindings"][0].update(
            capability_id="workstream.default", capability_version="v1", stage="pre_submit"
        )
        bad["pre_submit_bindings"] = [bad["post_submit_bindings"].pop(0)]
        issues[0]["path"][0] = "pre_submit_bindings"
    elif fault == "unselectable":
        compilation = compilation.model_copy(
            update={
                "checker_capabilities": SimpleNamespace(
                    definitions=[
                        d.model_copy(update={"selectable": False})
                        for d in compilation.checker_capabilities.definitions
                    ]
                )
            }
        )
    else:
        issues[0]["code"] = "context_constraint"
    assert selected_configuration_correction_context(compilation, bad, issues) == []


def test_correction_contracts_deduplicate_registry_and_share_twenty_issue_bound():
    from app.adapters.project_agents.compilation_draft import (
        selected_configuration_correction_context,
    )

    compilation, bad, _ = _configured_runtime_proposal()
    requirement, binding = bad["requirements"][0], bad["post_submit_bindings"][0]
    bad["requirements"] = [requirement | {"requirement_id": f"check_{i}"} for i in range(25)]
    bad["post_submit_bindings"] = [binding | {"requirement_id": f"check_{i}"} for i in range(25)]
    issues = [
        {"path": ["post_submit_bindings", i, "parameters", 1, "value"], "code": "schema_const"}
        for i in range(25)
    ]
    selected = selected_configuration_correction_context(compilation, bad, issues)
    assert len(selected) == 1
    assert selected[0]["binding_paths"] == [["post_submit_bindings", i] for i in range(20)]
    assert selected_configuration_correction_context(compilation, bad, issues[:1] * 20) == (
        selected_configuration_correction_context(compilation, bad, issues[:1])
    )


@pytest.mark.parametrize("corrected", [True, False])
async def test_actual_openai_sdk_uses_selected_schema_for_mixed_profile_correction(
    monkeypatch, corrected
):
    """A completed mixed tuple remains invalid; only the model's corrected output can pass."""
    compilation, bad, good = _configured_runtime_proposal()
    handle = compilation.material.handle_for(compilation.material.documents[0])
    responses = iter(
        [
            _chat_tool_call("draft-read", "read_document", {"handle": handle}),
            _chat_text("mixed", json.dumps(bad)),
            _chat_tool_call("correction-read", "read_document", {"handle": handle}),
            _chat_text("next", json.dumps(good if corrected else bad)),
            _chat_tool_call("last-read", "read_document", {"handle": handle}),
            _chat_text("last", json.dumps(good if corrected else bad)),
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
            "model_provider": "openrouter",
            "model_api": "chat_completions",
            "model": "openai/gpt-5.6-terra",
        }
    )
    compilation = compilation.model_copy(update={"runtime_configuration": configuration})
    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)
    if corrected:
        assert await _compile(runtime, compilation, model=_TestModelSession(dispatch)) == (
            ProjectGuideCompilationResult.model_validate(good)
        )
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
    from app.adapters.project_agents.compilation_draft import (
        selected_configuration_correction_context,
    )

    assert correction[
        "selected_configuration_contracts"
    ] == selected_configuration_correction_context(
        compilation, bad, correction["validation_errors"]
    )
    assert len(correction["selected_configuration_contracts"]) == 1
    assert correction["untrusted_candidate_proposal"] == bad
    assert "do not mix tuples" in correction["correction_instruction"]
