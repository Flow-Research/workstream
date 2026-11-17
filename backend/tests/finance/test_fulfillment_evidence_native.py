"""Independent installed guards with real request authority and direct SQL."""

import json
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.db.errors import integrity_constraint_name
from app.db.session import get_db_session
from app.modules.compensation.api.fulfillment_evidence import FulfillmentEvidenceUnavailable
from app.modules.compensation.fulfillment.evidence_service import FulfillmentEvidenceService
from tests.finance.fulfillment_native_support import (
    insert_native, native_authority, native_custody, native_source,
)
from tests.finance.test_fulfillment_evidence_public_api import evidence_rows, report_for


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
