"""Terminal checker failures release one assignment without inventing a revision."""

from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.tasks import task_post_submit_outcome
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.runtime import AuthorizationDenied, PreparedAuthorizationUnsupported
from app.modules.outbox.service import OutboxService
from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
from app.modules.projects.schemas import RevisionPolicyInput
from app.modules.tasks.revision.models import TaskRevisionExhaustion
from app.modules.tasks.schemas import AdmissionBackedSubmissionResponse
from tests.checkers.execution.support import service_link_state
from tests.checkers.execution.completion_fixture import completed_evidence
from tests.tasks.post_submit_routing.outcome_support import outcome_snapshot
from tests.tasks.post_submit_routing.remediation_support import no_economic_effects, remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_dispatch.test_revision_capacity import _fail_current_submission
from tests.tasks.submission_lineage_support import _verify_put_attempt
from tests.tasks.test_public_submission_intake import _client


def test_zero_revision_policy_is_explicit_finite_and_hashable():
    """Zero is a required policy value; absence and malformed limits fail closed."""
    from app.modules.projects.api.policy_lineage import policy_digest

    values = {"max_revision_rounds": 0, "revision_deadline_hours": 48,
              "allowed_resubmission_states": ["needs_revision"]}
    zero = RevisionPolicyInput.model_validate(values)
    semantics = RevisionPolicySemantics.model_validate(values)
    assert zero.max_revision_rounds == semantics.max_revision_rounds == 0
    assert "max_revision_rounds" in RevisionPolicyInput.model_json_schema()["required"]
    assert "max_revision_rounds" in RevisionPolicySemantics.model_json_schema()["required"]
    assert policy_digest("revision", semantics) != policy_digest(
        "revision", semantics.model_copy(update={"max_revision_rounds": 1}),
    )
    for model in (RevisionPolicyInput, RevisionPolicySemantics):
        for invalid in (None, -1, 0.5, float("inf"), True, "0"):
            with pytest.raises(ValidationError):
                model.model_validate(values | {"max_revision_rounds": invalid})
        with pytest.raises(ValidationError):
            model.model_validate({key: value for key, value in values.items()
                                  if key != "max_revision_rounds"})


async def _apply(h, envelope=None):
    async with h.factory() as session, session.begin():
        return await task_post_submit_outcome(session, h.factory).apply(
            envelope or h.envelope, current_generation=None,
        )


async def _snapshot(h):
    async with h.factory() as session:
        owners = tuple(await outcome_snapshot(session))
        retained = (await session.execute(text("""
            SELECT (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.submissions r),
              (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_revision_exhaustions r),
              (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_revision_preparations r),
              (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_revision_expirations r),
              (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.route_operation_id)
                 FROM public.task_post_submit_routing_requests r)
        """))).one()
        return owners, tuple(retained)


async def terminal_facts(h, outcome, *, expected_round):
    """Read independent committed evidence, current release and absence of a timer."""
    async with h.factory() as session:
        receipt = await session.scalar(select(TaskRevisionExhaustion).where(
            TaskRevisionExhaustion.routing_manifest_id == outcome.routing_manifest_id,
        ))
        assert receipt is not None
        assert receipt.assignment_id == str(h.request.assignment_id)
        assert receipt.source_submission_id == str(h.created.submission_id)
        assert receipt.contributor_id == str(h.actor_context.actor_profile_id)
        assert receipt.revision_round == receipt.max_revision_rounds == expected_round
        state = (await session.execute(text("""
            SELECT t.status,t.assigned_to,a.status,a.released_at,
              public.task_routing_outcome_complete(m),
              (SELECT count(*) FROM public.task_revision_preparations p WHERE p.routing_manifest_id=m.id),
              (SELECT count(*) FROM public.outbox_events e
                 WHERE e.idempotency_key='task.revision.expire:'||m.id::text)
            FROM public.task_post_submit_routing_manifests m
            JOIN public.workstream_tasks t ON t.id=m.task_id
            JOIN public.task_assignments a ON a.id=m.assignment_id WHERE m.id=:id
        """), {"id": outcome.routing_manifest_id})).one()
        assert state == ("ready", None, "revision_exhausted", receipt.exhausted_at, True, 0, 0)
        assert await session.scalar(text("""
            SELECT count(*) FROM public.audit_events
            WHERE id=:id AND action_id='task.post_submit.route'
              AND event_type='SensitiveAuthorizationAllowed' AND after_facts->>'allowed'='true'
        """), {"id": receipt.authorization_decision_id}) == 1
        await no_economic_effects(session)
        return receipt


