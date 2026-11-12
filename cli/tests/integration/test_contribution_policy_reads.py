"""Built-binary public Finance reads and hostile wire response regressions."""

from copy import deepcopy
import json
from urllib.parse import parse_qs, quote, urlsplit

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_contributor_task_mutations import KEY, POLICY, canonical_error

VERSION = "018f0ebc-7966-7e8d-bc4d-1cae1e000077"


def selection(published=VERSION, draft=None):
    return {
        "project_id": PROJECT,
        "contribution_policy_id": POLICY,
        "current_published_version_id": published,
        "open_draft_version_id": draft,
    }


def policy(*, empty=False, compensated=False):
    rules = []
    if not empty:
        for kind, identifier in (
            ("accepted_submission", ACTOR),
            ("completed_review", KEY),
        ):
            rules.append(
                {
                    "rule_id": identifier,
                    "contribution_type": kind,
                    "compensation_mode": "unpaid",
                    "definitions": [],
                }
            )
    if compensated:
        rules[0].update(
            compensation_mode="compensated",
            definitions=[
                {
                    "reward_model_version": 1,
                    "task_size": None,
                    "definition_id": PROJECT,
                    "instrument_type": "money",
                    "unit_code": "USD",
                    "quantity": "99999999999999999999.123456789012345678",
                    "adapter_binding_id": KEY,
                },
                {
                    "reward_model_version": 1,
                    "task_size": None,
                    "definition_id": VERSION,
                    "instrument_type": "project_points",
                    "unit_code": "research_points",
                    "quantity": "9007199254740993",
                    "adapter_binding_id": ACTOR,
                },
            ],
        )
    return {
        "project_id": PROJECT,
        "contribution_policy_id": POLICY,
        "name": "Governed project policy",
        "policy_status": "draft" if empty else "active",
        "contribution_policy_version_id": VERSION,
        "version_number": 1,
        "reward_model_version": 1,
        "instrument_type": None,
        "unit_code": None,
        "adapter_binding_id": None,
        "version_status": "draft" if empty else "published",
        "rules": rules,
    }


def invoke(
    cli,
    origin,
    action,
    *flags,
    project=PROJECT,
    selected=POLICY,
    output="json",
    token=TOKEN,
):
    selectors = (project,) if action == "current" else (project, selected)
    return cli(
        origin,
        token,
        "project",
        "contribution-policy",
        action,
        *selectors,
        *flags,
        "-o",
        output,
    )


def test_policy_reads_exact_wire_selection_history_and_complete_text(cli):
    with http_fixture() as (origin, response, requests):
        for value in (selection(None, VERSION), selection(), selection(VERSION, KEY)):
            response["body"] = json.dumps(value).encode()
            for spelling in (
                PROJECT,
                PROJECT.replace("-", ""),
                "{" + PROJECT + "}",
                "urn:uuid:" + PROJECT,
            ):
                before = len(requests)
                result = invoke(cli, origin, "current", project=spelling)
                assert result.returncode == 0 and json.loads(result.stdout) == value, (
                    result.stderr
                )
                assert len(requests) == before + 1
                assert requests[-1] == (
                    "GET",
                    f"/api/v1/projects/{quote(spelling, safe=':')}/contribution-policies/current",
                    "Bearer " + TOKEN,
                )
            text = invoke(cli, origin, "current", output="text")
            assert (
                text.returncode == 0
                and json.loads(
                    text.stdout.removeprefix("Current selectors (not authority): ")
                )
                == value
            )
        for value in (
            policy(empty=True),
            policy(),
            policy(compensated=True),
            policy() | {"policy_status": "retired", "version_status": "retired"},
            policy(empty=True) | {"policy_status": "active"},
            policy() | {"version_status": "retired"},
            policy() | {"version_number": 2**100},
        ):
            response["body"] = json.dumps(value).encode()
            for flags in ((), ("--version", VERSION.replace("-", ""))):
                before = len(requests)
                result = invoke(
                    cli,
                    origin,
                    "show",
                    *flags,
                    project=PROJECT.replace("-", ""),
                    selected=POLICY.replace("-", ""),
                )
                assert result.returncode == 0 and result.stderr == "", result.stderr
                assert json.loads(result.stdout) == value
                assert len(requests) == before + 1
                path = urlsplit(requests[-1][1])
                assert (
                    path.path
                    == f"/api/v1/projects/{PROJECT.replace('-', '')}/contribution-policies/{POLICY.replace('-', '')}"
                )
                assert parse_qs(path.query) == (
                    {"version_id": [VERSION.replace("-", "")]} if flags else {}
                )
            text = invoke(cli, origin, "show", output="text")
            assert (
                text.returncode == 0
                and json.loads(
                    text.stdout.removeprefix(
                        "Contribution policy (not authority or readiness): "
                    )
                )
                == value
            )
        value = policy() | {"name": "Guide \u202e\u001b[31m policy"}
        response["body"] = json.dumps(value).encode()
        text = invoke(cli, origin, "show", output="text")
        assert (
            text.returncode == 0
            and "\u202e" not in text.stdout
            and "\u001b" not in text.stdout
        )
        assert (
            json.loads(
                text.stdout.removeprefix(
                    "Contribution policy (not authority or readiness): "
                )
            )
            == value
        )


