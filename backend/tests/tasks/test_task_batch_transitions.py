"""Public complete-member transitions with actual PostgreSQL, AUTH and source bytes."""

import asyncio
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.models import AdminRoleGrant
from app.modules.authorization.runtime import ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus
from app.modules.projects.models import ProjectGuide
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.models import AuditEvent, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.service import TaskService, TaskValidationError
from app.modules.tasks.task_batch_transition.models import TaskBatchTransitionMember, TaskBatchTransitionReceipt
from app.modules.tasks.task_batch_transitions import TaskBatchTransitionCommands
from app.modules.tasks.task_batch_transitions import _membership_digest
from app.modules.tasks.task_import_membership import TaskImportMembership
from tests.authorization.guide_activation.pg_support import revoke_manager_grant
from tests.test_task_import_sources import import_source_client as import_source_client
from tests.test_tasks import (
    task_database_env as task_database_env,
    auth_headers,
    complete_guide_payload,
    create_active_project,
    create_policy_bundle_for_guide,
    seed_active_guide_for_downstream_test,
)
from tests.tasks.test_task_import_batches import _batch_path, _verified_source, _project
from tests.tasks.test_task_import_contract import document


async def _import(client, count=2):
    """Create actual retained bytes and native membership with screenable instructions."""
    project = (await create_active_project(client, slug="bulk-" + uuid4().hex))["id"]
    value = document(count)
    for row in value["tasks"]:
        row.update(acceptance_criteria="Accurate, complete work", rejection_criteria="Incomplete work")
    source = await _verified_source(client, project, value)
    imported = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    return project, imported.json()


def _path(project, batch, operation):
    return f"{_batch_path(project)}/{batch['batch_id']}/{operation}"


async def _success_facts(project):
    """Observe committed success identities rather than relying on response status alone."""
    async with db_session.get_session_factory()() as session:
        task_ids = list(await session.scalars(select(WorkstreamTask.id).where(WorkstreamTask.project_id == project)))
        tasks = list((await session.execute(select(
            WorkstreamTask.id, WorkstreamTask.status, WorkstreamTask.locked_guide_version,
            WorkstreamTask.locked_contribution_policy_version_id,
            WorkstreamTask.task_size, WorkstreamTask.locked_submission_award_definition_id,
        ).where(WorkstreamTask.project_id == project).order_by(WorkstreamTask.id))).all())
        roots = set(await session.scalars(select(TaskBatchTransitionReceipt.id).where(TaskBatchTransitionReceipt.project_id == project)))
        members = set(await session.scalars(select(TaskBatchTransitionMember.id).where(TaskBatchTransitionMember.project_id == project)))
        receipts = set(await session.scalars(select(TaskCommandReceipt.id).where(
            TaskCommandReceipt.task_id.in_(task_ids), TaskCommandReceipt.action_id.in_(["project.task.screen", "project.task.release"]),
        )))
        lifecycle = set(await session.scalars(select(AuditEvent.id).where(
            AuditEvent.entity_id.in_(task_ids), AuditEvent.event_type.in_(["TaskScreened", "TaskReleased"]),
        )))
        allows = set(await session.scalars(select(AuditEvent.id).where(
            AuditEvent.resource_type == "project", AuditEvent.resource_id == project,
            AuditEvent.event_type == "SensitiveAuthorizationAllowed",
            AuditEvent.action_id.in_(["project.task.screen", "project.task.release"]),
        )))
        return tasks, roots, members, receipts, lifecycle, allows


