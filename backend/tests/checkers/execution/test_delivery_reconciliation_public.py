"""Public PostgreSQL proof for one-shot uncertain post-submit delivery recovery."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from app.adapters import artifacts as artifact_adapters
from app.adapters.checkers.external_service import RemoteTlsExternalCheckerAdapter
from app.adapters.outbox import production_outbox_delivery
from app.adapters.tasks import evaluation_completion_handler
from app.core.identifiers import new_record_id
from app.modules.outbox.api import FinalizationCause, HandlerOutcome
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryChildPayload,
    PostSubmitDeliveryOperationUnavailable,
)
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)
from tests.authorization.admin_access.support import create_project
from tests.post_submit_materialization_helpers import material_fixture
from tests.reviews.lifecycle.fixtures import (
    live_acceptance_lifecycle as live_acceptance_lifecycle,
)
from tests.tasks.evaluation_delivery.support import delivery_fixture, invoked, outcome, state
from tests.checkers.execution.support import ControlledSelectedExecution
from tests.checkers.external.test_remote_node import fixture_placement, read_fixture_native_request, remote_adapter_endpoint
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
)


def _paths(project_id, event_id=None):
    collection = f"/api/v1/operations/projects/{project_id}/post-submit-deliveries"
    return collection, (
        f"{collection}/{event_id}/reconcile" if event_id is not None else None
    )


async def _project_facts(factory, project_id):
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM public.task_post_submit_routing_manifests
                       WHERE project_id=:project) AS manifests,
                      (SELECT count(*) FROM public.final_acceptances
                       WHERE project_id=:project) AS acceptances,
                      (SELECT count(*) FROM public.contribution_records
                       WHERE project_id=:project) AS contributions,
                      (SELECT count(*) FROM public.compensation_awards
                       WHERE project_id=:project) AS awards,
                      (SELECT count(*) FROM public.audit_events
                       WHERE project_id=:project
                         AND action_id='task.post_submit.route') AS routing_audits,
                      (SELECT count(*) FROM public.outbox_events
                       WHERE project_id=:project
                         AND event_type='TaskPostSubmitRouted') AS routing_notices
                    """
                ),
                {"project": str(project_id)},
            )
        ).one()
        return tuple(row)


async def _retained_effect_rows(factory, project_id):
    """Snapshot every retained routing/acceptance consequence, not only counts."""
    selections = (
        ("task_post_submit_routing_manifests", "project_id=:project"),
        ("final_acceptances", "project_id=:project"),
        ("contribution_records", "project_id=:project"),
        ("compensation_awards", "project_id=:project"),
        (
            "audit_events",
            "project_id=:project AND action_id='task.post_submit.route'",
        ),
        (
            "outbox_events",
            "project_id=:project AND event_type='TaskPostSubmitRouted'",
        ),
    )
    async with factory() as session:
        rows = []
        for table, predicate in selections:
            rows.append(
                await session.scalar(
                text(
                    "SELECT COALESCE("
                    "jsonb_agg(to_jsonb(row) ORDER BY to_jsonb(row)::text)::text, "
                    "'[]') FROM (SELECT * FROM public."
                    + table
                    + " WHERE "
                    + predicate
                    + ") AS row"
                ),
                {"project": str(project_id)},
            )
            )
        return tuple(rows)


async def _delivery_rows(factory, original_id, child_id=None):
    async with factory() as session:
        original = (
            await session.execute(
                text(
                    """
                    SELECT to_jsonb(e)::text,
                           (SELECT jsonb_agg(to_jsonb(a) ORDER BY a.claim_generation)::text
                            FROM public.outbox_delivery_attempts a
                            WHERE a.event_id=e.event_id)
                    FROM public.outbox_events e WHERE e.event_id=:event_id
                    """
                ),
                {"event_id": original_id},
            )
        ).one()
        child = None
        if child_id is not None:
            child = (
                await session.execute(
                    text(
                        """
                        SELECT delivery_state,last_error_code,causation_event_id,
                               payload_digest,payload
                        FROM public.outbox_events WHERE event_id=:event_id
                        """
                    ),
                    {"event_id": child_id},
                )
            ).one()
        return tuple(original), tuple(child) if child is not None else None


