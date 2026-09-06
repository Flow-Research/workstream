"""The retired derivation endpoint is absent from composition, not merely hidden."""

from fastapi.routing import APIRoute

from app.main import create_app


def test_retired_submission_derivation_route_is_not_registered() -> None:
    """A hidden route still violates retirement even when omitted from OpenAPI."""
    app = create_app()
    assert not any(
        route.path.rstrip("/").endswith("/derive-submission-artifact-policy")
        for route in app.routes
        if isinstance(route, APIRoute)
    )


def test_retired_submission_derivation_route_is_absent_from_openapi() -> None:
    """Clients must not discover the retired route through the public schema."""
    paths = create_app().openapi()["paths"]
    assert not any(
        path.rstrip("/").endswith("/derive-submission-artifact-policy") for path in paths
    )
