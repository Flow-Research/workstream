"""Authorized persisted policy configuration and current activation reachability."""

from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
import pytest

from app.db import session as db_session
from app.modules.projects.models import ReviewPolicy
from app.modules.projects.policy_mutation_service import policy_selector_etag
from projects.client_fixtures import (
    auth_headers,
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import create_project, create_guide, complete_guide_payload


async def _replace(client, project, guide, prior, mode=None, key=None):
    body = {"review_preference_window_seconds": 3600, "review_lease_duration_seconds": 1800}
    if mode is not None:
        body["human_review_required"] = mode
    return await client.put(
        f"/api/v1/projects/{project}/guides/{guide}/review-policy",
        headers=auth_headers()
        | {
            "If-Match": policy_selector_etag(prior.id, prior.policy_generation, prior.policy_hash),
            "Idempotency-Key": str(key or uuid4()),
        },
        json=body,
    )


async def _selected(project, version):
    async with db_session.get_session_factory()() as session:
        return await session.scalar(
            select(ReviewPolicy)
            .where(ReviewPolicy.project_id == project, ReviewPolicy.guide_version == version)
            .order_by(ReviewPolicy.policy_generation.desc())
        )


async def test_persisted_false_survives_omitted_update_and_old_version_is_immutable(project_client):
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    first = await _selected(project["id"], guide["version"])
    assert first.human_review_required is True and first.semantics_format == "v2"
    response = await _replace(project_client, project["id"], guide["id"], first, False)
    assert response.status_code == 200, response.text
    assert response.json()["human_review_required"] is False
    second = await _selected(project["id"], guide["version"])
    assert second.policy_hash != first.policy_hash
    key = uuid4()
    omitted = await _replace(project_client, project["id"], guide["id"], second, key=key)
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["human_review_required"] is False
    third = await _selected(project["id"], guide["version"])
    assert third.policy_hash == second.policy_hash
    explicit = await _replace(project_client, project["id"], guide["id"], third, True)
    assert explicit.status_code == 200, explicit.text
    replay = await _replace(project_client, project["id"], guide["id"], second, key=key)
    assert replay.status_code == 200 and replay.json() == omitted.json()
    async with db_session.get_session_factory()() as session:
        historical = await session.get(ReviewPolicy, first.id)
        assert historical.human_review_required is True
        assert historical.policy_hash == first.policy_hash
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                text("update review_policies set human_review_required=false where id=:id"),
                {"id": first.id},
            )
        await session.rollback()
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                text("update review_policies set semantics_format='v1' where id=:id"),
                {"id": first.id},
            )
        await session.rollback()




async def test_cross_project_mode_mutation_cannot_advance_policy(project_client):
    project = await create_project(project_client)
    foreign = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    prior = await _selected(project["id"], guide["version"])
    response = await _replace(project_client, foreign["id"], guide["id"], prior, False)
    assert response.status_code == 404, response.text
    current = await _selected(project["id"], guide["version"])
    assert current.id == prior.id and current.human_review_required is True


async def test_new_false_request_requires_current_project_manager_authority(
    project_client, monkeypatch
):
    from app.core.config import get_settings

    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    prior = await _selected(project["id"], guide["version"])
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "unprivileged-policy-caller")
    get_settings.cache_clear()
    denied = await _replace(project_client, project["id"], guide["id"], prior, False)
    assert denied.status_code == 403, denied.text
    current = await _selected(project["id"], guide["version"])
    assert current.id == prior.id and current.human_review_required is True
