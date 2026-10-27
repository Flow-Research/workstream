"""Setup proposes only checks and repairs strict output without granting new authority."""

import copy
import json
import re
from types import SimpleNamespace

import pytest

from app.adapters.project_agents.compilation_draft import (
    CompilationDraftParser,
    generated_compilation_schema,
)
from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.core.project_guide_instructions import (
    PROJECT_GUIDE_INSTRUCTIONS,
    PROJECT_GUIDE_OUTPUT_EXAMPLE,
)
from app.interfaces.project_agents import (
    CheckRuntimeDependency,
    CheckSpecification,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    require_complete_generated_specifications,
    validate_project_guide_compilation_result,
)
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from tests.projects.guide_compilation.helpers import (
    context,
    generated_result,
    ids,
    runtime_configuration,
    valid_specification,
)
from tests.test_agent_runtime import (
    _compile,
    _open_prompt_documents,
    _provider_payload,
    _sdk_result,
    model_credentials,  # noqa: F401
)


def _schema():
    from agents import AgentOutputSchema

    return generated_compilation_schema(
        AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
    )


def test_example_is_complete_valid_and_bound_to_instructions():
    example = PROJECT_GUIDE_OUTPUT_EXAMPLE
    raw = json.dumps(example["result"])
    assert CompilationDraftParser(_schema(), 100_000).parse(raw) == example["result"]
    result = ProjectGuideCompilationResult.model_validate_json(raw)
    assert {r.check_specification.execution_mode for r in result.requirements} == {
        "bounded_pre_submit",
        "background",
    }
    compilation = context(ids())
    # Replace only synthetic source identities for context-dependent validation.
    payload = copy.deepcopy(example["result"])
    actual_ref = generated_result().requirements[0].evidence_refs[0].model_dump(mode="json")
    for requirement in payload["requirements"]:
        requirement["evidence_refs"] = [actual_ref]
    for suggestion in payload["capability_suggestions"]:
        suggestion["evidence_refs"] = [actual_ref]
    payload["agent_version"] = compilation.agent_version
    actual = ProjectGuideCompilationResult.model_validate(payload)
    require_complete_generated_specifications(compilation, actual)
    validate_project_guide_compilation_result(compilation, actual)
    displayed = PROJECT_GUIDE_INSTRUCTIONS.split("Complete JSON output example:\n", 1)[1]
    assert CompilationDraftParser(_schema(), 100_000).parse(displayed) == example["result"]
    assert len(PROJECT_GUIDE_INSTRUCTIONS) <= 16_000
    assert "setup_notes" not in PROJECT_GUIDE_INSTRUCTIONS
    schema = _schema()
    assert "setup_notes" not in schema["properties"]
    assert "setup_notes" not in schema["required"]
    allowed = {
        "platform_covered",
        "guide_blocker",
        "supported_pre_submit",
        "supported_post_submit",
        "pre_submit_capability_gap",
        "post_submit_capability_gap",
    }
    assert set(schema["$defs"]["RequirementDisposition"]["enum"]) == allowed
    assert (
        set(schema["$defs"]["AtomicGuideRequirement"]["properties"]["disposition"]["enum"])
        == allowed
    )


