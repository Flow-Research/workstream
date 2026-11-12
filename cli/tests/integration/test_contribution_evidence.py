"""Built-process evidence reads, hostile wire data and private server CSV."""

from copy import deepcopy
from contextlib import contextmanager
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
import os
import subprocess
import sys
import pytest
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

from app.modules.contributions.api.records import ContributionExportResponse
from app.modules.contributions.records.csv import contribution_csv

STAMP = "2026-10-01T00:00:00Z"


def identity(n):
    return f"018f0ebc-7966-7e8d-bc4d-{n:012x}"


def evidence():
    return {
        "exported_at": STAMP,
        "items": [
            {
                "contribution_id": identity(3),
                "project_id": PROJECT,
                "task_id": identity(4),
                "task_size": "medium",
                "submission_id": identity(5),
                "contributor_id": ACTOR,
                "contributor_display_name": "Ada",
                "contribution_type": "accepted_submission",
                "source_review_id": None,
                "source_review_lease_id": None,
                "source_final_acceptance_id": identity(6),
                "source_task_assignment_id": identity(7),
                "artifact_hash": "sha256:" + "a" * 64,
                "contribution_policy_version_id": identity(8),
                "policy_version_number": 9223372036854775808,
                "recorded_at": STAMP,
                "accepted_at": STAMP,
                "acceptance_source": "task_post_submit_route",
                "acceptance_review_id": None,
                "acceptance_routing_manifest_id": identity(9),
                "task_title": "=project\n\x1b[31m\u009b\u202e\U000e0001",
                "source_type": "research",
                "source_ref": None,
                "external_task_id": None,
                "awards": [
                    {
                        "award_id": identity(10),
                        "award_definition_id": identity(11),
                        "instrument": "money",
                        "unit": "USD",
                        "quantity": "99999999999999999999.123456789012345678",
                    },
                ],
            }
        ],
    }


def csv_bytes(value):
    return contribution_csv(
        ContributionExportResponse.model_validate_json(json.dumps(value))
    )


def api_page(value, cursor=None):
    return value | {"next_cursor": cursor}


@contextmanager
def contribution_pages(responder):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - standard HTTP handler interface
            requests.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            status, headers, body = responder(self.path)
            self.send_response(status)
            entries = headers.items() if isinstance(headers, dict) else headers
            for key, value in entries:
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def many_items(start, count):
    prototype = evidence()["items"][0]
    items = []
    for index in range(start, start + count):
        item = deepcopy(prototype)
        item.update(contribution_id=identity(index), awards=[])
        items.append(item)
    return items


def test_contributions_exact_self_project_filters_and_text(cli):
    value = evidence()
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(api_page(value), ensure_ascii=False).encode()
        for args, path in (
            (
                ("contributions", "--project", PROJECT.replace("-", "")),
                "/api/v1/actors/me/contributions",
            ),
            (
                ("project", "contributions", PROJECT.replace("-", "")),
                f"/api/v1/projects/{PROJECT.replace('-', '')}/contributions/export",
            ),
        ):
            result = cli(
                origin,
                TOKEN,
                *args,
                "--type",
                "accepted_submission",
                "--recorded-from",
                "2026-10-01T01:00:00+01:00",
                "--recorded-before",
                "2026-10-02T00:00:00Z",
                "-o",
                "json",
            )
            assert result.returncode == 0 and json.loads(result.stdout) == value, (
                result.stderr
            )
            assert all(
                control not in result.stdout
                for control in ("\u009b", "\u202e", "\U000e0001")
            )
            method, target, bearer = requests[-1]
            assert method == "GET" and bearer == "Bearer " + TOKEN
            assert urlsplit(target).path == path
            expected = {
                "format": ["json"],
                "limit": ["1000"],
                "contribution_type": ["accepted_submission"],
                "recorded_from": [STAMP],
                "recorded_before": ["2026-10-02T00:00:00Z"],
            }
            if path.startswith("/api/v1/actors"):
                expected["project_id"] = [PROJECT.replace("-", "")]
            assert parse_qs(urlsplit(target).query) == expected
        rendered = cli(origin, TOKEN, "contributions")
        assert rendered.returncode == 0 and "\x1b" not in rendered.stdout
        assert "not payment status" in rendered.stdout
        assert "99999999999999999999.123456789012345678" in rendered.stdout
        assert len(requests) == 3


