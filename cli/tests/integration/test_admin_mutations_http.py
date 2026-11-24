"""Built-binary contracts for the eight public administrative POSTs."""

import json
from pathlib import Path
from urllib.parse import quote

import pytest

from test_admin_inspection_http import ACTOR_PROFILE
from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

LINK = "018f0ebc-7966-7e8d-bc4d-1cae1e000009"
GRANT = "018f0ebc-7966-7e8d-bc4d-1cae1e000010"
STAMP = "2026-10-01T00:00:00Z"
SERVICE = "workstream.review.projection"


def service_body():
    return {
        "service_identity": SERVICE,
        "subject": "service-subject",
        "reason": " provision ",
    }


def grant_body():
    return {
        "target_actor_profile_id": ACTOR,
        "role": "project_manager",
        "scope_type": "project",
        "scope_project_id": PROJECT,
        "reason": " grant ",
    }


def service_receipt():
    return {
        "actor_profile_id": ACTOR,
        "service_identity": SERVICE,
        "actor_status": "active",
        "identity_link_status": "active",
        "provisioning_method": "manual_service_provisioning",
        "created_at": STAMP,
        "linked_at": STAMP,
    }


def test_current_source_cleanup_service_identity_reaches_public_provision(
    cli, tmp_path
):
    identity = "workstream.artifact.source_cleanup"
    file = tmp_path / "service.json"
    file.write_text(json.dumps(service_body() | {"service_identity": identity}))
    with http_fixture() as (origin, response, requests):
        response.update(
            status=201,
            body=json.dumps(
                service_receipt() | {"service_identity": identity}
            ).encode(),
        )
        result = invoke(cli, origin, file, "service-actor", "provision")
        assert result.returncode == 0
        assert json.loads(result.stdout)["service_identity"] == identity
        assert len(requests) == 1
        assert requests == [("POST", "/api/v1/service-actors", "Bearer " + TOKEN)]


def lifecycle_receipt(resource, selected, *, version=None):
    return {
        "resource_type": resource,
        "resource_id": selected,
        "version": version,
        "http_status": 200,
    }


def grant_receipt(action):
    return {
        "resource_type": "admin_role_grant",
        "resource_id": GRANT,
        "version": 1 if action == "issue" else 2,
        "http_status": 201 if action == "issue" else 200,
    }


def invoke(cli, origin, file: Path, *args, key=KEY, output="json"):
    return cli(
        origin,
        TOKEN,
        "admin",
        *args,
        "--input",
        str(file),
        "--idempotency-key",
        key,
        "-o",
        output,
    )


@pytest.mark.parametrize(
    ("args", "body", "receipt", "path", "status"),
    [
        (
            ("service-actor", "provision"),
            service_body(),
            service_receipt(),
            "/api/v1/service-actors",
            201,
        ),
        *[
            (
                ("actor", action, ACTOR),
                {"reason": "  lifecycle  "},
                lifecycle_receipt("actor_profile", ACTOR),
                f"/api/v1/actors/{ACTOR}/{action}",
                200,
            )
            for action in ("suspend", "reactivate", "deactivate")
        ],
        *[
            (
                ("identity-link", action, LINK),
                {"reason": "  lifecycle  "},
                lifecycle_receipt("actor_identity_link", LINK),
                f"/api/v1/actor-identity-links/{LINK}/{action}",
                200,
            )
            for action in ("revoke", "reactivate")
        ],
        (
            ("role-grants", "issue"),
            grant_body(),
            grant_receipt("issue"),
            "/api/v1/admin-role-grants",
            201,
        ),
        (
            ("role-grants", "revoke", GRANT),
            {"reason": " revoke "},
            grant_receipt("revoke"),
            f"/api/v1/admin-role-grants/{GRANT}/revoke",
            200,
        ),
    ],
)
def test_each_admin_write_uses_exact_public_post_and_complete_receipt(
    cli, tmp_path, args, body, receipt, path, status
):
    file = tmp_path / "decision.json"
    wire = json.dumps(body, indent=2).encode() + b"\n"
    file.write_bytes(wire)
    with http_fixture() as (origin, response, requests):
        response.update(status=status, body=json.dumps(receipt).encode())
        result = invoke(cli, origin, file, *args)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == receipt
        assert requests == [("POST", path, "Bearer " + TOKEN)]
        assert response["raw_commands"] == [wire]
        assert response["commands"] == [("application/json", [KEY], body)]
        text = invoke(cli, origin, file, *args, output="text")
        assert text.returncode == 0 and "not cached authority" in text.stdout
        assert len(requests) == 2


