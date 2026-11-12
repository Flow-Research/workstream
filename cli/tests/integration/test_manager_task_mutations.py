"""Built-process contracts for deliberate public manager task preparation."""

from copy import deepcopy
import json
from urllib.parse import quote

from http2_fixture import goaway_fixture
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_contributor_task_mutations import KEY, POLICY, TASK_RESPONSE, canonical_error
from test_task_http_boundary import TASK

INPUT = {
    "title": TASK_RESPONSE["title"],
    "description": TASK_RESPONSE["description"],
    "skill_tags": TASK_RESPONSE["skill_tags"],
    "acceptance_criteria": "Complete evidence",
    "source_ref": "private-manager-source",
    "estimated_time_minutes": 17,
    "deadline_at": "2030-01-01T00:00:00Z",
}
LOCKS = {
    key: value for key, value in TASK_RESPONSE.items() if key.startswith("locked_")
} | {
    "locked_guide_source_snapshot_id": POLICY,
    "locked_guide_source_snapshot_hash": "sha256:" + "a" * 64,
    "locked_effective_project_submission_artifact_policy_id": POLICY,
    "locked_effective_project_submission_artifact_policy_hash": "sha256:" + "b" * 64,
    "locked_pre_submit_checker_policy_id": POLICY,
    "locked_pre_submit_checker_bundle_hash": "sha256:" + "c" * 64,
}


def receipt(action, payload=None):
    payload = deepcopy(INPUT if payload is None else payload)
    value = {
        k: TASK_RESPONSE[k] for k in ("id", "project_id", "created_at", "updated_at")
    }
    value.update(payload)
    value.setdefault("skill_tags", [])
    value.setdefault("source_type", "manual")
    value.update(
        created_by=ACTOR,
        status={"create": "draft", "screen": "screening", "release": "ready"}[action],
    )
    if action != "create":
        value.update(LOCKS)
    return value


def invoke(
    cli,
    origin,
    action,
    file,
    *,
    project=PROJECT,
    selector=TASK,
    key=KEY,
    token=TOKEN,
    output="json",
    flags=(),
    extra_env=None,
):
    arguments = (
        (project, "--input", str(file)) if action == "create" else (project, selector)
    )
    return cli(
        origin,
        token,
        "project",
        "task",
        action,
        *arguments,
        "--idempotency-key",
        key,
        *flags,
        "-o",
        output,
        extra_env=extra_env,
    )


def test_manager_task_exact_wire_defaults_nulls_large_body_and_text(cli, tmp_path):
    file = tmp_path / "task.json"
    with http_fixture() as (origin, response, requests):
        for action in ("create", "screen", "release"):
            response["status"] = 201 if action == "create" else 200
            response["body"] = json.dumps(receipt(action)).encode()
            wire = json.dumps(INPUT, indent=2).encode() + b"\n"
            file.write_bytes(wire)
            flags = () if action == "create" else ("--reason", "Explicit é\n")
            result = invoke(cli, origin, action, file, flags=flags)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == receipt(action)
            expected_path = (
                f"/api/v1/projects/{PROJECT}/tasks"
                if action == "create"
                else f"/api/v1/tasks/{TASK}/{action}"
            )
            assert requests[-1] == ("POST", expected_path, "Bearer " + TOKEN)
            assert response["commands"][-1] == (
                "application/json",
                [KEY],
                INPUT if action == "create" else {"reason": "Explicit é\n"},
            )
            if action == "create":
                assert response["raw_commands"][-1] == wire
            text = invoke(cli, origin, action, file, flags=flags, output="text")
            assert (
                text.returncode == 0
                and "\\n" in text.stdout
                and "\x1b" not in text.stdout
            )
            if action != "create":
                for selector in (
                    TASK.replace("-", ""),
                    "{" + TASK + "}",
                    "urn:uuid:" + TASK,
                ):
                    result = invoke(
                        cli,
                        origin,
                        action,
                        file,
                        selector=selector,
                        project=PROJECT.replace("-", ""),
                        key=KEY.replace("-", ""),
                    )
                    assert result.returncode == 0, result.stderr
                    assert (
                        requests[-1][1]
                        == f"/api/v1/tasks/{quote(selector, safe=':')}/{action}"
                    )
                    assert response["commands"][-1][1:] == ([KEY.replace("-", "")], {})
                invoke(cli, origin, action, file, flags=("--reason", ""))
                assert response["commands"][-1][-1] == {"reason": ""}
        for payload in (
            {"title": "Draft", "description": "Minimal"},
            INPUT | {"task_type": None, "rejection_criteria": None},
            INPUT
            | {"source_type": "csv_import", "import_batch_id": "client-chosen-id"},
            INPUT | {"description": "x" * 70000},
        ):
            file.write_text(json.dumps(payload))
            response.update(
                status=201, body=json.dumps(receipt("create", payload)).encode()
            )
            result = invoke(cli, origin, "create", file)
            assert result.returncode == 0, result.stderr
        response.update(
            status=200, body=json.dumps(receipt("screen", payload)).encode()
        )
        assert invoke(cli, origin, "screen", file).returncode == 0
        for action in ("screen", "release"):
            response.update(
                status=200,
                body=json.dumps(
                    receipt(action, INPUT | {"import_batch_id": "batch-text"})
                ).encode(),
            )
            assert invoke(cli, origin, action, file).returncode == 0
        for submitted, returned in (
            ("2030-01-01T02:00:00+02:00", "2030-01-01T00:00:00Z"),
            ("2030-01-01T00:00:00.123456789Z", "2030-01-01T00:00:00.123456Z"),
        ):
            payload = INPUT | {"deadline_at": submitted}
            file.write_text(json.dumps(payload))
            response.update(
                status=201,
                body=json.dumps(
                    receipt("create", payload) | {"deadline_at": returned}
                ).encode(),
            )
            assert invoke(cli, origin, "create", file).returncode == 0


