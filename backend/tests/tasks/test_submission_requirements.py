"""Exact requirements, contributor visibility and caller-owned historical reads."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.tasks import task_service
from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.projects.models import EffectiveProjectSubmissionArtifactPolicy
from app.modules.tasks import schemas
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.modules.tasks.schemas import (
    ContributorTaskSubmissionRequirements, ManagementTaskSubmissionRequirements,
    RequiredArtifactRequirement, RequiredEvidenceRequirement, ForbiddenArtifactRequirement,
    StorageReferenceRules, SubmissionPackagingRequirements,
)
from app.modules.tasks.service import TaskLockedContextInvalid, TaskNotFound, TaskService
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_draft_task, create_ready_task,
    admit_and_grant_project_submitter, seed_task_test_actor, auth_headers,
)

READS = (
    ("read_contributor_task_submission_requirements", ContributorTaskSubmissionRequirements),
    ("read_management_task_submission_requirements", ManagementTaskSubmissionRequirements),
)
FIELDS = {
    "task_id", "project_id", "guide_version", "policy_schema_version", "merge_algorithm_version",
    "required_packet_fields", "required_artifacts", "required_evidence", "forbidden_artifacts",
    "attestation_terms", "manifest_required", "artifact_hash_required", "artifact_hash_algorithm",
    "allowed_storage_schemes", "storage_reference_rules", "maximum_file_size_bytes",
    "maximum_package_size_bytes", "maximum_archive_entries", "maximum_archive_size_bytes", "packaging",
}


async def read_requirements(service, method, project, task, contributor):
    args = (UUID(project), UUID(task))
    return await getattr(service, method)(*args, UUID(contributor)) if method == READS[0][0] else await getattr(service, method)(*args)


def test_requirement_contracts():
    artifact = RequiredArtifactRequirement(key="answer", path="answer.md", hash_required=True, required=True)
    evidence = RequiredEvidenceRequirement(key="log", label="checker log", hash_required=True, required=True)
    forbidden = ForbiddenArtifactRequirement(pattern="*.secret", reason="private")
    storage = StorageReferenceRules(allowed_storage_schemes=("s3",), allowed_uri_prefixes=("s3://",),
                                    credentials_allowed=False, query_strings_allowed=False,
                                    fragments_allowed=False, path_traversal_allowed=False)
    packaging = SubmissionPackagingRequirements(package_required=True, allowed_package_formats=("zip",))
    values = dict(task_id=new_record_id(), project_id=new_record_id(), guide_version="guide", policy_schema_version=None,
                  merge_algorithm_version=None, required_packet_fields=("summary",), required_artifacts=(artifact,),
                  required_evidence=(evidence,), forbidden_artifacts=(forbidden,), attestation_terms=("original",),
                  manifest_required=True, artifact_hash_required=True, artifact_hash_algorithm="sha256",
                  allowed_storage_schemes=("s3",), storage_reference_rules=storage, maximum_file_size_bytes=None,
                  maximum_package_size_bytes=None, maximum_archive_entries=None, maximum_archive_size_bytes=None,
                  packaging=packaging)
    for _, cls in READS:
        result = cls(**values)
        assert type(result) is cls and set(result.model_dump()) == FIELDS
        assert result.model_dump(mode="json")["packaging"]["allowed_package_formats"] == ["zip"]
        for field, invalid in (("task_id", "bad"), ("project_id", str(new_record_id())), ("guide_version", " "),
                               ("required_artifacts", [artifact]), ("attestation_terms", ["mutable"])):
            with pytest.raises(ValidationError):
                cls(**{**values, field: invalid})
        with pytest.raises(ValidationError, match="extra_forbidden"):
            cls(**values, source_ref="private")
        with pytest.raises(ValidationError, match="frozen_instance"):
            result.guide_version = "changed"
    for item in (artifact, evidence, forbidden, storage, packaging):
        field = next(iter(type(item).model_fields))
        with pytest.raises(ValidationError, match="frozen_instance"):
            setattr(item, field, None)
        with pytest.raises(ValidationError, match="extra_forbidden"):
            type(item)(**item.model_dump(), private_material="private")
    for cls, values, field in ((StorageReferenceRules, storage.model_dump(), "allowed_uri_prefixes"),
                               (SubmissionPackagingRequirements, packaging.model_dump(), "allowed_package_formats")):
        with pytest.raises(ValidationError, match="tuple_type"):
            cls(**{**values, field: ["mutable"]})


def test_requirement_packaging_projection():
    service = task_service(MagicMock(spec=AsyncSession), settings=get_settings())
    result = service._packaging_requirements({"packaging": {"package_required": False}})
    assert result.model_dump(exclude_none=True) == {"package_required": False}
    result = service._packaging_requirements({"packaging": {"package_required": True, "allowed_package_formats": ["zip"]}})
    assert result.allowed_package_formats == ("zip",)
    assert result.model_dump(mode="json")["allowed_package_formats"] == ["zip"]
    for bad in ({"package_required": True, "private_material": "secret"},
                {"package_required": "yes"}, {"package_required": True, "allowed_package_formats": "zip"},
                {"package_required": True, "allowed_package_formats": ["unsupported"]}, {}):
        with pytest.raises(TaskLockedContextInvalid) as failure:
            service._packaging_requirements({"packaging": bad})
        assert failure.value.code == "task_locked_context_invalid"
        assert failure.value.details == {"field": "effective_policy.packaging"}
        assert "secret" not in str(failure.value)


async def test_requirement_selectors_reject_before_sql():
    session = MagicMock(spec=AsyncSession)
    service = task_service(session, settings=get_settings())
    service._repo.lock_project_task = AsyncMock()
    service._repo.read_contributor_task_detail = AsyncMock()
    service._load_locked_task_context = AsyncMock()
    for method, _ in READS:
        count = 3 if method == READS[0][0] else 2
        for index in range(count):
            for invalid in (None, "bad", str(new_record_id()), 1, True):
                args = [new_record_id() for _ in range(count)]
                args[index] = invalid
                with pytest.raises(ValueError):
                    await getattr(service, method)(*args)
    service._repo.lock_project_task.assert_not_awaited()
    service._repo.read_contributor_task_detail.assert_not_awaited()
    service._load_locked_task_context.assert_not_awaited()
    session.execute.assert_not_called()
    session.scalar.assert_not_called()


async def test_requirement_scope_and_assignment_visibility(task_client, monkeypatch):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-requirements")
    ready = await create_ready_task(task_client, project["id"])
    outsider = await create_ready_task(task_client, foreign["id"])
    draft = await create_draft_task(task_client, project["id"])
    names = ("claimed", "wrong_contributor", "wrong_assignee", "active_only", "assignee_only", "unrelated", "released", "released_ready")
    tasks = {name: await create_ready_task(task_client, project["id"]) for name in names}
    other = await seed_task_test_actor("requirements-other")
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "requirements-owner")
    owner = grant["actor_profile_id"]
    claimed = await task_client.post(f"/api/v1/tasks/{tasks['claimed']['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    cases = {
        "wrong_contributor": ("claimed", owner, other, "active"),
        "wrong_assignee": ("claimed", other, owner, "active"),
        "active_only": ("ready", None, owner, "active"),
        "assignee_only": ("ready", owner, None, None),
        "unrelated": ("claimed", owner, None, None),
        "released": ("claimed", owner, owner, "released"),
        "released_ready": ("ready", None, owner, "released"),
    }
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        for name, (status, assignee, contributor, assignment_status) in cases.items():
            row = await session.get(WorkstreamTask, tasks[name]["id"])
            row.status, row.assigned_to = status, assignee
            if contributor:
                session.add(TaskAssignment(id=str(new_record_id()), task_id=row.id, project_id=row.project_id,
                    contributor_id=contributor, assigned_by=owner, status=assignment_status,
                    submitter_contribution_policy_version_id=row.locked_contribution_policy_version_id))
    async with factory() as session:
        service = task_service(session, settings=get_settings())
        outputs = []
        for method, cls in READS:
            result = await read_requirements(service, method, project["id"], ready["id"], owner)
            assert type(result) is cls and set(result.model_dump()) == FIELDS
            outputs.append(result.model_dump(mode="json", exclude_none=True))
            with patch.object(service, "_load_locked_task_context", wraps=service._load_locked_task_context) as resolve:
                for task_id in (outsider["id"], str(new_record_id())):
                    with pytest.raises(TaskNotFound, match="task not found"):
                        await read_requirements(service, method, project["id"], task_id, owner)
                resolve.assert_not_awaited()
        stored = await session.get(WorkstreamTask, ready["id"])
        policy = (await session.get(EffectiveProjectSubmissionArtifactPolicy,
                                   stored.locked_effective_project_submission_artifact_policy_id)).effective_policy
        expected = {key: value for key, value in policy.items() if key in FIELDS and value is not None}
        expected.update(task_id=ready["id"], project_id=project["id"], guide_version=stored.locked_guide_version,
                        policy_schema_version=policy["schema_version"],
                        required_packet_fields=["summary", "package_hash", "artifact_hash_manifest", "worker_attestation"],
                        storage_reference_rules=dict(allowed_storage_schemes=policy["allowed_storage_schemes"],
                            allowed_uri_prefixes=[f"{scheme}://" for scheme in policy["allowed_storage_schemes"]],
                            credentials_allowed=False, query_strings_allowed=False, fragments_allowed=False,
                            path_traversal_allowed=False))
        for key, fields in (("required_artifacts", {"key", "path", "hash_required", "required", "description"}),
                            ("required_evidence", {"key", "label", "hash_required", "required", "description"}),
                            ("forbidden_artifacts", {"pattern", "reason", "worker_facing_fix", "severity"})):
            expected[key] = [{k: v for k, v in rule.items() if k in fields and v is not None} for rule in policy[key]]
        assert outputs[0] == outputs[1] == expected
        assert outputs[0]["required_artifacts"] == [{"key": "required-artifact-001", "path": "answer.md", "hash_required": True, "required": True}]
        with patch.object(service, "_load_locked_task_context", wraps=service._load_locked_task_context) as resolve:
            with pytest.raises(TaskNotFound):
                await read_requirements(service, READS[0][0], project["id"], draft["id"], owner)
            resolve.assert_not_awaited()
        own = await session.get(WorkstreamTask, tasks["claimed"]["id"])
        assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == own.id))
        assert own.status == "claimed" and own.assigned_to == assignment.contributor_id == owner and assignment.status == "active"
        for method, cls in READS:
            assert type(await read_requirements(service, method, project["id"], own.id, owner)) is cls
        with patch.object(service, "_load_locked_task_context", wraps=service._load_locked_task_context) as resolve:
            with pytest.raises(TaskNotFound):
                await read_requirements(service, READS[0][0], project["id"], own.id, other)
            resolve.assert_not_awaited()
        for name, expected in cases.items():
            row = await session.get(WorkstreamTask, tasks[name]["id"])
            assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == row.id))
            assert (row.status, row.assigned_to, assignment.contributor_id if assignment else None,
                    assignment.status if assignment else None) == expected
            with patch.object(service, "_load_locked_task_context", wraps=service._load_locked_task_context) as resolve:
                if name == "released_ready":
                    result = await read_requirements(service, READS[0][0], project["id"], row.id, owner)
                    assert result.task_id == UUID(row.id)
                    resolve.assert_awaited_once()
                else:
                    with pytest.raises(TaskNotFound, match="task not found"):
                        await read_requirements(service, READS[0][0], project["id"], row.id, owner)
                    resolve.assert_not_awaited()


async def test_requirement_custody_and_caller_transaction(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    draft = await create_draft_task(task_client, project["id"])
    factory, contributor = db_session.get_session_factory(), str(new_record_id())
    for method, cls in READS:
        pending_id = str(new_record_id())
        async with factory() as session, session.begin():
            row = await session.get(WorkstreamTask, task["id"])
            original = row.title
            row.title = "requirements-uncommitted-marker"
            await session.flush()
            pending = WorkstreamTask(id=pending_id, project_id=project["id"])
            session.add(pending)
            result = await read_requirements(task_service(session, settings=get_settings()), method, project["id"], task["id"], contributor)
            assert type(result) is cls and pending in session.new and session.in_transaction()
            assert row.title == "requirements-uncommitted-marker"
            await session.rollback()
        async with factory() as observer:
            assert (await observer.get(WorkstreamTask, task["id"])).title == original
            assert await observer.get(WorkstreamTask, pending_id) is None
    async with factory() as session:
        with pytest.raises(TaskLockedContextInvalid, match="incomplete"):
            await read_requirements(task_service(session, settings=get_settings()), READS[1][0], project["id"], draft["id"], contributor)
    async with factory() as session, session.begin():
        row = await session.get(WorkstreamTask, task["id"])
        row.locked_post_submit_checker_policy_body = {**row.locked_post_submit_checker_policy_body, "blocking_severities": []}
    for method, _ in READS:
        async with factory() as session:
            assert (await session.get(WorkstreamTask, task["id"])).locked_post_submit_checker_policy_body["blocking_severities"] == []
            with pytest.raises(TaskLockedContextInvalid, match="custody is invalid") as error:
                await read_requirements(task_service(session, settings=get_settings()), method, project["id"], task["id"], contributor)
            assert error.value.code == "task_locked_context_invalid"


async def test_requirement_waits_for_task_before_projects(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory, name = db_session.get_session_factory(), "requirements-" + new_record_id().hex
    async with factory() as writer, factory() as reader:
        stored = await reader.get(WorkstreamTask, task["id"])
        original_body = stored.locked_post_submit_checker_policy_body.copy()
        await reader.execute(text("select set_config('application_name', :name, true)"), {"name": name})
        reader_pid = await reader.scalar(text("select pg_backend_pid()"))
        row = await writer.scalar(select(WorkstreamTask).where(WorkstreamTask.id == task["id"]).with_for_update())
        writer_pid = await writer.scalar(text("select pg_backend_pid()"))
        row.locked_post_submit_checker_policy_body = {**original_body, "blocking_severities": []}
        await writer.flush()
        service = task_service(reader, settings=get_settings())
        order = MagicMock()
        with patch.object(service._repo, "read_contributor_task_detail", wraps=service._repo.read_contributor_task_detail) as detail, patch.object(service._project_contexts, "lock_locked_policy_context", wraps=service._project_contexts.lock_locked_policy_context) as resolve:
            order.attach_mock(detail, "detail")
            order.attach_mock(resolve, "projects")
            pending = asyncio.create_task(service.read_contributor_task_submission_requirements(UUID(project["id"]), UUID(task["id"]), new_record_id()))
            try:
                await asyncio.wait_for(wait_for_named_database_lock(get_settings().database_url, name,
                    expected_waiter_pid=reader_pid, expected_blocker_pid=writer_pid), timeout=10)
                detail.assert_not_awaited()
                resolve.assert_not_awaited()
                assert not pending.done() and stored.locked_post_submit_checker_policy_body == original_body
                await writer.commit()
                with pytest.raises(TaskLockedContextInvalid, match="custody is invalid"):
                    await asyncio.wait_for(pending, timeout=10)
                detail.assert_awaited_once()
                resolve.assert_awaited_once()
                assert [call[0] for call in order.mock_calls] == ["detail", "projects"]
                assert stored.locked_post_submit_checker_policy_body["blocking_severities"] == []
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


def test_requirement_public_surface_and_removed_symbols():
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/tasks/{task_id}/submission-requirements"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ContributorTaskSubmissionRequirements",
    }
    assert set(schema["components"]["schemas"]["ManagementTaskSubmissionRequirements"]["properties"]) == FIELDS
    assert "SubmissionRequirementsResponse" not in schema["components"]["schemas"]
    assert not hasattr(schemas, "SubmissionRequirementsResponse")
    assert not hasattr(TaskService, "_submission_requirements_response")
    assert set(schema["components"]["schemas"]["ContributorTaskSubmissionRequirements"]["properties"]) == FIELDS
