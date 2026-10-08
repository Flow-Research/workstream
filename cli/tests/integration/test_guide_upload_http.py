"""Built-process guide original transfer: bytes, custody receipt and no replay."""

import hashlib
import json
import os
from urllib.parse import quote

import pytest

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_create_http import DOCUMENT, GUIDE
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture

ORIGINAL = b"%PDF-1.7\nOriginal binary \x00\xff\n%%EOF"
MEDIA = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
)


def receipt():
    return {
        "document_id": DOCUMENT,
        "sha256": "sha256:" + hashlib.sha256(ORIGINAL).hexdigest(),
        "byte_count": len(ORIGINAL),
        "status": "document_stored",
        "replayed": False,
    }


def invoke(
    cli,
    origin,
    path,
    *,
    selectors=(PROJECT, GUIDE, DOCUMENT),
    media=MEDIA[0],
    key=KEY,
    token=TOKEN,
    output="json",
    **kwargs,
):
    return cli(
        origin,
        token,
        "-o",
        output,
        "project",
        "guide",
        "upload",
        *selectors,
        "--file",
        str(path),
        "--media-type",
        media,
        "--idempotency-key",
        key,
        **kwargs,
    )


def test_guide_upload_exact_binary_selectors_receipt_and_safe_text(cli, tmp_path):
    original = tmp_path / "not-an-inferred-filetype"
    original.write_bytes(ORIGINAL)
    with http_fixture() as (origin, response, requests):
        response.update(status=202, body=json.dumps(receipt()).encode())
        for media in MEDIA:
            for transform in (
                lambda value: value,
                lambda value: value.replace("-", ""),
                lambda value: "{" + value + "}",
                lambda value: "urn:uuid:" + value,
            ):
                selectors = tuple(map(transform, (PROJECT, GUIDE, DOCUMENT)))
                result = invoke(
                    cli,
                    origin,
                    original,
                    selectors=selectors,
                    media=media,
                    key=KEY.replace("-", ""),
                )
                assert result.returncode == 0 and result.stderr == "", result.stderr
                assert result.stdout.strip().encode() == response["body"]
                assert requests[-1] == (
                    "POST",
                    "/api/v1/projects/"
                    + quote(selectors[0], safe=":")
                    + "/guides/"
                    + quote(selectors[1], safe=":")
                    + "/documents/"
                    + quote(selectors[2], safe=":")
                    + "/content",
                    "Bearer " + TOKEN,
                )
                assert response["commands"][-1] == (
                    media,
                    [KEY.replace("-", "")],
                    ORIGINAL,
                )
                assert response["raw_commands"][-1] == ORIGINAL
                assert response["content_lengths"][-1] == str(len(ORIGINAL))
        response["body"] = json.dumps(
            receipt() | {"status": "object_confirmed", "replayed": True}
        ).encode()
        text = invoke(cli, origin, original, output="text")
        assert text.returncode == 0 and text.stderr == "", text.stderr
        assert text.stdout.startswith(
            "Guide original storage receipt (not guide approval): "
        )
        assert text.stdout.count("\n") == 1 and "\x1b" not in text.stdout
        assert all(f'"{field}"' in text.stdout for field in receipt())
        assert len(requests) == 13  # One body per invocation, no authority preflight.


def test_guide_upload_bad_local_files_and_selectors_send_nothing(cli, tmp_path):
    path = tmp_path / "private-file-canary.pdf"
    path.write_bytes(ORIGINAL)
    with http_fixture() as (origin, _response, requests):
        for kwargs in (
            {"selectors": ("../private", GUIDE, DOCUMENT)},
            {"selectors": (PROJECT, "not-uuid", DOCUMENT)},
            {"selectors": (PROJECT, GUIDE, "not-uuid")},
            {"key": ""},
            {"key": "bad"},
            {"media": ""},
            {"media": "text/plain"},
            {"media": "application/pdf\r\nX-Injected: yes"},
        ):
            assert_failure(invoke(cli, origin, path, **kwargs), "invalid_arguments", 2)
        assert_failure(
            invoke(cli, origin, tmp_path / "missing"), "invalid_arguments", 2
        )
        assert_failure(invoke(cli, origin, tmp_path), "invalid_arguments", 2)
        path.write_bytes(b"")
        assert_failure(invoke(cli, origin, path), "invalid_arguments", 2)
        # Sparse oversize file exercises the bound without allocating 512MiB.
        with path.open("wb") as file:
            file.truncate(512 * 1024 * 1024 + 1)
        assert_failure(invoke(cli, origin, path), "invalid_arguments", 2)
        fifo = tmp_path / "fifo"
        os.mkfifo(fifo)
        rejected = invoke(cli, origin, fifo)
        assert_failure(rejected, "invalid_arguments", 2)
        assert "private-file-canary" not in rejected.stderr
        assert requests == []


@pytest.mark.parametrize("change", ("append", "truncate", "overwrite_restored_mtime"))
def test_guide_upload_changed_original_never_confirms_storage(cli, tmp_path, change):
    path = tmp_path / "changed-original.pdf"
    path.write_bytes(ORIGINAL)
    original_stat = path.stat()
    mutations = []

    def mutate():
        # The server has received the original bytes, but has not sent
        # its receipt. No timing sleep or racing test thread is needed.
        if change == "append":
            with path.open("ab") as file:
                file.write(b"appended-but-not-uploaded")
        elif change == "truncate":
            with path.open("r+b") as file:
                file.truncate(len(ORIGINAL) - 1)
        else:
            path.write_bytes(b"!" + ORIGINAL[1:])
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        mutations.append(change)

    with http_fixture() as (origin, response, requests):
        response.update(status=202, body=json.dumps(receipt()).encode())
        response["after_body"] = mutate
        result = invoke(cli, origin, path)
        assert mutations == [change]
        assert response["raw_commands"] == [ORIGINAL]
        assert len(requests) == 1  # No upload retry after a source change.
        assert_failure(result, "guide_document_upload_source_changed")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert str(path) not in result.stderr