def test_dependency_guidance_matches_canonical_triples_methods_and_nested_material():
    from tests.projects.guide_compilation.test_check_specifications import (
        _requirement,
        _with_requirement,
    )

    guidance = PROJECT_GUIDE_INSTRUCTIONS.split("DEPENDENCIES\n", 1)[1].split(
        "OUTPUT AND VALIDATION\n", 1
    )[0]
    availability = re.search(
        r"kind/provisioning; unavailable_code=([a-z_]+):\n(.*?)\.\n", guidance, re.DOTALL
    )
    assert availability is not None
    dependencies = {
        kind: CheckRuntimeDependency(
            dependency_id=kind,
            kind=kind,
            provisioning=provisioning,
            unavailable_code=availability[1],
            purpose="Provide the declared checker support.",
        )
        for kind, provisioning in re.findall(r"([a-z_]+)/([a-z_]+)", availability[2])
    }
    assert set(dependencies) == {
        "checker_tool",
        "isolated_execution",
        "model_service",
        "nested_sandbox",
    }

    def admit(method, selected, *, material=False):
        body = valid_specification().model_dump(mode="json")
        body.update(evaluation_method=method, execution_mode="background")
        body["runtime_dependencies"] = [item.model_dump(mode="json") for item in selected]
        body["infrastructure_failures"] = [
            {"code": code, "condition": "Required checker support is unavailable."}
            for code in sorted({item.unavailable_code for item in selected})
        ]
        if material:
            body["inputs"].append(
                {"input_id": "cache", "kind": "prepared_material", "purpose": "Offline inputs."}
            )
        specification = CheckSpecification.model_validate(body)
        requirement = _requirement(
            disposition="post_submit_capability_gap", check_specification=specification
        )
        require_complete_generated_specifications(context(ids()), _with_requirement(requirement))

    method_guidance = re.search(r"evaluation_method/kind: (.*?)\.\n", guidance, re.DOTALL)
    assert method_guidance is not None
    methods = dict(re.findall(r"([a-z_]+) requires ([a-z_]+)", method_guidance[1]))
    assert set(methods) == {"isolated_execution", "model_evaluation"}
    for method, required_kind in methods.items():
        admit(method, [dependencies[required_kind]])

    cache_guidance = re.search(
        r"Cache: ([a-z_]+)/([a-z_]+)/([a-z_]+) requires ([a-z_]+)/([a-z_]+)\.", guidance
    )
    assert cache_guidance is not None
    kind, provisioning, code, nested_kind, nested_provisioning = cache_guidance.groups()
    cache = CheckRuntimeDependency(
        dependency_id="cache",
        kind=kind,
        provisioning=provisioning,
        unavailable_code=code,
        purpose="Provide the declared offline inputs.",
    )
    assert cache.kind == "prepared_material"
    nested = dependencies[nested_kind]
    assert nested.provisioning == nested_provisioning
    trial_dependencies = {
        item.dependency_id: item
        for item in [dependencies[methods["isolated_execution"]], cache, nested]
    }
    admit(
        "isolated_execution",
        list(trial_dependencies.values()),
        material=True,
    )

    combined = re.search(r"model\+trial=([a-z_]+)\+([a-z_]+);", guidance)
    assert combined is not None
    admit(
        "model_evaluation",
        [dependencies[kind] for kind in combined.groups()] + [cache],
        material=True,
    )



@pytest.mark.parametrize(
    "disposition", ["human_review", "project_lifecycle_policy", "informational"]
)
def test_inference_cannot_return_management_classifications_but_retained_reads_survive(disposition):
    payload = _provider_payload()
    requirement = payload["requirements"][0]
    requirement.update(disposition=disposition, platform_coverage=None)
    assert CompilationDraftParser(_schema(), 100_000).parse(json.dumps(payload)) is None
    retained = ProjectGuideCompilationResult.model_validate(payload)
    original = accepted_compilation_result(retained)
    assert (
        accepted_compilation_result(
            ProjectGuideCompilationResult.model_validate(
                original.canonical_result,
            )
        )
        == original
    )
    with pytest.raises(ValueError, match="outside PRE and POST"):
        require_complete_generated_specifications(context(ids()), retained)
    manager = context(ids()).model_copy(
        update={
            "runtime_configuration": runtime_configuration().model_copy(
                update={
                    "runtime_key": "manager_authored",
                    "model_provider": "none",
                    "model_api": "none",
                    "model": "none",
                }
            ),
        }
    )
    require_complete_generated_specifications(manager, retained)