@pytest.mark.parametrize("mode", ["single", "bulk"])
async def test_optional_criteria_survive_public_import_screen_release(import_source_client, mode):
    """Guide-governed briefs need no invented task-local acceptance text."""
    client = import_source_client
    project = (await create_active_project(client, slug="optional-" + uuid4().hex))["id"]
    value = document(3)
    for row in value["tasks"]:
        row["title"] = "Repair the supplied Python worker"
        row["description"] = "Investigate the intermittent crash and repair the supplied worker."
    value["tasks"][1]["acceptance_criteria"] = None
    supplied = "Preserve the documented billing rules."
    value["tasks"][2]["acceptance_criteria"] = supplied
    source = await _verified_source(client, project, value)
    imported = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    batch = imported.json()
    task_ids = [row["id"] for row in batch["tasks"]]
    async with db_session.get_session_factory()() as session:
        guide = (await session.scalars(select(ProjectGuide).where(
            ProjectGuide.project_id == project, ProjectGuide.status == "active",
        ))).one()
        expected_guide = guide.version
        expected_policy = guide.contribution_policy_version_id
    assert expected_policy is not None

    for operation, status in (("screen", "screening"), ("release", "ready")):
        paths = ([_path(project, batch, operation)] if mode == "bulk" else
                 [f"/api/v1/tasks/{task_id}/{operation}" for task_id in task_ids])
        for path in paths:
            key, payload = auth_headers(), {"reason": "Approve briefs under the project guide"}
            result = await client.post(path, headers=key, json=payload)
            assert result.status_code == 200, result.text
            before = await _success_facts(project)
            replay = await client.post(path, headers=key, json=payload)
            assert replay.status_code == 200 and replay.json() == result.json(), replay.text
            after = await _success_facts(project)
            assert before[:-1] == after[:-1]
            assert len(after[-1] - before[-1]) == (3 if mode == "bulk" else 1)
        async with db_session.get_session_factory()() as session:
            for task_id, criteria in zip(task_ids, [None, None, supplied], strict=True):
                task = await session.get(WorkstreamTask, task_id)
                assert task.status == status
                assert task.acceptance_criteria == criteria
                assert task.locked_guide_version == expected_guide
                assert task.locked_contribution_policy_version_id == expected_policy
    facts = await _success_facts(project)
    assert len(facts[3]) == len(facts[4]) == 6


@pytest.mark.parametrize("count", [200, 500])
async def test_public_source_import_screen_release_complete_journey(
    import_source_client, count, record_property, monkeypatch,
):
    """Every exact native member reaches READY with original ordered retained receipts."""
    client = import_source_client
    project, batch = await _import(client, count)
    for operation, status in (("screen", "screening"), ("release", "ready")):
        key, payload = auth_headers(), {"reason": "Explicit complete-batch decision"}
        started = time.monotonic()
        result = await client.post(_path(project, batch, operation), headers=key, json=payload)
        record_property(f"{count}_{operation}_seconds", time.monotonic() - started)
        assert result.status_code == 200, result.text
        original = result.json()
        assert original["project_id"] == project and original["batch_id"] == batch["batch_id"]
        assert original["operation"] == operation and original["row_count"] == count
        assert [row["task_id"] for row in original["tasks"]] == [row["id"] for row in batch["tasks"]]
        assert [row["row_index"] for row in original["tasks"]] == list(range(count))
        assert all(row["status"] == status and row["locked_guide_version"] for row in original["tasks"])
        before = await _success_facts(project)
        async def fail_policy_load(*_args, **_kwargs):
            raise AssertionError(f"committed {operation.upper()} replay read policy custody")

        with monkeypatch.context() as replay_patch:
            replay_patch.setattr(
                TaskService,
                "_load_active_policy_context" if operation == "screen" else "_load_locked_task_context",
                fail_policy_load,
            )
            replay = await client.post(_path(project, batch, operation), headers=key, json=payload)
        assert replay.status_code == 200 and replay.json() == original, replay.text
        after = await _success_facts(project)
        assert before[:-1] == after[:-1] and len(after[-1] - before[-1]) == count
        async with db_session.get_session_factory()() as session:
            root = (await session.scalars(select(TaskBatchTransitionReceipt).where(
                TaskBatchTransitionReceipt.project_id == project,
                TaskBatchTransitionReceipt.action_id == f"project.task.{operation}",
            ))).one()
            links = list(await session.scalars(select(TaskBatchTransitionMember).where(
                TaskBatchTransitionMember.transition_receipt_id == root.id,
            ).order_by(TaskBatchTransitionMember.row_index)))
            assert root.response == original and root.status == "committed" and len(links) == count
            assert len({link.task_idempotency_key for link in links}) == count
            lifecycle_rows = list(await session.scalars(select(AuditEvent).where(
                AuditEvent.entity_type == "task",
                AuditEvent.entity_id.in_([link.task_id for link in links]),
                AuditEvent.event_type == ("TaskScreened" if operation == "screen" else "TaskReleased"),
            )))
            lifecycle_by_task = {event.entity_id: event for event in lifecycle_rows}
            assert len(lifecycle_rows) == len(lifecycle_by_task) == count
            for link, row in zip(links, original["tasks"], strict=True):
                receipt = await session.get(TaskCommandReceipt, link.task_command_receipt_id)
                decision = await session.get(AuditEvent, link.authorization_decision_id)
                assert receipt.batch_transition_receipt_id == root.id
                assert receipt.task_id == link.task_id == row["task_id"]
                assert receipt.response["status"] == row["status"]
                assert receipt.locked_context_hash == row["locked_context_hash"]
                assert decision.action_id == root.action_id
                assert decision.resource_type == "project" and decision.resource_id == project
                assert decision.event_type == "SensitiveAuthorizationAllowed"
                lifecycle = lifecycle_by_task[row["task_id"]]
                assert lifecycle.event_payload["references"]["authorization_decision_id"] == decision.id
                authority = lifecycle.event_payload["manager_authority_facts"]
                assert authority["resource_type"] == "task_authority" and authority["resource_id"] == row["task_id"]
                assert authority["scope_project_id"] == project
                assert lifecycle.event_payload["authorization_resource_digest"] == decision.after_facts["resource_context_digest"]
    facts = await _success_facts(project)
    assert len(facts[1]) == 2 and all(len(values) == count * 2 for values in facts[2:5])
    assert all(row.status == "ready" for row in facts[0])


