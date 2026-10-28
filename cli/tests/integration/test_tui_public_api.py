"""Built native PTY/ConPTY -> real socket/Flow verifier -> isolated PostgreSQL.

Canonical fixtures arrange an approved guide, started work and a retained
immutable attempt. The original test remains GET-only; separate tests prove
claim/start and initial public intake through the native UI. Intake uses the
fixture's local ART provider and explicit in-process guest rules, not S3 or
sandbox-execution proof. No DB/AUTH/TASK owner is replaced; the signed fixture
issuer's JWKS transport is local.
"""

import asyncio
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from httpx import ASGITransport, AsyncClient
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
from app.adapters.auth.flow import FlowAuthVerifier
from app.core.identifiers import new_record_id
from app.main import create_app
from app.modules.artifacts.models import ArtifactPutAttempt, SubmissionBundleAdmission
from app.modules.authorization.models import ProjectRoleGrant
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.contributions.records.models import ContributionRecord
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from tests.authentication.fixtures import (
    auth_database_env as _auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authentication.support import (
    issue_asymmetric_token,
    jwks_transport,
    production_verifier_settings,
)
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
from tests.tasks.submission_lineage_support import _verify_put_attempt
from tests.trusted_intake_fixtures import LocalIntakeAdapter

signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)
admin_access = pytest_asyncio.fixture(_admin_access.__wrapped__)
auth_database_env = _auth_database_env


