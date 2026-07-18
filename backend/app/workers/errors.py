"""Worker infrastructure exceptions."""

from __future__ import annotations


class CeleryConfigurationError(RuntimeError):
    """Raised when Celery cannot be configured from Workstream settings."""
