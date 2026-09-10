from __future__ import annotations

from app.modules.checkers.catalogue import project_guide_pre_submission_capabilities

from tests.projects.guide_compilation.helpers import runtime_configuration

from uuid import UUID, uuid4

from app.core.hashing import canonical_json_hash

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    PreSubmissionBindingProposal,
    PostSubmissionBindingProposal,
    CapabilityParameter,
    CapabilitySuggestion,
    CompilationFinding,
    GuideEvidenceRef,
    PlatformCoverageRef,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
    validate_project_guide_compilation_result,
)
from app.modules.projects.api.guide_documents import GuideDocumentManifest, GuideDocumentVersion
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerClassification,
    build_pre_submission_checker_catalogue,
)
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.post_submit_policy import DEFAULT_DURABLE_CHECKERS


SHA256 = "sha256:" + "a" * 64
SOURCE_ITEM_ID = UUID("11111111-1111-1111-1111-111111111111")
DOCUMENT_VERSION_ID = UUID("22222222-2222-2222-2222-222222222222")


def _context() -> ProjectGuideCompilationContext:
    setup_id = uuid4()
    material = GuideDocumentManifest(
        project_id=uuid4(), guide_id=uuid4(), guide_version="v1",
        source_snapshot_id=uuid4(), source_snapshot_hash=SHA256,
        setup_run_id=setup_id, setup_generation=1,
        documents=(GuideDocumentVersion(
            source_item_id=SOURCE_ITEM_ID, ingest_id=DOCUMENT_VERSION_ID, item_order=0,
            put_attempt_id=uuid4(), content_id=uuid4(), replica_id=uuid4(),
            storage_namespace_id="primary", namespace_fingerprint=SHA256,
            sha256=SHA256, byte_count=100, media_type="application/pdf",
        ),),
    )
    return ProjectGuideCompilationContext(
        task_examples=({"content": "Review a claim using the project guide."},),
        material=material,
        setup_run_id=setup_id,
        setup_generation=1,
        instruction_version="v1",
        agent_identity="project-guide-compilation-agent-v1",
        agent_version="v1",
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=current_post_submit_catalogue(),
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


def test_pre_submission_projection_preserves_exact_manifest_and_selectability() -> None:
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.quality.placeholder_signal"})
    )
    projection = project_guide_pre_submission_capabilities(catalogue)

    assert projection.manifest_sha256 == catalogue.manifest_sha256
    assert len(projection.definitions) == len(catalogue.entries)
    assert [item.stable_id for item in projection.definitions] == [
        item.stable_id for item in catalogue.entries
    ]
    for definition, source in zip(projection.definitions, catalogue.entries, strict=True):
        projected = definition.model_dump(mode="json")
        selectable = projected.pop("selectable")
        assert projected == source.manifest_entry()
        assert selectable is (
            source.state.value == "enabled"
            and source.dispatch_kind.value == "policy_primitive"
            and source.phase.value == "project_policy"
        )
    disabled = next(
        item
        for item in projection.definitions
        if item.stable_id == "artifact.quality.placeholder_signal"
    )
    assert disabled.state == "disabled"
    assert disabled.selectable is False
    assert projection.available is True


def test_pre_submission_projection_reports_disabled_mandatory_unavailable() -> None:
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
    )
    projection = project_guide_pre_submission_capabilities(catalogue)
    assert projection.available is False
    assert projection.definitions[0].classification == (
        PreSubmissionCheckerClassification.MANDATORY_SECURITY.value
    )
    assert projection.definitions[0].selectable is False


def test_compilation_rejects_unavailable_mandatory_pre_submission_projection() -> None:
    context = _context().model_copy(
        update={
            "pre_submission_capabilities": project_guide_pre_submission_capabilities(
                build_pre_submission_checker_catalogue(
                    disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
                )
            )
        }
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(severity="info", code="guide.ready", message="Guide is complete."),
        ),
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="projection is unavailable"):
        validate_project_guide_compilation_result(context, result)