async def _lock_delivery_read_authority_nowait(
    factory, *, actor_id, grant_id, project_id,
):
    """Prove detached source waits retain no AUTH or project row lock."""
    async with factory.begin() as session:
        for statement, parameters in (
            ("SELECT id FROM public.actor_profiles WHERE id=:id FOR UPDATE NOWAIT", {"id": str(actor_id)}),
            ("SELECT id FROM public.actor_identity_links WHERE actor_profile_id=:id FOR UPDATE NOWAIT", {"id": str(actor_id)}),
            ("SELECT id FROM public.admin_role_grants WHERE id=:id FOR UPDATE NOWAIT", {"id": str(grant_id)}),
            ("SELECT id FROM public.projects WHERE id=:id FOR UPDATE NOWAIT", {"id": str(project_id)}),
        ):
            assert await session.scalar(text(statement), parameters) is not None


async def _discover_one(admin_access, project_id, *, classification):
    collection, _ = _paths(project_id)
    response = await admin_access.signed.client.get(
        collection, headers=admin_access.target.headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_id"] == str(project_id)
    assert body["next_cursor"] is None
    assert len(body["items"]) == 1
    source = body["items"][0]
    assert set(source) == {
        "project_id",
        "event_id",
        "event_type",
        "event_version",
        "aggregate_id",
        "evaluation_request_id",
        "checker_run_id",
        "evaluation_generation",
        "claim_generation",
        "payload_digest",
        "finalized_at",
        "delivery_state",
        "error_code",
        "classification",
        "reconciliation_event_id",
        "reconciliation_state",
    }
    assert source["classification"] == classification
    assert source["delivery_state"] == "dead_letter"
    assert source["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
    assert "outcome_json" not in response.text
    assert '"payload":' not in response.text
    return source


async def _reconcile(
    admin_access,
    project_id,
    event_id,
    request_key,
    *,
    actor=None,
    reason="Reconcile one exact uncertain post-submit delivery",
):
    _, command = _paths(project_id, event_id)
    assert command is not None
    caller = actor or admin_access.target
    return await admin_access.signed.client.post(
        command,
        headers=caller.headers | {"Idempotency-Key": str(request_key)},
        json={"reason": reason},
    )


@pytest.mark.asyncio
async def test_public_operator_recovers_rolled_back_acceptance_once(
    tmp_path, auth_database_env, live_acceptance_lifecycle,
) -> None:
    """An UNKNOWN completion with rolled-back effects accepts under its live child."""
    admin_access = live_acceptance_lifecycle
    async with authorized_routing_source(
        tmp_path, auth_database_env, human_review_required=False,
        contribution_awards=("project_points",),
    ) as h:
        async with h.factory() as session:
            await session.begin()
            staged = await apply_outcome(session, h, 2)
            assert staged.final_acceptance_id is not None
            await session.rollback()
        assert await _project_facts(h.factory, h.request.project_id) == (0,) * 6
        finalized = await h.completion_delivery.finalize(
            h.envelope.claim, FinalizationCause.UNKNOWN
        )
        assert outcome(finalized)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        original_before, _ = await _delivery_rows(h.factory, h.envelope.claim.event_id)
        await _discover_one(admin_access, h.request.project_id, classification="retry_safe")
        key = new_record_id()
        created = await _reconcile(
            admin_access, h.request.project_id, h.envelope.claim.event_id, key
        )
        assert created.status_code == 201, created.text
        successor = created.json()["successor"]
        assert successor["classification"] == "retry_safe"
        child_id = UUID(successor["event_id"])
        async with h.factory() as observer:
            operator_grant_id = await observer.scalar(text(
                "SELECT id FROM public.admin_role_grants "
                "WHERE target_actor_profile_id=:actor AND role='operator' "
                "AND scope_type='system' AND status='active'"
            ), {"actor": str(admin_access.target.id)})
        assert operator_grant_id is not None
        revoked = await admin_access.signed.revoke(
            admin_access.admin,
            str(operator_grant_id),
            reason="End uncertain delivery reconciliation duty",
        )
        assert revoked.status_code == 200, revoked.text
        delivery = production_outbox_delivery(h.factory)
        delivered = await delivery.deliver(
            child_id, h.request.project_id, "recover-completion"
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged", outcome(delivered)
        assert await _project_facts(h.factory, h.request.project_id) == (1,) * 6
        async with h.factory() as session:
            actual = (await session.execute(text("""
                SELECT a.project_id=:project, a.task_id=:task, a.submission_id=:submission,
                       a.source_review_id IS NULL, c.source_review_id IS NULL,
                       c.contributor_id=s.contributor_id,
                       c.source_final_acceptance_id=a.id,
                       c.source_task_assignment_id=s.task_assignment_id,
                       c.contribution_policy_version_id=s.contribution_policy_version_id,
                       c.artifact_hash=content.sha256,
                       t.status='accepted', s.attempt_status='accepted',
                       m.completion_event_id=:original
                FROM public.final_acceptances a
                JOIN public.contribution_records c ON c.source_final_acceptance_id=a.id
                JOIN public.submissions s ON s.id=a.submission_id
                JOIN public.artifact_contents content ON content.id=s.artifact_content_id
                JOIN public.workstream_tasks t ON t.id=a.task_id
                JOIN public.task_post_submit_routing_manifests m
                  ON m.id=a.source_routing_manifest_id
                WHERE a.project_id=:project
            """), {
                "project": h.request.project_id, "task": h.request.task_id,
                "submission": h.request.submission_id, "original": h.envelope.claim.event_id,
            })).one()
            assert tuple(actual) == (True,) * 13
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
        retained = await _retained_effect_rows(h.factory, h.request.project_id)
        original_after, child = await _delivery_rows(h.factory, h.envelope.claim.event_id, child_id)
        assert original_after == original_before
        assert child[:3] == ("acknowledged", None, h.envelope.claim.event_id)
        await admin_access.signed.grant(admin_access.admin, admin_access.target)
        replay = await _reconcile(admin_access, h.request.project_id, h.envelope.claim.event_id, key)
        assert replay.status_code == 201, replay.text
        assert replay.json()["source"]["classification"] == "retry_safe"
        assert replay.json()["source"]["reconciliation_state"] == "acknowledged"
        assert replay.json()["successor"] == successor
        await delivery.deliver(child_id, h.request.project_id, "duplicate-completion")
        assert await _retained_effect_rows(h.factory, h.request.project_id) == retained
        assert (await _delivery_rows(h.factory, h.envelope.claim.event_id))[0] == original_before


@pytest.mark.asyncio
async def test_public_operator_verifies_committed_request_without_execution(
    tmp_path, auth_database_env, admin_access, monkeypatch,
) -> None:
    """A committed checker result is acknowledged without executing it again."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        await admin_access.signed.grant(admin_access.admin, admin_access.target)
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        assert await prepared.handler(original) is HandlerOutcome.ACKNOWLEDGE
        completed = await state(h)
        assert completed["run"]["status"] == "completed"
        assert completed["events"] == 1
        opens = tuple(h.store.opens)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)
        original_before, _ = await _delivery_rows(h.factory, original.claim.event_id)
        await _discover_one(admin_access, h.request.project_id, classification="committed")
        key = new_record_id()
        created = await _reconcile(admin_access, h.request.project_id, original.claim.event_id, key)
        assert created.status_code == 201, created.text
        successor = created.json()["successor"]
        assert successor["classification"] == "committed"

        async def forbidden_execution(*_args, **_kwargs):
            pytest.fail("committed request recovery must not execute the checker again")

        monkeypatch.setattr(
            "app.modules.checkers.execution.PostSubmissionExecutor.evaluate_post_submission",
            forbidden_execution,
        )
        child_id = UUID(successor["event_id"])
        delivery = production_outbox_delivery(h.factory)
        receipt = await delivery.deliver(child_id, h.request.project_id, "verify-request")
        assert outcome(receipt)["delivery_state"] == "acknowledged", outcome(receipt)
        assert await state(h) == completed
        assert tuple(h.store.opens) == opens
        original_after, child = await _delivery_rows(h.factory, original.claim.event_id, child_id)
        assert original_after == original_before
        assert child[:3] == ("acknowledged", None, original.claim.event_id)
        replay = await _reconcile(admin_access, h.request.project_id, original.claim.event_id, key)
        assert replay.status_code == 201, replay.text
        assert replay.json()["successor"] == successor
        await delivery.deliver(child_id, h.request.project_id, "duplicate-request")
        assert await state(h) == completed


@pytest.mark.asyncio
async def test_public_operator_retries_proven_no_effect_request_once(
    tmp_path,
    auth_database_env,
    monkeypatch,
    admin_access,
) -> None:
    """A queued generation-zero request may run once behind the immutable child."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        operator_grant = await admin_access.signed.grant(
            admin_access.admin, admin_access.target
        )
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        receipt = await prepared.delivery.finalize(
            original.claim, FinalizationCause.UNKNOWN
        )
        assert outcome(receipt)["delivery_state"] == "dead_letter"
        assert outcome(receipt)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        unstarted = await state(h)
        assert unstarted["run"]["status"] == "queued"
        assert unstarted["run"]["worker_lease_generation"] == 0
        assert unstarted["run"]["execute_evidence_id"] is None
        assert not h.store.opens
        original_before, _ = await _delivery_rows(h.factory, original.claim.event_id)

        source = await _discover_one(
            admin_access, h.request.project_id, classification="retry_safe"
        )
        assert source["event_id"] == str(original.claim.event_id)
        assert source["evaluation_request_id"] == str(h.request.evaluation_request_id)
        assert source["checker_run_id"] == str(h.created.evaluation_attempt_id)
        assert source["evaluation_generation"] == 1
        assert source["claim_generation"] == original.claim.claim_generation

        key = new_record_id()
        created = await _reconcile(
            admin_access, h.request.project_id, original.claim.event_id, key
        )
        assert created.status_code == 201, created.text
        result = created.json()
        assert result["source"] == source | {
            "reconciliation_event_id": result["successor"]["event_id"],
            "reconciliation_state": "pending",
        }
        assert result["successor"]["classification"] == "retry_safe"

        replay = await _reconcile(
            admin_access, h.request.project_id, original.claim.event_id, key
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["successor"] == result["successor"]
        conflict = await _reconcile(
            admin_access,
            h.request.project_id,
            original.claim.event_id,
            new_record_id(),
        )
        assert conflict.status_code == 409, conflict.text
        revoked = await admin_access.signed.revoke(
            admin_access.admin,
            operator_grant,
            reason="End uncertain delivery reconciliation duty",
        )
        assert revoked.status_code == 200, revoked.text

        settings = h.settings.model_copy(
            update={
                "external_runner_endpoints": None,
            }
        )
        monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
        monkeypatch.setattr(
            artifact_adapters,
            "worker_post_submission_materialization",
            lambda *, sessions: h.service,
        )
        selected = ControlledSelectedExecution()
        monkeypatch.setattr(
            "app.adapters.checkers.configured_post_submit_external_execution",
            lambda settings, *, sessions: selected,
        )
        child_id = UUID(result["successor"]["event_id"])
        delivered = await production_outbox_delivery(h.factory).deliver(
            child_id, h.request.project_id, "reconcile-request"
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        assert len(selected.requests) == 1
        completed = await state(h)
        assert completed["run"]["status"] == "completed"
        assert completed["events"] == 1

        original_after, child = await _delivery_rows(
            h.factory, original.claim.event_id, child_id
        )
        assert original_after == original_before
        assert child[:3] == ("acknowledged", None, original.claim.event_id)
        replay_grant = await admin_access.signed.grant(
            admin_access.admin, admin_access.target
        )
        acknowledged_replay = await _reconcile(
            admin_access, h.request.project_id, original.claim.event_id, key
        )
        assert acknowledged_replay.status_code == 201, acknowledged_replay.text
        assert acknowledged_replay.json()["source"]["reconciliation_state"] == (
            "acknowledged"
        )
        assert acknowledged_replay.json()["successor"] == result["successor"]
        replay_revoked = await admin_access.signed.revoke(
            admin_access.admin,
            replay_grant,
            reason="End retained reconciliation inspection duty",
        )
        assert replay_revoked.status_code == 200, replay_revoked.text
        concealed = await admin_access.signed.client.get(
            _paths(h.request.project_id)[0], headers=admin_access.target.headers
        )
        assert concealed.status_code == 404, concealed.text


@pytest.mark.asyncio
async def test_retained_child_authorizes_before_replay_or_conflict(
    tmp_path,
    auth_database_env,
    admin_access,
) -> None:
    """A retained child cannot disclose replay or conflict before fresh authority."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        grant_id = await admin_access.signed.grant(
            admin_access.admin, admin_access.target
        )
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)
        key = new_record_id()
        created = await _reconcile(
            admin_access, h.request.project_id, original.claim.event_id, key
        )
        assert created.status_code == 201, created.text
        successor = created.json()["successor"]
        async with h.factory() as observer:
            denials_before = await observer.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE action_id='operations.post_submit_delivery.reconcile' "
                "AND after_facts->>'allowed'='false'"
            ))
        state_before_denials = await state(h)

        async def denied_variants(actor):
            return (
                await _reconcile(
                    admin_access, h.request.project_id, original.claim.event_id, key,
                    actor=actor,
                ),
                await _reconcile(
                    admin_access, h.request.project_id, original.claim.event_id, key,
                    actor=actor,
                    reason="Substitute the retained reconciliation reason",
                ),
                await _reconcile(
                    admin_access, h.request.project_id, original.claim.event_id,
                    new_record_id(), actor=actor,
                ),
            )

        non_operator = await admin_access.signed.actor("non-operator-replay")
        denied_non_operator = await denied_variants(non_operator)

        revoked = await admin_access.signed.revoke(
            admin_access.admin,
            grant_id,
            reason="End retained reconciliation replay duty",
        )
        assert revoked.status_code == 200, revoked.text
        denied_revoked = await denied_variants(admin_access.target)
        assert [
            (response.status_code, response.json()["error"]["code"])
            for response in denied_non_operator + denied_revoked
        ] == [(404, "post_submit_delivery_not_found")] * 6
        async with h.factory() as observer:
            denials_after = await observer.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE action_id='operations.post_submit_delivery.reconcile' "
                "AND after_facts->>'allowed'='false'"
            ))
            children = await observer.scalar(text(
                "SELECT count(*) FROM public.outbox_events "
                "WHERE causation_event_id=:event_id"
            ), {"event_id": original.claim.event_id})
        assert denials_after == denials_before + 6
        assert children == 1
        assert await state(h) == state_before_denials

        await admin_access.signed.grant(admin_access.admin, admin_access.target)
        replay = await _reconcile(
            admin_access, h.request.project_id, original.claim.event_id, key
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["successor"] == successor
        conflict_payload = await _reconcile(
            admin_access,
            h.request.project_id,
            original.claim.event_id,
            key,
            reason="Substitute the retained reconciliation reason",
        )
        conflict_key = await _reconcile(
            admin_access,
            h.request.project_id,
            original.claim.event_id,
            new_record_id(),
        )
        assert [response.status_code for response in (conflict_payload, conflict_key)] == [
            409,
            409,
        ]


@pytest.mark.asyncio
async def test_discovery_source_wait_retains_no_authority_or_project_lock(
    tmp_path,
    auth_database_env,
    admin_access,
) -> None:
    """Detached TASK custody cannot cycle through the open read-audit transaction."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        grant_id = await admin_access.signed.grant(
            admin_access.admin, admin_access.target
        )
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)
        reached_task_lock = asyncio.Event()

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            lowered = statement.lower()
            if "workstream_tasks" in lowered and "for update" in lowered:
                reached_task_lock.set()

        discovery = None
        try:
            async with h.factory() as blocker, blocker.begin():
                assert await blocker.scalar(
                    text("SELECT id FROM public.workstream_tasks WHERE id=:id FOR UPDATE"),
                    {"id": str(h.request.task_id)},
                ) is not None
                event.listen(Engine, "before_cursor_execute", capture)
                discovery = asyncio.create_task(
                    admin_access.signed.client.get(
                        _paths(h.request.project_id)[0],
                        headers=admin_access.target.headers,
                    )
                )
                try:
                    await asyncio.wait_for(reached_task_lock.wait(), timeout=10)
                    assert not discovery.done()
                    await _lock_delivery_read_authority_nowait(
                        h.factory,
                        actor_id=admin_access.target.id,
                        grant_id=grant_id,
                        project_id=h.request.project_id,
                    )
                    async with h.factory() as observer:
                        allowed = await observer.scalar(text(
                            "SELECT count(*) FROM public.audit_events "
                            "WHERE action_id='operations.post_submit_delivery.list'"
                        ))
                    assert allowed == 0
                finally:
                    event.remove(Engine, "before_cursor_execute", capture)
            response = await asyncio.wait_for(discovery, timeout=10)
            assert response.status_code == 200, response.text
        finally:
            if discovery is not None and not discovery.done():
                discovery.cancel()
                await asyncio.gather(discovery, return_exceptions=True)
        async with h.factory() as observer:
            allowed = await observer.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE action_id='operations.post_submit_delivery.list'"
            ))
        assert allowed == 1


