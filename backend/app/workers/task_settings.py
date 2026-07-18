"""Helpers for applying runtime settings to Celery task objects."""

from __future__ import annotations

from app.core.config import get_settings


def sync_task_settings(*tasks: object) -> None:
    """Sync mutable Celery task settings from the current test/runtime config."""
    settings = get_settings()
    for task in tasks:
        task_app = task.app
        if settings.celery_broker_url is not None:
            task_app.conf.broker_url = settings.celery_broker_url
        elif settings.celery_task_always_eager:
            task_app.conf.broker_url = "memory://"
        task_app.conf.result_backend = settings.celery_result_backend_url
        task_app.conf.task_always_eager = settings.celery_task_always_eager
        task_app.conf.task_eager_propagates = True
