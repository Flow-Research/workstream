"""Signed concurrent callbacks must use actual current database custody."""

import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.compensation.fulfillment.evidence_service import FulfillmentEvidenceService
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.finance.test_fulfillment_evidence_public_api import evidence_rows, report_for
from tests.reviews.lifecycle.test_fence import observe_advisory_wait
from tests.reviews.lifecycle.transition_support import command_for, controller


async def earning_facts(source):
    async with source.factory() as session:
        return (await session.execute(text("""SELECT
            (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM contribution_records c),
            (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM compensation_awards a),
            (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM compensation_fulfillment_roots r)
        """))).one()


@pytest.mark.parametrize("first_family", ("report", "exception"))
async def test_rc_late_failure_and_exception_serialize_ordinals(fulfillment_api_source, monkeypatch, first_family):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    fulfilled = report_for(source.obligation)
    response = await source.client.post(prefix + "/fulfillment-reports", json=fulfilled,
        headers=source.headers | {"Idempotency-Key": fulfilled["external_event_id"]})
    assert response.status_code == 201, response.text
    before = await earning_facts(source)
    failure = report_for(source.obligation) | {
        "reported_status": "failed", "fulfilled_quantity": None, "fulfilled_at": None,
        "external_reference": None, "failure_code": "PROVIDER_TIMEOUT",
    }
    incident = {key: failure[key] for key in (
        "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
        "adapter_binding_id", "correlation_id", "contract_version", "route_key",
    )} | {"exception_event_id": failure["external_event_id"],
        "original_fulfillment_event_id": fulfilled["external_event_id"],
        "kind": "provider_status_conflict", "observed_at": fulfilled["reported_at"],
        "reported_at": failure["reported_at"]}
    requests = {"report": ("/fulfillment-reports", failure, "external_event_id"),
                "exception": ("/fulfillment-exceptions", incident, "exception_event_id")}
    # Each table has its own binding/event identity; shared values still cannot
    # collapse two distinct evidence types or assign the same root ordinal.
    locked, release, located = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids, flushed = [], []
    original_locate = FulfillmentEvidenceService._locate
    original_flush = FulfillmentEvidenceService._flush_evidence

    async def locate(owner, award_id):
        result = await original_locate(owner, award_id)
        pids.append(await owner._session.scalar(text("SELECT pg_backend_pid()")))
        if len(pids) == 2:
            located.set()
        return result

    async def flush(owner):
        await original_flush(owner)
        flushed.append(await owner._session.scalar(text("SELECT pg_backend_pid()")))
        if len(flushed) == 1:
            locked.set()
            await release.wait()

    async def send(family):
        suffix, body, key = requests[family]
        return await source.client.post(prefix + suffix, json=body,
            headers=source.headers | {"Idempotency-Key": body[key]})

    pending = []
    with monkeypatch.context() as patch:
        patch.setattr(FulfillmentEvidenceService, "_locate", locate)
        patch.setattr(FulfillmentEvidenceService, "_flush_evidence", flush)
        try:
            pending.append(asyncio.create_task(send(first_family)))
            await asyncio.wait_for(locked.wait(), 30)
            second = "exception" if first_family == "report" else "report"
            pending.append(asyncio.create_task(send(second)))
            await asyncio.wait_for(located.wait(), 30)
            assert pids[0] != pids[1]
            await observe_advisory_wait(source.factory, pids[1], pending[1])
            async with source.factory() as observer:
                before_release = await observer.scalar(text("SELECT clock_timestamp()"))
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*pending), 30)
        finally:
            release.set()
            for running in pending:
                if not running.done():
                    running.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    receipts, exceptions, _ = await evidence_rows(source)
    assert len(receipts) == 2 and len(exceptions) == 1
    failed, exception = receipts[1], exceptions[0]
    assert [receipts[0]["evidence_ordinal"], *sorted((failed["evidence_ordinal"], exception["evidence_ordinal"]))] == [1, 2, 3]
    first, last = (failed, exception) if first_family == "report" else (exception, failed)
    assert (first["evidence_ordinal"], last["evidence_ordinal"]) == (2, 3)
    assert datetime.fromisoformat(last["received_at"]) >= before_release
    observed = await source.client.get(prefix + "/finance-evidence", headers=source.headers)
    assert observed.status_code == 200, observed.text
    status = observed.json()["status"]
    assert status["fulfillment_status"] == "fulfilled" and status["fulfillment_attention_required"] is True
    assert status["latest_receipt_id"] == failed["id"]
    assert status["latest_exception_id"] == exception["id"]
    assert status["last_failure_code"] == "PROVIDER_TIMEOUT"
    assert datetime.fromisoformat(status["updated_at"]) == datetime.fromisoformat(last["received_at"])
    before_replay = await evidence_rows(source)
    for family in ("report", "exception"):
        replay = await send(family)
        assert replay.status_code == 200 and replay.json()["replay"] is True, replay.text
    assert await evidence_rows(source) == before_replay
    assert await earning_facts(source) == before


