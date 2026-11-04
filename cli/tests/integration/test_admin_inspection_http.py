"""Built-binary contracts for privileged, read-only administrative inspection."""

import json
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

STAMP = "2026-10-01T00:00:00Z"
ROLES = (
    "access_administrator",
    "operator",
    "project_manager",
    "finance_authority",
    "audit_authority",
)
ACTOR_PROFILE = {
    "actor_profile_id": ACTOR,
    "actor_kind": "human",
    "status": "active",
    "provisioning_method": "automatic_first_access",
    "service_identity": None,
    "display_name": "Ada\n\u202e",
    "created_at": STAMP,
    "updated_at": STAMP,
    "last_seen_at": None,
    "suspended_at": None,
    "reactivated_at": None,
    "deactivated_at": None,
}
LINK = {
    "identity_link_id": KEY,
    "actor_profile_id": ACTOR,
    "subject_kind": "human",
    "status": "active",
    "linked_at": STAMP,
    "last_verified_at": STAMP,
    "revoked_at": None,
    "reactivated_at": None,
}
GRANT = {
    "grant_id": KEY,
    "target_actor_profile_id": ACTOR,
    "role": "project_manager",
    "scope_type": "project",
    "scope_project_id": PROJECT,
    "status": "active",
    "version": 1,
    "granted_by_ref_kind": "actor_profile",
    "granted_by_ref": ACTOR,
    "granted_by_admin_role_grant_id": KEY,
    "grant_reason": "Explicit decision",
    "granted_at": STAMP,
    "revoked_by_actor_profile_id": None,
    "revoked_by_admin_role_grant_id": None,
    "revoked_reason": None,
    "revoked_at": None,
}
PERMISSIONS = {
    "items": [{"permission_id": f"test.permission_{i}"} for i in range(94)],
    "total": 94,
}
DEFINITIONS = {
    "items": [
        {
            "role": role,
            "allowed_scopes": ["system"],
            "permission_ids": ["actor.profile.read_any"],
        }
        for role in ROLES
    ],
    "total": 5,
}


def invoke(cli, origin, *args, output="json", token=TOKEN):
    return cli(origin, token, "admin", *args, "-o", output)


def page(items, cursor=None, total=None):
    return {
        "items": items,
        "total": len(items) if total is None else total,
        "next_cursor": cursor,
    }


def test_admin_exact_actor_and_catalogue_wires(cli):
    with http_fixture() as (origin, response, requests):
        for spelling in (
            ACTOR,
            ACTOR.replace("-", ""),
            "{" + ACTOR + "}",
            "urn:uuid:" + ACTOR,
        ):
            for command, body, suffix in (
                (("actor", "show", spelling), ACTOR_PROFILE, ""),
                (("actor", "identity-links", spelling), LINK, "/identity-links"),
            ):
                response["body"] = json.dumps(body).encode()
                result = invoke(cli, origin, *command)
                assert result.returncode == 0 and json.loads(result.stdout) == body, (
                    result.stderr
                )
                assert requests[-1] == (
                    "GET",
                    f"/api/v1/actors/{quote(spelling, safe=':')}{suffix}",
                    "Bearer " + TOKEN,
                )
        for command, body, path in (
            ("permissions", PERMISSIONS, "/api/v1/authorization/permissions"),
            (
                "role-definitions",
                DEFINITIONS,
                "/api/v1/authorization/admin-role-definitions",
            ),
        ):
            response["body"] = json.dumps(body).encode()
            result = invoke(cli, origin, command)
            assert result.returncode == 0 and json.loads(result.stdout) == body, (
                result.stderr
            )
            assert requests[-1] == ("GET", path, "Bearer " + TOKEN)
        response["body"] = json.dumps(ACTOR_PROFILE).encode()
        text = invoke(cli, origin, "actor", "show", ACTOR, output="text")
        assert text.returncode == 0 and "not authority" in text.stdout
        assert "\u202e" not in text.stdout and "\\u202e" in text.stdout
        service = ACTOR_PROFILE | {
            "actor_kind": "service",
            "provisioning_method": "manual_service_provisioning",
            "service_identity": "workstream.artifact.verifier",
            "display_name": None,
        }
        response["body"] = json.dumps(service).encode()
        assert json.loads(invoke(cli, origin, "actor", "show", ACTOR).stdout) == service


