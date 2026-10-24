"""Trial identity, real current execution custody, atomic reservation and replay."""

import asyncio
import json

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.adapters.auth import post_submit_execution_authority
from app.adapters.tasks import evaluation_task_guard
from app.core.identifiers import new_record_id
from app.interfaces.project_agents import CapabilityParameter
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceStableSubject,
    TrialEvidenceUnavailable,
)
from app.modules.checkers.api.trial_profiles import (
    PinnedTrialExecutionCatalog,
    TrialAuthorityBinding,
)
from app.modules.checkers.models import CheckerTrialEvidence
from app.modules.checkers.trial_evidence import TrialEvidenceReservations
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor, reserve
from tests.checkers.external.support import post_registry_spec
from tests.checkers.external.test_trial_profiles import configuration, digest, profile, projection
from tests.checkers.external.test_trial_policy import trial_specification
from tests.checkers.external.test_revision_materialization import DiagnosticMaterialization
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_checker_materialization import _limits


def _subject(request, projected):
    identity = request.identity
    return TrialEvidenceStableSubject(
        project_id=identity.project_id,
        task_id=identity.task_id,
        assignment_id=identity.assignment_id,
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        requirement_id=request.input["requirement_id"],
        registry_entry_id=request.registry.registry_entry_id,
        registry_entry_digest=request.registry.entry_digest,
        configuration_sha256=request.configuration_sha256,
        trial_kind=projected.trial_kind,
        slot_index=0,
        plan_sha256=digest("1"),
        input_digest=request.input_sha256,
        materials_digest=external_checker_json_hash(
            [item.model_dump(mode="json") for item in request.materials]
        ),
    )


def _owner(session, request, catalog):
    return TrialEvidenceReservations(
        session,
        request=request,
        tasks=evaluation_task_guard(session),
        profiles=catalog,
        authority=post_submit_execution_authority(session),
    )


def _trial_fixture():
    selected = profile()
    # The shared artifact/model evidence protocol bounds each receipt to 1 MiB.
    assert selected.limits.maximum_receipt_bytes <= 1_048_576
    projected = projection(selected)
    config = {
        key: value
        for key, value in configuration(selected, projected).items()
        if key.startswith("trial_")
    }
    document = {
        "type": "object",
        "properties": {key: {"const": value} for key, value in config.items()},
        "required": sorted(config),
        "additionalProperties": False,
    }
    original = post_registry_spec()
    spec = type(original).model_validate(
        original.model_copy(
            update={
                "configuration_schema": ExternalCheckerSchema(
                    schema_id="trial_test_configuration",
                    schema_version="v1",
                    document=document,
                    schema_sha256=external_checker_json_hash(document),
                ),
            }
        ).model_dump()
    )

    async def parameters(_factory, _project, _registry):
        return tuple(CapabilityParameter(name=key, value=value) for key, value in config.items())

    def catalog_for(request):
        return PinnedTrialExecutionCatalog(
            tuple(
                TrialAuthorityBinding(
                    registry_entry_id=entry.registry.registry_entry_id,
                    registry_entry_digest=entry.registry.entry_digest,
                    checker_image_digest=entry.registry.image_digest,
                    configuration_sha256=entry.configuration_sha256,
                    profile=selected,
                    projection=projected,
                )
                for entry in request.policy.entries
            )
        )

    return spec, parameters, projected, catalog_for


async def _reject_raw_subject_substitution(factory, ticket):
    """A malformed owner insert must fail its guard, not just its unique key."""
    async with factory() as session:
        original = await session.scalar(
            text("SELECT to_jsonb(e) FROM checker_trial_evidence e WHERE id=:id"),
            {"id": ticket.trial_evidence_id},
        )
    for key, value, remove in (
        ("input_digest", None, False),
        ("input_digest", None, True),
        ("trial_kind", None, False),
        ("trial_kind", None, True),
        ("materials_digest", None, False),
        ("plan_sha256", None, True),
        ("slot_index", 1, False),
    ):
        candidate = dict(original)
        candidate["id"] = str(new_record_id())
        subject = dict(original["subject"])
        if remove:
            subject.pop(key)
        else:
            subject[key] = value
        candidate["subject"] = subject
        candidate["address_digest"] = external_checker_json_hash(
            {
                name: item
                for name, item in subject.items()
                if name not in {"plan_sha256", "input_digest", "materials_digest"}
            }
        )
        with pytest.raises(IntegrityError) as denied:
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO checker_trial_evidence SELECT * FROM "
                        "jsonb_populate_record(NULL::checker_trial_evidence,CAST(:payload AS jsonb))"
                    ),
                    {"payload": json.dumps(candidate)},
                )
        assert denied.value.orig.sqlstate == "23514"


