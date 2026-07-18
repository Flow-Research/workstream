"""Fail-closed verification for externally issued Flow access tokens."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt

from app.adapters.auth.metrics import AuthVerifierMetrics, InProcessAuthVerifierMetrics
from app.core.config import Settings
from app.interfaces.auth import (
    AuthHttpClientFactory,
    AuthVerificationError,
    AuthVerificationUnavailableError,
)
from app.schemas.auth import (
    AuthVerificationResult,
    LegacyAuthorizationCompatibilityContext,
    MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS,
    VerifiedIssuerToken,
    actor_id_from_external_identity,
    normalize_legacy_roles,
)

LOCAL_FLOW_AUTH_ENVIRONMENTS = {"local", "dev", "development", "test"}
SUPPORTED_ALGORITHMS = {
    "RS256": "RSA",
    "RS384": "RSA",
    "RS512": "RSA",
    "ES256": "EC",
    "ES384": "EC",
    "ES512": "EC",
    "EdDSA": "OKP",
}
SUBJECT_KINDS = {"human", "service", "agent", "space"}


def actor_id_from_flow_identity(external_issuer: str, external_subject: str) -> str:
    """Build the historical stable Workstream actor identifier."""
    return actor_id_from_external_identity(external_issuer, external_subject)


def _decode_base64url(value: str) -> bytes:
    """Decode one unpadded base64url token segment."""
    decoded: bytes | None = None
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(f"{value}{padding}", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        pass
    if decoded is None:
        raise AuthVerificationError("malformed token segment")
    return decoded


def _decode_json_segment(value: str, *, maximum_bytes: int) -> dict[str, Any]:
    """Decode a bounded JSON object from one base64url token segment."""
    decoded = _decode_base64url(value)
    if len(decoded) > maximum_bytes:
        raise AuthVerificationError("token segment exceeds configured limit")
    payload: Any = None
    try:
        payload = json.loads(decoded)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    if payload is None:
        raise AuthVerificationError("malformed token JSON")
    if not isinstance(payload, dict):
        raise AuthVerificationError("malformed token JSON")
    return payload


def _normalize_audience(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        audiences = (value,)
    elif (
        isinstance(value, list) and value and all(isinstance(item, str) and item for item in value)
    ):
        audiences = tuple(value)
    else:
        raise AuthVerificationError("token audience is invalid")
    if len(audiences) > 16 or any(len(audience) > 256 for audience in audiences):
        raise AuthVerificationError("token audience is invalid")
    return audiences


def _normalize_scopes(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        raw_scopes = value.split()
    elif isinstance(value, list) and all(
        isinstance(item, str) and item and not any(character.isspace() for character in item)
        for item in value
    ):
        raw_scopes = value
    else:
        raise AuthVerificationError("token scope is invalid")
    scopes = frozenset(scope.strip() for scope in raw_scopes if scope.strip())
    if not scopes or len(scopes) > 64 or any(len(scope) > 128 for scope in scopes):
        raise AuthVerificationError("token scope is invalid")
    return scopes


def _canonical_https_url(value: str | None, *, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} must be configured")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(f"{name} must be a canonical HTTPS URL")
    return value


def _http_timeout(connect: float, read: float, write: float, pool: float) -> httpx.Timeout:
    return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)


class FlowAuthVerifier:
    """Verify final issuer tokens with pinned policy and bounded network access."""

    def __init__(
        self,
        settings: Settings,
        *,
        jwks_transport: httpx.AsyncBaseTransport | None = None,
        introspection_transport: httpx.AsyncBaseTransport | None = None,
        jwks_client_factory: AuthHttpClientFactory | None = None,
        introspection_client_factory: AuthHttpClientFactory | None = None,
        metrics: AuthVerifierMetrics | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._environment = settings.environment.strip().lower()
        self._local_hmac_secret = settings.flow_auth_local_hmac_secret
        if self._local_hmac_secret and self._environment not in LOCAL_FLOW_AUTH_ENVIRONMENTS:
            raise RuntimeError("local Flow auth verifier cannot run outside local/test")

        self._metrics = metrics or InProcessAuthVerifierMetrics()
        self._monotonic = monotonic
        if jwks_transport is not None and jwks_client_factory is not None:
            raise ValueError("JWKS transport and client factory are mutually exclusive")
        if introspection_transport is not None and introspection_client_factory is not None:
            raise ValueError("introspection transport and client factory are mutually exclusive")
        self._jwks_client_factory = jwks_client_factory or partial(
            httpx.AsyncClient,
            transport=jwks_transport,
        )
        self._introspection_client_factory = introspection_client_factory or partial(
            httpx.AsyncClient,
            transport=introspection_transport,
        )
        self._refresh_lock = asyncio.Lock()
        self._keys: dict[str, dict[str, Any]] = {}
        self._cache_expires_at = 0.0
        self._unknown_kid_refresh_at = 0.0
        self._refresh_retry_at = 0.0
        self._refresh_generation = 0
        self._negative_kids: OrderedDict[str, float] = OrderedDict()

        if self._local_hmac_secret:
            self._issuer = settings.flow_auth_issuer
            if (
                not self._issuer
                or len(self._issuer.encode("utf-8"))
                > MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS
            ):
                raise RuntimeError("WORKSTREAM_FLOW_AUTH_ISSUER is invalid")
            self._audience = settings.flow_auth_audience
            self._algorithms = ("HS256",)
            self._jwks_url = None
            self._introspection_mode = "disabled"
            self._introspection_url = None
            return

        self._issuer = _canonical_https_url(settings.token_issuer, name="WORKSTREAM_TOKEN_ISSUER")
        if len(self._issuer.encode("utf-8")) > MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS:
            raise RuntimeError("WORKSTREAM_TOKEN_ISSUER is invalid")
        if urlsplit(self._issuer).hostname == "auth.flow.local":
            raise RuntimeError("WORKSTREAM_TOKEN_ISSUER cannot use the placeholder issuer")
        self._jwks_url = _canonical_https_url(
            settings.token_jwks_url,
            name="WORKSTREAM_TOKEN_JWKS_URL",
        )
        self._audience = settings.token_audience.strip()
        if not self._audience or any(character.isspace() for character in self._audience):
            raise RuntimeError("WORKSTREAM_TOKEN_AUDIENCE must be configured")
        self._algorithms = self._parse_algorithms(settings.token_algorithms)
        self._validate_size_bounds()
        self._validate_scope_setting(
            settings.required_human_scope,
            name="WORKSTREAM_REQUIRED_HUMAN_SCOPE",
        )
        self._validate_scope_setting(
            settings.required_service_scope,
            name="WORKSTREAM_REQUIRED_SERVICE_SCOPE",
        )

        mode = settings.token_introspection_mode
        if mode is None:
            raise RuntimeError("WORKSTREAM_TOKEN_INTROSPECTION_MODE must be configured")
        self._introspection_mode = mode
        if mode == "disabled":
            if (
                not settings.token_introspection_disabled_reason
                or not settings.token_introspection_disabled_reason.strip()
            ):
                raise RuntimeError(
                    "WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON must document issuer policy"
                )
            self._introspection_url = None
        else:
            self._introspection_url = _canonical_https_url(
                settings.token_introspection_url,
                name="WORKSTREAM_TOKEN_INTROSPECTION_URL",
            )
            if self._introspection_url == self._jwks_url:
                raise RuntimeError("introspection and JWKS endpoints must be distinct")
            if (
                not settings.token_introspection_client_id
                or not settings.token_introspection_client_id.strip()
            ):
                raise RuntimeError("WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_ID must be configured")
            if (
                not settings.token_introspection_client_secret
                or not settings.token_introspection_client_secret.strip()
            ):
                raise RuntimeError(
                    "WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_SECRET must be configured"
                )

    def canonical_issuer(self) -> str:
        """Return the exact configured issuer used by successful token results."""
        return self._issuer

    @staticmethod
    def _parse_algorithms(raw: str) -> tuple[str, ...]:
        algorithms = tuple(item.strip() for item in raw.split(",") if item.strip())
        if not algorithms or len(set(algorithms)) != len(algorithms):
            raise RuntimeError("WORKSTREAM_TOKEN_ALGORITHMS must be a unique pinned list")
        if any(algorithm not in SUPPORTED_ALGORITHMS for algorithm in algorithms):
            raise RuntimeError("WORKSTREAM_TOKEN_ALGORITHMS contains an unsupported algorithm")
        families = {SUPPORTED_ALGORITHMS[algorithm] for algorithm in algorithms}
        if len(families) != 1:
            raise RuntimeError("WORKSTREAM_TOKEN_ALGORITHMS cannot mix key families")
        return algorithms

    def _validate_size_bounds(self) -> None:
        if self._settings.token_header_max_bytes > self._settings.token_max_bytes:
            raise RuntimeError("token header limit cannot exceed token limit")
        if self._settings.token_payload_max_bytes > self._settings.token_max_bytes:
            raise RuntimeError("token payload limit cannot exceed token limit")

    @staticmethod
    def _validate_scope_setting(value: str, *, name: str) -> None:
        if not value or value != value.strip() or any(character.isspace() for character in value):
            raise RuntimeError(f"{name} must contain one non-empty scope token")

    async def verify(self, token: str) -> AuthVerificationResult:
        """Verify one bearer token without granting Workstream product authority."""
        try:
            if self._local_hmac_secret:
                result = self._verify_local_hmac_token(token)
                self._metrics.introspection("disabled", "skipped")
            else:
                result = await self._verify_asymmetric_token(token)
            metric_result = (
                "unsupported_kind" if result.token.subject_kind in {"agent", "space"} else "success"
            )
            self._metrics.verification(metric_result)
            return result
        except AuthVerificationUnavailableError:
            self._metrics.verification("unavailable")
            raise
        except AuthVerificationError:
            self._metrics.verification("invalid")
            raise

    def _parse_token_segments(self, token: str) -> tuple[str, str, str, dict[str, Any]]:
        if not token or len(token.encode()) > self._settings.token_max_bytes:
            raise AuthVerificationError("token exceeds configured limit")
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthVerificationError("malformed token")
        header_segment, payload_segment, signature_segment = parts
        header = _decode_json_segment(
            header_segment,
            maximum_bytes=self._settings.token_header_max_bytes,
        )
        _decode_json_segment(
            payload_segment,
            maximum_bytes=self._settings.token_payload_max_bytes,
        )
        if "jku" in header or "x5u" in header:
            raise AuthVerificationError("remote token key headers are forbidden")
        if header.get("crit") is not None:
            raise AuthVerificationError("critical token headers are unsupported")
        return header_segment, payload_segment, signature_segment, header

    async def _verify_asymmetric_token(self, token: str) -> AuthVerificationResult:
        _, _, _, header = self._parse_token_segments(token)
        algorithm = header.get("alg")
        kid = header.get("kid")
        if algorithm not in self._algorithms:
            raise AuthVerificationError("token algorithm is not allowed")
        if not isinstance(kid, str) or not kid or len(kid) > 256:
            raise AuthVerificationError("token key identifier is invalid")

        try:
            async with asyncio.timeout(self._settings.token_jwks_total_timeout_seconds):
                jwk_data = await self._resolve_key(kid)
        except TimeoutError:
            raise AuthVerificationUnavailableError("issuer key resolution timed out") from None
        if jwk_data.get("alg") != algorithm:
            raise AuthVerificationError("token algorithm does not match issuer key")
        claims: dict[str, Any] | None = None
        try:
            signing_key = jwt.PyJWK.from_dict(jwk_data, algorithm=algorithm).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._settings.token_clock_skew_seconds,
                options={
                    "require": ["iss", "sub", "aud", "exp", "iat", "jti", "subject_kind", "scope"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            pass
        if not isinstance(claims, dict):
            raise AuthVerificationError("token signature or claims are invalid")

        result = self._result_from_verified_claims(claims, auth_source="flow")
        await self._apply_introspection(token, result.token)
        return result

    def _verify_local_hmac_token(self, token: str) -> AuthVerificationResult:
        header_segment, payload_segment, signature_segment, header = self._parse_token_segments(
            token
        )
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise AuthVerificationError("unsupported local token header")
        expected_signature = hmac.new(
            self._local_hmac_secret.encode(),
            f"{header_segment}.{payload_segment}".encode(),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_signature, _decode_base64url(signature_segment)):
            raise AuthVerificationError("invalid local token signature")
        claims = _decode_json_segment(
            payload_segment,
            maximum_bytes=self._settings.token_payload_max_bytes,
        )
        self._validate_local_claims(claims)
        return self._result_from_verified_claims(claims, auth_source="flow")

    def _validate_local_claims(self, claims: dict[str, Any]) -> None:
        if claims.get("iss") != self._issuer:
            raise AuthVerificationError("token issuer is invalid")
        if self._audience not in _normalize_audience(claims.get("aud")):
            raise AuthVerificationError("token audience is invalid")
        now = datetime.now(UTC).timestamp()
        skew = self._settings.token_clock_skew_seconds
        exp = claims.get("exp")
        iat = claims.get("iat")
        nbf = claims.get("nbf")
        if isinstance(exp, bool) or not isinstance(exp, int | float) or exp <= now - skew:
            raise AuthVerificationError("token is expired")
        if isinstance(iat, bool) or not isinstance(iat, int | float) or iat > now + skew:
            raise AuthVerificationError("token issued-at claim is invalid")
        if nbf is not None and (
            isinstance(nbf, bool) or not isinstance(nbf, int | float) or nbf > now + skew
        ):
            raise AuthVerificationError("token is not active")

    def _result_from_verified_claims(
        self,
        claims: dict[str, Any],
        *,
        auth_source: str,
    ) -> AuthVerificationResult:
        subject = claims.get("sub")
        token_id = claims.get("jti")
        subject_kind = claims.get("subject_kind")
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or subject != subject.strip()
            or len(subject) > MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS
        ):
            raise AuthVerificationError("token subject is required")
        if not isinstance(token_id, str) or not token_id or len(token_id) > 512:
            raise AuthVerificationError("token identifier is required")
        if subject_kind not in SUBJECT_KINDS:
            raise AuthVerificationError("token subject kind is invalid")
        scopes = _normalize_scopes(claims.get("scope"))
        if subject_kind == "human" and self._settings.required_human_scope not in scopes:
            raise AuthVerificationError("required human scope is missing")
        if subject_kind == "service" and self._settings.required_service_scope not in scopes:
            raise AuthVerificationError("required service scope is missing")

        exp = claims.get("exp")
        iat = claims.get("iat")
        nbf = claims.get("nbf")
        if any(
            isinstance(value, bool) or not isinstance(value, int | float) for value in (exp, iat)
        ):
            raise AuthVerificationError("token temporal claims are invalid")
        if nbf is not None and (isinstance(nbf, bool) or not isinstance(nbf, int | float)):
            raise AuthVerificationError("token not-before claim is invalid")

        verified = VerifiedIssuerToken(
            issuer=self._issuer,
            subject=subject,
            audience=_normalize_audience(claims.get("aud")),
            expires_at=int(exp),
            issued_at=int(iat),
            not_before=int(nbf) if nbf is not None else None,
            token_id=token_id,
            subject_kind=subject_kind,
            scopes=scopes,
        )
        legacy = None
        if subject_kind == "human":
            legacy = LegacyAuthorizationCompatibilityContext(
                roles=normalize_legacy_roles(claims.get("roles")),
                auth_source=auth_source,
                is_dev_auth=False,
            )
        return AuthVerificationResult(token=verified, legacy=legacy)

    async def _resolve_key(self, kid: str) -> dict[str, Any]:
        now = self._monotonic()
        self._prune_negative_kids(now)
        if now < self._cache_expires_at and kid in self._keys:
            self._metrics.jwks_cache("hit")
            return self._keys[kid]
        if now < self._refresh_retry_at:
            raise AuthVerificationUnavailableError("issuer key refresh is cooling down")
        if self._negative_kids.get(kid, 0.0) > now:
            self._metrics.jwks_cache("negative_hit")
            raise AuthVerificationError("token key identifier is unknown")
        if now < self._unknown_kid_refresh_at and not (
            self._keys and now >= self._cache_expires_at
        ):
            if self._keys and now < self._cache_expires_at:
                self._remember_unknown_kid(kid)
                raise AuthVerificationError("token key identifier is unknown")
            raise AuthVerificationUnavailableError("issuer key refresh is cooling down")
        self._metrics.jwks_cache("expired" if self._keys else "miss")
        observed_generation = self._refresh_generation

        async with self._refresh_lock:
            now = self._monotonic()
            self._prune_negative_kids(now)
            if now < self._cache_expires_at and kid in self._keys:
                self._metrics.jwks_cache("hit")
                return self._keys[kid]
            if now < self._refresh_retry_at:
                raise AuthVerificationUnavailableError("issuer key refresh is cooling down")
            if self._negative_kids.get(kid, 0.0) > now:
                self._metrics.jwks_cache("negative_hit")
                raise AuthVerificationError("token key identifier is unknown")
            if self._refresh_generation != observed_generation:
                self._remember_unknown_kid(kid)
                raise AuthVerificationError("token key identifier is unknown")
            if now < self._unknown_kid_refresh_at and not (
                self._keys and now >= self._cache_expires_at
            ):
                if self._keys and now < self._cache_expires_at:
                    self._remember_unknown_kid(kid)
                    raise AuthVerificationError("token key identifier is unknown")
                raise AuthVerificationUnavailableError("issuer key refresh is cooling down")
            try:
                await self._refresh_jwks()
            except AuthVerificationUnavailableError:
                self._refresh_retry_at = (
                    self._monotonic() + self._settings.token_unknown_kid_cache_ttl_seconds
                )
                self._metrics.jwks_refresh("failure")
                raise
            self._metrics.jwks_refresh("success")
            if kid in self._keys:
                return self._keys[kid]
            self._remember_unknown_kid(kid)
            raise AuthVerificationError("token key identifier is unknown")

    async def _refresh_jwks(self) -> None:
        payload = await self._request_json(
            method="GET",
            url=self._jwks_url,
            maximum_bytes=self._settings.token_jwks_max_response_bytes,
            timeout=_http_timeout(
                self._settings.token_jwks_connect_timeout_seconds,
                self._settings.token_jwks_read_timeout_seconds,
                self._settings.token_jwks_write_timeout_seconds,
                self._settings.token_jwks_pool_timeout_seconds,
            ),
            total_timeout=self._settings.token_jwks_total_timeout_seconds,
            client_factory=self._jwks_client_factory,
        )
        raw_keys = payload.get("keys")
        if not isinstance(raw_keys, list) or not raw_keys:
            raise AuthVerificationUnavailableError("issuer key set is invalid")
        if len(raw_keys) > self._settings.token_jwks_max_keys:
            raise AuthVerificationUnavailableError("issuer key set exceeds configured limit")

        keys: dict[str, dict[str, Any]] = {}
        seen_kids: set[str] = set()
        for raw_key in raw_keys:
            if not isinstance(raw_key, dict):
                raise AuthVerificationUnavailableError("issuer key set is invalid")
            kid = raw_key.get("kid")
            if not isinstance(kid, str) or not kid or len(kid) > 256 or kid in seen_kids:
                raise AuthVerificationUnavailableError("issuer key identifier is invalid")
            seen_kids.add(kid)
            algorithm = raw_key.get("alg")
            if algorithm not in self._algorithms:
                continue
            if raw_key.get("kty") != SUPPORTED_ALGORITHMS[algorithm]:
                continue
            if raw_key.get("use") not in (None, "sig"):
                continue
            key_ops = raw_key.get("key_ops")
            if key_ops is not None and (not isinstance(key_ops, list) or "verify" not in key_ops):
                continue
            key_is_valid = True
            try:
                jwt.PyJWK.from_dict(raw_key, algorithm=algorithm)
                self._validate_jwk_strength(raw_key, algorithm=algorithm)
            except (AuthVerificationError, jwt.PyJWTError, ValueError, TypeError):
                key_is_valid = False
            if not key_is_valid:
                raise AuthVerificationUnavailableError("issuer key set is invalid")
            keys[kid] = raw_key
        if not keys:
            raise AuthVerificationUnavailableError("issuer key set has no eligible signing keys")
        self._keys = keys
        now = self._monotonic()
        self._cache_expires_at = now + self._settings.token_jwks_cache_ttl_seconds
        self._unknown_kid_refresh_at = now + self._settings.token_unknown_kid_cache_ttl_seconds
        self._refresh_retry_at = 0.0
        self._refresh_generation += 1
        for kid in keys:
            self._negative_kids.pop(kid, None)

    @staticmethod
    def _validate_jwk_strength(raw_key: dict[str, Any], *, algorithm: str) -> None:
        if algorithm.startswith("RS"):
            modulus = raw_key.get("n")
            if not isinstance(modulus, str):
                raise ValueError("RSA modulus is missing")
            modulus_bits = int.from_bytes(_decode_base64url(modulus), "big").bit_length()
            if modulus_bits < 2_048:
                raise ValueError("RSA modulus is below 2048 bits")
            return
        expected_curves = {
            "ES256": "P-256",
            "ES384": "P-384",
            "ES512": "P-521",
        }
        if algorithm in expected_curves and raw_key.get("crv") != expected_curves[algorithm]:
            raise ValueError("EC curve does not match algorithm")
        if algorithm == "EdDSA" and raw_key.get("crv") not in {"Ed25519", "Ed448"}:
            raise ValueError("EdDSA curve is unsupported")

    async def _apply_introspection(self, bearer: str, token: VerifiedIssuerToken) -> None:
        if self._introspection_mode == "disabled":
            self._metrics.introspection("disabled", "skipped")
            return
        try:
            payload = await self._request_json(
                method="POST",
                url=self._introspection_url,
                maximum_bytes=self._settings.token_introspection_max_response_bytes,
                timeout=_http_timeout(
                    self._settings.token_introspection_connect_timeout_seconds,
                    self._settings.token_introspection_read_timeout_seconds,
                    self._settings.token_introspection_write_timeout_seconds,
                    self._settings.token_introspection_pool_timeout_seconds,
                ),
                total_timeout=self._settings.token_introspection_total_timeout_seconds,
                client_factory=self._introspection_client_factory,
                auth=(
                    self._settings.token_introspection_client_id,
                    self._settings.token_introspection_client_secret,
                ),
                data={"token": bearer, "token_type_hint": "access_token"},
            )
        except AuthVerificationUnavailableError:
            self._metrics.introspection("required", "unavailable")
            raise

        if payload.get("active") is not True:
            self._metrics.introspection("required", "inactive")
            raise AuthVerificationError("token is inactive")
        try:
            audience = _normalize_audience(payload.get("aud"))
        except AuthVerificationError:
            self._metrics.introspection("required", "invalid")
            raise
        if (
            payload.get("iss") != token.issuer
            or payload.get("sub") != token.subject
            or frozenset(token.audience) != frozenset(audience)
            or payload.get("jti") != token.token_id
        ):
            self._metrics.introspection("required", "invalid")
            raise AuthVerificationError("introspection response does not match token")
        self._metrics.introspection("required", "success")

    async def _request_json(
        self,
        *,
        method: str,
        url: str,
        maximum_bytes: int,
        timeout: httpx.Timeout,
        total_timeout: float,
        client_factory: AuthHttpClientFactory,
        auth: tuple[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=0)
        request_failed = False
        try:
            async with asyncio.timeout(total_timeout):
                async with client_factory(
                    timeout=timeout,
                    limits=limits,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(method, url, auth=auth, data=data) as response:
                        if response.is_redirect or response.status_code != 200:
                            raise AuthVerificationUnavailableError(
                                "identity verification endpoint is unavailable"
                            )
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > maximum_bytes:
                                raise AuthVerificationUnavailableError(
                                    "identity verification response exceeds configured limit"
                                )
        except AuthVerificationUnavailableError:
            raise
        except (TimeoutError, httpx.HTTPError):
            request_failed = True
        if request_failed:
            raise AuthVerificationUnavailableError("identity verification endpoint is unavailable")
        payload: Any = None
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        if payload is None:
            raise AuthVerificationUnavailableError("identity verification response is invalid")
        if not isinstance(payload, dict):
            raise AuthVerificationUnavailableError("identity verification response is invalid")
        return payload

    def _prune_negative_kids(self, now: float) -> None:
        expired = [kid for kid, expires_at in self._negative_kids.items() if expires_at <= now]
        for kid in expired:
            self._negative_kids.pop(kid, None)

    def _remember_unknown_kid(self, kid: str) -> None:
        self._negative_kids[kid] = (
            self._monotonic() + self._settings.token_unknown_kid_cache_ttl_seconds
        )
        self._negative_kids.move_to_end(kid)
        while len(self._negative_kids) > self._settings.token_unknown_kid_cache_max_entries:
            self._negative_kids.popitem(last=False)
