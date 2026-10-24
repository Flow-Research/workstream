"""Shared public drill operations; production API and durable owners retain authority."""

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4
from zipfile import ZipFile, ZipInfo
import time

import httpx
from sqlalchemy import select, text

from app.core.identifiers import new_record_id
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.projects.models import ProjectGuide
from app.modules.tasks.models import AuditEvent
from experiments.pilot04_external_checker_runtime.public_guide_setup import public_guide_setup
from api_contract_e2e import flow_settings, issue_flow_token

_GOVERNED_TABLES = (
    "task_post_submit_routing_requests", "task_post_submit_routing_manifests",
    "final_acceptances", "contribution_records", "compensation_awards", "reviews",
)

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _fixture_hashes(archive):
    """Derive expected identities from fixture bytes before public processing."""
    from tests.post_submit_materialization_helpers import _archive_facts

    _, manifest, _, archive_sha256 = _archive_facts(archive)
    return {'archive_sha256': archive_sha256, 'semantic_manifest_sha256': manifest.sha256}


def _assert_input_hashes(row, expected):
    _require(all(getattr(row, key) == value for key, value in expected.items()),
             'retained artifact differs from independently inspected submitted ZIP')


def _token(env: dict[str, str], actor) -> str:
    issuer, audience, secret = flow_settings(env)
    return issue_flow_token(
        str(actor.actor_profile_id), [], issuer=issuer, audience=audience, secret=secret
    )


def _with_fixture_file(archive: bytes, name: str) -> bytes:
    """Add a deterministic project-rule marker without changing valid packet members."""
    output = BytesIO(archive)
    with ZipFile(output, "a") as target:
        target.writestr(
            ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)),
            b"sample project rule marker\n",
        )
    return output.getvalue()


async def _json(client: httpx.AsyncClient, method: str, path: str, token: str,
                expected: int, **options) -> dict:
    headers = {"Authorization": "Bearer " + token, **options.pop("headers", {})}
    response = await client.request(method, path, headers=headers, **options)
    if response.status_code != expected:
        # Public error codes are enough to diagnose without printing guide bytes or tokens.
        try:
            error = response.json().get("error", {}).get("code")
        except ValueError:
            error = None
        raise RuntimeError(f"{method} {path} returned {response.status_code}/{error}; expected {expected}")
    return response.json()


async def _seed_contributor(factory) -> ActorIdentityFacts:
    """Create a Flow-linked human without an administrator role grant."""
    actor = ActorIdentityFacts(new_record_id(), new_record_id(), ActorKind.HUMAN)
    async with factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor.actor_profile_id), actor_kind="human", status="active",
            provisioning_method="automatic_first_access", created_by="public-probe-fixture",
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(actor.identity_link_id), actor_profile_id=str(actor.actor_profile_id),
            issuer="https://identity.flowresearch.tech",
            subject=str(actor.actor_profile_id), subject_kind="human",
            status="active", linked_by="public-probe-fixture",
            last_verified_at=datetime.now(UTC),
        ))
    return actor


async def _assert_outbox_worker_custody(session, event: OutboxEvent,
                                        project_id: UUID) -> None:
    """Bind the observed worker attempts to this event and project authority."""
    _require(event.project_id == str(project_id) and event.attempt_count > 0,
             "OUTBOX completion lacks this project's worker attempt")
    actor_id = await session.scalar(select(ActorProfile.id).where(
        ActorProfile.service_identity == ServiceIdentity.OUTBOX_DISPATCHER.value
    ))
    _require(actor_id is not None, "OUTBOX dispatcher actor is absent")
    attempts = (await session.scalars(select(OutboxDeliveryAttempt).where(
        OutboxDeliveryAttempt.event_id == event.event_id
    ).order_by(OutboxDeliveryAttempt.claim_generation))).all()
    _require(len(attempts) == event.attempt_count,
             "OUTBOX worker attempt history is incomplete")
    for generation, attempt in enumerate(attempts, 1):
        ids = (attempt.claim_decision_event_id, attempt.invoke_decision_event_id,
               attempt.finalize_decision_event_id)
        _require(attempt.claim_generation == generation
                 and attempt.project_id == str(project_id)
                 and attempt.payload_digest == event.payload_digest
                 and attempt.claim_owner.startswith("celery:")
                 and attempt.stage == "completed"
                 and all(ids) and len(set(ids)) == 3,
                 "OUTBOX worker attempt lacks exact completed phase custody")
        decisions = (await session.scalars(select(AuditEvent).where(
            AuditEvent.id.in_(ids)
        ))).all()
        _require(len(decisions) == 3 and {decision.id for decision in decisions} == set(ids),
                 "OUTBOX dispatch decisions are incomplete")
        for decision in decisions:
            _require(decision.actor_id == actor_id
                     and decision.event_type == "SensitiveAuthorizationAllowed"
                     and decision.action_id == decision.permission_id == "outbox.dispatch"
                     and decision.project_id == str(project_id)
                     and decision.resource_type == "outbox_event"
                     and decision.resource_id == str(event.event_id),
                     "OUTBOX phase decision differs from registered project dispatcher")


