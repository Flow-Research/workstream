"""Composition root for the read-only forge facts capability (ADR 0014).

GitHub is the only forge provider today. The selected POST evaluation wiring
(WS-GHPROOF-001 chunk 04) resolves the provider named by a locked binding.
"""

from __future__ import annotations

import httpx

from app.adapters.github.app_facts import (
    GitHubAppFactsAdapter,
    GitHubAppFactsConfiguration,
    load_github_app_private_key,
)
from app.core.config import Settings
from app.interfaces.external_services import (
    ExternalServiceAdapterFactory,
    ExternalServiceAdapterIdentity,
    ExternalServiceConfigurationError,
)
from app.interfaces.forge_facts import (
    FORGE_FACTS_CAPABILITY_KEY,
    GITHUB_FORGE,
    ForgeFactsAdapter,
)


def _github_app_adapter(
    settings: Settings, transport: httpx.AsyncBaseTransport | None
) -> GitHubAppFactsAdapter:
    """Construct the provider from complete settings or fail as configuration."""
    app_id = settings.github_app_id
    private_key = settings.github_app_private_key
    if app_id is None or private_key is None:
        raise ExternalServiceConfigurationError(
            ExternalServiceAdapterIdentity(FORGE_FACTS_CAPABILITY_KEY, GITHUB_FORGE)
        )
    return GitHubAppFactsAdapter(
        GitHubAppFactsConfiguration(
            app_id=app_id,
            installation_id=settings.github_app_installation_id,
            api_base_url=settings.github_api_base_url,
            request_timeout_seconds=settings.github_api_request_timeout_seconds,
            total_deadline_seconds=settings.github_facts_total_deadline_seconds,
            maximum_attempts=settings.github_facts_maximum_attempts,
        ),
        load_github_app_private_key(private_key),
        transport=transport,
    )


def forge_facts_adapter_factory(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ExternalServiceAdapterFactory[ForgeFactsAdapter]:
    """Register one provider per forge; the provider key is the forge name."""
    factory = ExternalServiceAdapterFactory[ForgeFactsAdapter](FORGE_FACTS_CAPABILITY_KEY)
    factory.register(
        GITHUB_FORGE,
        lambda: _github_app_adapter(settings, transport),
    )
    return factory


__all__ = ("forge_facts_adapter_factory",)
