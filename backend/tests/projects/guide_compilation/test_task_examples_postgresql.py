"""Required example text through real guide authority, PostgreSQL and replay."""

import json
from uuid import uuid4

import pytest
from httpx import AsyncClient
from app.core.hashing import canonical_json_hash
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_session_factory
from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples
from tests.projects.client_fixtures import (
    auth_headers,
    project_client as project_client,
    project_database_env as project_database_env,
)
from tests.projects.guide_fixtures import create_project, create_source_snapshot, create_guide, complete_guide_payload


async def _guide(client, project_id, examples, *, key=None):
    return await client.post(
        f"/api/v1/projects/{project_id}/guides",
        headers=auth_headers() | {"Idempotency-Key": key or str(uuid4())},
        json={"version": "example-proof", "task_examples": examples},
    )


async def test_required_examples_reject_before_product_effects_then_exact_replay(project_client):  # noqa: F811
    project = await create_project(project_client)
    route = f"/api/v1/projects/{project['id']}/guides"
    for patch in [{}, {"task_examples": []}, {"task_examples": [{"content": " \t\u2003"}]}]:
        response = await project_client.post(
            route, headers=auth_headers(), json={"version": "example-proof", **patch},
        )
        assert response.status_code == 422
    async with get_session_factory()() as session:
        for table in ("project_guides", "guide_source_snapshots", "project_setup_runs", "workstream_tasks", "guide_mutation_idempotency_records"):
            assert await session.scalar(text(f"select count(*) from {table} where project_id=:project"), {"project": project["id"]}) == 0
    examples = [{"content": "Draft a claim review."}, {"content": "  雪\nSecond starting idea.", "title": "Second", "labels": ["research"]}]
    key = str(uuid4())
    first = await _guide(project_client, project["id"], examples, key=key)
    assert first.status_code == 201, first.text
    guide = first.json()
    normalized = [item.model_dump(mode="json") for item in validate_task_examples(examples)]
    assert guide["task_examples"] == normalized
    assert guide["task_examples_hash"] == task_examples_hash(validate_task_examples(examples))
    replay = await _guide(project_client, project["id"], examples, key=key)
    assert replay.status_code == 201 and replay.json() == guide
    for changed in [list(reversed(examples)), [examples[0] | {"content": "Changed"}, examples[1]],
                    [examples[0], examples[1] | {"title": "Changed"}],
                    [examples[0], examples[1] | {"labels": ["changed"]}]]:
        response = await _guide(project_client, project["id"], changed, key=key)
        assert response.status_code == 409, response.text
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    assert snapshot["manifest_json"]["task_examples_hash"] == guide["task_examples_hash"]
    assert snapshot["manifest_json"]["task_examples_count"] == 2
    async with get_session_factory()() as session:
        stored = (await session.execute(text("select task_examples,task_examples_hash from project_guides where id=:id"), {"id": guide["id"]})).one()
        assert stored.task_examples == normalized
        assert stored.task_examples_hash == guide["task_examples_hash"]
        assert await session.scalar(text("select count(*) from workstream_tasks where project_id=:id"), {"id": project["id"]}) == 0
        assert await session.scalar(text("select count(*) from project_guides where project_id=:id"), {"id": project["id"]}) == 1


