"""First journey stage: public identity, real bootstrap, public grants and project.

Run inside run_isolated_tests.py. This stage is not full journey certification.
"""

from __future__ import annotations

import base64
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from uuid import uuid4

from client import JourneyClient
from public_setup import configure_guide, publish_unpaid_terms, approve_and_activate
from runtime import durable_runtime
from task_work import claim_and_read
from submission_work import submit_and_observe
from artifact_work import inspect_submission_custody

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
from local_flow_tokens import issue_flow_token  # noqa: E402
from run_isolated_tests import NAME_RE  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402


def main():
    import app

    if Path(app.__file__).resolve().parent != BACKEND / "app":
        raise RuntimeError("journey imported a different worktree's backend")
    database_url = os.environ["WORKSTREAM_DATABASE_URL"]
    if not NAME_RE.fullmatch(urlsplit(database_url).path.lstrip("/")):
        raise RuntimeError("requires runner-owned isolated database")
    executable = Path(os.environ["WORKSTREAM_CLI_EXECUTABLE"])
    secret = secrets.token_hex(32)
    issuer, audience = "https://identity.flowresearch.tech", "cli-journey-local"
    environment = dict(os.environ)
    environment.update(
        PYTHONPATH=str(BACKEND),
        WORKSTREAM_ENVIRONMENT="local",
        WORKSTREAM_AUTH_PROVIDER="flow",
        WORKSTREAM_FLOW_AUTH_ISSUER=issuer,
        WORKSTREAM_FLOW_AUTH_AUDIENCE=audience,
        WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET=secret,
        WORKSTREAM_PROJECT_AGENT_RUNTIME="manager_authored",
        WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER="none",
        WORKSTREAM_PROJECT_AGENT_MODEL_API="none",
        WORKSTREAM_PROJECT_AGENT_MODEL="none",
        WORKSTREAM_CELERY_TASK_ALWAYS_EAGER="false",
        WORKSTREAM_API_RATE_LIMIT_KEY_SECRET=base64.b64encode(
            secrets.token_bytes(32)
        ).decode(),
        WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET=base64.b64encode(
            secrets.token_bytes(32)
        ).decode(),
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    with (
        tempfile.TemporaryDirectory(prefix="workstream-cli-bootstrap-") as temporary,
        ExitStack() as stack,
    ):
        directory = Path(temporary)
        through_setup = os.environ.get("WORKSTREAM_CLI_JOURNEY_SETUP") == "1"
        if through_setup:
            start_workers = stack.enter_context(
                durable_runtime(ROOT, directory, environment)
            )
        with (directory / "api.log").open("wb") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                    "--log-level",
                    "error",
                ],
                cwd=BACKEND,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(
                            "API exited before readiness; no journey pass"
                        )
                    try:
                        with urlopen(origin + "/api/v1/health", timeout=2) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.25)
                else:
                    raise RuntimeError(
                        "API readiness deadline exceeded; no journey pass"
                    )
                client = JourneyClient(executable, origin, directory)
                tokens = {
                    name: issue_flow_token(
                        f"cli-journey-{name}",
                        [],
                        issuer=issuer,
                        audience=audience,
                        secret=secret,
                    )
                    for name in (
                        "administrator",
                        "manager",
                        "finance",
                        "operator",
                        "alice",
                        "bob",
                    )
                }
                actors = {
                    name: client.call(token, "whoami")["actor_profile_id"]
                    for name, token in tokens.items()
                }
                bootstrap = subprocess.run(
                    [
                        sys.executable,
                        "scripts/bootstrap_access_administrator.py",
                        "--actor-profile-id",
                        actors["administrator"],
                        "--execute",
                    ],
                    cwd=BACKEND,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    check=False,
                )
                if (
                    bootstrap.returncode
                    or json.loads(bootstrap.stdout)["result_code"] != "bootstrapped"
                ):
                    raise RuntimeError("documented deployment bootstrap failed")
                for name, role in (
                    ("manager", "project_manager"),
                    ("finance", "finance_authority"),
                    ("operator", "operator"),
                ):
                    client.write_and_replay(
                        tokens["administrator"],
                        "admin",
                        "role-grants",
                        "issue",
                        body={
                            "target_actor_profile_id": actors[name],
                            "role": role,
                            "scope_type": "system",
                            "reason": "Isolated CLI journey",
                        },
                    )
                key = str(uuid4())
                command = (
                    "project",
                    "create",
                    "--name",
                    "CLI journey",
                    "--slug",
                    "cli-journey-" + uuid4().hex,
                    "--idempotency-key",
                    key,
                )
                project = client.call(tokens["manager"], *command)
                if client.call(tokens["manager"], *command) != project:
                    raise AssertionError("project exact replay changed receipt")
                client.complete_stage("identity_authority_project")
                if through_setup:
                    # Proposal review/activation and contribution export require
                    # exact-project grants, not merely their system counterparts.
                    for name, role in (
                        ("manager", "project_manager"),
                        ("finance", "finance_authority"),
                    ):
                        client.write_and_replay(
                            tokens["administrator"],
                            "admin",
                            "role-grants",
                            "issue",
                            body={
                                "target_actor_profile_id": actors[name],
                                "role": role,
                                "scope_type": "project",
                                "scope_project_id": project["id"],
                                "reason": "Exact-project CLI journey authority",
                            },
                        )
                    for identity in (
                        "artifact.put_resolver",
                        "artifact.verifier",
                        "artifact.scheduler",
                        "artifact.binding",
                        "artifact.guide_reader",
                        "artifact.materializer",
                        "project.setup",
                        "outbox.dispatcher",
                        "checker.pre_submit",
                        "checker.post_submit",
                        "task.post_submit_router",
                        "task.assignment_reconciler",
                    ):
                        client.write(
                            tokens["administrator"],
                            "admin",
                            "service-actor",
                            "provision",
                            body={
                                "service_identity": "workstream." + identity,
                                "subject": "cli-journey-service-" + identity,
                                "reason": "Isolated CLI journey",
                            },
                            key=str(uuid4()),
                        )
                    registry_entries = {}
                    for phase in ("pre", "post"):
                        registry_entries[phase] = client.call(
                            tokens["operator"],
                            "operations",
                            "checker",
                            "registry",
                            "register",
                            "--input",
                            str(ROOT / f".local-agent-loop/registry-{phase}.json"),
                            "--idempotency-key",
                            str(uuid4()),
                        )
                    project_id = project["id"]
                    start_workers()
                    publish_unpaid_terms(client, tokens["finance"], project_id)
                    guide_id = configure_guide(client, tokens, project_id)
                    approve_and_activate(
                        client, tokens["manager"], project_id, guide_id,
                        registry_entries,
                    )
                    client.complete_stage("public_guide_activation")
                    if os.environ.get("WORKSTREAM_CLI_JOURNEY_TASKS") == "1":
                        activation = subprocess.run(
                            [
                                sys.executable,
                                "scripts/transition_review_lifecycle.py",
                                "--actor-profile-id",
                                actors["operator"],
                                "--phase",
                                "live",
                            ],
                            cwd=BACKEND,
                            env=environment,
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )
                        if activation.returncode:
                            raise RuntimeError("documented lifecycle activation failed")
                        task_id, assignment_id, grant = claim_and_read(
                            client, tokens, actors, project_id
                        )
                        client.complete_stage("task_claim_and_guide")
                        if os.environ.get("WORKSTREAM_CLI_JOURNEY_SUBMIT") == "1":
                            receipt = submit_and_observe(
                                client,
                                tokens,
                                actors,
                                project_id,
                                task_id,
                                assignment_id,
                                grant,
                            )
                            client.complete_stage(
                                "submission_contribution_export_revocation"
                            )
                            inspect_submission_custody(
                                client,
                                tokens,
                                project_id,
                                task_id,
                                receipt["submission_id"],
                            )
                            client.complete_stage("operator_submission_custody")
                print(
                    json.dumps(
                        {
                            "result": "passed",
                            "cli_invocations": len(client.steps),
                            "verified_stages": client.completed_stages,
                            "scope": "local manager-authored unpaid automated-acceptance branch",
                        }
                    )
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