def test_contributions_empty_review_and_filter_validation(cli):
    with http_fixture() as (origin, response, requests):
        for value in ({"exported_at": STAMP, "items": []}, evidence()):
            if value["items"]:
                value["items"][0].update(
                    contribution_type="completed_review", task_size=None,
                    source_review_id=identity(20),
                    source_review_lease_id=identity(21),
                    source_final_acceptance_id=None,
                    source_task_assignment_id=None,
                    accepted_at=None,
                    acceptance_source=None,
                    acceptance_routing_manifest_id=None,
                    awards=[],
                )
            response["body"] = json.dumps(api_page(value)).encode()
            result = cli(origin, TOKEN, "contributions", "-o", "json")
            assert result.returncode == 0 and json.loads(result.stdout) == value
        before = len(requests)
        for args in (
            ("--project", "../foreign"),
            ("--type", "paid"),
            ("--type", ""),
            ("--recorded-from", "2026-10-01"),
            ("--recorded-from", STAMP, "--recorded-before", STAMP),
            ("--actor", ACTOR),
            ("--csv", ""),
        ):
            result = cli(origin, TOKEN, "-o", "json", "contributions", *args)
            assert_failure(result, "invalid_arguments", 2)
        assert len(requests) == before


def test_contributions_refuse_wrong_scope_shape_lineage_and_duplicate_identity(cli):
    original = evidence()
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(api_page(original)).encode()
        control = cli(origin, TOKEN, "project", "contributions", PROJECT, "-o", "json")
        assert control.returncode == 0, control.stderr
        mutations = [
            {"project_id": identity(99)},
            {"actor_profile_id": ACTOR},
            {"contributor_id": "bad"},
            {"task_title": None},
            {"awards": None},
            {"awards": [None]},
            {"source_final_acceptance_id": None},
            {"source_review_id": identity(20)},
            {"acceptance_routing_manifest_id": None},
            {"accepted_at": "yesterday"},
            {"policy_version_number": 0},
            {"artifact_hash": "sha256:bad"},
            {"awards": [original["items"][0]["awards"][0] | {"quantity": "1e2"}]},
            {"awards": [original["items"][0]["awards"][0] | {"instrument": "project_points", "unit": "POINTS", "quantity": "1.0"}]},
        ]
        for patch in mutations:
            value = deepcopy(original)
            value["items"][0].update(patch)
            response["body"] = json.dumps(api_page(value)).encode()
            assert_failure(
                cli(origin, TOKEN, "project", "contributions", PROJECT, "-o", "json"),
                "invalid_api_response",
            )
        for field in tuple(original["items"][0]):
            value = deepcopy(original)
            del value["items"][0][field]
            response["body"] = json.dumps(api_page(value)).encode()
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )
        duplicate = deepcopy(original)
        duplicate["items"].append(deepcopy(duplicate["items"][0]))
        duplicate["items"][1]["contribution_id"] = identity(3).replace("-", "")
        duplicate["items"][1]["awards"] = []
        response["body"] = json.dumps(api_page(duplicate)).encode()
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        response["body"] = json.dumps(api_page(original)).encode()
        for flags in (
            ("--type", "completed_review"),
            ("--recorded-before", STAMP),
            ("--recorded-from", "2026-10-02T00:00:00Z"),
        ):
            assert_failure(
                cli(origin, TOKEN, "contributions", *flags, "-o", "json"),
                "invalid_api_response",
            )


def test_contribution_csv_exact_bytes_private_no_overwrite_and_symlink(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        body = csv_bytes(evidence())
        response["body"] = body
        response["headers"] = {"Content-Type": "text/csv; charset=utf-8"}
        output = tmp_path / "earned.csv"
        result = cli(
            origin,
            TOKEN,
            "project",
            "contributions",
            PROJECT,
            "--csv",
            str(output),
            "-o",
            "json",
        )
        assert result.returncode == 0 and json.loads(result.stdout) == {
            "format": "csv",
            "saved": True,
        }, result.stderr
        assert output.read_bytes() == body and output.stat().st_mode & 0o777 == 0o600
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "format": ["csv"],
            "limit": ["1000"],
        }
        assert "'=project" in output.read_text()
        for target in (output, tmp_path / "link.csv"):
            if target != output:
                target.symlink_to(output)
            result = cli(
                origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"
            )
            assert_failure(result, "invalid_arguments", 2)
            assert output.read_bytes() == body
        assert not list(tmp_path.glob(".workstream-contributions-*"))