async def test_reason_limit_matches_canonical_transition_without_partial_effects(import_source_client, monkeypatch):
    """Reject oversized reasons before effects and preserve the exact allowed boundary."""
    client = import_source_client
    project, batch = await _import(client)
    before = await _success_facts(project)
    for operation in ("screen", "release"):
        refused = await client.post(_path(project, batch, operation), headers=auth_headers(),
                                    json={"reason": "é" * 1001})
        assert refused.status_code == 422, refused.text
        assert await _success_facts(project) == before
    reasons = {"screen": "é" * 1000, "release": "\x01" * 1000}
    original_load = TaskService._load_active_policy_context
    original_locked_load = TaskService._load_locked_task_context
    active_context_loads = locked_context_loads = 0

    async def count_active_policy_load(service, project_id):
        nonlocal active_context_loads
        active_context_loads += 1
        return await original_load(service, project_id)

    async def count_locked_policy_load(service, task):
        nonlocal locked_context_loads
        locked_context_loads += 1
        return await original_locked_load(service, task)

    monkeypatch.setattr(TaskService, "_load_active_policy_context", count_active_policy_load)
    monkeypatch.setattr(TaskService, "_load_locked_task_context", count_locked_policy_load)
    for operation, reason in reasons.items():
        admitted = await client.post(_path(project, batch, operation), headers=auth_headers(),
                                     json={"reason": reason})
        assert admitted.status_code == 200, admitted.text
    assert active_context_loads == 1 and locked_context_loads == 1
    async with db_session.get_session_factory()() as session:
        retained = list(await session.scalars(select(TaskBatchTransitionReceipt.reason).where(
            TaskBatchTransitionReceipt.project_id == project,
        )))
        assert len(retained) == 2 and set(retained) == set(reasons.values())
        task_ids = list(await session.scalars(select(WorkstreamTask.id).where(
            WorkstreamTask.project_id == project,
        )))
        lifecycle = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.entity_id.in_(task_ids),
            AuditEvent.event_type.in_(("TaskScreened", "TaskReleased")),
        )))
        assert len(lifecycle) == 4
        assert {event.reason for event in lifecycle} == set(reasons.values())
        assert {
            event.event_payload["manager_authority_facts"]["reason"] for event in lifecycle
        } == set(reasons.values())