@pytest.mark.usefixtures("model_credentials")
@pytest.mark.parametrize("phase", ["draft", "review"])
@pytest.mark.parametrize(
    "fault",
    [
        "prose",
        "duplicate",
        "extra",
        "notes",
        "lifecycle",
        "canonical",
        "source",
        "version",
    ],
)
async def test_rejected_output_gets_error_feedback_then_complete_revalidation(
    monkeypatch, phase, fault
):
    from agents import Runner

    calls = []
    marker = "private-rejected-output-781"
    bad = _provider_payload()
    if fault in {"extra", "notes"}:
        bad["setup_notes" if fault == "notes" else marker] = [marker]
    elif fault == "lifecycle":
        bad["requirements"][0].update(
            disposition="project_lifecycle_policy", platform_coverage=None
        )
    elif fault == "canonical":
        bad["submission_artifact_policy"]["required_artifacts"] = ["../private"]
    elif fault == "source":
        bad["requirements"][0]["evidence_refs"][0]["sha256"] = "sha256:" + "f" * 64
    elif fault == "version":
        bad["agent_version"] = "wrong_version"
    raw = json.dumps(bad)
    if fault == "prose":
        raw = marker + raw
    elif fault == "duplicate":
        raw = '{"status":"draft_ready",' + raw[1:]
    rejected_call = 1 if phase == "draft" else 2

    async def run(agent, prompt, **kwargs):
        calls.append(json.loads(prompt))
        await _open_prompt_documents(agent, prompt)
        if len(calls) == rejected_call:
            return SimpleNamespace(final_output=agent.output_type.validate_json(raw))
        if len(calls) == rejected_call + 1:
            errors = calls[-1]["validation_errors"]
            assert errors and len(errors) <= 20
            assert marker not in prompt and "../private" not in prompt
            assert "candidate_proposal" not in calls[-1]
        return _sdk_result(agent)

    monkeypatch.setattr(Runner, "run", run)
    assert (
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))
        == generated_result()
    )
    assert len(calls) == 3


@pytest.mark.usefixtures("model_credentials")
@pytest.mark.parametrize("phase", ["draft", "review"])
async def test_output_correction_exhaustion_never_returns_a_proposal(monkeypatch, phase):
    from agents import Runner

    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(json.loads(prompt))
        await _open_prompt_documents(agent, prompt)
        if phase == "review" and len(calls) == 1:
            return _sdk_result(agent)
        return SimpleNamespace(final_output=agent.output_type.validate_json("not-json"))

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))
    assert len(calls) == (3 if phase == "draft" else 4)


@pytest.mark.usefixtures("model_credentials")
async def test_draft_and_review_share_two_corrections(monkeypatch):
    """A draft repair cannot grant the review a new correction allowance."""
    from agents import Runner

    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(json.loads(prompt))
        await _open_prompt_documents(agent, prompt)
        if len(calls) == 2:
            return _sdk_result(agent)
        return SimpleNamespace(final_output=agent.output_type.validate_json("not-json"))

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))
    assert len(calls) == 4
    assert calls[1]["phase"] == "checker_specification"
    assert calls[2]["phase"] == calls[3]["phase"] == "coverage_review"


@pytest.mark.usefixtures("model_credentials")
async def test_corrections_cannot_reset_model_turn_budget(monkeypatch):
    """Count actual model-boundary calls, including a rejected completed output."""
    from agents import OpenAIResponsesModel, Runner

    turns = []
    phases = []

    async def response(self, *args, **kwargs):
        turns.append(1)
        return SimpleNamespace(output=[])

    async def run(agent, prompt, **kwargs):
        phases.append(kwargs["max_turns"])
        await _open_prompt_documents(agent, prompt)
        for _ in range(2):
            await agent.model.get_response(
                agent.instructions,
                [],
                agent.model_settings,
                agent.tools,
                agent.output_type,
                [],
                None,
            )
        return SimpleNamespace(final_output=agent.output_type.validate_json("not-json"))

    monkeypatch.setattr(OpenAIResponsesModel, "get_response", response)
    monkeypatch.setattr(Runner, "run", run)
    config = runtime_configuration().model_copy(update={"maximum_turns": 4})
    compilation = context(ids()).model_copy(update={"runtime_configuration": config})
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(config), compilation)
    assert len(turns) == 2
    assert phases == [2]


