"""Model relay selectors remain private, POST-only and request-bound."""

import asyncio
import json
import struct
from unittest.mock import AsyncMock

import pytest

from app.adapters.checkers import external_checker_execution_factory
from app.interfaces.external_checker_execution import (
    ExternalCheckerMaterialGrant,
    ExternalCheckerModelGrant,
)
from workstream_external_services import ExternalServiceProtocolError
from app.modules.checkers.api.external import (
    external_checker_json_hash,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
)
from tests.checkers.external.support import (
    execution_identity,
    execution_material,
    registry_entry,
)


def request(phase="post_submit"):
    """Build actual normalized custody without assigning model authority."""
    identity = execution_identity(phase)
    inputs = {"task_version": "v3"}
    return make_external_checker_execution_request(
        registry=registry_entry(phase),
        identity=identity,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
        input=inputs,
        input_sha256=external_checker_json_hash(inputs),
        materials=(execution_material(identity),),
    )


@pytest.mark.asyncio
async def test_model_selector_is_outside_image_request(tmp_path):
    value = request()
    grant = ExternalCheckerModelGrant("model_" + "a" * 32, value.request_digest)
    result = make_external_checker_execution_result(
        request_digest=value.request_digest,
        registry_entry_id=value.registry.registry_entry_id,
        registry_entry_digest=value.registry.entry_digest,
        phase="post_submit",
        outcome="infrastructure_failed",
        verdict=None,
        findings=(),
        infrastructure_failure_code="implementation_unavailable",
    )
    received = asyncio.get_running_loop().create_future()

    async def handle(reader, writer):
        try:
            size = struct.unpack(">I", await reader.readexactly(4))[0]
            received.set_result(json.loads(await reader.readexactly(size)))
            body = json.dumps({
                "protocol_version": "external_checker_service.v1",
                "result": result.model_dump(mode="json"),
                "isolation": None,
            }).encode()
            writer.write(struct.pack(">I", len(body)) + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    path = tmp_path / "checker.sock"
    server = await asyncio.start_unix_server(handle, path)
    try:
        adapter = external_checker_execution_factory(
            socket_path=path, timeout_seconds=90.0,
        ).create("unix_socket")
        await adapter.execute(
            value, ExternalCheckerMaterialGrant("extract_" + "b" * 32, value.request_digest),
            model_grant=grant,
        )
        wire = await asyncio.wait_for(received, 1)
        assert wire["model_grant"] == {
            "grant_id": grant.grant_id, "binding_digest": value.request_digest,
        }
        assert wire["request"] == value.model_dump(mode="json")
        assert grant.grant_id not in json.dumps(wire["request"])
        assert grant.grant_id not in repr(grant)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,substituted", [("pre_submit", False), ("post_submit", True)])
async def test_wrong_phase_or_request_cannot_open_model_transport(tmp_path, monkeypatch, phase, substituted):
    value = request(phase)
    connect = AsyncMock()
    monkeypatch.setattr(asyncio, "open_unix_connection", connect)
    adapter = external_checker_execution_factory(
        socket_path=tmp_path / "unused.sock", timeout_seconds=90.0,
    ).create("unix_socket")
    grant = ExternalCheckerModelGrant(
        "model_" + "a" * 32, "sha256:" + "0" * 64 if substituted else value.request_digest,
    )
    with pytest.raises(ExternalServiceProtocolError):
        await adapter.execute(
            value, ExternalCheckerMaterialGrant("extract_" + "b" * 32, value.request_digest),
            model_grant=grant,
        )
    connect.assert_not_called()
