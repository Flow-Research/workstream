from __future__ import annotations

import asyncio
from hashlib import sha256
import logging
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response, StreamingResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, field_validator
import pytest
from starlette.requests import Request

from app.core.api_controls import ApiErrorResponse, error_response
from app.core.config import Settings
from app.main import create_app


def _assert_uuid(value: str) -> None:
    parsed = UUID(value)
    assert str(parsed) == value
    assert parsed.int != 0
    assert parsed.version in range(1, 9)


def test_error_response_fallback_ids_remain_consistent() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    response = error_response(
        request,
        status_code=500,
        code="internal_error",
        message="Internal server error",
    )

    correlation_id = response.headers["x-correlation-id"]
    assert response.headers["x-request-id"] == correlation_id
    assert f'"correlation_id":"{correlation_id}"'.encode() in response.body


async def _get(app, path: str = "/health", **kwargs):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        return await client.get(path, **kwargs)


async def test_missing_and_supplied_request_context_propagates() -> None:
    app = create_app()
    generated = await _get(app)
    request_id = str(uuid4())
    correlation_id = str(uuid4())
    supplied = await _get(
        app,
        headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
    )
    request_only = await _get(app, headers={"X-Request-ID": request_id})
    correlation_only = await _get(app, headers={"X-Correlation-ID": correlation_id})

    _assert_uuid(generated.headers["x-request-id"])
    assert generated.headers["x-correlation-id"] == generated.headers["x-request-id"]
    assert supplied.headers["x-request-id"] == request_id
    assert supplied.headers["x-correlation-id"] == correlation_id
    assert request_only.headers["x-request-id"] == request_id
    assert request_only.headers["x-correlation-id"] == request_id
    _assert_uuid(correlation_only.headers["x-request-id"])
    assert correlation_only.headers["x-correlation-id"] == correlation_id


@pytest.mark.parametrize(
    "invalid_id",
    [
        str(uuid4()).upper(),
        str(uuid4()).replace("-", ""),
        "00000000-0000-0000-0000-000000000000",
        "00000000-0000-9000-8000-000000000001",
        f"{uuid4()}, {uuid4()}",
    ],
)
async def test_invalid_request_context_short_circuits_without_reflection(
    invalid_id: str,
) -> None:
    app = create_app()
    called = False

    @app.get("/_test/not-called")
    async def not_called() -> dict[str, bool]:
        nonlocal called
        called = True
        return {"called": True}

    response = await _get(app, "/_test/not-called", headers={"X-Request-ID": invalid_id})

    assert response.status_code == 400
    assert called is False
    assert response.headers["x-request-id"] == response.headers["x-correlation-id"]
    _assert_uuid(response.headers["x-request-id"])
    assert invalid_id not in response.text
    assert response.json() == {
        "detail": "Invalid request identifier",
        "error": {
            "code": "invalid_request",
            "message": "Invalid request identifier",
            "details": {},
            "correlation_id": response.headers["x-correlation-id"],
            "retryable": False,
        },
    }


@pytest.mark.parametrize(
    "headers",
    [
        [(b"x-request-id", str(uuid4()).encode())] * 2,
        [
            (b"x-request-id", str(uuid4()).encode()),
            (b"X-Request-ID", str(uuid4()).encode()),
        ],
        [(b"x-correlation-id", str(uuid4()).encode())] * 2,
        [(b"x-request-id", b"\xff" * 36)],
    ],
)
async def test_duplicate_and_non_ascii_request_context_is_rejected(
    headers: list[tuple[bytes, bytes]],
) -> None:
    response = await _get(create_app(), headers=headers)

    assert response.status_code == 400
    assert response.headers["x-request-id"] == response.headers["x-correlation-id"]
    assert response.json()["error"]["code"] == "invalid_request"