@pytest.mark.asyncio
async def test_tui_signed_initial_intake_pending_verification_replay_and_revocation(
    tmp_path, auth_database_env, admin_access, rsa_signing_material
):
    """Native UI and real owners; local ART and in-process guest rules, not S3."""
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
        manager = await project_manager(admin_access, h.project_id)
        # Keep this fixture's exact ART namespace, store and scratch configuration.
        # Only replace authentication settings with the production Flow verifier
        # settings; do not inherit admin_access's disabled artifact backend.
        flow = production_verifier_settings(database_url=auth_database_env)
        settings = h.settings.model_copy(
            update={
                name: getattr(flow, name)
                for name in type(flow).model_fields
                if name.startswith(("auth_", "token_"))
            }
            | {"database_url": auth_database_env}
        )
        app = create_app(settings)
        jwks_requests = []
        app.state.auth_verifier = FlowAuthVerifier(
            settings,
            jwks_transport=jwks_transport(rsa_signing_material[1], jwks_requests),
        )
        assert app.state.auth_configuration_valid
        assert not app.dependency_overrides, "DB/AUTH/TASK owners must remain real"
        assert settings.auth_provider == "flow"
        assert settings.artifact_local_root == h.settings.artifact_local_root
        assert settings.artifact_scratch_root == h.settings.artifact_scratch_root

        project, task = str(h.project_id), str(h.task_id)
        route = f"/api/v1/tasks/{task}/submission-bundle-preparations"
        corrected = tmp_path / "corrected.zip"
        corrected.write_bytes(h.archive_bytes)
        blocked_zip = tmp_path / "blocked.zip"
        archive = BytesIO(h.archive_bytes)
        with ZipFile(archive, "a") as contents:
            # Canonical default-checker fixture, not a real private key. Missing
            # summary/evidence alone must not be invented as a blocking default
            # check: absent summary is a warning on this locked policy branch.
            contents.writestr(
                "synthetic-private-key.txt",
                b"-----BEGIN OPENSSH PRIVATE KEY-----\nencoded",
            )
        blocked_zip.write_bytes(archive.getvalue())
        failed_key, corrected_key = str(uuid4()), str(uuid4())
        models = (
            SelectedPreSubmitRun,
            ArtifactPutAttempt,
            SubmissionBundleAdmission,
            Submission,
            ContributionRecord,
        )

        async def counts():
            async with h.factory() as session:
                result = {
                    model.__tablename__: await session.scalar(
                        select(func.count()).select_from(model)
                    )
                    for model in models
                }
                assert result[Submission.__tablename__] == 0
                assert result[ContributionRecord.__tablename__] == 0
                return result

        # _prepared_packet already created one PRE run and verified ART packet.
        # Test deltas, not a fictitious empty preparation database.
        baseline = await counts()
        requests = []
        posts = []

        async def observed(scope, receive, send):
            if scope["type"] != "http":
                return await app(scope, receive, send)
            requests.append((scope["method"], scope["path"]))
            if scope["method"] != "POST":
                return await app(scope, receive, send)
            record = {
                "path": scope["path"],
                "headers": dict(scope["headers"]),
                "body": bytearray(),
                "response_body": bytearray(),
            }
            posts.append(record)

            async def observed_receive():
                message = await receive()
                if message["type"] == "http.request":
                    record["body"].extend(message.get("body", b""))
                    assert len(record["body"]) <= 1024 * 1024
                return message

            async def observed_send(message):
                if message["type"] == "http.response.start":
                    record["status"] = message["status"]
                elif message["type"] == "http.response.body":
                    record["response_body"].extend(message.get("body", b""))
                    assert len(record["response_body"]) <= 1024 * 1024
                    if not message.get("more_body", False):
                        record["response"] = json.loads(record["response_body"])
                await send(message)

            await app(scope, observed_receive, observed_send)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            project_response = await client.get(
                "/api/v1/actors/me/projects", headers=owner.headers
            )
            assert project_response.status_code == 200, project_response.text
            [project_row] = project_response.json()["items"]
            task_response = await client.get(
                f"/api/v1/tasks/{task}", headers=owner.headers
            )
            assert task_response.status_code == 200, task_response.text
            task_body = task_response.json()
            assert task_body["status"] == "in_progress"

            # This explicitly named fixture executes guest rules in-process.
            # The production signed verifier, public route, PRE and ART owners,
            # PostgreSQL and local provider remain real, with no dependency swap.
            with patch(
                "app.adapters.artifacts.trusted_submission_intake",
                return_value=LocalIntakeAdapter(),
            ):
                async with socket_api(observed) as origin:
                    with Terminal(
                        origin, owner.token, "--plain", columns=180, rows=60
                    ) as terminal:

                        async def wait(text):
                            return await asyncio.to_thread(terminal.wait, text, 60)

                        async def confirm(path, key, summary):
                            terminal.send("a")
                            for label, value in (
                                ("One readable, nonempty regular ZIP", str(path)),
                                ("Summary", summary),
                                (
                                    "Attestation",
                                    h.preparation_request.contributor_attestation,
                                ),
                                ("Caller-owned replay key", key),
                            ):
                                await wait(label)
                                if value:
                                    terminal.send(value)
                                terminal.send("\r")
                            await wait("Confirm prepare")
                            for identity in (
                                str(owner.id),
                                project,
                                task,
                                str(h.assignment_id),
                                key,
                            ):
                                assert identity in terminal.screen
                            terminal.send("s")
                            terminal.send("y")

                        async def replay():
                            terminal.send("p")
                            await wait("Confirm prepare")
                            terminal.send("s")
                            terminal.send("y")

                        await wait(project_row["name"])
                        terminal.send("\r")
                        await wait("[Ready]")
                        terminal.send("2")
                        await wait(task_body["title"])
                        terminal.send("\r")
                        await wait(task_body["description"])
                        await confirm(blocked_zip, failed_key, "")
                        await wait("pre_submission_checker_failed")
                        await wait("No immutable Submission")
                        assert len(posts) == 1
                        failed = posts[0]
                        assert failed["status"] == 422
                        failure = failed["response"]["error"]
                        assert failure["code"] == "pre_submission_checker_failed"
                        details = failure["details"]
                        assert details["eligible_to_submit"] is False
                        assert details["results"]
                        [blocking] = [
                            result
                            for result in details["results"]
                            if result["status"] == "failed"
                        ]
                        assert blocking == {
                            "source": "workstream_default",
                            "check_id": "high_confidence_secrets_absent",
                            "status": "failed",
                            "failure_code": "high_confidence_secret_detected",
                            "finding_count": 1,
                        }
                        await wait("high_confidence_secret_detected")
                        assert "synthetic-private-key.txt" not in terminal.screen
                        assert "BEGIN OPENSSH PRIVATE KEY" not in terminal.screen
                        failed_counts = await counts()
                        assert failed_counts == baseline | {
                            SelectedPreSubmitRun.__tablename__: baseline[
                                SelectedPreSubmitRun.__tablename__
                            ]
                            + 1
                        }
                        # A known failed intake can return to Overview and open
                        # a new, deliberately confirmed corrected packet/key.
                        terminal.send("\x1b")
                        await wait(task_body["description"])
                        await confirm(
                            corrected, corrected_key, h.preparation_request.summary
                        )
                        await wait("stored_pending_verification")
                        assert len(posts) == 2
                        pending = posts[1]["response"]
                        assert posts[1]["status"] == 202
                        assert pending["submission_bundle_preparation_status"] == (
                            "stored_pending_verification"
                        )
                        assert pending["admission_id"] is None
                        pending_counts = await counts()
                        assert pending_counts == failed_counts | {
                            SelectedPreSubmitRun.__tablename__: failed_counts[
                                SelectedPreSubmitRun.__tablename__
                            ]
                            + 1,
                            ArtifactPutAttempt.__tablename__: failed_counts[
                                ArtifactPutAttempt.__tablename__
                            ]
                            + 1,
                        }
                        # Consume POST's put_attempt_id, never a GET preparation ID.
                        admission = await _verify_put_attempt(
                            h.factory,
                            h.store,
                            h.namespace,
                            h.settings,
                            pending["put_attempt_id"],
                        )
                        await replay()
                        await wait(str(admission))
                        await wait("ready")
                        assert len(posts) == 3
                        assert posts[2]["response"] == pending | {
                            "submission_bundle_preparation_status": "ready",
                            "admission_id": str(admission),
                            "replayed": True,
                        }
                        ready_counts = await counts()
                        assert ready_counts == pending_counts | {
                            SubmissionBundleAdmission.__tablename__: pending_counts[
                                SubmissionBundleAdmission.__tablename__
                            ]
                            + 1
                        }
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
                        revoked = await signed.client.post(
                            f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke",
                            headers=manager.headers | {"Idempotency-Key": str(uuid4())},
                            json={"reason": "Prove fresh preparation replay denial"},
                        )
                        assert revoked.status_code == 200, revoked.text
                        await replay()
                        await wait("Protected preparation text cleared")
                        assert len(posts) == 4 and posts[3]["status"] == 404
                        for protected in (
                            task_body["description"],
                            str(corrected),
                            h.preparation_request.summary,
                            h.preparation_request.contributor_attestation,
                            pending["put_attempt_id"],
                            str(admission),
                        ):
                            assert protected not in terminal.screen
                        terminal.send("psy")
                        await asyncio.to_thread(terminal.pump, 0.3)
                        assert len(posts) == 4, "denial did not disable replay"
                        await asyncio.to_thread(terminal.quit)
                        assert owner.token.encode() not in terminal.raw
                        assert await counts() == ready_counts

        assert jwks_requests, "signed proof never used the real Flow JWKS verifier"
        assert all(
            method == "GET" or (method == "POST" and path == route)
            for method, path in requests
        )
        assert [post["path"] for post in posts] == [route] * 4
        assert bytes(posts[0]["body"]) == blocked_zip.read_bytes()
        assert posts[0]["headers"][b"idempotency-key"] == failed_key.encode()
        assert b"x-submission-summary" not in posts[0]["headers"]
        # This observer records what the real owner consumed. A denied request
        # may correctly stop before reading bytes; pending/ready exact replay
        # must both consume the original archive.
        assert [bytes(post["body"]) for post in posts[1:3]] == [h.archive_bytes] * 2
        for post in posts[1:]:
            assert post["headers"][b"idempotency-key"] == corrected_key.encode()
            assert post["headers"][b"x-task-assignment-id"] == (
                str(h.assignment_id).encode()
            )
            assert post["headers"][b"x-submission-summary"] == (
                h.preparation_request.summary.encode()
            )
            assert post["headers"][b"x-contributor-attestation"] == (
                h.preparation_request.contributor_attestation.encode()
            )
            assert post["headers"][b"content-type"] == b"application/zip"
        assert await counts() == ready_counts


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
