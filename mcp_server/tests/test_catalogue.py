"""Catalogue closure tests for the Workstream MCP server."""

from __future__ import annotations

import pytest
from mcp.server.lowlevel.server import NotificationOptions

from workstream_mcp.schemas import (
    ArtifactHashEntryInput,
    ClaimTaskInput,
    EvidenceItemInput,
    MCP_PROMPTS,
    RESOURCE_DEFINITIONS,
    TOOL_DEFINITIONS,
    SubmitReviewInput,
)
from workstream_mcp.server import build_fastmcp_server, create_mcp_application


def test_catalogue_exposes_exact_resource_types_and_tools() -> None:
    """The v0.1 MCP surface is closed to the approved catalogue."""
    app = create_mcp_application(gateway=object())  # type: ignore[arg-type]

    assert [resource.name for resource in app.resources] == [
        "my_projects",
        "my_contributions",
        "tasks",
        "task_context",
        "task_status",
        "current_review",
        "review_context",
    ]
    assert [tool.name for tool in app.tools] == [
        "claim_task",
        "release_task",
        "run_pre_submit_check",
        "submit_task",
        "claim_review",
        "release_review",
        "submit_review",
    ]
    assert app.prompts == ()


def test_catalogue_contains_no_token_inputs_or_mutating_resources() -> None:
    """Identity is transport-provided and resources stay read-only."""
    all_resource_templates = [
        template for resource in RESOURCE_DEFINITIONS for template in resource.uri_templates
    ]
    all_tool_fields = [field for tool in TOOL_DEFINITIONS for field in tool.input_fields]

    assert MCP_PROMPTS == ()
    assert len(RESOURCE_DEFINITIONS) == 7
    assert len(TOOL_DEFINITIONS) == 7
    assert all(resource.mutating is False for resource in RESOURCE_DEFINITIONS)
    assert [tool.name for tool in TOOL_DEFINITIONS if tool.mutating is False] == [
        "run_pre_submit_check"
    ]
    assert not any("token" in template.lower() for template in all_resource_templates)
    assert "bearer_token" not in all_tool_fields
    assert "authorization" not in all_tool_fields


@pytest.mark.asyncio
async def test_fastmcp_runtime_registration_matches_closed_catalogue() -> None:
    """Runtime registration must match the static WS-MCP-001 catalogue."""
    server = build_fastmcp_server(gateway=object())  # type: ignore[arg-type]

    tools = await server.list_tools()
    resources = await server.list_resources()
    resource_templates = await server.list_resource_templates()
    prompts = await server.list_prompts()

    tool_names = [tool.name for tool in tools]
    tool_schemas = {tool.name: tool.inputSchema for tool in tools}
    tool_annotations = {tool.name: tool.annotations for tool in tools}
    tool_titles = {tool.name: tool.title for tool in tools}
    tool_descriptions = {tool.name: tool.description for tool in tools}
    tool_output_schemas = {tool.name: tool.outputSchema for tool in tools}
    resource_uris = [str(resource.uri) for resource in resources]
    template_uris = [str(template.uriTemplate) for template in resource_templates]
    resource_metadata = {
        str(resource.uri): (resource.title, resource.description) for resource in resources
    }
    resource_metadata.update(
        {
            str(template.uriTemplate): (template.title, template.description)
            for template in resource_templates
        }
    )

    assert tool_names == [tool.name for tool in TOOL_DEFINITIONS]
    assert prompts == []
    assert len(resources) + len(resource_templates) == sum(
        len(resource.uri_templates) for resource in RESOURCE_DEFINITIONS
    )
    assert set(resource_uris + template_uris) == {
        template for resource in RESOURCE_DEFINITIONS for template in resource.uri_templates
    }
    for definition in RESOURCE_DEFINITIONS:
        for uri_template in definition.uri_templates:
            assert resource_metadata[uri_template] == (
                definition.title,
                definition.description,
            )
    for tool in TOOL_DEFINITIONS:
        schema = tool_schemas[tool.name]
        assert tool_titles[tool.name] == tool.title
        assert tool_descriptions[tool.name] == tool.description
        assert set(schema["properties"]) == set(tool.input_fields)
        assert "bearer_token" not in schema["properties"]
        assert "authorization" not in schema["properties"]
        for field_name in tool.input_fields:
            field_schema = schema["properties"][field_name]
            assert field_schema["description"]
            assert field_schema["examples"]
    assert tool_schemas["claim_task"]["required"] == ["task_id", "request_id"]
    assert tool_schemas["claim_task"]["properties"]["request_id"]["format"] == "uuid"
    request_id_schema = tool_schemas["claim_task"]["properties"]["request_id"]
    assert "new UUID for every new logical operation" in request_id_schema["description"]
    assert "Never reuse it for a different task, review, or action" in request_id_schema[
        "description"
    ]
    assert request_id_schema["examples"] == ["11111111-1111-4111-8111-111111111111"]
    task_id_schema = tool_schemas["claim_task"]["properties"]["task_id"]
    assert task_id_schema["pattern"] == "^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    assert task_id_schema["minLength"] == 1
    assert task_id_schema["maxLength"] == 100
    release_reason_schema = tool_schemas["release_task"]["properties"]["reason"]
    assert release_reason_schema["default"] is None
    assert release_reason_schema["anyOf"][0]["maxLength"] == 1000
    assert "summary" in tool_schemas["submit_task"]["$defs"]["SubmissionInput"]["properties"]
    submission_properties = tool_schemas["submit_task"]["$defs"]["SubmissionInput"][
        "properties"
    ]
    assert submission_properties["summary"]["maxLength"] == 10000
    assert submission_properties["worker_attestation"]["maxLength"] == 20000
    assert submission_properties["artifact_hash_manifest"]["maxItems"] == 1000
    assert submission_properties["evidence_items"]["maxItems"] == 1000
    for field_name in (
        "summary",
        "package_uri",
        "package_hash",
        "artifact_hash_manifest",
        "worker_attestation",
        "evidence_items",
    ):
        assert submission_properties[field_name]["description"]
        assert submission_properties[field_name]["examples"]
    artifact_properties = tool_schemas["submit_task"]["$defs"]["ArtifactHashEntryInput"][
        "properties"
    ]
    evidence_properties = tool_schemas["submit_task"]["$defs"]["EvidenceItemInput"][
        "properties"
    ]
    assert all(field["description"] and field["examples"] for field in artifact_properties.values())
    assert all(field["description"] and field["examples"] for field in evidence_properties.values())
    review_properties = tool_schemas["submit_review"]["properties"]
    assert review_properties["findings"]["maxItems"] == 100
    assert tool_schemas["submit_review"]["properties"]["decision"]["enum"] == [
        "accept",
        "needs_revision",
        "reject",
    ]
    assert tool_schemas["submit_review"]["required"] == [
        "review_ref",
        "decision",
        "findings",
        "request_id",
    ]
    finding_properties = tool_schemas["submit_review"]["$defs"]["ReviewFindingInput"][
        "properties"
    ]
    assert all(field["description"] and field["examples"] for field in finding_properties.values())
    expected_output_titles = {
        "claim_task": "ClaimTaskResult",
        "release_task": "ReleaseTaskResult",
        "run_pre_submit_check": "PreSubmitCheckResult",
        "submit_task": "SubmitTaskResult",
        "claim_review": "ClaimReviewResult",
        "release_review": "ReleaseReviewResult",
        "submit_review": "SubmitReviewResult",
    }
    for tool_name, output_title in expected_output_titles.items():
        output_schema = tool_output_schemas[tool_name]
        assert output_schema is not None
        assert output_schema["title"] == output_title
        assert output_schema["type"] == "object"
        assert output_schema["properties"]["operation"]["const"] == tool_name
        assert output_schema["properties"]["outcome"]["description"]
        assert output_schema["properties"]["data"]["description"]
        assert set(output_schema["required"]) == {
            "operation",
            "outcome",
            "workstream_ref",
            "next_resource",
            "summary",
            "data",
        }
    assert tool_annotations["run_pre_submit_check"] is not None
    assert tool_annotations["run_pre_submit_check"].readOnlyHint is True
    assert tool_annotations["run_pre_submit_check"].destructiveHint is False
    for tool_name in set(tool_names) - {"run_pre_submit_check"}:
        annotations = tool_annotations[tool_name]
        assert annotations is not None
        assert annotations.readOnlyHint is False
        assert annotations.idempotentHint is True


