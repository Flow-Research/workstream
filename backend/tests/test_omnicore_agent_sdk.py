"""Actual OmniCoreAgent loop qualification over the closed synthetic transport."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from contextlib import suppress
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from app.adapters.project_agents.omnicore_agent import (
    OmniCoreAgentProjectGuideRuntime,
    _GuardRejection,
    _LoopbackOpenRouterGuard,
    _MODEL_TOOLS,
    _TEST_UPSTREAM_AUTHORITY,
    _rebuild_provider_success_body,
    _run_native_agent,
    _unique_object,
    _validated_test_upstream,
    _validate_request_body,
)
from app.adapters.model_usage.openrouter import openrouter_request_options
from app.adapters.project_agents.provider_resilience import (
    ProviderCircuit,
    ProviderCircuitOpen,
)
from app.adapters.project_agents.omnicore_profile import (
    LITELLM_VERSION,
    OMNICORE_CIRCUIT_FAILURE_THRESHOLD,
    OMNICORE_OPENAI_VERSION,
    OMNICOREAGENT_VERSION,
    OMNICORE_QUALIFICATION_MODEL,
    _require_sdk_versions,
    build_omnicore_agent_adapter_profile,
    require_omnicore_agent_adapter_profile,
)
from app.interfaces.guide_document_tools import GuideDocumentToolResult
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
    project_guide_compilation_prompt_bytes,
)
from app.interfaces.project_guide_runtime import canonical_adapter_profile
from app.modules.projects.api.task_examples import validate_task_examples
from tests.projects.guide_compilation.helpers import (
    context,
    generated_result,
    ids,
)
from tests.test_guide_compilation_draft import (
    _invalid_canonical_payload,
    _rejected_semantic_payload,
)


class _SyntheticOpenRouter:
    """Bounded loopback provider capturing only generated test material."""

    def __init__(
        self,
        *,
        handle: str,
        final_output: str,
        final_outputs: tuple[str, ...] | None = None,
        skip_tool_on_correction: bool = False,
        retry_statuses: tuple[int, ...] = (),
        always_status: int | None = None,
        error_message: str = "synthetic persistent provider failure",
        tool_calls_before_final: int = 1,
        finish_reason_override: str | None = None,
        response_content_type: str = "application/json",
        response_padding_bytes: int = 0,
        hang: bool = False,
    ) -> None:
        self.handle = handle
        self.final_output = final_output
        self.final_outputs = final_outputs
        self.skip_tool_on_correction = skip_tool_on_correction
        self.retry_statuses = retry_statuses
        self.always_status = always_status
        self.error_message = error_message
        self.tool_calls_before_final = tool_calls_before_final
        self.finish_reason_override = finish_reason_override
        self.response_content_type = response_content_type
        self.response_padding_bytes = response_padding_bytes
        self.hang = hang
        self.requests: list[tuple[dict[str, str], dict[str, object]]] = []
        self.received = asyncio.Event()
        self.disconnected = asyncio.Event()
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def url(self) -> str:
        assert self._server is not None and self._server.sockets
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/chat/completions"

    async def __aenter__(self) -> _SyntheticOpenRouter:
        self._server = await asyncio.start_server(self._accepted, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _accepted(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self._handle(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            lines = head[:-4].decode("ascii").split("\r\n")
            headers = {}
            for line in lines[1:]:
                name, value = line.split(":", 1)
                headers[name.lower()] = value.strip()
            body = json.loads(await reader.readexactly(int(headers["content-length"])))
            self.requests.append((headers, body))
            self.received.set()
            if self.hang:
                await reader.read()
                self.disconnected.set()
                return
            if self.always_status is not None:
                await self._respond(
                    writer,
                    self.always_status,
                    {"error": {"message": self.error_message}},
                    extra_headers={"Retry-After": "0"},
                    content_type=self.response_content_type,
                )
                return
            if len(self.requests) <= len(self.retry_statuses):
                status = self.retry_statuses[len(self.requests) - 1]
                await self._respond(
                    writer,
                    status,
                    {"error": {"message": "synthetic retryable provider failure"}},
                    extra_headers={"Retry-After": "0"},
                    content_type=self.response_content_type,
                )
                return
            successful_index = len(self.requests) - len(self.retry_statuses)
            cycle_index = (successful_index - 1) % (self.tool_calls_before_final + 1)
            if self.skip_tool_on_correction and any(
                "correction_instruction" in str(item.get("content", ""))
                for item in body["messages"]
            ):
                cycle_index = self.tool_calls_before_final
            if cycle_index < self.tool_calls_before_final:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{successful_index}",
                            "index": 0,
                            "type": "function",
                            "function": {
                                "name": "read_document",
                                "arguments": json.dumps({"handle": self.handle}),
                            },
                        }
                    ],
                }
                finish_reason = "tool_calls"
            else:
                completion_index = (successful_index - 1) // (self.tool_calls_before_final + 1)
                output = (
                    self.final_outputs[min(completion_index, len(self.final_outputs) - 1)]
                    if self.final_outputs
                    else self.final_output
                )
                message = {"role": "assistant", "content": output}
                finish_reason = "stop"
            await self._respond(
                writer,
                200,
                {
                    "id": f"chatcmpl-{len(self.requests)}",
                    "object": "chat.completion",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": self.finish_reason_override or finish_reason,
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                    **(
                        {"synthetic_padding": "x" * self.response_padding_bytes}
                        if self.response_padding_bytes
                        else {}
                    ),
                },
                content_type=self.response_content_type,
            )
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    @staticmethod
    async def _respond(
        writer: asyncio.StreamWriter,
        status: int,
        body: dict[str, object],
        *,
        extra_headers: dict[str, str] | None = None,
        content_type: str = "application/json",
    ) -> None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = [
            f"HTTP/1.1 {status} Synthetic",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(payload)}",
            "Connection: close",
        ]
        headers.extend(f"{name}: {value}" for name, value in (extra_headers or {}).items())
        writer.write(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + payload)
        await writer.drain()


def _runtime_context():
    compilation_context = context(ids())
    configuration = compilation_context.runtime_configuration.model_copy(
        update={
            "runtime_key": "omnicore_agent",
            "model_provider": "openrouter",
            "model_api": "chat_completions",
            "model": OMNICORE_QUALIFICATION_MODEL,
            "adapter_profile": canonical_adapter_profile(build_omnicore_agent_adapter_profile({})),
            "timeout_seconds": 300,
            "maximum_turns": 6,
        }
    )
    return compilation_context.model_copy(update={"runtime_configuration": configuration})


class _GuardAdmission:
    """Minimal admission probe for direct guard transport tests."""

    def __init__(self) -> None:
        self.before = 0
        self.succeeded = 0

    def before_request(self) -> None:
        self.before += 1

    def request_succeeded(self) -> None:
        self.succeeded += 1


def _provider_output() -> str:
    return generated_result().model_dump_json()


def _wrong_agent_version_output() -> str:
    payload = json.loads(_provider_output())
    payload["agent_version"] = "stale-version"
    return json.dumps(payload)


def _large_provider_output() -> str:
    result = generated_result()
    requirement = result.requirements[0]
    payload = result.model_dump(mode="python", exclude={"setup_notes"})
    payload["requirements"] = [
        requirement.model_copy(
            update={
                "suggestion_id": f"synthetic_requirement_{index}",
                "statement": (
                    "The synthetic guide requires a bounded observable answer. " * 12
                ).strip(),
                "classification_rationale": (
                    "This informational requirement preserves exact source evidence. " * 10
                ).strip(),
            }
        ).model_dump(mode="python")
        for index in range(10)
    ]
    return type(result).model_validate(payload).model_dump_json()


def _capabilities(
    compilation_context,
    *,
    returned_text: str = "Generated synthetic guide text.",
    returned_source_item_id=None,
):
    opened: set[str] = set()
    reads: list[str] = []
    attempts: list[str] = []
    rejections: list[str] = []
    output_characters = 0
    document = compilation_context.material.documents[0]
    handle = compilation_context.material.handle_for(document)

    def result(supplied_handle: str, operation: str) -> GuideDocumentToolResult:
        nonlocal output_characters
        attempts.append(supplied_handle)
        if len(attempts) > compilation_context.runtime_configuration.maximum_tool_calls:
            rejections.append("tool_calls")
            raise ValueError("synthetic workspace tool-call budget exceeded")
        if supplied_handle != handle:
            rejections.append("handle")
            raise ValueError("synthetic workspace handle is invalid")
        source_item_id = returned_source_item_id or document.source_item_id
        if source_item_id != document.source_item_id:
            rejections.append("source_identity")
            raise ValueError("synthetic workspace source identity changed")
        next_output = output_characters + len(returned_text)
        if next_output > compilation_context.runtime_configuration.maximum_tool_output_characters:
            rejections.append("tool_output")
            raise ValueError("synthetic workspace output budget exceeded")
        output_characters = next_output
        opened.add(supplied_handle)
        reads.append(supplied_handle)
        return GuideDocumentToolResult(
            handle=handle,
            source_item_id=source_item_id,
            document_version_id=document.ingest_id,
            sha256=document.sha256,
            operation=operation,
            text=returned_text,
            locators=(),
            next_offset=None,
            total_characters=len(returned_text),
        )

    async def read_document(
        supplied_handle: str, *, offset: int = 0, limit: int = 16000
    ) -> GuideDocumentToolResult:
        assert offset == 0 and limit == 16000
        return result(supplied_handle, "read")

    async def search_document(
        supplied_handle: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> GuideDocumentToolResult:
        assert offset == 0 and query and limit == 20
        return result(supplied_handle, "search")

    async def opened_handles() -> frozenset[str]:
        return frozenset(opened)

    return (
        SimpleNamespace(
            tools=SimpleNamespace(
                read_document=read_document,
                search_document=search_document,
                opened_handles=opened_handles,
                attempts=attempts,
                rejections=rejections,
            ),
            model=SimpleNamespace(
                maximum_output_tokens=16_384,
                reasoning_effort="medium",
                text_verbosity="low",
            ),
        ),
        reads,
        handle,
    )


@pytest.fixture(autouse=True)
def synthetic_credential(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-omnicore-test-key")


async def _send_guard_request(
    base_url: str,
    *,
    model: str = OMNICORE_QUALIFICATION_MODEL,
    header_override: tuple[str, str] | None = None,
) -> bytes:
    parsed = urlparse(base_url)
    request_body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "Synthetic."},
                {"role": "user", "content": "Synthetic."},
            ],
            "temperature": 0,
            "max_tokens": 16_384,
            "reasoning_effort": "medium",
            "tools": _MODEL_TOOLS,
            "usage": {"include": True},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Host": f"127.0.0.1:{parsed.port}",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "User-Agent": "litellm/1.106.2",
        "HTTP-Referer": "https://litellm.ai",
        "X-Title": "liteLLM",
        "Authorization": "Bearer synthetic-omnicore-test-key",
        "Content-Type": "application/json",
        "Content-Length": str(len(request_body)),
    }
    if header_override is not None:
        headers[header_override[0]] = header_override[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", parsed.port)
    request_path = parsed.path + "/chat/completions"
    wire = [f"POST {request_path} HTTP/1.1"]
    wire.extend(f"{name}: {item}" for name, item in headers.items())
    writer.write(("\r\n".join(wire) + "\r\n\r\n").encode("ascii") + request_body)
    await writer.drain()
    status_line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return status_line


def test_profile_provider_and_test_transport_are_closed(monkeypatch):
    profile = build_omnicore_agent_adapter_profile({})
    assert profile["provider_retries"] == 3
    assert profile["provider_attempts"] == 4
    assert profile["provider_fallbacks_allowed"] is False
    assert profile["data_collection"] == "deny"
    assert profile["provider_plugin_disable_requests"] is True
    assert profile["sdk_environment"] == "omnicore"
    assert profile["process_sdk_exclusive"] is True
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="no runtime options"):
        build_omnicore_agent_adapter_profile({"base_url": "https://example.invalid"})

    compilation_context = _runtime_context()
    monkeypatch.delenv("OPENROUTER_API_KEY")
    runtime = OmniCoreAgentProjectGuideRuntime(compilation_context.runtime_configuration)
    assert runtime.identity == compilation_context.runtime_configuration.adapter_identity
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-omnicore-test-key")
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="loopback"):
        OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url="https://example.invalid/chat/completions",
        )
    for model in ("openai/gpt-5.6-terra:online", "openrouter/auto"):
        with pytest.raises(ProjectAgentRuntimeConfigurationError, match="unsupported"):
            OmniCoreAgentProjectGuideRuntime(
                compilation_context.runtime_configuration.model_copy(update={"model": model})
            )


def test_profile_rejects_litellm_distribution_drift():
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="does not match"):
        _require_sdk_versions(
            OMNICOREAGENT_VERSION,
            OMNICORE_OPENAI_VERSION,
            LITELLM_VERSION + ".drifted",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda body: body.update(models=[OMNICORE_QUALIFICATION_MODEL]),
        lambda body: body.update(route="alternate"),
        lambda body: body.update(plugins=[]),
        lambda body: body.update(model="openrouter/auto"),
        lambda body: body.update(usage={"include": False}),
        lambda body: body.update(reasoning_effort="high"),
        lambda body: body.update(temperature=1),
        lambda body: body.update(max_tokens=1),
        lambda body: body.update(tools=[{"type": "web_search", "web_search": {}}]),
    ],
)
def test_transport_rejects_each_routing_and_tool_mutation_before_forward(mutation):
    body = {
        "model": OMNICORE_QUALIFICATION_MODEL,
        "messages": [
            {"role": "system", "content": "Generated synthetic instruction."},
            {"role": "user", "content": "Generated synthetic request."},
        ],
        "temperature": 0,
        "max_tokens": 16_384,
        "reasoning_effort": "medium",
        "tools": copy.deepcopy(_MODEL_TOOLS),
        "usage": {"include": True},
    }
    mutation(body)
    with pytest.raises(_GuardRejection):
        _validate_request_body(
            body,
            expected_model=OMNICORE_QUALIFICATION_MODEL,
            expected_reasoning_effort="medium",
        )


def test_transport_rejects_duplicate_json_members():
    with pytest.raises(ValueError, match="duplicate"):
        _unique_object([("model", OMNICORE_QUALIFICATION_MODEL), ("model", "openrouter/auto")])


def _provider_tool_response(*, choice_index=0, call_indexes=(0,)) -> bytes:
    calls = []
    for position, index in enumerate(call_indexes):
        call = {
            "id": f"call_{position}",
            "type": "function",
            "function": {
                "name": "read_document",
                "arguments": '{"handle":"00000000-0000-0000-0000-000000000001"}',
            },
        }
        if index is not None:
            call["index"] = index
        calls.append(call)
    return json.dumps(
        {
            "id": "chatcmpl-index-test",
            "object": "chat.completion",
            "created": 1,
            "model": OMNICORE_QUALIFICATION_MODEL,
            "choices": [
                {
                    "index": choice_index,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": calls,
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }
    ).encode("utf-8")


@pytest.mark.parametrize("choice_index", [False, 0.0, "0", 1])
def test_transport_rejects_non_exact_choice_indexes(choice_index):
    with pytest.raises(_GuardRejection):
        _rebuild_provider_success_body(
            _provider_tool_response(choice_index=choice_index),
            expected_model=OMNICORE_QUALIFICATION_MODEL,
        )


@pytest.mark.parametrize(
    "call_indexes",
    [
        (False,),
        (0.0,),
        ("0",),
        (1,),
        (0, True),
        (0, 1.0),
    ],
)
def test_transport_rejects_non_exact_tool_call_indexes(call_indexes):
    with pytest.raises(_GuardRejection):
        _rebuild_provider_success_body(
            _provider_tool_response(call_indexes=call_indexes),
            expected_model=OMNICORE_QUALIFICATION_MODEL,
        )


@pytest.mark.parametrize("call_indexes", [(None,), (0,), (0, 1)])
def test_transport_strips_valid_optional_tool_call_indexes(call_indexes):
    rebuilt = json.loads(
        _rebuild_provider_success_body(
            _provider_tool_response(call_indexes=call_indexes),
            expected_model=OMNICORE_QUALIFICATION_MODEL,
        )
    )
    calls = rebuilt["choices"][0]["message"]["tool_calls"]
    assert len(calls) == len(call_indexes)
    assert all(set(call) == {"id", "type", "function"} for call in calls)


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("Authorization", "Bearer hostile-key"),
        ("HTTP-Referer", "https://example.invalid"),
        ("User-Agent", "litellm/0.0.0"),
        ("Cookie", "session=hostile"),
    ],
)
async def test_transport_header_mutations_never_reach_upstream(header, value):
    handle = "00000000-0000-0000-0000-000000000001"
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output='{"synthetic":true}',
    ) as provider:
        profile = require_omnicore_agent_adapter_profile(build_omnicore_agent_adapter_profile({}))
        guard = _LoopbackOpenRouterGuard(
            credential="synthetic-omnicore-test-key",
            model=OMNICORE_QUALIFICATION_MODEL,
            profile=profile,
            admission=_GuardAdmission(),
            maximum_requests=1,
            maximum_logical_turns=1,
            io_timeout_seconds=5,
            upstream=_validated_test_upstream(provider.url, _TEST_UPSTREAM_AUTHORITY),
        )
        await guard.start()
        try:
            status_line = await _send_guard_request(guard.base_url, header_override=(header, value))
            assert status_line.startswith((b"HTTP/1.1 400", b"HTTP/1.1 401"))
        finally:
            await guard.close(5)
    assert provider.requests == []


async def test_transport_stops_oversized_provider_response():
    async with _SyntheticOpenRouter(
        handle="00000000-0000-0000-0000-000000000001",
        final_output='{"synthetic":true}',
    ) as provider:
        profile = require_omnicore_agent_adapter_profile(build_omnicore_agent_adapter_profile({}))
        guard = _LoopbackOpenRouterGuard(
            credential="synthetic-omnicore-test-key",
            model=OMNICORE_QUALIFICATION_MODEL,
            profile=replace(profile, maximum_response_bytes=64),
            admission=_GuardAdmission(),
            maximum_requests=1,
            maximum_logical_turns=1,
            io_timeout_seconds=5,
            upstream=_validated_test_upstream(provider.url, _TEST_UPSTREAM_AUTHORITY),
        )
        await guard.start()
        try:
            status_line = await _send_guard_request(guard.base_url)
            assert status_line.startswith(b"HTTP/1.1 422")
        finally:
            await guard.close(5)
    assert len(provider.requests) == 1


async def test_transport_binds_the_trusted_configured_model():
    configured_model = "anthropic/claude-sonnet-4.5"
    configuration = _runtime_context().runtime_configuration.model_copy(
        update={"model": configured_model}
    )
    runtime = OmniCoreAgentProjectGuideRuntime(configuration)
    await runtime.aclose()

    async with _SyntheticOpenRouter(
        handle="00000000-0000-0000-0000-000000000001",
        final_output='{"synthetic":true}',
    ) as provider:
        profile = require_omnicore_agent_adapter_profile(build_omnicore_agent_adapter_profile({}))
        guard = _LoopbackOpenRouterGuard(
            credential="synthetic-omnicore-test-key",
            model=configured_model,
            profile=profile,
            admission=_GuardAdmission(),
            maximum_requests=1,
            maximum_logical_turns=1,
            io_timeout_seconds=5,
            upstream=_validated_test_upstream(provider.url, _TEST_UPSTREAM_AUTHORITY),
        )
        await guard.start()
        try:
            status_line = await _send_guard_request(
                guard.base_url,
                model=configured_model,
            )
            assert status_line.startswith(b"HTTP/1.1 200")
        finally:
            await guard.close(5)
    assert len(provider.requests) == 1
    assert provider.requests[0][1]["model"] == configured_model


async def test_actual_sdk_tool_loop_retries_and_rebuilds_private_provider_controls(
    monkeypatch, tmp_path
):
    from app.adapters.project_agents import provider_resilience

    class CountingCircuit:
        def __init__(self):
            self.acquired = 0
            self.required = 0
            self.successes = 0
            self.failures = 0
            self.releases = 0

        def acquire(self, _lifetime):
            self.acquired += 1
            return object()

        def require_current(self, _lease):
            self.required += 1

        def succeeded(self, _lease):
            self.successes += 1

        def failed(self, _lease):
            self.failures += 1

        def release(self, _lease):
            self.releases += 1

    circuit = CountingCircuit()
    monkeypatch.setattr(provider_resilience, "circuit_for", lambda *_: circuit)
    monkeypatch.chdir(tmp_path)
    compilation_context = _runtime_context()
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        retry_statuses=(408, 429, 500),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            outcome = await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()

    assert outcome == generated_result()
    assert reads == [handle, handle]
    assert len(provider.requests) == 7
    assert circuit.acquired == 4
    assert circuit.required == 4
    assert circuit.successes == 4
    assert circuit.failures == 0
    expected_options = openrouter_request_options()
    assert all(body["provider"] == expected_options["provider"] for _, body in provider.requests)
    assert all(body["plugins"] == expected_options["plugins"] for _, body in provider.requests)
    assert all(body["model"] == OMNICORE_QUALIFICATION_MODEL for _, body in provider.requests)
    assert all(body["tools"] == _MODEL_TOOLS for _, body in provider.requests)
    expected_fields = {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "tools",
        "usage",
        "provider",
        "plugins",
        "reasoning_effort",
        "verbosity",
    }
    assert all(set(body) == expected_fields for _, body in provider.requests)
    for request_index in (4, 6):
        messages = provider.requests[request_index][1]["messages"]
        assert [message["role"] for message in messages[-2:]] == ["assistant", "tool"]
        assert set(messages[-2]) == {"role", "tool_calls"}
        assert set(messages[-1]) == {"role", "content", "tool_call_id"}
    for headers, _body in provider.requests:
        assert headers["authorization"] == "Bearer synthetic-omnicore-test-key"
        assert "http-referer" not in headers
        assert "x-title" not in headers
        assert "cookie" not in headers
    assert not (tmp_path / "workspace").exists()
    assert not (tmp_path / "telemetry").exists()
    assert os.environ["OPENROUTER_API_KEY"] == "synthetic-omnicore-test-key"


async def test_actual_sdk_large_valid_draft_crosses_review_handoff():
    compilation_context = _runtime_context()
    capabilities, reads, handle = _capabilities(compilation_context)
    output = _large_provider_output()
    assert 16_000 < len(output.encode("utf-8")) < 32_000
    async with _SyntheticOpenRouter(handle=handle, final_output=output) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            result = await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert result == type(result).model_validate_json(output)
    assert reads == [handle, handle]
    assert len(provider.requests) == 4
    for request_index in (0, 2):
        messages = provider.requests[request_index][1]["messages"]
        instructions = [
            message["content"]
            for message in messages
            if message["role"] == "system"
            and isinstance(message.get("content"), str)
            and "checker-specification schema: " in message["content"]
        ]
        assert len(instructions) == 1
        schema_text = instructions[0].split("checker-specification schema: ", 1)[1]
        presented_schema, _ = json.JSONDecoder().raw_decode(schema_text)
        assert "requirements" in presented_schema["properties"]
        requirement = presented_schema["$defs"]["AtomicGuideRequirement"]
        assert {"stage", "check_specification", "classification_rationale"} <= set(requirement["required"])
        assert set(presented_schema["$defs"]["CompilationStage"]["enum"]) == {
            "pre_submit", "post_submit"
        }
        assert "PreSubmissionBindingProposal" not in presented_schema["$defs"]
        assert "PostSubmissionBindingProposal" not in presented_schema["$defs"]



async def test_actual_sdk_rejects_oversized_workstream_input_before_provider():
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "task_examples": validate_task_examples([{"content": "A" * 1024}]),
            "runtime_configuration": base.runtime_configuration.model_copy(
                update={"maximum_manifest_bytes": 1024}
            )
        }
    )
    assert len(project_guide_compilation_prompt_bytes(compilation_context)) > 1024
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectAgentRuntimeError, match="prompt exceeds"):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert reads == []
    assert provider.requests == []


async def test_actual_sdk_foreign_source_identity_is_rejected_before_opening():
    compilation_context = _runtime_context()
    capabilities, reads, handle = _capabilities(
        compilation_context,
        returned_source_item_id=uuid4(),
    )
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectGuideCompilationInvalidOutputError):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert provider.requests
    assert reads == []
    assert capabilities.tools.rejections == ["source_identity"]
    assert await capabilities.tools.opened_handles() == frozenset()


@pytest.mark.parametrize(
    ("configuration_updates", "returned_text", "tool_calls_before_final", "rejection"),
    [
        ({"maximum_turns": 12, "maximum_tool_calls": 3}, "bounded", 3, "tool_calls"),
        (
            {"maximum_turns": 12, "maximum_tool_output_characters": 65_536},
            "x" * 16_000,
            5,
            "tool_output",
        ),
    ],
)
async def test_actual_sdk_neutral_tool_budgets_stop_access(
    configuration_updates,
    returned_text,
    tool_calls_before_final,
    rejection,
):
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "runtime_configuration": base.runtime_configuration.model_copy(
                update=configuration_updates
            )
        }
    )
    capabilities, _reads, handle = _capabilities(
        compilation_context,
        returned_text=returned_text,
    )
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        tool_calls_before_final=tool_calls_before_final,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(
                (ProjectAgentRuntimeError, ProjectGuideCompilationInvalidOutputError)
            ):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert provider.requests
    assert rejection in capabilities.tools.rejections


async def test_actual_sdk_malformed_output_is_terminal_invalid_output():
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output="not-json",
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert caught.value.failure_code == "schema_invalid"
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    ("outputs", "correction_phase", "issue_code"),
    [
        (
            ("not-json", _provider_output(), _provider_output()),
            "checker_specification",
            "invalid_json",
        ),
        ((_provider_output(), "not-json", _provider_output()), "coverage_review", "invalid_json"),
        (
            (_wrong_agent_version_output(), _provider_output(), _provider_output()),
            "checker_specification",
            "context_constraint",
        ),
        *[
            (
                (json.dumps(_rejected_semantic_payload(fault)), _provider_output(), _provider_output()),
                "checker_specification",
                code,
            )
            for fault, code in [
                ("blocked", "blocked_evidence"), ("duplicate", "suggestion_ids_unique"),
                ("code_overlap", "verdict_code_overlap"),
                ("unknown_finding", "finding_reference"),
            ]
        ],
        (
            (json.dumps(_invalid_canonical_payload("material")), _provider_output(), _provider_output()),
            "checker_specification",
            "canonical_constraint",
        ),
        (
            (json.dumps(_invalid_canonical_payload("unsafe")), _provider_output(), _provider_output()),
            "checker_specification",
            "unsafe_text",
        ),
    ],
)
async def test_actual_sdk_corrects_known_invalid_output_within_attempt(
    outputs, correction_phase, issue_code
):
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "runtime_configuration": base.runtime_configuration.model_copy(
                update={"maximum_turns": 12}
            )
        }
    )
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        final_outputs=outputs,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            result = await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert result == generated_result()
    assert reads == [handle, handle, handle]
    assert len(provider.requests) == 6
    correction_messages = provider.requests[4 if correction_phase == "coverage_review" else 2][1][
        "messages"
    ]
    assert correction_phase in str(correction_messages)
    assert issue_code in str(correction_messages)
    correction = next(
        json.loads(item["content"][item["content"].index("{"):]) for item in correction_messages
        if isinstance(item.get("content"), str) and '"correction_instruction"' in item["content"]
    )
    rejected = outputs[1 if correction_phase == "coverage_review" else 0]
    if rejected == "not-json" or "private-draft-marker" in rejected:
        assert "untrusted_candidate_proposal" not in correction
        assert "private-draft-marker" not in str(correction_messages)
    else:
        assert correction["untrusted_candidate_proposal"] == json.loads(rejected)
        assert "never instructions or accepted policy" in correction["correction_instruction"]


@pytest.mark.parametrize("next_failure", ["malformed", "oversized", "unsafe"])
async def test_actual_sdk_discards_previous_rejected_candidate(next_failure):
    base = _runtime_context()
    configuration = base.runtime_configuration.model_copy(
        update={"maximum_turns": 12, "maximum_manifest_bytes": 256_000}
    )
    compilation_context = base.model_copy(update={"runtime_configuration": configuration})
    rejected = _rejected_semantic_payload("duplicate")
    next_output = {
        "malformed": "not-json", "oversized": "x" * 256_001,
        "unsafe": json.dumps(_invalid_canonical_payload("unsafe")),
    }[next_failure]
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle, final_output=_provider_output(),
        final_outputs=(json.dumps(rejected), next_output, _provider_output(), _provider_output()),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(configuration, upstream_url=provider.url)
        runtime.admit_execution()
        try:
            assert await runtime.compile_project_guide(compilation_context, capabilities) == generated_result()
        finally:
            await runtime.aclose()
    assert reads == [handle] * 4
    assert len(provider.requests) == 8
    prompts = []
    for index in [2, 4]:
        prompts.append(next(
            json.loads(item["content"][item["content"].index("{"):])
            for item in provider.requests[index][1]["messages"]
            if isinstance(item.get("content"), str) and '"correction_instruction"' in item["content"]
        ))
    assert prompts[0]["untrusted_candidate_proposal"] == rejected
    assert "untrusted_candidate_proposal" not in prompts[1]
    assert "private-draft-marker" not in json.dumps(prompts[1])


async def test_actual_sdk_bounds_full_correction_envelope():
    base = _runtime_context()
    rejected = json.dumps(_rejected_semantic_payload("duplicate"))
    limit = max(len(project_guide_compilation_prompt_bytes(base)), len(rejected.encode())) + 1
    configuration = base.runtime_configuration.model_copy(
        update={"maximum_turns": 12, "maximum_manifest_bytes": limit}
    )
    compilation_context = base.model_copy(update={"runtime_configuration": configuration})
    assert len(project_guide_compilation_prompt_bytes(compilation_context)) <= limit
    assert len(rejected.encode()) <= limit
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(handle=handle, final_output=rejected) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(configuration, upstream_url=provider.url)
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectGuideCompilationInvalidOutputError):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert reads == [handle]
    assert len(provider.requests) == 2


@pytest.mark.parametrize("last_review_valid", [True, False])
async def test_actual_sdk_corrections_are_bounded_per_phase(last_review_valid):
    """Draft repair cannot consume either of the review phase's two repairs."""
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "runtime_configuration": base.runtime_configuration.model_copy(
                update={"maximum_turns": 12}
            )
        }
    )
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        final_outputs=(
            "not-json", _provider_output(), "not-json", "not-json",
            _provider_output() if last_review_valid else "not-json",
        ),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            if last_review_valid:
                assert await runtime.compile_project_guide(
                    compilation_context, capabilities
                ) == generated_result()
            else:
                with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
                    await runtime.compile_project_guide(compilation_context, capabilities)
                assert caught.value.failure_code == "schema_invalid"
        finally:
            await runtime.aclose()
    assert reads == [handle] * 5
    assert len(provider.requests) == 10
    for index, phase in ((2, "checker_specification"), (6, "coverage_review"), (8, "coverage_review")):
        correction = next(
            json.loads(item["content"][item["content"].index("{"):])
            for item in provider.requests[index][1]["messages"]
            if isinstance(item.get("content"), str) and '"correction_instruction"' in item["content"]
        )
        assert correction["phase"] == phase


