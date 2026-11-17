"""Independent installed guards with real request authority and direct SQL."""

import asyncio
from datetime import timedelta
import json
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from fastapi import Request
from app.db.errors import integrity_constraint_name
from app.db.session import get_db_session
from app.modules.compensation.api.fulfillment_evidence import FulfillmentEvidenceUnavailable
from app.modules.compensation.fulfillment.evidence_service import FulfillmentEvidenceService
from tests.finance.fulfillment_native_support import (
    insert_native, native_authority, native_custody, native_report_ack, native_source,
)
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.finance.test_fulfillment_evidence_public_api import evidence_rows, report_for
from tests.reviews.lifecycle.test_fence import observe_advisory_wait


def incident_for(report):
    return {key: report[key] for key in (
        "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
        "adapter_binding_id", "correlation_id", "contract_version", "route_key",
    )} | {"exception_event_id": str(new_record_id()),
        "original_fulfillment_event_id": report["external_event_id"], "kind": "provider_reversal",
        "observed_at": report["reported_at"], "reported_at": report["reported_at"]}


async def test_native_source_authority_body_parent_and_immutability_refusals(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    fulfilled = report_for(source.obligation)
    response = await source.client.post(prefix + "/fulfillment-reports", json=fulfilled,
        headers=source.headers | {"Idempotency-Key": fulfilled["external_event_id"]})
    assert response.status_code == 201, response.text
    baseline = await evidence_rows(source)
    mutations = (
        ("source_instance_id", new_record_id(), "fulfillment_evidence_lifecycle"),
        ("fulfillment_root_id", new_record_id(), "fulfillment_evidence_source"),
        ("award_id", new_record_id(), "fulfillment_evidence_source"),
        ("project_id", str(new_record_id()), "fulfillment_evidence_source"),
        ("reporter_actor_id", str(new_record_id()), "fulfillment_evidence_reporter"),
        ("reporter_identity_link_id", str(new_record_id()), "fulfillment_evidence_reporter"),
        ("authorization_decision_id", new_record_id(), "fulfillment_evidence_authority"),
        ("authorization_resource_digest", "sha256:" + "0" * 64, "fulfillment_evidence_authority"),
        ("body_quantity", None, "fulfillment_report_body"),
        ("claimed_digest", "sha256:" + "0" * 64, "fulfillment_evidence_body_digest"),
        ("old_allow", UUID(baseline[0][0]["authorization_decision_id"]), "fulfillment_evidence_authority"),
        ("original_receipt_id", new_record_id(), "fulfillment_exception_parent"),
        ("kind", "provider_status_conflict", "fulfillment_exception_body"),
    )
    for field, changed, expected in mutations:
        exception = field in {"original_receipt_id", "kind"}
        body = incident_for(fulfilled) if exception else report_for(source.obligation)
        if field == "body_quantity":
            body["fulfilled_quantity"] = "0.01" if source.obligation["quantity"] != "0.01" else "0.02"
        if field == "old_allow":
            body = fulfilled
        observed = []
        async def probe(owner, award, event, raw):
            value = json.loads(raw)
            located = await native_source(owner, award)
            async with native_custody(owner, located) as custody:
                digest = changed if field == "claimed_digest" else canonical_json_hash(value)
                async with native_authority(owner, custody, value, digest, exception=exception) as values:
                    if field == "old_allow":
                        values["authorization_decision_id"] = changed
                    elif field not in {"body_quantity", "claimed_digest"}:
                        values[field] = changed
                    try:
                        await insert_native(owner, values, exception=exception)
                    except IntegrityError as exc:
                        observed.append(integrity_constraint_name(exc))
                        raise
                    raise AssertionError("native guard admitted substituted evidence")
        method, suffix, key = (("exception", "/fulfillment-exceptions", "exception_event_id") if exception
                              else ("report", "/fulfillment-reports", "external_event_id"))
        with monkeypatch.context() as patch:
            patch.setattr(FulfillmentEvidenceService, method, probe)
            denied = await source.client.post(prefix + suffix, json=body,
                headers=source.headers | {"Idempotency-Key": body[key]})
        assert denied.status_code == 503 and observed == [expected], (field, denied.text, observed)
        assert await evidence_rows(source) == baseline
    incident = incident_for(fulfilled)
    recorded = await source.client.post(prefix + "/fulfillment-exceptions", json=incident,
        headers=source.headers | {"Idempotency-Key": incident["exception_event_id"]})
    assert recorded.status_code == 201, recorded.text
    immutable = await evidence_rows(source)
    statements = [f"{verb} public.{table}" for table in (
        "compensation_fulfillment_receipts", "compensation_fulfillment_exceptions",
    ) for verb in ("UPDATE", "DELETE FROM")]
    for statement in statements:
        if statement.startswith("UPDATE"):
            statement += " SET recording_lifecycle_generation=recording_lifecycle_generation"
        async with source.factory() as session:
            with pytest.raises(DBAPIError, match="immutable"):
                await session.execute(text(statement))
            await session.rollback()
    async with source.factory() as session:
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(text("TRUNCATE public.compensation_fulfillment_receipts, "
                                       "public.compensation_fulfillment_exceptions"))
        await session.rollback()
    assert await evidence_rows(source) == immutable


async def test_native_allow_receipt_deferred_closure(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    fulfilled = report_for(source.obligation)
    prefix = f"/api/v1/compensation/awards/{fulfilled['award_id']}"
    seeded = await source.client.post(prefix + "/fulfillment-reports", json=fulfilled,
        headers=source.headers | {"Idempotency-Key": fulfilled["external_event_id"]})
    assert seeded.status_code == 201, seeded.text
    async with source.factory() as session:
        assert await session.scalar(text("SELECT tgdeferrable AND tginitdeferred FROM pg_trigger "
            "WHERE tgname='compensation_fulfillment_allow_closure' "
            "AND tgrelid='public.audit_events'::regclass")) is True
    before = await evidence_rows(source)
    for exception in (False, True):
        for paired_other in (False, True):
            body = incident_for(fulfilled) if exception else report_for(source.obligation)
            observed = []
            async def probe(owner, award, event, raw):
                value = json.loads(raw)
                located = await native_source(owner, award)
                async with native_custody(owner, located) as custody:
                    async with native_authority(owner, custody, value, canonical_json_hash(value), exception=exception):
                        if paired_other:
                            other = (value | {"exception_event_id": str(new_record_id())}) if exception else (
                                value | {"external_event_id": str(new_record_id()), "reported_status": "failed",
                                    "fulfilled_quantity": None, "fulfilled_at": None, "external_reference": None,
                                    "failure_code": "PROVIDER_TIMEOUT"})
                            async with native_authority(owner, custody, other, canonical_json_hash(other), exception=exception) as row:
                                await insert_native(owner, row, exception=exception)
                        try:
                            # Force the installed deferred trigger without ever
                            # committing an orphan, even if the guard is removed.
                            await owner._session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                        except IntegrityError as exc:
                            observed.append(integrity_constraint_name(exc))
                            raise
                        raise FulfillmentEvidenceUnavailable("native closure probe rollback")
            method, suffix, key = (("exception", "/fulfillment-exceptions", "exception_event_id") if exception
                                  else ("report", "/fulfillment-reports", "external_event_id"))
            with monkeypatch.context() as patch:
                patch.setattr(FulfillmentEvidenceService, method, probe)
                response = await source.client.post(prefix + suffix, json=body,
                    headers=source.headers | {"Idempotency-Key": body[key]})
            expected = "fulfillment_exception_allow_closure" if exception else "fulfillment_report_allow_closure"
            assert response.status_code == 503 and observed == [expected], (response.text, observed)
            assert await evidence_rows(source) == before


@pytest.mark.parametrize("isolation", ("REPEATABLE READ", "SERIALIZABLE"))
async def test_native_non_rc_refuses_without_effects(fulfillment_api_source, isolated_database_env, monkeypatch, isolation):
    source = fulfillment_api_source
    body = report_for(source.obligation)
    app, observed = source.client._transport.app, []
    engine = create_async_engine(isolated_database_env, poolclass=NullPool, isolation_level=isolation)
    async def session_dependency():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    async def probe(owner, award, event, raw):
        value = json.loads(raw)
        located = await native_source(owner, award)
        async with native_custody(owner, located) as custody:
            async with native_authority(owner, custody, value, canonical_json_hash(value), exception=False) as row:
                try:
                    await insert_native(owner, row, exception=False)
                except IntegrityError as exc:
                    observed.append(integrity_constraint_name(exc))
                    raise
                raise FulfillmentEvidenceUnavailable("native isolation probe rollback")
    before = await evidence_rows(source)
    app.dependency_overrides[get_db_session] = session_dependency
    try:
        with monkeypatch.context() as patch:
            patch.setattr(FulfillmentEvidenceService, "report", probe)
            response = await source.client.post(
                f"/api/v1/compensation/awards/{body['award_id']}/fulfillment-reports", json=body,
                headers=source.headers | {"Idempotency-Key": body["external_event_id"]})
        assert response.status_code == 503 and observed == ["fulfillment_evidence_read_committed"], (response.text, observed)
        assert await evidence_rows(source) == before
    finally:
        app.dependency_overrides.pop(get_db_session)
        await engine.dispose()


async def test_native_body_guard_removal_exposes_partial_report_only_until_rollback(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    body = report_for(source.obligation)
    body["fulfilled_quantity"] = "0.01" if source.obligation["quantity"] != "0.01" else "0.02"
    signature = "public.compensation_fulfillment_report_valid(jsonb,jsonb,timestamp with time zone)"
    async with source.factory() as session:
        original = await session.scalar(text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))"), {"name": signature})
    before, admitted = await evidence_rows(source), []
    async def probe(owner, award, event, raw):
        value = json.loads(raw)
        located = await native_source(owner, award)
        async with native_custody(owner, located) as custody:
            async with native_authority(owner, custody, value, canonical_json_hash(value), exception=False) as row:
                await owner._session.execute(text("""CREATE OR REPLACE FUNCTION
                    public.compensation_fulfillment_report_valid(body jsonb,obligation jsonb,received_at timestamptz)
                    RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp
                    AS $$ SELECT true $$"""))
                stored = await insert_native(owner, row, exception=False)
                admitted.append(stored)
                raise FulfillmentEvidenceUnavailable("rollback native body guard mutation")
    with monkeypatch.context() as patch:
        patch.setattr(FulfillmentEvidenceService, "report", probe)
        response = await source.client.post(
            f"/api/v1/compensation/awards/{body['award_id']}/fulfillment-reports", json=body,
            headers=source.headers | {"Idempotency-Key": body["external_event_id"]})
    assert response.status_code == 503 and len(admitted) == 1, response.text
    assert await evidence_rows(source) == before
    async with source.factory() as session:
        assert await session.scalar(text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))"), {"name": signature}) == original
        assert await session.scalar(text("SELECT public.compensation_fulfillment_report_valid("
            "CAST(:body AS jsonb),CAST(:obligation AS jsonb),:received_at)"),
            {"body": json.dumps(body), "obligation": json.dumps(source.obligation),
             "received_at": admitted[0].received_at}) is False


async def test_native_clock_is_assigned_after_wait_and_bounds_use_it(fulfillment_api_source, isolated_database_env, monkeypatch):
    source = fulfillment_api_source
    body = report_for(source.obligation)
    name, stored_rows = f"native-clock-{new_record_id().hex}", []
    async def probe(owner, award, event, raw):
        value = json.loads(raw)
        located = await native_source(owner, award)
        async with native_custody(owner, located) as custody:
            async with native_authority(owner, custody, value, canonical_json_hash(value), exception=False) as row:
                await owner._session.execute(text("SELECT set_config('application_name',:name,true)"), {"name": name})
                stored = await insert_native(owner, row, exception=False)
                stored_rows.append(stored)
                return await native_report_ack(owner, stored)
    async with source.factory() as blocker:
        await blocker.execute(text("SELECT id FROM compensation_fulfillment_roots WHERE id=:id FOR UPDATE"),
            {"id": UUID(source.obligation["fulfillment_root_id"])})
        holder = await blocker.scalar(text("SELECT pg_backend_pid()"))
        with monkeypatch.context() as patch:
            patch.setattr(FulfillmentEvidenceService, "report", probe)
            pending = asyncio.create_task(source.client.post(
                f"/api/v1/compensation/awards/{body['award_id']}/fulfillment-reports", json=body,
                headers=source.headers | {"Idempotency-Key": body["external_event_id"]}))
            try:
                await asyncio.wait_for(wait_for_named_database_lock(isolated_database_env, name,
                    expected_blocker_pid=holder), 30)
                assert not pending.done()
                async with source.factory() as observer:
                    before_release = await observer.scalar(text("SELECT clock_timestamp()"))
                await blocker.rollback()
                response = await asyncio.wait_for(pending, 30)
            finally:
                await blocker.rollback()
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    assert response.status_code == 201 and len(stored_rows) == 1, response.text
    received = stored_rows[0].received_at
    assert received >= before_release and received.year != 2000
    assert stored_rows[0].evidence_ordinal == 1
    async with source.factory() as session:
        for delta, expected in ((timedelta(seconds=300), True),
                                (timedelta(seconds=300, microseconds=1), False)):
            boundary = body | {"reported_at": (received + delta).isoformat(timespec="microseconds").replace("+00:00", "Z")}
            assert await session.scalar(text("SELECT public.compensation_fulfillment_report_valid("
                "CAST(:body AS jsonb),CAST(:obligation AS jsonb),:received_at)"),
                {"body": json.dumps(boundary), "obligation": json.dumps(source.obligation),
                 "received_at": received}) is expected
    before_replay = await evidence_rows(source)
    replay = await source.client.post(
        f"/api/v1/compensation/awards/{body['award_id']}/fulfillment-reports", json=body,
        headers=source.headers | {"Idempotency-Key": body["external_event_id"]})
    assert replay.status_code == 200 and replay.json() == response.json() | {"replay": True}, replay.text
    assert await evidence_rows(source) == before_replay


async def test_rr_native_guard_removal_exposes_cross_table_collision(fulfillment_api_source, isolated_database_env, monkeypatch):
    source = fulfillment_api_source
    fulfilled = report_for(source.obligation)
    prefix = f"/api/v1/compensation/awards/{fulfilled['award_id']}"
    seeded = await source.client.post(prefix + "/fulfillment-reports", json=fulfilled,
        headers=source.headers | {"Idempotency-Key": fulfilled["external_event_id"]})
    assert seeded.status_code == 201, seeded.text
    failure = report_for(source.obligation) | {"reported_status": "failed", "fulfilled_quantity": None,
        "fulfilled_at": None, "external_reference": None, "failure_code": "PROVIDER_TIMEOUT"}
    incident = incident_for(fulfilled)
    signature = "public.guard_compensation_fulfillment_evidence()"
    async with source.factory() as session:
        original = await session.scalar(text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))"), {"name": signature})
    start = original.index(" IF current_setting('transaction_isolation')")
    end = original.index(" PERFORM pg_catalog.pg_export_snapshot();", start)
    assert original[start:end].count("fulfillment_evidence_read_committed") == 1
    mutated = original[:start] + original[end:]
    assert "fulfillment_evidence_read_committed" not in mutated
    pinned, peer_held, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    rr_pid, collided, failures = asyncio.get_running_loop().create_future(), [], []
    original_flush, app_rc_guard = FulfillmentEvidenceService._flush_evidence, FulfillmentEvidenceService._require_transaction
    async def peer_flush(owner):
        await original_flush(owner)
        peer_held.set()
        await release.wait()
    async def probe(owner, award, event, raw):
        try:
            value = json.loads(raw)
            located = await native_source(owner, award)  # Pin RR before the peer append.
            rr_pid.set_result(await owner._session.scalar(text("SELECT pg_backend_pid()")))
            await owner._session.execute(text(mutated))
            pinned.set()
            await peer_held.wait()
            async with native_custody(owner, located) as custody:
                async with native_authority(owner, custody, value, canonical_json_hash(value), exception=False) as row:
                    collided.append(await insert_native(owner, row, exception=False))
                    raise FulfillmentEvidenceUnavailable("rollback stale-snapshot guard mutation")
        except FulfillmentEvidenceUnavailable:
            raise
        except Exception as exc:
            failures.append(exc)
            raise
    engine = create_async_engine(isolated_database_env, poolclass=NullPool, isolation_level="REPEATABLE READ")
    app, tasks = source.client._transport.app, []
    async def sessions(request: Request):
        factory = (lambda: AsyncSession(engine, expire_on_commit=False)) if request.headers.get("X-Proof-Isolation") == "rr" else source.factory
        async with factory() as session:
            yield session
    app.dependency_overrides[get_db_session] = sessions
    try:
        with monkeypatch.context() as patch:
            patch.setattr(FulfillmentEvidenceService, "report", probe)
            patch.setattr(FulfillmentEvidenceService, "_flush_evidence", peer_flush)
            try:
                tasks.append(asyncio.create_task(source.client.post(prefix + "/fulfillment-reports", json=failure,
                    headers=source.headers | {"Idempotency-Key": failure["external_event_id"], "X-Proof-Isolation": "rr"})))
                await asyncio.wait_for(pinned.wait(), 30)
                tasks.append(asyncio.create_task(source.client.post(prefix + "/fulfillment-exceptions", json=incident,
                    headers=source.headers | {"Idempotency-Key": incident["exception_event_id"]})))
                await asyncio.wait_for(peer_held.wait(), 30)
                await observe_advisory_wait(source.factory, await rr_pid, tasks[0])
                release.set()
                results = await asyncio.wait_for(asyncio.gather(*tasks), 30)
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if failures:
                    raise failures[0]
        assert results[0].status_code == 503 and results[1].status_code == 201, [r.text for r in results]
        receipts, exceptions, decisions = await evidence_rows(source)
        assert len(receipts) == len(exceptions) == len(collided) == 1
        # This read uses an independent committed RC connection, never RR's snapshot.
        assert collided[0].evidence_ordinal == exceptions[0]["evidence_ordinal"] == 2
        assert len(decisions) == 2  # Original success and peer; mutant allow rolled back.
        assert FulfillmentEvidenceService._require_transaction is app_rc_guard
        ordinary = await source.client.post(prefix + "/fulfillment-reports", json=failure,
            headers=source.headers | {"Idempotency-Key": failure["external_event_id"], "X-Proof-Isolation": "rr"})
        assert ordinary.status_code == 503, ordinary.text
        assert await evidence_rows(source) == (receipts, exceptions, decisions)
        async with source.factory() as session:
            assert await session.scalar(text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))"), {"name": signature}) == original
    finally:
        app.dependency_overrides.pop(get_db_session)
        await engine.dispose()
