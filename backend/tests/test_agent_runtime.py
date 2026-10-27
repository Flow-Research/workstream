"""One replaceable runtime, exact configuration custody, and untrusted output tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import httpx2
import pytest
from pydantic import ValidationError

from app.adapters.project_agents import build_project_guide_adapter_profile
from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.core.config import Settings
from app.core.project_agents import (
    project_guide_runtime_configuration,
)
from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS
from app.interfaces.guide_document_tools import GuideDocumentToolResult
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
    canonical_project_guide_compilation_context_bytes,
    invalid_compilation_failure_code,
    project_guide_compilation_prompt_bytes,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.interfaces.setup_model_proxy import SetupModelProxyReply
from app.modules.projects.api.guide_documents import GuideDocumentManifest
from tests.projects.guide_compilation.helpers import (
    SOURCE_SHA256,
    context,
    ids,
    runtime_configuration,
    valid_specification,
)
from tests.projects.guide_compilation.helpers import (
    generated_result as result,
)


@pytest.fixture(autouse=True)
def model_credentials(monkeypatch):
    """Use a test-only credential; SDK execution is replaced in every invocation test."""
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test-only")


async def _open_prompt_documents(agent, prompt, count=None):
    """Exercise the assigned-document tool in this Runner phase."""
    from agents.tool_context import ToolContext

    supplied = json.loads(prompt)
    material = supplied.get("guide_setup_context", supplied)["material"]
    for document in material["documents"][:count]:
        arguments = json.dumps({"handle": document["handle"]})
        await agent.tools[0].on_invoke_tool(
            ToolContext(context=None, tool_name="read_document",
                        tool_call_id="test-open", tool_arguments=arguments), arguments
        )


def _provider_payload(value=None):
    """Include nullable members required by the provider's strict JSON schema."""
    payload = (result() if value is None else value).model_dump(mode="json", exclude={"setup_notes"})
    for requirement in payload["requirements"]:
        requirement.setdefault("classification_rationale", None)
        requirement.setdefault("check_specification", None)
        if requirement["check_specification"] is not None:
            for item in requirement["check_specification"]["inputs"]:
                item.setdefault("relative_path", None)
                item.setdefault("evaluation_context_roles", None)
    return payload


def _provider_specification():
    """Include explicit null paths required by the provider schema."""
    specification = valid_specification().model_dump(mode="json")
    for item in specification["inputs"]:
        item.setdefault("relative_path", None)
        item.setdefault("evaluation_context_roles", None)
    return specification


def _sdk_result(agent, value=None):
    """Return the result of the active phase parser, as the SDK does."""
    return SimpleNamespace(final_output=agent.output_type.validate_json(
        json.dumps(_provider_payload(value))
    ))


class _TestModelSession:
    maximum_output_tokens = 4096
    reasoning_effort = "medium"
    text_verbosity = "low"

    def __init__(self, dispatch=None):
        self._dispatch = dispatch

    async def dispatch(self, phase, body):
        if self._dispatch is None:
            raise AssertionError("test unexpectedly dispatched a model request")
        response = await self._dispatch(phase, body)
        return SetupModelProxyReply(
            outcome="completed",
            call_index=0,
            status_code=response.status_code,
            response_json=json.dumps(
                response.json(), sort_keys=True, separators=(",", ":")
            ),
            response_headers=(),
            failure_code=None,
            session_exhausted=False,
        )


async def _compile(
    runtime,
    compilation_context,
    *,
    document_text="Assigned guide text.",
    model=None,
):
    """Supply scripted prior document access and always release circuit admission."""
    opened = {
        compilation_context.material.handle_for(document)
        for document in compilation_context.material.documents
    }

    async def opened_handles():
        return frozenset(opened)

    tool_calls = 0
    tool_output_characters = 0

    async def read_document(handle, *, offset=0, limit=16000):
        nonlocal tool_calls, tool_output_characters
        if tool_calls >= compilation_context.runtime_configuration.maximum_tool_calls:
            raise ValueError("guide document tool call budget exceeded")
        tool_calls += 1
        document = next(
            item
            for item in compilation_context.material.documents
            if compilation_context.material.handle_for(item) == handle
        )
        opened.add(handle)
        text = document_text[offset:offset + limit]
        total = tool_output_characters + len(text)
        if (
            total
            > compilation_context.runtime_configuration.maximum_tool_output_characters
        ):
            raise ValueError("guide document tool output budget exceeded")
        tool_output_characters = total
        return GuideDocumentToolResult(
            handle=handle,
            source_item_id=document.source_item_id,
            document_version_id=document.ingest_id,
            sha256=document.sha256,
            operation="read",
            text=text,
            locators=(),
            next_offset=None,
            total_characters=len(document_text),
        )

    async def search_document(handle, query, *, offset=0, limit=20):
        value = await read_document(handle, offset=offset, limit=limit)
        return value.model_copy(update={
            "operation": "search", "text": value.text if query in value.text else "",
        })

    capabilities = SimpleNamespace(
        tools=SimpleNamespace(
            opened_handles=opened_handles,
            read_document=read_document,
            search_document=search_document,
        ),
        model=model or _TestModelSession(),
    )
    runtime.admit_execution()
    try:
        return await runtime.compile_project_guide(compilation_context, capabilities)
    finally:
        await runtime.aclose()


def test_unified_compilation_instructions_preserve_untrusted_and_lifecycle_boundaries():
    for text in ("untrusted", "PRE", "POST", "ProjectGuideCompilationAgent"):
        assert text in PROJECT_GUIDE_INSTRUCTIONS


def test_runtime_never_requires_provider_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    assert runtime.identity.provider_key == "openai_agents_sdk"


def test_configuration_concerns_are_independent_and_secret_free():
    settings = Settings(
        project_agent_model="configured-model", project_agent_instructions="Trusted instructions."
    )
    configuration = project_guide_runtime_configuration(
        settings,
        adapter_profile_builder=partial(
            build_project_guide_adapter_profile, settings.project_agent_runtime
        ),
    )
    assert configuration.model == "configured-model"
    assert configuration.instructions == "Trusted instructions."
    assert configuration.runtime_key == "openai_agents_sdk"
    snapshot = configuration.model_dump_json()
    assert all(
        value not in snapshot
        for value in ("unit-test-only", "api.openai.com", "openrouter.ai")
    )
    assert (
        configuration.instructions_sha256
        == "sha256:" + hashlib.sha256(b"Trusted instructions.").hexdigest()
    )