async def test_concurrent_request_context_remains_isolated() -> None:
    app = create_app()
    identifiers = [(str(uuid4()), str(uuid4())) for _ in range(12)]

    async def call(request_id: str, correlation_id: str):
        return await _get(
            app,
            headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
        )

    responses = await asyncio.gather(*(call(*pair) for pair in identifiers))

    assert [
        (response.headers["x-request-id"], response.headers["x-correlation-id"])
        for response in responses
    ] == identifiers


async def test_response_context_overwrites_ids_and_preserves_headers() -> None:
    app = create_app()
    request_id = str(uuid4())
    correlation_id = str(uuid4())

    @app.get("/_test/headers")
    async def headers() -> Response:
        response = Response(
            "ok",
            headers={
                "X-Request-ID": str(uuid4()),
                "X-Correlation-ID": str(uuid4()),
                "Retry-After": "7",
            },
        )
        response.raw_headers.extend(
            [(b"set-cookie", b"first=1"), (b"set-cookie", b"second=2")]
        )
        return response

    response = await _get(
        app,
        "/_test/headers",
        headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
    )

    assert response.status_code == 200
    assert response.content == b"ok"
    assert response.headers["content-length"] == "2"
    assert response.headers["retry-after"] == "7"
    assert response.headers.get_list("set-cookie") == ["first=1", "second=2"]
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-correlation-id"] == correlation_id


async def test_streaming_and_background_responses_keep_context() -> None:
    app = create_app()
    completed: list[str] = []

    @app.get("/_test/stream")
    async def stream(background_tasks: BackgroundTasks) -> StreamingResponse:
        async def content():
            yield b"first"
            yield b"second"

        background_tasks.add_task(completed.append, "done")
        return StreamingResponse(content(), background=background_tasks)

    response = await _get(app, "/_test/stream")

    assert response.status_code == 200
    assert response.content == b"firstsecond"
    _assert_uuid(response.headers["x-request-id"])
    assert response.headers["x-correlation-id"] == response.headers["x-request-id"]
    assert completed == ["done"]