async def test_release_resolves_each_distinct_frozen_context_once(import_source_client, monkeypatch):
    """Two genuine historical guide contexts remain separate without per-Task graph reloads."""
    client = import_source_client
    project, batch = await _import(client)
    first = await client.post(
        f"/api/v1/tasks/{batch['tasks'][0]['id']}/screen", headers=auth_headers(),
        json={"reason": "Screen under the original guide"},
    )
    assert first.status_code == 200, first.text
    successor = await client.post(
        f"/api/v1/projects/{project}/guides", headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert successor.status_code == 201, successor.text
    await create_policy_bundle_for_guide(client, project, successor.json()["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(), project_id=project, guide_id=successor.json()["id"],
    )
    second = await client.post(
        f"/api/v1/tasks/{batch['tasks'][1]['id']}/screen", headers=auth_headers(),
        json={"reason": "Screen under the successor guide"},
    )
    assert second.status_code == 200, second.text
    assert first.json()["locked_guide_version"] != second.json()["locked_guide_version"]

    original = TaskService._load_locked_task_context
    loads = 0

    async def count_locked_policy_load(service, task):
        nonlocal loads
        loads += 1
        return await original(service, task)

    monkeypatch.setattr(TaskService, "_load_locked_task_context", count_locked_policy_load)
    released = await client.post(
        _path(project, batch, "release"), headers=auth_headers(),
        json={"reason": "Release both frozen guide generations"},
    )
    assert released.status_code == 200, released.text
    assert loads == 2
    versions = {
        row["task_id"]: row["locked_guide_version"] for row in released.json()["tasks"]
    }
    assert versions == {
        batch["tasks"][0]["id"]: first.json()["locked_guide_version"],
        batch["tasks"][1]["id"]: second.json()["locked_guide_version"],
    }


async def test_missing_active_guide_refuses_whole_batch_without_success_effects(import_source_client):
    """Actual unscreenable project imports DRAFTs but cannot bypass guide admission."""
    client = import_source_client
    project = await _project(client)
    value = document(2)
    for row in value["tasks"]:
        row.update(acceptance_criteria="Accurate, complete work", rejection_criteria="Incomplete work")
    source = await _verified_source(client, project, value)
    imported = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    before = await _success_facts(project)
    refused = await client.post(_path(project, imported.json(), "screen"), headers=auth_headers(), json={"reason": "No approved guide"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "task_batch_transition_invalid", refused.text
    assert "active guide" in refused.json()["detail"]
    assert await _success_facts(project) == before


async def test_late_staging_failure_rolls_back_and_replay_retains_original_batch(import_source_client, monkeypatch):
    """A real second canonical write followed by failure leaves no partial success."""
    client = import_source_client
    project, batch = await _import(client)
    before = await _success_facts(project)
    original_stage, calls = AuthorizedTaskCommands.stage_transition, 0

    async def fail_after_second_write(commands, prepared, decision, **kwargs):
        nonlocal calls
        response = await original_stage(commands, prepared, decision, **kwargs)
        calls += 1
        if calls == 2:
            raise TaskValidationError("Injected late canonical failure")
        return response

    key, payload = auth_headers(), {"reason": "Whole-batch screening"}
    monkeypatch.setattr(AuthorizedTaskCommands, "stage_transition", fail_after_second_write)
    failed = await client.post(_path(project, batch, "screen"), headers=key, json=payload)
    assert failed.status_code == 422 and calls == 2, failed.text
    assert await _success_facts(project) == before
    monkeypatch.setattr(AuthorizedTaskCommands, "stage_transition", original_stage)
    successful = await client.post(_path(project, batch, "screen"), headers=key, json=payload)
    assert successful.status_code == 200, successful.text
    before = await _success_facts(project)
    for reason in (None, " \n"):
        refused = await client.post(_path(project, batch, "release"), headers=auth_headers(), json={"reason": reason})
        assert refused.status_code == 422 and refused.json()["error"]["code"] == "task_batch_transition_invalid", refused.text
        assert await _success_facts(project) == before
    changed = await client.post(_path(project, batch, "screen"), headers=key, json={"reason": "Changed reason"})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "idempotency_mismatch", changed.text
    assert await _success_facts(project) == before
    advanced = await client.post(f"/api/v1/tasks/{batch['tasks'][0]['id']}/release", headers=auth_headers(),
                                 json={"reason": "Separate later decision"})
    assert advanced.status_code == 200, advanced.text
    before = await _success_facts(project)
    replay = await client.post(_path(project, batch, "screen"), headers=key, json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json() == successful.json()
    after = await _success_facts(project)
    assert after[:5] == before[:5]  # No task, root, member, receipt or lifecycle write.
    fresh = after[-1] - before[-1]
    assert before[-1] <= after[-1] and len(fresh) == len(batch["tasks"])
    async with db_session.get_session_factory()() as session:
        root = await session.get(TaskBatchTransitionReceipt, next(iter(before[1])))
        decisions = (await session.scalars(select(AuditEvent).where(AuditEvent.id.in_(fresh)))).all()
        assert len(decisions) == len(fresh)
        assert all((row.actor_id, row.action_id, row.resource_type, row.resource_id, row.project_id)
                   == (root.actor_profile_id, "project.task.screen", "project", project, project)
                   and row.matched_grant_id is not None and row.after_facts["allowed"] is True
                   for row in decisions)


async def test_revoked_manager_cannot_replay_a_successful_bulk_write(import_source_client):
    """The real canonical grant-revocation owner invalidates retained-key authority."""
    client = import_source_client
    project, batch = await _import(client)
    key, payload = auth_headers(), {"reason": "Before revocation"}
    result = await client.post(_path(project, batch, "screen"), headers=key, json=payload)
    assert result.status_code == 200, result.text
    before = await _success_facts(project)
    async with db_session.get_session_factory()() as session, session.begin():
        grants = list(await session.scalars(select(AdminRoleGrant).where(
            AdminRoleGrant.target_actor_profile_id == batch["tasks"][0]["created_by"],
            AdminRoleGrant.role == "project_manager", AdminRoleGrant.status == "active",
            or_(AdminRoleGrant.scope_type == "system", AdminRoleGrant.scope_project_id == project),
        ).order_by(AdminRoleGrant.id)))
        assert grants, "the actual manager must have covering authority before revocation"
        for grant in grants:
            link = (await session.scalars(select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == grant.granted_by_actor_profile_id,
            ))).one()
            context = HumanAuthorizationContext(
                actor_profile_id=UUID(link.actor_profile_id), identity_link_id=UUID(link.id),
                actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
                identity_link_status=IdentityLinkStatus.ACTIVE, request_id=uuid4(), correlation_id=uuid4(),
            )
            await revoke_manager_grant(session, context, UUID(str(grant.id)))
    denied = await client.post(_path(project, batch, "screen"), headers=key, json=payload)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "permission_not_granted", denied.text
    assert await _success_facts(project) == before
    async with db_session.get_session_factory()() as session:
        denials = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "project.task.screen", AuditEvent.event_type == "SensitiveAuthorizationDenied",
        )))
        assert len(denials) == 1 and denials[0].denial_code == "permission_not_granted"


@pytest.mark.parametrize("operation", ["screen", "release"])
async def test_same_key_concurrent_roots_observe_native_wait_then_one_success(
    import_source_client, monkeypatch, operation,
):
    """An observed PostgreSQL blocker proves aggregate reservation serialization."""
    client = import_source_client
    project, batch = await _import(client)
    if operation == "release":
        screened = await client.post(
            _path(project, batch, "screen"), headers=auth_headers(),
            json={"reason": "Prepare concurrent release"},
        )
        assert screened.status_code == 200, screened.text
    before = await _success_facts(project)
    original = TaskBatchTransitionCommands._reserve
    reserved, entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids, calls = [], 0

    async def gated(commands, *args, **kwargs):
        nonlocal calls
        calls += 1
        call = calls
        pids.append(await commands._session.scalar(select(func.pg_backend_pid())))
        if call == 2:
            entered.set()
        result = await original(commands, *args, **kwargs)
        if call == 1:
            reserved.set()
            await asyncio.wait_for(release.wait(), timeout=30)
        return result

    monkeypatch.setattr(TaskBatchTransitionCommands, "_reserve", gated)
    key, payload = auth_headers(), {"reason": "Concurrent exact request"}
    first = asyncio.create_task(client.post(_path(project, batch, operation), headers=key, json=payload))
    second = None
    try:
        await asyncio.wait_for(reserved.wait(), timeout=30)
        second = asyncio.create_task(client.post(_path(project, batch, operation), headers=key, json=payload))
        await asyncio.wait_for(entered.wait(), timeout=30)
        deadline = asyncio.get_running_loop().time() + 10
        async with db_session.get_session_factory()() as observer:
            while not await observer.scalar(text("select :holder = any(pg_blocking_pids(:waiter))"),
                                             {"holder": pids[0], "waiter": pids[1]}):
                assert asyncio.get_running_loop().time() < deadline, "no aggregate holder/waiter was observed"
                await asyncio.sleep(0.05)
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(first, second), timeout=60)
        assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
        assert responses[0].json() == responses[1].json()
        facts = await _success_facts(project)
        assert len(facts[1]) - len(before[1]) == 1
        assert all(len(facts[index]) - len(before[index]) == 2 for index in range(2, 5))
        assert len(facts[-1]) - len(before[-1]) == 4
        assert all(row.status == ("screening" if operation == "screen" else "ready") for row in facts[0])
    finally:
        release.set()
        for pending in (first, second):
            if pending is not None and not pending.done():
                pending.cancel()
        await asyncio.gather(*(pending for pending in (first, second) if pending is not None), return_exceptions=True)