async def test_example_sql_shape_hash_and_immutability_have_valid_control(project_client):  # noqa: F811
    project = await create_project(project_client)
    examples = [{"content": "  Review 雪.\n", "title": None, "labels": []}]
    response = await _guide(project_client, project["id"], examples)
    assert response.status_code == 201, response.text
    guide = response.json()
    async with get_session_factory()() as session:
        row = (await session.execute(text(
            "select project_guide_task_examples_valid(cast(:examples as jsonb)), "
            "project_guide_task_examples_hash(cast(:examples as jsonb))"
        ), {"examples": json.dumps(examples)})).one()
        assert row == (True, guide["task_examples_hash"])
    for bad in [None, [], examples, [{"content": "\u2003", "title": None, "labels": []}],
                [{"content": "Valid", "title": None, "labels": [], "extra": True}]]:
        async with get_session_factory()() as session, session.begin():
            with pytest.raises(DBAPIError, match="guide task examples are invalid"):
                await session.execute(text(
                    "insert into project_guides(id,project_id,version,status,created_by,task_examples,task_examples_hash) "
                    "values(:id,:project,:version,'draft','test',cast(:examples as json),:hash)"
                ), {"id": str(uuid4()), "project": project["id"], "version": str(uuid4()),
                    "examples": json.dumps(bad), "hash": "sha256:" + "0" * 64 if bad == examples else guide["task_examples_hash"]})
    for sql in ["update project_guides set task_examples='[]'::json where id=:id",
                "update project_guides set task_examples_hash=null where id=:id",
                "delete from project_guides where id=:id", "truncate project_guides cascade"]:
        async with get_session_factory()() as session, session.begin():
            with pytest.raises(DBAPIError, match="guide (task examples are immutable|source evidence cannot be deleted)"):
                await session.execute(text(sql), {"id": guide["id"]})


async def test_same_example_hash_cannot_cross_compose_setup_ownership(project_client):  # noqa: F811
    examples = [{"content": "Same illustrative task in two projects."}]
    projects, guides, snapshots = [], [], []
    for index in range(2):
        project = await create_project(project_client, name=f"Examples {index}")
        response = await _guide(project_client, project["id"], examples)
        assert response.status_code == 201, response.text
        guide = response.json()
        projects.append(project)
        guides.append(guide)
        snapshots.append(await create_source_snapshot(project_client, project["id"], guide["id"]))
    assert guides[0]["task_examples_hash"] == guides[1]["task_examples_hash"]
    async with get_session_factory()() as session, session.begin():
        with pytest.raises(DBAPIError, match="guide setup snapshot ownership mismatch"):
            await session.execute(text(
                "insert into project_setup_runs(id,project_id,guide_id,guide_version,source_snapshot_id,"
                "source_snapshot_hash,setup_generation,status,current_step,created_by) "
                "values(:id,:project,:guide,:version,:snapshot,:hash,99,'awaiting_documents','awaiting_documents','test')"
            ), {"id": str(uuid4()), "project": projects[0]["id"], "guide": guides[0]["id"],
                "version": guides[0]["version"], "snapshot": snapshots[1]["id"], "hash": snapshots[1]["bundle_hash"]})


