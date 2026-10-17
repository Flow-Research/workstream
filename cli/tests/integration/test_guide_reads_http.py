"""Built-process proof for a Project Manager's guide list, detail, readiness and original reads."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture

GUIDE = "018f0ebc-7966-7e8d-bc4d-1cae1e000020"
DOCUMENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000021"
AWAITED = "018f0ebc-7966-7e8d-bc4d-1cae1e000022"
POLICY = "018f0ebc-7966-7e8d-bc4d-1cae1e000023"
SETUP = "018f0ebc-7966-7e8d-bc4d-1cae1e000024"
WHEN = "2026-10-02T00:00:00Z"
HASH = "sha256:" + "a" * 64
ORIGINAL = "# Guide\n\nFollow the rubric. 雪\n".encode()
SUMMARY_ROW = {
    "guide_id": GUIDE,
    "version": "v1",
    "status": "draft",
    "created_at": WHEN,
    "effective_at": None,
}
RECORD = {
    "guide_id": GUIDE,
    "project_id": PROJECT,
    "version": "v1",
    "status": "draft",
    "change_summary": None,
    "task_examples_hash": HASH,
    "contribution_policy_id": None,
    "contribution_policy_version_id": None,
    "activation_operation_id": None,
    "approved_by": None,
    "created_by": "manager",
    "created_at": WHEN,
    "updated_at": WHEN,
    "effective_at": None,
    "superseded_at": None,
}
UPLOADED = {
    "document_id": DOCUMENT,
    "label": "guide.md",
    "media_type": "text/markdown",
    "order": 0,
    "ingest_state": "uploaded",
    "sha256": "sha256:" + hashlib.sha256(ORIGINAL).hexdigest(),
    "byte_count": len(ORIGINAL),
}
AWAITING = {
    "document_id": AWAITED,
    "label": "rubric.pdf",
    "media_type": "application/pdf",
    "order": 1,
    "ingest_state": "awaiting_upload",
    "sha256": None,
    "byte_count": None,
}
REVIEW = {
    "policy_id": POLICY,
    "generation": 1,
    "policy_hash": HASH,
    "human_review_required": True,
    "semantics_format": "v2",
    "semantics_status": "complete",
    "supersedes_policy_id": None,
    "review_preference_window_seconds": 3600,
    "review_lease_duration_seconds": 3600,
    "max_active_review_leases_per_reviewer": 1,
    "self_review_allowed": False,
    "reject_policy": "close_task",
    "finding_evidence_requirement": "optional",
    "allowed_decisions": ["accept", "needs_revision", "reject"],
    "minimum_finding_fields": [],
    "created_at": WHEN,
}
REVISION = {
    "policy_id": POLICY,
    "generation": 1,
    "policy_hash": HASH,
    "semantics_status": "complete",
    "supersedes_policy_id": None,
    "max_revision_rounds": 2,
    "revision_deadline_hours": 48,
    "allowed_resubmission_states": ["needs_revision"],
    "reviewer_reassignment_rule": None,
    "created_at": WHEN,
}
DETAIL = {
    "guide": RECORD,
    "documents": [UPLOADED, AWAITING],
    "review_policy": REVIEW,
    "revision_policy": REVISION,
    "latest_setup_run_id": SETUP,
    "latest_compilation_id": None,
}
CAPABILITY = {
    "requirement_id": "lint.style",
    "stage": "pre_submit",
    "title": "Style lint",
}
READINESS = {
    "project_id": PROJECT,
    "guide_id": GUIDE,
    "ready": False,
    "unmet": [
        {
            "code": "approval_blocked",
            "reason": "checker_capability_missing",
            "message": "The approved compilation still lists missing checker capabilities.",
            "missing_capabilities": [CAPABILITY],
        },
        {
            "code": "proposal_stale",
            "reason": "contribution_policy_unpublished",
            "message": "The project has no current published contribution policy version.",
            "missing_capabilities": [],
        },
    ],
}
GUIDES = f"/api/v1/projects/{PROJECT}/guides"


def _page(row, cursor=None):
    return json.dumps({"items": [row], "next_cursor": cursor}).encode()


def _json(cli, origin, *args):
    result = cli(origin, TOKEN, *args, "-o", "json")
    assert result.returncode == 0 and result.stderr == "", result.stderr
    return result


def test_guide_list_preserves_body_and_binds_filters(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = _page(SUMMARY_ROW, "next")
        result = _json(cli, origin, "project", "guide", "list", PROJECT, "--limit", "1")
        assert result.stdout.strip().encode() == response["body"]
        assert requests[-1] == ("GET", f"{GUIDES}?limit=1", "Bearer " + TOKEN)
        _json(
            cli,
            origin,
            "project",
            "guide",
            "list",
            PROJECT,
            "--status",
            "draft",
            "--cursor",
            "next",
        )
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["50"],
            "status": ["draft"],
            "cursor": ["next"],
        }
        text = cli(origin, TOKEN, "project", "guide", "list", PROJECT)
        assert text.returncode == 0, text.stderr
        assert "Status: draft\n" in text.stdout and "Next cursor: next\n" in text.stdout
        response["body"] = _page(
            SUMMARY_ROW | {"status": "active", "effective_at": WHEN}
        )
        assert_failure(
            cli(
                origin,
                TOKEN,
                "project",
                "guide",
                "list",
                PROJECT,
                "--status",
                "draft",
                "-o",
                "json",
            ),
            "invalid_api_response",
        )


def test_guide_detail_and_readiness_decode(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(DETAIL).encode()
        result = _json(cli, origin, "project", "guide", "show", PROJECT, GUIDE)
        assert json.loads(result.stdout) == DETAIL
        assert requests[-1][1] == f"{GUIDES}/{GUIDE}"
        response["body"] = json.dumps(READINESS).encode()
        result = _json(cli, origin, "project", "guide", "readiness", PROJECT, GUIDE)
        assert json.loads(result.stdout) == READINESS
        assert requests[-1][1] == f"{GUIDES}/{GUIDE}/activation-readiness"
        text = cli(origin, TOKEN, "project", "guide", "readiness", PROJECT, GUIDE)
        assert text.returncode == 0, text.stderr
        assert "Ready: false\n" in text.stdout
        assert "Unmet: approval_blocked checker_capability_missing:" in text.stdout
        assert "Missing capability: lint.style pre_submit Style lint\n" in text.stdout
        response["body"] = json.dumps(READINESS | {"ready": True, "unmet": []}).encode()
        assert (
            "Ready: true\n"
            in cli(
                origin, TOKEN, "project", "guide", "readiness", PROJECT, GUIDE
            ).stdout
        )


def test_guide_reads_reject_malformed_success(cli):
    condition = READINESS["unmet"][1]
    malformed = (
        (("list", PROJECT), _page(SUMMARY_ROW | {"status": "retired"})),
        (("list", PROJECT), _page(SUMMARY_ROW | {"extra": 1})),
        (
            ("show", PROJECT, GUIDE),
            json.dumps(DETAIL | {"guide": RECORD | {"guide_id": POLICY}}).encode(),
        ),
        (
            ("show", PROJECT, GUIDE),
            json.dumps(DETAIL | {"documents": [UPLOADED | {"sha256": None}]}).encode(),
        ),
        (
            ("show", PROJECT, GUIDE),
            json.dumps(DETAIL | {"documents": [AWAITING | {"byte_count": 9}]}).encode(),
        ),
        (
            ("show", PROJECT, GUIDE),
            json.dumps(DETAIL | {"documents": [AWAITING, UPLOADED]}).encode(),
        ),
        (
            ("show", PROJECT, GUIDE),
            json.dumps(
                DETAIL | {"review_policy": REVIEW | {"allowed_decisions": ["approve"]}}
            ).encode(),
        ),
        (
            ("show", PROJECT, GUIDE),
            json.dumps(
                DETAIL | {"guide": RECORD | {"status": "active"}, "review_policy": None}
            ).encode(),
        ),
        (
            ("readiness", PROJECT, GUIDE),
            json.dumps(READINESS | {"ready": True}).encode(),
        ),
        (
            ("readiness", PROJECT, GUIDE),
            json.dumps(READINESS | {"guide_id": POLICY}).encode(),
        ),
        (
            ("readiness", PROJECT, GUIDE),
            json.dumps(
                READINESS | {"unmet": [condition | {"code": "approval_blocked"}]}
            ).encode(),
        ),
        (
            ("readiness", PROJECT, GUIDE),
            json.dumps(
                READINESS
                | {"unmet": [condition | {"missing_capabilities": [CAPABILITY]}]}
            ).encode(),
        ),
        (
            ("readiness", PROJECT, GUIDE),
            json.dumps(
                READINESS | {"unmet": [condition | {"reason": "feeling_unready"}]}
            ).encode(),
        ),
    )
    with http_fixture() as (origin, response, _requests):
        for args, body in malformed:
            response["body"] = body
            assert_failure(
                cli(origin, TOKEN, "project", "guide", *args, "-o", "json"),
                "invalid_api_response",
            )


def test_guide_reads_refuse_invalid_arguments_before_any_request(cli, tmp_path):
    with http_fixture() as (origin, _response, requests):
        for args in (
            ("list", "not-a-uuid"),
            ("list", PROJECT, "--status", "retired"),
            ("list", PROJECT, "--limit", "0"),
            ("show", PROJECT, "not-a-uuid"),
            ("readiness", "not-a-uuid", GUIDE),
            ("document", PROJECT, GUIDE, "not-a-uuid", "--download", str(tmp_path)),
            (
                "document",
                PROJECT,
                GUIDE,
                DOCUMENT,
                "--download",
                str(tmp_path / "missing"),
            ),
        ):
            assert_failure(
                cli(origin, TOKEN, "project", "guide", *args, "-o", "json"),
                "invalid_arguments",
                2,
            )
        assert requests == []


@contextmanager
def guide_server():
    state = {
        "detail": deepcopy(DETAIL),
        "bytes": ORIGINAL,
        "headers": {"Content-Type": "text/markdown"},
    }
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - standard HTTP handler interface
            requests.append(self.path)
            if self.path.endswith("/content"):
                body, headers = state["bytes"], state["headers"]
            else:
                body, headers = (
                    json.dumps(state["detail"]).encode(),
                    {"Content-Type": "application/json"},
                )
            self.send_response(200)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_document_download_verifies_bytes_and_never_overwrites(cli, tmp_path):
    target = tmp_path / "downloads"
    target.mkdir()
    with guide_server() as (origin, state, requests):
        result = cli(
            origin,
            TOKEN,
            "project",
            "guide",
            "document",
            PROJECT,
            GUIDE,
            DOCUMENT,
            "--download",
            str(target),
        )
        assert result.returncode == 0, result.stderr
        assert (target / f"{DOCUMENT}.md").read_bytes() == ORIGINAL
        assert requests[-1] == f"{GUIDES}/{GUIDE}/documents/{DOCUMENT}/content"
        again = cli(
            origin,
            TOKEN,
            "project",
            "guide",
            "document",
            PROJECT,
            GUIDE,
            DOCUMENT,
            "--download",
            str(target),
        )
        assert (
            again.returncode != 0
            and (target / f"{DOCUMENT}.md").read_bytes() == ORIGINAL
        )

        fresh = tmp_path / "tampered"
        fresh.mkdir()
        state["bytes"] = ORIGINAL.replace(b"rubric", b"Rubric")
        assert_failure(
            cli(
                origin,
                TOKEN,
                "project",
                "guide",
                "document",
                PROJECT,
                GUIDE,
                DOCUMENT,
                "--download",
                str(fresh),
                "-o",
                "json",
            ),
            "guide_document_integrity_mismatch",
        )
        assert list(fresh.iterdir()) == []

        state["bytes"], state["headers"] = ORIGINAL, {"Content-Type": "application/pdf"}
        assert_failure(
            cli(
                origin,
                TOKEN,
                "project",
                "guide",
                "document",
                PROJECT,
                GUIDE,
                DOCUMENT,
                "--download",
                str(fresh),
                "-o",
                "json",
            ),
            "guide_document_integrity_mismatch",
        )
        count = len(requests)
        assert_failure(
            cli(
                origin,
                TOKEN,
                "project",
                "guide",
                "document",
                PROJECT,
                GUIDE,
                AWAITED,
                "--download",
                str(fresh),
                "-o",
                "json",
            ),
            "guide_document_not_uploaded",
        )
        assert len(requests) == count + 1 and not requests[-1].endswith("/content")
        assert list(fresh.iterdir()) == []
