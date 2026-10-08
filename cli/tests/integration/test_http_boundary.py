"""Exercise the built CLI against deliberately hostile HTTP responses."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
from urllib.parse import parse_qs, urlsplit

from http2_fixture import goaway_fixture

TOKEN = "caller.flow.token"
ACTOR = "018f0ebc-7966-7e8d-bc4d-1cae1e000001"
PROJECT = "018f0ebc-7966-7e8d-bc4d-1cae1e000002"
PROFILE = {
    "actor_profile_id": ACTOR,
    "actor_kind": "human",
    "status": "active",
    "domains": ["contributor"],
    "admin_roles": [],
    "project_role_grants": [],
    "display_name": "Ada",
    "contact_email": None,
    "created_at": "2026-10-01T00:00:00Z",
    "updated_at": "2026-10-01T00:00:00Z",
    "last_seen_at": None,
}
CONTEXT = {
    "actor_profile_id": ACTOR,
    "status": "active",
    "project_id": PROJECT,
    "admin_roles": [],
    "project_roles": ["submitter"],
    "effective_action_ids": ["task.claim"],
}


@contextmanager
def http_fixture():
    requests = []
    response = {
        "status": 200,
        "body": json.dumps(PROFILE).encode(),
        "headers": {"Content-Type": "application/json"},
        "delay": 0,
        "drop": False,
        "updates": [],
        "commands": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - standard HTTP handler interface
            requests.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            if response["drop"]:
                self.close_connection = True
                return
            time.sleep(response["delay"])
            self.send_response(response["status"])
            for key, value in response["headers"].items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(response["body"])
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_PATCH(self):  # noqa: N802 - standard HTTP handler interface
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            response["updates"].append(
                (self.headers.get("Content-Type"), json.loads(body))
            )
            self.do_GET()

        def do_POST(self):  # noqa: N802 - standard HTTP handler interface
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            response.setdefault("raw_commands", []).append(body)
            response["commands"].append(
                (
                    self.headers.get("Content-Type"),
                    self.headers.get_all("Idempotency-Key"),
                    json.loads(body)
                    if self.headers.get("Content-Type") == "application/json"
                    else body,
                )
            )
            response.setdefault("content_lengths", []).append(
                self.headers.get("Content-Length")
            )
            if after_body := response.get("after_body"):
                after_body()
            self.do_GET()

        def do_CONNECT(self):  # noqa: N802 - captures attempted HTTPS proxy use
            requests.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            self.send_error(502)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", response, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def assert_failure(result, code, exit_code=1):
    assert result.returncode == exit_code and result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == code


def test_project_show_preserves_projection_and_selector(cli):
    minimal = {"id": PROJECT, "name": "Project é\n\x1b[31m", "status": "draft"}
    full = minimal | {
        "slug": "project-slug",
        "description": "Details\n\x1b[32m",
        "created_at": PROFILE["created_at"],
        "updated_at": "2026-10-02T00:00:00Z",
    }
    with http_fixture() as (origin, response, requests):
        for value in (minimal, full, full | {"description": None}):
            response["body"] = json.dumps(value).encode()
            for selector in (
                PROJECT,
                PROJECT.replace("-", ""),
                "{" + PROJECT + "}",
                "urn:uuid:" + PROJECT,
            ):
                result = cli(origin, TOKEN, "project", "show", selector, "-o", "json")
                assert result.returncode == 0 and result.stderr == ""
                assert result.stdout.strip().encode() == response["body"]
                assert requests[-1] == (
                    "GET",
                    "/api/v1/projects/"
                    + selector.replace("{", "%7B").replace("}", "%7D"),
                    "Bearer " + TOKEN,
                )
            text = cli(origin, TOKEN, "project", "show", PROJECT)
            assert text.returncode == 0 and text.stderr == ""
            expected = f"Project: {PROJECT}\nName: Project é\\u000A\\u001B[31m\nStatus: draft\n"
            if "slug" in value:
                description = (
                    "—" if value["description"] is None else "Details\\u000A\\u001B[32m"
                )
                expected += (
                    f"Slug: project-slug\nDescription: {description}\n"
                    "Created: 2026-10-01T00:00:00Z\nUpdated: 2026-10-02T00:00:00Z\n"
                )
            assert text.stdout == expected
        assert len(requests) == 15  # Exactly one call per invocation; no preflight.


def test_project_show_rejects_malformed_or_substituted_projection(cli):
    minimal = {"id": PROJECT, "name": "Project", "status": "draft"}
    full = minimal | {
        "slug": "project-slug",
        "description": None,
        "created_at": PROFILE["created_at"],
        "updated_at": PROFILE["updated_at"],
    }
    variants = [
        json.dumps(minimal | {"id": ACTOR}),
        json.dumps(minimal | {"id": "not-uuid"}),
        json.dumps(minimal | {"name": None}),
        json.dumps(minimal | {"status": None}),
        json.dumps(minimal | {"slug": "partial"}),
        json.dumps(full | {"slug": None}),
        json.dumps(full | {"description": 12}),
        json.dumps(full | {"created_at": "not-time"}),
        json.dumps(full | {"updated_at": None}),
        json.dumps(full | {"private_storage_path": "secret"}),
        json.dumps({k: v for k, v in full.items() if k != "description"}),
        '{"id":"' + PROJECT + '","name":"A","status":"draft","name":"B"}',
        json.dumps({"ID": PROJECT, "name": "Project", "status": "draft"}),
        "null",
        "[]",
    ]
    with http_fixture() as (origin, response, requests):
        for value in variants:
            response["body"] = value.encode()
            result = cli(origin, TOKEN, "project", "show", PROJECT, "-o", "json")
            assert_failure(result, "invalid_api_response")
        assert len(requests) == len(variants)


def test_project_show_invalid_arguments_and_redirect_are_bounded(cli):
    with http_fixture() as (origin, response, requests):
        for args in (
            (),
            ("not-uuid",),
            (PROJECT + "/guides",),
            (PROJECT + "?token=" + TOKEN,),
            (PROJECT + "#fragment",),
            (PROJECT + "-" * 1000,),
            (PROJECT, "extra"),
            (PROJECT, "--actor-id", ACTOR),
            (PROJECT, "--endpoint", "/private"),
        ):
            assert_failure(
                cli(origin, TOKEN, "-o", "json", "project", "show", *args),
                "invalid_arguments",
                2,
            )
        assert requests == []
        with http_fixture() as (sink, _, forwarded):
            response.update(status=307, body=b"", headers={"Location": sink})
            assert_failure(
                cli(origin, TOKEN, "project", "show", PROJECT, "-o", "json"),
                "redirect_refused",
            )
            assert len(requests) == 1 and forwarded == []
        response.update(
            status=404,
            body=b'{"error":{"code":"project_authorization_resource_not_found"}}',
        )
        denied = cli(origin, TOKEN, "project", "show", PROJECT, "-o", "json")
        assert_failure(denied, "project_authorization_resource_not_found")
        assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
        assert len(requests) == 2


def test_profile_patch_is_not_replayed_after_http2_goaway(cli, tmp_path):
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = cli(
            origin,
            TOKEN,
            "-o",
            "json",
            "profile",
            "update",
            "--display-name",
            "Received before GOAWAY",
            extra_env=env,
        )
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert [json.loads(value) for value in bodies] == [
            {"display_name": "Received before GOAWAY"}
        ]
        assert connections == ["h2"]


def test_profile_update_sends_only_selected_fields(cli):
    with http_fixture() as (origin, response, requests):
        for flags, expected in (
            (("--display-name", "Ada é"), {"display_name": "Ada é"}),
            (
                ("--contact-email", "contact@example.test"),
                {"contact_email": "contact@example.test"},
            ),
            (("--clear-display-name",), {"display_name": None}),
            (("--clear-contact-email",), {"contact_email": None}),
            (
                ("--display-name", "Ada", "--clear-contact-email"),
                {"display_name": "Ada", "contact_email": None},
            ),
            (
                ("--clear-display-name", "--clear-contact-email"),
                {"display_name": None, "contact_email": None},
            ),
        ):
            result = cli(origin, TOKEN, "profile", "update", *flags, "-o", "json")
            assert result.returncode == 0 and result.stderr == ""
            assert json.loads(result.stdout) == PROFILE
            assert response["updates"][-1] == ("application/json", expected)
        assert requests == [("PATCH", "/api/v1/actors/me", "Bearer " + TOKEN)] * 6
        response["body"] = json.dumps({**PROFILE, "display_name": "Ada\x1b"}).encode()
        text = cli(origin, TOKEN, "profile", "update", "--display-name", "Ada")
        assert text.returncode == 0 and "Name: Ada\\u001B\n" in text.stdout


def test_profile_update_bad_arguments_never_write(cli):
    with http_fixture() as (origin, response, requests):
        for flags in (
            (),
            ("--clear-display-name=false",),
            ("--display-name", "Ada", "--clear-display-name"),
            ("--contact-email", "x", "--clear-contact-email"),
            ("--actor-profile-id", ACTOR),
            ("--admin-roles", "access_administrator"),
            ("unexpected",),
            ("--display-name", "x" * 9000),
            ("--display-name", b"\xff"),
        ):
            result = cli(origin, TOKEN, "-o", "json", "profile", "update", *flags)
            assert_failure(result, "invalid_arguments", exit_code=2)
        assert requests == [] and response["updates"] == []


def test_profile_update_uncertainty_and_known_denials(cli):
    with http_fixture() as (origin, response, requests):
        # Record body receipt, then lose the connection before status headers.
        response["drop"] = True
        result = cli(
            origin, TOKEN, "profile", "update", "--display-name", "Ada", "-o", "json"
        )
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(response["updates"]) == 1
        response["drop"] = False
        for status, body, headers, code, unknown in (
            (
                403,
                b'{"error":{"code":"actor_suspended"}}',
                {},
                "actor_suspended",
                False,
            ),
            (
                422,
                b'{"error":{"code":"validation_error"}}',
                {},
                "validation_error",
                False,
            ),
            (
                503,
                b'{"error":{"code":"service_unavailable"}}',
                {},
                "service_unavailable",
                True,
            ),
            (
                422,
                b'{"error":{"code":"invalid_api_response"}}',
                {},
                "invalid_api_response",
                False,
            ),
            (408, b"gateway timeout", {}, "api_error", True),
            (429, b"{}", {}, "api_error", True),
            (
                408,
                b'{"Error":{"Code":"gateway_timeout"}}',
                {},
                "api_error",
                True,
            ),
            (
                408,
                b'{"error":{"Code":"gateway_timeout"}}',
                {},
                "api_error",
                True,
            ),
            (
                408,
                b'{"Error":{"code":"gateway_timeout"}}',
                {},
                "api_error",
                True,
            ),
            (
                408,
                b'{"error":{"code":"a"},"error":{"code":"b"}}',
                {},
                "api_error",
                True,
            ),
            (
                408,
                b'{"error":{"code":"a","code":"b"}}',
                {},
                "api_error",
                True,
            ),
            (
                422,
                json.dumps({"error": {"code": TOKEN}}).encode(),
                {},
                "api_error",
                False,
            ),
            (200, b'{"actor_profile_id":"bad"}', {}, "invalid_api_response", True),
            (
                200,
                json.dumps(PROFILE).encode(),
                {"Content-Length": "99999"},
                "invalid_api_response",
                True,
            ),
            (200, b"x" * 65537, {}, "invalid_api_response", True),
        ):
            response.update(
                status=status,
                body=body,
                headers={"Content-Type": "application/json", **headers},
            )
            before = len(requests)
            result = cli(
                origin,
                TOKEN,
                "profile",
                "update",
                "--clear-contact-email",
                "-o",
                "json",
            )
            assert (
                json.loads(result.stderr)["error"].get("outcome_unknown", False)
                is unknown
            )
            assert_failure(result, code)
            assert len(requests) == before + 1
        response.update(
            status=503, body=b"{}", headers={"Content-Type": "application/json"}
        )
        text = cli(origin, TOKEN, "profile", "update", "--clear-display-name")
        assert text.returncode == 1 and text.stdout == ""
        assert "update outcome unknown; read whoami before retrying" in text.stderr


def test_profile_update_redirect_does_not_forward_body_or_bearer(cli):
    with (
        http_fixture() as (sink, _, sink_requests),
        http_fixture() as (origin, response, requests),
    ):
        response.update(status=307, body=b"", headers={"Location": sink})
        result = cli(
            origin, TOKEN, "profile", "update", "--display-name", "Ada", "-o", "json"
        )
        assert_failure(result, "redirect_refused")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 1 and sink_requests == []


def test_public_commands_and_noninteractive_output(cli):
    with http_fixture() as (origin, response, requests):
        raw = response["body"].decode()
        profile = cli(origin, TOKEN, "whoami", "-o", "json")
        assert (
            profile.returncode == 0
            and profile.stderr == ""
            and profile.stdout == raw + "\n"
        )
        assert requests == [("GET", "/api/v1/actors/me", "Bearer " + TOKEN)]

        response["body"] = json.dumps(
            {**PROFILE, "display_name": "Ada\x1b[31m\u202e"}
        ).encode()
        human = cli(origin, TOKEN, "whoami")
        assert human.returncode == 0 and human.stderr == ""
        assert "Ada\\u001B[31m\\u202E" in human.stdout and "\x1b" not in human.stdout

        defaulted = {
            key: value
            for key, value in PROFILE.items()
            if key not in {"domains", "admin_roles", "project_role_grants"}
        }
        response["body"] = json.dumps(defaulted).encode()
        omitted_defaults = cli(origin, TOKEN, "whoami", "-o", "json")
        assert omitted_defaults.returncode == 0 and omitted_defaults.stderr == ""
        assert json.loads(omitted_defaults.stdout) == defaulted

        response["body"] = json.dumps(CONTEXT).encode()
        context = cli(origin, TOKEN, "project", "access", PROJECT, "-o", "json")
        assert (
            context.returncode == 0
            and context.stderr == ""
            and json.loads(context.stdout) == CONTEXT
        )
        method, target, authorization = requests[-1]
        assert method == "GET" and authorization == "Bearer " + TOKEN
        parsed = urlsplit(target)
        assert parsed.path == "/api/v1/actors/me/authorization-context"
        assert parse_qs(parsed.query) == {"project_id": [PROJECT]}

        response["body"] = json.dumps(
            {
                **CONTEXT,
                "admin_roles": ["project_manager\x1b"],
                "project_roles": ["submitter\u202e"],
                "effective_action_ids": ["task.claim\x1b"],
            }
        ).encode()
        human_context = cli(origin, TOKEN, "project", "access", PROJECT)
        assert human_context.returncode == 0 and human_context.stderr == ""
        assert human_context.stdout == (
            f"Project: {PROJECT}\nActor: {ACTOR}\nStatus: active\n"
            "Admin roles: project_manager\\u001B\n"
            "Project roles: submitter\\u202E\n"
            "Effective actions (1):\n  task.claim\\u001B\n"
        )

        selector = "project /?&= é"
        response.update(
            status=404,
            body=json.dumps(
                {"error": {"code": "project_authorization_resource_not_found"}}
            ).encode(),
        )
        assert_failure(
            cli(origin, TOKEN, "project", "access", selector, "-o", "json"),
            "project_authorization_resource_not_found",
        )
        assert parse_qs(urlsplit(requests[-1][1]).query) == {"project_id": [selector]}

        response.update(status=200, body=json.dumps(CONTEXT).encode())
        assert_failure(
            cli(origin, TOKEN, "project", "access", "foreign", "-o", "json"),
            "invalid_api_response",
        )

        # A parser must not accept an ambiguous authority object and then emit
        # its conflicting fields unchanged for another consumer to interpret.
        for body in (
            ('{"project_id":"foreign",' + json.dumps(CONTEXT)[1:]).encode(),
            json.dumps({**CONTEXT, "PROJECT_ID": "foreign"}).encode(),
        ):
            response["body"] = body
            assert_failure(
                cli(origin, TOKEN, "project", "access", PROJECT, "-o", "json"),
                "invalid_api_response",
            )


def test_api_failures_and_invalid_responses(cli):
    with http_fixture() as (origin, response, requests):
        response.update(
            status=403,
            body=json.dumps(
                {"error": {"code": "permission_not_granted", "message": TOKEN}}
            ).encode(),
        )
        denied = cli(origin, TOKEN, "whoami", "-o", "json")
        assert_failure(denied, "permission_not_granted")
        assert json.loads(denied.stderr)["error"]["status"] == 403

        correlation = "018f0ebc-7966-7e8d-bc4d-1cae1e000003"
        response["headers"]["X-Correlation-ID"] = correlation
        human_denied = cli(origin, TOKEN, "whoami")
        assert human_denied.returncode == 1 and human_denied.stdout == ""
        assert human_denied.stderr == (
            f"Error: permission_not_granted (HTTP 403; correlation {correlation})\n"
        )
        response["headers"]["X-Correlation-ID"] = "unsafe-correlation"
        response["headers"]["X-Request-ID"] = correlation
        fallback = cli(origin, TOKEN, "whoami", "-o", "json")
        assert_failure(fallback, "permission_not_granted")
        assert json.loads(fallback.stderr)["error"]["correlation_id"] == correlation
        response["headers"]["X-Request-ID"] = "also-unsafe"
        dropped = cli(origin, TOKEN, "whoami", "-o", "json")
        assert_failure(dropped, "permission_not_granted")
        assert "correlation_id" not in json.loads(dropped.stderr)["error"]

        response["status"] = 200
        for body, content_type in (
            (b"{", "application/json"),
            (b"{}", "application/json"),
            (json.dumps({**PROFILE, "admin_roles": None}).encode(), "application/json"),
            (
                json.dumps({**PROFILE, "status": "unrecognized"}).encode(),
                "application/json",
            ),
            (json.dumps(PROFILE).encode(), "text/plain"),
            (
                json.dumps({**PROFILE, "display_name": "a" * 65537}).encode(),
                "application/json",
            ),
        ):
            response.update(body=body, headers={"Content-Type": content_type})
            before = len(requests)
            assert_failure(
                cli(origin, TOKEN, "whoami", "-o", "json"), "invalid_api_response"
            )
            assert len(requests) == before + 1, "invalid response was retried"


def test_reflected_credentials_are_not_error_codes(cli):
    with http_fixture() as (origin, response, _requests):
        for output in ("text", "json"):
            token = "credential_canary_AAA"
            for code in (token, token.upper(), "prefix_" + token + "_suffix"):
                response.update(
                    status=403,
                    body=json.dumps({"error": {"code": code}}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                result = cli(origin, token, "whoami", "-o", output)
                assert result.returncode == 1 and result.stdout == ""
                if output == "json":
                    assert json.loads(result.stderr)["error"] == {
                        "code": "api_error",
                        "status": 403,
                    }
                else:
                    assert result.stderr == "Error: api_error (HTTP 403)\n"


def test_reflected_credentials_are_not_correlation_ids(cli):
    with http_fixture() as (origin, response, _requests):
        for output in ("text", "json"):
            token = ACTOR
            for header, reflected in (
                ("X-Correlation-ID", token),
                ("X-Request-ID", token),
                ("X-Correlation-ID", token.upper()),
            ):
                response.update(
                    status=403,
                    body=b'{"error":{"code":"permission_not_granted"}}',
                    headers={"Content-Type": "application/json", header: reflected},
                )
                result = cli(origin, token, "whoami", "-o", output)
                assert result.returncode == 1 and result.stdout == ""
                assert "correlation" not in result.stderr
                # The preferred reflected header must not hide a safe fallback.
                response["headers"]["X-Correlation-ID"] = token
                response["headers"]["X-Request-ID"] = PROJECT
                fallback = cli(origin, token, "whoami", "-o", output)
                assert fallback.returncode == 1 and PROJECT in fallback.stderr


def test_supported_uuid_selectors_preserve_wire_spelling(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(CONTEXT).encode()
        for selector in (
            PROJECT.replace("-", ""),
            PROJECT.upper(),
            "{" + PROJECT + "}",
            "urn:uuid:" + PROJECT,
        ):
            result = cli(origin, TOKEN, "project", "access", selector, "-o", "json")
            assert result.returncode == 0 and json.loads(result.stdout) == CONTEXT
            assert parse_qs(urlsplit(requests[-1][1]).query) == {
                "project_id": [selector]
            }


def test_malformed_identity_responses_fail(cli):
    with http_fixture() as (origin, response, _requests):
        for body in (
            {**CONTEXT, "actor_profile_id": "not-uuid"},
            {**CONTEXT, "project_id": "not-uuid"},
            {**CONTEXT, "project_id": ACTOR},
        ):
            response["body"] = json.dumps(body).encode()
            for output in ("text", "json"):
                result = cli(origin, TOKEN, "project", "access", PROJECT, "-o", output)
                assert result.returncode == 1 and result.stdout == ""
                assert "invalid_api_response" in result.stderr

        response["body"] = json.dumps(
            {**PROFILE, "actor_profile_id": "not-uuid"}
        ).encode()
        assert_failure(
            cli(origin, TOKEN, "whoami", "-o", "json"), "invalid_api_response"
        )


def test_non_null_string_array_members_are_required(cli):
    with http_fixture() as (origin, response, _requests):
        for body in (
            *(
                {**CONTEXT, field: [None]}
                for field in ("admin_roles", "project_roles", "effective_action_ids")
            ),
            *(
                {**CONTEXT, field: ["submitter", None]}
                for field in ("admin_roles", "project_roles", "effective_action_ids")
            ),
            *(
                {**CONTEXT, field: [7]}
                for field in ("admin_roles", "project_roles", "effective_action_ids")
            ),
        ):
            response["body"] = json.dumps(body).encode()
            for output in ("text", "json"):
                result = cli(origin, TOKEN, "project", "access", PROJECT, "-o", output)
                assert result.returncode == 1 and result.stdout == ""
                assert "invalid_api_response" in result.stderr

        for field in ("domains", "admin_roles", "project_role_grants"):
            response["body"] = json.dumps({**PROFILE, field: [None]}).encode()
            assert_failure(
                cli(origin, TOKEN, "whoami", "-o", "json"), "invalid_api_response"
            )


def test_redirect_cannot_forward_the_bearer(cli):
    with http_fixture() as (origin, response, _requests):
        with http_fixture() as (destination, _unused, destination_requests):
            response.update(status=302, body=b"", headers={"Location": destination})
            assert_failure(
                cli(origin, TOKEN, "whoami", "-o", "json"), "redirect_refused"
            )
            assert destination_requests == [], "redirect target received the bearer"


def test_invalid_configuration_and_local_help_make_no_requests(cli):
    with http_fixture() as (origin, _response, requests):
        before = len(requests)
        for bad_origin in (
            "http://example.com",
            origin + "/api",
            origin + "?",
            "https://user:secret@example.com",
        ):
            assert_failure(
                cli(bad_origin, TOKEN, "whoami", "-o", "json"),
                "invalid_configuration",
                2,
            )
        for bad_token in ("", "Bearer abc", "abc\r\nInjected: true"):
            assert_failure(
                cli(origin, bad_token, "whoami", "-o", "json"),
                "invalid_configuration",
                2,
            )
        assert len(requests) == before, "invalid configuration sent a request"

        for args in (("--help",), ("--version",), ("completion", "bash")):
            result = cli("", "", *args)
            assert result.returncode == 0 and result.stdout and result.stderr == ""
        assert_failure(
            cli("", "", "-o", "json", "whoami", "--unknown", TOKEN),
            "invalid_arguments",
            2,
        )


def test_ambient_proxy_cannot_receive_a_connection(cli):
    with http_fixture() as (proxy, _unused, proxy_requests):
        result = cli(
            "https://workstream.invalid",
            TOKEN,
            "whoami",
            "-o",
            "json",
            extra_env={"HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "ALL_PROXY": proxy},
        )
        assert_failure(result, "service_unavailable")
        assert proxy_requests == [], "ambient proxy received a connection"


def test_request_timeout_is_bounded(cli):
    with http_fixture() as (origin, response, _requests):
        response.update(
            status=200,
            body=json.dumps(PROFILE).encode(),
            headers={"Content-Type": "application/json"},
            delay=13,
        )
        start = time.monotonic()
        assert_failure(
            cli(origin, TOKEN, "whoami", "-o", "json"), "service_unavailable"
        )
        assert time.monotonic() - start < 15, "CLI timeout exceeded its request bound"