def test_contribution_csv_reports_usage_and_real_write_failure(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        empty = cli(origin, TOKEN, "contributions", "--csv", "")
        assert empty.returncode == 2 and not empty.stdout and not requests
        assert "explicit filters and CSV path must not be empty" in empty.stderr
        response["body"] = csv_bytes(evidence())
        response["headers"] = {"Content-Type": "text/csv"}
        existing = tmp_path / "existing.csv"
        existing.write_bytes(b"keep")
        rejected = cli(origin, TOKEN, "contributions", "--csv", str(existing))
        assert rejected.returncode == 2 and not rejected.stdout
        assert "CSV destination exists or is inaccessible" in rejected.stderr
        assert existing.read_bytes() == b"keep"

        # Apply a real file-size limit in a separate launcher process, not a
        # mocked Go writer or a preexec callback in this threaded HTTP fixture.
        target = tmp_path / "limited.csv"
        launcher = (
            "import os,resource,signal,sys; "
            "signal.signal(signal.SIGXFSZ,signal.SIG_IGN); "
            "resource.setrlimit(resource.RLIMIT_FSIZE,(1,1)); "
            "os.execv(sys.argv[1],sys.argv[1:])"
        )
        for output in ("text", "json"):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    launcher,
                    os.environ["WORKSTREAM_CLI_EXECUTABLE"],
                    "contributions",
                    "--csv",
                    str(target),
                    "-o",
                    output,
                ],
                env={"WORKSTREAM_API_URL": origin, "WORKSTREAM_TOKEN": TOKEN},
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            assert result.returncode == 1 and not result.stdout, result.stderr
            assert TOKEN not in result.stderr and str(target) not in result.stderr
            if output == "json":
                assert json.loads(result.stderr)["error"]["code"] == "file_io_error"
            else:
                assert "cannot write contribution CSV" in result.stderr
            assert not target.exists()
            assert not list(tmp_path.glob(".workstream-contributions-*"))

        response["headers"] = {"Content-Type": "application/json"}
        response["body"] = json.dumps(api_page(evidence())).encode()
        staged = subprocess.run(
            [
                sys.executable,
                "-c",
                launcher,
                os.environ["WORKSTREAM_CLI_EXECUTABLE"],
                "contributions",
                "-o",
                "json",
            ],
            env={
                "WORKSTREAM_API_URL": origin,
                "WORKSTREAM_TOKEN": TOKEN,
                "TMPDIR": str(tmp_path),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        assert staged.returncode == 1 and not staged.stdout, staged.stderr
        assert json.loads(staged.stderr)["error"]["code"] == "file_io_error"
        assert TOKEN not in staged.stderr and str(tmp_path) not in staged.stderr
        assert not list(tmp_path.glob(".workstream-contributions-*"))


def test_contribution_csv_refuses_malformed_foreign_and_unsafe_rows(cli, tmp_path):
    body = csv_bytes(evidence())
    rows = list(csv.reader(StringIO(body.decode(), newline="")))
    with http_fixture() as (origin, response, _):
        response["headers"] = {"Content-Type": "text/csv"}

        def refused(content):
            response["body"] = content
            target = tmp_path / "refused.csv"
            result = cli(
                origin,
                TOKEN,
                "project",
                "contributions",
                PROJECT,
                "--csv",
                str(target),
                "-o",
                "json",
            )
            assert_failure(result, "invalid_api_response")
            assert not target.exists() and not list(
                tmp_path.glob(".workstream-contributions-*")
            )

        refused(body.replace(PROJECT.encode(), identity(99).encode()))
        refused(
            body.replace(b"' =", b"=")
            if b"' =" in body
            else body.replace(b"'=project", b"=project")
        )
        refused(body.replace(b'"quantity"', b'"extra"', 1))
        refused(body + b'"truncated')
        refused(b"\xff" + body)
        for column, value in (
            ("task_title", "different repeated fact"),
            ("award_id", identity(10).replace("-", "")),
            ("quantity", ""),
        ):
            changed = deepcopy(rows) + [deepcopy(rows[1])]
            changed[2][changed[0].index(column)] = value
            stream = StringIO(newline="")
            csv.writer(stream).writerows(changed)
            refused(stream.getvalue().encode())
        response["headers"] = {"Content-Type": "application/json"}
        refused(body)


def test_contributions_redaction_and_failure_never_publish(cli, tmp_path):
    with http_fixture() as (origin, response, _):
        for token in ("credential_canary_AAA", identity(9)):
            value = evidence()
            value["items"][0]["task_title"] = token
            response["body"] = json.dumps(api_page(value)).encode()
            assert_failure(
                cli(origin, token, "contributions", "-o", "json"),
                "invalid_api_response",
            )
            response["body"] = csv_bytes(value)
            response["headers"] = {"Content-Type": "text/csv"}
            target = tmp_path / "secret.csv"
            assert_failure(
                cli(origin, token, "contributions", "--csv", str(target), "-o", "json"),
                "invalid_api_response",
            )
            assert not target.exists()
            response["headers"] = {"Content-Type": "application/json"}
        for status, code in (
            (404, "contribution_export_not_found"),
            (422, "contribution_export_too_large"),
            (503, "contribution_export_unavailable"),
        ):
            response.update(
                status=status, body=json.dumps({"error": {"code": code}}).encode()
            )
            target = tmp_path / "failed.csv"
            result = cli(
                origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"
            )
            assert_failure(result, code)
            assert not target.exists()


@pytest.mark.parametrize("instrument,unit,quantity", [("money", "USD", "000001.2300"), ("project_points", "POINTS", "00012")])
def test_contributions_human_acceptance_and_leading_zero_quantities(cli, tmp_path, instrument, unit, quantity):
    value = evidence()
    item = value["items"][0]
    item.update(
        acceptance_source="human_review",
        acceptance_review_id=identity(40),
        acceptance_routing_manifest_id=None,
    )
    item["awards"][0].update(instrument=instrument, unit=unit, quantity=quantity)
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(api_page(value)).encode()
        result = cli(origin, TOKEN, "contributions", "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == value, (
            result.stderr
        )
        response["body"] = csv_bytes(value)
        response["headers"] = {"Content-Type": "text/csv"}
        target = tmp_path / "human.csv"
        saved = cli(origin, TOKEN, "contributions", "--csv", str(target), "-o", "json")
        assert saved.returncode == 0 and target.read_bytes() == response["body"], (
            saved.stderr
        )
        assert ('"' + quantity + '"').encode() in target.read_bytes()
        response["headers"] = {"Content-Type": "application/json"}
        for patch in (
            {"acceptance_review_id": None},
            {"acceptance_routing_manifest_id": identity(41)},
        ):
            bad = deepcopy(value)
            bad["items"][0].update(patch)
            response["body"] = json.dumps(api_page(bad)).encode()
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )


def test_contributions_json_and_csv_size_caps_reject_valid_oversized_exports(
    cli, tmp_path
):
    value = evidence()
    value["items"][0]["task_title"] = "x" * (32 * 1024 * 1024)
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(api_page(value)).encode()
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        response["headers"] = {"Content-Type": "text/csv"}
        response["body"] = csv_bytes(value)
        target = tmp_path / "oversized.csv"
        result = cli(origin, TOKEN, "contributions", "--csv", str(target), "-o", "json")
        assert_failure(result, "invalid_api_response")
        assert not target.exists() and not list(
            tmp_path.glob(".workstream-contributions-*")
        )


def test_contributions_complete_limit_order_and_unique_awards(cli, tmp_path):
    with http_fixture() as (origin, response, _):
        first = evidence()["items"][0]
        second = deepcopy(first)
        second.update(contribution_id=identity(30), awards=[])
        valid = {"exported_at": STAMP, "items": [first, second]}
        response["body"] = json.dumps(api_page(valid)).encode()
        assert cli(origin, TOKEN, "contributions", "-o", "json").returncode == 0
        for value in (
            {"exported_at": STAMP, "items": [second, first]},
            {
                "exported_at": STAMP,
                "items": [first, second | {"awards": first["awards"]}],
            },
            {"exported_at": STAMP, "items": None},
            valid | {"extra": "undocumented"},
        ):
            response["body"] = json.dumps(api_page(value)).encode()
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )
        items = [
            second | {"contribution_id": identity(100 + index)} for index in range(1000)
        ]
        response["body"] = json.dumps(
            api_page({"exported_at": STAMP, "items": items})
        ).encode()
        result = cli(origin, TOKEN, "contributions", "-o", "json")
        assert (
            result.returncode == 0 and len(json.loads(result.stdout)["items"]) == 1000
        )
        items.append(second | {"contribution_id": identity(1100)})
        response["body"] = json.dumps(
            api_page({"exported_at": STAMP, "items": items})
        ).encode()
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        response["headers"] = {"Content-Type": "text/csv; charset=utf-8"}
        for index, value in enumerate(
            (
                {"exported_at": STAMP, "items": []},
                {"exported_at": STAMP, "items": [second]},
            )
        ):
            body = csv_bytes(value)
            response["body"] = body
            target = tmp_path / f"empty-{index}.csv"
            result = cli(
                origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"
            )
            assert result.returncode == 0 and target.read_bytes() == body, result.stderr


