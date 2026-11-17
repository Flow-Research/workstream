"""Explicit credential-provider construction and private secret ownership."""

from __future__ import annotations

import os
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from workstream_external_services import ExternalServiceAdapterFactory

from workstream_mcp.adapters.keycloak import KeycloakCredentials
from workstream_mcp.oauth import McpCredentials, OAuthSettings


def _exchange_secret(settings: OAuthSettings) -> str:
    descriptor = os.open(settings.secret_file, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 4096
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IRWXO)
        ):
            raise ValueError("Exchange credential must be a bounded private regular file")
        secret = os.read(descriptor, 4097).decode("ascii").removesuffix("\n")
        if not secret or len(secret) > 4096 or any(ord(char) < 33 for char in secret):
            raise ValueError("Invalid exchange credential")
        return secret
    finally:
        os.close(descriptor)


@asynccontextmanager
async def create_credentials(settings: OAuthSettings) -> AsyncIterator[McpCredentials]:
    secret = _exchange_secret(settings)
    async with httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(5, connect=3),
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    ) as client:
        factory = ExternalServiceAdapterFactory[McpCredentials]("mcp_credentials")
        factory.register("keycloak", lambda: KeycloakCredentials(settings, client, secret))
        yield factory.create("keycloak")
