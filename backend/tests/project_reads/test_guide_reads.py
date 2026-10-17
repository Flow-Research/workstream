"""C1, C2, C3 and C9 authority, concealment, pagination and projection through the public API."""

from uuid import UUID

import pytest

from app.core.identifiers import new_record_id
from tests.test_tasks import admit_and_grant_project_submitter, auth_headers, create_active_project, set_dev_actor
from .support import (
    AUDITOR, EXACT_MANAGER, FINANCE, OPERATOR, OWNER, as_admin, as_manager, get_ok, project_path, status_of,
)


def _guides(project, suffix=""):
    return project_path(project, f"/guides{suffix}")


def _routes(project, guide, document):
    """The four guide reads for one project, guide and document."""
    return (
        _guides(project),
        _guides(project, f"/{guide}"),
        _guides(project, f"/{guide}/activation-readiness"),
        _guides(project, f"/{guide}/documents/{document}/content"),
    )


@pytest.fixture
def no_provider(monkeypatch):
    """Fail the read if anything opens the artifact provider; returns the call log."""
    calls = []

    def refuse(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("the artifact provider must not open for this read")

    monkeypatch.setattr("app.adapters.artifacts.create_artifact_store_bootstrap", refuse)
    return calls


async def _project_with_draft(client, monkeypatch, slug):
    """An active project whose v1 guide is active and whose v2 guide is a draft awaiting uploads."""
    from tests.projects.guide_fixtures import complete_guide_payload

    as_manager(monkeypatch)
    project = (await create_active_project(client, slug=slug))["id"]
    created = await client.post(_guides(project), headers=auth_headers(), json=complete_guide_payload("v2"))
    assert created.status_code == 201, created.text
    active = (await get_ok(client, _guides(project), status="active"))["items"]
    assert [item["version"] for item in active] == ["v1"]
    return project, active[0]["guide_id"], created.json()


async def test_guide_list_pages_by_creation_and_binds_the_status_filter(task_client, monkeypatch):
    project, active, draft = await _project_with_draft(task_client, monkeypatch, "guide-list")
    first = await get_ok(task_client, _guides(project), limit=1)
    assert [item["guide_id"] for item in first["items"]] == [active] and first["next_cursor"]
    second = await get_ok(task_client, _guides(project), limit=1, cursor=first["next_cursor"])
    assert [item["guide_id"] for item in second["items"]] == [draft["id"]] and second["next_cursor"] is None
    assert set(first["items"][0]) == {"guide_id", "version", "status", "created_at", "effective_at"}
    assert first["items"][0]["status"] == "active" and first["items"][0]["effective_at"] is not None
    assert second["items"][0] | {"created_at": None} == {
        "guide_id": draft["id"], "version": "v2", "status": "draft", "created_at": None, "effective_at": None,
    }
    assert [item["guide_id"] for item in (await get_ok(task_client, _guides(project), status="draft"))["items"]] == [
        draft["id"]
    ]
    assert (await get_ok(task_client, _guides(project), status="superseded"))["items"] == []
    reused = await task_client.get(
        _guides(project), params={"limit": 1, "status": "draft", "cursor": first["next_cursor"]},
        headers=auth_headers(),
    )
    assert reused.status_code == 422 and reused.json()["error"]["code"] == "project_read_cursor_invalid"
    assert await status_of(task_client, _guides(project), status="retired") == 422


async def test_guide_detail_projects_documents_policies_and_setup_lineage(task_client, monkeypatch, no_provider):
    project, active, draft = await _project_with_draft(task_client, monkeypatch, "guide-detail")
    detail = await get_ok(task_client, _guides(project, f"/{draft['id']}"))
    assert set(detail) == {
        "guide", "documents", "review_policy", "revision_policy", "latest_setup_run_id", "latest_compilation_id",
    }
    assert detail["guide"]["guide_id"] == draft["id"] and detail["guide"]["status"] == "draft"
    assert "task_examples" not in detail["guide"] and detail["guide"]["task_examples_hash"].startswith("sha256:")
    assert [(item["document_id"], item["label"], item["order"]) for item in detail["documents"]] == [
        (item["document_id"], item["label"], item["order"]) for item in draft["documents"]
    ]
    assert {(item["ingest_state"], item["sha256"], item["byte_count"]) for item in detail["documents"]} == {
        ("awaiting_upload", None, None)
    }
    assert detail["latest_setup_run_id"] == draft["setup"]["id"] and detail["latest_compilation_id"] is None
    assert (detail["review_policy"], detail["revision_policy"]) == (None, None)

    current = await get_ok(task_client, _guides(project, f"/{active}"))
    assert current["guide"]["status"] == "active" and current["guide"]["activation_operation_id"]
    review, revision = current["review_policy"], current["revision_policy"]
    assert review["allowed_decisions"] == ["accept", "needs_revision", "reject"]
    assert review["human_review_required"] is True and review["policy_hash"].startswith("sha256:")
    assert revision["max_revision_rounds"] == 7 and revision["allowed_resubmission_states"] == ["needs_revision"]
    assert current["latest_setup_run_id"] and current["latest_compilation_id"]
    assert no_provider == []


async def test_activation_readiness_reports_activations_refusal_over_http(task_client, monkeypatch):
    project, active, draft = await _project_with_draft(task_client, monkeypatch, "guide-readiness")
    waiting = await get_ok(task_client, _guides(project, f"/{draft['id']}/activation-readiness"))
    assert waiting["ready"] is False and (waiting["project_id"], waiting["guide_id"]) == (project, draft["id"])
    assert (waiting["unmet"][0]["code"], waiting["unmet"][0]["reason"]) == (
        "proposal_unavailable", "post_policy_unavailable",
    )
    assert set(waiting["unmet"][0]) == {"code", "reason", "message", "missing_capabilities"}
    activated = await get_ok(task_client, _guides(project, f"/{active}/activation-readiness"))
    assert activated["ready"] is False and activated["unmet"][0]["code"] == "proposal_unavailable"
    # A dry run leaves the guides exactly as they were.
    listed = (await get_ok(task_client, _guides(project)))["items"]
    assert [(item["guide_id"], item["status"]) for item in listed] == [(active, "active"), (draft["id"], "draft")]


async def test_exact_project_manager_reads_and_every_other_role_is_concealed(task_client, monkeypatch, no_provider):
    project, active, draft = await _project_with_draft(task_client, monkeypatch, "guide-authority")
    document = draft["documents"][0]["document_id"]
    as_manager(monkeypatch)
    other = (await create_active_project(task_client, slug="guide-authority-other"))["id"]
    await as_admin(task_client, monkeypatch, EXACT_MANAGER, "project_manager", project=project)
    for path in _routes(project, draft["id"], document)[:3]:
        assert await status_of(task_client, path) == 200, path
    assert await status_of(task_client, _routes(project, draft["id"], document)[3]) == 409
    for path in _routes(other, active, document):
        assert await status_of(task_client, path) == 404, path

    callers = (
        (FINANCE, "finance_authority", project), (OPERATOR, "operator", None), (AUDITOR, "audit_authority", None),
    )
    for subject, role, scope in callers:
        await as_admin(task_client, monkeypatch, subject, role, project=scope)
        for path in _routes(project, draft["id"], document):
            response = await task_client.get(path, headers=auth_headers())
            assert response.status_code == 404, (subject, path, response.text)
            assert response.json()["error"]["code"] == "project_authorization_resource_not_found"
    as_manager(monkeypatch)
    await admit_and_grant_project_submitter(task_client, monkeypatch, project, OWNER)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    for path in _routes(project, draft["id"], document):
        assert await status_of(task_client, path) == 404, path
    assert no_provider == []


async def test_guide_or_document_outside_the_project_is_concealed(task_client, monkeypatch, no_provider):
    project, active, draft = await _project_with_draft(task_client, monkeypatch, "guide-conceal")
    foreign, foreign_active, foreign_draft = await _project_with_draft(task_client, monkeypatch, "guide-conceal-b")
    document = draft["documents"][0]["document_id"]
    as_manager(monkeypatch)
    absent = str(new_record_id())
    for guide, selected in ((foreign_draft["id"], foreign_draft["documents"][0]["document_id"]), (absent, document)):
        for path in _routes(project, guide, selected)[1:]:
            response = await task_client.get(path, headers=auth_headers())
            assert response.status_code == 404, (path, response.text)
            assert response.json()["error"]["code"] == "project_authorization_resource_not_found"
    # A document of another guide in the same project is not a document of this guide.
    assert await status_of(task_client, _guides(project, f"/{active}/documents/{document}/content")) == 404
    assert await status_of(task_client, _guides(project, f"/{draft['id']}/documents/{absent}/content")) == 404
    missing = await task_client.get(_guides(project, f"/{draft['id']}/documents/{document}/content"), headers=auth_headers())
    assert missing.status_code == 409 and missing.json()["error"]["code"] == "guide_document_not_uploaded"
    for path in _routes(absent, active, document):
        assert await status_of(task_client, path) == 404, path
    assert foreign_active and no_provider == []


async def test_each_guide_read_records_one_allowed_authorization_decision(task_client, monkeypatch):
    from sqlalchemy import select

    from app.db import session as db_session
    from app.modules.tasks.models import AuditEvent

    project, active, _draft = await _project_with_draft(task_client, monkeypatch, "guide-audit")
    as_manager(monkeypatch)
    actions = (
        ("project.guide.list", _guides(project)),
        ("project.guide.read", _guides(project, f"/{active}")),
        ("project.guide.activation_readiness.read", _guides(project, f"/{active}/activation-readiness")),
    )

    async def decisions(action):
        async with db_session.get_session_factory()() as session:
            return (await session.scalars(
                select(AuditEvent).where(AuditEvent.action_id == action).order_by(AuditEvent.created_at)
            )).all()

    for action, path in actions:
        before = len(await decisions(action))
        assert await status_of(task_client, path) == 200
        rows = await decisions(action)
        assert len(rows) == before + 1, action
        assert (rows[-1].event_type, rows[-1].permission_id) == ("SensitiveAuthorizationAllowed", "project.guide.manage")
        assert rows[-1].matched_grant_id is not None and UUID(str(rows[-1].project_id)) == UUID(project)


async def test_guide_list_keeps_a_superseded_guide_after_its_successor_activates(task_client, monkeypatch):
    from app.db import session as db_session
    from tests.project_create_fixtures import seed_active_guide_for_downstream_test
    from tests.test_tasks import create_policy_bundle_for_guide

    project, first, draft = await _project_with_draft(task_client, monkeypatch, "guide-superseded")
    await create_policy_bundle_for_guide(task_client, project, draft["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(), project_id=project, guide_id=draft["id"],
    )
    listed = (await get_ok(task_client, _guides(project)))["items"]
    assert [(item["guide_id"], item["status"]) for item in listed] == [(first, "superseded"), (draft["id"], "active")]
    assert listed[0]["effective_at"] is not None
    superseded = (await get_ok(task_client, _guides(project), status="superseded"))["items"]
    assert [item["guide_id"] for item in superseded] == [first]
    assert [item["guide_id"] for item in (await get_ok(task_client, _guides(project), status="active"))["items"]] == [
        draft["id"]
    ]
    assert (await get_ok(task_client, _guides(project, f"/{first}")))["guide"]["status"] == "superseded"
