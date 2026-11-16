"""Built CLI -> real public API/PostgreSQL exact revision-repair authority."""

import asyncio
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import select, text

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "tests"))

from app.core.identifiers import new_record_id  # noqa: E402
from app.modules.tasks.revision.models import TaskRevisionPreparation  # noqa: E402
from tests.conftest import (  # noqa: E402
    configured_source_instance_id as configured_source_instance_id,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    isolated_database_env as isolated_database_env,
)
from tests.project_create_fixtures import seed_historical_project  # noqa: E402
from tests.tasks.post_submit_routing.remediation_support import remediation_source  # noqa: E402
from tests.tasks.post_submit_routing.support import activate_successor_guide  # noqa: E402
from tests.tasks.submission_dispatch.test_revision_capacity import (  # noqa: E402
    _retain_pre_revision_source,
)
from tests.tasks.test_public_submission_intake import _client  # noqa: E402
from tests.test_submission_predecessor_custody import _fixture_revision_context  # noqa: E402
from test_submission_public_api import socket_api  # noqa: E402


@pytest.mark.asyncio
async def test_cli_repairs_missing_root_then_paused_and_running_heads_under_fresh_authority(
    isolated_database_env,
    tmp_path,
    monkeypatch,
    cli,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        original_id = h.revision_preparation_id
        await _retain_pre_revision_source(h, source_id)
        foreign_project = new_record_id()
        async with h.factory() as session, session.begin():
            await seed_historical_project(
                session,
                project_id=str(foreign_project),
                name="Foreign revision project",
                slug="foreign-revision-project",
            )
        async with _client(h, monkeypatch, isolated_database_env) as direct:
            async with socket_api(direct._transport.app) as origin:
                route = f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair"

                async def call(
                    project, *, key, reason, parent=None, manifest=None, denied=None
                ):
                    selectors = (
                        (
                            "--parent-preparation-id",
                            parent[0],
                            "--parent-preparation-sha256",
                            parent[1],
                        )
                        if parent
                        else ("--routing-manifest-id", manifest)
                    )
                    result = await asyncio.to_thread(
                        cli,
                        origin,
                        "public-intake-token",
                        "project",
                        "task",
                        "repair-revision",
                        str(project),
                        str(h.request.task_id),
                        "--idempotency-key",
                        str(key),
                        "--reason",
                        reason,
                        *selectors,
                        "-o",
                        "json",
                        process_timeout=30,
                    )
                    assert result.returncode == (1 if denied else 0), result.stderr
                    assert result.stdout == "" if denied else result.stderr == ""
                    value = json.loads(result.stderr if denied else result.stdout)
                    if denied:
                        assert value["error"]["status"] == denied
                    return value

                root_key, root_reason = (
                    new_record_id(),
                    "Recover original routed failure",
                )
                root = await call(
                    h.request.project_id,
                    key=root_key,
                    reason=root_reason,
                    manifest=str(source_id),
                )
                assert (
                    root["sequence"] == 1 and root["predecessor_preparation_id"] is None
                )
                assert root["source_routing_manifest_id"] == str(source_id)
                assert root["preparation_id"] != str(original_id)
                assert (
                    root["clock_state"] == "running" and root["disposition"] == "ready"
                )
                assert (
                    await call(
                        h.request.project_id,
                        key=root_key,
                        reason=root_reason,
                        manifest=str(source_id),
                    )
                    == root
                )
                await call(
                    h.request.project_id,
                    key=root_key,
                    reason="Changed recovery",
                    manifest=str(source_id),
                    denied=409,
                )
                await call(
                    foreign_project,
                    key=new_record_id(),
                    reason=root_reason,
                    manifest=str(source_id),
                    denied=404,
                )

                await activate_successor_guide(h, max_revision_rounds=0)
                pause_key, pause_reason = (
                    new_record_id(),
                    "Pause while target revision limit is too low",
                )
                paused = await call(
                    h.request.project_id,
                    key=pause_key,
                    reason=pause_reason,
                    parent=(root["preparation_id"], root["preparation_sha256"]),
                )
                assert paused["predecessor_preparation_id"] == root["preparation_id"]
                assert (
                    paused["clock_state"] == "paused" and paused["deadline_at"] is None
                )
                assert (
                    paused["remaining_microseconds"] > 0
                    and paused["disposition"] == "context_blocked"
                )
                assert (
                    await call(
                        h.request.project_id,
                        key=pause_key,
                        reason=pause_reason,
                        parent=(root["preparation_id"], root["preparation_sha256"]),
                    )
                    == paused
                )
                await call(
                    h.request.project_id,
                    key=new_record_id(),
                    reason=pause_reason,
                    parent=(root["preparation_id"], root["preparation_sha256"]),
                    denied=409,
                )

                await activate_successor_guide(h, max_revision_rounds=2, version="v3")
                resume_key, resume_reason = (
                    new_record_id(),
                    "Adopt corrected active revision policy",
                )
                resumed = await call(
                    h.request.project_id,
                    key=resume_key,
                    reason=resume_reason,
                    parent=(paused["preparation_id"], paused["preparation_sha256"]),
                )
                assert resumed["predecessor_preparation_id"] == paused["preparation_id"]
                assert (
                    resumed["clock_state"] == "running"
                    and resumed["remaining_microseconds"] is None
                )
                assert (
                    resumed["deadline_at"] is not None
                    and resumed["disposition"] == "ready"
                )
                assert resumed["requested_at"] == root["requested_at"]
                assert (
                    await call(
                        h.request.project_id,
                        key=resume_key,
                        reason=resume_reason,
                        parent=(paused["preparation_id"], paused["preparation_sha256"]),
                    )
                    == resumed
                )
                direct_replay = await direct.post(
                    route,
                    json={
                        "parent_preparation_id": paused["preparation_id"],
                        "parent_preparation_sha256": paused["preparation_sha256"],
                        "reason": resume_reason,
                    },
                    headers={"Idempotency-Key": str(resume_key)},
                )
                assert (
                    direct_replay.status_code == 200 and direct_replay.json() == resumed
                )

                async with h.factory() as session:
                    heads = (
                        await session.scalars(
                            select(TaskRevisionPreparation)
                            .where(
                                TaskRevisionPreparation.routing_manifest_id
                                == source_id,
                            )
                            .order_by(TaskRevisionPreparation.sequence)
                        )
                    ).all()
                    assert [str(head.id) for head in heads] == [
                        root["preparation_id"],
                        paused["preparation_id"],
                        resumed["preparation_id"],
                    ]
                    assert [head.repair_idempotency_key for head in heads] == [
                        root_key,
                        pause_key,
                        resume_key,
                    ]
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM public.audit_events WHERE event_type='TaskRevisionContextRepaired'"
                            )
                        )
                        == 3
                    )

                # A same-key replay still needs a currently active caller.
                async with h.factory() as session, session.begin():
                    await session.execute(
                        text(
                            "UPDATE public.actor_profiles SET status='suspended', "
                            "suspended_by='cli-repair-proof', suspended_at=clock_timestamp(), "
                            "suspension_reason='Replay authority revoked' WHERE id=:id"
                        ),
                        {"id": str(h.actor_context.actor_profile_id)},
                    )
                await call(
                    h.request.project_id,
                    key=resume_key,
                    reason=resume_reason,
                    parent=(paused["preparation_id"], paused["preparation_sha256"]),
                    denied=403,
                )
