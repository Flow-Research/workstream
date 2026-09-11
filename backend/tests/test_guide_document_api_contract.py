"""Guide files use document metadata; required task examples are ordinary text."""

import pytest
from pydantic import ValidationError

from app.modules.projects.schemas import (
    ProjectGuideCreate, ProjectGuideUpdate, ProjectGuideResponse, ProjectGuideDocumentInput,
)


@pytest.mark.parametrize("schema,payload", [
    (ProjectGuideCreate, {"version": "v0.1", "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}], "task_examples": [{"content": "Review a claim."}]}),
    (ProjectGuideUpdate, {"change_summary": "Corrected source documents"}),
])
@pytest.mark.parametrize("field", ["content_markdown", "retained_content_markdown", "content", "inline_text"])
def test_guide_write_rejects_inline_body_fields(schema, payload, field):
    with pytest.raises(ValidationError) as error:
        schema.model_validate(payload | {field: "Inline guide content"})
    assert any(item["loc"] == (field,) and item["type"] == "extra_forbidden" for item in error.value.errors())


def test_current_guide_response_excludes_retained_body():
    assert "content_markdown" not in ProjectGuideResponse.model_fields
    assert "retained_content_markdown" not in ProjectGuideResponse.model_fields


@pytest.mark.parametrize("patch", [
    {"source_kind": "url_doc"}, {"source_kind": "rubric"},
    {"ingestion_adapter": "manual_import"}, {"media_type": "text/markdown"},
    {"media_type": "text/plain"}, {"media_type": "image/png"},
    {"media_type": "audio/wav"}, {"media_type": "application/vnd.ms-powerpoint"},
])
def test_source_metadata_rejects_superseded_or_unsupported_ingress(patch):
    with pytest.raises(ValidationError):
        ProjectGuideDocumentInput.model_validate({
            "label": "guide.pdf", "media_type": "application/pdf", **patch,
        })


@pytest.mark.parametrize("method,suffix", [
    ("GET", "post-submit-checker-policy/setup"),
    ("POST", "post-submit-checker-policy/approve"),
    ("POST", "post-submit-checker-policy/request-correction"),
    ("POST", "source-snapshots/{snapshot_id}/run-sufficiency-agent"),
    ("POST", "source-snapshots"),
    ("POST", "source-snapshots/{source_snapshot_id}/items/{source_item_id}/artifact"),
])
def test_superseded_setup_endpoints_are_not_registered(method, suffix):
    from app.core.config import Settings
    from app.main import create_app

    app = create_app(Settings(environment="test"))
    path = f"/api/v1/projects/{{project_id}}/guides/{{guide_id}}/{suffix}"
    assert method.lower() not in app.openapi().get("paths", {}).get(path, {})
    assert not any(
        getattr(route, "path", None) == path and method in getattr(route, "methods", set())
        for route in app.routes
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source,message", [
    ("unified_compilation", "unified compilation policy approval is unavailable"),
    ("agent_derivation", "manual policy lineage is required for this approval"),
    ("manual", "manual policy lineage is required for this approval"),
])
async def test_generic_approval_rejects_nonmanual_lineage_before_effects(source, message):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.modules.projects.service import ProjectService, PolicySetupBlocked
    from app.modules.projects.schemas import SubmissionArtifactPolicyApprove
    from app.schemas.auth import ActorContext

    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    service = ProjectService(session)
    guide = SimpleNamespace(id="guide", project_id="project", status="draft")
    policy = SimpleNamespace(id="policy", project_id="project", guide_id="guide",
                             lifecycle_status="draft", derivation_source=source)
    service._lock_project_guide_for_setup = AsyncMock(return_value=guide)
    service._repo = SimpleNamespace(lock_submission_artifact_policy=AsyncMock(return_value=policy))
    actor = ActorContext(actor_id="manager", external_subject="manager",
                         external_issuer="https://identity.test", roles=("project_manager",),
                         auth_source="dev_mock")
    with pytest.raises(PolicySetupBlocked, match=message):
        await service.approve_submission_artifact_policy(
            actor, "project", "guide", "policy", SubmissionArtifactPolicyApprove(),
        )
    service._repo.lock_submission_artifact_policy.assert_awaited_once_with("policy")
    assert policy.lifecycle_status == "draft"
    session.commit.assert_not_awaited()
    session.flush.assert_not_awaited()


def test_current_setup_response_excludes_superseded_post_policy_step():
    from app.modules.projects.schemas import ProjectSetupRunResponse
    assert "output_post_submit_checker_policy_id" not in ProjectSetupRunResponse.model_fields
    assert "post_submit_derivation_summary" not in ProjectSetupRunResponse.model_fields


def test_superseded_activation_implementation_is_absent():
    from app.modules.projects.service import ProjectService
    assert not hasattr(ProjectService, "activate_guide")
    assert callable(ProjectService.validate_activation_ready)


@pytest.mark.parametrize("examples", [None, [], [{"content": ""}], [{"content": " \t\n\u2003"}], [{}]])
def test_guide_create_requires_at_least_one_nonblank_task_example(examples):
    payload = {"version": "v0.1", "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}]}
    if examples is not None:
        payload["task_examples"] = examples
    with pytest.raises(ValidationError, match="task_examples"):
        ProjectGuideCreate.model_validate(payload)


def test_guide_examples_accept_minimal_and_diverse_descriptions_without_task_schema():
    examples = [
        {"content": "Draft a claim review."},
        {"content": "  Reproduce a reported result.\nKeep this whitespace. 雪", "title": "Paper task", "labels": ["research"]},
    ]
    created = ProjectGuideCreate.model_validate({"version": "v0.1", "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}], "task_examples": examples})
    assert [item.content for item in created.task_examples] == [item["content"] for item in examples]
    assert created.task_examples[0].title is None
    assert created.task_examples[0].labels == ()
    assert created.task_examples[1].labels == ("research",)


def test_task_example_commitment_includes_order_content_title_and_labels():
    from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples

    examples = [{"content": "First"}, {"content": "Second", "title": "Idea", "labels": ["code"]}]
    digest = task_examples_hash(validate_task_examples(examples))
    for changed in [list(reversed(examples)), [{"content": "Changed"}, examples[1]],
                    [examples[0], examples[1] | {"title": "Changed"}],
                    [examples[0], examples[1] | {"labels": ["review"]}]]:
        assert task_examples_hash(validate_task_examples(changed)) != digest


@pytest.mark.parametrize("content", ["雪" * 50_000, "\n" * 65_535 + "x"], ids=("multibyte_utf8", "json_escaping"))
def test_task_example_aggregate_budget_counts_utf8_and_json_escaping(content):
    with pytest.raises(ValidationError, match="aggregate byte limit"):
        ProjectGuideCreate.model_validate({"version": "v0.1", "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}], "task_examples": [{"content": content}]})


def test_guide_create_authorization_projection_contains_commitments_not_example_text():
    """The prepared boundary binds content without copying it into AUTH facts."""
    import json
    from types import SimpleNamespace
    from uuid import uuid4
    from app.modules.authorization.catalogue import ActionId
    from app.modules.projects.guide_mutation_service import GuideMutationService

    sentinel = "private-example-text-sentinel"
    payload = ProjectGuideCreate.model_validate({"version": "v0.1", "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}], "task_examples": [
        {"content": sentinel, "title": "private-example-title", "labels": ["private-label"]},
    ]})
    caller, digest = GuideMutationService._input(
        ActionId.PROJECT_GUIDE_CREATE, "POST /api/v1/projects/{project_id}/guides",
        SimpleNamespace(profile=SimpleNamespace(id=str(uuid4())), identity_link=SimpleNamespace(id=str(uuid4()))),
        uuid4(), payload, project_id=uuid4(), target_resource_id=uuid4(), operation_id=uuid4(),
    )
    projection = json.dumps(caller.request_value)
    assert sentinel not in projection
    assert "private-example-title" not in projection and "private-label" not in projection
    assert caller.request_value["request_digest"] == digest
    assert caller.request_value["task_examples_count"] == 1
    assert caller.request_value["task_examples_hash"].startswith("sha256:")


def test_document_upload_openapi_binary_body_and_bounded_responses():
    from app.core.config import Settings
    from app.main import create_app
    document = create_app(Settings(environment="test")).openapi()
    operation = document["paths"]["/api/v1/projects/{project_id}/guides/{guide_id}/documents/{document_id}/content"]["post"]
    body = operation["requestBody"]
    assert body["required"] is True
    assert set(body["content"]) == {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    assert all(value["schema"] == {"type": "string", "format": "binary"} for value in body["content"].values())
    responses = operation["responses"]
    assert responses["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GuideArtifactIngestResponse"}
    schema = document["components"]["schemas"]["GuideArtifactIngestResponse"]
    assert set(schema["properties"]) == {"document_id", "sha256", "byte_count", "status", "replayed"}
    for code in ("404", "409", "413", "422", "503"):
        assert responses[code]["description"]
        assert responses[code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ApiErrorResponse"}