@pytest.mark.usefixtures("model_credentials")
@pytest.mark.parametrize("phase", ["draft", "review"])
@pytest.mark.parametrize("corrected", [True, False])
@pytest.mark.parametrize("access", ["omitted", "search", "offset_read", "empty_read"])
async def test_blocked_proposal_must_open_all_originals_even_during_correction(
    monkeypatch,
    phase,
    corrected,
    access,
):
    """A blocker from one source cannot conceal a second assigned original."""
    from agents import Runner
    from uuid import uuid4

    compilation = context(ids())
    original = compilation.material.documents[0]
    second = original.model_copy(
        update={
            "source_item_id": uuid4(),
            "ingest_id": uuid4(),
            "put_attempt_id": uuid4(),
            "item_order": original.item_order + 1,
        }
    )
    compilation = compilation.model_copy(
        update={
            "material": compilation.material.model_copy(update={"documents": (original, second)}),
        }
    )
    blocked = _provider_payload()
    blocked.update(status="guide_blocked", submission_artifact_policy=None, requirements=[])
    blocked["findings"][0].update(
        severity="blocking_gap",
        code="ambiguous_requirement",
        message="The guide contradicts the required report format.",
    )
    calls = []
    rejected_call = 1 if phase == "draft" else 2

    async def run(agent, prompt, **kwargs):
        calls.append(json.loads(prompt))
        incomplete = len(calls) == rejected_call or (not corrected and len(calls) > rejected_call)
        await _open_prompt_documents(agent, prompt, count=1 if incomplete else None)
        if incomplete and access != "omitted":
            from agents.tool_context import ToolContext

            handle = compilation.material.handle_for(second)
            name = "search_document" if access == "search" else "read_document"
            arguments = {"handle": handle}
            if access == "search":
                arguments["query"] = "absent-from-original"
            else:
                arguments["offset"] = 1 if access == "offset_read" else 1000
            encoded = json.dumps(arguments)
            tool = next(item for item in agent.tools if item.name == name)
            observed = json.loads(await tool.on_invoke_tool(
                ToolContext(context=None, tool_name=name, tool_call_id="test-nonreading-access",
                            tool_arguments=encoded), encoded,
            ))
            assert bool(observed["text"]) is (access == "offset_read")
        if len(calls) == rejected_call + 1:
            assert calls[-1]["validation_errors"] == [{"path": [], "code": "source_coverage"}]
        return SimpleNamespace(final_output=agent.output_type.validate_json(json.dumps(blocked)))

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(compilation.runtime_configuration)
    if corrected:
        output = await _compile(runtime, compilation)
        assert output.status == "guide_blocked"
        assert len(calls) == 3
    else:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError):
            await _compile(runtime, compilation)
        assert len(calls) == (3 if phase == "draft" else 4)


@pytest.mark.usefixtures("model_credentials")
async def test_real_sdk_runner_corrects_invalid_json_then_performs_fresh_review(monkeypatch):
    """Exercise SDK tool dispatch and parser-exception propagation without model I/O."""
    from agents import OpenAIResponsesModel
    from agents.items import ModelResponse
    from agents.usage import Usage
    from openai.types.responses import (
        ResponseFunctionToolCall,
        ResponseOutputMessage,
        ResponseOutputText,
    )

    compilation = context(ids())
    handle = compilation.material.handle_for(compilation.material.documents[0])
    calls = []
    marker = "private-invalid-sdk-output-521"
    valid = json.dumps(_provider_payload())

    async def response(self, system_instructions, input, *args, **kwargs):
        calls.append(input)
        index = len(calls)
        if index in {1, 3, 5}:
            item = ResponseFunctionToolCall(
                id=f"fc_{index}",
                call_id=f"call_{index}",
                name="read_document",
                type="function_call",
                arguments=json.dumps({"handle": handle}),
                status="completed",
            )
        else:
            item = ResponseOutputMessage(
                id=f"msg_{index}",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(
                        type="output_text",
                        text=marker if index == 2 else valid,
                        annotations=[],
                    )
                ],
            )
        return ModelResponse(output=[item], usage=Usage(), response_id=f"resp_{index}")

    monkeypatch.setattr(OpenAIResponsesModel, "get_response", response)
    output = await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), compilation)
    assert output == generated_result()
    assert len(calls) == 6
    assert "validation_errors" in json.dumps(calls[2])
    assert marker not in json.dumps(calls[2])
    assert "coverage_review" in json.dumps(calls[4])
    assert "validation_errors" not in json.dumps(calls[4])


@pytest.mark.usefixtures("model_credentials")
async def test_empty_original_can_be_read_and_reported_as_blocked(monkeypatch):
    """A verified empty original is valid access evidence, unlike an empty search."""
    from agents import Runner

    blocked = _provider_payload()
    blocked.update(status="guide_blocked", submission_artifact_policy=None, requirements=[])
    blocked["findings"][0].update(severity="blocking_gap", message="The guide is empty.")
    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(prompt)
        await _open_prompt_documents(agent, prompt)
        return SimpleNamespace(final_output=agent.output_type.validate_json(json.dumps(blocked)))

    monkeypatch.setattr(Runner, "run", run)
    compilation = context(ids())
    output = await _compile(
        OpenAIAgentSdkProjectGuideRuntime(compilation.runtime_configuration), compilation,
        document_text="",
    )
    assert output.status == "guide_blocked"
    assert len(calls) == 2


