"""PostgreSQL regressions for the bounded external API drill repairs."""

from copy import deepcopy
import json
from uuid import UUID, uuid4

from httpx import AsyncClient
from pydantic import ValidationError
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.audit.schemas import ActorReferenceKind, AuthorityAuditEventInput, AuthorityEventType
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization import schemas as authority_schemas
from app.modules.authorization.models import AuthorityIdempotencyRecord, ProjectRoleGrant, ProjectRoleQualificationSnapshot
from app.modules.authorization.project_role_schemas import ProjectRoleGrantIssueBody
from app.modules.tasks.models import AuditEvent
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    Project,
    ProjectCreateIdempotencyRecord,
    ProjectGuide,
)
from app.modules.projects.schemas import ProjectCreate, ProjectGuideCreate, ProjectGuideUpdate
from projects.client_fixtures import (
    auth_headers,
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import complete_guide_payload, create_guide, create_project


PROJECT_TEXT_CASES = [
    ("project", "name"), ("project", "slug"), ("project", "description"),
    ("guide_create", "version"),
    ("guide_create", "change_summary"),
    ("guide_update", "change_summary"),
]


@pytest.mark.parametrize(("operation", "field"), PROJECT_TEXT_CASES)
def test_project_text_schema_rejects_nul_preserving_valid_values(operation: str, field: str) -> None:
    schema, payload = {
        "project": (ProjectCreate, {"name": "Name", "slug": "slug"}),
        "guide_create": (ProjectGuideCreate, {"version": "initial", "task_examples": [
            {"content": "Evaluate the assigned claim.", "title": None, "labels": []}]}),
        "guide_update": (ProjectGuideUpdate, {}),
    }[operation]
    for value in ("\x00leading", "embedded\x00nul", "trailing\x00", "line\n\x00"):
        with pytest.raises(ValidationError) as caught:
            schema.model_validate(payload | {field: value})
        assert caught.value.errors()[0]["loc"] == (field,)
        assert caught.value.errors()[0]["type"] == "string_pattern_mismatch"
    for value in ("", "  Unicode 名 é\nline\ttext  "):
        assert getattr(schema.model_validate(payload | {field: value}), field) == value
    if field in {"description", "change_summary"}:
        assert getattr(schema.model_validate(payload | {field: None}), field) is None
    else:
        with pytest.raises(ValidationError):
            schema.model_validate(payload | {field: None})
    assert ProjectGuideUpdate().model_dump(exclude_unset=True) == {}


async def project_text_state() -> list:
    """Selected product/replay tables only; includes hidden guide generation."""
    async with db_session.get_session_factory()() as session:
        return [(await session.execute(select(model.__table__).order_by(model.id))).mappings().all()
                for model in (Project, ProjectGuide, ProjectCreateIdempotencyRecord,
                              GuideMutationIdempotencyRecord)]


@pytest.mark.parametrize(("operation", "field"), PROJECT_TEXT_CASES)
async def test_project_text_nul_rejected_without_state_and_same_key_recovers(
    project_client: AsyncClient, operation: str, field: str,
) -> None:
    route, method, status = "/api/v1/projects", "POST", 201
    payload = {"name": "Unicode 名 project", "slug": "nul-" + uuid4().hex,
               "description": "Valid é description"}
    if operation != "project":
        project = await create_project(project_client)
        route += f"/{project['id']}/guides"
        payload = {"version": "initial", "task_examples": [
                       {"content": "Evaluate Unicode 名 claims.", "title": None, "labels": []}],
                   "change_summary": "Initial é summary"}
        if operation == "guide_update":
            created = await project_client.post(route, headers=auth_headers(), json=payload)
            assert created.status_code == 201, created.text
            route += "/" + created.json()["id"]
            method, status = "PATCH", 200
            payload = {"change_summary": "Updated é summary"}
    headers = auth_headers()
    before = await project_text_state()
    rejected = await project_client.request(method, route, headers=headers,
        json=payload | {field: "PRIVATE_BAD\x00TEXT"})
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "invalid_request"
    assert rejected.json()["error"]["retryable"] is False
    assert "PRIVATE_BAD" not in rejected.text
    assert await project_text_state() == before
    recovered = await project_client.request(method, route, headers=headers, json=payload)
    assert recovered.status_code == status, recovered.text
    for name, value in payload.items():
        assert recovered.json()[name] == value
    after = await project_text_state()
    assert after != before
    replay = await project_client.request(method, route, headers=headers, json=payload)
    assert replay.status_code == status, replay.text
    assert replay.json() == recovered.json()
    assert await project_text_state() == after


def maximum_qualification() -> dict:
    references = [f"{index:02d}" + "x" * 118 for index in range(20)]
    return {
        "skills_snapshot": {"availability": "available", "reference_ids": references[:],
                            "unavailable_reason": None},
        "reputation_snapshot": {"availability": "available", "reference_ids": references[:],
                                "unavailable_reason": None},
        "prior_project_work_refs": [str(uuid4()) for _ in range(20)],
        "external_expertise_refs": references[:],
    }


@pytest.mark.parametrize("field", ["display_name", "contact_email"])
async def test_profile_nul_rejected_without_partial_update(project_client: AsyncClient, field: str) -> None:
    route = "/api/v1/actors/me"
    control = await project_client.patch(route, headers=auth_headers(),
        json={"display_name": "Original 名", "contact_email": "opaque contact"})
    assert control.status_code == 200, control.text
    before = control.json()
    other = "contact_email" if field == "display_name" else "display_name"
    rejected = await project_client.patch(route, headers=auth_headers(),
        json={field: "before\x00after", other: "Must not persist"})
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "invalid_request"
    assert rejected.json()["error"]["retryable"] is False
    readback = await project_client.get(route, headers=auth_headers())
    assert readback.status_code == 200
    def stable(body: dict) -> dict:
        return {key: value for key, value in body.items()
                if key not in {"updated_at", "last_seen_at"}}
    assert stable(readback.json()) == stable(before)
    valid = await project_client.patch(route, headers=auth_headers(), json={field: "  Valid 名  "})
    assert valid.status_code == 200, valid.text
    assert valid.json()[field] == "Valid 名"
    assert valid.json()[other] == before[other]


async def test_context_nul_rejected_preserving_id_lookup_and_concealment(
    project_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client, name="Selector control")
    route = "/api/v1/actors/me/authorization-context"
    rejected = await project_client.get(route, headers=auth_headers(), params={"project_id": "before\x00after"})
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "invalid_request"
    assert rejected.json()["error"]["retryable"] is False
    assert "before" not in rejected.text
    response = await project_client.get(route, headers=auth_headers(), params={"project_id": project["id"]})
    assert response.status_code == 200, response.text
    assert response.json()["project_id"] == project["id"]
    assert response.json()["admin_roles"] == ["project_manager"]
    slug = await project_client.get(route, headers=auth_headers(), params={"project_id": project["slug"]})
    assert slug.status_code == 404, slug.text
    assert slug.json()["error"]["code"] == "project_authorization_resource_not_found"
    missing = await project_client.get(route, headers=auth_headers(), params={"project_id": str(uuid4())})
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "project_authorization_resource_not_found"
    try:
        with monkeypatch.context() as scoped:
            scoped.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", f"ungranted-selector-{uuid4()}")
            scoped.setenv("WORKSTREAM_DEV_AUTH_ROLES", "contributor")
            get_settings.cache_clear()
            admitted = await project_client.get("/api/v1/actors/me", headers=auth_headers())
            assert admitted.status_code == 200
            for selector in (project["id"], project["slug"]):
                concealed = await project_client.get(route, headers=auth_headers(), params={"project_id": selector})
                assert concealed.status_code == 404, concealed.text
                assert concealed.json()["error"]["code"] == "project_authorization_resource_not_found"
    finally:
        get_settings.cache_clear()


def maximum_role_request(role: str):
    body = ProjectRoleGrantIssueBody(target_actor_profile_id=uuid4(), role=role,
        qualification=maximum_qualification(), reason="Maximum qualification regression")
    return authority_schemas.ProjectRoleGrantIssueRequest(
        operation=authority_schemas.AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=uuid4(), target_actor_id=body.target_actor_profile_id, role=body.role,
        qualification=body.qualification, reason_digest=authority_schemas.derive_reason_digest(body.reason))


@pytest.mark.parametrize(("role", "size"), [("submitter", 8626), ("reviewer", 8625)])
def test_maximum_public_qualification_fits_canonical_authority_admission(role: str, size: int) -> None:
    request = maximum_role_request(role)
    encoded = json.dumps(request.model_dump(mode="json", exclude_none=True),
                         sort_keys=True, separators=(",", ":")).encode()
    assert len(encoded) == size
    assert 2048 < size <= 9 * 1024
    admitted = authority_schemas.parse_authority_request(request.model_dump())
    assert admitted == request


def assert_parser_error_drops_input(error: TypeError) -> None:
    assert str(error) == "invalid authority mutation request"
    assert error.__cause__ is None
    assert error.__context__ is None
    frames = []
    traceback = error.__traceback__
    while traceback is not None:
        if traceback.tb_frame.f_code is authority_schemas.parse_authority_request.__code__:
            frames.append(traceback.tb_frame.f_locals)
        traceback = traceback.tb_next
    assert len(frames) == 1
    # Caller frames necessarily own their inputs; the parser must not retain
    # its copies in either validation-failure or encoded-size-failure paths.
    for name in ("value", "candidate", "encoded", "admitted"):
        assert frames[0][name] is None


def test_qualification_expansion_preserves_closed_nonretaining_admission() -> None:
    request = maximum_role_request("submitter").model_dump()
    invalids = []
    for collection in ("skills_snapshot", "reputation_snapshot", "external_expertise_refs", "prior_project_work_refs"):
        invalid = deepcopy(request)
        references = invalid["qualification"][collection]
        if isinstance(references, dict):
            references = references["reference_ids"]
        references.append(references[0])
        invalids.append(invalid)
    secret = "PRIVATE_REJECTED_QUALIFICATION"
    invalid = deepcopy(request)
    invalid["qualification"]["external_expertise_refs"] = [secret + "x" * 121]
    invalids += [invalid, request | {"extra": secret},
                 request | {"operation": authority_schemas.AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE}]
    for value in invalids:
        with pytest.raises(TypeError, match="^invalid authority mutation request$") as caught:
            authority_schemas.parse_authority_request(value)
        assert secret not in str(caught.value)
        assert_parser_error_drops_input(caught.value)


@pytest.mark.parametrize("project_role", [False, True])
def test_authority_envelope_bound_is_operation_specific(monkeypatch: pytest.MonkeyPatch, project_role: bool) -> None:
    request = maximum_role_request("submitter") if project_role else authority_schemas.ActorProfileSuspendRequest(
        operation=authority_schemas.AuthorityOperation.ACTOR_PROFILE_SUSPEND,
        actor_profile_id=uuid4(), reason_digest=authority_schemas.derive_reason_digest("Bound proof"))
    limit = 9 * 1024 if project_role else 2048
    # Artificial serialization sizes exercise the guard itself; the real maximum
    # request test above separately proves the public schema's actual encoding.
    monkeypatch.setattr(authority_schemas.json, "dumps", lambda *args, **kwargs: "x" * limit)
    assert authority_schemas.parse_authority_request(request.model_dump()) == request
    secret = "PRIVATE_REJECTED_QUALIFICATION"
    monkeypatch.setattr(authority_schemas.json, "dumps",
                        lambda *args, **kwargs: secret + "x" * (limit + 1 - len(secret)))
    with pytest.raises(TypeError, match="^invalid authority mutation request$") as caught:
        authority_schemas.parse_authority_request(request.model_dump())
    assert_parser_error_drops_input(caught.value)


@pytest.mark.parametrize("role", ["submitter", "reviewer"])
async def test_maximum_qualification_grant_persists_replays_and_conflicts_without_extra_history(
    project_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, role: str,
) -> None:
    project = await create_project(project_client, name="Maximum qualification")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", f"qualification-target-{uuid4()}")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "contributor")
    get_settings.cache_clear()
    target = await project_client.get("/api/v1/actors/me", headers=auth_headers())
    assert target.status_code == 200, target.text
    actor_id = target.json()["actor_profile_id"]
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "project-manager-subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "project_manager")
    get_settings.cache_clear()
    qualification = maximum_qualification()
    payload = dict(target_actor_profile_id=actor_id, role=role, qualification=qualification,
                   reason="Maximum qualification regression")
    route = f"/api/v1/projects/{project['id']}/role-grants"
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    issued = await project_client.post(route, headers=headers, json=payload)
    assert issued.status_code == 201, issued.text
    replay = await project_client.post(route, headers=headers, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json() == issued.json()
    mismatch = await project_client.post(route, headers=headers, json=payload | {"reason": "Changed reason"})
    assert mismatch.status_code == 409, mismatch.text
    assert mismatch.json()["error"]["code"] == "idempotency_mismatch"
    conflict = await project_client.post(route, headers=auth_headers(), json=payload)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "project_role_grant_exists"
    read = await project_client.get(route + "/" + issued.json()["id"], headers=auth_headers())
    assert read.status_code == 200, read.text
    for field, expected in qualification.items():
        assert read.json()["qualification_snapshot"][field] == expected
    async with db_session.get_session_factory()() as session:
        grant = await session.get(ProjectRoleGrant, UUID(issued.json()["id"]))
        snapshot = await session.get(ProjectRoleQualificationSnapshot, UUID(issued.json()["qualification_snapshot_id"]))
        assert grant is not None and snapshot is not None
        assert grant.qualification_snapshot_id == snapshot.id
        assert (grant.project_id, grant.actor_profile_id, grant.role) == (project["id"], actor_id, role)
        for field, expected in qualification.items():
            assert getattr(snapshot, field) == expected
        assert await session.scalar(select(func.count()).select_from(ProjectRoleGrant)) == 1
        assert await session.scalar(select(func.count()).select_from(ProjectRoleQualificationSnapshot)) == 1
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", f"qualification-ungranted-{uuid4()}")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "contributor")
    get_settings.cache_clear()
    third_actor = await project_client.get("/api/v1/actors/me", headers=auth_headers())
    assert third_actor.status_code == 200, third_actor.text
    models = (ProjectRoleGrant, ProjectRoleQualificationSnapshot, AuthorityIdempotencyRecord, AuditEvent)
    async with db_session.get_session_factory()() as session:
        before = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    denied = await project_client.post(route, headers=auth_headers(), json=payload)
    assert denied.status_code == 404, denied.text
    assert denied.json()["error"]["code"] == "resource_not_found"
    async with db_session.get_session_factory()() as session:
        after = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    assert after == before


def test_api_drill_request_limits_are_exposed_in_openapi() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    assert schemas["ProjectRole"]["enum"] == ["submitter", "reviewer"]
    project = schemas["ProjectCreate"]["properties"]
    guide_create = schemas["ProjectGuideCreate"]["properties"]
    guide_update_schema = schemas["ProjectGuideUpdate"]
    guide_update = guide_update_schema["properties"]

    assert project["name"]["maxLength"] == 200
    assert project["slug"]["maxLength"] == 120
    assert guide_create["version"]["maxLength"] == 50
    assert "content_markdown" not in guide_create
    assert "content_markdown" not in guide_update
    assert {item.get("type") for item in guide_update["change_summary"]["anyOf"]} == {
        "null",
        "string",
    }


async def test_exact_unicode_project_and_guide_limits_persist_unchanged(
    project_client: AsyncClient,
) -> None:
    project_payload = {
        "name": "界" * 200,
        "slug": "ø" * 120,
        "description": "Exact character-limit proof",
    }
    project_response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json=project_payload,
    )
    assert project_response.status_code == 201, project_response.text
    assert project_response.json()["name"] == project_payload["name"]
    assert project_response.json()["slug"] == project_payload["slug"]

    version = "版" * 50
    guide_response = await project_client.post(
        f"/api/v1/projects/{project_response.json()['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload(version),
    )
    assert guide_response.status_code == 201, guide_response.text
    assert guide_response.json()["version"] == version

    async with db_session.get_session_factory()() as session:
        persisted_project = await session.get(Project, project_response.json()["id"])
        persisted_guide = await session.get(ProjectGuide, guide_response.json()["id"])
        assert persisted_project is not None
        assert persisted_guide is not None
        assert persisted_project.name == project_payload["name"]
        assert persisted_project.slug == project_payload["slug"]
        assert persisted_guide.version == version


@pytest.mark.parametrize(("field", "limit"), [("name", 200), ("slug", 120)])
async def test_project_overflow_has_no_state_and_same_key_recovers(
    project_client: AsyncClient,
    field: str,
    limit: int,
) -> None:
    key = uuid4()
    payload = {
        "name": "Overflow candidate",
        "slug": f"overflow-{uuid4()}",
    }
    payload[field] = "x" * (limit + 1)
    rejected = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=payload,
    )
    assert rejected.status_code == 422, rejected.text

    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(Project)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectCreateIdempotencyRecord)
                .where(ProjectCreateIdempotencyRecord.idempotency_key == key)
            )
            == 0
        )

    recovered_payload = {
        "name": "Recovered project",
        "slug": f"recovered-{uuid4()}",
    }
    recovered = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=recovered_payload,
    )
    assert recovered.status_code == 201, recovered.text
    assert recovered.json()[field] == recovered_payload[field]


