"""Strict signed keyset cursors for privacy-sensitive authorization reads."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
import hashlib
import hmac
import json
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.schemas import ProjectRole

_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_DECODED_BYTES = 384
_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
_ORDER = "timestamp_uuid_asc"


class InvalidPaginationCursor(ValueError):
    """One generic failure for malformed, forged, or replayed cursors."""


class _CursorPayload(BaseModel):
    model_config = _STRICT

    v: Literal[1]
    q: str
    ts: str
    id: str

    @field_validator("q")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
            raise ValueError("invalid cursor")
        return value


class _CursorEnvelope(BaseModel):
    model_config = _STRICT

    p: _CursorPayload
    s: str

    @field_validator("s")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        if len(value) != 43 or _BASE64URL.fullmatch(value) is None:
            raise ValueError("invalid cursor")
        return value


def authorization_read_query_digest(
    *,
    action_id: ActionId,
    project_id: UUID,
    limit: int,
    status: Literal["active", "revoked"] | None = None,
    role: ProjectRole | None = None,
) -> str:
    """Bind a cursor to one normalized read query and ordering contract."""
    return canonical_json_hash(
        {
            "action_id": action_id.value,
            "limit": limit,
            "order": _ORDER,
            "project_id": str(project_id),
            "role": role.value if role is not None else None,
            "status": status,
        }
    )


class AuthorizationReadCursorCodec:
    """Encode and verify one canonical HMAC-bound keyset boundary."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) != 32:
            raise ValueError("invalid pagination cursor HMAC secret")
        self._secret = bytes(secret)

    def encode(self, *, query_digest: str, timestamp: datetime, resource_id: UUID) -> str:
        """Return one canonical unpadded Base64url cursor."""
        payload = _CursorPayload(
            v=1,
            q=query_digest,
            ts=_canonical_timestamp(timestamp),
            id=str(resource_id),
        )
        payload_bytes = _canonical_json(payload.model_dump(mode="json"))
        signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        envelope = {"p": payload.model_dump(mode="json"), "s": _encode_base64url(signature)}
        return _encode_base64url(_canonical_json(envelope))

    def decode(self, value: str, *, query_digest: str) -> tuple[datetime, UUID]:
        """Verify a cursor and return its strict timestamp/UUID boundary."""
        try:
            decoded = _decode_base64url(value)
            if len(decoded) > _MAX_DECODED_BYTES:
                raise InvalidPaginationCursor("invalid cursor")
            raw = json.loads(decoded, object_pairs_hook=_reject_duplicate_keys)
            envelope = _CursorEnvelope.model_validate(raw)
            payload_bytes = _canonical_json(envelope.p.model_dump(mode="json"))
            signature = _decode_base64url(envelope.s)
            expected = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
            if not hmac.compare_digest(expected, signature):
                raise InvalidPaginationCursor("invalid cursor")
            if not hmac.compare_digest(envelope.p.q, query_digest):
                raise InvalidPaginationCursor("invalid cursor")
            timestamp = _parse_canonical_timestamp(envelope.p.ts)
            resource_id = UUID(envelope.p.id)
            if str(resource_id) != envelope.p.id:
                raise InvalidPaginationCursor("invalid cursor")
            return timestamp, resource_id
        except InvalidPaginationCursor:
            raise
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
            raise InvalidPaginationCursor("invalid cursor") from None


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str) -> bytes:
    if not value or len(value) > 512 or _BASE64URL.fullmatch(value) is None:
        raise InvalidPaginationCursor("invalid cursor")
    padding = "=" * (-len(value) % 4)
    decoded = base64.b64decode(
        (value + padding).encode("ascii"),
        altchars=b"-_",
        validate=True,
    )
    if _encode_base64url(decoded) != value:
        raise InvalidPaginationCursor("invalid cursor")
    return decoded


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise InvalidPaginationCursor("invalid cursor")
        value[key] = item
    return value


def _canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cursor timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_canonical_timestamp(value: str) -> datetime:
    if not value.endswith("Z"):
        raise InvalidPaginationCursor("invalid cursor")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if _canonical_timestamp(parsed) != value:
        raise InvalidPaginationCursor("invalid cursor")
    return parsed
