"""Bounded operational metrics for durable artifact admission."""

from __future__ import annotations

import json
import logging
from collections import Counter
from threading import Lock
from typing import Literal, Protocol

logger = logging.getLogger(__name__)
AdmissionPressureBand = Literal["normal", "warning", "critical", "exhausted"]


class ArtifactAdmissionMetrics(Protocol):
    def pressure(self, scope_type: str, counted_bytes: int, limit_bytes: int) -> None: ...


class InProcessArtifactAdmissionMetrics:
    """Process-lifetime counters with fixed, non-identifying labels."""

    _SCOPES = frozenset({"deployment", "project", "producer", "task"})

    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str]] = Counter()
        self._lock = Lock()

    def pressure(self, scope_type: str, counted_bytes: int, limit_bytes: int) -> None:
        if scope_type not in self._SCOPES or counted_bytes < 0 or limit_bytes <= 0:
            raise ValueError("artifact admission metric input is not allowed")
        band = pressure_band(counted_bytes, limit_bytes)
        with self._lock:
            self._counts[(scope_type, band)] += 1
        logger.info(
            "artifact_admission_metric %s",
            json.dumps(
                {
                    "metric": "workstream_artifact_admission_pressure_total",
                    "labels": {"scope_type": scope_type, "pressure_band": band},
                },
                sort_keys=True,
            ),
        )

    def snapshot(self) -> dict[tuple[str, str], int]:
        with self._lock:
            return dict(self._counts)


def pressure_band(counted_bytes: int, limit_bytes: int) -> AdmissionPressureBand:
    ratio = counted_bytes / limit_bytes
    if ratio >= 1:
        return "exhausted"
    if ratio >= 0.9:
        return "critical"
    if ratio >= 0.75:
        return "warning"
    return "normal"


artifact_admission_metrics = InProcessArtifactAdmissionMetrics()
