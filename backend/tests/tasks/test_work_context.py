"""Current work-context contracts and real authorized PostgreSQL projections."""

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime
import re
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.db import session as db_session
from app.main import create_app
from app.modules.projects.api.guide_activation_context import GuidePolicySelection
from app.modules.projects.api.locked_policy import GuideDisplayFacts, ProjectDisplayFacts
from app.modules.tasks.api import (
    ContributorTaskDetail,
    ManagementTaskDetail,
    TaskCompensationTerms,
)
from app.modules.tasks.schemas import (
    ContributorTaskLifecycle, ContributorTaskWorkContext, ManagementTaskWorkContext,
)
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.authorized_commands import TaskRevisionRepairError
from app.modules.tasks.api.authorization import TaskAuthorityFacts, TaskAuthorityOperation, TaskAuthorityDenied
from app.core.hashing import canonical_json_hash
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import AuditEvent, TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService, TaskValidationError
from app.modules.tasks import schemas
from app.modules.tasks.schemas import TaskRevisionRepairRequest
from app.modules.tasks.api.revision import RevisionCandidate, RevisionContextSnapshot
from app.modules.tasks.revision.service import candidate_from_packet
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_ready_task, create_draft_task, create_started_task,
    admit_and_grant_project_submitter, set_dev_actor, auth_headers,
)

COMMON = {"task_id", "project_id", "title", "description", "task_type", "difficulty", "skill_tags",
          "estimated_time_minutes", "status", "acceptance_criteria", "rejection_criteria",
          "deadline_at", "created_at", "updated_at"}
MANAGEMENT = {"source_type", "source_ref", "source_payload_hash", "import_batch_id", "external_task_id",
              "created_by", "assigned_to"}
CONTRIBUTOR = COMMON | {"compensation"}
CONTEXT = {"task", "project", "guide", "review_policy", "revision_policy", "contribution_policy_version_id"}
ACTIONS = ("task.work_context.read", "project.task.work_context.read")


def context_values():
    project_id, now = new_record_id(), datetime.now(UTC)
    task = ContributorTaskDetail(
        new_record_id(), project_id, "Title", "Work", None, None, ("tag",), None,
        "in_progress", None, None, None, now, now,
        TaskCompensationTerms(new_record_id(), "unpaid", "unpaid"),
    )
    selection = GuidePolicySelection(policy_id=new_record_id(), generation=1, policy_hash="sha256:" + "1" * 64)
    values = dict(project=ProjectDisplayFacts(project_id, "Project", "project", None),
                  guide=GuideDisplayFacts(new_record_id(), project_id, "guide", None, now),
                  review_policy=selection, revision_policy=selection, contribution_policy_version_id=new_record_id())
    task_values = asdict(task)
    task_values.pop("compensation")
    manager = ManagementTaskDetail(**task_values, source_type="manual", source_ref="private",
                                   source_payload_hash=None, import_batch_id=None, external_task_id=None,
                                   created_by="creator", assigned_to="owner")
    return task, manager, values


