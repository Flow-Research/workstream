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
    """Require exact Swagger asset versions, integrity digests and nonpersistent authorization."""
    from html.parser import HTMLParser

    class Assets(HTMLParser):
        def __init__(self):
            """Collect external asset attributes from the rendered documentation page."""
            super().__init__()
            self.assets = []

        def handle_starttag(self, tag, attrs):
            """Record script and stylesheet sources for integrity assertions."""
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


async def test_swagger_browser_oauth_preserves_bearer_api_authority() -> None:
    from app.core.config import Settings
    settings = Settings(
        auth_provider="flow", flow_auth_local_hmac_secret=None,
        token_issuer="https://identity.example.test/realms/flow",
        token_jwks_url="https://identity.example.test/realms/flow/protocol/openid-connect/certs",
        token_audience="workstream-api", token_algorithms="RS256",
        token_introspection_mode="disabled",
        token_introspection_disabled_reason="Short-lived test credentials",
    )
    app = create_app(settings)
    assert app.state.auth_configuration_valid
    schema = app.openapi()
    oauth = schema["components"]["securitySchemes"]["FlowIdentity"]["flows"]["authorizationCode"]
    assert oauth["authorizationUrl"] == settings.token_issuer + "/protocol/openid-connect/auth"
    assert oauth["tokenUrl"] == settings.token_issuer + "/protocol/openid-connect/token"
    assert set(oauth["scopes"]) == {"openid", "workstream:access", "workstream-api-audience"}
    protected = schema["paths"]["/api/v1/actors/me"]["get"]["security"]
    assert {"HTTPBearer": []} in protected
    assert {"FlowIdentity": ["openid", "workstream:access", "workstream-api-audience"]} in protected
    assert all(not ("HTTPBearer" in item and "FlowIdentity" in item) for item in protected)
    assert not schema["paths"]["/api/v1/health"]["get"].get("security")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://api.example.test") as client:
        page = await client.get("/docs")
        callback = await client.get("/docs/oauth2-redirect")
        denied = await client.get("/api/v1/actors/me")
    assert "usePkceWithAuthorizationCodeGrant: true" in page.text
    assert 'clientId: "workstream-swagger"' in page.text
    assert "persistAuthorization: false" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert callback.status_code == 200
    assert "swaggerUIRedirectOauth2" in callback.text
    assert callback.headers["referrer-policy"] == "no-referrer"
    assert denied.status_code == 401
