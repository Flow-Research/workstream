"""Model relay selectors remain private, POST-only and request-bound."""

import asyncio
import json
import struct
from unittest.mock import AsyncMock

import pytest

from app.adapters.checkers import external_checker_execution_factory
from app.interfaces.external_checker_execution import (
    ExternalCheckerModelGrant,
)
from workstream_external_services import ExternalServiceProtocolError
from app.modules.checkers.api.external import (
    external_checker_json_hash,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
)
from tests.checkers.external.support import (
    empty_external_material_grant,
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
            observed = await read_fixture_native_request(
                reader, writer, fixture_placement(value.registry.image_digest, callback_relay=True),
            )
            if observed is None:
                return
            received.set_result(observed)
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
    from tests.checkers.external.test_remote_node import fixture_placement, read_fixture_native_request, remote_adapter_endpoint

    try:
        async with remote_adapter_endpoint(tmp_path, path, model_proxy_socket_path=path) as endpoint:
            adapter = external_checker_execution_factory(
                **endpoint, timeout_seconds=90.0,
            ).create("remote_tls")
            await adapter.execute(
                value,
                empty_external_material_grant(value, suffix="b"),
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
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,substituted", [("pre_submit", False), ("post_submit", True)])
async def test_wrong_phase_or_request_cannot_open_model_transport(tmp_path, monkeypatch, phase, substituted):
    value = request(phase)
    connect = AsyncMock()
    monkeypatch.setattr(asyncio, "open_connection", connect)
    from tests.checkers.external.test_remote_node import _certificate_files, fixture_runner_endpoints

    certificates = _certificate_files(tmp_path)
    adapter = external_checker_execution_factory(
        endpoints=fixture_runner_endpoints(),
        ca_path=certificates["ca"],
        certificate_path=certificates["client_certificate"],
        private_key_path=certificates["client_key"],
        model_proxy_socket_path=None,
        timeout_seconds=90.0,
    ).create("remote_tls")
    grant = ExternalCheckerModelGrant(
        "model_" + "a" * 32, "sha256:" + "0" * 64 if substituted else value.request_digest,
    )
    with pytest.raises(ExternalServiceProtocolError):
        await adapter.execute(
            value,
            empty_external_material_grant(value, suffix="b"),
            model_grant=grant,
        )
    connect.assert_not_called()
