"""Real public contributor discovery and writes over approved prerequisites.

Only upstream guide inference/storage are scripted fixtures. Task, assignment,
grant and lifecycle operations exercise the real API with no route overrides.
"""

from contextlib import AsyncExitStack
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from api_contract_e2e import flow_settings, issue_flow_token
from tests.projects.guide_activation.pg_support import activation_case
from tests.authorization.guide_activation.pg_support import activate
from manager_task_journey import exercise_manager_task_preparation
from project_role_journey import exercise_project_role_decisions
from operator_task_journey import exercise_operator_task_journey


async def exercise_contributor_task_reads(
    direct, cli, origin, tokens, profiles, env, qualification
):
    manager = {"Authorization": f"Bearer {tokens['cli-manager']}"}
    admin = {"Authorization": f"Bearer {tokens['cli-admin']}"}
    token = tokens["cli-outsider"]
    issuer, audience, secret = flow_settings(env)
    specification = await direct.get("/openapi.json", timeout=60)
    assert specification.status_code == 200
    for suffix in ("work-context", "submission-requirements"):
        assert (
            "get"
            in specification.json()["paths"][f"/api/v1/tasks/{{task_id}}/{suffix}"]
        )

    async def post(path, body, headers=manager):
        response = await direct.post(
            path, headers=headers | {"Idempotency-Key": str(uuid4())}, json=body
        )
        assert response.status_code in (200, 201), response.text
        return response.json()

    def read(command, presented=token, status=None):
        result = cli(origin, presented, "task", *command, "-o", "json")
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            assert json.loads(result.stderr)["error"]["status"] == status
            return None
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    async def context_reads(task_id, presented=token, denied=False):
        values = {}
        for command, suffix in (
            ("context", "work-context"),
            ("requirements", "submission-requirements"),
        ):
            expected = await direct.get(
                f"/api/v1/tasks/{task_id}/{suffix}",
                headers={"Authorization": f"Bearer {presented}"},
            )
            if denied:
                # Each real route owns concealment; do not assume the same
                # status for work-context's command and requirements' read port.
                assert expected.status_code in (403, 404), expected.text
                read((command, task_id), presented, status=expected.status_code)
                continue
            assert expected.status_code == 200, expected.text
            value = read((command, task_id.replace("-", "")), presented)
            assert value == expected.json()
            values[command] = value
        if not denied:
            context, requirements = values["context"], values["requirements"]
            assert context["task"]["task_id"] == requirements["task_id"] == task_id
            assert (
                context["task"]["project_id"]
                == context["project"]["id"]
                == context["guide"]["project_id"]
                == requirements["project_id"]
                == project
            )
            assert context["guide"]["version"] == requirements["guide_version"]
        return values

    async def mutate(action, task_id, key, reason=None, presented=token, status=None):
        # Read the current public management projection AFTER administrator
        # changes; async invalidation is not simulated in this fixture.
        path = f"/api/v1/projects/{project}/tasks/{task_id}"
        before = await direct.get(path, headers=manager)
        assert before.status_code == 200, before.text
        flags = () if reason is None else ("--reason", reason)
        result = cli(
            origin,
            presented,
            "task",
            action,
            task_id.replace("-", ""),
            "--idempotency-key",
            str(key),
            *flags,
            "-o",
            "json",
        )
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            error = json.loads(result.stderr)["error"]
            assert error["status"] == status and "outcome_unknown" not in error
            after = await direct.get(path, headers=manager)
            assert after.status_code == 200 and after.json() == before.json()
            return error
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    async def grant(project, actor, role="submitter"):
        return await post(
            f"/api/v1/projects/{project}/role-grants",
            {
                "target_actor_profile_id": actor,
                "role": role,
                "qualification": qualification,
                "reason": "CLI contributor read proof",
            },
        )

    peer_profiles = {}
    peer_tokens = {}
    for name in ("cli-task-peer", "cli-task-reviewer", "cli-role-admin"):
        peer_tokens[name] = issue_flow_token(
            name, [], issuer=issuer, audience=audience, secret=secret
        )
        admitted = await direct.get(
            "/api/v1/actors/me",
            headers={"Authorization": f"Bearer {peer_tokens[name]}"},
        )
        assert admitted.status_code == 200, admitted.text
        peer_profiles[name] = admitted.json()["actor_profile_id"]

    async with AsyncExitStack() as stack:
        projects = []
        for _ in range(2):
            factory, command, actor, *_rest = await stack.enter_async_context(
                activation_case(env["WORKSTREAM_DATABASE_URL"])
            )
            await activate(factory, actor, command)
            projects.append(str(command.target.proposal.project_id))
            if len(projects) == 1:
                preparation_factory = factory
        project, foreign_project = projects
        ready_ids = []
        for selected_project, count in ((project, 3), (foreign_project, 1)):
            for index in range(count):
                if selected_project == project and index == 0:
                    with tempfile.TemporaryDirectory(
                        prefix="ws-cli-manager-input-"
                    ) as directory:
                        task_id = await exercise_manager_task_preparation(
                            direct,
                            cli,
                            origin,
                            tokens,
                            profiles,
                            preparation_factory,
                            project,
                            foreign_project,
                            Path(directory) / "task.json",
                        )
                    ready_ids.append(task_id)
                    continue
                created = await post(
                    f"/api/v1/projects/{selected_project}/tasks",
                    {
                        "title": f"Contributor work {index}",
                        "description": "Inspect the supplied evidence.",
                        "task_type": "evaluation",
                        "difficulty": "medium",
                        "skill_tags": ["analysis"],
                        "estimated_time_minutes": 17,
                        "acceptance_criteria": "Evidence is complete.",
                        "rejection_criteria": "Evidence is missing.",
                        "source_ref": "manager-private-source",
                    },
                )
                task_id = created["id"]
                for operation in ("screen", "release"):
                    transitioned = await post(
                        f"/api/v1/tasks/{task_id}/{operation}",
                        {"reason": "Prepare contributor discovery"},
                    )
                assert transitioned["status"] == "ready"
                if selected_project == project:
                    ready_ids.append(task_id)
                else:
                    foreign_task_id = task_id
        draft = await post(
            f"/api/v1/projects/{project}/tasks",
            {"title": "Not released", "description": "Draft control"},
        )
        actor_id = profiles["cli-outsider"]["actor_profile_id"]

        # Ready persisted work does not permit writes without Submitter authority.
        for action in ("claim",):
            await mutate(action, ready_ids[0], uuid4(), status=403)

        # Stored ready resources exist, but no matching grant permits either read.
        read(("ready", project), status=404)
        read(("show", ready_ids[0]), status=404)
        await context_reads(ready_ids[0], denied=True)
        revoke_first_grant = await exercise_project_role_decisions(
            direct,
            cli,
            origin,
            tokens,
            profiles,
            preparation_factory,
            project,
            foreign_project,
            qualification,
            peer_profiles["cli-task-reviewer"],
            peer_profiles["cli-role-admin"],
            peer_tokens["cli-role-admin"],
        )
        # Keep independent contributor lifecycle/cursor setup on the same real
        # control administrator, not the outer self-service bootstrap actor.
        # All contributor/manager CLI calls retain their original bearers.
        admin = {"Authorization": f"Bearer {peer_tokens['cli-role-admin']}"}
        # An active Submitter grant never substitutes for manager authority.
        with tempfile.TemporaryDirectory(prefix="ws-cli-submit-only-") as directory:
            task_input = Path(directory) / "task.json"
            task_input.write_text(
                json.dumps({"title": "Denied", "description": "Must not be created"})
            )
            for action in ("create", "screen", "release"):
                args = (
                    (project, "--input", str(task_input))
                    if action == "create"
                    else (project, ready_ids[0], "--reason", "Must not transition")
                )
                denied = cli(
                    origin,
                    token,
                    "project",
                    "task",
                    action,
                    *args,
                    "--idempotency-key",
                    str(uuid4()),
                    "-o",
                    "json",
                )
                assert denied.returncode == 1 and denied.stdout == ""
                assert json.loads(denied.stderr)["error"]["status"] == 403
        await grant(project, peer_profiles["cli-task-peer"])
        reviewer_ready = read(("ready", project), peer_tokens["cli-task-reviewer"])
        reviewer_detail = read(("show", ready_ids[0]), peer_tokens["cli-task-reviewer"])
        assert (
            reviewer_ready["items"][0]["compensation"]
            == reviewer_detail["compensation"]
        )
        await context_reads(ready_ids[0], peer_tokens["cli-task-reviewer"], denied=True)
        for action in ("claim",):
            await mutate(
                action,
                ready_ids[0],
                uuid4(),
                presented=peer_tokens["cli-task-reviewer"],
                status=403,
            )

        cursor = None
        observed = []
        first_cursor = None
        for index in range(3):
            flags = () if cursor is None else ("--cursor", cursor)
            page = read(("ready", project.replace("-", ""), "--limit", "1", *flags))
            params = {"limit": "1"} | ({} if cursor is None else {"cursor": cursor})
            expected = await direct.get(
                f"/api/v1/projects/{project}/tasks/ready",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            assert expected.status_code == 200 and page == expected.json()
            assert len(page["items"]) == 1
            assert set(page["items"][0]) == {
                "task_id",
                "project_id",
                "title",
                "task_type",
                "difficulty",
                "skill_tags",
                "estimated_time_minutes",
                "created_at",
                "compensation",
            }
            observed.append(page["items"][0]["task_id"])
            cursor = page["next_cursor"]
            if index == 0:
                first_cursor = cursor
                assert first_cursor is not None
        assert observed == ready_ids and cursor is None and draft["id"] not in observed

        async def detail(task_id, presented=token):
            value = read(("show", task_id.replace("-", "")), presented)
            expected = await direct.get(
                f"/api/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {presented}"},
            )
            assert expected.status_code == 200 and value == expected.json()
            assert value["task_id"] == task_id and value["project_id"] == project
            assert (
                "source_ref" not in value
                and "assigned_to" not in value
                and "created_by" not in value
            )
            return value

        await detail(ready_ids[0])
        await detail(ready_ids[0], peer_tokens["cli-task-peer"])
        ready_context = await context_reads(ready_ids[0])
        assert ready_context["context"]["lifecycle"] == {
            "assigned_to_current_actor": False,
            "next_actions": ["claim"],
        }
        await context_reads(ready_ids[0], peer_tokens["cli-task-peer"])
        await context_reads(draft["id"], denied=True)
        await context_reads(foreign_task_id, denied=True)
        read(("show", draft["id"]), status=404)
        read(("ready", foreign_project), status=404)
        read(("show", foreign_task_id), status=404)
        # The same caller has Submitter A, but not B. Use B's management baseline.
        for action in ("claim",):
            before = await direct.get(
                f"/api/v1/projects/{foreign_project}/tasks/{foreign_task_id}",
                headers=manager,
            )
            denied = cli(
                origin,
                token,
                "task",
                action,
                foreign_task_id,
                "--idempotency-key",
                str(uuid4()),
                "-o",
                "json",
            )
            assert denied.returncode == 1 and denied.stdout == ""
            assert json.loads(denied.stderr)["error"]["status"] == 403
            after = await direct.get(
                f"/api/v1/projects/{foreign_project}/tasks/{foreign_task_id}",
                headers=manager,
            )
            assert (
                before.status_code == after.status_code == 200
                and before.json() == after.json()
            )
        # Each cursor substitution retains authority before testing the codec.
        await grant(foreign_project, actor_id)
        read(("ready", foreign_project))
        read(("show", foreign_task_id))
        read(
            ("ready", foreign_project, "--limit", "1", "--cursor", first_cursor),
            status=422,
        )
        read(("ready", project, "--limit", "2", "--cursor", first_cursor), status=422)
        await post(
            "/api/v1/admin-role-grants",
            {
                "target_actor_profile_id": actor_id,
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": project,
                "reason": "Independent authorized cursor action control",
            },
            admin,
        )
        management_control = cli(
            origin, token, "project", "tasks", project, "--limit", "1", "-o", "json"
        )
        assert management_control.returncode == 0 and management_control.stderr == ""
        assert (
            json.loads(management_control.stdout)["items"][0]["task_id"] == ready_ids[0]
        )
        management = cli(
            origin,
            token,
            "project",
            "tasks",
            project,
            "--limit",
            "1",
            "--cursor",
            first_cursor,
            "-o",
            "json",
        )
        assert management.returncode == 1 and management.stdout == ""
        assert json.loads(management.stderr)["error"]["status"] == 422

        claim_key = uuid4()
        reason = "Assignment visibility control"
        claimed = await mutate("claim", ready_ids[0], claim_key, reason)
        assert claimed["assignment"]["contributor_id"] == actor_id
        assert claimed["assignment"]["task_id"] == claimed["task"]["id"] == ready_ids[0]
        assert (
            claimed["assignment"]["project_id"]
            == claimed["task"]["project_id"]
            == project
        )
        assert (
            claimed["assignment"]["submitter_contribution_policy_version_id"]
            == claimed["task"]["locked_contribution_policy_version_id"]
        )
        assert await mutate("claim", ready_ids[0], claim_key, reason) == claimed
        mismatch = await mutate("claim", ready_ids[0], claim_key, "Changed", status=409)
        assert mismatch["code"] == "idempotency_mismatch"
        mismatch = await mutate("claim", ready_ids[1], claim_key, reason, status=409)
        assert mismatch["code"] == "idempotency_mismatch"
        assert (await detail(ready_ids[0]))["status"] == "in_progress"
        claimed_context = await context_reads(ready_ids[0])
        assert claimed_context["context"]["lifecycle"] == {
            "assigned_to_current_actor": True,
            "next_actions": [],
        }
        assert claimed_context["requirements"] == ready_context["requirements"]
        assert (
            claimed_context["context"]["guide"]["version"]
            == claimed["task"]["locked_guide_version"]
        )
        assert (
            claimed_context["context"]["contribution_policy_version_id"]
            == claimed["task"]["locked_contribution_policy_version_id"]
        )
        for kind in ("review", "revision"):
            assert claimed_context["context"][f"{kind}_policy"] == {
                "policy_id": claimed["task"][f"locked_{kind}_policy_id"],
                "generation": claimed["task"][f"locked_{kind}_policy_generation"],
                "policy_hash": claimed["task"][f"locked_{kind}_policy_hash"],
            }
        # Same-project authority was demonstrated before and after this ownership change.
        read(("show", ready_ids[0]), peer_tokens["cli-task-peer"], status=404)
        await detail(ready_ids[1], peer_tokens["cli-task-peer"])
        await context_reads(ready_ids[0], peer_tokens["cli-task-peer"], denied=True)
        await context_reads(ready_ids[1], peer_tokens["cli-task-peer"])
        for presented in (token, peer_tokens["cli-task-peer"]):
            page = read(("ready", project), presented)
            assert {item["task_id"] for item in page["items"]} == set(ready_ids[1:])

        await mutate(
            "claim",
            ready_ids[0],
            uuid4(),
            presented=peer_tokens["cli-task-peer"],
            status=403,
        )
        # Claim already starts work; a different key cannot create another assignment.
        await mutate("claim", ready_ids[0], uuid4(), reason, status=403)
        assert await mutate("claim", ready_ids[0], claim_key, reason) == claimed

        await revoke_first_grant()
        read(("ready", project, "--limit", "1", "--cursor", first_cursor), status=404)
        read(("show", ready_ids[1]), status=404)
        await context_reads(ready_ids[1], denied=True)
        await mutate("claim", ready_ids[0], claim_key, reason, status=403)
        await mutate("claim", ready_ids[1], uuid4(), status=403)
        # Manager authority cannot substitute for a revoked Submitter grant.
        await grant(project, actor_id)
        read(("ready", project, "--limit", "1", "--cursor", first_cursor))
        await detail(ready_ids[1])
        await context_reads(ready_ids[1])
        # Establish fresh successful write authority before lifecycle denial.
        second_key = uuid4()
        second_claim = await mutate("claim", ready_ids[1], second_key)
        assert second_claim["assignment"]["contributor_id"] == actor_id
        await exercise_operator_task_journey(
            direct,
            cli,
            origin,
            tokens,
            env,
            project,
            foreign_project,
            ready_ids[1],
            actor_id,
        )
        # The same freshly authorized actor is suspended: stale revocation cannot
        # masquerade as lifecycle denial. Restore it for the outer journey.
        await post(
            f"/api/v1/actors/{actor_id}/suspend",
            {"reason": "CLI live contributor lifecycle control"},
            admin,
        )
        read(("ready", project), status=404)
        read(("show", ready_ids[1]), status=404)
        await context_reads(ready_ids[1], denied=True)
        await mutate("claim", ready_ids[1], second_key, status=403)
        await post(
            f"/api/v1/actors/{actor_id}/reactivate",
            {"reason": "Continue independent CLI proof"},
            admin,
        )
        read(("ready", project))
        await detail(ready_ids[1])
        await context_reads(ready_ids[1])