def test_adapter_profile_is_closed_effective_sdk_configuration():
    from app.adapters.project_agents.openai_profile import (
        OPENAI_AGENTS_SDK_VERSION,
        OPENAI_SDK_VERSION,
        require_openai_agents_sdk_adapter_profile,
    )
    from app.interfaces.project_guide_runtime import canonical_adapter_profile

    profile = build_project_guide_adapter_profile(
        "openai_agents_sdk", {"request_timeout_seconds": 25}
    )
    assert profile["agents_sdk_version"] == OPENAI_AGENTS_SDK_VERSION
    assert profile["openai_sdk_version"] == OPENAI_SDK_VERSION
    assert profile["request_timeout_seconds"] == 25
    assert profile["store"] is False
    assert profile["tracing_disabled"] is True
    assert profile["provider_fallbacks_allowed"] is False
    assert profile["data_collection"] == "deny"
    assert profile["provider_plugin_disable_requests"] is True
    assert require_openai_agents_sdk_adapter_profile(profile).request_timeout_seconds == 25
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="unsupported"):
        build_project_guide_adapter_profile("openai_agents_sdk", {"base_url": "https://evil"})
    tampered = runtime_configuration().model_copy(update={
        "adapter_profile": canonical_adapter_profile(dict(profile) | {"store": True})
    })
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="profile"):
        OpenAIAgentSdkProjectGuideRuntime(tampered)


def test_profile_canonicalization_preserves_utf8_and_rejects_unstorable_null():
    from app.interfaces.project_guide_runtime import canonical_adapter_profile

    assert canonical_adapter_profile({"label": "Café 🧪"}) == '{"label":"Café 🧪"}'
    with pytest.raises(ValueError, match="null character"):
        canonical_adapter_profile({"label": "\x00"})


@pytest.mark.parametrize("model", ["openai/gpt-5.6-terra:online", "openrouter/auto"])
def test_openrouter_rejects_provider_routed_model_variants(monkeypatch, model):
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test-only")
    configuration = runtime_configuration().model_copy(
        update={
            "model_provider": "openrouter",
            "model_api": "chat_completions",
            "model": model,
        }
    )
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="routing"):
        OpenAIAgentSdkProjectGuideRuntime(configuration)


@pytest.mark.parametrize(
    "patch",
    [
        {"instructions_sha256": "sha256:" + "0" * 64},
        {"api_key": "not-allowed"}, {"timeout_seconds": True}, {"timeout_seconds": 0},
        {"maximum_manifest_bytes": 1_000_001}, {"maximum_documents": 101},
        {"request_timeout_seconds": 0}, {"maximum_retries": 6}, {"retry_jitter": 1},
        {"model": ""},
    ],
)
def test_runtime_snapshot_rejects_invalid_or_secret_bearing_shapes(patch):
    with pytest.raises(ValidationError):
        ProjectGuideRuntimeConfiguration.model_validate(
            runtime_configuration().model_dump() | patch
        )


def test_snapshot_changes_identity_but_is_absent_from_provider_user_prompt():
    original = context(ids())
    changed = original.model_copy(
        update={
            "runtime_configuration": original.runtime_configuration.model_copy(
                update={"model": "another-model"}
            )
        }
    )
    assert canonical_project_guide_compilation_context_bytes(
        original
    ) != canonical_project_guide_compilation_context_bytes(changed)
    assert project_guide_compilation_prompt_bytes(
        original
    ) == project_guide_compilation_prompt_bytes(changed)
    prompt = json.loads(project_guide_compilation_prompt_bytes(original))
    assert "runtime_configuration" not in prompt
    assert isinstance(prompt["material"]["documents"], list)
    assert "namespace_fingerprint" not in json.dumps(prompt)
    assert "provider_object_ref" not in json.dumps(prompt)


