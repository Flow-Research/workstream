"""Closed forge selectors cross the existing transport without callback authority."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import struct
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.adapters.checkers import external_checker_execution_factory
from app.adapters.checkers.model_execution import ModelAwareExternalExecution
from app.interfaces.external_checker_execution import ExternalCheckerMaterialGrant
from app.interfaces.external_services import ExternalServiceProtocolError
from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
    ExternalCheckerSchema,
    external_checker_json_hash,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
)
from app.modules.checkers.api.forge_locator import (
    ExternalCheckerForgeLocator,
    require_forge_locator_request,
)
from tests.checkers.external.support import (
    SHA,
    execution_identity,
    execution_material,
    registry_entry,
    registry_spec,
)


def _request(*, locate=True, maximum_output_bytes=32768, output_document=None, model=False):
    values = registry_spec("post_submit", maximum_output_bytes=maximum_output_bytes).model_dump()
    documents = {
        "configuration_schema": {"type": "object"},
        "input_schema": {
            "type": "object",
            "properties": {
                "task_version": {"type": "string"},
                "workstream_forge_facts_stage": {"type": "string", "const": "locate"},
            },
            "additionalProperties": False,
        },
        "output_schema": output_document or {"type": "object"},
    }
    for key, document in documents.items():
        values[key] = ExternalCheckerSchema(
            schema_id=values[key]["schema_id"],
            schema_version="v1",
            document=document,
            schema_sha256=external_checker_json_hash(document),
        )
    spec = ExternalCheckerRegistrySpec.model_validate(values)
    entry_values = registry_entry("post_submit").model_dump()
    entry_values.update(spec.model_dump(), entry_digest=spec.spec_digest)
    entry = ExternalCheckerRegistryEntry.model_validate(entry_values)
    identity = execution_identity("post_submit")
    configuration = {"workstream_forge_facts_version": "v1"}
    if model:
        configuration.update(
            model_profile_id=str(uuid4()), model_profile_version=1, model_profile_digest=SHA
        )
    inputs = {"task_version": "v1"}
    if locate:
        inputs["workstream_forge_facts_stage"] = "locate"
    return make_external_checker_execution_request(
        registry=entry,
        identity=identity,
        configuration=configuration,
        configuration_sha256=external_checker_json_hash(configuration),
        input=inputs,
        input_sha256=external_checker_json_hash(inputs),
        materials=(execution_material(identity),),
    )


def _locator(request, change_url=None, **changes):
    value = dict(
        schema_version="external_checker_forge_locator.v1",
        request_digest=request.request_digest,
        registry_entry_id=str(request.registry.registry_entry_id),
        registry_entry_digest=request.registry.entry_digest,
        phase="post_submit",
        change_url=change_url,
    )
    value.update(changes)
    value["locator_digest"] = external_checker_json_hash(value)
    return value


def _work_result(request, *, infrastructure=False):
    return make_external_checker_execution_result(
        request_digest=request.request_digest,
        registry_entry_id=request.registry.registry_entry_id,
        registry_entry_digest=request.registry.entry_digest,
        phase="post_submit",
        outcome="infrastructure_failed" if infrastructure else "completed",
        verdict=None if infrastructure else "passed",
        findings=(),
        infrastructure_failure_code="invalid_output" if infrastructure else None,
    ).model_dump(mode="json")


def _isolation(request):
    return dict(
        repository="registry.example/checker",
        platform_manifest_digest=request.registry.image_digest,
        platform_manifest_media_type="application/vnd.oci.image.manifest.v1+json",
        platform_manifest_byte_count=128,
        operating_system="linux",
        architecture="amd64",
        config_image_id=SHA,
        runtime="runc",
        isolation_mode="docker-dev",
        sandbox_uid=65532,
        sandbox_gid=65532,
    )


@asynccontextmanager
async def _service(tmp_path, request, result, *, isolation=True):
    received = []
    socket = tmp_path / "checker.sock"

    async def handle(reader, writer):
        try:
            size = struct.unpack(">I", await reader.readexactly(4))[0]
            received.append(json.loads(await reader.readexactly(size)))
            body = json.dumps(
                dict(
                    protocol_version="external_checker_service.v1",
                    result=result,
                    isolation=_isolation(request) if isolation else None,
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            writer.write(struct.pack(">I", len(body)) + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, socket)
    try:
        yield (
            external_checker_execution_factory(
                socket_path=socket,
                timeout_seconds=90.0,
            ).create("unix_socket"),
            received,
        )
    finally:
        server.close()
        await server.wait_closed()


def _grant():
    return ExternalCheckerMaterialGrant(grant_id="extract_" + "a" * 32, binding_digest=SHA)


@pytest.mark.parametrize("url", [None, "https://forge.example/o/r/pull/2", "汉" * 2048])
def test_locator_parser_accepts_bound_null_and_character_bounded_urls(url):
    request = _request()
    result = ExternalCheckerForgeLocator.model_validate_json(json.dumps(_locator(request, url)))
    result.validate_request(request)
    assert result.change_url == url


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [None, "https://forge.example/o/r/pull/2"])
async def test_locator_socket_uses_separate_operation_and_no_model_grant(tmp_path, url):
    request = _request()
    async with _service(tmp_path, request, _locator(request, url)) as (adapter, received):
        response = await adapter.locate_forge_change(request, _grant())
    assert response.result.change_url == url
    assert response.isolation is not None
    assert received[0]["operation"] == "locate_forge_change"
    assert received[0]["request"]["request_digest"] == request.request_digest
    assert received[0]["model_grant"] is None
    assert received[0]["grant"] == {"grant_id": _grant().grant_id, "binding_digest": SHA}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"request_digest": "sha256:" + "b" * 64},
        {"registry_entry_id": str(uuid4())},
        {"registry_entry_digest": "sha256:" + "b" * 64},
        {"phase": "pre_submit"},
        {"change_url": "x" * 2049},
        {"change_url": "bad\nurl"},
        {"change_url": "bad\u0085url"},
        {"change_url": ""},
        {"unexpected": "field"},
    ],
)
async def test_locator_socket_rejects_resigned_substitutions_and_invalid_values(tmp_path, changes):
    request = _request()
    async with _service(tmp_path, request, _locator(request, **changes)) as (adapter, _):
        with pytest.raises(ExternalServiceProtocolError):
            await adapter.locate_forge_change(request, _grant())


@pytest.mark.asyncio
async def test_locator_socket_rejects_changed_digest_missing_isolation_and_completed_verdict(
    tmp_path,
):
    request = _request()
    changed = _locator(request)
    changed["locator_digest"] = "sha256:" + "b" * 64
    for value, isolation in [
        (changed, True),
        (_locator(request), False),
        (_work_result(request), True),
    ]:
        async with _service(tmp_path, request, value, isolation=isolation) as (adapter, _):
            with pytest.raises(ExternalServiceProtocolError):
                await adapter.locate_forge_change(request, _grant())
        (tmp_path / "checker.sock").unlink()


@pytest.mark.asyncio
async def test_locator_socket_allows_infrastructure_failure_without_isolation(tmp_path):
    request = _request()
    async with _service(
        tmp_path, request, _work_result(request, infrastructure=True), isolation=False
    ) as (adapter, _):
        response = await adapter.locate_forge_change(request, _grant())
    assert response.result.outcome == "infrastructure_failed"
    assert response.isolation is None


@pytest.mark.asyncio
async def test_socket_operation_rejects_marker_mismatches_and_locator_as_work_result(tmp_path):
    request = _request()
    ordinary = _request(locate=False)
    async with _service(tmp_path, ordinary, _locator(ordinary)) as (adapter, received):
        with pytest.raises(ExternalServiceProtocolError):
            await adapter.execute(request, _grant())
        with pytest.raises(ExternalServiceProtocolError):
            await adapter.locate_forge_change(ordinary, _grant())
        assert received == []
        with pytest.raises(ExternalServiceProtocolError):
            await adapter.execute(ordinary, _grant())
    assert received[0]["operation"] == "execute"


@pytest.mark.asyncio
async def test_locator_validates_locked_output_schema_and_output_byte_limit(tmp_path):
    for request in [
        _request(maximum_output_bytes=1024),
        _request(output_document={"type": "object", "required": ["project_specific_field"]}),
    ]:
        value = _locator(request, "汉" * 1000)
        parsed = ExternalCheckerForgeLocator.model_validate_json(json.dumps(value))
        with pytest.raises(ExternalCheckerContractError):
            parsed.validate_request(request)
        async with _service(tmp_path, request, value) as (adapter, _):
            with pytest.raises(ExternalServiceProtocolError):
                await adapter.locate_forge_change(request, _grant())
        (tmp_path / "checker.sock").unlink()


def test_locator_request_requires_locked_version_phase_and_schema_declaration():
    original = _request()
    require_forge_locator_request(original)
    for configuration, input_schema in [
        ({"workstream_forge_facts_version": "v2"}, original.registry.input_schema),
        (
            original.configuration,
            ExternalCheckerSchema(
                schema_id=original.registry.input_schema.schema_id,
                schema_version="v1",
                document={"type": "object"},
                schema_sha256=external_checker_json_hash({"type": "object"}),
            ),
        ),
    ]:
        # Exercise the explicit capability guard independently of request digest validation.
        changed = original.model_copy(
            update={
                "configuration": configuration,
                "registry": original.registry.model_copy(update={"input_schema": input_schema}),
            }
        )
        with pytest.raises(ExternalCheckerContractError, match="not selected"):
            require_forge_locator_request(changed)
    changed = original.model_copy(update={"identity": execution_identity("pre_submit")})
    with pytest.raises(ExternalCheckerContractError, match="not selected"):
        require_forge_locator_request(changed)


@pytest.mark.asyncio
async def test_model_wrapper_locator_delegates_without_authorization_sessions_or_paid_calls(
    tmp_path, monkeypatch
):
    request = _request(model=True)
    sessions = Mock(side_effect=AssertionError("locator opened model session"))
    authorize = AsyncMock(side_effect=AssertionError("locator requested model authority"))
    paid_calls = Mock(side_effect=AssertionError("locator requested paid calls"))
    monkeypatch.setattr("app.adapters.auth.checker_model_service_authorization", authorize)
    monkeypatch.setattr("app.adapters.checkers.model_call_service", paid_calls)
    async with _service(tmp_path, request, _locator(request)) as (adapter, received):
        wrapped = ModelAwareExternalExecution(execution=adapter, sessions=sessions)
        response = await wrapped.locate_forge_change(request, _grant())
    assert response.result.change_url is None
    assert received[0]["model_grant"] is None
    sessions.assert_not_called()
    authorize.assert_not_awaited()
    paid_calls.assert_not_called()