async def test_background_failure_is_bounded_after_response_start(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = logging.getLogger("app.core.api_controls")
    # In-process Alembic tests disable existing loggers through fileConfig.
    monkeypatch.setattr(logger, "disabled", False)
    caplog.set_level(logging.ERROR, logger=logger.name)
    app = create_app()

    @app.get("/_test/background-failure")
    async def background_failure(background_tasks: BackgroundTasks) -> dict[str, bool]:
        def fail() -> None:
            raise RuntimeError("token=secret-background-value")

        background_tasks.add_task(fail)
        return {"accepted": True}

    response = await _get(app, "/_test/background-failure")

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert response.headers["x-request-id"]
    assert "request_failed_after_response_start" in caplog.text
    assert "secret-background-value" not in caplog.text


@pytest.mark.parametrize(
    ("status_code", "code", "message", "retryable"),
    [
        (400, "invalid_request", "Invalid request", False),
        (401, "invalid_token", "Invalid bearer token", False),
        (403, "permission_not_granted", "Permission not granted", False),
        (409, "conflict", "Request conflict", False),
        (422, "invalid_request", "Invalid request", False),
        (429, "rate_limit_exceeded", "Rate limit exceeded", True),
        (503, "service_unavailable", "Service unavailable", True),
    ],
)
async def test_http_errors_use_stable_mapping_and_preserve_legacy_detail(
    status_code: int, code: str, message: str, retryable: bool
) -> None:
    app = create_app()

    async def fail() -> None:
        headers = {"Retry-After": "9"} if status_code == 429 else None
        raise HTTPException(status_code=status_code, detail="legacy detail", headers=headers)

    app.add_api_route(f"/_test/error/{status_code}", fail, methods=["GET"])
    response = await _get(app, f"/_test/error/{status_code}")

    assert response.status_code == status_code
    assert response.json()["detail"] == "legacy detail"
    assert response.json()["error"] == {
        "code": code,
        "message": message,
        "details": {},
        "correlation_id": response.headers["x-correlation-id"],
        "retryable": retryable,
    }
    ApiErrorResponse.model_validate(response.json())
    if status_code == 429:
        assert response.headers["retry-after"] == "9"


@pytest.mark.parametrize("debug", [False, True])
async def test_not_found_method_not_allowed_and_unhandled_errors_are_private(
    debug: bool,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = logging.getLogger("app.core.api_controls")
    monkeypatch.setattr(logger, "disabled", False)
    caplog.set_level(logging.ERROR, logger=logger.name)
    app = create_app(Settings(debug=debug))

    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("token=secret database failure")

    not_found = await _get(app, "/_test/missing")
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        method_not_allowed = await client.post("/health")
    failed = await _get(app, "/_test/boom")

    for response, status_code, detail, code, message in [
        (not_found, 404, "Not Found", "resource_not_found", "Resource not found"),
        (
            method_not_allowed,
            405,
            "Method Not Allowed",
            "method_not_allowed",
            "Method not allowed",
        ),
        (
            failed,
            500,
            "Internal server error",
            "internal_error",
            "Internal server error",
        ),
    ]:
        assert response.status_code == status_code
        assert response.json() == {
            "detail": detail,
            "error": {
                "code": code,
                "message": message,
                "details": {},
                "correlation_id": response.headers["x-correlation-id"],
                "retryable": False,
            },
        }
        ApiErrorResponse.model_validate(response.json())

    failure_record = next(
        record
        for record in caplog.records
        if record.message == "request_failed_before_response_start"
    )
    assert failure_record.correlation_id == failed.headers["x-correlation-id"]
    assert "secret" not in failed.text
    assert "secret" not in caplog.text


class ManyInvalidValues(BaseModel):
    """Request fixture that can produce more errors than the response cap."""

    values: list[Annotated[int, Field(gt=0)]]


class SafeValidatorMessage(BaseModel):
    """Request fixture for legacy sanitized validator compatibility."""

    value: str

    @field_validator("value")
    @classmethod
    def reject_value(cls, _value: str) -> str:
        raise ValueError("safe compatibility message")


async def test_validation_summary_is_bounded_and_legacy_messages_remain() -> None:
    app = create_app()

    @app.post("/_test/many-values")
    async def many_values(_payload: ManyInvalidValues) -> None:
        return None

    @app.post("/_test/safe-message")
    async def safe_message(_payload: SafeValidatorMessage) -> None:
        return None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        many = await client.post("/_test/many-values", json={"values": [-1] * 25})
        safe = await client.post("/_test/safe-message", json={"value": "rejected"})

    assert many.status_code == 422
    assert len(many.json()["detail"]) == 20
    assert len(many.json()["error"]["details"]["errors"]) == 20
    assert many.json()["error"]["details"]["truncated"] is True
    assert set(many.json()["error"]["details"]["errors"][0]) == {"type", "loc"}
    assert safe.status_code == 422
    assert "safe compatibility message" in safe.text
    assert "safe compatibility message" not in str(safe.json()["error"]["details"])
    assert safe.json()["detail"][0]["input"] == "redacted"


async def test_validation_summary_redacts_unsupported_location_parts() -> None:
    app = create_app()

    @app.get("/_test/unsupported-location")
    async def unsupported_location() -> None:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", None),
                    "input": "secret",
                    "ctx": "bounded context",
                }
            ]
        )

    response = await _get(app, "/_test/unsupported-location")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", None]
    assert response.json()["detail"][0]["ctx"] == "bounded context"
    assert response.json()["error"]["details"]["errors"][0]["loc"] == [
        "query",
        "redacted",
    ]