class ReservingExecution(ControlledSelectedExecution):
    def __init__(self, factory, catalog, projected):
        super().__init__()
        self.factory, self.catalog, self.projected = factory, catalog, projected
        self.tickets = []

    async def execute(self, request, grant):
        subject = _subject(request, self.projected)
        async with self.factory() as first, first.begin():
            ticket = await _owner(first, request, self.catalog).reserve(subject)
            assert not ticket.replayed
            self.tickets.append(ticket)
        async with self.factory() as second, second.begin():
            replay = await _owner(second, request, self.catalog).reserve(subject)
            assert replay.replayed and replay.trial_evidence_id == ticket.trial_evidence_id
            assert replay.origin == ticket.origin and replay.content_sha256 is None
            # A verifier may already hold ART rows when it checks its trial
            # FK. That key-share check must progress while publication retains
            # the trial row, rather than forming a reverse lock dependency.
            async with self.factory() as verifier, verifier.begin():
                await verifier.execute(text("SET LOCAL lock_timeout='1s'"))
                shared = await verifier.scalar(
                    text("SELECT id FROM checker_trial_evidence WHERE id=:id FOR KEY SHARE"),
                    {"id": ticket.trial_evidence_id},
                )
                assert shared == ticket.trial_evidence_id
        for field, value in (
            ("plan_sha256", digest("2")),
            ("input_digest", digest("3")),
            ("materials_digest", digest("4")),
            ("slot_index", 1),
            ("assignment_id", new_record_id()),
        ):
            with pytest.raises((TrialEvidenceUnavailable, ValueError)):
                async with self.factory() as session, session.begin():
                    await _owner(session, request, self.catalog).reserve(
                        subject.model_copy(update={field: value}),
                    )
        await _reject_raw_subject_substitution(self.factory, ticket)
        return await super().execute(request, grant)


async def test_trial_reservation_is_current_exact_immutable_and_replayed(
    tmp_path,
    isolated_database_env,
):
    spec, parameters, projected, catalog_for = _trial_fixture()
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        post_submit_registry_spec=spec,
        post_submit_binding_setup=parameters,
        post_submit_specification=trial_specification(),
        # The consumer executes multiple real transactions and contention probes
        # while material remains open; it is not the ten-second parser unit case.
        scratch_limits=_limits(total_deadline_seconds=120.0, reservation_ttl_seconds=150.0),
    ) as h:
        catalog = catalog_for(h.request)
        await reserve(h)
        h.service = DiagnosticMaterialization(h.service)
        adapter = ReservingExecution(h.factory, catalog, projected)
        completed = await live_executor(h, selected_execution=adapter).evaluate_post_submission(
            h.request
        )
        assert completed.outcome == "completed", completed.model_dump_json()
        assert len(adapter.tickets) == 1
        ticket = adapter.tickets[0]
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerTrialEvidence)) == 1
        # Current execution has ended: neither a guessed old lease nor an exact
        # historical address grants another trial or content access.
        with pytest.raises(TrialEvidenceUnavailable):
            async with h.factory() as session, session.begin():
                await _owner(session, adapter.requests[0], catalog).reserve(ticket.subject)
        for statement in (
            "UPDATE checker_trial_evidence SET maximum_bytes=maximum_bytes+1 WHERE id=:id",
            "DELETE FROM checker_trial_evidence WHERE id=:id",
        ):
            with pytest.raises(IntegrityError):
                async with h.factory() as session, session.begin():
                    await session.execute(text(statement), {"id": ticket.trial_evidence_id})


class RollbackExecution(ControlledSelectedExecution):
    def __init__(self, factory, catalog, projected):
        super().__init__()
        self.factory, self.catalog, self.projected = factory, catalog, projected

    async def execute(self, request, grant):
        subject = _subject(request, self.projected)
        entered = asyncio.Event()
        contender_pid = None

        async def contender():
            nonlocal contender_pid
            async with self.factory() as session, session.begin():
                contender_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                entered.set()
                return await _owner(session, request, self.catalog).reserve(subject)

        async with self.factory() as first:
            transaction = await first.begin()
            holder_pid = await first.scalar(text("SELECT pg_backend_pid()"))
            abandoned = await _owner(first, request, self.catalog).reserve(subject)
            pending = asyncio.create_task(contender())
            try:
                await asyncio.wait_for(entered.wait(), 5)
                async with asyncio.timeout(5):
                    async with self.factory() as observer:
                        while not await observer.scalar(
                            text("SELECT :holder = ANY(pg_blocking_pids(:contender))"),
                            {"holder": holder_pid, "contender": contender_pid},
                        ):
                            assert not pending.done(), "contender escaped custody wait"
                            await asyncio.sleep(0.02)
                await transaction.rollback()
                winner = await asyncio.wait_for(pending, 15)
            finally:
                if transaction.is_active:
                    await transaction.rollback()
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        assert not winner.replayed and winner.trial_evidence_id != abandoned.trial_evidence_id
        async with self.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerTrialEvidence)) == 1
            assert await session.get(CheckerTrialEvidence, str(abandoned.trial_evidence_id)) is None
        return await super().execute(request, grant)


async def test_concurrent_trial_reservation_waits_then_recovers_complete_rollback(
    tmp_path,
    isolated_database_env,
):
    spec, parameters, projected, catalog_for = _trial_fixture()
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        post_submit_registry_spec=spec,
        post_submit_binding_setup=parameters,
        post_submit_specification=trial_specification(),
        # The consumer executes multiple real transactions and contention probes
        # while material remains open; it is not the ten-second parser unit case.
        scratch_limits=_limits(total_deadline_seconds=120.0, reservation_ttl_seconds=150.0),
    ) as h:
        catalog = catalog_for(h.request)
        await reserve(h)
        h.service = DiagnosticMaterialization(h.service)
        adapter = RollbackExecution(h.factory, catalog, projected)
        completed = await live_executor(h, selected_execution=adapter).evaluate_post_submission(
            h.request
        )
        assert completed.outcome == "completed", completed.model_dump_json()