async def test_actual_sdk_review_correction_keeps_aggregate_turn_ceiling():
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "runtime_configuration": base.runtime_configuration.model_copy(
                update={"maximum_turns": 6}
            )
        }
    )
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        final_outputs=(_provider_output(), "not-json", "not-json", _provider_output()),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert caught.value.failure_code == "schema_invalid"
    assert reads == [handle] * 3
    assert len(provider.requests) == 6


async def test_actual_sdk_correction_keeps_aggregate_tool_quota():
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "runtime_configuration": base.runtime_configuration.model_copy(
                update={"maximum_turns": 12, "maximum_tool_calls": 1}
            )
        }
    )
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        final_outputs=("not-json", _provider_output()),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(
                (ProjectAgentRuntimeError, ProjectGuideCompilationInvalidOutputError)
            ):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert reads == [handle]
    assert "tool_calls" in capabilities.tools.rejections
    assert len(provider.requests) > 2


async def test_actual_sdk_rejects_historical_scope_and_exhausts_corrections():
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "runtime_configuration": base.runtime_configuration.model_copy(
                update={"maximum_turns": 12}
            )
        }
    )
    capabilities, reads, handle = _capabilities(compilation_context)
    out_of_scope = generated_result().model_dump(mode="json")
    out_of_scope["requirements"][0]["disposition"] = "human_review"
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=json.dumps(out_of_scope),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert caught.value.failure_code == "schema_invalid"
    assert len(reads) == 3
    assert len(provider.requests) == 6
    assert "schema_additionalProperties" in str(provider.requests[2][1]["messages"])
    assert "human_review" not in str(provider.requests[2][1]["messages"])