async def bound_service_link(source):
    async with source.factory() as session:
        return await session.scalar(text("SELECT l.id FROM actor_identity_links l "
            "JOIN project_compensation_adapter_bindings b ON b.adapter_actor_id=l.actor_profile_id "
            "WHERE b.id=:binding AND l.issuer=:issuer"),
            {"binding": UUID(source.obligation["adapter_binding_id"]), "issuer": source.access.signed.issuer})


async def authority_race(source, database_url, monkeypatch, *, first, lifecycle=None):
    """Hold genuine owner custody and observe each independent wait before release."""
    link, report = await bound_service_link(source), report_for(source.obligation)
    held, release = asyncio.Event(), asyncio.Event()
    names = {role: f"fulfillment-{role}-{new_record_id().hex}" for role in ("callback", "revocation", "lifecycle")}
    holder, acquisitions, hook_failures, callback_sessions = [], [], [], []
    original_target = AdminAuthorizationRepository.lock_identity_link_lifecycle_target
    original_locate, original_flush = FulfillmentEvidenceService._locate, FulfillmentEvidenceService._flush_evidence
    original_fence = PostgresJointLifecycleMutationFence.lock_controller
    async def fence(owner):
        if any(owner._session is session for session in callback_sessions):
            acquisitions.append(True)
        return await original_fence(owner)
    async def locate(owner, award):
        try:
            result = await original_locate(owner, award)
            callback_sessions.append(owner._session)
            await owner._session.execute(text("SELECT set_config('application_name',:name,true)"), {"name": names["callback"]})
            return result
        except Exception as exc:
            hook_failures.append(exc)
            raise
    async def flush(owner):
        await original_flush(owner)
        if first == "callback":
            holder.append(await owner._session.scalar(text("SELECT pg_backend_pid()")))
            held.set()
            await release.wait()
    async def target(repository, identity_link_id):
        try:
            await repository._session.execute(text("SELECT set_config('application_name',:name,true)"), {"name": names["revocation"]})
            result = await original_target(repository, identity_link_id)
            if first == "revocation" and not holder:
                holder.append(await repository._session.scalar(text("SELECT pg_backend_pid()")))
                held.set()
                await release.wait()
            return result
        except Exception as exc:
            hook_failures.append(exc)
            raise
    async def callback():
        return await source.client.post(
            f"/api/v1/compensation/awards/{source.obligation['award_id']}/fulfillment-reports",
            json=report, headers=source.headers | {"Idempotency-Key": report["external_event_id"]})
    async def revoke():
        return await source.client.post(f"/api/v1/actor-identity-links/{link}/revoke",
            headers=source.access.admin.headers | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Verify concurrent fulfillment authority"})
    transition_pid = asyncio.get_running_loop().create_future()
    async def change_phase():
        async with source.factory() as session, session.begin():
            transition_pid.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
            return await controller(session, lifecycle).transition(lifecycle)
    tasks, roles = [], [first, "revocation" if first == "callback" else "callback"]
    operations = {"callback": callback, "revocation": revoke}
    with monkeypatch.context() as patch:
        patch.setattr(AdminAuthorizationRepository, "lock_identity_link_lifecycle_target", target)
        patch.setattr(FulfillmentEvidenceService, "_locate", locate)
        patch.setattr(FulfillmentEvidenceService, "_flush_evidence", flush)
        patch.setattr(PostgresJointLifecycleMutationFence, "lock_controller", fence)
        try:
            tasks.append(asyncio.create_task(operations[first](), name=names[first]))
            await asyncio.wait_for(held.wait(), 30)
            tasks.append(asyncio.create_task(operations[roles[1]](), name=names[roles[1]]))
            await asyncio.wait_for(wait_for_named_database_lock(database_url, names[roles[1]],
                expected_blocker_pid=holder[0]), 30)
            if lifecycle is not None:
                assert first == "revocation"
                roles.append("lifecycle")
                tasks.append(asyncio.create_task(change_phase(), name=names["lifecycle"]))
                pid = await asyncio.wait_for(transition_pid, 30)
                await observe_advisory_wait(source.factory, pid, tasks[-1])
                assert pid != holder[0]
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), 30)
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if hook_failures:
                raise hook_failures[0]
    assert len(acquisitions) == 1, "callback reacquired REV instead of retaining its held fence"
    return dict(zip(roles, results)), report, link


