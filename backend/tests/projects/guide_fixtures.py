"""PROJECT guide, project authority and source-metadata test prerequisites."""

from __future__ import annotations

from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session as db_session
from app.modules.authorization.models import AdminRoleGrant
from app.modules.projects.models import PaymentPolicy
from projects.client_fixtures import auth_headers, ensure_access_administrator_bootstrap


def complete_guide_payload(version: str = "v1") -> dict:
    return {
        "version": version,
        "content_markdown": (
            f"# Guide {version}\n\n"
            "Contributors submit a complete project packet with original work, artifact "
            "hashes, evidence references, and an attestation. Reviewers use the "
            "locked policy bundle for automated checks and the guide body for human "
            "context."
        ),
        "change_summary": f"Initial {version}",
    }


async def create_project(client: AsyncClient, *, name: str = "STEM Eval") -> dict:
    slug = f"{name.lower().replace(' ', '-')}-{uuid4()}"
    response = await client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": name,
            "slug": slug,
            "description": "Internal STEM evaluation tasks",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_project_manager_admin_grant(project_id: str) -> UUID:
    """Grant the default registered human exact project diagnostic authority."""
    async with db_session.get_session_factory()() as session:
        existing = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.role == "project_manager",
                AdminRoleGrant.scope_project_id == project_id,
                AdminRoleGrant.status == "active",
            )
        )
        if existing is not None:
            return existing.id
    actor_id, _, grantor_id = await ensure_access_administrator_bootstrap()
    async with db_session.get_session_factory()() as session:
        grant = AdminRoleGrant(
            id=uuid4(),
            target_actor_profile_id=actor_id,
            role="project_manager",
            scope_type="project",
            scope_project_id=project_id,
            status="active",
            version=1,
            granted_by_actor_profile_id=actor_id,
            granted_by_admin_role_grant_id=grantor_id,
            grant_reason="AUTH-11C1 diagnostic read fixture",
        )
        session.add(grant)
        await session.commit()
        return grant.id


def source_snapshot_payload(*, source_label: str = "guide.md") -> dict:
    return {
        "items": [
            {
                "source_kind": "url_doc",
                "source_label": source_label,
                "ingestion_adapter": "manual_import",
                "media_type": "text/markdown",
            },
            {
                "source_kind": "rubric",
                "source_label": "rubric.md",
                "ingestion_adapter": "manual_import",
                "media_type": "text/markdown",
            },
        ]
    }


async def create_source_snapshot(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    payload: dict | None = None,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots",
        headers=auth_headers(),
        json=payload if payload is not None else source_snapshot_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_guide(client: AsyncClient, project_id: str, payload: dict) -> dict:
    request_payload = dict(payload)
    source_snapshot = request_payload.pop("source_snapshot", None)
    review_policy = request_payload.pop("review_policy", "default")
    revision_policy = request_payload.pop("revision_policy", "default")
    payment_policy = request_payload.pop("payment_policy", "default")
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides",
        headers=auth_headers(),
        json=request_payload,
    )
    assert response.status_code == 201, response.text
    guide = response.json()
    if review_policy is not None:
        values = (
            dict(review_policy)
            if isinstance(review_policy, dict)
            else {
                "requires_second_review": False,
                "allowed_decisions": ["accept", "needs_revision", "reject"],
                "minimum_finding_fields": ["issue", "required_fix"],
            }
        )
        values.pop("sla_hours", None)
        values = {
            "review_preference_window_seconds": 3600,
            "review_lease_duration_seconds": 1800,
            "max_active_review_leases_per_reviewer": 1,
            "self_review_allowed": False,
            "reject_policy": "close_task",
            "finding_evidence_requirement": "optional",
            **values,
        }
        policy_response = await client.put(
            f"/api/v1/projects/{project_id}/guides/{guide['id']}/review-policy",
            headers=auth_headers() | {"If-Match": '"no-current-policy"'},
            json=values,
        )
        assert policy_response.status_code == 200, policy_response.text
    if revision_policy is not None:
        values = (
            dict(revision_policy)
            if isinstance(revision_policy, dict)
            else {
                "max_revision_rounds": 7,
                "revision_deadline_hours": 48,
                "allowed_resubmission_states": ["needs_revision"],
                "reviewer_reassignment_rule": "same reviewer preferred",
            }
        )
        values.pop("auto_reject_after_limit", None)
        policy_response = await client.put(
            f"/api/v1/projects/{project_id}/guides/{guide['id']}/revision-policy",
            headers=auth_headers() | {"If-Match": '"no-current-policy"'},
            json=values,
        )
        assert policy_response.status_code == 200, policy_response.text
    async with db_session.get_session_factory()() as session:
        if payment_policy is not None:
            values = (
                payment_policy
                if isinstance(payment_policy, dict)
                else {
                    "base_amount": "25.00",
                    "currency": "USD",
                    "payout_type": "fixed",
                    "revision_payment_rule": "none",
                    "rejection_payment_rule": "none",
                    "accepted_payment_rule": "pay base amount",
                }
            )
            session.add(
                PaymentPolicy(
                    id=str(uuid4()),
                    project_id=project_id,
                    guide_version=guide["version"],
                    **values,
                )
            )
        await session.commit()
    await add_project_manager_admin_grant(project_id)
    if source_snapshot is not None:
        await create_source_snapshot(client, project_id, guide["id"], source_snapshot)
    return guide
