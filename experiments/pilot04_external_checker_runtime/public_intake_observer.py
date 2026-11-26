"""Opt-in drill entry point recording real adapter acknowledgements, never faking them."""

import asyncio
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from app.adapters.artifacts.trusted_intake import RemoteTlsTrustedIntakeAdapter
from app.adapters.checkers.external_service import RemoteTlsExternalCheckerAdapter

_TRACE = Path(os.environ["WORKSTREAM_PROBE_INTAKE_TRACE"])
_PRE_BARRIER = os.environ.get("WORKSTREAM_PROBE_PRE_BARRIER")
_prepare = RemoteTlsTrustedIntakeAdapter.prepare
_execute = RemoteTlsExternalCheckerAdapter.execute
_execute_pre = RemoteTlsExternalCheckerAdapter.execute_pre


def _record(event, identifier, **facts):
    with _TRACE.open("a") as output:
        output.write(json.dumps({"event": event, "session": identifier,
                                 "monotonic": time.monotonic(), **facts}) + "\n")


async def _observe_prepare(self, request):
    identifier = uuid4().hex
    _record("prepare_started", identifier, phase=request.phase, deadline_ms=request.deadline_ms)
    try:
        session = await _prepare(self, request)
    except BaseException:
        _record("prepare_failed", identifier)
        raise
    _record("prepare_ready", identifier)
    close = session.close

    async def observed_close():
        try:
            await close()
        except BaseException:
            _record("close_unconfirmed", identifier)
            raise
        _record("close_confirmed", identifier)

    session.close = observed_close
    return session


async def _observe_execute(self, request, grant, *, model_grant=None):
    _record('project_started', request.request_digest)
    result = await _execute(self, request, grant, model_grant=model_grant)
    _record('project_completed', request.request_digest)
    return result


async def _observe_pre(self, lease, grant):
    if _PRE_BARRIER is not None:
        root = Path(_PRE_BARRIER)
        selector = root / "source.sha256"
        source = lease.reservation.source
        if selector.exists() and selector.read_text().strip() == source.raw_sha256:
            temporary = root / "pre-dispatch.pending"
            with temporary.open("x") as output:
                json.dump({"run_id": str(lease.reservation.attempt_id),
                           "source_operation_id": str(source.location.operation_id),
                           "request_digest": lease.reservation.request_digest,
                           "lease_id": str(lease.lease_id),
                           "lease_generation": lease.lease_generation}, output)
            temporary.rename(root / "pre-dispatch.json")
            while not (root / "release-pre").exists():
                if time.time() >= lease.lease_expires_at.timestamp():
                    raise TimeoutError("PRE overlap fixture missed its original lease")
                await asyncio.sleep(0.05)
    return await _execute_pre(self, lease, grant)


# This explicitly selected proof entry point delegates all work to the original
# typed adapter. Production app imports and ordinary workers never install it.
RemoteTlsTrustedIntakeAdapter.prepare = _observe_prepare
RemoteTlsExternalCheckerAdapter.execute = _observe_execute
RemoteTlsExternalCheckerAdapter.execute_pre = _observe_pre
from app.main import app as app  # noqa: E402
