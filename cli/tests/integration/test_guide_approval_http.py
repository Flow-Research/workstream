"""Built-process manager decision, exact wire custody and uncertain writes."""

import json
from urllib.parse import quote

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_create_http import GUIDE
from test_guide_proposal_http import COMPILATION, HASH, OTHER, proposal
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture


def approval():
    return {"target": proposal()["target"], "acknowledged_warning_hashes": [HASH]}


def receipt(body=None):
    body = body or approval()
    return {
        "operation_id": COMPILATION,
        "target_digest": HASH,
        "artifact_policy_id": OTHER,
        "effective_policy_id": GUIDE,
        "effective_policy_hash": HASH,
        "pre_submit_policy_id": PROJECT,
        "pre_submit_bundle_hash": HASH,
        "effective_pre_submit_plan_hash": HASH,
        "acknowledged_warning_hashes": body.get("acknowledged_warning_hashes", []),
    }


def write_input(tmp_path, body=None):
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(body or approval(), indent=2), encoding="utf-8")
    return path


def invoke(
    cli,
    origin,
    path,
    *,
    selectors=(PROJECT, GUIDE, COMPILATION),
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
        "approve-pre",
        *selectors,
        "--input",
        str(path),
        "--idempotency-key",
        key,
        **kwargs,
    )


def test_approval_exact_post_raw_input_defaults_and_uuid_identity(cli, tmp_path):
    from uuid import UUID

    with http_fixture() as (origin, response, requests):
        bodies = [approval()]
        omitted = approval()
        del omitted["acknowledged_warning_hashes"]
        bodies.append(omitted)
        bodies.append(
            omitted
            | {
                "expected_previous_approval_operation_id": None,
                "expected_previous_approval_output_digest": None,
            }
        )
        bodies.append(
            approval()
            | {
                "expected_previous_approval_operation_id": PROJECT,
                "expected_previous_approval_output_digest": HASH,
            }
        )
        bodies.append(approval())
        bodies[-1]["target"]["setup_generation"] = 9223372036854775808
        for body in bodies:
            path = write_input(tmp_path, body)
            expected = receipt(body)
            response["body"] = json.dumps(expected).encode()
            selectors = tuple(x.replace("-", "") for x in (PROJECT, GUIDE, COMPILATION))
            result = invoke(cli, origin, path, selectors=selectors)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == expected
            assert response["raw_commands"][-1] == path.read_bytes()
            assert response["commands"][-1] == ("application/json", [KEY], body)
            assert requests[-1] == (
                "POST",
                "/api/v1/projects/{}/guides/{}/compilations/{}/pre-submission-approval".format(
                    *(quote(x, safe="") for x in selectors)
                ),
                "Bearer " + TOKEN,
            )
            assert all(
                UUID(expected[k]).version == 7
                for k in (
                    "operation_id",
                    "artifact_policy_id",
                    "effective_policy_id",
                    "pre_submit_policy_id",
                )
            )
        text = invoke(cli, origin, path, output="text")
        assert (
            text.returncode == 0
            and "not post-policy approval or guide activation" in text.stdout
        )
        assert HASH in text.stdout
        assert len(requests) == len(bodies) + 1 == len(response["commands"])


def test_approval_invalid_input_never_dispatches(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        variants = [None, [], {}, {"target": None}, approval() | {"private": True}]
        for key in (
            "project_id",
            "guide_id",
            "compilation_id",
            "source_snapshot_id",
            "result_hash",
        ):
            value = approval()
            value["target"][key] = (
                OTHER if key in {"project_id", "guide_id", "compilation_id"} else "bad"
            )
            variants.append(value)
        for value in (None, [None], [HASH, HASH], ["bad"], [HASH] * 201):
            variants.append(approval() | {"acknowledged_warning_hashes": value})
        for value in (
            {"expected_previous_approval_operation_id": PROJECT},
            {"expected_previous_approval_output_digest": HASH},
            {
                "expected_previous_approval_operation_id": "bad",
                "expected_previous_approval_output_digest": HASH,
            },
            {
                "expected_previous_approval_operation_id": PROJECT,
                "expected_previous_approval_output_digest": "bad",
            },
        ):
            variants.append(approval() | value)
        path = tmp_path / "input.json"
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
            .replace('"result_hash":', '"result_hash": "bad", "result_hash":')
            .encode(),
        ):
            path.write_bytes(raw)
            assert invoke(cli, origin, path).returncode == 2
        path = write_input(tmp_path)
        for key in ("", "not-a-key"):
            assert invoke(cli, origin, path, key=key).returncode == 2
        for index in range(3):
            selectors = [PROJECT, GUIDE, COMPILATION]
            selectors[index] = "../private"
            assert invoke(cli, origin, path, selectors=selectors).returncode == 2
        assert invoke(cli, origin, tmp_path).returncode == 2
        assert requests == response["commands"] == []


