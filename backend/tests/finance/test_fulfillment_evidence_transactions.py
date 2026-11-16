"""Real flushed evidence must survive only with its exact committed authority."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps.compensation_fulfillment import FulfillmentEvidenceRequest
from app.core.identifiers import new_record_id
from app.db.session import get_db_session
from app.core.api_controls import StructuredHTTPException
from app.modules.authorization.fulfillment_evidence_authorization import FulfillmentEvidenceAuthorizationAdapter
from app.modules.authorization.runtime import AuthorizationDenied
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentEvidenceDenied, FulfillmentExceptionAcknowledgement, FulfillmentReportAcknowledgement,
)
from tests.finance.test_fulfillment_evidence_public_api import evidence_rows, report_for


async def test_response_failure_rolls_back_flushed_evidence_and_allow(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    fulfilled = report_for(source.obligation)
    accepted = await source.client.post(prefix + "/fulfillment-reports", json=fulfilled,
        headers=source.headers | {"Idempotency-Key": fulfilled["external_event_id"]})
    assert accepted.status_code == 201, accepted.text
    original_finish = FulfillmentEvidenceRequest.finish
    for family, model, table in (
        ("report", FulfillmentReportAcknowledgement, "compensation_fulfillment_receipts"),
        ("exception", FulfillmentExceptionAcknowledgement, "compensation_fulfillment_exceptions"),
    ):
        for failure in ("serialization", "detached_validation", "award", "event", "root", "digest"):
            before = await evidence_rows(source)
            body = report_for(source.obligation)
            if family == "report":
                body.update(reported_status="failed", fulfilled_quantity=None, fulfilled_at=None,
                            external_reference=None, failure_code="PROVIDER_UNAVAILABLE")
                event_key, suffix = "external_event_id", "/fulfillment-reports"
            else:
                body = {key: body[key] for key in (
                    "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
                    "adapter_binding_id", "correlation_id", "contract_version", "route_key",
                )} | {"exception_event_id": str(new_record_id()),
                    "original_fulfillment_event_id": fulfilled["external_event_id"],
                    "kind": "provider_status_conflict", "observed_at": fulfilled["reported_at"],
                    "reported_at": fulfilled["reported_at"]}
                event_key, suffix = "exception_event_id", "/fulfillment-exceptions"
            flushed = []

            async def failing_finish(owner, value, response_model, **kwargs):
                row_id = value.receipt_id if family == "report" else value.exception_id
                row = (await owner.session.execute(text(
                    f"SELECT authorization_decision_id FROM public.{table} WHERE id=:id"
                ), {"id": row_id})).one()
                assert await owner.session.scalar(text(
                    "SELECT count(*) FROM public.audit_events WHERE id=:id "
                    "AND event_type='SensitiveAuthorizationAllowed'"
                ), {"id": row.authorization_decision_id}) == 1
                flushed.append(row_id)
                with monkeypatch.context() as patch:
                    if failure in {"serialization", "detached_validation"}:
                        def fail(*args, **kwargs):
                            raise ValueError("controlled precommit response failure")
                        method = "model_dump_json" if failure == "serialization" else "model_validate_json"
                        patch.setattr(model, method, fail)
                    else:
                        field = {"award": "award_id", "event": event_key,
                                 "root": "fulfillment_root_id",
                                 "digest": "report_digest" if family == "report" else "exception_digest"}[failure]
                        value = value.model_copy(update={field: "sha256:" + "0" * 64
                            if failure == "digest" else new_record_id()})
                    return await original_finish(owner, value, response_model, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(FulfillmentEvidenceRequest, "finish", failing_finish)
                response = await source.client.post(prefix + suffix, json=body,
                    headers=source.headers | {"Idempotency-Key": body[event_key]})
            assert len(flushed) == 1, (family, failure, response.text)
            assert response.status_code == (500 if failure in {"serialization", "detached_validation"} else 503)
            assert await evidence_rows(source) == before, (family, failure)


async def test_lookup_miss_commits_only_source_read_allow(fulfillment_api_source):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    event = new_record_id()
    response = await source.client.get(prefix + f"/fulfillment-reports/{event}", headers=source.headers)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "fulfillment_evidence_not_found"
    receipts, exceptions, decisions = await evidence_rows(source)
    assert receipts == [] and exceptions == [] and len(decisions) == 1
    decision = decisions[0]
    assert decision["event_type"] == "SensitiveAuthorizationAllowed"
    assert decision["action_id"] == "compensation.fulfillment.source.read"
    assert decision["resource_type"] == "compensation_fulfillment_report_lookup"
    assert UUID(decision["resource_id"]) == event
    assert decision["project_id"] == source.obligation["project_id"]
    assert decision["after_facts"]["resource_context_digest"].startswith("sha256:")


async def test_genuine_denial_restages_only_issuing_pending_decision(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    async with source.factory() as session:
        actor = await session.scalar(text("SELECT adapter_actor_id FROM project_compensation_adapter_bindings "
            "WHERE id=:id"), {"id": UUID(source.obligation["adapter_binding_id"])})
        link = await session.scalar(text("SELECT id FROM actor_identity_links "
            "WHERE actor_profile_id=:actor AND issuer=:issuer"),
            {"actor": actor, "issuer": source.access.signed.issuer})
    assert actor is not None and link is not None
    restaged = []
    original_restage = FulfillmentEvidenceAuthorizationAdapter.restage_denial

    async def inspect_restage(owner, error):
        assert not owner._session.in_transaction()
        assert isinstance(error.__cause__, AuthorizationDenied)
        decision = error.__cause__.decision
        assert owner._kernel._pending_denial is decision
        foreign = FulfillmentEvidenceAuthorizationAdapter(owner._session, owner._context)
        with pytest.raises(TypeError, match="invalid authorization denial evidence"):
            await original_restage(foreign, error)
        copied = FulfillmentEvidenceDenied("copied decision")
        copied.__cause__ = AuthorizationDenied(decision.model_copy())
        with pytest.raises(TypeError, match="invalid authorization denial evidence"):
            await original_restage(owner, copied)
        assert owner._kernel._pending_denial is decision
        assert await original_restage(owner, error) is True
        with pytest.raises(TypeError, match="invalid authorization denial evidence"):
            await original_restage(owner, error)
        restaged.append(decision)
        return True

    monkeypatch.setattr(FulfillmentEvidenceAuthorizationAdapter, "restage_denial", inspect_restage)
    async def transition(path):
        response = await source.client.post("/api/v1/" + path,
            headers=source.access.admin.headers | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Verify exact fulfillment denial custody"})
        assert response.status_code == 200, response.text

    for mutation, expected_code, restore in (
        (f"actors/{actor}/suspend", "actor_suspended", f"actors/{actor}/reactivate"),
        (f"actor-identity-links/{link}/revoke", "identity_link_revoked", f"actor-identity-links/{link}/reactivate"),
    ):
        await transition(mutation)
        report = report_for(source.obligation)
        prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}/fulfillment-reports"
        headers = source.headers | {"Idempotency-Key": report["external_event_id"]}
        denied = await source.client.post(prefix, json=report, headers=headers)
        assert denied.status_code == 404, denied.text
        receipts, exceptions, decisions = await evidence_rows(source)
        assert receipts == [] and exceptions == []
        assert len(decisions) == len(restaged)
        actual = next(d for d in decisions if UUID(d["id"]) == restaged[-1].decision_id)
        assert actual["event_type"] == "SensitiveAuthorizationDenied"
        assert actual["denial_code"] == expected_code
        assert UUID(actual["actor_id"]) == UUID(str(actor))
        assert UUID(actual["resource_id"]) == UUID(report["external_event_id"])
        await transition(restore)
    accepted = await source.client.post(prefix, json=report, headers=headers)
    assert accepted.status_code == 201, accepted.text
    receipts, exceptions, decisions = await evidence_rows(source)
    assert len(receipts) == 1 and exceptions == []
    assert sum(d["event_type"] == "SensitiveAuthorizationDenied" for d in decisions) == 2
    assert sum(d["event_type"] == "SensitiveAuthorizationAllowed" for d in decisions) == 1


async def test_pre_authority_failures_do_not_prepare_or_restage(fulfillment_api_source, isolated_database_env, monkeypatch):
    source = fulfillment_api_source
    app = source.client._transport.app
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}/fulfillment-reports"
    report = report_for(source.obligation)
    headers = source.headers | {"Idempotency-Key": report["external_event_id"]}
    def forbidden(*args, **kwargs):
        raise AssertionError("pre-authority failure reached preparation or denial restage")
    monkeypatch.setattr(FulfillmentEvidenceAuthorizationAdapter, "prepare", forbidden)
    monkeypatch.setattr(FulfillmentEvidenceAuthorizationAdapter, "restage_denial", forbidden)
    before = await evidence_rows(source)
    for isolation in ("REPEATABLE READ", "SERIALIZABLE"):
        engine = create_async_engine(isolated_database_env, poolclass=NullPool, isolation_level=isolation)
        async def isolated_session():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                yield session
        app.dependency_overrides[get_db_session] = isolated_session
        try:
            response = await source.client.post(prefix, headers=headers, json=report)
            assert response.status_code == 503, response.text
            assert await evidence_rows(source) == before
        finally:
            app.dependency_overrides.pop(get_db_session)
            await engine.dispose()
    from app.api.deps import compensation_fulfillment as dependency
    async def unavailable(*args, **kwargs):
        raise StructuredHTTPException(status_code=503, detail="registry unavailable",
            error_code="actor_registry_unavailable", error_message="Actor registry unavailable", retryable=True)
    monkeypatch.setattr(dependency, "resolve_authorization_actor", unavailable)
    response = await source.client.post(prefix, headers=headers, json=report)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "actor_registry_unavailable"
    assert await evidence_rows(source) == before
