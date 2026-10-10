"""Built-process exact manager decisions and unconfirmed-write boundaries."""

from copy import deepcopy
import json
from urllib.parse import quote
from uuid import UUID

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_post_policy_http import LARGE, SELECTORS, package
from test_guide_proposal_http import HASH, OTHER
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture


def approval():
    return {"target": package()["target"]}


def receipt(body=None):
    return {
        "operation_id": OTHER,
        "kind": "approve",
        "target": deepcopy((body or approval())["target"]),
        "correction": None,
    }


def write_input(tmp_path, body=None):
    path = tmp_path / "post-approval.json"
    path.write_text(json.dumps(body or approval(), indent=2), encoding="utf-8")
    return path


def invoke(
    cli,
    origin,
    path,
    *,
    selectors=SELECTORS,
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
        "approve-post",
        *selectors,
        "--input",
        str(path),
        "--idempotency-key",
        key,
        **kwargs,
    )


def unknown(result, code="invalid_api_response"):
    assert_failure(result, code)
    assert json.loads(result.stderr)["error"]["outcome_unknown"] is True


def test_post_approval_exact_wire_and_uuid_identity(cli, tmp_path):
    body = approval()
    body["target"]["proposal"]["setup_generation"] = LARGE
    body["target"]["proposal"]["guide_version"] = "Guide\x1b[31m\nversion"
    body["target"]["predecessor_policy_id"] = PROJECT
    path = write_input(tmp_path, body)
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(receipt(body)).encode()
        for selectors, key in (
            (SELECTORS, KEY),
            (tuple(UUID(x).hex for x in SELECTORS), UUID(KEY).hex),
        ):
            result = invoke(cli, origin, path, selectors=selectors, key=key)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == receipt(body)
            assert requests[-1] == (
                "POST",
                "/api/v1/projects/{}/guides/{}/compilations/{}/post-submission-policies/{}/approval".format(
                    *(quote(x, safe="") for x in selectors)
                ),
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == ("application/json", [key], body)
            assert response["raw_commands"][-1] == path.read_bytes()
        # Distinct UUID text in the response is still the same resource identity.
        equivalent = receipt(body)
        equivalent["target"]["policy_id"] = UUID(SELECTORS[-1]).hex
        equivalent["target"]["upstream"]["operation_id"] = UUID(
            equivalent["target"]["upstream"]["operation_id"]
        ).hex
        equivalent["target"]["predecessor_policy_id"] = UUID(PROJECT).hex
        response["body"] = json.dumps(equivalent).encode()
        assert invoke(cli, origin, path).returncode == 0
        result = invoke(cli, origin, path, output="text")
        assert result.returncode == 0 and result.stderr == ""
        assert "not guide activation" in result.stdout and "\x1b" not in result.stdout
        assert "\\u001b" in result.stdout
        assert len(requests) == len(response["commands"]) == 4


def test_post_approval_invalid_input_is_local(cli, tmp_path):
    path = write_input(tmp_path)
    variants = [{}, {"target": None}, approval() | {"kind": "approve"}]
    for field in approval()["target"]:
        if field == "predecessor_policy_id":
            continue  # Public schema default is null, not a required selector.
        for value in (None, "invalid"):
            body = approval()
            body["target"][field] = value
            variants.append(body)
    for index, field in enumerate(("project_id", "guide_id", "compilation_id")):
        body = approval()
        body["target"]["proposal"][field] = OTHER
        assert body["target"]["proposal"][field] != SELECTORS[index]
        variants.append(body)
    body = approval()
    body["target"]["policy_id"] = OTHER
    variants.append(body)
    body = approval()
    body["target"]["upstream"]["artifact_policy_id"] = PROJECT
    variants.append(body)
    with http_fixture() as (origin, response, requests):
        for body in variants:
            path.write_text(json.dumps(body), encoding="utf-8")
            result = invoke(cli, origin, path)
            assert result.returncode == 2 and result.stdout == "", result.stderr
        for raw in (
            b"",
            b"[",
            b" " * (1024 * 1024 + 1),
            json.dumps(approval())
            .replace('"target":', '"target": {}, "target":')
            .encode(),
            json.dumps(approval())
            .replace('"policy_hash":', '"policy_hash": "bad", "policy_hash":')
            .encode(),
        ):
            path.write_bytes(raw)
            assert invoke(cli, origin, path).returncode == 2
        path = write_input(tmp_path)
        for index in range(4):
            invalid = list(SELECTORS)
            invalid[index] = "../private"
            assert invoke(cli, origin, path, selectors=invalid).returncode == 2
        for key in ("", "bad"):
            assert invoke(cli, origin, path, key=key).returncode == 2
        assert invoke(cli, origin, tmp_path).returncode == 2
        assert response["commands"] == requests == []


def test_post_approval_policy_hash_substitution_is_unknown(cli, tmp_path):
    path = write_input(tmp_path)
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(receipt()).encode()
        assert invoke(cli, origin, path).returncode == 0
        substituted = receipt()
        substituted["target"]["policy_hash"] = "sha256:" + "f" * 64
        response["body"] = json.dumps(substituted).encode()
        unknown(invoke(cli, origin, path))
        assert len(requests) == 2


def test_post_approval_malformed_or_substituted_receipt_is_unknown(cli, tmp_path):
    body = approval()
    body["target"]["upstream"]["acknowledged_warning_hashes"] = [
        HASH,
        "sha256:" + "b" * 64,
    ]
    path = write_input(tmp_path, body)
    variants = []
    for field in receipt(body):
        missing = receipt(body)
        del missing[field]
        variants.append(missing)
        if field != "correction":
            variants.append(receipt(body) | {field: None})
    for operation in (
        "bad",
        "018f0ebc-7966-4e8d-bc4d-1cae1e00000a",
        "018f0ebc-7966-7e8d-1c4d-1cae1e00000a",
    ):
        variants.append(receipt(body) | {"operation_id": operation})
    variants += [
        receipt(body) | {"kind": "derive"},
        receipt(body) | {"correction": {}},
        receipt(body) | {"private": "unexpected"},
    ]
    for field in (
        "policy_id",
        "projection_operation_id",
        "predecessor_policy_id",
        "upstream_output_digest",
    ):
        changed = receipt(body)
        changed["target"][field] = (
            PROJECT if field != "upstream_output_digest" else "sha256:" + "f" * 64
        )
        variants.append(changed)
    for field, original in body["target"]["proposal"].items():
        if field == "component_hashes":
            for component in original:
                changed = receipt(body)
                changed["target"]["proposal"][field][component] = "sha256:" + "f" * 64
                variants.append(changed)
            continue
        if original is None:
            continue
        changed = receipt(body)
        if field.endswith("_id"):
            value = PROJECT if original != PROJECT else OTHER
        elif field == "setup_generation":
            value = original + 1
        elif "hash" in field or "digest" in field:
            value = "sha256:" + "f" * 64
        else:
            value = "different"
        changed["target"]["proposal"][field] = value
        variants.append(changed)
    for field, original in body["target"]["upstream"].items():
        changed = receipt(body)
        changed["target"]["upstream"][field] = (
            list(reversed(original))
            if isinstance(original, list)
            else (PROJECT if original != PROJECT else OTHER)
            if field.endswith("_id")
            else "sha256:" + "f" * 64
        )
        variants.append(changed)
    with http_fixture() as (origin, response, requests):
        for changed in variants:
            response["body"] = json.dumps(changed).encode()
            unknown(invoke(cli, origin, path))
        response["body"] = (
            json.dumps(receipt(body))
            .replace('"kind":', '"kind": null, "kind":')
            .encode()
        )
        unknown(invoke(cli, origin, path))
        assert len(requests) == len(variants) + 1


def test_post_approval_denial_and_transport_uncertainty(cli, tmp_path):
    path = write_input(tmp_path)
    with http_fixture() as (origin, response, requests):
        cases = [
            (404, canonical_error(), False),
            (409, canonical_error("proposal_stale"), False),
            (422, canonical_error("validation_error"), False),
            (503, canonical_error(), True),
            (403, {"error": canonical_error()["error"] | {"details": None}}, True),
            (403, {"error": {"code": "gateway"}}, True),
            (302, {}, True),
            (201, receipt(), True),
        ]
        for status, body, ambiguous in cases:
            response.update(
                status=status,
                body=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Location": origin + "/private",
                },
            )
            result = invoke(cli, origin, path)
            assert result.returncode == 1 and result.stdout == ""
            assert (
                json.loads(result.stderr)["error"].get("outcome_unknown", False)
                is ambiguous
            )
        response.update(status=200, body=b" " * 65537)
        unknown(invoke(cli, origin, path))
        response.update(
            body=json.dumps(receipt()).encode(), headers={"Content-Type": "text/html"}
        )
        unknown(invoke(cli, origin, path))
        bearer = "018f0ebc-7966-7e8d-bc4d-1cae1e00000f"
        response.update(
            body=json.dumps(receipt() | {"operation_id": bearer}).encode(),
            headers={"Content-Type": "application/json"},
        )
        unknown(invoke(cli, origin, path, token=bearer))
        response["drop"] = True
        result = invoke(cli, origin, path, output="text")
        assert result.returncode == 1 and result.stdout == ""
        assert "post-submission approval outcome unknown" in result.stderr
        assert (
            "unchanged project, guide, compilation, policy, input file contents and idempotency key"
            in result.stderr
        )
        response["drop"] = False
        for bearer in ("credential_canary_AAA", PROJECT):
            response.update(
                status=403,
                body=json.dumps(canonical_error(bearer)).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Correlation-ID": bearer,
                },
            )
            result = invoke(cli, origin, path, token=bearer)
            assert (
                result.returncode == 1 and bearer not in result.stdout + result.stderr
            )
            assert "correlation_id" not in json.loads(result.stderr)["error"]
        assert len(requests) == len(response["commands"]) == len(cases) + 6
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        unknown(invoke(cli, origin, path, extra_env=env), "service_unavailable")
        assert connections == ["h2"] and bodies == [path.read_bytes()]