async def test_sql_cannot_attach_old_standalone_successes_to_a_new_aggregate(import_source_client):
    """Real earlier canonical successes lack aggregate-root provenance and cannot enroll."""
    client = import_source_client
    project, batch = await _import(client)
    reason = "Historical standalone screening"
    for task in batch["tasks"]:
        screened = await client.post(f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers(), json={"reason": reason})
        assert screened.status_code == 200, screened.text
    before = await _success_facts(project)
    root_id = new_record_id()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError) as caught:
            async with session.begin():
                snapshot = await TaskImportMembership(session).prepare(UUID(project), UUID(batch["batch_id"]))
                receipts = {row.task_id: row for row in await session.scalars(select(TaskCommandReceipt).where(
                    TaskCommandReceipt.task_id.in_([row["id"] for row in batch["tasks"]]),
                    TaskCommandReceipt.action_id == "project.task.screen",
                ))}
                assert len(receipts) == 2 and all(row.batch_transition_receipt_id is None for row in receipts.values())
                actor = next(iter(receipts.values())).actor_profile_id
                link = (await session.scalars(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == actor))).one()
                compact = {"project_id": project, "batch_id": batch["batch_id"], "operation": "screen", "row_count": 2,
                           "tasks": [{"task_id": str(row.task_id), "row_index": row.row_index, "status": "screening",
                                      "locked_guide_version": receipts[str(row.task_id)].response["locked_guide_version"],
                                      "locked_contribution_policy_version_id": receipts[str(row.task_id)].response["locked_contribution_policy_version_id"],
                                      "locked_context_hash": receipts[str(row.task_id)].locked_context_hash} for row in snapshot.members]}
                root = TaskBatchTransitionReceipt(
                    id=root_id, actor_profile_id=actor, identity_link_id=link.id, action_id="project.task.screen",
                    idempotency_key=uuid4(), request_digest=canonical_json_hash({"project_id": project,
                        "batch_id": batch["batch_id"], "operation": "project.task.screen", "reason": reason}),
                    reason=reason, project_id=project, batch_id=batch["batch_id"], row_count=2,
                    manifest_digest=snapshot.manifest_digest, membership_digest=_membership_digest(snapshot),
                    status="pending",
                )
                session.add(root)
                await session.flush()
                for native in snapshot.members:
                    receipt = receipts[str(native.task_id)]
                    event = (await session.scalars(select(AuditEvent).where(
                        AuditEvent.entity_id == str(native.task_id), AuditEvent.event_type == "TaskScreened",
                    ))).one()
                    session.add(TaskBatchTransitionMember(
                        id=new_record_id(), transition_receipt_id=root_id, project_id=project, batch_id=batch["batch_id"],
                        native_member_id=str(native.member_id), task_id=str(native.task_id), row_index=native.row_index,
                        task_idempotency_key=receipt.idempotency_key, task_command_receipt_id=receipt.id,
                        authorization_decision_id=event.event_payload["references"]["authorization_decision_id"],
                    ))
                root.status, root.response, root.committed_at = "committed", compact, datetime.now(UTC)
                await session.flush()
        assert getattr(caught.value.orig, "sqlstate", None) == "23514"
    assert await _success_facts(project) == before


