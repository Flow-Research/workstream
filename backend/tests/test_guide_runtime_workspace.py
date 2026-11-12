"""Historical exact-ID OpenAI cleanup without current runtime dispatch."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx2
from openai import NotFoundError
import pytest

from app.adapters.project_agents import create_guide_runtime_cleanup_factory
from app.adapters.project_agents.openai_workspace import (
    OpenAIGuideRuntimeCleanupAdapter,
    RETAINED_OPENAI_GUIDE_RUNTIME_KEY,
    _cleanup_recorded_openai_guide_resources,
)
from workstream_external_services import UnknownExternalServiceProviderError
from app.modules.projects.api.guide_documents import (
    GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY,
    GuideRuntimeResource,
)


def missing(identifier="missing"):
    raise NotFoundError(
        "missing",
        response=httpx2.Response(
            404,
            request=httpx2.Request(
                "GET", f"https://api.openai.com/v1/resources/{identifier}"
            ),
        ),
        body=None,
    )


class Custody:
    def __init__(self, resources):
        self.resources = {item.allocation_id: item for item in resources}
        self.deleted = set()
        self.failed = set()

    async def cleanup_resources(self):
        return tuple(
            item
            for identifier, item in self.resources.items()
            if identifier not in self.deleted
        )

    async def record_deleted(self, identifier):
        self.deleted.add(identifier)

    async def record_cleanup_failed(self, identifier):
        self.failed.add(identifier)


def resource(kind, provider_id, *, parent=None):
    return GuideRuntimeResource(
        allocation_id=uuid4(),
        kind=kind,
        provider_id=provider_id,
        parent_provider_id=parent,
        document_handle=None,
        expires_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_cleanup_deletes_only_exact_recorded_ids_and_confirms_absence():
    container = resource("container", "cntr_owned")
    attachment = resource("attachment", "attachment_owned", parent="cntr_owned")
    file = resource("file", "file_owned")
    custody = Custody((container, attachment, file))
    calls = []

    class Containers:
        async def delete(self, identifier):
            calls.append(("container.delete", identifier))

        async def retrieve(self, identifier):
            calls.append(("container.retrieve", identifier))
            missing(identifier)

    class Files:
        async def delete(self, identifier):
            calls.append(("file.delete", identifier))
            return SimpleNamespace(id=identifier, deleted=True)

        async def retrieve(self, identifier):
            calls.append(("file.retrieve", identifier))
            missing(identifier)

    client = SimpleNamespace(containers=Containers(), files=Files())
    assert await _cleanup_recorded_openai_guide_resources(client, custody) is True
    assert custody.deleted == set(custody.resources)
    assert custody.failed == set()
    assert calls == [
        ("container.delete", "cntr_owned"),
        ("container.retrieve", "cntr_owned"),
        ("file.delete", "file_owned"),
        ("file.retrieve", "file_owned"),
    ]


@pytest.mark.asyncio
async def test_cleanup_keeps_unconfirmed_or_wrong_receipts_pending():
    container = resource("container", "cntr_owned")
    file = resource("file", "file_owned")
    custody = Custody((container, file))
    client = SimpleNamespace(
        containers=SimpleNamespace(
            delete=AsyncMock(),
            retrieve=AsyncMock(return_value=SimpleNamespace(id="cntr_owned")),
        ),
        files=SimpleNamespace(
            delete=AsyncMock(return_value=SimpleNamespace(id="file_foreign", deleted=True)),
            retrieve=AsyncMock(side_effect=lambda identifier: missing(identifier)),
        ),
    )
    assert await _cleanup_recorded_openai_guide_resources(client, custody) is False
    assert custody.deleted == set()
    assert custody.failed == {container.allocation_id, file.allocation_id}
    client.containers.delete.assert_awaited_once_with("cntr_owned")
    client.files.delete.assert_awaited_once_with("file_owned")


@pytest.mark.asyncio
async def test_cleanup_does_not_discover_or_touch_unrecorded_resources():
    custody = Custody(())
    client = SimpleNamespace(
        containers=SimpleNamespace(delete=AsyncMock(), retrieve=AsyncMock()),
        files=SimpleNamespace(delete=AsyncMock(), retrieve=AsyncMock()),
    )
    assert await _cleanup_recorded_openai_guide_resources(client, custody) is True
    client.containers.delete.assert_not_awaited()
    client.containers.retrieve.assert_not_awaited()
    client.files.delete.assert_not_awaited()
    client.files.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_retained_cleanup_requires_openai_key_and_never_uses_openrouter(
    monkeypatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-used")
    factory = create_guide_runtime_cleanup_factory()
    with pytest.raises(UnknownExternalServiceProviderError):
        factory.create("openrouter")
    adapter = factory.create(RETAINED_OPENAI_GUIDE_RUNTIME_KEY)
    assert adapter.identity.capability_key == GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY
    assert adapter.identity.provider_key == RETAINED_OPENAI_GUIDE_RUNTIME_KEY
    assert await adapter.cleanup(Custody(())) is False


@pytest.mark.asyncio
async def test_retained_cleanup_constructs_dedicated_openai_origin_client(monkeypatch):
    observed = []
    http_options = []
    custody = Custody(())
    owned_http_client = object()

    class Client:
        def __init__(self, **kwargs):
            observed.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setenv("OPENAI_API_KEY", "cleanup-only")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-used")
    monkeypatch.setattr(
        "openai.DefaultAsyncHttpx2Client",
        lambda **kwargs: http_options.append(kwargs) or owned_http_client,
    )
    monkeypatch.setattr("openai.AsyncOpenAI", Client)
    assert await OpenAIGuideRuntimeCleanupAdapter().cleanup(custody) is True
    assert observed == [
        {
            "api_key": "cleanup-only",
            "base_url": "https://api.openai.com/v1",
            "http_client": owned_http_client,
            "max_retries": 0,
            "timeout": 30,
        }
    ]
    assert http_options == [{"trust_env": False, "follow_redirects": False}]