async def test_unified_compilation_uses_scoped_tools_and_strict_output(monkeypatch):
    import openai
    from agents import FunctionTool, Runner

    clients = []
    client_type = openai.AsyncOpenAI

    def create_client(**kwargs):
        client = client_type(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", create_client)
    configuration = runtime_configuration()
    compilation_context = context(ids())
    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append((agent, prompt, kwargs))
        await _open_prompt_documents(agent, prompt)
        assert agent.instructions == configuration.instructions
        assert len(agent.tools) == 2 and agent.handoffs == []
        assert all(isinstance(tool, FunctionTool) for tool in agent.tools)
        assert [tool.name for tool in agent.tools] == ["read_document", "search_document"]
        assert agent.model.model == configuration.model
        assert agent.output_type.is_strict_json_schema() is True
        assert kwargs["max_turns"] == (
            configuration.maximum_turns // 2 if len(calls) == 1
            else configuration.maximum_turns
        )
        assert kwargs["run_config"].tracing_disabled is True
        assert kwargs["run_config"].trace_include_sensitive_data is False
        assert agent.model_settings.store is False
        assert agent.model_settings.parallel_tool_calls is False
        assert agent.model_settings.extra_body is None
        assert agent.model_settings.reasoning.effort == "medium"
        assert agent.model_settings.verbosity == "low"
        assert agent.model_settings.retry.max_retries == 2
        assert agent.model_settings.context_management is None
        assert agent.model_settings.response_include is None
        supplied = json.loads(prompt)
        assert "runtime_configuration" not in supplied
        if len(calls) == 1:
            return _sdk_result(agent)
        assert supplied["phase"] == "coverage_review"
        assert supplied["guide_setup_context"] == json.loads(calls[0][1])
        assert "runtime_configuration" not in supplied["guide_setup_context"]
        assert "setup_notes" not in supplied["candidate_proposal"]
        return _sdk_result(agent)

    monkeypatch.setattr(Runner, "run", run)
    output = await _compile(OpenAIAgentSdkProjectGuideRuntime(configuration), compilation_context)
    assert output == result()
    assert len(calls) == 2 and len(clients) == 1
    assert calls[0][0] is calls[1][0]
    assert clients[0].max_retries == 0 and clients[0].is_closed()
    assert clients[0].timeout == 300
    assert str(clients[0].base_url).rstrip("/") == "https://model-proxy.invalid/v1"


async def test_actual_sdk_tool_loop_uses_only_openrouter_chat_and_neutral_tools(
    monkeypatch,
):
    """Exercise the installed SDK parser and function-tool loop over captured HTTP."""
    captured = []
    payload = json.dumps(_provider_payload())
    compilation = context(ids())
    document = compilation.material.documents[0]
    handle = compilation.material.handle_for(document)
    responses = iter(
        [
            _chat_tool_call("draft-read", "read_document", {"handle": handle}),
            _chat_text("draft", payload),
            _chat_tool_call("review-read", "read_document", {"handle": handle}),
            _chat_text("review", payload),
        ]
    )

    async def dispatch(phase, body):
        captured.append((phase, body))
        request = httpx2.Request("POST", "https://model-proxy.invalid/v1/chat/completions")
        return httpx2.Response(200, json=next(responses), request=request)

    clients, http_options = _patch_openai_transport(monkeypatch, dispatch)
    config = compilation.runtime_configuration.model_copy(
        update={
            "model_provider": "openrouter",
            "model_api": "chat_completions",
            "model": "openai/gpt-5.6-terra",
        }
    )
    compilation = compilation.model_copy(update={"runtime_configuration": config})
    output = await _compile(
        OpenAIAgentSdkProjectGuideRuntime(config),
        compilation,
        model=_TestModelSession(dispatch),
    )
    assert output == result()
    assert len(captured) == 4
    assert [phase for phase, _ in captured] == ["draft", "draft", "review", "review"]
    for _phase, body in captured:
        assert body["model"] == "openai/gpt-5.6-terra"
        assert body["store"] is False
        assert body["parallel_tool_calls"] is False
        assert body["reasoning_effort"] == "medium"
        assert body["verbosity"] == "low"
        assert body["provider"] == {
            "allow_fallbacks": False,
            "data_collection": "deny",
        }
        assert body["plugins"] == [
            {"id": plugin, "enabled": False}
            for plugin in (
                "web",
                "file-parser",
                "response-healing",
                "armor",
                "pareto-router",
                "context-compression",
            )
        ]
        assert [tool["function"]["name"] for tool in body["tools"]] == [
            "read_document",
            "search_document",
        ]
        encoded = json.dumps(body)
        assert all(token not in encoded for token in (
            "code_interpreter", "container", "file_search", "s3://", "unit-test-only"
        ))
    observed, client = clients[0]
    owned_http_client = observed.pop("http_client")
    assert owned_http_client is not None
    assert observed == {
        "api_key": "setup-model-proxy",
        "base_url": "https://model-proxy.invalid/v1",
        "max_retries": 0,
        "timeout": 300,
    }
    assert http_options == []
    assert client.is_closed()


@pytest.mark.parametrize("failure", ["malformed_schema", "provider_fault", "tool_bound"])
async def test_actual_sdk_http_failures_are_bounded_and_sanitized(monkeypatch, failure):
    """Exercise parser, provider and local tool-bound failures through the real Runner."""
    compilation = context(ids())
    handle = compilation.material.handle_for(compilation.material.documents[0])
    calls = []
    if failure == "malformed_schema":
        responses = iter([_chat_text(f"malformed-{index}", "{invalid") for index in range(3)])
    elif failure == "tool_bound":
        responses = iter([
            _chat_tool_call("first-read", "read_document", {"handle": handle}),
            _chat_tool_call("second-read", "read_document", {"handle": handle}),
        ])
    else:
        responses = None

    async def dispatch(_phase, body):
        calls.append(body["model"])
        request = httpx2.Request("POST", "https://model-proxy.invalid/v1/chat/completions")
        if failure == "provider_fault":
            return httpx2.Response(
                401,
                json={"error": {"message": "private", "type": "auth", "code": "invalid_api_key"}},
                request=request,
            )
        return httpx2.Response(200, json=next(responses), request=request)

    clients, _http_options = _patch_openai_transport(monkeypatch, dispatch)
    updates = {
        "model_provider": "openrouter",
        "model_api": "chat_completions",
        "model": "openai/gpt-5.6-terra",
    }
    if failure == "tool_bound":
        updates["maximum_tool_calls"] = 1
    config = compilation.runtime_configuration.model_copy(update=updates)
    compilation = compilation.model_copy(update={"runtime_configuration": config})
    expected = (
        ProjectGuideCompilationInvalidOutputError
        if failure == "malformed_schema"
        else ProjectAgentRuntimeError
    )
    with pytest.raises(expected) as caught:
        await _compile(
            OpenAIAgentSdkProjectGuideRuntime(config),
            compilation,
            model=_TestModelSession(dispatch),
        )
    assert "private" not in str(caught.value)
    assert len(calls) == {"malformed_schema": 3, "tool_bound": 2, "provider_fault": 1}[failure]
    assert clients[0][1].is_closed()


async def test_actual_sdk_http_request_is_cancelled_and_client_closed(monkeypatch):
    """Caller cancellation reaches the SDK transport and awaits client shutdown."""
    started = asyncio.Event()

    async def dispatch(_phase, _body):
        started.set()
        await asyncio.Event().wait()

    clients, _http_options = _patch_openai_transport(monkeypatch, dispatch)
    compilation = context(ids())
    config = compilation.runtime_configuration.model_copy(update={
        "model_provider": "openrouter",
        "model_api": "chat_completions",
        "model": "openai/gpt-5.6-terra",
    })
    compilation = compilation.model_copy(update={"runtime_configuration": config})
    task = asyncio.create_task(
        _compile(
            OpenAIAgentSdkProjectGuideRuntime(config),
            compilation,
            model=_TestModelSession(dispatch),
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert clients[0][1].is_closed()


def _patch_openai_transport(monkeypatch, dispatch):
    import openai

    client_type = openai.AsyncOpenAI
    clients = []
    http_options = []

    def create_http_client(**kwargs):
        http_options.append(kwargs)
        return httpx2.AsyncClient(transport=httpx2.MockTransport(dispatch))

    def create_client(**kwargs):
        observed = dict(kwargs)
        client = client_type(**kwargs)
        clients.append((observed, client))
        return client

    monkeypatch.setattr(openai, "DefaultAsyncHttpx2Client", create_http_client)
    monkeypatch.setattr(openai, "AsyncOpenAI", create_client)
    return clients, http_options


def _chat_tool_call(identifier, name, arguments):
    return {
        "id": f"chatcmpl-{identifier}",
        "object": "chat.completion",
        "created": 1_800_000_000,
        "model": "openai/gpt-5.6-terra",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": identifier,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _chat_text(identifier, text):
    return {
        "id": f"chatcmpl-{identifier}",
        "object": "chat.completion",
        "created": 1_800_000_000,
        "model": "openai/gpt-5.6-terra",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.parametrize("failure", ["provider", "cancelled", "oversized"])
async def test_coverage_review_failure_never_returns_unchecked_draft(monkeypatch, failure):
    """A successful candidate cannot bypass a failed or unbounded review phase."""
    from agents import Runner

    configuration = runtime_configuration()
    compilation = context(ids())
    if failure == "oversized":
        prompt_size = len(project_guide_compilation_prompt_bytes(compilation))
        configuration = configuration.model_copy(update={"maximum_manifest_bytes": prompt_size + 1})
        compilation = compilation.model_copy(update={"runtime_configuration": configuration})
    calls = []

    async def run(agent, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return _sdk_result(agent)
        if failure == "cancelled":
            raise asyncio.CancelledError("private review detail")
        if failure == "provider":
            raise RuntimeError("private review detail")
        pytest.fail("oversized review reached the provider")

    monkeypatch.setattr(Runner, "run", run)
    expected_error = (ProjectGuideCompilationInvalidOutputError
                      if failure == "oversized" else ProjectAgentRuntimeError)
    with pytest.raises(expected_error) as caught:
        await _compile(OpenAIAgentSdkProjectGuideRuntime(configuration), compilation)
    if failure == "oversized":
        assert caught.value.failure_code == "schema_invalid"
    assert "private" not in str(caught.value)
    assert calls == ([1] if failure == "oversized" else [1, 1])


@pytest.mark.parametrize("review_count", [0, 1, 2])
async def test_review_must_open_every_original_independently(monkeypatch, review_count):
    """Draft opens cannot stand in for source access during the fresh review."""
    from agents import Runner

    compilation = context(ids())
    original = compilation.material.documents[0]
    second = original.model_copy(update={
        "source_item_id": uuid4(), "ingest_id": uuid4(),
        "put_attempt_id": uuid4(), "item_order": original.item_order + 1,
    })
    compilation = compilation.model_copy(update={
        "material": compilation.material.model_copy(update={"documents": (original, second)})
    })
    candidate = result()
    requirement = candidate.requirements[0]
    second_reference = requirement.evidence_refs[0].model_copy(update={
        "source_item_id": second.source_item_id, "document_version_id": second.ingest_id,
    })
    candidate = candidate.model_copy(update={"requirements": (
        requirement.model_copy(update={
            "evidence_refs": (*requirement.evidence_refs, second_reference),
        }), *candidate.requirements[1:],
    )})
    phases = []

    async def run(agent, prompt, **kwargs):
        phases.append(1)
        if len(phases) == 1:
            await _open_prompt_documents(agent, prompt)
        else:
            await _open_prompt_documents(agent, prompt, review_count)
        return _sdk_result(agent, candidate)

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(compilation.runtime_configuration)
    if review_count == 2:
        assert await _compile(runtime, compilation) == candidate
    else:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _compile(runtime, compilation)
        assert caught.value.failure_code == "schema_invalid"
    assert phases == ([1, 1] if review_count == 2 else [1, 1, 1, 1])


@pytest.mark.parametrize("kind", ["mapping", "json", "model"])
async def test_unified_runtime_accepts_complete_sdk_output(monkeypatch, kind):
    output = result()
    value = (
        output.model_dump(mode="json", exclude={"setup_notes"})
        if kind == "mapping"
        else output.model_dump_json(exclude={"setup_notes"})
        if kind == "json"
        else output
    )

    async def run(*args):
        return value

    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    monkeypatch.setattr(runtime, "_run", run)
    assert await _compile(runtime, context(ids())) == output


@pytest.mark.parametrize(
    "patch, diagnostic, failure_code",
    [
        ({"agent_version": "wrong"}, "agent version is invalid", "schema_invalid"),
        ({"status": "guide_blocked"}, "blocked compilation requires blocking evidence", "schema_invalid"),
        ({"findings": [{"severity": "info", "code": "bad", "message": "token=secret123"}]},
         "model-produced text is unsafe", "unsafe_text"),
    ],
)
async def test_unified_runtime_rejects_invalid_provider_output(
    monkeypatch, patch, diagnostic, failure_code
):
    from app.adapters.project_agents.result_validation import validate_project_guide_runtime_result

    compilation = context(ids())
    output = _provider_payload() | patch
    opened = {compilation.material.handle_for(item) for item in compilation.material.documents}
    with pytest.raises(ValueError, match=diagnostic):
        validate_project_guide_runtime_result(compilation, output, opened)

    async def run(*args):
        return output

    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
        await _compile(runtime, compilation)
    assert caught.value.failure_code == failure_code


async def test_unified_runtime_rejects_omitted_output_member(monkeypatch):
    output = _provider_payload()
    del output["findings"]

    async def run(*args):
        return output

    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(
        ProjectGuideCompilationInvalidOutputError, match="invalid structured output"
    ):
        await _compile(runtime, context(ids()))


async def test_oversized_prompt_is_rejected_before_sdk_execution(monkeypatch):
    configuration = runtime_configuration().model_copy(update={"maximum_manifest_bytes": 1024})
    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)

    async def forbidden(*args):
        pytest.fail("oversized prompt reached provider")

    monkeypatch.setattr(runtime, "_run", forbidden)
    with pytest.raises(ProjectAgentRuntimeError, match="size limit"):
        await _compile(runtime,
            context(ids()).model_copy(update={"runtime_configuration": configuration})
        )


async def test_runtime_rejects_context_configuration_substitution(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def forbidden(*args):
        pytest.fail("different configuration reached provider")

    monkeypatch.setattr(runtime, "_run", forbidden)
    changed = context(ids()).model_copy(
        update={
            "runtime_configuration": runtime_configuration().model_copy(update={"model": "changed"})
        }
    )
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="configuration mismatch"):
        await _compile(runtime, changed)


@pytest.mark.parametrize(
    "error", [RuntimeError("private provider detail"), TimeoutError("private timeout")]
)
async def test_runtime_failure_is_sanitized(monkeypatch, error):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        raise error

    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectAgentRuntimeError) as caught:
        await _compile(runtime, context(ids()))
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__


async def test_unified_compilation_propagates_caller_cancellation(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    started = asyncio.Event()

    async def run(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime, "_run", run)
    task = asyncio.create_task(_compile(runtime, context(ids())))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_invalid_compilation_classifier_separates_unsafe_text_from_schema_errors():
    assert (
        invalid_compilation_failure_code(ValueError("model-produced text is unsafe"))
        == "unsafe_text"
    )
    assert invalid_compilation_failure_code(TypeError("unknown")) == "schema_invalid"


async def test_runtime_internal_cancellation_is_sanitized(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        raise asyncio.CancelledError("private provider cancellation")

    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectAgentRuntimeError, match="project guide run cancelled") as caught:
        await _compile(runtime, context(ids()))
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("kind, expected", [
    ("valid", None), ("malformed", "schema_invalid"),
    ("schema", "schema_invalid"), ("unsafe", "schema_invalid"),
])
@pytest.mark.parametrize("redacted", [True, False])
async def test_actual_sdk_parser_preserves_known_invalid_output(monkeypatch, kind, expected, redacted):
    """Exercise the installed SDK parser before the adapter receives any result."""
    from agents import Runner, _debug
    monkeypatch.setattr(_debug, "DONT_LOG_MODEL_DATA", redacted)
    payload = _provider_payload()
    if kind == "schema":
        payload["status"] = "not-a-status"
    if kind == "unsafe":
        payload["findings"] = [{"severity": "info", "code": "bad", "message": "token=secret123", "evidence_refs": []}]
    raw = "{invalid" if kind == "malformed" else json.dumps(payload)
    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(1)
        await _open_prompt_documents(agent, prompt)
        return SimpleNamespace(final_output=agent.output_type.validate_json(raw))

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    if expected is None:
        assert await _compile(runtime, context(ids())) == result()
    else:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _compile(runtime, context(ids()))
        assert caught.value.failure_code == expected
        assert "secret123" not in str(caught.value)
        assert caught.value.__suppress_context__
    assert calls == ([1, 1] if kind == "valid" else [1, 1, 1])


@pytest.mark.parametrize("include_dependency", [True, False])
async def test_sdk_parser_requires_declared_isolated_execution_dependency(
    monkeypatch, include_dependency
):
    """Reproduce the live handoff failure through the actual SDK parser."""
    from agents import Runner

    payload = _provider_payload()
    payload["status"] = "draft_ready_with_warnings"
    requirement = payload["requirements"][0]
    requirement["disposition"] = "post_submit_capability_gap"
    requirement["classification_rationale"] = "Repeated trials need background execution."
    requirement["platform_coverage"] = None
    specification = _provider_specification()
    specification.update(
        evaluation_method="isolated_execution",
        execution_mode="background",
        maximum_duration_seconds=120,
        runtime_dependencies=[
            {
                "dependency_id": "execution",
                "kind": "isolated_execution",
                "provisioning": "current_runner",
                "purpose": "Run the evaluation in an isolated environment.",
                "unavailable_code": "implementation_unavailable",
            }
        ]
        if include_dependency
        else [],
        infrastructure_failures=[
            {
                "code": "implementation_unavailable",
                "condition": "The isolated environment is unavailable.",
            }
        ],
    )
    requirement["check_specification"] = specification
    payload["capability_suggestions"] = [
        {
            "requirement_id": requirement["requirement_id"],
            "stage": "post_submit",
            "title": "Repeated trial evaluation",
            "rationale": "A project implementation must run the required trials.",
            "evidence_refs": requirement["evidence_refs"],
        }
    ]
    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(1)
        await _open_prompt_documents(agent, prompt)
        return SimpleNamespace(final_output=agent.output_type.validate_json(json.dumps(payload)))

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    if include_dependency:
        output = await _compile(runtime, context(ids()))
        assert (
            output.requirements[0].check_specification.runtime_dependencies[0].kind
            == "isolated_execution"
        )
        assert output.status == "draft_ready_with_warnings"
    else:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _compile(runtime, context(ids()))
        assert caught.value.failure_code == "schema_invalid"
    assert calls == ([1, 1] if include_dependency else [1, 1, 1])


async def test_unclassified_sdk_behavior_error_remains_unresolved(monkeypatch):
    """A generic SDK behavior error is not proof of structured-output rejection."""
    from agents import Runner
    from agents.exceptions import ModelBehaviorError

    async def run(*args, **kwargs):
        raise ModelBehaviorError("private provider detail")

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectAgentRuntimeError, match="project guide run failed"):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))


async def _capture_parser_error(runtime):
    """Capture outside the payload-owning test frame, as a runtime caller would."""
    try:
        await _compile(runtime, context(ids()))
    except ProjectGuideCompilationInvalidOutputError as error:
        return error
    pytest.fail("invalid SDK output did not raise")


@pytest.mark.parametrize("redacted", [True, False])
@pytest.mark.parametrize("phase", ["draft", "review"])
async def test_sdk_parser_error_drops_payload_tracebacks(monkeypatch, redacted, phase):
    """A diagnostic collector must not recover rejected output through the error graph."""
    from agents import Runner, _debug

    marker = "private-parser-output-79436"
    payload = _provider_payload()
    payload["findings"] = [{"severity": "info", "code": "bad", "message": f"token={marker}", "evidence_refs": []}]
    if phase == "draft":
        payload["status"] = marker
    raw = json.dumps(payload)
    monkeypatch.setattr(_debug, "DONT_LOG_MODEL_DATA", redacted)

    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(1)
        if phase == "review" and len(calls) == 1:
            await _open_prompt_documents(agent, prompt)
            return _sdk_result(agent)
        return SimpleNamespace(final_output=agent.output_type.validate_json(raw))

    monkeypatch.setattr(Runner, "run", run)
    error = await _capture_parser_error(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()))
    assert error.failure_code == "schema_invalid"
    assert calls == ([1, 1, 1, 1] if phase == "review" else [1, 1, 1])
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert marker not in str(current)
        traceback = current.__traceback__
        while traceback is not None:
            assert marker not in repr(traceback.tb_frame.f_locals)
            traceback = traceback.tb_next
        pending.extend(link for link in (current.__cause__, current.__context__) if link is not None)


async def _capture_runtime_failure(runtime):
    try:
        await _compile(runtime, context(ids()))
    except ProjectAgentRuntimeError as error:
        return error
    pytest.fail("runtime failure did not raise")


@pytest.mark.parametrize("boundary", ["provider", "post_parser_validation"])
async def test_sanitized_error_graph_drops_provider_and_invalid_values(monkeypatch, boundary):
    marker = "private-runtime-output-78219"
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        if boundary == "provider":
            raise RuntimeError(marker)
        payload = result().model_dump(mode="json")
        payload["setup_notes"] = ["token=" + marker]
        return payload

    monkeypatch.setattr(runtime, "_run", run)
    error = (await _capture_runtime_failure(runtime) if boundary == "provider"
             else await _capture_parser_error(runtime))
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert marker not in str(current)
        frame = current.__traceback__
        while frame is not None:
            assert marker not in repr(frame.tb_frame.f_locals)
            frame = frame.tb_next
        pending.extend(link for link in (current.__cause__, current.__context__) if link is not None)


def test_sdk_output_schema_exposes_the_identifier_rule_to_the_model():
    """The provider sees the same bounded lowercase rule that parsing enforces."""
    import re

    from agents import AgentOutputSchema

    from app.interfaces.project_agents import ProjectGuideCompilationResult

    schema = AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
    for owner, field in (
        ("AtomicGuideRequirement", "requirement_id"),
        ("PreSubmissionBindingProposal", "requirement_id"),
        ("PreSubmissionBindingProposal", "capability_id"),
        ("PreSubmissionBindingProposal", "capability_version"),
        ("PlatformCoverageRef", "capability_id"),
        ("PlatformCoverageRef", "capability_version"),
        ("CapabilityParameter", "name"),
        ("CompilationFinding", "code"),
    ):
        pattern = schema["$defs"][owner]["properties"][field]["pattern"]
        assert re.fullmatch(pattern, "r001")
        assert not re.fullmatch(pattern, "R001")
        assert not re.fullmatch(pattern, "r" * 101)
        assert not re.fullmatch(pattern, "r/001")


def test_sdk_output_schema_has_one_intake_configuration_and_separate_post_parameters():
    """Actual SDK schema cannot ask the model for two conflicting intake policies."""
    from agents import AgentOutputSchema

    from app.interfaces.project_agents import ProjectGuideCompilationResult

    schema = AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
    intake = schema["$defs"]["SubmissionArtifactPolicyProposal"]
    for field in ("maximum_file_size_bytes", "maximum_package_size_bytes"):
        assert field in intake["required"]
        assert {item["type"] for item in intake["properties"][field]["anyOf"]} == {"integer", "null"}
    pre = schema["$defs"]["PreSubmissionBindingProposal"]
    post = schema["$defs"]["PostSubmissionBindingProposal"]
    assert pre["additionalProperties"] is False
    assert "parameters" in pre["properties"]
    assert pre["properties"]["parameters"]["maxItems"] == 50
    assert post["properties"]["parameters"]["maxItems"] == 50
    assert "parameters" in post["properties"]
    parameter_values = schema["$defs"]["CapabilityParameter"]["properties"]["value"]["anyOf"]
    array = next(item for item in parameter_values if item.get("type") == "array")
    assert array["minItems"] == 1
    assert array["maxItems"] == 50


def test_default_instructions_advertise_contextual_output_constraints():
    """Keep rules the JSON schema cannot express visible to the model."""
    from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS

    instructions = " ".join(PROJECT_GUIDE_INSTRUCTIONS.split())
    for rule in (
        "The PM sets review mode, revision caps/windows",
        "Ignore administrative clauses when extracting checks",
        "PRE: static inspection or other bounded work",
        "60 seconds",
        "All model evaluation is POST",
        "File presence is static",
        "Project layout, required files, metadata",
        "Missing implementations are same-stage capability gaps",
        "Each supported/gap PRE/POST requirement needs the complete typed check_specification",
        "Return exactly one JSON object",
        "At most two invalid-output corrections",
        "Reopen the assigned originals",
        "Leave unspecified project",
        "source_item_id, document_version_id and sha256",
        "model_evaluation requires model_service",
        "registered project image and its exact approved profile",
    ):
        assert rule in instructions
    assert "setup_notes" not in instructions



@pytest.mark.parametrize("blocked_phase", ["draft", "review"])
async def test_whole_run_deadline_cancels_once_and_closes_without_reinvocation(
    monkeypatch, blocked_phase
):
    """The whole-run budget interrupts an outstanding request before its own timeout."""
    from agents import Runner
    events = []

    async def blocked_run(agent, *args, **kwargs):
        events.append("run")
        if blocked_phase == "review" and events.count("run") == 1:
            return _sdk_result(agent)
        try:
            await asyncio.Event().wait()
        finally:
            events.append("cancelled")

    monkeypatch.setattr(Runner, "run", blocked_run)
    config = runtime_configuration().model_copy(update={"timeout_seconds": 1})
    runtime = OpenAIAgentSdkProjectGuideRuntime(config)
    started = asyncio.get_running_loop().time()
    try:
        with pytest.raises(ProjectAgentRuntimeError, match="project guide run timed out") as caught:
            await _compile(runtime, context(ids()).model_copy(update={"runtime_configuration": config}))
        assert 0.8 <= asyncio.get_running_loop().time() - started < 5
        assert events == (
            ["run", "run", "cancelled"] if blocked_phase == "review"
            else ["run", "cancelled"]
        )
        assert caught.value.__suppress_context__
    finally:
        await runtime.aclose()


# Manager-authored (provider-free) runtime ---------------------------------

_MANAGER_PAIR = {"runtime_key": "manager_authored", "model_provider": "none",
                 "model_api": "none", "model": "none"}


@pytest.mark.parametrize(
    "patch",
    [
        {"model_provider": "none", "model_api": "none"},
        {"model_provider": "none"},
        {"model_api": "none"},
        {"model": "none"},
    ],
)
def test_provider_none_is_only_valid_for_the_manager_authored_runtime(patch):
    with pytest.raises(ValidationError, match="guide runtime"):
        ProjectGuideRuntimeConfiguration.model_validate(runtime_configuration().model_dump() | patch)
    with pytest.raises(ValidationError, match="guide runtime"):
        Settings(**{"project_agent_" + ("runtime" if key == "runtime_key" else key): value
                    for key, value in (runtime_configuration().model_dump(
                        include={"runtime_key", "model_provider", "model_api", "model"}) | patch).items()})


def test_manager_authored_settings_snapshot_records_absent_inference():
    settings = Settings(project_agent_runtime="manager_authored", project_agent_model_provider="none",
                        project_agent_model_api="none", project_agent_model="none")
    configuration = project_guide_runtime_configuration(
        settings,
        adapter_profile_builder=partial(
            build_project_guide_adapter_profile, settings.project_agent_runtime
        ),
    )
    assert configuration.model_dump(include=set(_MANAGER_PAIR)) == _MANAGER_PAIR
    assert not configuration.uses_inference
    assert configuration.adapter_profile_values() == {}
    assert ProjectGuideRuntimeConfiguration.model_validate(configuration.model_dump()) == configuration
    default_settings = Settings()
    default = project_guide_runtime_configuration(
        default_settings,
        adapter_profile_builder=partial(
            build_project_guide_adapter_profile, default_settings.project_agent_runtime
        ),
    )
    assert (default.runtime_key, default.model_provider, default.model_api) == (
        "openai_agents_sdk", "openrouter", "chat_completions")
    assert default.uses_inference


def _manager_material(rules: bytes, *, extra: tuple[bytes, ...] = (), source_ids=()):
    """Return a context with one PDF original, the rules document and optional Markdown."""
    from tests.projects.guide_compilation.helpers import (
        SOURCE_BYTES,
        manager_runtime_configuration,
    )

    base = context(ids(), configuration=manager_runtime_configuration())
    pdf = base.material.documents[0]
    bodies = {pdf.sha256: SOURCE_BYTES}
    documents = [pdf]
    chosen = iter(source_ids)
    for order, body in enumerate((rules, *extra), start=1):
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        bodies[digest] = body
        documents.append(pdf.model_copy(update={
            "source_item_id": next(chosen, None) or uuid4(), "ingest_id": uuid4(),
            "item_order": order, "put_attempt_id": uuid4(), "sha256": digest,
            "byte_count": len(body), "media_type": "text/markdown",
        }))
    material = GuideDocumentManifest.model_validate(
        base.material.model_copy(update={"documents": tuple(documents)}).model_dump())
    return base.model_copy(update={"material": material}), bodies


class _DirectGrant:
    """Scripted neutral document tools recording each bounded read."""

    def __init__(self, compilation_context, bodies, *, fail=False):
        manifest = compilation_context.material
        self.opened, self.recorded = [], []

        async def read_document(handle, *, offset=0, limit=16000):
            if fail:
                raise RuntimeError("private storage detail")
            self.opened.append(handle)
            document = next(item for item in manifest.documents if manifest.handle_for(item) == handle)
            self.recorded.append(handle)
            text = bodies[document.sha256].decode("utf-8", errors="replace")
            fragment = text[offset:offset + limit]
            next_offset = offset + len(fragment) if offset + len(fragment) < len(text) else None
            return GuideDocumentToolResult(
                handle=handle,
                source_item_id=document.source_item_id,
                document_version_id=document.ingest_id,
                sha256=document.sha256,
                operation="read",
                text=fragment,
                locators=(),
                next_offset=next_offset,
                total_characters=len(text),
            )

        async def search_document(*_args, **_kwargs):
            pytest.fail("manager-authored runtime searched document text")

        async def opened_handles():
            return frozenset(self.recorded)

        self.capabilities = SimpleNamespace(
            tools=SimpleNamespace(
                read_document=read_document,
                search_document=search_document,
                opened_handles=opened_handles,
            ),
        )


def _rules(**overrides) -> bytes:
    body = {
        "format": "workstream.project_guide_rules.v1",
        "status": "draft_ready",
        "findings": [{"severity": "info", "code": "guide.ready", "message": "Guide is complete.",
                      "evidence_refs": [{"document": SOURCE_SHA256, "start_page": 1, "end_page": 2}]}],
        "submission_artifact_policy": {"maximum_file_size_bytes": 1000,
                                       "maximum_package_size_bytes": 10000,
                                       "required_artifacts": ["submission"]},
        "requirements": [{
            "requirement_id": "guide.context", "statement": "Use the project guide.",
            "disposition": "informational", "platform_coverage": None,
            "classification_rationale": "This identifies the governing guide for the work.",
            "check_specification": None,
            # The rules document itself supplies this background requirement.
            # PDF coverage remains owned by findings, including negative cases.
            "evidence_refs": [],
        }], "pre_submit_bindings": [], "post_submit_bindings": [],
        "capability_suggestions": [], "setup_notes": [],
    } | overrides
    return json.dumps(body).encode()


async def _manager_compile(compilation_context, grant):
    from app.adapters.project_agents import create_project_guide_runtime

    runtime = create_project_guide_runtime(compilation_context.runtime_configuration)
    runtime.admit_execution()
    try:
        return await runtime.compile_project_guide(compilation_context, grant.capabilities)
    finally:
        await runtime.aclose()


async def test_manager_authored_runtime_converts_rules_without_credentials_or_network(monkeypatch):
    import socket

    from app.adapters.project_agents.manager_authored import ManagerAuthoredProjectGuideRuntime

    monkeypatch.delenv("OPENAI_API_KEY")

    def no_network(*args, **kwargs):
        pytest.fail("manager-authored runtime opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    notes_id = uuid4()
    rules = _rules(findings=[
        {"severity": "info", "code": "guide.ready", "message": "Guide is complete.",
         "evidence_refs": [{"document": SOURCE_SHA256, "start_page": 1, "end_page": 2}]},
        {"severity": "info", "code": "guide.notes", "message": "Reviewer notes are present.",
         "evidence_refs": [{"document": f"{notes_id}.md", "section": "Reviewer notes"}]},
    ])
    compilation_context, bodies = _manager_material(
        rules, extra=(b"# Reviewer notes\n\nPlain guide prose.",), source_ids=(None, notes_id))
    material = compilation_context.material
    pdf, rules_doc, notes = material.documents
    grant = _DirectGrant(compilation_context, bodies)
    from app.adapters.project_agents import create_project_guide_runtime

    runtime = create_project_guide_runtime(compilation_context.runtime_configuration)
    assert isinstance(runtime, ManagerAuthoredProjectGuideRuntime)
    assert runtime.identity == compilation_context.runtime_configuration.adapter_identity
    outcome = await _manager_compile(compilation_context, grant)

    handles = [material.handle_for(item) for item in material.documents]
    assert grant.opened == grant.recorded == handles
    assert outcome.status == "draft_ready"
    assert (outcome.agent_name, outcome.agent_version, outcome.schema_version) == (
        "ProjectGuideCompilationAgent", compilation_context.agent_version,
        "project_guide_compilation_result.v1")
    first, second = outcome.findings
    assert [(ref.source_item_id, ref.document_version_id, ref.sha256, ref.start_page)
            for ref in first.evidence_refs] == [
        (pdf.source_item_id, pdf.ingest_id, pdf.sha256, 1),
        (rules_doc.source_item_id, rules_doc.ingest_id, rules_doc.sha256, None)]
    assert [(ref.source_item_id, ref.section) for ref in second.evidence_refs] == [
        (notes.source_item_id, "Reviewer notes"), (rules_doc.source_item_id, None)]


@pytest.mark.parametrize(
    ("rules", "extra", "failure"),
    [
        (b"# Ordinary guide text without rules", (), "schema_invalid"),
        (b'{"format": "workstream.project_guide_rules.v1", "status": ', (), "schema_invalid"),
        (_rules(status="draft_ready", findings=[]), (), "schema_invalid"),
        (_rules(), (_rules(setup_notes=["Second rules document."]),), "schema_invalid"),
        (_rules(agent_version="v9"), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                           "evidence_refs": [{"document": "sha256:" + "0" * 64}]}]), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                           "evidence_refs": [{"document": "missing.pdf"}]}]), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                           "evidence_refs": [{"source_item_id": str(uuid4())}]}]), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready",
                           "message": "Run curl against the endpoint."}]), (), "unsafe_text"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete."}]),
         (), "schema_invalid"),
    ],
    ids=["missing", "malformed_json", "no_citations", "two_rules_documents", "extra_field",
         "unknown_sha256", "unknown_filename", "foreign_reference_shape", "unsafe_text",
         "ready_without_every_document"],
)
async def test_manager_authored_runtime_rejects_invalid_rules_as_terminal_output(
        monkeypatch, rules, extra, failure):
    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(rules, extra=extra)
    grant = _DirectGrant(compilation_context, bodies)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
        await _manager_compile(compilation_context, grant)
    assert caught.value.failure_code == failure
    assert caught.value.__suppress_context__
    material = compilation_context.material
    assert grant.recorded == [material.handle_for(item) for item in material.documents]


