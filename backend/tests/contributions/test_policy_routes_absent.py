"""CP04A remains hidden from delivery routing."""

from app.api.router import api_router


def test_policy_routes_are_not_registered() -> None:
    paths = {route.path for route in api_router.routes if hasattr(route, "path")}
    assert all("contribution" not in path or "policy" not in path for path in paths)