def test_runtime_does_not_advertise_resource_subscriptions_or_list_events() -> None:
    """The v0.1 server is pull-based and exposes no subscription/event channel."""
    server = build_fastmcp_server(gateway=object())  # type: ignore[arg-type]

    capabilities = server._mcp_server.get_capabilities(  # noqa: SLF001
        NotificationOptions(),
        {},
    )

    assert capabilities.resources is not None
    assert capabilities.resources.subscribe is False
    assert capabilities.resources.listChanged is False
    assert capabilities.tools is not None
    assert capabilities.tools.listChanged is False
    assert capabilities.experimental == {}
    assert capabilities.tasks is None


@pytest.mark.parametrize("relative_ref", [".", ".."])
def test_stable_reference_validation_reports_relative_segments(relative_ref: str) -> None:
    """Relative path segments receive the specific path-safety validation error."""
    with pytest.raises(ValueError, match="must not be a relative path segment"):
        ClaimTaskInput(task_id=relative_ref, request_id="11111111-1111-4111-8111-111111111111")


def test_nested_tool_inputs_have_bounded_collections_and_metadata() -> None:
    """Arbitrary evidence and review input cannot grow without adapter-edge bounds."""
    deeply_nested: object = "value"
    for _ in range(7):
        deeply_nested = {"nested": deeply_nested}

    with pytest.raises(ValueError, match="metadata nesting"):
        EvidenceItemInput(type="note", label="evidence", metadata={"root": deeply_nested})
    with pytest.raises(ValueError):
        EvidenceItemInput(
            type="note",
            label="evidence",
            metadata={f"key-{index}": index for index in range(101)},
        )
    with pytest.raises(ValueError):
        ArtifactHashEntryInput(
            artifact="result.txt",
            hash="sha256:def",
            notes="x" * 10001,
        )
    with pytest.raises(ValueError):
        SubmitReviewInput(
            review_ref="review-1",
            decision="accept",
            findings=[{"summary": "finding"}] * 101,
            request_id="11111111-1111-4111-8111-111111111111",
        )
    with pytest.raises(ValueError):
        SubmitReviewInput(
            review_ref="review-1",
            decision="accept",
            findings=[{"summary": "finding", "evidence_refs": ["ref"] * 101}],
            request_id="11111111-1111-4111-8111-111111111111",
        )