def test_guide_upload_rejects_receipt_substitution_and_unconfirmed_storage(
    cli, tmp_path
):
    path = tmp_path / "original.pdf"
    path.write_bytes(ORIGINAL)
    invalid = [b"null", b"[]", b"{}", b"{} {}", b"\xff", b"x" * (64 * 1024 + 1)]
    for field in receipt():
        invalid.append(json.dumps(receipt() | {field: None}).encode())
        absent = receipt()
        del absent[field]
        invalid.append(json.dumps(absent).encode())
    for change in (
        {"document_id": PROJECT},
        {"document_id": "not-uuid"},
        {"sha256": "sha256:" + "a" * 64},
        {"sha256": "bad"},
        {"byte_count": len(ORIGINAL) + 1},
        {"byte_count": 0},
        {"byte_count": 1.5},
        {"byte_count": True},
        {"byte_count": 2**63},
        {"status": ""},
        {"status": 7},
        {"replayed": "false"},
        {"replayed": 0},
        {"provider_url": "https://private"},
    ):
        invalid.append(json.dumps(receipt() | change).encode())
    invalid.append(
        json.dumps(receipt())
        .replace('"replayed": false', '"replayed": false, "replayed": true')
        .encode()
    )
    with http_fixture() as (origin, response, _requests):
        response["status"] = 202
        for raw in invalid:
            response["body"] = raw
            result = invoke(cli, origin, path)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        for status in (
            "pending",
            "stale",
            "conflict",
            "provider_unavailable",
            "acknowledgement_unknown",
            "missing",
            "unsafe\n\x1b[31m",
        ):
            response["body"] = json.dumps(receipt() | {"status": status}).encode()
            for output in ("json", "text"):
                result = invoke(cli, origin, path, output=output)
                assert result.returncode == 1 and result.stdout == ""
                if output == "json":
                    assert json.loads(result.stderr)["error"] == {
                        "code": "guide_document_upload_unconfirmed",
                        "status": 202,
                        "outcome_unknown": True,
                    }
                else:
                    assert (
                        "unchanged selectors, original bytes, media type and idempotency key"
                        in result.stderr
                    )
                    assert "\x1b" not in result.stderr


def test_guide_upload_denial_ambiguity_and_credential_reflections(cli, tmp_path):
    path = tmp_path / "original.pdf"
    path.write_bytes(ORIGINAL)
    with http_fixture() as (origin, response, requests):
        for status, raw, headers, unknown in (
            (404, canonical_error(), {}, False),
            (409, canonical_error("idempotency_conflict"), {}, False),
            (413, canonical_error("document_too_large"), {}, False),
            (422, canonical_error("invalid_document"), {}, False),
            (
                403,
                canonical_error()
                | {"error": canonical_error()["error"] | {"details": None}},
                {},
                True,
            ),
            (403, {"error": {"code": "denied"}}, {}, True),
            (503, canonical_error("provider_unavailable"), {}, True),
            (302, {}, {"Location": origin + "/elsewhere"}, True),
            (200, receipt(), {}, True),
            (201, receipt(), {}, True),
            (202, receipt(), {"Content-Type": "text/plain"}, True),
            (202, receipt(), {"Content-Encoding": "gzip"}, True),
        ):
            response.update(
                status=status,
                body=json.dumps(raw).encode(),
                headers={"Content-Type": "application/json"} | headers,
            )
            previous = len(requests)
            result = invoke(cli, origin, path)
            assert result.returncode == 1 and result.stdout == ""
            assert (
                json.loads(result.stderr)["error"].get("outcome_unknown", False)
                is unknown
            )
            assert len(requests) == previous + 1
        for token in ("credential_canary_AAA", KEY):
            response.update(
                status=403,
                body=json.dumps(canonical_error(token)).encode(),
                headers={"Content-Type": "application/json", "X-Correlation-ID": token},
            )
            result = invoke(cli, origin, path, token=token)
            assert result.returncode == 1 and result.stdout == ""
            assert token not in result.stderr
        response.update(drop=True)
        previous = len(requests)
        result = invoke(cli, origin, path)
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == previous + 1


def test_guide_upload_http2_goaway_never_resends_original(cli, tmp_path):
    path = tmp_path / "original.pdf"
    path.write_bytes(ORIGINAL)
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = invoke(cli, origin, path, extra_env=env)
    assert_failure(result, "service_unavailable")
    assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
    assert connections == ["h2"] and bodies == [ORIGINAL]


def test_guide_upload_uses_binary_deadline_and_disables_ambient_proxy(cli, tmp_path):
    path = tmp_path / "original.pdf"
    path.write_bytes(ORIGINAL)
    with (
        http_fixture() as (origin, response, requests),
        http_fixture() as (proxy, _response, proxy_requests),
    ):
        response.update(status=202, body=json.dumps(receipt()).encode(), delay=13)
        result = invoke(
            cli,
            origin,
            path,
            extra_env={
                "HTTP_PROXY": proxy,
                "HTTPS_PROXY": proxy,
                "ALL_PROXY": proxy,
                "NO_PROXY": "",
            },
        )
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert len(requests) == 1 and proxy_requests == []