async def test_source_snapshot_hash_is_server_computed_and_canonical(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    expected_manifest = {
        "schema_version": "guide_source_snapshot.task_examples",
        "task_examples_hash": guide["task_examples_hash"],
        "task_examples_count": len(guide["task_examples"]),
        "snapshot_id": snapshot["id"],
        "generation": 1,
        "items": [
            {
                "item_id": item["id"],
                "item_order": item["item_order"],
                "source_kind": item["source_kind"],
                "source_label": item["source_label"],
                "ingestion_adapter": item["ingestion_adapter"],
                "media_type": item["media_type"],
            }
            for item in snapshot["items"]
        ],
    }
    expected_hash = canonical_json_hash(expected_manifest)

    assert snapshot["manifest_json"] == expected_manifest
    assert snapshot["bundle_hash"] == expected_hash
    assert [item["item_order"] for item in snapshot["items"]] == [0, 1]



async def test_retained_missing_examples_are_visible_and_never_invoke_provider(project_client, monkeypatch):  # noqa: F811
    """Inject retained input state in an isolated fixture; retain all production guards."""
    from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDelivery
    from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
    from app.workers import project_setup as worker

    project = await create_project(project_client)
    response = await _guide(project_client, project["id"], [{"content": "Review one claim."}])
    assert response.status_code == 201, response.text
    guide = response.json()
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    async with get_session_factory()() as session, session.begin():
        setup = (await session.execute(text(
            "select id,setup_generation from project_setup_runs where source_snapshot_id=:id"
        ), {"id": snapshot["id"]})).one()
        task_id = project_guide_compilation_task_id(setup.id, setup.setup_generation)
        await session.execute(text(
            "update project_setup_runs set status='dispatch_pending',current_step='dispatch',celery_task_id=:task where id=:id"
        ), {"id": setup.id, "task": task_id})
        # Only fixture construction can emulate a row predating example storage.
        # The separate immutability test proves this update fails with its guard.
        await session.execute(text("alter table project_guides disable trigger project_guide_task_examples_guard"))
        await session.execute(text("update project_guides set task_examples=null,task_examples_hash=null where id=:id"), {"id": guide["id"]})
        await session.execute(text("set constraints all immediate"))
        await session.execute(text("alter table project_guides enable trigger project_guide_task_examples_guard"))
    constructions = []
    def forbid_provider(configuration):
        constructions.append(configuration)
        raise AssertionError("missing examples reached provider construction")
    monkeypatch.setattr(worker, "create_project_guide_runtime", forbid_provider)
    delivery = ProjectGuideCompilationDelivery(project_id=project["id"], guide_id=guide["id"],
        source_snapshot_id=snapshot["id"], setup_run_id=setup.id,
        setup_generation=setup.setup_generation, task_id=task_id)
    first = await worker._run_project_guide_compilation(delivery)
    assert first["status"] == "setup_input_invalid"
    assert first["error_code"] == "task_examples_missing"
    assert await worker._run_project_guide_compilation(delivery) == first
    assert constructions == []
    diagnostic = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/setup-runs/latest", headers=auth_headers(),
    )
    assert diagnostic.status_code == 200, diagnostic.text
    assert diagnostic.json()["status"] == "setup_input_invalid"
    assert diagnostic.json()["error_code"] == "task_examples_missing"
    new_snapshot = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots",
        headers=auth_headers(), json={"items": [{"source_kind": "document", "source_label": "new.pdf", "ingestion_adapter": "upload", "media_type": "application/pdf"}]},
    )
    assert new_snapshot.status_code == 422, new_snapshot.text
    assert new_snapshot.json()["detail"] == "task_examples_missing"
    async with get_session_factory()() as session:
        assert await session.scalar(text("select count(*) from project_guide_compilation_attempts")) == 0
        assert await session.scalar(text("select count(*) from guide_source_snapshots where guide_id=:id"), {"id": guide["id"]}) == 1


@pytest.mark.parametrize('missing', [False, True])
async def test_unfinished_setup_diagnostic_validates_examples_without_finalization(clean_postgres_database, missing):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.modules.projects.models import ProjectSetupRun
    from app.modules.projects.guide_compilation.diagnostics import compilation_setup_response
    from .helpers import seed_database

    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session, session.begin():
            assert await session.scalar(text('select count(*) from project_guide_setup_finalizations')) == 0
            assert await session.scalar(text('select count(*) from project_guide_compilation_attempts')) == 0
            if missing:
                # Emulate retained pre-example data in an isolated rolled-back fixture.
                await session.execute(text('alter table project_guides disable trigger project_guide_task_examples_guard'))
                await session.execute(text('update project_guides set task_examples=null, task_examples_hash=null where id=:id'),
                                      {'id': str(values['guide'])})
                await session.execute(text('set constraints all immediate'))
                await session.execute(text('alter table project_guides enable trigger project_guide_task_examples_guard'))
            setup = await session.get(ProjectSetupRun, str(values['setup_1']))
            before = setup.status
            response = await compilation_setup_response(session, setup)
            assert response.status == ('setup_input_invalid' if missing else before)
            if missing:
                assert response.error_code == 'task_examples_missing'
                assert response.current_step == 'input_validation'
                assert 'new guide version' in response.error_summary
            assert setup.status == before
            assert await session.scalar(text('select count(*) from project_guide_setup_finalizations')) == 0
            assert await session.scalar(text('select count(*) from project_guide_compilation_attempts')) == 0
            await session.rollback()
    finally:
        await engine.dispose()