def test_contributions_traverse_1001_json_and_csv_without_exposing_cursors(
    cli, tmp_path
):
    json_cursor = "opaque.v2~é,+"
    csv_cursor = "opaque.v2~,+"
    first_items = many_items(100, 1000)
    first_items[0]["awards"] = deepcopy(evidence()["items"][0]["awards"])
    final_item = many_items(1100, 1)[0]
    final_item["task_title"] = "later \u009b\u202e\U000e0001 page"
    final_item["awards"] = [
        {
            "award_id": identity(9000),
            "award_definition_id": identity(9001),
            "instrument": "money",
            "unit": "USD",
            "quantity": "1.2300",
        }
    ]
    first = {"exported_at": STAMP, "items": first_items}
    second = {"exported_at": "2026-10-01T00:00:01Z", "items": [final_item]}
    csv_first, csv_second = csv_bytes(first), csv_bytes(second)
    csv_second_data = csv_second[csv_second.index(b"\n") + 1 :]

    def responder(target):
        selected = parse_qs(urlsplit(target).query)
        assert selected["format"] in (["json"], ["csv"])
        cursor = csv_cursor if selected["format"] == ["csv"] else json_cursor
        assert selected == {
            "format": selected["format"],
            "limit": ["1000"],
            "project_id": [PROJECT],
            "contribution_type": ["accepted_submission"],
            "recorded_from": [STAMP],
            "recorded_before": ["2026-10-02T00:00:00Z"],
        } | ({"cursor": [cursor]} if "cursor" in selected else {})
        continuation = selected.get("cursor")
        assert continuation in (None, [cursor])
        if selected["format"] == ["csv"]:
            if continuation is None:
                return (
                    200,
                    [
                        ("Content-Type", "text/csv; charset=utf-8"),
                        ("X-Workstream-Next-Cursor", csv_cursor),
                    ],
                    csv_first,
                )
            return 200, {"Content-Type": "text/csv"}, csv_second
        value = (
            api_page(first, json_cursor) if continuation is None else api_page(second)
        )
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps(value, ensure_ascii=False).encode(),
        )

    with contribution_pages(responder) as (origin, requests):
        args = (
            "contributions",
            "--project",
            PROJECT,
            "--type",
            "accepted_submission",
            "--recorded-from",
            STAMP,
            "--recorded-before",
            "2026-10-02T00:00:00Z",
        )
        result = cli(origin, TOKEN, *args, "-o", "json")
        assert result.returncode == 0 and result.stderr == "", result.stderr
        value = json.loads(result.stdout)
        assert set(value) == {"exported_at", "items"}
        assert value["exported_at"] == STAMP
        assert [item["contribution_id"] for item in value["items"]] == [
            item["contribution_id"] for item in first_items + [final_item]
        ]
        assert len({item["contribution_id"] for item in value["items"]}) == 1001
        assert value["items"][0]["awards"] == first_items[0]["awards"]
        assert value["items"][-1]["awards"] == final_item["awards"]
        assert all(
            mark not in result.stdout for mark in ("\u009b", "\u202e", "\U000e0001")
        )
        assert "\\u202e" in result.stdout and "next_cursor" not in result.stdout

        rendered = cli(origin, TOKEN, *args)
        assert rendered.returncode == 0 and "not payment status" in rendered.stdout
        assert all(
            mark not in rendered.stdout for mark in ("\u009b", "\u202e", "\U000e0001")
        )
        assert "\\u202e" in rendered.stdout

        target = tmp_path / "complete.csv"
        saved = cli(origin, TOKEN, *args, "--csv", str(target), "-o", "json")
        assert (
            saved.returncode == 0 and target.read_bytes() == csv_first + csv_second_data
        )
        assert target.stat().st_mode & 0o777 == 0o600
        assert not list(tmp_path.glob(".workstream-contributions-*"))
        assert len(requests) == 6