def test_manager_task_invalid_input_sends_nothing(cli, tmp_path):
    file = tmp_path / "task.json"
    with http_fixture() as (origin, _, requests):
        for body in (
            b"null",
            b"[]",
            b"{}",
            b'{"title":null,"description":"x"}',
            b'{"title":"x","title":"y","description":"x"}',
            json.dumps(INPUT | {"locked_guide_version": "forged"}).encode(),
            json.dumps(INPUT | {"skill_tags": [None]}).encode(),
            json.dumps(INPUT | {"skill_tags": None}).encode(),
            json.dumps(INPUT | {"source_type": None}).encode(),
            json.dumps(INPUT | {"estimated_time_minutes": 1.5}).encode(),
            json.dumps(INPUT | {"deadline_at": "not-a-time"}).encode(),
            b" " * (1024 * 1024 + 1),
        ):
            file.write_bytes(body)
            result = invoke(cli, origin, "create", file)
            assert result.returncode == 2 and result.stdout == "", result.stderr
        file.write_text(json.dumps(INPUT))
        for action in ("create", "screen", "release"):
            for overrides in (
                {"project": "../foreign"},
                {"key": "bad"},
                {"selector": "bad"}
                if action != "create"
                else {"project": PROJECT.replace("-", "")},
            ):
                assert invoke(cli, origin, action, file, **overrides).returncode == 2
        for action in ("screen", "release"):
            assert (
                invoke(
                    cli, origin, action, file, flags=("--reason", "é" * 1001)
                ).returncode
                == 2
            )
        assert requests == []


def test_manager_task_full_response_binding_and_required_lineage(cli, tmp_path):
    file = tmp_path / "task.json"
    file.write_text(json.dumps(INPUT))
    with http_fixture() as (origin, response, requests):
        for action in ("create", "screen", "release"):
            good = receipt(action)
            response.update(
                status=201 if action == "create" else 200,
                body=json.dumps(good).encode(),
            )
            assert invoke(cli, origin, action, file).returncode == 0
            variants = [
                good | {"project_id": POLICY},
                good | {"id": "bad"},
                good | {"created_by": "bad"},
                good | {"assigned_to": ACTOR},
                good | {"status": "claimed"},
                good | {"extra": "data"},
                good | {"skill_tags": [None]},
                good | {"created_at": "bad"},
                good | {"deadline_at": "bad"},
                good | {"import_batch_id": 1},
            ]
            for key in (
                "id",
                "project_id",
                "created_by",
                "title",
                "description",
                "source_type",
                "skill_tags",
                "status",
                "created_at",
                "updated_at",
            ):
                variants.extend(
                    [{k: v for k, v in good.items() if k != key}, good | {key: None}]
                )
            if action == "create":
                for key in INPUT:
                    variants.append(
                        good
                        | {
                            key: []
                            if key == "skill_tags"
                            else (
                                18
                                if key == "estimated_time_minutes"
                                else (
                                    "2040-01-01T00:00:00Z"
                                    if key == "deadline_at"
                                    else "substituted"
                                )
                            )
                        }
                    )
                variants.append(good | {"import_batch_id": "unexpected-batch"})
                variants.append(good | {"locked_guide_version": "unexpected"})
            else:
                variants.append(good | {"id": POLICY})
                for key in LOCKS:
                    variants.extend(
                        [
                            {k: v for k, v in good.items() if k != key},
                            good | {key: None},
                            good
                            | {
                                key: 0
                                if key.endswith("generation")
                                else ("" if key == "locked_guide_version" else "bad")
                            },
                        ]
                    )
            for variant in variants:
                response["body"] = json.dumps(variant).encode()
                before = len(requests)
                result = invoke(cli, origin, action, file)
                assert_failure(result, "invalid_api_response")
                assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
                assert len(requests) == before + 1


