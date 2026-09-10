"""Status-aware SDK retries and process-local model outage admission."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

from app.interfaces.project_agents import ProjectAgentRuntimeError
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration


class ProviderCircuitOpen(ProjectAgentRuntimeError):
    """Bounded outage signal with no provider payload or credentials."""

    def __init__(self) -> None:
        super().__init__("project guide provider circuit is open")


@dataclass(frozen=True)
class CircuitLease:
    epoch: int
    token: int
    expires_at: float


class ProviderCircuit:
    """Thread-safe worker-process circuit; no distributed health claim."""

    def __init__(self, threshold: int, cooldown: int, *, clock=time.monotonic):
        self._threshold = threshold
        self._cooldown = cooldown
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._epoch = 0
        self._token = 0
        self._opened_until: float | None = None
        self._probe: CircuitLease | None = None

    def acquire(self, lifetime: float) -> CircuitLease:
        """Admit before the product fence, allowing one bounded recovery probe."""
        with self._lock:
            now = self._clock()
            if self._opened_until is not None:
                if now < self._opened_until:
                    raise ProviderCircuitOpen()
                if self._probe is not None and now < self._probe.expires_at:
                    raise ProviderCircuitOpen()
                # Expired probes cannot subsequently close the next probe's epoch.
                self._epoch += 1
            self._token += 1
            lease = CircuitLease(self._epoch, self._token, now + lifetime)
            if self._opened_until is not None:
                self._probe = lease
            return lease

    def require_current(self, lease: CircuitLease) -> None:
        """Prevent an old admitted run from bypassing a subsequently opened circuit."""
        with self._lock:
            if (lease.epoch != self._epoch or self._clock() >= lease.expires_at
                    or (self._opened_until is not None and self._probe != lease)):
                raise ProviderCircuitOpen()

    def succeeded(self, lease: CircuitLease) -> None:
        """Only current work may establish recovery; late successes cannot close outages."""
        with self._lock:
            if lease.epoch != self._epoch or self._clock() >= lease.expires_at:
                return
            if self._opened_until is not None and self._probe != lease:
                return
            self._failures = 0
            self._opened_until = None
            self._probe = None

    def failed(self, lease: CircuitLease) -> None:
        """Count an exhausted logical model request once, never every retry."""
        with self._lock:
            if lease.epoch != self._epoch or self._clock() >= lease.expires_at:
                return
            self._failures += 1
            if self._probe == lease or self._failures >= self._threshold:
                self._epoch += 1
                self._opened_until = self._clock() + self._cooldown
                self._probe = None

    def release(self, lease: CircuitLease) -> None:
        """Release a losing/cancelled dispatch without claiming provider recovery."""
        with self._lock:
            if self._probe == lease:
                self._probe = None
                self._epoch += 1


@lru_cache(maxsize=32)
def _provider_circuit(runtime: str, provider: str, api: str, model: str,
                      threshold: int, cooldown: int) -> ProviderCircuit:
    # Endpoint and account are fixed by composition, not project/model input.
    return ProviderCircuit(threshold, cooldown)


def circuit_for(configuration: ProjectGuideRuntimeConfiguration) -> ProviderCircuit:
    """Share health across runtime instances in this worker process."""
    return _provider_circuit(
        configuration.runtime_key, configuration.model_provider, configuration.model_api,
        configuration.model, configuration.circuit_failure_threshold,
        configuration.circuit_cooldown_seconds,
    )


def _pretransmission_failure(error: Exception) -> bool:
    """Match the pinned OpenAI transport, not arbitrary connection-error messages."""
    import httpx2

    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(seen) < 8 and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout)):
            return True
        current = current.__cause__
    return False


def _retry_header(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    value = headers.get("x-should-retry") if headers is not None else None
    return value.strip().lower() if isinstance(value, str) else None


def transient_provider_failure(error: Exception) -> bool:
    """Classify health failures without treating ambiguity as replay permission."""
    from openai import APIConnectionError, APIStatusError

    if isinstance(error, APIConnectionError):
        return True
    if not isinstance(error, APIStatusError):
        return False
    code = getattr(error, "code", None)
    if isinstance(code, str) and code in {
        "insufficient_quota", "billing_hard_limit_reached", "billing_not_active",
        "credit_balance_exhausted",
    }:
        return False
    return error.status_code in {408, 409, 429} or 500 <= error.status_code <= 599


def model_retry_settings(configuration: ProjectGuideRuntimeConfiguration):
    """Reuse the SDK loop/backoff, supplying only Workstream's replay-safe policy."""
    from agents import ModelRetrySettings, ModelRetryBackoffSettings, retry_policies
    from agents.retry import RetryDecision

    def safe_policy(context):
        normalized = context.normalized
        if (context.response_started or context.stateful_request
                or context.replay_safety == "unsafe" or normalized.is_abort
                or not transient_provider_failure(context.error)
                or _retry_header(context.error) == "false"):
            return RetryDecision(retry=False)
        safe = (
            _pretransmission_failure(context.error)
            or (normalized.status_code == 429 and normalized.error_code == "rate_limit_exceeded")
            or context.replay_safety == "safe"
        )
        if not safe:
            return RetryDecision(retry=False)
        delay = normalized.retry_after
        if delay is not None:
            # Never retry sooner than requested merely to fit the configured cap.
            if not math.isfinite(delay) or delay < 0 or delay > configuration.retry_max_delay_seconds:
                return RetryDecision(retry=False)
        return RetryDecision(retry=True, delay=delay)

    return ModelRetrySettings(
        max_retries=configuration.maximum_retries,
        backoff=ModelRetryBackoffSettings(
            initial_delay=configuration.retry_initial_delay_seconds,
            max_delay=configuration.retry_max_delay_seconds,
            multiplier=configuration.retry_backoff_multiplier,
            jitter=configuration.retry_jitter,
        ),
        policy=retry_policies.all(retry_policies.provider_suggested(), safe_policy),
    )


class ModelCircuitAdmission:
    """Hold pre-fence admission, preserving it across native retries of one turn."""

    def __init__(self, configuration: ProjectGuideRuntimeConfiguration):
        self._circuit = circuit_for(configuration)
        self._lifetime = configuration.timeout_seconds + configuration.cleanup_timeout_seconds
        self._lease = self._circuit.acquire(self._lifetime)
        self._closed = False
        self._model_failed = False

    def before_request(self) -> None:
        if self._closed:
            raise ProviderCircuitOpen()
        if self._lease is None:
            self._lease = self._circuit.acquire(self._lifetime)
        self._circuit.require_current(self._lease)
        self._model_failed = False

    def request_succeeded(self) -> None:
        if self._lease is not None:
            self._circuit.succeeded(self._lease)
            self._lease = None
        self._model_failed = False

    def request_failed(self, error: Exception) -> None:
        # The Runner may still retry this request. Count only when it exits.
        self._model_failed = transient_provider_failure(error)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._lease is not None:
            if self._model_failed:
                self._circuit.failed(self._lease)
            self._circuit.release(self._lease)
            self._lease = None