def test_policy_invalid_selectors_send_no_request_and_current_relations_fail(cli):
    with http_fixture() as (origin, response, requests):
        for action in ("current", "show"):
            assert invoke(cli, origin, action, project="../foreign").returncode == 2
        assert invoke(cli, origin, "show", selected="bad").returncode == 2
        for version in ("", "bad", "../other"):
            result = invoke(cli, origin, "show", "--version", version)
            assert result.returncode == 2 and result.stdout == ""
        assert requests == []
        good = selection()
        response["body"] = json.dumps(good).encode()
        assert invoke(cli, origin, "current").returncode == 0
        invalid = [
            selection(None, None),
            selection(VERSION, VERSION.replace("-", "")),
            good | {"project_id": ACTOR},
            good | {"contribution_policy_id": "bad"},
            good | {"current_published_version_id": "bad"},
            good | {"open_draft_version_id": "bad"},
            good | {"extra": 1},
        ]
        for key in good:
            invalid.append({k: v for k, v in good.items() if k != key})
            if key in ("project_id", "contribution_policy_id"):
                invalid.append(good | {key: None})
        for value in invalid:
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin, "current"), "invalid_api_response")


def test_policy_view_binds_full_nested_facts_and_normalized_identities(cli):
    good = policy(compensated=True)
    invalid = [
        good | {"project_id": ACTOR},
        good | {"contribution_policy_id": KEY},
        good | {"contribution_policy_version_id": KEY},
        good | {"policy_status": "ready"},
        good | {"version_status": "active"},
        good | {"version_number": 0},
        good | {"version_number": -1},
        good | {"version_number": 1.5},
        good | {"version_number": "1"},
        good | {"name": " "},
        good | {"private": 1},
        good | {"rules": [None]},
    ]
    for key in good:
        invalid.append({k: v for k, v in good.items() if k != key})
        if good[key] is not None:
            invalid.append(good | {key: None})
    for key in good["rules"][0]:
        for value in (None, "unknown" if key != "definitions" else [None]):
            altered = deepcopy(good)
            altered["rules"][0][key] = value
            invalid.append(altered)
        altered = deepcopy(good)
        del altered["rules"][0][key]
        invalid.append(altered)
    for key in good["rules"][0]["definitions"][0]:
        altered = deepcopy(good)
        del altered["rules"][0]["definitions"][0][key]
        invalid.append(altered)
        if good["rules"][0]["definitions"][0][key] is not None:
            altered = deepcopy(good)
            altered["rules"][0]["definitions"][0][key] = None
            invalid.append(altered)
    for change in (
        {"definition_id": "bad"},
        {"adapter_binding_id": "bad"},
        {"instrument_type": "token"},
        {"quantity": 9.3},
        {"quantity": "0"},
        {"quantity": "NaN"},
        {"quantity": "1e3"},
        {"unit_code": ""},
        {"extra": 1},
    ):
        altered = deepcopy(good)
        altered["rules"][0]["definitions"][0].update(change)
        invalid.append(altered)
    for change in (
        {"rule_id": ACTOR.replace("-", "")},
        {"contribution_type": "accepted_submission"},
        {"extra": 1},
    ):
        altered = deepcopy(good)
        altered["rules"][1].update(change)
        invalid.append(altered)
    for change in (
        {"definition_id": PROJECT.replace("-", "")},
        {"instrument_type": "money"},
    ):
        altered = deepcopy(good)
        altered["rules"][0]["definitions"][1].update(change)
        invalid.append(altered)
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(good).encode()
        assert invoke(cli, origin, "show", "--version", VERSION).returncode == 0
        for value in invalid:
            response["body"] = json.dumps(value).encode()
            before = len(requests)
            result = invoke(cli, origin, "show", "--version", VERSION)
            assert_failure(result, "invalid_api_response")
            assert "outcome_unknown" not in json.loads(result.stderr)["error"]
            assert len(requests) == before + 1
        for action, good in (("current", selection()), ("show", policy())):
            response["body"] = (
                b'{"project_id":"'
                + PROJECT.encode()
                + b'",'
                + json.dumps(good)[1:].encode()
            )
            assert_failure(invoke(cli, origin, action), "invalid_api_response")


