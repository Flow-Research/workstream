"""Signed public API/PostgreSQL journey for explicit administrative CLI writes."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

import pytest

from test_public_self_service import _ready

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "tests"))
from api_contract_e2e import (  # noqa: E402
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
)
from app.db.session import dispose_engine  # noqa: E402
from scripts.bootstrap_access_administrator import _run as run_bootstrap  # noqa: E402
from tests.conftest import (  # noqa: E402
    configured_source_instance_id as configured_source_instance_id,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
)


def write(
    cli,
    origin: str,
    token: str,
    input_file: Path,
    args: tuple[str, ...],
    body: dict,
    *,
    key: str | None = None,
):
    input_file.write_text(json.dumps(body), encoding="utf-8")
    return cli(
        origin,
        token,
        "admin",
        *args,
        "--input",
        str(input_file),
        "--idempotency-key",
        key or str(uuid4()),
        "-o",
        "json",
    )


def success(result, resource: str, status: int) -> dict:
    assert result.returncode == 0 and result.stderr == "", result.stderr
    value = json.loads(result.stdout)
    if resource == "service_actor":
        assert value["actor_status"] == value["identity_link_status"] == "active"
    else:
        assert value["resource_type"] == resource and value["http_status"] == status
    return value


def denial(result, status: int, code: str) -> None:
    assert result.returncode == 1 and result.stdout == "", result.stderr
    error = json.loads(result.stderr)["error"]
    assert error["status"] == status and error["code"] == code
    assert "outcome_unknown" not in error


def read(cli, origin: str, token: str, *args: str) -> dict:
    result = cli(origin, token, "admin", *args, "-o", "json")
    assert result.returncode == 0 and result.stderr == "", result.stderr
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_admin_cli_writes_preserve_real_authority_and_distinct_lifecycles(
    tmp_path: Path, cli, clean_postgres_database
) -> None:
    env = api_environment()
    assert env["WORKSTREAM_DATABASE_URL"] == clean_postgres_database
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    tokens = {
        name: issue_flow_token(
            name + "-cli607", [], issuer=issuer, audience=audience, secret=secret
        )
        for name in ("admin", "second", "target", "outsider")
    }
    origin = f"http://127.0.0.1:{find_free_port()}"
    input_file = tmp_path / "admin-decision.json"
    with (tmp_path / "admin-mutations-api.log").open("wb") as log:
        process = subprocess.Popen(  # noqa: S603 - fixed local API fixture
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                origin.rsplit(":", 1)[1],
                "--log-level",
                "error",
                "--no-access-log",
            ],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            await _ready(origin + "/api/v1/health", process)
            profiles = {}
            for name, token in tokens.items():
                result = cli(origin, token, "whoami", "-o", "json")
                assert result.returncode == 0, result.stderr
                profiles[name] = json.loads(result.stdout)["actor_profile_id"]
            bootstrap_code, bootstrap = await run_bootstrap(
                UUID(profiles["admin"]), execute=True
            )
            assert bootstrap_code == 0 and bootstrap["result_code"] == "bootstrapped"
            admin, second, target, outsider = (
                tokens[name] for name in ("admin", "second", "target", "outsider")
            )

            provision = {
                "service_identity": "workstream.review.projection",
                "subject": "service-cli607",
                "reason": "Explicit fixed principal",
            }
            denial(
                write(
                    cli,
                    origin,
                    outsider,
                    input_file,
                    ("service-actor", "provision"),
                    provision,
                ),
                403,
                "permission_not_granted",
            )
            created = success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("service-actor", "provision"),
                    provision,
                ),
                "service_actor",
                201,
            )
            service_actor = read(
                cli, origin, admin, "actor", "show", created["actor_profile_id"]
            )
            assert service_actor["service_identity"] == provision["service_identity"]
            assert (
                service_actor["actor_kind"] == "service"
                and service_actor["status"] == "active"
            )

            issue = {
                "target_actor_profile_id": profiles["second"],
                "role": "access_administrator",
                "scope_type": "system",
                "reason": "Second administrator",
            }
            issue_key = str(uuid4())
            first = success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("role-grants", "issue"),
                    issue,
                    key=issue_key,
                ),
                "admin_role_grant",
                201,
            )
            assert (
                success(
                    write(
                        cli,
                        origin,
                        admin,
                        input_file,
                        ("role-grants", "issue"),
                        issue,
                        key=issue_key,
                    ),
                    "admin_role_grant",
                    201,
                )
                == first
            )
            denial(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("role-grants", "issue"),
                    issue | {"reason": "Changed"},
                    key=issue_key,
                ),
                409,
                "idempotency_mismatch",
            )
            second_grant = first["resource_id"]
            assert first["version"] == 1

            # A second current administrator can write; profile suspension does
            # not revoke the target's identity link.
            success(
                write(
                    cli,
                    origin,
                    second,
                    input_file,
                    ("actor", "suspend", profiles["target"]),
                    {"reason": "Explicit target pause"},
                ),
                "actor_profile",
                200,
            )
            assert (
                read(cli, origin, admin, "actor", "show", profiles["target"])["status"]
                == "suspended"
            )
            target_link = read(
                cli, origin, admin, "actor", "identity-links", profiles["target"]
            )
            assert target_link["status"] == "active"
            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("actor", "reactivate", profiles["target"]),
                    {"reason": "Resume target"},
                ),
                "actor_profile",
                200,
            )

            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("actor", "suspend", profiles["second"]),
                    {"reason": "Pause administrator"},
                ),
                "actor_profile",
                200,
            )
            denial(
                write(
                    cli,
                    origin,
                    second,
                    input_file,
                    ("actor", "suspend", profiles["target"]),
                    {"reason": "Denied while suspended"},
                ),
                403,
                "actor_suspended",
            )
            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("actor", "reactivate", profiles["second"]),
                    {"reason": "Resume administrator"},
                ),
                "actor_profile",
                200,
            )

            second_link = read(
                cli, origin, admin, "actor", "identity-links", profiles["second"]
            )["identity_link_id"]
            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("identity-link", "revoke", second_link),
                    {"reason": "Pause external binding"},
                ),
                "actor_identity_link",
                200,
            )
            assert (
                read(cli, origin, admin, "actor", "show", profiles["second"])["status"]
                == "active"
            )
            denial(
                write(
                    cli,
                    origin,
                    second,
                    input_file,
                    ("actor", "suspend", profiles["target"]),
                    {"reason": "Denied with revoked link"},
                ),
                403,
                "identity_link_revoked",
            )
            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("identity-link", "reactivate", second_link),
                    {"reason": "Restore external binding"},
                ),
                "actor_identity_link",
                200,
            )

            revoked = success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("role-grants", "revoke", second_grant),
                    {"reason": "End administrator grant"},
                ),
                "admin_role_grant",
                200,
            )
            assert revoked["resource_id"] == second_grant and revoked["version"] == 2
            denial(
                write(
                    cli,
                    origin,
                    second,
                    input_file,
                    ("role-grants", "revoke", bootstrap["grant_id"]),
                    {"reason": "Cross revoke after authority loss"},
                ),
                403,
                "permission_not_granted",
            )
            retained = read(cli, origin, admin, "role-grants", "--scope", "system")
            assert any(
                item["grant_id"] == bootstrap["grant_id"] and item["status"] == "active"
                for item in retained["items"]
            )
            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("identity-link", "revoke", second_link),
                    {"reason": "Revoke link again"},
                ),
                "actor_identity_link",
                200,
            )
            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("identity-link", "reactivate", second_link),
                    {"reason": "Reactivate link again"},
                ),
                "actor_identity_link",
                200,
            )
            denial(
                write(
                    cli,
                    origin,
                    second,
                    input_file,
                    ("actor", "suspend", profiles["target"]),
                    {"reason": "Grant remains revoked"},
                ),
                403,
                "permission_not_granted",
            )

            success(
                write(
                    cli,
                    origin,
                    admin,
                    input_file,
                    ("actor", "deactivate", profiles["target"]),
                    {"reason": "Final target deactivation"},
                ),
                "actor_profile",
                200,
            )
            assert (
                read(cli, origin, admin, "actor", "show", profiles["target"])["status"]
                == "deactivated"
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            await dispose_engine()
