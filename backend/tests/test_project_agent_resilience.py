"""Native SDK retry and circuit proof without provider calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx2
import pytest
from agents import Agent, ModelSettings, OpenAIResponsesModel, Runner, RunConfig, function_tool
from agents.items import ModelResponse
from agents.usage import Usage
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from app.adapters.project_agents.provider_resilience import (
    ProviderCircuit, ProviderCircuitOpen, model_retry_settings,
)
from app.core.config import Settings
from app.core.project_agents import project_guide_runtime_configuration


def configuration(**overrides):
    return project_guide_runtime_configuration(Settings(_env_file=None, **overrides))


def status_error(status, code, **headers):
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return APIStatusError("provider failure", response=httpx2.Response(
        status, request=request, headers=headers), body={"code": code})


def connection_error(cause=None, *, timeout=False):
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    error = APITimeoutError(request=request) if timeout else APIConnectionError(request=request)
    error.__cause__ = cause
    return error


def completed():
    return ModelResponse(output=[ResponseOutputMessage(
        id="msg_test", type="message", role="assistant", status="completed",
        content=[ResponseOutputText(type="output_text", text="done", annotations=[])],
    )], usage=Usage(), response_id="resp_test")


class ScriptedModel(OpenAIResponsesModel):
    def __init__(self, events):
        super().__init__(model="gpt-5.6-terra", openai_client=AsyncOpenAI(api_key="test", max_retries=0))
        self.events = list(events)
        self.calls = 0

    async def get_response(self, *args, **kwargs):
        self.calls += 1
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event


@pytest.fixture
def delays(monkeypatch):
    from agents.run_internal import model_retry
    observed = []

    async def sleep(delay):
        observed.append(delay)

    monkeypatch.setattr(model_retry, "_sleep_for_retry", sleep)
    return observed


async def run(model, *, tools=()):
    return await Runner.run(Agent(name="retry-proof", model=model, tools=list(tools),
        model_settings=ModelSettings(retry=model_retry_settings(configuration()))),
        "test", run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False))


@pytest.mark.parametrize("error", [
    status_error(429, "rate_limit_exceeded"),
    status_error(503, "server_error", **{"x-should-retry": "true"}),
    connection_error(httpx2.ConnectTimeout("connect failed")),
    connection_error(httpx2.ConnectError("DNS failed")),
    connection_error(httpx2.PoolTimeout("pool unavailable")),
])
async def test_native_sdk_retries_proven_safe_failures(error, delays):
    model = ScriptedModel([error, completed()])
    result = await run(model)
    assert result.final_output == "done"
    assert model.calls == 2
    assert len(delays) == 1 and 0.875 <= delays[0] <= 1.125


@pytest.mark.parametrize("error", [
    status_error(400, "invalid_request"), status_error(401, "invalid_api_key"),
    status_error(403, "permission_denied"), status_error(408, "request_timeout"),
    status_error(409, "conflict"), status_error(500, "server_error"),
    status_error(502, "server_error"), status_error(503, "server_error"),
    status_error(504, "server_error"), status_error(429, "insufficient_quota"),
    status_error(429, "billing_hard_limit_reached", **{"x-should-retry": "true"}),
    status_error(429, "credit_balance_exhausted", **{"x-should-retry": "true"}),
    status_error(429, "rate_limit_exceeded", **{"x-should-retry": "false"}),
    status_error(429, "unknown"), connection_error(), connection_error(timeout=True),
    connection_error(httpx2.ReadTimeout("read failed"), timeout=True),
    connection_error(httpx2.WriteTimeout("write failed"), timeout=True),
    connection_error(httpx2.RemoteProtocolError("response lost")),
    ValueError("invalid model output"), PermissionError("file access denied"),
])
async def test_permanent_or_ambiguous_failure_never_replays(error, delays):
    model = ScriptedModel([error, completed()])
    with pytest.raises(type(error)):
        await run(model)
    assert model.calls == 1 and delays == []


async def test_retry_exhaustion_and_exponential_backoff(delays):
    model = ScriptedModel([status_error(429, "rate_limit_exceeded") for _ in range(4)])
    with pytest.raises(APIStatusError):
        await run(model)
    assert model.calls == 3 and len(delays) == 2
    assert 0.875 <= delays[0] <= 1.125 and 1.75 <= delays[1] <= 2.25


async def test_retry_after_is_respected_without_retrying_early(delays):
    model = ScriptedModel([status_error(429, "rate_limit_exceeded", **{"retry-after": "7"}), completed()])
    await run(model)
    assert delays == [7]
    delays.clear()
    model = ScriptedModel([status_error(429, "rate_limit_exceeded", **{"retry-after": "90"}), completed()])
    with pytest.raises(APIStatusError):
        await run(model)
    assert model.calls == 1 and delays == []


async def test_model_retry_does_not_repeat_completed_local_document_tool(delays):
    opened = []

    @function_tool(failure_error_function=None)
    async def open_document(handle: str) -> str:
        opened.append(handle)
        return "document staged"

    request = ModelResponse(output=[ResponseFunctionToolCall(
        id="fc_test", call_id="call_test", name="open_document", type="function_call",
        arguments='{"handle":"assigned-only"}', status="completed",
    )], usage=Usage(), response_id="resp_tool")
    model = ScriptedModel([request, status_error(429, "rate_limit_exceeded"), completed()])
    await run(model, tools=[open_document])
    assert model.calls == 3 and opened == ["assigned-only"]


async def test_cancellation_never_retries(delays):
    model = ScriptedModel([asyncio.CancelledError(), completed()])
    with pytest.raises(asyncio.CancelledError):
        await run(model)
    assert model.calls == 1 and delays == []


def test_circuit_single_half_open_probe_and_stale_success():
    now = [0.0]
    circuit = ProviderCircuit(3, 60, clock=lambda: now[0])
    old_success = circuit.acquire(1000)
    for _ in range(3):
        circuit.failed(circuit.acquire(1000))
    circuit.succeeded(old_success)
    with pytest.raises(ProviderCircuitOpen):
        circuit.acquire(1000)
    now[0] = 60

    def acquire(_):
        try:
            return circuit.acquire(300)
        except ProviderCircuitOpen:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        leases = list(executor.map(acquire, range(8)))
    probe, = [lease for lease in leases if lease is not None]
    circuit.succeeded(probe)
    circuit.require_current(circuit.acquire(1000))


def test_expired_or_released_probe_cannot_close_new_outage():
    now = [0.0]
    circuit = ProviderCircuit(1, 60, clock=lambda: now[0])
    circuit.failed(circuit.acquire(1000))
    now[0] = 60
    old = circuit.acquire(10)
    now[0] = 71
    current = circuit.acquire(10)
    circuit.succeeded(old)
    with pytest.raises(ProviderCircuitOpen):
        circuit.acquire(10)
    circuit.release(current)
    replacement = circuit.acquire(10)
    circuit.failed(replacement)
    with pytest.raises(ProviderCircuitOpen):
        circuit.acquire(10)


def test_request_deadline_is_independent_and_hashed():
    default = configuration()
    changed = configuration(project_agent_request_timeout_seconds=25)
    assert default.model == "gpt-5.6-terra" and default.request_timeout_seconds == 300
    assert changed.request_timeout_seconds == 25
    assert default.timeout_seconds == changed.timeout_seconds == 1800
    assert default.sha256 != changed.sha256


def test_circuit_counts_exhausted_turn_once_and_isolates_models(monkeypatch):
    from app.adapters.project_agents import provider_resilience as owner
    circuit = ProviderCircuit(2, 60)
    monkeypatch.setattr(owner, "circuit_for", lambda _: circuit)
    admission = owner.ModelCircuitAdmission(configuration())
    for _ in range(3):
        admission.before_request()
        admission.request_failed(status_error(429, "rate_limit_exceeded"))
    admission.close()
    admission.close()
    second = circuit.acquire(1000)
    circuit.failed(second)
    with pytest.raises(ProviderCircuitOpen):
        circuit.acquire(1000)
    assert owner._provider_circuit("openai_agents_sdk", "openai", "responses", "model-a", 3, 60) is not owner._provider_circuit("openai_agents_sdk", "openai", "responses", "model-b", 3, 60)


async def test_open_circuit_prevents_product_fence_and_resource_allocation(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from app.adapters.project_agents import provider_resilience as owner
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
    from app.modules.projects.guide_compilation import orchestrator as module
    from app.modules.projects.guide_compilation.contracts import CompilationRecoveryClassification
    from app.modules.projects.api.guide_compilation import ProjectGuideCompilationExecutionError

    circuit = ProviderCircuit(1, 60)
    circuit.failed(circuit.acquire(1000))
    monkeypatch.setattr(owner, "circuit_for", lambda _: circuit)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(module, "project_guide_compilation_prompt_bytes", lambda _: b"manifest")
    calls = []

    class Backend:
        async def load(self, attempt):
            return SimpleNamespace(classification=CompilationRecoveryClassification.RESERVED)

        async def context(self, state):
            return SimpleNamespace(runtime_configuration=configuration())

        async def fence(self, state):
            calls.append("fence")
            raise AssertionError("open circuit must prevent fencing")

        def capabilities(self, state, context):
            calls.append("resources")
            raise AssertionError("open circuit must prevent resources")

    orchestrator = module.GuideCompilationOrchestrator(Backend(), OpenAIAgentSdkProjectGuideRuntime)
    with pytest.raises(ProjectGuideCompilationExecutionError, match="runtime_unavailable"):
        await orchestrator.execute(SimpleNamespace(attempt_id=uuid4()))
    assert calls == []


async def test_outer_deadline_cancels_backoff_without_second_request(monkeypatch):
    from agents.run_internal import model_retry
    sleeping = asyncio.Event()

    async def backoff(_):
        sleeping.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(model_retry, "_sleep_for_retry", backoff)
    model = ScriptedModel([status_error(429, "rate_limit_exceeded"), completed()])
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await run(model)
    assert sleeping.is_set()
    assert model.calls == 1


async def test_cleanup_bypasses_open_inference_circuit(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from datetime import datetime, timezone
    from openai import NotFoundError
    from app.adapters.project_agents import provider_resilience as owner
    from app.adapters.project_agents.openai_workspace import OpenAIGuideWorkspace
    from app.modules.projects.api.guide_documents import GuideRuntimeResource

    circuit = ProviderCircuit(1, 60)
    circuit.failed(circuit.acquire(1000))
    monkeypatch.setattr(owner, "circuit_for", lambda _: circuit)
    allocation = uuid4()
    resource = GuideRuntimeResource(allocation, "file", "file_assigned", None, None, datetime.now(timezone.utc))
    calls = []

    class Resources:
        async def cleanup_resources(self):
            return (resource,)

        async def record_deleted(self, identifier):
            calls.append(("record_deleted", identifier))

        async def record_cleanup_failed(self, identifier):
            raise AssertionError("cleanup failed")

    class Files:
        async def delete(self, identifier):
            calls.append(("delete", identifier))
            return SimpleNamespace(id=identifier, deleted=True)

        async def retrieve(self, identifier):
            calls.append(("retrieve", identifier))
            raise NotFoundError("gone", response=httpx2.Response(404,
                request=httpx2.Request("GET", "https://api.openai.com/v1/files/file_assigned")), body=None)

    workspace = OpenAIGuideWorkspace(SimpleNamespace(files=Files()), configuration(),
        SimpleNamespace(documents=()), SimpleNamespace(resources=Resources()))
    await workspace._cleanup()
    assert calls == [("delete", "file_assigned"), ("retrieve", "file_assigned"), ("record_deleted", allocation)]