async def test_public_api_drill_runtime_emits_admissible_inference():
    """The actual scripted worker result must satisfy current inference admission."""
    from scripts.guide_compilation_e2e import E2EProjectGuideRuntime
    from app.adapters.project_agents.result_validation import validate_project_guide_runtime_result
    from app.interfaces.project_agents import PROJECT_GUIDE_COMPILATION_AGENT_VERSION

    compilation = context(ids()).model_copy(update={
        "agent_version": PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
    })
    runtime = E2EProjectGuideRuntime(compilation.runtime_configuration)
    output = await _compile(runtime, compilation)
    opened = {compilation.material.handle_for(item) for item in compilation.material.documents}
    assert validate_project_guide_runtime_result(compilation, output, opened) == output
    assert runtime.calls == 1


async def test_recorded_public_journey_runtime_emits_admissible_inference(monkeypatch):
    """The prefork drill must generate complete specs and omit removed notes."""
    import hashlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from experiments.pilot04_external_checker_runtime.guide_runtime import RecordedGuideRuntime
    from experiments.pilot04_external_checker_runtime.guide_inputs import GUIDE_BYTES, TASK_EXAMPLES
    from app.adapters.project_agents.result_validation import validate_project_guide_runtime_result
    from app.interfaces.project_agents import PROJECT_GUIDE_COMPILATION_AGENT_VERSION
    from app.modules.projects.api.task_examples import validate_task_examples
    from tests.checkers.external.support import capability_projection, registry_entry

    compilation = context(ids(), checker_capabilities=capability_projection(
        registry_entry("pre_submit"), registry_entry("post_submit"),
    ))
    document = compilation.material.documents[0].model_copy(update={
        "sha256": "sha256:" + hashlib.sha256(GUIDE_BYTES).hexdigest(),
        "byte_count": len(GUIDE_BYTES), "media_type": "text/markdown",
    })
    compilation = compilation.model_copy(update={
        "agent_version": PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
        "task_examples": validate_task_examples(TASK_EXAMPLES),
        "material": compilation.material.model_copy(update={"documents": (document,)}),
    })
    runtime = RecordedGuideRuntime(compilation.runtime_configuration)
    output = await _compile(runtime, compilation, document_text=GUIDE_BYTES.decode())
    opened = {compilation.material.handle_for(document)}
    assert validate_project_guide_runtime_result(compilation, output, opened) == output
    assert len(output.pre_submit_bindings) == len(output.post_submit_bindings) == 1
    assert runtime.calls == 1


@pytest.mark.parametrize("profile_refused", [False, True])
async def test_public_drill_requires_operator_profile_before_guide_setup(monkeypatch, profile_refused):
    """A missing/refused model profile must never start the guide's upload flow."""
    from pathlib import Path
    from unittest.mock import AsyncMock

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import guide_compilation_e2e
    from experiments.pilot04_external_checker_runtime import public_guide_setup as probe

    project_id = "00000000-0000-4000-8000-000000000021"
    manager, operator = object(), object()
    async def seed(_factory, _project, **kwargs):
        return (operator if kwargs.get("role") == "operator" else manager), None
    monkeypatch.setattr(probe, "seed_review_actor", seed)
    denied = RuntimeError("profile publication refused")
    publish = AsyncMock(side_effect=denied if profile_refused else None,
                        return_value={"spec": {"project_id": project_id, "profile_version": 1}})
    monkeypatch.setattr(guide_compilation_e2e, "publish_scripted_model_profile", publish)
    reached_guide = RuntimeError("guide setup reached")
    client = object()
    async def call(_client, method, path, token, status, **kwargs):
        assert method == "POST"
        if path == "/api/v1/projects":
            return {"id": project_id}
        assert path == f"/api/v1/projects/{project_id}/guides"
        publish.assert_awaited_once_with(client, "operator-token", project_id)
        raise reached_guide
    def token_for(actor):
        return "operator-token" if actor is operator else "manager-token"
    with pytest.raises(RuntimeError) as error:
        await probe.public_guide_setup(client, object(), True, call, token_for)
    assert error.value is (denied if profile_refused else reached_guide)
    publish.assert_awaited_once_with(client, "operator-token", project_id)