def test_work_context_contracts():
    task, manager, values = context_values()
    lifecycle = ContributorTaskLifecycle(assigned_to_current_actor=True, next_actions=())
    for cls, detail, extra in (
        (ContributorTaskWorkContext, task, {"lifecycle": lifecycle, "guide_documents": ()}),
        (ManagementTaskWorkContext, manager, {}),
    ):
        result = cls(task=detail, **values, **extra)
        assert type(result.task) is type(detail)
        assert not hasattr(result.task, "_sa_instance_state")
        with pytest.raises(ValidationError, match="frozen"):
            result.contribution_policy_version_id = new_record_id()
        with pytest.raises(FrozenInstanceError):
            result.task.title = "changed"
        for replacement in (
            {"task": manager if detail is task else task},
            {"task": replace(detail, project_id=new_record_id())},
            {"project": replace(values["project"], id=new_record_id())},
            {"guide": replace(values["guide"], project_id=new_record_id())},
            {"contribution_policy_version_id": "invalid"},
        ):
            with pytest.raises(ValidationError):
                cls(**(dict(task=detail, **values, **extra) | replacement))
        for kind in ("review_policy", "revision_policy"):
            for field, invalid in (("policy_id", "invalid"), ("generation", 0), ("policy_hash", "invalid")):
                with pytest.raises(ValidationError):
                    cls(**(dict(task=detail, **values, **extra) | {
                        kind: values[kind].model_dump() | {field: invalid},
                    }))
        subclass = type("UnexpectedTaskDetail", (type(detail),), {})
        subclass_values = asdict(detail)
        if isinstance(detail, ContributorTaskDetail):
            subclass_values["compensation"] = detail.compensation
        with pytest.raises(ValidationError, match="work context task is invalid"):
            cls(task=subclass(**subclass_values), **values, **extra)
        with pytest.raises(ValidationError, match="extra_forbidden"):
            cls(task=detail, **values, **extra, base_amount=25)
    for extra in ({"next_actions": ("submit",)}, {"next_actions": ("start",)}, {"next_actions": ("claim", "start")},
                  {"assigned_to_current_actor": []}, {"can_submit": True}, {"status": "in_progress"}):
        with pytest.raises(ValidationError):
            ContributorTaskLifecycle(**(lifecycle.model_dump() | extra))
    with pytest.raises(ValidationError, match="frozen"):
        lifecycle.next_actions = ()
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ManagementTaskWorkContext(task=manager, **values, lifecycle=lifecycle)


def test_work_context_openapi():
    schema = create_app().openapi()
    definitions = schema["components"]["schemas"]
    for route, name, fields, action in (
        ("/api/v1/tasks/{task_id}/work-context", "ContributorTaskWorkContext", CONTEXT | {"lifecycle", "guide_documents", "revision_context"}, ACTIONS[0]),
        ("/api/v1/projects/{project_id}/tasks/{task_id}/work-context", "ManagementTaskWorkContext", CONTEXT, ACTIONS[1]),
    ):
        operation = schema["paths"][route]["get"]
        assert operation["x-workstream-action-id"] == action
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": f"#/components/schemas/{name}"}
        assert set(definitions[name]["properties"]) == fields
        assert definitions[name]["additionalProperties"] is False
    assert set(definitions["ContributorTaskDetail"]["properties"]) == CONTRIBUTOR | {"last_assignment_outcome"}
    assert set(definitions["ManagementTaskDetail"]["properties"]) == COMMON | MANAGEMENT | {
        "last_assignment_outcome", "revision_context",
    }
    for name, field, target in (
        ("ContributorTaskDetail", "last_assignment_outcome", "TaskAssignmentOutcome"),
        ("ManagementTaskDetail", "last_assignment_outcome", "TaskAssignmentOutcome"),
        ("ManagementTaskDetail", "revision_context", "ContributorRevisionContext"),
    ):
        nullable = definitions[name]["properties"][field]
        assert nullable["anyOf"] == [{"$ref": f"#/components/schemas/{target}"}, {"type": "null"}]
        assert field not in definitions[name].get("required", [])
    assert set(definitions["TaskAssignmentOutcome"]["properties"]) == {
        "assignment_id", "submission_id", "status", "status_reason", "closed_at", "next_action",
    }
    assert definitions["TaskAssignmentOutcome"]["additionalProperties"] is False
    assert set(definitions["ContributorTaskLifecycle"]["properties"]) == {"assigned_to_current_actor", "next_actions"}
    assert set(definitions["GuidePolicySelection"]["properties"]) == {"policy_id", "generation", "policy_hash"}
    assert definitions["ContributorTaskWorkContext"]["properties"]["contribution_policy_version_id"]["format"] == "uuid"
    assert "TaskWorkContextResponse" not in definitions


