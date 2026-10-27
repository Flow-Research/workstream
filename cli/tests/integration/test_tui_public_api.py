"""Built native PTY/ConPTY -> real socket/Flow verifier -> isolated PostgreSQL.

Canonical fixtures arrange an approved guide, started work and a retained
immutable attempt. The original test remains GET-only; the separate action
test proves claim/start through the native UI. Neither is a public intake or
external artifact-provider journey. No AUTH/TASK port is replaced; only the
signed fixture issuer's JWKS transport is local.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from test_public_self_service import (
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
)
from test_submission_public_api import socket_api
from tui_terminal_support import Terminal
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.authorization.models import ProjectRoleGrant
from app.modules.checkers.models import CheckerRun
from app.modules.contributions.records.models import ContributionRecord
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from tests.authentication.fixtures import (
    auth_database_env as _auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authentication.support import issue_asymmetric_token
from tests.authorization.admin_access.fixtures import (
    admin_access as _admin_access,
    signed_access as _signed_access,
)
from tests.authorization.admin_access.support import SignedActor
from tests.authorization.task_authority.test_postgresql import grant, project_manager
from tests.authorization.task_reads.support import create_task
from tests.conftest import (
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.tasks.test_submission_lineage import _prepared_packet

signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)
admin_access = pytest_asyncio.fixture(_admin_access.__wrapped__)
auth_database_env = _auth_database_env


@pytest.mark.asyncio
async def test_tui_real_signed_owner_positive_reads_then_fresh_grant_revocation(
    tmp_path, auth_database_env, admin_access
):
    signed = admin_access.signed
    async with _prepared_packet(auth_database_env, tmp_path) as h:
        # Bind the actual stored identity link, not intake_client's actor override.
        subject = f"human-{h.context.actor_profile_id}"
        owner = SignedActor(
            h.context.actor_profile_id,
            subject,
            issue_asymmetric_token(
                signed.private_key,
                claims={"sub": subject, "jti": str(uuid4()), "roles": []},
            ),
        )
        client = signed.client
        profile = await client.get("/api/v1/actors/me", headers=owner.headers)
        assert profile.status_code == 200, profile.text
        assert profile.json()["actor_profile_id"] == str(owner.id)
        async with h.factory() as session:
            receipt = await compose_hidden_submission_creation_command(
                session,
                h.context,
                request_id=new_record_id(),
                correlation_id=new_record_id(),
            ).create(h.creation)
        submission_id = str(receipt.submission_id)
        access = SimpleNamespace(signed=signed)
        ready_id = await create_task(access, h.project_id, owner)
        project, task = str(h.project_id), str(h.task_id)
        paths = {
            "projects": "/api/v1/actors/me/projects?limit=50",
            "ready": f"/api/v1/projects/{project}/tasks/ready?limit=50",
            "mine": f"/api/v1/actors/me/assignments?project_id={project}&state=active&limit=50",
            "attempts": f"/api/v1/actors/me/submissions?project_id={project}&limit=50",
            "task": f"/api/v1/tasks/{task}",
            "ready_task": f"/api/v1/tasks/{ready_id}",
            "context": f"/api/v1/tasks/{task}/work-context",
            "intake": f"/api/v1/tasks/{task}/submission-requirements",
            "submission": f"/api/v1/submissions/{submission_id}",
        }
        direct = {}
        for name, path in paths.items():
            response = await client.get(path, headers=owner.headers)
            assert response.status_code == 200, (name, response.text)
            direct[name] = response.json()
        assert [item["project_id"] for item in direct["projects"]["items"]] == [project]
        assert [item["task_id"] for item in direct["ready"]["items"]] == [str(ready_id)]
        assert [item["task_id"] for item in direct["mine"]["items"]] == [task]
        assert [item["submission_id"] for item in direct["attempts"]["items"]] == [
            submission_id
        ]
        assert direct["submission"]["task_id"] == task
        assert (
            direct["context"]["task"]["task_id"] == direct["intake"]["task_id"] == task
        )
        assert (
            direct["context"]["guide"]["version"] == direct["intake"]["guide_version"]
        )
        assert (
            direct["ready"]["items"][0]["compensation"]
            == direct["ready_task"]["compensation"]
        )
        # A different signed, genuinely granted actor still cannot inspect an
        # immutable attempt or reuse its assignment-sensitive guide context.
        foreign = await signed.actor("tui-foreign-owner", roles=())
        await grant(SimpleNamespace(signed=signed, target=foreign), owner, h.project_id)
        for name in ("submission", "context"):
            response = await client.get(paths[name], headers=foreign.headers)
            assert response.status_code == 404, (name, response.text)
        # The real role-grant owner forbids self revocation. Use a distinct
        # signed manager whose exact project grant was issued by the actual
        # bootstrapped administrator, rather than bypassing that guard.
        manager = await project_manager(admin_access, h.project_id)

        models = (
            WorkstreamTask,
            TaskAssignment,
            Submission,
            CheckerRun,
            ContributionRecord,
        )

        async def counts():
            async with h.factory() as session:
                return {
                    model.__tablename__: await session.scalar(
                        select(func.count()).select_from(model)
                    )
                    for model in models
                }

        before = await counts()
        requests = []
        app = client._transport.app
        assert not app.dependency_overrides, (
            "public proof cannot replace AUTH/TASK owners"
        )

        async def observed(scope, receive, send):
            if scope["type"] == "http":
                requests.append((scope["method"], scope["path"], scope["query_string"]))
            await app(scope, receive, send)

        async with socket_api(observed) as origin:
            with Terminal(origin, owner.token, "--plain") as terminal:

                async def wait(text):
                    return await asyncio.to_thread(terminal.wait, text)

                await wait(direct["projects"]["items"][0]["name"])
                terminal.send("\r")
                await wait(direct["ready"]["items"][0]["title"])
                terminal.send("\r")
                await wait(str(ready_id))
                await wait(direct["ready_task"]["description"])
                terminal.send("\x1b")
                await wait("[Ready]")
                terminal.send("\t")
                await wait("[Mine]")
                await wait(direct["mine"]["items"][0]["title"])
                terminal.send("\r")
                await wait(task)
                await wait(direct["task"]["description"])
                terminal.send("\t")
                await wait("[Context]")
                await wait(direct["context"]["guide"]["version"])
                terminal.send("\t")
                await wait("[Intake]")
                terminal.send("\x1b")
                await wait("[Mine]")
                terminal.send("\t")
                await wait("[Submissions]")
                await wait(direct["attempts"]["items"][0]["title"])
                terminal.send("\r")
                await wait(submission_id)
                await wait(direct["submission"]["summary"])
                async with h.factory() as session:
                    grant_id = await session.scalar(
                        select(ProjectRoleGrant.id).where(
                            ProjectRoleGrant.actor_profile_id == str(owner.id),
                            ProjectRoleGrant.project_id == project,
                            ProjectRoleGrant.role == "submitter",
                            ProjectRoleGrant.status == "active",
                        )
                    )
                assert grant_id is not None
                revoked = await client.post(
                    f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke",
                    headers=manager.headers | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Prove TUI observes fresh grant revocation"},
                )
                assert revoked.status_code == 200, revoked.text
                denied = await client.get(paths["submission"], headers=owner.headers)
                assert denied.status_code == 404
                terminal.send("r")
                await wait("Denied")
                assert direct["submission"]["summary"] not in terminal.screen
                assert submission_id not in terminal.screen
                await asyncio.to_thread(terminal.quit)
                assert owner.token.encode() not in terminal.raw
        allowed = {path.split("?", 1)[0] for path in paths.values()} | {
            "/api/v1/actors/me"
        }
        assert requests and all(
            method == "GET" and path in allowed for method, path, _ in requests
        )
        assert ("GET", paths["submission"], b"") in requests
        assert await counts() == before, "read-only TUI mutated product records"


@pytest.mark.asyncio
async def test_tui_real_signed_claim_replay_start_replay_then_fresh_revocation(
    tmp_path, auth_database_env, admin_access
):
    signed = admin_access.signed
    async with _prepared_packet(auth_database_env, tmp_path) as h:
        subject = f"human-{h.context.actor_profile_id}"
        owner = SignedActor(
            h.context.actor_profile_id,
            subject,
            issue_asymmetric_token(
                signed.private_key,
                claims={"sub": subject, "jti": str(uuid4()), "roles": []},
            ),
        )
        client = signed.client
        profile = await client.get("/api/v1/actors/me", headers=owner.headers)
        assert profile.status_code == 200, profile.text
        assert profile.json()["actor_profile_id"] == str(owner.id)
        access = SimpleNamespace(signed=signed)
        ready_id = await create_task(access, h.project_id, owner)
        project, task = str(h.project_id), str(ready_id)
        detail_path = f"/api/v1/tasks/{task}"
        ready = await client.get(detail_path, headers=owner.headers)
        assert ready.status_code == 200, ready.text
        assert ready.json()["status"] == "ready"
        projects = await client.get(
            "/api/v1/actors/me/projects?limit=50", headers=owner.headers
        )
        assert projects.status_code == 200, projects.text
        project_name = projects.json()["items"][0]["name"]
        manager = await project_manager(admin_access, h.project_id)
        claim_key, start_key = str(uuid4()), str(uuid4())
        writes = []
        app = client._transport.app
        assert not app.dependency_overrides, (
            "public proof cannot replace AUTH/TASK owners"
        )

        async def observed(scope, receive, send):
            if scope["type"] == "http" and scope["method"] == "POST":
                writes.append(
                    (
                        scope["path"],
                        dict(scope["headers"]).get(b"idempotency-key", b"").decode(),
                    )
                )
            await app(scope, receive, send)

        async with socket_api(observed) as origin:
            with Terminal(origin, owner.token, "--plain") as terminal:

                async def wait(text):
                    return await asyncio.to_thread(terminal.wait, text)

                async def confirm(action, key):
                    terminal.send("a")
                    await wait("Caller-owned replay key")
                    terminal.send(key)
                    terminal.send("\r")
                    await wait("Confirm " + action)
                    assert task in terminal.screen and key in terminal.screen
                    assert (
                        project in terminal.screen and str(owner.id) in terminal.screen
                    )
                    terminal.send("s")
                    terminal.send("y")
                    await wait(action.capitalize() + " confirmed")

                async def replay(action):
                    terminal.send("p")
                    await wait("Confirm " + action)
                    terminal.send("s")
                    terminal.send("y")
                    await wait(action.capitalize() + " confirmed")

                await wait(project_name)
                terminal.send("\r")
                await wait("Evaluate proof")
                terminal.send("\r")
                await wait(task)
                await confirm("claim", claim_key)
                await replay("claim")
                # Claim does not implicitly start. A fresh Mine read and exact
                # task detail are required before opening the second action.
                terminal.send("\x1b")
                await wait(ready.json()["description"])
                terminal.send("2")
                await wait("Evaluate proof")
                terminal.send("/Evaluate proof\r")
                await wait("local filter: Evaluate proof")
                terminal.send("\r")
                await wait(task)
                await confirm("start", start_key)
                await replay("start")
                current = await client.get(detail_path, headers=owner.headers)
                assert current.status_code == 200, current.text
                assert current.json()["status"] == "in_progress"
                async with h.factory() as session:
                    assignments = (
                        await session.scalars(
                            select(TaskAssignment).where(TaskAssignment.task_id == task)
                        )
                    ).all()
                    assert len(assignments) == 1
                    assert assignments[0].contributor_id == str(owner.id)
                    grant_id = await session.scalar(
                        select(ProjectRoleGrant.id).where(
                            ProjectRoleGrant.actor_profile_id == str(owner.id),
                            ProjectRoleGrant.project_id == project,
                            ProjectRoleGrant.role == "submitter",
                            ProjectRoleGrant.status == "active",
                        )
                    )
                assert grant_id is not None
                revoked = await client.post(
                    f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke",
                    headers=manager.headers | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Prove fresh authority after native TUI replay"},
                )
                assert revoked.status_code == 200, revoked.text
                terminal.send("p")
                await wait("Confirm start")
                terminal.send("s")
                terminal.send("y")
                await wait("Request denied")
                assert "Start confirmed" in terminal.screen
                assert ready.json()["description"] not in terminal.screen
                await asyncio.to_thread(terminal.quit)
                assert owner.token.encode() not in terminal.raw

        assert writes == [
            (detail_path + "/claim", claim_key),
            (detail_path + "/claim", claim_key),
            (detail_path + "/start", start_key),
            (detail_path + "/start", start_key),
            (detail_path + "/start", start_key),
        ]
        for denied_key in (start_key, str(uuid4())):
            denied = await client.post(
                detail_path + "/start",
                headers=owner.headers | {"Idempotency-Key": denied_key},
                json={},
            )
            assert denied.status_code == 403, denied.text
        assert (await client.get(detail_path, headers=owner.headers)).status_code == 404