def test_admin_scope_filtered_grants_and_cursor(cli):
    with http_fixture() as (origin, response, requests):
        cursor = "opaque+/=é&next=not-another-parameter"
        response["body"] = json.dumps(page([GRANT], cursor, 2)).encode()
        for args, expected_path in (
            (("role-grants",), "/api/v1/admin-role-grants"),
            (
                ("actor", "role-grants", ACTOR.replace("-", "")),
                f"/api/v1/actors/{ACTOR.replace('-', '')}/admin-role-grants",
            ),
        ):
            result = invoke(
                cli,
                origin,
                *args,
                "--scope",
                "project",
                "--project-id",
                PROJECT.replace("-", ""),
                "--status",
                "active",
                "--limit",
                "1",
                "--cursor",
                cursor,
            )
            assert result.returncode == 0 and json.loads(result.stdout) == page(
                [GRANT], cursor, 2
            ), result.stderr
            url = urlsplit(requests[-1][1])
            assert url.path == expected_path
            assert parse_qs(url.query) == {
                "scope_type": ["project"],
                "scope_project_id": [PROJECT.replace("-", "")],
                "status": ["active"],
                "limit": ["1"],
                "cursor": [cursor],
            }
        system_grant = GRANT | {
            "scope_type": "system",
            "scope_project_id": None,
            "role": "access_administrator",
            "status": "revoked",
            "version": 2,
            "granted_by_ref_kind": "system_principal",
            "granted_by_ref": "workstream:system:bootstrap",
            "granted_by_admin_role_grant_id": None,
            "revoked_by_actor_profile_id": ACTOR,
            "revoked_by_admin_role_grant_id": KEY,
            "revoked_reason": "retired",
            "revoked_at": STAMP,
        }
        response["body"] = json.dumps(page([system_grant])).encode()
        result = invoke(
            cli, origin, "role-grants", "--scope", "system", "--status", "all"
        )
        assert result.returncode == 0 and json.loads(result.stdout)["items"] == [
            system_grant
        ]
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "scope_type": ["system"],
            "status": ["all"],
            "limit": ["50"],
        }
        response["body"] = json.dumps(page([])).encode()
        assert (
            invoke(
                cli, origin, "actor", "role-grants", ACTOR, "--scope", "system"
            ).returncode
            == 0
        )


def test_admin_omitted_status_binds_default_active_response_on_both_routes(cli):
    revoked = GRANT | {
        "status": "revoked",
        "version": 2,
        "revoked_by_actor_profile_id": ACTOR,
        "revoked_by_admin_role_grant_id": KEY,
        "revoked_reason": "End assignment",
        "revoked_at": STAMP,
    }
    with http_fixture() as (origin, response, requests):
        for args in (("role-grants",), ("actor", "role-grants", ACTOR)):
            response["body"] = json.dumps(page([GRANT])).encode()
            active = invoke(
                cli, origin, *args, "--scope", "project", "--project-id", PROJECT
            )
            assert active.returncode == 0 and json.loads(active.stdout)["items"] == [
                GRANT
            ]
            assert "status" not in parse_qs(urlsplit(requests[-1][1]).query)

            response["body"] = json.dumps(page([revoked])).encode()
            refused = invoke(
                cli, origin, *args, "--scope", "project", "--project-id", PROJECT
            )
            assert_failure(refused, "invalid_api_response")
            assert "status" not in parse_qs(urlsplit(requests[-1][1]).query)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "active", "suspended_at": STAMP},
        {"status": "active", "deactivated_at": STAMP},
        {"status": "suspended", "suspended_at": None},
        {"status": "deactivated", "deactivated_at": None},
    ],
)
def test_admin_actor_response_integrity_rejects_impossible_lifecycle(cli, changes):
    with http_fixture() as (origin, response, _requests):
        response["body"] = json.dumps(ACTOR_PROFILE | changes).encode()
        assert_failure(
            invoke(cli, origin, "actor", "show", ACTOR), "invalid_api_response"
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "active", "revoked_at": STAMP},
        {"status": "revoked", "revoked_at": None},
    ],
)
def test_admin_identity_link_response_integrity_rejects_impossible_lifecycle(
    cli, changes
):
    with http_fixture() as (origin, response, _requests):
        response["body"] = json.dumps(LINK | changes).encode()
        assert_failure(
            invoke(cli, origin, "actor", "identity-links", ACTOR),
            "invalid_api_response",
        )