async def test_work_context_invalid_selectors():
    session, authority = MagicMock(), MagicMock()
    commands = AuthorizedTaskCommands(session, authorization=authority, audit=MagicMock(),
                                      actor_profile_id=new_record_id(), contexts=MagicMock(), guide_documents=MagicMock())
    for invalid in (None, "not-a-uuid", str(new_record_id()), []):
        with pytest.raises(TaskValidationError):
            await commands.contributor_work_context(invalid)
        for args in ((invalid, new_record_id()), (new_record_id(), invalid)):
            with pytest.raises(TaskValidationError):
                await commands.management_work_context(*args)
    session.begin.assert_not_called()
    session.execute.assert_not_called()
    authority.prepare.assert_not_called()


async def decisions(session, task_id):
    project_id = await session.scalar(select(WorkstreamTask.project_id).where(WorkstreamTask.id == task_id))
    return list(await session.scalars(select(AuditEvent).where(
        AuditEvent.project_id == project_id, AuditEvent.resource_type == "project",
        AuditEvent.resource_id == project_id, AuditEvent.action_id.in_(ACTIONS),
    )))


async def snapshot(factory, task_id):
    async with factory() as session:
        state = []
        for model, predicate in (
            (WorkstreamTask, WorkstreamTask.id == task_id),
            (TaskAssignment, TaskAssignment.task_id == task_id),
            (TaskCommandReceipt, TaskCommandReceipt.task_id == task_id),
            (AuditEvent, (AuditEvent.entity_type == "task") & (AuditEvent.entity_id == task_id)),
        ):
            rows = (await session.execute(select(*model.__table__.c).where(predicate).order_by(model.id))).mappings().all()
            state.append([dict(row) for row in rows])
        return state, {event.id for event in await decisions(session, task_id)}


async def test_work_context_public_projections(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "context-owner")
    claimed = await task_client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        row = await session.get(WorkstreamTask, task["id"])
        row.source_ref = row.source_payload_hash = row.import_batch_id = row.external_task_id = "PRIVATE"
        row.deadline_at = datetime(2030, 1, 1, tzinfo=UTC)
    for management in (True, False):
        set_dev_actor(monkeypatch, roles="project_manager" if management else "viewer",
                      subject="project-manager-subject" if management else "context-owner")
        actor = await task_client.get("/api/v1/actors/me", headers=auth_headers())
        assert actor.status_code == 200, actor.text
        path = f"/api/v1/projects/{project['id']}" if management else "/api/v1"
        before, previous = await snapshot(factory, task["id"])
        stored = before[0][0]
        assert stored["source_ref"] == "PRIVATE"
        assert stored["assigned_to"] == grant["actor_profile_id"] and stored["status"] == "in_progress"
        response = await task_client.get(f"{path}/tasks/{task['id']}/work-context", headers=auth_headers())
        assert response.status_code == 200, response.text
        body = response.json()
        fields = (COMMON | MANAGEMENT) if management else CONTRIBUTOR
        assert set(body) == CONTEXT | (set() if management else {"lifecycle", "guide_documents"})
        # Initial work has no revision preparation. The public route
        # excludes None; prepared revision contexts are covered by their journey.
        assert "revision_context" not in body
        assert set(body["task"]) == fields
        for name in fields - {"created_at", "updated_at", "deadline_at", "compensation"}:
            assert body["task"][name] == stored["id" if name == "task_id" else name], name
        for name in ("created_at", "updated_at", "deadline_at"):
            assert datetime.fromisoformat(body["task"][name]) == stored[name]
        if not management:
            assert body["lifecycle"] == {
                "assigned_to_current_actor": True,
                "next_actions": [],
            }
            assert body["task"]["compensation"] == {
                "contribution_policy_version_id": str(
                    stored["locked_contribution_policy_version_id"]
                ),
                "accepted_submission": "unpaid",
                "completed_review": "unpaid",
            }
            assert "PRIVATE" not in response.text
        for kind in ("review", "revision"):
            assert body[f"{kind}_policy"] == {
                "policy_id": stored[f"locked_{kind}_policy_id"],
                "generation": stored[f"locked_{kind}_policy_generation"],
                "policy_hash": stored[f"locked_{kind}_policy_hash"],
            }
        assert body["contribution_policy_version_id"] == str(stored["locked_contribution_policy_version_id"])
        after, current = await snapshot(factory, task["id"])
        assert after == before and len(current - previous) == 1
        async with factory() as session:
            event = await session.get(AuditEvent, next(iter(current - previous)))
            assert (event.action_id, event.project_id, event.resource_id, event.actor_id) == (
                ACTIONS[int(management)], project["id"], project["id"], actor.json()["actor_profile_id"],
            )
            assert event.resource_type == "project"
            assert set(event.after_facts) == {"allowed", "resource_context_digest"}
            assert event.after_facts["allowed"] is True
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", event.after_facts["resource_context_digest"])