@pytest.mark.parametrize("first", ("callback", "revocation"))
async def test_revocation_and_callback_lock_order(fulfillment_api_source, isolated_database_env, monkeypatch, first):
    source = fulfillment_api_source
    before = await earning_facts(source)
    results, report, _ = await authority_race(source, isolated_database_env, monkeypatch, first=first)
    assert results["revocation"].status_code == 200, results["revocation"].text
    assert results["callback"].status_code == (201 if first == "callback" else 404), results["callback"].text
    receipts, exceptions, decisions = await evidence_rows(source)
    assert exceptions == [] and len(decisions) == 1
    if first == "callback":
        assert len(receipts) == 1 and receipts[0]["report_body"] == report
        assert decisions[0]["event_type"] == "SensitiveAuthorizationAllowed"
        assert receipts[0]["authorization_decision_id"] == decisions[0]["id"]
    else:
        assert receipts == []
        assert decisions[0]["event_type"] == "SensitiveAuthorizationDenied"
        assert decisions[0]["denial_code"] == "identity_link_revoked"
    assert await earning_facts(source) == before


async def test_three_party_revocation_callback_lifecycle_has_no_cycle(fulfillment_api_source, isolated_database_env, monkeypatch):
    source = fulfillment_api_source
    command = await command_for(source.access.target.id, "draining")
    before = await earning_facts(source)
    results, report, link = await authority_race(source, isolated_database_env, monkeypatch,
        first="revocation", lifecycle=command)
    assert results["revocation"].status_code == 200, results["revocation"].text
    assert results["callback"].status_code == 404, results["callback"].text
    assert results["lifecycle"].phase == "draining" and results["lifecycle"].generation == 3
    assert await earning_facts(source) == before
    receipts, exceptions, decisions = await evidence_rows(source)
    assert receipts == [] and exceptions == [] and len(decisions) == 1
    assert decisions[0]["event_type"] == "SensitiveAuthorizationDenied"
    restored = await source.client.post(f"/api/v1/actor-identity-links/{link}/reactivate",
        headers=source.access.admin.headers | {"Idempotency-Key": str(new_record_id())},
        json={"reason": "Restore the original reporter after the lock-order proof"})
    assert restored.status_code == 200, restored.text
    recorded = await source.client.post(
        f"/api/v1/compensation/awards/{source.obligation['award_id']}/fulfillment-reports",
        json=report, headers=source.headers | {"Idempotency-Key": report["external_event_id"]})
    assert recorded.status_code == 201, recorded.text
    receipts, _, _ = await evidence_rows(source)
    assert len(receipts) == 1 and receipts[0]["recording_lifecycle_generation"] == 3
    assert await earning_facts(source) == before
