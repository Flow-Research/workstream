from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from starlette.testclient import TestClient

PROJECT_ID = "019a2a00-0000-7000-8000-000000000601"
POLICY_ID = "019a2a00-0000-7000-8000-000000000602"
VERSION_ID = "019a2a00-0000-7000-8000-000000000603"
KEY = "019a2a00-0000-7000-8000-000000000604"
EVENT_ID = "019a2a00-0000-7000-8000-000000000605"
ACTOR_ID = "019a2a00-0000-7000-8000-000000000606"
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _rules() -> list[dict[str, Any]]:
    return [
        {
            "contribution_type": contribution_type,
            "compensation_mode": "unpaid",
        }
        for contribution_type in ("accepted_submission", "completed_review")
    ]


def _receipt(**changes: Any) -> dict[str, Any]:
    value = {
        "event_id": EVENT_ID,
        "operation_id": KEY,
        "request_digest": "sha256:" + "a" * 64,
        "event_type": "draft_created",
        "actor_profile_id": ACTOR_ID,
        "project_id": PROJECT_ID,
        "contribution_policy_id": POLICY_ID,
        "contribution_policy_version_id": VERSION_ID,
        "version_number": 1,
        "prior_current_version_id": None,
        "prior_current_version_number": None,
        "from_policy_status": None,
        "to_policy_status": "draft",
        "from_version_status": None,
        "to_version_status": "draft",
        "occurred_at": "2026-10-23T10:00:00Z",
    }
    value.update(changes)
    return value