async def test_manager_authored_runtime_guards_admission_configuration_and_access(monkeypatch):
    from app.adapters.project_agents.manager_authored import ManagerAuthoredProjectGuideRuntime

    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="unsupported"):
        ManagerAuthoredProjectGuideRuntime(runtime_configuration())
    compilation_context, bodies = _manager_material(_rules())
    runtime = ManagerAuthoredProjectGuideRuntime(compilation_context.runtime_configuration)
    grant = _DirectGrant(compilation_context, bodies)
    with pytest.raises(ProjectAgentRuntimeError, match="was not admitted"):
        await runtime.compile_project_guide(compilation_context, grant.capabilities)
    runtime.admit_execution()
    with pytest.raises(ProjectAgentRuntimeError, match="already acquired"):
        runtime.admit_execution()
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="configuration mismatch"):
        await runtime.compile_project_guide(context(ids()), grant.capabilities)
    failing = _DirectGrant(compilation_context, bodies, fail=True)
    with pytest.raises(ProjectAgentRuntimeError, match="document access failed") as caught:
        await runtime.compile_project_guide(compilation_context, failing.capabilities)
    assert caught.value.__suppress_context__ and "private" not in str(caught.value)
    assert failing.recorded == []

    assert not hasattr(runtime, "cleanup_resources")