def test_admin_actor_and_link_reactivated_history_remains_readable(cli):
    with http_fixture() as (origin, response, _requests):
        for actor in (
            ACTOR_PROFILE | {"status": "active", "reactivated_at": STAMP},
            ACTOR_PROFILE | {"status": "suspended", "suspended_at": STAMP},
            ACTOR_PROFILE
            | {
                "status": "deactivated",
                "suspended_at": STAMP,
                "deactivated_at": STAMP,
            },
        ):
            response["body"] = json.dumps(actor).encode()
            result = invoke(cli, origin, "actor", "show", ACTOR)
            assert result.returncode == 0 and json.loads(result.stdout) == actor, (
                result.stderr
            )
        for link in (
            LINK | {"status": "active", "reactivated_at": STAMP},
            LINK | {"status": "revoked", "revoked_at": STAMP},
        ):
            response["body"] = json.dumps(link).encode()
            result = invoke(cli, origin, "actor", "identity-links", ACTOR)
            assert result.returncode == 0 and json.loads(result.stdout) == link, (
                result.stderr
            )


REVOKED_GRANT = GRANT | {
    "status": "revoked",
    "version": 2,
    "revoked_by_actor_profile_id": ACTOR,
    "revoked_by_admin_role_grant_id": KEY,
    "revoked_reason": "End assignment",
    "revoked_at": STAMP,
}


@pytest.mark.parametrize(
    "grant",
    [
        REVOKED_GRANT | {"status": "active"},
        REVOKED_GRANT | {"version": 1},
        REVOKED_GRANT | {"revoked_at": None},
        REVOKED_GRANT | {"revoked_reason": ""},
        REVOKED_GRANT | {"revoked_reason": "é" * 251},
        GRANT | {"version": 2},
        GRANT | {"revoked_at": STAMP},
        GRANT | {"role": "operator"},
        GRANT | {"role": "access_administrator"},
    ],
)
def test_admin_grant_response_integrity_rejects_impossible_scope_or_lifecycle(
    cli, grant
):
    with http_fixture() as (origin, response, _requests):
        response["body"] = json.dumps(page([grant])).encode()
        for args in (("role-grants",), ("actor", "role-grants", ACTOR)):
            assert_failure(
                invoke(
                    cli,
                    origin,
                    *args,
                    "--scope",
                    "project",
                    "--project-id",
                    PROJECT,
                    "--status",
                    "all",
                ),
                "invalid_api_response",
            )


def test_admin_grant_active_and_revoked_history_remains_readable(cli):
    with http_fixture() as (origin, response, _requests):
        response["body"] = json.dumps(
            page([GRANT, REVOKED_GRANT | {"grant_id": PROJECT}])
        ).encode()
        result = invoke(
            cli,
            origin,
            "role-grants",
            "--scope",
            "project",
            "--project-id",
            PROJECT,
            "--status",
            "all",
        )
        assert result.returncode == 0 and json.loads(result.stdout)["items"] == [
            GRANT,
            REVOKED_GRANT | {"grant_id": PROJECT},
        ], result.stderr


