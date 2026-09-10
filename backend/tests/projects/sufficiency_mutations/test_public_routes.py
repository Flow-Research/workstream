"""Every public sufficiency mutation conceals fixed-service callers early."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.modules.projects import guide_mutation_router as module
from app.modules.projects.repository import ProjectRepository
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.commands import create_payload


@pytest.mark.parametrize(
    "suffix,body,lookup_method",
    [
        ("sufficiency-reports", create_payload().model_dump(mode="json"), "get_guide"),
        (
            f"sufficiency-reports/{rows.REPORT}/acknowledge-warnings",
            {"acknowledgement_note": "Understood"},
            "get_guide_sufficiency_report",
        ),
    ],
)
async def test_public_mutation_conceals_service(monkeypatch, suffix, body, lookup_method):
    app = create_app(Settings(environment="test"))

    async def verified_service():
        return SimpleNamespace(token=SimpleNamespace(subject_kind="service"))

    app.dependency_overrides[module.get_auth_verification_result] = verified_service
    resolver = AsyncMock(side_effect=AssertionError("service reached actor resolution"))
    lookup = AsyncMock(side_effect=AssertionError("service reached project lookup"))
    monkeypatch.setattr(module, "resolve_authorization_actor", resolver)
    monkeypatch.setattr(ProjectRepository, lookup_method, lookup)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{rows.PROJECT}/guides/{rows.GUIDE}/{suffix}",
            headers={"Authorization": "Bearer service-token", "Idempotency-Key": str(rows.KEY)},
            json=body,
        )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "project_authorization_resource_not_found"
    resolver.assert_not_awaited()
    lookup.assert_not_awaited()