def test_post_submission_projection_uses_registry_and_frozen_default_truth() -> None:
    projection = current_post_submit_catalogue()
    by_name = {item.capability_id: item for item in projection.definitions}

    assert projection.source_version == "v0.1"
    assert set(DEFAULT_DURABLE_CHECKERS).issubset(by_name)
    assert {name for name, item in by_name.items() if item.platform_default} == set(
        DEFAULT_DURABLE_CHECKERS
    )
    assert [item.capability_id for item in projection.definitions if item.selectable] == [
        "check_acceptance_criteria_present"
    ]
    assert all(item.stage == "post_submit" for item in projection.definitions)


def test_post_submission_projection_rejects_sparse_definitions() -> None:
    from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue

    projection = current_post_submit_catalogue()
    body = projection.model_dump(mode="json")
    sparse_keys = {"capability_id", "capability_version", "stage", "platform_default", "selectable"}
    body["definitions"] = [
        {key: value for key, value in item.items() if key in sparse_keys}
        for item in body["definitions"]
    ]
    body["manifest_sha256"] = canonical_json_hash(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    with pytest.raises(ValidationError, match="Field required"):
        PostSubmitCatalogue.model_validate(body)


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
        CapabilitySuggestion(requirement_id="r001", stage="pre_submit",
                             title="new checker", rationale=unsafe, evidence_refs=(_evidence(),))


@pytest.mark.parametrize(
    "safe",
    [
        "Require credential handling attestation.",
        "Document token rotation requirements.",
        "Avoid password storage in submissions.",
    ],
)
def test_model_produced_text_allows_safe_security_policy_language(safe: str) -> None:
    suggestion = CapabilitySuggestion(requirement_id="r001", stage="pre_submit",
                                      title="security guidance", rationale=safe, evidence_refs=(_evidence(),))
    assert suggestion.rationale == safe


def test_compilation_context_requires_task_examples_and_preserves_all_input() -> None:
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes
    import json

    payload = _context().model_dump(mode="json")
    examples = [{"content": "A starting idea."}, {"content": "  修復 worker\n", "title": "Second", "labels": ["research", "repair"]}]
    context = ProjectGuideCompilationContext.model_validate(payload | {"task_examples": examples})
    sent = json.loads(project_guide_compilation_prompt_bytes(context))
    assert sent["task_examples"] == [item.model_dump(mode="json") for item in context.task_examples]
    del payload["task_examples"]
    with pytest.raises(ValidationError, match="task_examples"):
        ProjectGuideCompilationContext.model_validate(payload)
    with pytest.raises(ValidationError, match="task_examples"):
        ProjectGuideCompilationContext.model_validate(payload | {"task_examples": []})


def test_maximum_examples_and_documents_fit_default_runtime_input_budgets() -> None:
    """Admission's largest text list fits real catalogue and maximum file metadata."""
    import json
    from app.interfaces.project_agents import (
        MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES,
        canonical_project_guide_compilation_context_bytes,
        project_guide_compilation_prompt_bytes,
    )
    from app.modules.projects.api.task_examples import MAXIMUM_TASK_EXAMPLE_BYTES

    context = _context()
    examples = [{"content": "x" * 65_536, "title": None, "labels": []},
                {"content": "", "title": None, "labels": []}]
    overhead = len(json.dumps(examples, sort_keys=True, separators=(",", ":")).encode())
    examples[1]["content"] = "y" * (MAXIMUM_TASK_EXAMPLE_BYTES - overhead)
    assert len(json.dumps(examples, sort_keys=True, separators=(",", ":")).encode()) == MAXIMUM_TASK_EXAMPLE_BYTES
    prototype = context.material.documents[0].model_dump(mode="json")
    documents = [prototype | {
        "source_item_id": str(uuid4()), "ingest_id": str(uuid4()),
        "put_attempt_id": str(uuid4()), "item_order": index,
    } for index in range(100)]
    material = context.material.model_dump(mode="json") | {"documents": documents, "guide_version": "g" * 50}
    largest = ProjectGuideCompilationContext.model_validate(
        context.model_dump(mode="json") | {"task_examples": examples, "material": material},
    )
    assert len(largest.task_examples) == 2
    assert len(largest.material.documents) == 100
    assert len(project_guide_compilation_prompt_bytes(largest)) <= largest.runtime_configuration.maximum_manifest_bytes
    assert len(canonical_project_guide_compilation_context_bytes(largest)) <= MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES


def test_unified_result_accepts_exact_stage_capability_and_closed_parameters() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(severity="info", code="guide.ready", message="Guide is complete."),
        ),
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Validate the submission packet.",
                disposition="supported_pre_submit",
                evidence_refs=(_evidence(),),
            ),
            AtomicGuideRequirement(
                requirement_id="requirement.acceptance",
                statement="Check acceptance criteria coverage.",
                disposition="supported_post_submit",
            ),
        ),
        pre_submit_bindings=(
            PreSubmissionBindingProposal(
                requirement_id="requirement.packet",
                capability_id="policy.file_size.limit",
                capability_version="v1",
                stage="pre_submit",
            ),
        ),
        post_submit_bindings=(
            PostSubmissionBindingProposal(
                requirement_id="requirement.acceptance",
                capability_id="check_acceptance_criteria_present",
                capability_version="v0.1",
                stage="post_submit",
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(context, result)


@pytest.mark.parametrize(
    ("capability_id", "version", "stage", "expected_error"),
    [
        ("submission.packet.required_fields", "v1", "pre_submit", "binding is invalid"),
        ("policy.submission_packet.validate", "stale", "pre_submit", "version is stale"),
        ("unknown.capability", "v1", "pre_submit", "binding is invalid"),
        (
            "check_submission_packet",
            "v0.1",
            "post_submit",
            "binding is invalid",
        ),
        (
            "check_acceptance_criteria_present",
            "v0.1",
            "pre_submit",
            "binding is invalid",
        ),
    ],
)
def test_unified_result_rejects_default_unknown_stale_and_wrong_stage_bindings(
    capability_id: str, version: str, stage: str, expected_error: str
) -> None:
    context = _context()
    disposition = "supported_post_submit" if stage == "post_submit" else "supported_pre_submit"
    binding_type = PreSubmissionBindingProposal if stage == "pre_submit" else PostSubmissionBindingProposal
    binding = binding_type(
        requirement_id="requirement.one",
        capability_id=capability_id,
        capability_version=version,
        stage=stage,
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.one",
                statement="Validate one requirement.",
                disposition=disposition,
            ),
        ),
        pre_submit_bindings=(binding,) if stage == "pre_submit" else (),
        post_submit_bindings=(binding,) if stage == "post_submit" else (),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match=expected_error):
        validate_project_guide_compilation_result(context, result)


