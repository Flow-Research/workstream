"""Nominal capabilities and fail-closed prepare/consume/replay/closure translation."""

import asyncio
from contextlib import asynccontextmanager
from copy import Error as CopyError, copy, deepcopy
import pickle
from uuid import uuid4

import pytest

from app.modules.authorization import project_setup_finalization as adapters
from app.modules.authorization.api import (
    AuthorizationDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
    PreparedSetupFinalization,
)
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationUnsupported,
)
from .support import Case


@pytest.mark.parametrize("operation", [copy, deepcopy, pickle.dumps])
async def test_prepared_finalization_is_process_local(monkeypatch, operation):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        assert isinstance(prepared, PreparedSetupFinalization)
        with pytest.raises((CopyError, TypeError)):
            operation(prepared)
        prepared._handle = object()
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume_new(case.facts)
    assert case.evidence.events == []


@pytest.mark.parametrize("stage", ["enter", "prepare", "consume", "replay", "close"])
@pytest.mark.parametrize(
    "error,public",
    [
        (PreparedAuthorizationHandleInvalid("private"), PreparedAuthorizationInvalid),
        (
            PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED),
            AuthorizationDenied,
        ),
        (AuthorizationEvidenceUnavailable("private"), AuthorizationUnavailable),
    ],
)
async def test_prepare_consume_and_close_fail_closed(monkeypatch, stage, error, public):
    case = Case(monkeypatch)
    original_fixed = adapters.fixed_service_prepared_authorization
    exits = []

    async def fail(*args, **kwargs):
        raise error

    @asynccontextmanager
    async def fixed(*args, **kwargs):
        if stage == "enter":
            raise error
        async with original_fixed(*args, **kwargs) as owned:
            if stage == "prepare":
                monkeypatch.setattr(owned.service, "prepare", fail)
            elif stage in {"consume", "replay"}:
                monkeypatch.setattr(
                    owned.service, "consume" if stage == "consume" else "validate_replay", fail
                )
            try:
                yield owned
            finally:
                exits.append(True)
                if stage == "close":
                    raise error

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    with pytest.raises(public) as caught:
        async with case.prepare() as prepared:
            if stage == "replay":
                await prepared.validate_replay(case.facts, uuid4())
            elif stage == "consume":
                await prepared.consume_new(case.facts)
    assert "private" not in str(caught.value)
    assert exits == ([] if stage == "enter" else [True])
    assert case.closed == case.services


@pytest.mark.parametrize(
    "error",
    [RuntimeError("caller"), AuthorizationEvidenceUnavailable("caller"), asyncio.CancelledError()],
)
async def test_caller_error_is_preserved_and_closes_once(monkeypatch, error):
    case = Case(monkeypatch)
    with pytest.raises(type(error)) as caught:
        async with case.prepare():
            raise error
    assert caught.value is error
    assert len(case.closed) == 1


@pytest.mark.parametrize("operation", ["consume", "replay"])
async def test_wrong_fact_kind_is_concealed(monkeypatch, operation):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        with pytest.raises(PreparedAuthorizationInvalid):
            if operation == "consume":
                await prepared.consume_new(object())
            else:
                await prepared.validate_replay(object(), uuid4())
    assert case.evidence.events == []
