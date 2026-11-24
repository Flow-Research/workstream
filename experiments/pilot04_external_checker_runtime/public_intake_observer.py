"""Opt-in drill entry point recording real adapter acknowledgements, never faking them."""

import json
import os
from pathlib import Path
import time
from uuid import uuid4

from app.adapters.artifacts.trusted_intake import RemoteTlsTrustedIntakeAdapter
from app.adapters.checkers.external_service import RemoteTlsExternalCheckerAdapter

_TRACE = Path(os.environ["WORKSTREAM_PROBE_INTAKE_TRACE"])
_prepare = RemoteTlsTrustedIntakeAdapter.prepare
_execute = RemoteTlsExternalCheckerAdapter.execute


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


# This explicitly selected proof entry point delegates all work to the original
# typed adapter. Production app imports and ordinary workers never install it.
RemoteTlsTrustedIntakeAdapter.prepare = _observe_prepare
RemoteTlsExternalCheckerAdapter.execute = _observe_execute
from app.main import app as app  # noqa: E402