def test_unified_result_rejects_open_nested_or_executable_configuration() -> None:
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value={"command": "sh"})
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value="import subprocess")
    with pytest.raises(ValidationError):
        PreSubmissionBindingProposal(
            requirement_id="requirement.packet",
            capability_id="policy.submission_packet.validate",
            capability_version="https://unsafe.invalid",
            stage="pre_submit",
        )
    with pytest.raises(ValidationError):
        PlatformCoverageRef(
            capability_id="artifact.outer_zip.valid",
            capability_version="https://unsafe.invalid",
            stage="pre_submit",
        )
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value=float("nan"))
    with pytest.raises(ValidationError):
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes="1000",
            maximum_package_size_bytes=10_000,
        )
    with pytest.raises(ValidationError):
        GuideEvidenceRef(
            source_item_id=SOURCE_ITEM_ID,
            document_version_id=DOCUMENT_VERSION_ID,
            sha256=SHA256,
            start_page="0",
            end_page=1,
        )


def test_pre_submission_projection_resource_budget_is_deeply_frozen() -> None:
    projection = project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue())
    with pytest.raises(ValidationError):
        projection.definitions[0].resource_budget.maximum_results = 99


@pytest.mark.parametrize("field", ["canonical_content", "content_markdown", "provider_url"])
def test_manifest_rejects_document_bodies_and_untrusted_storage_coordinates(field):
    body = _context().material.model_dump(mode="python")
    with pytest.raises(ValidationError, match=field):
        GuideDocumentManifest.model_validate(body | {field: "untrusted content"})


@pytest.mark.parametrize("field", ["source_item_id", "ingest_id", "put_attempt_id", "replica_id", "sha256"])
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


def test_supported_requirement_requires_exactly_one_binding() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Validate the submission packet.",
                disposition="supported_pre_submit",
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="must have one binding"):
        validate_project_guide_compilation_result(context, result)