def test_openapi_documents_request_error_and_response_context() -> None:
    schema = create_app().openapi()
    error_schema = schema["components"]["schemas"]["ApiError"]
    validation_schema = schema["components"]["schemas"]["HTTPValidationError"]

    assert set(error_schema["required"]) == {
        "code",
        "message",
        "details",
        "correlation_id",
        "retryable",
    }
    assert "error" in validation_schema["required"]
    response_schema = schema["components"]["schemas"]["ApiErrorResponse"]
    assert response_schema["required"] == ["error"]
    assert set(response_schema["properties"]) == {"error", "detail"}
    assert response_schema["additionalProperties"] is False
    methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    route_inventory = sorted(
        f"{method.upper()} {path}"
        for path, path_item in schema["paths"].items()
        for method in path_item
        if method in methods
    )
    protected_inventory = sorted(
        f"{method.upper()} {path}"
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method in methods and operation.get("security")
    )
    assert len(route_inventory) == 57
    assert sha256("\n".join(route_inventory).encode()).hexdigest() == (
        "03f8b0166ded1cf563acfd32443aeefc3f7331eb59a46756ab4f551c6d673dc1"
    )
    assert len(protected_inventory) == 55
    assert sha256("\n".join(protected_inventory).encode()).hexdigest() == (
        "229a935e1d17697fd0b315ac4f8638644b1fdd7b6cf48a372e5dd2b584eef02c"
    )
    assert set(schema["paths"]["/health"]["get"]["responses"]) == {"200", "400", "500"}
    assert {"401", "403", "503"} <= set(
        schema["paths"]["/api/v1/auth/me"]["get"]["responses"]
    )
    service_actor_responses = schema["paths"]["/api/v1/service-actors"]["post"][
        "responses"
    ]
    assert "409" in service_actor_responses
    assert service_actor_responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    assert {"404"} <= set(
        schema["paths"]["/api/v1/tasks/{task_id}"]["get"]["responses"]
    )
    assert {"404", "409"} <= set(
        schema["paths"]["/api/v1/tasks/{task_id}/claim"]["post"]["responses"]
    )
    action_declarations = {
        f"{method.upper()} {path}": operation["x-workstream-action-id"]
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method in methods and "x-workstream-action-id" in operation
    }
    assert action_declarations == {
        "GET /api/v1/actors/me": "actor.profile.read_self",
        "PATCH /api/v1/actors/me": "actor.profile.update_self",
        "GET /api/v1/actors/{actor_profile_id}": "actor.profile.read",
        "GET /api/v1/actors/{actor_profile_id}/identity-links": "actor.identity_link.read",
        "POST /api/v1/service-actors": "actor.service.provision",
        "GET /api/v1/authorization/permissions": "authorization.permission_catalogue.read",
        "GET /api/v1/authorization/admin-role-definitions": (
            "authorization.admin_role_definitions.read"
        ),
        "GET /api/v1/admin-role-grants": "admin_role_grant.list",
        "POST /api/v1/admin-role-grants": "admin_role_grant.issue",
        "GET /api/v1/actors/{actor_profile_id}/admin-role-grants": (
            "actor.admin_role_grant_history.read"
        ),
        "POST /api/v1/admin-role-grants/{grant_id}/revoke": "admin_role_grant.revoke",
    }
    for path, schema_name in (
        ("/api/v1/actors/{actor_profile_id}", "ActorProfileAdminResponse"),
        (
            "/api/v1/actors/{actor_profile_id}/identity-links",
            "ActorIdentityLinkAdminResponse",
        ),
    ):
        operation = schema["paths"][path]["get"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{schema_name}"
        }
        assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ApiErrorResponse"
        }
        assert schema["components"]["schemas"][schema_name]["additionalProperties"] is False
    assert not any("bootstrap" in path for path in schema["paths"])
    assert {"404", "409"} <= set(
        schema["paths"]["/api/v1/projects/{project_id}/guides/{guide_id}/activate"][
            "post"
        ]["responses"]
    )
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method not in {"get", "put", "post", "delete", "options", "head", "patch"}:
                continue
            request_headers = {
                parameter["name"] for parameter in operation["parameters"]
            }
            assert {"X-Request-ID", "X-Correlation-ID"} <= request_headers
            for response in operation["responses"].values():
                assert {"X-Request-ID", "X-Correlation-ID"} <= set(response["headers"])
                assert response["headers"]["X-Request-ID"]["required"] is True
                assert response["headers"]["X-Correlation-ID"]["required"] is True
