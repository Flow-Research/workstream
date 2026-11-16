"""Selected PRE work stays outside short claim and finalization roots."""

from __future__ import annotations

from app.adapters.artifacts import selected_pre_submit_source_contracts

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.identifiers import new_record_id
from app.modules.artifacts.selected_pre_submit_execution import (
    SelectedPreSubmitExecutionService,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
)
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitAuthorityEvidence,
    SelectedPreSubmitExecuteFacts,
    SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitInfrastructureUnavailable,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)


class _Session:
    def __init__(self, order: list[str]) -> None:
        self.active = False
        self.order = order

    @asynccontextmanager
    async def begin(self):
        assert not self.active
        self.active = True
        self.order.append("begin")
        try:
            yield
        finally:
            self.active = False
            self.order.append("commit")


class _Prepared:
    def __init__(self, order: list[str], phase: str) -> None:
        self.order = order
        self.phase = phase

    async def consume(self, facts):
        self.order.append("consume_" + self.phase)
        return SelectedPreSubmitAuthorityEvidence(
            evidence_id=new_record_id(), facts_digest=facts.facts_digest
        )


class _Authority:
    def __init__(self, session: _Session, order: list[str]) -> None:
        self.session = session
        self.order = order

    @asynccontextmanager
    async def prepare_execution(self, _reservation):
        assert self.session.active
        self.order.append("prepare_execute")
        yield _Prepared(self.order, "execute")

    @asynccontextmanager
    async def prepare_finalization(self, _facts):
        assert self.session.active
        self.order.append("prepare_finalize")
        yield _Prepared(self.order, "finalize")


class _Coordinator:
    def __init__(self, session: _Session, order: list[str], lease) -> None:
        self.session = session
        self.order = order
        self.lease = lease

    async def claim(self, *, authority, **_values):
        assert self.session.active
        self.order.append("claim")
        await authority.consume(SelectedPreSubmitExecuteFacts(self.lease))
        return self.lease

    async def committed_execution(self, **_values):
        assert not self.session.active
        self.order.append("committed_execution")
        return object()

    async def read_expired_lease(self, **_values):
        assert self.session.active
        self.order.append("read_expired_lease")
        return self.lease

    async def finalize(self, *, authority, execution, infrastructure_failure_code, **_values):
        assert self.session.active
        self.order.append("finalize")
        facts = SelectedPreSubmitFinalizeFacts(
            lease=self.lease,
            execution=execution,
            infrastructure_failure_code=infrastructure_failure_code,
         source_contracts=selected_pre_submit_source_contracts())
        await authority.consume(facts)
        return SimpleNamespace(terminal=facts, capability=None)


class _Materialization:
    def __init__(self, session: _Session, order: list[str]) -> None:
        self.session = session
        self.order = order

    async def materialize_selected_pre_submit(self, *_args, **_kwargs):
        assert not self.session.active
        self.order.append("materialize")
        raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")


def _reservation() -> SelectedPreSubmitReservationFacts:
    return SelectedPreSubmitReservationFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        project_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        attempt_id=new_record_id(),
        idempotency_key=new_record_id(),
        attempt_request_digest="sha256:" + "0" * 64,
        prepared_generation_id=new_record_id(),
        policy_sha256="sha256:" + "1" * 64,
        default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        default_input_sha256="sha256:" + "2" * 64,
        archive_sha256="sha256:" + "3" * 64,
        archive_byte_count=100,
        semantic_manifest_sha256="sha256:" + "4" * 64,
        execution_budget_ms=60_000,
     source_contracts=selected_pre_submit_source_contracts())


@pytest.mark.asyncio
async def test_selected_pre_execution_commits_lease_before_work_and_finalizes_after() -> None:
    order: list[str] = []
    session = _Session(order)
    reservation = _reservation()
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation,
        lease_id=new_record_id(),
        lease_generation=1,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    service = SelectedPreSubmitExecutionService(
        session=session,
        coordinator=_Coordinator(session, order, lease),
        authority=_Authority(session, order),
        materialization=_Materialization(session, order),
    )

    completed = await service.execute(
        reservation=reservation,
        materialization=SimpleNamespace(),
    )

    assert completed.terminal.infrastructure_failure_code == "material_unavailable"
    assert order == [
        "begin",
        "prepare_execute",
        "claim",
        "consume_execute",
        "commit",
        "committed_execution",
        "materialize",
        "begin",
        "prepare_finalize",
        "finalize",
        "consume_finalize",
        "commit",
    ]


@pytest.mark.asyncio
async def test_selected_pre_recovery_finalizes_expired_lease_without_material() -> None:
    order: list[str] = []
    session = _Session(order)
    reservation = _reservation()
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation,
        lease_id=new_record_id(),
        lease_generation=1,
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    service = SelectedPreSubmitExecutionService(
        session=session,
        coordinator=_Coordinator(session, order, lease),
        authority=_Authority(session, order),
        materialization=_Materialization(session, order),
    )

    completed = await service.recover_expired(
        run_id=reservation.attempt_id,
        reservation=reservation,
    )

    assert completed.terminal.infrastructure_failure_code == "deadline_exceeded"
    assert order == [
        "begin",
        "read_expired_lease",
        "commit",
        "begin",
        "prepare_finalize",
        "finalize",
        "consume_finalize",
        "commit",
    ]

    with pytest.raises(
        SelectedPreSubmitInfrastructureUnavailable,
        match="material_unavailable",
    ):
        await service.recover_expired(
            run_id=new_record_id(),
            reservation=reservation,
        )
