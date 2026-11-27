"""Canonical hashing helpers shared across Workstream domains."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_hash(value: dict[str, Any]) -> str:
    """Hash a JSON object with Workstream canonical JSON encoding.

    Args:
        value: JSON-compatible object to encode with sorted keys.

    Returns:
        SHA-256 digest prefixed with ``sha256:``.
    """
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_sha256(sha256: str) -> None:
    """Require one canonical lower-case SHA-256 commitment."""
    if (
        not isinstance(sha256, str)
        or len(sha256) != 71
        or not sha256.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in sha256[7:])
    ):
        raise ValueError("artifact commitment digest is invalid")