async def test_work_context_owned_state_matrix(task_client, monkeypatch):
    project = await create_active_project(task_client)
    draft = await create_draft_task(task_client, project["id"])
    states = {state for edge in ALLOWED_TASK_TRANSITIONS for state in edge}
    assert states == {"draft", "screening", "ready", "in_progress", "submitted", "evaluation_pending", "review_pending", "needs_revision"}
    tasks = {state: await create_ready_task(task_client, project["id"]) for state in sorted(states)}
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "worker-one")
    denied = await task_client.get(f"/api/v1/tasks/{draft['id']}/work-context", headers=auth_headers())
    assert denied.status_code == 404 and denied.json()["error"]["code"] == "project_authorization_resource_not_found"
    factory, seen = db_session.get_session_factory(), set()
    seen_tasks = set()
    for state in ("needs_revision", "ready", *sorted(states - {"needs_revision", "ready"})):
        task = tasks[state]
        claim = await task_client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
        assert claim.status_code == 200, claim.text
        assignment_id = claim.json()["assignment"]["id"]
        assert claim.json()["task"]["status"] == "in_progress"
        seen_tasks.add(task["id"])
        async with factory() as session, session.begin():
            row = await session.get(WorkstreamTask, task["id"])
            assert row.locked_contribution_policy_version_id is not None
            row.status = state  # Projection fixture only; preserves full locked custody and active assignment.
        async with factory() as session:
            row = await session.get(WorkstreamTask, task["id"])
            assignment = await session.get(TaskAssignment, assignment_id)
            assert assignment.task_id == row.id
            assert row.status == state and assignment.status == "active"
            assert row.assigned_to == assignment.contributor_id == grant["actor_profile_id"]
            assert row.locked_contribution_policy_version_id == assignment.submitter_contribution_policy_version_id
        response = await task_client.get(f"/api/v1/tasks/{task['id']}/work-context", headers=auth_headers())
        assert response.status_code == 200, (state, response.text)
        body = response.json()
        assert body["task"]["status"] == state
        assert body["lifecycle"] == {"assigned_to_current_actor": True, "next_actions": []}
        seen.add(body["task"]["status"])
    assert seen == states and len(seen_tasks) == len(states) == 8


