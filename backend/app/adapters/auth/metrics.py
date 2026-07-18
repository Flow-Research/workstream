"""Bounded verifier metrics emitted without identity or credential labels."""

from __future__ import annotations

import json
import logging
from collections import Counter
from threading import Lock
from typing import Literal, Protocol

VerificationResult = Literal["success", "invalid", "unsupported_kind", "unavailable"]
CacheResult = Literal["hit", "miss", "negative_hit", "expired"]
RefreshResult = Literal["success", "failure"]
IntrospectionResult = Literal["success", "inactive", "invalid", "unavailable", "skipped"]
IntrospectionMode = Literal["disabled", "required"]

logger = logging.getLogger(__name__)


class AuthVerifierMetrics(Protocol):
    """Metrics port used at the verifier boundary."""

    def verification(self, result: VerificationResult) -> None: ...

    def jwks_cache(self, result: CacheResult) -> None: ...

    def jwks_refresh(self, result: RefreshResult) -> None: ...

    def introspection(self, mode: IntrospectionMode, result: IntrospectionResult) -> None: ...


class InProcessAuthVerifierMetrics:
    """Process-lifetime bounded counters with structured metric emission."""

    _ALLOWED_LABELS = {
        "workstream_auth_verification_total": {
            "result": frozenset({"success", "invalid", "unsupported_kind", "unavailable"})
        },
        "workstream_auth_jwks_cache_total": {
            "result": frozenset({"hit", "miss", "negative_hit", "expired"})
        },
        "workstream_auth_jwks_refresh_total": {"result": frozenset({"success", "failure"})},
        "workstream_auth_introspection_total": {
            "mode": frozenset({"disabled", "required"}),
            "result": frozenset({"success", "inactive", "invalid", "unavailable", "skipped"}),
        },
    }

    def __init__(self) -> None:
        self._counts: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._lock = Lock()

    def _increment(self, name: str, **labels: str) -> None:
        allowed = self._ALLOWED_LABELS.get(name)
        if allowed is None or set(labels) != set(allowed):
            raise ValueError("auth verifier metric name or labels are not allowed")
        if any(value not in allowed[label] for label, value in labels.items()):
            raise ValueError("auth verifier metric label value is not allowed")
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counts[key] += 1
        logger.info(
            "auth_verifier_metric %s",
            json.dumps({"metric": name, "labels": labels}, sort_keys=True),
        )

    def verification(self, result: VerificationResult) -> None:
        self._increment("workstream_auth_verification_total", result=result)

    def jwks_cache(self, result: CacheResult) -> None:
        self._increment("workstream_auth_jwks_cache_total", result=result)

    def jwks_refresh(self, result: RefreshResult) -> None:
        self._increment("workstream_auth_jwks_refresh_total", result=result)

    def introspection(self, mode: IntrospectionMode, result: IntrospectionResult) -> None:
        self._increment("workstream_auth_introspection_total", mode=mode, result=result)

    def snapshot(self) -> dict[tuple[str, tuple[tuple[str, str], ...]], int]:
        """Return a copy for deterministic tests and operational adapters."""
        with self._lock:
            return dict(self._counts)