async def test_actual_sdk_correction_requires_new_source_read():
    base = _runtime_context()
    compilation_context = base.model_copy(
        update={
            "runtime_configuration": base.runtime_configuration.model_copy(
                update={"maximum_turns": 12}
            )
        }
    )
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        final_outputs=(_provider_output(), "not-json", _provider_output()),
        skip_tool_on_correction=True,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert caught.value.failure_code == "schema_invalid"
    assert reads == [handle, handle]
    assert len(provider.requests) == 6


async def test_exhausted_native_retries_open_shared_provider_circuit(monkeypatch):
    from app.adapters.project_agents import provider_resilience

    circuit = ProviderCircuit(1, 60)
    monkeypatch.setattr(provider_resilience, "circuit_for", lambda *_: circuit)
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        always_status=500,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectAgentRuntimeError, match="run failed"):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert len(provider.requests) == 4

    blocked = OmniCoreAgentProjectGuideRuntime._for_test(
        compilation_context.runtime_configuration,
        upstream_url="http://127.0.0.1:1/chat/completions",
    )
    with pytest.raises(ProviderCircuitOpen):
        blocked.admit_execution()
    await blocked.aclose()


@pytest.mark.parametrize(
    ("status", "expected_attempts"),
    [(200, 1), (400, 1), (429, 4), (500, 4)],
)
async def test_actual_sdk_provider_error_body_never_reaches_logs_or_exception(
    caplog,
    monkeypatch,
    status,
    expected_attempts,
):
    from app.adapters.project_agents import provider_resilience

    monkeypatch.setattr(
        provider_resilience,
        "circuit_for",
        lambda *_: ProviderCircuit(OMNICORE_CIRCUIT_FAILURE_THRESHOLD, 60),
    )
    marker = f"private-guide-marker-{status}"
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        always_status=status,
        error_message=marker,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectAgentRuntimeError) as caught:
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert len(provider.requests) == expected_attempts
    assert marker not in str(caught.value)
    assert all(marker not in record.getMessage() for record in caplog.records)


