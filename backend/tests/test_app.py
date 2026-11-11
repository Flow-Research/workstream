from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import create_app


def _application_paths(app) -> set[str]:
    """Return concrete application paths across FastAPI router representations."""
    paths = set(app.openapi()["paths"])
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        route_contexts = getattr(route, "effective_route_contexts", None)
        if route_contexts is not None:
            paths.update(context.path for context in route_contexts())
    return paths


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
    paths = _application_paths(app)
    forbidden_segments = {"login", "signup", "register", "password", "password-reset"}

    assert not any(
        segment in forbidden_segments
        for path in paths
        for segment in path.lower().strip("/").split("/")
    )


async def test_swagger_uses_pinned_integrity_checked_assets() -> None:
    from html.parser import HTMLParser

    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.assets = []

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag in {"script", "link"} and ("src" in attributes or "href" in attributes):
                self.assets.append(attributes)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://testserver",
    ) as client:
        response = await client.get("/docs")
    assert response.status_code == 200
    parsed = Assets()
    parsed.feed(response.text)
    expected = {
        "swagger-ui-bundle.js": "sha384-7xcoc6ZKDFF7Ek627QTC3Bg/K+5Y36NJ8MWAE43D2m6+3Sh9XO3tdsfHhrS8gNIQ",
        "swagger-ui.css": "sha384-3nuX7df3EaAoiqLBeyS1Ola0Gpg9ryJKVtarubwfnA1cOH8AWHUdbPSIvEqPZ9VH",
    }
    assert len(parsed.assets) == len(expected)
    for asset in parsed.assets:
        url = asset.get("src", asset.get("href"))
        filename = url.rsplit("/", 1)[1]
        assert url == f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.0/{filename}"
        assert asset["integrity"] == expected[filename]
        assert asset["crossorigin"] == "anonymous"
    assert "url: '/openapi.json'" in response.text
    assert "persistAuthorization: false" in response.text