def test_policy_read_credential_safety_bounds_and_backend_denial(cli):
    with http_fixture() as (origin, response, requests):
        for action, value in (("current", selection()), ("show", policy())):
            response["body"] = json.dumps(value).encode()
            assert_failure(
                invoke(cli, origin, action, token=POLICY.replace("-", "")),
                "invalid_api_response",
            )
            response["body"] = b" " * (64 * 1024 + 1)
            assert_failure(invoke(cli, origin, action), "invalid_api_response")
            response.update(
                status=404,
                body=json.dumps(
                    canonical_error()
                    | {
                        "error": canonical_error()["error"]
                        | {"code": "contribution_policy_not_found"}
                    }
                ).encode(),
            )
            response["headers"] = {
                "Content-Type": "application/json",
                "X-Correlation-ID": ACTOR,
            }
            before = len(requests)
            result = invoke(cli, origin, action, token=ACTOR.replace("-", ""))
            assert_failure(result, "contribution_policy_not_found")
            assert (
                ACTOR not in result.stderr
                and "outcome_unknown" not in json.loads(result.stderr)["error"]
            )
            assert len(requests) == before + 1
            response["status"] = 200


def test_v2_policy_read_preserves_three_tiers_and_rejects_wrong_selection(cli):
    value = policy(compensated=True)
    value.update(
        reward_model_version=2,
        instrument_type="money",
        unit_code="USD",
        adapter_binding_id=KEY,
    )
    template = value["rules"][0]["definitions"][0]
    value["rules"][0]["definitions"] = [
        template
        | {
            "definition_id": identifier,
            "reward_model_version": 2,
            "task_size": size,
            "quantity": amount,
        }
        for identifier, size, amount in (
            (PROJECT, "small", "2.125000000000000001"),
            (VERSION, "medium", "4"),
            (KEY, "large", "8"),
        )
    ]
    invalid = []
    for change in (
        {"task_size": "medium"},
        {"task_size": None},
        {"reward_model_version": 1},
        {"unit_code": "NGN"},
    ):
        bad = deepcopy(value)
        bad["rules"][0]["definitions"][0].update(change)
        invalid.append(bad)
    bad = deepcopy(value)
    bad["rules"][0]["definitions"].pop()
    invalid.append(bad)
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(value).encode()
        result = invoke(cli, origin, "show", "--version", VERSION)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == value
        for bad in invalid:
            response["body"] = json.dumps(bad).encode()
            assert_failure(
                invoke(cli, origin, "show", "--version", VERSION),
                "invalid_api_response",
            )