async def test_guide_version_overflow_has_no_state_and_same_key_recovers(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client, name="Guide version recovery")
    key = uuid4()
    rejected = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=complete_guide_payload("v" * 51),
    )
    assert rejected.status_code == 422, rejected.text

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectGuide)
                .where(ProjectGuide.project_id == project["id"])
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GuideMutationIdempotencyRecord)
                .where(GuideMutationIdempotencyRecord.idempotency_key == key)
            )
            == 0
        )

    recovered = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=complete_guide_payload("recovered-v1"),
    )
    assert recovered.status_code == 201, recovered.text
    assert recovered.json()["version"] == "recovered-v1"


async def test_guide_content_null_has_no_state_then_recovery_and_omission_succeed(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client, name="Guide content recovery")
    seed_payload = complete_guide_payload() | {
        "review_policy": None,
        "revision_policy": None,
        "payment_policy": None,
    }
    guide = await create_guide(project_client, project["id"], seed_payload)
    path = f"/api/v1/projects/{project['id']}/guides/{guide['id']}"
    key = uuid4()
    async with db_session.get_session_factory()() as session:
        seeded = await session.get(ProjectGuide, guide["id"])
        assert seeded is not None
        seeded_updated_at = seeded.updated_at

    rejected = await project_client.patch(
        path,
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json={"content_markdown": None},
    )
    assert rejected.status_code == 422, rejected.text

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(ProjectGuide, guide["id"])
        assert persisted is not None
        assert persisted.change_summary == guide["change_summary"]
        assert persisted.updated_at == seeded_updated_at
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GuideMutationIdempotencyRecord)
                .where(GuideMutationIdempotencyRecord.idempotency_key == key)
            )
            == 0
        )

    replacement = "Valid metadata replacement."
    recovered = await project_client.patch(
        path,
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json={"change_summary": replacement},
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["change_summary"] == replacement

    summary_only = await project_client.patch(
        path,
        headers=auth_headers(),
        json={"change_summary": None},
    )
    assert summary_only.status_code == 200, summary_only.text
    assert "content_markdown" not in summary_only.json()
    assert summary_only.json()["change_summary"] is None

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(ProjectGuide, guide["id"])
        assert persisted is not None
        assert persisted.retained_content_markdown is None
        assert persisted.change_summary is None
        record = await session.scalar(
            select(GuideMutationIdempotencyRecord).where(
                GuideMutationIdempotencyRecord.idempotency_key == key
            )
        )
        assert record is not None
        assert record.status == "committed"


async def test_unsupported_adjudicator_role_is_rejected_without_grant(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client, name="Unsupported role")
    target_subject = f"role-target-{uuid4()}"
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", target_subject)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "contributor")
    get_settings.cache_clear()
    target_admission = await project_client.get("/api/v1/actors/me", headers=auth_headers())
    assert target_admission.status_code == 200, target_admission.text
    target_actor_id = target_admission.json()["actor_profile_id"]

    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "project-manager-subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "project_manager")
    get_settings.cache_clear()
    key = uuid4()
    payload = {
        "target_actor_profile_id": target_actor_id,
        "role": "adjudicator",
        "qualification": {
            "skills_snapshot": {
                "availability": "available",
                "reference_ids": ["skill:opaque"],
                "unavailable_reason": None,
            },
            "reputation_snapshot": {
                "availability": "unavailable",
                "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            "prior_project_work_refs": [],
            "external_expertise_refs": [],
        },
        "reason": "Current v0.1 role vocabulary regression",
    }
    headers = auth_headers() | {"Idempotency-Key": str(key)}
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/role-grants",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"]["errors"][0]["loc"] == ["body", "role"]

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectRoleGrant)
                .where(
                    ProjectRoleGrant.project_id == project["id"],
                    ProjectRoleGrant.actor_profile_id == target_actor_id,
                )
            )
            == 0
        )

    accepted = await project_client.post(
        f"/api/v1/projects/{project['id']}/role-grants",
        headers=headers,
        json=payload | {"role": "reviewer"},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["actor_profile_id"] == target_actor_id
    assert accepted.json()["role"] == "reviewer"

    async with db_session.get_session_factory()() as session:
        grant = await session.scalar(
            select(ProjectRoleGrant).where(
                ProjectRoleGrant.project_id == project["id"],
                ProjectRoleGrant.actor_profile_id == target_actor_id,
                ProjectRoleGrant.role == "reviewer",
                ProjectRoleGrant.status == "active",
            )
        )
        assert grant is not None



def test_adjudicator_invalidation_audit_facts_are_rejected() -> None:
    """Unsupported role facts cannot enter the typed authority audit contract."""
    project_id, event_id = uuid4(), uuid4()
    projection = {
        "role": "reviewer", "scope_type": "project", "scope_id": str(project_id),
        "future_obligation": "rev_reviewer_obligation",
    }
    event = AuthorityAuditEventInput(
        event_id=event_id,
        event_type=AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
        entity_type="authority_invalidation",
        entity_id=str(event_id),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(uuid4()),
        request_id=uuid4(),
        correlation_id=uuid4(),
        permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
        project_id=str(project_id),
        resource_type="actor_profile",
        resource_id=str(uuid4()),
        target_ref_kind="project_role_grant",
        target_ref_id=str(uuid4()),
        reason="authority_state_changed",
        idempotency_reference=uuid4(),
        invalidation_cause_event_id=uuid4(),
        invalidation_target_kind="actor_profile",
        invalidation_target_ref=str(uuid4()),
        before_facts={"effective": True, **projection},
        after_facts={"effective": False, **projection},
    )
    unsupported = projection | {"role": "adjudicator", "future_obligation": "none"}
    with pytest.raises(TypeError, match="^invalid authority audit input$"):
        AuthorityAuditEventInput.model_validate(event.model_dump() | {
            "before_facts": {"effective": True, **unsupported},
            "after_facts": {"effective": False, **unsupported},
        })
