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
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from uuid import uuid4

from client import JourneyClient, RefreshingToken, installed_mcp
from public_setup import configure_guide, publish_unpaid_terms, approve_and_activate
from runtime import (
    durable_runtime,
    load_journey_configuration,
    prepare_versioned_source_bucket,
)
from task_work import claim_and_read, create_claimed_task, issue_submitter
from submission_work import submit_and_observe, observe_review_pending
from artifact_work import inspect_submission_custody

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
from identity_protocol_probe import IdentityProtocolProbe  # noqa: E402
from local_flow_tokens import issue_flow_token  # noqa: E402
from run_isolated_tests import NAME_RE  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

ACTORS = ("administrator", "manager", "finance", "operator", "alice", "bob")


def public_actors(client, tokens):
    actors = {
        name: client.call(tokens[name], "whoami")["actor_profile_id"] for name in ACTORS
    }
    if len(set(actors.values())) != len(ACTORS):
        raise AssertionError("journey requires six distinct public actor profiles")
    return actors


def connected_tokens(environment):
    """Read rotating grants for isolated actors from the configured real provider."""
    issuer = environment["WORKSTREAM_TOKEN_ISSUER"]
    suffix = "/realms/flow"
    if (
        not issuer.endswith(suffix)
        or environment.get("WORKSTREAM_TOKEN_AUDIENCE") != "workstream-api"
    ):
        raise RuntimeError(
            "paired proof requires the configured Flow API issuer and audience"
        )
    provider = IdentityProtocolProbe(
        issuer.removesuffix(suffix), ssl.create_default_context()
    )
    path = Path(environment["WORKSTREAM_CLI_JOURNEY_REFRESH_FILE"])
    if not path.is_absolute():
        raise RuntimeError("paired proof refresh file must be absolute")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or not 0 < metadata.st_size <= 65_536
        ):
            raise RuntimeError("paired proof requires an owned private refresh file")
        try:
            grants = json.loads(stream.read(65_537))
        except (ValueError, UnicodeError):
            raise RuntimeError("paired proof refresh file is invalid") from None
    if type(grants) is not dict or set(grants) != {*ACTORS, "mcp"}:
        raise RuntimeError(
            "paired proof requires one refresh grant for each fixture actor and MCP"
        )
    mcp = grants["mcp"]
    if (
        type(mcp) is not dict
        or set(mcp) != {"refresh_token", "scope"}
        or type(mcp["scope"]) is not str
        or not 0 < len(mcp["scope"]) <= 128
        or "workstream:access" not in mcp["scope"].split()
    ):
        raise RuntimeError(
            "paired proof requires the original MCP refresh grant and scopes"
        )
    if any(
        type(token) is not str or not 0 < len(token) <= 8192
        for token in [*(grants[name] for name in ACTORS), mcp["refresh_token"]]
    ):
        raise RuntimeError("paired proof received an invalid refresh grant")
    return {
        name: RefreshingToken(provider, "workstream-cli-login", grants[name])
        for name in ACTORS
    } | {
        "mcp": RefreshingToken(
            provider,
            "workstream-mcp-proof",
            mcp["refresh_token"],
            resource=environment["WORKSTREAM_MCP_RESOURCE_URL"],
            scope=mcp["scope"],
        ),
    }


