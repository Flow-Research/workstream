from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_create_app() -> None:
    app = create_app()

    assert app.title == "Workstream API"


async def test_health_endpoint() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_versioned_health_endpoint() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_no_local_auth_routes() -> None:
    app = create_app()
    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    forbidden_segments = {"login", "signup", "register", "password", "password-reset"}

    assert not any(
        segment in forbidden_segments
        for path in paths
        for segment in path.lower().strip("/").split("/")
    )