async def test_native_commit_refuses_empty_pending_root_and_late_command_attachment(import_source_client):
    """Fast-path closure rejects declarations without children and later surplus receipts."""
    client = import_source_client
    project, batch = await _import(client)
    before = await _success_facts(project)
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError) as caught:
            async with session.begin():
                snapshot = await TaskImportMembership(session).prepare(UUID(project), UUID(batch["batch_id"]))
                actor = await session.scalar(select(TaskCommandReceipt.actor_profile_id).where(
                    TaskCommandReceipt.task_id == batch["tasks"][0]["id"],
                    TaskCommandReceipt.action_id == "project.task.create",
                ))
                link = (await session.scalars(select(ActorIdentityLink).where(
                    ActorIdentityLink.actor_profile_id == actor,
                ))).one()
                session.add(TaskBatchTransitionReceipt(
                    id=new_record_id(), actor_profile_id=actor, identity_link_id=link.id,
                    action_id="project.task.screen", idempotency_key=uuid4(),
                    request_digest=canonical_json_hash({"project_id": project, "batch_id": batch["batch_id"],
                        "operation": "project.task.screen", "reason": None}),
                    reason=None, project_id=project, batch_id=batch["batch_id"], row_count=2,
                    manifest_digest=snapshot.manifest_digest, membership_digest=_membership_digest(snapshot),
                    status="pending",
                ))
                await session.flush()
        assert getattr(caught.value.orig, "sqlstate", None) == "23514"
        assert "task batch transition cannot remain pending" in str(caught.value.orig)
    assert await _success_facts(project) == before

    screened = await client.post(_path(project, batch, "screen"), headers=auth_headers(), json={})
    assert screened.status_code == 200, screened.text
    before = await _success_facts(project)
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError) as caught:
            async with session.begin():
                retained = (await session.scalars(select(TaskCommandReceipt).where(
                    TaskCommandReceipt.task_id == batch["tasks"][0]["id"],
                    TaskCommandReceipt.action_id == "project.task.screen",
                ))).one()
                values = {column.key: getattr(retained, column.key) for column in TaskCommandReceipt.__table__.columns}
                values.update(id=new_record_id(), idempotency_key=uuid4())
                session.add(TaskCommandReceipt(**values))
                await session.flush()
        assert getattr(caught.value.orig, "sqlstate", None) == "23514"
        assert "task batch transition command must be committed with its root" in str(caught.value.orig)
    assert await _success_facts(project) == before