def test_manager_task_credential_denial_uncertainty_and_one_http2_post(cli, tmp_path):
    file = tmp_path / "task.json"
    file.write_text(json.dumps(INPUT))
    with http_fixture() as (origin, response, requests):
        for action in ("create", "screen", "release"):
            success = 201 if action == "create" else 200
            response.update(status=success, body=json.dumps(receipt(action)).encode())
            assert invoke(cli, origin, action, file).returncode == 0
            response["body"] = json.dumps(
                receipt(action) | {"external_task_id": TOKEN}
            ).encode()
            if action == "create":
                file.write_text(json.dumps(INPUT | {"external_task_id": TOKEN}))
            reflected = invoke(cli, origin, action, file)
            assert_failure(reflected, "invalid_api_response")
            file.write_text(json.dumps(INPUT))
            response.update(status=403, body=json.dumps(canonical_error()).encode())
            denied = invoke(cli, origin, action, file)
            assert_failure(denied, "authorization_denied")
            assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
            for status, body in (
                (403, {"error": {"code": "denied"}}),
                (500, canonical_error()),
                (success, receipt(action) | {"status": "claimed"}),
            ):
                response.update(status=status, body=json.dumps(body).encode())
                before = len(requests)
                result = invoke(cli, origin, action, file)
                assert result.returncode == 1 and result.stdout == ""
                assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
                assert len(requests) == before + 1
            text = invoke(cli, origin, action, file, output="text")
            assert text.returncode == 1 and "unchanged" in text.stderr
    for action in ("create", "screen", "release"):
        with goaway_fixture(tmp_path) as (origin, env, requests, _):
            result = invoke(cli, origin, action, file, extra_env=env)
            assert result.returncode == 1 and result.stdout == ""
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert len(requests) == 1


def test_manager_task_sizes_bind_response_and_preserve_omitted_history(cli, tmp_path):
    file = tmp_path / "task.json"
    with http_fixture() as (origin, response, requests):
        for size in (None, "small", "medium", "large"):
            payload = INPUT if size is None else INPUT | {"task_size": size}
            file.write_text(json.dumps(payload))
            returned = receipt("create", payload) | {"task_size": size or "small"}
            response.update(status=201, body=json.dumps(returned).encode())
            result = invoke(cli, origin, "create", file)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["task_size"] == (size or "small")
            assert response["commands"][-1][-1] == payload
            response["body"] = json.dumps(returned | {"task_size": "large" if size != "large" else "small"}).encode()
            result = invoke(cli, origin, "create", file)
            assert result.returncode == 1 and result.stdout == ""
        file.write_text(json.dumps(INPUT))
        response["body"] = json.dumps(receipt("create")).encode()
        assert invoke(cli, origin, "create", file).returncode == 0
        file.write_text(json.dumps(INPUT | {"task_size": "small"}))
        result = invoke(cli, origin, "create", file)
        assert result.returncode == 1 and result.stdout == ""
        prior = len(requests)
        for size in (None, "Small", "", 3, True):
            file.write_text(json.dumps(INPUT | {"task_size": size}))
            result = invoke(cli, origin, "create", file)
            assert result.returncode == 2 and result.stdout == ""
        assert len(requests) == prior
