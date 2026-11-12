"""Actual worker startup selection and synchronous entry guard, before SQL."""

import os
from types import SimpleNamespace

import pytest
from celery.concurrency.prefork import TaskPool
from celery.concurrency.solo import TaskPool as SoloPool
from celery.exceptions import WorkerShutdown

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
        assert app.amqp.router.route({}, "workstream.project_setup.compile")["queue"].name == "celery"
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


def test_actual_other_queue_worker_allows_solo(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers.celery_app import create_celery_app
    app = create_celery_app()
    app.conf.task_always_eager = False
    try:
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
        app.conf.task_always_eager = False
        with pytest.raises(WorkerShutdown, match="exclusive worker queue"):
            app.Worker(pool="prefork", queues=[topology.FINALIZATION_QUEUE, topology.OUTBOX_QUEUE])
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
                  for kind in ("PostSubmissionEvaluationRequested", "SubmissionFinalizationRequested"))
    async def candidates(_after):
        return DeliveryCandidatePage(items=items, next_after=None)
    published = []
    monkeypatch.setattr(outbox, "_candidates", candidates)
    monkeypatch.setattr(outbox.deliver_event, "apply_async", lambda **kwargs: published.append(("post", kwargs)))
    monkeypatch.setattr(outbox.finalize_submission, "apply_async", lambda **kwargs: published.append(("final", kwargs)))
    try:
        assert outbox.scan_pending.apply(task_id=str(new_record_id()), throw=True).get() == {"selected": 2, "published": 2}
        assert published == [(kind, {"args": (str(item.event_id), str(item.project_id))})
                             for kind, item in zip(("post", "final"), items, strict=True)]
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