async def test_actual_sdk_output_limit_is_not_retried_or_counted_by_circuit(monkeypatch):
    from app.adapters.project_agents import provider_resilience

    circuit = ProviderCircuit(1, 60)
    monkeypatch.setattr(provider_resilience, "circuit_for", lambda *_: circuit)
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        finish_reason_override="length",
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectAgentRuntimeError, match="run failed"):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert len(provider.requests) == 1

    admitted = OmniCoreAgentProjectGuideRuntime._for_test(
        compilation_context.runtime_configuration,
        upstream_url="http://127.0.0.1:1/chat/completions",
    )
    admitted.admit_execution()
    await admitted.aclose()


@pytest.mark.parametrize("failure_kind", ["content_type", "response_size"])
async def test_actual_sdk_deterministic_success_transport_rejection_is_not_retried(
    monkeypatch,
    failure_kind,
):
    from app.adapters.project_agents import omnicore_profile, provider_resilience

    circuit = ProviderCircuit(1, 60)
    monkeypatch.setattr(provider_resilience, "circuit_for", lambda *_: circuit)
    provider_options: dict[str, object]
    if failure_kind == "content_type":
        provider_options = {"response_content_type": "text/plain"}
    else:
        monkeypatch.setattr(omnicore_profile, "OMNICORE_MAXIMUM_RESPONSE_BYTES", 1_024)
        provider_options = {"response_padding_bytes": 2_048}
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        **provider_options,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectAgentRuntimeError):
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert len(provider.requests) == 1

    admitted = OmniCoreAgentProjectGuideRuntime._for_test(
        compilation_context.runtime_configuration,
        upstream_url="http://127.0.0.1:1/chat/completions",
    )
    admitted.admit_execution()
    await admitted.aclose()


