"""Installed guide declaration: exact JSON input, response identity and recovery."""

from copy import deepcopy
import json
import os
from urllib.parse import quote

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import (
    ACTOR,
    PROFILE,
    PROJECT,
    TOKEN,
    assert_failure,
    http_fixture,
)

GUIDE = "018f0ebc-7966-7e8d-bc4d-1cae1e000007"
SETUP = "018f0ebc-7966-7e8d-bc4d-1cae1e000008"
DOCUMENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000009"
DECLARATION = {
    "version": "guide é\n\x1b[31m",
    "task_examples": [{"content": "Evaluate this work é\n\x1b[32m"}],
    "documents": [
        {"label": "  Guide\u0085\u00a0file.pdf\u001e ", "media_type": "application/pdf"}
    ],
}


def receipt(body=DECLARATION):
    return {
        "contribution_policy_id": None,
        "contribution_policy_version_id": None,
        "activation_operation_id": None,
        "id": GUIDE,
        "project_id": PROJECT,
        "version": body["version"],
        "status": "draft",
        "change_summary": body.get("change_summary"),
        "task_examples": [
            {"title": None, "labels": [], **item} for item in body["task_examples"]
        ],
        "task_examples_hash": "sha256:" + "a" * 64,
        "approved_by": None,
        "effective_at": None,
        "created_by": ACTOR,
        "created_at": PROFILE["created_at"],
        "updated_at": PROFILE["updated_at"],
        "superseded_at": None,
        "documents": [
            {
                "document_id": DOCUMENT,
                "label": " ".join(item["label"].split()),
                "media_type": item["media_type"],
                "order": index,
            }
            for index, item in enumerate(body["documents"])
        ],
        "setup": {"id": SETUP, "status": "awaiting_documents"},
    }


def invoke(cli, origin, path, *, selector=PROJECT, key=KEY, output="json", **kwargs):
    return cli(
        origin,
        TOKEN,
        "-o",
        output,
        "project",
        "guide",
        "create",
        selector,
        "--input",
        str(path),
        "--idempotency-key",
        key,
        **kwargs,
    )


def write_input(tmp_path, body=DECLARATION):
    path = tmp_path / "guide.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_guide_create_preserves_body_selectors_defaults_and_safe_text(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        for summary in ("omit", None, "", "Changed é\n\x1b[33m"):
            body = deepcopy(DECLARATION)
            if summary != "omit":
                body["change_summary"] = summary
            body["task_examples"] += [
                {"content": "Second", "title": None, "labels": ["tag é"]}
            ]
            path = write_input(tmp_path, body)
            response.update(
                status=201, body=json.dumps(receipt(body), ensure_ascii=False).encode()
            )
            for selector in (
                PROJECT,
                PROJECT.replace("-", ""),
                "{" + PROJECT + "}",
                "urn:uuid:" + PROJECT,
            ):
                for key in (KEY, KEY.replace("-", "")):
                    result = invoke(cli, origin, path, selector=selector, key=key)
                    assert result.returncode == 0 and result.stderr == "", result.stderr
                    assert result.stdout.strip().encode() == response["body"]
                    assert response["raw_commands"][-1] == path.read_bytes()
                    assert response["commands"][-1] == ("application/json", [key], body)
                    assert requests[-1] == (
                        "POST",
                        "/api/v1/projects/" + quote(selector, safe=":") + "/guides",
                        "Bearer " + TOKEN,
                    )
            text = invoke(cli, origin, path, output="text")
            assert text.returncode == 0 and text.stderr == "", text.stderr
            assert text.stdout.startswith(
                "Guide declaration (documents still need uploading): "
            )
            for key in receipt(body):
                assert f'"{key}"' in text.stdout
            assert "\x1b" not in text.stdout and text.stdout.count("\n") == 1
        assert len(requests) == 36


def test_guide_create_accepts_markdown_document_declaration(cli, tmp_path):
    body = deepcopy(DECLARATION)
    body["documents"] = [{"label": "Guide.md", "media_type": "text/markdown"}]
    path = write_input(tmp_path, body)
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(receipt(body)).encode())

        result = invoke(cli, origin, path)

        assert result.returncode == 0 and result.stderr == ""
        assert json.loads(result.stdout)["documents"] == receipt(body)["documents"]
        assert response["commands"] == [("application/json", [KEY], body)]
        assert len(requests) == 1


