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
async def selected_public_work(tmp_path, database_url, monkeypatch, *, human_review_required, instrument="money"):
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
            human_review_required=human_review_required,
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
            created = await client.post(f"/api/v1/projects/{project}/tasks",
                headers={"Idempotency-Key": str(new_record_id())},
                json={"title": "Medium work", "description": "Complete the approved work.", "task_size": "medium"})
            assert created.status_code == 201, created.text
            task = created.json()
            h.task_id = UUID(task["id"])
            for operation, body in (("screen", {}), ("release", {"reason": "Approved exact reward selection"})):
                response = await client.post(f"/api/v1/tasks/{h.task_id}/{operation}",
                    headers={"Idempotency-Key": str(new_record_id())}, json=body)
                assert response.status_code == 200, response.text
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
            claim = await client.post(f"/api/v1/tasks/{h.task_id}/claim",
                headers={"Idempotency-Key": str(new_record_id())}, json={"reason": "Start exact Medium work"})
            assert claim.status_code == 200, claim.text
            h.assignment_id = UUID(claim.json()["assignment"]["id"])
            data = archive_with_modes(policy["evidence_path"], project)
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