def test_policy_current_read_forwards_selector_and_rejects_substitution(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream["json"] = {
        "project_id": PROJECT_ID,
        "contribution_policy_id": POLICY_ID,
        "current_published_version_id": None,
        "open_draft_version_id": VERSION_ID,
    }
    result = call(
        client,
        name="workstream_contribution_policy_current_get",
        arguments={"project_id": PROJECT_ID},
    ).json()["result"]
    assert result["isError"] is False
    assert received[0].url.path == f"/api/v1/projects/{PROJECT_ID}/contribution-policies/current"

    received.clear()
    upstream["json"]["project_id"] = POLICY_ID
    result = call(
        client,
        name="workstream_contribution_policy_current_get",
        arguments={"project_id": PROJECT_ID},
    ).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_api_response"


def test_policy_create_forwards_body_and_typed_key_only(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    upstream.update(status=201, json=_receipt())
    result = call(
        client,
        name="workstream_contribution_policy_create",
        arguments={
            "project_id": PROJECT_ID,
            "body": {"name": "Core policy"},
            "idempotency_key": KEY,
        },
        token="finance-caller",
        extra_headers={"Idempotency-Key": EVENT_ID},
    ).json()["result"]
    assert result["isError"] is False
    request = received[0]
    assert request.method == "POST"
    assert request.url.path == f"/api/v1/projects/{PROJECT_ID}/contribution-policies/drafts"
    assert request.headers["idempotency-key"] == KEY
    assert request.headers["authorization"] == "Bearer finance-caller"
    assert json.loads(request.content) == {"name": "Core policy"}


@pytest.mark.parametrize(
    ("action", "method", "suffix", "body", "transition"),
    [
        (
            "update",
            "PUT",
            "",
            {
                "instrument_type": None,
                "unit_code": None,
                "adapter_binding_id": None,
                "rules": _rules(),
            },
            {
                "event_type": "draft_updated",
                "from_policy_status": "draft",
                "to_policy_status": "draft",
                "from_version_status": "draft",
                "to_version_status": "draft",
            },
        ),
        (
            "publish",
            "POST",
            "/publication",
            {},
            {
                "event_type": "published",
                "from_policy_status": "draft",
                "to_policy_status": "active",
                "from_version_status": "draft",
                "to_version_status": "published",
            },
        ),
        (
            "retire",
            "POST",
            "/retirement",
            {},
            {
                "event_type": "retired",
                "from_policy_status": "active",
                "to_policy_status": "retired",
                "from_version_status": "published",
                "to_version_status": "retired",
                "prior_current_version_id": VERSION_ID,
                "prior_current_version_number": 1,
            },
        ),
    ],
)
def test_policy_existing_version_mutations_bind_route_key_and_transition(
    adapter: Adapter,
    call: Call,
    action: str,
    method: str,
    suffix: str,
    body: dict[str, Any],
    transition: dict[str, Any],
) -> None:
    client, received, upstream = adapter
    upstream.update(status=200, json=_receipt(**transition))
    result = call(
        client,
        name=f"workstream_contribution_policy_{action}",
        arguments={
            "project_id": PROJECT_ID,
            "policy_id": POLICY_ID,
            "version_id": VERSION_ID,
            "body": body,
            "idempotency_key": KEY,
        },
    ).json()["result"]
    assert result["isError"] is False
    request = received[0]
    assert request.method == method
    assert request.url.path == (
        f"/api/v1/projects/{PROJECT_ID}/contribution-policies/{POLICY_ID}/versions/"
        f"{VERSION_ID}{suffix}"
    )
    assert request.headers["idempotency-key"] == KEY
    assert json.loads(request.content) == body


def test_policy_mutation_rejects_substituted_receipt_as_uncertain(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream.update(status=201, json=_receipt(operation_id=EVENT_ID))
    result = call(
        client,
        name="workstream_contribution_policy_create",
        arguments={
            "project_id": PROJECT_ID,
            "body": {"name": "Core policy"},
            "idempotency_key": KEY,
        },
    ).json()["result"]
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


def test_policy_current_rejects_selection_without_any_version(adapter: Adapter, call: Call) -> None:
    client, _, upstream = adapter
    upstream["json"] = {
        "project_id": PROJECT_ID,
        "contribution_policy_id": POLICY_ID,
        "current_published_version_id": None,
        "open_draft_version_id": None,
    }
    result = call(
        client,
        name="workstream_contribution_policy_current_get",
        arguments={"project_id": PROJECT_ID},
    ).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_api_response"


def test_policy_mutation_rejects_inconsistent_transition_as_uncertain(
    adapter: Adapter, call: Call
) -> None:
    client, _, upstream = adapter
    upstream.update(status=201, json=_receipt(to_version_status="published"))
    result = call(
        client,
        name="workstream_contribution_policy_create",
        arguments={
            "project_id": PROJECT_ID,
            "body": {"name": "Core policy"},
            "idempotency_key": KEY,
        },
    ).json()["result"]
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"


def test_invalid_policy_graph_never_dispatches(adapter: Adapter, call: Call) -> None:
    client, received, _ = adapter
    duplicate = {
        "contribution_type": "accepted_submission",
        "compensation_mode": "unpaid",
    }
    result = call(
        client,
        name="workstream_contribution_policy_update",
        arguments={
            "project_id": PROJECT_ID,
            "policy_id": POLICY_ID,
            "version_id": VERSION_ID,
            "body": {
                "instrument_type": None,
                "unit_code": None,
                "adapter_binding_id": None,
                "rules": [duplicate, duplicate],
            },
            "idempotency_key": KEY,
        },
    ).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize(
    "invalid", [None, "missing_tier", "points_fraction", "per_rule_header", "null_header"]
)
def test_paid_policy_uses_exact_portable_input_contract(
    adapter: Adapter, call: Call, invalid: str | None
) -> None:
    client, received, upstream = adapter
    body: dict[str, Any] = {
        "instrument_type": "project_points",
        "unit_code": "FLOW",
        "adapter_binding_id": ACTOR_ID,
        "rules": [
            {
                "contribution_type": "accepted_submission",
                "compensation_mode": "compensated",
                "quantities": {"small": "10", "medium": "20", "large": "100"},
            },
            {
                "contribution_type": "completed_review",
                "compensation_mode": "compensated",
                "quantity": "3",
            },
        ],
    }
    if invalid == "missing_tier":
        del body["rules"][0]["quantities"]["medium"]
    elif invalid == "points_fraction":
        body["rules"][1]["quantity"] = "3.0"
    elif invalid == "per_rule_header":
        body["rules"][0]["unit_code"] = "OTHER"
    elif invalid == "null_header":
        body["adapter_binding_id"] = None
    upstream.update(
        status=200,
        json=_receipt(
            event_type="draft_updated",
            from_policy_status="draft",
            to_policy_status="draft",
            from_version_status="draft",
            to_version_status="draft",
        ),
    )
    result = call(
        client,
        name="workstream_contribution_policy_update",
        arguments={
            "project_id": PROJECT_ID,
            "policy_id": POLICY_ID,
            "version_id": VERSION_ID,
            "idempotency_key": KEY,
            "body": body,
        },
    ).json()["result"]
    if invalid is None:
        assert result["isError"] is False
        assert len(received) == 1 and json.loads(received[0].content) == body
    else:
        assert result["structuredContent"]["error"] == "invalid_tool_input"
        assert received == []


def _policy_view() -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "contribution_policy_id": POLICY_ID,
        "contribution_policy_version_id": VERSION_ID,
        "name": "Exact policy",
        "policy_status": "active",
        "version_number": 1,
        "version_status": "published",
        "instrument_type": "money",
        "unit_code": "USD",
        "adapter_binding_id": ACTOR_ID,
        "rules": [
            {
                "rule_id": KEY,
                "contribution_type": "accepted_submission",
                "compensation_mode": "compensated",
                "definitions": [
                    {
                        "definition_id": identifier,
                        "task_size": size,
                        "instrument_type": "money",
                        "unit_code": "USD",
                        "quantity": quantity,
                        "adapter_binding_id": ACTOR_ID,
                    }
                    for identifier, size, quantity in (
                        (PROJECT_ID, "small", "2.125000000000000001"),
                        (POLICY_ID, "medium", "4"),
                        (VERSION_ID, "large", "8"),
                    )
                ],
            },
            {
                "rule_id": ACTOR_ID,
                "contribution_type": "completed_review",
                "compensation_mode": "unpaid",
                "definitions": [],
            },
        ],
    }


@pytest.mark.parametrize("collection", [False, True])
def test_policy_reads_and_lists_require_complete_current_graphs(
    adapter: Adapter, call: Call, collection: bool
) -> None:
    from copy import deepcopy

    client, received, upstream = adapter
    arguments = {"project_id": PROJECT_ID}
    if not collection:
        arguments.update(policy_id=POLICY_ID, version_id=VERSION_ID)
    name = (
        "workstream_contribution_policies_list"
        if collection
        else "workstream_contribution_policy_get"
    )

    def read(view):
        value = deepcopy(view)
        if collection:
            value.update(
                created_at="2026-10-23T10:00:00Z",
                published_at=None if value["version_status"] == "draft" else "2026-10-23T10:00:00Z",
                retired_at=None,
            )
            value = {"items": [value], "next_cursor": None}
        upstream["json"] = value
        before = len(received)
        result = call(client, name=name, arguments=arguments).json()["result"]
        assert len(received) == before + 1
        return result

    valid = _policy_view()
    empty = deepcopy(valid)
    empty.update(
        version_status="draft",
        instrument_type=None,
        unit_code=None,
        adapter_binding_id=None,
        rules=[],
    )
    unpaid = deepcopy(empty)
    unpaid.update(
        version_status="published",
        rules=[
            {
                "rule_id": KEY,
                "contribution_type": "accepted_submission",
                "compensation_mode": "unpaid",
                "definitions": [],
            },
            {
                "rule_id": ACTOR_ID,
                "contribution_type": "completed_review",
                "compensation_mode": "unpaid",
                "definitions": [],
            },
        ],
    )
    reviewer_only = deepcopy(valid)
    reviewer_only["rules"][0].update(compensation_mode="unpaid", definitions=[])
    reviewer_only["rules"][1].update(
        compensation_mode="compensated",
        definitions=[
            valid["rules"][0]["definitions"][0]
            | {"definition_id": EVENT_ID, "task_size": None, "quantity": "1"},
        ],
    )
    for view in (valid, empty, unpaid, reviewer_only):
        assert read(view)["isError"] is False

    invalid = []
    for change in (
        {"rules": []},
        {"version_number": 0},
        {"unit_code": "NGN"},
        {"adapter_binding_id": KEY},
        {"private": 1},
    ):
        invalid.append(deepcopy(valid) | change)
    partial = deepcopy(valid)
    partial.update(version_status="draft", rules=partial["rules"][:1])
    invalid.append(partial)
    for change in (
        {"task_size": "medium"},
        {"quantity": "0"},
        {"private": 1},
    ):
        altered = deepcopy(valid)
        altered["rules"][0]["definitions"][0].update(change)
        invalid.append(altered)
    altered = deepcopy(valid)
    altered["rules"][0]["definitions"].pop()
    invalid.append(altered)
    altered = deepcopy(valid)
    altered["rules"][1]["definitions"] = [deepcopy(valid["rules"][0]["definitions"][0])]
    invalid.append(altered)
    for view in invalid:
        assert read(view)["structuredContent"]["error"] == "invalid_api_response", view