def test_post_submission_binding_rejects_unowned_parameters() -> None:
    context = _context()
    binding = PostSubmissionBindingProposal(
        requirement_id="requirement.one",
        capability_id="check_acceptance_criteria_present",
        capability_version="v0.1",
        stage="post_submit",
        parameters=(CapabilityParameter(name="unowned_parameter", value=True),),
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.one",
                statement="Validate one requirement.",
                disposition="supported_post_submit",
            ),
        ),
        post_submit_bindings=(binding,),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="Extra inputs"):
        validate_project_guide_compilation_result(context, result)


@pytest.mark.parametrize(
    ("status", "finding_severity", "disposition", "expected_error"),
    [
        ("draft_ready", "blocking_gap", "informational", "cannot contain blocking"),
        ("draft_ready", "info", "guide_blocker", "cannot contain blocking"),
        ("draft_ready", "warning", "informational", "cannot contain warnings"),
        (
            "draft_ready_with_warnings",
            "info",
            "informational",
            "requires a warning",
        ),
        ("guide_blocked", "info", "informational", "requires blocking evidence"),
    ],
)
def test_result_status_must_match_findings_and_blocking_dispositions(
    status: str, finding_severity: str, disposition: str, expected_error: str
) -> None:
    result = ProjectGuideCompilationResult(
        status=status,
        findings=(
            CompilationFinding(
                severity=finding_severity,
                code="guide.status",
                message="Guide status evidence.",
            ),
        ),
        submission_artifact_policy=(None if status == "guide_blocked" else _artifact_policy()),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.status",
                statement="Check guide status.",
                disposition=disposition,
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match=expected_error):
        validate_project_guide_compilation_result(_context(), result)


@pytest.mark.parametrize(
    "invalid_capability_id",
    ["policy.submission_packet.validate", "artifact.quality.placeholder_signal"],
)
def test_platform_coverage_requires_exact_mandatory_platform_capability(
    invalid_capability_id: str,
) -> None:
    context = _context()
    valid = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.zip",
                statement="Validate the outer ZIP.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="artifact.outer_zip.valid",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(context, valid)

    invalid = valid.model_copy(
        update={
            "requirements": (
                valid.requirements[0].model_copy(
                    update={
                        "platform_coverage": PlatformCoverageRef(
                            capability_id=invalid_capability_id,
                            capability_version="v1",
                            stage="pre_submit",
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="canonical truth"):
        validate_project_guide_compilation_result(context, invalid)


def test_platform_coverage_rejects_disabled_platform_capability() -> None:
    context = _context().model_copy(
        update={
            "pre_submission_capabilities": project_guide_pre_submission_capabilities(
                build_pre_submission_checker_catalogue(
                    disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
                )
            )
        }
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.zip",
                statement="Validate the outer ZIP.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="artifact.outer_zip.valid",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="projection is unavailable"):
        validate_project_guide_compilation_result(context, result)


def test_platform_coverage_accepts_exact_post_submit_default() -> None:
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Run the platform submission-packet check.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="check_submission_packet",
                    capability_version="v0.1",
                    stage="post_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(_context(), result)


def test_platform_coverage_ref_is_required_only_for_platform_disposition() -> None:
    missing = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.coverage",
                statement="Require canonical coverage proof.",
                disposition="platform_covered",
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="requires canonical proof"):
        validate_project_guide_compilation_result(_context(), missing)

    misplaced = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.info",
                statement="Record an informational requirement.",
                disposition="informational",
                platform_coverage=PlatformCoverageRef(
                    capability_id="artifact.outer_zip.valid",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="cannot claim platform coverage"):
        validate_project_guide_compilation_result(_context(), misplaced)


def test_blocked_result_cannot_publish_policy_or_bindings() -> None:
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


@pytest.mark.parametrize("parameters", [[], [{"name": "maximum_file_size_bytes", "value": 1000}]])
def test_pre_submission_binding_rejects_duplicate_policy_configuration(parameters):
    """The sole intake configuration is the artifact policy, never a second copy."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        PreSubmissionBindingProposal(
            requirement_id="requirement.size", capability_id="policy.file_size.limit",
            capability_version="v1", stage="pre_submit", parameters=parameters,
        )


def test_context_rejects_instruction_version_separate_from_snapshot() -> None:
    payload = _context().model_dump(mode="json")
    payload["instruction_version"] = "different"
    with pytest.raises(ValidationError, match="instruction configuration mismatch"):
        ProjectGuideCompilationContext.model_validate(payload)
