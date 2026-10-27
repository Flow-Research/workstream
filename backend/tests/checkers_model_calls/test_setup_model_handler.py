"""Closed provider-shape and metadata checks before setup model spend."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.adapters.model_usage.openrouter import (
    bounded_response_bytes,
    openrouter_request_options,
)
from app.adapters.project_agents.setup_model_handler import (
    OpenAISetupProvider,
    OpenRouterSetupProvider,
    SetupModelProxyHandler,
    SetupProviderResponse,
    _completed_reply,
    _validate_request,
)
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.setup_model_proxy import SetupModelProxyRequest, SetupModelProxySubject
from app.modules.model_usage.api import (
    ModelCallUnavailable,
    ModelCallUsage,
    ObservedSetupModelUsageEffect,
    ProjectModelProfile,
    SetupModelEffectAuthorityFacts,
    SetupModelUsageSlotKey,
)
from tests.checkers_model_calls.test_model_call_contract import profile_spec


def _profile(*, provider="openrouter", api="chat_completions", model="openai/model"):
    source = profile_spec().model_dump(mode="python")
    source.update(
        provider=provider,
        api=api,
        model_snapshot=model,
        maximum_input_tokens=1_050_000,
        maximum_output_tokens=128_000,
        maximum_calls=1,
        maximum_total_input_tokens=1_050_000,
        maximum_total_output_tokens=128_000,
        allowed_tools=("read_document", "search_document"),
        maximum_tool_calls=10,
        maximum_tool_output_bytes=100_000,
    )
    source["pricing"].update(
        uncached_input_nanodollars_per_token=5_000,
        cached_input_nanodollars_per_token=400,
        output_nanodollars_per_token=18_000,
    )
    spec = type(profile_spec()).model_validate(source)
    return ProjectModelProfile(
        operation_id=new_record_id(),
        actor_profile_id=new_record_id(),
        spec=spec,
        profile_digest=canonical_json_hash(spec.model_dump(mode="json")),
        profile_id=new_record_id(),
        authorization_evidence_id=new_record_id(),
        created_at=datetime.now(UTC),
    )


def _metadata():
    return {
        "data": {
            "id": "openai/model",
            "canonical_slug": "openai/model-20261023",
            "context_length": 1_050_000,
            "top_provider": {
                "context_length": 1_050_000,
                "max_completion_tokens": 128_000,
            },
            "supported_parameters": [
                "max_tokens",
                "reasoning_effort",
                "tool_choice",
                "tools",
                "verbosity",
            ],
            "pricing": {
                "prompt": "0.000002",
                "completion": "0.000012",
                "web_search": "0.01",
                "input_cache_read": "0.0000002",
                "input_cache_write": "0.0000025",
                "overrides": [
                    {
                        "min_prompt_tokens": 272_000,
                        "prompt": "0.000004",
                        "completion": "0.000018",
                        "input_cache_read": "0.0000004",
                        "input_cache_write": "0.000005",
                    }
                ],
            },
        }
    }


class _MetadataClient:
    def __init__(self, payload):
        self.payload = payload
        self.gets = []

    @asynccontextmanager
    async def stream(self, method, url, **_kwargs):
        assert method == "GET"
        self.gets.append(url)
        body = json.dumps(self.payload).encode()

        class Response:
            status_code = 200

            async def aiter_bytes(self):
                yield body

        yield Response()

    async def aclose(self):
        return None


async def test_openrouter_reserves_full_profile_only_after_current_metadata(monkeypatch):
    import httpx

    client = _MetadataClient(_metadata())
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)
    provider = OpenRouterSetupProvider(api_key="private", profile=_profile())

    assert await provider.count_input({"messages": []}) == 1_050_000
    assert client.gets == ["https://openrouter.ai/api/v1/model/openai/model"]


async def test_provider_body_reader_stops_before_accumulating_over_profile():
    class Response:
        async def aiter_bytes(self):
            yield b"a" * 8
            yield b"b"

    with pytest.raises(ValueError, match="exceeds profile"):
        await bounded_response_bytes(Response(), 8)


async def test_openai_count_includes_every_semantic_input_field():
    recorded = []

    class Counter:
        async def count(self, **kwargs):
            recorded.append(kwargs)
            return SimpleNamespace(input_tokens=73)

    provider = object.__new__(OpenAISetupProvider)
    provider._counter = SimpleNamespace(responses=SimpleNamespace(input_tokens=Counter()))
    schema = {
        "type": "object",
        "properties": {f"field_{index}": {"type": "string"} for index in range(200)},
    }
    body = {
        "model": "gpt-exact",
        "input": "bounded",
        "instructions": "bounded",
        "parallel_tool_calls": False,
        "reasoning": {"effort": "medium"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "result",
                "strict": True,
                "schema": schema,
            },
        },
        "tool_choice": "auto",
        "tools": _tools(),
        "truncation": "disabled",
        "max_output_tokens": 128_000,
        "store": False,
    }

    assert await provider.count_input(body) == 73
    assert recorded == [
        {
            key: value
            for key, value in body.items()
            if key
            in {
                "input",
                "instructions",
                "model",
                "parallel_tool_calls",
                "reasoning",
                "text",
                "tool_choice",
                "tools",
                "truncation",
            }
        }
    ]


@pytest.mark.parametrize(
    "mutation",
    ["context", "pricing", "request_fee", "disabled_search_price", "alias", "parameters"],
)
async def test_openrouter_metadata_drift_fails_before_dispatch(monkeypatch, mutation):
    import httpx

    payload = _metadata()
    data = payload["data"]
    if mutation == "context":
        data["context_length"] = data["top_provider"]["context_length"] = 1_050_001
    elif mutation == "pricing":
        data["pricing"]["overrides"][0]["completion"] = "0.000018001"
    elif mutation == "request_fee":
        data["pricing"]["request"] = "1"
    elif mutation == "disabled_search_price":
        data["pricing"]["web_search"] = "NaN"
    elif mutation == "alias":
        data["id"] = "openai/resolved-other-model"
    else:
        data["supported_parameters"].remove("tools")
    client = _MetadataClient(payload)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)
    provider = OpenRouterSetupProvider(api_key="private", profile=_profile())

    with pytest.raises(ModelCallUnavailable):
        await provider.count_input({"messages": []})


def _subject(profile):
    return SetupModelProxySubject(
        compilation_attempt_id=new_record_id(),
        project_id=profile.spec.project_id,
        guide_id=new_record_id(),
        source_snapshot_id=new_record_id(),
        setup_run_id=new_record_id(),
        setup_generation=1,
        runtime_configuration_hash=canonical_json_hash({"runtime": 1}),
        profile_id=profile.profile_id,
        profile_version=profile.spec.profile_version,
        profile_digest=profile.profile_digest,
        provider=profile.spec.provider,
        api=profile.spec.api,
        model=profile.spec.model_snapshot,
    )


def _tools():
    return [
        {"type": "function", "function": {"name": "read_document"}},
        {"type": "function", "function": {"name": "search_document"}},
    ]


@pytest.mark.parametrize("extra", [{"prompt": {"id": "remote"}}, {"service_tier": "flex"}])
def test_openai_remote_prompt_and_unpriced_tier_are_rejected(extra):
    profile = _profile(provider="openai", api="responses", model="gpt-exact")
    body = {
        "model": "gpt-exact",
        "input": "bounded",
        "instructions": "bounded",
        "max_output_tokens": 128_000,
        "parallel_tool_calls": False,
        "store": False,
        "stream": False,
        "truncation": "disabled",
        "reasoning": {"effort": "medium"},
        "text": {
            "verbosity": "low",
            "format": {"type": "json_schema", "name": "result", "strict": True, "schema": {}},
        },
        "tools": _tools(),
        **extra,
    }
    request = SetupModelProxyRequest(
        subject=_subject(profile),
        phase="draft",
        call_index=0,
        provider_request_json=json.dumps(body, sort_keys=True, separators=(",", ":")),
    )

    with pytest.raises(ModelCallUnavailable):
        _validate_request(profile, request, body)


@pytest.mark.parametrize(
    "mutation", ["reasoning", "web-plugin", "search-options", "server-tool", "model-variant", "missing-usage"]
)
def test_openrouter_requires_locked_settings_and_routing_controls(mutation):
    profile = _profile()
    body = {
        "model": "openai/model",
        "messages": [],
        "max_tokens": 128_000,
        "stream": False,
        "tools": _tools(),
        "usage": {"include": True},
        "reasoning_effort": "medium",
        "verbosity": "low",
        **openrouter_request_options(),
    }
    request = SetupModelProxyRequest(
        subject=_subject(profile),
        phase="draft",
        call_index=0,
        provider_request_json=json.dumps(body, sort_keys=True, separators=(",", ":")),
    )

    _validate_request(profile, request, body)
    if mutation == "reasoning":
        body["reasoning_effort"] = "high"
    elif mutation == "web-plugin":
        body["plugins"][0]["enabled"] = True
    elif mutation == "search-options":
        body["web_search_options"] = {"search_context_size": "low"}
    elif mutation == "server-tool":
        body["tools"][0] = {"type": "openrouter:web_search"}
    elif mutation == "missing-usage":
        body.pop("usage")
    else:
        body["model"] = "openai/model:online"
    request = replace(
        request,
        provider_request_json=json.dumps(body, sort_keys=True, separators=(",", ":")),
    )
    with pytest.raises(ModelCallUnavailable):
        _validate_request(profile, request, body)



@pytest.mark.parametrize("provider,api,model", [
    ("openrouter", "chat_completions", "openai/model"),
    ("openai", "responses", "gpt-exact"),
])
async def test_native_setup_sdk_request_passes_locked_listener_validation_without_provider_reply(
    provider, api, model,
):
    """The actual Runner's serialized request must cross the pre-effect guard."""
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes
    from app.interfaces.setup_model_proxy import canonical_provider_json
    from tests.projects.guide_compilation.helpers import context, ids, runtime_configuration

    profile = _profile(provider=provider, api=api, model=model)
    # Native SDK requests include the full output schema, unlike the small
    # hand-written request fixtures elsewhere in this module.
    spec = type(profile.spec).model_validate(profile.spec.model_dump() | {
        "maximum_request_bytes": 1_048_576, "maximum_total_request_bytes": 1_048_576,
    })
    profile = ProjectModelProfile.model_validate(profile.model_dump() | {
        "spec": spec, "profile_digest": canonical_json_hash(spec.model_dump(mode="json")),
    })
    configuration = runtime_configuration().model_copy(update={
        "model_provider": provider, "model_api": api, "model": model,
    })
    values = ids()
    values["project"] = profile.spec.project_id
    compilation = context(values, configuration=configuration)
    subject = replace(
        _subject(profile), guide_id=compilation.material.guide_id,
        source_snapshot_id=compilation.material.source_snapshot_id,
        setup_run_id=compilation.material.setup_run_id,
        setup_generation=compilation.material.setup_generation,
        runtime_configuration_hash=configuration.sha256,
    )
    observed = []

    class ListenerBoundaryReached(BaseException):
        """Stop locally after validation; do not invent a provider response."""

    class DenyingModelCapability:
        maximum_output_tokens = profile.spec.maximum_output_tokens
        reasoning_effort = profile.spec.settings.reasoning_effort
        text_verbosity = profile.spec.settings.text_verbosity

        async def dispatch(self, phase, body):
            observed.append(body)
            request = SetupModelProxyRequest(
                subject=subject, phase=phase, call_index=0,
                provider_request_json=canonical_provider_json(body),
            )
            _validate_request(profile, request, body)
            raise ListenerBoundaryReached()

    async def no_tool_before_response(*_args, **_kwargs):
        raise AssertionError("No provider response exists to request document tools")

    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)
    runtime.admit_execution()
    try:
        with pytest.raises(ListenerBoundaryReached):
            await runtime._run(
                compilation, project_guide_compilation_prompt_bytes(compilation).decode(),
                SimpleNamespace(model=DenyingModelCapability(), tools=SimpleNamespace(
                    read_document=no_tool_before_response,
                    search_document=no_tool_before_response,
                    opened_handles=no_tool_before_response,
                )),
            )
    finally:
        await runtime.aclose()
    assert len(observed) == 1
    if provider == "openai":
        assert "usage" not in observed[0]


