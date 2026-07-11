"""Tests for structured review decisions and findings (Issue #34)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.review.models import (
    REVIEW_DECISION_ACCEPT,
    REVIEW_DECISION_NEEDS_REVISION,
    REVIEW_DECISION_REJECT,
)
from app.modules.tasks.models import AuditEvent, Submission, WorkstreamTask

from tests.test_tasks import (
    auth_headers,
    create_active_project,
    create_started_task,
    set_dev_actor,
)


# ── database fixtures (same pattern as test_tasks / test_checkers) ──


@pytest.fixture
def review_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
) -> Iterator[str]:
    """Fresh database migrated to head, downgraded after each test class/module."""
    import asyncio
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="review-test-subject")
    get_settings.cache_clear()

    from app.db import session as db_session
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
async def review_client(review_database_env: str) -> AsyncIterator[AsyncClient]:
    """httpx async client wired to the FastAPI app."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


# ── helpers ──


async def _create_locked_submission(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Return a locked submission that is ready for review."""
    project = await create_active_project(client)
    task = await create_started_task(client, project["id"], monkeypatch)
    submission_resp = await client.post(
        f"/api/v1/tasks/{task['id']}/submit",
        headers=auth_headers(),
        json={
            "summary": "test submission",
            "package_hash": "sha256:test",
            "worker_attestation": "I attest this is original.",
            "artifact_hash_manifest": [],
            "evidence_items": [{"type": "log", "label": "test", "uri": "local://test", "hash": "sha256:test"}],
        },
    )
    assert submission_resp.status_code == 201, submission_resp.text
    submission = submission_resp.json()
    # finalize submission to lock it
    finalize_resp = await client.post(
        f"/api/v1/tasks/{task['id']}/submissions/{submission['id']}/finalize",
        headers=auth_headers(),
        json={"reason": "ready for review"},
    )
    # finalize may succeed or already be locked
    assert finalize_resp.status_code in (200, 409), finalize_resp.text
    return submission


def _finding_payload(severity: str = "medium") -> dict:
    return {
        "severity": severity,
        "area": "logic",
        "issue": "incorrect computation in step 3",
        "required_fix": "re-run with correct formula",
        "evidence_ref": "file://line 42",
    }


def _review_payload(submission_id: str, decision: str, **overrides) -> dict:
    body = {
        "submission_id": submission_id,
        "decision": decision,
        "acceptance_evidence_refs": [],
        "comment": None,
        "findings": [],
    }
    body.update(overrides)
    return body


# ── tests ──


class TestReviewDecisionValidation:
    """Acceptance: API rejects unknown decision values."""

    async def test_rejects_unknown_decision(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(submission["id"], "approved")
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"

    async def test_rejects_empty_decision(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(submission["id"], "")  # empty string
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"


class TestRejectAndNeedsRevisionRequireFindings:
    """Acceptance: reject / needs_revision require at least one finding."""

    async def test_reject_without_findings_is_rejected(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(submission["id"], REVIEW_DECISION_REJECT, findings=[])
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"
        assert "finding" in resp.text.lower()

    async def test_needs_revision_without_findings_is_rejected(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(submission["id"], REVIEW_DECISION_NEEDS_REVISION, findings=[])
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"
        assert "finding" in resp.text.lower()


class TestAcceptRequiresEvidence:
    """Acceptance: accept requires evidence refs and no blocking checker results."""

    async def test_accept_without_evidence_is_rejected(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(submission["id"], REVIEW_DECISION_ACCEPT, acceptance_evidence_refs=[])
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"
        assert "evidence" in resp.text.lower()

    async def test_accept_blocked_by_checker_result(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept must be rejected when a CheckerResult with blocks_review=True exists."""
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)

        # Seed a blocking checker result directly
        async with db_session.get_session_factory()() as session:
            session.add(CheckerResult(
                id=str(uuid4()),
                checker_run_id=str(uuid4()),  # orphaned run id is fine for this test
                task_id=submission["task_id"],
                submission_id=submission["id"],
                checker_name="blocking-checker",
                status="failed",
                severity="high",
                blocks_review=True,
                message="blocked for testing",
            ))
            await session.commit()

        body = _review_payload(
            submission["id"],
            REVIEW_DECISION_ACCEPT,
            acceptance_evidence_refs=["evidence/log.txt"],
        )
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"
        assert "blocking" in resp.text.lower()


class TestAuditEventCreated:
    """Acceptance: audit event records review decision with actor identity."""

    async def test_review_creates_audit_event(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(
            submission["id"],
            REVIEW_DECISION_NEEDS_REVISION,
            findings=[_finding_payload("high")],
        )
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 201, f"expected 201, got {resp.status_code}: {resp.text}"
        review_json = resp.json()
        assert review_json["decision"] == REVIEW_DECISION_NEEDS_REVISION
        assert len(review_json["findings"]) == 1

        # Verify audit event exists
        async with db_session.get_session_factory()() as session:
            audit = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "review",
                    AuditEvent.entity_id == review_json["id"],
                )
            )
            assert audit is not None, "no audit event found for created review"
            assert audit.event_type == "review_decision_created"
            assert audit.actor_id != ""


class TestSuccessfulDecisionFlows:
    """End-to-end: valid decisions produce correct responses."""

    async def test_reject_with_finding_succeeds(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(
            submission["id"],
            REVIEW_DECISION_REJECT,
            findings=[_finding_payload("critical"), _finding_payload("high")],
        )
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["decision"] == REVIEW_DECISION_REJECT
        assert len(data["findings"]) == 2

    async def test_accept_with_evidence_succeeds(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)
        body = _review_payload(
            submission["id"],
            REVIEW_DECISION_ACCEPT,
            acceptance_evidence_refs=["evidence/checker-log.txt"],
        )
        resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["decision"] == REVIEW_DECISION_ACCEPT
        assert len(data["acceptance_evidence_refs"]) == 1

    async def test_query_reviews_for_submission(
        self, review_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_dev_actor(monkeypatch, roles="project_manager,reviewer", subject="reviewer-actor")
        submission = await _create_locked_submission(review_client, monkeypatch)

        # create two reviews
        for _ in range(2):
            body = _review_payload(
                submission["id"],
                REVIEW_DECISION_NEEDS_REVISION,
                findings=[_finding_payload()],
            )
            resp = await review_client.post("/api/v1/reviews", headers=auth_headers(), json=body)
            assert resp.status_code == 201, resp.text

        # query
        list_resp = await review_client.get(
            f"/api/v1/reviews/{submission['id']}", headers=auth_headers(),
        )
        assert list_resp.status_code == 200, list_resp.text
        reviews = list_resp.json()
        assert len(reviews) == 2