def test_contributions_reject_cursor_and_cross_page_failures_without_output(
    cli, tmp_path
):
    first_items = many_items(100, 1000)
    first_items[0]["awards"] = deepcopy(evidence()["items"][0]["awards"])
    first = {"exported_at": STAMP, "items": first_items}

    terminal_without_cursor = json.dumps(first).encode()
    with contribution_pages(
        lambda _target: (
            200,
            {"Content-Type": "application/json"},
            terminal_without_cursor,
        )
    ) as (origin, _):
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )

    for bad_cursor in ("", "é" * 513):
        body = json.dumps(api_page(first, bad_cursor)).encode()
        with contribution_pages(
            lambda _target, body=body: (
                200,
                {"Content-Type": "application/json"},
                body,
            )
        ) as (origin, requests):
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )
            assert len(requests) == 1

    second_items = many_items(2000, 1000)

    def repeated_cursor(target):
        selected = parse_qs(urlsplit(target).query)
        items = first_items if "cursor" not in selected else second_items
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                api_page({"exported_at": STAMP, "items": items}, "repeat")
            ).encode(),
        )

    with contribution_pages(repeated_cursor) as (origin, requests):
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        assert len(requests) == 2

    def empty_continuation(target):
        selected = parse_qs(urlsplit(target).query)
        value = (
            first
            if "cursor" not in selected
            else {
                "exported_at": STAMP,
                "items": [],
            }
        )
        cursor = "second" if "cursor" not in selected else None
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps(api_page(value, cursor)).encode(),
        )

    with contribution_pages(empty_continuation) as (origin, requests):
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        assert len(requests) == 2

    for final_item in (
        deepcopy(first_items[0]),
        many_items(1100, 1)[0] | {"awards": [deepcopy(first_items[0]["awards"][0])]},
    ):

        def duplicate_page(target, final_item=final_item):
            selected = parse_qs(urlsplit(target).query)
            value = (
                first
                if "cursor" not in selected
                else {
                    "exported_at": STAMP,
                    "items": [final_item],
                }
            )
            cursor = "second" if "cursor" not in selected else None
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps(api_page(value, cursor)).encode(),
            )

        with contribution_pages(duplicate_page) as (origin, requests):
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )
            assert len(requests) == 2

    def denied_page(target):
        selected = parse_qs(urlsplit(target).query)
        if "cursor" not in selected:
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps(api_page(first, "denied")).encode(),
            )
        return (
            404,
            {"Content-Type": "application/json"},
            json.dumps({"error": {"code": "contribution_export_not_found"}}).encode(),
        )

    with contribution_pages(denied_page) as (origin, requests):
        result = cli(origin, TOKEN, "contributions", "-o", "json")
        assert_failure(result, "contribution_export_not_found")
        assert len(requests) == 2

    csv_first = csv_bytes(first)

    def csv_denied(target):
        selected = parse_qs(urlsplit(target).query)
        if "cursor" not in selected:
            return (
                200,
                [
                    ("Content-Type", "text/csv"),
                    ("X-Workstream-Next-Cursor", "denied"),
                ],
                csv_first,
            )
        return (
            404,
            {"Content-Type": "application/json"},
            json.dumps({"error": {"code": "contribution_export_not_found"}}).encode(),
        )

    with contribution_pages(csv_denied) as (origin, requests):
        target = tmp_path / "denied.csv"
        result = cli(origin, TOKEN, "contributions", "--csv", str(target), "-o", "json")
        assert_failure(result, "contribution_export_not_found")
        assert len(requests) == 2 and not target.exists()
        assert not list(tmp_path.glob(".workstream-contributions-*"))

    final_csv = csv_bytes({"exported_at": STAMP, "items": many_items(1100, 1)})
    changed_header = final_csv.replace(b'"contribution_id",', b"contribution_id,", 1)

    def changed_csv_header(target):
        selected = parse_qs(urlsplit(target).query)
        if "cursor" not in selected:
            return (
                200,
                [
                    ("Content-Type", "text/csv"),
                    ("X-Workstream-Next-Cursor", "second"),
                ],
                csv_first,
            )
        return 200, {"Content-Type": "text/csv"}, changed_header

    with contribution_pages(changed_csv_header) as (origin, requests):
        target = tmp_path / "changed-header.csv"
        assert_failure(
            cli(origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"),
            "invalid_api_response",
        )
        assert len(requests) == 2 and not target.exists()
        assert not list(tmp_path.glob(".workstream-contributions-*"))

    with contribution_pages(
        lambda _target: (
            200,
            [
                ("Content-Type", "text/csv"),
                ("X-Workstream-Next-Cursor", "one"),
                ("X-Workstream-Next-Cursor", "two"),
            ],
            csv_first,
        )
    ) as (origin, requests):
        target = tmp_path / "ambiguous.csv"
        assert_failure(
            cli(origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"),
            "invalid_api_response",
        )
        assert len(requests) == 1 and not target.exists()