def run_default_review_branch(client, tokens, actors, registry_entries):
    """Use the same public setup but leave required human review untouched."""
    project = client.call(
        tokens["manager"],
        "project",
        "create",
        "--name",
        "CLI incident review branch",
        "--slug",
        "cli-review-" + uuid4().hex,
        "--idempotency-key",
        str(uuid4()),
    )
    project_id = project["id"]
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
                "scope_project_id": project_id,
                "reason": "Exact-project default review branch",
            },
        )
    publish_unpaid_terms(client, tokens["finance"], project_id)
    guide_id = configure_guide(client, tokens, project_id, human_review_required=True)
    approve_and_activate(
        client, tokens["manager"], project_id, guide_id, registry_entries
    )
    issue_submitter(client, tokens["manager"], actors["alice"], project_id)
    task_id, assignment_id = create_claimed_task(
        client, tokens, project_id, title="Human review of incident summary"
    )
    observe_review_pending(client, tokens, project_id, task_id, assignment_id)


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
        WORKSTREAM_SUBMISSION_FEEDBACK_EMAIL_ENABLED="false",
        WORKSTREAM_API_RATE_LIMIT_KEY_SECRET=base64.b64encode(
            secrets.token_bytes(32)
        ).decode(),
        WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET=base64.b64encode(
            secrets.token_bytes(32)
        ).decode(),
    )
    mcp_executable = environment.get("WORKSTREAM_CLI_JOURNEY_MCP_EXECUTABLE")
    pre_qualification = environment.get(
        "WORKSTREAM_CLI_JOURNEY_PRE_QUALIFICATION_IMAGE_DIGEST"
    )
    if pre_qualification is not None and (
        mcp_executable
        or any(
            environment.get(f"WORKSTREAM_CLI_JOURNEY_{stage}") != "1"
            for stage in ("SETUP", "TASKS", "SUBMIT")
        )
    ):
        raise RuntimeError(
            "PRE qualification requires the isolated CLI submission stages"
        )
    paired_tokens = None
    if mcp_executable:
        if any(
            environment.get(f"WORKSTREAM_CLI_JOURNEY_{stage}") != "1"
            for stage in ("SETUP", "TASKS", "SUBMIT")
        ):
            raise RuntimeError(
                "installed MCP proof requires the isolated submission stages"
            )
        paired_tokens = connected_tokens(environment)
        environment["WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET"] = ""
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
            registries = load_journey_configuration(environment)
            prepare_versioned_source_bucket(environment)
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
                tokens = paired_tokens or {
                    name: issue_flow_token(
                        f"cli-journey-{name}",
                        [],
                        issuer=issuer,
                        audience=audience,
                        secret=secret,
                    )
                    for name in ACTORS
                }
                actors = public_actors(client, tokens)
                mcp = None
                if mcp_executable:
                    mcp = stack.enter_context(
                        installed_mcp(
                            Path(mcp_executable),
                            origin,
                            directory,
                            environment,
                            tokens["mcp"],
                        )
                    )
                    if (
                        mcp.call("workstream_profile_get", {})["actor_profile_id"]
                        != actors["alice"]
                    ):
                        raise AssertionError(
                            "MCP and CLI contributor identities differ"
                        )
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
                        "artifact.source_cleanup",
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
                            str(registries[phase]),
                            "--idempotency-key",
                            str(uuid4()),
                        )
                    project_id = project["id"]
                    start_workers()
                    publish_unpaid_terms(client, tokens["finance"], project_id)
                    guide_id = configure_guide(client, tokens, project_id)
                    approve_and_activate(
                        client,
                        tokens["manager"],
                        project_id,
                        guide_id,
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
                        if pre_qualification is not None:
                            from pre_qualification import qualify

                            qualify(
                                client,
                                tokens["alice"],
                                task_id,
                                assignment_id,
                                environment,
                            )
                            client.complete_stage("source_first_pre_client_evidence")
                        elif os.environ.get("WORKSTREAM_CLI_JOURNEY_SUBMIT") == "1":
                            receipt = submit_and_observe(
                                client,
                                tokens,
                                actors,
                                project_id,
                                task_id,
                                assignment_id,
                                grant,
                                mcp=mcp,
                            )
                            client.complete_stage(
                                "submission_contribution_export_revocation"
                            )
                            if mcp is not None:
                                client.complete_stage(
                                    "installed_mcp_submission_revision"
                                )
                            inspect_submission_custody(
                                client,
                                tokens,
                                project_id,
                                task_id,
                                receipt["submission_id"],
                            )
                            client.complete_stage("operator_submission_custody")
                            run_default_review_branch(
                                client, tokens, actors, registry_entries
                            )
                            client.complete_stage("default_human_review_pending")
                print(
                    json.dumps(
                        {
                            "result": "passed",
                            "cli_invocations": len(client.steps),
                            "verified_stages": client.completed_stages,
                            "scope": "source-first PRE client evidence, native trace required"
                            if pre_qualification is not None
                            else "isolated manager-authored unpaid submission journey",
                            "authentication": "configured_flow_provider"
                            if mcp
                            else "isolated_local_hmac",
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
