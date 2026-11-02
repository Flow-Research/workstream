"""One attempt budget must cover candidate generation and coverage review together."""

from types import SimpleNamespace
from functools import partial
import json

import pytest

from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.adapters.project_agents import build_project_guide_adapter_profile
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.core.project_agents import project_guide_runtime_configuration
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    project_guide_compilation_prompt_bytes,
)
from tests.projects.guide_compilation.helpers import (
    generated_result,
    runtime_configuration,
)
from tests.test_agent_runtime import (
    _compile,
    _open_prompt_documents,
    _provider_payload,
    _sdk_result,
)
from tests.projects.guide_compilation.test_correction_context import correction_context


@pytest.mark.parametrize("boundary", ["model_turns", "tool_calls", "within_budget"])
async def test_coverage_review_cannot_reset_the_attempt_work_budget(monkeypatch, boundary):
    """Even a runner overrunning its phase allowance cannot make an extra provider call."""
    from agents import OpenAIResponsesModel, Runner

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    responses = []
    phases = []
    config = runtime_configuration().model_copy(
        update={
            "maximum_turns": 6 if boundary == "model_turns" else 10,
            "maximum_tool_calls": 1 if boundary == "tool_calls" else 8,
        }
    )

    async def response(self, *args, **kwargs):
        responses.append(self)
        return SimpleNamespace(output=[SimpleNamespace(type="message")])

    monkeypatch.setattr(OpenAIResponsesModel, "get_response", response)

    async def run(agent, prompt, **kwargs):
        inputs = json.loads(prompt)
        guide_context = inputs.get("guide_setup_context", inputs)
        assert guide_context[
            "correction_predecessor"
        ] == compilation.correction_predecessor.model_dump(mode="json")
        await _open_prompt_documents(agent, prompt)
        phases.append(kwargs["max_turns"])
        # Candidate uses three turns. The review tries four more, irrespective of
        # the SDK phase limit, to exercise the adapter's independent shared fence.
        for _ in range(3 if len(phases) == 1 else 4):
            await agent.model.get_response(
                agent.instructions,
                [],
                agent.model_settings,
                agent.tools,
                agent.output_type,
                [],
                None,
            )
        return _sdk_result(agent, generated_result())

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(config)
    compilation = correction_context().model_copy(update={"runtime_configuration": config})
    if boundary == "within_budget":
        assert await _compile(runtime, compilation) == generated_result()
    else:
        with pytest.raises(ProjectAgentRuntimeError, match="project guide run failed"):
            await _compile(runtime, compilation)
    assert phases == (
        [config.maximum_turns // 2]
        if boundary == "tool_calls"
        else [config.maximum_turns // 2, config.maximum_turns - 3]
    )
    assert len(responses) == {"model_turns": 6, "tool_calls": 3, "within_budget": 7}[boundary]
    assert all(model is responses[0] for model in responses)


async def test_oversize_predecessor_is_rejected_before_provider_execution(monkeypatch):
    """The authenticated body counts towards the actual provider prompt bound."""
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    compilation = correction_context()
    prompt = json.loads(project_guide_compilation_prompt_bytes(compilation))
    del prompt["correction_predecessor"]
    previous_size = len(
        json.dumps(prompt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    config = compilation.runtime_configuration.model_copy(
        update={"maximum_manifest_bytes": previous_size}
    )
    compilation = compilation.model_copy(update={"runtime_configuration": config})
    runtime = OpenAIAgentSdkProjectGuideRuntime(config)

    async def forbidden(*args):
        pytest.fail("oversize correction reached provider execution")

    monkeypatch.setattr(runtime, "_run", forbidden)
    with pytest.raises(ProjectAgentRuntimeError, match="prompt exceeds"):
        await _compile(runtime, compilation)


def _large_correction_proposals(configuration):
    """Use generated prose and an authenticated predecessor, never retained drill input."""
    template = generated_result()
    requirement = template.requirements[0].model_dump(mode="json")

    def proposal(count):
        return type(template).model_validate(
            {
                **template.model_dump(mode="json"),
                "requirements": [
                    {
                        **requirement,
                        "requirement_id": f"observable_{index}",
                        "statement": ("The archive preserves bounded evidence. " * 23).strip(),
                        "classification_rationale": (
                            "The platform validates bounded archive evidence. " * 18
                        ).strip(),
                    }
                    for index in range(count)
                ],
            }
        )

    predecessor, candidate = proposal(100), proposal(30)
    original = correction_context()
    compilation = ProjectGuideCompilationContext.model_validate(
        {
            **original.model_dump(),
            "runtime_configuration": configuration,
            "correction_predecessor": predecessor,
            "correction_feedback": original.correction_feedback.model_copy(
                update={
                    "predecessor_result_hash": canonical_json_hash(
                        predecessor.model_dump(mode="json")
                    ),
                }
            ),
        }
    )
    return compilation, candidate


@pytest.mark.parametrize("explicit_limit", [None, 256_000], ids=["default", "explicit_limit"])
async def test_large_manager_correction_reaches_review_with_default_envelope(
    monkeypatch, explicit_limit
):
    """The default fits a full correction; an explicit smaller bound still stops review."""
    from agents import Runner

    monkeypatch.delenv("WORKSTREAM_PROJECT_AGENT_MAX_MANIFEST_BYTES", raising=False)
    settings = Settings(
        _env_file=None,
        project_agent_runtime="openai_agents_sdk",
        project_agent_runtime_options={},
        project_agent_model_provider="openai",
        project_agent_model="test-model",
        project_agent_model_api="responses",
    )
    configuration = project_guide_runtime_configuration(
        settings,
        adapter_profile_builder=partial(
            build_project_guide_adapter_profile, settings.project_agent_runtime
        ),
    )
    if explicit_limit is not None:
        configuration = configuration.model_copy(update={"maximum_manifest_bytes": explicit_limit})
    compilation, candidate = _large_correction_proposals(configuration)
    original_prompt = project_guide_compilation_prompt_bytes(compilation)
    assert len(original_prompt) < 256_000
    prompts = []

    async def run(agent, prompt, **kwargs):
        prompts.append(json.loads(prompt))
        assert explicit_limit is None or len(prompts) == 1, "oversized review reached provider"
        await _open_prompt_documents(agent, prompt)
        return _sdk_result(agent, candidate)

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)
    if explicit_limit is not None:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError):
            await _compile(runtime, compilation)
        assert len(prompts) == 1
    else:
        assert await _compile(runtime, compilation) == candidate
        assert len(prompts) == 2
        assert prompts[1]["phase"] == "coverage_review"
        assert prompts[1]["guide_setup_context"] == json.loads(original_prompt)
        assert prompts[1]["candidate_proposal"] == _provider_payload(candidate)
        assert 256_000 < len(json.dumps(prompts[1], separators=(",", ":")).encode()) < 512_000
        assert (
            settings.project_agent_max_manifest_bytes
            == configuration.maximum_manifest_bytes
            == runtime_configuration().maximum_manifest_bytes
            == 512_000
        )