def test_approval_receipt_substitution_and_closed_shape(cli, tmp_path):
    path = write_input(tmp_path)
    with http_fixture() as (origin, response, requests):
        variants = []
        for key in receipt():
            missing, null = receipt(), receipt()
            del missing[key]
            null[key] = None
            variants += [missing, null]
        for key in (
            "operation_id",
            "artifact_policy_id",
            "effective_policy_id",
            "pre_submit_policy_id",
        ):
            for invalid in (
                "not-uuid",
                "018f0ebc-7966-4e8d-bc4d-1cae1e00000a",
                "018f0ebc-7966-7e8d-1c4d-1cae1e00000a",
            ):
                variants.append(receipt() | {key: invalid})
        # All fields are valid individually; only exact selected artifact binding differs.
        variants.append(receipt() | {"artifact_policy_id": PROJECT})
        for key in (
            "target_digest",
            "effective_policy_hash",
            "pre_submit_bundle_hash",
            "effective_pre_submit_plan_hash",
        ):
            variants.append(receipt() | {key: "bad"})
        for warnings in ([None], [], ["sha256:" + "f" * 64], [HASH, HASH]):
            variants.append(receipt() | {"acknowledged_warning_hashes": warnings})
        variants.append(receipt() | {"private": "credential"})
        for value in variants:
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, path)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response["body"] = (
            json.dumps(receipt())
            .replace('"operation_id":', '"operation_id": null, "operation_id":')
            .encode()
        )
        result = invoke(cli, origin, path)
        assert_failure(result, "invalid_api_response")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(variants) + 1


def test_approval_acknowledgment_order_is_not_silently_changed(cli, tmp_path):
    body = approval()
    body["acknowledged_warning_hashes"] += ["sha256:" + "b" * 64]
    path = write_input(tmp_path, body)
    with http_fixture() as (origin, response, requests):
        expected = receipt(body)
        response["body"] = json.dumps(expected).encode()
        assert invoke(cli, origin, path).returncode == 0
        expected["acknowledged_warning_hashes"].reverse()
        response["body"] = json.dumps(expected).encode()
        result = invoke(cli, origin, path)
        assert_failure(result, "invalid_api_response")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 2


def test_approval_uncertainty_credential_metadata_and_no_retry(cli, tmp_path):
    path = write_input(tmp_path)
    with http_fixture() as (origin, response, requests):
        cases = (
            (409, canonical_error("approval_blocked"), "application/json", False),
            (404, canonical_error(), "application/json", False),
            (422, canonical_error("validation_error"), "application/json", False),
            (
                403,
                {"error": canonical_error()["error"] | {"details": None}},
                "application/json",
                True,
            ),
            (503, canonical_error(), "application/json", True),
            (403, {"error": {"code": "gateway"}}, "application/json", True),
            (302, {}, "application/json", True),
            (201, receipt(), "application/json", True),
            (200, receipt(), "text/html", True),
        )
        for status, body, content_type, unknown in cases:
            response.update(
                status=status,
                body=json.dumps(body).encode(),
                headers={
                    "Content-Type": content_type,
                    "Location": origin + "/private",
                },
            )
            result = invoke(cli, origin, path)
            assert result.returncode == 1 and result.stdout == ""
            error = json.loads(result.stderr)["error"]
            assert error.get("outcome_unknown", False) is unknown
        response.update(
            status=200, body=b" " * 65537, headers={"Content-Type": "application/json"}
        )
        assert (
            json.loads(invoke(cli, origin, path).stderr)["error"]["outcome_unknown"]
            is True
        )
        response["drop"] = True
        lost = invoke(cli, origin, path, output="text")
        assert (
            lost.returncode == 1
            and lost.stdout == ""
            and "intake approval outcome unknown" in lost.stderr
        )
        assert (
            "unchanged project, guide, compilation, input file contents and idempotency key"
            in lost.stderr
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
                result.returncode == 1 and bearer not in result.stderr + result.stdout
            )
            assert "correlation_id" not in json.loads(result.stderr)["error"]
        assert len(requests) == len(response["commands"]) == len(cases) + 4


def test_approval_post_is_not_replayed_after_http2_goaway(cli, tmp_path):
    path = write_input(tmp_path)
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = invoke(cli, origin, path, extra_env=env)
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert connections == ["h2"]
        assert bodies == [path.read_bytes()]