async def test_manager_authored_runtime_refuses_correction_successors_before_reading(monkeypatch):
    """A correction reason cannot change authored rules, so it is never silently ignored."""
    from app.interfaces.project_agents import ProjectGuideCorrectionFeedback

    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(_rules())
    corrected = compilation_context.model_copy(update={
        "correction_feedback": ProjectGuideCorrectionFeedback(
            operation_id=uuid4(), predecessor_compilation_id=uuid4(),
            predecessor_result_hash="sha256:" + "1" * 64, target_digest="sha256:" + "2" * 64,
            reason="Require a test report.")})
    grant = _DirectGrant(corrected, bodies)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
        await _manager_compile(corrected, grant)
    assert caught.value.failure_code == "schema_invalid"
    assert grant.opened == grant.recorded == []


async def test_manager_authored_runtime_retains_only_the_first_parsed_rules_document(monkeypatch):
    """Later rules documents already invalidate the guide, so their bodies are not kept."""
    from app.adapters.project_agents.manager_authored import _read_rules_documents

    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(
        _rules(), extra=(_rules(setup_notes=["Second."]), _rules(setup_notes=["Third."])))
    grant = _DirectGrant(compilation_context, bodies)
    candidates = await _read_rules_documents(compilation_context, grant.capabilities)
    assert [document for document, _ in candidates] == list(compilation_context.material.documents[1:])
    assert isinstance(candidates[0][1], dict)
    assert [parsed for _, parsed in candidates[1:]] == [None, None]
    material = compilation_context.material
    assert grant.recorded == [material.handle_for(item) for item in material.documents]