def test_admin_rejects_bad_inputs_without_dispatch(cli):
    with http_fixture() as (origin, _response, requests):
        for args in (
            ("actor", "show", "not-a-uuid"),
            ("actor", "identity-links", "bad"),
            ("actor", "role-grants", "bad", "--scope", "system"),
            ("role-grants",),
            ("role-grants", "--scope", "project"),
            ("role-grants", "--scope", "system", "--project-id", PROJECT),
            ("role-grants", "--scope", "project", "--project-id", "bad"),
            ("role-grants", "--scope", "system", "--status", "any"),
            ("role-grants", "--scope", "system", "--limit", "0"),
            ("role-grants", "--scope", "system", "--limit", "101"),
            ("role-grants", "--scope", "system", "--cursor", ""),
        ):
            assert_failure(invoke(cli, origin, *args), "invalid_arguments", 2)
        assert requests == []


def test_admin_rejects_malformed_and_mismatched_success(cli):
    with http_fixture() as (origin, response, _requests):
        for body in (
            ACTOR_PROFILE | {"actor_profile_id": PROJECT},
            ACTOR_PROFILE | {"actor_kind": "service"},
            ACTOR_PROFILE | {"service_identity": "workstream.artifact.verifier"},
            ACTOR_PROFILE
            | {
                "actor_kind": "service",
                "service_identity": "workstream.unknown.service",
            },
            ACTOR_PROFILE | {"created_at": None},
            ACTOR_PROFILE | {"extra": "private"},
            {k: v for k, v in ACTOR_PROFILE.items() if k != "last_seen_at"},
            ACTOR_PROFILE | {"display_name": TOKEN},
        ):
            response["body"] = json.dumps(body).encode()
            assert_failure(
                invoke(cli, origin, "actor", "show", ACTOR), "invalid_api_response"
            )
        for body in (
            LINK | {"actor_profile_id": PROJECT},
            LINK | {"subject_kind": "agent"},
            LINK | {"last_verified_at": "bad"},
            [LINK],
        ):
            response["body"] = json.dumps(body).encode()
            assert_failure(
                invoke(cli, origin, "actor", "identity-links", ACTOR),
                "invalid_api_response",
            )
        for body in (
            page([GRANT | {"target_actor_profile_id": PROJECT}]),
            page([GRANT | {"scope_project_id": ACTOR}]),
            page([GRANT | {"status": "revoked"}]),
            page([GRANT, GRANT], total=2),
            page([GRANT], total=0),
            page([GRANT], cursor=""),
            page([GRANT | {"grant_reason": TOKEN}]),
            page([GRANT | {"grant_reason": "x" * (256 * 1024)}]),
            {"items": [GRANT], "total": 1},
        ):
            response["body"] = json.dumps(body).encode()
            result = invoke(
                cli,
                origin,
                "actor",
                "role-grants",
                ACTOR,
                "--scope",
                "project",
                "--project-id",
                PROJECT,
                "--status",
                "active",
            )
            assert_failure(result, "invalid_api_response")
        for command, body in (
            ("permissions", PERMISSIONS | {"total": 81}),
            (
                "permissions",
                {
                    "items": PERMISSIONS["items"]
                    + [{"permission_id": "operations.task.start_override"}],
                    "total": 95,
                },
            ),
            ("permissions", PERMISSIONS | {"unknown": True}),
            ("permissions", PERMISSIONS | {"items": [PERMISSIONS["items"][0]] * 94}),
            ("role-definitions", DEFINITIONS | {"items": DEFINITIONS["items"][:-1]}),
            (
                "role-definitions",
                DEFINITIONS | {"items": [DEFINITIONS["items"][0]] * 5},
            ),
        ):
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin, command), "invalid_api_response")


def test_admin_denial_is_concealed_and_never_retried(cli):
    with http_fixture() as (origin, response, requests):
        for status, code in ((403, "permission_not_granted"), (404, "actor_not_found")):
            response["status"] = status
            response["body"] = json.dumps(canonical_error(code)).encode()
            before = len(requests)
            assert_failure(invoke(cli, origin, "actor", "show", ACTOR), code)
            assert len(requests) == before + 1
