from __future__ import annotations

from typing import Any

import pytest
from conftest import mcp_call
from starlette.testclient import TestClient

from workstream_mcp.auth import CredentialError, request_bearer, request_correlation_id


class Headers:
    def __init__(self, values: dict[str, list[str]]) -> None:
        self.values = values

    def getlist(self, key: str) -> list[str]:
        return self.values.get(key, [])


@pytest.mark.parametrize("value", ["Bearer a.b-c_d~e+/=", "bearer case-insensitive"])
def test_transport_safe_bearer_is_preserved_exactly(value: str) -> None:
    assert request_bearer(Headers({"authorization": [value]})) == value


@pytest.mark.parametrize(
    "values", [[], [""], ["Basic abc"], ["Bearer "], ["Bearer has space"], ["Bearer a", "Bearer b"]]
)
def test_invalid_bearer_is_rejected(values: list[str]) -> None:
    with pytest.raises(CredentialError):
        request_bearer(Headers({"authorization": values}))


def test_only_uuid_correlation_ids_are_forwarded() -> None:
    valid = "a2b3c4d5-e6f7-4123-8abc-1234567890ab"
    assert request_correlation_id(Headers({"x-correlation-id": [valid]})) == valid
    assert request_correlation_id(Headers({"x-correlation-id": ["unsafe\nheader"]})) is None
    assert request_correlation_id(Headers({"x-request-id": [valid, valid]})) is None


@pytest.mark.parametrize("token", [None, "", "bad token"])
def test_invalid_or_missing_credentials_do_not_dispatch(
    adapter: tuple[TestClient, list[Any], dict[str, Any]], token: str | None
) -> None:
    client, received, _ = adapter
    response = mcp_call(client, token=token)
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True
    assert received == []


def test_caller_bearer_and_correlation_are_forwarded_without_mutation(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, _ = adapter
    correlation = "a2b3c4d5-e6f7-4123-8abc-1234567890ab"
    response = mcp_call(
        client, token="opaque.token+/=", extra_headers={"x-correlation-id": correlation}
    )
    assert response.json()["result"]["isError"] is False
    assert len(received) == 1
    assert received[0].headers["authorization"] == "Bearer opaque.token+/="
    assert received[0].headers["x-request-id"] == correlation
    assert str(received[0].url) == "http://workstream.test/api/v1/actors/me"