async def test_manager_authored_runtime_rejects_rules_the_citation_rule_would_not_catch(monkeypatch):
    """Exactly-one and resolvable-reference rules fail on their own, not via coverage."""
    monkeypatch.delenv("OPENAI_API_KEY")
    valid_ref = {"document": SOURCE_SHA256}
    first_id, second_id = uuid4(), uuid4()
    # Each rules document cites the other, so whichever one a regression chose,
    # every document would be cited and only the exactly-one rule can reject.
    duplicated, bodies = _manager_material(
        _rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                          "evidence_refs": [valid_ref, {"document": f"{second_id}.md"}]}]),
        extra=(_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                                 "evidence_refs": [valid_ref, {"document": f"{first_id}.md"}]}]),),
        source_ids=(first_id, second_id))
    unresolved, unresolved_bodies = _manager_material(_rules(findings=[
        {"severity": "info", "code": "guide.ready", "message": "Complete.",
         "evidence_refs": [valid_ref, {"document": "sha256:" + "0" * 64}]}]))
    for compilation_context, documents in ((duplicated, bodies), (unresolved, unresolved_bodies)):
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _manager_compile(compilation_context, _DirectGrant(compilation_context, documents))
        assert caught.value.failure_code == "schema_invalid"


async def test_manager_authored_runtime_ignores_non_candidates_and_survives_deep_nesting(monkeypatch):
    from app.adapters.project_agents.manager_authored import MAXIMUM_RULES_DOCUMENT_BYTES

    monkeypatch.delenv("OPENAI_API_KEY")
    nested = b'{"format": "workstream.project_guide_rules.v1", "x": ' + b"[" * 200_000 + b"]" * 200_000 + b"}"
    oversized = _rules(setup_notes=["Padding."]).replace(
        b'"setup_notes"', b'"pad": "' + b" " * MAXIMUM_RULES_DOCUMENT_BYTES + b'", "setup_notes"')
    for body in (nested, oversized):
        compilation_context, bodies = _manager_material(body)
        grant = _DirectGrant(compilation_context, bodies)
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _manager_compile(compilation_context, grant)
        assert caught.value.failure_code == "schema_invalid"
        assert set(grant.recorded) == {
            compilation_context.material.handle_for(item)
            for item in compilation_context.material.documents
        }
    # Rules JSON stored under a non-Markdown media type is read but never treated as rules.
    compilation_context, bodies = _manager_material(_rules())
    pdf, rules_doc = compilation_context.material.documents
    relabeled = compilation_context.material.model_copy(update={"documents": (
        pdf, rules_doc.model_copy(update={"media_type": "application/pdf"}))})
    compilation_context = compilation_context.model_copy(update={"material": relabeled})
    with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
        await _manager_compile(compilation_context, _DirectGrant(compilation_context, bodies))
    assert caught.value.failure_code == "schema_invalid"


async def test_manager_authored_runtime_refuses_a_substituted_document_version(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(_rules())
    grant = _DirectGrant(compilation_context, bodies)

    async def substituted(handle, *, offset=0, limit=16000):
        document = compilation_context.material.documents[0]
        return GuideDocumentToolResult(
            handle=handle,
            source_item_id=document.source_item_id,
            document_version_id=uuid4(),
            sha256=document.sha256,
            operation="read",
            text="substituted",
            locators=(),
            next_offset=None,
            total_characters=11,
        )

    grant.capabilities.tools.read_document = substituted
    with pytest.raises(ProjectAgentRuntimeError, match="document access failed"):
        await _manager_compile(compilation_context, grant)
    assert grant.recorded == []