async def test_native_cancellation_never_returns_while_sdk_task_remains_live():
    release = asyncio.Event()
    started = asyncio.Event()

    class CancellationResistantAgent:
        task: asyncio.Task[object] | None = None
        cancellations = 0

        async def run(self, *_args, **_kwargs):
            self.task = asyncio.current_task()
            started.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    self.cancellations += 1
            return {"status": "success", "termination_reason": "stop", "response": "{}"}

    class Guard:
        transient_failure_exhausted = False

        def begin_logical_request(self):
            return None

        async def close(self, _timeout):
            return None

    class Admission:
        def before_request(self):
            return None

        def request_failed(self, _transient):
            return None

        def request_succeeded(self):
            return None

    agent = CancellationResistantAgent()
    outer = asyncio.create_task(
        _run_native_agent(
            agent,
            "synthetic",
            guard=Guard(),
            admission=Admission(),
            cleanup_timeout_seconds=0.01,
        )
    )
    await started.wait()
    outer.cancel()
    await asyncio.sleep(0.05)
    assert not outer.done()
    assert agent.task is not None and not agent.task.done()
    assert agent.cancellations >= 2
    release.set()
    with pytest.raises(ProjectAgentRuntimeError, match="cancellation did not finish"):
        await outer
    assert agent.task.done()


