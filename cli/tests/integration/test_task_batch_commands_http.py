"""Built batch CLI uses separate typed calls and preserves uncertain-write recovery."""

from copy import deepcopy
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
from uuid import UUID

import pytest
from app.modules.tasks.schemas import TaskResponse
from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import ACTOR, PROJECT, TOKEN, http_fixture
from test_task_batch_sources_http import SOURCE

BATCH = "018f0ebc-7966-7e8d-bc4d-1cae1e000006"
ALTERNATE_SOURCE = "018f0ebc-7966-7e8d-bc4d-1cae1e000007"


@contextmanager
def equivalent_source_fixture(selected, read_status=200):
    """Serve distinct original import and exact selected-source read responses."""
    requests, commands = [], []
    prefix = f"/api/v1/projects/{PROJECT}"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - standard HTTP handler interface
            commands.append(
                (
                    self.headers.get_all("Idempotency-Key"),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            self.respond(201, creation())

        def do_GET(self):  # noqa: N802 - standard HTTP handler interface
            self.respond(read_status, selected)

        def respond(self, status, body):
            requests.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"http://127.0.0.1:{server.server_port}",
            requests,
            commands,
            [
                ("POST", f"{prefix}/task-import-batches", "Bearer " + TOKEN),
                (
                    "GET",
                    f"{prefix}/task-import-sources/{ALTERNATE_SOURCE}",
                    "Bearer " + TOKEN,
                ),
            ],
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def selected_source():
    return {
        "source_id": ALTERNATE_SOURCE,
        "project_id": PROJECT,
        "sha256": creation()["sha256"],
        "byte_count": creation()["byte_count"],
        "media_type": "application/json",
        "status": "verified",
        "created_at": "2026-10-11T12:00:00Z",
    }


def test_equivalent_verified_source_preserves_original_response_without_write_retry(
    cli,
):
    with equivalent_source_fixture(selected_source()) as (
        origin,
        requests,
        commands,
        expected,
    ):
        result = invoke(cli, origin, "import", target=ALTERNATE_SOURCE)
        assert result.returncode == 0 and json.loads(result.stdout) == creation(), (
            result.stderr
        )
        assert requests == expected
        assert commands == [([KEY], {"source_id": ALTERNATE_SOURCE})]


@pytest.mark.parametrize(
    "change", ["digest", "count", "unverified", "selector", "denied", "malformed"]
)
def test_post_import_source_verification_failure_stays_unknown(cli, change):
    selected, read_status = selected_source(), 200
    if change == "digest":
        selected["sha256"] = "sha256:" + "b" * 64
    elif change == "count":
        selected["byte_count"] += 1
    elif change == "unverified":
        selected["status"] = "declared"
    elif change == "selector":
        selected["source_id"] = SOURCE
    elif change == "denied":
        selected, read_status = canonical_error(), 403
    else:
        selected["provider_path"] = "private"
    with equivalent_source_fixture(selected, read_status) as (
        origin,
        requests,
        commands,
        expected,
    ):
        result = invoke(cli, origin, "import", target=ALTERNATE_SOURCE)
        assert result.returncode == 1 and result.stdout == ""
        error = json.loads(result.stderr)["error"]
        assert (
            error["code"] == "invalid_api_response" and error["outcome_unknown"] is True
        )
        assert requests == expected
        assert commands == [([KEY], {"source_id": ALTERNATE_SOURCE})]


def creation(count=2):
    """Construct public DTO-shaped HTTP fixtures; these are not native custody proof."""
    tasks = []
    for index in range(count):
        row = dict.fromkeys(TaskResponse.model_fields)
        row.update(
            id=str(UUID(int=UUID(ACTOR).int + 1000 + index)),
            project_id=PROJECT,
            task_size="small",
            external_task_id=f"brief-{index}",
            title="Caption café",
            description="Quoted\nbrief",
            skill_tags=["French"],
            source_type="json_import",
            source_ref=f"task-import-source:{SOURCE}",
            source_payload_hash="sha256:" + "a" * 64,
            import_batch_id=BATCH,
            status="draft",
            created_by=ACTOR,
            created_at="2026-10-11T12:00:00Z",
            updated_at="2026-10-11T12:00:00Z",
        )
        tasks.append(TaskResponse.model_validate(row).model_dump(mode="json"))
    return {
        "batch_id": BATCH,
        "project_id": PROJECT,
        "source_id": SOURCE,
        "sha256": "sha256:" + "a" * 64,
        "byte_count": 1000,
        "schema_version": "workstream.task_import.v1",
        "mapping_version": "workstream.task_import.draft_mapping.v1",
        "label": None,
        "row_count": count,
        "created_at": "2026-10-11T12:00:00Z",
        "tasks": tasks,
    }


def status(count=2):
    original = creation(count)
    return {
        "creation": original,
        "current_tasks": [
            {"task_id": row["id"], "row_index": index, "status": "ready"}
            for index, row in enumerate(original["tasks"])
        ],
    }


def transition(operation="screen", count=2):
    return {
        "project_id": PROJECT,
        "batch_id": BATCH,
        "operation": operation,
        "row_count": count,
        "tasks": [
            {
                "task_id": row["id"],
                "row_index": index,
                "status": "screening" if operation == "screen" else "ready",
                "locked_guide_version": "v1.0.0",
                "locked_contribution_policy_version_id": ACTOR,
                "locked_context_hash": "sha256:" + "b" * 64,
            }
            for index, row in enumerate(creation(count)["tasks"])
        ],
    }


def invoke(
    cli,
    origin,
    operation,
    *,
    project=PROJECT,
    target=None,
    key=KEY,
    reason="Decision",
    **kwargs,
):
    args = [
        "-o",
        "json",
        "project",
        "task-batch",
        operation,
        project,
        target or (SOURCE if operation == "import" else BATCH),
    ]
    if operation != "status":
        args.extend(("--idempotency-key", key))
    if operation in {"screen", "release"} and reason is not None:
        args.extend(("--reason", reason))
    return cli(origin, TOKEN, *args, **kwargs)


def test_explicit_commands_preserve_original_and_current_facts_and_exact_requests(cli):
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(creation()).encode())
        result = invoke(cli, origin, "import")
        assert result.returncode == 0 and json.loads(result.stdout) == creation(), (
            result.stderr
        )
        response.update(status=200, body=json.dumps(status()).encode())
        result = invoke(cli, origin, "status")
        assert result.returncode == 0 and json.loads(result.stdout) == status(), (
            result.stderr
        )
        for operation in ("screen", "release"):
            response.update(body=json.dumps(transition(operation)).encode())
            for _ in range(2):
                result = invoke(cli, origin, operation)
                assert result.returncode == 0 and json.loads(
                    result.stdout
                ) == transition(operation), result.stderr
        prefix = f"/api/v1/projects/{PROJECT}/task-import-batches"
        assert requests == [
            ("POST", prefix, "Bearer " + TOKEN),
            ("GET", f"{prefix}/{BATCH}", "Bearer " + TOKEN),
            *(
                ("POST", f"{prefix}/{BATCH}/{operation}", "Bearer " + TOKEN)
                for operation in ("screen", "screen", "release", "release")
            ),
        ]
        assert response["commands"] == [
            ("application/json", [KEY], {"source_id": SOURCE}),
            *[("application/json", [KEY], {"reason": "Decision"}) for _ in range(4)],
        ]


@pytest.mark.parametrize("operation", ["import", "screen", "release"])
def test_batch_write_waits_past_ordinary_deadline_without_retry(cli, operation):
    """Actual delayed headers use the scoped write budget through each public command."""
    expected = creation() if operation == "import" else transition(operation)
    with http_fixture() as (origin, response, requests):
        response.update(
            status=201 if operation == "import" else 200,
            body=json.dumps(expected).encode(),
            delay=13,
        )
        result = invoke(cli, origin, operation)
        assert result.returncode == 0 and json.loads(result.stdout) == expected, (
            result.stderr
        )
        assert len(requests) == len(response["commands"]) == 1
        assert response["commands"][0][1] == [KEY]


def test_batch_status_keeps_ordinary_deadline(cli):
    """A delayed observation remains bounded by the normal read transport."""
    with http_fixture() as (origin, response, requests):
        response.update(body=json.dumps(status()).encode(), delay=13)
        started = time.monotonic()
        result = invoke(cli, origin, "status")
        assert time.monotonic() - started < 15
        assert result.returncode == 1 and result.stdout == ""
        error = json.loads(result.stderr)["error"]
        assert error["code"] == "service_unavailable" and not error.get(
            "outcome_unknown", False
        )
        assert len(requests) == 1 and response["commands"] == []


def test_complete_500_row_original_status_and_compact_results_are_not_truncated(cli):
    with http_fixture() as (origin, response, _requests):
        for operation, body, code in (
            ("import", creation(500), 201),
            ("status", status(500), 200),
            ("screen", transition(count=500), 200),
        ):
            raw = json.dumps(body).encode()
            assert len(raw) > 64 * 1024
            response.update(status=code, body=raw)
            result = invoke(cli, origin, operation)
            assert result.returncode == 0 and json.loads(result.stdout) == body, (
                result.stderr
            )


def test_malformed_or_crossed_original_receipts_are_uncertain_imports(cli):
    values = []
    for field, value in (
        ("project_id", SOURCE),
        ("source_id", PROJECT),
        ("row_count", 3),
        ("schema_version", "other"),
    ):
        values.append(creation() | {field: value})
    for change in ("advanced", "locked", "duplicate", "source", "extra", "null"):
        value = deepcopy(creation())
        row = value["tasks"][1]
        if change == "advanced":
            row["status"] = "ready"
        elif change == "locked":
            row["locked_guide_version"] = "v1.0.0"
        elif change == "duplicate":
            row["id"] = value["tasks"][0]["id"]
        elif change == "source":
            row["source_ref"] = "task-import-source:" + PROJECT
        elif change == "extra":
            row["provider_path"] = "private"
        else:
            row["title"] = None
        values.append(value)
    with http_fixture() as (origin, response, requests):
        for value in values:
            response.update(status=201, body=json.dumps(value).encode())
            result = invoke(cli, origin, "import")
            assert result.returncode == 1 and result.stdout == "", result.stderr
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(values)


def test_malformed_complete_membership_and_current_projection_are_refused(cli):
    with http_fixture() as (origin, response, _requests):
        value = status()
        value["current_tasks"].reverse()
        response.update(body=json.dumps(value).encode())
        result = invoke(cli, origin, "status")
        assert (
            result.returncode == 1
            and "outcome_unknown" not in json.loads(result.stderr)["error"]
        )
        for change in (
            "missing",
            "duplicate",
            "reordered",
            "null_index",
            "foreign_status",
            "missing_lock",
        ):
            value = transition()
            if change == "missing":
                value["tasks"].pop()
            elif change == "duplicate":
                value["tasks"][1]["task_id"] = value["tasks"][0]["task_id"]
            elif change == "reordered":
                value["tasks"].reverse()
            elif change == "null_index":
                value["tasks"][0]["row_index"] = None
            elif change == "foreign_status":
                value["tasks"][1]["status"] = "ready"
            else:
                value["tasks"][1]["locked_context_hash"] = None
            response.update(body=json.dumps(value).encode())
            result = invoke(cli, origin, "screen")
            assert (
                result.returncode == 1
                and json.loads(result.stderr)["error"]["outcome_unknown"] is True
            )


def test_invalid_selectors_keys_and_release_reasons_make_zero_requests(cli):
    with http_fixture() as (origin, _response, requests):
        for operation in ("import", "status", "screen", "release"):
            assert invoke(cli, origin, operation, project="../private").returncode == 2
            assert invoke(cli, origin, operation, target="../private").returncode == 2
        for operation in ("import", "screen", "release"):
            assert invoke(cli, origin, operation, key="").returncode == 2
        assert invoke(cli, origin, "release", reason=None).returncode == 2
        assert invoke(cli, origin, "release", reason=" \n").returncode == 2
        for operation in ("screen", "release"):
            for count in (1001, 4001):
                assert (
                    invoke(cli, origin, operation, reason="é" * count).returncode == 2
                )
        assert requests == []


def test_uncertain_batch_writes_are_once_only_and_preserve_manual_recovery(
    cli, tmp_path
):
    with http_fixture() as (origin, response, requests):
        for operation in ("import", "screen", "release"):
            response.update(drop=True)
            result = invoke(cli, origin, operation)
            assert result.returncode == 1 and result.stdout == ""
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 3
        response.update(
            drop=False, status=403, body=json.dumps(canonical_error()).encode()
        )
        result = invoke(cli, origin, "release")
        assert "outcome_unknown" not in json.loads(result.stderr)["error"]
        response.update(body=b'{"detail":"unrecognized denial"}')
        result = invoke(cli, origin, "release")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = invoke(cli, origin, "release", extra_env=env)
    assert result.returncode == 1 and connections == ["h2"]
    assert bodies == [b'{"reason":"Decision"}']
    assert json.loads(result.stderr)["error"]["outcome_unknown"] is True


def test_original_size_formats_reject_null_and_mixed_batches(cli):
    with http_fixture() as (origin, response, requests):
        for operation in ("import", "status"):
            for change in ("new", "old", "null", "mixed", "unknown", "partial"):
                original = creation()
                original["tasks"][1]["task_size"] = "large"
                if change == "old":
                    for row in original["tasks"]:
                        row.pop("task_size")
                elif change == "null":
                    original["tasks"][0]["task_size"] = None
                elif change == "mixed":
                    original["tasks"][0].pop("task_size")
                elif change == "unknown":
                    original["tasks"][0]["task_size"] = "Small"
                elif change == "partial":
                    original["tasks"][0].pop("difficulty")
                value = original
                if operation == "status":
                    value = status() | {"creation": original}
                response.update(status=201 if operation == "import" else 200,
                                body=json.dumps(value).encode())
                result = invoke(cli, origin, operation)
                if change in {"new", "old"}:
                    assert result.returncode == 0, result.stderr
                    assert json.loads(result.stdout) == value
                else:
                    assert result.returncode == 1 and result.stdout == "", result.stderr
                    error = json.loads(result.stderr)["error"]
                    assert error["code"] == "invalid_api_response"
                    assert error.get("outcome_unknown", False) == (operation == "import")
        assert len(requests) == 12
