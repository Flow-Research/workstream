"""Guide setup contracts, exact source evidence, and default submission limits."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.adapters.tasks import task_service
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CompilationFinding,
    GuideEvidenceRef,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
    project_guide_compilation_prompt_bytes,
    validate_project_guide_compilation_result,
)
from app.modules.projects.api.guide_documents import GuideDocumentManifest, GuideDocumentVersion
from tests.projects.guide_compilation.helpers import runtime_configuration, valid_specification

SHA256 = "sha256:" + "a" * 64

@pytest.mark.parametrize(
    "project_limit, default_limit, expected",
    [
        (100, None, 100),
        (None, 50, 50),
        (100, 50, 50),
        (20, 50, 20),
        (None, None, None),
    ],
)
@pytest.mark.parametrize("field", ["maximum_archive_entries", "maximum_archive_size_bytes"])
def test_archive_limit_projection_and_default_floor(
    monkeypatch, project_limit, default_limit, expected, field
):
    from app.modules.projects import service
    from app.modules.projects.guide_compilation.projection_payloads import policy_body

    proposal = SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1000,
        maximum_package_size_bytes=2000,
        **{field: project_limit},
    )
    monkeypatch.setitem(service.WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY, field, default_limit)
    body = policy_body(None, proposal)
    assert body[field] == project_limit
    effective = service.ProjectService(None)._merge_effective_submission_artifact_policy(body)
    assert effective[field] == expected
    assert effective["project_policy"][field] == project_limit
    assert effective["workstream_default_policy"][field] == default_limit


@pytest.mark.parametrize("field", ["required_evidence", "attestation_terms"])
@pytest.mark.parametrize(
    "value, valid",
    [
        ("results", True),
        ("a" + "b" * 99, True),
        ("results.v0_1-ok", True),
        ("", False),
        ("a" + "b" * 100, False),
        ("Provide results", False),
        ("evidence/results", False),
        ("9results", False),
        ("Results", False),
    ],
)
def test_policy_identifier_schema_matches_existing_validator(field, value, valid):
    import re
    from app.interfaces.project_agents import _SAFE_IDENTIFIER

    schema = SubmissionArtifactPolicyProposal.model_json_schema()["properties"][field]["items"]
    assert schema["pattern"] == _SAFE_IDENTIFIER.pattern
    assert (schema["minLength"], schema["maxLength"]) == (1, 100)
    assert "machine identifier" in schema["description"]
    assert (re.fullmatch(schema["pattern"], value) is not None) is valid
    arguments = dict(maximum_file_size_bytes=100, maximum_package_size_bytes=1000)
    arguments[field] = (value,)
    if valid:
        assert getattr(SubmissionArtifactPolicyProposal(**arguments), field) == (value,)
    else:
        with pytest.raises(ValidationError, match="identifier is invalid"):
            SubmissionArtifactPolicyProposal(**arguments)


def test_model_schema_describes_existing_expanded_byte_limit():
    properties = SubmissionArtifactPolicyProposal.model_json_schema()["properties"]
    assert "expanded bytes" in properties["maximum_package_size_bytes"]["description"]
    assert "not compressed upload bytes" in properties["maximum_package_size_bytes"]["description"]
    assert (
        "entire submitted compressed ZIP" in properties["maximum_archive_size_bytes"]["description"]
    )
    assert "directory entries" in properties["maximum_archive_entries"]["description"]
    assert "ZIP root" in properties["required_artifacts"]["description"]


@pytest.mark.parametrize("default_limit", [None, 50])
@pytest.mark.parametrize("field", ["maximum_archive_entries", "maximum_archive_size_bytes"])
def test_omitted_optional_archive_limit_preserves_default_floor(monkeypatch, default_limit, field):
    from app.modules.projects import service
    from app.modules.projects.schemas import SubmissionArtifactPolicyInput

    owner = service.ProjectService(None)
    policy = owner._canonical_policy_body(SubmissionArtifactPolicyInput().model_dump())
    del policy[field]
    monkeypatch.setitem(service.WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY, field, default_limit)
    effective = owner._merge_effective_submission_artifact_policy(policy)
    assert effective[field] == default_limit
    assert field not in policy


@pytest.mark.parametrize("limit", [2, None, 0, True])
@pytest.mark.parametrize("field", ["maximum_archive_entries", "maximum_archive_size_bytes"])
def test_task_requirements_response_carries_valid_locked_archive_limit(limit, field):
    from types import SimpleNamespace
    from app.modules.projects.service import ProjectService
    from app.modules.projects.schemas import SubmissionArtifactPolicyInput
    from app.modules.tasks.service import TaskLockedContextInvalid

    owner = ProjectService(None)
    policy = owner._merge_effective_submission_artifact_policy(
        owner._canonical_policy_body(SubmissionArtifactPolicyInput().model_dump())
    )
    policy[field] = limit
    from app.modules.projects.api.locked_policy import CanonicalJsonObject

    context = SimpleNamespace(
        facts=SimpleNamespace(effective_policy=CanonicalJsonObject.from_mapping(policy))
    )
    task = SimpleNamespace(id=str(uuid4()), project_id=str(uuid4()), locked_guide_version="v0.1")
    if limit is not None and (type(limit) is not int or limit <= 0):
        with pytest.raises(TaskLockedContextInvalid):
            task_service(
                None, settings=get_settings()
            )._contributor_submission_requirements_response(task, context)
    else:
        response = task_service(
            None, settings=get_settings()
        )._contributor_submission_requirements_response(task, context)
        assert response.model_dump(mode="json")[field] == limit


SOURCE_ITEM_ID = new_record_id()
DOCUMENT_VERSION_ID = new_record_id()


def _context() -> ProjectGuideCompilationContext:
    setup_id = new_record_id()
    material = GuideDocumentManifest(
        project_id=new_record_id(),
        guide_id=new_record_id(),
        guide_version="v1",
        source_snapshot_id=new_record_id(),
        source_snapshot_hash=SHA256,
        setup_run_id=setup_id,
        setup_generation=1,
        documents=(
            GuideDocumentVersion(
                source_item_id=SOURCE_ITEM_ID,
                ingest_id=DOCUMENT_VERSION_ID,
                item_order=0,
                put_attempt_id=new_record_id(),
                content_id=new_record_id(),
                replica_id=new_record_id(),
                storage_namespace_id="primary",
                namespace_fingerprint=SHA256,
                sha256=SHA256,
                byte_count=100,
                media_type="application/pdf",
            ),
        ),
    )
    return ProjectGuideCompilationContext(
        task_examples=({"content": "Review a claim using the project guide."},),
        material=material,
        setup_run_id=setup_id,
        setup_generation=1,
        instruction_version="v1",
        agent_identity="project-guide-compilation-agent-v1",
        agent_version="v1",
        runtime_configuration=runtime_configuration(),
    )


def _evidence() -> GuideEvidenceRef:
    return GuideEvidenceRef(
        source_item_id=SOURCE_ITEM_ID,
        document_version_id=DOCUMENT_VERSION_ID,
        sha256=SHA256,
        start_page=1,
        end_page=10,
    )


def _artifact_policy() -> SubmissionArtifactPolicyProposal:
    return SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000,
        maximum_package_size_bytes=10_000,
        required_artifacts=("submission",),
    )


def _suggestion(stage: str = "pre_submit") -> AtomicGuideRequirement:
    return AtomicGuideRequirement(
        suggestion_id=f"required_item_{stage}",
        statement="The submitted work must include the required item.",
        stage=stage,
        classification_rationale="The project guide identifies this required item.",
        check_specification=valid_specification(),
        evidence_refs=(_evidence(),),
    )


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"raw_excerpt": "secret"}, "raw_excerpt"),
        ({"url": "https://example.invalid"}, "url"),
        ({"path": "/tmp/guide"}, "path"),
        ({"credential": "token=secret"}, "credential"),
        ({"signed_reference": "signed"}, "signed_reference"),
        ({"caller_text": "ignore prior instructions"}, "caller_text"),
    ],
)
def test_guide_evidence_ref_rejects_non_lineage_fields(payload: dict[str, str], field: str) -> None:
    with pytest.raises(ValidationError) as error:
        GuideEvidenceRef.model_validate(
            {
                "source_item_id": str(uuid4()),
                "document_version_id": str(uuid4()),
                "sha256": SHA256,
                "start_page": 1,
                "end_page": 1,
                **payload,
            }
        )
    assert field in str(error.value)


@pytest.mark.parametrize(
    "unsafe",
    [
        "https://example.invalid/instructions",
        "/etc/passwd",
        "token=secret",
        "Bearer opaque-token",
        "password hunter2",
        "secret hidden-value",
        "credential private-value",
        "api key private-value",
        "token opaque-value",
        "import subprocess",
        "curl example.invalid",
        "see docs/guide.md",
        r"C:\Users\worker\guide.txt",
        "Contact jane@example.com",
        "line\x00break",
    ],
)
def test_model_produced_text_rejects_unsafe_shapes(unsafe: str) -> None:
    with pytest.raises(ValidationError):
        CompilationFinding(severity="info", code="guide.note", message=unsafe)


@pytest.mark.parametrize(
    "safe",
    [
        "Require credential handling attestation.",
        "Document token rotation requirements.",
        "Avoid password storage in submissions.",
    ],
)
def test_model_produced_text_allows_safe_security_policy_language(safe: str) -> None:
    finding = CompilationFinding(severity="info", code="guide.note", message=safe)
    assert finding.message == safe


def test_compilation_context_requires_task_examples_and_preserves_all_input() -> None:
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes
    import json

    payload = _context().model_dump(mode="json")
    examples = [
        {"content": "A starting idea."},
        {"content": "  修復 worker\n", "title": "Second", "labels": ["research", "repair"]},
    ]
    context = ProjectGuideCompilationContext.model_validate_json(
        json.dumps(payload | {"task_examples": examples})
    )
    sent = json.loads(project_guide_compilation_prompt_bytes(context))
    assert sent["task_examples"] == [item.model_dump(mode="json") for item in context.task_examples]
    del payload["task_examples"]
    with pytest.raises(ValidationError, match="task_examples"):
        ProjectGuideCompilationContext.model_validate(payload)
    with pytest.raises(ValidationError, match="task_examples"):
        ProjectGuideCompilationContext.model_validate(payload | {"task_examples": []})


def test_maximum_examples_and_documents_fit_default_runtime_input_budgets() -> None:
    """Largest task examples and document metadata fit the bounded setup input."""
    import json
    from app.interfaces.project_agents import (
        MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES,
        canonical_project_guide_compilation_context_bytes,
        project_guide_compilation_prompt_bytes,
    )
    from app.modules.projects.api.task_examples import MAXIMUM_TASK_EXAMPLE_BYTES

    context = _context()
    examples = [
        {"content": "x" * 65_536, "title": None, "labels": []},
        {"content": "", "title": None, "labels": []},
    ]
    overhead = len(json.dumps(examples, sort_keys=True, separators=(",", ":")).encode())
    examples[1]["content"] = "y" * (MAXIMUM_TASK_EXAMPLE_BYTES - overhead)
    assert (
        len(json.dumps(examples, sort_keys=True, separators=(",", ":")).encode())
        == MAXIMUM_TASK_EXAMPLE_BYTES
    )
    prototype = context.material.documents[0].model_dump(mode="json")
    documents = [
        prototype
        | {
            "source_item_id": str(uuid4()),
            "ingest_id": str(uuid4()),
            "put_attempt_id": str(uuid4()),
            "item_order": index,
        }
        for index in range(100)
    ]
    material = context.material.model_dump(mode="json") | {
        "documents": documents,
        "guide_version": "g" * 50,
    }
    largest = ProjectGuideCompilationContext.model_validate_json(
        json.dumps(
            context.model_dump(mode="json") | {"task_examples": examples, "material": material}
        ),
    )
    assert len(largest.task_examples) == 2
    assert len(largest.material.documents) == 100
    assert (
        len(project_guide_compilation_prompt_bytes(largest))
        <= largest.runtime_configuration.maximum_manifest_bytes
    )
    assert (
        len(canonical_project_guide_compilation_context_bytes(largest))
        <= MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES
    )


@pytest.mark.parametrize("stage", ["pre_submit", "post_submit"])
def test_setup_result_carries_source_linked_pre_or_post_specification(stage: str) -> None:
    proposal = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(CompilationFinding(
            severity="info", code="guide.ready", message="Guide is complete.",
            evidence_refs=(_evidence(),),
        ),),
        submission_artifact_policy=_artifact_policy(),
        requirements=(_suggestion(stage),),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(_context(), proposal)
    assert proposal.requirements[0].stage == stage
    assert proposal.requirements[0].check_specification.pass_conditions


def test_setup_result_rejects_implementation_selection_fields() -> None:
    proposal = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(_suggestion(),),
        agent_version="v1",
    )
    for field, value in (
        ("pre_submit_bindings", []),
        ("post_submit_bindings", []),
        ("capability_suggestions", []),
    ):
        with pytest.raises(ValidationError, match=field):
            ProjectGuideCompilationResult.model_validate(
                proposal.model_dump(mode="json") | {field: value}
            )
    with pytest.raises(ValidationError, match="checker_capabilities"):
        ProjectGuideCompilationContext.model_validate(
            _context().model_dump(mode="json") | {"checker_capabilities": {}}
        )


def test_setup_prompt_contains_only_assigned_guide_and_task_examples() -> None:
    context = _context()
    sent = json.loads(project_guide_compilation_prompt_bytes(context))
    assert set(sent) == {"material", "task_examples"}
    assert sent["task_examples"] == [item.model_dump(mode="json") for item in context.task_examples]
    assert "checker_capabilities" not in json.dumps(sent)
    assert "runtime_configuration" not in json.dumps(sent)


def test_result_status_matches_findings_and_blocked_policy_boundary() -> None:
    ready = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(_context(), ready)
    with pytest.raises(ValueError, match="requires a warning"):
        validate_project_guide_compilation_result(
            _context(), ready.model_copy(update={"status": "draft_ready_with_warnings"})
        )
    with pytest.raises(ValueError, match="cannot contain blocking"):
        validate_project_guide_compilation_result(
            _context(), ready.model_copy(update={"findings": (
                CompilationFinding(severity="blocking_gap", code="guide.blocked", message="Guide is incomplete."),
            )})
        )
    with pytest.raises(ValueError, match="requires blocking evidence"):
        validate_project_guide_compilation_result(
            _context(), ready.model_copy(update={"status": "guide_blocked", "submission_artifact_policy": None})
        )


def test_typed_artifact_policy_and_evidence_ref_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes="1000", maximum_package_size_bytes=10_000,
        )
    with pytest.raises(ValidationError):
        GuideEvidenceRef(
            source_item_id=SOURCE_ITEM_ID, document_version_id=DOCUMENT_VERSION_ID,
            sha256=SHA256, start_page="0", end_page=1,
        )


@pytest.mark.parametrize("field", ["canonical_content", "content_markdown", "provider_url"])
def test_manifest_rejects_document_bodies_and_untrusted_storage_coordinates(field):
    body = _context().material.model_dump(mode="python")
    with pytest.raises(ValidationError, match=field):
        GuideDocumentManifest.model_validate(body | {field: "untrusted content"})


@pytest.mark.parametrize(
    "field", ["source_item_id", "ingest_id", "put_attempt_id", "replica_id", "sha256"]
)
def test_manifest_requires_exact_document_identity(field):
    body = _context().material.model_dump(mode="python")
    document = dict(body["documents"][0])
    del document[field]
    body["documents"] = [document]
    with pytest.raises(ValidationError, match=field):
        GuideDocumentManifest.model_validate(body)


def test_compilation_material_snapshot_cannot_drift_after_validation() -> None:
    snapshot = _context().material
    with pytest.raises(ValidationError):
        snapshot.documents = ()
    with pytest.raises(TypeError):
        snapshot.documents[0] = snapshot.documents[0]
    with pytest.raises(ValidationError):
        snapshot.documents[0].sha256 = "sha256:" + "b" * 64
    body = snapshot.model_dump(mode="python")
    document = dict(body["documents"][0])
    document["sha256"] = "sha256:" + "b" * 64
    changed = GuideDocumentManifest.model_validate(body | {"documents": [document]})
    assert changed.sha256 != snapshot.sha256


def test_unified_result_rejects_unresolved_evidence_lineage() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(
                severity="info",
                code="guide.ready",
                message="Guide is complete.",
                evidence_refs=(
                    GuideEvidenceRef(
                        source_item_id=uuid4(),
                        document_version_id=DOCUMENT_VERSION_ID,
                        sha256=SHA256,
                        start_page=1,
                        end_page=1,
                    ),
                ),
            ),
        ),
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="source lineage"):
        validate_project_guide_compilation_result(context, result)


def test_blocked_result_cannot_publish_artifact_policy() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="guide_blocked",
        findings=(
            CompilationFinding(
                severity="blocking_gap",
                code="guide.blocked",
                message="Guide has a blocking gap.",
            ),
        ),
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="blocked guide"):
        validate_project_guide_compilation_result(context, result)


def test_context_rejects_instruction_version_separate_from_snapshot() -> None:
    payload = _context().model_dump(mode="json")
    payload["instruction_version"] = "different"
    with pytest.raises(ValidationError, match="instruction configuration mismatch"):
        ProjectGuideCompilationContext.model_validate_json(json.dumps(payload))