def test_guide_create_input_bounds_and_large_valid_response(cli, tmp_path):
    body = deepcopy(DECLARATION)
    body["task_examples"] = [{"content": "é" * 32768}]
    path = write_input(tmp_path, body)
    raw = path.read_bytes()
    path.write_bytes(raw + b" " * (1024 * 1024 - len(raw)))
    with http_fixture() as (origin, response, requests):
        response.update(
            status=201, body=json.dumps(receipt(body), ensure_ascii=False).encode()
        )
        assert len(response["body"]) > 65536
        result = invoke(cli, origin, path)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert result.stdout.strip().encode() == response["body"]
        assert len(response["raw_commands"][0]) == 1024 * 1024
        # The per-operation response envelope accepts its exact bound, but not
        # one additional byte; unrelated command limits remain unchanged.
        response["body"] += b" " * (2 * 1024 * 1024 - len(response["body"]))
        assert invoke(cli, origin, path).returncode == 0
        response["body"] += b" "
        rejected = invoke(cli, origin, path)
        assert_failure(rejected, "invalid_api_response")
        assert json.loads(rejected.stderr)["error"]["outcome_unknown"] is True
        path.write_bytes(path.read_bytes() + b" ")
        assert_failure(invoke(cli, origin, path), "invalid_arguments", 2)
        assert len(requests) == 3


def test_guide_create_invalid_local_input_has_no_network_or_file_disclosure(
    cli, tmp_path
):
    invalid = [
        b"",
        b"null",
        b"[]",
        b"{}",
        b"{} {}",
        b'{"version":"bad\xff"}',
        b'{"version":"a","version":"b","task_examples":[],"documents":[]}',
    ]
    for field in ("version", "task_examples", "documents"):
        body = deepcopy(DECLARATION)
        body[field] = None
        invalid.append(json.dumps(body).encode())
    for update in (
        {"endpoint": "/private"},
        {"actor_id": ACTOR},
        {"task_examples": [None]},
        {"task_examples": [{"content": None}]},
        {"task_examples": [{"content": "x", "labels": [None]}]},
        {"task_examples": [{"content": "x", "labels": None}]},
        {"task_examples": [{"content": "x", "title": 42}]},
        {"task_examples": [{"content": "x", "unknown": True}]},
        {"documents": [None]},
        {"documents": [{"label": None, "media_type": "application/pdf"}]},
        {"documents": [{"label": "x", "media_type": "text/plain"}]},
        {
            "documents": [
                {
                    "label": "x",
                    "media_type": "application/pdf",
                    "url": "https://private",
                }
            ]
        },
    ):
        invalid.append(json.dumps(DECLARATION | update).encode())
    path = tmp_path / "private_input_credential_canary.json"
    with http_fixture() as (origin, _response, requests):
        for raw in invalid:
            path.write_bytes(raw)
            result = invoke(cli, origin, path)
            assert_failure(result, "invalid_arguments", 2)
            assert str(path) not in result.stdout + result.stderr
        path.write_bytes(b" " * (1024 * 1024 + 1))
        assert_failure(invoke(cli, origin, path), "invalid_arguments", 2)
        path.unlink()
        for source in (path, tmp_path):
            result = invoke(cli, origin, source)
            assert_failure(result, "invalid_arguments", 2)
            assert str(source) not in result.stderr
        fifo = tmp_path / "guide_fifo"
        os.mkfifo(fifo)
        assert_failure(invoke(cli, origin, fifo), "invalid_arguments", 2)
        path = write_input(tmp_path)
        for selector, key in (("../../private", KEY), (PROJECT, "not-a-key")):
            assert_failure(
                invoke(cli, origin, path, selector=selector, key=key),
                "invalid_arguments",
                2,
            )
        assert requests == []


def test_guide_create_rejects_malformed_substituted_or_incomplete_receipt(
    cli, tmp_path
):
    path = write_input(tmp_path)
    good = receipt()
    variants = []
    for field in (
        "id",
        "project_id",
        "version",
        "status",
        "created_by",
        "created_at",
        "updated_at",
        "documents",
        "setup",
        "task_examples",
        "task_examples_hash",
    ):
        variants.append(good | {field: None})
    for field in good:
        variants.append({key: value for key, value in good.items() if key != field})
    # Policy/activation UUIDs are optional in the public response schema.
    optional = {
        "contribution_policy_id",
        "contribution_policy_version_id",
        "activation_operation_id",
    }
    variants = [
        item
        for item in variants
        if set(good) - set(item) not in [{field} for field in optional]
    ]
    for update in (
        {"id": "bad"},
        {"project_id": ACTOR},
        {"version": "different"},
        {"status": "active"},
        {"change_summary": "different"},
        {"created_by": "bad"},
        {"created_at": "yesterday"},
        {"updated_at": "today"},
        {"task_examples_hash": "bad"},
        {"approved_by": "bad"},
        {"effective_at": "bad"},
        {"superseded_at": "bad"},
        {"contribution_policy_id": "bad"},
        {"unknown": True},
        {"task_examples": [None]},
        {"task_examples": [{"content": "different"}]},
        {
            "task_examples": [
                {
                    "content": DECLARATION["task_examples"][0]["content"],
                    "labels": [None],
                }
            ]
        },
        {
            "task_examples": [
                {"content": DECLARATION["task_examples"][0]["content"], "labels": None}
            ]
        },
        {"setup": {"id": SETUP, "status": "queued"}},
        {"setup": {"id": None, "status": "awaiting_documents"}},
        {"setup": {"id": SETUP}},
        {"documents": [None]},
    ):
        variants.append(good | update)
    for update in (
        {"document_id": "bad"},
        {"label": "different"},
        {"media_type": "text/plain"},
        {"order": None},
        {"order": 1},
        {"order": True},
        {"unknown": True},
    ):
        variants.append(good | {"documents": [good["documents"][0] | update]})
    with http_fixture() as (origin, response, requests):
        response["status"] = 201
        for value in variants:
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, path)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response["body"] = (
            json.dumps(good)
            .replace('"status": "draft"', '"status": "draft", "status": "draft"')
            .encode()
        )
        assert_failure(invoke(cli, origin, path), "invalid_api_response")
        assert len(requests) == len(variants) + 1


