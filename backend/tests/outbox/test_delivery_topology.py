"""Actual worker startup selection and synchronous entry guard, before SQL."""

import os
from types import SimpleNamespace

import pytest
from celery.concurrency.prefork import TaskPool
from celery.concurrency.solo import TaskPool as SoloPool
from celery.exceptions import QueueNotFound, WorkerShutdown

from app.workers import outbox_topology as topology


def worker(*, queues=(topology.OUTBOX_QUEUE,), pool=TaskPool, eager=False):
    return SimpleNamespace(pool_cls=pool, app=SimpleNamespace(
        conf=SimpleNamespace(task_always_eager=eager),
        amqp=SimpleNamespace(queues=SimpleNamespace(consume_from=queues)),
    ))


@pytest.fixture(autouse=True)
def restore_process_state(monkeypatch):
    from celery._state import _set_task_join_will_block, task_join_will_block

    original_join_guard = task_join_will_block()
    monkeypatch.setattr(topology, "_validated_parent", None)
    monkeypatch.setattr(topology, "_validated_finalization", False)
    monkeypatch.setattr(topology, "_validated_scan", False)
    try:
        yield
    finally:
        # Actual Worker construction changes this process-global Celery flag.
        _set_task_join_will_block(original_join_guard)


@pytest.mark.parametrize("pool", ["solo", SoloPool, "threads"])
def test_delivery_queue_requires_prefork(pool):
    with pytest.raises(WorkerShutdown):
        topology.validate_outbox_worker(worker(pool=pool))
    assert topology._validated_parent is None


def test_delivery_queue_rejects_eager():
    with pytest.raises(WorkerShutdown):
        topology.validate_outbox_worker(worker(eager=True))
    assert topology._validated_parent is None


def test_other_queue_allows_solo():
    topology.validate_outbox_worker(worker(queues=("celery",), pool=SoloPool))
    assert topology._validated_parent is None


@pytest.mark.parametrize("mode", ["direct", "eager", "unvalidated", "parent", "dynamic_queue"])
def test_delivery_entry_rejects_unvalidated_execution(monkeypatch, mode):
    configured = worker()
    if mode == "dynamic_queue":
        configured = worker(queues=("celery",), pool=TaskPool)
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", lambda: os.getpid() if mode != "parent" else 1)
    if mode == "unvalidated":
        topology._validated_parent = None
    request = SimpleNamespace(is_eager=mode == "eager", called_directly=mode == "direct")
    with pytest.raises(RuntimeError, match="validated prefork"):
        topology.require_outbox_worker(SimpleNamespace(app=configured.app, request=request))


def test_validated_prefork_child_enters(monkeypatch):
    configured = worker(pool="prefork")
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    topology.require_outbox_worker(SimpleNamespace(app=configured.app,
        time_limit=topology.OUTBOX_HARD_LIMIT_SECONDS,
        request=SimpleNamespace(is_eager=False, called_directly=False, timelimit=None)))


def test_synchronous_task_rejects_before_sql(monkeypatch):
    from uuid import uuid4
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import outbox
    def forbidden(*_args, **_kwargs):
        pytest.fail("unvalidated delivery reached SQL/async execution")
    monkeypatch.setattr(outbox, "run_async_task", forbidden)
    try:
        with pytest.raises(RuntimeError, match="validated prefork"):
            outbox.deliver_event.apply(args=(str(uuid4()), str(uuid4())), task_id=str(uuid4()), throw=True)
        with pytest.raises(RuntimeError, match="validated prefork"):
            outbox.deliver_event(str(uuid4()), str(uuid4()))
    finally:
        get_settings.cache_clear()


