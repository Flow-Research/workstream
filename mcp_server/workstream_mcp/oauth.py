"""MCP-owned credential boundary; product authorization remains in Workstream."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from workstream_external_services import ExternalServiceAdapter


class InvalidCredential(Exception):
    """The request cannot establish the required authenticated principal."""


class IdentityUnavailable(Exception):
    """The external identity provider cannot currently be consulted safely."""


@dataclass(frozen=True, slots=True)
class OAuthSettings:
    issuer: str
    resource: str
    secret_file: Path
    client_id: str = "workstream-mcp"
    api_audience: str = "workstream-api"

    def __post_init__(self) -> None:
        for value in (self.issuer, self.resource):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or value.endswith("/")
                or len(value) > 256
                or any(ord(char) < 33 for char in value)
            ):
                raise ValueError("OAuth URLs must be exact HTTPS URLs without credentials")
        if urlsplit(self.resource).path != "/mcp":
            raise ValueError("MCP resource must identify the deployed /mcp endpoint")
        if not self.secret_file.is_absolute():
            raise ValueError("OAuth secret file must be an absolute private path")
        for value in (self.client_id, self.api_audience):
            if not value or len(value) > 128 or any(char.isspace() for char in value):
                raise ValueError("OAuth client and audience must be bounded identifiers")


@dataclass(frozen=True, slots=True)
class McpIdentity:
    subject: str
    client_id: str
    expires_at: int
    scopes: frozenset[str]
    token: str = field(repr=False)


class McpCredentials(ExternalServiceAdapter, Protocol):
    async def verify(self, token: str) -> McpIdentity:
        """Verify an MCP-only source credential without issuing another token."""

    async def exchange(self, identity: McpIdentity) -> str:
        """Return a verified API bearer for this exact authenticated subject."""
