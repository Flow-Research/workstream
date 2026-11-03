"""Invalid drafts are rejected; bounded corrections must pass source review."""

import copy
import json
from types import SimpleNamespace

import httpx2
import pytest

from app.adapters.project_agents.compilation_draft import (
    CompilationDraftParser,
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
from tests.projects.guide_compilation.test_correction_context import correction_context
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
        AgentOutputSchema(ProjectGuideCompilationResult).json_schema(),
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
        payload["requirements"][0]["check_specification"]["inputs"][0]["relative_path"] = "../private"
    else:
        payload["findings"][0]["message"] = "token=private-draft-marker-7391"
    return payload


def _rejected_semantic_payload(fault):
    """Synthetic versions of the live invariant failures, with no private fixture data."""
    if fault == "unsafe":
        return _invalid_canonical_payload("unsafe")
    payload = _provider_payload()
    if fault == "agent_version":
        payload["agent_version"] = "project_guide_compilation_agent.v1"
    elif fault == "blocked":
        payload["status"] = "guide_blocked"
        payload["submission_artifact_policy"] = None
    elif fault == "duplicate":
        payload["requirements"].append(copy.deepcopy(payload["requirements"][0]))
    else:
        requirement = payload["requirements"][0]
        specification = _provider_specification()
        if fault == "code_overlap":
            specification["inability_to_evaluate"][0]["code"] = specification["failure_findings"][0]["code"]
        elif fault == "unknown_finding":
            specification["negative_tests"][0]["expected_finding_codes"] = ["unknown_finding"]
        requirement["check_specification"] = specification
    return payload


async def test_actual_openai_sdk_sends_only_manager_reason_on_explicit_correction(monkeypatch):
    """Provider phases receive the PM request without prior proposal or custody IDs."""
    compilation = correction_context()
    handle = compilation.material.handle_for(compilation.material.documents[0])
    good = json.dumps(_provider_payload())
    responses = iter([
        _chat_tool_call("draft-read", "read_document", {"handle": handle}),
        _chat_text("draft", good),
        _chat_tool_call("review-read", "read_document", {"handle": handle}),
        _chat_text("review", good),
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
    assert len(requests) == 4
    for request in requests:
        system = next(item["content"] for item in request["messages"] if item["role"] == "system")
        assert f'Trusted output agent_version is "{compilation.agent_version}".' in system
    draft = next(json.loads(item["content"]) for item in requests[0]["messages"]
                 if item["role"] == "user" and isinstance(item.get("content"), str))
    assert set(draft) == {"material", "task_examples", "manager_feedback"}
    assert draft["manager_feedback"] == compilation.correction_feedback.reason
    review = next(json.loads(item["content"]) for item in requests[2]["messages"]
                  if item["role"] == "user" and isinstance(item.get("content"), str)
                  and '"guide_setup_context"' in item["content"])
    assert review["guide_setup_context"] == draft
    for body in (draft, review["guide_setup_context"]):
        exposed = json.dumps(body)
        assert "Preserve this coverage." not in exposed
        assert str(compilation.correction_feedback.operation_id) not in exposed
        assert compilation.correction_feedback.predecessor_result_hash not in exposed


def test_private_text_diagnostic_does_not_expose_other_invalid_fields(parser):
    """A mixed rejection keeps the unsafe value out of diagnostics."""
    payload = _rejected_semantic_payload("code_overlap")
    payload["requirements"][0]["check_specification"]["check_steps"] = [
        "token=private-draft-marker-7391"
    ]
    assert parser.parse(json.dumps(payload)) == payload
    issues = parser.canonical_issues(payload)
    assert parser.unsafe_text is True
    assert issues == [
        {"path": ["requirements", 0, "check_specification", "check_steps"],
         "code": "unsafe_text"},
    ]
    assert "private-draft-marker" not in json.dumps(issues)
    assert parser.canonical_issues(_rejected_semantic_payload("code_overlap")) == [
        {"path": ["requirements", 0, "check_specification"],
         "code": "verdict_code_overlap"},
    ]
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
    [("agent_version", "agent_version"), ("blocked", "blocked_evidence"),
     ("duplicate", "suggestion_ids_unique"),
     ("code_overlap", "verdict_code_overlap"),
     ("unsafe", "unsafe_text"), ("unknown_finding", "finding_reference")],
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
    if fault == "agent_version":
        assert correction["validation_errors"] == [
            {"path": ["agent_version"], "code": "agent_version"}
        ]
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
