from __future__ import annotations

import asyncio
import typing

import httpx2 as httpx
import pytest
from conftest import profile_fixture

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import WorkstreamGateway, create_http_client


def settings(**changes: typing.Any) -> Settings:
    values: dict[str, typing.Any] = {"api_url": "http://127.0.0.1:8000"}
    values.update(changes)
    return Settings(**values)


@pytest.mark.asyncio
async def test_gateway_preserves_valid_full_profile_and_uses_safe_client() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json=profile_fixture(), headers={"content-type": "application/json"}
        )

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        result = await WorkstreamGateway(settings(), client).profile_get("Bearer opaque")
    finally:
        await client.aclose()
    assert result.data == profile_fixture()
    assert result.failure is None
    assert seen[0].headers["accept-encoding"] == "identity"
    assert seen[0].headers["authorization"] == "Bearer opaque"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected_code"),
    [
        (
            401,
            {"error": {"code": "invalid_token", "message": "token secret", "details": {}}},
            "invalid_token",
        ),
        (
            403,
            {"error": {"code": "identity_link_revoked", "message": "private", "details": {}}},
            "identity_link_revoked",
        ),
        (500, {"error": {"code": "unknown_internal", "message": "secret", "details": {}}}, None),
    ],
)
async def test_gateway_returns_only_safe_upstream_failure(
    status: int, body: dict[str, object], expected_code: str | None
) -> None:
    client = httpx.AsyncClient(
        base_url="http://api.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body)),
    )
    try:
        result = await WorkstreamGateway(settings(), client).profile_get("Bearer opaque")
    finally:
        await client.aclose()
    assert result.data is None
    assert result.failure is not None
    assert result.failure.status == status
    assert result.failure.code == expected_code
    assert "secret" not in str(result.failure.payload())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        lambda: httpx.Response(
            200,
            json={"actor_profile_id": "missing fields"},
            headers={"content-type": "application/json"},
        ),
        lambda: httpx.Response(200, content=b"[]", headers={"content-type": "application/json"}),
        lambda: httpx.Response(200, json=profile_fixture(), headers={"content-type": "text/plain"}),
        lambda: httpx.Response(
            200,
            content=b"x" * 4096,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        ),
        lambda: httpx.Response(
            200,
            content=b"x" * 4096,
            headers={"content-type": "application/json", "content-length": "4096"},
        ),
    ],
)
async def test_gateway_rejects_invalid_or_oversized_success(response: typing.Any) -> None:
    client = httpx.AsyncClient(
        base_url="http://api.test", transport=httpx.MockTransport(lambda _: response())
    )
    try:
        result = await WorkstreamGateway(settings(max_response_bytes=1024), client).profile_get(
            "Bearer opaque"
        )
    finally:
        await client.aclose()
    assert result.data is None
    assert result.failure is not None
    assert result.failure.status == 502


@pytest.mark.asyncio
async def test_gateway_timeout_and_cancellation_have_distinct_outcomes() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(
            200, json=profile_fixture(), headers={"content-type": "application/json"}
        )

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        gateway = WorkstreamGateway(
            settings(
                total_timeout_seconds=0.1, connect_timeout_seconds=0.1, read_timeout_seconds=0.1
            ),
            client,
        )
        # Timeout outcome
        result = await gateway.profile_get("Bearer opaque")
        assert result.failure is not None
        assert result.failure.status == 504

        # Cancellation outcome
        gateway_no_timeout = WorkstreamGateway(settings(), client)
        task = asyncio.create_task(gateway_no_timeout.profile_get("Bearer opaque"))
        await asyncio.sleep(0)  # Yield to let the task start
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        await client.aclose()


def test_outbound_client_disables_environment_proxy_and_redirects() -> None:
    client = create_http_client(settings())
    try:
        assert client.follow_redirects is False
        assert client._trust_env is False
    finally:
        asyncio.run(client.aclose())