@pytest.mark.parametrize("management", (False, True))
async def test_work_context_projection_failure_rolls_back(task_client, monkeypatch, management):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    if management:
        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    factory = db_session.get_session_factory()
    before, previous = await snapshot(factory, task["id"])
    actor = await task_client.get("/api/v1/actors/me", headers=auth_headers())
    assert actor.status_code == 200, actor.text
    captured = []

    async def unavailable(owner, request):
        assert request.task_id == UUID(task["id"]) and request.project_id == UUID(project["id"])
        detail = await original(owner, request)
        assert type(detail) is (ManagementTaskDetail if management else ContributorTaskDetail)
        assert detail.task_id == UUID(task["id"]) and detail.project_id == UUID(project["id"])
        staged = [event for event in await decisions(owner._session, task["id"]) if event.id not in previous]
        assert len(staged) == 1 and staged[0].after_facts["allowed"] is True
        assert staged[0].action_id == ACTIONS[int(management)] and staged[0].project_id == project["id"]
        assert staged[0].actor_id == actor.json()["actor_profile_id"]
        captured.append(staged[0].id)
        return None

    method = "read_management_task_detail" if management else "read_contributor_task_detail"
    original = getattr(TaskRepository, method)
    monkeypatch.setattr(TaskRepository, method, unavailable)
    path = f"/api/v1/projects/{project['id']}" if management else "/api/v1"
    response = await task_client.get(f"{path}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "resource_not_found"
    assert response.json()["error"]["retryable"] is False
    assert len(captured) == 1
    after, current = await snapshot(factory, task["id"])
    assert after == before and current == previous
    async with factory() as session:
        assert await session.get(AuditEvent, captured[0]) is None


async def test_work_context_project_scope(task_client):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-context")
    task = await create_ready_task(task_client, foreign["id"])
    factory = db_session.get_session_factory()
    before, _ = await snapshot(factory, task["id"])
    assert before[0][0]["project_id"] == foreign["id"]
    valid = await task_client.get(f"/api/v1/projects/{foreign['id']}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert valid.status_code == 200, valid.text
    before, previous = await snapshot(factory, task["id"])
    denied = await task_client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert denied.status_code == 404 and denied.json()["error"]["code"] == "resource_not_found"
    assert await snapshot(factory, task["id"]) == (before, previous)


async def test_work_context_missing_locked_context(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    before, previous = await snapshot(factory, task["id"])
    loader = TaskService._load_locked_task_context
    staged_ids = []

    async def observe_authorized_custody(owner, row):
        staged = [event for event in await decisions(owner._session, row.id) if event.id not in previous]
        assert len(staged) == 1 and staged[0].after_facts["allowed"] is True
        assert staged[0].action_id == ACTIONS[1] and staged[0].project_id == project["id"]
        staged_ids.append(staged[0].id)
        return await loader(owner, row)

    monkeypatch.setattr(TaskService, "_load_locked_task_context", observe_authorized_custody)
    response = await task_client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert len(staged_ids) == 1
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "task_locked_context_invalid"
    assert "locked_guide_version" in response.json()["error"]["details"]["missing_fields"]
    assert await snapshot(factory, task["id"]) == (before, previous)


def test_work_context_obsolete_symbols_absent():
    for name in ("TaskProjectContext", "TaskWorkerTaskContext", "TaskGuideContext", "TaskReviewPolicyContext",
                 "TaskRevisionPolicyContext", "TaskWorkerLifecycleContext", "TaskWorkContextResponse"):
        assert not hasattr(schemas, name)
    assert not hasattr(TaskService, "_work_context_response")
    assert not hasattr(TaskService, "_worker_safe_task_response")
    assert not hasattr(AuthorizedTaskCommands, "work_context")


def test_revision_repair_request_requires_exact_parent_and_bounded_reason():
    values = dict(parent_preparation_id=new_record_id(),
                  parent_preparation_sha256="sha256:" + "a" * 64, reason="Correct context")
    assert TaskRevisionRepairRequest(**values).reason == "Correct context"
    assert TaskRevisionRepairRequest(routing_manifest_id=new_record_id(), reason="Recover root").routing_manifest_id
    for change in ({"parent_preparation_id": "not-a-uuid"},
                   {"parent_preparation_sha256": "sha256:invalid"},
                   {"reason": "  "}, {"reason": "😀" * 251}, {"extra": "unexpected"},
                   {"routing_manifest_id": new_record_id()}):
        with pytest.raises(ValidationError):
            TaskRevisionRepairRequest(**(values | change))
    with pytest.raises(ValidationError):
        TaskRevisionRepairRequest(reason="Missing source")


def test_revision_repair_decodes_serialized_strict_source_lineage():
    from asyncpg.pgproto.pgproto import UUID as DriverUUID
    from app.modules.tasks.revision.service import project_revision

    lineage = {
        name: new_record_id() if name.endswith("_id") else 1 if name.endswith("_generation")
        else "sha256:" + "a" * 64 if name.endswith("_hash") else "v1"
        for name in schemas.TaskPolicyLineage.model_fields
    }
    source = RevisionContextSnapshot(
        guide_id=new_record_id(), activation_operation_id=new_record_id(),
        activation_generation=1, activated_at=datetime.now(UTC),
        lineage=schemas.TaskPolicyLineage(**lineage),
    )
    candidate = RevisionCandidate(
        prior=source, target=source, target_post_policy_json="{}",
        max_revision_rounds=2, revision_deadline_hours=24, target_max_revision_rounds=2,
    )
    packet = {"candidate": candidate.model_dump(mode="json")}
    with pytest.raises(ValidationError):
        RevisionCandidate.model_validate(packet["candidate"])
    assert candidate_from_packet(packet) == candidate
    preparation_id, predecessor_id, manifest_id, submission_id = (new_record_id() for _ in range(4))
    row = SimpleNamespace(
        id=DriverUUID(str(preparation_id)), predecessor_id=DriverUUID(str(predecessor_id)),
        routing_manifest_id=DriverUUID(str(manifest_id)), submission_id=str(submission_id),
        preparation_sha256="sha256:" + "b" * 64, packet=packet, sequence=2,
        next_revision_round=1, max_revision_rounds=2, requested_at=datetime.now(UTC),
        deadline_at=datetime.max.replace(tzinfo=UTC), outcome="kept", blocked_reason=None,
    )
    view = project_revision(row, datetime.now(UTC))
    assert (view.preparation_id, view.predecessor_preparation_id,
            view.source_routing_manifest_id, view.source_submission_id) == (
                preparation_id, predecessor_id, manifest_id, submission_id,
            )
    assert type(view.preparation_id) is UUID


@pytest.mark.parametrize(("disposition", "expected"), [
    ("ready", "context_blocked"),
    ("context_blocked", "context_blocked"),
    ("revision_deadline_expired", "revision_deadline_expired"),
    ("revision_limit_reached", "revision_limit_reached"),
])
async def test_revision_projection_stale_source_preserves_deadline_and_limit_priority(
    monkeypatch, disposition, expected,
):
    from app.modules.tasks.revision.service import project_current_revision

    row = SimpleNamespace(id=new_record_id())

    class Session:
        calls = 0

        async def execute(self, *_args, **_kwargs):
            self.calls += 1
            return SimpleNamespace(all=lambda: [(row.id, False)])

        async def scalar(self, *_args, **_kwargs):
            self.calls += 1
            return datetime.now(UTC)

    view = SimpleNamespace(disposition=disposition)
    view.model_copy = lambda *, update: SimpleNamespace(disposition=update["disposition"])
    monkeypatch.setattr("app.modules.tasks.revision.service.project_revision", lambda *_: view)
    session = Session()
    result = await project_current_revision(session, row)
    assert result.disposition == expected
    assert session.calls == 2


class _RevisionRepairSession:
    def __init__(self, parent, child, now):
        self.parent, self.child, self.now = parent, child, now
        self.scalar_calls = 0

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def scalar(self, _):
        self.scalar_calls += 1
        return self.child if self.scalar_calls == 1 else self.now

    async def get(self, *_):
        return self.parent


@pytest.mark.parametrize("case", ["replay", "denied", "changed_head", "expired"])
async def test_revision_repair_replay_and_current_source_failures(monkeypatch, case):
    project_id, task_id, actor_id = new_record_id(), new_record_id(), new_record_id()
    assignment_id, contributor_id, submission_id = new_record_id(), new_record_id(), new_record_id()
    parent_id, child_id, manifest_id, key = (new_record_id() for _ in range(4))
    now = datetime.now(UTC)
    request = TaskRevisionRepairRequest(
        parent_preparation_id=parent_id, parent_preparation_sha256="sha256:" + "a" * 64,
        reason="Recover current revision context",
    )
    digest = canonical_json_hash({
        "project_id": str(project_id), "task_id": str(task_id),
        "parent_preparation_id": str(parent_id),
        "parent_preparation_sha256": request.parent_preparation_sha256,
        "reason": request.reason,
    })
    parent = SimpleNamespace(
        id=parent_id, project_id=str(project_id), task_id=str(task_id),
        preparation_sha256=request.parent_preparation_sha256,
        routing_manifest_id=manifest_id, assignment_id=str(assignment_id),
        contributor_id=str(contributor_id), submission_id=str(submission_id),
        next_revision_round=1, source_submission_version=1, blocked_reason=None,
        deadline_at=now if case == "expired" else datetime.max.replace(tzinfo=UTC),
    )
    child = SimpleNamespace(
        id=child_id, project_id=str(project_id), task_id=str(task_id),
        predecessor_id=parent_id, routing_manifest_id=manifest_id,
        repair_request_digest=digest, repair_reason=request.reason,
        repair_authority_context={}, assignment_id=str(assignment_id),
        submission_id=str(submission_id), created_at=now,
    ) if case in {"replay", "denied"} else None
    task = SimpleNamespace(id=str(task_id), project_id=str(project_id),
                           assigned_to=str(contributor_id), status="submitted" if child else "needs_revision")
    assignment = SimpleNamespace(id=str(assignment_id), contributor_id=str(contributor_id),
                                 status="active", accepted_at=now, released_at=None)
    latest = SimpleNamespace(id=str(submission_id), task_assignment_id=str(assignment_id),
                             contributor_id=str(contributor_id), version=1)
    manifest = SimpleNamespace(id=manifest_id, routing_recommendation="needs_revision",
                               assignment_id=str(assignment_id), contributor_id=str(contributor_id),
                               submission_version=1)
    session = _RevisionRepairSession(parent, child, now)
    commands = AuthorizedTaskCommands.__new__(AuthorizedTaskCommands)
    commands._session, commands._actor_id = session, actor_id
    commands._repo = SimpleNamespace(
        lock_project_task=AsyncMock(return_value=task),
        lock_accepted_assignment=AsyncMock(return_value=assignment),
        get_latest_submission_for_task=AsyncMock(return_value=latest),
        read_routing_manifest=AsyncMock(return_value=manifest),
    )
    commands._facts = lambda *_: TaskAuthorityFacts(
        TaskAuthorityOperation.REVISION_REPAIR, task_id, project_id, actor_id, task.status,
        contributor_id, assignment_id, contributor_id, "sha256:" + "b" * 64,
    )
    commands._authorize_facts = AsyncMock(side_effect=TaskAuthorityDenied("denied")
                                         if case == "denied" else None)
    commands._audit = SimpleNamespace(record_revision_repair=AsyncMock())
    projection = AsyncMock(return_value="current-eligibility")
    monkeypatch.setattr("app.modules.tasks.authorized_commands.project_current_revision", projection)
    monkeypatch.setattr("app.modules.tasks.authorized_commands.head_for_source",
                        AsyncMock(return_value=parent if case != "changed_head" else SimpleNamespace(id=new_record_id())))
    if case == "replay":
        assert await commands.repair_revision_context(project_id, task_id, request, idempotency_key=key) == "current-eligibility"
        projection.assert_awaited_once_with(session, child)
        commands._authorize_facts.assert_awaited_once()
        commands._repo.read_routing_manifest.assert_not_awaited()
        commands._audit.record_revision_repair.assert_not_awaited()
    elif case == "denied":
        with pytest.raises(TaskAuthorityDenied):
            await commands.repair_revision_context(project_id, task_id, request, idempotency_key=key)
        commands._audit.record_revision_repair.assert_not_awaited()
    else:
        with pytest.raises(TaskRevisionRepairError) as caught:
            await commands.repair_revision_context(project_id, task_id, request, idempotency_key=key)
        assert caught.value.code == ("revision_context_changed" if case == "changed_head"
                                     else "revision_deadline_expired")
        commands._authorize_facts.assert_awaited_once()
        commands._audit.record_revision_repair.assert_not_awaited()
