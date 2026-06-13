from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.projects.models import (
    CheckerPolicy,
    PaymentPolicy,
    ProjectGuide,
    RevisionPolicy,
    ReviewPolicy,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError


@pytest.fixture
def project_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "project-token")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "project-manager-subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "flow-test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "project_manager")
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())

    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    with migration_lock():
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield postgres_database_url
        command.downgrade(config, "base")
    asyncio.run(db_session.dispose_engine())
    get_settings.cache_clear()


@pytest.fixture
async def project_client(project_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


def auth_headers(token: str = "project-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_project_guide_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in ProjectGuide.__table__.indexes
        if index.name == "uq_project_guides_one_active_per_project"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "status = 'active'" in postgres_compiled


def test_policy_models_have_project_guide_foreign_keys() -> None:
    expected_constraints = {
        CheckerPolicy: "fk_checker_policies_project_guide",
        ReviewPolicy: "fk_review_policies_project_guide",
        RevisionPolicy: "fk_revision_policies_project_guide",
        PaymentPolicy: "fk_payment_policies_project_guide",
    }

    for model, constraint_name in expected_constraints.items():
        constraint = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )

        assert [column.name for column in constraint.columns] == ["project_id", "guide_version"]
        assert [element.column.table.name for element in constraint.elements] == [
            "project_guides",
            "project_guides",
        ]
        assert [element.column.name for element in constraint.elements] == ["project_id", "version"]


def complete_guide_payload(version: str = "v1") -> dict:
    return {
        "version": version,
        "content_markdown": f"# Guide {version}",
        "required_task_fields": ["title", "description", "acceptance_criteria"],
        "required_submission_fields": ["summary", "evidence", "worker_attestation"],
        "task_instructions": "Do the task.",
        "output_requirements": "Submit a packet.",
        "acceptance_criteria": "Meets the guide.",
        "rejection_criteria": "Missing evidence.",
        "reviewer_rubric": "Check evidence and output.",
        "forbidden_actions": "No copied work.",
        "required_skills": ["stem"],
        "difficulty_scale": {"easy": 1, "hard": 3},
        "estimated_time_policy": {"default_minutes": 60},
        "common_rejection_reasons": ["missing evidence"],
        "evidence_policy": {"required": ["log"]},
        "unacceptable_work_policy": "Copied or unverifiable work.",
        "change_summary": f"Initial {version}",
        "checker_policy": {
            "required_checkers": ["check_policy_context_present"],
            "warning_checkers": [],
            "blocking_severities": ["high"],
        },
        "review_policy": {
            "requires_second_review": False,
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": ["issue", "required_fix"],
            "sla_hours": 24,
        },
        "revision_policy": {
            "max_revision_rounds": 7,
            "revision_deadline_hours": 48,
            "auto_reject_after_limit": True,
            "allowed_resubmission_states": ["needs_revision"],
            "reviewer_reassignment_rule": "same reviewer preferred",
        },
        "payment_policy": {
            "base_amount": "25.00",
            "currency": "USD",
            "payout_type": "fixed",
            "revision_payment_rule": "none",
            "rejection_payment_rule": "none",
            "accepted_payment_rule": "pay base amount",
        },
    }


async def create_project(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "STEM Eval",
            "slug": "stem-eval",
            "description": "Internal STEM evaluation tasks",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_guide(client: AsyncClient, project_id: str, payload: dict) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides",
        headers=auth_headers(),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_project_can_be_created(project_client: AsyncClient) -> None:
    project = await create_project(project_client)

    assert project["name"] == "STEM Eval"
    assert project["status"] == "draft"
    assert project["currency"] == "USD"


async def test_draft_guide_can_be_created(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    assert guide["version"] == "v1"
    assert guide["status"] == "draft"
    assert guide["created_by"]


async def test_activation_requires_evidence_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["evidence_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "evidence policy" in response.json()["detail"]


async def test_activation_requires_all_policies(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["checker_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "checker policy" in response.json()["detail"]


async def test_activation_requires_review_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["review_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "review policy" in response.json()["detail"]


async def test_activation_requires_payment_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["payment_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "payment policy is required" in response.json()["detail"]


async def test_activation_requires_revision_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "revision policy is required" in response.json()["detail"]


async def test_review_policy_rejects_invalid_decision_names(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["review_policy"]["allowed_decisions"] = ["accept", "hold"]

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "allowed_decisions" in detail["loc"]
    assert detail["input"] == "hold"


async def test_activation_requires_complete_payment_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["payment_policy"]["accepted_payment_rule"] = None
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "payment policy is incomplete" in response.json()["detail"]


async def test_activation_requires_complete_revision_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"]["allowed_resubmission_states"] = []
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "revision policy is incomplete" in response.json()["detail"]


async def test_revision_policy_requires_deadline(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    del payload["revision_policy"]["revision_deadline_hours"]

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "revision_deadline_hours" in detail["loc"]


async def test_activation_rejects_unregistered_checker_names(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["checker_policy"]["required_checkers"] = ["missing_checker"]
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "unregistered checker policy names" in response.json()["detail"]


async def test_activation_rejects_unsupported_revision_resubmission_states(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"]["allowed_resubmission_states"] = ["random_state"]
    guide = await create_guide(project_client, project["id"], payload)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "invalid resubmission states" in response.json()["detail"]


async def test_guide_activation_and_active_guide_retrieval(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    active = await project_client.get(
        f"/api/v1/projects/{project['id']}/active-guide",
        headers=auth_headers(),
    )

    assert activation.status_code == 200, activation.text
    assert active.status_code == 200, active.text
    assert active.json()["guide"]["status"] == "active"
    assert active.json()["guide"]["version"] == "v1"
    assert active.json()["checker_policy"]["required_checkers"] == [
        "check_policy_context_present"
    ]
    assert active.json()["revision_policy"]["max_revision_rounds"] == 7
    assert active.json()["revision_policy"]["auto_reject_after_limit"] is True
    assert active.json()["payment_policy"]["base_amount"] == "25.00"


async def test_draft_guide_edit_and_active_guide_edit_block(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    draft_update = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={
            "content_markdown": "# Updated draft",
            "evidence_policy": {"required": ["log", "hash"]},
        },
    )
    assert draft_update.status_code == 200, draft_update.text
    assert draft_update.json()["content_markdown"] == "# Updated draft"

    activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    assert activation.status_code == 200, activation.text

    active_update = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"content_markdown": "# Mutate active"},
    )
    assert active_update.status_code == 409


async def test_new_active_guide_supersedes_prior_without_mutating_content(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    first = await create_guide(project_client, project["id"], complete_guide_payload("v1"))
    first_activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{first['id']}/activate",
        headers=auth_headers(),
    )
    assert first_activation.status_code == 200, first_activation.text

    second = await create_guide(project_client, project["id"], complete_guide_payload("v2"))
    second_activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{second['id']}/activate",
        headers=auth_headers(),
    )

    assert second_activation.status_code == 200, second_activation.text
    assert second_activation.json()["guide"]["version"] == "v2"

    async with db_session.get_session_factory()() as session:
        first_guide = await session.get(ProjectGuide, first["id"])

    assert first_guide is not None
    assert first_guide.status == "superseded"
    assert first_guide.content_markdown == "# Guide v1"


async def test_database_enforces_single_active_guide_per_project(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    first = await create_guide(project_client, project["id"], complete_guide_payload("v1"))
    second = await create_guide(project_client, project["id"], complete_guide_payload("v2"))

    async with db_session.get_session_factory()() as session:
        first_guide = await session.get(ProjectGuide, first["id"])
        second_guide = await session.get(ProjectGuide, second["id"])
        assert first_guide is not None
        assert second_guide is not None
        first_guide.status = "active"
        second_guide.status = "active"
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_active_guide_lookup_surfaces_duplicate_rows() -> None:
    guides = [
        ProjectGuide(id="guide-1", project_id="project-1", version="v1", status="active"),
        ProjectGuide(id="guide-2", project_id="project-1", version="v2", status="active"),
    ]

    class FakeScalars:
        def all(self) -> list[ProjectGuide]:
            return guides

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    class FakeSession:
        async def execute(self, statement) -> FakeResult:
            return FakeResult()

    with pytest.raises(ProjectRepositoryIntegrityError, match="multiple active guides"):
        await ProjectRepository(FakeSession()).get_active_guide("project-1")


async def test_activation_conflict_returns_conflict_response(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client)
    first = await create_guide(project_client, project["id"], complete_guide_payload("v1"))
    first_activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{first['id']}/activate",
        headers=auth_headers(),
    )
    assert first_activation.status_code == 200, first_activation.text

    second = await create_guide(project_client, project["id"], complete_guide_payload("v2"))

    async def hide_active_guides(self: ProjectRepository, project_id: str) -> list[ProjectGuide]:
        return []

    monkeypatch.setattr(ProjectRepository, "list_active_guides", hide_active_guides)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{second['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 409
    assert "concurrent update" in response.json()["detail"]


async def test_worker_cannot_create_project_records(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "worker")
    get_settings.cache_clear()

    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={"name": "Worker Project", "slug": "worker-project"},
    )

    assert response.status_code == 403


async def test_project_create_validation_errors_are_structured(project_client: AsyncClient) -> None:
    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={"slug": "missing-name"},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