async def _assert_task_has_no_effects(session, task_id: str) -> None:
    """A second task cannot borrow its first task's accepted project evidence."""
    for table in _GOVERNED_TABLES:
        query = (
            "SELECT count(*) FROM public.compensation_awards a "
            "JOIN public.contribution_records c ON c.id=a.contribution_record_id "
            "WHERE c.task_id=:task"
            if table == "compensation_awards" else
            f"SELECT count(*) FROM public.{table} WHERE task_id=:task"
        )
        _require(await session.scalar(text(query), {"task": task_id}) == 0,
                 "late-refusal task committed governed effects")


async def _wait_outbox_acknowledged(factory, event_id: UUID, project_id: UUID) -> None:
    """Observe ordinary Beat-discovered delivery by the real prefork worker."""
    async with factory() as session:
        current = await session.get(OutboxEvent, event_id)
        _require(current is not None, "expected outbox event is missing")
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        async with factory() as session:
            event = await session.get(OutboxEvent, event_id)
            if event.delivery_state == "acknowledged":
                await _assert_outbox_worker_custody(session, event, project_id)
                return
            if event.delivery_state in {"dead_letter", "cancelled"}:
                raise RuntimeError(f"outbox event ended {event.delivery_state}")
        await asyncio.sleep(0.3)
    raise RuntimeError("Beat-discovered outbox event was not acknowledged by prefork worker")


async def _started_public_task(client, *, project_id: str, manager_token: str,
                               contributor_token: str, source_ref: str) -> tuple[str, str]:
    """Use the same public task, claim and start path for both project tasks."""
    from tests.test_tasks import complete_task_payload

    payload = complete_task_payload()
    payload["source_ref"] = source_ref
    created = await _json(
        client, "POST", f"/api/v1/projects/{project_id}/tasks", manager_token, 201,
        headers={"Idempotency-Key": str(uuid4())}, json=payload,
    )
    task_id = created["id"]
    for operation in ("screen", "release"):
        await _json(
            client, "POST", f"/api/v1/tasks/{task_id}/{operation}",
            manager_token, 200, headers={"Idempotency-Key": str(uuid4())},
            json={"reason": "Public first journey"},
        )
    claimed = await _json(
        client, "POST", f"/api/v1/tasks/{task_id}/claim", contributor_token,
        200, headers={"Idempotency-Key": str(uuid4())},
    )
    assignment_id = claimed["assignment"]["id"]
    await _json(
        client, "POST", f"/api/v1/tasks/{task_id}/start", contributor_token,
        200, headers={"Idempotency-Key": str(uuid4())},
    )
    await _json(
        client, "GET", f"/api/v1/tasks/{task_id}/submission-requirements",
        contributor_token, 200,
    )
    return task_id, assignment_id


async def _public_project(client, factory, env, *, human_review_required, pre_requirements=1):
    """Public guide activation and submitter grant shared by every runtime trial."""
    compilation = await public_guide_setup(
        client, factory, human_review_required, _json, lambda actor: _token(env, actor),
        pre_requirements=pre_requirements,
    )
    manager = compilation.manager
    guide_id = str(compilation.guide_id)
    contributor = await _seed_contributor(factory)

    manager_token, contributor_token = _token(env, manager), _token(env, contributor)
    project_id = str(compilation.project_id)
    activation_path = f"/api/v1/projects/{project_id}/guides/{guide_id}/activate"
    body = compilation.activation
    activation_headers = {"Idempotency-Key": str(uuid4())}
    activated = await _json(
        client, "POST", activation_path, manager_token, 200,
        headers=activation_headers, json=body,
    )
    _require(activated["prior_project_status"] == "draft"
             and activated["command"]["target"]["proposal"]["guide_id"] == guide_id,
             "public activation receipt lacks the draft guide lineage")
    async with factory() as session:
        bound = await session.get(ProjectGuide, guide_id)
        _require(bound is not None and bound.status == "active"
                 and str(bound.activation_operation_id) == activated["operation_id"],
                 "public activation did not bind the guide")
    replay = await _json(
        client, "POST", activation_path, manager_token, 200,
        headers=activation_headers, json=body,
    )
    _require(replay == activated, "public activation replay changed receipt")

    admitted = await _json(client, "GET", "/api/v1/actors/me", contributor_token, 200)
    _require(admitted["actor_profile_id"] == str(contributor.actor_profile_id),
             "Flow-linked contributor did not resolve to the stored human")
    role_grant = await _json(
        client, "POST", f"/api/v1/projects/{project_id}/role-grants",
        manager_token, 201,
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "target_actor_profile_id": str(contributor.actor_profile_id),
            "role": "submitter",
            "qualification": {
                "skills_snapshot": {
                    "availability": "unavailable", "reference_ids": [],
                    "unavailable_reason": "no_record",
                },
                "reputation_snapshot": {
                    "availability": "unavailable", "reference_ids": [],
                    "unavailable_reason": "no_record",
                },
                "prior_project_work_refs": [], "external_expertise_refs": [],
            },
            "reason": "Assign this contributor to the public first-journey task",
        },
    )
    _require(role_grant["role"] == "submitter"
             and role_grant["actor_profile_id"] == str(contributor.actor_profile_id),
             "public project submitter grant names another actor or role")

    return compilation, contributor, manager_token, contributor_token
