"""Bounded Keycloak JWT verification and Standard Token Exchange V2."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import jwt
from workstream_external_services import ExternalServiceAdapterIdentity

from workstream_mcp.oauth import (
    IdentityUnavailable,
    InvalidCredential,
    McpIdentity,
    OAuthSettings,
)

_ACCESS_TYPE = "urn:ietf:params:oauth:token-type:access_token"
_MAX_TOKEN_BYTES = 16_384
_MAX_RESPONSE_BYTES = 65_536


class KeycloakCredentials:
    """No user token cache, redirects, implicit retries, or caller-chosen targets."""

    identity = ExternalServiceAdapterIdentity("mcp_credentials", "keycloak")

    def __init__(self, settings: OAuthSettings, client: httpx.AsyncClient, secret: str) -> None:
        if not secret or len(secret) > 4096 or any(ord(char) < 33 for char in secret):
            raise ValueError("Invalid exchange credential")
        self._settings = settings
        self._client = client
        self._secret = secret
        self._keys: dict[str, Any] = {}
        self._keys_until = 0.0
        self._next_refresh = 0.0
        self._refresh_lock = asyncio.Lock()

    async def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with asyncio.timeout(8):
                async with self._client.stream(
                    method,
                    self._settings.issuer + path,
                    follow_redirects=False,
                    **kwargs,
                ) as response:
                    if response.status_code in (400, 401, 403):
                        raise InvalidCredential
                    if response.status_code != 200:
                        raise IdentityUnavailable
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > _MAX_RESPONSE_BYTES:
                            raise IdentityUnavailable
            value = json.loads(body)
            if not isinstance(value, dict):
                raise IdentityUnavailable
            return value
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise IdentityUnavailable from None

    async def _key(self, kid: str) -> Any:
        async with self._refresh_lock:
            now = time.monotonic()
            if now < self._keys_until and kid in self._keys:
                return self._keys[kid]
            if now < self._next_refresh:
                if now >= self._keys_until:
                    raise IdentityUnavailable
                raise InvalidCredential
            self._next_refresh = now + 5
            try:
                document = await self._json("GET", "/protocol/openid-connect/certs")
            except InvalidCredential:
                raise IdentityUnavailable from None
            items = document.get("keys")
            if not isinstance(items, list) or not 1 <= len(items) <= 16:
                raise IdentityUnavailable
            keys: dict[str, Any] = {}
            try:
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError
                    # A provider may publish encryption or other algorithm keys.
                    if item.get("use") != "sig" or item.get("alg") != "RS256":
                        continue
                    name = item.get("kid")
                    if not isinstance(name, str) or not 1 <= len(name) <= 128 or name in keys:
                        raise ValueError
                    if item.get("kty") != "RSA":
                        raise ValueError
                    key = jwt.PyJWK.from_dict(item).key
                    if not 2048 <= key.key_size <= 8192:
                        raise ValueError
                    keys[name] = key
            except (ValueError, TypeError, jwt.PyJWTError, AttributeError):
                raise IdentityUnavailable from None
            if not keys:
                raise IdentityUnavailable
            self._keys, self._keys_until = keys, now + 300
            if kid not in keys:
                raise InvalidCredential
            return keys[kid]

    async def _claims(self, token: str, audiences: set[str], lifetime: int) -> dict[str, Any]:
        if not isinstance(token, str) or len(token) > _MAX_TOKEN_BYTES or not token.isascii():
            raise InvalidCredential
        try:
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") != "RS256"
                or header.get("crit")
                or "jku" in header
                or "jwk" in header
            ):
                raise InvalidCredential
            kid = header.get("kid")
            if not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                raise InvalidCredential
            key = await self._key(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._settings.issuer,
                audience=list(audiences),
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "exp",
                        "iat",
                        "jti",
                        "azp",
                        "scope",
                        "subject_kind",
                    ],
                },
            )
            raw_aud = claims["aud"]
            actual_aud = {raw_aud} if isinstance(raw_aud, str) else set(raw_aud)
            if actual_aud != audiences or claims.get("typ") != "Bearer":
                raise InvalidCredential
            if claims["subject_kind"] != "human":
                raise InvalidCredential
            for name in ("sub", "jti", "azp"):
                if not isinstance(claims[name], str) or not 1 <= len(claims[name]) <= 256:
                    raise InvalidCredential
            if (
                type(claims["exp"]) is not int
                or type(claims["iat"]) is not int
                or not 0 < claims["exp"] - claims["iat"] <= lifetime
            ):
                raise InvalidCredential
            scope = claims["scope"]
            if not isinstance(scope, str) or len(scope) > 1024:
                raise InvalidCredential
            if "workstream:access" not in scope.split():
                raise InvalidCredential
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise InvalidCredential from None

    async def verify(self, token: str) -> McpIdentity:
        claims = await self._claims(
            token,
            {self._settings.resource, self._settings.client_id},
            300,
        )
        return McpIdentity(
            claims["sub"],
            claims["azp"],
            claims["exp"],
            frozenset(claims["scope"].split()),
            token,
        )

    async def exchange(self, identity: McpIdentity) -> str:
        # The caller passes a verified value; recheck expiry before provider I/O.
        if identity.expires_at <= int(time.time()):
            raise InvalidCredential
        result = await self._json(
            "POST",
            "/protocol/openid-connect/token",
            auth=httpx.BasicAuth(self._settings.client_id, self._secret),
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": identity.token,
                "subject_token_type": _ACCESS_TYPE,
                "requested_token_type": _ACCESS_TYPE,
                "audience": self._settings.api_audience,
                "scope": "workstream:access",
            },
        )
        if (
            not isinstance(result.get("token_type"), str)
            or result["token_type"].lower() != "bearer"
            or result.get("issued_token_type") != _ACCESS_TYPE
            or "refresh_token" in result
        ):
            raise IdentityUnavailable
        token = result.get("access_token")
        if not isinstance(token, str):
            raise IdentityUnavailable
        try:
            claims = await self._claims(token, {self._settings.api_audience}, 120)
            if (
                claims["sub"] != identity.subject
                or claims["azp"] != self._settings.client_id
                or claims["exp"] > identity.expires_at
                or not set(claims["scope"].split()) <= identity.scopes
            ):
                raise InvalidCredential
        except InvalidCredential:
            raise IdentityUnavailable from None
        return "Bearer " + token