@pytest.mark.parametrize("corruption", ["missing_member", "pending_root", "authority_facts_digest"])
async def test_native_commit_refuses_incomplete_aggregate_after_real_canonical_stages(
    import_source_client, corruption,
):
    """Initial custody corruption must roll back both actual canonical Task writes."""
    client = import_source_client
    project, batch = await _import(client)
    before = await _success_facts(project)
    changed = False
    staged_task_ids = set()

    def corrupt_before_flush(session, flush_context, instances):
        nonlocal changed
        if corruption == "authority_facts_digest":
            staged_task_ids.update(
                row.entity_id for row in session.new
                if isinstance(row, AuditEvent) and row.event_type == "TaskScreened"
            )
        if changed:
            return
        if corruption == "missing_member":
            for row in list(session.new):
                if isinstance(row, TaskBatchTransitionMember) and row.row_index == 1:
                    # Remove the initial INSERT; an UPDATE/DELETE guard cannot
                    # mask missing complete-member commit closure.
                    session.expunge(row)
                    changed = True
        elif corruption == "pending_root":
            for row in list(session.dirty):
                if isinstance(row, TaskBatchTransitionReceipt) and row.status == "committed":
                    # Preserve the valid pending declaration without writing an
                    # invalid state shape. Deferred closure must reject commit.
                    session.expire(row)
                    changed = True
        else:
            if staged_task_ids != {row["id"] for row in batch["tasks"]}:
                # Corrupt the last initial lifecycle INSERT after both actual
                # canonical Task writes, rather than the first row's flush.
                return
            for row in list(session.new):
                if isinstance(row, AuditEvent) and row.event_type == "TaskScreened":
                    # A digest-shaped altered pre-write fact must not borrow the
                    # genuine consumed decision's unchanged resource digest.
                    payload = dict(row.event_payload)
                    facts = dict(payload["manager_authority_facts"])
                    original_hash = facts["locked_context_hash"]
                    facts["locked_context_hash"] = "sha256:" + "0" * 64
                    assert facts["locked_context_hash"] != original_hash
                    payload["manager_authority_facts"] = facts
                    row.event_payload = payload
                    changed = True
                    break

    event.listen(Session, "before_flush", corrupt_before_flush)
    try:
        refused = await client.post(
            _path(project, batch, "screen"), headers=auth_headers(),
            json={"reason": "Canonical Task writes before native refusal"},
        )
        assert changed, "the intended final aggregate INSERT/completion was not reached"
        if corruption == "authority_facts_digest":
            assert staged_task_ids == {row["id"] for row in batch["tasks"]}, "all canonical Task writes must precede native refusal"
        assert refused.status_code == 503 and refused.json()["error"]["retryable"] is True, refused.text
        assert await _success_facts(project) == before
    finally:
        event.remove(Session, "before_flush", corrupt_before_flush)