@pytest.mark.asyncio
async def test_discovery_classifier_failure_rolls_back_allowed_audit(
    tmp_path,
    auth_database_env,
    admin_access,
    monkeypatch,
) -> None:
    """A detached source failure cannot retain a successful read decision."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        await admin_access.signed.grant(admin_access.admin, admin_access.target)
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)

        async def unavailable(*_args, **_kwargs):
            raise PostSubmitDeliveryOperationUnavailable("forced_classifier_failure")

        monkeypatch.setattr(
            "app.modules.checkers.delivery_reconciliation.classify_post_submit_delivery",
            unavailable,
        )
        response = await admin_access.signed.client.get(
            _paths(h.request.project_id)[0], headers=admin_access.target.headers
        )
        assert response.status_code == 503, response.text
        async with h.factory() as observer:
            allowed = await observer.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE action_id='operations.post_submit_delivery.list'"
            ))
        assert allowed == 0


@pytest.mark.asyncio
async def test_public_operator_verifies_committed_acceptance_without_repeating_effects(
    tmp_path,
    auth_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
) -> None:
    """Acceptance commit plus acknowledgement loss verifies retained effects only."""
    admin_access = live_acceptance_lifecycle
    async with authorized_routing_source(
        tmp_path,
        auth_database_env,
        human_review_required=False,
        contribution_awards=("project_points",),
    ) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        assert await handler(h.envelope) is HandlerOutcome.ACKNOWLEDGE
        effects = await _project_facts(h.factory, h.request.project_id)
        assert effects == (1, 1, 1, 1, 1, 1)
        retained_effects = await _retained_effect_rows(h.factory, h.request.project_id)
        finalized = await h.completion_delivery.finalize(
            h.envelope.claim, FinalizationCause.UNKNOWN
        )
        assert outcome(finalized)["delivery_state"] == "dead_letter"
        original_before, _ = await _delivery_rows(
            h.factory, h.envelope.claim.event_id
        )
        async with h.factory() as observer:
            grant_id = await observer.scalar(text(
                "SELECT id FROM public.admin_role_grants "
                "WHERE target_actor_profile_id=:actor AND role='operator' "
                "AND scope_type='system' AND status='active'"
            ), {"actor": str(admin_access.target.id)})
        reached_rev_lock = asyncio.Event()

        def capture_rev(_conn, _cursor, statement, _parameters, _context, _many):
            if "pg_advisory_xact_lock" in statement.lower():
                reached_rev_lock.set()

        discovery = None
        try:
            async with h.factory() as blocker, blocker.begin():
                fence = PostgresJointLifecycleMutationFence(blocker)
                generation = await fence.observe_generation()
                async with fence.hold(generation):
                    event.listen(Engine, "before_cursor_execute", capture_rev)
                    discovery = asyncio.create_task(_discover_one(
                        admin_access, h.request.project_id, classification="committed"
                    ))
                    try:
                        await asyncio.wait_for(reached_rev_lock.wait(), timeout=10)
                        assert not discovery.done()
                        await _lock_delivery_read_authority_nowait(
                            h.factory,
                            actor_id=admin_access.target.id,
                            grant_id=grant_id,
                            project_id=h.request.project_id,
                        )
                    finally:
                        event.remove(Engine, "before_cursor_execute", capture_rev)
            source = await asyncio.wait_for(discovery, timeout=10)
        finally:
            if discovery is not None and not discovery.done():
                discovery.cancel()
                await asyncio.gather(discovery, return_exceptions=True)
        assert source["checker_run_id"] == str(h.result.attempt_id)
        created = await _reconcile(
            admin_access,
            h.request.project_id,
            h.envelope.claim.event_id,
            new_record_id(),
        )
        assert created.status_code == 201, created.text
        result = created.json()
        assert result["successor"]["classification"] == "committed"
        child_id = UUID(result["successor"]["event_id"])

        async def unexpected_apply(*_args, **_kwargs):
            pytest.fail("committed reconciliation invoked the routing writer")

        monkeypatch.setattr(TaskPostSubmitOutcome, "apply", unexpected_apply)

        delivered = await production_outbox_delivery(h.factory).deliver(
            child_id, h.request.project_id, "reconcile-completion"
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        assert await _project_facts(h.factory, h.request.project_id) == effects
        assert await _retained_effect_rows(
            h.factory, h.request.project_id
        ) == retained_effects
        original_after, child = await _delivery_rows(
            h.factory, h.envelope.claim.event_id, child_id
        )
        assert original_after == original_before
        assert child[:3] == ("acknowledged", None, h.envelope.claim.event_id)


@pytest.mark.asyncio
async def test_public_operator_projects_uncertain_child_as_permanently_held(
    tmp_path,
    auth_database_env,
    admin_access,
    monkeypatch,
) -> None:
    """A lost POST response holds the actual child execution and both retry paths."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        await admin_access.signed.grant(admin_access.admin, admin_access.target)
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)
        request_keys = (new_record_id(), new_record_id())
        responses = await asyncio.gather(
            *(
                _reconcile(
                    admin_access,
                    h.request.project_id,
                    original.claim.event_id,
                    request_key,
                )
                for request_key in request_keys
            )
        )
        assert sorted(response.status_code for response in responses) == [201, 409]
        created_index = next(
            index for index, response in enumerate(responses) if response.status_code == 201
        )
        created = responses[created_index]
        created_key = request_keys[created_index]
        assert created.status_code == 201, created.text
        child_id = UUID(created.json()["successor"]["event_id"])

        before = await _project_facts(h.factory, h.request.project_id)
        received = []

        async def receive_without_result(reader, writer):
            try:
                observed = await read_fixture_native_request(
                    reader, writer, fixture_placement(h.request.policy.entries[0].registry.image_digest),
                )
                if observed is not None:
                    received.append(observed)
            finally:
                writer.close()
                await writer.wait_closed()

        monkeypatch.setattr("app.core.config.get_settings", lambda: h.settings)
        monkeypatch.setattr(
            artifact_adapters, "worker_post_submission_materialization", lambda *, sessions: h.service,
        )
        with TemporaryDirectory(prefix="ws-a28-post-") as directory:
            native_socket = Path(directory) / "native.sock"
            native = await asyncio.start_unix_server(receive_without_result, native_socket)
            try:
                async with remote_adapter_endpoint(tmp_path, native_socket) as endpoint:
                    selected = RemoteTlsExternalCheckerAdapter(
                        **endpoint, timeout_seconds=90.0,
                        source_contracts=artifact_adapters.selected_pre_submit_source_contracts(),
                    )
                    monkeypatch.setattr(
                        "app.adapters.checkers.configured_post_submit_external_execution",
                        lambda settings, *, sessions: selected,
                    )
                    delivery = production_outbox_delivery(h.factory, worker_group="post")
                    child_unknown = await delivery.deliver(child_id, h.request.project_id, "unknown-child")
                    assert await delivery.deliver(child_id, h.request.project_id, "duplicate-child") is None
            finally:
                native.close()
                await native.wait_closed()

        assert outcome(child_unknown)["delivery_state"] == "dead_letter"
        assert outcome(child_unknown)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        assert outcome(child_unknown)["invocation_unknown"] is True
        assert len(received) == 1
        assert received[0]["operation"] == "execute"
        assert received[0]["request"]["identity"]["evaluation_request_id"] == str(h.request.evaluation_request_id)
        running = await state(h)
        assert running["run"]["status"] == "running"
        assert running["run"]["worker_lease_generation"] == 1
        assert running["run"]["execute_evidence_id"] in running["allows"]
        assert running["run"]["finalize_evidence_id"] is None
        assert running["run"]["result_json"] is None
        assert running["members"] == running["events"] == 0
        assert not h.preparation._active and not list((h.scratch / "workspaces").iterdir())
        assert await _project_facts(h.factory, h.request.project_id) == before

        held = await _discover_one(
            admin_access, h.request.project_id, classification="unresolved"
        )
        assert held["reconciliation_event_id"] == str(child_id)
        assert held["reconciliation_state"] == "held"
        held_replay = await _reconcile(
            admin_access,
            h.request.project_id,
            original.claim.event_id,
            created_key,
        )
        assert held_replay.status_code == 201, held_replay.text
        assert held_replay.json()["source"]["reconciliation_state"] == "held"
        assert held_replay.json()["source"]["classification"] == "unresolved"
        assert held_replay.json()["successor"] == created.json()["successor"]
        refused = await _reconcile(
            admin_access,
            h.request.project_id,
            original.claim.event_id,
            new_record_id(),
        )
        assert refused.status_code == 409, refused.text
        scope = f"/api/v1/operations/projects/{h.request.project_id}"
        retry_sources = await admin_access.signed.client.get(
            f"{scope}/checker-retry-sources", headers=admin_access.target.headers,
        )
        assert retry_sources.status_code == 200, retry_sources.text
        assert retry_sources.json()["items"] == []
        new_generation = await admin_access.signed.client.post(
            f"{scope}/checker-runs/{h.created.evaluation_attempt_id}/retry",
            headers=admin_access.target.headers | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Check that a possibly invoked runner cannot start another generation"},
        )
        assert new_generation.status_code == 404, new_generation.text
        assert new_generation.json()["error"]["code"] == "checker_recovery_source_not_found"
        assert await state(h) == running