def test_admin_uuid_selector_normalization_and_nullable_lifecycle_version(
    cli, tmp_path
):
    file = tmp_path / "decision.json"
    file.write_text('{"reason":"explicit"}')
    selector = "{" + ACTOR + "}"
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(
            {
                k: v
                for k, v in lifecycle_receipt("actor_profile", ACTOR).items()
                if k != "version"
            }
        ).encode()
        assert invoke(cli, origin, file, "actor", "suspend", selector).returncode == 0
        assert requests == [
            (
                "POST",
                f"/api/v1/actors/{quote(selector, safe=':')}/suspend",
                "Bearer " + TOKEN,
            )
        ]
        response["body"] = json.dumps(
            lifecycle_receipt("actor_profile", ACTOR)
        ).encode()
        assert invoke(cli, origin, file, "actor", "suspend", selector).returncode == 0


def test_admin_input_contracts_preserve_distinct_reason_and_scope_semantics(
    cli, tmp_path
):
    file = tmp_path / "decision.json"
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(service_receipt()).encode())
        # ProvisionReason has no NUL or trim rule; the backend owns its final decision.
        body = service_body() | {"reason": "\x00"}
        file.write_text(json.dumps(body))
        assert invoke(cli, origin, file, "service-actor", "provision").returncode == 0
        assert response["commands"][-1][2] == body
        response.update(
            status=200,
            body=json.dumps(lifecycle_receipt("actor_profile", ACTOR)).encode(),
        )
        file.write_text(json.dumps({"reason": "  lifecycle  "}))
        assert invoke(cli, origin, file, "actor", "suspend", ACTOR).returncode == 0
        assert response["commands"][-1][2] == {"reason": "  lifecycle  "}
        for separator in "\x1c\x1d\x1e\x1f":
            python_stripped = {"reason": separator + "x" * 500}
            file.write_text(json.dumps(python_stripped))
            assert invoke(cli, origin, file, "actor", "suspend", ACTOR).returncode == 0
            assert response["commands"][-1][2] == python_stripped

        invalid = (
            (("service-actor", "provision"), service_body() | {"subject": " space "}),
            *(
                (
                    ("service-actor", "provision"),
                    service_body() | {"subject": sep + "subject"},
                )
                for sep in "\x1c\x1d\x1e\x1f"
            ),
            (
                ("service-actor", "provision"),
                service_body() | {"service_identity": "arbitrary"},
            ),
            (("actor", "suspend", ACTOR), {"reason": "  "}),
            *(
                (("actor", "suspend", ACTOR), {"reason": sep})
                for sep in "\x1c\x1d\x1e\x1f"
            ),
            (("actor", "suspend", ACTOR), {"reason": "\x00"}),
            (("identity-link", "revoke", LINK), {"reason": "é" * 251}),
            (("role-grants", "issue"), grant_body() | {"scope_project_id": None}),
            (("role-grants", "issue"), grant_body() | {"role": "arbitrary"}),
            (("role-grants", "issue"), grant_body() | {"role": "access_administrator"}),
            (("role-grants", "issue"), grant_body() | {"role": "operator"}),
            (("role-grants", "revoke", GRANT), {"reason": "\x00"}),
            (("role-grants", "revoke", GRANT), {"reason": ""}),
        )
        before = len(requests)
        for args, body in invalid:
            file.write_text(json.dumps(body))
            assert_failure(
                invoke(cli, origin, file, *args), "invalid_arguments", exit_code=2
            )
            assert len(requests) == before

        file.write_text(json.dumps(service_body()))
        assert_failure(
            invoke(cli, origin, file, "service-actor", "provision", key="not-a-uuid"),
            "invalid_arguments",
            exit_code=2,
        )
        assert_failure(
            invoke(cli, origin, file, "actor", "suspend", "not-a-uuid"),
            "invalid_arguments",
            exit_code=2,
        )
        assert len(requests) == before

        response.update(status=201, body=json.dumps(grant_receipt("issue")).encode())
        system = grant_body() | {"scope_type": "system"}
        system.pop("scope_project_id")
        for body in (system, system | {"scope_project_id": None}):
            file.write_text(json.dumps(body))
            assert invoke(cli, origin, file, "role-grants", "issue").returncode == 0
        for role in ("project_manager", "finance_authority", "audit_authority"):
            project = grant_body() | {"role": role}
            file.write_text(json.dumps(project))
            assert invoke(cli, origin, file, "role-grants", "issue").returncode == 0
            assert response["commands"][-1][2] == project


