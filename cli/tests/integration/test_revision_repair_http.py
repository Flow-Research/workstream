"""Built-process contract for one explicit manager revision-context repair."""

from copy import deepcopy
import json

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture
from test_task_context_http import REVISION_CONTEXT
from test_task_http_boundary import DETAIL, TASK

PARENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000005"
MANIFEST = REVISION_CONTEXT["source_routing_manifest_id"]
SHA = "sha256:" + "b" * 64
REASON = "Adopt the corrected approved context"


def invoke(
    cli,
    origin,
    *,
    source="parent",
    output="json",
    flags=(),
    project=PROJECT,
    task=TASK,
    key=KEY,
):
    selectors = (
        ("--parent-preparation-id", PARENT, "--parent-preparation-sha256", SHA)
        if source == "parent"
        else ("--routing-manifest-id", MANIFEST)
    )
    return cli(
        origin,
        TOKEN,
        "project",
        "task",
        "repair-revision",
        project,
        task,
        "--idempotency-key",
        key,
        "--reason",
        REASON,
        *selectors,
        *flags,
        "-o",
        output,
    )


def repaired(source="parent", *, clock="running"):
    value = deepcopy(REVISION_CONTEXT)
    value["preparation_id"] = "018f0ebc-7966-7e8d-bc4d-1cae1e000004"
    value["predecessor_preparation_id"] = PARENT if source == "parent" else None
    value["sequence"] = 2 if source == "parent" else 1
    value["outcome"] = "rebased" if source == "parent" else "kept"
    value["direction"] = "forward" if source == "parent" else "kept"
    value["changes"] = [
        {"component": "guide", "before": "old\n\x1b[31m", "after": "new"}
    ]
    if clock == "paused":
        value.update(
            deadline_at=None,
            clock_state="paused",
            remaining_microseconds=123456789,
            outcome="blocked",
            disposition="context_blocked",
            direction=None,
            target=None,
            target_reward_selection=None,
            changes=[],
        )
    return value


def test_exact_parent_and_missing_root_wire_and_clock_projection(cli):
    with http_fixture() as (origin, response, requests):
        for source, clock in (("parent", "running"), ("manifest", "paused")):
            value = repaired(source, clock=clock)
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, source=source)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == value
            assert requests[-1] == (
                "POST",
                f"/api/v1/projects/{PROJECT}/tasks/{TASK}/revision-context/repair",
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == (
                "application/json",
                [KEY],
                (
                    {"parent_preparation_id": PARENT, "parent_preparation_sha256": SHA}
                    if source == "parent"
                    else {"routing_manifest_id": MANIFEST}
                )
                | {"reason": REASON},
            )
            text = invoke(cli, origin, source=source, output="text")
            assert text.returncode == 0 and text.stderr == "", text.stderr
            assert "\x1b" not in text.stdout
            if clock == "running":
                assert "\\u001b" in text.stdout
            assert f'"clock_state":"{clock}"' in text.stdout
            assert f'"disposition":"{value["disposition"]}"' in text.stdout
        # A new subcommand must not consume the existing positional manager read.
        response["body"] = json.dumps(DETAIL).encode()
        detail = cli(origin, TOKEN, "project", "task", PROJECT, TASK, "-o", "json")
        assert detail.returncode == 0 and json.loads(detail.stdout) == DETAIL
        assert requests[-1][:2] == ("GET", f"/api/v1/projects/{PROJECT}/tasks/{TASK}")


def test_invalid_repair_inputs_send_nothing(cli):
    with http_fixture() as (origin, _, requests):
        bad = [
            ("bad", TASK, KEY, ()),
            (PROJECT, "bad", KEY, ()),
            (PROJECT, TASK, "bad", ()),
            (PROJECT, TASK, KEY, ("--routing-manifest-id", MANIFEST)),
            (PROJECT, TASK, KEY, ("--parent-preparation-sha256", "bad")),
            (PROJECT, TASK, KEY, ("--reason", " ")),
            (PROJECT, TASK, KEY, ("--reason", "é" * 501)),
        ]
        for project, task, key, flags in bad:
            assert (
                invoke(
                    cli, origin, project=project, task=task, key=key, flags=flags
                ).returncode
                == 2
            )
        for args in (
            ("--idempotency-key", KEY, "--reason", REASON),
            (
                "--idempotency-key",
                KEY,
                "--reason",
                REASON,
                "--parent-preparation-id",
                PARENT,
            ),
            (
                "--idempotency-key",
                KEY,
                "--reason",
                REASON,
                "--routing-manifest-id",
                MANIFEST,
                "--parent-preparation-id",
                PARENT,
            ),
            ("--reason", REASON, "--routing-manifest-id", MANIFEST),
        ):
            result = cli(
                origin,
                TOKEN,
                "project",
                "task",
                "repair-revision",
                PROJECT,
                TASK,
                *args,
                "-o",
                "json",
            )
            assert_failure(result, "invalid_arguments", 2)
        assert requests == []


def test_malformed_or_substituted_success_is_unknown_not_success(cli):
    with http_fixture() as (origin, response, requests):
        good = repaired()
        response["body"] = json.dumps(good).encode()
        assert invoke(cli, origin).returncode == 0
        variants = [
            good | {"predecessor_preparation_id": MANIFEST},
            good | {"preparation_id": "bad"},
            good | {"preparation_sha256": "sha256:" + "A" * 64},
            good | {"clock_state": "paused"},
            good | {"deadline_at": None},
            good | {"remaining_microseconds": 1},
            good | {"disposition": "unknown"},
            good
            | {"changes": [{"component": "guide", "before": TOKEN, "after": "new"}]},
            good | {"extra": 1},
            {k: v for k, v in good.items() if k != "direction"},
            {k: v for k, v in good.items() if k != "prior"},
        ]
        for variant in variants:
            response["body"] = json.dumps(variant).encode()
            before = len(requests)
            result = invoke(cli, origin)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert len(requests) == before + 1
        response["body"] = json.dumps(
            repaired("manifest") | {"source_routing_manifest_id": TASK}
        ).encode()
        assert_failure(invoke(cli, origin, source="manifest"), "invalid_api_response")


def test_canonical_denial_and_uncertain_write_keep_original_key(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        response.update(status=403, body=json.dumps(canonical_error()).encode())
        denied = invoke(cli, origin)
        assert_failure(denied, "authorization_denied")
        assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
        response.update(status=500, body=json.dumps(canonical_error()).encode())
        unknown = invoke(cli, origin)
        assert unknown.returncode == 1 and unknown.stdout == ""
        assert json.loads(unknown.stderr)["error"]["outcome_unknown"] is True
        text_unknown = invoke(cli, origin, output="text")
        assert text_unknown.returncode == 1 and "unchanged" in text_unknown.stderr
        assert response["commands"][-1][1] == [KEY]
        assert len(requests) == 3
    with goaway_fixture(tmp_path) as (origin, env, requests, _):
        selectors = (
            "--parent-preparation-id",
            PARENT,
            "--parent-preparation-sha256",
            SHA,
        )
        result = cli(
            origin,
            TOKEN,
            "project",
            "task",
            "repair-revision",
            PROJECT,
            TASK,
            "--idempotency-key",
            KEY,
            "--reason",
            REASON,
            *selectors,
            "-o",
            "json",
            extra_env=env,
        )
        assert result.returncode == 1 and result.stdout == ""
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 1