@pytest.mark.asyncio
async def test_child_reclassifies_source_transition_before_any_effect(
    tmp_path,
    auth_database_env,
    admin_access,
) -> None:
    """A scheduled retry-safe child refuses a now-running original source."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        await admin_access.signed.grant(admin_access.admin, admin_access.target)
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)
        created = await _reconcile(
            admin_access,
            h.request.project_id,
            original.claim.event_id,
            new_record_id(),
        )
        assert created.status_code == 201, created.text
        child_id = UUID(created.json()["successor"]["event_id"])
        before = await _project_facts(h.factory, h.request.project_id)

        delivery = production_outbox_delivery(h.factory)
        claim = await delivery.claim(child_id, h.request.project_id, "source-transition")
        assert claim is not None
        envelope = await delivery._begin_invocation(claim)
        assert envelope is not None
        handler = delivery._registry.get(envelope.event_type, envelope.event_version)
        assert handler is not None
        payload = PostSubmitDeliveryChildPayload.model_validate_json(envelope.payload_json)
        # Commit the actual execute phase, as if its worker stopped before I/O.
        # Its real AUTH event must satisfy the same custody as production.
        executor = handler._executor(envelope, original, payload, h.request)
        lease, replay = await executor._claim(h.request)
        assert replay is None and lease.lease_generation == 1
        running = await state(h)
        assert running["run"]["status"] == "running"
        assert running["run"]["execute_evidence_id"] in running["allows"]
        assert running["run"]["finalize_evidence_id"] is None
        assert not h.store.opens

        assert await handler(envelope) is HandlerOutcome.REJECT
        refused = await delivery.finalize(
            claim, FinalizationCause.REJECT,
        )
        assert outcome(refused)["delivery_state"] == "dead_letter"
        assert outcome(refused)["error_code"] == "HANDLER_REJECTED"
        assert await state(h) == running
        assert not h.store.opens
        assert await _project_facts(h.factory, h.request.project_id) == before
        held = await _discover_one(
            admin_access, h.request.project_id, classification="unresolved"
        )
        assert held["reconciliation_event_id"] == str(child_id)
        assert held["reconciliation_state"] == "held"


@pytest.mark.asyncio
async def test_foreign_scope_and_non_operator_denials_leave_no_child(
    tmp_path,
    auth_database_env,
    admin_access,
) -> None:
    """Foreign selectors are concealed pre-lock and denial retains no product write."""
    async with material_fixture(tmp_path, auth_database_env) as h:
        prepared = await delivery_fixture(h)
        original = await invoked(h, prepared)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)
        foreign_project = await create_project("Foreign delivery reconciliation scope")
        await admin_access.signed.grant(
            admin_access.admin,
            admin_access.target,
            role="project_manager",
            project_id=h.request.project_id,
        )
        statements = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lower())

        event.listen(Engine, "before_cursor_execute", capture)
        try:
            foreign = await _reconcile(
                admin_access,
                foreign_project,
                original.claim.event_id,
                new_record_id(),
            )
        finally:
            event.remove(Engine, "before_cursor_execute", capture)
        assert foreign.status_code == 404, foreign.text
        assert not any(
            table in statement
            for statement in statements
            for table in (
                "workstream_tasks",
                "task_assignments",
                "submissions",
                "checker_runs",
                "checker_submission_fences",
            )
        )

        denied = await _reconcile(
            admin_access,
            h.request.project_id,
            original.claim.event_id,
            new_record_id(),
        )
        assert denied.status_code == 404, denied.text
        async with h.factory() as session:
            children = await session.scalar(
                text(
                    "SELECT count(*) FROM public.outbox_events "
                    "WHERE causation_event_id=:event_id"
                ),
                {"event_id": original.claim.event_id},
            )
            denials = await session.scalar(
                text(
                    "SELECT count(*) FROM public.audit_events "
                    "WHERE action_id='operations.post_submit_delivery.reconcile' "
                    "AND after_facts->>'allowed'='false'"
                )
            )
        assert children == 0
        assert denials == 1