async def test_actual_sdk_cancellation_closes_forward_and_runtime_lifecycle():
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        hang=True,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        assert runtime.identity == compilation_context.runtime_configuration.adapter_identity
        different_context = compilation_context.model_copy(
            update={
                "runtime_configuration": compilation_context.runtime_configuration.model_copy(
                    update={"timeout_seconds": 299}
                )
            }
        )
        with pytest.raises(ProjectAgentRuntimeConfigurationError, match="mismatch"):
            await runtime.compile_project_guide(different_context, capabilities)
        with pytest.raises(ProjectAgentRuntimeError, match="not admitted"):
            await runtime.compile_project_guide(compilation_context, capabilities)
        runtime.admit_execution()
        task = asyncio.create_task(runtime.compile_project_guide(compilation_context, capabilities))
        await asyncio.wait_for(provider.received.wait(), timeout=180)
        first_closer = asyncio.create_task(runtime.aclose())
        await asyncio.sleep(0)
        second_closer = asyncio.create_task(runtime.aclose())
        first_closer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first_closer
        await second_closer
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(provider.disconnected.wait(), timeout=30)
        await runtime.aclose()
        with pytest.raises(ProjectAgentRuntimeError, match="closed"):
            await runtime.compile_project_guide(compilation_context, capabilities)


