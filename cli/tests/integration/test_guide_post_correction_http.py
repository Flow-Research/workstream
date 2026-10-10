"""Built process proof of exact correction writes and unconfirmed outcomes."""

from copy import deepcopy
import json
from uuid import UUID

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_post_approval_http import approval, unknown
from test_guide_post_policy_http import LARGE, SELECTORS
from test_guide_proposal_http import HASH, OTHER
from test_http_boundary import PROJECT, TOKEN, http_fixture


def correction_input():
    return approval() | {"reason": "Clarify evidence for the evaluation."}


def receipt(body=None):
    target = deepcopy((body or correction_input())["target"])
    return {
        "operation_id": OTHER,
        "kind": "correction",
        "target": target,
        "correction": {
            "operation_id": OTHER,
            "target_digest": target["upstream"]["target_digest"],
            "successor_setup_run_id": PROJECT,
            "successor_setup_generation": target["proposal"]["setup_generation"] + 1,
            "feedback_hash": HASH,
            "status": "correction_requested",
        },
    }


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
        "correct-post",
        *selectors,
        "--input",
        str(path),
        "--idempotency-key",
        key,
        **kwargs,
    )


def test_post_correction_wire_and_invalid_input(cli, tmp_path):
    body = correction_input()
    body["target"]["proposal"]["setup_generation"] = LARGE
    body["target"]["proposal"]["guide_version"] = "Guide\x1b[31m"
    body["reason"] = "  Reconsider café\nwith evidence\tplease  "
    path = tmp_path / "correction.json"
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(receipt(body)).encode())
        for selectors in (SELECTORS, tuple(UUID(x).hex for x in SELECTORS)):
            result = invoke(cli, origin, path, selectors=selectors)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == receipt(body)
            assert requests[-1] == (
                "POST",
                "/api/v1/projects/{}/guides/{}/compilations/{}/post-submission-policies/{}/corrections".format(
                    *selectors
                ),
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == ("application/json", [KEY], body)
            assert response["raw_commands"][-1] == path.read_bytes()
        result = invoke(cli, origin, path, output="text")
        assert result.returncode == 0 and "not dispatched" in result.stdout
        assert "\x1b" not in result.stdout and "\\u001b" in result.stdout
        variants = [{}, body | {"unknown": True}, body | {"target": None}]
        variants += [body | {"reason": reason} for reason in (None, 1, "", "a" * 4001)]
        for index, field in enumerate(("project_id", "guide_id", "compilation_id")):
            changed = deepcopy(body)
            changed["target"]["proposal"][field] = OTHER
            assert OTHER != SELECTORS[index]
            variants.append(changed)
        changed = deepcopy(body)
        changed["target"]["policy_id"] = OTHER
        variants.append(changed)
        for changed in variants:
            path.write_text(json.dumps(changed), encoding="utf-8")
            assert invoke(cli, origin, path).returncode == 2
        for raw in (
            b"",
            b"[",
            b" " * (1024 * 1024 + 1),
            json.dumps(body).replace('"reason":', '"reason": null, "reason":').encode(),
        ):
            path.write_bytes(raw)
            assert invoke(cli, origin, path).returncode == 2
        path.write_text(json.dumps(body), encoding="utf-8")
        assert invoke(cli, origin, path, key="invalid").returncode == 2
        assert invoke(cli, origin, tmp_path).returncode == 2
        for index in range(4):
            selectors = list(SELECTORS)
            selectors[index] = "../private"
            assert invoke(cli, origin, path, selectors=selectors).returncode == 2
        assert len(requests) == 3


def test_post_correction_receipt_binding(cli, tmp_path):
    body = correction_input()
    path = tmp_path / "correction.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(receipt()).encode())
        assert invoke(cli, origin, path).returncode == 0
        # Otherwise valid receipt: the mutant without exact target equality
        # must fail at the rejection assertion, after the successful control.
        changed = receipt()
        changed["target"]["policy_hash"] = "sha256:" + "f" * 64
        response["body"] = json.dumps(changed).encode()
        unknown(invoke(cli, origin, path))
        variants = [
            receipt() | {"kind": "approve"},
            receipt() | {"correction": None},
            receipt() | {"unknown": True},
        ]
        for field in receipt():
            changed = receipt()
            del changed[field]
            variants.append(changed)
        for field, values in {
            "operation_id": ("bad", "018f0ebc-7966-4e8d-bc4d-1cae1e00000a"),
            "target_digest": ("sha256:" + "f" * 64,),
            "successor_setup_run_id": ("bad", None),
            "successor_setup_generation": (
                None,
                0,
                True,
                "2",
                body["target"]["proposal"]["setup_generation"] + 2,
            ),
            "feedback_hash": ("bad", None),
            "status": ("queued", None),
        }.items():
            for value in values:
                changed = receipt()
                changed["correction"][field] = value
                variants.append(changed)
        for changed in variants:
            response["body"] = json.dumps(changed).encode()
            unknown(invoke(cli, origin, path))
        changed = receipt()
        changed["correction"]["unknown"] = True
        response["body"] = json.dumps(changed).encode()
        unknown(invoke(cli, origin, path))
        equivalent = receipt()
        equivalent["target"]["policy_id"] = UUID(SELECTORS[-1]).hex
        equivalent["correction"]["successor_setup_run_id"] = UUID(PROJECT).hex
        # The backend schema supplies this public default when status is omitted.
        del equivalent["correction"]["status"]
        response["body"] = json.dumps(equivalent).encode()
        assert invoke(cli, origin, path).returncode == 0
        assert len(requests) == len(variants) + 4


def test_post_correction_transport_and_credentials(cli, tmp_path):
    path = tmp_path / "correction.json"
    path.write_text(json.dumps(correction_input()), encoding="utf-8")
    with http_fixture() as (origin, response, requests):
        for status, body, ambiguous in (
            (404, canonical_error(), False),
            (409, canonical_error("operation_conflict"), False),
            (422, canonical_error("validation_error"), False),
            (503, canonical_error(), True),
            (403, {"error": canonical_error()["error"] | {"details": None}}, True),
            (302, {}, True),
            (200, receipt(), True),
        ):
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
        response.update(status=201, body=b" " * 65537)
        unknown(invoke(cli, origin, path))
        response.update(
            body=json.dumps(receipt()).encode(), headers={"Content-Type": "text/html"}
        )
        unknown(invoke(cli, origin, path))
        for location in ("outer", "operation_id", "successor_setup_run_id"):
            reflected = receipt()
            bearer = "018f0ebc-7966-7e8d-bc4d-1cae1e00000f"
            if location == "outer":
                reflected["operation_id"] = bearer
            else:
                reflected["correction"][location] = bearer
            response.update(
                body=json.dumps(reflected).encode(),
                headers={"Content-Type": "application/json"},
            )
            unknown(invoke(cli, origin, path, token=bearer))
            unknown(invoke(cli, origin, path, token=UUID(bearer).hex))
        response["drop"] = True
        result = invoke(cli, origin, path, output="text")
        assert result.returncode == 1 and result.stdout == ""
        assert "post-submission correction outcome unknown" in result.stderr
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
            assert result.returncode == 1 and result.stdout == ""
            assert (
                bearer not in result.stderr
                and "correlation_id" not in json.loads(result.stderr)["error"]
            )
        assert len(requests) == 18
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        unknown(invoke(cli, origin, path, extra_env=env), "service_unavailable")
        assert connections == ["h2"] and bodies == [path.read_bytes()]