def test_delivery_routes_to_dedicated_queue(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers.celery_app import create_celery_app
    app = create_celery_app()
    try:
        route = app.amqp.router.route({}, topology.OUTBOX_DELIVERY_TASK)
        assert route["queue"].name == topology.OUTBOX_QUEUE
        from app.workers.celery_app import PROJECT_GUIDE_COMPILATION_TASK
        from app.workers.project_setup_topology import PROJECT_GUIDE_QUEUE
        assert app.amqp.router.route({}, PROJECT_GUIDE_COMPILATION_TASK)["queue"].name == PROJECT_GUIDE_QUEUE
        with pytest.raises(QueueNotFound):
            app.amqp.router.route({}, "workstream.unregistered")
    finally:
        app.close()
        get_settings.cache_clear()


@pytest.mark.parametrize("task_limit,message_limit", [
    (None, None), (300, None), (topology.OUTBOX_HARD_LIMIT_SECONDS + 1, None),
    (topology.OUTBOX_HARD_LIMIT_SECONDS, 300),
    (topology.OUTBOX_HARD_LIMIT_SECONDS, topology.OUTBOX_HARD_LIMIT_SECONDS + 1),
    (topology.OUTBOX_HARD_LIMIT_SECONDS, 0),
])
def test_delivery_cannot_disable_or_extend_process_bound(monkeypatch, task_limit, message_limit):
    configured = worker()
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    with pytest.raises(RuntimeError, match="bounded hard time limit"):
        topology.require_outbox_worker(SimpleNamespace(app=configured.app, time_limit=task_limit,
            request=SimpleNamespace(is_eager=False, called_directly=False, timelimit=(message_limit, None))))


@pytest.mark.parametrize("pool,eager", [("solo", False), ("threads", False), ("prefork", True)])
def test_actual_worker_startup_rejects_invalid_delivery_topology(monkeypatch, pool, eager):
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers.celery_app import create_celery_app
    app = create_celery_app()
    app.conf.task_always_eager = eager
    try:
        with pytest.raises(WorkerShutdown):
            app.Worker(pool=pool, queues=[topology.OUTBOX_QUEUE])
        assert topology._validated_parent is None
    finally:
        app.close()
        get_settings.cache_clear()


def test_actual_unregistered_queue_worker_is_refused(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers.celery_app import create_celery_app
    app = create_celery_app()
    app.conf.task_always_eager = False
    try:
        with pytest.raises(Exception, match="isn't|missing"):
            app.Worker(pool="solo", queues=["workstream.unrelated"])
        assert topology._validated_parent is None
    finally:
        app.close()
        get_settings.cache_clear()


@pytest.mark.parametrize("extra", [topology.OUTBOX_QUEUE, "celery"])
def test_finalization_worker_cannot_share_capacity_with_other_queues(extra):
    with pytest.raises(WorkerShutdown, match="exclusive worker queue"):
        topology.validate_outbox_worker(worker(queues=(topology.FINALIZATION_QUEUE, extra)))
    assert topology._validated_parent is None


def test_finalization_prefork_worker_rejects_general_delivery(monkeypatch):
    configured = worker(queues=(topology.FINALIZATION_QUEUE,))
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    task = SimpleNamespace(app=configured.app, time_limit=topology.FINALIZATION_HARD_LIMIT_SECONDS,
        request=SimpleNamespace(is_eager=False, called_directly=False, timelimit=None))
    topology.require_outbox_worker(task, finalization=True)
    with pytest.raises(RuntimeError, match="validated prefork"):
        topology.require_outbox_worker(task)


def test_finalization_task_routes_to_reserved_queue(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers.celery_app import create_celery_app
    app = create_celery_app()
    try:
        assert app.amqp.router.route({}, topology.FINALIZATION_DELIVERY_TASK)["queue"].name == topology.FINALIZATION_QUEUE
        assert app.amqp.router.route({}, topology.OUTBOX_SCAN_TASK)["queue"].name == topology.OUTBOX_SCAN_QUEUE
        assert app.tasks[topology.OUTBOX_SCAN_TASK].time_limit == topology.OUTBOX_SCAN_HARD_LIMIT_SECONDS
        assert app.conf.beat_schedule["outbox-delivery-recovery"] == {
            "task": topology.OUTBOX_SCAN_TASK, "schedule": 60.0,
        }
        app.conf.task_always_eager = False
        with pytest.raises(WorkerShutdown, match="exclusive worker queue"):
            app.Worker(pool="prefork", queues=[topology.FINALIZATION_QUEUE, topology.OUTBOX_QUEUE])
    finally:
        app.close()
        get_settings.cache_clear()


def test_every_registered_workstream_task_has_one_explicit_queue(monkeypatch):
    """Independent task inventory rejects an accidental default or mixed role."""
    from app.core.config import get_settings
    from app.workers.celery_app import WORKSTREAM_TASK_ROUTES, create_celery_app

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    app = create_celery_app()
    expected = {
        "workstream.project_setup.compile_project_guide": "workstream.project_setup",
        "workstream.project_setup.derive_post_policy": "workstream.project_control",
        "workstream.project_setup.scan_post_policy_approvals": "workstream.project_control",
        "workstream.project_setup.cleanup_runtime_resources": "workstream.project_control",
        "workstream.tasks.scan_retained_revisions": "workstream.project_control",
        "workstream.artifacts.cleanup_stale_scratch": "workstream.artifacts",
        "workstream.artifacts.resolve_put_attempt": "workstream.artifacts",
        "workstream.artifacts.verify_object": "workstream.artifacts",
        "workstream.artifacts.scan_pending_work": "workstream.artifacts",
        "workstream.artifacts.continue_guide_setup": "workstream.artifacts",
        "workstream.artifacts.scan_guide_setup_continuations": "workstream.artifacts",
        "workstream.outbox.scan_pending": "workstream.outbox_scan",
        "workstream.outbox.deliver_event": "workstream.outbox",
        "workstream.outbox.finalize_submission": "workstream.submission_finalization",
        "workstream.artifacts.sweep_submission_sources": "workstream.source_cleanup",
    }
    try:
        app.loader.import_default_modules()
        assert {name for name in app.tasks if name.startswith("workstream.")} == set(expected)
        assert app.conf.task_routes[0] is WORKSTREAM_TASK_ROUTES
        assert {name: route["queue"] for name, route in WORKSTREAM_TASK_ROUTES.items()} == expected
        assert {queue.name for queue in app.conf.task_queues} == set(expected.values())
        assert app.conf.task_create_missing_queues is False
        for scheduled in app.conf.beat_schedule.values():
            assert scheduled["task"] in expected
        for name, queue in expected.items():
            assert app.amqp.router.route({}, name)["queue"].name == queue
    finally:
        app.close()
        get_settings.cache_clear()


@pytest.mark.parametrize("queues", [
    (topology.OUTBOX_SCAN_QUEUE, topology.OUTBOX_QUEUE),
    (topology.OUTBOX_SCAN_QUEUE, topology.FINALIZATION_QUEUE),
    (topology.OUTBOX_SCAN_QUEUE, "celery"),
])
def test_scan_worker_refuses_shared_queues(queues):
    with pytest.raises(WorkerShutdown, match="exclusive worker queue"):
        topology.validate_outbox_worker(worker(queues=queues))


def test_scan_entry_requires_dedicated_prefork_and_sixty_second_limit(monkeypatch):
    configured = worker(queues=(topology.OUTBOX_SCAN_QUEUE,))
    topology.validate_outbox_worker(configured)
    task = SimpleNamespace(app=configured.app, time_limit=topology.OUTBOX_SCAN_HARD_LIMIT_SECONDS,
        request=SimpleNamespace(is_eager=False, called_directly=False, timelimit=None))
    with pytest.raises(RuntimeError, match="validated prefork"):
        topology.require_outbox_scan_worker(task)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    topology.require_outbox_scan_worker(task)
    with pytest.raises(RuntimeError, match="bounded hard time limit"):
        topology.require_outbox_scan_worker(SimpleNamespace(app=configured.app, time_limit=61,
            request=task.request))
    with pytest.raises(RuntimeError, match="validated prefork"):
        topology.require_outbox_worker(task)


@pytest.mark.parametrize("selected,name,routing_key", [
    ("workstream.outbox_scan", "workstream.outbox.deliver_event", "workstream.outbox_scan"),
    ("workstream.project_control", "workstream.artifacts.verify_object", "workstream.project_control"),
    ("workstream.artifacts", "workstream.artifacts.verify_object", "workstream.project_control"),
])
def test_dedicated_worker_rejects_foreign_registered_delivery_before_owner_io(
    monkeypatch, selected, name, routing_key,
):
    from app.core.config import get_settings
    from app.workers import source_cleanup_topology as boundary
    from app.workers.celery_app import create_celery_app

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    app = create_celery_app()
    monkeypatch.setattr(boundary, "_selected_queue_parent", os.getpid())
    monkeypatch.setattr(boundary, "_selected_queue", selected)
    monkeypatch.setattr(boundary, "_validated_parent", None)
    monkeypatch.setattr(boundary.os, "getppid", os.getpid)
    fake = SimpleNamespace(name=name, app=app,
        request=SimpleNamespace(delivery_info={"routing_key": routing_key}))
    try:
        with pytest.raises(RuntimeError, match="dedicated worker rejects a foreign task"):
            boundary.WorkerTaskBoundary.before_start(fake, "task-id", (), {})
    finally:
        app.close()
        get_settings.cache_clear()


def test_scan_routes_each_event_group_without_acknowledging(monkeypatch):
    from app.core.config import get_settings
    from app.core.identifiers import new_record_id
    from app.modules.outbox.api import DeliveryCandidate, DeliveryCandidatePage
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import outbox
    items = tuple(DeliveryCandidate(event_id=new_record_id(), project_id=new_record_id(), event_type=kind)
                  for kind in ("PostSubmissionEvaluationRequested", "SubmissionFinalizationRequested", "SubmissionFinalizationRecoveryRequested"))
    async def candidates(_after):
        return DeliveryCandidatePage(items=items, next_after=None)
    published = []
    monkeypatch.setattr(outbox, "_candidates", candidates)
    monkeypatch.setattr(outbox, "require_outbox_scan_worker", lambda _task: None)
    monkeypatch.setattr(outbox.deliver_event, "apply_async", lambda **kwargs: published.append(("post", kwargs)))
    monkeypatch.setattr(outbox.finalize_submission, "apply_async", lambda **kwargs: published.append(("final", kwargs)))
    try:
        assert outbox.scan_pending.apply(task_id=str(new_record_id()), throw=True).get() == {"selected": 3, "published": 3}
        assert published == [(kind, {"args": (str(item.event_id), str(item.project_id))})
                             for kind, item in zip(("post", "final", "final"), items, strict=True)]
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("finalization", [False, True])
def test_finalization_child_defers_provider_startup_for_sql_only_replay(monkeypatch, finalization):
    import importlib
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    module = importlib.import_module("app.workers.celery_app")
    configured = worker(queues=(topology.FINALIZATION_QUEUE if finalization else topology.OUTBOX_QUEUE,))
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    calls = []
    def unavailable(callback):
        calls.append(callback)
        raise RuntimeError("provider startup unavailable")
    monkeypatch.setattr(module, "run_async_task", unavailable)
    try:
        if finalization:
            module.initialize_artifact_runtime_for_process()
            assert calls == []
        else:
            with pytest.raises(RuntimeError, match="provider startup unavailable"):
                module.initialize_artifact_runtime_for_process()
            assert calls == [module.initialize_artifact_internal_runtime]
    finally:
        get_settings.cache_clear()