def test_paid_quote_heavy_response_becomes_bounded_unavailable_reply():
    profile = _profile()
    body = {
        "model": "openai/model",
        "messages": [],
        "max_tokens": 128_000,
        "stream": False,
        "tools": _tools(),
        "usage": {"include": True},
        "reasoning_effort": "medium",
        "verbosity": "low",
        **openrouter_request_options(),
    }
    request = SetupModelProxyRequest(
        subject=_subject(profile),
        phase="draft",
        call_index=0,
        provider_request_json=json.dumps(body, sort_keys=True, separators=(",", ":")),
    )
    response_json = json.dumps({"output": '"' * 500_000}, sort_keys=True, separators=(",", ":"))
    assert len(response_json.encode()) < 1024 * 1024

    reply = _completed_reply(
        request,
        profile,
        status_code=200,
        response_json=response_json,
    )

    assert reply.outcome == "unavailable"
    assert reply.failure_code == "model_response_too_large"


async def test_handler_persists_observation_before_response_art_and_replays_without_send():
    profile = _profile()
    body = {
        "model": "openai/model",
        "messages": [],
        "max_tokens": 128_000,
        "stream": False,
        "tools": _tools(),
        "usage": {"include": True},
        "reasoning_effort": "medium",
        "verbosity": "low",
        **openrouter_request_options(),
    }
    request = SetupModelProxyRequest(
        subject=_subject(profile),
        phase="draft",
        call_index=0,
        provider_request_json=json.dumps(body, sort_keys=True, separators=(",", ":")),
    )
    key = SetupModelUsageSlotKey(
        compilation_attempt_id=request.subject.compilation_attempt_id,
        project_id=request.subject.project_id,
        guide_id=request.subject.guide_id,
        source_snapshot_id=request.subject.source_snapshot_id,
        setup_run_id=request.subject.setup_run_id,
        setup_generation=request.subject.setup_generation,
        runtime_configuration_hash=request.subject.runtime_configuration_hash,
        profile_id=request.subject.profile_id,
        profile_version=request.subject.profile_version,
        profile_digest=request.subject.profile_digest,
        phase=request.phase,
        call_index=request.call_index,
    )
    slot_id, effect_id, internal_id = (new_record_id() for _ in range(3))
    effect = SetupModelEffectAuthorityFacts(
        project_id=profile.spec.project_id,
        slot_id=slot_id,
        slot_key=key,
        effect_id=effect_id,
        internal_call_request_id=internal_id,
    )
    prepared = SimpleNamespace(
        slot_key=key,
        slot_id=slot_id,
        effect_id=effect_id,
        internal_call_request_id=internal_id,
    )
    dispatch = SimpleNamespace(
        replayed=False,
        effect=effect,
        internal_call_request_id=internal_id,
    )
    events = []
    stored = {}

    class Session:
        @asynccontextmanager
        async def begin(self):
            yield self

    @asynccontextmanager
    async def sessions():
        yield Session()

    class Profiles:
        async def read_exact(self, *_args, **_kwargs):
            return profile

    class Calls:
        completed = None
        observed = None
        fail_completion = True

        async def recover_existing(self, *_args):
            events.append("recover")
            return self.completed or self.observed

        async def prepare(self, *_args):
            events.append("prepare")
            return prepared

        async def reserve_dispatch(self, *_args):
            events.append("reserve")
            return dispatch

        async def mark_uncertain(self, supplied, digest, *, provider_response_id=None):
            events.append(("observe", provider_response_id))
            self.observed = ObservedSetupModelUsageEffect(
                effect=supplied,
                uncertainty_digest=digest,
                provider_response_id=provider_response_id,
                replayed=False,
            )

        async def complete(self, *_args, response_evidence, **_kwargs):
            events.append("complete")
            if self.fail_completion:
                self.fail_completion = False
                raise ModelCallUnavailable("simulated_response_commit_loss")
            self.completed = SimpleNamespace(
                effect=effect,
                response_evidence=response_evidence,
                state="completed",
            )
            self.observed = None
            return self.completed

    calls = Calls()

    class Outputs:
        async def store_setup_output(self, artifact):
            data = b"".join([chunk async for chunk in artifact.byte_source])
            events.append("store_" + artifact.selector.role)
            stored[artifact.selector.role] = data
            return SimpleNamespace(
                status="verified",
                put_attempt_id=new_record_id(),
                content_id=new_record_id(),
                verification_receipt_id=new_record_id(),
            )

        async def recover_setup_output(self, selector):
            events.append("recover_response_art")
            data = stored["model_response"]
            return SimpleNamespace(
                status="verified",
                put_attempt_id=new_record_id(),
                content_id=new_record_id(),
                verification_receipt_id=new_record_id(),
                content_sha256=selector.content_sha256,
                byte_count=len(data),
            )

        async def read_setup_response(self, *_args):
            events.append("read_response")
            return stored["model_response"]

    class Bindings:
        async def bind_setup_output(self, binding):
            events.append("bind_" + binding.selector.role)
            return SimpleNamespace(
                binding_id=new_record_id(),
                content_id=new_record_id(),
                put_attempt_id=binding.put_attempt_id,
                verification_receipt_id=binding.verification_receipt_id,
            )

    provider_calls = 0
    response_json = json.dumps(
        {
            "id": "response-1",
            "model": "openai/model",
            "choices": [{"message": {"content": "bounded"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    class Provider:
        async def count_input(self, _body):
            return 1

        async def dispatch(self, _body):
            nonlocal provider_calls
            provider_calls += 1
            events.append("provider")
            return SetupProviderResponse(
                status_code=200,
                response_json=response_json,
                provider_response_id="response-1",
                provider_model="openai/model",
                usage=ModelCallUsage(
                    input_tokens=1,
                    cached_input_tokens=0,
                    output_tokens=1,
                    reasoning_tokens=0,
                ),
            )

    @asynccontextmanager
    async def provider(_profile):
        yield Provider()

    handler = SetupModelProxyHandler(
        sessions=sessions,
        authorization=lambda *_args: _async_value(object()),
        calls=lambda *_args: calls,
        profiles=lambda _session: Profiles(),
        outputs=Outputs(),
        bindings=lambda _session: Bindings(),
        provider=provider,
    )

    assert (await handler.handle(request)).outcome == "unavailable"
    first_events = list(events)
    assert first_events.index(("observe", "response-1")) < first_events.index(
        "store_model_response"
    )
    assert first_events[-1] == "complete"

    assert (await handler.handle(request)).outcome == "completed"
    assert provider_calls == 1
    assert events[-5:] == [
        "recover",
        "recover_response_art",
        "bind_model_response",
        "read_response",
        "complete",
    ]

    assert (await handler.handle(request)).outcome == "completed"
    assert provider_calls == 1
    assert events[-2:] == ["recover", "read_response"]


async def _async_value(value):
    return value
