"""Current public work selection through real ART admission and persisted outbox handlers."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import post_submission_materialization
from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.tasks.models import SubmissionDispatch
from tests.authorization.post_submit_routing.support import provision_router
from tests.post_submit_materialization_helpers import (
    _material_storage, archive_with_modes, provision_material_services,
)
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.selected_policy_fixtures import approved_selected_policy_fixture
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.evaluation_delivery.support import delivery_fixture, outcome
from tests.tasks.submission_lineage_support import _verify_put_attempt
from tests.tasks.test_public_submission_intake import _client
from tests.test_artifact_admission import _context, _seed_human_actor
from tests.trusted_intake_fixtures import LocalIntakeAdapter


@asynccontextmanager
async def selected_public_work(tmp_path, database_url, monkeypatch, *, human_review_required, instrument="money", post_submit_registry_spec=None):
    """Only policy/actor setup is arranged; TASK/Assignment/Submission use HTTP."""
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings, bootstrap, namespace, store, scratch, manager = _material_storage(
        tmp_path, "local", None, None, None,
    )
    context = _context()
    try:
        plan, policy = await approved_selected_policy_fixture(
            factory, namespace, guide_version="initial", contribution_awards=(instrument,),
            human_review_required=human_review_required, post_submit_registry_spec=post_submit_registry_spec,
        )
        project = plan.lineage.project_id
        await provision_material_services(factory, artifacts=True, checker=True)
        async with factory() as session, session.begin():
            await _seed_human_actor(session, context)
            await grant_fixture_admin_role(session, str(context.actor_profile_id), project_id=str(project))
        async with engine.begin() as connection:
            await install_submitter_grant(connection, {
                "actor": str(context.actor_profile_id), "project": str(project),
            })
        h = SimpleNamespace(factory=factory, engine=engine, settings=settings, actor_context=context,
                            store=store, namespace=namespace, manager=manager, scratch=scratch)
        h.service = post_submission_materialization(
            sessions=factory, store=store, namespace=namespace,
            preparation=ArtifactPreparationService(manager),
            intake=LocalIntakeAdapter(),
            archive_limits=SubmissionArchiveLimits(), artifact_deadline_ms=120_000,
        )
        async with _client(h, monkeypatch, database_url) as client:
            h.client = client
            create_path = f"/api/v1/projects/{project}/tasks"
            create_headers = {"Idempotency-Key": str(new_record_id())}
            create_body = {"title": "Medium work", "description": "Complete the approved work.", "task_size": "medium"}
            created = await client.post(create_path, headers=create_headers, json=create_body)
            assert created.status_code == 201, created.text
            task = created.json()
            h.manager_commands = [(create_path, create_headers, create_body, 201, task)]
            h.task_id = UUID(task["id"])
            for operation, body in (("screen", {}), ("release", {"reason": "Approved exact reward selection"})):
                path, headers = f"/api/v1/tasks/{h.task_id}/{operation}", {"Idempotency-Key": str(new_record_id())}
                response = await client.post(path, headers=headers, json=body)
                assert response.status_code == 200, response.text
                h.manager_commands.append((path, headers, body, 200, response.json()))
            # A second size under the same policy must retain a distinct lookup key.
            small = await client.post(f"/api/v1/projects/{project}/tasks",
                headers={"Idempotency-Key": str(new_record_id())},
                json={"title": "Small sibling", "description": "Same policy, different size.", "task_size": "small"})
            assert small.status_code == 201, small.text
            for operation in ("screen", "release"):
                response = await client.post(f"/api/v1/tasks/{small.json()['id']}/{operation}",
                    headers={"Idempotency-Key": str(new_record_id())}, json={"reason": "Publish sibling selection"})
                assert response.status_code == 200, response.text
            ready = await client.get(f"/api/v1/projects/{project}/tasks/ready")
            assert ready.status_code == 200, ready.text
            terms = {row["compensation"]["task_size"]: row["compensation"]["accepted_submission"][0]["quantity"]
                     for row in ready.json()["items"]}
            assert terms == ({"small": "2.125000000000000001", "medium": "4.250000000000000002"}
                             if instrument == "money" else {"small": "7", "medium": "14"})
            management = await client.get(f"/api/v1/projects/{project}/tasks/{h.task_id}")
            assert management.status_code == 200 and management.json()["task_size"] == "medium", management.text
            context = await client.get(f"/api/v1/projects/{project}/tasks/{h.task_id}/work-context")
            assert context.status_code == 200 and context.json()["task"]["task_size"] == "medium", context.text
            h.claim_headers = {"Idempotency-Key": str(new_record_id())}
            h.claim_body = {"reason": "Start exact Medium work"}
            claim = await client.post(f"/api/v1/tasks/{h.task_id}/claim",
                headers=h.claim_headers, json=h.claim_body)
            assert claim.status_code == 200, claim.text
            h.claim_response = claim.json()
            h.assignment_id = UUID(claim.json()["assignment"]["id"])
            data = archive_with_modes(policy["evidence_path"], project)
            h.data = data
            packet = {"summary": "Completed required work and evidence.",
                "contributor_attestation": "I confirm rights_confirmed and no confidential data, credentials or copied source. "
                    + " ".join(policy["attestation_terms"])}
            prepared = await client.post(f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations",
                headers={"Content-Type": "application/zip", "Idempotency-Key": str(new_record_id()),
                    "X-Task-Assignment-Id": str(h.assignment_id), "X-Submission-Summary": packet["summary"],
                    "X-Contributor-Attestation": packet["contributor_attestation"]}, content=data)
            assert prepared.status_code == 202, prepared.text
            admission = await _verify_put_attempt(factory, store, namespace, settings, prepared.json()["put_attempt_id"])
            h.submission_body = packet | {"assignment_id": str(h.assignment_id), "admission_id": str(admission)}
            submitted = await client.post(f"/api/v1/tasks/{h.task_id}/submissions", json=h.submission_body)
            assert submitted.status_code == 201, submitted.text
            h.submission_response = submitted.json()
            async with factory() as session:
                dispatch = await session.scalar(select(SubmissionDispatch).where(
                    SubmissionDispatch.submission_id == submitted.json()["submission_id"]))
                h.created = dispatch.result()
                h.request = (await evaluation_coordinator(session).read_reserved_evaluation(
                    project_id=project, task_id=h.task_id, submission_id=h.created.submission_id,
                    request_id=h.created.evaluation_request_id,
                )).request
            async with factory() as session:
                sql_hash = await session.scalar(text("SELECT public.revision_task_context_digest(t) "
                    "FROM public.workstream_tasks t WHERE id=:id"), {"id": h.task_id})
                receipt_hash = await session.scalar(text("SELECT locked_context_hash FROM public.task_command_receipts "
                    "WHERE task_id=:id AND action_id='task.claim' AND idempotency_key=:key"),
                    {"id": h.task_id, "key": UUID(h.claim_headers["Idempotency-Key"])})
                assert sql_hash == receipt_hash
            yield h
    finally:
        manager.close()
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize("human_review_required,instrument", [(False, "money"), (True, "money"), (False, "project_points")])
async def test_medium_public_claim_to_selected_automatic_acceptance(
    tmp_path, isolated_database_env, monkeypatch, live_acceptance_lifecycle, human_review_required, instrument,
):
    from app.adapters import artifacts as artifact_adapters
    from app.adapters.outbox import production_outbox_delivery

    async with selected_public_work(tmp_path, isolated_database_env, monkeypatch,
                                    human_review_required=human_review_required, instrument=instrument) as h:
        await provision_router(h.factory)
        await delivery_fixture(h)
        settings = h.settings.model_copy(update={"external_checker_service_socket": None,
                                               "external_checker_material_root": None})
        monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
        monkeypatch.setattr(artifact_adapters, "worker_post_submission_materialization", lambda *, sessions: h.service)
        delivery = production_outbox_delivery(h.factory)
        receipt = await delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "selected-medium-request")
        assert outcome(receipt)["delivery_state"] == "acknowledged", outcome(receipt)
        async with h.factory() as session:
            completed = await session.scalar(text("SELECT completion_event_id FROM public.checker_runs WHERE id=:id"),
                                             {"id": h.created.evaluation_attempt_id})
            assert completed is not None
        receipt = await delivery.deliver(completed, h.request.project_id, "selected-medium-completion")
        assert outcome(receipt)["delivery_state"] == "acknowledged", outcome(receipt)
        async with h.factory() as session:
            copied = (await session.execute(text("""SELECT t.task_size,a.submitter_task_size,s.task_size,
                t.locked_submission_award_definition_id,a.submitter_award_definition_id,s.contribution_award_definition_id,
                d.task_size,d.quantity,t.status FROM public.workstream_tasks t
                JOIN public.task_assignments a ON a.task_id=t.id JOIN public.submissions s ON s.task_assignment_id=a.id
                JOIN public.contribution_award_definitions d ON d.id=s.contribution_award_definition_id WHERE t.id=:id"""),
                {"id": h.task_id})).one()
            assert copied[0:3] == ("medium",)*3
            assert copied[3] == copied[4] == copied[5]
            assert copied[6] == "medium"
            tiers = (await session.execute(text("""SELECT d.quantity FROM public.contribution_award_definitions d
                JOIN public.submissions s ON s.contribution_policy_version_id=d.contribution_policy_version_id
                WHERE s.id=:id AND d.contribution_type='accepted_submission'"""),
                {"id": h.created.submission_id})).scalars().all()
            assert len(set(tiers)) == 3
            assert copied[8] == ("review_pending" if human_review_required else "accepted")
            awards = (await session.execute(text("SELECT award_definition_id,quantity FROM public.compensation_awards"))).all()
            assert awards == ([] if human_review_required else [(copied[5],copied[7])])
            for table in ("final_acceptances", "contribution_records"):
                assert await session.scalar(text(f"SELECT count(*) FROM public.{table}")) == int(not human_review_required)
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
        evidence = await h.client.get("/api/v1/actors/me/contributions")
        assert evidence.status_code == 200, evidence.text
        if human_review_required:
            assert evidence.json()["items"] == []
        else:
            (record,) = evidence.json()["items"]
            assert record["task_size"] == "medium"
            assert record["submission_id"] == str(h.created.submission_id)
            assert record["awards"][0]["award_definition_id"] == str(copied[5])
            assert record["awards"][0]["quantity"] == ("4.250000000000000002" if instrument == "money" else "14")
        assert await delivery.deliver(completed, h.request.project_id, "selected-medium-replay") is None


@pytest.mark.parametrize("target_instrument,target_quantity", [
    (None, None), ("money", "1"), ("money", "8"), ("project_points", "14"),
], ids=["unpaid", "lower-money", "higher-money", "points"])
async def test_original_claim_replay_after_rebase(tmp_path, isolated_database_env, monkeypatch,
                                               live_acceptance_lifecycle, target_instrument, target_quantity):
    """Revised terms change the replacement's award, never original command/evidence."""
    from app.modules.checkers.models import CheckerRun
    from tests.checkers.execution.support import ControlledSelectedExecution, live_executor, reserve
    from tests.checkers.external.support import post_registry_spec
    from tests.tasks.post_submit_routing.outcome_support import invoked_completion
    from tests.tasks.post_submit_routing.support import activate_successor_guide, source_values
    from tests.test_submission_predecessor_custody import _fixture_revision_context

    async with selected_public_work(tmp_path, isolated_database_env, monkeypatch,
            human_review_required=False, post_submit_registry_spec=post_registry_spec()) as h:
        await reserve(h)
        h.result = await live_executor(h, selected_execution=ControlledSelectedExecution(verdict="failed")).evaluate_post_submission(h.request)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(h.result.attempt_id))
            assert run.routing_recommendation == "needs_revision"
            h.material = dict(run.material_custody)
        h.source = {}
        h.source = await source_values(h)
        await provision_router(h.factory)
        h.envelope = await invoked_completion(h)
        await activate_successor_guide(
            h, version="revised", human_review_required=False,
            contribution_awards=() if target_instrument is None else (target_instrument,),
            submission_quantities=({"small": "1", "medium": target_quantity, "large": "21"}
                                   if target_instrument is not None else None),
        )
        await _fixture_revision_context(h)
        view = await h.client.get(f"/api/v1/tasks/{h.task_id}/work-context")
        assert view.status_code == 200, view.text
        revision = view.json()["revision_context"]
        assert revision["prior_reward_selection"] == {
            "compensation_mode": "compensated", "task_size": "medium",
            "instrument": "money", "unit": "USD", "quantity": "4.250000000000000002",
        }
        assert revision["target_reward_selection"] == {
            "compensation_mode": "unpaid" if target_instrument is None else "compensated",
            "task_size": "medium", "instrument": target_instrument,
            "unit": None if target_instrument is None else ("USD" if target_instrument == "money" else "PTS"),
            "quantity": target_quantity,
        }
        assert "adapter_binding_id" not in view.text
        foreign = _context()
        async with h.factory() as session, session.begin():
            await _seed_human_actor(session, foreign)
        async with h.engine.begin() as connection:
            await install_submitter_grant(connection, {
                "actor": str(foreign.actor_profile_id), "project": str(h.request.project_id),
            })
        async with h.factory() as session:
            original = await session.scalar(text("SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"),
                                            {"id": h.created.submission_id})
            counts = {table: await session.scalar(text(f"SELECT count(*) FROM public.{table}"))
                      for table in ("task_command_receipts", "task_assignments", "submissions", "final_acceptances", "contribution_records", "compensation_awards")}
            decisions = await session.scalar(text("SELECT count(*) FROM public.audit_events WHERE action_id='task.claim' "
                "AND event_type='SensitiveAuthorizationAllowed' AND actor_id=:actor"),
                {"actor": str(h.actor_context.actor_profile_id)})
        for path, headers, body, expected_status, expected_result in h.manager_commands:
            recorded = await h.client.post(path, headers=headers, json=body)
            assert recorded.status_code == expected_status and recorded.json() == expected_result, recorded.text
            changed_body = body | ({"title": "Changed creation"} if expected_status == 201 else {"reason": "Changed transition"})
            changed_command = await h.client.post(path, headers=headers, json=changed_body)
            assert changed_command.status_code == 409, changed_command.text
        replay = await h.client.post(f"/api/v1/tasks/{h.task_id}/claim", headers=h.claim_headers, json=h.claim_body)
        assert replay.status_code == 200 and replay.json() == h.claim_response, replay.text
        changed = await h.client.post(f"/api/v1/tasks/{h.task_id}/claim", headers=h.claim_headers,
                                      json={"reason": "Different request"})
        assert changed.status_code == 409, changed.text
        with monkeypatch.context() as foreign_environment:
            async with _client(h, foreign_environment, isolated_database_env,
                               subject=f"human-{foreign.actor_profile_id}") as other:
                denied = await other.post(f"/api/v1/tasks/{h.task_id}/claim", headers=h.claim_headers, json=h.claim_body)
                assert denied.status_code == 403, denied.text
        submission = await h.client.post(f"/api/v1/tasks/{h.task_id}/submissions", json=h.submission_body)
        assert submission.status_code == 201 and submission.json() == h.submission_response, submission.text
        async with h.factory() as session:
            assert await session.scalar(text("SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"),
                                        {"id": h.created.submission_id}) == original
            assert {table: await session.scalar(text(f"SELECT count(*) FROM public.{table}")) for table in counts} == counts
            assert await session.scalar(text("SELECT count(*) FROM public.audit_events WHERE action_id='task.claim' "
                "AND event_type='SensitiveAuthorizationAllowed' AND actor_id=:actor"),
                {"actor": str(h.actor_context.actor_profile_id)}) > decisions

        # The acknowledged replacement takes the new selection; original evidence stays exact.
        from tests.tasks.post_submit_routing.support import revision_archive
        from app.adapters.outbox import production_outbox_delivery
        old_submission = h.created.submission_id
        replacement_data = revision_archive(h.data)
        headers = {"Content-Type": "application/zip", "Idempotency-Key": str(new_record_id()),
            "X-Task-Assignment-Id": str(h.assignment_id),
            "X-Submission-Summary": "Corrected the failed work under the revised guide.",
            "X-Contributor-Attestation": h.submission_body["contributor_attestation"],
            "X-Predecessor-Submission-Id": str(old_submission),
            "X-Revision-Preparation-Id": revision["preparation_id"],
            "X-Revision-Preparation-Sha256": revision["preparation_sha256"]}
        stale = await h.client.post(f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations",
            headers=headers | {"Idempotency-Key": str(new_record_id()), "X-Revision-Preparation-Sha256": "sha256:"+"0"*64}, content=replacement_data)
        assert stale.status_code == 409, stale.text
        prepared = await h.client.post(f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations",
                                       headers=headers, content=replacement_data)
        assert prepared.status_code == 202, prepared.text
        admission = await _verify_put_attempt(h.factory, h.store, h.namespace, h.settings, prepared.json()["put_attempt_id"])
        submitted = await h.client.post(f"/api/v1/tasks/{h.task_id}/submissions", json={
            "assignment_id": str(h.assignment_id), "admission_id": str(admission),
            "predecessor_submission_id": str(old_submission), "summary": headers["X-Submission-Summary"],
            "contributor_attestation": headers["X-Contributor-Attestation"]})
        assert submitted.status_code == 201, submitted.text
        async with h.factory() as session:
            dispatch = await session.scalar(select(SubmissionDispatch).where(
                SubmissionDispatch.submission_id == submitted.json()["submission_id"]))
            h.created = dispatch.result()
            h.request = (await evaluation_coordinator(session).read_reserved_evaluation(
                project_id=h.request.project_id, task_id=h.task_id, submission_id=h.created.submission_id,
                request_id=h.created.evaluation_request_id)).request
            copied = (await session.execute(text("""SELECT s.task_size,s.contribution_award_definition_id,
                s.contribution_policy_version_id,a.submitter_task_size,a.submitter_award_definition_id,
                a.submitter_contribution_policy_version_id,d.task_size,d.contribution_award_definition_id,
                d.contribution_policy_version_id FROM public.submissions s
                JOIN public.task_assignments a ON a.id=s.task_assignment_id
                JOIN public.submission_bundle_admissions d ON d.id=s.submission_bundle_admission_id
                WHERE s.id=:id"""), {"id": h.created.submission_id})).one()
            assert copied[0] == copied[3] == copied[6] == "medium"
            assert copied[1] == copied[4] == copied[7]
            assert (copied[1] is None) == (target_instrument is None)
            assert str(copied[1]) != original["contribution_award_definition_id"]
            assert copied[2] == copied[5] == copied[8]
            assert str(copied[2]) != original["contribution_policy_version_id"]
        await reserve(h)
        h.result = await live_executor(h, selected_execution=ControlledSelectedExecution(verdict="passed")).evaluate_post_submission(h.request)
        await delivery_fixture(h)
        async with h.factory() as session:
            completion = await session.scalar(text("SELECT completion_event_id FROM public.checker_runs WHERE id=:id"),
                                              {"id": h.result.attempt_id})
        delivered = await production_outbox_delivery(h.factory).deliver(completion, h.request.project_id, "revised-unpaid-completion")
        assert outcome(delivered)["delivery_state"] == "acknowledged", outcome(delivered)
        async with h.factory() as session:
            assert await session.scalar(text("SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"),
                                        {"id": old_submission}) == original
            assert await session.scalar(text("SELECT submission_id FROM public.contribution_records")) == h.created.submission_id
            awards = (await session.execute(text("SELECT award_definition_id,instrument_type,unit_code,quantity "
                                                "FROM public.compensation_awards"))).all()
            if target_instrument is None:
                assert awards == []
            else:
                from decimal import Decimal
                assert awards == [(copied[1], target_instrument,
                                   "USD" if target_instrument == "money" else "PTS", Decimal(target_quantity))]
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
            assert await session.scalar(text("SELECT status FROM public.workstream_tasks WHERE id=:id"), {"id": h.task_id}) == "accepted"
        evidence = await h.client.get("/api/v1/actors/me/contributions")
        assert evidence.status_code == 200, evidence.text
        (record,) = evidence.json()["items"]
        assert record["submission_id"] == str(h.created.submission_id)
        assert record["task_size"] == "medium"
        if target_instrument is None:
            assert record["awards"] == []
        else:
            (award,) = record["awards"]
            assert award["award_definition_id"] == str(copied[1])
            assert award["quantity"] == target_quantity