def test_guide_create_rejects_valid_activation_facts_on_draft(cli, tmp_path):
    path = write_input(tmp_path)
    facts = {
        "contribution_policy_id": ACTOR,
        "contribution_policy_version_id": PROJECT,
        "activation_operation_id": KEY,
        "approved_by": ACTOR,
        "effective_at": PROFILE["created_at"],
        "superseded_at": PROFILE["updated_at"],
    }
    bindings = (
        *(dict([item]) for item in facts.items()),
        {
            key: facts[key]
            for key in ("contribution_policy_id", "contribution_policy_version_id")
        },
        {
            key: facts[key]
            for key in ("contribution_policy_id", "activation_operation_id")
        },
        {
            key: facts[key]
            for key in ("contribution_policy_version_id", "activation_operation_id")
        },
        {
            key: facts[key]
            for key in (
                "contribution_policy_id",
                "contribution_policy_version_id",
                "activation_operation_id",
            )
        },
        facts,
    )
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(receipt()).encode())
        positive = invoke(cli, origin, path)
        assert positive.returncode == 0 and positive.stderr == "", positive.stderr
        for binding in bindings:
            response["body"] = json.dumps(receipt() | binding).encode()
            result = invoke(cli, origin, path)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(bindings) + 1


def test_guide_create_normalized_duplicate_document_identity_and_order(cli, tmp_path):
    body = deepcopy(DECLARATION)
    body["documents"].append(
        {
            "label": "Second.docx",
            "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    )
    path = write_input(tmp_path, body)
    good = receipt(body)
    good["documents"][1]["document_id"] = ACTOR
    with http_fixture() as (origin, response, _requests):
        response.update(status=201, body=json.dumps(good).encode())
        assert invoke(cli, origin, path).returncode == 0
        for second_id in (DOCUMENT, DOCUMENT.replace("-", "")):
            value = deepcopy(good)
            value["documents"][1]["document_id"] = second_id
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin, path), "invalid_api_response")
        value = deepcopy(good)
        value["documents"].reverse()
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin, path), "invalid_api_response")


def test_guide_create_denial_versus_uncertain_outcome(cli, tmp_path):
    path = write_input(tmp_path)
    with http_fixture() as (origin, response, requests):
        for status in (403, 404, 409, 422):
            response.update(status=status, body=json.dumps(canonical_error()).encode())
            result = invoke(cli, origin, path)
            assert_failure(result, "authorization_denied")
            assert "outcome_unknown" not in json.loads(result.stderr)["error"]
        response["body"] = json.dumps(
            canonical_error()
            | {"error": canonical_error()["error"] | {"details": None}}
        ).encode()
        result = invoke(cli, origin, path)
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response.update(status=500, body=json.dumps(canonical_error()).encode())
        assert (
            json.loads(invoke(cli, origin, path).stderr)["error"]["outcome_unknown"]
            is True
        )
        for status in (200, 202):
            response.update(status=status, body=json.dumps(receipt()).encode())
            result = invoke(cli, origin, path)
            assert result.returncode == 1 and result.stdout == ""
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response.update(status=307, headers={"Location": origin + "/private"})
        assert_failure(invoke(cli, origin, path), "redirect_refused")
        response["drop"] = True
        result = invoke(cli, origin, path, output="text")
        assert result.returncode == 1 and result.stdout == ""
        assert (
            "unchanged project, input file contents and idempotency key"
            in result.stderr
        )
        assert len(requests) == 10


def test_guide_create_http2_never_replays_a_transmitted_body(cli, tmp_path):
    path = write_input(tmp_path)
    with goaway_fixture(tmp_path) as (origin, trust, bodies, connections):
        result = invoke(cli, origin, path, extra_env=trust)
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert bodies == [path.read_bytes()]
        assert len(connections) == 1