async def _assert_exhausted_assignment_immutable(h, receipt):
    """Every terminal assignment mutation fails without changing receipt history."""
    assignment_id = receipt.assignment_id
    receipt_id = receipt.id

    async def custody():
        async with h.factory() as session:
            row = (await session.execute(text("""
                SELECT to_jsonb(a),to_jsonb(e),
                  (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.version)
                     FROM public.submissions s WHERE s.task_assignment_id=a.id),
                  (SELECT to_jsonb(o) FROM public.outbox_events o
                     WHERE o.event_id=e.outcome_event_id),
                  (SELECT to_jsonb(v) FROM public.audit_events v WHERE v.id=e.audit_event_id),
                  public.task_revision_exhaustion_complete(e.id)
                FROM public.task_assignments a
                JOIN public.task_revision_exhaustions e ON e.assignment_id=a.id
                WHERE a.id=:assignment AND e.id=:receipt
            """), {"assignment": assignment_id, "receipt": receipt_id})).one()
            assert row[-1] is True
            return row

    before = await custody()
    attacks = (
        ("UPDATE public.task_assignments SET status='active' WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET released_at=NULL WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET released_at=released_at+interval '1 second' "
         "WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET accepted_at=accepted_at+interval '1 second' "
         "WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET id=:new_assignment,project_id=:new_project,"
         "task_id=:new_task,contributor_id=:new_contributor WHERE id=:assignment", {
             "new_assignment": new_record_id(), "new_project": new_record_id(),
             "new_task": new_record_id(), "new_contributor": new_record_id(),
         }),
        ("UPDATE public.task_assignments SET submitter_contribution_policy_version_id=:replacement "
         "WHERE id=:assignment", {"replacement": new_record_id()}),
        ("DELETE FROM public.task_assignments WHERE id=:assignment", {}),
    )
    for statement, parameters in attacks:
        with pytest.raises(DBAPIError) as rejected:
            async with h.factory() as session, session.begin():
                await session.execute(text(statement), parameters | {"assignment": assignment_id})
                raise AssertionError("terminal assignment mutation unexpectedly succeeded")
        assert rejected.value.orig.sqlstate == "23514"
        database_error = rejected.value.orig.__cause__
        assert database_error.constraint_name == "ck_revision_exhausted_assignment_immutable"
        assert await custody() == before


async def _submit_initial_after_reclaim(h, client):
    claim = await client.post(f"/api/v1/tasks/{h.request.task_id}/claim",
                              headers={"Idempotency-Key": str(new_record_id())})
    assert claim.status_code == 200, claim.text
    assignment = UUID(claim.json()["assignment"]["id"])
    assert assignment != h.request.assignment_id
    assert claim.json()["task"]["status"] == "in_progress"
    h.data = revision_archive(h.data)
    headers = {"Content-Type": "application/zip", "X-Task-Assignment-Id": str(assignment),
               "Idempotency-Key": str(new_record_id()),
               "X-Submission-Summary": h.creation_request.summary,
               "X-Contributor-Attestation": h.creation_request.contributor_attestation}
    route = f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations"
    prepared = await client.post(route, headers=headers, content=h.data)
    assert prepared.status_code == 202, prepared.text
    admission = await _verify_put_attempt(h.factory, h.store, h.namespace, h.settings,
                                         prepared.json()["put_attempt_id"])
    ready = await client.post(route, headers=headers, content=h.data)
    assert ready.status_code == 202 and ready.json()["admission_id"] == str(admission), ready.text
    created = await client.post(f"/api/v1/tasks/{h.request.task_id}/submissions", json={
        "assignment_id": str(assignment), "admission_id": str(admission),
        "summary": h.creation_request.summary,
        "contributor_attestation": h.creation_request.contributor_attestation,
    })
    assert created.status_code == 201, created.text
    return AdmissionBackedSubmissionResponse.model_validate(created.json())