@pytest.mark.parametrize("table", ["task_batch_transition_receipts", "task_batch_transition_members"])
@pytest.mark.parametrize("operation", ["update", "delete", "truncate"])
async def test_committed_aggregate_custody_refuses_direct_sql_mutation(
    import_source_client, table, operation,
):
    """Retained aggregate facts refuse mutation and each table owns a TRUNCATE guard."""
    client = import_source_client
    project, batch = await _import(client)
    key, payload = auth_headers(), {"reason": "Immutable aggregate success"}
    result = await client.post(_path(project, batch, "screen"), headers=key, json=payload)
    assert result.status_code == 200, result.text
    async with db_session.get_session_factory()() as session, session.begin():
        snapshot = text(f"select to_jsonb(t) from {table} t order by id")
        before = list(await session.scalars(snapshot))
        assert before
        if operation == "truncate":
            assert await session.scalar(text(
                "select count(*) from pg_trigger where tgrelid=cast(:table as regclass) "
                "and not tgisinternal and (tgtype & 32)=32 and (tgtype & 1)=0 and tgenabled='O'"
            ), {"table": table}) == 1, "each aggregate table needs its own enabled statement guard"
        update = {
            "task_batch_transition_receipts": "reason='changed retained decision'",
            "task_batch_transition_members": "task_idempotency_key=:new_key",
        }[table]
        statement = {
            "update": f"update {table} set {update}",
            "delete": f"delete from {table}",
            "truncate": f"truncate {table} cascade",
        }[operation]
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(text(statement), {"new_key": uuid4()})
        assert list(await session.scalars(snapshot)) == before
    replay = await client.post(_path(project, batch, "screen"), headers=key, json=payload)
    assert replay.status_code == 200 and replay.json() == result.json(), replay.text
