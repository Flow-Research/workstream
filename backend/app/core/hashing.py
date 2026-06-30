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