async def _other_eligible_actor(h):
    from tests.test_artifact_admission import _context, _seed_human_actor
    from tests.submission_preparation_auth_helpers import install_submitter_grant

    actor = _context(actor_profile_id=new_record_id(), identity_link_id=new_record_id())
    async with h.factory() as session, session.begin():
        await _seed_human_actor(session, actor)
    async with h.engine.begin() as connection:
        await install_submitter_grant(connection, {
            "project": str(h.request.project_id), "actor": str(actor.actor_profile_id),
        })
    return actor


async def _history_rejects_source(h, client, source_id):
    from app.modules.tasks.api.assignment_outcome import TaskAssignmentOutcome

    history = await client.get(f"/api/v1/tasks/{h.request.task_id}/submissions")
    assert history.status_code == 200, history.text
    row = next(item for item in history.json()["items"] if item["id"] == str(source_id))
    assert (row["status"], row["status_reason"]) == ("rejected", "revision_limit_reached")
    async with h.factory() as session:
        receipt = await session.scalar(select(TaskRevisionExhaustion).where(
            TaskRevisionExhaustion.source_submission_id == str(source_id),
        ))
        expected = TaskAssignmentOutcome(
            assignment_id=UUID(receipt.assignment_id), submission_id=UUID(receipt.source_submission_id),
            status="revision_exhausted", status_reason="revision_limit_reached", closed_at=receipt.exhausted_at,
        ).model_dump(mode="json")
    detail = await client.get(f"/api/v1/tasks/{h.request.task_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["last_assignment_outcome"] == expected
    mine = await client.get("/api/v1/actors/me/assignments", params={"state": "closed"})
    assert mine.status_code == 200, mine.text
    # A closed claim projects only the contributor's own facts.
    [closed] = [item for item in mine.json()["items"] if item["assignment_id"] == receipt.assignment_id]
    assert (closed["state"], closed["assignment_status"], closed["next_action"]) == (
        "closed", "revision_exhausted", "none",
    )
    assert closed["task_status"] is None and closed["revision"] is None
    assert closed["latest_submission"]["submission_id"] == str(source_id)
    assert closed["latest_submission"]["status_reason"] == "revision_limit_reached"
    active = await client.get("/api/v1/actors/me/assignments", params={"state": "active"})
    assert active.status_code == 200, active.text
    assert receipt.assignment_id not in {item["assignment_id"] for item in active.json()["items"]}
    return expected


async def _manager_sees_latest_outcome(h, monkeypatch, database_url, expected):
    from types import SimpleNamespace
    from app.modules.authorization.api import ActorIdentityFacts, ActorKind
    from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor
    from tests.test_artifact_admission import _context, _seed_human_actor

    manager = _context(actor_profile_id=new_record_id(), identity_link_id=new_record_id())
    async with h.factory() as session, session.begin():
        await _seed_human_actor(session, manager)
    await seed_review_actor(h.factory, h.request.project_id, actor=ActorIdentityFacts(
        manager.actor_profile_id, manager.identity_link_id, ActorKind.HUMAN,
    ))
    viewer = SimpleNamespace(**(vars(h) | {"actor_context": manager}))
    async with _client(viewer, monkeypatch, database_url) as client:
        detail = await client.get(f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["last_assignment_outcome"] == expected


@pytest.mark.parametrize("human_review_required", [True, False])
async def test_zero_cap_releases_immediately_and_reclaim_resets_only_assignment_rounds(
    tmp_path, isolated_database_env, monkeypatch, human_review_required,
):
    """Both modes retain old facts while the same or another eligible actor restarts."""
    async with remediation_source(tmp_path, isolated_database_env, max_revision_rounds=0,
                                  human_review_required=human_review_required) as h:
        first_envelope = h.envelope
        first_submission = str(h.created.submission_id)
        async with h.factory() as session:
            original = await session.scalar(text("SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"),
                                            {"id": h.created.submission_id})
        first = await _apply(h)
        first_receipt = await terminal_facts(h, first, expected_round=0)
        await _assert_exhausted_assignment_immutable(h, first_receipt)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            await _history_rejects_source(h, client, first_submission)
            h.created = await _submit_initial_after_reclaim(h, client)
            assert h.created.submission_version == 2
        before = await _snapshot(h)
        assert await _apply(h, first_envelope) == first.model_copy(update={"replayed": True})
        assert await _snapshot(h) == before
        second = await _fail_current_submission(h, terminal=True)
        await terminal_facts(h, second, expected_round=0)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            latest = await _history_rejects_source(h, client, h.created.submission_id)
        await _manager_sees_latest_outcome(h, monkeypatch, isolated_database_env, latest)
        h.actor_context = await _other_eligible_actor(h)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            unrelated = await client.get(f"/api/v1/tasks/{h.request.task_id}")
            assert unrelated.status_code == 200, unrelated.text
            assert unrelated.json()["last_assignment_outcome"] is None
            h.created = await _submit_initial_after_reclaim(h, client)
            assert h.created.submission_version == 3
        before = await _snapshot(h)
        assert await _apply(h, first_envelope) == first.model_copy(update={"replayed": True})
        assert await _snapshot(h) == before
        await service_link_state(h.factory, ServiceIdentity.TASK_POST_SUBMIT_ROUTER, active=False)
        denied = await _snapshot(h)
        with pytest.raises((AuthorizationDenied, PreparedAuthorizationUnsupported)):
            await _apply(h, first_envelope)
        assert await _snapshot(h) == denied
        await service_link_state(h.factory, ServiceIdentity.TASK_POST_SUBMIT_ROUTER, active=True)
        async with h.factory() as session:
            # The packet is unchanged; only its attempt outcome records the exhaustion.
            outcome = ["attempt_status", "status_reason", "decided_at", "updated_at"]
            assert await session.scalar(text(
                "SELECT to_jsonb(s)-CAST(:outcome AS text[]) FROM public.submissions s WHERE id=:id"
            ), {"id": first_submission, "outcome": outcome}) == {
                key: value for key, value in original.items() if key not in outcome
            }
            assert (await session.execute(text(
                "SELECT attempt_status,status_reason,decided_at FROM public.submissions WHERE id=:id"
            ), {"id": first_submission})).one() == (
                "rejected", "revision_limit_reached", first_receipt.exhausted_at,
            )
            rows = (await session.execute(text("""
                SELECT version,task_assignment_id,supersedes_submission_id FROM public.submissions
                WHERE task_id=:id ORDER BY version
            """), {"id": h.request.task_id})).all()
            assert [row.version for row in rows] == [1, 2, 3]
            assert len({row.task_assignment_id for row in rows}) == 3
            assert all(row.supersedes_submission_id is None for row in rows)
            await no_economic_effects(session)


class StagedFailure(RuntimeError):
    """Deliberate failure after one real participant has written."""


async def test_exhaustion_caller_and_real_participant_failures_roll_back_every_owner(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.adapters.audit import _TaskRoutingAudit

    async with remediation_source(tmp_path, isolated_database_env, max_revision_rounds=0) as h:
        before = await _snapshot(h)
        for owner_type, method in ((_TaskRoutingAudit, "record"), (OutboxService, "append")):
            original = getattr(owner_type, method)
            reached = []

            async def fail_after_write(owner, *args, **kwargs):
                value = await original(owner, *args, **kwargs)
                reached.append(value)
                if owner_type is _TaskRoutingAudit:
                    assert await owner._session.scalar(select(TaskRevisionExhaustion.id)) is not None
                raise StagedFailure("after real participant write")

            with monkeypatch.context() as patch:
                patch.setattr(owner_type, method, fail_after_write)
                with pytest.raises(StagedFailure, match="after real participant write"):
                    await _apply(h)
            assert len(reached) == 1
            assert await _snapshot(h) == before
        async with h.factory() as session:
            await session.begin()
            staged = await task_post_submit_outcome(session, h.factory).apply(h.envelope, current_generation=None)
            assert await session.scalar(select(TaskRevisionExhaustion.id)) is not None
            await session.rollback()
        assert await _snapshot(h) == before
        committed = await _apply(h)
        assert committed.submission_id == staged.submission_id
        await terminal_facts(h, committed, expected_round=0)
        final = await _snapshot(h)
        for statement in ("UPDATE public.task_revision_exhaustions SET revision_round=revision_round",
                          "DELETE FROM public.task_revision_exhaustions",
                          "TRUNCATE public.task_revision_exhaustions"):
            with pytest.raises(DBAPIError, match="revision exhaustions are immutable"):
                async with h.factory() as session, session.begin():
                    await session.execute(text(statement))
            assert await _snapshot(h) == final


async def test_direct_sql_exhaustion_rejects_forged_receipts_and_partial_release(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Bypass ORM validation while preserving every database guard and participant."""
    async with (
        remediation_source(tmp_path / "own", isolated_database_env, max_revision_rounds=0) as h,
        completed_evidence(tmp_path / "foreign", isolated_database_env,
                           provision_services=False, storage_settings=h.settings) as foreign,
    ):
        assert foreign.request.project_id != h.request.project_id
        assert foreign.request.task_id != h.request.task_id
        assert foreign.request.assignment_id != h.request.assignment_id
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT id FROM public.submissions WHERE id=:id"
            ), {"id": foreign.created.submission_id}) == foreign.created.submission_id
        before = await _snapshot(h)
        for attack in ("source", "policy", "authority", "missing_closure"):
            reached = []

            async def insert_directly(session, *, receipt, task, assignment):
                values = {column.key: getattr(receipt, column.key)
                          for column in TaskRevisionExhaustion.__table__.columns
                          if column.key not in {"created_at", "creation_xid"}}
                if attack == "source":
                    values["source_submission_id"] = str(foreign.created.submission_id)
                elif attack == "policy":
                    values["revision_policy_generation"] += 1
                elif attack == "authority":
                    values["authorization_decision_id"] = str(await session.scalar(text(
                        "SELECT id FROM public.audit_events WHERE id<>:decision ORDER BY id LIMIT 1"
                    ), {"decision": receipt.authorization_decision_id}))
                    assert values["authorization_decision_id"] != "None"
                reached.append(attack)
                # Core INSERT bypasses mapped-object validation and the canonical writer.
                await session.execute(TaskRevisionExhaustion.__table__.insert().values(**values))
                assert attack == "missing_closure", "forged receipt survived its INSERT guard"
                assert await session.scalar(select(TaskRevisionExhaustion.id)) == receipt.id
                # The valid receipt alone cannot commit a partial terminal outcome.
                await session.execute(text("SET CONSTRAINTS revision_exhaustion_closure IMMEDIATE"))

            expected = ("revision exhaustion closure unavailable" if attack == "missing_closure"
                        else "revision exhaustion source or authority differs")
            with monkeypatch.context() as patch:
                patch.setattr("app.modules.tasks.revision.exhaustion.commit_exhaustion", insert_directly)
                with pytest.raises(DBAPIError, match=expected):
                    await _apply(h)
            assert reached == [attack]
            assert await _snapshot(h) == before
        for statement, identity in (
            ("UPDATE public.workstream_tasks SET status='ready',assigned_to=NULL WHERE id=:id",
             h.request.task_id),
            ("UPDATE public.task_assignments SET status='revision_exhausted',"
             "released_at=clock_timestamp() WHERE id=:id", h.request.assignment_id),
        ):
            with pytest.raises(DBAPIError, match="revision exhaustion receipt required"):
                async with h.factory() as session, session.begin():
                    await session.execute(text(statement), {"id": identity})
            assert await _snapshot(h) == before
        # The same source remains usable through the complete canonical transaction.
        await terminal_facts(h, await _apply(h), expected_round=0)