@pytest.mark.parametrize(
    "wrong",
    [
        lifecycle_receipt("actor_identity_link", ACTOR),
        lifecycle_receipt("actor_profile", LINK),
        lifecycle_receipt("actor_profile", ACTOR, version=1),
        lifecycle_receipt("actor_profile", ACTOR) | {"http_status": 201},
        lifecycle_receipt("actor_profile", ACTOR) | {"extra": "untrusted"},
        lifecycle_receipt("actor_profile", ACTOR) | {"resource_id": TOKEN},
    ],
)
def test_malformed_lifecycle_success_is_uncertain_and_silent(cli, tmp_path, wrong):
    file = tmp_path / "decision.json"
    file.write_text('{"reason":"explicit"}')
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(wrong).encode()
        result = invoke(cli, origin, file, "actor", "suspend", ACTOR)
        assert_failure(result, "invalid_api_response")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 1


@pytest.mark.parametrize(
    ("args", "body", "status", "wrong"),
    [
        (
            ("service-actor", "provision"),
            service_body(),
            201,
            service_receipt() | {"service_identity": "workstream.project.setup"},
        ),
        (
            ("service-actor", "provision"),
            service_body(),
            201,
            service_receipt() | {"actor_status": "suspended"},
        ),
        (
            ("role-grants", "issue"),
            grant_body(),
            201,
            grant_receipt("issue") | {"version": 2},
        ),
        (
            ("role-grants", "issue"),
            grant_body(),
            201,
            grant_receipt("issue") | {"extra": "untrusted"},
        ),
        (
            ("role-grants", "revoke", GRANT),
            {"reason": "revoke"},
            200,
            grant_receipt("revoke") | {"resource_id": ACTOR},
        ),
    ],
)
def test_malformed_service_or_grant_success_is_uncertain(
    cli, tmp_path, args, body, status, wrong
):
    file = tmp_path / "decision.json"
    file.write_text(json.dumps(body))
    with http_fixture() as (origin, response, requests):
        response.update(status=status, body=json.dumps(wrong).encode())
        result = invoke(cli, origin, file, *args)
        assert_failure(result, "invalid_api_response")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 1


def test_valid_uuid_bearer_reflection_is_not_printed(cli, tmp_path):
    file = tmp_path / "decision.json"
    file.write_text(json.dumps(service_body()))
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(service_receipt()).encode())
        result = cli(
            origin,
            ACTOR,
            "admin",
            "service-actor",
            "provision",
            "--input",
            str(file),
            "--idempotency-key",
            KEY,
            "-o",
            "json",
        )
        assert_failure(result, "invalid_api_response")
        assert ACTOR not in result.stdout + result.stderr
        assert len(requests) == 1


def test_admin_denial_mismatch_and_lost_response_are_distinct(cli, tmp_path):
    file = tmp_path / "decision.json"
    file.write_text('{"reason":"explicit"}')
    with http_fixture() as (origin, response, requests):
        for status, code in (
            (403, "authorization_denied"),
            (409, "idempotency_mismatch"),
        ):
            response.update(
                status=status, body=json.dumps(canonical_error(code)).encode()
            )
            result = invoke(cli, origin, file, "actor", "suspend", ACTOR)
            assert_failure(result, code)
            assert "outcome_unknown" not in json.loads(result.stderr)["error"]
        response["drop"] = True
        result = invoke(cli, origin, file, "actor", "suspend", ACTOR)
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        text = invoke(cli, origin, file, "actor", "suspend", ACTOR, output="text")
        assert text.returncode == 1 and "unchanged action" in text.stderr
        assert len(requests) == 4


def test_admin_read_namespace_remains_available(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(ACTOR_PROFILE).encode()
        result = cli(origin, TOKEN, "admin", "actor", "show", ACTOR, "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == ACTOR_PROFILE
        assert requests == [("GET", f"/api/v1/actors/{ACTOR}", "Bearer " + TOKEN)]
